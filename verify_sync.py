#!/usr/bin/env python3
"""验证数据同步功能."""

import asyncio
import os
from tri_arb.storage.database import DatabaseManager
from sqlalchemy import select, text

async def verify_sync():
    """验证数据同步."""

    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trading")

    print("=" * 70)
    print("验证 XT WebSocket 数据同步功能")
    print("=" * 70)
    print()

    db_manager = DatabaseManager(database_url=database_url)

    try:
        async with db_manager.session() as session:
            # 查询 WebSocket 连接记录
            print("1. WebSocket 连接记录:")
            print("-" * 70)
            result = await session.execute(text("""
                SELECT
                    connection_id,
                    start_time,
                    end_time,
                    is_active,
                    total_messages,
                    account_updates,
                    position_updates,
                    order_updates,
                    trade_updates,
                    data_sync_count,
                    last_sync_time
                FROM xt_websocket_connections
                ORDER BY start_time DESC
                LIMIT 3
            """))
            rows = result.fetchall()

            if rows:
                for row in rows:
                    print(f"  连接ID: {row[0][:8]}...")
                    print(f"  开始时间: {row[1]}")
                    print(f"  结束时间: {row[2]}")
                    print(f"  是否活跃: {row[3]}")
                    print(f"  总消息数: {row[4]}")
                    print(f"  账户更新: {row[5]}")
                    print(f"  持仓更新: {row[6]}")
                    print(f"  订单更新: {row[7]}")
                    print(f"  成交更新: {row[8]}")
                    print(f"  数据同步次数: {row[9]}")
                    print(f"  最后同步时间: {row[10]}")
                    print()
            else:
                print("  ❌ 没有找到连接记录")
                print()

            # 查询账户更新记录
            print("2. 账户更新记录 (最近5条):")
            print("-" * 70)
            result = await session.execute(text("""
                SELECT
                    currency,
                    available,
                    frozen,
                    total,
                    update_time,
                    raw_data::jsonb->>'source' as source
                FROM xt_account_updates
                ORDER BY update_time DESC
                LIMIT 5
            """))
            rows = result.fetchall()

            if rows:
                for row in rows:
                    print(f"  币种: {row[0]}, 可用: {row[1]}, 冻结: {row[2]}, 总计: {row[3]}")
                    print(f"    更新时间: {row[4]}, 来源: {row[5] or 'websocket'}")
            else:
                print("  ❌ 没有找到账户更新记录")
            print()

            # 查询持仓更新记录
            print("3. 持仓更新记录 (最近5条):")
            print("-" * 70)
            result = await session.execute(text("""
                SELECT
                    symbol,
                    side,
                    quantity,
                    entry_price,
                    unrealized_pnl,
                    update_time,
                    raw_data::jsonb->>'source' as source
                FROM xt_position_updates
                ORDER BY update_time DESC
                LIMIT 5
            """))
            rows = result.fetchall()

            if rows:
                for row in rows:
                    print(f"  {row[0]} {row[1]}, 数量: {row[2]}, 开仓价: {row[3]}, 盈亏: {row[4]}")
                    print(f"    更新时间: {row[5]}, 来源: {row[6] or 'websocket'}")
            else:
                print("  ❌ 没有找到持仓更新记录")
            print()

            # 查询订单更新记录
            print("4. 订单更新记录 (最近5条):")
            print("-" * 70)
            result = await session.execute(text("""
                SELECT
                    symbol,
                    order_id,
                    side,
                    status,
                    quantity,
                    price,
                    update_time,
                    raw_data::jsonb->>'source' as source
                FROM xt_order_updates
                ORDER BY update_time DESC
                LIMIT 5
            """))
            rows = result.fetchall()

            if rows:
                for row in rows:
                    print(f"  {row[0]} 订单#{row[1][:8]}... {row[2]} {row[3]}")
                    print(f"    数量: {row[4]}, 价格: {row[5]}")
                    print(f"    更新时间: {row[6]}, 来源: {row[7] or 'websocket'}")
            else:
                print("  ❌ 没有找到订单更新记录")
            print()

            # 查询成交更新记录
            print("5. 成交更新记录 (最近5条):")
            print("-" * 70)
            result = await session.execute(text("""
                SELECT
                    symbol,
                    trade_id,
                    side,
                    price,
                    quantity,
                    update_time,
                    raw_data::jsonb->>'source' as source
                FROM xt_trade_updates
                ORDER BY update_time DESC
                LIMIT 5
            """))
            rows = result.fetchall()

            if rows:
                for row in rows:
                    print(f"  {row[0]} 成交#{row[1][:8]}... {row[2]}")
                    print(f"    价格: {row[3]}, 数量: {row[4]}")
                    print(f"    更新时间: {row[5]}, 来源: {row[6] or 'websocket'}")
            else:
                print("  ❌ 没有找到成交更新记录")
            print()

    except Exception as e:
        print(f"❌ 查询失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await db_manager.close()

    print("=" * 70)
    print("验证完成")
    print("=" * 70)
    print()
    print("✅ 功能说明:")
    print("  1. 连接记录显示了 WebSocket 连接的统计信息")
    print("  2. 数据更新记录显示了通过 REST API 同步的数据 (source=rest_sync)")
    print("  3. 如果 data_sync_count > 0，说明数据同步功能正常工作")
    print()

if __name__ == "__main__":
    asyncio.run(verify_sync())
