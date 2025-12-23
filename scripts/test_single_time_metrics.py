#!/usr/bin/env python3
"""
测试脚本：计算指定时间点的持仓指标数据
用于验证计算逻辑是否正确
"""

import asyncio
import argparse
from datetime import datetime, timedelta
from decimal import Decimal
import os
import sys

# 添加项目根目录到路径
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.storage.position_metrics_models import PositionMetrics
from rich.console import Console
from rich.table import Table

console = Console()


def _format_decimal(value: Decimal, precision: int = 8) -> str:
    """格式化 Decimal 值"""
    if value is None:
        return "0"
    return f"{value:.{precision}f}".rstrip('0').rstrip('.')


async def calculate_metrics_for_time(
    session: AsyncSession,
    calc: PositionCalculator,
    account_id: str,
    exchange: str,
    symbol: str,
    target_time: datetime,
):
    """计算指定时间点的指标数据"""
    # 获取该时间点所在日期的零点快照
    today_midnight = datetime.combine(target_time.date(), datetime.min.time()).replace(tzinfo=None)
    
    console.print(f"[cyan]计算时间点:[/cyan] {target_time}")
    console.print(f"[cyan]今日零点:[/cyan] {today_midnight}")
    console.print()
    
    # 获取今日零点快照
    midnight_snapshot_query = (
        select(PositionMetrics)
        .where(PositionMetrics.account_id == account_id)
        .where(PositionMetrics.exchange == exchange)
        .where(PositionMetrics.symbol == symbol)
        .where(PositionMetrics.timestamp == today_midnight)
        .limit(1)
    )
    midnight_result = await session.execute(midnight_snapshot_query)
    midnight_snapshot = midnight_result.scalar_one_or_none()
    
    if not midnight_snapshot:
        console.print(f"[red]错误:[/red] 未找到 {symbol} 在 {today_midnight} 的零点快照")
        return None
    
    console.print(f"[green]找到零点快照:[/green]")
    console.print(f"  matched_qty: {_format_decimal(midnight_snapshot.matched_qty)}")
    console.print(f"  left_long_qty: {_format_decimal(midnight_snapshot.left_long_qty)}")
    console.print(f"  left_short_qty: {_format_decimal(midnight_snapshot.left_short_qty)}")
    console.print(f"  long_value: {_format_decimal(midnight_snapshot.long_value)}")
    console.print(f"  short_value: {_format_decimal(midnight_snapshot.short_value)}")
    console.print(f"  avg_buy_prz: {_format_decimal(midnight_snapshot.avg_buy_prz)}")
    console.print(f"  avg_sell_prz: {_format_decimal(midnight_snapshot.avg_sell_prz)}")
    console.print(f"  cumulative_realized_pnl: {_format_decimal(midnight_snapshot.cumulative_realized_pnl)}")
    console.print()
    
    # 构建初始累计值
    midnight_matched_qty = midnight_snapshot.matched_qty or Decimal("0")
    midnight_left_long_qty = midnight_snapshot.left_long_qty or Decimal("0")
    midnight_left_short_qty = midnight_snapshot.left_short_qty or Decimal("0")
    
    cumulative_buy_vol = midnight_left_long_qty + midnight_matched_qty
    cumulative_sell_vol = midnight_left_short_qty + midnight_matched_qty
    
    midnight_long_value = midnight_snapshot.long_value or Decimal("0")
    midnight_short_value = midnight_snapshot.short_value or Decimal("0")
    midnight_avg_buy_prz = midnight_snapshot.avg_buy_prz or Decimal("0")
    midnight_avg_sell_prz = midnight_snapshot.avg_sell_prz or Decimal("0")
    
    initial_cumulative = {
        symbol: {
            "cumulative_buy_volume": cumulative_buy_vol,
            "cumulative_sell_volume": cumulative_sell_vol,
            "cumulative_buy_value": midnight_long_value,
            "cumulative_sell_value": midnight_short_value,
            "cumulative_realized_pnl": midnight_snapshot.cumulative_realized_pnl or Decimal("0"),
            "prev_matched_qty": midnight_matched_qty,
            "prev_avg_buy_prz": midnight_avg_buy_prz,
            "prev_avg_sell_prz": midnight_avg_sell_prz,
        }
    }
    
    console.print(f"[green]初始累计值:[/green]")
    console.print(f"  cumulative_buy_volume: {_format_decimal(cumulative_buy_vol)}")
    console.print(f"  cumulative_sell_volume: {_format_decimal(cumulative_sell_vol)}")
    console.print(f"  cumulative_buy_value: {_format_decimal(midnight_long_value)}")
    console.print(f"  cumulative_sell_value: {_format_decimal(midnight_short_value)}")
    console.print(f"  cumulative_realized_pnl: {_format_decimal(initial_cumulative[symbol]['cumulative_realized_pnl'])}")
    console.print(f"  prev_matched_qty: {_format_decimal(midnight_matched_qty)}")
    console.print()
    
    # 获取从今日零点到目标时间点的成交统计
    today_date = target_time.date()
    today_daily_stats = await calc.get_daily_trade_stats(
        start_date=today_date,
        end_date=today_date,
        symbol=symbol,
        end_time=target_time,
    )
    
    if not today_daily_stats or today_date not in today_daily_stats:
        console.print(f"[yellow]警告:[/yellow] 从 {today_midnight} 到 {target_time} 之间没有成交数据")
        return None
    
    day_stats = today_daily_stats.get(today_date, {}).get(symbol, {})
    console.print(f"[green]今日成交统计 (到 {target_time}):[/green]")
    console.print(f"  buy_volume: {_format_decimal(day_stats.get('buy_volume', Decimal('0')))}")
    console.print(f"  sell_volume: {_format_decimal(day_stats.get('sell_volume', Decimal('0')))}")
    console.print(f"  buy_trade_value: {_format_decimal(day_stats.get('buy_trade_value', Decimal('0')))}")
    console.print(f"  sell_trade_value: {_format_decimal(day_stats.get('sell_trade_value', Decimal('0')))}")
    console.print()
    
    # 使用 calc_daily_realized_series 的逻辑，但从初始累计值开始
    today_series_result = calc._calc_daily_realized_series_with_initial(
        daily_stats={today_date: today_daily_stats.get(today_date, {})},
        initial_cumulative=initial_cumulative,
    )
    
    if today_date not in today_series_result or symbol not in today_series_result[today_date]:
        console.print(f"[red]错误:[/red] 计算失败，未返回结果")
        return None
    
    metrics = today_series_result[today_date][symbol]
    
    # 获取收盘价
    close_prices = await calc._get_close_prices(today_midnight, target_time, symbol)
    close_prz = close_prices.get(symbol, Decimal("0"))
    
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
    
    # 计算累计值
    today_realized_pnl = metrics.get("daily_realized_pnl", Decimal("0"))
    cumulative_realized_pnl_at_midnight = midnight_snapshot.cumulative_realized_pnl or Decimal("0")
    cumulative_realized_pnl_now = cumulative_realized_pnl_at_midnight + today_realized_pnl
    cumulative_pnl = cumulative_realized_pnl_now + unrealized_pnl
    
    # 显示结果
    table = Table(title=f"{symbol} - {target_time} 计算结果", show_header=True, header_style="bold cyan")
    table.add_column("字段", justify="left", style="cyan")
    table.add_column("值", justify="right", style="green")
    
    table.add_row("open_left_long_qty", _format_decimal(midnight_snapshot.left_long_qty))
    table.add_row("open_left_short_qty", _format_decimal(midnight_snapshot.left_short_qty))
    table.add_row("open_left_long_value", _format_decimal(midnight_snapshot.left_long_value))
    table.add_row("open_left_short_value", _format_decimal(midnight_snapshot.left_short_value))
    table.add_row("", "")
    table.add_row("daily_sum_buy_qty", _format_decimal(metrics.get("daily_buy_volume", Decimal("0"))))
    table.add_row("daily_sum_sell_qty", _format_decimal(metrics.get("daily_sell_volume", Decimal("0"))))
    table.add_row("daily_sum_buy_value", _format_decimal(metrics.get("daily_buy_value", Decimal("0"))))
    table.add_row("daily_sum_sell_value", _format_decimal(metrics.get("daily_sell_value", Decimal("0"))))
    table.add_row("", "")
    table.add_row("long_qty", _format_decimal(metrics.get("total_long_qty", Decimal("0"))))
    table.add_row("short_qty", _format_decimal(metrics.get("total_short_qty", Decimal("0"))))
    table.add_row("long_value", _format_decimal(metrics.get("total_long_value", Decimal("0"))))
    table.add_row("short_value", _format_decimal(metrics.get("total_short_value", Decimal("0"))))
    table.add_row("", "")
    table.add_row("avg_buy_prz", _format_decimal(avg_buy_prz))
    table.add_row("avg_sell_prz", _format_decimal(avg_sell_prz))
    table.add_row("matched_qty", _format_decimal(metrics.get("matched_qty", Decimal("0"))))
    table.add_row("", "")
    table.add_row("daily_realized_pnl", _format_decimal(today_realized_pnl))
    table.add_row("cumulative_realized_pnl", _format_decimal(cumulative_realized_pnl_now))
    table.add_row("", "")
    table.add_row("left_long_qty", _format_decimal(left_long_qty))
    table.add_row("left_short_qty", _format_decimal(left_short_qty))
    table.add_row("left_long_value", _format_decimal(metrics.get("close_left_long_value", Decimal("0"))))
    table.add_row("left_short_value", _format_decimal(metrics.get("close_left_short_value", Decimal("0"))))
    table.add_row("", "")
    table.add_row("close_prz", _format_decimal(close_prz))
    table.add_row("unrealized_pnl", _format_decimal(unrealized_pnl))
    table.add_row("daily_pnl", _format_decimal(today_realized_pnl + unrealized_pnl))
    table.add_row("cumulative_pnl", _format_decimal(cumulative_pnl))
    
    console.print()
    console.print(table)
    
    return {
        "timestamp": target_time,
        "symbol": symbol,
        "metrics": metrics,
        "close_prz": close_prz,
        "unrealized_pnl": unrealized_pnl,
        "daily_realized_pnl": today_realized_pnl,
        "cumulative_realized_pnl": cumulative_realized_pnl_now,
        "cumulative_pnl": cumulative_pnl,
    }


async def main():
    parser = argparse.ArgumentParser(description="计算指定时间点的持仓指标数据")
    parser.add_argument("--account-id", required=True, help="账号ID")
    parser.add_argument("--exchange", required=True, help="交易所名称")
    parser.add_argument("--symbol", required=True, help="交易对符号")
    parser.add_argument("--date", required=True, help="日期 (YYYY-MM-DD)")
    parser.add_argument("--time", default="00:05", help="时间 (HH:MM)，默认 00:05")
    parser.add_argument("--database-url", help="数据库连接URL（可选，默认从环境变量读取）")
    
    args = parser.parse_args()
    
    # 解析日期和时间
    try:
        date_obj = datetime.strptime(args.date, "%Y-%m-%d").date()
        time_obj = datetime.strptime(args.time, "%H:%M").time()
        target_time = datetime.combine(date_obj, time_obj).replace(tzinfo=None)
    except ValueError as e:
        console.print(f"[red]错误:[/red] 日期或时间格式不正确: {e}")
        return
    
    # 获取数据库连接URL
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        console.print("[red]错误:[/red] 未设置数据库连接URL，请使用 --database-url 参数或设置 DATABASE_URL 环境变量")
        return
    
    # 初始化数据库管理器
    db_manager = DatabaseManager(database_url)
    
    # 初始化合约乘数服务
    contract_multiplier_service = ContractMultiplierService()
    
    async with db_manager.session() as session:
        # 创建合约乘数获取器
        def contract_multiplier_getter(symbol: str) -> Decimal:
            return contract_multiplier_service.get_multiplier_sync(args.exchange, symbol)
        
        # 创建位置计算器
        calc = PositionCalculator(session, contract_multiplier_getter)
        
        # 计算指标
        result = await calculate_metrics_for_time(
            session=session,
            calc=calc,
            account_id=args.account_id,
            exchange=args.exchange,
            symbol=args.symbol,
            target_time=target_time,
        )
        
        if result:
            console.print()
            console.print("[green]计算完成！[/green]")


if __name__ == "__main__":
    asyncio.run(main())
