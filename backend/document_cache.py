"""
文档缓存模块
使用数据库持久化存储解析后的章节内容，以便后续检索和使用
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from database import db


class DocumentCache:
    """文档缓存管理器（基于数据库）"""
    
    def store(self, file_id: str, chunks: List[Dict[str, Any]], metadata: Dict[str, Any]):
        """
        存储解析后的文档内容到数据库
        
        Args:
            file_id: 文件 ID
            chunks: 解析后的 chunks 列表
            metadata: 文档元数据（文件名、目录结构、统计信息等）
        """
        # 从 metadata 中提取文件信息
        filename = metadata.get("filename", "")
        file_size = metadata.get("file_size", 0)
        file_path = metadata.get("file_path", "")
        
        # 提取文件格式（从 file_path 或 filename）
        file_format = ""
        if file_path:
            from pathlib import Path
            file_format = Path(file_path).suffix
        elif filename:
            from pathlib import Path
            file_format = Path(filename).suffix
        
        # 获取上传时间（从 metadata 或使用当前时间）
        upload_time = metadata.get("upload_time", datetime.now().isoformat())
        
        # 存储到数据库
        db.store_complete_document(
            file_id=file_id,
            filename=filename,
            file_size=file_size,
            file_format=file_format,
            file_path=file_path,
            upload_time=upload_time,
            chunks=chunks,
            metadata=metadata
        )
    
    def get(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文档内容（从数据库）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            包含 chunks 和 metadata 的字典，如果不存在则返回 None
        """
        chunks = self.get_chunks(file_id)
        metadata = self.get_metadata(file_id)
        
        if chunks is None or metadata is None:
            return None
        
        return {
            "chunks": chunks,
            "metadata": metadata,
        }
    
    def get_chunks(self, file_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取文档的 chunks（从数据库）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            chunks 列表，如果不存在则返回 None
        """
        return db.get_chunks(file_id)
    
    def get_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文档元数据（从数据库）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            元数据字典，如果不存在则返回 None
        """
        return db.get_metadata(file_id)
    
    def remove(self, file_id: str) -> bool:
        """
        删除文档缓存（从数据库）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否成功删除
        """
        return db.delete_file(file_id)
    
    def exists(self, file_id: str) -> bool:
        """
        检查文档是否存在（在数据库中）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否存在
        """
        return db.file_exists(file_id)
    
    def list_all(self) -> List[str]:
        """
        获取所有已缓存的文件 ID 列表（从数据库）
        
        Returns:
            文件 ID 列表
        """
        files = db.get_all_files()
        return [file["file_id"] for file in files]
    
    def clear(self):
        """
        清空所有缓存（从数据库）
        注意：此操作会删除所有文件记录，请谨慎使用
        """
        all_files = self.list_all()
        for file_id in all_files:
            db.delete_file(file_id)


# 全局缓存实例（基于数据库）
document_cache = DocumentCache()

