#!/usr/bin/env python3
"""
测试脚本：提取 Markdown 文件的目录树结构
直接读取本地文件并测试（不依赖 Docker）
"""

import sys
from pathlib import Path

# 添加 backend 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "backend"))

# 模拟 langchain 导入（测试时不需要实际使用）
class MockMarkdownHeaderTextSplitter:
    def __init__(self, *args, **kwargs):
        pass
    
    def split_text(self, text):
        return []

class MockRecursiveCharacterTextSplitter:
    def __init__(self, *args, **kwargs):
        pass

sys.modules['langchain.text_splitter'] = type(sys)('langchain.text_splitter')
sys.modules['langchain.text_splitter'].MarkdownHeaderTextSplitter = MockMarkdownHeaderTextSplitter
sys.modules['langchain.text_splitter'].RecursiveCharacterTextSplitter = MockRecursiveCharacterTextSplitter

try:
    sys.modules['langchain_text_splitters'] = type(sys)('langchain_text_splitters')
    sys.modules['langchain_text_splitters'].MarkdownHeaderTextSplitter = MockMarkdownHeaderTextSplitter
    sys.modules['langchain_text_splitters'].RecursiveCharacterTextSplitter = MockRecursiveCharacterTextSplitter
except:
    pass

from md_processor import MarkdownProcessor


def print_tree(nodes, indent=0, max_nodes=50):
    """递归打印目录树结构"""
    count = [0]
    
    def _print(nodes, indent):
        for node in nodes:
            if count[0] >= max_nodes:
                return
            prefix = "  " * indent
            level_marker = "├─" if indent > 0 else "─"
            print(f"{prefix}{level_marker} [{node.level}] {node.title}")
            count[0] += 1
            if node.children and count[0] < max_nodes:
                _print(node.children, indent + 1)
    
    _print(nodes, indent)
    if count[0] >= max_nodes:
        print("  ... (更多节点)")


def find_node_by_title(nodes, title_pattern):
    """查找包含特定标题模式的节点"""
    results = []
    for node in nodes:
        if title_pattern in node.title:
            results.append(node)
        if node.children:
            results.extend(find_node_by_title(node.children, title_pattern))
    return results


def find_parent(nodes, target_node, parent=None):
    """查找节点的父节点"""
    for node in nodes:
        if node == target_node:
            return parent
        if node.children:
            result = find_parent(node.children, target_node, node)
            if result is not None:
                return result
    return None


def test_toc_extraction(file_path: str):
    """测试目录树提取"""
    print("=" * 80)
    print(f"测试文件: {file_path}")
    print("=" * 80)
    print()
    
    try:
        processor = MarkdownProcessor()
        
        # 读取文件内容
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"文件读取成功，内容长度: {len(content)} 字符")
        print()
        
        # 提取目录树（使用 SemanticSplitter）
        toc_tree = processor.semantic_splitter.extract_toc_tree(content)
        
        if not toc_tree:
            print("❌ 未找到任何目录节点")
            return
        
        print(f"✅ 成功提取目录树，共 {len(toc_tree)} 个根节点")
        print()
        print("目录树结构（前50个节点）：")
        print("-" * 80)
        print_tree(toc_tree, max_nodes=50)
        print("-" * 80)
        print()
        
        # 统计总节点数
        def count_nodes(nodes):
            total = len(nodes)
            for node in nodes:
                if node.children:
                    total += count_nodes(node.children)
            return total
        
        total_nodes = count_nodes(toc_tree)
        print(f"总节点数: {total_nodes}")
        print()
        
        # 检查特定节点
        print("检查特定节点关系：")
        print("-" * 80)
        
        # 查找 3.2 节点（排除 3.2.1, 3.2.2 等）
        nodes_3_2 = find_node_by_title(toc_tree, "3.2")
        nodes_3_2_filtered = [n for n in nodes_3_2 if n.title.startswith("3.2 ") or n.title == "3.2"]
        
        if nodes_3_2_filtered:
            for node_3_2 in nodes_3_2_filtered:
                print(f"找到节点: {node_3_2.title} (level={node_3_2.level})")
                print(f"  子节点数量: {len(node_3_2.children)}")
                if node_3_2.children:
                    print("  子节点列表（前20个）:")
                    for child in node_3_2.children[:20]:
                        print(f"    - {child.title} (level={child.level})")
                    if len(node_3_2.children) > 20:
                        print(f"    ... (还有 {len(node_3_2.children) - 20} 个子节点)")
                else:
                    print("  ⚠️  没有子节点！")
                print()
        else:
            print("❌ 未找到 '3.2' 节点")
            print(f"   但找到了 {len(nodes_3_2)} 个包含 '3.2' 的节点")
            for n in nodes_3_2[:5]:
                print(f"     - {n.title} (level={n.level})")
            print()
        
        # 查找 3.2.1、3.2.2、3.2.3 节点
        print("查找 3.2.1, 3.2.2, 3.2.3 节点:")
        print("-" * 80)
        for sub_title in ["3.2.1", "3.2.2", "3.2.3"]:
            nodes_sub = find_node_by_title(toc_tree, sub_title)
            if nodes_sub:
                for node_sub in nodes_sub:
                    print(f"找到节点: {node_sub.title} (level={node_sub.level})")
                    parent = find_parent(toc_tree, node_sub)
                    if parent:
                        print(f"  父节点: {parent.title} (level={parent.level})")
                        if parent.title.startswith("3.2") and not parent.title.startswith("3.2."):
                            print(f"  ✅ 正确归类到 3.2 之下")
                        else:
                            print(f"  ⚠️  父节点不是 3.2，而是: {parent.title}")
                    else:
                        print(f"  ⚠️  没有找到父节点")
                    print()
            else:
                print(f"❌ 未找到 '{sub_title}' 节点")
                print()
        
        # 检查特殊段落
        print("检查特殊段落：")
        print("-" * 80)
        special_sections = ["思考题", "参考文献"]
        for section_name in special_sections:
            nodes_special = find_node_by_title(toc_tree, section_name)
            if nodes_special:
                print(f"✅ 找到 '{section_name}' 节点:")
                for node in nodes_special:
                    print(f"  - {node.title} (level={node.level}, type={node.section_type})")
            else:
                print(f"❌ 未找到 '{section_name}' 节点")
            print()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 测试文件路径
    test_file = "第3章 如何获取用户的真实需求 v2.md"
    
    if not Path(test_file).exists():
        print(f"❌ 文件不存在: {test_file}")
        print("请确保文件在当前目录下")
        sys.exit(1)
    
    test_toc_extraction(test_file)

