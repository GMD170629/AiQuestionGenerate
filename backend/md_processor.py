"""
Markdown 解析引擎
功能：读取 Markdown 文件，按标题层级切分，保留代码块，进行文本切片
"""

import re
import json
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

try:
    from langchain.text_splitter import (
        MarkdownHeaderTextSplitter,
        RecursiveCharacterTextSplitter,
    )
except ImportError:
    # 如果 langchain 版本不同，尝试其他导入方式
    try:
        from langchain_text_splitters import (
            MarkdownHeaderTextSplitter,
            RecursiveCharacterTextSplitter,
        )
    except ImportError:
        raise ImportError(
            "无法导入 LangChain 文本分割器。请确保已安装 langchain 或 langchain-text-splitters。"
        )


class CodeBlockAwareSplitter:
    """代码块、图片、公式感知的文本分割器，确保这些内容不被切断"""
    
    def __init__(self, chunk_size: int, chunk_overlap: int, separators: List[str]):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators
    
    def _find_protected_blocks(self, text: str) -> List[Tuple[int, int, str]]:
        """
        找到所有需要保护的内容块的起始和结束位置
        包括：代码块、图片、LaTeX 公式
        
        Returns:
            [(start_pos, end_pos, block_type), ...] 保护块位置列表
            block_type: 'code', 'image', 'formula_block', 'formula_inline'
        """
        protected_blocks = []
        
        # 1. 匹配代码块：```language\n...\n``` 或 ```\n...\n```
        code_pattern = r'```(?:\w+)?\n.*?```'
        for match in re.finditer(code_pattern, text, flags=re.DOTALL):
            protected_blocks.append((match.start(), match.end(), 'code'))
        
        # 2. 匹配图片：![alt](url) 或 ![alt](url "title")
        image_pattern = r'!\[.*?\]\(.*?\)'
        for match in re.finditer(image_pattern, text):
            protected_blocks.append((match.start(), match.end(), 'image'))
        
        # 3. 匹配块级 LaTeX 公式：$$...$$（非贪婪匹配，避免匹配多个公式）
        formula_block_pattern = r'\$\$.*?\$\$'
        for match in re.finditer(formula_block_pattern, text, flags=re.DOTALL):
            protected_blocks.append((match.start(), match.end(), 'formula_block'))
        
        # 4. 匹配行内 LaTeX 公式：$...$（需要确保不是 $$）
        # 使用负向前后查找来避免匹配 $$...$$ 中的 $
        formula_inline_pattern = r'(?<!\$)\$(?!\$).*?(?<!\$)\$(?!\$)'
        for match in re.finditer(formula_inline_pattern, text):
            protected_blocks.append((match.start(), match.end(), 'formula_inline'))
        
        # 按起始位置排序
        protected_blocks.sort(key=lambda x: x[0])
        
        return protected_blocks
    
    def _is_in_protected_block(self, pos: int, protected_blocks: List[Tuple[int, int, str]]) -> bool:
        """检查位置是否在受保护的内容块内"""
        for start, end, _ in protected_blocks:
            if start <= pos < end:
                return True
        return False
    
    def _find_code_blocks(self, text: str) -> List[Tuple[int, int]]:
        """
        找到所有代码块的起始和结束位置（向后兼容）
        
        Returns:
            [(start_pos, end_pos), ...] 代码块位置列表
        """
        protected_blocks = self._find_protected_blocks(text)
        return [(start, end) for start, end, block_type in protected_blocks if block_type == 'code']
    
    def _find_safe_split_point(self, text: str, start: int, max_length: int, protected_blocks: List[Tuple[int, int, str]]) -> int:
        """
        找到安全的分割点（不在受保护的内容块内）
        
        Args:
            text: 文本内容
            start: 起始位置
            max_length: 最大长度
            protected_blocks: 受保护的内容块位置列表
            
        Returns:
            安全的分割位置
        """
        target_pos = start + max_length
        
        # 如果目标位置在受保护的内容块内，找到内容块结束位置
        for start_block, end_block, _ in protected_blocks:
            if start_block <= target_pos < end_block:
                # 返回内容块结束位置之后
                return end_block
        
        # 如果不在受保护的内容块内，尝试在分隔符处分割
        for separator in self.separators:
            if separator:
                # 从目标位置向前查找分隔符
                search_start = max(start, target_pos - self.chunk_overlap)
                pos = text.rfind(separator, search_start, target_pos)
                if pos != -1 and not self._is_in_protected_block(pos, protected_blocks):
                    return pos + len(separator)
        
        # 如果找不到合适的分隔符，返回目标位置
        return target_pos
    
    def split_text(self, text: str) -> List[str]:
        """
        分割文本，保护代码块、图片、公式的完整性
        """
        if len(text) <= self.chunk_size:
            return [text]
        
        # 找到所有受保护的内容块位置（代码块、图片、公式）
        protected_blocks = self._find_protected_blocks(text)
        
        chunks = []
        start = 0
        
        while start < len(text):
            # 计算当前 chunk 的结束位置
            end = self._find_safe_split_point(text, start, self.chunk_size, protected_blocks)
            
            # 确保不超过文本长度
            end = min(end, len(text))
            
            # 提取 chunk
            chunk = text[start:end]
            chunks.append(chunk)
            
            # 计算下一个 chunk 的起始位置（考虑 overlap）
            if end >= len(text):
                break
            
            # 从 overlap 位置开始下一个 chunk
            start = max(start + 1, end - self.chunk_overlap)
            
            # 确保下一个起始位置不在受保护的内容块中间
            while start < len(text) and self._is_in_protected_block(start, protected_blocks):
                # 找到下一个受保护内容块的结束位置
                for start_block, end_block, _ in protected_blocks:
                    if start_block <= start < end_block:
                        start = end_block
                        break
                else:
                    break
        
        return chunks


class TOCNode:
    """目录树节点"""
    def __init__(self, title: str, level: int, line_number: int, section_type: str, section_title: str):
        self.title = title
        self.level = level
        self.line_number = line_number  # 标题所在的行号（从0开始）
        self.section_type = section_type
        self.section_title = section_title
        self.children: List['TOCNode'] = []
        self.end_line_number: int = None  # 该节点内容结束的行号（不包含）
    
    def __repr__(self):
        indent = "  " * (self.level - 1)
        return f"{indent}{self.title} (L{self.level}, lines {self.line_number}-{self.end_line_number})"


class SemanticSplitter:
    """基于语义的文本分割器，先提取目录树，再按目录树切分"""
    
    def __init__(self):
        """初始化语义分割器，定义章节编号和特殊段落的匹配模式"""
        
        # 章节编号模式（按优先级排序）
        # 注意：数字编号的层级需要动态计算（根据点的数量）
        self.chapter_patterns = [
            # 第X章、第一章、第1章等
            (r'^第[一二三四五六七八九十百千万\d]+章\s+.*', 1, 'chapter'),
            # 第X节、第一节等
            (r'^第[一二三四五六七八九十百千万\d]+节\s+.*', 2, 'section'),
            # 数字编号：1.1、1.1.1、1.2.3.4 等（至少两级）
            # 层级根据点的数量动态计算：1个点=level 2, 2个点=level 3, 以此类推
            (r'^\d+\.\d+(?:\.\d+)*\s+.*', None, 'numbered'),  # None 表示需要动态计算
            # 注意：单级数字编号（如 "1."、"2."）不应该作为章节标题，因为容易与列表项混淆
            # 中文数字编号：一、二、三、四等（但需要排除，因为容易与列表项混淆）
            # 字母编号：A.、B.、C. 或 a.、b.、c.（但需要排除，因为容易与列表项混淆）
        ]
        
        # 特殊段落模式（教材常见）
        self.special_section_patterns = [
            # 参考文献相关
            (r'^参考文献\s*$', 'references'),
            (r'^References\s*$', 'references'),
            (r'^参考书目\s*$', 'references'),
            (r'^Bibliography\s*$', 'references'),
            
            # 课后习题相关
            (r'^课后习题\s*$', 'exercises'),
            (r'^课后题目\s*$', 'exercises'),
            (r'^练习题\s*$', 'exercises'),
            (r'^习题\s*$', 'exercises'),
            (r'^Exercises?\s*$', 'exercises'),
            (r'^思考题\s*$', 'exercises'),
            (r'^思考与练习\s*$', 'exercises'),
            (r'^复习题\s*$', 'exercises'),
            (r'^复习思考题\s*$', 'exercises'),
            
            # 答案相关
            (r'^答案\s*$', 'answers'),
            (r'^参考答案\s*$', 'answers'),
            (r'^答案与解析\s*$', 'answers'),
            (r'^Answers?\s*$', 'answers'),
            
            # 附录相关
            (r'^附录\s*[A-Z\d一二三四五六七八九十]*\s*[:：]?\s*.*', 'appendix'),
            (r'^Appendix\s*[A-Z\d]*\s*[:：]?\s*.*', 'appendix'),
            
            # 前言序言相关
            (r'^前言\s*$', 'preface'),
            (r'^序言\s*$', 'preface'),
            (r'^序\s*$', 'preface'),
            (r'^Preface\s*$', 'preface'),
            (r'^Foreword\s*$', 'preface'),
            
            # 目录相关
            (r'^目录\s*$', 'contents'),
            (r'^Contents?\s*$', 'contents'),
            
            # 索引相关
            (r'^索引\s*$', 'index'),
            (r'^Index\s*$', 'index'),
            
            # 术语表相关
            (r'^术语表\s*$', 'glossary'),
            (r'^词汇表\s*$', 'glossary'),
            (r'^Glossary\s*$', 'glossary'),
            
            # 小结总结相关
            (r'^本章小结\s*$', 'summary'),
            (r'^小结\s*$', 'summary'),
            (r'^总结\s*$', 'summary'),
            (r'^Summary\s*$', 'summary'),
            (r'^本章总结\s*$', 'summary'),
            
            # 学习目标相关
            (r'^学习目标\s*$', 'learning_objectives'),
            (r'^学习要求\s*$', 'learning_objectives'),
            (r'^学习要点\s*$', 'learning_objectives'),
            (r'^Learning Objectives?\s*$', 'learning_objectives'),
            
            # 案例相关
            (r'^案例\s*[:：]?\s*.*', 'case_study'),
            (r'^案例分析\s*[:：]?\s*.*', 'case_study'),
            (r'^Case Study\s*[:：]?\s*.*', 'case_study'),
            
            # 实验相关
            (r'^实验\s*[:：]?\s*.*', 'experiment'),
            (r'^实验指导\s*[:：]?\s*.*', 'experiment'),
            (r'^实验内容\s*[:：]?\s*.*', 'experiment'),
            (r'^Experiment\s*[:：]?\s*.*', 'experiment'),
            
            # 拓展阅读相关
            (r'^拓展阅读\s*$', 'further_reading'),
            (r'^延伸阅读\s*$', 'further_reading'),
            (r'^Further Reading\s*$', 'further_reading'),
            
            # 重点内容相关
            (r'^本章重点\s*$', 'key_points'),
            (r'^重点内容\s*$', 'key_points'),
            (r'^Key Points?\s*$', 'key_points'),
            
            # 学习建议相关
            (r'^学习建议\s*$', 'learning_tips'),
            (r'^学习提示\s*$', 'learning_tips'),
            (r'^Learning Tips?\s*$', 'learning_tips'),
        ]
    
    def _is_chapter_header(self, line: str) -> Tuple[bool, int, str, str]:
        """
        检查是否是章节标题
        
        Returns:
            (is_chapter, level, type, title)
        """
        line_stripped = line.strip()
        
        # 先检查是否是 Markdown 标题语法
        md_header_match = re.match(r'^(#{1,6})\s+(.+)$', line_stripped)
        if md_header_match:
            level = len(md_header_match.group(1))
            title = md_header_match.group(2).strip()
            
            # 过滤规则：排除不应该作为章节标题的内容
            # _should_exclude_title 会检查是否符合章节编号模式
            if self._should_exclude_title(title, level):
                return False, 0, '', ''
            
            # 如果没被排除，说明符合章节编号模式，查找对应的模式信息
            for pattern, pattern_level, pattern_type in self.chapter_patterns:
                match = re.match(pattern, title, re.IGNORECASE)
                if match:
                    # 如果是数字编号类型，需要动态计算层级
                    if pattern_type == 'numbered' and pattern_level is None:
                        # 提取章节编号部分：取标题的第一个词（章节编号）
                        # 例如 "3.2.1 业务需求" -> "3.2.1"
                        number_part = title.split()[0] if title.split() else title
                        # 只计算章节编号部分的点的数量
                        # 层级 = 点的数量 + 1（因为第一个数字不算层级）
                        dot_count = number_part.count('.')
                        calculated_level = dot_count + 1  # 3.2 有1个点=level 2, 3.2.1 有2个点=level 3
                        return True, calculated_level, pattern_type, title
                    else:
                        return True, pattern_level, pattern_type, title
            
            # 如果没找到匹配的模式（理论上不应该发生），返回 False
            return False, 0, '', ''
        
        # 检查是否符合章节编号模式（非 Markdown 语法）
        for pattern, pattern_level, pattern_type in self.chapter_patterns:
            match = re.match(pattern, line_stripped, re.IGNORECASE)
            if match:
                # 如果是数字编号类型，需要动态计算层级
                if pattern_type == 'numbered' and pattern_level is None:
                    # 提取章节编号部分：取标题的第一个词（章节编号）
                    # 例如 "3.2.1 业务需求" -> "3.2.1"
                    number_part = line_stripped.split()[0] if line_stripped.split() else line_stripped
                    # 只计算章节编号部分的点的数量
                    # 层级 = 点的数量 + 1（因为第一个数字不算层级）
                    dot_count = number_part.count('.')
                    calculated_level = dot_count + 1  # 3.2 有1个点=level 2, 3.2.1 有2个点=level 3
                    return True, calculated_level, pattern_type, line_stripped
                else:
                    return True, pattern_level, pattern_type, line_stripped
        
        return False, 0, '', ''
    
    def _should_exclude_title(self, title: str, level: int) -> bool:
        """
        判断是否应该排除该标题（不是真正的章节标题）
        
        通用规则：
        1. 特殊段落（如小结、思考题、参考文献等）不应该作为章节标题
        2. 只有符合章节编号模式的标题才被认为是章节标题
        3. 列表项格式的标题（如 "1."、"（1）"、"一、"等）不应该作为章节标题
        
        Args:
            title: 标题文本
            level: 标题级别
            
        Returns:
            True 表示应该排除，False 表示应该保留
        """
        title_stripped = title.strip()
        
        # 1. 先检查是否是特殊段落（特殊段落不应该作为章节标题）
        is_special, _, _ = self._is_special_section(f"# {title_stripped}")
        if is_special:
            return True
        
        # 2. 检查是否符合章节编号模式
        matches_chapter_pattern = False
        for pattern, _, _ in self.chapter_patterns:
            if re.match(pattern, title_stripped, re.IGNORECASE):
                matches_chapter_pattern = True
                break
        
        # 3. 如果符合章节编号模式，保留（不排除）
        if matches_chapter_pattern:
            return False
        
        # 4. 如果不符合章节编号模式，检查是否是列表项格式
        # 列表项格式的通用模式（不应该作为章节标题）
        list_item_patterns = [
            r'^\(\d+\)\s+',  # (1) (2) (3)
            r'^\d+[、．.]\s+(?!\d)',  # 1. 2. 3.（单级数字编号，但不是"3.1"）
            r'^[一二三四五六七八九十]+[、．.]\s+[^第]',  # 一、二、三（但不是"第一章"）
            r'^[A-Za-z][、．.]\s+[^第]',  # A. B. C.（但不是章节）
        ]
        
        for pattern in list_item_patterns:
            if re.match(pattern, title_stripped, re.IGNORECASE):
                return True
        
        # 5. 对于所有级别，如果不符合章节编号模式，应该被排除
        # 这是核心规则：只有符合章节编号模式的标题才是真正的章节标题
        return True
    
    def _is_special_section(self, line: str) -> Tuple[bool, str, str]:
        """
        检查是否是特殊段落
        
        Returns:
            (is_special, section_type, title)
        """
        line_stripped = line.strip()
        
        # 先检查是否是 Markdown 标题语法
        md_header_match = re.match(r'^(#{1,6})\s+(.+)$', line_stripped)
        if md_header_match:
            title = md_header_match.group(2).strip()
            # 检查标题内容是否符合特殊段落模式
            for pattern, section_type in self.special_section_patterns:
                if re.match(pattern, title, re.IGNORECASE):
                    return True, section_type, title
        
        # 检查非 Markdown 语法的特殊段落
        for pattern, section_type in self.special_section_patterns:
            if re.match(pattern, line_stripped, re.IGNORECASE):
                return True, section_type, line_stripped
        
        return False, '', ''
    
    def extract_toc_tree(self, text: str) -> List[TOCNode]:
        """
        从文本中提取目录树结构
        
        要求：
        - 标题必须独占一行
        - 按照语义识别章节编号和特殊段落
        - 构建层级目录树结构
        
        Args:
            text: 文档内容
            
        Returns:
            目录树根节点列表
        """
        lines = text.split('\n')
        root_nodes: List[TOCNode] = []
        node_stack: List[TOCNode] = []  # 用于维护当前路径的节点栈
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # 检查是否是章节标题（标题必须独占一行）
            is_chapter, level, chapter_type, title = self._is_chapter_header(line)
            if is_chapter:
                # 创建新节点
                node = TOCNode(
                    title=title,
                    level=level,
                    line_number=i,
                    section_type=chapter_type,
                    section_title=title
                )
                
                # 找到合适的父节点：弹出所有层级大于等于当前层级的节点
                while node_stack and node_stack[-1].level >= level:
                    # 设置父节点的结束行号为当前标题行的行号
                    node_stack[-1].end_line_number = i
                    node_stack.pop()
                
                # 添加到父节点的children或root_nodes
                if node_stack:
                    node_stack[-1].children.append(node)
                else:
                    root_nodes.append(node)
                
                node_stack.append(node)
                continue
            
            # 检查是否是特殊段落（必须独占一行）
            # 特殊段落应该被添加到目录树中，作为独立的段落节点
            is_special, section_type, section_title = self._is_special_section(line)
            if is_special:
                # 特殊段落作为独立节点，层级设为当前栈顶层级+1，如果没有栈则设为1
                special_level = (node_stack[-1].level + 1) if node_stack else 1
                
                # 更新当前栈顶节点的结束行号
                if node_stack:
                    node_stack[-1].end_line_number = i
                
                # 创建特殊段落节点
                special_node = TOCNode(
                    title=section_title,
                    level=special_level,
                    line_number=i,
                    section_type=section_type,
                    section_title=section_title
                )
                
                # 找到合适的父节点：弹出所有层级大于等于当前层级的节点
                while node_stack and node_stack[-1].level >= special_level:
                    node_stack.pop()
                
                # 添加到父节点的children或root_nodes
                if node_stack:
                    node_stack[-1].children.append(special_node)
                else:
                    root_nodes.append(special_node)
                
                node_stack.append(special_node)
                continue
        
        # 设置所有剩余节点的结束行号为文件末尾
        for node in node_stack:
            node.end_line_number = len(lines)
        
        # 递归设置所有没有设置结束行号的节点的结束行号
        def set_end_lines(nodes: List[TOCNode], parent_end: int):
            """递归设置节点的结束行号"""
            for i, node in enumerate(nodes):
                if node.end_line_number is None:
                    # 如果节点有子节点，结束行号应该等于最后一个子节点的结束行号
                    if node.children:
                        # 先递归处理子节点
                        set_end_lines(node.children, parent_end)
                        # 节点的结束行号等于最后一个子节点的结束行号
                        if node.children:
                            node.end_line_number = node.children[-1].end_line_number
                        else:
                            node.end_line_number = parent_end
                    else:
                        # 没有子节点，结束行号设为下一个兄弟节点或父节点结束行号
                        if i + 1 < len(nodes):
                            node.end_line_number = nodes[i + 1].line_number
                        else:
                            node.end_line_number = parent_end
                else:
                    # 如果已经有结束行号，递归处理子节点
                    if node.children:
                        set_end_lines(node.children, node.end_line_number)
        
        set_end_lines(root_nodes, len(lines))
        
        return root_nodes
    
    def _flatten_toc_tree(self, nodes: List[TOCNode], result: List[TOCNode] = None) -> List[TOCNode]:
        """
        将目录树扁平化为列表（深度优先遍历）
        
        Args:
            nodes: 节点列表
            result: 结果列表（递归使用）
            
        Returns:
            扁平化的节点列表
        """
        if result is None:
            result = []
        
        for node in nodes:
            result.append(node)
            if node.children:
                self._flatten_toc_tree(node.children, result)
        
        return result
    
    def split_by_semantics(self, text: str) -> List[Dict[str, Any]]:
        """
        基于语义分割文本：先提取目录树，再按目录树切分
        
        Returns:
            包含 content 和 metadata 的字典列表
        """
        lines = text.split('\n')
        
        # 1. 提取目录树
        toc_tree = self.extract_toc_tree(text)
        
        if not toc_tree:
            # 如果没有找到任何标题，返回整个文档作为一个chunk
            return [{
                "content": text,
                "metadata": {
                    "Header 1": None,
                    "Header 2": None,
                    "Header 3": None,
                    "section_type": None,
                    "section_title": None,
                }
            }]
        
        # 2. 扁平化目录树
        flat_nodes = self._flatten_toc_tree(toc_tree)
        
        # 3. 根据目录树切分文件
        chunks = []
        
        for node in flat_nodes:
            # 确定该节点的内容范围
            start_line = node.line_number
            end_line = node.end_line_number if node.end_line_number is not None else len(lines)
            
            # 提取该节点的内容（包含标题行）
            node_lines = lines[start_line:end_line]
            content = '\n'.join(node_lines).strip()
            
            if not content:
                continue
            
            # 构建元数据
            # 需要找到该节点的所有父节点来构建 Header 1/2/3
            def find_parent_path(current_node: TOCNode, target_node: TOCNode, path: List[TOCNode] = None) -> List[TOCNode]:
                if path is None:
                    path = []
                
                if current_node == target_node:
                    return path + [current_node]
                
                for child in current_node.children:
                    result = find_parent_path(child, target_node, path + [current_node])
                    if result:
                        return result
                
                return None
            
            # 找到节点的完整路径
            parent_path = None
            for root in toc_tree:
                path = find_parent_path(root, node)
                if path:
                    parent_path = path
                    break
            
            # 构建 Header 1/2/3
            metadata = {
                "Header 1": None,
                "Header 2": None,
                "Header 3": None,
                "section_type": node.section_type,
                "section_title": node.section_title,
            }
            
            if parent_path:
                # 根据路径设置 Header
                for i, path_node in enumerate(parent_path[:-1]):  # 不包括当前节点
                    if i == 0:
                        metadata["Header 1"] = path_node.title
                    elif i == 1:
                        metadata["Header 2"] = path_node.title
                    elif i == 2:
                        metadata["Header 3"] = path_node.title
                
                # 当前节点根据层级设置对应的 Header
                current_level = node.level
                if current_level == 1:
                    metadata["Header 1"] = node.title
                elif current_level == 2:
                    metadata["Header 2"] = node.title
                elif current_level == 3:
                    metadata["Header 3"] = node.title
            
            chunks.append({
                "content": content,
                "metadata": metadata
            })
        
        return chunks


class MarkdownProcessor:
    """Markdown 文件处理器"""
    
    def __init__(self, chunk_size: int = 1200, chunk_overlap: int = 200, max_tokens_before_split: int = 1500,
                 enable_knowledge_extraction: bool = True):
        """
        初始化处理器
        
        Args:
            chunk_size: 每个 chunk 的最大字符数（默认 1200）
            chunk_overlap: chunk 之间的重叠字符数（默认 200）
            max_tokens_before_split: 触发二次切片的最大 tokens 数（默认 1500）
            enable_knowledge_extraction: 是否启用知识提取（默认 True）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_tokens_before_split = max_tokens_before_split
        self.enable_knowledge_extraction = enable_knowledge_extraction
        
        # 语义分割器（优先使用）
        self.semantic_splitter = SemanticSplitter()
        
        # 配置 Markdown 标题分割器（作为备用）
        # 支持 #, ##, ### 三个层级的标题
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        self.markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=False,  # 保留标题在内容中
        )
        
        # 配置代码块感知的递归字符分割器（用于二次切片）
        # 使用中文友好的分隔符
        self.code_aware_splitter = CodeBlockAwareSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "，", " ", ""],
        )
    
    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的 tokens 数量
        粗略估算：1 token ≈ 4 字符（中文和英文混合）
        
        Args:
            text: 文本内容
            
        Returns:
            估算的 tokens 数量
        """
        return len(text) // 4
    
    def read_file(self, file_path: str) -> str:
        """
        读取 Markdown 文件内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容字符串
            
        Raises:
            FileNotFoundError: 文件不存在
            UnicodeDecodeError: 文件编码错误
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                with open(path, "r", encoding="gbk") as f:
                    content = f.read()
                return content
            except Exception as e:
                try:
                    error_msg = repr(e) if hasattr(e, '__repr__') else "编码错误"
                except (UnicodeEncodeError, UnicodeDecodeError):
                    error_msg = "编码错误"
                raise UnicodeDecodeError(
                    "utf-8", b"", 0, 1, f"无法解码文件，尝试了 utf-8 和 gbk 编码: {error_msg}"
                )
    
    def process(self, file_path: str) -> List[Dict[str, Any]]:
        """
        处理 Markdown 文件
        
        流程：
        1. 读取文件内容
        2. 使用语义分割器提取目录树，按目录树切分文件
        3. 如果语义分割失败，回退到 MarkdownHeaderTextSplitter
        4. 不限制切片字数，每个目录项对应一个完整的切片
        
        Args:
            file_path: Markdown 文件路径
            
        Returns:
            包含 content 和 metadata 的字典列表
            格式：
            [
                {
                    "content": "文档内容",
                    "metadata": {
                        "Header 1": "一级标题",
                        "Header 2": "二级标题",
                        "Header 3": "三级标题",
                        "section_type": "章节类型（chapter/section/numbered/special等）",
                        "section_title": "段落标题",
                        "source": "文件路径"
                    }
                },
                ...
            ]
        """
        # 1. 读取文件内容
        content = self.read_file(file_path)
        
        if not content.strip():
            return []
        
        # 2. 优先使用语义分割器（基于目录树）
        try:
            semantic_chunks = self.semantic_splitter.split_by_semantics(content)
            # 检查是否成功识别到章节（至少有一个 chunk 有标题）
            has_chapters = any(
                chunk.get("metadata", {}).get("Header 1") or 
                chunk.get("metadata", {}).get("Header 2") or
                chunk.get("metadata", {}).get("Header 3") or
                chunk.get("metadata", {}).get("section_type")
                for chunk in semantic_chunks
            )
            
            if has_chapters and len(semantic_chunks) > 0:
                # 添加 source 信息
                result_chunks = []
                for chunk in semantic_chunks:
                    chunk_metadata = chunk["metadata"].copy()
                    chunk_metadata["source"] = file_path
                    result_chunks.append({
                        "content": chunk["content"],
                        "metadata": chunk_metadata
                    })
                return result_chunks
        except Exception as e:
            # 语义分割失败，继续尝试备用方案
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "语义切分失败"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "语义切分失败"
        
        # 3. 如果语义分割失败，使用 MarkdownHeaderTextSplitter 作为备用
        try:
            md_docs = self.markdown_splitter.split_text(content)
            result_chunks = []
            for doc in md_docs:
                doc_metadata = doc.metadata.copy()
                doc_metadata["source"] = file_path
                result_chunks.append({
                    "content": doc.page_content,
                    "metadata": doc_metadata
                })
            return result_chunks
        except Exception as e:
            # 如果切分失败，返回整个文档作为一个 chunk
            try:
                error_msg = repr(e) if hasattr(e, '__repr__') else "标题切分失败"
            except (UnicodeEncodeError, UnicodeDecodeError):
                error_msg = "标题切分失败"
            return [{
                "content": content,
                "metadata": {
                    "source": file_path,
                    "error": f"标题切分失败: {error_msg}"
                }
            }]
    
    def get_chapter_name(self, metadata: Dict[str, Any]) -> str:
        """
        从元数据中提取章节名称
        
        Args:
            metadata: 元数据字典
            
        Returns:
            章节名称字符串
        """
        # 优先使用 section_title（语义分割识别的标题）
        if metadata.get("section_title"):
            return metadata["section_title"]
        
        # 按优先级获取标题
        if metadata.get("Header 1"):
            return metadata["Header 1"]
        elif metadata.get("Header 2"):
            return metadata["Header 2"]
        elif metadata.get("Header 3"):
            return metadata["Header 3"]
        else:
            return "未命名章节"
    
    def get_chapter_level(self, metadata: Dict[str, Any]) -> int:
        """
        从元数据中提取章节层级
        
        Args:
            metadata: 元数据字典
            
        Returns:
            层级数字（1, 2, 3 或 0 表示无标题）
        """
        # 优先使用 section_title 计算层级（对于数字编号）
        section_title = metadata.get("section_title")
        section_type = metadata.get("section_type")
        
        # 如果是数字编号类型，根据章节编号计算层级
        if section_type == "numbered" and section_title:
            # 提取章节编号部分（第一个词）
            number_part = section_title.split()[0] if section_title.split() else section_title
            # 检查是否符合数字编号模式（如 3.2.1）
            if re.match(r'^\d+\.\d+(?:\.\d+)*', number_part):
                # 计算点的数量：1个点=level 2, 2个点=level 3, 以此类推
                dot_count = number_part.count('.')
                return dot_count + 1  # 3.2 有1个点=level 2, 3.2.1 有2个点=level 3
        
        # 根据 section_type 判断层级
        if section_type == "chapter":
            return 1
        elif section_type == "section":
            return 2
        elif section_type == "numbered_single":
            return 1
        
        # 回退到 Header 层级
        if metadata.get("Header 1"):
            return 1
        elif metadata.get("Header 2"):
            return 2
        elif metadata.get("Header 3"):
            return 3
        else:
            return 0
    
    async def extract_knowledge_metadata(self, chunk_content: str, chunk_metadata: Dict[str, Any],
                                       api_key: Optional[str] = None, 
                                       model: Optional[str] = None,
                                       api_endpoint: Optional[str] = None,
                                       file_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        调用 LLM 提取知识点的语义信息
        
        Args:
            chunk_content: 切片内容
            chunk_metadata: 切片元数据
            api_key: OpenRouter API 密钥（可选，默认从数据库读取）
            model: 模型名称（可选，默认从数据库读取）
            api_endpoint: API端点URL（可选，默认从数据库读取）
            file_id: 文件 ID（可选，用于查询文件名和教材信息）
            
        Returns:
            知识点元数据字典，包含：
            - core_concept: 核心概念
            - confusion_points: 学生易错点列表
            - bloom_level: Bloom 认知层级（1-6）
            - application_scenarios: 应用场景列表（可选）
            注意：知识点应该是独立的，不包含前置依赖（prerequisites）
            如果提取失败则返回 None
        """
        try:
            # 导入 OpenRouter 客户端（延迟导入，避免循环依赖）
            from generator import OpenRouterClient
            import httpx
            
            # 创建 OpenRouter 客户端
            client = OpenRouterClient(api_key=api_key, model=model, api_endpoint=api_endpoint)
            
            # 获取上下文信息（文件名、教材名称、目录路径）
            context_info = []
            
            # 查询文件信息和已有知识点
            filename = None
            textbook_names = []
            existing_concepts = []
            if file_id:
                try:
                    from database import db
                    file_info = db.get_file(file_id)
                    if file_info:
                        filename = file_info.get("filename", "")
                        if filename:
                            context_info.append(f"文件名: {filename}")
                    
                    # 查询教材信息
                    textbooks = db.get_file_textbooks(file_id)
                    if textbooks:
                        textbook_names = [t.get("name", "") for t in textbooks if t.get("name")]
                        if textbook_names:
                            context_info.append(f"教材名称: {', '.join(textbook_names)}")
                    
                    # 查询该文件已有的知识点（用于避免重复）
                    existing_nodes = db.get_file_knowledge_nodes(file_id)
                    existing_concepts = [node.get("core_concept", "") for node in existing_nodes if node.get("core_concept")]
                    if existing_concepts:
                        print(f"[知识提取] 发现该文件已有 {len(existing_concepts)} 个知识点，将用于参考避免重复")
                except Exception as e:
                    print(f"[知识提取] 警告：查询文件/教材信息失败: {e}")
            
            # 构建目录路径信息
            chapter_path = []
            
            # 先添加层级化的 Header 路径
            if chunk_metadata.get("Header 1"):
                chapter_path.append(chunk_metadata["Header 1"])
            if chunk_metadata.get("Header 2"):
                chapter_path.append(chunk_metadata["Header 2"])
            if chunk_metadata.get("Header 3"):
                chapter_path.append(chunk_metadata["Header 3"])
            
            # 如果 section_title 存在且与最后一个元素不同，添加它（提供更详细的章节信息）
            section_title = chunk_metadata.get("section_title")
            if section_title and (not chapter_path or chapter_path[-1] != section_title):
                chapter_path.append(section_title)
            
            if chapter_path:
                context_info.append(f"章节路径: {' > '.join(chapter_path)}")
            
            context_str = "\n".join(context_info) if context_info else "（无额外上下文信息）"
            
            # 构建提示词
            system_prompt = """你是一位资深的计算机科学教育专家，专门从事计算机教材的知识点分析与提取工作。你的任务是分析计算机科学相关教材的内容，提取知识点的语义信息，确保生成的知识节点紧密围绕教材主题，符合计算机科学学科特点。

**重要提示**：
1. 这是计算机科学相关的教材内容，所有知识点都应该围绕计算机科学领域（包括但不限于：编程语言、数据结构、算法、操作系统、计算机网络、数据库、软件工程、人工智能等）。
2. 提取的知识点必须与教材主题紧密相关，不能偏离计算机科学领域。
3. 核心概念、前置依赖、应用场景等都应该限定在计算机科学范围内。
4. 如果教材片段涉及具体的计算机技术、算法、系统或理论，请确保知识点表述准确且专业。

**知识点提取原则**：
1. **限定数量**：每个教材片段只提取 **1个** 核心概念。如果片段涉及多个概念，请选择最重要的、最核心的理论概念。
2. **避免重复**：如果提供了"已有知识点列表"，请仔细检查：
   - 如果当前片段的核心概念已经存在于列表中，**必须使用完全相同的名称**（不要添加括号、英文翻译等变体）
   - 例如：如果列表中已有"人工智能"，不要生成"人工智能（Artificial Intelligence）"或"人工智能的研究途径"
   - 如果概念本质相同但名称略有不同，请统一使用列表中已有的名称
   - **不要重复生成已存在的核心概念**
3. **只提取核心概念**：只提取真正的、可独立存在的核心知识点，**不要提取**：
   - 主题的某个方面（如"XX的历史"、"XX的特点"、"XX的优势与缺点"、"XX与XX的对比"等）
   - 主题的子话题（如"XX的研究途径"、"XX的应用"等）
   - 主题的某个属性或特征（如"XX的定义"、"XX的概念"等）
   - 如果片段主要讨论某个核心概念的某个方面，应该提取该核心概念本身，而不是这个方面
   - 例如：如果片段讨论"人工智能的历史"，应该提取"人工智能"而不是"人工智能的历史"
4. **通用理论优先**：只提取通用的、可复用的理论知识点，不要提取：
   - 具体的代码实现细节
   - 特定工具的使用方法（如"如何使用IDE"、"如何安装某个软件"等）
   - 示例代码或示例程序
   - 具体的配置步骤
   - 特定版本或特定平台的说明
   - 过于具体的应用实例细节
5. **标准命名**：核心概念名称必须使用计算机科学领域的标准术语，遵循业界通用命名规范：
   - 使用准确的专业术语（如"二叉树"而不是"树结构"、"快速排序"而不是"排序方法"）
   - 避免使用模糊或口语化的表达
   - 优先使用英文术语的标准中文翻译，或直接使用英文术语（如果更通用）
   - 保持命名简洁、清晰、唯一（避免"XX的概念"、"XX简介"等冗余表达）
   - 同一概念在整个文件中应保持命名一致
6. **知识点独立性**：每个提取的知识点应该是独立的，不依赖其他知识点。**不要提取前置依赖知识点（Prerequisites）**，因为知识点之间应该是平等的关系，而不是依赖关系。

请仔细分析提供的教材片段，提取以下信息：
1. **核心概念（Core Concept）**：该片段主要讲解的核心知识点是什么？必须是计算机科学领域的专业概念，使用准确的术语。**只提取1个最核心的概念**。该概念应该是独立的，不依赖其他知识点。
2. **学生易错点（Confusion Points）**：学生在学习这个知识点时，容易混淆或出错的地方有哪些？应该针对计算机科学学习中的常见误解和难点。
3. **Bloom 认知层级（Bloom Level）**：该知识点属于 Bloom 认知分类的哪个层级？
   - Level 1: 记忆（Remember）- 能够回忆或识别信息（如：记住算法步骤、数据结构的定义）
   - Level 2: 理解（Understand）- 能够解释、说明或总结（如：解释算法的原理、理解数据结构的特点）
   - Level 3: 应用（Apply）- 能够在新的情境中使用知识（如：应用算法解决问题、使用数据结构实现程序）
   - Level 4: 分析（Analyze）- 能够分解、比较或区分（如：分析算法复杂度、比较不同算法的优劣）
   - Level 5: 评价（Evaluate）- 能够判断、批评或评估（如：评估算法的适用性、评价设计方案的优劣）
   - Level 6: 创造（Create）- 能够设计、构建或创造（如：设计新算法、构建系统架构）
4. **应用场景（Application Scenarios）**：该知识点在计算机科学实际中的应用场景有哪些？应该提供具体的、相关的应用实例（但要避免过于具体的实现细节）。

**重要**：**不要提取前置依赖知识点（Prerequisites）**，所有知识点应该是独立的、平等的。

请严格按照以下 JSON 格式返回，不要添加任何额外的文本、说明或代码块标记：

```json
{
  "core_concept": "核心概念名称",
  "confusion_points": ["易错点1", "易错点2", ...],
  "bloom_level": 3,
  "application_scenarios": ["应用场景1", "应用场景2", ...]
}
```"""

            # 构建已有知识点信息
            existing_concepts_str = ""
            if existing_concepts:
                concepts_list = "\n".join(f"- {concept}" for concept in existing_concepts[:50])  # 最多显示50个，避免提示词过长
                existing_concepts_str = f"""
**已有知识点列表（请参考并避免重复）：**
{concepts_list}

**重要**：
- 如果当前片段的核心概念已经存在于上述列表中，**必须使用完全相同的名称**
- 不要生成变体名称（如添加括号、英文翻译等）
- 如果概念本质相同，请统一使用列表中已有的名称
- **不要重复生成已存在的核心概念**
- 如果片段讨论的是某个已有概念的某个方面（如历史、特点、优势等），应该提取该核心概念本身，而不是这个方面
"""
            
            user_prompt = f"""请分析以下计算机教材片段，提取知识点的语义信息。

**上下文信息：**
{context_str}
{existing_concepts_str}
**教材内容：**
```markdown
{chunk_content}
```

**重要要求：**
1. 提取的知识点必须紧密围绕教材主题和上下文信息中的教材名称。
2. 核心概念应该与章节路径（如果提供）的内容相符。
3. 所有知识点都应该限定在计算机科学领域范围内。
4. 如果提供了教材名称，知识点应该与该教材的主题和范围保持一致。
5. **只提取1个核心概念**，选择最重要的、最核心的理论知识点。
6. **使用标准术语命名**，确保概念名称清晰、准确、符合计算机科学领域的通用命名规范。
7. **避免重复**：如果提供了已有知识点列表，请检查当前片段的核心概念是否已存在：
   - 如果已存在，必须使用完全相同的名称
   - 不要生成"XX的历史"、"XX的特点"、"XX的优势与缺点"等不是核心概念的内容
   - 如果片段讨论的是某个核心概念的某个方面，应该提取该核心概念本身
8. **只提取真正的核心概念**：不要提取主题的某个方面、子话题或属性，只提取可独立存在的核心知识点。
9. **知识点独立性**：**不要提取前置依赖知识点（Prerequisites）**，所有知识点应该是独立的、平等的，不依赖其他知识点。

请严格按照 JSON 格式返回，不要添加任何额外的文本、说明或代码块标记。直接返回 JSON 对象即可。"""
            
            # 构建请求消息
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # 检查 API 配置
            if not client.api_key:
                error_msg = "API key 未配置，无法调用知识提取 API"
                print(f"[知识提取] ✗ {error_msg}")
                print(f"[知识提取] 提示：请在系统设置中配置 OpenRouter API key")
                return None
            
            # 清理 API key（去除前后空格）
            api_key_cleaned = client.api_key.strip()
            if api_key_cleaned != client.api_key:
                print(f"[知识提取] ⚠ API key 包含前后空格，已自动清理")
            
            # 检查 API key 格式（不显示完整 key，只显示前3个和后3个字符）
            if len(api_key_cleaned) < 20:
                print(f"[知识提取] ⚠ API key 长度异常: {len(api_key_cleaned)} 字符（通常应该更长）")
            else:
                print(f"[知识提取] API key 格式检查: 长度={len(api_key_cleaned)}, 前缀={api_key_cleaned[:3]}..., 后缀=...{api_key_cleaned[-3:]}")
            
            print(f"[知识提取] 调用 API: {client.api_endpoint}, 模型: {client.model}")
            
            # 调用 OpenRouter API（使用清理后的 API key）
            headers = {
                "Authorization": f"Bearer {api_key_cleaned}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/your-repo",
                "X-Title": "AI Question Generator",
            }
            
            payload = {
                "model": client.model,
                "messages": messages,
                "temperature": 0.3,  # 降低温度，提高准确性
                "max_tokens": 2000,
            }
            
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                try:
                    response = await http_client.post(
                        client.api_endpoint,
                        headers=headers,
                        json=payload
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                except httpx.HTTPStatusError as e:
                    error_msg = f"API 调用失败，状态码: {e.response.status_code}"
                    print(f"[知识提取] ✗ {error_msg}")
                    print(f"[知识提取] 响应内容: {e.response.text[:500]}")
                    return None
                except httpx.RequestError as e:
                    error_msg = f"API 请求失败: {str(e)}"
                    print(f"[知识提取] ✗ {error_msg}")
                    return None
                
                # 提取生成的文本
                if "choices" not in result or len(result["choices"]) == 0:
                    error_msg = "知识提取 API 返回结果中没有 choices 字段"
                    print(f"[知识提取] ✗ {error_msg}")
                    print(f"[知识提取] API 响应: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
                    return None
                
                generated_text = result["choices"][0]["message"]["content"].strip()
                
                # 清理可能的代码块标记
                if generated_text.startswith("```json"):
                    generated_text = generated_text[7:].strip()
                elif generated_text.startswith("```"):
                    generated_text = generated_text[3:].strip()
                
                if generated_text.endswith("```"):
                    generated_text = generated_text[:-3].strip()
                
                # 解析 JSON
                try:
                    knowledge_data = json.loads(generated_text)
                    
                    # 验证必需字段
                    if "core_concept" not in knowledge_data or "bloom_level" not in knowledge_data:
                        error_msg = f"知识提取结果缺少必需字段。返回的字段: {list(knowledge_data.keys())}"
                        print(f"[知识提取] ✗ {error_msg}")
                        print(f"[知识提取] 返回的数据: {json.dumps(knowledge_data, ensure_ascii=False, indent=2)[:500]}")
                        return None
                    
                    # 确保字段类型正确
                    if not isinstance(knowledge_data.get("core_concept"), str):
                        error_msg = f"core_concept 必须是字符串，当前类型: {type(knowledge_data.get('core_concept'))}"
                        print(f"[知识提取] ✗ {error_msg}")
                        return None
                    
                    if not isinstance(knowledge_data.get("bloom_level"), int):
                        error_msg = f"bloom_level 必须是整数，当前类型: {type(knowledge_data.get('bloom_level'))}"
                        print(f"[知识提取] ✗ {error_msg}")
                        return None
                    
                    bloom_level = knowledge_data["bloom_level"]
                    if bloom_level < 1 or bloom_level > 6:
                        print(f"[知识提取] ⚠ bloom_level 超出范围 (1-6)，当前值: {bloom_level}，已自动调整")
                        bloom_level = max(1, min(6, bloom_level))  # 限制在有效范围内
                        knowledge_data["bloom_level"] = bloom_level
                    
                    # 确保列表字段存在（不包含 prerequisites，因为知识点应该是独立的）
                    if "confusion_points" not in knowledge_data:
                        knowledge_data["confusion_points"] = []
                    if "application_scenarios" not in knowledge_data:
                        knowledge_data["application_scenarios"] = None
                    
                    # 确保列表字段是列表类型
                    if not isinstance(knowledge_data["confusion_points"], list):
                        knowledge_data["confusion_points"] = []
                    if knowledge_data["application_scenarios"] is not None and not isinstance(knowledge_data["application_scenarios"], list):
                        knowledge_data["application_scenarios"] = None
                    
                    # 强制移除 prerequisites，确保知识点独立
                    if "prerequisites" in knowledge_data:
                        del knowledge_data["prerequisites"]
                    # 确保 prerequisites 字段不存在或为空数组（向后兼容）
                    knowledge_data["prerequisites"] = []
                    
                    # 检查并统一重复的知识点名称
                    core_concept = knowledge_data["core_concept"].strip()
                    if existing_concepts:
                        # 检查完全匹配
                        if core_concept in existing_concepts:
                            print(f"[知识提取] ⚠ 发现重复知识点，使用已有名称: {core_concept}")
                        else:
                            # 检查相似匹配（去除括号内容、去除"的XX"后缀等）
                            core_concept_base = core_concept.split("（")[0].split("(")[0].strip()  # 去除括号内容
                            core_concept_base = core_concept_base.split("的")[0].strip() if "的" in core_concept_base else core_concept_base  # 去除"的XX"后缀
                            
                            # 查找匹配的已有知识点
                            for existing_concept in existing_concepts:
                                existing_base = existing_concept.split("（")[0].split("(")[0].strip()
                                existing_base = existing_base.split("的")[0].strip() if "的" in existing_base else existing_base
                                
                                # 如果基础名称相同，使用已有名称
                                if core_concept_base == existing_base or core_concept_base in existing_base or existing_base in core_concept_base:
                                    print(f"[知识提取] ⚠ 发现相似知识点，统一使用已有名称: {existing_concept} (原: {core_concept})")
                                    knowledge_data["core_concept"] = existing_concept
                                    break
                    
                    print(f"[知识提取] ✓ 成功提取知识点: {knowledge_data['core_concept']} (bloom_level: {knowledge_data['bloom_level']})")
                    return knowledge_data
                    
                except json.JSONDecodeError as e:
                    error_msg = f"知识提取 JSON 解析失败: {e}"
                    print(f"[知识提取] ✗ {error_msg}")
                    print(f"[知识提取] 原始响应前1000字符:\n{generated_text[:1000]}")
                    return None
                    
        except Exception as e:
            error_msg = f"知识提取失败: {str(e)}"
            print(f"[知识提取] ✗ {error_msg}")
            import traceback
            traceback.print_exc()
            return None
    
    async def process_with_knowledge_extraction(self, file_path: str, file_id: str,
                                               api_key: Optional[str] = None,
                                               model: Optional[str] = None,
                                               api_endpoint: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        处理 Markdown 文件并提取知识点（异步版本）
        
        流程：
        1. 读取文件内容
        2. 使用语义分割器提取目录树，按目录树切分文件
        3. 如果语义分割失败，回退到 MarkdownHeaderTextSplitter
        4. 对每个切片调用 LLM 提取知识点元数据
        5. 将知识点保存到数据库
        
        Args:
            file_path: Markdown 文件路径
            file_id: 文件 ID（用于关联知识点节点）
            api_key: OpenRouter API 密钥（可选）
            model: 模型名称（可选）
            api_endpoint: API端点URL（可选）
            
        Returns:
            包含 content 和 metadata 的字典列表
        """
        # 先进行常规处理
        chunks = self.process(file_path)
        
        if not chunks or not self.enable_knowledge_extraction:
            return chunks
        
        # 导入数据库模块（延迟导入，避免循环依赖）
        from database import db
        
        # 对每个切片提取知识点
        for chunk_idx, chunk in enumerate(chunks):
            chunk_content = chunk.get("content", "")
            chunk_metadata = chunk.get("metadata", {})
            
            if not chunk_content.strip():
                continue
            
            try:
                # 调用 LLM 提取知识点
                knowledge_data = await self.extract_knowledge_metadata(
                    chunk_content, chunk_metadata, api_key, model, api_endpoint, file_id
                )
                
                if knowledge_data:
                    # 获取 chunk_id（需要从数据库查询，因为 chunks 表是存储后才有的）
                    # 这里我们需要先存储 chunks，然后获取 chunk_id
                    # 但为了简化，我们可以先存储知识点，然后在存储 chunks 时关联
                    # 或者我们可以使用临时 ID，稍后更新
                    
                    # 生成节点 ID
                    node_id = str(uuid.uuid4())
                    
                    # 注意：这里 chunk_id 需要从数据库获取，但 chunks 可能还没有存储
                    # 所以我们先不存储，而是在存储 chunks 后再调用这个方法
                    # 或者我们可以修改逻辑，在存储 chunks 后立即提取知识点
                    
                    # 暂时跳过存储，因为 chunk_id 还不存在
                    # 知识点提取将在存储 chunks 后单独调用
                    chunk["knowledge_metadata"] = knowledge_data
                    
            except Exception as e:
                print(f"警告：切片 {chunk_idx} 的知识点提取失败: {e}")
                continue
        
        return chunks


def normalize_concept_name(concept: str) -> str:
    """
    标准化概念名称，用于去重比较
    
    处理规则：
    1. 去除首尾空格
    2. 统一空格（多个连续空格合并为一个）
    3. 去除常见的冗余后缀（如"的概念"、"简介"、"概述"等）
    4. 转换为小写（用于比较，但不改变原始存储）
    
    Args:
        concept: 原始概念名称
        
    Returns:
        标准化后的概念名称（用于比较）
    """
    if not concept:
        return ""
    
    # 去除首尾空格
    normalized = concept.strip()
    
    # 统一空格（多个连续空格合并为一个）
    import re
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # 去除常见的冗余后缀
    redundant_suffixes = [
        "的概念", "简介", "概述", "介绍",
        "的基本概念", "基础概念", "的核心概念"
    ]
    for suffix in redundant_suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
    
    # 转换为小写用于比较
    normalized_lower = normalized.lower()
    
    return normalized_lower


def is_concept_duplicate(concept1: str, concept2: str, threshold: float = 0.85) -> bool:
    """
    检查两个概念是否重复
    
    使用标准化名称进行比较，如果完全相同或高度相似则认为重复
    
    Args:
        concept1: 第一个概念名称
        concept2: 第二个概念名称
        threshold: 相似度阈值（0-1），默认0.85
        
    Returns:
        True 如果认为重复，False 否则
    """
    normalized1 = normalize_concept_name(concept1)
    normalized2 = normalize_concept_name(concept2)
    
    # 完全相同的标准化名称
    if normalized1 == normalized2:
        return True
    
    # 检查是否互为子串（一个包含另一个，且长度差异不超过30%）
    if normalized1 in normalized2 or normalized2 in normalized1:
        len1, len2 = len(normalized1), len(normalized2)
        if len1 > 0 and len2 > 0:
            ratio = min(len1, len2) / max(len1, len2)
            if ratio >= threshold:
                return True
    
    # 可以使用更复杂的相似度算法（如编辑距离），但为了性能先使用简单方法
    return False


def process_markdown_file(file_path: str, chunk_size: int = 1200, chunk_overlap: int = 200) -> List[Dict[str, Any]]:
    """
    便捷函数：处理 Markdown 文件
    
    Args:
        file_path: Markdown 文件路径
        chunk_size: 每个 chunk 的最大字符数
        chunk_overlap: chunk 之间的重叠字符数
        
    Returns:
        包含 content 和 metadata 的字典列表
    """
    processor = MarkdownProcessor(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return processor.process(file_path)


async def extract_and_store_knowledge_nodes(file_id: str, 
                                           api_key: Optional[str] = None,
                                           model: Optional[str] = None,
                                           api_endpoint: Optional[str] = None) -> int:
    """
    为文件的所有切片提取并存储知识点节点
    
    这个函数应该在 chunks 已经存储到数据库后调用，因为需要 chunk_id。
    
    Args:
        file_id: 文件 ID
        api_key: OpenRouter API 密钥（可选）
        model: 模型名称（可选）
        api_endpoint: API端点URL（可选）
        
    Returns:
        成功提取的知识点节点数量
    """
    from database import db
    from knowledge_extraction_progress import knowledge_extraction_progress
    
    print(f"[知识提取] 开始为文件 {file_id} 提取知识点...")
    
    # 如果没有提供 API 配置，从数据库读取
    if not api_key or not model or not api_endpoint:
        ai_config = db.get_ai_config()
        if not api_key:
            api_key = ai_config.get("api_key")
        if not model:
            model = ai_config.get("model", "openai/gpt-4o-mini")
        if not api_endpoint:
            api_endpoint = ai_config.get("api_endpoint", "https://openrouter.ai/api/v1/chat/completions")
        
        print(f"[知识提取] 从数据库读取 API 配置: endpoint={api_endpoint}, model={model}, api_key={'已配置' if api_key else '未配置'}")
    
    # 检查 API key 是否配置
    if not api_key:
        error_msg = "API key 未配置，无法进行知识提取"
        print(f"[知识提取] ✗ {error_msg}")
        await knowledge_extraction_progress.push_progress(
            file_id=file_id,
            current=0,
            total=0,
            message=error_msg + "，请在系统设置中配置 OpenRouter API key",
            status="failed"
        )
        return 0
    
    # 获取文件的所有切片（包含 chunk_id）
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT chunk_id, chunk_index, content, metadata_json 
            FROM chunks 
            WHERE file_id = ? 
            ORDER BY chunk_index
        """, (file_id,))
        rows = cursor.fetchall()
        
        if not rows:
            await knowledge_extraction_progress.push_progress(
                file_id=file_id,
                current=0,
                total=0,
                message="文件没有切片，跳过知识提取",
                status="completed"
            )
            return 0
        
        chunks_with_ids = []
        for row in rows:
            chunks_with_ids.append({
                "chunk_id": row["chunk_id"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "metadata": json.loads(row["metadata_json"])
            })
    
    total_chunks = len(chunks_with_ids)
    processor = MarkdownProcessor(enable_knowledge_extraction=True)
    extracted_count = 0
    skipped_count = 0  # 跳过的重复知识点数量
    
    # 获取文件中已存在的知识点（用于去重）
    existing_nodes = db.get_file_knowledge_nodes(file_id)
    print(f"[知识提取] 文件 {file_id} 中已存在 {len(existing_nodes)} 个知识点")
    
    # 当前批次提取的知识点集合（用于本次提取过程中的去重）
    # 存储标准化后的概念名称用于快速比较
    current_batch_concepts = set()
    
    # 初始化进度
    await knowledge_extraction_progress.push_progress(
        file_id=file_id,
        current=0,
        total=total_chunks,
        message=f"开始提取知识点，共 {total_chunks} 个切片（已存在 {len(existing_nodes)} 个知识点）",
        status="extracting"
    )
    
    # 对每个切片提取知识点
    for idx, chunk_data in enumerate(chunks_with_ids):
        chunk_id = chunk_data["chunk_id"]
        chunk_content = chunk_data.get("content", "")
        chunk_metadata = chunk_data.get("metadata", {})
        
        if not chunk_content.strip():
            # 更新进度（跳过空切片）
            await knowledge_extraction_progress.push_progress(
                file_id=file_id,
                current=idx + 1,
                total=total_chunks,
                current_chunk=f"切片 {chunk_data.get('chunk_index', idx + 1)}（空内容，跳过）",
                message=f"处理中: {idx + 1}/{total_chunks}",
                status="extracting"
            )
            continue
        
        # 更新进度
        chunk_info = chunk_metadata.get("section_title") or chunk_metadata.get("Header 1") or chunk_metadata.get("Header 2") or f"切片 {chunk_data.get('chunk_index', idx + 1)}"
        await knowledge_extraction_progress.push_progress(
            file_id=file_id,
            current=idx,
            total=total_chunks,
            current_chunk=chunk_info[:50],  # 限制长度
            message=f"正在提取知识点: {chunk_info[:30]}... ({idx + 1}/{total_chunks})",
            status="extracting"
        )
        
        try:
            # 调用 LLM 提取知识点
            knowledge_data = await processor.extract_knowledge_metadata(
                chunk_content, chunk_metadata, api_key, model, api_endpoint, file_id
            )
            
            if knowledge_data:
                core_concept = knowledge_data["core_concept"]
                normalized_concept = normalize_concept_name(core_concept)
                
                # 检查是否重复
                is_duplicate = False
                duplicate_reason = ""
                
                # 先检查与当前批次已提取的知识点（使用标准化名称快速比较）
                if normalized_concept in current_batch_concepts:
                    is_duplicate = True
                    duplicate_reason = "与当前批次已提取的知识点重复"
                
                # 如果未重复，检查与数据库中已存在的知识点（使用更精确的相似度比较）
                if not is_duplicate:
                    for node in existing_nodes:
                        existing_concept = node["core_concept"]
                        if is_concept_duplicate(core_concept, existing_concept):
                            is_duplicate = True
                            duplicate_reason = f"与已有知识点重复: {existing_concept}"
                            break
                
                if is_duplicate:
                    skipped_count += 1
                    print(f"[知识提取] ⊘ 跳过重复知识点: {core_concept} ({duplicate_reason})")
                    # 更新进度
                    await knowledge_extraction_progress.push_progress(
                        file_id=file_id,
                        current=idx + 1,
                        total=total_chunks,
                        current_chunk=chunk_info[:50],
                        message=f"跳过重复知识点: {core_concept[:30]}...",
                        status="extracting"
                    )
                    continue
                
                # 生成节点 ID
                node_id = str(uuid.uuid4())
                
                # 存储知识点节点（不包含 prerequisites，确保知识点独立）
                success = db.store_knowledge_node(
                    node_id=node_id,
                    chunk_id=chunk_id,
                    file_id=file_id,
                    core_concept=core_concept,
                    prerequisites=[],  # 知识点应该是独立的，不包含前置依赖
                    confusion_points=knowledge_data.get("confusion_points", []),
                    bloom_level=knowledge_data["bloom_level"],
                    application_scenarios=knowledge_data.get("application_scenarios")
                )
                
                if success:
                    extracted_count += 1
                    # 添加到当前批次集合，避免后续重复（使用标准化名称）
                    current_batch_concepts.add(normalized_concept)
                    print(f"[知识提取] ✓ 成功提取并存储知识点节点: {core_concept} (chunk_id: {chunk_id}, bloom_level: {knowledge_data['bloom_level']})")
                else:
                    error_msg = f"存储知识点节点失败: {core_concept}"
                    print(f"[知识提取] ✗ {error_msg}")
                    # 更新进度，包含错误信息
                    await knowledge_extraction_progress.push_progress(
                        file_id=file_id,
                        current=idx + 1,
                        total=total_chunks,
                        current_chunk=chunk_info[:50],
                        message=f"存储失败: {error_msg}",
                        status="extracting"
                    )
            else:
                error_msg = f"切片 {chunk_data['chunk_index']} 的知识点提取返回空结果（可能是 API 调用失败或格式解析失败）"
                print(f"[知识提取] ✗ {error_msg}")
                # 更新进度，包含错误信息
                await knowledge_extraction_progress.push_progress(
                    file_id=file_id,
                    current=idx + 1,
                    total=total_chunks,
                    current_chunk=chunk_info[:50],
                    message=f"提取失败: 请检查后端日志",
                    status="extracting"
                )
                        
        except Exception as e:
            error_msg = f"切片 {chunk_data.get('chunk_index', 'unknown')} 的知识点提取异常: {str(e)}"
            print(f"[知识提取] ✗ {error_msg}")
            import traceback
            traceback.print_exc()
            # 更新进度，包含错误信息
            await knowledge_extraction_progress.push_progress(
                file_id=file_id,
                current=idx + 1,
                total=total_chunks,
                current_chunk=chunk_info[:50] if 'chunk_info' in locals() else f"切片 {chunk_data.get('chunk_index', idx + 1)}",
                message=f"异常: {str(e)[:50]}",
                status="extracting"
            )
            continue
    
    # 完成进度
    message = f"知识点提取完成：成功提取 {extracted_count} 个新知识点"
    if skipped_count > 0:
        message += f"，跳过 {skipped_count} 个重复知识点"
    message += f"（共处理 {total_chunks} 个切片）"
    
    await knowledge_extraction_progress.push_progress(
        file_id=file_id,
        current=total_chunks,
        total=total_chunks,
        message=message,
        status="completed"
    )
    
    # 重新加载知识图谱（确保新提取的知识点能够被查询到）
    try:
        from graph_manager import knowledge_graph
        knowledge_graph.reload()
        print(f"知识图谱已重新加载，当前节点数: {knowledge_graph.graph.number_of_nodes()}")
    except Exception as e:
        print(f"警告：重新加载知识图谱失败: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"知识点提取完成：成功提取 {extracted_count} 个新知识点，跳过 {skipped_count} 个重复知识点（共处理 {len(chunks_with_ids)} 个切片）")
    return extracted_count


async def build_textbook_knowledge_dependencies(textbook_id: str,
                                                api_key: Optional[str] = None,
                                                model: Optional[str] = None,
                                                api_endpoint: Optional[str] = None) -> Dict[str, Any]:
    """
    为教材下的所有知识点构建依赖关系
    
    使用 LLM 分析教材下所有知识点之间的依赖关系，并更新数据库中的 prerequisites 字段。
    
    Args:
        textbook_id: 教材 ID
        api_key: OpenRouter API 密钥（可选，默认从数据库读取）
        model: 模型名称（可选，默认从数据库读取）
        api_endpoint: API端点URL（可选，默认从数据库读取）
        
    Returns:
        构建结果字典，包含：
        - success: 是否成功
        - total_concepts: 知识点总数
        - dependencies_built: 构建的依赖关系数量
        - message: 结果消息
    """
    from database import db
    from generator import OpenRouterClient
    import httpx
    import json
    
    print(f"[依赖构建] 开始为教材 {textbook_id} 构建知识点依赖关系...")
    
    # 获取教材信息
    textbook = db.get_textbook(textbook_id)
    if not textbook:
        return {
            "success": False,
            "total_concepts": 0,
            "dependencies_built": 0,
            "message": "教材不存在"
        }
    
    textbook_name = textbook.get("name", "")
    
    # 获取教材下的所有知识点
    knowledge_nodes = db.get_textbook_knowledge_nodes(textbook_id)
    if not knowledge_nodes:
        return {
            "success": False,
            "total_concepts": 0,
            "dependencies_built": 0,
            "message": "教材下没有知识点，请先进行知识提取"
        }
    
    total_concepts = len(knowledge_nodes)
    print(f"[依赖构建] 教材 '{textbook_name}' 共有 {total_concepts} 个知识点")
    
    # 如果没有提供 API 配置，从数据库读取
    if not api_key or not model or not api_endpoint:
        ai_config = db.get_ai_config()
        if not api_key:
            api_key = ai_config.get("api_key")
        if not model:
            model = ai_config.get("model", "openai/gpt-4o-mini")
        if not api_endpoint:
            api_endpoint = ai_config.get("api_endpoint", "https://openrouter.ai/api/v1/chat/completions")
    
    # 检查 API key 是否配置
    if not api_key:
        error_msg = "API key 未配置，无法构建依赖关系"
        print(f"[依赖构建] ✗ {error_msg}")
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg + "，请在系统设置中配置 OpenRouter API key"
        }
    
    # 构建知识点列表（用于 LLM 分析）
    concepts_list = []
    for node in knowledge_nodes:
        concept_info = {
            "node_id": node["node_id"],
            "core_concept": node["core_concept"],
            "bloom_level": node.get("bloom_level", 3),
            "confusion_points": node.get("confusion_points", []),
            "application_scenarios": node.get("application_scenarios", [])
        }
        concepts_list.append(concept_info)
    
    # 构建提示词
    system_prompt = """你是一位资深的计算机科学教育专家，专门从事计算机教材的知识点依赖关系分析工作。你的任务是分析教材中所有知识点之间的依赖关系，确定哪些知识点是其他知识点的前置依赖。

**重要原则**：
1. **依赖关系的定义**：如果学习知识点 A 之前必须先掌握知识点 B，则 B 是 A 的前置依赖（prerequisite）。
2. **依赖关系应该是明确的、必要的**：只有当知识点 A 的学习确实需要知识点 B 的基础时，才建立依赖关系。
3. **避免过度依赖**：不要为每个知识点都建立大量依赖关系，只建立最核心、最必要的依赖。
4. **依赖关系应该是教材内的**：只分析提供的知识点列表中的知识点之间的依赖关系，不要引入外部知识点。
5. **依赖关系应该是有向的**：如果 A 依赖 B，则 B 不依赖 A（避免循环依赖）。

请仔细分析提供的知识点列表，为每个知识点确定其前置依赖知识点（prerequisites）。前置依赖应该是：
- 在学习当前知识点之前必须掌握的基础知识点
- 与当前知识点有明确的逻辑关系
- 属于同一教材的知识点

请严格按照以下 JSON 格式返回，不要添加任何额外的文本、说明或代码块标记：

```json
{
  "dependencies": [
    {
      "node_id": "节点ID（必须）",
      "core_concept": "知识点名称（可选，用于验证）",
      "prerequisites": ["前置知识点1", "前置知识点2", ...]
    },
    ...
  ]
}
```

**重要**：
- 每个依赖项必须包含 `node_id` 字段，该字段应该与上述知识点列表中的 `node_id` 完全匹配
- `prerequisites` 数组中的每个元素应该是上述知识点列表中的 `core_concept`（知识点名称）
- 如果某个知识点没有前置依赖，`prerequisites` 应该为空数组 `[]`
- 必须返回所有知识点的依赖关系，不能遗漏任何知识点
```"""

    concepts_text = "\n".join([
        f"{idx + 1}. {concept['core_concept']} (node_id: {concept['node_id']}, Bloom Level: {concept['bloom_level']})"
        for idx, concept in enumerate(concepts_list)
    ])
    
    user_prompt = f"""请分析以下教材 "{textbook_name}" 中的所有知识点，构建它们之间的依赖关系。

**知识点列表：**
{concepts_text}

**要求：**
1. **必须返回所有知识点的依赖关系**：返回的 `dependencies` 数组必须包含上述列表中的每一个知识点，不能遗漏任何知识点。
2. 为每个知识点确定其前置依赖知识点（prerequisites）
3. 前置依赖必须是上述列表中的知识点（使用 `core_concept` 名称）
4. 只建立必要的、明确的依赖关系
5. 避免循环依赖
6. 如果某个知识点没有前置依赖，prerequisites 应该为空数组 `[]`
7. **每个依赖项必须包含 `node_id` 字段**，该字段必须与上述知识点列表中的 `node_id` 完全匹配

**重要**：请确保返回的 `dependencies` 数组包含所有 {total_concepts} 个知识点，不能遗漏任何知识点。"""
    
    # 创建 OpenRouter 客户端
    client = OpenRouterClient(api_key=api_key, model=model, api_endpoint=api_endpoint)
    
    # 调用 LLM API
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-repo",
        "X-Title": "AI Question Generator",
    }
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    payload = {
        "model": client.model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4000,
    }
    
    dependencies_built = 0
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            response = await http_client.post(
                client.api_endpoint,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 提取生成的文本
            if "choices" not in result or len(result["choices"]) == 0:
                error_msg = "API 返回结果中没有 choices 字段"
                print(f"[依赖构建] ✗ {error_msg}")
                return {
                    "success": False,
                    "total_concepts": total_concepts,
                    "dependencies_built": 0,
                    "message": error_msg
                }
            
            generated_text = result["choices"][0]["message"]["content"].strip()
            
            # 清理可能的代码块标记
            if generated_text.startswith("```json"):
                generated_text = generated_text[7:].strip()
            elif generated_text.startswith("```"):
                generated_text = generated_text[3:].strip()
            
            if generated_text.endswith("```"):
                generated_text = generated_text[:-3].strip()
            
            # 解析 JSON
            try:
                dependencies_data = json.loads(generated_text)
                
                print(f"[依赖构建] JSON 解析成功，返回的数据结构: {list(dependencies_data.keys())}")
                
                if "dependencies" not in dependencies_data:
                    error_msg = f"API 返回结果中没有 dependencies 字段。返回的字段: {list(dependencies_data.keys())}"
                    print(f"[依赖构建] ✗ {error_msg}")
                    print(f"[依赖构建] 完整响应: {json.dumps(dependencies_data, ensure_ascii=False, indent=2)[:2000]}")
                    return {
                        "success": False,
                        "total_concepts": total_concepts,
                        "dependencies_built": 0,
                        "message": error_msg
                    }
                
                # 构建 node_id 到概念的映射
                node_id_to_concept = {node["node_id"]: node["core_concept"] for node in knowledge_nodes}
                concept_to_node_id = {node["core_concept"]: node["node_id"] for node in knowledge_nodes}
                
                dependencies_list = dependencies_data.get("dependencies", [])
                print(f"[依赖构建] 收到 {len(dependencies_list)} 个知识点的依赖关系（期望 {total_concepts} 个）")
                print(f"[依赖构建] 知识点映射: {len(concept_to_node_id)} 个知识点")
                
                if len(dependencies_list) < total_concepts:
                    print(f"[依赖构建] ⚠ 警告：返回的依赖关系数量 ({len(dependencies_list)}) 少于知识点总数 ({total_concepts})")
                
                # 记录已处理的 node_id，确保没有遗漏
                processed_node_ids = set()
                
                # 更新数据库中的依赖关系
                for dep_info in dependencies_list:
                    node_id = dep_info.get("node_id")
                    core_concept = dep_info.get("core_concept")
                    prerequisites = dep_info.get("prerequisites", [])
                    
                    # 如果提供了 core_concept 但没有 node_id，通过 core_concept 查找 node_id
                    if not node_id and core_concept:
                        node_id = concept_to_node_id.get(core_concept.strip())
                        if not node_id:
                            print(f"[依赖构建] ⚠ 警告：找不到知识点 '{core_concept}' 对应的 node_id，跳过")
                            continue
                    elif not node_id:
                        print(f"[依赖构建] ⚠ 警告：依赖信息中既没有 node_id 也没有 core_concept，跳过")
                        continue
                    
                    # 验证 node_id 是否存在
                    if node_id not in node_id_to_concept:
                        print(f"[依赖构建] ⚠ 警告：node_id '{node_id}' 不在教材知识点列表中，跳过")
                        continue
                    
                    actual_concept = node_id_to_concept[node_id]
                    
                    # 验证 prerequisites 中的知识点是否存在于教材中
                    valid_prerequisites = []
                    for prereq_concept in prerequisites:
                        prereq_concept = prereq_concept.strip()
                        if prereq_concept in concept_to_node_id:
                            valid_prerequisites.append(prereq_concept)
                        else:
                            print(f"[依赖构建] ⚠ 警告：前置依赖 '{prereq_concept}' 不在教材知识点列表中，已忽略")
                    
                    # 更新数据库（即使 prerequisites 为空也要更新，确保清空旧的依赖关系）
                    try:
                        success = db.update_knowledge_node_prerequisites(node_id, valid_prerequisites)
                        if success:
                            dependencies_built += 1
                            processed_node_ids.add(node_id)
                            if valid_prerequisites:
                                print(f"[依赖构建] ✓ 更新知识点 '{actual_concept}' (node_id: {node_id}) 的依赖关系: {len(valid_prerequisites)} 个前置依赖")
                            else:
                                print(f"[依赖构建] ✓ 更新知识点 '{actual_concept}' (node_id: {node_id}) 的依赖关系: 无前置依赖（已清空）")
                        else:
                            print(f"[依赖构建] ✗ 更新知识点 '{actual_concept}' (node_id: {node_id}) 的依赖关系失败（数据库更新返回 False）")
                    except Exception as e:
                        print(f"[依赖构建] ✗ 更新知识点 '{actual_concept}' (node_id: {node_id}) 的依赖关系时发生异常: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 检查是否有遗漏的知识点
                all_node_ids = set(node["node_id"] for node in knowledge_nodes)
                missing_node_ids = all_node_ids - processed_node_ids
                if missing_node_ids:
                    print(f"[依赖构建] ⚠ 警告：有 {len(missing_node_ids)} 个知识点没有被处理:")
                    for missing_node_id in missing_node_ids:
                        missing_concept = node_id_to_concept.get(missing_node_id, "未知")
                        print(f"[依赖构建]   - {missing_concept} (node_id: {missing_node_id})")
                
                # 重新加载知识图谱
                try:
                    from graph_manager import knowledge_graph
                    knowledge_graph.reload()
                    print(f"[依赖构建] ✓ 知识图谱已重新加载，当前节点数: {knowledge_graph.graph.number_of_nodes()}")
                except Exception as e:
                    print(f"[依赖构建] ⚠ 警告：重新加载知识图谱失败: {e}")
                
                message = f"成功为 {dependencies_built} 个知识点构建了依赖关系（共 {total_concepts} 个知识点）"
                print(f"[依赖构建] ✓ {message}")
                
                return {
                    "success": True,
                    "total_concepts": total_concepts,
                    "dependencies_built": dependencies_built,
                    "message": message
                }
                
            except json.JSONDecodeError as e:
                error_msg = f"JSON 解析失败: {e}"
                print(f"[依赖构建] ✗ {error_msg}")
                print(f"[依赖构建] 原始响应前1000字符:\n{generated_text[:1000]}")
                return {
                    "success": False,
                    "total_concepts": total_concepts,
                    "dependencies_built": 0,
                    "message": error_msg
                }
                
    except httpx.HTTPStatusError as e:
        error_msg = f"API 调用失败，状态码: {e.response.status_code}"
        print(f"[依赖构建] ✗ {error_msg}")
        print(f"[依赖构建] 响应内容: {e.response.text[:500]}")
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg
        }
    except httpx.RequestError as e:
        error_msg = f"API 请求失败: {str(e)}"
        print(f"[依赖构建] ✗ {error_msg}")
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg
        }
    except Exception as e:
        error_msg = f"构建依赖关系失败: {str(e)}"
        print(f"[依赖构建] ✗ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "total_concepts": total_concepts,
            "dependencies_built": 0,
            "message": error_msg
        }


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
    from md_processor import SemanticSplitter
    
    # 如果没有提供目录树，尝试从 chunks 中提取
    if toc_tree is None:
        # 需要从第一个 chunk 的 metadata 中获取 source 信息来读取文件
        # 但这里我们假设可以从 chunks 的 metadata 中重建目录树
        # 实际上，我们需要使用 SemanticSplitter 来提取目录树
        # 为了简化，我们直接从 chunks 的 metadata 中提取章节信息
        pass
    
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

