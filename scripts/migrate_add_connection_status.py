#!/usr/bin/env python3
"""数据库迁移脚本：添加ConnectionStatus表和唯一性约束.

此脚本用于：
1. 创建connection_status表
2. 为order_updates表添加唯一性约束
3. 为trade_updates表添加唯一性约束

运行方式：
    uv run python scripts/migrate_add_connection_status.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text
from tri_arb.storage.database import DatabaseManager
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def main():
    """执行数据库迁移."""
    logger.info("Starting database migration: add ConnectionStatus table and unique constraints")

    db_manager = DatabaseManager()

    try:
        async with db_manager.async_engine.begin() as conn:
            # 1. 创建connection_status表
            logger.info("Creating connection_status table...")
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS connection_status (
                    id SERIAL PRIMARY KEY,
                    exchange VARCHAR(20) NOT NULL UNIQUE,
                    is_connected BOOLEAN DEFAULT FALSE,
                    last_connected_at TIMESTAMP,
                    last_disconnected_at TIMESTAMP,
                    last_order_event_time TIMESTAMP,
                    last_trade_event_time TIMESTAMP,
                    last_account_event_time TIMESTAMP,
                    last_order_id BIGINT,
                    last_trade_id BIGINT,
                    total_reconnect_count INTEGER DEFAULT 0,
                    last_data_gap_seconds INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            # 创建索引
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_exchange_connected
                ON connection_status (exchange, is_connected);
            """))

            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_last_order_event_time
                ON connection_status (last_order_event_time);
            """))

            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_last_trade_event_time
                ON connection_status (last_trade_event_time);
            """))

            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_last_account_event_time
                ON connection_status (last_account_event_time);
            """))

            logger.info("✓ connection_status table created")

            # 2. 为order_updates表添加唯一性约束
            logger.info("Adding unique constraint to order_updates table...")

            # 检查约束是否已存在
            result = await conn.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'order_updates'
                AND constraint_name = 'uq_order_update_event';
            """))

            if not result.fetchone():
                # 先删除可能存在的重复数据
                logger.info("Removing duplicate order updates...")
                await conn.execute(text("""
                    DELETE FROM order_updates a USING order_updates b
                    WHERE a.id > b.id
                    AND a.exchange = b.exchange
                    AND a.order_id = b.order_id
                    AND a.event_time = b.event_time;
                """))

                # 添加唯一性约束
                await conn.execute(text("""
                    ALTER TABLE order_updates
                    ADD CONSTRAINT uq_order_update_event
                    UNIQUE (exchange, order_id, event_time);
                """))
                logger.info("✓ Unique constraint added to order_updates")
            else:
                logger.info("✓ Unique constraint already exists on order_updates")

            # 3. 为trade_updates表添加唯一性约束
            logger.info("Adding unique constraint to trade_updates table...")

            # 检查约束是否已存在
            result = await conn.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'trade_updates'
                AND constraint_name = 'uq_trade_id';
            """))

            if not result.fetchone():
                # 先删除可能存在的重复数据
                logger.info("Removing duplicate trades...")
                await conn.execute(text("""
                    DELETE FROM trade_updates a USING trade_updates b
                    WHERE a.id > b.id
                    AND a.exchange = b.exchange
                    AND a.trade_id = b.trade_id;
                """))

                # 添加唯一性约束
                await conn.execute(text("""
                    ALTER TABLE trade_updates
                    ADD CONSTRAINT uq_trade_id
                    UNIQUE (exchange, trade_id);
                """))
                logger.info("✓ Unique constraint added to trade_updates")
            else:
                logger.info("✓ Unique constraint already exists on trade_updates")

        logger.info("✅ Database migration completed successfully")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
