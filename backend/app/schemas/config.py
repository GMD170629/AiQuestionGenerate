"""
配置相关的 Pydantic 数据模型
"""

from typing import Optional
from pydantic import BaseModel, Field


class AIConfigUpdate(BaseModel):
    """AI 配置更新模型"""
    api_endpoint: str = Field(..., description="API端点URL")
    api_key: str = Field(..., description="API密钥")
    model: str = Field(..., description="模型名称")
    max_tokens: Optional[int] = Field(None, description="最大输出 tokens 数量限制，为空表示使用系统默认值", ge=100, le=128000)

