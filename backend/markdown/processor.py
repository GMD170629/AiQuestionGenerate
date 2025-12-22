"""
Markdown 处理器主模块
处理 Markdown 文件的解析和切分
"""

import re
from pathlib import Path
from typing import List, Dict, Any

try:
    from langchain.text_splitter import MarkdownHeaderTextSplitter
except ImportError:
    try:
        from langchain_text_splitters import MarkdownHeaderTextSplitter
    except ImportError:
        raise ImportError(
            "无法导入 LangChain 文本分割器。请确保已安装 langchain 或 langchain-text-splitters。"
        )

from .text_splitters import CodeBlockAwareSplitter
from .toc_extractor import SemanticSplitter


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

