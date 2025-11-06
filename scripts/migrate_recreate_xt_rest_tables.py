#!/usr/bin/env python3
"""数据库迁移脚本：重新创建XT REST API表.

此脚本用于：
1. 删除旧的XT REST API表（xt_spot_balances, xt_perp_balances, xt_perp_positions）
2. 重新创建这些表，包含所有新字段（未实现盈亏、已实现盈亏等）

运行方式：
    uv run python scripts/migrate_recreate_xt_rest_tables.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import text
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_rest_models import Base as XTRestBase
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def main():
    """执行数据库迁移."""
    logger.info("Starting database migration: recreate XT REST API tables with new fields")
    
    db_manager = DatabaseManager()
    
    try:
        async with db_manager.async_engine.begin() as conn:
            # 1. 删除旧的XT REST API表
            logger.info("Dropping old XT REST API tables...")
            
            await conn.execute(text("DROP TABLE IF EXISTS xt_perp_positions CASCADE;"))
            logger.info("✓ Dropped xt_perp_positions")
            
            await conn.execute(text("DROP TABLE IF EXISTS xt_perp_balances CASCADE;"))
            logger.info("✓ Dropped xt_perp_balances")
            
            await conn.execute(text("DROP TABLE IF EXISTS xt_spot_balances CASCADE;"))
            logger.info("✓ Dropped xt_spot_balances")
            
            # 2. 重新创建XT REST API表（包含所有新字段）
            logger.info("Creating new XT REST API tables with all fields...")
            await conn.run_sync(XTRestBase.metadata.create_all)
            logger.info("✓ Created XT REST API tables with new fields")
            
        logger.info("✅ Migration completed successfully!")
        print("\n✅ XT REST API tables recreated with new fields:")
        print("  - xt_spot_balances")
        print("  - xt_perp_balances (with unrealized_pnl, realized_pnl, equity, margin, margin_ratio)")
        print("  - xt_perp_positions (with realized_pnl)")
        
    except Exception as e:
        logger.error("Migration failed", error=str(e), exc_info=True)
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())

