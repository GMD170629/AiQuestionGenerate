"""
题目库查询相关路由
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from database import db

router = APIRouter(prefix="/questions", tags=["题目库"])


@router.get("")
async def get_all_questions(
    file_id: Optional[str] = None,
    question_type: Optional[str] = None,
    textbook_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0
):
    """
    获取所有题目列表（支持按文件、题型和教材筛选）
    
    Args:
        file_id: 文件 ID（可选，如果提供则只返回该文件的题目）
        question_type: 题型（可选，如果提供则只返回该题型的题目）
        textbook_id: 教材 ID（可选，如果提供则只返回该教材的题目）
        limit: 限制返回数量（可选）
        offset: 偏移量（用于分页）
    
    Returns:
        题目列表和总数
    """
    try:
        questions = db.get_all_questions(
            file_id=file_id,
            question_type=question_type,
            textbook_id=textbook_id,
            limit=limit,
            offset=offset
        )
        
        total = db.get_question_count(file_id=file_id, question_type=question_type, textbook_id=textbook_id)
        
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


@router.get("/statistics")
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

