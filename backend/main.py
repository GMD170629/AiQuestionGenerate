"""
FastAPI 应用主入口（向后兼容）
从新的 app.main 导入应用实例
"""

# 从新的应用入口导入应用实例
from app.main import app

__all__ = ["app"]
