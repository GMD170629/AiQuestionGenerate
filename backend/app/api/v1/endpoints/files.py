"""
文件管理相关路由
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from app.services.markdown_service import (
    MarkdownProcessor,
    extract_toc,
    calculate_statistics,
    extract_and_store_knowledge_nodes,
)
from app.core.cache import document_cache
from app.core.db import db
from app.schemas import FileInfo, ChunkInfo
from app.services.file_service import process_single_file, ALLOWED_EXTENSIONS

router = APIRouter(prefix="/files", tags=["文件管理"])

# 创建临时目录用于存储上传的文件
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    上传 Markdown 文件接口
    支持 Markdown 文件上传，文件将存储在临时目录中
    上传完成后会在后台异步提取知识点（如果启用）
    """
    result = await process_single_file(file, UPLOAD_DIR)
    
    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result["error"]
        )
    
    # 如果文件解析成功，在后台异步提取知识点
    if result.get("parsed"):
        file_id = result.get("file_id")
        if file_id:
            # 在后台异步提取知识点（不阻塞响应）
            background_tasks.add_task(
                extract_and_store_knowledge_nodes,
                file_id=file_id
            )
            print(f"已添加知识点提取任务到后台队列: file_id={file_id}")
    
    return JSONResponse(status_code=200, content=result)


@router.post("/upload/batch")
async def upload_files_batch(files: List[UploadFile] = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    批量上传 Markdown 文件接口
    支持一次上传多个 Markdown 文件
    上传完成后会在后台异步提取知识点（如果启用）
    
    Args:
        files: 文件列表
        
    Returns:
        包含每个文件上传结果的列表
    """
    if not files:
        raise HTTPException(status_code=400, detail="没有提供文件")
    
    results = []
    for file in files:
        result = await process_single_file(file, UPLOAD_DIR)
        results.append(result)
        
        # 如果文件解析成功，在后台异步提取知识点
        if result.get("parsed"):
            file_id = result.get("file_id")
            if file_id:
                # 在后台异步提取知识点（不阻塞响应）
                background_tasks.add_task(
                    extract_and_store_knowledge_nodes,
                    file_id=file_id
                )
                print(f"已添加知识点提取任务到后台队列: file_id={file_id}")
    
    # 统计成功和失败的数量
    success_count = sum(1 for r in results if "error" not in r)
    failed_count = len(results) - success_count
    
    return JSONResponse(
        status_code=200,
        content={
            "message": f"批量上传完成：成功 {success_count} 个，失败 {failed_count} 个",
            "total": len(results),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }
    )


@router.get("", response_model=List[FileInfo])
async def list_files():
    """
    获取所有已上传的文件列表（从数据库读取）
    """
    try:
        # 从数据库获取所有文件信息
        db_files = db.get_all_files()
        
        files = []
        for db_file in db_files:
            # 获取文件所属的教材
            textbooks = db.get_file_textbooks(db_file["file_id"])
            
            file_data = {
                "file_id": db_file["file_id"],
                "filename": db_file["filename"],
                "file_size": db_file["file_size"],
                "upload_time": db_file["upload_time"],
                "file_path": db_file["file_path"],
                "textbooks": textbooks,  # 添加教材信息
            }
            files.append(file_data)
        
        return files
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取文件列表失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取文件列表失败"
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {error_msg}")


@router.get("/{file_id}")
async def get_file(file_id: str):
    """
    获取文件内容（用于预览）
    """
    # 尝试找到文件（可能是 .md 或 .markdown）
    file_path = None
    for ext in ALLOWED_EXTENSIONS:
        potential_path = UPLOAD_DIR / f"{file_id}{ext}"
        if potential_path.exists():
            file_path = potential_path
            break
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    try:
        # 读取文件内容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 从数据库获取文件信息
        file_info = db.get_file(file_id)
        original_filename = file_info.get("filename", file_path.name) if file_info else file_path.name
        
        return JSONResponse(
            content={
                "file_id": file_id,
                "filename": original_filename,
                "content": content,
                "file_size": file_path.stat().st_size,
            }
        )
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，无法读取")
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "读取文件失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "读取文件失败"
        raise HTTPException(status_code=500, detail=f"读取文件失败: {error_msg}")


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """
    删除文件
    """
    # 尝试找到文件（可能是 .md 或 .markdown）
    file_path = None
    for ext in ALLOWED_EXTENSIONS:
        potential_path = UPLOAD_DIR / f"{file_id}{ext}"
        if potential_path.exists():
            file_path = potential_path
            break
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    try:
        file_path.unlink()
        # 同时从数据库删除文件记录（会自动删除相关的 chunks 和 metadata）
        db.delete_file(file_id)
        return JSONResponse(
            content={
                "message": "文件删除成功",
                "file_id": file_id,
            }
        )
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "删除文件失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "删除文件失败"
        raise HTTPException(status_code=500, detail=f"删除文件失败: {error_msg}")


@router.post("/{file_id}/parse")
async def parse_file(file_id: str, chunk_size: int = 1200, chunk_overlap: int = 200,
                    background_tasks: BackgroundTasks = BackgroundTasks()):
    """
    解析 Markdown 文件
    使用 Markdown 解析引擎对文件进行结构化切分
    解析完成后会在后台异步提取知识点（如果启用）
    
    Args:
        file_id: 文件 ID
        chunk_size: 每个 chunk 的最大字符数（默认 1200）
        chunk_overlap: chunk 之间的重叠字符数（默认 200）
    
    Returns:
        解析后的 chunks 列表，包含 content 和 metadata
    """
    # 尝试找到文件（可能是 .md 或 .markdown）
    file_path = None
    for ext in ALLOWED_EXTENSIONS:
        potential_path = UPLOAD_DIR / f"{file_id}{ext}"
        if potential_path.exists():
            file_path = potential_path
            break
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    try:
        # 使用解析引擎处理文件
        processor = MarkdownProcessor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = processor.process(str(file_path))
        
        # 格式化输出，添加章节名和层级信息
        result = []
        for chunk in chunks:
            chapter_name = processor.get_chapter_name(chunk["metadata"])
            chapter_level = processor.get_chapter_level(chunk["metadata"])
            
            result.append({
                "content": chunk["content"],
                "metadata": {
                    **chunk["metadata"],
                    "chapter_name": chapter_name,
                    "chapter_level": chapter_level,
                }
            })
        
        # 提取目录结构和统计信息
        toc = extract_toc(result)
        stats = calculate_statistics(result)
        
        # 尝试从现有缓存中获取原始文件名，如果没有则使用 UUID 文件名
        existing_metadata = document_cache.get_metadata(file_id)
        original_filename = existing_metadata.get("filename", file_path.name) if existing_metadata else file_path.name
        
        # 获取文件信息（如果存在）
        file_info = db.get_file(file_id)
        upload_time = file_info.get("upload_time", datetime.now().isoformat()) if file_info else datetime.now().isoformat()
        
        # 更新缓存
        document_cache.store(
            file_id=file_id,
            chunks=result,
            metadata={
                "filename": original_filename,
                "file_size": file_path.stat().st_size,
                "file_path": str(file_path),
                "upload_time": upload_time,
                "toc": toc,
                "statistics": stats,
            }
        )
        
        # 提取并保存章节信息
        try:
            from app.services.markdown_service import build_chapters_from_toc_tree, extract_chapters_from_chunks
            
            # 尝试从 processor 中获取目录树
            toc_tree = None
            if hasattr(processor, 'semantic_splitter'):
                content = processor.read_file(str(file_path))
                toc_tree = processor.semantic_splitter.extract_toc_tree(content)
            
            # 构建章节列表
            if toc_tree:
                chapters_data = build_chapters_from_toc_tree(toc_tree, result)
            else:
                chapters_data = extract_chapters_from_chunks(result)
            
            # 建立章节之间的父子关系
            chapter_name_to_temp_id = {}
            for chapter in chapters_data:
                temp_id = str(uuid.uuid4())
                chapter["temp_id"] = temp_id
                chapter_name_to_temp_id[(chapter["level"], chapter["name"])] = temp_id
            
            # 设置 parent_id
            for chapter in chapters_data:
                parent_name = chapter.get("parent_name")
                parent_level = chapter.get("parent_level")
                if parent_name and parent_level:
                    parent_key = (parent_level, parent_name)
                    if parent_key in chapter_name_to_temp_id:
                        chapter["parent_temp_id"] = chapter_name_to_temp_id[parent_key]
                    else:
                        chapter["parent_temp_id"] = None
                else:
                    chapter["parent_temp_id"] = None
                chapter.pop("parent_name", None)
                chapter.pop("parent_level", None)
            
            # 获取 chunk_index 到 chunk_id 的映射
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
            
            # 更新章节数据
            temp_id_to_real_id = {}
            for chapter in chapters_data:
                chunk_indices = chapter.get("chunk_ids", [])
                chunk_ids = [chunk_index_to_id.get(idx) for idx in chunk_indices if idx in chunk_index_to_id]
                chapter["chunk_ids"] = [cid for cid in chunk_ids if cid is not None]
                
                real_id = str(uuid.uuid4())
                temp_id = chapter["temp_id"]
                temp_id_to_real_id[temp_id] = real_id
                chapter["chapter_id"] = real_id
                chapter.pop("temp_id", None)
            
            # 更新 parent_id
            for chapter in chapters_data:
                parent_temp_id = chapter.get("parent_temp_id")
                if parent_temp_id and parent_temp_id in temp_id_to_real_id:
                    chapter["parent_id"] = temp_id_to_real_id[parent_temp_id]
                else:
                    chapter["parent_id"] = None
                chapter.pop("parent_temp_id", None)
            
            # 存储章节到数据库
            db.store_chapters(file_id, chapters_data)
        except Exception as e:
            import traceback
            print(f"警告：章节提取失败: {repr(e)}")
            print(traceback.format_exc())
        
        # 在后台异步提取知识点（不阻塞响应）
        background_tasks.add_task(
            extract_and_store_knowledge_nodes,
            file_id=file_id
        )
        print(f"已添加知识点提取任务到后台队列: file_id={file_id}")
        
        return JSONResponse(
            content={
                "file_id": file_id,
                "filename": original_filename,
                "total_chunks": len(result),
                "toc": toc,
                "statistics": stats,
                "chunks": result,
            }
        )
    except FileNotFoundError as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "文件不存在"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "文件不存在"
        raise HTTPException(status_code=404, detail=error_msg)
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "解析文件失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "解析文件失败"
        raise HTTPException(status_code=500, detail=f"解析文件失败: {error_msg}")


@router.get("/{file_id}/info")
async def get_file_info(file_id: str):
    """
    获取文件的目录结构和统计信息（从缓存中）
    
    Args:
        file_id: 文件 ID
    
    Returns:
        文件的目录结构和统计信息
    """
    # 检查缓存
    cached_metadata = document_cache.get_metadata(file_id)
    if cached_metadata:
        return JSONResponse(
            content={
                "file_id": file_id,
                "parsed": True,
                "toc": cached_metadata.get("toc", []),
                "statistics": cached_metadata.get("statistics", {}),
            }
        )
    
    # 如果缓存中没有，尝试解析文件
    file_path = None
    for ext in ALLOWED_EXTENSIONS:
        potential_path = UPLOAD_DIR / f"{file_id}{ext}"
        if potential_path.exists():
            file_path = potential_path
            break
    
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    try:
        processor = MarkdownProcessor()
        chunks = processor.process(str(file_path))
        toc = extract_toc(chunks)
        stats = calculate_statistics(chunks)
        
        return JSONResponse(
            content={
                "file_id": file_id,
                "parsed": False,
                "toc": toc,
                "statistics": stats,
            }
        )
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取文件信息失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取文件信息失败"
        raise HTTPException(status_code=500, detail=f"获取文件信息失败: {error_msg}")


@router.get("/{file_id}/chunks")
async def get_file_chunks(file_id: str):
    """
    获取文件的切片数据（从数据库读取）
    
    Args:
        file_id: 文件 ID
    
    Returns:
        文件的切片列表，包含 content 和 metadata
    """
    # 从数据库获取切片数据
    chunks = db.get_chunks(file_id)
    if chunks is None:
        raise HTTPException(status_code=404, detail="文件不存在或未解析")
    
    # 获取文件信息
    file_info = db.get_file(file_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 格式化输出，添加章节名和层级信息
    processor = MarkdownProcessor()
    result = []
    for chunk in chunks:
        chapter_name = processor.get_chapter_name(chunk.get("metadata", {}))
        chapter_level = processor.get_chapter_level(chunk.get("metadata", {}))
        
        result.append({
            "content": chunk.get("content", ""),
            "metadata": {
                **chunk.get("metadata", {}),
                "chapter_name": chapter_name,
                "chapter_level": chapter_level,
            }
        })
    
    return JSONResponse(
        content={
            "file_id": file_id,
            "filename": file_info.get("filename", ""),
            "total_chunks": len(result),
            "chunks": result,
        }
    )


@router.get("/{file_id}/chapters")
async def get_file_chapters(file_id: str):
    """
    获取文件的章节树（从数据库读取）
    
    Args:
        file_id: 文件 ID
    
    Returns:
        文件的章节树结构，包含层级关系和关联的切片 ID
    """
    # 检查文件是否存在
    file_info = db.get_file(file_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 获取章节树
    chapter_tree = db.get_chapter_tree(file_id)
    
    return JSONResponse(
        content={
            "file_id": file_id,
            "filename": file_info.get("filename", ""),
            "chapters": chapter_tree,
        }
    )


@router.get("/{file_id}/chapters/flat")
async def get_file_chapters_flat(file_id: str):
    """
    获取文件的章节列表（扁平结构，从数据库读取）
    
    Args:
        file_id: 文件 ID
    
    Returns:
        文件的章节列表（扁平结构）
    """
    # 检查文件是否存在
    file_info = db.get_file(file_id)
    if not file_info:
        raise HTTPException(status_code=404, detail="文件不存在")
    
    # 获取章节列表
    chapters = db.get_file_chapters(file_id)
    
    return JSONResponse(
        content={
            "file_id": file_id,
            "filename": file_info.get("filename", ""),
            "chapters": chapters,
        }
    )


@router.get("/{file_id}/textbooks")
async def get_file_textbooks(file_id: str):
    """
    获取文件所属的所有教材
    
    Args:
        file_id: 文件 ID
        
    Returns:
        教材列表
    """
    try:
        # 检查文件是否存在
        file = db.get_file(file_id)
        if not file:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        textbooks = db.get_file_textbooks(file_id)
        return JSONResponse(content=textbooks)
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取文件所属教材失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取文件所属教材失败"
        raise HTTPException(status_code=500, detail=f"获取文件所属教材失败: {error_msg}")


@router.get("/chapters/{chapter_id}")
async def get_chapter(chapter_id: str):
    """
    获取单个章节信息
    
    Args:
        chapter_id: 章节 ID
    
    Returns:
        章节信息，包含关联的切片列表
    """
    chapter = db.get_chapter(chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    
    # 获取关联的切片
    chunks = db.get_chapter_chunks(chapter_id)
    
    return JSONResponse(
        content={
            "chapter": chapter,
            "chunks": chunks,
        }
    )

