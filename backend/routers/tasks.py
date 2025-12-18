"""
任务管理相关路由
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse

from database import db
from models import TaskCreate, TaskUpdate
from schemas import TextbookGenerationRequest
from task_manager import task_manager
from task_progress import task_progress_manager
from services.task_service import process_full_textbook_task

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
        return StreamingResponse(error_generator(), media_type="text/event-stream")
    
    async def progress_generator():
        newline = "\n"
        
        # 注册进度队列
        progress_queue = await task_progress_manager.register_queue(task_id)
        
        try:
            # 发送初始状态（从数据库获取）
            initial_state = {
                "status": "connected",
                "progress": task.get("progress", 0.0),
                "percentage": round(task.get("progress", 0.0) * 100, 2),
                "current_file": task.get("current_file"),
                "status": task.get("status", "PENDING"),
                "total_files": task.get("total_files", 0),
                "message": "已连接到进度流",
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json_module.dumps(initial_state, ensure_ascii=False)}{newline}{newline}"
            
            # 获取最后状态（如果有）
            last_state = await task_progress_manager.get_last_state(task_id)
            if last_state:
                yield f"data: {json_module.dumps(last_state, ensure_ascii=False)}{newline}{newline}"
            
            # 持续监听进度更新
            while True:
                try:
                    # 等待进度更新，设置超时以定期发送心跳
                    progress_data = await asyncio.wait_for(progress_queue.get(), timeout=30.0)
                    
                    # 构建响应数据
                    # 如果 progress_data 中没有 status 或 status 为 None，使用 "progress"
                    response_data = {
                        **progress_data,
                        "status": progress_data.get("status") or "progress"
                    }
                    
                    yield f"data: {json_module.dumps(response_data, ensure_ascii=False)}{newline}{newline}"
                    
                    # 如果任务完成或失败，结束流
                    if progress_data.get("status") in ["COMPLETED", "FAILED"]:
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
                        task_status = current_task.get("status")
                        if task_status in ["COMPLETED", "FAILED"]:
                            final_state = {
                                "status": task_status.lower(),
                                "progress": current_task.get("progress", 1.0 if task_status == "COMPLETED" else 0.0),
                                "percentage": round(current_task.get("progress", 1.0 if task_status == "COMPLETED" else 0.0) * 100, 2),
                                "current_file": current_task.get("current_file"),
                                "message": "任务已完成" if task_status == "COMPLETED" else "任务失败",
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
    
    return StreamingResponse(progress_generator(), media_type="text/event-stream")


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
    request: TextbookGenerationRequest,
    background_tasks: BackgroundTasks
):
    """
    启动全书自动化出题任务
    
    当用户选择教材点击生成时：
    1. 在数据库创建一个 Task 记录
    2. 使用 FastAPI.BackgroundTasks 启动后台任务
    3. 立即返回 task_id，前端可以通过 SSE 接口监听进度
    
    Args:
        request: 教材生成请求，包含 textbook_id
        background_tasks: FastAPI 后台任务管理器
        
    Returns:
        任务信息，包含 task_id
    """
    try:
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
        success = db.create_task(
            task_id=task_id,
            textbook_id=request.textbook_id,
            total_files=total_files
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="创建任务失败")
        
        # 4. 启动后台任务
        background_tasks.add_task(process_full_textbook_task, task_id)
        
        # 5. 返回任务信息
        task = db.get_task(task_id)
        return JSONResponse(content={
            "message": "任务已启动",
            "task_id": task_id,
            "task": task
        })
        
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "启动任务失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "启动任务失败"
        raise HTTPException(status_code=500, detail=f"启动任务失败: {error_msg}")

