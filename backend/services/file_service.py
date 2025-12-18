"""
文件处理服务
处理文件上传、解析、存储等业务逻辑
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import UploadFile, HTTPException

from md_processor import (
    MarkdownProcessor,
    extract_toc,
    calculate_statistics,
)
from document_cache import document_cache
from database import db

# 允许的文件类型
ALLOWED_EXTENSIONS = {".md", ".markdown"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


async def process_single_file(file: UploadFile, upload_dir: Path) -> Dict[str, Any]:
    """
    处理单个文件上传的辅助函数
    
    Args:
        file: 上传的文件对象
        upload_dir: 上传目录路径
        
    Returns:
        包含文件信息的字典，如果失败则包含 error 字段
    """
    try:
        # 检查文件扩展名
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            return {
                "filename": file.filename,
                "error": f"不支持的文件类型。仅支持 Markdown 文件（.md 或 .markdown）。"
            }
        
        # 读取文件内容以检查大小
        contents = await file.read()
        file_size = len(contents)
        
        # 检查文件大小
        if file_size > MAX_FILE_SIZE:
            return {
                "filename": file.filename,
                "error": f"文件过大。最大允许大小为 {MAX_FILE_SIZE / 1024 / 1024}MB。"
            }
        
        if file_size == 0:
            return {
                "filename": file.filename,
                "error": "文件为空。"
            }
        
        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        file_path = upload_dir / f"{file_id}{file_ext}"
        
        # 保存文件
        try:
            with open(file_path, "wb") as f:
                f.write(contents)
        except Exception as e:
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "文件保存失败"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "文件保存失败"
            return {
                "filename": file.filename,
                "error": f"文件保存失败: {error_msg}"
            }
        
        # 自动解析文件并缓存
        try:
            processor = MarkdownProcessor(
                chunk_size=1200,
                chunk_overlap=200,
                max_tokens_before_split=1500
            )
            chunks = processor.process(str(file_path))
            
            # 打印切片信息（用于验证）
            print(f"\n{'='*80}")
            print(f"文件解析完成: {file.filename}")
            print(f"{'='*80}")
            print(f"总切片数量: {len(chunks)}")
            print(f"\n前 2 个切片预览:")
            print(f"{'-'*80}")
            
            for idx, chunk in enumerate(chunks[:2], 1):
                metadata = chunk.get("metadata", {})
                content_preview = chunk.get("content", "")[:200]  # 前200字符预览
                
                # 构建标题路径
                header_path = []
                if "Header 1" in metadata:
                    header_path.append(f"H1: {metadata['Header 1']}")
                if "Header 2" in metadata:
                    header_path.append(f"H2: {metadata['Header 2']}")
                if "Header 3" in metadata:
                    header_path.append(f"H3: {metadata['Header 3']}")
                
                print(f"\n切片 #{idx}:")
                print(f"  标题路径: {' > '.join(header_path) if header_path else '无标题'}")
                print(f"  内容长度: {len(chunk.get('content', ''))} 字符")
                print(f"  估算 tokens: {processor._estimate_tokens(chunk.get('content', ''))}")
                if "chunk_index" in metadata:
                    print(f"  二次切片索引: {metadata['chunk_index']}/{metadata.get('total_chunks', 1)-1}")
                print(f"  内容预览: {content_preview}...")
                print(f"{'-'*80}")
            
            print(f"{'='*80}\n")
            
            # 提取目录结构和统计信息
            toc = extract_toc(chunks)
            stats = calculate_statistics(chunks)
            
            upload_time = datetime.now().isoformat()
            
            # 存储到数据库（通过 document_cache）
            document_cache.store(
                file_id=file_id,
                chunks=chunks,
                metadata={
                    "filename": file.filename,
                    "file_size": file_size,
                    "file_path": str(file_path),
                    "upload_time": upload_time,
                    "toc": toc,
                    "statistics": stats,
                }
            )
            
            # 提取并保存章节信息
            try:
                _store_chapters(file_id, file_path, chunks, processor)
            except Exception as e:
                # 章节提取失败不影响文件上传，但记录错误
                import traceback
                print(f"警告：章节提取失败: {repr(e)}")
                print(traceback.format_exc())
            
            # 注意：知识点提取将在后台异步进行，不阻塞文件上传响应
            # 知识点提取会在 chunks 存储到数据库后自动触发
            
            # 返回包含解析结果的信息
            return {
                "message": "文件上传并解析成功",
                "file_id": file_id,
                "filename": file.filename,
                "file_size": file_size,
                "file_path": str(file_path),
                "upload_time": datetime.now().isoformat(),
                "parsed": True,
                "total_chunks": len(chunks),
                "toc": toc,
                "statistics": stats,
            }
        except Exception as e:
            # 解析失败不影响上传，但记录错误
            return {
                "message": "文件上传成功，但解析失败",
                "file_id": file_id,
                "filename": file.filename,
                "file_size": file_size,
                "file_path": str(file_path),
                "upload_time": datetime.now().isoformat(),
                "parsed": False,
                "parse_error": repr(e) if hasattr(e, '__repr__') else "解析错误",
            }
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "处理文件失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "处理文件失败"
        return {
            "filename": file.filename if file else "未知文件",
            "error": f"处理文件失败: {error_msg}"
        }


def _store_chapters(file_id: str, file_path: Path, chunks: list, processor: MarkdownProcessor):
    """
    存储章节信息到数据库
    
    Args:
        file_id: 文件 ID
        file_path: 文件路径
        chunks: 切片列表
        processor: Markdown 处理器
    """
    from md_processor import build_chapters_from_toc_tree, extract_chapters_from_chunks
    
    # 尝试从 processor 中获取目录树
    toc_tree = None
    if hasattr(processor, 'semantic_splitter'):
        content = processor.read_file(str(file_path))
        toc_tree = processor.semantic_splitter.extract_toc_tree(content)
    
    # 构建章节列表（使用 chunk_index，稍后转换为 chunk_id）
    if toc_tree:
        chapters_data = build_chapters_from_toc_tree(toc_tree, chunks)
    else:
        chapters_data = extract_chapters_from_chunks(chunks)
    
    # 建立章节之间的父子关系（通过名称匹配）
    chapter_name_to_temp_id = {}  # 临时存储章节名称到临时 ID 的映射
    for chapter in chapters_data:
        # 生成临时 ID（实际存储时会生成真正的 UUID）
        temp_id = str(uuid.uuid4())
        chapter["temp_id"] = temp_id
        chapter_name_to_temp_id[(chapter["level"], chapter["name"])] = temp_id
    
    # 设置 parent_id（使用临时 ID）
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
        
        # 清理临时字段
        chapter.pop("parent_name", None)
        chapter.pop("parent_level", None)
    
    # 等待 chunks 存储完成后再获取 chunk_id
    # 查询数据库获取 chunk_index 到 chunk_id 的映射
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
    
    # 更新章节数据中的 chunk_ids（从 chunk_index 转换为 chunk_id）
    # 并建立临时 ID 到真实 ID 的映射
    temp_id_to_real_id = {}
    for chapter in chapters_data:
        # 转换 chunk_ids
        chunk_indices = chapter.get("chunk_ids", [])
        chunk_ids = [chunk_index_to_id.get(idx) for idx in chunk_indices if idx in chunk_index_to_id]
        chapter["chunk_ids"] = [cid for cid in chunk_ids if cid is not None]
        
        # 生成真实的章节 ID
        real_id = str(uuid.uuid4())
        temp_id = chapter["temp_id"]
        temp_id_to_real_id[temp_id] = real_id
        chapter["chapter_id"] = real_id
        chapter.pop("temp_id", None)
    
    # 更新 parent_id（从临时 ID 转换为真实 ID）
    for chapter in chapters_data:
        parent_temp_id = chapter.get("parent_temp_id")
        if parent_temp_id and parent_temp_id in temp_id_to_real_id:
            chapter["parent_id"] = temp_id_to_real_id[parent_temp_id]
        else:
            chapter["parent_id"] = None
        chapter.pop("parent_temp_id", None)
    
    # 存储章节到数据库
    db.store_chapters(file_id, chapters_data)

