#!/usr/bin/env python3
"""删除所有数据库表的脚本。

⚠️  警告：此操作会删除所有表和数据，请谨慎使用！
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tri_arb.storage.database import DatabaseManager
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def drop_all_tables():
    """删除所有表"""
    print("=" * 60)
    print("⚠️  警告：此操作将删除所有数据库表和数据！")
    print("=" * 60)
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        from dotenv import load_dotenv
        load_dotenv()
        database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ 错误: 未设置 DATABASE_URL 环境变量")
        return False
    
    # 确认操作
    print(f"\n数据库 URL: {database_url.split('@')[-1] if '@' in database_url else 'localhost'}")
    print("\n确认要删除所有表吗？(yes/no): ", end='')
    
    # 如果是从命令行运行，需要用户确认
    if sys.stdin.isatty():
        confirm = input().strip().lower()
        if confirm != 'yes':
            print("❌ 操作已取消")
            return False
    else:
        # 非交互式环境，直接执行（用于脚本调用）
        print("yes (非交互式模式)")
    
    db_manager = DatabaseManager(database_url=database_url)
    
    try:
        print("\n开始删除所有表...")
        await db_manager.drop_tables()
        print("✅ 所有表已删除")
        return True
        
    except Exception as e:
        print(f"\n❌ 删除表失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    print("准备删除所有数据库表...\n")
    
    success = asyncio.run(drop_all_tables())
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 所有表已删除！")
        print("=" * 60)
        print("\n提示：现在可以重新运行 subscribe 或 watch 命令，表会自动创建。")
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ 删除失败")
        print("=" * 60)
        sys.exit(1)

