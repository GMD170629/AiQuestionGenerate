"""
数据库模块
使用 SQLite 持久化存储文件信息和解析后的分片数据
"""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from contextlib import contextmanager


class Database:
    """数据库管理器"""
    
    def __init__(self, db_path: str = "data/question_generator.db"):
        """
        初始化数据库
        
        Args:
            db_path: 数据库文件路径（相对于工作目录）
        """
        self.db_path = Path(db_path)
        # 确保数据库目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 文件信息表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_format TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    upload_time TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 文档分片表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
                    UNIQUE(file_id, chunk_index)
                )
            """)
            
            # 文档元数据表（存储 toc、statistics 等）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_metadata (
                    file_id TEXT PRIMARY KEY,
                    metadata_json TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE
                )
            """)
            
            # 题目表（存储生成的题目）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS questions (
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
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE
                )
            """)
            
            # 任务表（存储生成任务）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
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
            """)
            
            # 如果表已存在，检查并添加新列（用于升级现有数据库）
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='questions'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(questions)")
                columns = [row[1] for row in cursor.fetchall()]
                
                # 添加 explain 列（如果不存在）
                if 'explain' not in columns:
                    try:
                        cursor.execute("ALTER TABLE questions ADD COLUMN explain TEXT")
                    except sqlite3.OperationalError:
                        pass
                
                # 添加 test_cases_json 列（如果不存在）
                if 'test_cases_json' not in columns:
                    try:
                        cursor.execute("ALTER TABLE questions ADD COLUMN test_cases_json TEXT")
                    except sqlite3.OperationalError:
                        pass
                
                # 添加 textbook_id 列（如果不存在）
                if 'textbook_id' not in columns:
                    try:
                        cursor.execute("ALTER TABLE questions ADD COLUMN textbook_id TEXT")
                    except sqlite3.OperationalError:
                        pass
                
                # 添加 file_path 列（如果不存在）
                if 'file_path' not in columns:
                    try:
                        cursor.execute("ALTER TABLE questions ADD COLUMN file_path TEXT")
                    except sqlite3.OperationalError:
                        pass
            
            # 教材表（存储教材信息）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS textbooks (
                    textbook_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 文件-教材关联表（多对多关系）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS textbook_files (
                    textbook_id TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    display_order INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (textbook_id, file_id),
                    FOREIGN KEY (textbook_id) REFERENCES textbooks(textbook_id) ON DELETE CASCADE,
                    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE
                )
            """)
            
            # 章节表（存储教材章节信息）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapters (
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
            """)
            
            # 章节-切片关联表（多对多关系）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chapter_chunks (
                    chapter_id TEXT NOT NULL,
                    chunk_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chapter_id, chunk_id),
                    FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id) ON DELETE CASCADE,
                    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE
                )
            """)
            
            # 知识点节点表（存储从切片中提取的知识点语义信息）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_nodes (
                    node_id TEXT PRIMARY KEY,
                    chunk_id INTEGER NOT NULL,
                    file_id TEXT NOT NULL,
                    core_concept TEXT NOT NULL,
                    level INTEGER NOT NULL DEFAULT 3 CHECK(level >= 1 AND level <= 3),
                    parent_id TEXT,
                    prerequisites_json TEXT NOT NULL DEFAULT '[]',
                    confusion_points_json TEXT NOT NULL DEFAULT '[]',
                    bloom_level INTEGER NOT NULL CHECK(bloom_level >= 1 AND bloom_level <= 6),
                    application_scenarios_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id) ON DELETE CASCADE,
                    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
                    FOREIGN KEY (parent_id) REFERENCES knowledge_nodes(node_id) ON DELETE SET NULL
                )
            """)
            
            # 知识点依赖关系表（存储横向依赖关系：同级或跨级）
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
            
            # AI配置表（存储API端点、密钥和模型）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_config (
                    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_endpoint TEXT NOT NULL DEFAULT 'https://openrouter.ai/api/v1/chat/completions',
                    api_key TEXT,
                    model TEXT NOT NULL DEFAULT 'openai/gpt-4o-mini',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(config_id)
                )
            """)
            
            # 初始化默认配置（如果表为空）
            cursor.execute("SELECT COUNT(*) as count FROM ai_config")
            if cursor.fetchone()["count"] == 0:
                # 从环境变量读取默认值
                import os
                default_api_key = os.getenv("OPENROUTER_API_KEY", "")
                default_model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
                default_endpoint = "https://openrouter.ai/api/v1/chat/completions"
                cursor.execute("""
                    INSERT INTO ai_config (api_endpoint, api_key, model, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (default_endpoint, default_api_key, default_model, datetime.now().isoformat()))
            
            # 先运行数据库迁移（如果表已存在，迁移会添加新字段）
            # 必须在创建索引之前运行，确保所有列都存在
            self._run_migrations(conn)
            
            # 创建索引以提高查询性能
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks(file_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_file_chunk ON chunks(file_id, chunk_index)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_questions_file_id ON questions(file_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(question_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_questions_created_at ON questions(created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_textbook_files_textbook ON textbook_files(textbook_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_textbook_files_file ON textbook_files(file_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_textbook_id ON tasks(textbook_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_questions_textbook_id ON questions(textbook_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chapters_file_id ON chapters(file_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chapters_parent_id ON chapters(parent_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chapter_chunks_chapter ON chapter_chunks(chapter_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chapter_chunks_chunk ON chapter_chunks(chunk_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_chunk_id ON knowledge_nodes(chunk_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_file_id ON knowledge_nodes(file_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_bloom_level ON knowledge_nodes(bloom_level)
            """)
            # 这些索引依赖于迁移逻辑添加的列，所以必须在迁移之后创建
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_level ON knowledge_nodes(level)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_parent_id ON knowledge_nodes(parent_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_dependencies_source ON knowledge_dependencies(source_node_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_knowledge_dependencies_target ON knowledge_dependencies(target_node_id)
            """)
            
            conn.commit()
    
    def _run_migrations(self, conn):
        """
        运行数据库迁移（在初始化时调用）
        
        Args:
            conn: 数据库连接
        """
        cursor = conn.cursor()
        
        try:
            # 检查 knowledge_nodes 表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_nodes'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                # 检查表结构，获取现有字段
                cursor.execute("PRAGMA table_info(knowledge_nodes)")
                rows = cursor.fetchall()
                # 使用 Row 对象的字典访问方式（因为连接已设置 row_factory = sqlite3.Row）
                columns = [row["name"] for row in rows]
                
                # 如果表存在但没有 level 字段，需要添加
                if "level" not in columns:
                    try:
                        cursor.execute("""
                            ALTER TABLE knowledge_nodes 
                            ADD COLUMN level INTEGER NOT NULL DEFAULT 3 CHECK(level >= 1 AND level <= 3)
                        """)
                    except sqlite3.OperationalError as e:
                        print(f"添加 level 字段失败（可能已存在）: {e}")
                
                # 如果表存在但没有 parent_id 字段，需要添加
                if "parent_id" not in columns:
                    try:
                        cursor.execute("""
                            ALTER TABLE knowledge_nodes 
                            ADD COLUMN parent_id TEXT
                        """)
                    except sqlite3.OperationalError as e:
                        print(f"添加 parent_id 字段失败（可能已存在）: {e}")
                
                # 注意：索引创建在 _init_database 方法中进行，这里只负责添加列
            
            # 确保 knowledge_dependencies 表存在
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
            
            # 注意：索引创建在 _init_database 方法中进行，这里只负责创建表
            
            conn.commit()
        except Exception as e:
            # 迁移失败不应该阻止数据库初始化
            print(f"数据库迁移警告: {e}")
            conn.rollback()
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 使用 Row 工厂，可以通过列名访问
        # 设置 text_factory 为 str，确保正确处理 Unicode 字符（包括中文）
        conn.text_factory = str
        # 启用外键约束
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()
    
    def store_file(self, file_id: str, filename: str, file_size: int, 
                   file_format: str, file_path: str, upload_time: str):
        """
        存储文件信息
        
        Args:
            file_id: 文件 ID
            filename: 原始文件名
            file_size: 文件大小（字节）
            file_format: 文件格式（如 .md）
            file_path: 文件存储路径
            upload_time: 上传时间（ISO 格式）
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO files 
                (file_id, filename, file_size, file_format, file_path, upload_time)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (file_id, filename, file_size, file_format, file_path, upload_time))
            conn.commit()
    
    def store_chunks(self, file_id: str, chunks: List[Dict[str, Any]]):
        """
        存储文档分片
        
        Args:
            file_id: 文件 ID
            chunks: 分片列表，每个分片包含 content 和 metadata
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 先删除旧的分片
            cursor.execute("DELETE FROM chunks WHERE file_id = ?", (file_id,))
            # 插入新分片
            for idx, chunk in enumerate(chunks):
                metadata_json = json.dumps(chunk.get("metadata", {}), ensure_ascii=False)
                # 确保 content 是 Unicode 字符串
                content = chunk.get("content", "")
                if isinstance(content, bytes):
                    content = content.decode('utf-8', errors='replace')
                elif not isinstance(content, str):
                    content = str(content)
                cursor.execute("""
                    INSERT INTO chunks (file_id, chunk_index, content, metadata_json)
                    VALUES (?, ?, ?, ?)
                """, (file_id, idx, content, metadata_json))
            conn.commit()
    
    def store_metadata(self, file_id: str, metadata: Dict[str, Any]):
        """
        存储文档元数据（toc、statistics 等）
        
        Args:
            file_id: 文件 ID
            metadata: 元数据字典
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            metadata_json = json.dumps(metadata, ensure_ascii=False)
            cached_at = datetime.now().isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO file_metadata 
                (file_id, metadata_json, cached_at)
                VALUES (?, ?, ?)
            """, (file_id, metadata_json, cached_at))
            conn.commit()
    
    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文件信息
        
        Args:
            file_id: 文件 ID
            
        Returns:
            文件信息字典，如果不存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE file_id = ?", (file_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_chunks(self, file_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取文档分片
        
        Args:
            file_id: 文件 ID
            
        Returns:
            分片列表，如果不存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chunk_index, content, metadata_json 
                FROM chunks 
                WHERE file_id = ? 
                ORDER BY chunk_index
            """, (file_id,))
            rows = cursor.fetchall()
            if not rows:
                return None
            
            chunks = []
            for row in rows:
                chunks.append({
                    "content": row["content"],
                    "metadata": json.loads(row["metadata_json"])
                })
            return chunks
    
    def get_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文档元数据
        
        Args:
            file_id: 文件 ID
            
        Returns:
            元数据字典，如果不存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT metadata_json FROM file_metadata WHERE file_id = ?
            """, (file_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row["metadata_json"])
            return None
    
    def get_all_files(self) -> List[Dict[str, Any]]:
        """
        获取所有文件信息列表
        
        Returns:
            文件信息列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_id, filename, file_size, file_format, 
                       file_path, upload_time, created_at
                FROM files 
                ORDER BY upload_time DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def delete_file(self, file_id: str) -> bool:
        """
        删除文件及其相关数据（分片、元数据）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否成功删除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 由于外键约束，删除文件会自动删除相关的 chunks 和 metadata
            cursor.execute("DELETE FROM files WHERE file_id = ?", (file_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def file_exists(self, file_id: str) -> bool:
        """
        检查文件是否存在
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否存在
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM files WHERE file_id = ?", (file_id,))
            return cursor.fetchone() is not None
    
    def store_complete_document(self, file_id: str, filename: str, file_size: int,
                                file_format: str, file_path: str, upload_time: str,
                                chunks: List[Dict[str, Any]], metadata: Dict[str, Any]):
        """
        存储完整的文档信息（文件信息 + 分片 + 元数据）
        这是一个便捷方法，用于一次性存储所有数据
        
        Args:
            file_id: 文件 ID
            filename: 原始文件名
            file_size: 文件大小
            file_format: 文件格式
            file_path: 文件路径
            upload_time: 上传时间
            chunks: 分片列表
            metadata: 元数据字典
        """
        self.store_file(file_id, filename, file_size, file_format, file_path, upload_time)
        self.store_chunks(file_id, chunks)
        self.store_metadata(file_id, metadata)
    
    def store_question(self, file_id: str, question: Dict[str, Any], 
                      source_file: Optional[str] = None,
                      textbook_id: Optional[str] = None,
                      file_path: Optional[str] = None):
        """
        存储单个题目
        
        Args:
            file_id: 文件 ID
            question: 题目字典，包含 type, stem, options, answer, explain, code_snippet, test_cases, difficulty, chapter
            source_file: 来源文件名（可选）
            textbook_id: 教材 ID（可选）
            file_path: 文件路径（可选）
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            options_json = json.dumps(question.get("options"), ensure_ascii=False) if question.get("options") else None
            created_at = datetime.now().isoformat()
            
            # 处理 explain 字段
            explain = question.get("explain", "")
            
            # 处理测试用例（如果是编程题）
            test_cases_json = None
            if question.get("type") == "编程题" and question.get("test_cases"):
                test_cases = question.get("test_cases")
                if isinstance(test_cases, dict):
                    test_cases_json = json.dumps(test_cases, ensure_ascii=False)
            
            cursor.execute("""
                INSERT INTO questions 
                (file_id, question_type, stem, options_json, answer, explain, 
                 code_snippet, test_cases_json, difficulty, chapter, source_file, 
                 textbook_id, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id,
                question.get("type"),
                question.get("stem"),
                options_json,
                question.get("answer"),
                explain,
                question.get("code_snippet"),
                test_cases_json,
                question.get("difficulty", "中等"),
                question.get("chapter"),
                source_file,
                textbook_id,
                file_path,
                created_at
            ))
            conn.commit()
    
    def store_questions(self, file_id: str, questions: List[Dict[str, Any]], 
                       source_file: Optional[str] = None,
                       textbook_id: Optional[str] = None,
                       file_path: Optional[str] = None):
        """
        批量存储题目
        
        Args:
            file_id: 文件 ID
            questions: 题目列表
            source_file: 来源文件名（可选）
            textbook_id: 教材 ID（可选）
            file_path: 文件路径（可选）
        """
        for question in questions:
            self.store_question(file_id, question, source_file, textbook_id, file_path)
    
    def get_all_questions(self, file_id: Optional[str] = None, 
                          question_type: Optional[str] = None,
                          textbook_id: Optional[str] = None,
                          limit: Optional[int] = None,
                          offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取题目列表（支持按文件、题型和教材筛选）
        
        Args:
            file_id: 文件 ID（可选，如果提供则只返回该文件的题目）
            question_type: 题型（可选，如果提供则只返回该题型的题目）
            textbook_id: 教材 ID（可选，如果提供则只返回该教材的题目）
            limit: 限制返回数量（可选）
            offset: 偏移量（用于分页）
            
        Returns:
            题目列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 构建查询条件
            conditions = []
            params = []
            
            if file_id:
                conditions.append("q.file_id = ?")
                params.append(file_id)
            
            if question_type:
                conditions.append("q.question_type = ?")
                params.append(question_type)
            
            if textbook_id:
                conditions.append("q.textbook_id = ?")
                params.append(textbook_id)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 构建查询语句
            query = f"""
                SELECT 
                    q.question_id,
                    q.file_id,
                    q.question_type,
                    q.stem,
                    q.options_json,
                    q.answer,
                    q.explain,
                    q.code_snippet,
                    q.test_cases_json,
                    q.difficulty,
                    q.chapter,
                    q.source_file,
                    q.created_at,
                    f.filename
                FROM questions q
                LEFT JOIN files f ON q.file_id = f.file_id
                {where_clause}
                ORDER BY q.created_at DESC
            """
            
            if limit:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            questions = []
            for row in rows:
                question = {
                    "question_id": row["question_id"],
                    "file_id": row["file_id"],
                    "type": row["question_type"],
                    "stem": row["stem"],
                    "answer": row["answer"],
                    "explain": row["explain"],
                    "code_snippet": row["code_snippet"],
                    "difficulty": row["difficulty"],
                    "chapter": row["chapter"],
                    "source_file": row["source_file"] or row["filename"],
                    "created_at": row["created_at"],
                }
                
                # 解析选项 JSON
                if row["options_json"]:
                    try:
                        question["options"] = json.loads(row["options_json"])
                    except:
                        question["options"] = []
                
                # 解析测试用例 JSON（编程题）
                if row["test_cases_json"]:
                    try:
                        question["test_cases"] = json.loads(row["test_cases_json"])
                    except:
                        question["test_cases"] = None
                
                questions.append(question)
            
            return questions
    
    def get_question_count(self, file_id: Optional[str] = None, 
                           question_type: Optional[str] = None,
                           textbook_id: Optional[str] = None) -> int:
        """
        获取题目总数（支持按文件、题型和教材筛选）
        
        Args:
            file_id: 文件 ID（可选）
            question_type: 题型（可选）
            textbook_id: 教材 ID（可选）
            
        Returns:
            题目总数
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if file_id:
                conditions.append("file_id = ?")
                params.append(file_id)
            
            if question_type:
                conditions.append("question_type = ?")
                params.append(question_type)
            
            if textbook_id:
                conditions.append("textbook_id = ?")
                params.append(textbook_id)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            cursor.execute(f"SELECT COUNT(*) as count FROM questions{where_clause}", params)
            row = cursor.fetchone()
            return row["count"] if row else 0
    
    def get_question_statistics(self) -> Dict[str, Any]:
        """
        获取题目统计信息
        
        Returns:
            包含题型分布、文件分布等统计信息的字典
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 题型统计
            cursor.execute("""
                SELECT question_type, COUNT(*) as count
                FROM questions
                GROUP BY question_type
            """)
            type_stats = {row["question_type"]: row["count"] for row in cursor.fetchall()}
            
            # 文件统计
            cursor.execute("""
                SELECT f.filename, COUNT(*) as count
                FROM questions q
                LEFT JOIN files f ON q.file_id = f.file_id
                GROUP BY q.file_id, f.filename
                ORDER BY count DESC
            """)
            file_stats = [{"filename": row["filename"] or "未知", "count": row["count"]} 
                         for row in cursor.fetchall()]
            
            # 总题目数
            cursor.execute("SELECT COUNT(*) as count FROM questions")
            total_count = cursor.fetchone()["count"]
            
            return {
                "total": total_count,
                "by_type": type_stats,
                "by_file": file_stats
            }
    
    def get_ai_config(self) -> Dict[str, Any]:
        """
        获取AI配置
        
        Returns:
            AI配置字典，包含 api_endpoint, api_key, model
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT api_endpoint, api_key, model, updated_at
                FROM ai_config
                ORDER BY config_id DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return {
                    "api_endpoint": row["api_endpoint"],
                    "api_key": row["api_key"] or "",
                    "model": row["model"],
                    "updated_at": row["updated_at"]
                }
            # 如果没有配置，返回默认值
            return {
                "api_endpoint": "https://openrouter.ai/api/v1/chat/completions",
                "api_key": "",
                "model": "openai/gpt-4o-mini",
                "updated_at": datetime.now().isoformat()
            }
    
    def update_ai_config(self, api_endpoint: str, api_key: str, model: str) -> bool:
        """
        更新AI配置
        
        Args:
            api_endpoint: API端点URL
            api_key: API密钥
            model: 模型名称
            
        Returns:
            是否成功更新
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 检查是否已有配置
            cursor.execute("SELECT COUNT(*) as count FROM ai_config")
            count = cursor.fetchone()["count"]
            
            if count > 0:
                # 更新现有配置
                cursor.execute("""
                    UPDATE ai_config
                    SET api_endpoint = ?, api_key = ?, model = ?, updated_at = ?
                    WHERE config_id = (SELECT config_id FROM ai_config ORDER BY config_id DESC LIMIT 1)
                """, (api_endpoint, api_key, model, datetime.now().isoformat()))
            else:
                # 插入新配置
                cursor.execute("""
                    INSERT INTO ai_config (api_endpoint, api_key, model, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (api_endpoint, api_key, model, datetime.now().isoformat()))
            
            conn.commit()
            return cursor.rowcount > 0
    
    # ========== 教材相关方法 ==========
    
    def create_textbook(self, textbook_id: str, name: str, description: Optional[str] = None) -> bool:
        """
        创建教材
        
        Args:
            textbook_id: 教材 ID
            name: 教材名称
            description: 教材描述（可选）
            
        Returns:
            是否成功创建
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            try:
                cursor.execute("""
                    INSERT INTO textbooks (textbook_id, name, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (textbook_id, name, description, now, now))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def get_textbook(self, textbook_id: str) -> Optional[Dict[str, Any]]:
        """
        获取教材信息
        
        Args:
            textbook_id: 教材 ID
            
        Returns:
            教材信息字典，如果不存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM textbooks WHERE textbook_id = ?", (textbook_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_all_textbooks(self) -> List[Dict[str, Any]]:
        """
        获取所有教材列表
        
        Returns:
            教材信息列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, COUNT(tf.file_id) as file_count
                FROM textbooks t
                LEFT JOIN textbook_files tf ON t.textbook_id = tf.textbook_id
                GROUP BY t.textbook_id
                ORDER BY t.updated_at DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_textbook(self, textbook_id: str, name: Optional[str] = None, 
                       description: Optional[str] = None) -> bool:
        """
        更新教材信息
        
        Args:
            textbook_id: 教材 ID
            name: 教材名称（可选）
            description: 教材描述（可选）
            
        Returns:
            是否成功更新
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            
            if not updates:
                return False
            
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(textbook_id)
            
            cursor.execute(f"""
                UPDATE textbooks
                SET {', '.join(updates)}
                WHERE textbook_id = ?
            """, params)
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_textbook(self, textbook_id: str) -> bool:
        """
        删除教材（会自动删除关联的文件关系）
        
        Args:
            textbook_id: 教材 ID
            
        Returns:
            是否成功删除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM textbooks WHERE textbook_id = ?", (textbook_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def add_file_to_textbook(self, textbook_id: str, file_id: str, display_order: int = 0) -> bool:
        """
        将文件添加到教材
        
        Args:
            textbook_id: 教材 ID
            file_id: 文件 ID
            display_order: 显示顺序
            
        Returns:
            是否成功添加
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                now = datetime.now().isoformat()
                cursor.execute("""
                    INSERT OR REPLACE INTO textbook_files (textbook_id, file_id, display_order, created_at)
                    VALUES (?, ?, ?, ?)
                """, (textbook_id, file_id, display_order, now))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def remove_file_from_textbook(self, textbook_id: str, file_id: str) -> bool:
        """
        从教材中移除文件
        
        Args:
            textbook_id: 教材 ID
            file_id: 文件 ID
            
        Returns:
            是否成功移除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM textbook_files 
                WHERE textbook_id = ? AND file_id = ?
            """, (textbook_id, file_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_textbook_files(self, textbook_id: str) -> List[Dict[str, Any]]:
        """
        获取教材中的所有文件
        
        Args:
            textbook_id: 教材 ID
            
        Returns:
            文件信息列表（按 display_order 排序）
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.*, tf.display_order
                FROM files f
                INNER JOIN textbook_files tf ON f.file_id = tf.file_id
                WHERE tf.textbook_id = ?
                ORDER BY tf.display_order ASC, f.upload_time ASC
            """, (textbook_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_file_textbooks(self, file_id: str) -> List[Dict[str, Any]]:
        """
        获取文件所属的所有教材
        
        Args:
            file_id: 文件 ID
            
        Returns:
            教材信息列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*
                FROM textbooks t
                INNER JOIN textbook_files tf ON t.textbook_id = tf.textbook_id
                WHERE tf.file_id = ?
                ORDER BY t.updated_at DESC
            """, (file_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_file_order_in_textbook(self, textbook_id: str, file_id: str, display_order: int) -> bool:
        """
        更新文件在教材中的显示顺序
        
        Args:
            textbook_id: 教材 ID
            file_id: 文件 ID
            display_order: 新的显示顺序
            
        Returns:
            是否成功更新
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE textbook_files
                SET display_order = ?
                WHERE textbook_id = ? AND file_id = ?
            """, (display_order, textbook_id, file_id))
            conn.commit()
            return cursor.rowcount > 0
    
    # ========== 任务相关方法 ==========
    # 注意：这些方法是同步的，可以在 FastAPI 的 BackgroundTasks 中使用
    # 如果需要真正的异步操作，可以考虑使用 aiosqlite 库
    
    def create_task(self, task_id: str, textbook_id: str, total_files: int = 0) -> bool:
        """
        创建生成任务
        
        Args:
            task_id: 任务 ID
            textbook_id: 教材 ID
            total_files: 总文件数
            
        Returns:
            是否成功创建
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            try:
                cursor.execute("""
                    INSERT INTO tasks (task_id, textbook_id, status, progress, total_files, created_at, updated_at)
                    VALUES (?, ?, 'PENDING', 0.0, ?, ?, ?)
                """, (task_id, textbook_id, total_files, now, now))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务信息
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务信息字典，如果不存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_all_tasks(self, textbook_id: Optional[str] = None, 
                     status: Optional[str] = None,
                     limit: Optional[int] = None,
                     offset: int = 0) -> List[Dict[str, Any]]:
        """
        获取所有任务列表（支持按教材和状态筛选）
        
        Args:
            textbook_id: 教材 ID（可选）
            status: 任务状态（可选）
            limit: 限制返回数量（可选）
            offset: 偏移量（用于分页）
            
        Returns:
            任务列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 构建查询条件
            conditions = []
            params = []
            
            if textbook_id:
                conditions.append("textbook_id = ?")
                params.append(textbook_id)
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 构建查询语句
            query = f"""
                SELECT t.*, tb.name as textbook_name
                FROM tasks t
                LEFT JOIN textbooks tb ON t.textbook_id = tb.textbook_id
                {where_clause}
                ORDER BY t.created_at DESC
            """
            
            if limit:
                query += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_task_status(self, task_id: str, status: str, 
                          error_message: Optional[str] = None) -> bool:
        """
        更新任务状态
        
        Args:
            task_id: 任务 ID
            status: 新状态（PENDING, PROCESSING, COMPLETED, FAILED）
            error_message: 错误消息（可选，仅在失败时使用）
            
        Returns:
            是否成功更新
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            if error_message:
                cursor.execute("""
                    UPDATE tasks
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE task_id = ?
                """, (status, error_message, now, task_id))
            else:
                cursor.execute("""
                    UPDATE tasks
                    SET status = ?, updated_at = ?
                    WHERE task_id = ?
                """, (status, now, task_id))
            
            conn.commit()
            return cursor.rowcount > 0
    
    def update_task_progress(self, task_id: str, progress: float, 
                            current_file: Optional[str] = None) -> bool:
        """
        更新任务进度
        
        Args:
            task_id: 任务 ID
            progress: 进度值（0.0-1.0 之间的浮点数）
            current_file: 当前处理的文件（可选）
            
        Returns:
            是否成功更新
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            # 确保进度在 0.0-1.0 之间
            progress = max(0.0, min(1.0, progress))
            
            if current_file:
                cursor.execute("""
                    UPDATE tasks
                    SET progress = ?, current_file = ?, updated_at = ?
                    WHERE task_id = ?
                """, (progress, current_file, now, task_id))
            else:
                cursor.execute("""
                    UPDATE tasks
                    SET progress = ?, updated_at = ?
                    WHERE task_id = ?
                """, (progress, now, task_id))
            
            conn.commit()
            return cursor.rowcount > 0
    
    def update_task(self, task_id: str, status: Optional[str] = None,
                   progress: Optional[float] = None,
                   current_file: Optional[str] = None,
                   total_files: Optional[int] = None,
                   error_message: Optional[str] = None) -> bool:
        """
        更新任务信息（综合方法）
        
        Args:
            task_id: 任务 ID
            status: 任务状态（可选）
            progress: 进度值（可选）
            current_file: 当前处理的文件（可选）
            total_files: 总文件数（可选）
            error_message: 错误消息（可选）
            
        Returns:
            是否成功更新
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            updates = []
            params = []
            
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            
            if progress is not None:
                # 确保进度在 0.0-1.0 之间
                progress = max(0.0, min(1.0, progress))
                updates.append("progress = ?")
                params.append(progress)
            
            if current_file is not None:
                updates.append("current_file = ?")
                params.append(current_file)
            
            if total_files is not None:
                updates.append("total_files = ?")
                params.append(total_files)
            
            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            
            if not updates:
                return False
            
            updates.append("updated_at = ?")
            params.append(now)
            params.append(task_id)
            
            cursor.execute(f"""
                UPDATE tasks
                SET {', '.join(updates)}
                WHERE task_id = ?
            """, params)
            
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功删除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_textbook_tasks(self, textbook_id: str) -> List[Dict[str, Any]]:
        """
        获取教材的所有任务
        
        Args:
            textbook_id: 教材 ID
            
        Returns:
            任务列表
        """
        return self.get_all_tasks(textbook_id=textbook_id)
    
    # ========== 章节相关方法 ==========
    
    def store_chapters(self, file_id: str, chapters: List[Dict[str, Any]]):
        """
        存储章节信息（包括层级关系和切片关联）
        
        Args:
            file_id: 文件 ID
            chapters: 章节列表，每个章节包含：
                - chapter_id: 章节 ID（可选，如果不提供则自动生成）
                - name: 章节名称
                - level: 层级
                - section_type: 章节类型
                - parent_id: 父章节 ID（可选）
                - display_order: 显示顺序
                - chunk_ids: 关联的切片 ID 列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 先删除该文件的所有章节和关联关系
            cursor.execute("DELETE FROM chapter_chunks WHERE chapter_id IN (SELECT chapter_id FROM chapters WHERE file_id = ?)", (file_id,))
            cursor.execute("DELETE FROM chapters WHERE file_id = ?", (file_id,))
            
            # 插入章节
            for chapter_data in chapters:
                # 如果提供了 chapter_id，使用它；否则生成新的
                chapter_id = chapter_data.get("chapter_id")
                if not chapter_id:
                    chapter_id = str(uuid.uuid4())
                
                name = chapter_data.get("name", "")
                level = chapter_data.get("level", 1)
                section_type = chapter_data.get("section_type")
                parent_id = chapter_data.get("parent_id")
                display_order = chapter_data.get("display_order", 0)
                chunk_ids = chapter_data.get("chunk_ids", [])
                
                cursor.execute("""
                    INSERT INTO chapters (chapter_id, file_id, name, level, section_type, parent_id, display_order, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (chapter_id, file_id, name, level, section_type, parent_id, display_order, datetime.now().isoformat()))
                
                # 插入章节-切片关联
                for chunk_id in chunk_ids:
                    cursor.execute("""
                        INSERT INTO chapter_chunks (chapter_id, chunk_id, created_at)
                        VALUES (?, ?, ?)
                    """, (chapter_id, chunk_id, datetime.now().isoformat()))
            
            conn.commit()
    
    def get_file_chapters(self, file_id: str) -> List[Dict[str, Any]]:
        """
        获取文件的所有章节（树形结构）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            章节列表（包含子章节信息）
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取所有章节
            cursor.execute("""
                SELECT chapter_id, file_id, name, level, section_type, parent_id, display_order, created_at
                FROM chapters
                WHERE file_id = ?
                ORDER BY level ASC, display_order ASC
            """, (file_id,))
            chapters = [dict(row) for row in cursor.fetchall()]
            
            # 获取每个章节关联的切片 ID
            for chapter in chapters:
                chapter_id = chapter["chapter_id"]
                cursor.execute("""
                    SELECT chunk_id
                    FROM chapter_chunks
                    WHERE chapter_id = ?
                    ORDER BY chunk_id ASC
                """, (chapter_id,))
                chunk_ids = [row["chunk_id"] for row in cursor.fetchall()]
                chapter["chunk_ids"] = chunk_ids
            
            return chapters
    
    def get_chapter_tree(self, file_id: str) -> List[Dict[str, Any]]:
        """
        获取文件的章节树（层级结构）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            章节树列表（根节点列表，每个节点包含 children）
        """
        chapters = self.get_file_chapters(file_id)
        
        # 构建章节字典（以 chapter_id 为键）
        chapter_dict = {ch["chapter_id"]: {**ch, "children": []} for ch in chapters}
        
        # 构建树形结构
        root_chapters = []
        for chapter in chapters:
            chapter_id = chapter["chapter_id"]
            parent_id = chapter.get("parent_id")
            
            if parent_id and parent_id in chapter_dict:
                # 有父节点，添加到父节点的 children
                chapter_dict[parent_id]["children"].append(chapter_dict[chapter_id])
            else:
                # 根节点
                root_chapters.append(chapter_dict[chapter_id])
        
        # 对每个层级的 children 按 display_order 排序
        def sort_children(node):
            node["children"].sort(key=lambda x: (x["level"], x["display_order"]))
            for child in node["children"]:
                sort_children(child)
        
        for root in root_chapters:
            sort_children(root)
        
        return root_chapters
    
    def get_chapter(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        """
        获取单个章节信息
        
        Args:
            chapter_id: 章节 ID
            
        Returns:
            章节信息字典，如果不存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chapter_id, file_id, name, level, section_type, parent_id, display_order, created_at
                FROM chapters
                WHERE chapter_id = ?
            """, (chapter_id,))
            row = cursor.fetchone()
            if row:
                chapter = dict(row)
                # 获取关联的切片 ID
                cursor.execute("""
                    SELECT chunk_id
                    FROM chapter_chunks
                    WHERE chapter_id = ?
                    ORDER BY chunk_id ASC
                """, (chapter_id,))
                chunk_ids = [row["chunk_id"] for row in cursor.fetchall()]
                chapter["chunk_ids"] = chunk_ids
                return chapter
            return None
    
    def get_chapter_chunks(self, chapter_id: str) -> List[Dict[str, Any]]:
        """
        获取章节关联的所有切片
        
        Args:
            chapter_id: 章节 ID
            
        Returns:
            切片列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.chunk_id, c.file_id, c.chunk_index, c.content, c.metadata_json
                FROM chunks c
                INNER JOIN chapter_chunks cc ON c.chunk_id = cc.chunk_id
                WHERE cc.chapter_id = ?
                ORDER BY c.chunk_index ASC
            """, (chapter_id,))
            rows = cursor.fetchall()
            chunks = []
            for row in rows:
                chunks.append({
                    "chunk_id": row["chunk_id"],
                    "file_id": row["file_id"],
                    "chunk_index": row["chunk_index"],
                    "content": row["content"],
                    "metadata": json.loads(row["metadata_json"])
                })
            return chunks
    
    def delete_file_chapters(self, file_id: str) -> bool:
        """
        删除文件的所有章节（包括关联关系）
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否成功删除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 删除章节-切片关联
            cursor.execute("DELETE FROM chapter_chunks WHERE chapter_id IN (SELECT chapter_id FROM chapters WHERE file_id = ?)", (file_id,))
            # 删除章节
            cursor.execute("DELETE FROM chapters WHERE file_id = ?", (file_id,))
            conn.commit()
            return True
    
    # ========== 知识点节点相关方法 ==========
    
    def store_knowledge_node(self, node_id: str, chunk_id: int, file_id: str,
                            core_concept: str, prerequisites: List[str],
                            confusion_points: List[str], bloom_level: int,
                            application_scenarios: Optional[List[str]] = None) -> bool:
        """
        存储知识点节点
        
        Args:
            node_id: 节点 ID
            chunk_id: 关联的切片 ID
            file_id: 所属文件 ID
            core_concept: 核心概念
            prerequisites: 前置依赖知识点列表（已废弃，保留用于兼容）
            confusion_points: 学生易错点列表
            bloom_level: Bloom 认知层级（1-6）
            application_scenarios: 应用场景列表（可选）
            
        Returns:
            是否成功存储
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            prerequisites_json = json.dumps(prerequisites, ensure_ascii=False)
            confusion_points_json = json.dumps(confusion_points, ensure_ascii=False)
            application_scenarios_json = json.dumps(application_scenarios, ensure_ascii=False) if application_scenarios else None
            
            try:
                # level 和 parent_id 字段保留在数据库中但不再使用，使用默认值
                cursor.execute("""
                    INSERT OR REPLACE INTO knowledge_nodes 
                    (node_id, chunk_id, file_id, core_concept, level, parent_id,
                     prerequisites_json, confusion_points_json, bloom_level, 
                     application_scenarios_json, created_at)
                    VALUES (?, ?, ?, ?, 3, NULL, ?, ?, ?, ?, ?)
                """, (node_id, chunk_id, file_id, core_concept,
                      prerequisites_json, confusion_points_json, bloom_level, 
                      application_scenarios_json, now))
                conn.commit()
                return True
            except sqlite3.IntegrityError as e:
                print(f"存储知识点节点失败: {e}")
                return False
    
    def get_knowledge_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        获取知识点节点信息
        
        Args:
            node_id: 节点 ID
            
        Returns:
            知识点节点信息字典，如果不存在则返回 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id, chunk_id, file_id, core_concept, level, parent_id,
                       prerequisites_json, confusion_points_json, bloom_level, 
                       application_scenarios_json, created_at
                FROM knowledge_nodes
                WHERE node_id = ?
            """, (node_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "node_id": row["node_id"],
                    "chunk_id": row["chunk_id"],
                    "file_id": row["file_id"],
                    "core_concept": row["core_concept"],
                    "prerequisites": json.loads(row["prerequisites_json"]) if "prerequisites_json" in row and row["prerequisites_json"] else [],
                    "confusion_points": json.loads(row["confusion_points_json"]) if "confusion_points_json" in row and row["confusion_points_json"] else [],
                    "bloom_level": row["bloom_level"],
                    "application_scenarios": json.loads(row["application_scenarios_json"]) if "application_scenarios_json" in row and row["application_scenarios_json"] else None,
                    "created_at": row["created_at"]
                }
            return None
    
    def get_chunk_knowledge_nodes(self, chunk_id: int) -> List[Dict[str, Any]]:
        """
        获取切片关联的所有知识点节点
        
        Args:
            chunk_id: 切片 ID
            
        Returns:
            知识点节点列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id, chunk_id, file_id, core_concept, level, parent_id,
                       prerequisites_json, confusion_points_json, bloom_level, 
                       application_scenarios_json, created_at
                FROM knowledge_nodes
                WHERE chunk_id = ?
                ORDER BY created_at ASC
            """, (chunk_id,))
            rows = cursor.fetchall()
            nodes = []
            for row in rows:
                nodes.append({
                    "node_id": row["node_id"],
                    "chunk_id": row["chunk_id"],
                    "file_id": row["file_id"],
                    "core_concept": row["core_concept"],
                    "prerequisites": json.loads(row["prerequisites_json"]) if "prerequisites_json" in row.keys() and row["prerequisites_json"] else [],
                    "confusion_points": json.loads(row["confusion_points_json"]) if "confusion_points_json" in row.keys() and row["confusion_points_json"] else [],
                    "bloom_level": row["bloom_level"],
                    "application_scenarios": json.loads(row["application_scenarios_json"]) if "application_scenarios_json" in row.keys() and row["application_scenarios_json"] else None,
                    "created_at": row["created_at"]
                })
            return nodes
    
    def get_file_knowledge_nodes(self, file_id: str) -> List[Dict[str, Any]]:
        """
        获取文件的所有知识点节点
        
        Args:
            file_id: 文件 ID
            
        Returns:
            知识点节点列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id, chunk_id, file_id, core_concept, level, parent_id,
                       prerequisites_json, confusion_points_json, bloom_level, 
                       application_scenarios_json, created_at
                FROM knowledge_nodes
                WHERE file_id = ?
                ORDER BY created_at ASC
            """, (file_id,))
            rows = cursor.fetchall()
            nodes = []
            for row in rows:
                nodes.append({
                    "node_id": row["node_id"],
                    "chunk_id": row["chunk_id"],
                    "file_id": row["file_id"],
                    "core_concept": row["core_concept"],
                    "prerequisites": json.loads(row["prerequisites_json"]) if "prerequisites_json" in row.keys() and row["prerequisites_json"] else [],
                    "confusion_points": json.loads(row["confusion_points_json"]) if "confusion_points_json" in row.keys() and row["confusion_points_json"] else [],
                    "bloom_level": row["bloom_level"],
                    "application_scenarios": json.loads(row["application_scenarios_json"]) if "application_scenarios_json" in row.keys() and row["application_scenarios_json"] else None,
                    "created_at": row["created_at"]
                })
            return nodes
    
    def delete_knowledge_node(self, node_id: str) -> bool:
        """
        删除知识点节点
        
        Args:
            node_id: 节点 ID
            
        Returns:
            是否成功删除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_file_knowledge_nodes(self, file_id: str) -> bool:
        """
        删除文件的所有知识点节点
        
        Args:
            file_id: 文件 ID
            
        Returns:
            是否成功删除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM knowledge_nodes WHERE file_id = ?", (file_id,))
            conn.commit()
            return True
    
    def get_textbook_knowledge_nodes(self, textbook_id: str) -> List[Dict[str, Any]]:
        """
        获取教材下所有文件的知识点节点
        
        Args:
            textbook_id: 教材 ID
            
        Returns:
            知识点节点列表
        """
        # 先获取教材下的所有文件
        files = self.get_textbook_files(textbook_id)
        if not files:
            return []
        
        # 获取所有文件的知识点
        file_ids = [file["file_id"] for file in files]
        placeholders = ",".join(["?"] * len(file_ids))
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT node_id, chunk_id, file_id, core_concept, level, parent_id,
                       prerequisites_json, confusion_points_json, bloom_level, 
                       application_scenarios_json, created_at
                FROM knowledge_nodes
                WHERE file_id IN ({placeholders})
                ORDER BY created_at ASC
            """, file_ids)
            rows = cursor.fetchall()
            nodes = []
            for row in rows:
                nodes.append({
                    "node_id": row["node_id"],
                    "chunk_id": row["chunk_id"],
                    "file_id": row["file_id"],
                    "core_concept": row["core_concept"],
                    "prerequisites": json.loads(row["prerequisites_json"]) if "prerequisites_json" in row.keys() and row["prerequisites_json"] else [],
                    "confusion_points": json.loads(row["confusion_points_json"]) if "confusion_points_json" in row.keys() and row["confusion_points_json"] else [],
                    "bloom_level": row["bloom_level"],
                    "application_scenarios": json.loads(row["application_scenarios_json"]) if "application_scenarios_json" in row.keys() and row["application_scenarios_json"] else None,
                    "created_at": row["created_at"]
                })
            return nodes
    
    def update_knowledge_node_prerequisites(self, node_id: str, prerequisites: List[str]) -> bool:
        """
        更新知识点节点的前置依赖（已废弃，保留用于兼容）
        建议使用 add_knowledge_dependency 方法
        
        Args:
            node_id: 节点 ID
            prerequisites: 前置依赖知识点列表
            
        Returns:
            是否成功更新
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            prerequisites_json = json.dumps(prerequisites, ensure_ascii=False)
            cursor.execute("""
                UPDATE knowledge_nodes
                SET prerequisites_json = ?
                WHERE node_id = ?
            """, (prerequisites_json, node_id))
            conn.commit()
            return cursor.rowcount > 0
    
    # ========== 知识点依赖关系相关方法 ==========
    
    def add_knowledge_dependency(self, source_node_id: str, target_node_id: str, 
                                 dependency_type: str = "depends_on") -> bool:
        """
        添加知识点依赖关系（横向依赖：同级或跨级）
        
        Args:
            source_node_id: 源节点 ID（依赖者）
            target_node_id: 目标节点 ID（被依赖者）
            dependency_type: 依赖类型，默认为 "depends_on"
            
        Returns:
            是否成功添加
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO knowledge_dependencies 
                    (source_node_id, target_node_id, dependency_type, created_at)
                    VALUES (?, ?, ?, ?)
                """, (source_node_id, target_node_id, dependency_type, now))
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.IntegrityError as e:
                print(f"添加知识点依赖关系失败: {e}")
                return False
    
    def remove_knowledge_dependency(self, source_node_id: str, target_node_id: str) -> bool:
        """
        删除知识点依赖关系
        
        Args:
            source_node_id: 源节点 ID
            target_node_id: 目标节点 ID
            
        Returns:
            是否成功删除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM knowledge_dependencies
                WHERE source_node_id = ? AND target_node_id = ?
            """, (source_node_id, target_node_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_node_dependencies(self, node_id: str) -> List[Dict[str, Any]]:
        """
        获取节点的所有依赖关系（该节点依赖的其他节点）
        
        Args:
            node_id: 节点 ID
            
        Returns:
            依赖关系列表，每个元素包含 target_node_id 和 dependency_type
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT target_node_id, dependency_type, created_at
                FROM knowledge_dependencies
                WHERE source_node_id = ?
                ORDER BY created_at ASC
            """, (node_id,))
            rows = cursor.fetchall()
            return [
                {
                    "target_node_id": row["target_node_id"],
                    "dependency_type": row["dependency_type"],
                    "created_at": row["created_at"]
                }
                for row in rows
            ]
    
    def get_node_dependents(self, node_id: str) -> List[Dict[str, Any]]:
        """
        获取节点的所有被依赖关系（依赖该节点的其他节点）
        
        Args:
            node_id: 节点 ID
            
        Returns:
            被依赖关系列表，每个元素包含 source_node_id 和 dependency_type
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT source_node_id, dependency_type, created_at
                FROM knowledge_dependencies
                WHERE target_node_id = ?
                ORDER BY created_at ASC
            """, (node_id,))
            rows = cursor.fetchall()
            return [
                {
                    "source_node_id": row["source_node_id"],
                    "dependency_type": row["dependency_type"],
                    "created_at": row["created_at"]
                }
                for row in rows
            ]
    
    def delete_node_dependencies(self, node_id: str) -> bool:
        """
        删除节点的所有依赖关系（包括作为源节点和目标节点）
        
        Args:
            node_id: 节点 ID
            
        Returns:
            是否成功删除
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM knowledge_dependencies
                WHERE source_node_id = ? OR target_node_id = ?
            """, (node_id, node_id))
            conn.commit()
            return True


# 全局数据库实例
# 数据库文件存储在 data/ 目录下，确保持久化
db = Database(db_path="data/question_generator.db")

