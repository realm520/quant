#!/usr/bin/env python3
"""测试数据库表创建脚本."""

import asyncio
import os
from tri_arb.storage.database import DatabaseManager

async def main():
    """测试创建所有数据库表."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("错误: 请设置 DATABASE_URL 环境变量")
        return
    
    print(f"数据库URL: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    print("正在创建数据库表...\n")
    
    db_manager = DatabaseManager(database_url=database_url)
    try:
        await db_manager.create_tables()
        print("\n✅ 所有表创建完成！")
    except Exception as e:
        print(f"\n❌ 创建表时出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db_manager.close()

if __name__ == "__main__":
    asyncio.run(main())

