import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from md_processor import (
    MarkdownProcessor,
    process_markdown_file,
    extract_toc,
    calculate_statistics,
)
from document_cache import document_cache
from generator import (
    generate_questions, 
    generate_questions_for_chunk,
    OpenRouterClient, 
    select_random_chunks, 
    build_context_from_chunks, 
    get_chapter_name_from_chunks
)
from models import QuestionGenerationRequest, QuestionList, Task, TaskCreate, TaskUpdate
from database import db
from task_progress import task_progress_manager
from task_manager import task_manager

app = FastAPI(title="AI 计算机教材习题生成器", version="1.0.0")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js 默认端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建临时目录用于存储上传的文件
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 允许的文件类型
ALLOWED_EXTENSIONS = {".md", ".markdown"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


# Pydantic 模型
class FileInfo(BaseModel):
    file_id: str
    filename: str
    file_size: int
    upload_time: str
    file_path: str
    textbooks: Optional[List[Dict[str, Any]]] = Field(default=[], description="文件所属的教材列表")


class ChunkInfo(BaseModel):
    content: str
    metadata: dict


@app.get("/")
async def root():
    return {"message": "AI 计算机教材习题生成器 API"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/config/ai")
async def get_ai_config():
    """
    获取 AI 配置信息（API端点、密钥、模型）
    注意：返回完整的配置信息，包括 API Key
    """
    try:
        config = db.get_ai_config()
        return JSONResponse(content=config)
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取配置失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取配置失败"
        raise HTTPException(status_code=500, detail=f"获取AI配置失败: {error_msg}")


class AIConfigUpdate(BaseModel):
    api_endpoint: str = Field(..., description="API端点URL")
    api_key: str = Field(..., description="API密钥")
    model: str = Field(..., description="模型名称")


@app.post("/config/ai")
async def update_ai_config(config: AIConfigUpdate):
    """
    更新 AI 配置信息（API端点、密钥、模型）
    
    Args:
        config: AI配置对象，包含 api_endpoint, api_key, model
    """
    try:
        # 验证配置
        if not config.api_endpoint:
            raise HTTPException(status_code=400, detail="API端点不能为空")
        if not config.model:
            raise HTTPException(status_code=400, detail="模型名称不能为空")
        
        # 更新配置
        success = db.update_ai_config(
            api_endpoint=config.api_endpoint,
            api_key=config.api_key,
            model=config.model
        )
        
        if success:
            return JSONResponse(
                content={
                    "message": "配置更新成功",
                    "config": {
                        "api_endpoint": config.api_endpoint,
                        "api_key": config.api_key[:10] + "..." if len(config.api_key) > 10 else "已设置",
                        "model": config.model
                    }
                }
            )
        else:
            raise HTTPException(status_code=500, detail="更新配置失败")
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "更新配置失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "更新配置失败"
        raise HTTPException(status_code=500, detail=f"更新AI配置失败: {error_msg}")


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    上传 Markdown 文件接口
    支持 Markdown 文件上传，文件将存储在临时目录中
    """
    # 检查文件扩展名
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型。仅支持 Markdown 文件（.md 或 .markdown）。"
        )
    
    # 读取文件内容以检查大小
    contents = await file.read()
    file_size = len(contents)
    
    # 检查文件大小
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大。最大允许大小为 {MAX_FILE_SIZE / 1024 / 1024}MB。"
        )
    
    if file_size == 0:
        raise HTTPException(
            status_code=400,
            detail="文件为空。"
        )
    
    # 生成唯一文件名
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    
    # 保存文件
    try:
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "文件保存失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "文件保存失败"
        raise HTTPException(
            status_code=500,
            detail=f"文件保存失败: {error_msg}"
        )
    
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
            # 从 chunks 中提取章节结构
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
        except Exception as e:
            # 章节提取失败不影响文件上传，但记录错误
            import traceback
            print(f"警告：章节提取失败: {repr(e)}")
            print(traceback.format_exc())
        
        # 返回包含解析结果的信息
        return JSONResponse(
            status_code=200,
            content={
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
        )
    except Exception as e:
        # 解析失败不影响上传，但记录错误
        return JSONResponse(
            status_code=200,
            content={
                "message": "文件上传成功，但解析失败",
                "file_id": file_id,
                "filename": file.filename,
                "file_size": file_size,
                "file_path": str(file_path),
                "upload_time": datetime.now().isoformat(),
                "parsed": False,
                "parse_error": repr(e) if hasattr(e, '__repr__') else "解析错误",
            }
        )


@app.get("/files", response_model=List[FileInfo])
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


@app.get("/files/{file_id}")
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


@app.delete("/files/{file_id}")
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


@app.post("/files/{file_id}/parse")
async def parse_file(file_id: str, chunk_size: int = 1200, chunk_overlap: int = 200):
    """
    解析 Markdown 文件
    使用 Markdown 解析引擎对文件进行结构化切分
    
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
            from md_processor import build_chapters_from_toc_tree, extract_chapters_from_chunks
            
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


@app.get("/files/{file_id}/info")
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


@app.get("/files/{file_id}/chunks")
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


@app.get("/files/{file_id}/chapters")
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


@app.get("/files/{file_id}/chapters/flat")
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


@app.get("/chapters/{chapter_id}")
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


@app.post("/generate", response_model=QuestionList)
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


@app.post("/generate/stream")
async def generate_questions_stream_endpoint(request: QuestionGenerationRequest):
    """
    流式生成题目接口（Server-Sent Events）
    
    根据上传的 Markdown 文件流式生成习题，实时返回生成状态。
    
    Args:
        request: 题目生成请求，包含文件 ID、题型、数量等参数
    
    Returns:
        StreamingResponse: Server-Sent Events 流式响应
    """
    import json as json_module
    import asyncio
    
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
                
                # 调用流式生成
                questions_data = await client.generate_questions_stream(
                    context=context,
                    question_count=total_question_count,
                    question_types=request.question_types,
                    chapter_name=chapter_name,
                    on_status_update=lambda s, d: status_queue.put_nowait((s, d))
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
                    status, data = await asyncio.wait_for(status_queue.get(), timeout=120.0)
                    
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


@app.get("/questions")
async def get_all_questions(
    file_id: Optional[str] = None,
    question_type: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0
):
    """
    获取所有题目列表（支持按文件和题型筛选）
    
    Args:
        file_id: 文件 ID（可选，如果提供则只返回该文件的题目）
        question_type: 题型（可选，如果提供则只返回该题型的题目）
        limit: 限制返回数量（可选）
        offset: 偏移量（用于分页）
    
    Returns:
        题目列表和总数
    """
    try:
        questions = db.get_all_questions(
            file_id=file_id,
            question_type=question_type,
            limit=limit,
            offset=offset
        )
        
        total = db.get_question_count(file_id=file_id, question_type=question_type)
        
        return JSONResponse(
            content={
                "questions": questions,
                "total": total,
                "limit": limit,
                "offset": offset
            }
        )
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取题目列表失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取题目列表失败"
        raise HTTPException(status_code=500, detail=f"获取题目列表失败: {error_msg}")


@app.get("/questions/statistics")
async def get_question_statistics():
    """
    获取题目统计信息
    
    Returns:
        包含题型分布、文件分布等统计信息的字典
    """
    try:
        stats = db.get_question_statistics()
        return JSONResponse(content=stats)
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取统计信息失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取统计信息失败"
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {error_msg}")


# ========== 教材相关 API ==========

class TextbookCreate(BaseModel):
    name: str = Field(..., description="教材名称")
    description: Optional[str] = Field(default=None, description="教材描述")


class TextbookUpdate(BaseModel):
    name: Optional[str] = Field(default=None, description="教材名称")
    description: Optional[str] = Field(default=None, description="教材描述")


class FileToTextbook(BaseModel):
    file_id: str = Field(..., description="文件 ID")
    display_order: int = Field(default=0, description="显示顺序")


class FileOrderUpdate(BaseModel):
    display_order: int = Field(..., ge=0, description="新的显示顺序")


@app.post("/textbooks")
async def create_textbook(textbook: TextbookCreate):
    """
    创建教材
    
    Args:
        textbook: 教材信息
        
    Returns:
        创建的教材信息
    """
    try:
        textbook_id = str(uuid.uuid4())
        success = db.create_textbook(
            textbook_id=textbook_id,
            name=textbook.name,
            description=textbook.description
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="创建教材失败，可能教材 ID 已存在")
        
        created_textbook = db.get_textbook(textbook_id)
        return JSONResponse(content=created_textbook)
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "创建教材失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "创建教材失败"
        raise HTTPException(status_code=500, detail=f"创建教材失败: {error_msg}")


@app.get("/textbooks")
async def list_textbooks():
    """
    获取所有教材列表
    
    Returns:
        教材列表
    """
    try:
        textbooks = db.get_all_textbooks()
        return JSONResponse(content=textbooks)
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取教材列表失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取教材列表失败"
        raise HTTPException(status_code=500, detail=f"获取教材列表失败: {error_msg}")


@app.get("/textbooks/{textbook_id}")
async def get_textbook(textbook_id: str):
    """
    获取教材详情
    
    Args:
        textbook_id: 教材 ID
        
    Returns:
        教材信息和文件列表
    """
    try:
        textbook = db.get_textbook(textbook_id)
        if not textbook:
            raise HTTPException(status_code=404, detail="教材不存在")
        
        files = db.get_textbook_files(textbook_id)
        
        return JSONResponse(content={
            **textbook,
            "files": files
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取教材详情失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取教材详情失败"
        raise HTTPException(status_code=500, detail=f"获取教材详情失败: {error_msg}")


@app.put("/textbooks/{textbook_id}")
async def update_textbook(textbook_id: str, textbook: TextbookUpdate):
    """
    更新教材信息
    
    Args:
        textbook_id: 教材 ID
        textbook: 要更新的教材信息
        
    Returns:
        更新后的教材信息
    """
    try:
        # 检查教材是否存在
        existing = db.get_textbook(textbook_id)
        if not existing:
            raise HTTPException(status_code=404, detail="教材不存在")
        
        success = db.update_textbook(
            textbook_id=textbook_id,
            name=textbook.name,
            description=textbook.description
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="更新教材失败")
        
        updated_textbook = db.get_textbook(textbook_id)
        return JSONResponse(content=updated_textbook)
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "更新教材失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "更新教材失败"
        raise HTTPException(status_code=500, detail=f"更新教材失败: {error_msg}")


@app.delete("/textbooks/{textbook_id}")
async def delete_textbook(textbook_id: str):
    """
    删除教材
    
    Args:
        textbook_id: 教材 ID
        
    Returns:
        删除结果
    """
    try:
        success = db.delete_textbook(textbook_id)
        if not success:
            raise HTTPException(status_code=404, detail="教材不存在")
        
        return JSONResponse(content={
            "message": "教材删除成功",
            "textbook_id": textbook_id
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "删除教材失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "删除教材失败"
        raise HTTPException(status_code=500, detail=f"删除教材失败: {error_msg}")


@app.post("/textbooks/{textbook_id}/files")
async def add_file_to_textbook(textbook_id: str, file_info: FileToTextbook):
    """
    将文件添加到教材
    
    Args:
        textbook_id: 教材 ID
        file_info: 文件信息（包含 file_id 和 display_order）
        
    Returns:
        添加结果
    """
    try:
        # 检查教材是否存在
        textbook = db.get_textbook(textbook_id)
        if not textbook:
            raise HTTPException(status_code=404, detail="教材不存在")
        
        # 检查文件是否存在
        file = db.get_file(file_info.file_id)
        if not file:
            raise HTTPException(status_code=404, detail="文件不存在")
        
        success = db.add_file_to_textbook(
            textbook_id=textbook_id,
            file_id=file_info.file_id,
            display_order=file_info.display_order
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="添加文件到教材失败")
        
        return JSONResponse(content={
            "message": "文件添加成功",
            "textbook_id": textbook_id,
            "file_id": file_info.file_id
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "添加文件到教材失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "添加文件到教材失败"
        raise HTTPException(status_code=500, detail=f"添加文件到教材失败: {error_msg}")


@app.delete("/textbooks/{textbook_id}/files/{file_id}")
async def remove_file_from_textbook(textbook_id: str, file_id: str):
    """
    从教材中移除文件
    
    Args:
        textbook_id: 教材 ID
        file_id: 文件 ID
        
    Returns:
        移除结果
    """
    try:
        success = db.remove_file_from_textbook(textbook_id, file_id)
        if not success:
            raise HTTPException(status_code=404, detail="文件不在教材中")
        
        return JSONResponse(content={
            "message": "文件移除成功",
            "textbook_id": textbook_id,
            "file_id": file_id
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "从教材中移除文件失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "从教材中移除文件失败"
        raise HTTPException(status_code=500, detail=f"从教材中移除文件失败: {error_msg}")


@app.get("/files/{file_id}/textbooks")
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


@app.put("/textbooks/{textbook_id}/files/{file_id}/order")
async def update_file_order(
    textbook_id: str, 
    file_id: str, 
    order_update: FileOrderUpdate
):
    """
    更新文件在教材中的显示顺序
    
    Args:
        textbook_id: 教材 ID
        file_id: 文件 ID
        display_order: 新的显示顺序
        
    Returns:
        更新结果
    """
    try:
        success = db.update_file_order_in_textbook(textbook_id, file_id, order_update.display_order)
        if not success:
            raise HTTPException(status_code=404, detail="文件不在教材中")
        
        return JSONResponse(content={
            "message": "文件顺序更新成功",
            "textbook_id": textbook_id,
            "file_id": file_id,
            "display_order": order_update.display_order
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "更新文件顺序失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "更新文件顺序失败"
        raise HTTPException(status_code=500, detail=f"更新文件顺序失败: {error_msg}")


# ========== 任务相关 API ==========

@app.get("/tasks/{task_id}/progress")
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


@app.get("/tasks/{task_id}")
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


@app.get("/tasks")
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


@app.post("/tasks")
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


@app.put("/tasks/{task_id}")
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


# ========== 应用启动事件：恢复未完成的任务 ==========

@app.on_event("startup")
async def startup_event():
    """
    应用启动时恢复未完成的任务
    """
    try:
        # 获取所有未完成的任务（PENDING 或 PROCESSING 状态）
        pending_tasks = db.get_all_tasks(status="PENDING")
        processing_tasks = db.get_all_tasks(status="PROCESSING")
        
        all_unfinished_tasks = pending_tasks + processing_tasks
        
        if all_unfinished_tasks:
            print(f"发现 {len(all_unfinished_tasks)} 个未完成的任务，开始恢复...")
            
            for task_info in all_unfinished_tasks:
                task_id = task_info.get("task_id")
                task_status = task_info.get("status")
                
                # 如果是 PROCESSING 状态，重置为 PENDING（因为可能是重启前未完成的任务）
                if task_status == "PROCESSING":
                    db.update_task_status(task_id, "PENDING", "项目重启，任务待恢复")
                    print(f"任务 {task_id} 状态重置为 PENDING")
                
                # 如果是 PAUSED 状态，保持暂停状态，不自动恢复（需要手动恢复）
                if task_status == "PAUSED":
                    print(f"任务 {task_id} 处于暂停状态，不会自动恢复")
                    continue
                
                # 启动任务恢复
                asyncio.create_task(process_full_textbook_task(task_id))
                print(f"任务 {task_id} 已恢复执行")
        else:
            print("没有未完成的任务需要恢复")
    except Exception as e:
        print(f"恢复任务时发生错误: {e}")


# ========== 全书自动化出题 ==========

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
                        questions_data = await generate_questions_for_chunk(chunk)
                        
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


class TextbookGenerationRequest(BaseModel):
    """
    教材生成题目请求模型
    """
    textbook_id: str = Field(..., description="教材 ID")


@app.post("/generate-book")
async def generate_book_endpoint(
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


@app.post("/tasks/{task_id}/pause")
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


@app.post("/tasks/{task_id}/resume")
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


@app.post("/tasks/{task_id}/cancel")
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

