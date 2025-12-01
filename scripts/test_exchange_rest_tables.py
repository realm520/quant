#!/usr/bin/env python3
"""测试 Exchange-specific REST API 表创建."""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.exchange_rest_models import ExchangeRestBase
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def main():
    """测试表创建."""
    print("=" * 60)
    print("测试 Exchange-specific REST API 表创建")
    print("=" * 60)
    
    # 检查 metadata 中的表
    metadata_tables = list(ExchangeRestBase.metadata.tables.keys())
    print(f"\n📋 Metadata 中的表 ({len(metadata_tables)} 个):")
    for table_name in sorted(metadata_tables):
        print(f"  - {table_name}")
    
    # 检查 binance_balance_rest 是否在 metadata 中
    if "binance_balance_rest" in metadata_tables:
        print("\n✓ binance_balance_rest 在 metadata 中")
    else:
        print("\n✗ binance_balance_rest 不在 metadata 中！")
        print("  这可能是模型没有正确注册的问题。")
        return
    
    # 创建数据库管理器
    db_manager = DatabaseManager()
    
    try:
        # 创建表
        print("\n📦 开始创建表...")
        await db_manager.create_tables()
        print("\n✅ 表创建完成")
        
        # 检查数据库中实际存在的表
        from sqlalchemy import inspect, text
        async with db_manager.async_engine.connect() as conn:
            def check_tables(sync_conn):
                inspector = inspect(sync_conn)
                existing_tables = set(inspector.get_table_names())
                return existing_tables
            
            existing_tables = await conn.run_sync(check_tables)
            
            print(f"\n📊 数据库中实际存在的 Exchange REST 表 ({len([t for t in existing_tables if '_rest' in t])} 个):")
            rest_tables = [t for t in existing_tables if '_rest' in t]
            for table_name in sorted(rest_tables):
                print(f"  - {table_name}")
            
            # 检查 binance_balance_rest 是否存在
            if "binance_balance_rest" in existing_tables:
                print("\n✅ binance_balance_rest 表已创建")
            else:
                print("\n❌ binance_balance_rest 表未创建！")
                print("  可能的原因：")
                print("  1. 创建表时出错但被忽略了")
                print("  2. 表名不匹配")
                print("  3. 权限问题")
                
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n❌ 错误: {e}")
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())

