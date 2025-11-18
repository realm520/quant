#!/usr/bin/env python3
"""数据库迁移脚本：为 rest_positions 表添加 account_id 列.

此脚本用于：
1. 检查 rest_positions 表是否存在 account_id 列
2. 如果不存在，添加 account_id 列和相应的索引

运行方式：
    uv run python scripts/migrate_add_account_id_to_rest_positions.py
"""

import asyncio
import os
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
    logger.info("Starting database migration: add account_id column to rest_positions table")

    # 从环境变量获取数据库URL，如果没有则使用默认值
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/trading"
    )
    logger.info(f"Database URL: {database_url}")

    db_manager = DatabaseManager(database_url=database_url)

    try:
        async with db_manager.async_engine.begin() as conn:
            # 1. 检查 account_id 列是否已存在
            logger.info("Checking if account_id column exists in rest_positions table...")
            result = await conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'rest_positions'
                AND column_name = 'account_id';
            """))

            if result.fetchone():
                logger.info("✓ account_id column already exists in rest_positions table")
            else:
                # 2. 添加 account_id 列
                logger.info("Adding account_id column to rest_positions table...")
                await conn.execute(text("""
                    ALTER TABLE rest_positions
                    ADD COLUMN account_id VARCHAR(64);
                """))
                logger.info("✓ account_id column added")

                # 3. 创建索引
                logger.info("Creating index on account_id column...")
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_rest_position_account_time
                    ON rest_positions (account_id, query_time);
                """))
                logger.info("✓ Index created on account_id column")

        logger.info("✅ Database migration completed successfully")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())

