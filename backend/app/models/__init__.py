"""
数据模型模块
统一导出所有模型，方便导入
"""

# 题目相关模型
from app.models.question import (
    TestCase,
    Question,
    QuestionList,
    QuestionGenerationRequest,
)

# 任务相关模型
from app.models.task import (
    Task,
    TaskCreate,
    TaskUpdate,
)

# 章节相关模型
from app.models.chapter import (
    Chapter,
    ChapterTree,
)

# 知识点相关模型
from app.models.knowledge import (
    KnowledgeNode,
)

# 生成计划相关模型
from app.models.generation_plan import (
    ChunkGenerationPlan,
    TextbookGenerationPlan,
)

__all__ = [
    # 题目相关
    "TestCase",
    "Question",
    "QuestionList",
    "QuestionGenerationRequest",
    # 任务相关
    "Task",
    "TaskCreate",
    "TaskUpdate",
    # 章节相关
    "Chapter",
    "ChapterTree",
    # 知识点相关
    "KnowledgeNode",
    # 生成计划相关
    "ChunkGenerationPlan",
    "TextbookGenerationPlan",
]
