"""
目录提取器模块
包含目录树节点和基于语义的文本分割器
"""

import re
from typing import List, Dict, Any, Tuple


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

