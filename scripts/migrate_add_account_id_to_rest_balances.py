#!/usr/bin/env python3
"""数据库迁移脚本：为 rest_balances 表添加 account_id 列."""

import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text
from tri_arb.storage.database import DatabaseManager
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def main():
    logger.info("Starting database migration: add account_id column to rest_balances table")
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/trading",
    )
    logger.info("Database URL: %s", database_url)

    db_manager = DatabaseManager(database_url=database_url)

    try:
        async with db_manager.async_engine.begin() as conn:
            logger.info("Checking if account_id column exists in rest_balances table...")
            result = await conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'rest_balances'
                      AND column_name = 'account_id';
                    """
                )
            )
            if result.fetchone():
                logger.info("\u2713 account_id column already exists in rest_balances table")
            else:
                logger.info("Adding account_id column to rest_balances table...")
                await conn.execute(
                    text(
                        """
                        ALTER TABLE rest_balances
                        ADD COLUMN account_id VARCHAR(64);
                        """
                    )
                )
                logger.info("\u2713 account_id column added")

                logger.info("Creating index on account_id column...")
                await conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_rest_balance_account_time
                        ON rest_balances (account_id, query_time);
                        """
                    )
                )
                logger.info("\u2713 Index created on account_id column")
        logger.info("\u2705 Database migration completed successfully")
    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        raise
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
