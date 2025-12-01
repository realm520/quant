#!/usr/bin/env python3
"""测试 binance_balance_rest 表创建功能."""

import asyncio
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.exchange_rest_models import (
    Base as ExchangeRestBase,
    BinanceBalanceRest,
    BinancePositionRest,
    BinanceOrderRest,
    XTBalanceRest,
    OKXBalanceRest,
    GateBalanceRest,
)
from tri_arb.config.logging import get_logger
from sqlalchemy import inspect

logger = get_logger(__name__)


async def main():
    """测试表创建."""
    print("=" * 70)
    print("测试 binance_balance_rest 表创建功能")
    print("=" * 70)
    
    # 1. 检查模型是否正确导入
    print("\n1. 检查模型导入...")
    print(f"   BinanceBalanceRest: {BinanceBalanceRest}")
    print(f"   BinanceBalanceRest.__tablename__: {BinanceBalanceRest.__tablename__}")
    
    # 2. 检查 metadata 中的表
    print("\n2. 检查 ExchangeRestBase.metadata 中的表...")
    metadata_tables = list(ExchangeRestBase.metadata.tables.keys())
    print(f"   找到 {len(metadata_tables)} 个表:")
    for table_name in sorted(metadata_tables):
        marker = "✓" if table_name == "binance_balance_rest" else " "
        print(f"   {marker} {table_name}")
    
    if "binance_balance_rest" in metadata_tables:
        print("\n   ✓ binance_balance_rest 在 metadata 中")
    else:
        print("\n   ✗ binance_balance_rest 不在 metadata 中！")
        print("   这是问题所在！")
        return
    
    # 3. 检查表的定义
    print("\n3. 检查 binance_balance_rest 表的定义...")
    try:
        table = ExchangeRestBase.metadata.tables["binance_balance_rest"]
        print(f"   表名: {table.name}")
        print(f"   列数: {len(table.columns)}")
        print(f"   索引数: {len(table.indexes)}")
        print(f"   列名: {[col.name for col in table.columns]}")
    except KeyError:
        print("   ✗ 无法获取表定义")
        return
    
    # 4. 连接数据库并检查现有表
    print("\n4. 连接数据库并检查现有表...")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("   错误: 请设置 DATABASE_URL 环境变量")
        print("   示例: export DATABASE_URL='postgresql+asyncpg://user:password@localhost:5432/trading'")
        return
    
    db_manager = DatabaseManager(database_url=database_url)
    
    try:
        async with db_manager.async_engine.connect() as conn:
            def check_existing_tables(sync_conn):
                inspector = inspect(sync_conn)
                existing_tables = set(inspector.get_table_names())
                return existing_tables
            
            existing_tables = await conn.run_sync(check_existing_tables)
            
            print(f"   数据库中现有表数: {len(existing_tables)}")
            rest_tables = [t for t in existing_tables if "_rest" in t]
            print(f"   REST 相关表 ({len(rest_tables)} 个):")
            for table_name in sorted(rest_tables):
                marker = "✓" if table_name == "binance_balance_rest" else " "
                print(f"   {marker} {table_name}")
            
            if "binance_balance_rest" in existing_tables:
                print("\n   ✓ binance_balance_rest 表已存在")
            else:
                print("\n   ✗ binance_balance_rest 表不存在，需要创建")
        
        # 5. 尝试创建表
        print("\n5. 尝试创建表...")
        await db_manager.create_tables()
        print("   ✓ create_tables() 执行完成")
        
        # 6. 再次检查表是否被创建
        print("\n6. 再次检查表是否被创建...")
        async with db_manager.async_engine.connect() as conn:
            existing_tables = await conn.run_sync(check_existing_tables)
            
            if "binance_balance_rest" in existing_tables:
                print("   ✓ binance_balance_rest 表已成功创建！")
                
                # 检查表结构
                def get_table_info(sync_conn):
                    inspector = inspect(sync_conn)
                    columns = inspector.get_columns("binance_balance_rest")
                    indexes = inspector.get_indexes("binance_balance_rest")
                    return columns, indexes
                
                columns, indexes = await conn.run_sync(get_table_info)
                print(f"\n   表结构:")
                print(f"   列数: {len(columns)}")
                for col in columns:
                    print(f"     - {col['name']}: {col['type']}")
                print(f"   索引数: {len(indexes)}")
                for idx in indexes:
                    print(f"     - {idx['name']}: {idx['column_names']}")
            else:
                print("   ✗ binance_balance_rest 表仍然不存在！")
                print("   创建表可能失败了，请检查日志")
        
        print("\n" + "=" * 70)
        print("测试完成")
        print("=" * 70)
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())

