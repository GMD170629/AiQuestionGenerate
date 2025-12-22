"""
教材管理相关路由
"""

import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from database import db
from schemas import (
    TextbookCreate,
    TextbookUpdate,
    FileToTextbook,
    FileOrderUpdate
)
from md_processor import build_textbook_knowledge_dependencies

router = APIRouter(prefix="/textbooks", tags=["教材管理"])


@router.post("")
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


@router.get("")
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


@router.get("/{textbook_id}")
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


@router.put("/{textbook_id}")
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


@router.delete("/{textbook_id}")
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


@router.post("/{textbook_id}/files")
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


@router.delete("/{textbook_id}/files/{file_id}")
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


@router.put("/{textbook_id}/files/{file_id}/order")
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


@router.post("/{textbook_id}/build-dependencies")
async def build_knowledge_dependencies(textbook_id: str):
    """
    为教材下的所有知识点构建依赖关系
    
    使用 LLM 分析教材下所有知识点之间的依赖关系（prerequisites 和 dependents），
    并将结果存储到数据库的 prerequisites_json 字段中。
    
    Args:
        textbook_id: 教材 ID
        
    Returns:
        构建结果，包含：
        - success: 是否成功
        - total_concepts: 知识点总数
        - dependencies_built: 构建的依赖关系数量
        - message: 结果消息
    """
    try:
        # 检查教材是否存在
        textbook = db.get_textbook(textbook_id)
        if not textbook:
            raise HTTPException(status_code=404, detail="教材不存在")
        
        # 调用依赖关系构建函数
        result = await build_textbook_knowledge_dependencies(textbook_id)
        
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "依赖关系构建失败")
            )
        
        return JSONResponse(content={
            "message": result.get("message", "依赖关系构建成功"),
            "textbook_id": textbook_id,
            "total_concepts": result.get("total_concepts", 0),
            "dependencies_built": result.get("dependencies_built", 0)
        })
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "依赖关系构建失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "依赖关系构建失败"
        raise HTTPException(status_code=500, detail=f"依赖关系构建失败: {error_msg}")


