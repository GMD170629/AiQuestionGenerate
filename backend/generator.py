"""
LLM 题目生成模块
功能：调用 OpenRouter API，基于教材切片生成各类习题
"""

import os
import sys
import json
import random
from typing import List, Dict, Any, Optional
import httpx
from models import Question, QuestionList
from md_processor import MarkdownProcessor
from database import db
from graph_manager import knowledge_graph
from prompts import PromptManager

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
    model: Optional[str] = None,
    adaptive_mode: bool = False
) -> int:
    """
    计算题目生成所需的最大 tokens
    
    Args:
        question_count: 题目数量
        model: 模型名称
        adaptive_mode: 是否为自适应模式
    
    Returns:
        最大 tokens 数
    """
    # 如果是自适应模式，按最大可能数量（10题）估算
    estimated_count = 10 if adaptive_mode else question_count
    estimated_tokens = estimated_count * TOKENS_PER_QUESTION
    
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


def extract_knowledge_from_chunks(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    从前置 chunks 中提取知识点信息（核心概念、前置依赖、Bloom 层级等）
    
    这是新的出题流程的第一步：从 chunks 中提取知识点，而不是直接使用文本
    
    Args:
        chunks: 切片列表
        
    Returns:
        包含完整知识点信息的字典：
        - core_concept: 核心概念
        - bloom_level: Bloom 认知层级
        - prerequisites: 前置依赖知识点列表（字符串列表）
        - prerequisites_context: 前置知识点上下文列表（详细信息）
        - confusion_points: 学生易错点列表
        - application_scenarios: 应用场景列表
        - knowledge_summary: 知识点摘要（用于生成题目）
    """
    result = {
        "core_concept": None,
        "bloom_level": None,
        "prerequisites": [],
        "prerequisites_context": [],
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
            
            result["core_concept"] = primary_kn.get("core_concept")
            result["bloom_level"] = primary_kn.get("bloom_level")
            result["prerequisites"] = primary_kn.get("prerequisites", [])
            result["confusion_points"] = primary_kn.get("confusion_points", [])
            result["application_scenarios"] = primary_kn.get("application_scenarios") or []
            
            # 获取前置知识点上下文（通过知识图谱）
            if result["core_concept"]:
                prerequisites_context = knowledge_graph.get_prerequisite_context(
                    result["core_concept"], max_depth=3, max_concepts=3
                )
                result["prerequisites_context"] = prerequisites_context
            
            # 构建知识点摘要（用于生成题目）
            summary_parts = []
            
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
            
            if result["prerequisites"]:
                summary_parts.append(f"前置依赖：{', '.join(result['prerequisites'][:3])}")
            
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
    
    这是新的出题流程的核心：基于知识点而不是原始文本生成题目
    
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
    
    # 提取参考内容
    reference_content = None
    if chunks and len(chunks) > 0:
        reference_content = chunks[0].get("content", "")[:500]
    
    # 使用 PromptManager 构建提示词
    return PromptManager.build_knowledge_based_prompt(
        core_concept=core_concept,
        bloom_level=bloom_level,
        knowledge_summary=knowledge_summary,
        prerequisites_context=prerequisites_context,
        confusion_points=confusion_points,
        application_scenarios=application_scenarios,
        reference_content=reference_content
    )


def build_system_prompt(include_type_requirements: bool = True) -> str:
    """
    构建系统提示词（包含通用规则和题型要求）
    
    Args:
        include_type_requirements: 是否包含通用题型要求说明
        
    Returns:
        完整的系统提示词字符串
    """
    return PromptManager.build_system_prompt(include_type_requirements=include_type_requirements)


def build_task_specific_prompt(question_types: List[str], question_count: int, 
                               context: Optional[str] = None, 
                               adaptive: bool = False,
                               knowledge_context: Optional[Dict[str, Any]] = None,
                               allowed_difficulties: Optional[List[str]] = None) -> str:
    """
    构建具体任务要求的提示词（用于用户提示词）
    
    Args:
        question_types: 题型列表（如果为空且 adaptive=True，则让 AI 自主决定）
        question_count: 每种题型的数量（如果 adaptive=True，则作为建议数量）
        context: 教材内容上下文（用于检测是否包含代码）
        adaptive: 是否启用自适应模式（让 AI 自主决定数量和题型）
        knowledge_context: 知识点上下文（包含核心概念、Bloom层级、前置知识点等）
        allowed_difficulties: 允许的难度列表，如 ["中等", "困难"]，None 表示不限制
        
    Returns:
        具体任务要求的提示词字符串（不包含通用规则）
    """
    # 提取知识点信息
    bloom_level = None
    core_concept = None
    
    if knowledge_context:
        bloom_level = knowledge_context.get("bloom_level")
        core_concept = knowledge_context.get("core_concept")
    
    # 使用 PromptManager 构建任务提示词
    return PromptManager.build_task_specific_prompt(
        question_types=question_types,
        question_count=question_count,
        context=context,
        adaptive=adaptive,
        bloom_level=bloom_level,
        core_concept=core_concept,
        allowed_difficulties=allowed_difficulties
    )


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
        allowed_difficulties: Optional[List[str]] = None
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
        # 获取知识点上下文
        knowledge_context = {}
        if chunks:
            knowledge_context = extract_knowledge_from_chunks(chunks)
        
        # 构建具体任务要求提示词（用于用户提示词）
        adaptive_mode = not batch_question_types or len(batch_question_types) == 0
        task_prompt = build_task_specific_prompt(
            batch_question_types if not adaptive_mode else [],
            batch_count,
            context=context,
            adaptive=adaptive_mode,
            knowledge_context=knowledge_context if knowledge_context else None,
            allowed_difficulties=allowed_difficulties
        )
        
        # 构建前置知识点上下文提示
        core_concept = knowledge_context.get("core_concept")
        prerequisites_context = knowledge_context.get("prerequisites_context", [])
        prerequisites_prompt = PromptManager.build_prerequisites_prompt(
            prerequisites_context=prerequisites_context,
            core_concept=core_concept
        )
        
        # 构建用户提示词（只包含具体任务信息）
        user_prompt = PromptManager.build_user_prompt_base(
            adaptive=adaptive_mode,
            question_count=batch_count,
            chapter_name=chapter_name,
            core_concept=core_concept,
            knowledge_prompt="",  # 流式模式下不包含知识点提示，因为上下文已经在前面
            prerequisites_prompt=prerequisites_prompt,
            coherence_prompt="",  # 流式模式下不需要连贯性提示
            task_prompt=task_prompt,
            context=context
        )
        
        # 构建系统提示词（包含通用规则和题型要求）
        system_prompt = build_system_prompt(include_type_requirements=True)
        
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
            model=self.model,
            adaptive_mode=adaptive_mode
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
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                async with client.stream(
                    "POST",
                    self.api_endpoint,
                    headers=headers,
                    json=payload
                ) as response:
                    response.raise_for_status()
                    
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
                    questions = []
                    programming_question_failed = False
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
                            # 如果是编程题，检查是否缺少必需字段
                            if q_data.get("type") == "编程题":
                                # 检查是否缺少 answer 字段
                                if "answer" in error_msg.lower() and ("missing" in error_msg.lower() or "required" in error_msg.lower() or "field required" in error_msg.lower()):
                                    programming_question_failed = True
                                    if on_status_update:
                                        on_status_update("error", {
                                            "message": "编程题生成失败：缺少 answer 字段。编程题必须提供完整的解决方案代码。"
                                        })
                                # 检查是否缺少 explain 字段
                                elif "explain" in error_msg.lower() and ("missing" in error_msg.lower() or "required" in error_msg.lower() or "field required" in error_msg.lower()):
                                    programming_question_failed = True
                                    if on_status_update:
                                        on_status_update("error", {
                                            "message": "编程题生成失败：缺少 explain 字段。编程题必须提供详细的解析说明。"
                                        })
                                # 检查是否缺少测试用例
                                elif "测试用例" in error_msg or "test_cases" in error_msg.lower():
                                    programming_question_failed = True
                                    if on_status_update:
                                        on_status_update("error", {
                                            "message": f"编程题生成失败：{error_msg}。编程题必须提供完整的测试用例。"
                                        })
                                else:
                                    # 其他编程题错误也标记为失败
                                    programming_question_failed = True
                                    if on_status_update:
                                        on_status_update("error", {
                                            "message": f"编程题生成失败：{error_msg}"
                                        })
                            else:
                                if on_status_update:
                                    on_status_update("warning", {
                                        "message": f"跳过无效题目数据: {error_msg}"
                                    })
                            continue
                    
                    # 如果编程题生成失败，抛出错误
                    if programming_question_failed:
                        raise ValueError("编程题生成失败：编程题必须提供以下必需字段：answer（完整的解决方案代码）、explain（详细的解析说明）和 test_cases（完整的测试用例，包括 input_cases 和 output_cases）。")
                    
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
                    try:
                        batch_questions = await self._generate_batch_stream(
                            context, [q_type], count, chapter_name, on_status_update, 0, chunks
                        )
                        all_questions.extend(batch_questions)
                    except Exception as e:
                        if on_status_update:
                            on_status_update("warning", {
                                "message": f"{q_type}生成失败: {str(e)}，跳过"
                            })
                        continue
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
            
            try:
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
            except Exception as e:
                if on_status_update:
                    on_status_update("warning", {
                        "message": f"第 {batch_idx} 批题目生成失败: {str(e)}，跳过该批次"
                    })
                continue
        
        if on_status_update:
            on_status_update("complete", {
                "questions": all_questions,
                "total": len(all_questions)
            })
        
        return all_questions

    async def _generate_batch(
        self,
        context: str,
        batch_question_types: List[str],
        batch_count: int,
        chapter_name: Optional[str] = None,
        retry_count: int = 0,
        chunks: Optional[List[Dict[str, Any]]] = None,
        allowed_difficulties: Optional[List[str]] = None,
        textbook_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        生成一批题目（非流式，内部方法，支持重试）
        
        Args:
            context: 教材内容上下文（现在主要用于向后兼容，优先使用知识点）
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
        # ========== 新的出题流程：基于知识点生成题目 ==========
        # 1. 从前置 chunks 中提取知识点
        knowledge_info = {}
        if chunks:
            knowledge_info = extract_knowledge_from_chunks(chunks)
        
        # 2. 构建基于知识点的提示词（与测试生成接口保持一致）
        knowledge_prompt = ""
        if knowledge_info.get("core_concept"):
            knowledge_prompt = build_knowledge_based_prompt(knowledge_info, chunks)
        else:
            # 如果没有知识点信息，只提供基本信息（与测试生成接口保持一致）
            knowledge_prompt = "## 教材信息：\n"
            if textbook_name:
                knowledge_prompt += f"**教材名称**：{textbook_name}\n"
        
        # 提取章节名称（如果还没有提取）
        if not chapter_name and chunks:
            chapter_name = get_chapter_name_from_chunks(chunks)
        
        if chapter_name:
            knowledge_prompt += f"\n**章节**：{chapter_name}\n"
        
        # 3. 构建具体任务要求提示词（用于用户提示词）
        adaptive_mode = not batch_question_types or len(batch_question_types) == 0
        task_prompt = build_task_specific_prompt(
            batch_question_types if not adaptive_mode else [],
            batch_count,
            context=None,  # 与测试生成接口保持一致，不使用原始文本上下文
            adaptive=adaptive_mode,
            knowledge_context=knowledge_info if knowledge_info.get("core_concept") else None,
            allowed_difficulties=allowed_difficulties
        )
        
        # 4. 构建连贯性说明
        core_concept = knowledge_info.get("core_concept")
        prerequisites_context = knowledge_info.get("prerequisites_context", [])
        coherence_prompt = PromptManager.build_coherence_prompt(
            prerequisites_context=prerequisites_context,
            core_concept=core_concept
        )
        
        # 5. 构建用户提示词（基于知识点，只包含具体任务信息，与测试生成接口保持一致）
        user_prompt = PromptManager.build_user_prompt_base(
            adaptive=adaptive_mode,
            question_count=batch_count,
            chapter_name=chapter_name,
            core_concept=None,  # 已在 knowledge_prompt 中包含
            knowledge_prompt=knowledge_prompt,
            prerequisites_prompt="",  # 已在 knowledge_prompt 中包含
            coherence_prompt=coherence_prompt,
            task_prompt=task_prompt,
            context=None  # 不使用原始文本上下文，与测试生成接口保持一致
        )
        
        # 构建系统提示词（包含通用规则和题型要求）
        system_prompt = build_system_prompt(include_type_requirements=True)
        
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
        
        # 根据题目数量动态调整max_tokens（使用实际的adaptive_mode值，与测试生成接口保持一致）
        max_tokens = calculate_max_tokens_for_questions(
            batch_count,
            model=self.model,
            adaptive_mode=adaptive_mode
        )
        
        # 输出全书出题时使用的提示词到日志
        print("\n" + "="*80)
        print("[全书出题] 提示词信息")
        print("="*80)
        print(f"[全书出题] 教材名称: {textbook_name or '未指定'}")
        print(f"[全书出题] 章节名称: {chapter_name or '未指定'}")
        print(f"[全书出题] 题目数量: {batch_count}")
        print(f"[全书出题] 自适应模式: {adaptive_mode}")
        print(f"[全书出题] 允许的难度: {allowed_difficulties or '全部'}")
        print(f"[全书出题] 题型: {batch_question_types if batch_question_types else '自适应选择'}")
        print("\n[全书出题] 知识点信息:")
        if knowledge_info.get("core_concept"):
            print(f"  - 核心概念: {knowledge_info.get('core_concept')}")
            print(f"  - Bloom层级: {knowledge_info.get('bloom_level', '未指定')}")
            print(f"  - 前置依赖: {knowledge_info.get('prerequisites', [])}")
            print(f"  - 易错点: {knowledge_info.get('confusion_points', [])}")
        else:
            print("  - 未提取到知识点信息")
        print("\n[全书出题] 系统提示词:")
        print("-"*80)
        print(system_prompt[:500] + "..." if len(system_prompt) > 500 else system_prompt)
        print("\n[全书出题] Few-Shot 示例:")
        print("-"*80)
        print(few_shot_example[:500] + "..." if len(few_shot_example) > 500 else few_shot_example)
        print("\n[全书出题] 知识点提示词:")
        print("-"*80)
        print(knowledge_prompt[:500] + "..." if len(knowledge_prompt) > 500 else knowledge_prompt)
        print("\n[全书出题] 任务提示词:")
        print("-"*80)
        print(task_prompt[:500] + "..." if len(task_prompt) > 500 else task_prompt)
        print("\n[全书出题] 连贯性提示词:")
        print("-"*80)
        print(coherence_prompt[:500] + "..." if len(coherence_prompt) > 500 else coherence_prompt)
        print("\n[全书出题] 完整用户提示词:")
        print("-"*80)
        print(user_prompt[:1000] + "..." if len(user_prompt) > 1000 else user_prompt)
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
                questions = []
                programming_question_failed = False
                for q_data in questions_data:
                    try:
                        question = Question(**q_data)
                        questions.append(question.model_dump())
                    except Exception as e:
                        try:
                            error_msg = repr(e) if hasattr(e, '__repr__') else str(e)
                        except (UnicodeEncodeError, UnicodeDecodeError):
                            error_msg = "未知错误"
                        
                        # 如果是编程题，检查是否缺少必需字段
                        if q_data.get("type") == "编程题":
                            # 检查是否缺少 answer 字段
                            if "answer" in error_msg.lower() and ("missing" in error_msg.lower() or "required" in error_msg.lower() or "field required" in error_msg.lower()):
                                programming_question_failed = True
                                print(f"错误：编程题生成失败 - 缺少 answer 字段。编程题必须提供完整的解决方案代码。")
                            # 检查是否缺少 explain 字段
                            elif "explain" in error_msg.lower() and ("missing" in error_msg.lower() or "required" in error_msg.lower() or "field required" in error_msg.lower()):
                                programming_question_failed = True
                                print(f"错误：编程题生成失败 - 缺少 explain 字段。编程题必须提供详细的解析说明。")
                            # 检查是否缺少测试用例
                            elif "测试用例" in error_msg or "test_cases" in error_msg.lower():
                                programming_question_failed = True
                                print(f"错误：编程题生成失败 - {error_msg}。编程题必须提供完整的测试用例。")
                            else:
                                # 其他编程题错误也标记为失败
                                programming_question_failed = True
                                print(f"错误：编程题生成失败 - {error_msg}")
                        else:
                            print(f"警告：跳过无效题目数据: {error_msg}")
                        continue
                
                # 如果编程题生成失败，抛出错误
                if programming_question_failed:
                    raise ValueError("编程题生成失败：编程题必须提供以下必需字段：answer（完整的解决方案代码）、explain（详细的解析说明）和 test_cases（完整的测试用例，包括 input_cases 和 output_cases）。")
                
                return questions
                
        except httpx.TimeoutException:
            # 超时错误，尝试重试
            if retry_count < MAX_RETRIES:
                import asyncio
                retry_delay = get_retry_delay(self.model, retry_count)
                await asyncio.sleep(retry_delay)
                return await self._generate_batch(
                    context, batch_question_types, batch_count,
                    chapter_name, retry_count + 1, chunks, allowed_difficulties, textbook_name
                )
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
                    try:
                        batch_questions = await self._generate_batch(
                            context, [q_type], count, chapter_name, 0, chunks, None, None
                        )
                        all_questions.extend(batch_questions)
                    except Exception as e:
                        print(f"警告：{q_type}生成失败: {e}，跳过")
                        continue
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
            try:
                batch_questions = await self._generate_batch(
                    context, [batch_type], batch_count, chapter_name, 0, chunks, None, None
                )
                all_questions.extend(batch_questions)
            except Exception as e:
                print(f"警告：批次生成失败（{batch_type}，{batch_count} 道）: {e}，跳过该批次")
                continue
        
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
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    textbook_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    为单个切片生成题目（基于知识点，使用自适应模式）
    
    新的逻辑：
    1. 从 chunk 中提取知识点信息
    2. 基于知识点生成题目，而不是直接基于文本
    3. 每个切片生成1-2道题目，难度为中等或困难
    
    Args:
        chunk: 单个切片，包含 content 和 metadata
        api_key: OpenRouter API 密钥（可选）
        model: 模型名称（可选）
        
    Returns:
        题目字典列表
    """
    if not chunk or not chunk.get("content"):
        return []
    
    # 构建上下文（仅作为参考）
    context = chunk.get("content", "")
    metadata = chunk.get("metadata", {})
    
    # 提取章节名称
    processor = MarkdownProcessor()
    chapter_name = processor.get_chapter_name(metadata)
    
    # 创建 OpenRouter 客户端
    client = OpenRouterClient(api_key=api_key, model=model)
    
    # 随机生成1-2道题目
    import random
    question_count = random.randint(1, 2)
    
    # 使用自适应模式生成题目（基于知识点）
    # 调用 _generate_batch 方法，传入空的 question_types 列表启用自适应模式
    # 每个切片生成1-2道题目，难度限制为中等、困难
    # 传入单个 chunk 的列表以提取知识点
    questions_data = await client._generate_batch(
        context=context,  # 仅作为参考
        batch_question_types=[],  # 空列表启用自适应模式
        batch_count=question_count,  # 1-2道题目
        chapter_name=chapter_name,
        retry_count=0,
        chunks=[chunk],  # 用于提取知识点
        allowed_difficulties=["中等", "困难"],  # 限制难度为中等、困难，不生成简单题目
        textbook_name=textbook_name  # 传递教材名称
    )
    
    # 为每个题目添加章节信息
    for question in questions_data:
        if chapter_name:
            question["chapter"] = chapter_name
    
    return questions_data

