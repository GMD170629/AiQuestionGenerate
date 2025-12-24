"""
教材相关的 Pydantic 数据模型
"""

from typing import Optional
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

