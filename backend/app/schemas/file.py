"""
文件相关的 Pydantic 数据模型
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """文件信息模型"""
    file_id: str
    filename: str
    file_size: int
    upload_time: str
    file_path: str
    textbooks: Optional[List[Dict[str, Any]]] = Field(
        default=[],
        description="文件所属的教材列表"
    )


class ChunkInfo(BaseModel):
    """切片信息模型"""
    content: str
    metadata: dict


class FileToTextbook(BaseModel):
    """添加文件到教材请求模型"""
    file_id: str = Field(..., description="文件 ID")
    display_order: int = Field(default=0, description="显示顺序")


class FileOrderUpdate(BaseModel):
    """更新文件顺序请求模型"""
    display_order: int = Field(..., ge=0, description="新的显示顺序")

