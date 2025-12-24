#!/usr/bin/env python3
"""
数据库重置脚本
检查数据库表结构，如果与代码定义不符，删除所有表并重建
一次性执行脚本，不需要集成到系统中
"""

import sqlite3
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple


# 期望的表结构定义（从 database.py 中提取）
EXPECTED_TABLES = {
    "files": {
        "columns": ["file_id", "filename", "file_size", "file_format", "file_path", "upload_time", "created_at"],
        "primary_key": "file_id",
        "create_sql": """
            CREATE TABLE files (
                file_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_format TEXT NOT NULL,
                file_path TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
    },
    "chunks": {
        "columns": ["chunk_id", "file_id", "chunk_index", "content", "metadata_json", "created_at"],
        "primary_key": "chunk_id",
        "create_sql": """
            CREATE TABLE chunks (
                chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
                UNIQUE(file_id, chunk_index)
            )
        """
    },
    "file_metadata": {
        "columns": ["file_id", "metadata_json", "cached_at"],
        "primary_key": "file_id",
        "create_sql": """
            CREATE TABLE file_metadata (
                file_id TEXT PRIMARY KEY,
                metadata_json TEXT NOT NULL,
                cached_at TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE
            )
        """
    },
    "questions": {
        "columns": ["question_id", "file_id", "question_type", "stem", "options_json", "answer", 
                   "explain", "code_snippet", "test_cases_json", "difficulty", "chapter", 
                   "source_file", "textbook_id", "file_path", "created_at"],
        "primary_key": "question_id",
        "create_sql": """
            CREATE TABLE questions (
                question_id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT NOT NULL,
                question_type TEXT NOT NULL,
                stem TEXT NOT NULL,
                options_json TEXT,
                answer TEXT NOT NULL,
                explain TEXT NOT NULL,
                code_snippet TEXT,
                test_cases_json TEXT,
                difficulty TEXT NOT NULL,
                chapter TEXT,
                source_file TEXT,
                textbook_id TEXT,
                file_path TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE
            )
        """
    },
    "tasks": {
        "columns": ["task_id", "textbook_id", "status", "progress", "current_file", 
                   "total_files", "created_at", "updated_at", "error_message"],
        "primary_key": "task_id",
        "create_sql": """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                textbook_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                progress REAL NOT NULL DEFAULT 0.0,
                current_file TEXT,
                total_files INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (textbook_id) REFERENCES textbooks(textbook_id) ON DELETE CASCADE
            )
        """
    },
    "textbooks": {
        "columns": ["textbook_id", "name", "description", "created_at", "updated_at"],
        "primary_key": "textbook_id",
        "create_sql": """
            CREATE TABLE textbooks (
                textbook_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
    },
    "textbook_files": {
        "columns": ["textbook_id", "file_id", "display_order", "created_at"],
        "primary_key": ("textbook_id", "file_id"),
        "create_sql": """
            CREATE TABLE textbook_files (
                textbook_id TEXT NOT NULL,
                file_id TEXT NOT NULL,
                display_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (textbook_id, file_id),
                FOREIGN KEY (textbook_id) REFERENCES textbooks(textbook_id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE
            )
        """
    },
    "chapters": {
        "columns": ["chapter_id", "file_id", "name", "level", "section_type", 
                   "parent_id", "display_order", "created_at"],
        "primary_key": "chapter_id",
        "create_sql": """
            CREATE TABLE chapters (
                chapter_id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                name TEXT NOT NULL,
                level INTEGER NOT NULL,
                section_type TEXT,
                parent_id TEXT,
                display_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE
            )
        """
    },
    "chapter_chunks": {
        "columns": ["chapter_id", "chunk_id", "created_at"],
        "primary_key": ("chapter_id", "chunk_id"),
        "create_sql": """
            CREATE TABLE chapter_chunks (
                chapter_id TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chapter_id, chunk_id),
                FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE,
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
            )
        """
    },
    "knowledge_nodes": {
        "columns": ["node_id", "chunk_id", "file_id", "core_concept", "level", "parent_id",
                   "prerequisites_json", "confusion_points_json", "bloom_level", 
                   "application_scenarios_json", "created_at"],
        "primary_key": "node_id",
        "create_sql": """
            CREATE TABLE knowledge_nodes (
                node_id TEXT PRIMARY KEY,
                chunk_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                core_concept TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 3 CHECK(level >= 1 AND level <= 3),  -- 已废弃：不再使用层级结构
                parent_id TEXT,  -- 已废弃：不再使用层级结构
                prerequisites_json TEXT NOT NULL DEFAULT '[]',
                confusion_points_json TEXT NOT NULL DEFAULT '[]',
                bloom_level INTEGER NOT NULL CHECK(bloom_level >= 1 AND bloom_level <= 6),
                application_scenarios_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
                FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES knowledge_nodes(node_id) ON DELETE SET NULL
            )
        """
    },
    "knowledge_dependencies": {
        "columns": ["dependency_id", "source_node_id", "target_node_id", "dependency_type", "created_at"],
        "primary_key": "dependency_id",
        "create_sql": """
            CREATE TABLE knowledge_dependencies (
                dependency_id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                dependency_type TEXT NOT NULL DEFAULT 'depends_on',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_node_id) REFERENCES knowledge_nodes(node_id) ON DELETE CASCADE,
                FOREIGN KEY (target_node_id) REFERENCES knowledge_nodes(node_id) ON DELETE CASCADE,
                UNIQUE(source_node_id, target_node_id)
            )
        """
    },
    "ai_config": {
        "columns": ["config_id", "api_endpoint", "api_key", "model", "updated_at"],
        "primary_key": "config_id",
        "create_sql": """
            CREATE TABLE ai_config (
                config_id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_endpoint TEXT NOT NULL DEFAULT 'https://openrouter.ai/api/v1/chat/completions',
                api_key TEXT,
                model TEXT NOT NULL DEFAULT 'openai/gpt-4o-mini',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(config_id)
            )
        """
    }
}

# 期望的索引定义
EXPECTED_INDEXES = [
    ("idx_chunks_file_id", "chunks", "file_id"),
    ("idx_chunks_file_chunk", "chunks", "file_id, chunk_index"),
    ("idx_questions_file_id", "questions", "file_id"),
    ("idx_questions_type", "questions", "question_type"),
    ("idx_questions_created_at", "questions", "created_at"),
    ("idx_textbook_files_textbook", "textbook_files", "textbook_id"),
    ("idx_textbook_files_file", "textbook_files", "file_id"),
    ("idx_tasks_textbook_id", "tasks", "textbook_id"),
    ("idx_tasks_status", "tasks", "status"),
    ("idx_questions_textbook_id", "questions", "textbook_id"),
    ("idx_chapters_file_id", "chapters", "file_id"),
    ("idx_chapters_parent_id", "chapters", "parent_id"),
    ("idx_chapter_chunks_chapter", "chapter_chunks", "chapter_id"),
    ("idx_chapter_chunks_chunk", "chapter_chunks", "chunk_id"),
    ("idx_knowledge_nodes_chunk_id", "knowledge_nodes", "chunk_id"),
    ("idx_knowledge_nodes_file_id", "knowledge_nodes", "file_id"),
    ("idx_knowledge_nodes_bloom_level", "knowledge_nodes", "bloom_level"),
    # 已废弃的索引（level 和 parent_id 字段不再使用）
    # ("idx_knowledge_nodes_level", "knowledge_nodes", "level"),
    # ("idx_knowledge_nodes_parent_id", "knowledge_nodes", "parent_id"),
    ("idx_knowledge_dependencies_source", "knowledge_dependencies", "source_node_id"),
    ("idx_knowledge_dependencies_target", "knowledge_dependencies", "target_node_id"),
]


def get_actual_schema(conn: sqlite3.Connection) -> Dict[str, Dict]:
    """获取实际数据库表结构"""
    cursor = conn.cursor()
    schema = {}
    
    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    rows = cursor.fetchall()
    tables = [row["name"] if isinstance(row, sqlite3.Row) else row[0] for row in rows]
    
    for table_name in tables:
        # 获取表的所有列信息
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_info = cursor.fetchall()
        
        columns = []
        primary_key = None
        for col_info in columns_info:
            # PRAGMA table_info 返回: cid, name, type, notnull, dflt_value, pk
            col_name = col_info["name"] if isinstance(col_info, sqlite3.Row) else col_info[1]
            pk_flag = col_info["pk"] if isinstance(col_info, sqlite3.Row) else col_info[5]
            columns.append(col_name)
            if pk_flag == 1:  # pk 字段
                if primary_key is None:
                    primary_key = col_name
                else:
                    # 复合主键
                    primary_key = (primary_key, col_name)
        
        schema[table_name] = {
            "columns": columns,
            "primary_key": primary_key
        }
    
    return schema


def compare_schemas(expected: Dict[str, Dict], actual: Dict[str, Dict]) -> Tuple[bool, List[str]]:
    """比较期望和实际的表结构"""
    differences = []
    is_match = True
    
    # 检查表是否存在
    expected_tables = set(expected.keys())
    actual_tables = set(actual.keys())
    
    missing_tables = expected_tables - actual_tables
    extra_tables = actual_tables - expected_tables
    
    if missing_tables:
        is_match = False
        differences.append(f"缺少表: {', '.join(missing_tables)}")
    
    if extra_tables:
        is_match = False
        differences.append(f"多余的表: {', '.join(extra_tables)}")
    
    # 检查每个表的列
    common_tables = expected_tables & actual_tables
    for table_name in common_tables:
        expected_cols = set(expected[table_name]["columns"])
        actual_cols = set(actual[table_name]["columns"])
        
        missing_cols = expected_cols - actual_cols
        extra_cols = actual_cols - expected_cols
        
        if missing_cols:
            is_match = False
            differences.append(f"表 {table_name} 缺少列: {', '.join(missing_cols)}")
        
        if extra_cols:
            is_match = False
            differences.append(f"表 {table_name} 多余列: {', '.join(extra_cols)}")
    
    return is_match, differences


def drop_all_tables(conn: sqlite3.Connection):
    """删除所有表"""
    cursor = conn.cursor()
    
    # 禁用外键约束
    cursor.execute("PRAGMA foreign_keys = OFF")
    
    # 获取所有表名
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    rows = cursor.fetchall()
    tables = [row["name"] if isinstance(row, sqlite3.Row) else row[0] for row in rows]
    
    print(f"正在删除 {len(tables)} 个表...")
    for table_name in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            print(f"  ✓ 删除表: {table_name}")
        except sqlite3.OperationalError as e:
            print(f"  ✗ 删除表 {table_name} 失败: {e}")
    
    # 重新启用外键约束
    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()


def create_all_tables(conn: sqlite3.Connection):
    """创建所有表"""
    cursor = conn.cursor()
    
    # 按依赖顺序创建表
    table_order = [
        "files",
        "chunks",
        "file_metadata",
        "textbooks",
        "textbook_files",
        "questions",
        "tasks",
        "chapters",
        "chapter_chunks",
        "knowledge_nodes",
        "knowledge_dependencies",
        "ai_config"
    ]
    
    print(f"正在创建 {len(table_order)} 个表...")
    for table_name in table_order:
        if table_name not in EXPECTED_TABLES:
            continue
        
        try:
            create_sql = EXPECTED_TABLES[table_name]["create_sql"].strip()
            cursor.execute(create_sql)
            print(f"  ✓ 创建表: {table_name}")
        except sqlite3.OperationalError as e:
            print(f"  ✗ 创建表 {table_name} 失败: {e}")
            raise
    
    conn.commit()


def create_all_indexes(conn: sqlite3.Connection):
    """创建所有索引"""
    cursor = conn.cursor()
    
    print(f"正在创建 {len(EXPECTED_INDEXES)} 个索引...")
    for index_name, table_name, columns in EXPECTED_INDEXES:
        try:
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {index_name} 
                ON {table_name}({columns})
            """)
            print(f"  ✓ 创建索引: {index_name}")
        except sqlite3.OperationalError as e:
            print(f"  ✗ 创建索引 {index_name} 失败: {e}")


def initialize_ai_config(conn: sqlite3.Connection):
    """初始化 AI 配置表"""
    cursor = conn.cursor()
    
    # 检查是否已有配置
    cursor.execute("SELECT COUNT(*) as count FROM ai_config")
    row = cursor.fetchone()
    if row and row[0] > 0:
        print("  AI 配置表已有数据，跳过初始化")
        return
    
    # 从配置模块读取默认值
    from datetime import datetime
    from app.core.config import settings
    default_api_key = settings.openrouter_api_key
    default_model = settings.openrouter_model
    default_endpoint = settings.openrouter_api_endpoint
    
    cursor.execute("""
        INSERT INTO ai_config (api_endpoint, api_key, model, updated_at)
        VALUES (?, ?, ?, ?)
    """, (default_endpoint, default_api_key, default_model, datetime.now().isoformat()))
    
    conn.commit()
    print("  ✓ 初始化 AI 配置表")


def reset_database(db_path: str = "data/question_generator.db", force: bool = False):
    """
    重置数据库：检查表结构，如果不符则删除所有表并重建
    
    Args:
        db_path: 数据库文件路径
        force: 是否强制重置（即使结构匹配也重置）
    """
    db_file = Path(db_path)
    
    if not db_file.exists():
        print(f"数据库文件不存在: {db_path}")
        print("将创建新的数据库...")
        db_file.parent.mkdir(parents=True, exist_ok=True)
        force = True  # 新数据库需要创建所有表
    
    print("=" * 60)
    print("数据库结构检查和重置")
    print("=" * 60)
    print(f"数据库路径: {db_path}")
    print()
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    
    try:
        # 获取实际表结构
        print("正在检查数据库表结构...")
        actual_schema = get_actual_schema(conn)
        
        if not force and actual_schema:
            # 比较表结构
            is_match, differences = compare_schemas(EXPECTED_TABLES, actual_schema)
            
            if is_match:
                print("✓ 数据库表结构与代码定义完全匹配，无需重置")
                return
            
            print("✗ 数据库表结构与代码定义不匹配:")
            for diff in differences:
                print(f"  - {diff}")
            print()
        elif force:
            print("强制重置模式：将删除所有表并重建")
            print()
        else:
            print("数据库为空，将创建所有表")
            print()
        
        # 确认重置
        if not force:
            response = input("是否删除所有表并重建？(yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("已取消重置操作")
                return
        
        # 执行重置
        print()
        print("=" * 60)
        print("开始重置数据库")
        print("=" * 60)
        
        # 1. 删除所有表
        drop_all_tables(conn)
        print()
        
        # 2. 创建所有表
        create_all_tables(conn)
        print()
        
        # 3. 创建所有索引
        create_all_indexes(conn)
        print()
        
        # 4. 初始化 AI 配置
        initialize_ai_config(conn)
        print()
        
        print("=" * 60)
        print("数据库重置完成！")
        print("=" * 60)
        
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    # 解析命令行参数
    db_path = "data/question_generator.db"
    force = False
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    if "--force" in sys.argv or "-f" in sys.argv:
        force = True
    
    reset_database(db_path, force=force)

