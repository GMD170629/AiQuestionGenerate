"""
API v1 版本路由
统一导出所有 v1 版本的路由
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    config,
    files,
    questions,
    textbooks,
    tasks,
    question_library,
    knowledge_graph,
    knowledge_extraction,
    test_generation,
    prompts,
    dev,
)

# 创建 API v1 路由器
# 注意：如果不需要版本前缀，可以设置为空字符串 ""
# 当前设置为空，保持与原有路由路径一致
api_router = APIRouter()

# 注册所有端点路由
api_router.include_router(config.router)
api_router.include_router(files.router)
api_router.include_router(questions.router)
api_router.include_router(question_library.router)
api_router.include_router(textbooks.router)
api_router.include_router(tasks.router)
api_router.include_router(knowledge_graph.router)
api_router.include_router(knowledge_extraction.router)
api_router.include_router(test_generation.router)
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])

# 开发模式路由（仅在开发模式下注册）
from app.core.config import settings
if settings.dev_mode:
    api_router.include_router(dev.router)

__all__ = ["api_router"]
