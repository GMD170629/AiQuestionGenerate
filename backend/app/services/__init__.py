"""
业务逻辑服务模块
统一导出所有服务，方便导入
"""

# AI 生成服务
from app.services.ai_service import (
    OpenRouterClient,
    generate_questions,
    generate_questions_for_chunk,
    select_random_chunks,
    build_context_from_chunks,
    get_chapter_name_from_chunks,
)

# Markdown 解析服务
from app.services.markdown_service import (
    MarkdownProcessor,
    extract_toc,
    calculate_statistics,
    extract_and_store_knowledge_nodes,
    process_markdown_file,
    build_textbook_knowledge_dependencies,
)

# 文件处理服务
from app.services.file_service import (
    process_single_file,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
)

# 任务处理服务
from app.services.task_service import (
    process_full_textbook_task,
)

__all__ = [
    # AI 服务
    "OpenRouterClient",
    "generate_questions",
    "generate_questions_for_chunk",
    "select_random_chunks",
    "build_context_from_chunks",
    "get_chapter_name_from_chunks",
    # Markdown 服务
    "MarkdownProcessor",
    "extract_toc",
    "calculate_statistics",
    "extract_and_store_knowledge_nodes",
    "process_markdown_file",
    "build_textbook_knowledge_dependencies",
    # 文件服务
    "process_single_file",
    "ALLOWED_EXTENSIONS",
    "MAX_FILE_SIZE",
    # 任务服务
    "process_full_textbook_task",
]
