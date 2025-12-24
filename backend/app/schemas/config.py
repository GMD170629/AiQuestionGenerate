"""
配置相关的 Pydantic 数据模型
"""

from pydantic import BaseModel, Field


class AIConfigUpdate(BaseModel):
    """AI 配置更新模型"""
    api_endpoint: str = Field(..., description="API端点URL")
    api_key: str = Field(..., description="API密钥")
    model: str = Field(..., description="模型名称")

