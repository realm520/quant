#!/usr/bin/env python3
"""基于 PositionMetricsScheduler._get_or_calculate_daily_initial_positions 的测试脚本。

用途：
    - 给定 account_id / exchange / target_date
    - 按与正式调度逻辑相同的方式，调用
      PositionMetricsScheduler._get_or_calculate_daily_initial_positions
    - 打印返回的 initial_positions_yesterday（逐 symbol 展示各字段），
      并额外通过 _get_prior_left_positions_from_trades 打印
      截止 target_date 00:00 的累积已实现盈亏 cumulative_realized_pnl，
      方便你核对缓存与 SQL 是否一致。

注意：
    - 时间全部按 UTC 处理，target_date 对应的是 UTC 日期的 00:00。
    - 数据全部来源于数据库中的成交与 position_metrics 表。
"""

import asyncio
import sys
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.services.position_metrics_scheduler import PositionMetricsScheduler

# 与 debug_position_today.py 保持一致的数据库地址
DATABASE_URL = "postgresql+asyncpg://oliver:oliver%230987654321@quant-infra-pg-cluster.cluster-cjhorql2nmcs.ap-southeast-1.rds.amazonaws.com:5432/trading"

console = Console()


def _fmt_dec(v: Decimal, prec: int = 8) -> str:
    if v is None:
        return "0"
    q = v.quantize(Decimal(f"1e-{prec}"))
    return format(q, "f")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "测试 _get_or_calculate_daily_initial_positions："
            "给定账号/交易所/日期，输出按 symbol 的 initial_* 字段和累计已实现盈亏"
        )
    )
    parser.add_argument("--account-id", required=True, help="账号ID，例如 account_008 / binance_main_001")
    parser.add_argument("--exchange", required=True, choices=["xt", "binance"], help="交易所标识")
    parser.add_argument(
        "--date",
        type=str,
        required=False,
        help="目标日期（UTC），格式 YYYY-MM-DD；不填则默认使用昨天的日期",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        required=False,
        help="可选：仅查看某个 symbol 的 initial_* / 累计实现数据",
    )

    args = parser.parse_args()

    # 解析目标日期（UTC）
    today_utc = datetime.now(timezone.utc).date()
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = today_utc - timedelta(days=1)

    console.print(f"[cyan]目标日期 (UTC): {target_date} 00:00[/cyan]")
    console.print(f"[cyan]账号: {args.account_id}, 交易所: {args.exchange}[/cyan]\n")

    # 初始化 DB 与 Scheduler
    db_manager = DatabaseManager(database_url=DATABASE_URL)
    scheduler = PositionMetricsScheduler(db_manager=db_manager)

    async with db_manager.session() as session:
        # 合约乘数服务（与正式逻辑一致）
        contract_multiplier_service = ContractMultiplierService()

        def sync_getter(symbol: str) -> Decimal:
            return contract_multiplier_service.get_multiplier_sync(args.exchange, symbol)

        calc = PositionCalculator(
            session,
            exchange=args.exchange,
            account_id=args.account_id,
            contract_multiplier_getter=sync_getter,
        )

        # 1) 调用与正式调度相同的内部方法，获取 initial_positions
        initial_positions = await scheduler._get_or_calculate_daily_initial_positions(
            session=session,
            calc=calc,
            account_id=args.account_id,
            exchange=args.exchange,
            target_date=target_date,
        )

        # 2) 直接从成交记录计算“最早成交 -> target_date 00:00”区间的 prior 状态（含 cumulative_realized_pnl）
        target_start_time = datetime(target_date.year, target_date.month, target_date.day).replace(tzinfo=None)
        prior_from_trades = await scheduler._get_prior_left_positions_from_trades(
            calc=calc,
            target_start_time=target_start_time,
        )

        # 过滤 symbol（如果指定）
        if args.symbol:
            initial_positions = {k: v for k, v in initial_positions.items() if k == args.symbol}
            prior_from_trades = {k: v for k, v in prior_from_trades.items() if k == args.symbol}

        # 打印 initial_positions 结果
        if not initial_positions:
            console.print("[yellow]没有计算出任何 initial_positions（可能该账号该日之前无成交）[/yellow]")
        else:
            table = Table(title=f"{target_date} 00:00 初始持仓 (来自 _get_or_calculate_daily_initial_positions)")
            table.add_column("symbol", justify="left")
            table.add_column("initial_long_qty", justify="right")
            table.add_column("initial_short_qty", justify="right")
            table.add_column("initial_long_value", justify="right")
            table.add_column("initial_short_value", justify="right")

            for symbol, data in sorted(initial_positions.items()):
                table.add_row(
                    symbol,
                    _fmt_dec(data.get("initial_long_qty", Decimal("0")), 4),
                    _fmt_dec(data.get("initial_short_qty", Decimal("0")), 4),
                    _fmt_dec(data.get("initial_long_value", Decimal("0")), 8),
                    _fmt_dec(data.get("initial_short_value", Decimal("0")), 8),
                )

            console.print(table)

        # 打印从成交记录计算出的累计已实现盈亏（以及对应的 left_* 持仓）
        if not prior_from_trades:
            console.print("[yellow]没有从成交记录计算出 prior 状态（可能该账号该日之前无成交）[/yellow]")
        else:
            table2 = Table(title=f"{target_date} 00:00 截止的持仓与累积已实现盈亏 (来自 _get_prior_left_positions_from_trades)")
            table2.add_column("symbol", justify="left")
            table2.add_column("initial_long_qty", justify="right")
            table2.add_column("initial_short_qty", justify="right")
            table2.add_column("initial_long_value", justify="right")
            table2.add_column("initial_short_value", justify="right")
            table2.add_column("cumulative_realized_pnl", justify="right")

            for symbol, data in sorted(prior_from_trades.items()):
                table2.add_row(
                    symbol,
                    _fmt_dec(data.get("initial_long_qty", Decimal("0")), 4),
                    _fmt_dec(data.get("initial_short_qty", Decimal("0")), 4),
                    _fmt_dec(data.get("initial_long_value", Decimal("0")), 8),
                    _fmt_dec(data.get("initial_short_value", Decimal("0")), 8),
                    _fmt_dec(data.get("cumulative_realized_pnl", Decimal("0")), 4),
                )

            console.print("\n")
            console.print(table2)

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
