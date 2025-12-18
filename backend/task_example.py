"""
任务进度推送使用示例
展示如何在生成任务中集成进度推送功能
"""

import asyncio
from typing import List, Dict, Any
from database import db
from task_progress import task_progress_manager


async def generate_questions_for_textbook(
    task_id: str,
    textbook_id: str,
    file_ids: List[str],
    question_types: List[str],
    question_count: int = 5
):
    """
    为教材生成题目的示例函数
    
    这个函数展示了如何在生成任务中：
    1. 创建任务
    2. 更新任务进度
    3. 推送进度更新
    4. 处理每个文件
    5. 完成任务
    
    Args:
        task_id: 任务 ID
        textbook_id: 教材 ID
        file_ids: 文件 ID 列表
        question_types: 题型列表
        question_count: 每种题型的数量
    """
    total_files = len(file_ids)
    
    # 1. 创建任务
    db.create_task(task_id, textbook_id, total_files)
    await task_progress_manager.push_progress(
        task_id=task_id,
        progress=0.0,
        message=f"开始处理 {total_files} 个文件"
    )
    
    # 2. 更新任务状态为处理中
    db.update_task_status(task_id, "PROCESSING")
    
    try:
        # 3. 遍历每个文件
        for file_index, file_id in enumerate(file_ids):
            # 获取文件信息
            file_info = db.get_file(file_id)
            if not file_info:
                continue
            
            filename = file_info.get("filename", file_id)
            file_path = file_info.get("file_path", "")
            
            # 计算当前进度
            current_progress = (file_index + 1) / total_files
            
            # 更新数据库中的任务进度
            db.update_task_progress(
                task_id=task_id,
                progress=current_progress,
                current_file=filename
            )
            
            # 推送进度更新
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=current_progress,
                current_file=filename,
                message=f"正在处理: {filename} ({file_index + 1}/{total_files})"
            )
            
            # 这里可以调用实际的生成逻辑
            # 例如：从 document_cache 获取 chunks，然后调用 generate_questions
            # chunks = document_cache.get_chunks(file_id)
            # questions = await generate_questions(...)
            # db.store_questions(file_id, questions, filename, textbook_id, file_path)
            
            # 模拟处理时间
            await asyncio.sleep(1)
        
        # 4. 任务完成
        db.update_task_status(task_id, "COMPLETED")
        db.update_task_progress(task_id, 1.0)
        
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=1.0,
            message="所有文件处理完成",
            status="COMPLETED"
        )
        
    except Exception as e:
        # 5. 任务失败
        error_message = str(e)
        db.update_task_status(task_id, "FAILED", error_message)
        
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.0,
            message=f"任务失败: {error_message}",
            status="FAILED"
        )
        
        raise


# 使用示例
async def main():
    """使用示例"""
    task_id = "task-123"
    textbook_id = "textbook-456"
    file_ids = ["file-1", "file-2", "file-3"]
    question_types = ["单选题", "多选题", "判断题"]
    
    await generate_questions_for_textbook(
        task_id=task_id,
        textbook_id=textbook_id,
        file_ids=file_ids,
        question_types=question_types,
        question_count=5
    )


if __name__ == "__main__":
    asyncio.run(main())

