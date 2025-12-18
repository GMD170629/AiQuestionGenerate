"""
Markdown 解析引擎
功能：读取 Markdown 文件，按标题层级切分，保留代码块，进行文本切片
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Tuple

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
    
    def __init__(self, chunk_size: int = 1200, chunk_overlap: int = 200, max_tokens_before_split: int = 1500):
        """
        初始化处理器
        
        Args:
            chunk_size: 每个 chunk 的最大字符数（默认 1200）
            chunk_overlap: chunk 之间的重叠字符数（默认 200）
            max_tokens_before_split: 触发二次切片的最大 tokens 数（默认 1500）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_tokens_before_split = max_tokens_before_split
        
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

