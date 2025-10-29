#!/usr/bin/env python3
"""添加 OKX Order 表的唯一性约束.

这个迁移脚本会：
1. 为 okx_orders 表添加 (ord_id, u_time) 组合唯一性约束
2. 删除可能存在的重复数据（保留最新的）
"""

import asyncio
import os
from sqlalchemy import text
from tri_arb.storage.database import DatabaseManager
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def migrate():
    """执行迁移."""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/trading"
    )

    logger.info("Starting OKX order constraint migration")
    logger.info(f"Database URL: {database_url}")

    db_manager = DatabaseManager(database_url=database_url)

    try:
        async with db_manager.session() as session:
            # 1. 检查表是否存在
            result = await session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'okx_orders'
                )
            """))
            table_exists = result.scalar()

            if not table_exists:
                logger.info("Table okx_orders does not exist yet, skipping migration")
                return

            # 2. 检查唯一性约束是否已存在
            result = await session.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'okx_orders'
                  AND constraint_type = 'UNIQUE'
                  AND constraint_name = 'uq_okx_order_id_time'
            """))
            constraint_exists = result.scalar()

            if constraint_exists:
                logger.info("Unique constraint 'uq_okx_order_id_time' already exists, skipping")
                return

            # 3. 删除重复的 (ord_id, u_time)（保留最新的）
            logger.info("Checking for duplicate (ord_id, u_time) combinations...")
            result = await session.execute(text("""
                SELECT ord_id, u_time, COUNT(*)
                FROM okx_orders
                WHERE ord_id IS NOT NULL AND u_time IS NOT NULL
                GROUP BY ord_id, u_time
                HAVING COUNT(*) > 1
            """))
            duplicates = result.fetchall()

            if duplicates:
                logger.warning(f"Found {len(duplicates)} duplicate (ord_id, u_time) combinations, cleaning up...")

                for ord_id, u_time, count in duplicates:
                    logger.info(f"Removing {count - 1} duplicate(s) for ord_id={ord_id}, u_time={u_time}")

                    # 删除旧的记录，保留最新的（按 created_at 排序）
                    await session.execute(text("""
                        DELETE FROM okx_orders
                        WHERE id IN (
                            SELECT id
                            FROM okx_orders
                            WHERE ord_id = :ord_id AND u_time = :u_time
                            ORDER BY created_at DESC
                            OFFSET 1
                        )
                    """), {"ord_id": ord_id, "u_time": u_time})

                await session.commit()
                logger.info("Duplicate records removed")
            else:
                logger.info("No duplicate (ord_id, u_time) combinations found")

            # 4. 添加唯一性约束
            logger.info("Adding unique constraint 'uq_okx_order_id_time'...")
            await session.execute(text("""
                ALTER TABLE okx_orders
                ADD CONSTRAINT uq_okx_order_id_time UNIQUE (ord_id, u_time)
            """))
            await session.commit()

            logger.info("✅ Unique constraint added successfully")

            # 5. 验证约束
            result = await session.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'okx_orders'
                  AND constraint_type = 'UNIQUE'
            """))
            constraints = result.fetchall()

            logger.info("Current unique constraints on okx_orders:")
            for constraint in constraints:
                logger.info(f"  - {constraint[0]}")

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        raise
    finally:
        await db_manager.close()

    logger.info("Migration completed successfully")


if __name__ == "__main__":
    asyncio.run(migrate())
