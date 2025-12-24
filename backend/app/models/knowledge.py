"""
知识点相关的数据模型
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class KnowledgeNode(BaseModel):
    """
    知识点节点模型
    用于存储从文档切片中提取的知识点语义信息
    
    关系结构：
    - dependencies: 通过 knowledge_dependencies 表存储横向依赖关系
    """
    
    node_id: Optional[str] = Field(
        default=None,
        description="节点 ID（数据库生成）"
    )
    
    chunk_id: int = Field(
        ...,
        description="关联的切片 ID"
    )
    
    file_id: str = Field(
        ...,
        description="所属文件 ID"
    )
    
    core_concept: str = Field(
        ...,
        min_length=1,
        description="核心概念（该切片的主要知识点）"
    )
    
    prerequisites: List[str] = Field(
        default_factory=list,
        description="前置依赖知识点列表（学习该概念前需要掌握的知识点，已废弃，使用 knowledge_dependencies 表）"
    )
    
    confusion_points: List[str] = Field(
        default_factory=list,
        description="学生易错点列表（学习该概念时容易混淆或出错的地方）"
    )
    
    bloom_level: int = Field(
        ...,
        ge=1,
        le=6,
        description="Bloom 认知层级（1-6级）：1-记忆，2-理解，3-应用，4-分析，5-评价，6-创造"
    )
    
    application_scenarios: Optional[List[str]] = Field(
        default=None,
        description="应用场景列表（可选，该知识点在实际中的应用场景）"
    )
    
    created_at: Optional[str] = Field(
        default=None,
        description="创建时间（ISO 格式）"
    )

