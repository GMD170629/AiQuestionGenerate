"""
知识提取进度相关路由
"""

import asyncio
import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from app.core.knowledge_extraction_progress import knowledge_extraction_progress
from app.services.markdown_service import extract_and_store_knowledge_nodes
from app.core.db import db

router = APIRouter(prefix="/knowledge-extraction", tags=["知识提取进度"])


@router.get("/{file_id}/progress")
async def get_knowledge_extraction_progress(file_id: str):
    """
    获取知识提取进度（SSE 流式）
    
    Args:
        file_id: 文件 ID
        
    Returns:
        Server-Sent Events 流，包含进度更新
    """
    import json as json_module
    
    async def progress_generator():
        newline = "\n"
        
        # 获取最后状态
        last_state = await knowledge_extraction_progress.get_last_state(file_id)
        if last_state:
            initial_data = {
                "status": "connected",
                **last_state
            }
            yield f"data: {json_module.dumps(initial_data, ensure_ascii=False)}{newline}{newline}"
        
        # 创建进度队列
        progress_queue = asyncio.Queue()
        await knowledge_extraction_progress.register_queue(file_id, progress_queue)
        
        try:
            while True:
                try:
                    # 等待进度更新（超时时间 30 秒）
                    progress_data = await asyncio.wait_for(progress_queue.get(), timeout=30.0)
                    
                    # 发送进度更新
                    yield f"data: {json_module.dumps(progress_data, ensure_ascii=False)}{newline}{newline}"
                    
                    # 如果已完成或失败，结束流
                    if progress_data.get("status") in ["completed", "failed"]:
                        break
                        
                except asyncio.TimeoutError:
                    # 发送心跳，保持连接
                    heartbeat = {
                        "status": "heartbeat",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json_module.dumps(heartbeat, ensure_ascii=False)}{newline}{newline}"
                    
                    # 检查是否已完成
                    current_state = await knowledge_extraction_progress.get_last_state(file_id)
                    if current_state and current_state.get("status") in ["completed", "failed"]:
                        final_data = {
                            "status": current_state.get("status"),
                            **current_state
                        }
                        yield f"data: {json_module.dumps(final_data, ensure_ascii=False)}{newline}{newline}"
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
            # 注销队列
            await knowledge_extraction_progress.unregister_queue(file_id, progress_queue)
    
    return StreamingResponse(
        progress_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/{file_id}/status")
async def get_knowledge_extraction_status(file_id: str):
    """
    获取知识提取的当前状态（一次性查询）
    
    Args:
        file_id: 文件 ID
        
    Returns:
        当前进度状态
    """
    state = await knowledge_extraction_progress.get_last_state(file_id)
    
    if not state:
        return {
            "file_id": file_id,
            "status": "not_started",
            "message": "知识提取尚未开始",
            "current": 0,
            "total": 0,
            "progress": 0.0,
            "percentage": 0.0
        }
    
    return {
        "file_id": file_id,
        **state
    }


@router.post("/{file_id}/retry")
async def retry_knowledge_extraction(file_id: str, background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    重试知识提取任务
    
    Args:
        file_id: 文件 ID
        background_tasks: 后台任务管理器
        
    Returns:
        重试任务已启动的确认信息
    """
    # 检查文件是否存在
    file_info = db.get_file(file_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 检查文件是否有切片
    chunks = db.get_chunks(file_id)
    if not chunks or len(chunks) == 0:
        raise HTTPException(status_code=400, detail="文件没有切片，无法进行知识提取")
    
    # 清除之前的进度状态（如果存在）
    await knowledge_extraction_progress.clear_progress(file_id)
    
    # 在后台异步执行知识提取任务
    background_tasks.add_task(
        extract_and_store_knowledge_nodes,
        file_id=file_id
    )
    
    return {
        "file_id": file_id,
        "message": "知识提取任务已启动",
        "status": "started"
    }

