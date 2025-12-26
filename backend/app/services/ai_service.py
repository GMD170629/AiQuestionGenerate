"""
LLM 题目生成模块
功能：调用 OpenRouter API，基于教材切片生成各类习题
"""

import os
import sys
import json
import random
import logging
from typing import List, Dict, Any, Optional
import httpx
from app.models import Question, QuestionList, ChunkGenerationPlan, TextbookGenerationPlan
from app.services.markdown_service import MarkdownProcessor
from app.core.db import db
from app.services.knowledge_graph_service import knowledge_graph
from prompts import PromptManager
from prompts import PromptManager

# 配置日志
logger = logging.getLogger(__name__)

# 确保使用 UTF-8 编码
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    import io
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


# OpenRouter API 配置（默认值，实际配置从数据库读取）
DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"


# 配置常量
BATCH_SIZE = 5  # 每批生成的题目数量（防止超时）
MAX_RETRIES = 3  # 最大重试次数
REQUEST_TIMEOUT = 600.0  # 请求超时时间（秒）- 默认值：10分钟
STREAM_TIMEOUT = 1800.0  # 流式请求超时时间（秒）- 默认值：30分钟（确保流式传输不会断开）

# Gemini 模型需要更长的超时时间
GEMINI_TIMEOUT_MULTIPLIER = 1.5  # Gemini 模型的超时倍数（基础时间已足够长）
GEMINI_RETRY_DELAY = 5.0  # Gemini 模型重试延迟（秒）

# Token 限制配置
# 不同任务类型的基础 token 限制
MIN_QUESTION_GENERATION_TOKENS = 2000  # 题目生成最小 tokens
MAX_QUESTION_GENERATION_TOKENS = 16000  # 题目生成最大 tokens（从 8000 提高到 16000）
TOKENS_PER_QUESTION = 500  # 每道题估算的 tokens 数

MIN_KNOWLEDGE_EXTRACTION_TOKENS = 2000  # 知识提取最小 tokens
MAX_KNOWLEDGE_EXTRACTION_TOKENS = 4000  # 知识提取最大 tokens（从 2000 提高到 4000）

MIN_DEPENDENCY_BUILDING_TOKENS = 8000  # 依赖构建最小 tokens
MAX_DEPENDENCY_BUILDING_TOKENS = 32000  # 依赖构建最大 tokens

# 不同模型的最大输出 token 限制（根据模型能力调整）
MODEL_MAX_OUTPUT_TOKENS = {
    # Gemini 系列支持更大的输出
    "gemini": 32000,
    "google/gemini": 32000,
    # GPT-4 系列
    "gpt-4": 16000,
    "gpt-4-turbo": 16000,
    "gpt-4o": 16000,
    # Claude 系列
    "claude": 16000,
    "anthropic/claude": 16000,
    # 默认值
    "default": 16000,
}


def get_timeout_config(model: Optional[str] = None, is_stream: bool = False) -> httpx.Timeout:
    """
    根据模型类型返回合适的超时配置
    
    对于流式请求，read timeout 设置得很长（30分钟），确保在接收数据时不会断开连接。
    httpx 的 read timeout 在流式传输时会在每次读取数据时重置计时器，
    所以只要数据在持续传输，就不会超时。
    
    Args:
        model: 模型名称（如 "google/gemini-3-pro-preview"）
        is_stream: 是否为流式请求
        
    Returns:
        httpx.Timeout 对象，包含细粒度的超时配置
    """
    # 检测是否为 Gemini 模型
    is_gemini = model and ("gemini" in model.lower() or "google" in model.lower())
    
    # 基础超时时间
    if is_stream:
        # 流式请求使用更长的超时时间，确保在接收数据时不会断开
        # 30分钟足够长，httpx 会在每次读取数据时重置计时器
        base_timeout = STREAM_TIMEOUT
    else:
        # 普通请求：至少10分钟
        base_timeout = REQUEST_TIMEOUT
    
    # Gemini 模型使用更长的超时时间
    if is_gemini:
        base_timeout = base_timeout * GEMINI_TIMEOUT_MULTIPLIER
    
    # 设置细粒度的超时配置
    # connect: 连接超时（建立连接的时间）
    # read: 读取超时（等待响应的时间）
    #   - 对于流式请求：设置为很长的值（30分钟），确保在接收数据时不会断开
    #   - 对于普通请求：设置为10分钟以上
    # write: 写入超时（发送请求的时间）
    # pool: 连接池超时
    return httpx.Timeout(
        connect=60.0,  # 连接超时：60秒（足够建立连接）
        read=base_timeout,  # 读取超时：根据模型和请求类型调整（流式请求30分钟，普通请求10分钟以上）
        write=120.0,  # 写入超时：120秒（足够发送请求，包括大请求）
        pool=60.0,  # 连接池超时：60秒
    )


def get_max_output_tokens(model: Optional[str] = None, task_type: str = "question_generation") -> int:
    """
    根据模型类型和任务类型返回合适的最大输出 token 限制
    
    Args:
        model: 模型名称（如 "google/gemini-3-pro-preview"）
        task_type: 任务类型，可选值：
            - "question_generation": 题目生成
            - "knowledge_extraction": 知识提取
            - "dependency_building": 依赖构建
    
    Returns:
        最大输出 token 限制
    """
    # 确定任务的基础限制
    if task_type == "question_generation":
        base_max = MAX_QUESTION_GENERATION_TOKENS
    elif task_type == "knowledge_extraction":
        base_max = MAX_KNOWLEDGE_EXTRACTION_TOKENS
    elif task_type == "dependency_building":
        base_max = MAX_DEPENDENCY_BUILDING_TOKENS
    else:
        base_max = MAX_QUESTION_GENERATION_TOKENS  # 默认值
    
    # 根据模型类型调整限制
    if not model:
        return base_max
    
    model_lower = model.lower()
    
    # 检查模型是否支持更大的输出
    for key, max_tokens in MODEL_MAX_OUTPUT_TOKENS.items():
        if key in model_lower:
            # 返回任务限制和模型限制中的较小值
            return min(base_max, max_tokens)
    
    # 默认返回任务的基础限制
    return base_max


def calculate_max_tokens_for_questions(
    question_count: int,
    model: Optional[str] = None
) -> int:
    """
    计算题目生成所需的最大 tokens
    
    Args:
        question_count: 题目数量
        model: 模型名称
    
    Returns:
        最大 tokens 数
    """
    estimated_tokens = question_count * TOKENS_PER_QUESTION
    
    # 获取模型支持的最大输出 tokens
    model_max = get_max_output_tokens(model, "question_generation")
    
    # 返回估算值和限制值之间的合理值
    return min(model_max, max(MIN_QUESTION_GENERATION_TOKENS, estimated_tokens))


def get_retry_delay(model: Optional[str] = None, retry_count: int = 0) -> float:
    """
    根据模型类型和重试次数返回重试延迟时间
    
    Args:
        model: 模型名称
        retry_count: 当前重试次数
        
    Returns:
        重试延迟时间（秒）
    """
    # 检测是否为 Gemini 模型
    is_gemini = model and ("gemini" in model.lower() or "google" in model.lower())
    
    if is_gemini:
        # Gemini 模型使用更长的重试延迟，并随重试次数递增
        base_delay = GEMINI_RETRY_DELAY
        return base_delay + (retry_count * 2.0)  # 每次重试增加2秒
    else:
        # 其他模型使用较短的重试延迟
        return 2.0 + (retry_count * 1.0)  # 基础2秒，每次重试增加1秒


# 兼容性：保留 detect_code_in_text 函数，但内部逻辑已移至 PromptManager
def detect_code_in_text(text: str) -> bool:
    """
    检测文本中是否包含代码（兼容性函数）
    
    Args:
        text: 要检测的文本
        
    Returns:
        如果包含代码返回 True，否则返回 False
    """
    # 使用 PromptManager 的检测逻辑（通过私有方法模拟）
    code_indicators = [
        '```',  # Markdown 代码块
        'def ',  # Python 函数定义
        'class ',  # 类定义
        'function ',  # JavaScript 函数
        'import ',  # 导入语句
        'return ',  # 返回语句
        'if ',  # 条件语句
        'for ',  # 循环语句
        'while ',  # while 循环
    ]
    
    if '```' in text:
        return True
    
    code_count = sum(1 for indicator in code_indicators[1:] if indicator in text)
    return code_count >= 3


def get_hierarchy_context(node_id: str) -> Dict[str, Any]:
    """
    获取知识点的基本信息（已简化，不再使用层级结构）
    
    Args:
        node_id: 知识点节点 ID
        
    Returns:
        包含知识点信息的字典：
        - core_concept: 核心概念
        - hierarchy_path: 概念名称（用于兼容）
    """
    result = {
        "core_concept": None,
        "hierarchy_path": ""
    }
    
    try:
        # 获取当前节点
        current_node = db.get_knowledge_node(node_id)
        if not current_node:
            return result
        
        current_concept = current_node.get("core_concept", "")
        result["core_concept"] = current_concept
        result["hierarchy_path"] = current_concept
    
    except Exception as e:
        print(f"警告：获取知识点信息失败: {e}")
    
    return result


def get_dependency_edges(node_id: str) -> List[Dict[str, Any]]:
    """
    获取知识点的横向依赖关系（基于 knowledge_dependencies 表）
    
    Args:
        node_id: 知识点节点 ID
        
    Returns:
        依赖关系列表，每个元素包含：
        - target_node_id: 被依赖的节点 ID
        - target_concept: 被依赖的概念名称
        - dependency_type: 依赖类型
    """
    try:
        dependencies = db.get_node_dependencies(node_id)
        result = []
        
        for dep in dependencies:
            target_node_id = dep.get("target_node_id")
            if target_node_id:
                target_node = db.get_knowledge_node(target_node_id)
                if target_node:
                    result.append({
                        "target_node_id": target_node_id,
                        "target_concept": target_node.get("core_concept", ""),
                        "dependency_type": dep.get("dependency_type", "depends_on")
                    })
        
        return result
    except Exception as e:
        print(f"警告：获取依赖关系失败: {e}")
        return []


def extract_knowledge_from_chunks(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    从前置 chunks 中提取知识点信息（核心概念、前置依赖、Bloom 层级等）
    
    这是新的出题流程的第一步：从 chunks 中提取知识点，而不是直接使用文本
    升级版：包含层级背景和横向依赖关系
    
    Args:
        chunks: 切片列表
        
    Returns:
        包含完整知识点信息的字典：
        - core_concept: 核心概念
        - node_id: 知识点节点 ID
        - level: 知识点层级（1, 2, 或 3）
        - bloom_level: Bloom 认知层级
        - prerequisites: 前置依赖知识点列表（字符串列表，已废弃）
        - prerequisites_context: 前置知识点上下文列表（详细信息，基于知识图谱）
        - dependency_edges: 横向依赖关系列表（基于 knowledge_dependencies 表）
        - hierarchy_context: 层级背景信息（一级、二级、三级）
        - confusion_points: 学生易错点列表
        - application_scenarios: 应用场景列表
        - knowledge_summary: 知识点摘要（用于生成题目）
    """
    result = {
        "core_concept": None,
        "node_id": None,
        "level": 3,  # 默认三级
        "bloom_level": None,
        "prerequisites": [],
        "prerequisites_context": [],
        "dependency_edges": [],
        "hierarchy_context": {},
        "confusion_points": [],
        "application_scenarios": [],
        "knowledge_summary": ""
    }
    
    try:
        # 尝试从数据库获取 chunks 的知识点节点
        if not chunks:
            return result
        
        # 收集所有 chunks 的知识点信息
        all_knowledge_nodes = []
        
        for chunk in chunks:
            chunk_content = chunk.get("content", "")
            chunk_metadata = chunk.get("metadata", {})
            file_id = chunk_metadata.get("source", "")
            
            if not file_id:
                continue
            
            # 提取 file_id（如果 source 是文件路径）
            import re
            uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
            uuid_match = re.search(uuid_pattern, file_id, re.IGNORECASE)
            actual_file_id = uuid_match.group(0) if uuid_match else file_id
            
            # 查询数据库，找到匹配的 chunk_id
            with db._get_connection() as conn:
                cursor = conn.cursor()
                content_prefix = chunk_content[:200] if len(chunk_content) > 200 else chunk_content
                content_length = len(chunk_content)
                
                cursor.execute("""
                    SELECT chunk_id FROM chunks 
                    WHERE file_id = ? 
                    AND LENGTH(content) BETWEEN ? AND ?
                    AND content LIKE ?
                    LIMIT 1
                """, (actual_file_id, max(0, content_length - 100), content_length + 100, content_prefix + "%"))
                row = cursor.fetchone()
                
                if row:
                    chunk_id = row["chunk_id"]
                    # 获取该 chunk 的知识点节点
                    knowledge_nodes = db.get_chunk_knowledge_nodes(chunk_id)
                    all_knowledge_nodes.extend(knowledge_nodes)
        
        # 如果没有找到知识点节点，尝试从第一个 chunk 提取
        if not all_knowledge_nodes and chunks:
            # 可以在这里调用 LLM 实时提取知识点（如果需要）
            # 但为了性能，我们优先使用已存储的知识点
            pass
        
        # 合并所有知识点信息
        if all_knowledge_nodes:
            # 使用第一个知识点节点作为主要知识点
            primary_kn = all_knowledge_nodes[0]
            node_id = primary_kn.get("node_id")
            
            result["core_concept"] = primary_kn.get("core_concept")
            result["node_id"] = node_id
            result["bloom_level"] = primary_kn.get("bloom_level")
            result["prerequisites"] = primary_kn.get("prerequisites", [])
            result["confusion_points"] = primary_kn.get("confusion_points", [])
            result["application_scenarios"] = primary_kn.get("application_scenarios") or []
            
            # 获取层级背景（向上溯源）
            if node_id:
                result["hierarchy_context"] = get_hierarchy_context(node_id)
            
            # 获取横向依赖关系（基于 knowledge_dependencies 表）
            if node_id:
                result["dependency_edges"] = get_dependency_edges(node_id)
            
            # 获取前置知识点上下文（通过知识图谱）
            if result["core_concept"]:
                prerequisites_context = knowledge_graph.get_prerequisite_context(
                    result["core_concept"], max_depth=3, max_concepts=3
                )
                result["prerequisites_context"] = prerequisites_context
            
            # 构建知识点摘要（用于生成题目）
            summary_parts = []
            
            # 添加层级路径
            hierarchy_path = result["hierarchy_context"].get("hierarchy_path", "")
            if hierarchy_path:
                summary_parts.append(f"层级路径：{hierarchy_path}")
            
            if result["core_concept"]:
                summary_parts.append(f"核心概念：{result['core_concept']}")
            
            if result["bloom_level"]:
                bloom_names = {
                    1: "记忆",
                    2: "理解",
                    3: "应用",
                    4: "分析",
                    5: "评价",
                    6: "创造"
                }
                summary_parts.append(f"认知层级：{bloom_names.get(result['bloom_level'], '未知')}（Level {result['bloom_level']}）")
            
            # 添加横向依赖信息
            if result["dependency_edges"]:
                dep_concepts = [dep["target_concept"] for dep in result["dependency_edges"][:3]]
                summary_parts.append(f"前置依赖：{', '.join(dep_concepts)}")
            
            if result["confusion_points"]:
                summary_parts.append(f"易错点：{', '.join(result['confusion_points'][:3])}")
            
            if result["application_scenarios"]:
                summary_parts.append(f"应用场景：{', '.join(result['application_scenarios'][:2])}")
            
            result["knowledge_summary"] = "；".join(summary_parts)
            
            # 如果没有摘要，使用核心概念作为摘要
            if not result["knowledge_summary"] and result["core_concept"]:
                result["knowledge_summary"] = f"核心概念：{result['core_concept']}"
    
    except Exception as e:
        # 如果获取失败，不影响题目生成
        print(f"警告：从 chunks 提取知识点失败: {e}")
        import traceback
        traceback.print_exc()
    
    return result


def build_knowledge_based_prompt(knowledge_info: Dict[str, Any], 
                                 chunks: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    基于知识点信息构建题目生成提示词
    
    Args:
        knowledge_info: 知识点信息字典（来自 extract_knowledge_from_chunks）
        chunks: 原始 chunks（仅作为参考，不直接使用）
        
    Returns:
        构建好的提示词字符串
    """
    # 提取知识点信息
    core_concept = knowledge_info.get("core_concept")
    bloom_level = knowledge_info.get("bloom_level")
    knowledge_summary = knowledge_info.get("knowledge_summary", "")
    prerequisites_context = knowledge_info.get("prerequisites_context", [])
    confusion_points = knowledge_info.get("confusion_points", [])
    application_scenarios = knowledge_info.get("application_scenarios", [])
    
    # 提取参考内容（仅显示前500字符）
    reference_content = None
    if chunks and len(chunks) > 0:
        reference_content = chunks[0].get("content", "")[:500]
    
    # 直接使用 PromptManager 构建提示词（所有提示词组装逻辑已在 prompts 模块中定义）
    return PromptManager.build_knowledge_based_prompt(
        core_concept=core_concept,
        bloom_level=bloom_level,
        knowledge_summary=knowledge_summary,
        prerequisites_context=prerequisites_context,
        confusion_points=confusion_points,
        application_scenarios=application_scenarios,
        reference_content=reference_content
    )


def validate_question_distribution(questions: List[Dict[str, Any]], 
                                   knowledge_nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证题目分布是否符合三层图谱结构的阶梯式分布要求
    
    确保生成的习题集是从"基础概念（Level 1）"到"具体实现（Level 3）"阶梯式分布的
    
    Args:
        questions: 生成的题目列表
        knowledge_nodes: 相关的知识点节点列表
        
    Returns:
        验证结果字典：
        - is_valid: 是否符合要求
        - level_distribution: 各层级的题目分布统计
        - suggestions: 改进建议
    """
    result = {
        "is_valid": True,
        "level_distribution": {
            "level_1": 0,
            "level_2": 0,
            "level_3": 0,
            "unknown": 0
        },
        "suggestions": []
    }
    
    try:
        # 统计各层级的题目数量
        for question in questions:
            # 尝试从题目中提取关联的知识点（如果有的话）
            # 这里假设题目可能包含章节信息或知识点信息
            # 实际实现可能需要更复杂的匹配逻辑
            
            # 暂时标记为未知，实际应用中需要建立题目与知识点的关联
            result["level_distribution"]["unknown"] += 1
        
        # 如果有知识点节点信息，可以统计知识点数量
        if knowledge_nodes:
            total_nodes = len(knowledge_nodes)
            if total_nodes == 0:
                result["suggestions"].append("未找到相关知识点，建议先提取知识点")
        
        # 如果没有建议，说明分布合理
        if not result["suggestions"]:
            result["suggestions"].append("题目分布合理，符合阶梯式学习路径")
    
    except Exception as e:
        print(f"警告：验证题目分布失败: {e}")
        result["is_valid"] = True  # 验证失败不影响题目生成
    
    return result


def build_system_prompt(include_type_requirements: bool = True, mode: Optional[str] = None) -> str:
    """
    构建系统提示词（包含通用规则和题型要求）
    
    Args:
        include_type_requirements: 是否包含通用题型要求说明
        mode: 出题模式（"课后习题" 或 "提高习题"），如果为 None 则使用基础提示词
        
    Returns:
        完整的系统提示词字符串
    """
    return PromptManager.build_system_prompt(include_type_requirements=include_type_requirements, mode=mode)


    # build_task_specific_prompt 函数已废弃，使用 PromptManager.build_question_generation_user_prompt 替代


class OpenRouterClient:
    """OpenRouter API 客户端"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, api_endpoint: Optional[str] = None):
        """
        初始化 OpenRouter 客户端
        
        Args:
            api_key: OpenRouter API 密钥（如果为 None，则从数据库读取）
            model: 模型名称（如果为 None，则从数据库读取）
            api_endpoint: API端点URL（如果为 None，则从数据库读取）
        """
        # 优先使用传入的参数，否则从数据库读取配置
        config = db.get_ai_config()
        
        self.api_key = api_key if api_key else config.get("api_key", "")
        self.model = model if model else config.get("model", "openai/gpt-4o-mini")
        self.api_endpoint = api_endpoint if api_endpoint else config.get("api_endpoint", DEFAULT_API_URL)
        
        if not self.api_key:
            raise ValueError(
                "OpenRouter API 密钥未设置。请在前端设置页面配置 API 密钥。"
            )
        
        # 打印配置信息（用于调试，生产环境可以移除或改为日志）
        print(f"[OpenRouterClient] API端点: {self.api_endpoint}")
        print(f"[OpenRouterClient] 使用模型: {self.model}")
        print(f"[OpenRouterClient] API Key 已设置: {'是' if self.api_key else '否'} (长度: {len(self.api_key) if self.api_key else 0})")
    
    async def _continue_generation_on_length_limit(
        self,
        messages: List[Dict[str, Any]],
        accumulated_text: str,
        headers: Dict[str, Any],
        payload_template: Dict[str, Any],
        timeout_config: httpx.Timeout,
        on_status_update=None,
        max_continuations: int = 3
    ) -> str:
        """
        当检测到 finish_reason == "length" 时，继续生成剩余内容
        
        Args:
            messages: 原始消息列表
            accumulated_text: 已生成的文本
            headers: HTTP 请求头
            payload_template: 请求 payload 模板（不包含 messages）
            timeout_config: 超时配置
            on_status_update: 状态更新回调函数
            max_continuations: 最大续写次数（防止无限循环）
        
        Returns:
            完整的生成文本（包含续写部分）
        """
        continuation_count = 0
        full_text = accumulated_text
        
        while continuation_count < max_continuations:
            continuation_count += 1
            
            if on_status_update:
                on_status_update("warning", {
                    "message": f"检测到内容被截断，正在续写（第 {continuation_count}/{max_continuations} 次）..."
                })
            
            # 构建续写消息：将已生成的文本作为 assistant 消息，然后添加续写提示
            continuation_messages = messages.copy()
            continuation_messages.append({
                "role": "assistant",
                "content": full_text
            })
            continuation_messages.append({
                "role": "user",
                "content": "请接着上面的内容继续写，不要重复。"
            })
            
            # 构建续写请求
            continuation_payload = {
                **payload_template,
                "messages": continuation_messages,
                "stream": False  # 续写使用非流式，便于检查 finish_reason
            }
            
            try:
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    response = await client.post(
                        self.api_endpoint,
                        headers=headers,
                        json=continuation_payload
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    
                    # 提取生成的文本
                    if "choices" not in result or len(result["choices"]) == 0:
                        if on_status_update:
                            on_status_update("warning", {
                                "message": "续写请求返回结果中没有 choices 字段，停止续写"
                            })
                        break
                    
                    continuation_text = result["choices"][0]["message"]["content"].strip()
                    finish_reason = result["choices"][0].get("finish_reason", "")
                    
                    # 拼接续写内容
                    full_text += continuation_text
                    
                    if on_status_update:
                        on_status_update("streaming", {
                            "text": full_text,
                            "delta": continuation_text
                        })
                    
                    # 如果 finish_reason 不是 "length"，说明已经完成
                    if finish_reason != "length":
                        if on_status_update:
                            on_status_update("parsing", {
                                "message": f"续写完成（finish_reason: {finish_reason}）"
                            })
                        break
                    
                    # 如果还是 "length"，继续下一轮续写
                    if on_status_update:
                        on_status_update("warning", {
                            "message": f"续写内容仍被截断，继续续写（第 {continuation_count + 1}/{max_continuations} 次）..."
                        })
            
            except Exception as e:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"续写请求失败: {str(e)}，停止续写"
                    })
                break
        
        return full_text
    
    async def _generate_batch_stream(
        self,
        context: str,
        batch_question_types: List[str],
        batch_count: int,
        chapter_name: Optional[str] = None,
        on_status_update=None,
        retry_count: int = 0,
        chunks: Optional[List[Dict[str, Any]]] = None,
        allowed_difficulties: Optional[List[str]] = None,
        mode: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        生成一批题目（内部方法，支持重试）
        
        Args:
            context: 教材内容上下文
            batch_question_types: 本批要生成的题型列表
            batch_count: 本批要生成的题目数量
            chapter_name: 章节名称（可选）
            on_status_update: 状态更新回调函数
            retry_count: 当前重试次数
            chunks: 切片列表（用于获取知识点上下文）
            allowed_difficulties: 允许的难度列表，如 ["中等", "困难"]，None 表示不限制
            
        Returns:
            题目字典列表
        """
        logger.info(f"[流式生成] 开始生成批次 - 题型: {batch_question_types}, 数量: {batch_count}, 章节: {chapter_name or '未指定'}, 重试: {retry_count}")
        
        # 获取知识点上下文
        knowledge_info = {}
        if chunks:
            knowledge_info = extract_knowledge_from_chunks(chunks)
            if knowledge_info.get("core_concept"):
                logger.info(f"[流式生成] 提取到知识点 - 核心概念: {knowledge_info.get('core_concept')}")
        
        # 验证题型列表不能为空
        if not batch_question_types or len(batch_question_types) == 0:
            raise ValueError("batch_question_types 不能为空，必须指定要生成的题型")
        
        # 构建完整的用户提示词（所有内容在一个字符串中）
        core_concept = knowledge_info.get("core_concept")
        bloom_level = knowledge_info.get("bloom_level")
        knowledge_summary = knowledge_info.get("knowledge_summary")
        prerequisites_context = knowledge_info.get("prerequisites_context", [])
        confusion_points = knowledge_info.get("confusion_points", [])
        application_scenarios = knowledge_info.get("application_scenarios", [])
        reference_content = context  # 使用传入的context作为参考内容
        
        user_prompt = PromptManager.build_question_generation_user_prompt(
            question_count=batch_count,
            question_types=batch_question_types,
            chapter_name=chapter_name,
            core_concept=core_concept,
            bloom_level=bloom_level,
            knowledge_summary=knowledge_summary,
            prerequisites_context=prerequisites_context,
            confusion_points=confusion_points,
            application_scenarios=application_scenarios,
            reference_content=reference_content,
            allowed_difficulties=allowed_difficulties,
            strict_plan_mode=False,  # 流式生成不使用严格模式
            textbook_name=None,
            mode=mode
        )
        
        # 构建系统提示词（包含通用规则和题型要求，根据模式选择不同的提示词）
        system_prompt = build_system_prompt(include_type_requirements=True, mode=mode)
        
        # 获取 Few-Shot 示例
        few_shot_example = PromptManager.get_few_shot_example()
        
        # 构建请求消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": few_shot_example},
            {"role": "assistant", "content": "我理解了格式要求。请提供教材内容，我将生成符合要求的题目。"},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 OpenRouter API（流式）
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "AI Question Generator",
        }
        
        # 根据题目数量动态调整max_tokens
        max_tokens = calculate_max_tokens_for_questions(
            batch_count,
            model=self.model
        )
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
            "stream": True,  # 启用流式传输
        }
        
        try:
            if on_status_update:
                on_status_update("start", {"message": f"开始生成第 {retry_count + 1} 批题目（{batch_count} 道）..."})
            
            # 使用针对模型的超时配置
            timeout_config = get_timeout_config(self.model, is_stream=True)
            logger.info(f"[流式生成] 调用API开始 - 模型: {self.model}, max_tokens: {max_tokens}")
            
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                async with client.stream(
                    "POST",
                    self.api_endpoint,
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()
                    logger.info(f"[流式生成] API连接成功，开始接收流式数据")
                    
                    accumulated_text = ""
                    finish_reason = None
                    
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        
                        # OpenRouter 流式响应格式：data: {...}
                        if line.startswith("data: "):
                            data_str = line[6:]  # 移除 "data: " 前缀
                            
                            if data_str.strip() == "[DONE]":
                                break
                            
                            try:
                                chunk_data = json.loads(data_str)
                                
                                # 提取增量文本和 finish_reason
                                if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                                    choice = chunk_data["choices"][0]
                                    delta = choice.get("delta", {})
                                    content = delta.get("content", "")
                                    
                                    # 检查是否有 finish_reason（通常在最后一个 chunk 中）
                                    if "finish_reason" in choice and choice["finish_reason"]:
                                        finish_reason = choice["finish_reason"]
                                    
                                    if content:
                                        accumulated_text += content
                                        if on_status_update:
                                            on_status_update("streaming", {
                                                "text": accumulated_text,
                                                "delta": content
                                            })
                            except json.JSONDecodeError:
                                continue
                    
                    # 如果 finish_reason 是 "length"，继续生成剩余内容
                    if finish_reason == "length":
                        if on_status_update:
                            on_status_update("warning", {
                                "message": "检测到内容因长度限制被截断，正在续写..."
                            })
                        
                        # 构建 payload 模板（不包含 messages）
                        payload_template = {
                            "model": self.model,
                            "temperature": payload.get("temperature", 0.7),
                            "max_tokens": payload.get("max_tokens", 8000),
                        }
                        
                        # 调用续写函数
                        accumulated_text = await self._continue_generation_on_length_limit(
                            messages=messages,
                            accumulated_text=accumulated_text,
                            headers=headers,
                            payload_template=payload_template,
                            timeout_config=timeout_config,
                            on_status_update=on_status_update,
                            max_continuations=3
                        )
                    
                    # 处理完整的生成文本
                    if on_status_update:
                        on_status_update("parsing", {"message": "正在解析生成的题目..."})
                    
                    logger.info(f"[流式生成] 流式数据接收完成，开始解析 - 文本长度: {len(accumulated_text)}")
                    generated_text = accumulated_text.strip()
                    
                    # 清理可能的代码块标记和前后空白
                    if generated_text.startswith("```json"):
                        generated_text = generated_text[7:].strip()
                    elif generated_text.startswith("```"):
                        generated_text = generated_text[3:].strip()
                    
                    if generated_text.endswith("```"):
                        generated_text = generated_text[:-3].strip()
                    
                    # 解析 JSON
                    questions_data = None
                    try:
                        questions_data = json.loads(generated_text)
                    except json.JSONDecodeError as e:
                        # 尝试提取 JSON 数组部分
                        import re
                        json_match = re.search(r'\[\s*\{.*\}\s*\]', generated_text, re.DOTALL)
                        if json_match:
                            try:
                                questions_data = json.loads(json_match.group())
                            except json.JSONDecodeError:
                                pass
                        
                        if questions_data is None:
                            start_idx = generated_text.find('[')
                            end_idx = generated_text.rfind(']')
                            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                                try:
                                    json_str = generated_text[start_idx:end_idx + 1]
                                    questions_data = json.loads(json_str)
                                except json.JSONDecodeError:
                                    pass
                        
                        if questions_data is None:
                            # JSON解析失败，尝试重试
                            if retry_count < MAX_RETRIES:
                                if on_status_update:
                                    on_status_update("warning", {
                                        "message": f"JSON解析失败，正在重试 ({retry_count + 1}/{MAX_RETRIES})..."
                                    })
                                import asyncio
                                retry_delay = get_retry_delay(self.model, retry_count)
                                await asyncio.sleep(retry_delay)  # 根据模型类型和重试次数调整延迟
                                return await self._generate_batch_stream(
                                    context, batch_question_types, batch_count,
                                    chapter_name, on_status_update, retry_count + 1, chunks, allowed_difficulties
                                )
                            else:
                                if on_status_update:
                                    on_status_update("error", {
                                        "message": f"无法解析 JSON 响应（已重试{MAX_RETRIES}次）: {str(e)}"
                                    })
                                raise ValueError(f"无法解析 JSON 响应: {str(e)}")
                    
                    # 验证并转换题目数据
                    logger.info(f"[流式生成] 开始解析题目数据 - 原始数据条数: {len(questions_data)}")
                    questions = []
                    skipped_count = 0
                    for idx, q_data in enumerate(questions_data):
                        try:
                            question = Question(**q_data)
                            questions.append(question.model_dump())
                            if on_status_update:
                                on_status_update("progress", {
                                    "current": idx + 1,
                                    "total": len(questions_data),
                                    "message": f"已解析 {idx + 1}/{len(questions_data)} 道题目"
                                })
                        except Exception as e:
                            error_msg = str(e)
                            # 如果题目验证失败，跳过该题目，继续处理下一个
                            skipped_count += 1
                            logger.warning(f"[流式生成] 题目数据验证失败（第 {idx + 1} 道题），跳过: {error_msg}\n题目数据: {q_data}")
                            if on_status_update:
                                on_status_update("warning", {
                                    "message": f"第 {idx + 1} 道题目验证失败，已跳过: {error_msg[:100]}"
                                })
                    
                    # 如果所有题目都验证失败，记录警告
                    if skipped_count > 0:
                        logger.warning(f"[流式生成] 共跳过 {skipped_count} 道验证失败的题目，成功解析 {len(questions)} 道题目")
                    if len(questions) == 0 and len(questions_data) > 0:
                        logger.error(f"[流式生成] 所有题目验证失败，共 {len(questions_data)} 道题目")
                        if on_status_update:
                            on_status_update("warning", {
                                "message": f"所有题目验证失败，共 {len(questions_data)} 道题目"
                            })
                    
                    logger.info(f"[流式生成] 批次生成完成 - 成功生成 {len(questions)} 道题目")
                    return questions
                    
        except httpx.TimeoutException:
            # 超时错误，尝试重试
            if retry_count < MAX_RETRIES:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"请求超时，正在重试 ({retry_count + 1}/{MAX_RETRIES})..."
                    })
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)  # 根据模型类型和重试次数调整延迟
                return await self._generate_batch_stream(
                    context, batch_question_types, batch_count,
                    chapter_name, on_status_update, retry_count + 1, chunks, allowed_difficulties
                )
            else:
                error_msg = f"请求超时（已重试{MAX_RETRIES}次，模型: {self.model}）"
                if on_status_update:
                    on_status_update("error", {"message": error_msg})
                raise ValueError(error_msg)
        except httpx.HTTPStatusError as e:
            # HTTP错误，某些错误可以重试
            if e.response.status_code >= 500 and retry_count < MAX_RETRIES:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"服务器错误，正在重试 ({retry_count + 1}/{MAX_RETRIES})..."
                    })
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._generate_batch_stream(
                    context, batch_question_types, batch_count,
                    chapter_name, on_status_update, retry_count + 1, chunks, allowed_difficulties
                )
            error_msg = f"OpenRouter API 请求失败: HTTP {e.response.status_code} (模型: {self.model})"
            if on_status_update:
                on_status_update("error", {"message": error_msg})
            raise ValueError(error_msg)
        except httpx.RequestError as e:
            # 网络错误，可以重试
            if retry_count < MAX_RETRIES:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"网络错误，正在重试 ({retry_count + 1}/{MAX_RETRIES})..."
                    })
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._generate_batch_stream(
                    context, batch_question_types, batch_count,
                    chapter_name, on_status_update, retry_count + 1, chunks, allowed_difficulties
                )
            error_msg = f"OpenRouter API 请求错误: {str(e)} (模型: {self.model})"
            if on_status_update:
                on_status_update("error", {"message": error_msg})
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"生成题目时发生错误: {str(e)}"
            if on_status_update:
                on_status_update("error", {"message": error_msg})
            raise ValueError(error_msg)
    
    async def generate_questions_stream(
        self,
        context: str,
        question_count: int = 5,
        question_types: Optional[List[str]] = None,
        chapter_name: Optional[str] = None,
        on_status_update=None,
        chunks: Optional[List[Dict[str, Any]]] = None
    ):
        """
        流式调用 OpenRouter API 生成题目（支持 Server-Sent Events）
        支持分批生成，防止大批量题目生成时连接超时
        
        Args:
            context: 教材内容上下文
            question_count: 要生成的总题目数量（默认 5）
            question_types: 要生成的题型列表（如果为 None，则随机生成）
            chapter_name: 章节名称（可选）
            on_status_update: 状态更新回调函数，接收 (status, data) 参数
            
        Returns:
            题目字典列表
        """
        # 如果没有指定题型，使用默认题型
        if not question_types:
            question_types = ["单选题", "多选题", "判断题"]
        
        # question_count 已经是总数量，不需要再乘以题型数量
        total_count = question_count
        
        # 如果题目数量较少，直接生成（按题型平均分配）
        if total_count <= BATCH_SIZE:
            # 平均分配题目到各题型
            count_per_type = max(1, total_count // len(question_types))
            remaining = total_count - count_per_type * len(question_types)
            
            # 如果无法平均分配，前几个题型多分配1道
            type_counts = [count_per_type + (1 if i < remaining else 0) for i in range(len(question_types))]
            
            # 如果只有一种题型或题目数量很少，直接生成
            if len(question_types) == 1 or total_count <= 3:
                return await self._generate_batch_stream(
                    context, question_types, total_count, chapter_name, on_status_update, 0, chunks
                )
            
            # 否则按题型分批生成
            all_questions = []
            for q_type, count in zip(question_types, type_counts):
                if count > 0:
                    # 如果生成失败，直接抛出异常，不跳过
                    batch_questions = await self._generate_batch_stream(
                        context, [q_type], count, chapter_name, on_status_update, 0, chunks
                    )
                    all_questions.extend(batch_questions)
            return all_questions
        
        # 大批量题目，分批生成
        # 按题型平均分配题目数量
        count_per_type = max(1, total_count // len(question_types))
        remaining = total_count - count_per_type * len(question_types)
        
        # 前几个题型多分配1道题
        type_counts = [count_per_type + (1 if i < remaining else 0) for i in range(len(question_types))]
        
        all_questions = []
        batches = []
        
        # 将题目按题型分组，然后分批
        for q_type, type_count in zip(question_types, type_counts):
            count_per_type_batch = type_count
            # 如果该题型需要生成的题目数量大于批次大小，需要分成多批
            while count_per_type_batch > 0:
                batch_size = min(BATCH_SIZE, count_per_type_batch)
                batches.append((q_type, batch_size))
                count_per_type_batch -= batch_size
        
        # 执行分批生成
        total_batches = len(batches)
        for batch_idx, (batch_type, batch_count) in enumerate(batches, 1):
            if on_status_update:
                on_status_update("progress", {
                    "current": batch_idx,
                    "total": total_batches,
                    "message": f"正在生成第 {batch_idx}/{total_batches} 批题目（{batch_type}，{batch_count} 道）..."
                })
            
            # 如果生成失败，直接抛出异常，不跳过
            batch_questions = await self._generate_batch_stream(
                context, [batch_type], batch_count, chapter_name, on_status_update, 0, chunks
            )
            all_questions.extend(batch_questions)
            
            # 批次完成时发送题目数据
            if on_status_update and batch_questions:
                on_status_update("batch_complete", {
                    "batch_index": batch_idx,
                    "total_batches": total_batches,
                    "questions": batch_questions,
                    "message": f"第 {batch_idx}/{total_batches} 批题目生成完成（{len(batch_questions)} 道）"
                })
        
        if on_status_update:
            on_status_update("complete", {
                "questions": all_questions,
                "total": len(all_questions)
            })
        
        return all_questions

    async def _plan_single_file(
        self,
        textbook_name: str,
        file_chunks_info: List[Dict[str, Any]],
        existing_type_distribution: Optional[Dict[str, int]] = None,
        mode: str = "课后习题",
        retry_count: int = 0
    ) -> List[ChunkGenerationPlan]:
        """
        为单个文件规划题目生成任务（辅助函数）
        
        Args:
            textbook_name: 教材名称
            file_chunks_info: 单个文件的切片信息列表
            existing_type_distribution: 已规划文件的题型分布（用于参考）
            retry_count: 当前重试次数
            
        Returns:
            该文件的切片生成计划列表
        """
        if not file_chunks_info:
            return []
        
        # 构建切片目录信息
        chunks_catalog = []
        for idx, chunk_info in enumerate(file_chunks_info, 1):
            chunk_id = chunk_info.get("chunk_id")
            chapter_name = chunk_info.get("chapter_name", "未命名章节")
            content_summary = chunk_info.get("content_summary", "")
            
            if chunk_id is None:
                raise ValueError(f"切片信息 {idx} 缺少 chunk_id 字段")
            
            chunks_catalog.append({
                "chunk_id": chunk_id,
                "chapter_name": chapter_name,
                "content_summary": content_summary[:500] if content_summary else ""  # 限制摘要长度
            })
        
        # 从数据库读取任务规划系统提示词
        try:
            system_prompt = PromptManager.get_task_planning_system_prompt()
        except Exception as e:
            logger.error(f"[规划任务] 无法从数据库获取任务规划系统提示词: {e}")
            raise ValueError(f"无法从数据库获取任务规划系统提示词: {e}")
        
        # 构建切片目录文本
        chunks_text = "\n".join([
            f"{idx + 1}. **切片 ID: {chunk['chunk_id']}** | **章节: {chunk['chapter_name']}**\n"
            f"   内容摘要: {chunk['content_summary'] if chunk.get('content_summary') else '（无摘要）'}\n"
            for idx, chunk in enumerate(chunks_catalog)
        ])
        
        # 如果有已规划的题型分布，添加到提示词中
        existing_distribution_text = ""
        if existing_type_distribution:
            existing_distribution_text = f"""

## 已规划文件的题型分布参考：

以下是从其他已规划文件中统计的题型分布，请参考这些数据来保持全书题型比例的均衡：

{json.dumps(existing_type_distribution, ensure_ascii=False, indent=2)}

**注意**：请参考上述题型分布，确保当前文件的规划与整体分布保持协调，避免某些题型过多或过少。"""
        
        # 使用 PromptManager 构建用户提示词
        try:
            # 构建基础用户提示词
            base_user_prompt = PromptManager.build_task_planning_user_prompt(
                textbook_name=textbook_name,
                chunks_text=chunks_text,
                chunk_count=len(chunks_catalog)
            )
            
            # 如果有已规划的题型分布，追加到提示词中
            if existing_distribution_text:
                mode_text = "提高习题" if mode == "提高习题" else "课后习题"
                user_prompt = f"""{base_user_prompt}

## 出题模式：
**模式**：{mode_text}

{existing_distribution_text}

**额外要求**：
- 严格按照{mode_text}模式的特点和要求进行规划
- 与已规划文件的题型分布保持协调（如果提供了已规划分布）"""
            else:
                user_prompt = base_user_prompt
        except Exception as e:
            logger.error(f"[规划任务] 构建任务规划用户提示词失败: {e}")
            raise ValueError(f"构建任务规划用户提示词失败: {e}")
        
        # 构建请求消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 OpenRouter API
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "AI Question Generator",
        }
        
        # 估算 max_tokens（规划任务通常不需要太多 tokens）
        max_tokens = min(4000, MAX_KNOWLEDGE_EXTRACTION_TOKENS)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,  # 规划任务使用较低温度，确保稳定性
            "max_tokens": max_tokens,
        }
        
        try:
            # 使用针对模型的超时配置
            timeout_config = get_timeout_config(self.model, is_stream=False)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(
                    self.api_endpoint,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                
                # 提取生成的文本
                if "choices" not in result or len(result["choices"]) == 0:
                    raise ValueError("API 返回结果中没有 choices 字段")
                
                generated_text = result["choices"][0]["message"]["content"].strip()
                finish_reason = result["choices"][0].get("finish_reason", "")
                
                # 如果 finish_reason 是 "length"，继续生成剩余内容
                if finish_reason == "length":
                    # 构建 payload 模板（不包含 messages）
                    payload_template = {
                        "model": self.model,
                        "temperature": payload.get("temperature", 0.3),
                        "max_tokens": payload.get("max_tokens", 4000),
                    }
                    
                    # 调用续写函数
                    generated_text = await self._continue_generation_on_length_limit(
                        messages=messages,
                        accumulated_text=generated_text,
                        headers=headers,
                        payload_template=payload_template,
                        timeout_config=timeout_config,
                        on_status_update=None,  # 规划任务没有状态更新回调
                        max_continuations=2  # 规划任务最多续写2次
                    )
                
                # 清理可能的代码块标记和前后空白
                generated_text = generated_text.strip()
                
                # 移除代码块标记
                if generated_text.startswith("```json"):
                    generated_text = generated_text[7:].strip()
                elif generated_text.startswith("```"):
                    generated_text = generated_text[3:].strip()
                
                if generated_text.endswith("```"):
                    generated_text = generated_text[:-3].strip()
                
                # 解析 JSON
                plan_data = None
                try:
                    plan_data = json.loads(generated_text)
                except json.JSONDecodeError as e:
                    # 尝试提取 JSON 对象部分
                    import re
                    # 匹配 {...} 格式的 JSON 对象
                    json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
                    if json_match:
                        try:
                            plan_data = json.loads(json_match.group())
                        except json.JSONDecodeError:
                            pass
                    
                    if plan_data is None:
                        # JSON解析失败，尝试重试
                        if retry_count < MAX_RETRIES:
                            import asyncio
                            retry_delay = get_retry_delay(self.model, retry_count)
                            await asyncio.sleep(retry_delay)
                            return await self._plan_single_file(
                                textbook_name, file_chunks_info, existing_type_distribution, mode, retry_count + 1
                            )
                        else:
                            try:
                                error_msg = repr(e) if hasattr(e, '__repr__') else "JSON 解析错误"
                            except (UnicodeEncodeError, UnicodeDecodeError):
                                error_msg = "JSON 解析错误"
                            raise ValueError(
                                f"无法解析规划任务 JSON 响应（已重试{MAX_RETRIES}次）: {error_msg}\n"
                                f"响应内容前500字符: {generated_text[:500]}"
                            )
                
                # 验证并转换规划数据
                try:
                    # 验证 plans 数组长度
                    plans = plan_data.get("plans", [])
                    if len(plans) != len(file_chunks_info):
                        raise ValueError(
                            f"规划结果中的切片数量 ({len(plans)}) 与输入的切片数量 ({len(file_chunks_info)}) 不一致"
                        )
                    
                    # 验证每个计划的 chunk_id 是否匹配
                    input_chunk_ids = {chunk["chunk_id"] for chunk in file_chunks_info}
                    plan_chunk_ids = {plan.get("chunk_id") for plan in plans}
                    
                    if input_chunk_ids != plan_chunk_ids:
                        missing_ids = input_chunk_ids - plan_chunk_ids
                        extra_ids = plan_chunk_ids - input_chunk_ids
                        error_parts = []
                        if missing_ids:
                            error_parts.append(f"缺少切片 ID: {missing_ids}")
                        if extra_ids:
                            error_parts.append(f"多余的切片 ID: {extra_ids}")
                        raise ValueError("规划结果中的切片 ID 与输入不匹配: " + ", ".join(error_parts))
                    
                    # 构建 chunk_id 到 chapter_name 的映射
                    chunk_id_to_chapter_name = {
                        chunk["chunk_id"]: chunk.get("chapter_name", "未命名章节")
                        for chunk in file_chunks_info
                    }
                    
                    # 构建 ChunkGenerationPlan 对象列表
                    chunk_plans = []
                    for plan_item in plans:
                        chunk_id = plan_item.get("chunk_id")
                        # 从映射中获取 chapter_name，如果 AI 返回的结果中没有则使用默认值
                        chapter_name = plan_item.get("chapter_name") or chunk_id_to_chapter_name.get(chunk_id, "未命名章节")
                        chunk_plan = ChunkGenerationPlan(
                            **plan_item,
                            chapter_name=chapter_name
                        )
                        chunk_plans.append(chunk_plan)
                    
                    logger.info(f"[规划任务] 单文件规划完成 - 切片数: {len(chunk_plans)}, 总题目数: {sum(p.question_count for p in chunk_plans)}")
                    return chunk_plans
                    
                except Exception as e:
                    # 验证失败，尝试重试
                    logger.warning(f"[规划任务] 单文件规划验证失败，准备重试 - 重试次数: {retry_count}/{MAX_RETRIES}, 错误: {str(e)}")
                    if retry_count < MAX_RETRIES:
                        import asyncio
                        retry_delay = get_retry_delay(self.model, retry_count)
                        await asyncio.sleep(retry_delay)
                        return await self._plan_single_file(
                            textbook_name, file_chunks_info, existing_type_distribution, retry_count + 1
                        )
                    else:
                        try:
                            error_msg = repr(e) if hasattr(e, '__repr__') else "规划任务验证错误"
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            error_msg = "规划任务验证错误"
                        logger.error(f"[规划任务] 单文件规划验证失败，已达最大重试次数 - 错误: {error_msg}")
                        raise ValueError(f"规划任务验证失败（已重试{MAX_RETRIES}次）: {error_msg}")
                
        except httpx.TimeoutException:
            # 超时错误，尝试重试
            logger.warning(f"[规划任务] 单文件请求超时，准备重试 - 重试次数: {retry_count}/{MAX_RETRIES}, 模型: {self.model}")
            if retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._plan_single_file(
                    textbook_name, file_chunks_info, existing_type_distribution, retry_count + 1
                )
            logger.error(f"[规划任务] 单文件请求超时，已达最大重试次数 - 模型: {self.model}")
            raise ValueError(f"规划任务请求超时（已重试{MAX_RETRIES}次，模型: {self.model}）")
        except httpx.HTTPStatusError as e:
            # HTTP错误，某些错误可以重试
            if e.response.status_code >= 500 and retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._plan_single_file(
                    textbook_name, file_chunks_info, existing_type_distribution, retry_count + 1
                )
            error_msg = f"OpenRouter API 请求失败: HTTP {e.response.status_code} (模型: {self.model})"
            if e.response.text:
                response_text_safe = e.response.text[:500].encode('utf-8', errors='replace').decode('utf-8')
                error_msg += f"\n响应内容: {response_text_safe}"
            raise ValueError(error_msg)
        except httpx.RequestError as e:
            # 网络错误，可以重试
            if retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._plan_single_file(
                    textbook_name, file_chunks_info, existing_type_distribution, retry_count + 1
                )
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "网络请求错误"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "网络请求错误"
            raise ValueError(f"OpenRouter API 请求错误: {error_msg} (模型: {self.model})")
        except Exception as e:
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "未知错误"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "规划任务时发生未知错误"
            raise ValueError(f"规划任务时发生错误: {error_msg}")

    async def plan_generation_tasks(
        self,
        textbook_name: str,
        chunks_info: List[Dict[str, Any]],
        mode: str = "课后习题",
        retry_count: int = 0
    ) -> TextbookGenerationPlan:
        """
        规划教材题目生成任务
        
        按文件分组，每个文件单独调用 LLM 规划，最后合并结果。
        已规划文件的题型分布会传递给后续文件作为参考，确保全书题型比例均衡。
        
        Args:
            textbook_name: 教材名称
            chunks_info: 切片信息列表，每个元素包含：
                - chunk_id: 切片 ID (int)
                - file_id: 文件 ID (str) - 用于按文件分组
                - chapter_name: 章节名称 (str)
                - content_summary: 内容摘要 (str)
            mode: 出题模式（"课后习题" 或 "提高习题"）
            retry_count: 当前重试次数（仅用于整体重试，单文件重试在 _plan_single_file 中处理）
            
        Returns:
            TextbookGenerationPlan 对象，包含所有切片的生成计划
        """
        logger.info(f"[规划任务] 开始规划题目生成任务 - 教材: {textbook_name}, 模式: {mode}, 切片数: {len(chunks_info)}, 重试次数: {retry_count}")
        
        if not chunks_info:
            raise ValueError("切片信息列表不能为空")
        
        # 按文件分组
        files_chunks: Dict[str, List[Dict[str, Any]]] = {}
        for chunk_info in chunks_info:
            file_id = chunk_info.get("file_id")
            if not file_id:
                # 如果没有 file_id，尝试从数据库查询
                chunk_id = chunk_info.get("chunk_id")
                if chunk_id:
                    # 从数据库查询 file_id
                    with db._get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT file_id FROM chunks WHERE chunk_id = ?", (chunk_id,))
                        row = cursor.fetchone()
                        if row:
                            file_id = row["file_id"]
                        else:
                            logger.warning(f"[规划任务] 无法找到 chunk_id={chunk_id} 对应的 file_id，跳过该切片")
                            continue
                else:
                    logger.warning(f"[规划任务] 切片信息缺少 file_id 和 chunk_id，跳过")
                    continue
            
            if file_id not in files_chunks:
                files_chunks[file_id] = []
            files_chunks[file_id].append(chunk_info)
        
        if not files_chunks:
            raise ValueError("没有有效的文件切片信息")
        
        logger.info(f"[规划任务] 按文件分组完成 - 文件数: {len(files_chunks)}")
        
        # 逐个文件规划，并累积题型分布
        all_plans: List[ChunkGenerationPlan] = []
        accumulated_type_distribution: Dict[str, int] = {}
        file_count = len(files_chunks)
        
        for file_idx, (file_id, file_chunks_info) in enumerate(files_chunks.items(), 1):
            logger.info(f"[规划任务] 规划文件 {file_idx}/{file_count} - file_id: {file_id}, 切片数: {len(file_chunks_info)}")
            
            # 调用单文件规划函数，传递已累积的题型分布作为参考
            file_plans = await self._plan_single_file(
                textbook_name=textbook_name,
                file_chunks_info=file_chunks_info,
                existing_type_distribution=accumulated_type_distribution if accumulated_type_distribution else None,
                mode=mode,
                retry_count=0  # 单文件重试在 _plan_single_file 内部处理
            )
            
            # 合并规划结果
            all_plans.extend(file_plans)
            
            # 更新累积的题型分布
            for plan in file_plans:
                for q_type, count in plan.type_distribution.items():
                    accumulated_type_distribution[q_type] = accumulated_type_distribution.get(q_type, 0) + count
            
            logger.info(f"[规划任务] 文件 {file_idx}/{file_count} 规划完成 - 题目数: {sum(p.question_count for p in file_plans)}, 累积题型分布: {accumulated_type_distribution}")
        
        # 计算总题目数量
        total_questions = sum(plan.question_count for plan in all_plans)
        
        # 创建 TextbookGenerationPlan 对象
        textbook_plan = TextbookGenerationPlan(
            plans=all_plans,
            total_questions=total_questions,
            type_distribution=accumulated_type_distribution
        )
        
        logger.info(f"[规划任务] 规划完成 - 总题目数: {total_questions}, 题型分布: {accumulated_type_distribution}")
        return textbook_plan
        
        # 调用 OpenRouter API
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "AI Question Generator",
        }
        
        # 估算 max_tokens（规划任务通常不需要太多 tokens）
        max_tokens = min(4000, MAX_KNOWLEDGE_EXTRACTION_TOKENS)
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,  # 规划任务使用较低温度，确保稳定性
            "max_tokens": max_tokens,
        }
        
        try:
            # 使用针对模型的超时配置
            timeout_config = get_timeout_config(self.model, is_stream=False)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(
                    self.api_endpoint,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                
                # 提取生成的文本
                if "choices" not in result or len(result["choices"]) == 0:
                    raise ValueError("API 返回结果中没有 choices 字段")
                
                generated_text = result["choices"][0]["message"]["content"].strip()
                finish_reason = result["choices"][0].get("finish_reason", "")
                
                # 如果 finish_reason 是 "length"，继续生成剩余内容
                if finish_reason == "length":
                    # 构建 payload 模板（不包含 messages）
                    payload_template = {
                        "model": self.model,
                        "temperature": payload.get("temperature", 0.3),
                        "max_tokens": payload.get("max_tokens", 4000),
                    }
                    
                    # 调用续写函数
                    generated_text = await self._continue_generation_on_length_limit(
                        messages=messages,
                        accumulated_text=generated_text,
                        headers=headers,
                        payload_template=payload_template,
                        timeout_config=timeout_config,
                        on_status_update=None,  # 规划任务没有状态更新回调
                        max_continuations=2  # 规划任务最多续写2次
                    )
                
                # 清理可能的代码块标记和前后空白
                generated_text = generated_text.strip()
                
                # 移除代码块标记
                if generated_text.startswith("```json"):
                    generated_text = generated_text[7:].strip()
                elif generated_text.startswith("```"):
                    generated_text = generated_text[3:].strip()
                
                if generated_text.endswith("```"):
                    generated_text = generated_text[:-3].strip()
                
                # 解析 JSON
                plan_data = None
                try:
                    plan_data = json.loads(generated_text)
                except json.JSONDecodeError as e:
                    # 尝试提取 JSON 对象部分
                    import re
                    # 匹配 {...} 格式的 JSON 对象
                    json_match = re.search(r'\{.*\}', generated_text, re.DOTALL)
                    if json_match:
                        try:
                            plan_data = json.loads(json_match.group())
                        except json.JSONDecodeError:
                            pass
                    
                    if plan_data is None:
                        # JSON解析失败，尝试重试
                        if retry_count < MAX_RETRIES:
                            import asyncio
                            retry_delay = get_retry_delay(self.model, retry_count)
                            await asyncio.sleep(retry_delay)
                            return await self.plan_generation_tasks(
                                textbook_name, chunks_info, retry_count + 1
                            )
                        else:
                            try:
                                error_msg = repr(e) if hasattr(e, '__repr__') else "JSON 解析错误"
                            except (UnicodeEncodeError, UnicodeDecodeError):
                                error_msg = "JSON 解析错误"
                            raise ValueError(
                                f"无法解析规划任务 JSON 响应（已重试{MAX_RETRIES}次）: {error_msg}\n"
                                f"响应内容前500字符: {generated_text[:500]}"
                            )
                
                # 验证并转换规划数据
                try:
                    # 验证 plans 数组长度
                    plans = plan_data.get("plans", [])
                    if len(plans) != len(chunks_info):
                        raise ValueError(
                            f"规划结果中的切片数量 ({len(plans)}) 与输入的切片数量 ({len(chunks_info)}) 不一致"
                        )
                    
                    # 验证每个计划的 chunk_id 是否匹配
                    input_chunk_ids = {chunk["chunk_id"] for chunk in chunks_info}
                    plan_chunk_ids = {plan.get("chunk_id") for plan in plans}
                    
                    if input_chunk_ids != plan_chunk_ids:
                        missing_ids = input_chunk_ids - plan_chunk_ids
                        extra_ids = plan_chunk_ids - input_chunk_ids
                        error_parts = []
                        if missing_ids:
                            error_parts.append(f"缺少切片 ID: {missing_ids}")
                        if extra_ids:
                            error_parts.append(f"多余的切片 ID: {extra_ids}")
                        raise ValueError("规划结果中的切片 ID 与输入不匹配: " + ", ".join(error_parts))
                    
                    # 构建 TextbookGenerationPlan 对象
                    chunk_plans = []
                    for plan_item in plans:
                        chunk_plan = ChunkGenerationPlan(**plan_item)
                        chunk_plans.append(chunk_plan)
                    
                    # 计算总题目数量
                    total_questions = sum(plan.question_count for plan in chunk_plans)
                    
                    # 使用 LLM 返回的顶层 type_distribution（统计所有切片的题型分布总和）
                    # 如果 LLM 没有返回，则从各切片的 type_distribution 汇总
                    type_distribution = plan_data.get("type_distribution", {})
                    if not type_distribution:
                        # 如果 LLM 没有返回顶层 type_distribution，从各切片汇总
                        type_distribution = {}
                        for plan in chunk_plans:
                            for q_type, count in plan.type_distribution.items():
                                type_distribution[q_type] = type_distribution.get(q_type, 0) + count
                    
                    # 创建 TextbookGenerationPlan 对象
                    textbook_plan = TextbookGenerationPlan(
                        plans=chunk_plans,
                        total_questions=total_questions,
                        type_distribution=type_distribution
                    )
                    
                    logger.info(f"[规划任务] 规划完成 - 总题目数: {total_questions}, 题型分布: {type_distribution}")
                    return textbook_plan
                    
                except Exception as e:
                    # 验证失败，尝试重试
                    logger.warning(f"[规划任务] 规划验证失败，准备重试 - 重试次数: {retry_count}/{MAX_RETRIES}, 错误: {str(e)}")
                    if retry_count < MAX_RETRIES:
                        import asyncio
                        retry_delay = get_retry_delay(self.model, retry_count)
                        await asyncio.sleep(retry_delay)
                        return await self.plan_generation_tasks(
                            textbook_name, chunks_info, retry_count + 1
                        )
                    else:
                        try:
                            error_msg = repr(e) if hasattr(e, '__repr__') else "规划任务验证错误"
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            error_msg = "规划任务验证错误"
                        logger.error(f"[规划任务] 规划验证失败，已达最大重试次数 - 错误: {error_msg}")
                        raise ValueError(f"规划任务验证失败（已重试{MAX_RETRIES}次）: {error_msg}")
                
        except httpx.TimeoutException:
            # 超时错误，尝试重试
            logger.warning(f"[规划任务] 请求超时，准备重试 - 重试次数: {retry_count}/{MAX_RETRIES}, 模型: {self.model}")
            if retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self.plan_generation_tasks(
                    textbook_name, chunks_info, retry_count + 1
                )
            logger.error(f"[规划任务] 请求超时，已达最大重试次数 - 模型: {self.model}")
            raise ValueError(f"规划任务请求超时（已重试{MAX_RETRIES}次，模型: {self.model}）")
        except httpx.HTTPStatusError as e:
            # HTTP错误，某些错误可以重试
            if e.response.status_code >= 500 and retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self.plan_generation_tasks(
                    textbook_name, chunks_info, retry_count + 1
                )
            error_msg = f"OpenRouter API 请求失败: HTTP {e.response.status_code} (模型: {self.model})"
            if e.response.text:
                response_text_safe = e.response.text[:500].encode('utf-8', errors='replace').decode('utf-8')
                error_msg += f"\n响应内容: {response_text_safe}"
            raise ValueError(error_msg)
        except httpx.RequestError as e:
            # 网络错误，可以重试
            if retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self.plan_generation_tasks(
                    textbook_name, chunks_info, retry_count + 1
                )
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "网络请求错误"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "网络请求错误"
            raise ValueError(f"OpenRouter API 请求错误: {error_msg} (模型: {self.model})")
        except Exception as e:
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "未知错误"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "规划任务时发生未知错误"
            raise ValueError(f"规划任务时发生错误: {error_msg}")

    async def _generate_batch(
        self,
        context: str,
        batch_question_types: List[str],
        batch_count: int,
        chapter_name: Optional[str] = None,
        retry_count: int = 0,
        chunks: Optional[List[Dict[str, Any]]] = None,
        allowed_difficulties: Optional[List[str]] = None,
        textbook_name: Optional[str] = None,
        strict_plan_mode: bool = False,
        mode: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        生成一批题目（非流式，内部方法，支持重试）
        
        Args:
            context: 教材内容上下文（仅作为参考，实际生成基于知识点）
            batch_question_types: 本批要生成的题型列表
            batch_count: 本批要生成的题目数量
            chapter_name: 章节名称（可选）
            retry_count: 当前重试次数
            chunks: 切片列表（用于提取知识点）
            allowed_difficulties: 允许的难度列表，如 ["中等", "困难"]，None 表示不限制
            textbook_name: 教材名称（可选，全书出题时使用）
            
        Returns:
            题目字典列表
        """
        logger.info(f"[题目生成] 开始生成批次 - 题型: {batch_question_types}, 数量: {batch_count}, 章节: {chapter_name or '未指定'}, 重试: {retry_count}")
        
        # ========== 新的出题流程：基于知识点生成题目（升级版：三层图谱结构）==========
        # 1. 从前置 chunks 中提取知识点（包含层级背景和横向依赖）
        knowledge_info = {}
        knowledge_nodes = []
        if chunks:
            knowledge_info = extract_knowledge_from_chunks(chunks)
            if knowledge_info.get("core_concept"):
                logger.info(f"[题目生成] 提取到知识点 - 核心概念: {knowledge_info.get('core_concept')}, Bloom层级: {knowledge_info.get('bloom_level')}")
            
            # 收集相关的知识点节点（用于后续验证）
            if knowledge_info.get("node_id"):
                node_id = knowledge_info["node_id"]
                current_node = db.get_knowledge_node(node_id)
                if current_node:
                    knowledge_nodes.append(current_node)
                    
                    # 获取依赖节点（用于生成干扰项或前置条件）
                    dependency_edges = knowledge_info.get("dependency_edges", [])
                    for dep in dependency_edges[:3]:  # 最多3个依赖节点
                        dep_node = db.get_knowledge_node(dep.get("target_node_id"))
                        if dep_node:
                            knowledge_nodes.append(dep_node)
        
        # 2. 提取章节名称（如果还没有提取）
        if not chapter_name and chunks:
            chapter_name = get_chapter_name_from_chunks(chunks)
        
        # 3. 验证题型列表不能为空
        if not batch_question_types or len(batch_question_types) == 0:
            raise ValueError("batch_question_types 不能为空，必须指定要生成的题型")
        
        # 4. 构建完整的用户提示词（所有内容在一个字符串中）
        core_concept = knowledge_info.get("core_concept")
        bloom_level = knowledge_info.get("bloom_level")
        knowledge_summary = knowledge_info.get("knowledge_summary")
        prerequisites_context = knowledge_info.get("prerequisites_context", [])
        confusion_points = knowledge_info.get("confusion_points", [])
        application_scenarios = knowledge_info.get("application_scenarios", [])
        reference_content = chunks[0].get("content", "") if chunks else None
        
        user_prompt = PromptManager.build_question_generation_user_prompt(
            question_count=batch_count,
            question_types=batch_question_types,
            chapter_name=chapter_name,
            core_concept=core_concept,
            bloom_level=bloom_level,
            knowledge_summary=knowledge_summary,
            prerequisites_context=prerequisites_context,
            confusion_points=confusion_points,
            application_scenarios=application_scenarios,
            reference_content=reference_content,
            allowed_difficulties=allowed_difficulties,
            strict_plan_mode=strict_plan_mode,
            textbook_name=textbook_name,
            mode=mode
        )
        
        # 构建系统提示词（包含通用规则和题型要求，根据模式选择不同的提示词）
        system_prompt = build_system_prompt(include_type_requirements=True, mode=mode)
        
        # 获取 Few-Shot 示例
        few_shot_example = PromptManager.get_few_shot_example()
        
        # 构建请求消息
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": few_shot_example},
            {"role": "assistant", "content": "我理解了格式要求。请提供教材内容，我将生成符合要求的题目。"},
            {"role": "user", "content": user_prompt}
        ]
        
        # 调用 OpenRouter API
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "AI Question Generator",
        }
        
        # 根据题目数量动态调整max_tokens
        max_tokens = calculate_max_tokens_for_questions(
            batch_count,
            model=self.model
        )
        
        # 输出全书出题时使用的提示词到日志
        print("\n" + "="*80)
        print("[全书出题] 提示词信息")
        print("="*80)
        print(f"[全书出题] 教材名称: {textbook_name or '未指定'}")
        print(f"[全书出题] 章节名称: {chapter_name or '未指定'}")
        print(f"[全书出题] 题目数量: {batch_count}")
        print(f"[全书出题] 允许的难度: {allowed_difficulties or '全部'}")
        print(f"[全书出题] 题型: {batch_question_types}")
        print("\n[全书出题] 知识点信息:")
        if knowledge_info.get("core_concept"):
            print(f"  - 核心概念: {knowledge_info.get('core_concept')}")
            print(f"  - Bloom层级: {knowledge_info.get('bloom_level', '未指定')}")
            print(f"  - 前置依赖: {knowledge_info.get('prerequisites', [])}")
            print(f"  - 易错点: {knowledge_info.get('confusion_points', [])}")
        else:
            print("  - 未提取到知识点信息")
        print("\n[全书出题] Few-Shot 示例:")
        print("-"*80)
        print(few_shot_example[:500] + "..." if len(few_shot_example) > 500 else few_shot_example)
        print("\n[全书出题] 完整用户提示词:")
        print("-"*80)
        print(user_prompt[:2000] + "..." if len(user_prompt) > 2000 else user_prompt)
        print("\n[全书出题] 模型: " + self.model)
        print("[全书出题] max_tokens: " + str(max_tokens))
        print("="*80 + "\n")
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        
        try:
            # 使用针对模型的超时配置
            timeout_config = get_timeout_config(self.model, is_stream=False)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(
                    self.api_endpoint,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                
                # 提取生成的文本
                if "choices" not in result or len(result["choices"]) == 0:
                    raise ValueError("API 返回结果中没有 choices 字段")
                
                generated_text = result["choices"][0]["message"]["content"].strip()
                finish_reason = result["choices"][0].get("finish_reason", "")
                
                # 如果 finish_reason 是 "length"，继续生成剩余内容
                if finish_reason == "length":
                    # 构建 payload 模板（不包含 messages）
                    payload_template = {
                        "model": self.model,
                        "temperature": payload.get("temperature", 0.7),
                        "max_tokens": payload.get("max_tokens", 8000),
                    }
                    
                    # 调用续写函数
                    generated_text = await self._continue_generation_on_length_limit(
                        messages=messages,
                        accumulated_text=generated_text,
                        headers=headers,
                        payload_template=payload_template,
                        timeout_config=timeout_config,
                        on_status_update=None,  # 非流式请求没有状态更新回调
                        max_continuations=3
                    )
                
                # 清理可能的代码块标记和前后空白
                generated_text = generated_text.strip()
                
                # 移除代码块标记
                if generated_text.startswith("```json"):
                    generated_text = generated_text[7:].strip()
                elif generated_text.startswith("```"):
                    generated_text = generated_text[3:].strip()
                
                if generated_text.endswith("```"):
                    generated_text = generated_text[:-3].strip()
                
                # 解析 JSON
                questions_data = None
                try:
                    questions_data = json.loads(generated_text)
                except json.JSONDecodeError as e:
                    # 尝试提取 JSON 数组部分（使用更精确的正则表达式）
                    import re
                    # 匹配 [...] 格式的 JSON 数组
                    json_match = re.search(r'\[\s*\{.*\}\s*\]', generated_text, re.DOTALL)
                    if json_match:
                        try:
                            questions_data = json.loads(json_match.group())
                        except json.JSONDecodeError:
                            pass
                    
                    # 如果还是失败，尝试查找第一个 [ 到最后一个 ] 之间的内容
                    if questions_data is None:
                        start_idx = generated_text.find('[')
                        end_idx = generated_text.rfind(']')
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            try:
                                json_str = generated_text[start_idx:end_idx + 1]
                                questions_data = json.loads(json_str)
                            except json.JSONDecodeError:
                                pass
                    
                    if questions_data is None:
                        # JSON解析失败，尝试重试
                        if retry_count < MAX_RETRIES:
                            import asyncio
                            retry_delay = get_retry_delay(self.model, retry_count)
                            await asyncio.sleep(retry_delay)
                            return await self._generate_batch(
                                context, batch_question_types, batch_count,
                                chapter_name, retry_count + 1, chunks, allowed_difficulties, textbook_name
                            )
                        else:
                            try:
                                error_msg = repr(e) if hasattr(e, '__repr__') else "JSON 解析错误"
                            except (UnicodeEncodeError, UnicodeDecodeError):
                                error_msg = "JSON 解析错误"
                            raise ValueError(
                                f"无法解析 JSON 响应（已重试{MAX_RETRIES}次）: {error_msg}\n"
                                f"响应内容前500字符: {generated_text[:500]}"
                            )
                
                # 验证并转换题目数据
                logger.info(f"[题目生成] 开始解析题目数据 - 原始数据条数: {len(questions_data)}")
                questions = []
                skipped_count = 0
                for idx, q_data in enumerate(questions_data):
                    try:
                        question = Question(**q_data)
                        questions.append(question.model_dump())
                    except Exception as e:
                        try:
                            error_msg = repr(e) if hasattr(e, '__repr__') else str(e)
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            error_msg = "未知错误"
                        
                        # 如果题目验证失败，跳过该题目，继续处理下一个
                        skipped_count += 1
                        logger.warning(f"[题目生成] 题目数据验证失败（第 {idx + 1} 道题），跳过: {error_msg}\n题目数据: {q_data}")
                
                # 如果所有题目都验证失败，记录警告
                if skipped_count > 0:
                    logger.warning(f"[题目生成] 共跳过 {skipped_count} 道验证失败的题目，成功解析 {len(questions)} 道题目")
                if len(questions) == 0 and len(questions_data) > 0:
                    logger.error(f"[题目生成] 所有题目验证失败，共 {len(questions_data)} 道题目")
                
                # 验证题目分布（如果有关联的知识点节点）
                if knowledge_nodes and questions:
                    validation_result = validate_question_distribution(questions, knowledge_nodes)
                    if not validation_result["is_valid"]:
                        logger.warning(f"[题目生成] 题目分布验证警告: {validation_result['suggestions']}")
                    else:
                        logger.info(f"[题目生成] 题目分布验证通过")
                
                logger.info(f"[题目生成] 批次生成完成 - 成功生成 {len(questions)} 道题目")
                return questions
                
        except httpx.TimeoutException:
            # 超时错误，尝试重试
            logger.warning(f"[题目生成] 请求超时，准备重试 - 重试次数: {retry_count}/{MAX_RETRIES}, 模型: {self.model}")
            if retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._generate_batch(
                    context, batch_question_types, batch_count,
                    chapter_name, retry_count + 1, chunks, allowed_difficulties, textbook_name
                )
            logger.error(f"[题目生成] 请求超时，已达最大重试次数 - 模型: {self.model}")
            raise ValueError(f"请求超时（已重试{MAX_RETRIES}次，模型: {self.model}）")
        except httpx.HTTPStatusError as e:
            # HTTP错误，某些错误可以重试
            if e.response.status_code >= 500 and retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._generate_batch(
                    context, batch_question_types, batch_count,
                    chapter_name, retry_count + 1, chunks, allowed_difficulties, textbook_name
                )
            error_msg = f"OpenRouter API 请求失败: HTTP {e.response.status_code} (模型: {self.model})"
            if e.response.text:
                response_text_safe = e.response.text[:500].encode('utf-8', errors='replace').decode('utf-8')
                error_msg += f"\n响应内容: {response_text_safe}"
            raise ValueError(error_msg)
        except httpx.RequestError as e:
            # 网络错误，可以重试
            if retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._generate_batch(
                    context, batch_question_types, batch_count,
                    chapter_name, retry_count + 1, chunks, allowed_difficulties, textbook_name
                )
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "网络请求错误"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "网络请求错误"
            raise ValueError(f"OpenRouter API 请求错误: {error_msg} (模型: {self.model})")
        except Exception as e:
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "未知错误"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "生成题目时发生未知错误"
            raise ValueError(f"生成题目时发生错误: {error_msg}")
    
    async def generate_questions(
        self,
        context: str,
        question_count: int = 5,
        question_types: Optional[List[str]] = None,
        chapter_name: Optional[str] = None,
        chunks: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        调用 OpenRouter API 生成题目（支持分批生成，防止超时）
        
        Args:
            context: 教材内容上下文
            question_count: 要生成的总题目数量（默认 5）
            question_types: 要生成的题型列表（如果为 None，则随机生成）
            chapter_name: 章节名称（可选）
            
        Returns:
            题目字典列表
        """
        # 如果没有指定题型，使用默认题型
        if not question_types:
            question_types = ["单选题", "多选题", "判断题"]
        
        # question_count 已经是总数量，不需要再乘以题型数量
        total_count = question_count
        
        # 如果题目数量较少，直接生成（按题型平均分配）
        if total_count <= BATCH_SIZE:
            # 平均分配题目到各题型
            count_per_type = max(1, total_count // len(question_types))
            remaining = total_count - count_per_type * len(question_types)
            
            # 如果无法平均分配，前几个题型多分配1道
            type_counts = [count_per_type + (1 if i < remaining else 0) for i in range(len(question_types))]
            
            # 如果只有一种题型或题目数量很少，直接生成
            if len(question_types) == 1 or total_count <= 3:
                return await self._generate_batch(
                    context, question_types, total_count, chapter_name, 0, chunks, None, None
                )
            
            # 否则按题型分批生成
            all_questions = []
            for q_type, count in zip(question_types, type_counts):
                if count > 0:
                    # 如果生成失败，直接抛出异常，不跳过
                    batch_questions = await self._generate_batch(
                        context, [q_type], count, chapter_name, 0, chunks, None, None
                    )
                    all_questions.extend(batch_questions)
            return all_questions
        
        # 大批量题目，分批生成
        # 按题型平均分配题目数量
        count_per_type = max(1, total_count // len(question_types))
        remaining = total_count - count_per_type * len(question_types)
        
        # 前几个题型多分配1道题
        type_counts = [count_per_type + (1 if i < remaining else 0) for i in range(len(question_types))]
        
        all_questions = []
        batches = []
        
        # 将题目按题型分组，然后分批
        for q_type, type_count in zip(question_types, type_counts):
            count_per_type_batch = type_count
            while count_per_type_batch > 0:
                batch_size = min(BATCH_SIZE, count_per_type_batch)
                batches.append((q_type, batch_size))
                count_per_type_batch -= batch_size
        
        # 执行分批生成
        for batch_type, batch_count in batches:
            # 如果生成失败，直接抛出异常，不跳过
            batch_questions = await self._generate_batch(
                context, [batch_type], batch_count, chapter_name, 0, chunks, None, None
            )
            all_questions.extend(batch_questions)
        
        return all_questions


def select_random_chunks(chunks: List[Dict[str, Any]], count: int = 2) -> List[Dict[str, Any]]:
    """
    随机选择指定数量的相关切片
    
    Args:
        chunks: 切片列表
        count: 要选择的切片数量（默认 2）
        
    Returns:
        选中的切片列表
    """
    if not chunks:
        return []
    
    # 确保不超过可用切片数量
    count = min(count, len(chunks))
    
    # 随机选择切片
    selected = random.sample(chunks, count)
    
    return selected


def build_context_from_chunks(chunks: List[Dict[str, Any]]) -> str:
    """
    从切片列表构建上下文字符串
    
    Args:
        chunks: 切片列表
        
    Returns:
        合并后的上下文字符串
    """
    context_parts = []
    
    for idx, chunk in enumerate(chunks, 1):
        content = chunk.get("content", "")
        metadata = chunk.get("metadata", {})
        
        # 构建章节标题路径
        header_path = []
        if "Header 1" in metadata:
            header_path.append(f"# {metadata['Header 1']}")
        if "Header 2" in metadata:
            header_path.append(f"## {metadata['Header 2']}")
        if "Header 3" in metadata:
            header_path.append(f"### {metadata['Header 3']}")
        
        # 添加章节标题（如果有）
        if header_path:
            context_parts.append("\n".join(header_path))
        
        # 添加内容
        context_parts.append(content)
        
        # 如果不是最后一个切片，添加分隔符
        if idx < len(chunks):
            context_parts.append("\n\n---\n\n")
    
    return "\n".join(context_parts)


def get_chapter_name_from_chunks(chunks: List[Dict[str, Any]]) -> Optional[str]:
    """
    从切片列表中提取章节名称
    
    Args:
        chunks: 切片列表
        
    Returns:
        章节名称（如果存在）
    """
    if not chunks:
        return None
    
    # 使用第一个切片的章节信息
    first_chunk = chunks[0]
    metadata = first_chunk.get("metadata", {})
    
    processor = MarkdownProcessor()
    chapter_name = processor.get_chapter_name(metadata)
    
    if chapter_name and chapter_name != "未命名章节":
        return chapter_name
    
    return None


async def generate_questions(
    chunks: List[Dict[str, Any]],
    question_count: int = 5,
    question_types: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    chunks_per_request: int = 2
) -> QuestionList:
    """
    根据教材切片生成题目（基于知识点）
    
    新的核心逻辑：
    1. 从前置 chunks 中提取知识点（核心概念、前置依赖、Bloom层级等）
    2. 基于知识点信息生成题目，而不是直接基于文本
    3. 题目与知识点关联，而不是与chunks直接关联
    
    Args:
        chunks: 解析后的文本切片列表
        question_count: 要生成的题目数量（默认 5，范围 5-10）
        question_types: 要生成的题型列表（可选）
        api_key: OpenRouter API 密钥（可选，默认从环境变量读取）
        model: 模型名称（可选，默认使用配置的模型）
        chunks_per_request: 每次请求使用的切片数量（默认 2，范围 1-2）
        
    Returns:
        QuestionList 对象，包含生成的题目列表
    """
    if not chunks:
        raise ValueError("切片列表为空，无法生成题目")
    
    # 确保题目数量在合理范围内
    question_count = max(5, min(10, question_count))
    
    # 确保每次请求使用的切片数量在合理范围内
    chunks_per_request = max(1, min(2, chunks_per_request))
    
    # 随机选择切片（用于提取知识点）
    selected_chunks = select_random_chunks(chunks, chunks_per_request)
    
    # 提取章节名称
    chapter_name = get_chapter_name_from_chunks(selected_chunks)
    
    # 构建上下文（仅作为参考，实际生成基于知识点）
    context = build_context_from_chunks(selected_chunks)
    
    # 创建 OpenRouter 客户端
    client = OpenRouterClient(api_key=api_key, model=model)
    
    # 生成题目（基于知识点，传入 chunks 用于提取知识点）
    questions_data = await client.generate_questions(
        context=context,  # 仅作为参考
        question_count=question_count,
        question_types=question_types,
        chapter_name=chapter_name,
        chunks=selected_chunks  # 用于提取知识点
    )
    
    # 为每个题目添加章节信息
    for question in questions_data:
        if chapter_name:
            question["chapter"] = chapter_name
    
    # 构建 QuestionList
    questions = [Question(**q) for q in questions_data]
    
    return QuestionList(
        questions=questions,
        total=len(questions),
        chapter=chapter_name
    )


async def generate_questions_for_chunk(
    chunk: Dict[str, Any],
    type_distribution: Dict[str, int],
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    textbook_name: Optional[str] = None,
    mode: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    为单个切片生成题目（基于知识点）
    
    逻辑：
    1. 从 chunk 中提取知识点信息
    2. 基于知识点生成题目，而不是直接基于文本
    3. 按照 type_distribution 中每种题型的精确数量生成
    4. 仅生成中等和困难难度的题目，不生成简单题目
    
    Args:
        chunk: 单个切片，包含 content 和 metadata
        api_key: OpenRouter API 密钥（可选）
        model: 模型名称（可选）
        textbook_name: 教材名称（可选）
        type_distribution: 每种题型的精确数量，例如 {"单选题": 2, "多选题": 2, "判断题": 1}
        
    Returns:
        题目字典列表（仅包含中等和困难难度的题目）
        
    Raises:
        ValueError: 如果 type_distribution 为空或无效，或生成题目失败
    """
    total_count = sum(type_distribution.values())
    logger.info(f"[切片生成] 开始为切片生成题目 - 题型分布: {type_distribution}, 总数量: {total_count}, 教材: {textbook_name or '未指定'}")
    
    if not chunk or not chunk.get("content"):
        raise ValueError("切片内容为空，无法生成题目")
    
    if not type_distribution or len(type_distribution) == 0:
        raise ValueError("type_distribution 不能为空")
    
    # 构建上下文（仅作为参考）
    context = chunk.get("content", "")
    metadata = chunk.get("metadata", {})
    
    # 提取章节名称
    processor = MarkdownProcessor()
    chapter_name = processor.get_chapter_name(metadata)
    
    # 创建 OpenRouter 客户端
    client = OpenRouterClient(api_key=api_key, model=model)
    
    # 按照 type_distribution 中每种题型的数量分别生成
    all_questions = []
    for question_type, count in type_distribution.items():
        if count <= 0:
            continue
        
        logger.info(f"[切片生成] 生成题型 - {question_type}: {count} 道")
        
        # 如果生成失败，直接抛出异常，不跳过
        batch_questions = await client._generate_batch(
            context=context,  # 仅作为参考
            batch_question_types=[question_type],  # 每次只生成一种题型
            batch_count=count,  # 生成该题型的精确数量
            chapter_name=chapter_name,
            retry_count=0,
            chunks=[chunk],  # 用于提取知识点
            allowed_difficulties=None,
            textbook_name=textbook_name,  # 传递教材名称
            strict_plan_mode=True,  # 启用严格计划模式
            mode=mode  # 传递出题模式
        )
        all_questions.extend(batch_questions)
        logger.info(f"[切片生成] 题型 {question_type} 生成完成 - 实际生成 {len(batch_questions)} 道")
    
    # 为每个题目添加章节信息
    for question in all_questions:
        if chapter_name:
            question["chapter"] = chapter_name
    
    logger.info(f"[切片生成] 切片生成完成 - 总共生成 {len(all_questions)} 道题目")
    return all_questions

