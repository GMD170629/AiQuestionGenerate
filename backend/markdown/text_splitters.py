"""
文本分割器模块
包含代码块、图片、公式感知的文本分割器
"""

import re
from typing import List, Tuple


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

