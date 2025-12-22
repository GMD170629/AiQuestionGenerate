"""
数据库迁移脚本
用于更新现有数据库结构以支持新的知识点层级模型
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional


def migrate_knowledge_nodes_schema(db_path: str = "data/question_generator.db") -> bool:
    """
    迁移 knowledge_nodes 表结构，添加 level 和 parent_id 字段
    
    Args:
        db_path: 数据库文件路径
        
    Returns:
        是否成功迁移
    """
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"数据库文件不存在: {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 检查是否已经迁移过（检查 level 字段是否存在）
        cursor.execute("PRAGMA table_info(knowledge_nodes)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "level" in columns and "parent_id" in columns:
            print("数据库已经包含 level 和 parent_id 字段，跳过迁移")
            conn.close()
            return True
        
        print("开始迁移 knowledge_nodes 表...")
        
        # 1. 添加 level 字段（默认为 3，表示三级原子点）
        if "level" not in columns:
            print("添加 level 字段...")
            cursor.execute("""
                ALTER TABLE knowledge_nodes 
                ADD COLUMN level INTEGER NOT NULL DEFAULT 3 CHECK(level >= 1 AND level <= 3)
            """)
            print("✓ level 字段添加成功")
        
        # 2. 添加 parent_id 字段
        if "parent_id" not in columns:
            print("添加 parent_id 字段...")
            cursor.execute("""
                ALTER TABLE knowledge_nodes 
                ADD COLUMN parent_id TEXT
            """)
            print("✓ parent_id 字段添加成功")
        
        # 3. 添加外键约束（SQLite 不支持 ALTER TABLE ADD FOREIGN KEY，需要重建表）
        # 由于 SQLite 的限制，我们只能添加索引，外键约束在创建表时已经定义
        # 对于现有表，我们需要手动检查数据完整性
        
        # 4. 创建索引
        print("创建索引...")
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_level 
                ON knowledge_nodes(level)
            """)
            print("✓ level 索引创建成功")
        except sqlite3.OperationalError:
            print("  level 索引已存在，跳过")
        
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_parent_id 
                ON knowledge_nodes(parent_id)
            """)
            print("✓ parent_id 索引创建成功")
        except sqlite3.OperationalError:
            print("  parent_id 索引已存在，跳过")
        
        # 5. 创建 knowledge_dependencies 表（如果不存在）
        print("创建 knowledge_dependencies 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_dependencies (
                dependency_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                dependency_type TEXT NOT NULL DEFAULT 'depends_on',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_node_id) REFERENCES knowledge_nodes(node_id) ON DELETE CASCADE,
                FOREIGN KEY (target_node_id) REFERENCES knowledge_nodes(node_id) ON DELETE CASCADE,
                UNIQUE(source_node_id, target_node_id)
            )
        """)
        print("✓ knowledge_dependencies 表创建成功")
        
        # 6. 创建依赖关系表的索引
        print("创建依赖关系表索引...")
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_dependencies_source 
                ON knowledge_dependencies(source_node_id)
            """)
            print("✓ source_node_id 索引创建成功")
        except sqlite3.OperationalError:
            print("  source_node_id 索引已存在，跳过")
        
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_dependencies_target 
                ON knowledge_dependencies(target_node_id)
            """)
            print("✓ target_node_id 索引创建成功")
        except sqlite3.OperationalError:
            print("  target_node_id 索引已存在，跳过")
        
        conn.commit()
        print("✓ 数据库迁移完成")
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ 数据库迁移失败: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def clean_old_test_data(db_path: str = "data/question_generator.db") -> int:
    """
    清理旧的扁平化知识点测试数据
    
    删除所有 level 为 3 且没有 parent_id 的孤立知识点节点（可能是测试数据）
    注意：此操作会删除数据，请谨慎使用
    
    Args:
        db_path: 数据库文件路径
        
    Returns:
        删除的记录数
    """
    db_file = Path(db_path)
    if not db_file.exists():
        print(f"数据库文件不存在: {db_path}")
        return 0
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 检查表结构
        cursor.execute("PRAGMA table_info(knowledge_nodes)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "level" not in columns:
            print("数据库尚未迁移，无法清理旧数据")
            conn.close()
            return 0
        
        # 统计要删除的数据
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM knowledge_nodes
            WHERE level = 3 AND parent_id IS NULL
        """)
        count = cursor.fetchone()["count"]
        
        if count == 0:
            print("没有需要清理的旧测试数据")
            conn.close()
            return 0
        
        print(f"发现 {count} 条可能的旧测试数据（level=3 且 parent_id=NULL）")
        print("注意：此操作会删除数据，如需保留请先备份数据库")
        
        # 询问确认（在实际使用中，可以通过参数控制）
        # 这里我们提供一个安全的选项：只删除没有依赖关系的孤立节点
        cursor.execute("""
            DELETE FROM knowledge_nodes
            WHERE node_id IN (
                SELECT kn.node_id
                FROM knowledge_nodes kn
                LEFT JOIN knowledge_dependencies kd1 ON kn.node_id = kd1.source_node_id
                LEFT JOIN knowledge_dependencies kd2 ON kn.node_id = kd2.target_node_id
                WHERE kn.level = 3 
                  AND kn.parent_id IS NULL
                  AND kd1.source_node_id IS NULL
                  AND kd2.target_node_id IS NULL
            )
        """)
        
        deleted_count = cursor.rowcount
        conn.commit()
        print(f"✓ 已删除 {deleted_count} 条孤立的旧测试数据")
        conn.close()
        return deleted_count
        
    except Exception as e:
        print(f"✗ 清理旧数据失败: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return 0


def run_migrations(db_path: str = "data/question_generator.db", clean_test_data: bool = False) -> bool:
    """
    运行所有数据库迁移
    
    Args:
        db_path: 数据库文件路径
        clean_test_data: 是否清理旧测试数据
        
    Returns:
        是否成功
    """
    print("=" * 60)
    print("开始数据库迁移")
    print("=" * 60)
    
    # 1. 迁移表结构
    success = migrate_knowledge_nodes_schema(db_path)
    if not success:
        print("✗ 表结构迁移失败，终止迁移")
        return False
    
    # 2. 清理旧测试数据（可选）
    if clean_test_data:
        print("\n" + "=" * 60)
        print("清理旧测试数据")
        print("=" * 60)
        deleted_count = clean_old_test_data(db_path)
        print(f"清理完成，删除了 {deleted_count} 条记录")
    
    print("\n" + "=" * 60)
    print("数据库迁移完成")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    import sys
    
    # 从命令行参数读取配置
    clean_data = "--clean" in sys.argv
    
    success = run_migrations(clean_test_data=clean_data)
    sys.exit(0 if success else 1)

