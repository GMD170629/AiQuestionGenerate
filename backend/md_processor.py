"""
Markdown 解析引擎（兼容层）
从新的模块化结构中导入所有已拆分的内容，保持向后兼容
功能：读取 Markdown 文件，按标题层级切分，保留代码块，进行文本切片
"""

import re
import json
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# 从新模块导入所有已拆分的内容
from markdown.processor import MarkdownProcessor, process_markdown_file
from markdown.toc_extractor import TOCNode, SemanticSplitter
from markdown.text_splitters import CodeBlockAwareSplitter
from markdown.chapter_extractor import (
    extract_toc,
    calculate_statistics,
    extract_chapters_from_chunks,
    build_chapters_from_toc_tree,
)
from prompts import PromptManager

# 扩展 MarkdownProcessor 类，添加知识提取方法
# 注意：extract_knowledge_metadata 方法保留在原始实现中
# 为了保持向后兼容，我们需要扩展 MarkdownProcessor 类
_BaseMarkdownProcessor = MarkdownProcessor


# 扩展 MarkdownProcessor，添加知识提取方法
class MarkdownProcessor(_BaseMarkdownProcessor):
    """扩展的 MarkdownProcessor，添加知识提取功能"""
    
    async def extract_knowledge_metadata(self, chunk_content: str, chunk_metadata: Dict[str, Any],
                                       api_key: Optional[str] = None, 
                                       model: Optional[str] = None,
                                       api_endpoint: Optional[str] = None,
                                       file_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        调用 LLM 提取知识点的语义信息
        
        Args:
            chunk_content: 切片内容
            chunk_metadata: 切片元数据
            api_key: OpenRouter API 密钥（可选，默认从数据库读取）
            model: 模型名称（可选，默认从数据库读取）
            api_endpoint: API端点URL（可选，默认从数据库读取）
            file_id: 文件 ID（可选，用于查询文件名和教材信息）
            
        Returns:
            知识点元数据字典，包含：
            - core_concept: 核心概念
            - confusion_points: 学生易错点列表
            - bloom_level: Bloom 认知层级（1-6）
            - application_scenarios: 应用场景列表（可选）
            注意：知识点应该是独立的，不包含前置依赖（prerequisites）
            如果提取失败则返回 None
        """
        try:
            # 导入 OpenRouter 客户端（延迟导入，避免循环依赖）
            from generator import OpenRouterClient, get_timeout_config, get_max_output_tokens
            import httpx
            
            # 创建 OpenRouter 客户端
            client = OpenRouterClient(api_key=api_key, model=model, api_endpoint=api_endpoint)
            
            # 获取上下文信息（文件名、教材名称、目录路径）
            context_info = []
            
            # 查询文件信息和已有知识点
            filename = None
            textbook_names = []
            existing_concepts = []
            if file_id:
                try:
                    from database import db
                    file_info = db.get_file(file_id)
                    if file_info:
                        filename = file_info.get("filename", "")
                        if filename:
                            context_info.append(f"文件名: {filename}")
                    
                    # 查询教材信息
                    textbooks = db.get_file_textbooks(file_id)
                    if textbooks:
                        textbook_names = [t.get("name", "") for t in textbooks if t.get("name")]
                        if textbook_names:
                            context_info.append(f"教材名称: {', '.join(textbook_names)}")
                    
                    # 查询该文件已有的知识点（用于避免重复）
                    existing_nodes = db.get_file_knowledge_nodes(file_id)
                    existing_concepts = [node.get("core_concept", "") for node in existing_nodes if node.get("core_concept")]
                    if existing_concepts:
                        print(f"[知识提取] 发现该文件已有 {len(existing_concepts)} 个知识点，将用于参考避免重复")
                except Exception as e:
                    print(f"[知识提取] 警告：查询文件/教材信息失败: {e}")
            
            # 构建目录路径信息
            chapter_path = []
            
            # 先添加层级化的 Header 路径
            if chunk_metadata.get("Header 1"):
                chapter_path.append(chunk_metadata["Header 1"])
            if chunk_metadata.get("Header 2"):
                chapter_path.append(chunk_metadata["Header 2"])
            if chunk_metadata.get("Header 3"):
                chapter_path.append(chunk_metadata["Header 3"])
            
            # 如果 section_title 存在且与最后一个元素不同，添加它（提供更详细的章节信息）
            section_title = chunk_metadata.get("section_title")
            if section_title and (not chapter_path or chapter_path[-1] != section_title):
                chapter_path.append(section_title)
            
            if chapter_path:
                context_info.append(f"章节路径: {' > '.join(chapter_path)}")
            
            context_str = "\n".join(context_info) if context_info else "（无额外上下文信息）"
            
            # 构建提示词（使用 PromptManager）
            system_prompt = PromptManager.get_knowledge_extraction_system_prompt()

            # 构建已有知识点信息
            existing_concepts_str = ""
            if existing_concepts:
                concepts_list = "\n".join(f"- {concept}" for concept in existing_concepts[:50])  # 最多显示50个，避免提示词过长
                existing_concepts_str = f"""
**已有知识点列表（请参考并避免重复）：**
{concepts_list}

**重要**：
- 如果当前片段的核心概念已经存在于上述列表中，**必须使用完全相同的名称**
- 不要生成变体名称（如添加括号、英文翻译等）
- 如果概念本质相同，请统一使用列表中已有的名称
- **不要重复生成已存在的核心概念**
- 如果片段讨论的是某个已有概念的某个方面（如历史、特点、优势等），应该提取该核心概念本身，而不是这个方面
"""
            
            # 使用 PromptManager 构建用户提示词
            user_prompt = PromptManager.build_knowledge_extraction_user_prompt(
                context_str=context_str,
                existing_concepts_str=existing_concepts_str,
                chunk_content=chunk_content
            )
            
            # 构建请求消息
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # 检查 API 配置
            if not client.api_key:
                error_msg = "API key 未配置，无法调用知识提取 API"
                print(f"[知识提取] ✗ {error_msg}")
                print(f"[知识提取] 提示：请在系统设置中配置 OpenRouter API key")
                return None
            
            # 清理 API key（去除前后空格）
            api_key_cleaned = client.api_key.strip()
            if api_key_cleaned != client.api_key:
                print(f"[知识提取] ⚠ API key 包含前后空格，已自动清理")
            
            # 检查 API key 格式（不显示完整 key，只显示前3个和后3个字符）
            if len(api_key_cleaned) < 20:
                print(f"[知识提取] ⚠ API key 长度异常: {len(api_key_cleaned)} 字符（通常应该更长）")
            else:
                print(f"[知识提取] API key 格式检查: 长度={len(api_key_cleaned)}, 前缀={api_key_cleaned[:3]}..., 后缀=...{api_key_cleaned[-3:]}")
            
            print(f"[知识提取] 调用 API: {client.api_endpoint}, 模型: {client.model}")
            
            # 调用 OpenRouter API（使用清理后的 API key）
            headers = {
                "Authorization": f"Bearer {api_key_cleaned}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/your-repo",
                "X-Title": "AI Question Generator",
            }
            
            # 使用统一的 token 限制配置
            max_tokens = get_max_output_tokens(client.model, "knowledge_extraction")
            
            payload = {
                "model": client.model,
                "messages": messages,
                "temperature": 0.3,  # 降低温度，提高准确性
                "max_tokens": max_tokens,
            }
            
            # 使用针对模型的超时配置
            timeout_config = get_timeout_config(client.model, is_stream=False)
            async with httpx.AsyncClient(timeout=timeout_config) as http_client:
                try:
                    response = await http_client.post(
                        client.api_endpoint,
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                except httpx.HTTPStatusError as e:
                    error_msg = f"API 调用失败，状态码: {e.response.status_code}"
                    print(f"[知识提取] ✗ {error_msg}")
                    print(f"[知识提取] 响应内容: {e.response.text[:500]}")
                    return None
                except httpx.RequestError as e:
                    error_msg = f"API 请求失败: {str(e)}"
                    print(f"[知识提取] ✗ {error_msg}")
                    return None
                
                # 提取生成的文本
                if "choices" not in result or len(result["choices"]) == 0:
                    error_msg = "知识提取 API 返回结果中没有 choices 字段"
                    print(f"[知识提取] ✗ {error_msg}")
                    print(f"[知识提取] API 响应: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
                    return None
                
                generated_text = result["choices"][0]["message"]["content"].strip()
                
                # 清理可能的代码块标记
                if generated_text.startswith("```json"):
                    generated_text = generated_text[7:].strip()
                elif generated_text.startswith("```"):
                    generated_text = generated_text[3:].strip()
                
                if generated_text.endswith("```"):
                    generated_text = generated_text[:-3].strip()
                
                # 解析 JSON
                try:
                    knowledge_data = json.loads(generated_text)
                    
                    # 验证必需字段
                    if "core_concept" not in knowledge_data or "bloom_level" not in knowledge_data:
                        error_msg = f"知识提取结果缺少必需字段。返回的字段: {list(knowledge_data.keys())}"
                        print(f"[知识提取] ✗ {error_msg}")
                        print(f"[知识提取] 返回的数据: {json.dumps(knowledge_data, ensure_ascii=False, indent=2)[:500]}")
                        return None
                    
                    # 确保字段类型正确
                    if not isinstance(knowledge_data.get("core_concept"), str):
                        error_msg = f"core_concept 必须是字符串，当前类型: {type(knowledge_data.get('core_concept'))}"
                        print(f"[知识提取] ✗ {error_msg}")
                        return None
                    
                    if not isinstance(knowledge_data.get("bloom_level"), int):
                        error_msg = f"bloom_level 必须是整数，当前类型: {type(knowledge_data.get('bloom_level'))}"
                        print(f"[知识提取] ✗ {error_msg}")
                        return None
                    
                    bloom_level = knowledge_data["bloom_level"]
                    if bloom_level < 1 or bloom_level > 6:
                        print(f"[知识提取] ⚠ bloom_level 超出范围 (1-6)，当前值: {bloom_level}，已自动调整")
                        bloom_level = max(1, min(6, bloom_level))  # 限制在有效范围内
                        knowledge_data["bloom_level"] = bloom_level
                    
                    # 确保列表字段存在（不包含 prerequisites，因为知识点应该是独立的）
                    if "confusion_points" not in knowledge_data:
                        knowledge_data["confusion_points"] = []
                    if "application_scenarios" not in knowledge_data:
                        knowledge_data["application_scenarios"] = None
                    
                    # 确保列表字段是列表类型
                    if not isinstance(knowledge_data["confusion_points"], list):
                        knowledge_data["confusion_points"] = []
                    if knowledge_data["application_scenarios"] is not None and not isinstance(knowledge_data["application_scenarios"], list):
                        knowledge_data["application_scenarios"] = None
                    
                    # 强制移除 prerequisites，确保知识点独立
                    if "prerequisites" in knowledge_data:
                        del knowledge_data["prerequisites"]
                    # 确保 prerequisites 字段不存在或为空数组（向后兼容）
                    knowledge_data["prerequisites"] = []
                    
                    # 检查并统一重复的知识点名称
                    core_concept = knowledge_data["core_concept"].strip()
                    if existing_concepts:
                        # 检查完全匹配
                        if core_concept in existing_concepts:
                            print(f"[知识提取] ⚠ 发现重复知识点，使用已有名称: {core_concept}")
                        else:
                            # 检查相似匹配（去除括号内容、去除"的XX"后缀等）
                            core_concept_base = core_concept.split("（")[0].split("(")[0].strip()  # 去除括号内容
                            core_concept_base = core_concept_base.split("的")[0].strip() if "的" in core_concept_base else core_concept_base  # 去除"的XX"后缀
                            
                            # 查找匹配的已有知识点
                            for existing_concept in existing_concepts:
                                existing_base = existing_concept.split("（")[0].split("(")[0].strip()
                                existing_base = existing_base.split("的")[0].strip() if "的" in existing_base else existing_base
                                
                                # 如果基础名称相同，使用已有名称
                                if core_concept_base == existing_base or core_concept_base in existing_base or existing_base in core_concept_base:
                                    print(f"[知识提取] ⚠ 发现相似知识点，统一使用已有名称: {existing_concept} (原: {core_concept})")
                                    knowledge_data["core_concept"] = existing_concept
                                    break
                    
                    print(f"[知识提取] ✓ 成功提取知识点: {knowledge_data['core_concept']} (bloom_level: {knowledge_data['bloom_level']})")
                    return knowledge_data
                    
                except json.JSONDecodeError as e:
                    error_msg = f"知识提取 JSON 解析失败: {e}"
                    print(f"[知识提取] ✗ {error_msg}")
                    print(f"[知识提取] 原始响应前1000字符:\n{generated_text[:1000]}")
                    return None
                    
        except Exception as e:
            error_msg = f"知识提取失败: {str(e)}"
            print(f"[知识提取] ✗ {error_msg}")
            import traceback
            traceback.print_exc()
            return None
    
    async def process_with_knowledge_extraction(self, file_path: str, file_id: str,
                                               api_key: Optional[str] = None,
                                               model: Optional[str] = None,
                                               api_endpoint: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        处理 Markdown 文件并提取知识点（异步版本）
        
        流程：
        1. 读取文件内容
        2. 使用语义分割器提取目录树，按目录树切分文件
        3. 如果语义分割失败，回退到 MarkdownHeaderTextSplitter
        4. 对每个切片调用 LLM 提取知识点元数据
        5. 将知识点保存到数据库
        
        Args:
            file_path: Markdown 文件路径
            file_id: 文件 ID（用于关联知识点节点）
            api_key: OpenRouter API 密钥（可选）
            model: 模型名称（可选）
            api_endpoint: API端点URL（可选）
            
        Returns:
            包含 content 和 metadata 的字典列表
        """
        # 先进行常规处理
        chunks = self.process(file_path)
        
        if not chunks or not self.enable_knowledge_extraction:
            return chunks
        
        # 导入数据库模块（延迟导入，避免循环依赖）
        from database import db
        
        # 对每个切片提取知识点
        for chunk_idx, chunk in enumerate(chunks):
            chunk_content = chunk.get("content", "")
            chunk_metadata = chunk.get("metadata", {})
            
            if not chunk_content.strip():
                continue
            
            try:
                # 调用 LLM 提取知识点
                knowledge_data = await self.extract_knowledge_metadata(
                    chunk_content, chunk_metadata, api_key, model, api_endpoint, file_id
                )
                
                if knowledge_data:
                    # 获取 chunk_id（需要从数据库查询，因为 chunks 表是存储后才有的）
                    # 这里我们需要先存储 chunks，然后获取 chunk_id
                    # 但为了简化，我们可以先存储知识点，然后在存储 chunks 时关联
                    # 或者我们可以使用临时 ID，稍后更新
                    
                    # 生成节点 ID
                    node_id = str(uuid.uuid4())
                    
                    # 注意：这里 chunk_id 需要从数据库获取，但 chunks 可能还没有存储
                    # 所以我们先不存储，而是在存储 chunks 后再调用这个方法
                    # 或者我们可以修改逻辑，在存储 chunks 后立即提取知识点
                    
                    # 暂时跳过存储，因为 chunk_id 还不存在
                    # 知识点提取将在存储 chunks 后单独调用
                    chunk["knowledge_metadata"] = knowledge_data
                    
            except Exception as e:
                print(f"警告：切片 {chunk_idx} 的知识点提取失败: {e}")
                continue
        
        return chunks


def _try_fix_truncated_json(json_text: str, expected_count: int) -> Optional[str]:
    """
    尝试修复被截断的 JSON 字符串
    
    Args:
        json_text: 可能被截断的 JSON 文本
        expected_count: 期望的知识点数量
        
    Returns:
        修复后的 JSON 文本，如果无法修复则返回 None
    """
    import json
    import re
    
    if not json_text or not json_text.strip():
        return None
    
    # 如果 JSON 已经完整，直接返回
    try:
        data = json.loads(json_text)
        if isinstance(data, dict) and "dependencies" in data:
            if len(data["dependencies"]) >= expected_count:
                return json_text  # 已经完整
    except:
        pass
    
    # 尝试找到最后一个完整的依赖项
    # 查找 "dependencies": [ ... ] 结构
    pattern = r'"dependencies"\s*:\s*\['
    match = re.search(pattern, json_text)
    if not match:
        return None
    
    # 从 dependencies 数组开始位置查找
    start_pos = match.end()
    
    # 尝试找到最后一个完整的对象
    # 查找模式：{ "node_id": "...", "core_concept": "...", "prerequisites": [...] }
    bracket_count = 0
    array_bracket_count = 1  # dependencies 数组的括号计数
    last_complete_pos = start_pos
    in_string = False
    escape_next = False
    
    for i in range(start_pos, len(json_text)):
        char = json_text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        
        if in_string:
            continue
        
        if char == '[':
            array_bracket_count += 1
        elif char == ']':
            array_bracket_count -= 1
            if array_bracket_count == 0:
                # 数组结束，找到最后一个完整位置
                last_complete_pos = i + 1
                break
        elif char == '{':
            bracket_count += 1
        elif char == '}':
            bracket_count -= 1
            if bracket_count == 0:
                # 找到一个完整的对象，记录位置（但继续查找，找到最后一个）
                last_complete_pos = i + 1
    
    # 如果找到了完整的结构，尝试补全 JSON
    if last_complete_pos > start_pos:
        # 提取完整的部分
        prefix = json_text[:last_complete_pos].rstrip()
        
        # 移除末尾可能的逗号
        prefix = re.sub(r',\s*$', '', prefix)
        
        # 补全 JSON 结构
        fixed_json = prefix + "\n  ]\n}"
        
        # 验证修复后的 JSON 是否有效
        try:
            data = json.loads(fixed_json)
            if isinstance(data, dict) and "dependencies" in data:
                print(f"[依赖构建] 修复后包含 {len(data['dependencies'])} 个依赖项（期望 {expected_count} 个）")
                return fixed_json
        except:
            pass
    
    return None


async def _build_dependencies_in_batches(
    textbook_id: str,
    textbook_name: str,
    concepts_list: List[Dict[str, Any]],
    knowledge_nodes: List[Dict[str, Any]],
    api_key: str,
    model: str,
    api_endpoint: str,
    batch_size: int
) -> Dict[str, Any]:
    """
    分批处理知识点的依赖关系构建
    
    Args:
        textbook_id: 教材 ID
        textbook_name: 教材名称
        concepts_list: 知识点列表
        knowledge_nodes: 知识点节点列表
        api_key: API 密钥
        model: 模型名称
        api_endpoint: API 端点
        batch_size: 每批处理的知识点数量
        
    Returns:
        构建结果字典
    """
    from database import db
    import asyncio
    
    total_concepts = len(concepts_list)
    total_batches = (total_concepts + batch_size - 1) // batch_size
    dependencies_built = 0
    
    print(f"[依赖构建] 分批处理：共 {total_concepts} 个知识点，分为 {total_batches} 批，每批 {batch_size} 个")
    
    # 构建 node_id 到概念的映射（全局）
    node_id_to_concept = {node["node_id"]: node["core_concept"] for node in knowledge_nodes}
    concept_to_node_id = {node["core_concept"]: node["node_id"] for node in knowledge_nodes}
    
    # 分批处理
    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, total_concepts)
        batch_concepts = concepts_list[start_idx:end_idx]
        
        print(f"[依赖构建] 处理第 {batch_idx + 1}/{total_batches} 批（知识点 {start_idx + 1}-{end_idx}）")
        
        # 调用单批处理函数
        batch_result = await _build_dependencies_single_batch(
            textbook_id, textbook_name, batch_concepts, knowledge_nodes,
            api_key, model, api_endpoint
        )
        
        if batch_result.get("success"):
            batch_dependencies_built = batch_result.get("dependencies_built", 0)
            dependencies_built += batch_dependencies_built
            print(f"[依赖构建] 第 {batch_idx + 1} 批完成：成功构建 {batch_dependencies_built} 个依赖关系")
        else:
            error_msg = batch_result.get("message", "未知错误")
            print(f"[依赖构建] ⚠ 第 {batch_idx + 1} 批处理失败: {error_msg}")
            # 继续处理下一批，不中断整个流程
    
    # 重新加载知识图谱
    try:
        from graph_manager import knowledge_graph
        knowledge_graph.reload()
        print(f"[依赖构建] ✓ 知识图谱已重新加载，当前节点数: {knowledge_graph.graph.number_of_nodes()}")
    except Exception as e:
        print(f"[依赖构建] ⚠ 警告：重新加载知识图谱失败: {e}")
    
    message = f"分批处理完成：成功为 {dependencies_built} 个知识点构建了依赖关系（共 {total_concepts} 个知识点，{total_batches} 批）"
    print(f"[依赖构建] ✓ {message}")
    
    return {
        "success": True,
        "total_concepts": total_concepts,
        "dependencies_built": dependencies_built,
        "message": message
    }


def normalize_concept_name(concept: str) -> str:
    """
    标准化概念名称，用于去重比较
    
    处理规则：
    1. 去除首尾空格
    2. 统一空格（多个连续空格合并为一个）
    3. 去除常见的冗余后缀（如"的概念"、"简介"、"概述"等）
    4. 转换为小写（用于比较，但不改变原始存储）
    
    Args:
        concept: 原始概念名称
        
    Returns:
        标准化后的概念名称（用于比较）
    """
    if not concept:
        return ""
    
    # 去除首尾空格
    normalized = concept.strip()
    
    # 统一空格（多个连续空格合并为一个）
    import re
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # 去除常见的冗余后缀
    redundant_suffixes = [
        "的概念", "简介", "概述", "介绍",
        "的基本概念", "基础概念", "的核心概念"
    ]
    for suffix in redundant_suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
    
    # 转换为小写用于比较
    normalized_lower = normalized.lower()
    
    return normalized_lower


def is_concept_duplicate(concept1: str, concept2: str, threshold: float = 0.85) -> bool:
    """
    检查两个概念是否重复
    
    使用标准化名称进行比较，如果完全相同或高度相似则认为重复
    
    Args:
        concept1: 第一个概念名称
        concept2: 第二个概念名称
        threshold: 相似度阈值（0-1），默认0.85
        
    Returns:
        True 如果认为重复，False 否则
    """
    normalized1 = normalize_concept_name(concept1)
    normalized2 = normalize_concept_name(concept2)
    
    # 完全相同的标准化名称
    if normalized1 == normalized2:
        return True
    
    # 检查是否互为子串（一个包含另一个，且长度差异不超过30%）
    if normalized1 in normalized2 or normalized2 in normalized1:
        len1, len2 = len(normalized1), len(normalized2)
        if len1 > 0 and len2 > 0:
            ratio = min(len1, len2) / max(len1, len2)
            if ratio >= threshold:
                return True
    
    # 可以使用更复杂的相似度算法（如编辑距离），但为了性能先使用简单方法
    return False


def process_markdown_file(file_path: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> List[Dict[str, Any]]:
    """
    便捷函数：处理 Markdown 文件
    
    Args:
        file_path: Markdown 文件路径
        chunk_size: 每个 chunk 的最大字符数
        chunk_overlap: chunk 之间的重叠字符数
        
    Returns:
        包含 content 和 metadata 的字典列表
    """
    processor = MarkdownProcessor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return processor.process(file_path)


async def extract_and_store_knowledge_nodes(file_id: str, 
                                           api_key: Optional[str] = None,
                                           model: Optional[str] = None,
                                           api_endpoint: Optional[str] = None) -> int:
    """
    为文件的所有切片提取并存储知识点节点
    
    这个函数应该在 chunks 已经存储到数据库后调用，因为需要 chunk_id。
    
    Args:
        file_id: 文件 ID
        api_key: OpenRouter API 密钥（可选）
        model: 模型名称（可选）
        api_endpoint: API端点URL（可选）
        
    Returns:
        成功提取的知识点节点数量
    """
    from database import db
    from knowledge_extraction_progress import knowledge_extraction_progress
    
    print(f"[知识提取] 开始为文件 {file_id} 提取知识点...")
    
    # 如果没有提供 API 配置，从数据库读取
    if not api_key or not model or not api_endpoint:
        ai_config = db.get_ai_config()
        if not api_key:
            api_key = ai_config.get("api_key")
        if not model:
            model = ai_config.get("model", "openai/gpt-4o-mini")
        if not api_endpoint:
            api_endpoint = ai_config.get("api_endpoint", "https://openrouter.ai/api/v1/chat/completions")
        
        print(f"[知识提取] 从数据库读取 API 配置: endpoint={api_endpoint}, model={model}, api_key={'已配置' if api_key else '未配置'}")
    
    # 检查 API key 是否配置
    if not api_key:
        error_msg = "API key 未配置，无法进行知识提取"
        print(f"[知识提取] ✗ {error_msg}")
        await knowledge_extraction_progress.push_progress(
            file_id=file_id,
            current=0,
            total=0,
            message=error_msg + "，请在系统设置中配置 OpenRouter API key",
            status="failed"
        )
        return 0
    
    # 获取文件的所有切片（包含 chunk_id）
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT chunk_id, chunk_index, content, metadata_json 
            FROM chunks 
            WHERE file_id = ? 
            ORDER BY chunk_index
        """, (file_id,))
        rows = cursor.fetchall()
        
        if not rows:
            await knowledge_extraction_progress.push_progress(
                file_id=file_id,
                current=0,
                total=0,
                message="文件没有切片，跳过知识提取",
                status="completed"
            )
            return 0
        
        chunks_with_ids = []
        for row in rows:
            chunks_with_ids.append({
                "chunk_id": row["chunk_id"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "metadata": json.loads(row["metadata_json"])
            })
    
    total_chunks = len(chunks_with_ids)
    processor = MarkdownProcessor(enable_knowledge_extraction=True)
    extracted_count = 0
    skipped_count = 0  # 跳过的重复知识点数量
    
    # 获取文件中已存在的知识点（用于去重）
    existing_nodes = db.get_file_knowledge_nodes(file_id)
    print(f"[知识提取] 文件 {file_id} 中已存在 {len(existing_nodes)} 个知识点")
    
    # 当前批次提取的知识点集合（用于本次提取过程中的去重）
    # 存储标准化后的概念名称用于快速比较
    current_batch_concepts = set()
    
    # 初始化进度
    await knowledge_extraction_progress.push_progress(
        file_id=file_id,
        current=0,
        total=total_chunks,
        message=f"开始提取知识点，共 {total_chunks} 个切片（已存在 {len(existing_nodes)} 个知识点）",
        status="extracting"
    )
    
    # 对每个切片提取知识点
    for idx, chunk_data in enumerate(chunks_with_ids):
        chunk_id = chunk_data["chunk_id"]
        chunk_content = chunk_data.get("content", "")
        chunk_metadata = chunk_data.get("metadata", {})
        
        if not chunk_content.strip():
            # 更新进度（跳过空切片）
            await knowledge_extraction_progress.push_progress(
                file_id=file_id,
                current=idx + 1,
                total=total_chunks,
                current_chunk=f"切片 {chunk_data.get('chunk_index', idx + 1)}（空内容，跳过）",
                message=f"处理中: {idx + 1}/{total_chunks}",
                status="extracting"
            )
            continue
        
        # 更新进度
        chunk_info = chunk_metadata.get("section_title") or chunk_metadata.get("Header 1") or chunk_metadata.get("Header 2") or f"切片 {chunk_data.get('chunk_index', idx + 1)}"
        await knowledge_extraction_progress.push_progress(
            file_id=file_id,
            current=idx,
            total=total_chunks,
            current_chunk=chunk_info[:50],  # 限制长度
            message=f"正在提取知识点: {chunk_info[:30]}... ({idx + 1}/{total_chunks})",
            status="extracting"
        )
        
        try:
            # 调用 LLM 提取知识点
            knowledge_data = await processor.extract_knowledge_metadata(
                chunk_content, chunk_metadata, api_key, model, api_endpoint, file_id
            )
            
            if knowledge_data:
                core_concept = knowledge_data["core_concept"]
                normalized_concept = normalize_concept_name(core_concept)
                
                # 检查是否重复
                is_duplicate = False
                duplicate_reason = ""
                
                # 先检查与当前批次已提取的知识点（使用标准化名称快速比较）
                if normalized_concept in current_batch_concepts:
                    is_duplicate = True
                    duplicate_reason = "与当前批次已提取的知识点重复"
                
                # 如果未重复，检查与数据库中已存在的知识点（使用更精确的相似度比较）
                if not is_duplicate:
                    for node in existing_nodes:
                        existing_concept = node["core_concept"]
                        if is_concept_duplicate(core_concept, existing_concept):
                            is_duplicate = True
                            duplicate_reason = f"与已有知识点重复: {existing_concept}"
                            break
                
                if is_duplicate:
                    skipped_count += 1
                    print(f"[知识提取] ⊘ 跳过重复知识点: {core_concept} ({duplicate_reason})")
                    # 更新进度
                    await knowledge_extraction_progress.push_progress(
                        file_id=file_id,
                        current=idx + 1,
                        total=total_chunks,
                        current_chunk=chunk_info[:50],
                        message=f"跳过重复知识点: {core_concept[:30]}...",
                        status="extracting"
                    )
                    continue
                
                # 生成节点 ID
                node_id = str(uuid.uuid4())
                
                # 存储知识点节点（不包含 prerequisites，确保知识点独立）
                # 默认设置为 level 3（三级原子点），parent_id 为 None（后续可构建层级关系）
                success = db.store_knowledge_node(
                    node_id=node_id,
                    chunk_id=chunk_id,
                    file_id=file_id,
                    core_concept=core_concept,
                    level=3,  # 默认三级原子点
                    parent_id=None,  # 后续可构建层级关系
                    prerequisites=[],  # 知识点应该是独立的，不包含前置依赖
                    confusion_points=knowledge_data.get("confusion_points", []),
                    bloom_level=knowledge_data["bloom_level"],
                    application_scenarios=knowledge_data.get("application_scenarios")
                )
                
                if success:
                    extracted_count += 1
                    # 添加到当前批次集合，避免后续重复（使用标准化名称）
                    current_batch_concepts.add(normalized_concept)
                    print(f"[知识提取] ✓ 成功提取并存储知识点节点: {core_concept} (chunk_id: {chunk_id}, bloom_level: {knowledge_data['bloom_level']})")
                else:
                    error_msg = f"存储知识点节点失败: {core_concept}"
                    print(f"[知识提取] ✗ {error_msg}")
                    # 更新进度，包含错误信息
                    await knowledge_extraction_progress.push_progress(
                        file_id=file_id,
                        current=idx + 1,
                        total=total_chunks,
                        current_chunk=chunk_info[:50],
                        message=f"存储失败: {error_msg}",
                        status="extracting"
                    )
            else:
                error_msg = f"切片 {chunk_data['chunk_index']} 的知识点提取返回空结果（可能是 API 调用失败或格式解析失败）"
                print(f"[知识提取] ✗ {error_msg}")
                # 更新进度，包含错误信息
                await knowledge_extraction_progress.push_progress(
                    file_id=file_id,
                    current=idx + 1,
                    total=total_chunks,
                    current_chunk=chunk_info[:50],
                    message=f"提取失败: 请检查后端日志",
                    status="extracting"
                )
                        
        except Exception as e:
            error_msg = f"切片 {chunk_data.get('chunk_index', 'unknown')} 的知识点提取异常: {str(e)}"
            print(f"[知识提取] ✗ {error_msg}")
            import traceback
            traceback.print_exc()
            # 更新进度，包含错误信息
            await knowledge_extraction_progress.push_progress(
                file_id=file_id,
                current=idx + 1,
                total=total_chunks,
                current_chunk=chunk_info[:50] if 'chunk_info' in locals() else f"切片 {chunk_data.get('chunk_index', idx + 1)}",
                message=f"异常: {str(e)[:50]}",
                status="extracting"
            )
            continue
    
    # 完成进度
    message = f"知识点提取完成：成功提取 {extracted_count} 个新知识点"
    if skipped_count > 0:
        message += f"，跳过 {skipped_count} 个重复知识点"
    message += f"（共处理 {total_chunks} 个切片）"
    
    await knowledge_extraction_progress.push_progress(
        file_id=file_id,
        current=total_chunks,
        total=total_chunks,
        message=message,
        status="completed"
    )
    
    # 重新加载知识图谱（确保新提取的知识点能够被查询到）
    try:
        from graph_manager import knowledge_graph
        knowledge_graph.reload()
        print(f"知识图谱已重新加载，当前节点数: {knowledge_graph.graph.number_of_nodes()}")
    except Exception as e:
        print(f"警告：重新加载知识图谱失败: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"知识点提取完成：成功提取 {extracted_count} 个新知识点，跳过 {skipped_count} 个重复知识点（共处理 {len(chunks_with_ids)} 个切片）")
    return extracted_count


async def build_textbook_knowledge_dependencies(textbook_id: str,
                                                api_key: Optional[str] = None,
                                                model: Optional[str] = None,
                                                api_endpoint: Optional[str] = None) -> Dict[str, Any]:
    """
    为教材下的所有知识点构建依赖关系
    
    使用 LLM 分析教材下所有知识点之间的依赖关系，并更新数据库中的 prerequisites 字段。
    当知识点数量较多时，会自动采用分批处理策略以避免响应被截断。
    
    Args:
        textbook_id: 教材 ID
        api_key: OpenRouter API 密钥（可选，默认从数据库读取）
        model: 模型名称（可选，默认从数据库读取）
        api_endpoint: API端点URL（可选，默认从数据库读取）
        
    Returns:
        构建结果字典，包含：
        - success: 是否成功
        - total_concepts: 知识点总数
        - dependencies_built: 构建的依赖关系数量
        - message: 结果消息
    """
    from database import db
    from generator import OpenRouterClient
    import httpx
    import json
    
    print(f"[依赖构建] 开始为教材 {textbook_id} 构建知识点依赖关系...")
    
    # 获取教材信息
    textbook = db.get_textbook(textbook_id)
    if not textbook:
        return {
            "success": False,
            "total_concepts": 0,
            "dependencies_built": 0,
            "message": "教材不存在"
        }
    
    textbook_name = textbook.get("name", "")
    
    # 获取教材下的所有知识点
    knowledge_nodes = db.get_textbook_knowledge_nodes(textbook_id)
    if not knowledge_nodes:
        return {
            "success": False,
            "total_concepts": 0,
            "dependencies_built": 0,
            "message": "教材下没有知识点，请先进行知识提取"
        }
    
    total_concepts = len(knowledge_nodes)
    print(f"[依赖构建] 教材 '{textbook_name}' 共有 {total_concepts} 个知识点")
    
    # 如果没有提供 API 配置，从数据库读取
    if not api_key or not model or not api_endpoint:
        ai_config = db.get_ai_config()
        if not api_key:
            api_key = ai_config.get("api_key")
        if not model:
            model = ai_config.get("model", "openai/gpt-4o-mini")
        if not api_endpoint:
            api_endpoint = ai_config.get("api_endpoint", "https://openrouter.ai/api/v1/chat/completions")
    
    # 检查 API key 是否配置
    if not api_key:
        error_msg = "API key 未配置，无法构建依赖关系"
        print(f"[依赖构建] ✗ {error_msg}")
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg + "，请在系统设置中配置 OpenRouter API key"
        }
    
    # 构建知识点列表（用于 LLM 分析）
    concepts_list = []
    for node in knowledge_nodes:
        concept_info = {
            "node_id": node["node_id"],
            "core_concept": node["core_concept"],
            "bloom_level": node.get("bloom_level", 3),
            "confusion_points": node.get("confusion_points", []),
            "application_scenarios": node.get("application_scenarios", [])
        }
        concepts_list.append(concept_info)
    
    # 判断是否需要分批处理（知识点数量超过阈值时）
    BATCH_SIZE = 50  # 每批处理的知识点数量
    USE_BATCH_MODE = total_concepts > BATCH_SIZE
    
    if USE_BATCH_MODE:
        print(f"[依赖构建] 知识点数量较多（{total_concepts} > {BATCH_SIZE}），采用分批处理模式")
        return await _build_dependencies_in_batches(
            textbook_id, textbook_name, concepts_list, knowledge_nodes,
            api_key, model, api_endpoint, BATCH_SIZE
        )
    
    # 单次处理模式（知识点数量较少时）
    return await _build_dependencies_single_batch(
        textbook_id, textbook_name, concepts_list, knowledge_nodes,
        api_key, model, api_endpoint
    )


async def _build_dependencies_single_batch(
    textbook_id: str,
    textbook_name: str,
    concepts_list: List[Dict[str, Any]],
    knowledge_nodes: List[Dict[str, Any]],
    api_key: str,
    model: str,
    api_endpoint: str
) -> Dict[str, Any]:
    """
    单次处理所有知识点的依赖关系构建
    
    Args:
        textbook_id: 教材 ID
        textbook_name: 教材名称
        concepts_list: 知识点列表
        knowledge_nodes: 知识点节点列表
        api_key: API 密钥
        model: 模型名称
        api_endpoint: API 端点
        
    Returns:
        构建结果字典
    """
    from database import db
    from generator import (
        OpenRouterClient, 
        get_timeout_config, 
        get_max_output_tokens,
        MIN_DEPENDENCY_BUILDING_TOKENS
    )
    import httpx
    import json
    
    total_concepts = len(concepts_list)
    
    # 构建提示词（使用 PromptManager）
    system_prompt = PromptManager.get_dependency_analysis_system_prompt()
    # 注意：由于依赖关系分析需要包含 node_id 等特殊字段，我们需要自定义构建 user_prompt
    # 但系统提示词可以使用通用的

    concepts_text = "\n".join([
        f"{idx + 1}. {concept['core_concept']} (node_id: {concept['node_id']}, Bloom Level: {concept['bloom_level']})"
        for idx, concept in enumerate(concepts_list)
    ])
    
    # 构建用户提示词（由于需要包含 node_id 等特殊要求，需要自定义构建）
    # 但可以使用 PromptManager 的基础模板，然后添加特定要求
    base_user_prompt = PromptManager.build_dependency_analysis_user_prompt(
        textbook_name=textbook_name,
        concepts_list=concepts_text
    )
    # 扩展用户提示词，添加 node_id 等特定要求
    user_prompt = f"""{base_user_prompt}

**额外要求（特定于本系统）**：
1. **必须返回所有知识点的依赖关系**：返回的 `dependencies` 数组必须包含上述列表中的每一个知识点，不能遗漏任何知识点。
2. **每个依赖项必须包含 `node_id` 字段**，该字段必须与上述知识点列表中的 `node_id` 完全匹配
3. 前置依赖必须是上述列表中的知识点（使用 `core_concept` 名称）
4. 如果某个知识点没有前置依赖，prerequisites 应该为空数组 `[]`
5. **请确保返回完整的 JSON，不要被截断**

**重要**：请确保返回的 `dependencies` 数组包含所有 {total_concepts} 个知识点，不能遗漏任何知识点。

**JSON 格式要求**：
```json
{{
  "dependencies": [
    {{
      "node_id": "节点ID（必须）",
      "core_concept": "知识点名称（可选，用于验证）",
      "prerequisites": ["前置知识点1", "前置知识点2", ...]
    }},
    ...
  ]
}}
```"""
    
    # 创建 OpenRouter 客户端
    client = OpenRouterClient(api_key=api_key, model=model, api_endpoint=api_endpoint)
    
    # 调用 LLM API
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-repo",
        "X-Title": "AI Question Generator",
    }
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    # 根据知识点数量动态调整 max_tokens
    # 估算：每个知识点大约需要 100-200 tokens，加上 JSON 结构，预留更多空间
    estimated_tokens = total_concepts * 200 + 1000
    
    # 使用统一的 token 限制配置
    model_max = get_max_output_tokens(model, "dependency_building")
    max_tokens = max(MIN_DEPENDENCY_BUILDING_TOKENS, min(model_max, estimated_tokens))
    
    print(f"[依赖构建] 使用 max_tokens={max_tokens} (估算需要 {estimated_tokens} tokens)")
    
    payload = {
        "model": client.model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    
    dependencies_built = 0
    
    try:
        # 使用针对模型的超时配置
        timeout_config = get_timeout_config(model, is_stream=False)
        async with httpx.AsyncClient(timeout=timeout_config) as http_client:
            response = await http_client.post(
                client.api_endpoint,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 提取生成的文本
            if "choices" not in result or len(result["choices"]) == 0:
                error_msg = "API 返回结果中没有 choices 字段"
                print(f"[依赖构建] ✗ {error_msg}")
                return {
                    "success": False,
                    "total_concepts": total_concepts,
                    "dependencies_built": 0,
                    "message": error_msg
                }
            
            generated_text = result["choices"][0]["message"]["content"].strip()
            finish_reason = result["choices"][0].get("finish_reason", "")
            
            # 如果 finish_reason 是 "length"，继续生成剩余内容
            if finish_reason == "length":
                print(f"[依赖构建] ⚠ 检测到内容因长度限制被截断，正在续写...")
                
                # 续写逻辑
                continuation_count = 0
                max_continuations = 3
                full_text = generated_text
                
                while continuation_count < max_continuations:
                    continuation_count += 1
                    print(f"[依赖构建] 续写第 {continuation_count}/{max_continuations} 次...")
                    
                    # 构建续写消息
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
                        "model": model,
                        "messages": continuation_messages,
                        "temperature": 0.3,
                        "max_tokens": max_tokens,
                    }
                    
                    try:
                        continuation_response = await http_client.post(
                            client.api_endpoint,
                            headers=headers,
                            json=continuation_payload
                        )
                        continuation_response.raise_for_status()
                        
                        continuation_result = continuation_response.json()
                        
                        if "choices" not in continuation_result or len(continuation_result["choices"]) == 0:
                            print(f"[依赖构建] ⚠ 续写请求返回结果中没有 choices 字段，停止续写")
                            break
                        
                        continuation_text = continuation_result["choices"][0]["message"]["content"].strip()
                        continuation_finish_reason = continuation_result["choices"][0].get("finish_reason", "")
                        
                        # 拼接续写内容
                        full_text += continuation_text
                        
                        # 如果 finish_reason 不是 "length"，说明已经完成
                        if continuation_finish_reason != "length":
                            print(f"[依赖构建] ✓ 续写完成（finish_reason: {continuation_finish_reason}）")
                            break
                        
                        # 如果还是 "length"，继续下一轮续写
                        if continuation_count < max_continuations:
                            print(f"[依赖构建] ⚠ 续写内容仍被截断，继续续写...")
                    
                    except Exception as e:
                        print(f"[依赖构建] ⚠ 续写请求失败: {str(e)}，停止续写")
                        break
                
                generated_text = full_text
            
            # 清理可能的代码块标记
            if generated_text.startswith("```json"):
                generated_text = generated_text[7:].strip()
            elif generated_text.startswith("```"):
                generated_text = generated_text[3:].strip()
            
            if generated_text.endswith("```"):
                generated_text = generated_text[:-3].strip()
            
            # 尝试解析 JSON，如果失败则尝试修复
            dependencies_data = None
            try:
                dependencies_data = json.loads(generated_text)
            except json.JSONDecodeError as json_error:
                print(f"[依赖构建] ⚠ JSON 解析失败，尝试修复被截断的 JSON: {json_error}")
                # 尝试修复被截断的 JSON
                fixed_text = _try_fix_truncated_json(generated_text, total_concepts)
                if fixed_text:
                    try:
                        dependencies_data = json.loads(fixed_text)
                        print(f"[依赖构建] ✓ JSON 修复成功")
                    except json.JSONDecodeError as e2:
                        print(f"[依赖构建] ✗ JSON 修复失败: {e2}")
                        raise json_error  # 抛出原始错误
                else:
                    raise json_error  # 如果无法修复，抛出原始错误
            
            if dependencies_data:
                
                print(f"[依赖构建] JSON 解析成功，返回的数据结构: {list(dependencies_data.keys())}")
                
                if "dependencies" not in dependencies_data:
                    error_msg = f"API 返回结果中没有 dependencies 字段。返回的字段: {list(dependencies_data.keys())}"
                    print(f"[依赖构建] ✗ {error_msg}")
                    print(f"[依赖构建] 完整响应: {json.dumps(dependencies_data, ensure_ascii=False, indent=2)[:2000]}")
                    return {
                        "success": False,
                        "total_concepts": total_concepts,
                        "dependencies_built": 0,
                        "message": error_msg
                    }
                
                # 构建 node_id 到概念的映射
                node_id_to_concept = {node["node_id"]: node["core_concept"] for node in knowledge_nodes}
                concept_to_node_id = {node["core_concept"]: node["node_id"] for node in knowledge_nodes}
                
                dependencies_list = dependencies_data.get("dependencies", [])
                print(f"[依赖构建] 收到 {len(dependencies_list)} 个知识点的依赖关系（期望 {total_concepts} 个）")
                print(f"[依赖构建] 知识点映射: {len(concept_to_node_id)} 个知识点")
                
                if len(dependencies_list) < total_concepts:
                    print(f"[依赖构建] ⚠ 警告：返回的依赖关系数量 ({len(dependencies_list)}) 少于知识点总数 ({total_concepts})")
                
                # 记录已处理的 node_id，确保没有遗漏
                processed_node_ids = set()
                
                # 更新数据库中的依赖关系
                for dep_info in dependencies_list:
                    node_id = dep_info.get("node_id")
                    core_concept = dep_info.get("core_concept")
                    prerequisites = dep_info.get("prerequisites", [])
                    
                    # 如果提供了 core_concept 但没有 node_id，通过 core_concept 查找 node_id
                    if not node_id and core_concept:
                        node_id = concept_to_node_id.get(core_concept.strip())
                        if not node_id:
                            print(f"[依赖构建] ⚠ 警告：找不到知识点 '{core_concept}' 对应的 node_id，跳过")
                            continue
                    elif not node_id:
                        print(f"[依赖构建] ⚠ 警告：依赖信息中既没有 node_id 也没有 core_concept，跳过")
                        continue
                    
                    # 验证 node_id 是否存在
                    if node_id not in node_id_to_concept:
                        print(f"[依赖构建] ⚠ 警告：node_id '{node_id}' 不在教材知识点列表中，跳过")
                        continue
                    
                    actual_concept = node_id_to_concept[node_id]
                    
                    # 验证 prerequisites 中的知识点是否存在于教材中
                    valid_prerequisites = []
                    for prereq_concept in prerequisites:
                        prereq_concept = prereq_concept.strip()
                        if prereq_concept in concept_to_node_id:
                            valid_prerequisites.append(prereq_concept)
                        else:
                            print(f"[依赖构建] ⚠ 警告：前置依赖 '{prereq_concept}' 不在教材知识点列表中，已忽略")
                    
                    # 更新数据库（即使 prerequisites 为空也要更新，确保清空旧的依赖关系）
                    try:
                        success = db.update_knowledge_node_prerequisites(node_id, valid_prerequisites)
                        if success:
                            dependencies_built += 1
                            processed_node_ids.add(node_id)
                            if valid_prerequisites:
                                print(f"[依赖构建] ✓ 更新知识点 '{actual_concept}' (node_id: {node_id}) 的依赖关系: {len(valid_prerequisites)} 个前置依赖")
                            else:
                                print(f"[依赖构建] ✓ 更新知识点 '{actual_concept}' (node_id: {node_id}) 的依赖关系: 无前置依赖（已清空）")
                        else:
                            print(f"[依赖构建] ✗ 更新知识点 '{actual_concept}' (node_id: {node_id}) 的依赖关系失败（数据库更新返回 False）")
                    except Exception as e:
                        print(f"[依赖构建] ✗ 更新知识点 '{actual_concept}' (node_id: {node_id}) 的依赖关系时发生异常: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 检查是否有遗漏的知识点
                all_node_ids = set(node["node_id"] for node in knowledge_nodes)
                missing_node_ids = all_node_ids - processed_node_ids
                if missing_node_ids:
                    print(f"[依赖构建] ⚠ 警告：有 {len(missing_node_ids)} 个知识点没有被处理:")
                    for missing_node_id in missing_node_ids:
                        missing_concept = node_id_to_concept.get(missing_node_id, "未知")
                        print(f"[依赖构建]   - {missing_concept} (node_id: {missing_node_id})")
                
                # 重新加载知识图谱
                try:
                    from graph_manager import knowledge_graph
                    knowledge_graph.reload()
                    print(f"[依赖构建] ✓ 知识图谱已重新加载，当前节点数: {knowledge_graph.graph.number_of_nodes()}")
                except Exception as e:
                    print(f"[依赖构建] ⚠ 警告：重新加载知识图谱失败: {e}")
                
                message = f"成功为 {dependencies_built} 个知识点构建了依赖关系（共 {total_concepts} 个知识点）"
                print(f"[依赖构建] ✓ {message}")
                
                return {
                    "success": True,
                    "total_concepts": total_concepts,
                    "dependencies_built": dependencies_built,
                    "message": message
                }
            else:
                # 如果 dependencies_data 为 None（JSON 解析失败且无法修复）
                error_msg = "JSON 解析失败且无法修复"
                print(f"[依赖构建] ✗ {error_msg}")
                print(f"[依赖构建] 原始响应前1000字符:\n{generated_text[:1000]}")
                return {
                    "success": False,
                    "total_concepts": total_concepts,
                    "dependencies_built": 0,
                    "message": error_msg
                }
                
    except json.JSONDecodeError as e:
        # 如果 JSON 解析失败且修复也失败，会抛出异常到这里
        error_msg = f"JSON 解析失败: {e}"
        print(f"[依赖构建] ✗ {error_msg}")
        if 'generated_text' in locals():
            print(f"[依赖构建] 原始响应前1000字符:\n{generated_text[:1000]}")
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg
        }
    except httpx.HTTPStatusError as e:
        error_msg = f"API 调用失败，状态码: {e.response.status_code}"
        print(f"[依赖构建] ✗ {error_msg}")
        print(f"[依赖构建] 响应内容: {e.response.text[:500]}")
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg
        }
    except httpx.RequestError as e:
        error_msg = f"API 请求失败: {str(e)}"
        print(f"[依赖构建] ✗ {error_msg}")
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg
        }
    except Exception as e:
        error_msg = f"构建依赖关系失败: {str(e)}"
        print(f"[依赖构建] ✗ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg
        }

