"""
教材相关的 Pydantic 数据模型
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class TextbookCreate(BaseModel):
    """创建教材请求模型"""
    name: str = Field(..., description="教材名称")
    description: Optional[str] = Field(default=None, description="教材描述")


class TextbookUpdate(BaseModel):
    """更新教材请求模型"""
    name: Optional[str] = Field(default=None, description="教材名称")
    description: Optional[str] = Field(default=None, description="教材描述")


class TextbookGenerationRequest(BaseModel):
    """教材生成题目请求模型"""
    textbook_id: str = Field(..., description="教材 ID")
    mode: str = Field(default="课后习题", description="出题模式：课后习题 或 提高习题")
    task_settings: Optional[Dict[str, Any]] = Field(
        default=None,
        description="任务设定（JSON对象），包含难度、题型偏好等配置"
    )

