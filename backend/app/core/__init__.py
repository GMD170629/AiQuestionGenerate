"""
核心配置和基础功能模块
统一导出核心模块
"""

# 数据库
from app.core.db import Database, db

# 缓存
from app.core.cache import DocumentCache, document_cache

# 任务管理
from app.core.task_manager import TaskManager, task_manager

# 任务进度
from app.core.task_progress import TaskProgressManager, task_progress_manager

# 数据库迁移
from app.core.migrations import migrate_knowledge_nodes_schema

# 知识提取进度
from app.core.knowledge_extraction_progress import KnowledgeExtractionProgressManager

__all__ = [
    # 数据库
    "Database",
    "db",
    # 缓存
    "DocumentCache",
    "document_cache",
    # 任务管理
    "TaskManager",
    "task_manager",
    # 任务进度
    "TaskProgressManager",
    "task_progress_manager",
    # 数据库迁移
    "migrate_knowledge_nodes_schema",
    # 知识提取进度
    "KnowledgeExtractionProgressManager",
]
