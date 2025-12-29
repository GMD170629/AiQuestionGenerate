"""
题目生成测试路由
用于测试单个切片的题目生成功能，返回详细的调试信息
"""

import json
import logging
import traceback
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.ai_service import (
    OpenRouterClient,
    build_context_from_chunks,
    get_chapter_name_from_chunks,
    extract_knowledge_from_chunks,
    build_system_prompt,
    calculate_max_tokens_for_questions,
)
from prompts import PromptManager
from app.core.db import db
from app.core.cache import document_cache

# 配置日志
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test-generation", tags=["题目生成测试"])


class TestGenerationRequest(BaseModel):
    """测试生成请求"""
    textbook_id: Optional[str] = None
    file_id: str
    chunk_index: int
    mode: str = "课后习题"  # 出题模式：课后习题 或 提高习题
    question_count: int = 5
    question_types: Optional[list[str]] = None


class TestPlanRequest(BaseModel):
    """测试规划请求"""
    textbook_id: Optional[str] = None
    file_id: str
    chunk_index: int
    mode: str = "课后习题"  # 出题模式：课后习题 或 提高习题


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
        # 提取章节名称
        chapter_name = get_chapter_name_from_chunks(chunk_list)
        
        # 验证题型列表不能为空
        question_types = request.question_types or ["单选题", "多选题", "判断题"]
        if not question_types or len(question_types) == 0:
            raise HTTPException(status_code=400, detail="question_types 不能为空，必须指定要生成的题型")
        
        # 根据模式设置难度限制
        mode = request.mode or "课后习题"
        if mode == "提高习题":
            # 提高习题模式：只生成中等和困难题目
            allowed_difficulties = ["中等", "困难"]
        else:
            # 课后习题模式：允许所有难度
            allowed_difficulties = None
        
        # 构建完整的用户提示词（所有内容在一个字符串中）
        core_concept = knowledge_info.get("core_concept")
        bloom_level = knowledge_info.get("bloom_level")
        knowledge_summary = knowledge_info.get("knowledge_summary")
        prerequisites_context = knowledge_info.get("prerequisites_context", [])
        confusion_points = knowledge_info.get("confusion_points", [])
        application_scenarios = knowledge_info.get("application_scenarios", [])
        reference_content = selected_chunk.get("content", "")
        
        user_prompt = PromptManager.build_question_generation_user_prompt(
            question_count=request.question_count,
            question_types=question_types,
            chapter_name=chapter_name,
            core_concept=core_concept,
            bloom_level=bloom_level,
            knowledge_summary=knowledge_summary,
            prerequisites_context=prerequisites_context,
            confusion_points=confusion_points,
            application_scenarios=application_scenarios,
            reference_content=reference_content,
            allowed_difficulties=allowed_difficulties,
            strict_plan_mode=False,  # 测试接口不使用严格模式
            textbook_name=textbook_name,
            mode=mode  # 使用指定的模式
        )
        
        # 构建系统提示词（包含通用规则和题型要求，根据模式选择）
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
            model=client.model
        )
        
        payload = {
            "model": client.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }
        
        from app.services.ai_service import get_timeout_config
        
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
        from app.services.markdown_service import MarkdownProcessor
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


@router.post("/plan")
async def plan_single_chunk(request: TestPlanRequest):
    """
    为单个切片规划题目生成任务（自动规划）
    
    返回该切片的题型和数量规划结果
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
        
        if not textbook_name:
            textbook_name = "未命名教材"
        
        # 6. 获取切片信息用于规划
        from app.services.markdown_service import MarkdownProcessor
        processor = MarkdownProcessor()
        
        metadata = selected_chunk.get("metadata", {})
        chapter_name = processor.get_chapter_name(metadata)
        content = selected_chunk.get("content", "")
        content_summary = content[:500] if len(content) > 500 else content
        
        # 从数据库获取 chunk_id（通过 chunk_index 查询）
        chunk_id = None
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunk_id
                FROM chunks
                WHERE file_id = ? AND chunk_index = ?
            """, (request.file_id, request.chunk_index))
            row = cursor.fetchone()
            if row:
                chunk_id = row["chunk_id"]
        
        if chunk_id is None:
            # 如果数据库中没有找到，使用 chunk_index 作为临时 ID
            chunk_id = request.chunk_index
        
        # 7. 构建切片信息用于规划
        chunk_info = {
            "chunk_id": chunk_id,
            "file_id": request.file_id,
            "chapter_name": chapter_name or "未命名章节",
            "content_summary": content_summary
        }
        
        # 8. 调用 AI 进行规划
        mode = request.mode or "课后习题"
        from app.services.ai_service import OpenRouterClient
        
        client = OpenRouterClient()
        
        # 使用 _plan_single_file 方法，但只传入一个切片
        plans = await client._plan_single_file(
            textbook_name=textbook_name,
            file_chunks_info=[chunk_info],
            existing_type_distribution=None,
            mode=mode,
            retry_count=0
        )
        
        if not plans or len(plans) == 0:
            raise HTTPException(status_code=500, detail="规划失败，未返回任何计划")
        
        # 返回第一个（也是唯一的）规划结果
        plan = plans[0]
        
        return JSONResponse(content={
            "plan": {
                "chunk_id": plan.chunk_id,
                "question_count": plan.question_count,
                "question_types": plan.question_types,
                "type_distribution": plan.type_distribution,
                "chapter_name": plan.chapter_name,
            },
            "mode": mode,
            "textbook_name": textbook_name,
        })
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_trace = traceback.format_exc()
        logger.error(f"[测试规划] 规划失败 - 错误: {error_msg}")
        logger.debug(f"[测试规划] 错误堆栈:\n{error_trace}")
        raise HTTPException(
            status_code=500,
            detail=f"规划失败: {error_msg}"
        )

