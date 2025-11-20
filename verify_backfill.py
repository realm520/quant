#!/usr/bin/env python3
"""XT WebSocket 断线回补功能验证脚本"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 添加项目路径
sys.path.insert(0, '/home/ubuntu/quant/src')

from tri_arb.storage.xt_websocket_models import XTOrderUpdate


async def count_orders_in_window(hours: int = 1) -> int:
    """统计指定时间窗口内的订单数量"""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres@localhost:5432/trading"
    )

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            time_threshold = datetime.utcnow() - timedelta(hours=hours)

            stmt = select(func.count(XTOrderUpdate.id)).where(
                XTOrderUpdate.update_time >= time_threshold
            )

            result = await session.execute(stmt)
            count = result.scalar()

            return count or 0

    finally:
        await engine.dispose()


async def count_rest_synced_orders(hours: int = 1) -> tuple[int, int]:
    """统计通过REST API回补的订单数量

    Returns:
        (rest_sync订单数, rest_sync_fixed_lookback订单数)
    """
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres@localhost:5432/trading"
    )

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            time_threshold = datetime.utcnow() - timedelta(hours=hours)

            # 统计 rest_sync 订单
            stmt_rest = select(func.count(XTOrderUpdate.id)).where(
                and_(
                    XTOrderUpdate.update_time >= time_threshold,
                    XTOrderUpdate.raw_data.cast(str).contains('"source": "rest_sync"')
                )
            )

            result_rest = await session.execute(stmt_rest)
            count_rest = result_rest.scalar() or 0

            # 统计 rest_sync_fixed_lookback 订单
            stmt_fixed = select(func.count(XTOrderUpdate.id)).where(
                and_(
                    XTOrderUpdate.update_time >= time_threshold,
                    XTOrderUpdate.raw_data.cast(str).contains('"source": "rest_sync_fixed_lookback"')
                )
            )

            result_fixed = await session.execute(stmt_fixed)
            count_fixed = result_fixed.scalar() or 0

            return count_rest, count_fixed

    finally:
        await engine.dispose()


async def show_recent_orders(hours: int = 1, limit: int = 10):
    """显示最近的订单记录"""
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres@localhost:5432/trading"
    )

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            time_threshold = datetime.utcnow() - timedelta(hours=hours)

            stmt = select(XTOrderUpdate).where(
                XTOrderUpdate.update_time >= time_threshold
            ).order_by(
                XTOrderUpdate.update_time.desc()
            ).limit(limit)

            result = await session.execute(stmt)
            orders = result.scalars().all()

            print(f"\n最近 {hours} 小时的订单记录（最多 {limit} 条）：")
            print("=" * 100)
            print(f"{'时间':<20} {'交易对':<15} {'订单ID':<20} {'方向':<6} {'状态':<10} {'来源':<30}")
            print("-" * 100)

            for order in orders:
                # 解析来源
                import json
                try:
                    raw_data = json.loads(order.raw_data)
                    source = raw_data.get("source", "websocket")
                except:
                    source = "unknown"

                print(
                    f"{order.update_time.strftime('%Y-%m-%d %H:%M:%S'):<20} "
                    f"{order.symbol:<15} "
                    f"{order.order_id:<20} "
                    f"{order.side:<6} "
                    f"{order.status:<10} "
                    f"{source:<30}"
                )

            print("=" * 100)
            print(f"\n总计：{len(orders)} 条订单\n")

    finally:
        await engine.dispose()


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python verify_backfill.py count_window <hours>  # 统计时间窗口内的订单数")
        print("  python verify_backfill.py count_rest <hours>    # 统计REST API回补的订单数")
        print("  python verify_backfill.py show <hours> <limit>  # 显示最近的订单")
        sys.exit(1)

    command = sys.argv[1]

    if command == "count_window":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        count = await count_orders_in_window(hours)
        print(count)

    elif command == "count_rest":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        count_rest, count_fixed = await count_rest_synced_orders(hours)
        print(f"{count_rest},{count_fixed}")

    elif command == "show":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        await show_recent_orders(hours, limit)

    else:
        print(f"未知命令: {command}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
