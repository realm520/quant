#!/usr/bin/env python3
"""诊断币安断线重连功能的脚本."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sqlalchemy import select, text
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.models import ConnectionStatus, OrderUpdate, TradeUpdate
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def diagnose():
    """诊断断线重连功能."""

    print("\n" + "="*80)
    print("币安断线重连功能诊断")
    print("="*80 + "\n")

    db_manager = DatabaseManager()

    try:
        async with db_manager.async_engine.begin() as conn:
            # 1. 检查connection_status表是否存在
            print("1️⃣ 检查connection_status表...")
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'connection_status'
                );
            """))
            table_exists = result.scalar()

            if not table_exists:
                print("   ❌ connection_status表不存在！")
                print("   💡 请运行迁移脚本: uv run python scripts/migrate_add_connection_status.py")
                return
            else:
                print("   ✅ connection_status表存在")

            # 2. 检查连接状态记录
            print("\n2️⃣ 检查连接状态记录...")
            async with db_manager.session() as session:
                result = await session.execute(
                    select(ConnectionStatus).where(ConnectionStatus.exchange == "binance_perp")
                )
                status = result.scalar_one_or_none()

                if status is None:
                    print("   ⚠️  没有binance_perp的连接状态记录")
                    print("   💡 这是正常的，首次连接时会自动创建")
                else:
                    print("   ✅ 找到连接状态记录:")
                    print(f"      - 当前状态: {'已连接' if status.is_connected else '已断开'}")
                    print(f"      - 最后连接时间: {status.last_connected_at}")
                    print(f"      - 最后断线时间: {status.last_disconnected_at}")
                    print(f"      - 总重连次数: {status.total_reconnect_count}")
                    print(f"      - 最后断线时长: {status.last_data_gap_seconds}秒" if status.last_data_gap_seconds else "      - 最后断线时长: N/A")
                    print(f"      - 最后订单事件: {status.last_order_event_time}")
                    print(f"      - 最后成交事件: {status.last_trade_event_time}")
                    print(f"      - 最后订单ID: {status.last_order_id}")
                    print(f"      - 最后成交ID: {status.last_trade_id}")

            # 3. 检查唯一性约束
            print("\n3️⃣ 检查唯一性约束...")

            # 检查订单表约束
            result = await conn.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'order_updates'
                AND constraint_name = 'uq_order_update_event';
            """))
            order_constraint = result.fetchone()

            if order_constraint:
                print("   ✅ order_updates表的唯一性约束存在")
            else:
                print("   ❌ order_updates表缺少唯一性约束")
                print("   💡 请运行迁移脚本")

            # 检查成交表约束
            result = await conn.execute(text("""
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_name = 'trade_updates'
                AND constraint_name = 'uq_trade_id';
            """))
            trade_constraint = result.fetchone()

            if trade_constraint:
                print("   ✅ trade_updates表的唯一性约束存在")
            else:
                print("   ❌ trade_updates表缺少唯一性约束")
                print("   💡 请运行迁移脚本")

            # 4. 检查最近的订单数据
            print("\n4️⃣ 检查最近1小时的订单数据...")
            cutoff_time = datetime.now() - timedelta(hours=1)

            async with db_manager.session() as session:
                result = await session.execute(
                    select(OrderUpdate)
                    .where(OrderUpdate.exchange == "binance_perp")
                    .where(OrderUpdate.event_time >= cutoff_time)
                    .order_by(OrderUpdate.event_time.desc())
                    .limit(10)
                )
                orders = result.scalars().all()

                if not orders:
                    print("   ⚠️  最近1小时没有订单记录")
                    print("   💡 这可能是正常的（如果没有交易）")
                else:
                    print(f"   ✅ 找到 {len(orders)} 条最近的订单记录:")
                    for order in orders[:5]:
                        print(f"      - {order.event_time}: {order.symbol} {order.side} {order.order_status} (ID: {order.order_id})")

            # 5. 检查最近的成交数据
            print("\n5️⃣ 检查最近1小时的成交数据...")

            async with db_manager.session() as session:
                result = await session.execute(
                    select(TradeUpdate)
                    .where(TradeUpdate.exchange == "binance_perp")
                    .where(TradeUpdate.event_time >= cutoff_time)
                    .order_by(TradeUpdate.event_time.desc())
                    .limit(10)
                )
                trades = result.scalars().all()

                if not trades:
                    print("   ⚠️  最近1小时没有成交记录")
                    print("   💡 这可能是正常的（如果没有成交）")
                else:
                    print(f"   ✅ 找到 {len(trades)} 条最近的成交记录:")
                    for trade in trades[:5]:
                        print(f"      - {trade.event_time}: {trade.symbol} {trade.side} {trade.quantity}@{trade.price} (Trade ID: {trade.trade_id})")

            # 6. 统计活跃交易对
            print("\n6️⃣ 检查最近24小时活跃的交易对...")
            cutoff_time_24h = datetime.now() - timedelta(hours=24)

            async with db_manager.session() as session:
                result = await session.execute(
                    select(OrderUpdate.symbol)
                    .where(OrderUpdate.exchange == "binance_perp")
                    .where(OrderUpdate.event_time >= cutoff_time_24h)
                    .distinct()
                )
                symbols = [row[0] for row in result.fetchall()]

                if not symbols:
                    print("   ⚠️  最近24小时没有活跃的交易对")
                    print("   💡 数据补全功能需要至少有一个活跃交易对")
                else:
                    print(f"   ✅ 找到 {len(symbols)} 个活跃交易对:")
                    for symbol in symbols:
                        print(f"      - {symbol}")

            # 7. 检查是否有重复数据
            print("\n7️⃣ 检查是否有重复的订单数据...")
            result = await conn.execute(text("""
                SELECT exchange, order_id, event_time, COUNT(*) as cnt
                FROM order_updates
                WHERE exchange = 'binance_perp'
                GROUP BY exchange, order_id, event_time
                HAVING COUNT(*) > 1
                LIMIT 5;
            """))
            duplicates = result.fetchall()

            if duplicates:
                print(f"   ⚠️  发现 {len(duplicates)} 组重复的订单数据:")
                for dup in duplicates:
                    print(f"      - order_id={dup[1]}, event_time={dup[2]}, count={dup[3]}")
                print("   💡 唯一性约束应该阻止这种情况")
            else:
                print("   ✅ 没有重复的订单数据")

            print("\n" + "="*80)
            print("诊断完成")
            print("="*80 + "\n")

            # 提供建议
            print("📋 下一步建议:")
            if not table_exists or not order_constraint or not trade_constraint:
                print("1. 运行数据库迁移脚本:")
                print("   uv run python scripts/migrate_add_connection_status.py")

            if not symbols:
                print("2. 确保有活跃的订单数据（至少下一个订单）")

            print("3. 测试断线重连:")
            print("   a. 启动订阅: uv run tri-arb subscribe --exchange binance_perp --channels account order")
            print("   b. 断开网络")
            print("   c. 下单")
            print("   d. 重连网络")
            print("   e. 等待5秒自动重连")
            print("   f. 查看日志中的数据补全信息")

            print("\n4. 查看实时日志:")
            print("   tail -f logs/tri_arb.log | grep -E '(data recovery|reconnect|missing_data)'")

    except Exception as e:
        print(f"\n❌ 诊断过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(diagnose())
