"""
API 请求和响应的数据模型定义
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
    textbooks: Optional[List[Dict[str, Any]]] = Field(default=[], description="文件所属的教材列表")


class ChunkInfo(BaseModel):
    """切片信息模型"""
    content: str
    metadata: dict


class AIConfigUpdate(BaseModel):
    """AI 配置更新模型"""
    api_endpoint: str = Field(..., description="API端点URL")
    api_key: str = Field(..., description="API密钥")
    model: str = Field(..., description="模型名称")


class TextbookCreate(BaseModel):
    """创建教材请求模型"""
    name: str = Field(..., description="教材名称")
    description: Optional[str] = Field(default=None, description="教材描述")


class TextbookUpdate(BaseModel):
    """更新教材请求模型"""
    name: Optional[str] = Field(default=None, description="教材名称")
    description: Optional[str] = Field(default=None, description="教材描述")


class FileToTextbook(BaseModel):
    """添加文件到教材请求模型"""
    file_id: str = Field(..., description="文件 ID")
    display_order: int = Field(default=0, description="显示顺序")


class FileOrderUpdate(BaseModel):
    """更新文件顺序请求模型"""
    display_order: int = Field(..., ge=0, description="新的显示顺序")


class TextbookGenerationRequest(BaseModel):
    """教材生成题目请求模型"""
    textbook_id: str = Field(..., description="教材 ID")

