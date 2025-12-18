#!/usr/bin/env python3
"""
测试脚本：提取 Markdown 文件的目录树结构
仅用于验证目录树提取逻辑是否正确
"""

import sys
from pathlib import Path

from md_processor import MarkdownProcessor


def print_tree(nodes, indent=0):
    """递归打印目录树结构"""
    for node in nodes:
        prefix = "  " * indent
        level_marker = "├─" if indent > 0 else "─"
        print(f"{prefix}{level_marker} [{node.level}] {node.title}")
        print(f"{prefix}    type: {node.section_type}, lines: {node.line_number}-{node.end_line_number}")
        
        if node.children:
            print_tree(node.children, indent + 1)


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
        
        # 提取目录树
        toc_tree = processor.extract_toc_tree(content)
        
        if not toc_tree:
            print("❌ 未找到任何目录节点")
            return
        
        print(f"✅ 成功提取目录树，共 {len(toc_tree)} 个根节点")
        print()
        print("目录树结构（前50个节点）：")
        print("-" * 80)
        
        # 扁平化并打印前50个节点
        def flatten_nodes(nodes, result=None):
            if result is None:
                result = []
            for node in nodes:
                result.append(node)
                if node.children:
                    flatten_nodes(node.children, result)
            return result
        
        flat_nodes = flatten_nodes(toc_tree)
        for i, node in enumerate(flat_nodes[:50]):
            indent = node.level - 1
            prefix = "  " * indent
            print(f"{prefix}[{node.level}] {node.title}")
        
        if len(flat_nodes) > 50:
            print(f"... (还有 {len(flat_nodes) - 50} 个节点)")
        
        print("-" * 80)
        print()
        
        # 检查特定节点
        print("检查特定节点关系：")
        print("-" * 80)
        
        # 查找 3.2 节点
        nodes_3_2 = find_node_by_title(toc_tree, "3.2")
        # 过滤掉 3.2.1, 3.2.2 等
        nodes_3_2 = [n for n in nodes_3_2 if n.title.startswith("3.2 ") or n.title == "3.2"]
        
        if nodes_3_2:
            for node_3_2 in nodes_3_2:
                print(f"找到节点: {node_3_2.title} (level={node_3_2.level})")
                print(f"  子节点数量: {len(node_3_2.children)}")
                if node_3_2.children:
                    print("  子节点列表:")
                    for child in node_3_2.children[:10]:  # 只显示前10个
                        print(f"    - {child.title} (level={child.level})")
                    if len(node_3_2.children) > 10:
                        print(f"    ... (还有 {len(node_3_2.children) - 10} 个子节点)")
                else:
                    print("  ⚠️  没有子节点！")
                print()
        else:
            print("❌ 未找到 '3.2' 节点")
            print()
        
        # 查找 3.2.1、3.2.2、3.2.3 节点
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
    # 测试文件路径（相对于 backend 目录）
    test_file = "../第3章 如何获取用户的真实需求 v2.md"
    
    if not Path(test_file).exists():
        print(f"❌ 文件不存在: {test_file}")
        print("请确保文件在项目根目录下")
        sys.exit(1)
    
    test_toc_extraction(test_file)

