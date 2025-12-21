#!/usr/bin/env python3
"""诊断表创建失败的原因."""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_websocket_models import Base as XTWebSocketBase


async def diagnose():
    """诊断表创建问题."""
    db_manager = DatabaseManager()
    
    # 获取 metadata 中的所有表
    metadata_tables = set(XTWebSocketBase.metadata.tables.keys())
    print(f"XT WebSocket metadata 中的表: {sorted(metadata_tables)}")
    print()
    
    # 检查哪些表在数据库中
    async with db_manager.async_engine.connect() as conn:
        def check_and_create(sync_conn):
            inspector = inspect(sync_conn)
            existing_tables = set(inspector.get_table_names())
            print(f"数据库中已存在的 XT 表: {sorted([t for t in existing_tables if t.startswith('xt_')])}")
            print()
            
            # 检查哪些表缺失
            missing_tables = metadata_tables - existing_tables
            if missing_tables:
                print(f"缺失的表: {sorted(missing_tables)}")
                print()
                
                # 尝试创建缺失的表
                for table_name in sorted(missing_tables):
                    print(f"=" * 80)
                    print(f"尝试创建表: {table_name}")
                    print("=" * 80)
                    table = XTWebSocketBase.metadata.tables[table_name]
                    
                    try:
                        # 生成 SQL
                        print("1. 生成 CREATE TABLE SQL...")
                        create_table_sql = str(CreateTable(table).compile(dialect=sync_conn.dialect))
                        print(f"   SQL 长度: {len(create_table_sql)} 字符")
                        print(f"   SQL (前 500 字符):")
                        print(f"   {create_table_sql[:500]}")
                        print()
                        
                        # 执行 SQL
                        print("2. 执行 CREATE TABLE SQL...")
                        sync_conn.execute(text(create_table_sql))
                        sync_conn.commit()
                        print("   ✓ SQL 执行成功")
                        print()
                        
                        # 验证表是否存在
                        print("3. 验证表是否创建成功...")
                        inspector = inspect(sync_conn)
                        if inspector.has_table(table_name):
                            print(f"   ✓ 表 {table_name} 创建成功")
                        else:
                            print(f"   ✗ 表 {table_name} 创建失败（表不存在）")
                    except Exception as e:
                        sync_conn.rollback()
                        print(f"   ✗ 创建表 {table_name} 时出错:")
                        print(f"   错误类型: {type(e).__name__}")
                        print(f"   错误信息: {e}")
                        import traceback
                        print("   完整堆栈:")
                        traceback.print_exc()
                    print()
            else:
                print("所有表都已存在")
        
        await conn.run_sync(check_and_create)
    
    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(diagnose())
