#!/usr/bin/env python3
"""测试零点快照功能（只计算，不写入数据库）

用途：
    - 使用 PositionCalculator 的日度逻辑计算零点快照
    - 直接显示计算结果，不写入数据库
    - 用于验证零点快照的计算是否正确
"""

import asyncio
import sys
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, Any

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from sqlalchemy import select, func, cast, Date

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService

# 数据库地址
DATABASE_URL = "postgresql+asyncpg://oliver:oliver%230987654321@quant-infra-pg-cluster.cluster-cjhorql2nmcs.ap-southeast-1.rds.amazonaws.com:5432/trading"

console = Console()


def _fmt_dec(v: Optional[Decimal], prec: int = 8) -> str:
    if v is None:
        return "0"
    q = v.quantize(Decimal(f"1e-{prec}"))
    return format(q, "f")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="测试零点快照：只计算并显示结果（不写入数据库）"
    )
    parser.add_argument("--account-id", required=True, help="账号ID，例如 account_008")
    parser.add_argument("--exchange", required=True, choices=["xt", "binance"], help="交易所标识")
    parser.add_argument("--symbol", type=str, required=False, help="可选：仅查看某个 symbol")
    parser.add_argument(
        "--start-date",
        type=str,
        required=False,
        help="起始日期，格式 YYYY-MM-DD；不填则自动取最早成交日",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=False,
        help="结束日期（包含），格式 YYYY-MM-DD；不填则默认昨天",
    )

    args = parser.parse_args()

    # 解析日期
    today_utc = datetime.now(timezone.utc).date()
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    else:
        end_date = today_utc - timedelta(days=1)

    # 初始化 DB
    db_manager = DatabaseManager(database_url=DATABASE_URL)

    async with db_manager.session() as session:
        # 合约乘数服务
        contract_multiplier_service = ContractMultiplierService()

        def sync_getter(symbol: str) -> Decimal:
            return contract_multiplier_service.get_multiplier_sync(args.exchange, symbol)

        calc = PositionCalculator(
            session,
            exchange=args.exchange,
            account_id=args.account_id,
            contract_multiplier_getter=sync_getter,
        )

        # 1. 查出最早成交日期
        time_column = (
            calc.TradeModel.transaction_time
            if calc.exchange == "binance"
            else calc.TradeModel.update_time
        )
        earliest_query = select(func.min(cast(time_column, Date)))
        if calc.exchange == "binance":
            earliest_query = earliest_query.where(calc.TradeModel.exchange == "binance_perp")
        if calc.account_id:
            earliest_query = earliest_query.where(calc.TradeModel.account_id == calc.account_id)
        if args.symbol:
            earliest_query = earliest_query.where(calc.TradeModel.symbol == args.symbol)

        earliest_result = await session.execute(earliest_query)
        earliest_date: Optional[date] = earliest_result.scalar()

        if not earliest_date:
            console.print("[yellow]该账号(以及可选 symbol) 没有任何成交记录[/yellow]")
            await db_manager.close()
            return

        if args.start_date:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
            if start_date < earliest_date:
                start_date = earliest_date
        else:
            start_date = earliest_date

        if end_date < start_date:
            console.print("[red]end_date 早于 start_date，参数不合法[/red]")
            await db_manager.close()
            return

        console.print(
            f"[cyan]账号: {args.account_id}, 交易所: {args.exchange}, "
            f"symbol: {args.symbol or 'ALL'}[/cyan]"
        )
        console.print(
            f"[cyan]trade_date 区间: {start_date} -> {end_date} (闭区间)[/cyan]\n"
        )

        # 2. 获取日度成交统计 & 日度盈亏序列
        console.print("[cyan]正在计算日度数据...[/cyan]")
        daily_stats = await calc.get_daily_trade_stats(
            start_date=start_date,
            end_date=end_date,
            symbol=args.symbol,
        )

        if not daily_stats:
            console.print("[yellow]在指定日期区间内没有任何成交记录[/yellow]")
            await db_manager.close()
            return

        daily_series = calc.calc_daily_realized_series(daily_stats)
        if not daily_series:
            console.print("[red]calc_daily_realized_series 返回为空[/red]")
            await db_manager.close()
            return

        console.print("[green]计算完成！[/green]\n")

        # 3. 显示每个日期的快照
        for trade_date in sorted(daily_series.keys()):
            if trade_date < start_date or trade_date > end_date:
                continue

            day_data: Dict[str, Dict[str, Decimal]] = daily_series.get(trade_date, {})
            if not day_data:
                continue

            for symbol, metrics in sorted(day_data.items()):
                if args.symbol and symbol != args.symbol:
                    continue

                # 获取当日最后一笔成交价
                day_end = datetime.combine(trade_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)
                day_start = datetime.combine(trade_date, datetime.min.time()).replace(tzinfo=None)
                close_prices = await calc._get_close_prices(day_start, day_end, symbol)
                close_prz = close_prices.get(symbol, Decimal("0"))

                # 计算未实现盈亏
                unrealized_pnl = Decimal("0")
                if close_prz > 0:
                    left_long_qty = metrics.get("close_left_long_qty", Decimal("0"))
                    left_short_qty = metrics.get("close_left_short_qty", Decimal("0"))
                    avg_buy_prz = metrics.get("avg_buy_prz", Decimal("0"))
                    avg_sell_prz = metrics.get("avg_sell_prz", Decimal("0"))
                    unrealized_pnl = (
                        left_long_qty * (close_prz - avg_buy_prz) +
                        left_short_qty * (avg_sell_prz - close_prz)
                    )

                daily_realized_pnl = metrics.get("daily_realized_pnl", Decimal("0"))
                cumulative_realized_pnl = metrics.get("cumulative_realized_pnl", Decimal("0"))
                daily_pnl = daily_realized_pnl + unrealized_pnl
                cumulative_pnl = cumulative_realized_pnl + unrealized_pnl

                table = Table(title=f"{symbol} - trade_date={trade_date} 收盘快照")
                table.add_column("字段", justify="left")
                table.add_column("值", justify="right")

                def add_row(field: str, value: Any, prec: int = 8):
                    if isinstance(value, Decimal):
                        table.add_row(field, _fmt_dec(value, prec))
                    else:
                        table.add_row(field, str(value))

                # 开盘持仓
                add_row("open_left_long_qty", metrics.get("open_left_long_qty", Decimal("0")), 4)
                add_row("open_left_short_qty", metrics.get("open_left_short_qty", Decimal("0")), 4)
                add_row("open_left_long_value", metrics.get("open_left_long_value", Decimal("0")), 8)
                add_row("open_left_short_value", metrics.get("open_left_short_value", Decimal("0")), 8)

                # 当日成交量
                add_row("daily_sum_buy_qty", metrics.get("daily_buy_volume", Decimal("0")), 4)
                add_row("daily_sum_sell_qty", metrics.get("daily_sell_volume", Decimal("0")), 4)
                add_row("daily_sum_buy_value", metrics.get("daily_buy_value", Decimal("0")), 8)
                add_row("daily_sum_sell_value", metrics.get("daily_sell_value", Decimal("0")), 8)

                # 总持仓
                add_row("long_qty", metrics.get("total_long_qty", Decimal("0")), 4)
                add_row("short_qty", metrics.get("total_short_qty", Decimal("0")), 4)
                add_row("long_value", metrics.get("total_long_value", Decimal("0")), 8)
                add_row("short_value", metrics.get("total_short_value", Decimal("0")), 8)

                # 平均价格
                add_row("avg_buy_prz", metrics.get("avg_buy_prz", Decimal("0")), 8)
                add_row("avg_sell_prz", metrics.get("avg_sell_prz", Decimal("0")), 8)

                # 轧差和已实现盈亏
                add_row("matched_qty", metrics.get("matched_qty", Decimal("0")), 4)
                add_row("daily_realized_pnl", daily_realized_pnl, 8)
                add_row("cumulative_realized_pnl", cumulative_realized_pnl, 8)

                # 收盘持仓
                add_row("left_long_qty", metrics.get("close_left_long_qty", Decimal("0")), 4)
                add_row("left_short_qty", metrics.get("close_left_short_qty", Decimal("0")), 4)
                add_row("left_long_value", metrics.get("close_left_long_value", Decimal("0")), 8)
                add_row("left_short_value", metrics.get("close_left_short_value", Decimal("0")), 8)

                # 收盘价和未实现盈亏
                add_row("close_prz", close_prz, 8)
                add_row("unrealized_pnl", unrealized_pnl, 8)

                # PnL 汇总
                add_row("daily_pnl", daily_pnl, 8)
                add_row("cumulative_pnl", cumulative_pnl, 8)

                console.print(table)
                console.print("")

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
