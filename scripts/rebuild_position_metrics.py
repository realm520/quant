#!/usr/bin/env python3
"""
重建 position_metrics 表的所有数据。

用于修复 avg_sell_prz 计算错误导致的数据问题。
会重新计算所有零点快照和实时数据。
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.position_metrics_scheduler import PositionMetricsScheduler
from tri_arb.storage.position_metrics_models import PositionMetrics
from sqlalchemy.dialects.postgresql import insert as pg_insert


async def _calculate_metrics_for_time(
    session: AsyncSession,
    calc: PositionCalculator,
    account_id: str,
    exchange: str,
    symbol: str | None,
    target_time: datetime,
):
    """计算指定时间点的指标数据。
    
    这个函数复用了 position_metrics_scheduler.py 中的计算逻辑。
    """
    # 获取该时间点所在日期的零点快照
    today_midnight = datetime.combine(target_time.date(), datetime.min.time()).replace(tzinfo=None)
    
    # 获取今日零点快照的所有 symbol 数据
    all_today_snapshots_query = (
        select(PositionMetrics)
        .where(PositionMetrics.account_id == account_id)
        .where(PositionMetrics.exchange == exchange)
        .where(PositionMetrics.timestamp == today_midnight)
    )
    if symbol:
        all_today_snapshots_query = all_today_snapshots_query.where(PositionMetrics.symbol == symbol)
    
    all_snapshots_result = await session.execute(all_today_snapshots_query)
    all_snapshots = all_snapshots_result.scalars().all()
    
    if not all_snapshots:
        return  # 如果没有零点快照，跳过
    
    # 构建初始累计值（从今日零点快照读取）
    initial_cumulative = {}
    for snapshot in all_snapshots:
        midnight_matched_qty = snapshot.matched_qty or Decimal("0")
        midnight_left_long_qty = snapshot.left_long_qty or Decimal("0")
        midnight_left_short_qty = snapshot.left_short_qty or Decimal("0")
        
        cumulative_buy_vol = midnight_left_long_qty + midnight_matched_qty
        cumulative_sell_vol = midnight_left_short_qty + midnight_matched_qty
        
        midnight_long_value = snapshot.long_value or Decimal("0")
        midnight_short_value = snapshot.short_value or Decimal("0")
        midnight_avg_buy_prz = snapshot.avg_buy_prz or Decimal("0")
        midnight_avg_sell_prz = snapshot.avg_sell_prz or Decimal("0")
        
        initial_cumulative[snapshot.symbol] = {
            "cumulative_buy_volume": cumulative_buy_vol,
            "cumulative_sell_volume": cumulative_sell_vol,
            "cumulative_buy_value": midnight_long_value,
            "cumulative_sell_value": midnight_short_value,
            "cumulative_realized_pnl": snapshot.cumulative_realized_pnl or Decimal("0"),
            "prev_matched_qty": midnight_matched_qty,
            "prev_avg_buy_prz": midnight_avg_buy_prz,
            "prev_avg_sell_prz": midnight_avg_sell_prz,
        }
    
    # 获取从今日零点到目标时间点的成交统计
    today_date = target_time.date()
    today_daily_stats = await calc.get_daily_trade_stats(
        start_date=today_date,
        end_date=today_date,
        symbol=symbol,
        end_time=target_time,
    )
    
    if not today_daily_stats or today_date not in today_daily_stats:
        return  # 如果没有成交数据，跳过
    
    # 使用 calc_daily_realized_series 的逻辑，但从初始累计值开始
    today_series_result = calc._calc_daily_realized_series_with_initial(
        daily_stats={today_date: today_daily_stats.get(today_date, {})},
        initial_cumulative=initial_cumulative,
    )
    
    # 转换为指标格式
    today_metrics = {}
    if today_date in today_series_result:
        for sym, metrics in today_series_result[today_date].items():
            if symbol and sym != symbol:
                continue
            
            # 获取收盘价（到目标时间点的最后一笔成交价）
            close_prices = await calc._get_close_prices(today_midnight, target_time, sym)
            close_prz = close_prices.get(sym, Decimal("0"))
            
            # 计算未实现盈亏
            left_long_qty = metrics.get("close_left_long_qty", Decimal("0"))
            left_short_qty = metrics.get("close_left_short_qty", Decimal("0"))
            avg_buy_prz = metrics.get("avg_buy_prz", Decimal("0"))
            avg_sell_prz = metrics.get("avg_sell_prz", Decimal("0"))
            unrealized_pnl = Decimal("0")
            if close_prz > 0:
                unrealized_pnl = (
                    left_long_qty * (close_prz - avg_buy_prz) +
                    left_short_qty * (avg_sell_prz - close_prz)
                )
            
            today_metrics[sym] = {
                "buy_volume": metrics.get("daily_buy_volume", Decimal("0")),
                "sell_volume": metrics.get("daily_sell_volume", Decimal("0")),
                "buy_trade_value": metrics.get("daily_buy_value", Decimal("0")),
                "sell_trade_value": metrics.get("daily_sell_value", Decimal("0")),
                "long_qty": metrics.get("total_long_qty", Decimal("0")),
                "short_qty": metrics.get("total_short_qty", Decimal("0")),
                "long_value": metrics.get("total_long_value", Decimal("0")),
                "short_value": metrics.get("total_short_value", Decimal("0")),
                "avg_buy_prz": avg_buy_prz,
                "avg_sell_prz": avg_sell_prz,
                "matched_qty": metrics.get("matched_qty", Decimal("0")),
                "left_long_qty": left_long_qty,
                "left_short_qty": left_short_qty,
                "left_long_value": metrics.get("close_left_long_value", Decimal("0")),
                "left_short_value": metrics.get("close_left_short_value", Decimal("0")),
                "close_prz": close_prz,
                "unrealized_pnl": unrealized_pnl,
                "daily_realized_pnl": metrics.get("daily_realized_pnl", Decimal("0")),
                "cumulative_realized_pnl": metrics.get("cumulative_realized_pnl", Decimal("0")),
            }
    
    # 存储每个交易对的指标
    for sym, m in today_metrics.items():
        if symbol and sym != symbol:
            continue
        
        # 获取零点快照
        midnight_snapshot_query = (
            select(PositionMetrics)
            .where(PositionMetrics.account_id == account_id)
            .where(PositionMetrics.exchange == exchange)
            .where(PositionMetrics.symbol == sym)
            .where(PositionMetrics.timestamp == today_midnight)
            .limit(1)
        )
        midnight_result = await session.execute(midnight_snapshot_query)
        midnight_snapshot = midnight_result.scalar_one_or_none()
        
        midnight_matched_qty = Decimal("0")
        cumulative_realized_pnl_at_midnight = Decimal("0")
        if midnight_snapshot:
            midnight_matched_qty = midnight_snapshot.matched_qty or Decimal("0")
            cumulative_realized_pnl_at_midnight = midnight_snapshot.cumulative_realized_pnl or Decimal("0")
        
        today_unrealized_pnl = m.get("unrealized_pnl", Decimal("0"))
        today_realized_pnl = m.get("daily_realized_pnl", Decimal("0"))
        cumulative_realized_pnl_now = cumulative_realized_pnl_at_midnight + today_realized_pnl
        cumulative_pnl = cumulative_realized_pnl_now + today_unrealized_pnl
        
        open_left_long_qty_from_snapshot = midnight_snapshot.left_long_qty if midnight_snapshot else Decimal("0")
        open_left_short_qty_from_snapshot = midnight_snapshot.left_short_qty if midnight_snapshot else Decimal("0")
        open_left_long_value_from_snapshot = midnight_snapshot.left_long_value if midnight_snapshot else Decimal("0")
        open_left_short_value_from_snapshot = midnight_snapshot.left_short_value if midnight_snapshot else Decimal("0")
        
        # 使用 UPSERT 插入/更新数据
        stmt = pg_insert(PositionMetrics).values(
            timestamp=target_time,
            account_id=account_id,
            exchange=exchange,
            symbol=sym,
            open_left_long_qty=open_left_long_qty_from_snapshot,
            open_left_short_qty=open_left_short_qty_from_snapshot,
            open_left_long_value=open_left_long_value_from_snapshot,
            open_left_short_value=open_left_short_value_from_snapshot,
            daily_sum_buy_qty=m.get("buy_volume", Decimal("0")),
            daily_sum_sell_qty=m.get("sell_volume", Decimal("0")),
            daily_sum_buy_value=m.get("buy_trade_value", Decimal("0")),
            daily_sum_sell_value=m.get("sell_trade_value", Decimal("0")),
            long_qty=m.get("long_qty", Decimal("0")),
            short_qty=m.get("short_qty", Decimal("0")),
            long_value=m.get("long_value", Decimal("0")),
            short_value=m.get("short_value", Decimal("0")),
            avg_buy_prz=m.get("avg_buy_prz", Decimal("0")),
            avg_sell_prz=m.get("avg_sell_prz", Decimal("0")),
            matched_qty=m.get("matched_qty", Decimal("0")),
            daily_realized_pnl=today_realized_pnl,
            cumulative_realized_pnl=cumulative_realized_pnl_now,
            left_long_qty=m.get("left_long_qty", Decimal("0")),
            left_short_qty=m.get("left_short_qty", Decimal("0")),
            left_long_value=m.get("left_long_value", Decimal("0")),
            left_short_value=m.get("left_short_value", Decimal("0")),
            close_prz=m.get("close_prz", Decimal("0")),
            unrealized_pnl=today_unrealized_pnl,
            daily_pnl=today_realized_pnl + today_unrealized_pnl,
            cumulative_pnl=cumulative_pnl,
        )
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["timestamp", "account_id", "exchange", "symbol"],
            set_={
                "open_left_long_qty": stmt.excluded.open_left_long_qty,
                "open_left_short_qty": stmt.excluded.open_left_short_qty,
                "open_left_long_value": stmt.excluded.open_left_long_value,
                "open_left_short_value": stmt.excluded.open_left_short_value,
                "daily_sum_buy_qty": stmt.excluded.daily_sum_buy_qty,
                "daily_sum_sell_qty": stmt.excluded.daily_sum_sell_qty,
                "daily_sum_buy_value": stmt.excluded.daily_sum_buy_value,
                "daily_sum_sell_value": stmt.excluded.daily_sum_sell_value,
                "long_qty": stmt.excluded.long_qty,
                "short_qty": stmt.excluded.short_qty,
                "long_value": stmt.excluded.long_value,
                "short_value": stmt.excluded.short_value,
                "avg_buy_prz": stmt.excluded.avg_buy_prz,
                "avg_sell_prz": stmt.excluded.avg_sell_prz,
                "matched_qty": stmt.excluded.matched_qty,
                "daily_realized_pnl": stmt.excluded.daily_realized_pnl,
                "cumulative_realized_pnl": stmt.excluded.cumulative_realized_pnl,
                "left_long_qty": stmt.excluded.left_long_qty,
                "left_short_qty": stmt.excluded.left_short_qty,
                "left_long_value": stmt.excluded.left_long_value,
                "left_short_value": stmt.excluded.left_short_value,
                "close_prz": stmt.excluded.close_prz,
                "unrealized_pnl": stmt.excluded.unrealized_pnl,
                "daily_pnl": stmt.excluded.daily_pnl,
                "cumulative_pnl": stmt.excluded.cumulative_pnl,
            }
        )
        
        await session.execute(stmt)


async def rebuild_all_metrics(
    account_id: str,
    exchange: str,
    symbol: str | None = None,
    database_url: str | None = None,
):
    """重建缺失的 position_metrics 数据。
    
    只插入缺失的数据，不删除已有数据。
    每5分钟一个时间点。
    
    Args:
        account_id: 账号ID
        exchange: 交易所名称
        symbol: 交易对（可选），None 表示所有交易对
        database_url: 数据库连接URL（可选），如果不提供则从环境变量读取
    """
    # 获取数据库连接URL
    if database_url is None:
        database_url = os.getenv("DATABASE_URL")
    
    if database_url is None:
        raise ValueError(
            "数据库连接URL未设置。请通过以下方式之一设置：\n"
            "1. 设置环境变量 DATABASE_URL:\n"
            "   export DATABASE_URL='postgresql+asyncpg://user:password@host:port/dbname'\n"
            "2. 或在命令行传入 --database-url 参数"
        )
    
    db_manager = DatabaseManager(database_url=database_url)
    scheduler = PositionMetricsScheduler(db_manager)
    
    async with db_manager.session() as session:
        try:
            # 1. 查询时间范围（从数据库或交易表）
            print(f"正在查询时间范围...")
            
            # 2. 创建合约乘数服务（如果需要）
            from tri_arb.services.contract_multiplier_service import ContractMultiplierService
            contract_multiplier_service = ContractMultiplierService()
            
            # 创建合约乘数 getter
            contract_multiplier_getter = None
            if contract_multiplier_service:
                # 使用同步方法，直接调用公开 API（不需要 API key）
                service = contract_multiplier_service
                exchange_name = exchange
                
                # 使用闭包捕获 service 和 exchange
                def sync_getter(symbol: str) -> Decimal:
                    """同步获取合约乘数."""
                    try:
                        return service.get_multiplier_sync(exchange_name, symbol)
                    except Exception:
                        return Decimal("1")
                
                contract_multiplier_getter = sync_getter
            
            # 2. 创建 PositionCalculator（需要在 session 内创建）
            calc = PositionCalculator(
                session,
                exchange=exchange,
                account_id=account_id,
                contract_multiplier_getter=contract_multiplier_getter,
            )
            
            # 查询时间范围（从交易表查询，确定需要计算的时间范围）
            from tri_arb.storage.xt_websocket_models import XTTradeUpdate
            from tri_arb.storage.models import TradeUpdate
            
            TradeModel = XTTradeUpdate if exchange == "xt" else TradeUpdate
            time_column = (
                TradeModel.transaction_time if exchange == "binance"
                else TradeModel.update_time
            )
            
            trade_time_query = select(
                func.min(time_column).label('min_time'),
                func.max(time_column).label('max_time')
            )
            if exchange == "binance":
                trade_time_query = trade_time_query.where(TradeModel.exchange == "binance_perp")
            if account_id:
                trade_time_query = trade_time_query.where(TradeModel.account_id == account_id)
            if symbol:
                trade_time_query = trade_time_query.where(TradeModel.symbol == symbol)
            
            trade_time_result = await session.execute(trade_time_query)
            trade_time_range = trade_time_result.first()
            
            if not trade_time_range or not trade_time_range.min_time or not trade_time_range.max_time:
                print(f"⚠️  未找到交易数据，无法确定时间范围")
                return
            
            # 从最早交易日期开始，到最新交易日期结束
            min_date = trade_time_range.min_time.date()
            max_date = trade_time_range.max_time.date()
            min_time = datetime.combine(min_date, datetime.min.time()).replace(tzinfo=None)
            max_time = datetime.combine(max_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)
            print(f"从交易表找到时间范围: {min_time} -> {max_time}")
            
            # 4. 重建零点快照（如果不存在）
            print(f"正在重建零点快照（如果不存在）...")
            await scheduler._rebuild_midnight_snapshots(
                session=session,
                calc=calc,
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
            )
            await session.commit()
            print(f"零点快照重建完成")
            
            # 5. 查询数据库中已有的时间点（用于跳过已存在的数据）
            print(f"正在查询数据库中已有的时间点...")
            existing_times_query = select(
                PositionMetrics.timestamp,
                PositionMetrics.symbol
            ).where(
                PositionMetrics.account_id == account_id
            ).where(
                PositionMetrics.exchange == exchange
            )
            if symbol:
                existing_times_query = existing_times_query.where(PositionMetrics.symbol == symbol)
            
            existing_times_result = await session.execute(existing_times_query)
            # 使用 (timestamp, symbol) 作为键，因为同一个时间点可能有多个 symbol
            existing_times_set = {(row[0], row[1]) for row in existing_times_result.all()}
            print(f"数据库中已有 {len(existing_times_set)} 条记录")
            
            # 6. 计算缺失的实时数据（每5分钟间隔）
            print(f"正在计算缺失的实时数据（每5分钟间隔）...")
            
            # 从最小时间开始，每隔5分钟计算一次
            current_time = min_time
            # 如果不是整点，调整到下一个5分钟间隔
            if current_time.minute % 5 != 0:
                current_time = current_time.replace(minute=(current_time.minute // 5 + 1) * 5, second=0, microsecond=0)
            
            interval = timedelta(minutes=5)
            calculated_count = 0
            skipped_count = 0
            
            # 计算需要处理的时间点总数
            total_intervals = int((max_time - current_time).total_seconds() / 300) + 1
            print(f"需要检查 {total_intervals} 个时间点（每5分钟间隔）")
            
            while current_time <= max_time:
                # 跳过零点（零点快照已经重建，如果需要更新会在上面处理）
                if current_time.hour == 0 and current_time.minute == 0:
                    current_time += interval
                    continue
                
                try:
                    # 计算该时间点的数据
                    # _calculate_metrics_for_time 内部会为每个 symbol 检查并跳过已存在的数据
                    # 但为了效率，我们先检查是否所有 symbol 都已存在（如果指定了 symbol）
                    if symbol:
                        # 如果指定了 symbol，检查该时间点是否已存在
                        if (current_time, symbol) in existing_times_set:
                            skipped_count += 1
                            current_time += interval
                            continue
                    
                    # 计算该时间点的数据（函数内部使用 UPSERT，不会重复插入）
                    await _calculate_metrics_for_time(
                        session=session,
                        calc=calc,
                        account_id=account_id,
                        exchange=exchange,
                        symbol=symbol,
                        target_time=current_time,
                    )
                    calculated_count += 1
                    
                    # 每100个时间点提交一次
                    if calculated_count % 100 == 0:
                        await session.commit()
                        print(f"已计算 {calculated_count} 个时间点，跳过 {skipped_count} 个已存在的时间点...")
                except Exception as e:
                    print(f"计算时间点 {current_time} 的数据时出错: {e}")
                    await session.rollback()
                
                current_time += interval
            
            await session.commit()
            print(f"✅ 已计算 {calculated_count} 个缺失的时间点")
            print(f"✅ 跳过 {skipped_count} 个已存在的时间点")
            
            print(f"\n数据重建完成！")
            print(f"✅ 零点快照已重建（如果不存在）")
            print(f"✅ 缺失的实时数据已插入（每5分钟间隔）")
            
        except Exception as e:
            print(f"错误：{e}")
            await session.rollback()
            raise


async def main():
    parser = argparse.ArgumentParser(description="重建 position_metrics 表的所有数据")
    parser.add_argument("--account-id", required=True, help="账号ID")
    parser.add_argument("--exchange", required=True, help="交易所名称（如 xt, binance）")
    parser.add_argument("--symbol", default=None, help="交易对（可选），不指定则处理所有交易对")
    parser.add_argument(
        "--database-url",
        default=None,
        help="数据库连接URL（可选），如果不提供则从环境变量 DATABASE_URL 读取",
    )
    
    args = parser.parse_args()
    
    await rebuild_all_metrics(
        account_id=args.account_id,
        exchange=args.exchange,
        symbol=args.symbol,
        database_url=args.database_url,
    )


if __name__ == "__main__":
    asyncio.run(main())
