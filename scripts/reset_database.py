#!/usr/bin/env python3
"""清空并重建数据库脚本.

警告：此脚本会删除所有数据！仅用于开发环境。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tri_arb.storage.database import DatabaseManager
from tri_arb.config.logging import get_logger
from sqlalchemy import text

logger = get_logger(__name__)


async def reset_database():
    """清空并重建数据库."""

    # 确认操作
    print("⚠️  WARNING: This will DELETE ALL DATA in the database!")
    print("Are you sure you want to continue? (yes/no): ", end="")

    confirmation = input().strip().lower()
    if confirmation != "yes":
        print("Operation cancelled.")
        return

    print("\nInitializing database manager...")
    db_manager = DatabaseManager()

    try:
        print("\n📦 Dropping all existing tables and views...")

        # 先手动删除所有视图和CASCADE删除表
        async with db_manager.async_engine.begin() as conn:
            # 删除所有视图
            await conn.execute(
                text(
                    """
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT viewname FROM pg_views WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP VIEW IF EXISTS ' || quote_ident(r.viewname) || ' CASCADE';
                    END LOOP;
                END $$;
            """
                )
            )
            logger.info("All views dropped")

        # 然后删除表
        await db_manager.drop_tables()
        logger.info("All tables dropped successfully")
        print("✅ All tables and views dropped")

        print("\n📦 Creating fresh tables...")
        await db_manager.create_tables()
        logger.info("All tables created successfully")
        print("✅ All tables created")

        print("\n✨ Database reset complete!")
        print("\nTables created:")
        print(
            "  - Binance: account_updates, order_updates, trade_updates, listen_keys, connection_status"
        )
        print("  - OKX: okx_account_balances, okx_positions, okx_orders, okx_trades")
        print(
            "  - Gate.io: gate_account_balances, gate_positions, gate_orders, gate_trades"
        )
        print("  - XT: (WebSocket models)")
        print("  - REST API: (REST models)")

    except Exception as e:
        logger.error("Database reset failed", error=str(e), exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(reset_database())
