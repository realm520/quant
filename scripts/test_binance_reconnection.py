#!/usr/bin/env python3
"""测试币安用户数据流断线重连和数据恢复功能.

使用方法:
    1. 启动测试: uv run python scripts/test_binance_reconnection.py
    2. 观察日志输出，验证功能是否正常
"""

import asyncio
import os
import signal
import sys
from datetime import datetime

from tri_arb.config.logging import get_logger
from tri_arb.storage.database import DatabaseManager
from tri_arb.services.binance_user_stream import BinanceUserStreamService
from sqlalchemy import select
from sqlalchemy import text

logger = get_logger(__name__)


async def query_connection_status(db_manager: DatabaseManager):
    """查询连接状态."""
    async with db_manager.session() as session:
        result = await session.execute(
            text("""
                SELECT
                    exchange,
                    is_connected,
                    last_connected_at,
                    last_disconnected_at,
                    total_reconnect_count,
                    last_data_gap_seconds,
                    last_order_event_time,
                    last_trade_event_time
                FROM connection_status
                WHERE exchange = 'binance_perp'
            """)
        )
        row = result.fetchone()
        if row:
            print("\n" + "=" * 80)
            print("📊 连接状态:")
            print("=" * 80)
            print(f"  交易所: {row[0]}")
            print(f"  是否连接: {'✅ 已连接' if row[1] else '❌ 未连接'}")
            print(f"  最后连接时间: {row[2]}")
            print(f"  最后断线时间: {row[3]}")
            print(f"  总重连次数: {row[4]}")
            print(f"  最后断线时长: {row[5]} 秒 ({round(row[5] / 60, 2) if row[5] else 0} 分钟)")
            print(f"  最后订单事件: {row[6]}")
            print(f"  最后成交事件: {row[7]}")
            print("=" * 80)
        else:
            print("\n⚠️  未找到连接状态记录")


async def query_recent_data(db_manager: DatabaseManager):
    """查询最近的订单和成交数据."""
    async with db_manager.session() as session:
        # 查询最近5条订单
        result = await session.execute(
            text("""
                SELECT
                    order_id,
                    symbol,
                    side,
                    order_status,
                    event_time,
                    original_quantity,
                    cumulative_filled_quantity
                FROM order_updates
                WHERE exchange = 'binance_perp'
                ORDER BY event_time DESC
                LIMIT 5
            """)
        )
        orders = result.fetchall()

        if orders:
            print("\n" + "=" * 80)
            print("📝 最近的订单 (前5条):")
            print("=" * 80)
            for order in orders:
                print(f"  订单ID: {order[0]}")
                print(f"    交易对: {order[1]} | 方向: {order[2]} | 状态: {order[3]}")
                print(f"    时间: {order[4]} | 数量: {order[5]} | 已成交: {order[6]}")
                print()
        else:
            print("\n⚠️  未找到订单记录")

        # 查询最近5条成交
        result = await session.execute(
            text("""
                SELECT
                    trade_id,
                    symbol,
                    side,
                    price,
                    quantity,
                    event_time
                FROM trade_updates
                WHERE exchange = 'binance_perp'
                ORDER BY event_time DESC
                LIMIT 5
            """)
        )
        trades = result.fetchall()

        if trades:
            print("\n" + "=" * 80)
            print("💰 最近的成交 (前5条):")
            print("=" * 80)
            for trade in trades:
                print(f"  成交ID: {trade[0]}")
                print(f"    交易对: {trade[1]} | 方向: {trade[2]}")
                print(f"    价格: {trade[3]} | 数量: {trade[4]}")
                print(f"    时间: {trade[5]}")
                print()
        else:
            print("\n⚠️  未找到成交记录")


async def test_reconnection():
    """测试断线重连功能."""

    # 获取环境变量
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    database_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trading")

    if not api_key or not api_secret:
        print("❌ 错误: 请设置环境变量 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        print("   export BINANCE_API_KEY=your_key")
        print("   export BINANCE_API_SECRET=your_secret")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("🚀 币安用户数据流断线重连测试")
    print("=" * 80)
    print()
    print("📌 测试说明:")
    print("  1. 程序将启动 WebSocket 连接")
    print("  2. 按 Ctrl+C 模拟断线")
    print("  3. 重新运行脚本测试数据恢复")
    print()
    print("⏱️  测试将在 5 秒后开始...")
    await asyncio.sleep(5)

    # 创建数据库管理器
    db_manager = DatabaseManager(database_url=database_url)

    # 查询当前状态
    print("\n📊 查询当前连接状态...")
    await query_connection_status(db_manager)
    await query_recent_data(db_manager)

    # 创建用户数据流服务
    print("\n🔌 启动用户数据流...")
    service = BinanceUserStreamService(
        api_key=api_key,
        api_secret=api_secret,
        db_manager=db_manager,
        auto_reconnect=True,
        display_format="table",
        enabled_channels=["account", "order"],
    )

    # 设置信号处理
    def signal_handler(signum, frame):
        print("\n\n⚠️  收到中断信号，正在停止...")
        asyncio.create_task(service.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 启动服务
        await service.start()
    except KeyboardInterrupt:
        print("\n✅ 服务已停止")
    except Exception as e:
        print(f"\n❌ 服务异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db_manager.close()

        # 再次查询状态
        print("\n📊 查询最终连接状态...")
        db_manager = DatabaseManager(database_url=database_url)
        await query_connection_status(db_manager)
        await query_recent_data(db_manager)
        await db_manager.close()

    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)
    print()
    print("💡 验证建议:")
    print("  1. 检查日志中是否有 'Data recovery completed' 消息")
    print("  2. 查看 'new_orders_saved' 和 'duplicate_orders_skipped' 统计")
    print("  3. 验证连接状态表中的 total_reconnect_count")
    print("  4. 确认订单和成交数据完整性")
    print()


if __name__ == "__main__":
    asyncio.run(test_reconnection())
