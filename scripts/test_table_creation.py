#!/usr/bin/env python3
"""测试表创建逻辑，找出为什么 xt_order_update 和 xt_trade_update 没有创建成功."""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError, DBAPIError
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_websocket_models import Base as XTWebSocketBase
import asyncio


async def test_table_creation():
    """测试表创建."""
    db_manager = DatabaseManager()
    
    # 获取 metadata 中的所有表
    metadata_tables = set(XTWebSocketBase.metadata.tables.keys())
    print(f"XT WebSocket metadata 中的表: {sorted(metadata_tables)}")
    print()
    
    # 检查哪些表在数据库中
    async with db_manager.async_engine.connect() as conn:
        def check_tables(sync_conn):
            inspector = inspect(sync_conn)
            existing_tables = set(inspector.get_table_names())
            print(f"数据库中已存在的表: {sorted([t for t in existing_tables if t.startswith('xt_')])}")
            print()
            
            # 检查哪些表缺失
            missing_tables = metadata_tables - existing_tables
            if missing_tables:
                print(f"缺失的表: {sorted(missing_tables)}")
                print()
                
                # 尝试创建缺失的表
                for table_name in sorted(missing_tables):
                    print(f"尝试创建表: {table_name}")
                    table = XTWebSocketBase.metadata.tables[table_name]
                    
                    try:
                        from sqlalchemy.schema import CreateTable
                        create_table_sql = str(CreateTable(table).compile(dialect=sync_conn.dialect))
                        print(f"生成的 SQL (前 500 字符):")
                        print(create_table_sql[:500])
                        print()
                        
                        sync_conn.execute(text(create_table_sql))
                        sync_conn.commit()
                        
                        # 验证表是否创建成功
                        inspector = inspect(sync_conn)
                        if inspector.has_table(table_name):
                            print(f"✓ 表 {table_name} 创建成功")
                        else:
                            print(f"✗ 表 {table_name} 创建失败（表不存在）")
                    except Exception as e:
                        sync_conn.rollback()
                        print(f"✗ 创建表 {table_name} 时出错: {e}")
                        import traceback
                        traceback.print_exc()
                    print()
            else:
                print("所有表都已存在")
        
        await conn.run_sync(check_tables)
    
    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(test_table_creation())
