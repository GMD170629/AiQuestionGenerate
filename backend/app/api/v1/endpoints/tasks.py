"""
任务管理相关路由
"""

import asyncio
import uuid
import logging
import traceback
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.db import db
from app.models import TaskCreate, TaskUpdate
from app.schemas import TextbookGenerationRequest
from app.core.task_manager import task_manager
from app.core.task_progress import task_progress_manager
from app.services.task_service import process_full_textbook_task
from pydantic import BaseModel, Field
from typing import Dict, Any

# 配置日志
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["任务管理"])


@router.get("/{task_id}/progress")
async def get_task_progress(task_id: str):
    """
    获取任务进度（Server-Sent Events）
    
    实时推送任务进度更新，包括进度百分比和当前处理的文件名。
    
    Args:
        task_id: 任务 ID
        
    Returns:
        StreamingResponse: Server-Sent Events 流式响应
    """
    import json as json_module
    
    # 检查任务是否存在
    task = db.get_task(task_id)
    if not task:
        async def error_generator():
            newline = "\n"
            message = f'任务 {task_id} 不存在'
            yield f"data: {json_module.dumps({'status': 'error', 'message': message}, ensure_ascii=False)}{newline}{newline}"
        return StreamingResponse(
            error_generator(), 
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用代理缓冲，确保 SSE 流实时传输
            }
        )
    
    async def progress_generator():
        newline = "\n"
        
        # 注册进度队列
        progress_queue = await task_progress_manager.register_queue(task_id)
        print(f"[SSE] 任务 {task_id}: 客户端已连接，注册进度队列")
        
        try:
            # 发送初始状态（从数据库获取）
            task_status = task.get("status", "PENDING")
            initial_state = {
                "status": "connected",
                "task_status": task_status,  # 任务的实际状态
                "progress": task.get("progress", 0.0),
                "percentage": round(task.get("progress", 0.0) * 100, 2),
                "current_file": task.get("current_file"),
                "total_files": task.get("total_files", 0),
                "message": "已连接到进度流",
                "timestamp": datetime.now().isoformat()
            }
            initial_data = f"data: {json_module.dumps(initial_state, ensure_ascii=False)}{newline}{newline}"
            print(f"[SSE] 任务 {task_id}: 发送初始状态 - {initial_data[:200]}")
            yield initial_data
            
            # 获取最后状态（如果有）
            last_state = await task_progress_manager.get_last_state(task_id)
            if last_state:
                last_state_data = f"data: {json_module.dumps(last_state, ensure_ascii=False)}{newline}{newline}"
                print(f"[SSE] 任务 {task_id}: 发送最后状态 - {last_state_data[:200]}")
                yield last_state_data
            
            # 持续监听进度更新
            while True:
                try:
                    # 等待进度更新，设置超时以定期发送心跳
                    progress_data = await asyncio.wait_for(progress_queue.get(), timeout=30.0)
                    
                    # 构建响应数据
                    # 如果 progress_data 中没有 status 或 status 为 None，使用 "progress"
                    progress_status = progress_data.get("status")
                    if not progress_status:
                        progress_status = "progress"
                    
                    response_data = {
                        **progress_data,
                        "status": progress_status
                    }
                    
                    # 调试日志
                    print(f"[SSE] 任务 {task_id}: 发送进度更新 - 进度: {response_data.get('progress', 0):.2%}, 状态: {progress_status}, 消息: {response_data.get('message', '')[:50]}")
                    
                    yield f"data: {json_module.dumps(response_data, ensure_ascii=False)}{newline}{newline}"
                    
                    # 如果任务完成或失败，结束流（支持大小写）
                    progress_status_upper = progress_status.upper() if progress_status else ""
                    if progress_status_upper in ["COMPLETED", "FAILED", "CANCELLED"]:
                        break
                        
                except asyncio.TimeoutError:
                    # 发送心跳，保持连接
                    heartbeat = {
                        "status": "heartbeat",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json_module.dumps(heartbeat, ensure_ascii=False)}{newline}{newline}"
                    
                    # 检查任务状态，如果已完成或失败，结束流
                    current_task = db.get_task(task_id)
                    if current_task:
                        task_status = current_task.get("status", "")
                        task_status_upper = task_status.upper() if task_status else ""
                        if task_status_upper in ["COMPLETED", "FAILED", "CANCELLED"]:
                            # 根据状态设置消息和进度
                            if task_status_upper == "COMPLETED":
                                message = "任务已完成"
                                default_progress = 1.0
                            elif task_status_upper == "FAILED":
                                message = "任务失败"
                                default_progress = 0.0
                            else:  # CANCELLED
                                message = "任务已取消"
                                default_progress = current_task.get("progress", 0.0)
                            
                            final_state = {
                                "status": task_status.lower(),
                                "task_status": task_status,
                                "progress": current_task.get("progress", default_progress),
                                "percentage": round(current_task.get("progress", default_progress) * 100, 2),
                                "current_file": current_task.get("current_file"),
                                "message": message,
                                "timestamp": datetime.now().isoformat()
                            }
                            yield f"data: {json_module.dumps(final_state, ensure_ascii=False)}{newline}{newline}"
                            break
                except Exception as e:
                    error_data = {
                        "status": "error",
                        "message": f"获取进度更新时发生错误: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json_module.dumps(error_data, ensure_ascii=False)}{newline}{newline}"
                    break
        finally:
            # 取消注册队列
            await task_progress_manager.unregister_queue(task_id, progress_queue)
    
    return StreamingResponse(
        progress_generator(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用代理缓冲，确保 SSE 流实时传输
        }
    )


@router.get("/{task_id}")
async def get_task(task_id: str):
    """
    获取任务详情
    
    Args:
        task_id: 任务 ID
        
    Returns:
        任务信息
    """
    try:
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return JSONResponse(content=task)
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取任务失败"
        raise HTTPException(status_code=500, detail=f"获取任务失败: {error_msg}")


@router.get("")
async def list_tasks(
    textbook_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0
):
    """
    获取任务列表
    
    Args:
        textbook_id: 教材 ID（可选）
        status: 任务状态（可选）
        limit: 限制返回数量（可选）
        offset: 偏移量（用于分页）
        
    Returns:
        任务列表
    """
    try:
        tasks = db.get_all_tasks(
            textbook_id=textbook_id,
            status=status,
            limit=limit,
            offset=offset
        )
        return JSONResponse(content=tasks)
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取任务列表失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取任务列表失败"
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {error_msg}")


@router.post("")
async def create_task(task: TaskCreate):
    """
    创建任务
    
    Args:
        task: 任务创建请求
        
    Returns:
        创建的任务信息
    """
    try:
        task_id = str(uuid.uuid4())
        success = db.create_task(
            task_id=task_id,
            textbook_id=task.textbook_id,
            total_files=task.total_files
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="创建任务失败，可能任务 ID 已存在")
        
        created_task = db.get_task(task_id)
        return JSONResponse(content=created_task)
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "创建任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "创建任务失败"
        raise HTTPException(status_code=500, detail=f"创建任务失败: {error_msg}")


@router.put("/{task_id}")
async def update_task(task_id: str, task_update: TaskUpdate):
    """
    更新任务
    
    Args:
        task_id: 任务 ID
        task_update: 任务更新请求
        
    Returns:
        更新后的任务信息
    """
    try:
        # 检查任务是否存在
        existing = db.get_task(task_id)
        if not existing:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 更新数据库
        success = db.update_task(
            task_id=task_id,
            status=task_update.status,
            progress=task_update.progress,
            current_file=task_update.current_file,
            total_files=task_update.total_files,
            error_message=task_update.error_message
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="更新任务失败")
        
        # 如果更新了进度，推送到进度管理器
        if task_update.progress is not None or task_update.current_file is not None:
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=task_update.progress if task_update.progress is not None else existing.get("progress", 0.0),
                current_file=task_update.current_file if task_update.current_file is not None else existing.get("current_file"),
                status=task_update.status if task_update.status is not None else existing.get("status")
            )
        
        updated_task = db.get_task(task_id)
        return JSONResponse(content=updated_task)
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "更新任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "更新任务失败"
        raise HTTPException(status_code=500, detail=f"更新任务失败: {error_msg}")
    finally:
        # 取消注册任务
        await task_manager.unregister_task(task_id)


@router.post("/{task_id}/pause")
async def pause_task(task_id: str):
    """
    暂停任务
    
    Args:
        task_id: 任务 ID
        
    Returns:
        暂停结果
    """
    try:
        # 检查任务是否存在
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        current_status = task.get("status")
        if current_status not in ["PENDING", "PROCESSING"]:
            raise HTTPException(
                status_code=400, 
                detail=f"任务状态为 {current_status}，无法暂停。只能暂停 PENDING 或 PROCESSING 状态的任务。"
            )
        
        # 更新数据库状态
        db.update_task_status(task_id, "PAUSED")
        
        # 暂停任务执行
        success = await task_manager.pause_task(task_id)
        
        if success:
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=task.get("progress", 0.0),
                message="任务已暂停",
                status="PAUSED"
            )
        
        return JSONResponse(content={
            "message": "任务已暂停",
            "task_id": task_id,
            "status": "PAUSED"
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "暂停任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "暂停任务失败"
        raise HTTPException(status_code=500, detail=f"暂停任务失败: {error_msg}")


@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    """
    恢复任务
    
    Args:
        task_id: 任务 ID
        
    Returns:
        恢复结果
    """
    try:
        # 检查任务是否存在
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        current_status = task.get("status")
        if current_status != "PAUSED":
            raise HTTPException(
                status_code=400,
                detail=f"任务状态为 {current_status}，无法恢复。只能恢复 PAUSED 状态的任务。"
            )
        
        # 检查任务是否正在运行
        is_running = task_id in await task_manager.get_running_tasks()
        
        if not is_running:
            # 如果任务不在运行，重新启动任务
            asyncio.create_task(process_full_textbook_task(task_id))
        
        # 恢复任务执行
        success = await task_manager.resume_task(task_id)
        
        if success:
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=task.get("progress", 0.0),
                message="任务已恢复",
                status="PROCESSING"
            )
        
        # 更新数据库状态
        db.update_task_status(task_id, "PROCESSING")
        
        return JSONResponse(content={
            "message": "任务已恢复",
            "task_id": task_id,
            "status": "PROCESSING"
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "恢复任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "恢复任务失败"
        raise HTTPException(status_code=500, detail=f"恢复任务失败: {error_msg}")


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    取消任务
    
    Args:
        task_id: 任务 ID
        
    Returns:
        取消结果
    """
    try:
        # 检查任务是否存在
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        current_status = task.get("status")
        if current_status in ["COMPLETED", "FAILED", "CANCELLED"]:
            raise HTTPException(
                status_code=400,
                detail=f"任务状态为 {current_status}，无法取消。"
            )
        
        # 取消任务执行
        success = await task_manager.cancel_task(task_id)
        
        # 更新数据库状态
        db.update_task_status(task_id, "CANCELLED", "任务已取消")
        
        if success:
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=task.get("progress", 0.0),
                message="任务已取消",
                status="CANCELLED"
            )
        
        return JSONResponse(content={
            "message": "任务已取消",
            "task_id": task_id,
            "status": "CANCELLED"
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "取消任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "取消任务失败"
        raise HTTPException(status_code=500, detail=f"取消任务失败: {error_msg}")


@router.post("/generate-book")
async def generate_book(
    request: TextbookGenerationRequest
):
    """
    生成全书出题规划（不创建任务）
    
    当用户选择教材点击规划时：
    1. 处理所有文件并收集切片信息
    2. 调用 AI 进行出题规划
    3. 返回规划结果，用户可以编辑后提交执行
    
    Args:
        request: 教材生成请求，包含 textbook_id、mode、task_settings
        
    Returns:
        规划结果（不包含任务信息）
    """
    try:
        logger.info(f"[生成规划] 开始处理请求 - textbook_id: {request.textbook_id}, mode: {request.mode}")
        
        # 1. 检查教材是否存在
        logger.info(f"[生成规划] 步骤1: 检查教材是否存在 - textbook_id: {request.textbook_id}")
        textbook = db.get_textbook(request.textbook_id)
        if not textbook:
            logger.error(f"[生成规划] 教材不存在 - textbook_id: {request.textbook_id}")
            raise HTTPException(status_code=404, detail="教材不存在")
        
        textbook_name = textbook.get("name", "未命名教材")
        logger.info(f"[生成规划] 教材信息获取成功 - 名称: {textbook_name}")
        
        # 2. 获取教材下的文件数量
        logger.info(f"[生成规划] 步骤2: 获取教材文件列表 - textbook_id: {request.textbook_id}")
        files = db.get_textbook_files(request.textbook_id)
        logger.info(f"[生成规划] 获取到文件列表 - 总数: {len(files)}")
        
        md_files = [f for f in files if f.get("file_format", "").lower() in [".md", ".markdown"]]
        total_files = len(md_files)
        logger.info(f"[生成规划] Markdown 文件数量 - 总数: {total_files}")
        
        if total_files == 0:
            logger.error(f"[生成规划] 教材中没有 Markdown 文件 - textbook_id: {request.textbook_id}")
            raise HTTPException(status_code=400, detail="教材中没有 Markdown 文件")
        
        # 3. 处理文件并收集切片信息
        logger.info(f"[生成规划] 步骤3: 处理文件并收集切片信息")
        try:
            from app.services.markdown_service import MarkdownProcessor
            from pathlib import Path
            logger.info(f"[生成规划] 导入模块成功")
        except ImportError as e:
            error_msg = f"导入模块失败: {str(e)}"
            logger.error(f"[生成规划] {error_msg}")
            logger.error(f"[生成规划] 导入错误堆栈:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        try:
            processor = MarkdownProcessor(
                chunk_size=1200,
                chunk_overlap=200,
                max_tokens_before_split=1500
            )
            logger.info(f"[生成规划] MarkdownProcessor 初始化完成")
        except Exception as e:
            error_msg = f"MarkdownProcessor 初始化失败: {str(e)}"
            logger.error(f"[生成规划] {error_msg}")
            logger.error(f"[生成规划] 初始化错误堆栈:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        all_chunks_info = []
        processed_files = 0
        failed_files = 0
        
        for idx, file_info in enumerate(md_files, 1):
            file_id = file_info.get("file_id")
            filename = file_info.get("filename", file_id)
            file_path = file_info.get("file_path")
            
            logger.info(f"[生成规划] 处理文件 {idx}/{total_files} - filename: {filename}, file_id: {file_id}")
            
            if not file_path:
                logger.warning(f"[生成规划] 文件缺少路径 - filename: {filename}, file_id: {file_id}")
                failed_files += 1
                continue
            
            if not Path(file_path).exists():
                logger.warning(f"[生成规划] 文件不存在 - filename: {filename}, file_path: {file_path}")
                failed_files += 1
                continue
            
            try:
                logger.info(f"[生成规划] 开始处理文件切片 - filename: {filename}")
                chunks = processor.process(file_path)
                logger.info(f"[生成规划] 文件切片完成 - filename: {filename}, 切片数: {len(chunks) if chunks else 0}")
                
                if not chunks:
                    logger.warning(f"[生成规划] 文件切片为空 - filename: {filename}")
                    failed_files += 1
                    continue
                
                # 存储 chunks 到数据库
                logger.info(f"[生成规划] 存储切片到数据库 - filename: {filename}, 切片数: {len(chunks)}")
                db.store_chunks(file_id, chunks)
                
                # 获取存储后的 chunk_id
                chunk_index_to_id = {}
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT chunk_id, chunk_index
                        FROM chunks
                        WHERE file_id = ?
                        ORDER BY chunk_index
                    """, (file_id,))
                    for row in cursor.fetchall():
                        chunk_index_to_id[row["chunk_index"]] = row["chunk_id"]
                
                logger.info(f"[生成规划] 获取切片 ID 映射完成 - filename: {filename}, 映射数: {len(chunk_index_to_id)}")
                
                # 收集切片信息
                file_chunks_count = 0
                for chunk_index, chunk in enumerate(chunks):
                    chunk_id = chunk_index_to_id.get(chunk_index)
                    if chunk_id:
                        metadata = chunk.get("metadata", {})
                        chapter_name = processor.get_chapter_name(metadata)
                        content = chunk.get("content", "")
                        content_summary = content[:500] if len(content) > 500 else content
                        
                        all_chunks_info.append({
                            "chunk_id": chunk_id,
                            "file_id": file_id,
                            "chapter_name": chapter_name or "未命名章节",
                            "content_summary": content_summary
                        })
                        file_chunks_count += 1
                
                logger.info(f"[生成规划] 文件处理完成 - filename: {filename}, 收集切片数: {file_chunks_count}")
                processed_files += 1
                
            except Exception as e:
                failed_files += 1
                error_msg = str(e)
                error_trace = traceback.format_exc()
                logger.error(f"[生成规划] 处理文件失败 - filename: {filename}, 错误: {error_msg}")
                logger.debug(f"[生成规划] 错误堆栈:\n{error_trace}")
                continue
        
        logger.info(f"[生成规划] 文件处理统计 - 成功: {processed_files}, 失败: {failed_files}, 总切片数: {len(all_chunks_info)}")
        
        if not all_chunks_info:
            error_msg = f"没有收集到任何切片信息（处理文件: {processed_files}/{total_files}, 失败: {failed_files}）"
            logger.error(f"[生成规划] {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)
        
        # 4. 调用 AI 进行规划
        mode = request.mode or "课后习题"
        logger.info(f"[生成规划] 步骤4: 调用 AI 进行规划 - 切片数: {len(all_chunks_info)}, 模式: {mode}")
        try:
            from app.services.ai_service import OpenRouterClient
            logger.info(f"[生成规划] 导入 OpenRouterClient 成功")
        except ImportError as e:
            error_msg = f"导入 OpenRouterClient 失败: {str(e)}"
            logger.error(f"[生成规划] {error_msg}")
            logger.error(f"[生成规划] 导入错误堆栈:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=error_msg)
        
        try:
            client = OpenRouterClient()
            logger.info(f"[生成规划] OpenRouterClient 初始化完成")
            
            generation_plan = await client.plan_generation_tasks(
                textbook_name=textbook_name,
                chunks_info=all_chunks_info,
                mode=mode
            )
            
            logger.info(f"[生成规划] AI 规划完成 - 总题目数: {generation_plan.total_questions}, 题型分布: {generation_plan.type_distribution}")
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            logger.error(f"[生成规划] AI 规划失败 - 错误: {error_msg}")
            logger.debug(f"[生成规划] 错误堆栈:\n{error_trace}")
            raise HTTPException(
                status_code=500,
                detail=f"AI 规划失败: {error_msg}"
            )
        
        # 5. 转换规划结果为字典
        logger.info(f"[生成规划] 步骤5: 转换规划结果")
        plan_dict = None
        try:
            # 检查 generation_plan 是否有 model_dump 方法（Pydantic v2）或 dict 方法（Pydantic v1）
            if hasattr(generation_plan, 'model_dump'):
                plan_dict = generation_plan.model_dump()
                logger.info(f"[生成规划] 使用 model_dump() 方法转换规划结果")
            elif hasattr(generation_plan, 'dict'):
                plan_dict = generation_plan.dict()
                logger.info(f"[生成规划] 使用 dict() 方法转换规划结果")
            else:
                # 如果不是 Pydantic 模型，尝试转换为字典
                error_msg = f"generation_plan 不是有效的 Pydantic 模型，类型: {type(generation_plan)}"
                logger.error(f"[生成规划] {error_msg}")
                raise ValueError(error_msg)
            
            logger.info(f"[生成规划] 规划结果转换为字典成功 - 键数量: {len(plan_dict) if plan_dict else 0}")
            
            # 验证 plan_dict 是否为字典类型
            if not isinstance(plan_dict, dict):
                error_msg = f"plan_dict 不是字典类型，实际类型: {type(plan_dict)}"
                logger.error(f"[生成规划] {error_msg}")
                raise ValueError(error_msg)
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            logger.error(f"[生成规划] 转换规划结果失败 - 错误: {error_msg}")
            logger.error(f"[生成规划] 错误堆栈:\n{error_trace}")
            raise HTTPException(
                status_code=500,
                detail=f"转换规划结果失败: {error_msg}"
            )
        
        # 6. 返回规划结果
        logger.info(f"[生成规划] 步骤6: 返回规划结果 - 总题目数: {generation_plan.total_questions}")
        return JSONResponse(content={
            "message": "规划完成",
            "textbook_id": request.textbook_id,
            "textbook_name": textbook_name,
            "mode": mode,
            "total_files": total_files,
            "generation_plan": plan_dict
        })
        
    except HTTPException:
        # HTTPException 直接抛出，不记录日志（已经在抛出前记录）
        raise
    except Exception as e:
        # 捕获所有未预期的异常
        error_msg = str(e)
        error_trace = traceback.format_exc()
        logger.error(f"[生成规划] 未预期的错误 - 错误: {error_msg}")
        logger.error(f"[生成规划] 错误堆栈:\n{error_trace}")
        
        # 返回详细的错误信息
        try:
            error_detail = repr(e) if hasattr(e, '__repr__') else error_msg
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_detail = error_msg
        
        raise HTTPException(
            status_code=500,
            detail=f"规划任务失败: {error_detail}"
        )


class TaskExecuteRequest(BaseModel):
    """任务执行请求模型"""
    textbook_id: str = Field(..., description="教材 ID")
    mode: str = Field(default="课后习题", description="出题模式")
    generation_plan: Dict[str, Any] = Field(..., description="生成计划")
    task_settings: Optional[Dict[str, Any]] = Field(default=None, description="任务设置")


@router.post("/execute")
async def execute_task(
    request: TaskExecuteRequest,
    background_tasks: BackgroundTasks
):
    """
    创建任务并执行规划
    
    用户在编辑规划后，提交执行任务：
    1. 检查教材是否存在
    2. 创建任务记录
    3. 保存规划结果到任务
    4. 启动后台任务执行
    
    Args:
        request: 任务执行请求，包含 textbook_id、mode、generation_plan、task_settings
        background_tasks: FastAPI 后台任务管理器
        
    Returns:
        任务信息
    """
    task_id = None
    try:
        logger.info(f"[执行任务] 开始处理请求 - textbook_id: {request.textbook_id}, mode: {request.mode}")
        
        # 1. 检查教材是否存在
        textbook = db.get_textbook(request.textbook_id)
        if not textbook:
            raise HTTPException(status_code=404, detail="教材不存在")
        
        # 2. 获取教材下的文件数量
        files = db.get_textbook_files(request.textbook_id)
        md_files = [f for f in files if f.get("file_format", "").lower() in [".md", ".markdown"]]
        total_files = len(md_files)
        
        if total_files == 0:
            raise HTTPException(status_code=400, detail="教材中没有 Markdown 文件")
        
        # 3. 创建任务
        task_id = str(uuid.uuid4())
        mode = request.mode or "课后习题"
        logger.info(f"[执行任务] 创建任务 - task_id: {task_id}, mode: {mode}, total_files: {total_files}")
        
        success = db.create_task(
            task_id=task_id,
            textbook_id=request.textbook_id,
            total_files=total_files,
            mode=mode,
            task_settings=request.task_settings
        )
        
        if not success:
            logger.error(f"[执行任务] 创建任务失败 - task_id: {task_id}")
            raise HTTPException(status_code=400, detail="创建任务失败，可能任务 ID 已存在")
        
        # 4. 保存规划结果到任务
        logger.info(f"[执行任务] 保存规划结果到任务 - task_id: {task_id}")
        db.update_task_generation_plan(task_id, request.generation_plan)
        
        # 5. 更新任务状态为 PENDING
        db.update_task_status(task_id, "PENDING")
        
        # 6. 启动后台任务
        logger.info(f"[执行任务] 启动后台任务 - task_id: {task_id}")
        background_tasks.add_task(process_full_textbook_task, task_id)
        
        # 7. 返回任务信息
        updated_task = db.get_task(task_id)
        logger.info(f"[执行任务] 任务创建并启动成功 - task_id: {task_id}")
        return JSONResponse(content={
            "message": "任务已创建并启动执行",
            "task_id": task_id,
            "task": updated_task
        })
        
    except HTTPException:
        raise
    except Exception as e:
        # 如果任务已创建，更新状态为失败
        if task_id:
            try:
                db.update_task_status(task_id, "FAILED", f"执行任务失败: {str(e)}")
            except Exception:
                pass
        
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "执行任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "执行任务失败"
        raise HTTPException(status_code=500, detail=f"执行任务失败: {error_msg}")


@router.post("/create-and-execute")
async def create_and_execute_task(
    request: TextbookGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    创建任务并异步执行（规划在后台任务中进行）
    
    当用户点击"开始执行任务"时：
    1. 检查教材是否存在
    2. 获取文件数量
    3. 创建任务记录（状态为 PLANNING）
    4. 启动后台任务执行（后台任务会先规划，后生成题目）
    5. 立即返回任务信息
    
    Args:
        request: 教材生成请求，包含 textbook_id、mode、task_settings
        background_tasks: FastAPI 后台任务管理器
        
    Returns:
        任务信息
    """
    task_id = None
    try:
        logger.info(f"[创建并执行] 开始处理请求 - textbook_id: {request.textbook_id}, mode: {request.mode}")
        
        # 1. 检查教材是否存在
        logger.info(f"[创建并执行] 步骤1: 检查教材是否存在 - textbook_id: {request.textbook_id}")
        textbook = db.get_textbook(request.textbook_id)
        if not textbook:
            logger.error(f"[创建并执行] 教材不存在 - textbook_id: {request.textbook_id}")
            raise HTTPException(status_code=404, detail="教材不存在")
        
        textbook_name = textbook.get("name", "未命名教材")
        logger.info(f"[创建并执行] 教材信息获取成功 - 名称: {textbook_name}")
        
        # 2. 获取教材下的文件数量
        logger.info(f"[创建并执行] 步骤2: 获取教材文件列表 - textbook_id: {request.textbook_id}")
        files = db.get_textbook_files(request.textbook_id)
        logger.info(f"[创建并执行] 获取到文件列表 - 总数: {len(files)}")
        
        md_files = [f for f in files if f.get("file_format", "").lower() in [".md", ".markdown"]]
        total_files = len(md_files)
        logger.info(f"[创建并执行] Markdown 文件数量 - 总数: {total_files}")
        
        if total_files == 0:
            logger.error(f"[创建并执行] 教材中没有 Markdown 文件 - textbook_id: {request.textbook_id}")
            raise HTTPException(status_code=400, detail="教材中没有 Markdown 文件")
        
        # 3. 创建任务（状态为 PLANNING，规划将在后台任务中进行）
        task_id = str(uuid.uuid4())
        mode = request.mode or "课后习题"
        logger.info(f"[创建并执行] 创建任务 - task_id: {task_id}, mode: {mode}, total_files: {total_files}")
        
        success = db.create_task(
            task_id=task_id,
            textbook_id=request.textbook_id,
            total_files=total_files,
            mode=mode,
            task_settings=request.task_settings
        )
        
        if not success:
            logger.error(f"[创建并执行] 创建任务失败 - task_id: {task_id}")
            raise HTTPException(status_code=400, detail="创建任务失败，可能任务 ID 已存在")
        
        # 4. 更新任务状态为 PLANNING
        db.update_task_status(task_id, "PLANNING")
        
        # 5. 启动后台任务（后台任务会先进行规划，然后生成题目）
        logger.info(f"[创建并执行] 启动后台任务 - task_id: {task_id}")
        background_tasks.add_task(process_full_textbook_task, task_id)
        
        # 6. 推送初始进度
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.0,
            message="任务已创建，开始规划...",
            status="PLANNING"
        )
        
        # 7. 立即返回任务信息
        created_task = db.get_task(task_id)
        logger.info(f"[创建并执行] 任务创建并启动成功 - task_id: {task_id}")
        return JSONResponse(content={
            "message": "任务已创建并启动执行",
            "task_id": task_id,
            "task": created_task
        })
        
    except HTTPException:
        raise
    except Exception as e:
        # 如果任务已创建，更新状态为失败
        if task_id:
            try:
                db.update_task_status(task_id, "FAILED", f"创建任务失败: {str(e)}")
                await task_progress_manager.push_progress(
                    task_id=task_id,
                    progress=0.0,
                    message=f"任务失败: {str(e)}",
                    status="FAILED"
                )
            except Exception:
                pass
        
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "创建任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "创建任务失败"
        raise HTTPException(status_code=500, detail=f"创建任务失败: {error_msg}")


@router.post("/generate-and-execute")
async def generate_and_execute_task(
    request: TextbookGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    规划并执行任务（合并规划和执行流程）- 已废弃，保留用于兼容
    
    当用户点击"开始执行任务"时：
    1. 处理所有文件并收集切片信息
    2. 调用 AI 进行出题规划
    3. 创建任务记录并保存规划
    4. 在任务进度中推送规划信息
    5. 启动后台任务执行
    
    Args:
        request: 教材生成请求，包含 textbook_id、mode、task_settings
        background_tasks: FastAPI 后台任务管理器
        
    Returns:
        任务信息
    """
    task_id = None
    try:
        logger.info(f"[规划并执行] 开始处理请求 - textbook_id: {request.textbook_id}, mode: {request.mode}")
        
        # 1. 检查教材是否存在
        logger.info(f"[规划并执行] 步骤1: 检查教材是否存在 - textbook_id: {request.textbook_id}")
        textbook = db.get_textbook(request.textbook_id)
        if not textbook:
            logger.error(f"[规划并执行] 教材不存在 - textbook_id: {request.textbook_id}")
            raise HTTPException(status_code=404, detail="教材不存在")
        
        textbook_name = textbook.get("name", "未命名教材")
        logger.info(f"[规划并执行] 教材信息获取成功 - 名称: {textbook_name}")
        
        # 2. 获取教材下的文件数量
        logger.info(f"[规划并执行] 步骤2: 获取教材文件列表 - textbook_id: {request.textbook_id}")
        files = db.get_textbook_files(request.textbook_id)
        logger.info(f"[规划并执行] 获取到文件列表 - 总数: {len(files)}")
        
        md_files = [f for f in files if f.get("file_format", "").lower() in [".md", ".markdown"]]
        total_files = len(md_files)
        logger.info(f"[规划并执行] Markdown 文件数量 - 总数: {total_files}")
        
        if total_files == 0:
            logger.error(f"[规划并执行] 教材中没有 Markdown 文件 - textbook_id: {request.textbook_id}")
            raise HTTPException(status_code=400, detail="教材中没有 Markdown 文件")
        
        # 3. 创建任务（在规划之前创建，以便可以推送进度）
        task_id = str(uuid.uuid4())
        mode = request.mode or "课后习题"
        logger.info(f"[规划并执行] 创建任务 - task_id: {task_id}, mode: {mode}, total_files: {total_files}")
        
        success = db.create_task(
            task_id=task_id,
            textbook_id=request.textbook_id,
            total_files=total_files,
            mode=mode,
            task_settings=request.task_settings
        )
        
        if not success:
            logger.error(f"[规划并执行] 创建任务失败 - task_id: {task_id}")
            raise HTTPException(status_code=400, detail="创建任务失败，可能任务 ID 已存在")
        
        # 更新任务状态为 PLANNING
        db.update_task_status(task_id, "PLANNING")
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.0,
            message="开始规划任务...",
            status="PLANNING"
        )
        
        # 4. 处理文件并收集切片信息
        logger.info(f"[规划并执行] 步骤4: 处理文件并收集切片信息")
        try:
            from app.services.markdown_service import MarkdownProcessor
            from pathlib import Path
            logger.info(f"[规划并执行] 导入模块成功")
        except ImportError as e:
            error_msg = f"导入模块失败: {str(e)}"
            logger.error(f"[规划并执行] {error_msg}")
            logger.error(f"[规划并执行] 导入错误堆栈:\n{traceback.format_exc()}")
            db.update_task_status(task_id, "FAILED", error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
        
        try:
            processor = MarkdownProcessor(
                chunk_size=1200,
                chunk_overlap=200,
                max_tokens_before_split=1500
            )
            logger.info(f"[规划并执行] MarkdownProcessor 初始化完成")
        except Exception as e:
            error_msg = f"MarkdownProcessor 初始化失败: {str(e)}"
            logger.error(f"[规划并执行] {error_msg}")
            logger.error(f"[规划并执行] 初始化错误堆栈:\n{traceback.format_exc()}")
            db.update_task_status(task_id, "FAILED", error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
        
        all_chunks_info = []
        processed_files = 0
        failed_files = 0
        
        for idx, file_info in enumerate(md_files, 1):
            file_id = file_info.get("file_id")
            filename = file_info.get("filename", file_id)
            file_path = file_info.get("file_path")
            
            logger.info(f"[规划并执行] 处理文件 {idx}/{total_files} - filename: {filename}, file_id: {file_id}")
            
            # 推送文件处理进度
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.02 * (idx / total_files),  # 规划阶段占 2% 进度
                current_file=filename,
                message=f"正在处理文件: {filename} ({idx}/{total_files})",
                status="PLANNING"
            )
            
            if not file_path:
                logger.warning(f"[规划并执行] 文件缺少路径 - filename: {filename}, file_id: {file_id}")
                failed_files += 1
                continue
            
            if not Path(file_path).exists():
                logger.warning(f"[规划并执行] 文件不存在 - filename: {filename}, file_path: {file_path}")
                failed_files += 1
                continue
            
            try:
                logger.info(f"[规划并执行] 开始处理文件切片 - filename: {filename}")
                chunks = processor.process(file_path)
                logger.info(f"[规划并执行] 文件切片完成 - filename: {filename}, 切片数: {len(chunks) if chunks else 0}")
                
                if not chunks:
                    logger.warning(f"[规划并执行] 文件切片为空 - filename: {filename}")
                    failed_files += 1
                    continue
                
                # 存储 chunks 到数据库
                logger.info(f"[规划并执行] 存储切片到数据库 - filename: {filename}, 切片数: {len(chunks)}")
                db.store_chunks(file_id, chunks)
                
                # 获取存储后的 chunk_id
                chunk_index_to_id = {}
                with db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT chunk_id, chunk_index
                        FROM chunks
                        WHERE file_id = ?
                        ORDER BY chunk_index
                    """, (file_id,))
                    for row in cursor.fetchall():
                        chunk_index_to_id[row["chunk_index"]] = row["chunk_id"]
                
                logger.info(f"[规划并执行] 获取切片 ID 映射完成 - filename: {filename}, 映射数: {len(chunk_index_to_id)}")
                
                # 收集切片信息
                file_chunks_count = 0
                for chunk_index, chunk in enumerate(chunks):
                    chunk_id = chunk_index_to_id.get(chunk_index)
                    if chunk_id:
                        metadata = chunk.get("metadata", {})
                        chapter_name = processor.get_chapter_name(metadata)
                        content = chunk.get("content", "")
                        content_summary = content[:500] if len(content) > 500 else content
                        
                        all_chunks_info.append({
                            "chunk_id": chunk_id,
                            "file_id": file_id,
                            "chapter_name": chapter_name or "未命名章节",
                            "content_summary": content_summary
                        })
                        file_chunks_count += 1
                
                logger.info(f"[规划并执行] 文件处理完成 - filename: {filename}, 收集切片数: {file_chunks_count}")
                processed_files += 1
                
            except Exception as e:
                failed_files += 1
                error_msg = str(e)
                error_trace = traceback.format_exc()
                logger.error(f"[规划并执行] 处理文件失败 - filename: {filename}, 错误: {error_msg}")
                logger.debug(f"[规划并执行] 错误堆栈:\n{error_trace}")
                continue
        
        logger.info(f"[规划并执行] 文件处理统计 - 成功: {processed_files}, 失败: {failed_files}, 总切片数: {len(all_chunks_info)}")
        
        if not all_chunks_info:
            error_msg = f"没有收集到任何切片信息（处理文件: {processed_files}/{total_files}, 失败: {failed_files}）"
            logger.error(f"[规划并执行] {error_msg}")
            db.update_task_status(task_id, "FAILED", error_msg)
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message=f"任务失败: {error_msg}",
                status="FAILED"
            )
            raise HTTPException(status_code=400, detail=error_msg)
        
        # 5. 调用 AI 进行规划
        mode = request.mode or "课后习题"
        logger.info(f"[规划并执行] 步骤5: 调用 AI 进行规划 - 切片数: {len(all_chunks_info)}, 模式: {mode}")
        
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.05,
            message=f"正在规划生成任务（共 {len(all_chunks_info)} 个切片）...",
            status="PLANNING"
        )
        
        try:
            from app.services.ai_service import OpenRouterClient
            logger.info(f"[规划并执行] 导入 OpenRouterClient 成功")
        except ImportError as e:
            error_msg = f"导入 OpenRouterClient 失败: {str(e)}"
            logger.error(f"[规划并执行] {error_msg}")
            logger.error(f"[规划并执行] 导入错误堆栈:\n{traceback.format_exc()}")
            db.update_task_status(task_id, "FAILED", error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
        
        try:
            client = OpenRouterClient()
            logger.info(f"[规划并执行] OpenRouterClient 初始化完成")
            
            generation_plan = await client.plan_generation_tasks(
                textbook_name=textbook_name,
                chunks_info=all_chunks_info,
                mode=mode
            )
            
            logger.info(f"[规划并执行] AI 规划完成 - 总题目数: {generation_plan.total_questions}, 题型分布: {generation_plan.type_distribution}")
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            logger.error(f"[规划并执行] AI 规划失败 - 错误: {error_msg}")
            logger.debug(f"[规划并执行] 错误堆栈:\n{error_trace}")
            db.update_task_status(task_id, "FAILED", f"AI 规划失败: {error_msg}")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message=f"任务失败: AI 规划失败: {error_msg}",
                status="FAILED"
            )
            raise HTTPException(
                status_code=500,
                detail=f"AI 规划失败: {error_msg}"
            )
        
        # 6. 转换规划结果为字典
        logger.info(f"[规划并执行] 步骤6: 转换规划结果")
        plan_dict = None
        try:
            # 检查 generation_plan 是否有 model_dump 方法（Pydantic v2）或 dict 方法（Pydantic v1）
            if hasattr(generation_plan, 'model_dump'):
                plan_dict = generation_plan.model_dump()
                logger.info(f"[规划并执行] 使用 model_dump() 方法转换规划结果")
            elif hasattr(generation_plan, 'dict'):
                plan_dict = generation_plan.dict()
                logger.info(f"[规划并执行] 使用 dict() 方法转换规划结果")
            else:
                error_msg = f"generation_plan 不是有效的 Pydantic 模型，类型: {type(generation_plan)}"
                logger.error(f"[规划并执行] {error_msg}")
                raise ValueError(error_msg)
            
            logger.info(f"[规划并执行] 规划结果转换为字典成功 - 键数量: {len(plan_dict) if plan_dict else 0}")
            
            # 验证 plan_dict 是否为字典类型
            if not isinstance(plan_dict, dict):
                error_msg = f"plan_dict 不是字典类型，实际类型: {type(plan_dict)}"
                logger.error(f"[规划并执行] {error_msg}")
                raise ValueError(error_msg)
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            logger.error(f"[规划并执行] 转换规划结果失败 - 错误: {error_msg}")
            logger.error(f"[规划并执行] 错误堆栈:\n{error_trace}")
            db.update_task_status(task_id, "FAILED", f"转换规划结果失败: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"转换规划结果失败: {error_msg}"
            )
        
        # 7. 保存规划结果到任务
        logger.info(f"[规划并执行] 步骤7: 保存规划结果到任务 - task_id: {task_id}")
        db.update_task_generation_plan(task_id, plan_dict)
        
        # 8. 构建规划信息消息，推送到任务日志
        type_distribution_str = ", ".join([f"{k}: {v}道" for k, v in generation_plan.type_distribution.items()])
        plan_message = (
            f"✅ 规划完成！\n"
            f"📊 规划详情：\n"
            f"  • 总题目数: {generation_plan.total_questions} 道\n"
            f"  • 题型分布: {type_distribution_str}\n"
            f"  • 出题模式: {mode}\n"
            f"  • 切片数量: {len(all_chunks_info)} 个\n"
            f"  • 处理文件: {processed_files}/{total_files} 个\n\n"
            f"🚀 开始执行任务..."
        )
        
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.1,
            message=plan_message,
            status="PLANNING"
        )
        
        logger.info(f"[规划并执行] 规划信息已推送到任务日志 - task_id: {task_id}")
        
        # 9. 更新任务状态为 PENDING，准备执行
        db.update_task_status(task_id, "PENDING")
        
        # 10. 启动后台任务
        logger.info(f"[规划并执行] 启动后台任务 - task_id: {task_id}")
        background_tasks.add_task(process_full_textbook_task, task_id)
        
        # 11. 返回任务信息
        updated_task = db.get_task(task_id)
        logger.info(f"[规划并执行] 任务创建并启动成功 - task_id: {task_id}")
        return JSONResponse(content={
            "message": "任务已创建并启动执行",
            "task_id": task_id,
            "task": updated_task
        })
        
    except HTTPException:
        raise
    except Exception as e:
        # 如果任务已创建，更新状态为失败
        if task_id:
            try:
                db.update_task_status(task_id, "FAILED", f"执行任务失败: {str(e)}")
                await task_progress_manager.push_progress(
                    task_id=task_id,
                    progress=0.0,
                    message=f"任务失败: {str(e)}",
                    status="FAILED"
                )
            except Exception:
                pass
        
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "执行任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "执行任务失败"
        raise HTTPException(status_code=500, detail=f"执行任务失败: {error_msg}")

