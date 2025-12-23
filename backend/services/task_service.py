"""
任务处理服务
处理全书自动化出题任务的业务逻辑
"""

import asyncio
import logging
from pathlib import Path
from datetime import datetime

from md_processor import MarkdownProcessor
from generator import generate_questions_for_chunk, OpenRouterClient
from database import db
from task_manager import task_manager
from task_progress import task_progress_manager

# 配置日志
logger = logging.getLogger(__name__)


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
        logger.info(f"[任务] 开始处理任务 - task_id: {task_id}")
        
        # 1. 获取任务信息
        task = db.get_task(task_id)
        if not task:
            logger.error(f"[任务] 任务不存在 - task_id: {task_id}")
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
            logger.error(f"[任务] 教材不存在 - task_id: {task_id}, textbook_id: {textbook_id}")
            db.update_task_status(task_id, "FAILED", f"教材 {textbook_id} 不存在")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message=f"任务失败：教材 {textbook_id} 不存在",
                status="FAILED"
            )
            return
        
        textbook_name = textbook.get("name", "未命名教材")
        logger.info(f"[任务] 任务信息获取成功 - task_id: {task_id}, 教材: {textbook_name}")
        
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
        logger.info(f"[任务] 开始处理文件 - task_id: {task_id}, 文件数: {total_files}")
        
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
        
        # 6. 第一阶段：处理所有文件，收集所有切片的元数据
        logger.info(f"[任务] 第一阶段开始 - 处理文件并收集切片信息")
        
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.05,
            message="正在处理所有文件并收集切片信息...",
            status="PROCESSING"
        )
        
        # 存储所有文件的所有 chunks，并收集切片信息
        all_chunks_info = []  # 存储 (file_id, chunk_index, chunk, chunk_id) 的列表
        file_chunk_mapping = {}  # 存储 file_id -> [(chunk_index, chunk_id), ...] 的映射
        
        for idx, file_info in enumerate(md_files, 1):
            file_id = file_info.get("file_id")
            filename = file_info.get("filename", file_id)
            logger.info(f"[任务] 处理文件 - {idx}/{total_files}: {filename}")
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
            
            if not file_path or not Path(file_path).exists():
                print(f"警告：文件 {file_id} 没有路径或不存在，跳过")
                continue
            
            try:
                # 处理文件切片
                chunks = processor.process(file_path)
                
                if not chunks:
                    print(f"警告：文件 {filename} 切片为空，跳过")
                    continue
                
                # 存储 chunks 到数据库
                db.store_chunks(file_id, chunks)
                
                # 获取存储后的 chunk_id（通过 chunk_index 查询）
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
                
                # 收集切片信息
                file_chunk_mapping[file_id] = []
                for chunk_index, chunk in enumerate(chunks):
                    chunk_id = chunk_index_to_id.get(chunk_index)
                    if chunk_id:
                        metadata = chunk.get("metadata", {})
                        chapter_name = processor.get_chapter_name(metadata)
                        content = chunk.get("content", "")
                        content_summary = content[:500] if len(content) > 500 else content  # 摘要前500字符
                        
                        all_chunks_info.append({
                            "chunk_id": chunk_id,
                            "file_id": file_id,  # 添加 file_id，用于按文件分组
                            "chapter_name": chapter_name or "未命名章节",
                            "content_summary": content_summary
                        })
                        file_chunk_mapping[file_id].append((chunk_index, chunk_id, chunk))
                
                logger.info(f"[任务] 文件处理完成 - {filename}, 切片数: {len(chunks)}")
                print(f"文件 {filename} 处理完成，共 {len(chunks)} 个切片")
                
            except Exception as e:
                error_msg = str(e)
                print(f"错误：处理文件 {filename} 失败: {error_msg}")
                continue
        
        if not all_chunks_info:
            logger.error(f"[任务] 未收集到切片信息 - task_id: {task_id}")
            db.update_task_status(task_id, "FAILED", "没有收集到任何切片信息")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message="任务失败：没有收集到任何切片信息",
                status="FAILED"
            )
            return
        
        logger.info(f"[任务] 第一阶段完成 - 总切片数: {len(all_chunks_info)}")
        
        # 7. 第二阶段：调用 plan_generation_tasks 获取生成计划
        logger.info(f"[任务] 第二阶段开始 - 规划生成任务")
        
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.1,
            message=f"正在规划生成任务（共 {len(all_chunks_info)} 个切片）...",
            status="PROCESSING"
        )
        
        try:
            # 创建 OpenRouter 客户端
            client = OpenRouterClient()
            
            # 调用规划任务
            generation_plan = await client.plan_generation_tasks(
                textbook_name=textbook_name,
                chunks_info=all_chunks_info
            )
            
            # 构建 chunk_id 到规划的映射，方便后续查找
            plan_by_chunk_id = {plan.chunk_id: plan for plan in generation_plan.plans}
            
            logger.info(f"[任务] 第二阶段完成 - 规划题目数: {generation_plan.total_questions}, 题型分布: {generation_plan.type_distribution}")
            print(f"规划完成：共规划 {generation_plan.total_questions} 道题目，题型分布：{generation_plan.type_distribution}")
            
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.15,
                message=f"规划完成：共规划 {generation_plan.total_questions} 道题目",
                status="PROCESSING"
            )
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[任务] 规划任务失败 - task_id: {task_id}, 错误: {error_msg}", exc_info=True)
            print(f"错误：规划生成任务失败: {error_msg}")
            db.update_task_status(task_id, "FAILED", f"规划生成任务失败: {error_msg}")
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=0.0,
                message=f"任务失败：规划生成任务失败: {error_msg}",
                status="FAILED"
            )
            return
        
        # 8. 第三阶段：根据计划生成题目
        logger.info(f"[任务] 第三阶段开始 - 根据计划生成题目")
        
        # 如果任务是从暂停状态恢复的，从上次的进度继续
        current_task_info = db.get_task(task_id)
        start_progress = current_task_info.get("progress", 0.0) if current_task_info else 0.0
        start_file_index = max(0, int(start_progress * total_files))  # 从上次处理的文件继续（0-based索引）
        
        if start_file_index > 0:
            logger.info(f"[任务] 从暂停状态恢复 - 起始文件索引: {start_file_index}")
        
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
            
            # 更新当前处理的文件（规划阶段占 15%，生成阶段占 85%）
            file_progress = (file_index - 1) / total_files
            current_progress = 0.15 + 0.85 * file_progress
            db.update_task_progress(task_id, current_progress, filename)
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=current_progress,
                current_file=filename,
                message=f"正在生成题目: {filename} ({file_index}/{total_files})"
            )
            
            try:
                # 8.1 获取该文件的 chunks（从之前存储的映射中获取）
                if file_id not in file_chunk_mapping:
                    print(f"警告：文件 {file_id} 不在映射中，跳过")
                    continue
                
                file_chunks = file_chunk_mapping[file_id]
                total_chunks = len(file_chunks)
                logger.info(f"[任务] 开始处理文件切片 - 文件: {filename}, 切片数: {total_chunks}")
                
                # 8.2 对每个切片根据计划生成题目
                file_questions_count = 0
                for chunk_idx, (chunk_index, chunk_id, chunk) in enumerate(file_chunks, 1):
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
                    
                    # 从计划中查找该切片的规划
                    chunk_plan = plan_by_chunk_id.get(chunk_id)
                    
                    # 如果该切片在规划中需要生成题目，则根据规划生成
                    if chunk_plan and chunk_plan.question_count > 0:
                        # 使用规划的参数生成题目（按计划生成，使用 type_distribution）
                        if not hasattr(chunk_plan, 'type_distribution') or not chunk_plan.type_distribution:
                            logger.error(f"[任务] 切片 {chunk_id} 的规划缺少 type_distribution 字段")
                            print(f"警告：切片 {chunk_id} 的规划缺少 type_distribution 字段")
                            continue
                        
                        # 重试逻辑：最多重试2次（总共尝试3次）
                        max_retries = 2
                        questions_data = None
                        last_error = None
                        
                        for retry_attempt in range(max_retries + 1):  # 0, 1, 2 (总共3次尝试)
                            try:
                                if retry_attempt == 0:
                                    logger.info(f"[任务] 开始生成切片题目 - chunk_id: {chunk_id}, 计划题目数: {chunk_plan.question_count}, 题型分布: {chunk_plan.type_distribution}")
                                else:
                                    logger.info(f"[任务] 重试生成切片题目 - chunk_id: {chunk_id}, 重试次数: {retry_attempt}/{max_retries}")
                                    print(f"重试生成切片 {chunk_id} 的题目（第 {retry_attempt} 次重试）")
                                
                                questions_data = await generate_questions_for_chunk(
                                    chunk,
                                    type_distribution=chunk_plan.type_distribution,
                                    textbook_name=textbook_name
                                )
                                
                                # 检查是否生成成功（至少生成了一道题目）
                                if questions_data and len(questions_data) > 0:
                                    logger.info(f"[任务] 切片题目生成完成 - chunk_id: {chunk_id}, 实际生成: {len(questions_data)} 道")
                                    
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
                                    
                                    # 生成成功，跳出重试循环
                                    break
                                else:
                                    # 验证失败：返回了空列表（所有题目验证失败）
                                    error_msg = "所有题目验证失败，返回空列表"
                                    last_error = ValueError(error_msg)
                                    logger.warning(f"[任务] 切片题目验证失败 - chunk_id: {chunk_id}, 错误: {error_msg}")
                                    
                                    # 如果还有重试机会，继续重试
                                    if retry_attempt < max_retries:
                                        await asyncio.sleep(1)  # 重试前等待1秒
                                        continue
                                    else:
                                        # 所有重试都失败
                                        logger.error(f"[任务] 切片生成题目失败（已重试{max_retries}次） - chunk_id: {chunk_id}, 错误: {error_msg}")
                                        print(f"警告：切片 {chunk_id} 生成题目失败（已重试{max_retries}次）: {error_msg}")
                                        break
                                        
                            except Exception as e:
                                last_error = e
                                error_msg = str(e)
                                logger.warning(f"[任务] 切片生成题目异常 - chunk_id: {chunk_id}, 重试次数: {retry_attempt}/{max_retries}, 错误: {error_msg}")
                                
                                # 如果还有重试机会，继续重试
                                if retry_attempt < max_retries:
                                    await asyncio.sleep(1)  # 重试前等待1秒
                                    continue
                                else:
                                    # 所有重试都失败
                                    logger.error(f"[任务] 切片生成题目失败（已重试{max_retries}次） - chunk_id: {chunk_id}, 错误: {error_msg}", exc_info=True)
                                    print(f"警告：切片 {chunk_id} 生成题目失败（已重试{max_retries}次）: {error_msg}")
                                    break
                        
                        # 如果最终仍然失败，记录日志但继续处理下一个切片
                        if not questions_data or len(questions_data) == 0:
                            if last_error:
                                logger.error(f"[任务] 切片生成题目最终失败 - chunk_id: {chunk_id}, 已跳过该切片")
                            continue
                    else:
                        # 如果该切片不在规划中或规划为0题，跳过
                        print(f"跳过切片 {chunk_id}：规划中未包含或题目数量为0")
                    
                    # 计算当前进度
                    # 规划阶段占 15%，生成阶段占 85%
                    # 文件级别的进度 = (file_index - 1) / total_files
                    # 文件内切片进度 = chunk_idx / total_chunks
                    # 总体进度 = 0.15 + 0.85 * (文件级别进度 + 文件内切片进度 / total_files)
                    file_base_progress = (file_index - 1) / total_files
                    chunk_progress_in_file = chunk_idx / total_chunks
                    file_progress = file_base_progress + (chunk_progress_in_file / total_files)
                    current_progress = 0.15 + 0.85 * file_progress
                    
                    # 更新进度（每个切片生成后都更新）
                    db.update_task_progress(task_id, current_progress, filename)
                    await task_progress_manager.push_progress(
                        task_id=task_id,
                        progress=current_progress,
                        current_file=filename,
                        message=f"正在生成题目: {filename} - 切片 {chunk_idx}/{total_chunks} ({file_index}/{total_files})",
                        status="PROCESSING"
                    )
                    
                    # 添加小延迟，避免 API 限流
                    await asyncio.sleep(0.5)
                
                logger.info(f"[任务] 文件处理完成 - {filename}, 生成题目数: {file_questions_count}")
                print(f"文件 {filename} 处理完成，生成 {file_questions_count} 道题目")
                
            except Exception as e:
                error_msg = str(e)
                print(f"错误：处理文件 {filename} 失败: {error_msg}")
                # 继续处理下一个文件，不中断整个任务
                continue
            
            # 更新进度（规划阶段占 15%，生成阶段占 85%）
            file_progress = file_index / total_files
            current_progress = 0.15 + 0.85 * file_progress
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
        logger.warning(f"[任务] 任务被取消 - task_id: {task_id}")
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
        logger.error(f"[任务] 任务执行失败 - task_id: {task_id}, 错误: {error_msg}", exc_info=True)
        print(f"任务 {task_id} 执行失败: {error_msg}")
        db.update_task_status(task_id, "FAILED", error_msg)
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.0,
            message=f"任务失败: {error_msg}",
            status="FAILED"
        )

