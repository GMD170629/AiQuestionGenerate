"""
Pydantic 模式定义模块
统一导出所有 schemas，方便导入
"""

# 文件相关 schemas
from app.schemas.file import (
    FileInfo,
    ChunkInfo,
    FileToTextbook,
    FileOrderUpdate,
)

# 教材相关 schemas
from app.schemas.textbook import (
    TextbookCreate,
    TextbookUpdate,
    TextbookGenerationRequest,
)

# 配置相关 schemas
from app.schemas.config import (
    AIConfigUpdate,
)

__all__ = [
    # 文件相关
    "FileInfo",
    "ChunkInfo",
    "FileToTextbook",
    "FileOrderUpdate",
    # 教材相关
    "TextbookCreate",
    "TextbookUpdate",
    "TextbookGenerationRequest",
    # 配置相关
    "AIConfigUpdate",
]
