#!/usr/bin/env python3
"""迁移脚本：为已存在的 REST API 表添加 exchange_type 字段。

如果表已存在但缺少 exchange_type 字段，则添加该字段。
"""

import sys
import os
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tri_arb.storage.database import DatabaseManager
from tri_arb.config.logging import get_logger
from sqlalchemy import inspect, text

logger = get_logger(__name__)


async def migrate_tables():
    """为已存在的表添加 exchange_type 字段"""
    print("=" * 60)
    print("迁移脚本：为 REST API 表添加 exchange_type 字段")
    print("=" * 60)
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        from dotenv import load_dotenv
        load_dotenv()
        database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("❌ 错误: 未设置 DATABASE_URL 环境变量")
        return False
    
    db_manager = DatabaseManager(database_url=database_url)
    
    # 需要添加 exchange_type 字段的表
    tables_to_migrate = [
        "binance_account_snapshot",
        "binance_position_snapshot",
        "binance_order_snapshot",
        "xt_account_snapshot",
        "xt_position_snapshot",
        "xt_order_snapshot",
        "okx_account_snapshot",
        "okx_position_snapshot",
        "okx_order_snapshot",
        "gate_account_snapshot",
        "gate_position_snapshot",
        "gate_order_snapshot",
    ]
    
    try:
        async with db_manager.async_engine.connect() as conn:
            inspector = inspect(await conn.get_sync_engine())
            existing_tables = set(inspector.get_table_names())
            
            migrated_count = 0
            skipped_count = 0
            error_count = 0
            
            for table_name in tables_to_migrate:
                if table_name not in existing_tables:
                    print(f"⏭️  表 {table_name} 不存在，跳过")
                    skipped_count += 1
                    continue
                
                # 检查表是否已有 exchange_type 字段
                columns = [col['name'] for col in inspector.get_columns(table_name)]
                
                if 'exchange_type' in columns:
                    print(f"✓ 表 {table_name} 已有 exchange_type 字段，跳过")
                    skipped_count += 1
                    continue
                
                # 添加 exchange_type 字段
                print(f"📝 为表 {table_name} 添加 exchange_type 字段...")
                try:
                    # 先添加字段（允许 NULL，因为已有数据）
                    try:
                        await conn.execute(
                            text(f'ALTER TABLE {table_name} ADD COLUMN exchange_type VARCHAR(10)')
                        )
                        await conn.commit()
                    except Exception as add_col_err:
                        error_str = str(add_col_err).lower()
                        if "already exists" in error_str or "duplicate" in error_str:
                            print(f"  ⚠️  字段 exchange_type 已存在，跳过添加")
                            # 字段已存在，继续后续步骤
                        else:
                            raise
                    
                    # 为已有数据设置默认值（根据表名判断）
                    if 'account' in table_name:
                        # 账户表，默认设置为 perp（因为主要是合约账户）
                        default_value = 'perp'
                    elif 'position' in table_name:
                        # 持仓表，默认设置为 perp
                        default_value = 'perp'
                    else:
                        # 订单表，默认设置为 perp
                        default_value = 'perp'
                    
                    await conn.execute(
                        text(f"UPDATE {table_name} SET exchange_type = :default WHERE exchange_type IS NULL"),
                        {"default": default_value}
                    )
                    await conn.commit()
                    
                    # 设置为 NOT NULL
                    await conn.execute(
                        text(f'ALTER TABLE {table_name} ALTER COLUMN exchange_type SET NOT NULL')
                    )
                    await conn.commit()
                    
                    # 创建索引（根据表类型使用不同的索引名，与模型定义一致）
                    try:
                        exchange_prefix = table_name.split("_")[0]  # binance, xt, okx, gate
                        if 'account' in table_name:
                            # 账户表索引：idx_{exchange}_balance_type_time
                            index_name = f'idx_{exchange_prefix}_balance_type_time'
                            await conn.execute(
                                text(f'CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} (exchange_type, query_time)')
                            )
                            await conn.commit()
                    except Exception as idx_err:
                        # 索引可能已存在，忽略
                        await conn.rollback()
                        logger.debug(f"索引 {index_name} 可能已存在: {idx_err}")
                    
                    print(f"  ✓ 成功添加 exchange_type 字段（默认值: {default_value}）")
                    migrated_count += 1
                    
                except Exception as e:
                    await conn.rollback()
                    error_str = str(e).lower()
                    if "already exists" in error_str or "duplicate" in error_str:
                        print(f"  ⚠️  字段可能已存在: {e}")
                        skipped_count += 1
                    else:
                        print(f"  ❌ 添加字段失败: {e}")
                        error_count += 1
            
            print("\n" + "=" * 60)
            print(f"迁移完成:")
            print(f"  ✓ 成功迁移: {migrated_count} 个表")
            print(f"  ⏭️  跳过: {skipped_count} 个表")
            if error_count > 0:
                print(f"  ❌ 失败: {error_count} 个表")
            print("=" * 60)
            
            return error_count == 0
            
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await db_manager.close()


if __name__ == "__main__":
    print("开始迁移...\n")
    
    success = asyncio.run(migrate_tables())
    
    if success:
        print("\n🎉 迁移成功！")
        sys.exit(0)
    else:
        print("\n❌ 迁移失败")
        sys.exit(1)

