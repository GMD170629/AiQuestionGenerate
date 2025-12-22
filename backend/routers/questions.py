"""
题目生成和查询相关路由
"""

import json as json_module
import asyncio
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from generator import (
    generate_questions,
    select_random_chunks,
    build_context_from_chunks,
    get_chapter_name_from_chunks,
    OpenRouterClient
)
from md_processor import MarkdownProcessor
from document_cache import document_cache
from database import db
from models import QuestionGenerationRequest, QuestionList

router = APIRouter(prefix="/generate", tags=["题目生成"])


@router.post("", response_model=QuestionList)
async def generate_questions_endpoint(request: QuestionGenerationRequest):
    """
    生成题目接口（非流式，保持向后兼容）
    
    根据上传的 Markdown 文件生成习题。
    从缓存的文档切片中随机抽取 1-2 个相关切片，调用 LLM 生成 5-10 道题目。
    
    Args:
        request: 题目生成请求，包含文件 ID、题型、数量等参数
    
    Returns:
        QuestionList: 生成的题目列表，包含题目详情和章节信息
    """
    # 检查文件是否存在
    file_id = request.file_id
    
    # 从缓存中获取文档切片
    chunks = document_cache.get_chunks(file_id)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail=f"文件 {file_id} 未找到或未解析。请先上传并解析文件。"
        )
    
    # 如果指定了章节，筛选相关切片
    if request.chapter:
        filtered_chunks = []
        processor = MarkdownProcessor()
        for chunk in chunks:
            chapter_name = processor.get_chapter_name(chunk.get("metadata", {}))
            if chapter_name == request.chapter:
                filtered_chunks.append(chunk)
        
        if not filtered_chunks:
            raise HTTPException(
                status_code=404,
                detail=f"未找到章节 '{request.chapter}' 的内容。"
            )
        chunks = filtered_chunks
    
    try:
        # 计算总题目数量（每种题型生成指定数量）
        total_question_count = len(request.question_types) * request.question_count
        
        # 确保总数量在 5-10 范围内
        if total_question_count > 10:
            # 如果超过 10 道，按比例减少每种题型的数量
            adjusted_count = max(1, 10 // len(request.question_types))
            total_question_count = len(request.question_types) * adjusted_count
        elif total_question_count < 5:
            # 如果少于 5 道，增加到 5 道
            total_question_count = 5
        
        # 生成题目
        question_list = await generate_questions(
            chunks=chunks,
            question_count=total_question_count,
            question_types=request.question_types,
            chunks_per_request=2  # 每次随机抽取 1-2 个切片
        )
        
        # 添加来源文件信息
        metadata = document_cache.get_metadata(file_id)
        if metadata:
            question_list.source_file = metadata.get("filename", file_id)
        
        # 保存题目到数据库
        try:
            questions_dict = [q.model_dump() for q in question_list.questions]
            db.store_questions(file_id, questions_dict, question_list.source_file)
        except Exception as e:
            # 保存失败不影响返回结果，只记录错误
            print(f"保存题目到数据库失败: {e}")
        
        return question_list
        
    except ValueError as e:
        # 安全地处理异常消息，避免使用 str() 导致编码错误
        try:
            # 使用 repr() 而不是 str()，repr() 更安全地处理 Unicode
            error_msg = repr(e) if hasattr(e, '__repr__') else "请求参数错误"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "请求参数错误"
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        # 安全地处理异常消息，避免使用 str() 导致编码错误
        try:
            # 使用 repr() 而不是 str()，repr() 更安全地处理 Unicode
            error_msg = repr(e) if hasattr(e, '__repr__') else "生成题目时发生未知错误"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "生成题目时发生未知错误"
        raise HTTPException(status_code=500, detail=f"生成题目失败: {error_msg}")


@router.post("/stream")
async def generate_questions_stream_endpoint(request: QuestionGenerationRequest):
    """
    流式生成题目接口（Server-Sent Events）
    
    根据上传的 Markdown 文件流式生成习题，实时返回生成状态。
    
    Args:
        request: 题目生成请求，包含文件 ID、题型、数量等参数
    
    Returns:
        StreamingResponse: Server-Sent Events 流式响应
    """
    # 检查文件是否存在
    file_id = request.file_id
    
    # 从缓存中获取文档切片
    chunks = document_cache.get_chunks(file_id)
    if not chunks:
        async def error_generator():
            newline = "\n"
            message = f'文件 {file_id} 未找到或未解析。请先上传并解析文件。'
            yield f"data: {json_module.dumps({'status': 'error', 'message': message}, ensure_ascii=False)}{newline}{newline}"
        return StreamingResponse(error_generator(), media_type="text/event-stream")
    
    # 如果指定了章节，筛选相关切片
    if request.chapter:
        filtered_chunks = []
        processor = MarkdownProcessor()
        for chunk in chunks:
            chapter_name = processor.get_chapter_name(chunk.get("metadata", {}))
            if chapter_name == request.chapter:
                filtered_chunks.append(chunk)
        
        if not filtered_chunks:
            async def error_generator():
                newline = "\n"
                chapter = request.chapter
                message = f'未找到章节 \'{chapter}\' 的内容。'
                yield f"data: {json_module.dumps({'status': 'error', 'message': message}, ensure_ascii=False)}{newline}{newline}"
            return StreamingResponse(error_generator(), media_type="text/event-stream")
        chunks = filtered_chunks
    
    async def stream_generator():
        status_queue = asyncio.Queue()
        
        async def process_generation():
            try:
                # 计算总题目数量
                total_question_count = len(request.question_types) * request.question_count
                
                # 确保总数量在 5-10 范围内
                if total_question_count > 10:
                    adjusted_count = max(1, 10 // len(request.question_types))
                    total_question_count = len(request.question_types) * adjusted_count
                elif total_question_count < 5:
                    total_question_count = 5
                
                # 随机选择切片
                selected_chunks = select_random_chunks(chunks, min(2, len(chunks)))
                
                # 构建上下文
                context = build_context_from_chunks(selected_chunks)
                
                # 提取章节名称
                chapter_name = get_chapter_name_from_chunks(selected_chunks)
                
                # 创建 OpenRouter 客户端
                client = OpenRouterClient()
                
                # 调用流式生成（传入 selected_chunks 以获取知识点上下文）
                questions_data = await client.generate_questions_stream(
                    context=context,
                    question_count=total_question_count,
                    question_types=request.question_types,
                    chapter_name=chapter_name,
                    on_status_update=lambda s, d: status_queue.put_nowait((s, d)),
                    chunks=selected_chunks
                )
                
                # 为每个题目添加章节信息
                for question in questions_data:
                    if chapter_name:
                        question["chapter"] = chapter_name
                
                # 添加来源文件信息
                metadata = document_cache.get_metadata(file_id)
                source_file = metadata.get("filename", file_id) if metadata else file_id
                
                # 保存题目到数据库
                try:
                    db.store_questions(file_id, questions_data, source_file)
                except Exception as e:
                    print(f"保存题目到数据库失败: {e}")
                
                # 发送完成状态
                await status_queue.put(("complete", {
                    "questions": questions_data,
                    "total": len(questions_data),
                    "source_file": source_file,
                    "chapter": chapter_name
                }))
                
            except Exception as e:
                try:
                    error_msg = repr(e) if hasattr(e, '__repr__') else "生成题目时发生未知错误"
                except (UnicodeEncodeError, UnicodeDecodeError):
                    error_msg = "生成题目时发生未知错误"
                await status_queue.put(("error", {"message": f"生成题目失败: {error_msg}"}))
        
        # 启动生成任务
        generation_task = asyncio.create_task(process_generation())
        
        # 流式发送状态更新
        try:
            newline = "\n"
            while True:
                try:
                    # 延长超时时间到30分钟，确保在 LLM 正在返回数据时不会断开连接
                    status, data = await asyncio.wait_for(status_queue.get(), timeout=1800.0)
                    
                    if status == "start":
                        json_data = json_module.dumps({'status': 'start', 'message': data.get('message', '开始生成题目...')}, ensure_ascii=False)
                        yield f"data: {json_data}{newline}{newline}"
                    elif status == "streaming":
                        json_data = json_module.dumps({'status': 'streaming', 'text': data.get('text', ''), 'delta': data.get('delta', '')}, ensure_ascii=False)
                        yield f"data: {json_data}{newline}{newline}"
                    elif status == "parsing":
                        json_data = json_module.dumps({'status': 'parsing', 'message': data.get('message', '正在解析...')}, ensure_ascii=False)
                        yield f"data: {json_data}{newline}{newline}"
                    elif status == "progress":
                        json_data = json_module.dumps({'status': 'progress', 'current': data.get('current', 0), 'total': data.get('total', 0), 'message': data.get('message', '')}, ensure_ascii=False)
                        yield f"data: {json_data}{newline}{newline}"
                    elif status == "batch_complete":
                        result = {
                            "status": "batch_complete",
                            "batch_index": data.get("batch_index", 0),
                            "total_batches": data.get("total_batches", 0),
                            "questions": data.get("questions", []),
                            "message": data.get("message", "")
                        }
                        json_data = json_module.dumps(result, ensure_ascii=False)
                        yield f"data: {json_data}{newline}{newline}"
                    elif status == "warning":
                        json_data = json_module.dumps({'status': 'warning', 'message': data.get('message', '')}, ensure_ascii=False)
                        yield f"data: {json_data}{newline}{newline}"
                    elif status == "error":
                        json_data = json_module.dumps({'status': 'error', 'message': data.get('message', '')}, ensure_ascii=False)
                        yield f"data: {json_data}{newline}{newline}"
                        break
                    elif status == "complete":
                        result = {
                            "status": "complete",
                            "questions": data.get("questions", []),
                            "total": data.get("total", 0),
                            "source_file": data.get("source_file"),
                            "chapter": data.get("chapter")
                        }
                        json_data = json_module.dumps(result, ensure_ascii=False)
                        yield f"data: {json_data}{newline}{newline}"
                        break
                except asyncio.TimeoutError:
                    json_data = json_module.dumps({'status': 'error', 'message': '生成超时'}, ensure_ascii=False)
                    yield f"data: {json_data}{newline}{newline}"
                    break
        finally:
            if not generation_task.done():
                generation_task.cancel()
    
    return StreamingResponse(stream_generator(), media_type="text/event-stream")



