#!/usr/bin/env python3
"""
删除今天以前创建的所有题目表数据脚本

使用方法:
    python delete_old_questions.py [--db-path <数据库路径>] [--dry-run] [--confirm]

参数:
    --db-path: 数据库文件路径，默认为 data/question_generator.db
    --dry-run: 仅显示将要删除的记录数量，不实际删除
    --confirm: 跳过确认提示，直接执行删除
"""

import sqlite3
import sys
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import Optional


def get_today_date_str() -> str:
    """
    获取今天的日期字符串（格式：YYYY-MM-DD）
    
    Returns:
        今天的日期字符串
    """
    return date.today().strftime("%Y-%m-%d")


def count_old_questions(conn: sqlite3.Connection, before_date: str) -> int:
    """
    统计指定日期之前创建的题目数量
    
    Args:
        conn: 数据库连接
        before_date: 日期字符串（格式：YYYY-MM-DD）
    
    Returns:
        题目数量
    """
    cursor = conn.cursor()
    # 使用日期比较，created_at 字段存储的是 ISO 格式的时间戳
    # 比较时使用 DATE() 函数提取日期部分，或者直接比较字符串（如果格式一致）
    cursor.execute("""
        SELECT COUNT(*) 
        FROM questions 
        WHERE DATE(created_at) < DATE(?)
    """, (before_date,))
    result = cursor.fetchone()
    return result[0] if result else 0


def get_old_questions_info(conn: sqlite3.Connection, before_date: str) -> list:
    """
    获取指定日期之前创建的题目信息（用于预览）
    
    Args:
        conn: 数据库连接
        before_date: 日期字符串（格式：YYYY-MM-DD）
    
    Returns:
        题目信息列表
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT question_id, question_type, chapter, created_at, stem
        FROM questions 
        WHERE DATE(created_at) < DATE(?)
        ORDER BY created_at DESC
        LIMIT 10
    """, (before_date,))
    return cursor.fetchall()


def delete_old_questions(conn: sqlite3.Connection, before_date: str) -> int:
    """
    删除指定日期之前创建的所有题目
    
    Args:
        conn: 数据库连接
        before_date: 日期字符串（格式：YYYY-MM-DD）
    
    Returns:
        删除的题目数量
    """
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM questions 
        WHERE DATE(created_at) < DATE(?)
    """, (before_date,))
    deleted_count = cursor.rowcount
    conn.commit()
    return deleted_count


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="删除今天以前创建的所有题目表数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 预览将要删除的记录数量
  python delete_old_questions.py --dry-run
  
  # 删除并确认
  python delete_old_questions.py --confirm
  
  # 使用自定义数据库路径
  python delete_old_questions.py --db-path /path/to/database.db --confirm
        """
    )
    
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/question_generator.db",
        help="数据库文件路径（默认: data/question_generator.db）"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅显示将要删除的记录数量，不实际删除"
    )
    
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="跳过确认提示，直接执行删除"
    )
    
    args = parser.parse_args()
    
    # 检查数据库文件是否存在
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"❌ 错误: 数据库文件不存在: {db_path}")
        print(f"   请检查路径是否正确")
        sys.exit(1)
    
    # 获取今天的日期
    today = get_today_date_str()
    print(f"📅 今天的日期: {today}")
    print(f"🗄️  数据库路径: {db_path.absolute()}")
    print()
    
    # 连接数据库
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        print(f"❌ 错误: 无法连接数据库: {e}")
        sys.exit(1)
    
    try:
        # 统计要删除的题目数量
        count = count_old_questions(conn, today)
        
        if count == 0:
            print("✅ 没有找到今天以前创建的题目，无需删除。")
            return
        
        print(f"📊 找到 {count} 条今天以前创建的题目记录")
        
        # 显示部分记录预览
        if not args.dry_run:
            print("\n📋 部分记录预览（最近10条）:")
            preview_records = get_old_questions_info(conn, today)
            if preview_records:
                print(f"{'ID':<8} {'题型':<10} {'章节':<20} {'创建时间':<20} {'题干（前30字）'}")
                print("-" * 100)
                for record in preview_records:
                    question_id, qtype, chapter, created_at, stem = record
                    chapter_str = chapter[:18] if chapter else "N/A"
                    stem_preview = stem[:28] if stem else "N/A"
                    print(f"{question_id:<8} {qtype:<10} {chapter_str:<20} {created_at:<20} {stem_preview}")
            print()
        
        # 如果是 dry-run 模式，只显示统计信息
        if args.dry_run:
            print(f"🔍 [预览模式] 将删除 {count} 条记录")
            print("   使用 --confirm 参数执行实际删除操作")
            return
        
        # 确认删除
        if not args.confirm:
            print("⚠️  警告: 此操作将永久删除今天以前创建的所有题目数据，且无法恢复！")
            response = input("   确认删除？(输入 'yes' 确认): ")
            if response.lower() != 'yes':
                print("❌ 操作已取消")
                return
        
        # 执行删除
        print("🗑️  正在删除...")
        deleted_count = delete_old_questions(conn, today)
        
        if deleted_count == count:
            print(f"✅ 成功删除 {deleted_count} 条题目记录")
        else:
            print(f"⚠️  警告: 预期删除 {count} 条，实际删除 {deleted_count} 条")
        
    except sqlite3.Error as e:
        print(f"❌ 数据库操作错误: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
