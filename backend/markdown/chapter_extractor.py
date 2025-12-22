"""
章节提取工具模块
提供从 chunks 中提取目录、章节结构等工具函数
"""

import re
from typing import List, Dict, Any

from .toc_extractor import TOCNode


def extract_toc(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    从解析后的 chunks 中提取目录结构
    
    Args:
        chunks: 解析后的 chunks 列表
        
    Returns:
        目录结构列表，格式：
        [
            {"level": 1, "title": "一级标题", "chunk_count": 3, "section_type": "chapter"},
            {"level": 2, "title": "二级标题", "chunk_count": 2, "section_type": "section"},
            ...
        ]
    """
    toc = []
    seen_titles = {}  # 用于去重和统计
    
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        
        # 获取标题和层级
        title = None
        level = 0
        section_type = metadata.get("section_type")
        
        # 优先使用语义分割识别的标题
        if metadata.get("section_title"):
            title = metadata["section_title"]
            # 根据 section_type 判断层级
            if section_type == "chapter":
                level = 1
            elif section_type in ["section", "numbered"]:
                level = 2
            elif section_type == "numbered_single":
                level = 1
            elif section_type:
                # 特殊段落类型，层级设为 0
                level = 0
        elif metadata.get("Header 1"):
            title = metadata["Header 1"]
            level = 1
        elif metadata.get("Header 2"):
            title = metadata["Header 2"]
            level = 2
        elif metadata.get("Header 3"):
            title = metadata["Header 3"]
            level = 3
        
        if title:
            # 使用层级+标题+类型作为唯一标识
            key = f"{level}:{title}:{section_type or ''}"
            if key not in seen_titles:
                seen_titles[key] = {
                    "level": level,
                    "title": title,
                    "chunk_count": 1,
                    "section_type": section_type,
                }
                toc.append(seen_titles[key])
            else:
                seen_titles[key]["chunk_count"] += 1
    
    return toc


def calculate_statistics(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    计算文档统计信息
    
    Args:
        chunks: 解析后的 chunks 列表
        
    Returns:
        统计信息字典
    """
    total_chunks = len(chunks)
    total_chars = sum(len(chunk.get("content", "")) for chunk in chunks)
    total_words = sum(len(chunk.get("content", "").split()) for chunk in chunks)
    
    # 计算中文字数（粗略估计）
    chinese_chars = sum(
        sum(1 for char in chunk.get("content", "") if '\u4e00' <= char <= '\u9fff')
        for chunk in chunks
    )
    
    # 统计章节数
    chapters = set()
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        chapter_name = metadata.get("chapter_name", "")
        if chapter_name and chapter_name != "未命名章节":
            chapters.add(chapter_name)
    
    return {
        "total_chunks": total_chunks,
        "total_chars": total_chars,
        "total_words": total_words,
        "chinese_chars": chinese_chars,
        "chapter_count": len(chapters),
        "avg_chunk_size": round(total_chars / total_chunks, 2) if total_chunks > 0 else 0,
    }


def extract_chapters_from_chunks(chunks: List[Dict[str, Any]], toc_tree: List[TOCNode] = None) -> List[Dict[str, Any]]:
    """
    从 chunks 和目录树中提取章节结构
    
    Args:
        chunks: 解析后的 chunks 列表
        toc_tree: 目录树（可选，如果不提供则从 chunks 中提取）
        
    Returns:
        章节列表，每个章节包含：
        - name: 章节名称
        - level: 层级
        - section_type: 章节类型
        - parent_id: 父章节 ID（可选）
        - display_order: 显示顺序
        - chunk_ids: 关联的切片 ID 列表（基于 chunk_index）
    """
    # 构建章节字典（以章节名称为键，用于去重和构建层级关系）
    chapter_dict = {}  # key: (level, name), value: chapter_data
    chapter_list = []  # 扁平化的章节列表
    
    # 从 chunks 中提取章节信息
    for chunk_idx, chunk in enumerate(chunks):
        metadata = chunk.get("metadata", {})
        
        # 获取章节名称和层级
        section_title = metadata.get("section_title")
        section_type = metadata.get("section_type")
        
        # 如果没有 section_title，尝试从 Header 中获取
        if not section_title:
            if metadata.get("Header 1"):
                section_title = metadata["Header 1"]
                section_type = section_type or "chapter"
            elif metadata.get("Header 2"):
                section_title = metadata["Header 2"]
                section_type = section_type or "section"
            elif metadata.get("Header 3"):
                section_title = metadata["Header 3"]
                section_type = section_type or "section"
        
        if not section_title:
            continue
        
        # 计算层级
        level = 1
        if section_type == "chapter":
            level = 1
        elif section_type == "section":
            level = 2
        elif section_type == "numbered":
            # 从 section_title 中提取层级（如 "3.2.1" -> level 3）
            number_part = section_title.split()[0] if section_title.split() else section_title
            if re.match(r'^\d+\.\d+(?:\.\d+)*', number_part):
                dot_count = number_part.count('.')
                level = dot_count + 1
        else:
            # 从 Header 中获取层级
            if metadata.get("Header 1"):
                level = 1
            elif metadata.get("Header 2"):
                level = 2
            elif metadata.get("Header 3"):
                level = 3
        
        # 使用 (level, name) 作为唯一标识
        chapter_key = (level, section_title)
        
        if chapter_key not in chapter_dict:
            # 创建新章节
            chapter_data = {
                "name": section_title,
                "level": level,
                "section_type": section_type,
                "parent_id": None,  # 稍后设置
                "display_order": len(chapter_list),
                "chunk_ids": []
            }
            chapter_dict[chapter_key] = chapter_data
            chapter_list.append(chapter_data)
        
        # 添加 chunk_id（使用 chunk_index + 1，因为 chunk_id 是自增的）
        # 注意：这里我们使用 chunk_index 作为临时 ID，实际存储时会使用真实的 chunk_id
        chunk_index = chunk_idx  # chunks 列表中的索引
        if chunk_index not in chapter_dict[chapter_key]["chunk_ids"]:
            chapter_dict[chapter_key]["chunk_ids"].append(chunk_index)
    
    # 构建层级关系（根据章节名称和层级推断父子关系）
    # 对于每个章节，查找可能的父章节
    for i, chapter in enumerate(chapter_list):
        if chapter["level"] == 1:
            chapter["parent_id"] = None
        else:
            # 查找最近的、层级更小的章节作为父章节
            parent = None
            for j in range(i - 1, -1, -1):
                candidate = chapter_list[j]
                if candidate["level"] < chapter["level"]:
                    parent = candidate
                    break
            # 如果找到了父章节，设置 parent_id（这里先用名称，实际存储时会转换为 ID）
            if parent:
                chapter["parent_name"] = parent["name"]  # 临时存储父章节名称
                chapter["parent_level"] = parent["level"]
    
    return chapter_list


def build_chapters_from_toc_tree(toc_tree: List[TOCNode], chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    从目录树构建章节结构（更准确的方法）
    
    Args:
        toc_tree: 目录树节点列表
        chunks: 解析后的 chunks 列表
        
    Returns:
        章节列表
    """
    chapter_list = []
    node_to_chapter = {}  # 用于存储节点到章节的映射
    
    def process_node(node: TOCNode, parent_chapter: Dict[str, Any] = None, display_order: int = 0):
        """递归处理目录树节点"""
        # 创建章节数据
        chapter_data = {
            "name": node.title,
            "level": node.level,
            "section_type": node.section_type,
            "parent_id": None,  # 稍后设置
            "parent_name": parent_chapter["name"] if parent_chapter else None,  # 临时存储父章节名称
            "parent_level": parent_chapter["level"] if parent_chapter else None,  # 临时存储父章节层级
            "display_order": display_order,
            "chunk_ids": []
        }
        
        # 查找关联的 chunks（通过比较 section_title 或 Header 信息）
        for chunk_idx, chunk in enumerate(chunks):
            metadata = chunk.get("metadata", {})
            # 检查 chunk 是否属于当前章节
            chunk_title = metadata.get("section_title") or metadata.get("Header 1") or metadata.get("Header 2") or metadata.get("Header 3")
            if chunk_title == node.title:
                chapter_data["chunk_ids"].append(chunk_idx)
        
        chapter_list.append(chapter_data)
        node_to_chapter[node] = chapter_data
        
        # 处理子节点
        for child_idx, child_node in enumerate(node.children):
            process_node(child_node, chapter_data, child_idx)
    
    # 处理所有根节点
    for root_idx, root_node in enumerate(toc_tree):
        process_node(root_node, None, root_idx)
    
    return chapter_list

