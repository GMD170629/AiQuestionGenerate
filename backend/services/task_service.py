"""
任务处理服务
处理全书自动化出题任务的业务逻辑
"""

import asyncio
from pathlib import Path
from datetime import datetime

from md_processor import MarkdownProcessor
from generator import generate_questions_for_chunk
from database import db
from task_manager import task_manager
from task_progress import task_progress_manager


async def process_full_textbook_task(task_id: str):
    """
    处理全书自动化出题任务（后台异步函数）
    
    逻辑：
    1. 根据 task_id 获取教材信息
    2. 遍历教材下的所有 .md 文件
    3. 对每个文件调用 md_processor 切片
    4. 对每个切片调用 generator 生成题目（使用自适应模式）
    5. 实时更新任务进度
    6. 支持暂停和取消
    
    Args:
        task_id: 任务 ID
    """
    # 注册任务到任务管理器
    current_task = asyncio.current_task()
    if current_task:
        await task_manager.register_task(task_id, current_task)
    
    try:
        # 1. 获取任务信息
        task = db.get_task(task_id)
        if not task:
            print(f"任务 {task_id} 不存在")
            return
        
        textbook_id = task.get("textbook_id")
        if not textbook_id:
            db.update_task_status(task_id, "FAILED", "任务缺少教材 ID")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message="任务失败：缺少教材 ID",
                status="FAILED"
            )
            return
        
        # 2. 获取教材信息
        textbook = db.get_textbook(textbook_id)
        if not textbook:
            db.update_task_status(task_id, "FAILED", f"教材 {textbook_id} 不存在")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message=f"任务失败：教材 {textbook_id} 不存在",
                status="FAILED"
            )
            return
        
        # 3. 获取教材下的所有文件
        files = db.get_textbook_files(textbook_id)
        if not files:
            db.update_task_status(task_id, "FAILED", "教材中没有文件")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message="任务失败：教材中没有文件",
                status="FAILED"
            )
            return
        
        # 过滤出 .md 文件
        md_files = [f for f in files if f.get("file_format", "").lower() in [".md", ".markdown"]]
        
        if not md_files:
            db.update_task_status(task_id, "FAILED", "教材中没有 Markdown 文件")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message="任务失败：教材中没有 Markdown 文件",
                status="FAILED"
            )
            return
        
        # 4. 更新任务状态和总文件数
        total_files = len(md_files)
        db.update_task(task_id, status="PROCESSING", total_files=total_files)
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.0,
            message=f"开始处理 {total_files} 个文件",
            status="PROCESSING"
        )
        
        # 5. 初始化处理器
        processor = MarkdownProcessor(
            chunk_size=1200,
            chunk_overlap=200,
            max_tokens_before_split=1500
        )
        
        # 6. 遍历每个文件
        # 如果任务是从暂停状态恢复的，从上次的进度继续
        current_task_info = db.get_task(task_id)
        start_progress = current_task_info.get("progress", 0.0) if current_task_info else 0.0
        start_file_index = max(0, int(start_progress * total_files))  # 从上次处理的文件继续（0-based索引）
        
        total_questions_generated = 0
        for idx, file_info in enumerate(md_files[start_file_index:], start_file_index):
            file_index = idx + 1  # 转换为1-based索引用于显示
            
            # 检查任务是否已取消或暂停
            if not await task_manager.check_and_wait(task_id):
                db.update_task_status(task_id, "CANCELLED", "任务已取消")
                await task_progress_manager.push_progress(
                    task_id=task_id,
                    progress=db.get_task(task_id).get("progress", 0.0),
                    message="任务已取消",
                    status="CANCELLED"
                )
                return
            
            file_id = file_info.get("file_id")
            filename = file_info.get("filename", file_id)
            file_path = file_info.get("file_path")
            
            if not file_path:
                print(f"警告：文件 {file_id} 没有路径，跳过")
                continue
            
            # 更新当前处理的文件
            current_progress = (file_index - 1) / total_files
            db.update_task_progress(task_id, current_progress, filename)
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=current_progress,
                current_file=filename,
                message=f"正在处理: {filename} ({file_index}/{total_files})"
            )
            
            try:
                # 6.1 处理文件切片
                if not Path(file_path).exists():
                    print(f"警告：文件 {file_path} 不存在，跳过")
                    continue
                
                chunks = processor.process(file_path)
                
                if not chunks:
                    print(f"警告：文件 {filename} 切片为空，跳过")
                    continue
                
                total_chunks = len(chunks)
                
                # 6.2 对每个切片生成题目（使用自适应模式）
                file_questions_count = 0
                for chunk_index, chunk in enumerate(chunks, 1):
                    # 检查任务是否已取消或暂停
                    if not await task_manager.check_and_wait(task_id):
                        db.update_task_status(task_id, "CANCELLED", "任务已取消")
                        await task_progress_manager.push_progress(
                            task_id=task_id,
                            progress=db.get_task(task_id).get("progress", 0.0),
                            message="任务已取消",
                            status="CANCELLED"
                        )
                        return
                    
                    try:
                        # 使用自适应模式生成题目
                        textbook_name = textbook.get("name") if textbook else None
                        questions_data = await generate_questions_for_chunk(
                            chunk,
                            textbook_name=textbook_name
                        )
                        
                        if questions_data:
                            # 保存题目到数据库
                            for question in questions_data:
                                # 添加章节信息
                                metadata = chunk.get("metadata", {})
                                chapter_name = processor.get_chapter_name(metadata)
                                if chapter_name:
                                    question["chapter"] = chapter_name
                                
                                # 保存题目（关联到文件、教材和任务）
                                db.store_question(
                                    file_id=file_id,
                                    question=question,
                                    source_file=filename,
                                    textbook_id=textbook_id,
                                    file_path=file_path
                                )
                                file_questions_count += 1
                                total_questions_generated += 1
                        
                        # 计算当前进度
                        # 文件级别的进度 = (file_index - 1) / total_files
                        # 文件内切片进度 = chunk_index / total_chunks
                        # 总体进度 = 文件级别进度 + (文件内切片进度 / total_files)
                        file_base_progress = (file_index - 1) / total_files
                        chunk_progress_in_file = chunk_index / total_chunks
                        current_progress = file_base_progress + (chunk_progress_in_file / total_files)
                        
                        # 更新进度（每个切片生成后都更新）
                        db.update_task_progress(task_id, current_progress, filename)
                        await task_progress_manager.push_progress(
                            task_id=task_id,
                            progress=current_progress,
                            current_file=filename,
                            message=f"正在处理: {filename} - 切片 {chunk_index}/{total_chunks} ({file_index}/{total_files})",
                            status="PROCESSING"
                        )
                        
                        # 添加小延迟，避免 API 限流
                        await asyncio.sleep(0.5)
                        
                    except Exception as e:
                        print(f"警告：切片 {chunk_index} 生成题目失败: {e}")
                        continue
                
                print(f"文件 {filename} 处理完成，生成 {file_questions_count} 道题目")
                
            except Exception as e:
                error_msg = str(e)
                print(f"错误：处理文件 {filename} 失败: {error_msg}")
                # 继续处理下一个文件，不中断整个任务
                continue
            
            # 更新进度
            current_progress = file_index / total_files
            db.update_task_progress(task_id, current_progress, filename)
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=current_progress,
                current_file=filename,
                message=f"已完成: {filename} ({file_index}/{total_files})，已生成 {total_questions_generated} 道题目"
            )
        
        # 7. 任务完成（再次检查是否被取消）
        if await task_manager.is_cancelled(task_id):
            db.update_task_status(task_id, "CANCELLED", "任务已取消")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=db.get_task(task_id).get("progress", 0.0),
                message="任务已取消",
                status="CANCELLED"
            )
        else:
            db.update_task_status(task_id, "COMPLETED")
            db.update_task_progress(task_id, 1.0)
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=1.0,
                message=f"任务完成！共生成 {total_questions_generated} 道题目",
                status="COMPLETED"
            )
            print(f"任务 {task_id} 完成，共生成 {total_questions_generated} 道题目")
        
    except asyncio.CancelledError:
        # 任务被取消
        db.update_task_status(task_id, "CANCELLED", "任务已取消")
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=db.get_task(task_id).get("progress", 0.0) if db.get_task(task_id) else 0.0,
            message="任务已取消",
            status="CANCELLED"
        )
        print(f"任务 {task_id} 已取消")
    except Exception as e:
        error_msg = str(e)
        print(f"任务 {task_id} 执行失败: {error_msg}")
        db.update_task_status(task_id, "FAILED", error_msg)
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.0,
            message=f"任务失败: {error_msg}",
            status="FAILED"
        )

