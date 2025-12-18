"""
开发模式相关路由
仅在开发模式下可用，用于快速清空系统数据
"""

import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from database import db
from document_cache import document_cache
from graph_manager import knowledge_graph

router = APIRouter(prefix="/dev", tags=["开发模式"])

# 检查是否为开发模式
DEV_MODE = os.getenv("DEV_MODE", "false").lower() in ("true", "1", "yes")


def check_dev_mode():
    """检查是否为开发模式，如果不是则抛出异常"""
    if not DEV_MODE:
        raise HTTPException(
            status_code=403,
            detail="此功能仅在开发模式下可用。请设置环境变量 DEV_MODE=true 启用开发模式。"
        )


@router.get("/status")
async def get_dev_status():
    """
    获取开发模式状态
    """
    return JSONResponse(content={
        "dev_mode": DEV_MODE,
        "message": "开发模式已启用" if DEV_MODE else "开发模式未启用"
    })


@router.post("/clear-all")
async def clear_all_data():
    """
    清空所有系统数据（仅在开发模式下可用）
    
    清空内容包括：
    - 所有上传的文件（uploads目录）
    - 所有教材（textbooks）
    - 所有题目（questions）
    - 所有文档切片（chunks）
    - 所有章节（chapters）
    - 所有知识点节点（knowledge_nodes）
    - 所有任务（tasks）
    - 所有文件元数据（file_metadata）
    
    注意：不会清空 AI 配置（ai_config）
    """
    check_dev_mode()
    
    try:
        stats = {
            "files_deleted": 0,
            "textbooks_deleted": 0,
            "questions_deleted": 0,
            "chunks_deleted": 0,
            "chapters_deleted": 0,
            "knowledge_nodes_deleted": 0,
            "tasks_deleted": 0,
            "file_metadata_deleted": 0,
        }
        
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 删除所有任务
            cursor.execute("SELECT COUNT(*) as count FROM tasks")
            stats["tasks_deleted"] = cursor.fetchone()["count"]
            cursor.execute("DELETE FROM tasks")
            
            # 2. 删除所有知识点节点
            cursor.execute("SELECT COUNT(*) as count FROM knowledge_nodes")
            stats["knowledge_nodes_deleted"] = cursor.fetchone()["count"]
            cursor.execute("DELETE FROM knowledge_nodes")
            
            # 3. 删除所有章节-切片关联
            cursor.execute("DELETE FROM chapter_chunks")
            
            # 4. 删除所有章节
            cursor.execute("SELECT COUNT(*) as count FROM chapters")
            stats["chapters_deleted"] = cursor.fetchone()["count"]
            cursor.execute("DELETE FROM chapters")
            
            # 5. 删除所有题目
            cursor.execute("SELECT COUNT(*) as count FROM questions")
            stats["questions_deleted"] = cursor.fetchone()["count"]
            cursor.execute("DELETE FROM questions")
            
            # 6. 删除所有文件-教材关联
            cursor.execute("DELETE FROM textbook_files")
            
            # 7. 删除所有教材
            cursor.execute("SELECT COUNT(*) as count FROM textbooks")
            stats["textbooks_deleted"] = cursor.fetchone()["count"]
            cursor.execute("DELETE FROM textbooks")
            
            # 8. 删除所有文档切片
            cursor.execute("SELECT COUNT(*) as count FROM chunks")
            stats["chunks_deleted"] = cursor.fetchone()["count"]
            cursor.execute("DELETE FROM chunks")
            
            # 9. 删除所有文件元数据
            cursor.execute("SELECT COUNT(*) as count FROM file_metadata")
            stats["file_metadata_deleted"] = cursor.fetchone()["count"]
            cursor.execute("DELETE FROM file_metadata")
            
            # 10. 获取所有文件信息（用于删除文件）
            cursor.execute("SELECT file_id, file_path FROM files")
            files = cursor.fetchall()
            stats["files_deleted"] = len(files)
            
            # 11. 删除所有文件记录
            cursor.execute("DELETE FROM files")
            
            conn.commit()
        
        # 12. 删除 uploads 目录中的所有文件
        upload_dir = Path("uploads")
        if upload_dir.exists():
            for file_path in upload_dir.iterdir():
                if file_path.is_file():
                    try:
                        file_path.unlink()
                    except Exception as e:
                        print(f"删除文件失败 {file_path}: {e}")
        
        # 13. 清空知识图谱（内存中的图）
        try:
            knowledge_graph.graph.clear()
            knowledge_graph.concept_to_node_id.clear()
            knowledge_graph.node_id_to_concept.clear()
            knowledge_graph.concept_metadata.clear()
            knowledge_graph._is_loaded = False
        except Exception as e:
            print(f"清空知识图谱失败: {e}")
        
        return JSONResponse(content={
            "message": "所有数据已清空",
            "stats": stats,
            "note": "AI 配置（ai_config）未被清空"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "清空数据失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "清空数据失败"
        raise HTTPException(status_code=500, detail=f"清空数据失败: {error_msg}")

