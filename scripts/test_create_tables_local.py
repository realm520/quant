#!/usr/bin/env python3
"""本地测试 create_tables() 功能。

先删除所有表，然后重新创建，验证没有重复表定义错误。
"""

import sys
import os
import asyncio

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tri_arb.storage.database import DatabaseManager
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def test_create_tables():
    """测试创建表"""
    print("=" * 60)
    print("测试 create_tables() 功能")
    print("=" * 60)
    
    # 从环境变量获取数据库 URL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ 错误: 未设置 DATABASE_URL 环境变量")
        print("请设置: export DATABASE_URL='postgresql+asyncpg://user:password@host:port/dbname'")
        return False
    
    print(f"数据库 URL: {database_url.split('@')[-1] if '@' in database_url else 'localhost'}")
    
    db_manager = DatabaseManager(database_url=database_url)
    
    try:
        # 1. 先删除所有表
        print("\n" + "-" * 60)
        print("步骤 1: 删除所有表...")
        print("-" * 60)
        try:
            await db_manager.drop_tables()
            print("✓ 所有表已删除")
        except Exception as e:
            print(f"⚠️  删除表时出错（可能表不存在）: {e}")
        
        # 2. 重新创建所有表
        print("\n" + "-" * 60)
        print("步骤 2: 重新创建所有表...")
        print("-" * 60)
        await db_manager.create_tables()
        print("\n✅ 所有表创建成功！")
        
        # 3. 验证表是否存在
        print("\n" + "-" * 60)
        print("步骤 3: 验证表是否存在...")
        print("-" * 60)
        from sqlalchemy import inspect, text
        
        async with db_manager.async_engine.connect() as conn:
            inspector = inspect(await conn.get_sync_engine())
            existing_tables = set(inspector.get_table_names())
            
            # 检查关键表
            expected_tables = {
                # Binance WebSocket
                "binance_account_update",
                "binance_order_update",
                "binance_trade_update",
                "binance_account_snapshot",
                # XT WebSocket
                "xt_account_update",
                "xt_position_update",
                "xt_order_update",
                "xt_trade_update",
                "xt_transfer_update",
                "xt_connection",
                # XT REST
                "xt_account_snapshot",
                "xt_position_snapshot",
                # Exchange REST
                "binance_account_snapshot",
                "binance_position_snapshot",
                "binance_order_snapshot",
                "xt_account_snapshot",
                "xt_position_snapshot",
                "xt_order_snapshot",
            }
            
            found_tables = existing_tables & expected_tables
            missing_tables = expected_tables - existing_tables
            
            print(f"\n找到 {len(found_tables)} 个预期表:")
            for table in sorted(found_tables):
                print(f"  ✓ {table}")
            
            if missing_tables:
                print(f"\n缺少 {len(missing_tables)} 个表:")
                for table in sorted(missing_tables):
                    print(f"  ✗ {table}")
            else:
                print("\n✓ 所有预期表都存在")
            
            print(f"\n总表数: {len(existing_tables)}")
            print(f"表列表: {sorted(existing_tables)}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    print("开始测试 create_tables()...\n")
    
    success = asyncio.run(test_create_tables())
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 测试通过！")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("❌ 测试失败")
        print("=" * 60)
        sys.exit(1)

