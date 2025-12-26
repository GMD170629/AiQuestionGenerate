"""
任务相关的数据模型
"""

from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


class Task(BaseModel):
    """
    生成任务模型
    用于管理教材题目生成任务的状态和进度
    """
    
    task_id: str = Field(
        ...,
        description="任务 ID"
    )
    
    textbook_id: str = Field(
        ...,
        description="教材 ID"
    )
    
    status: Literal["PLANNING", "PENDING", "PROCESSING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"] = Field(
        default="PENDING",
        description="任务状态：PLANNING（规划中）、PENDING（等待中）、PROCESSING（执行中）、PAUSED（已暂停）、COMPLETED（已完成）、FAILED（失败）、CANCELLED（已取消）"
    )
    
    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="任务进度（0.0-1.0 之间的浮点数）"
    )
    
    current_file: Optional[str] = Field(
        default=None,
        description="当前正在处理的文件"
    )
    
    total_files: int = Field(
        default=0,
        ge=0,
        description="总文件数"
    )
    
    created_at: Optional[str] = Field(
        default=None,
        description="创建时间（ISO 格式）"
    )
    
    updated_at: Optional[str] = Field(
        default=None,
        description="更新时间（ISO 格式）"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="错误消息（仅在失败时使用）"
    )
    
    textbook_name: Optional[str] = Field(
        default=None,
        description="教材名称（从关联表查询，可选）"
    )
    
    mode: Optional[str] = Field(
        default=None,
        description="出题模式：课后习题 或 提高习题"
    )
    
    task_settings: Optional[Dict[str, Any]] = Field(
        default=None,
        description="任务设定（JSON对象）"
    )
    
    generation_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="生成计划（JSON对象），包含规划结果"
    )


class TaskCreate(BaseModel):
    """
    创建任务请求模型
    """
    
    textbook_id: str = Field(
        ...,
        description="教材 ID"
    )
    
    total_files: int = Field(
        default=0,
        ge=0,
        description="总文件数"
    )


class TaskUpdate(BaseModel):
    """
    更新任务请求模型
    """
    
    status: Optional[Literal["PLANNING", "PENDING", "PROCESSING", "PAUSED", "COMPLETED", "FAILED", "CANCELLED"]] = Field(
        default=None,
        description="任务状态"
    )
    
    progress: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="任务进度（0.0-1.0 之间的浮点数）"
    )
    
    current_file: Optional[str] = Field(
        default=None,
        description="当前正在处理的文件"
    )
    
    total_files: Optional[int] = Field(
        default=None,
        ge=0,
        description="总文件数"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="错误消息"
    )

