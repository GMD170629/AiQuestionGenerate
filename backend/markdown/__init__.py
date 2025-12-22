"""
Markdown 处理模块
提供 Markdown 文件解析、切分、知识提取等功能
"""

# 从各子模块导出主要接口
from .processor import MarkdownProcessor, process_markdown_file
from .toc_extractor import TOCNode, SemanticSplitter
from .text_splitters import CodeBlockAwareSplitter
from .chapter_extractor import (
    extract_toc,
    calculate_statistics,
    extract_chapters_from_chunks,
    build_chapters_from_toc_tree,
)

# 知识提取相关的函数需要从 knowledge_extractor 导入
# 但由于知识提取模块代码很长，我们在 md_processor.py 兼容层中处理

__all__ = [
    "MarkdownProcessor",
    "process_markdown_file",
    "TOCNode",
    "SemanticSplitter",
    "CodeBlockAwareSplitter",
    "extract_toc",
    "calculate_statistics",
    "extract_chapters_from_chunks",
    "build_chapters_from_toc_tree",
]

