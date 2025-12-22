#!/usr/bin/env python3
"""测试脚本：打印第一次运行程序时创建的所有零点快照数据.

用法:
    python3 scripts/test_first_run_snapshots.py --account-id account_008 --exchange xt [--symbol tradoor_usdt]
"""

import asyncio
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from sqlalchemy import select, func, cast, Date

from tri_arb.config.logging import get_logger
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.storage.database import DatabaseManager

logger = get_logger(__name__)
console = Console()

# 数据库连接配置（请根据实际情况修改）
DATABASE_URL = "postgresql+asyncpg://oliver:oliver%230987654321@quant-infra-pg-cluster.cluster-cjhorql2nmcs.ap-southeast-1.rds.amazonaws.com:5432/trading"


def _format_decimal(value: Optional[Decimal], precision: int = 4) -> str:
    """格式化 Decimal 值为字符串."""
    if value is None:
        return "N/A"
    return f"{float(value):.{precision}f}"


async def main():
    parser = argparse.ArgumentParser(description="测试第一次运行程序时创建的所有零点快照")
    parser.add_argument("--account-id", required=True, help="账号ID")
    parser.add_argument("--exchange", required=True, choices=["binance", "xt"], help="交易所")
    parser.add_argument("--symbol", help="交易对（可选），如果不指定则处理所有交易对")
    args = parser.parse_args()
    
    # 初始化
    db_manager = DatabaseManager(database_url=DATABASE_URL)
    contract_multiplier_service = ContractMultiplierService()
    
    def sync_getter(symbol: str) -> Decimal:
        return contract_multiplier_service.get_multiplier_sync(args.exchange, symbol)
    
    async with db_manager.session() as session:
        # 创建计算器
        calc = PositionCalculator(
            session,
            exchange=args.exchange,
            account_id=args.account_id,
            contract_multiplier_getter=sync_getter,
        )
        
        # 1. 查询最早和最后成交日期
        time_column = (
            calc.TradeModel.transaction_time
            if args.exchange == "binance"
            else calc.TradeModel.update_time
        )
        
        earliest_query = select(func.min(cast(time_column, Date)))
        latest_query = select(func.max(cast(time_column, Date)))
        
        if args.exchange == "binance":
            earliest_query = earliest_query.where(calc.TradeModel.exchange == "binance_perp")
            latest_query = latest_query.where(calc.TradeModel.exchange == "binance_perp")
        if args.account_id:
            earliest_query = earliest_query.where(calc.TradeModel.account_id == args.account_id)
            latest_query = latest_query.where(calc.TradeModel.account_id == args.account_id)
        if args.symbol:
            earliest_query = earliest_query.where(calc.TradeModel.symbol == args.symbol)
            latest_query = latest_query.where(calc.TradeModel.symbol == args.symbol)
        
        earliest_result = await session.execute(earliest_query)
        latest_result = await session.execute(latest_query)
        earliest_date = earliest_result.scalar()
        latest_date = latest_result.scalar()
        
        if not earliest_date or not latest_date:
            console.print(f"[red]没有找到成交记录[/red]")
            return
        
        console.print(f"[green]成交日期范围: {earliest_date} -> {latest_date}[/green]")
        
        # 2. 获取日度成交统计
        console.print(f"[yellow]正在获取日度成交统计...[/yellow]")
        daily_stats = await calc.get_daily_trade_stats(
            start_date=earliest_date,
            end_date=latest_date,
            symbol=args.symbol,
        )
        
        if not daily_stats:
            console.print(f"[red]日度成交统计为空[/red]")
            return
        
        console.print(f"[green]找到 {len(daily_stats)} 天的成交数据[/green]")
        
        # 3. 计算每日和累积已实现盈亏
        console.print(f"[yellow]正在计算每日和累积已实现盈亏...[/yellow]")
        daily_series = calc.calc_daily_realized_series(daily_stats)
        
        if not daily_series:
            console.print(f"[red]日度计算结果为空[/red]")
            return
        
        console.print(f"[green]计算完成，共 {len(daily_series)} 天的数据[/green]\n")
        
        # 4. 打印所有快照数据
        console.print(f"[bold cyan]=== 所有零点快照数据 ===[/bold cyan]\n")
        
        for trade_date in sorted(daily_series.keys()):
            day_data = daily_series.get(trade_date, {})
            
            # 计算零点时间戳
            midnight_timestamp = datetime.combine(trade_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)
            
            console.print(f"[bold]交易日期: {trade_date} (快照时间戳: {midnight_timestamp})[/bold]")
            
            for symbol, metrics in sorted(day_data.items()):
                # 获取收盘价
                day_end = datetime.combine(trade_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)
                day_start = datetime.combine(trade_date, datetime.min.time()).replace(tzinfo=None)
                close_prices = await calc._get_close_prices(day_start, day_end, symbol)
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
                
                daily_realized_pnl = metrics.get("daily_realized_pnl", Decimal("0"))
                cumulative_realized_pnl = metrics.get("cumulative_realized_pnl", Decimal("0"))
                daily_pnl = daily_realized_pnl + unrealized_pnl
                cumulative_pnl = cumulative_realized_pnl + unrealized_pnl
                
                # 创建表格显示
                table = Table(title=f"{symbol} - trade_date={trade_date} 零点快照")
                table.add_column("字段", style="cyan")
                table.add_column("值", style="green", justify="right")
                
                # 开盘持仓
                table.add_row("open_left_long_qty", _format_decimal(metrics.get("open_left_long_qty", Decimal("0")), 2))
                table.add_row("open_left_short_qty", _format_decimal(metrics.get("open_left_short_qty", Decimal("0")), 2))
                table.add_row("open_left_long_value", _format_decimal(metrics.get("open_left_long_value", Decimal("0")), 4))
                table.add_row("open_left_short_value", _format_decimal(metrics.get("open_left_short_value", Decimal("0")), 4))
                table.add_row("", "")  # 空行
                
                # 当日成交量
                table.add_row("daily_sum_buy_qty", _format_decimal(metrics.get("daily_buy_volume", Decimal("0")), 2))
                table.add_row("daily_sum_sell_qty", _format_decimal(metrics.get("daily_sell_volume", Decimal("0")), 2))
                table.add_row("daily_sum_buy_value", _format_decimal(metrics.get("daily_buy_value", Decimal("0")), 4))
                table.add_row("daily_sum_sell_value", _format_decimal(metrics.get("daily_sell_value", Decimal("0")), 4))
                table.add_row("", "")  # 空行
                
                # 总持仓
                table.add_row("long_qty", _format_decimal(metrics.get("total_long_qty", Decimal("0")), 2))
                table.add_row("short_qty", _format_decimal(metrics.get("total_short_qty", Decimal("0")), 2))
                table.add_row("long_value", _format_decimal(metrics.get("total_long_value", Decimal("0")), 4))
                table.add_row("short_value", _format_decimal(metrics.get("total_short_value", Decimal("0")), 4))
                table.add_row("", "")  # 空行
                
                # 平均价格
                table.add_row("avg_buy_prz", _format_decimal(metrics.get("avg_buy_prz", Decimal("0")), 8))
                table.add_row("avg_sell_prz", _format_decimal(metrics.get("avg_sell_prz", Decimal("0")), 8))
                table.add_row("", "")  # 空行
                
                # 轧差和已实现盈亏
                table.add_row("matched_qty", _format_decimal(metrics.get("matched_qty", Decimal("0")), 2))
                table.add_row("daily_realized_pnl", _format_decimal(daily_realized_pnl, 8))
                table.add_row("cumulative_realized_pnl", _format_decimal(cumulative_realized_pnl, 8))
                table.add_row("", "")  # 空行
                
                # 收盘持仓
                table.add_row("left_long_qty", _format_decimal(left_long_qty, 2))
                table.add_row("left_short_qty", _format_decimal(left_short_qty, 2))
                table.add_row("left_long_value", _format_decimal(metrics.get("close_left_long_value", Decimal("0")), 4))
                table.add_row("left_short_value", _format_decimal(metrics.get("close_left_short_value", Decimal("0")), 4))
                table.add_row("", "")  # 空行
                
                # 收盘价和未实现盈亏
                table.add_row("close_prz", _format_decimal(close_prz, 8))
                table.add_row("unrealized_pnl", _format_decimal(unrealized_pnl, 8))
                table.add_row("", "")  # 空行
                
                # PnL 汇总
                table.add_row("daily_pnl", _format_decimal(daily_pnl, 8))
                table.add_row("cumulative_pnl", _format_decimal(cumulative_pnl, 8))
                
                console.print(table)
                console.print()  # 空行
        
        # 5. 打印汇总信息
        console.print(f"[bold cyan]=== 汇总信息 ===[/bold cyan]")
        console.print(f"账号: {args.account_id}")
        console.print(f"交易所: {args.exchange}")
        console.print(f"交易对: {args.symbol or '所有'}")
        console.print(f"成交日期范围: {earliest_date} -> {latest_date}")
        console.print(f"快照数量: {sum(len(day_data) for day_data in daily_series.values())}")
        console.print(f"快照时间戳范围: {datetime.combine(earliest_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)} -> {datetime.combine(latest_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)}")


if __name__ == "__main__":
    asyncio.run(main())
