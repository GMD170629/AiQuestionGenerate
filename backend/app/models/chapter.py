"""
章节相关的数据模型
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Chapter(BaseModel):
    """
    教材章节模型
    用于表示教材的目录树结构
    """
    
    chapter_id: Optional[str] = Field(
        default=None,
        description="章节 ID（数据库生成）"
    )
    
    file_id: str = Field(
        ...,
        description="所属文件 ID"
    )
    
    name: str = Field(
        ...,
        min_length=1,
        description="章节名称"
    )
    
    level: int = Field(
        ...,
        ge=1,
        le=10,
        description="章节层级（1-10）"
    )
    
    section_type: Optional[str] = Field(
        default=None,
        description="章节类型（chapter/section/numbered/special等）"
    )
    
    parent_id: Optional[str] = Field(
        default=None,
        description="父章节 ID（用于构建层级关系）"
    )
    
    display_order: int = Field(
        default=0,
        ge=0,
        description="显示顺序"
    )
    
    chunk_ids: List[int] = Field(
        default_factory=list,
        description="关联的切片 ID 列表"
    )
    
    created_at: Optional[str] = Field(
        default=None,
        description="创建时间（ISO 格式）"
    )


class ChapterTree(BaseModel):
    """
    章节树模型
    用于表示完整的章节层级结构
    """
    
    chapter: Chapter = Field(
        ...,
        description="章节信息"
    )
    
    children: List['ChapterTree'] = Field(
        default_factory=list,
        description="子章节列表"
    )

