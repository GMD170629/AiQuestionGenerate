"""
题目生成测试路由
用于测试单个切片的题目生成功能，返回详细的调试信息
"""

import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from generator import (
    OpenRouterClient,
    extract_knowledge_from_chunks,
    build_knowledge_based_prompt,
    build_task_specific_prompt,
    build_system_prompt,
    build_context_from_chunks,
    get_chapter_name_from_chunks,
    calculate_max_tokens_for_questions
)
from prompts import PromptManager
from database import db
from document_cache import document_cache

router = APIRouter(prefix="/test-generation", tags=["题目生成测试"])


class TestGenerationRequest(BaseModel):
    """测试生成请求"""
    textbook_id: Optional[str] = None
    file_id: str
    chunk_index: int
    question_count: int = 5
    question_types: Optional[list[str]] = None


@router.post("/test")
async def test_generation(request: TestGenerationRequest):
    """
    测试单个切片的题目生成功能
    
    返回详细的调试信息，包括：
    - 应用的提示词（系统提示词、用户提示词）
    - LLM返回的原始响应
    - 生成的题目
    - 应用的知识点信息
    - 切片内容
    - LLM接口调用过程（请求信息、HTTP状态码）
    - LLM接口返回的原始信息（tokens使用情况、finish_reason等）
    """
    try:
        # 1. 获取文件信息
        file_info = db.get_file(request.file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        # 2. 获取切片列表
        chunks = db.get_chunks(request.file_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="文件未解析或没有切片")
        
        # 3. 检查切片索引
        if request.chunk_index < 0 or request.chunk_index >= len(chunks):
            raise HTTPException(
                status_code=400,
                detail=f"切片索引超出范围，有效范围：0-{len(chunks)-1}"
            )
        
        # 4. 获取指定的切片
        selected_chunk = chunks[request.chunk_index]
        
        # 5. 获取教材信息
        textbook_name = None
        if request.textbook_id:
            textbook = db.get_textbook(request.textbook_id)
            if textbook:
                textbook_name = textbook.get("name")
        
        # 6. 提取知识点信息
        chunk_list = [selected_chunk]
        knowledge_info = extract_knowledge_from_chunks(chunk_list)
        
        # 7. 构建提示词
        knowledge_prompt = ""
        if knowledge_info.get("core_concept"):
            knowledge_prompt = build_knowledge_based_prompt(knowledge_info, chunk_list)
        else:
            # 如果没有知识点信息，只提供基本信息
            knowledge_prompt = "## 教材信息：\n"
            if textbook_name:
                knowledge_prompt += f"**教材名称**：{textbook_name}\n"

        # 提取章节名称
        chapter_name = get_chapter_name_from_chunks(chunk_list)
        if chapter_name:
            knowledge_prompt += f"\n**章节**：{chapter_name}\n"
        
        # 构建题型专用提示词（具体任务要求）
        question_types = request.question_types or ["单选题", "多选题", "判断题"]
        adaptive_mode = not request.question_types or len(request.question_types) == 0
        # 测试接口默认只生成中等和困难题目，不生成简单题目
        allowed_difficulties = ["中等", "困难"]
        task_prompt = build_task_specific_prompt(
            question_types if not adaptive_mode else [],
            request.question_count,
            context=None,
            adaptive=adaptive_mode,
            knowledge_context=knowledge_info if knowledge_info.get("core_concept") else None,
            allowed_difficulties=allowed_difficulties
        )
        
        # 构建连贯性说明
        core_concept = knowledge_info.get("core_concept")
        prerequisites_context = knowledge_info.get("prerequisites_context", [])
        coherence_prompt = PromptManager.build_coherence_prompt(
            prerequisites_context=prerequisites_context,
            core_concept=core_concept
        )
        
        # 构建用户提示词
        user_prompt = PromptManager.build_user_prompt_base(
            adaptive=adaptive_mode,
            question_count=request.question_count,
            chapter_name=chapter_name,
            core_concept=None,  # 已在 knowledge_prompt 中包含
            knowledge_prompt=knowledge_prompt,
            prerequisites_prompt="",  # 已在 knowledge_prompt 中包含
            coherence_prompt=coherence_prompt,
            task_prompt=task_prompt,
            context=None  # 不使用原始文本上下文
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
        
        # 8. 调用 LLM API（测试模式，返回原始响应）
        client = OpenRouterClient()
        
        headers = {
            "Authorization": f"Bearer {client.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "AI Question Generator",
        }
        
        # 使用统一的 token 限制计算函数
        max_tokens = calculate_max_tokens_for_questions(
            request.question_count,
            model=client.model,
            adaptive_mode=not request.question_types or len(request.question_types) == 0
        )
        
        payload = {
            "model": client.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        
        import httpx
        from generator import get_timeout_config
        
        # 初始化调试信息变量
        request_info = {
            "api_endpoint": client.api_endpoint,
            "model": client.model,
            "payload": {
                "model": payload["model"],
                "messages_count": len(payload["messages"]),
                "temperature": payload["temperature"],
                "max_tokens": payload["max_tokens"],
            },
            "headers": {
                "Content-Type": headers["Content-Type"],
                "HTTP-Referer": headers["HTTP-Referer"],
                "X-Title": headers["X-Title"],
                "Authorization": "Bearer ***" if client.api_key else None,  # 隐藏API key
            },
        }
        http_status_code = None
        api_response_full = None
        finish_reason = None
        usage_info = None
        error_response_text = None
        raw_response = None
        questions_data = None
        
        # 使用针对模型的超时配置
        timeout_config = get_timeout_config(client.model, is_stream=False)
        
        try:
            async with httpx.AsyncClient(timeout=timeout_config) as http_client:
                response = await http_client.post(
                    client.api_endpoint,
                    headers=headers,
                    json=payload
                )
                
                # 保存HTTP状态码
                http_status_code = response.status_code
                
                # 检查HTTP状态码
                response.raise_for_status()
                
                result = response.json()
                
                # 保存完整的API响应（用于调试）
                api_response_full = result.copy()
                
                # 提取生成的文本
                if "choices" not in result or len(result["choices"]) == 0:
                    raise ValueError("API 返回结果中没有 choices 字段")
                
                # 提取finish_reason
                if len(result["choices"]) > 0:
                    finish_reason = result["choices"][0].get("finish_reason", None)
                
                # 提取usage信息（tokens使用情况）
                if "usage" in result:
                    usage_info = result["usage"]
                
                raw_response = result["choices"][0]["message"]["content"].strip()
                
                # 解析生成的题目
                generated_text = raw_response.strip()
                
                # 清理可能的代码块标记
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
                except json.JSONDecodeError:
                    # 尝试提取 JSON 数组部分
                    import re
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
                
                # 9. 构建返回结果
                result_data = {
                    "chunk_info": {
                        "chunk_index": request.chunk_index,
                        "total_chunks": len(chunks),
                        "content": selected_chunk.get("content", ""),
                        "metadata": selected_chunk.get("metadata", {}),
                        "chapter_name": chapter_name,
                    },
                    "knowledge_info": {
                        "core_concept": knowledge_info.get("core_concept"),
                        "bloom_level": knowledge_info.get("bloom_level"),
                        "prerequisites": knowledge_info.get("prerequisites", []),
                        "prerequisites_context": knowledge_info.get("prerequisites_context", []),
                        "confusion_points": knowledge_info.get("confusion_points", []),
                        "application_scenarios": knowledge_info.get("application_scenarios", []),
                        "knowledge_summary": knowledge_info.get("knowledge_summary", ""),
                    },
                    "prompts": {
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                        "knowledge_prompt": knowledge_prompt,
                        "task_prompt": task_prompt,
                        "coherence_prompt": coherence_prompt,
                    },
                    "llm_response": {
                        "raw_response": raw_response,
                        "parsed_questions": questions_data if questions_data else None,
                        "parse_success": questions_data is not None,
                        "http_status_code": http_status_code,
                        "finish_reason": finish_reason,
                        "usage": usage_info,  # 包含 prompt_tokens, completion_tokens, total_tokens
                        "api_response": {
                            "id": api_response_full.get("id") if api_response_full else None,
                            "model": api_response_full.get("model") if api_response_full else None,
                            "object": api_response_full.get("object") if api_response_full else None,
                            "created": api_response_full.get("created") if api_response_full else None,
                            "choices": [
                                {
                                    "index": choice.get("index"),
                                    "finish_reason": choice.get("finish_reason"),
                                    "message_role": choice.get("message", {}).get("role"),
                                    "message_content_length": len(choice.get("message", {}).get("content", "")),
                                }
                                for choice in api_response_full.get("choices", [])
                            ] if api_response_full else [],
                            "usage": usage_info,  # 包含 prompt_tokens, completion_tokens, total_tokens
                        } if api_response_full else None,
                        "api_response_raw": api_response_full,  # 完整的原始API响应（用于详细调试）
                    },
                    "llm_request": request_info,
                    "file_info": {
                        "file_id": request.file_id,
                        "filename": file_info.get("filename", ""),
                        "textbook_name": textbook_name,
                    },
                }
                
                return JSONResponse(content=result_data)
                
        except httpx.HTTPStatusError as e:
            # HTTP错误，保存状态码和错误响应
            http_status_code = e.response.status_code
            try:
                error_response_text = e.response.text[:1000]  # 限制长度
            except:
                error_response_text = None
            # 重新抛出异常，但会在外层捕获并返回调试信息
            raise
        except httpx.RequestError as e:
            # 网络错误
            raise
        except Exception as e:
            # 其他错误
            raise
            
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        # HTTP错误，返回详细的调试信息
        try:
            error_response_text = e.response.text[:1000] if e.response else None
        except:
            error_response_text = None
        
        # 构建包含调试信息的错误响应
        error_data = {
            "error": "LLM API 请求失败",
            "http_status_code": e.response.status_code if e.response else None,
            "error_message": str(e),
            "error_response": error_response_text,
            "llm_request": request_info,
            "llm_response": {
                "http_status_code": e.response.status_code if e.response else None,
                "finish_reason": finish_reason,
                "usage": usage_info,
            },
        }
        raise HTTPException(status_code=500, detail=error_data)
    except httpx.RequestError as e:
        # 网络错误
        error_data = {
            "error": "网络请求错误",
            "error_message": str(e),
            "llm_request": request_info,
            "llm_response": {
                "http_status_code": http_status_code,
                "finish_reason": finish_reason,
                "usage": usage_info,
            },
        }
        raise HTTPException(status_code=500, detail=error_data)
    except Exception as e:
        # 其他错误，尝试返回部分调试信息
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "测试生成失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "测试生成失败"
        
        error_data = {
            "error": "测试生成失败",
            "error_message": error_msg,
            "http_status_code": http_status_code,
            "llm_request": request_info,
            "llm_response": {
                "http_status_code": http_status_code,
                "finish_reason": finish_reason,
                "usage": usage_info,
                "raw_response": raw_response,
                "parsed_questions": questions_data,
            },
        }
        raise HTTPException(status_code=500, detail=error_data)


@router.get("/chunks/{file_id}")
async def get_file_chunks_for_test(file_id: str):
    """
    获取文件的切片列表（用于测试选择）
    """
    try:
        file_info = db.get_file(file_id)
        if not file_info:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        chunks = db.get_chunks(file_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="文件未解析或没有切片")
        
        # 格式化切片信息
        from md_processor import MarkdownProcessor
        processor = MarkdownProcessor()
        
        chunk_list = []
        for idx, chunk in enumerate(chunks):
            metadata = chunk.get("metadata", {})
            chapter_name = processor.get_chapter_name(metadata)
            chapter_level = processor.get_chapter_level(metadata)
            
            # 获取内容预览
            content = chunk.get("content", "")
            content_preview = content[:200] + "..." if len(content) > 200 else content
            
            chunk_list.append({
                "index": idx,
                "content_preview": content_preview,
                "content_length": len(content),
                "chapter_name": chapter_name,
                "chapter_level": chapter_level,
                "metadata": metadata,
            })
        
        return JSONResponse(content={
            "file_id": file_id,
            "filename": file_info.get("filename", ""),
            "total_chunks": len(chunks),
            "chunks": chunk_list,
        })
        
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取切片列表失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取切片列表失败"
        raise HTTPException(status_code=500, detail=f"获取切片列表失败: {error_msg}")

