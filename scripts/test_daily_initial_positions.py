#!/usr/bin/env python3
"""零点快照验证脚本

用途：
    - 给定 account_id / exchange / 起止日期 / 可选 symbol
    - 使用 PositionCalculator 的日度逻辑 (get_daily_trade_stats + calc_daily_realized_series)
      计算 **理论上的每日收盘快照**（即第二天 00:00 的零点快照）
    - 同时从 position_metrics 表读取对应 timestamp 的记录
    - 把两者按字段逐项对比，验证零点快照写入是否符合日度逻辑

说明：
    - 零点快照含义：trade_date 当天的收盘情况，写在 trade_date+1 这天的 00:00
      例如：2025-12-11 的收盘 → timestamp = 2025-12-12 00:00 的记录
    - cumulative_realized_pnl：从最早成交日开始，每日 daily_realized_pnl 的累积
    - 本脚本 **不会写数据库**，只读；但可以选择先调用调度里的
      _rebuild_midnight_snapshots 来重建零点快照再做对比
"""

import asyncio
import sys
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from sqlalchemy import select, func, cast, Date

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.services.position_metrics_scheduler import PositionMetricsScheduler
from tri_arb.storage.position_metrics_models import PositionMetrics

# 与 debug_position_today.py 保持一致的数据库地址
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
        description=(
            "验证 position_metrics 零点快照是否符合日度计算逻辑："
            "一边用 PositionCalculator 日度逻辑算出理论快照，一边从表里读实际快照并对比"
        )
    )
    parser.add_argument("--account-id", required=True, help="账号ID，例如 account_008 / binance_main_001")
    parser.add_argument("--exchange", required=True, choices=["xt", "binance"], help="交易所标识")
    parser.add_argument("--symbol", type=str, required=False, help="可选：仅查看某个 symbol")
    parser.add_argument(
        "--start-date",
        type=str,
        required=False,
        help="起始 trade_date，格式 YYYY-MM-DD；不填则自动取该账号+symbol 最早成交日",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=False,
        help="结束 trade_date（包含），格式 YYYY-MM-DD；不填则默认昨天",
    )
    parser.add_argument(
        "--rebuild-first",
        action="store_true",
        help="在对比前先调用 _rebuild_midnight_snapshots 重建所有零点快照",
    )

    args = parser.parse_args()

    # 解析日期
    today_utc = datetime.now(timezone.utc).date()
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()
    else:
        end_date = today_utc - timedelta(days=1)

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

        # 如需要，先重建零点快照（会覆盖原有零点行）
        if args.rebuild_first:
            console.print("[cyan]先重建所有零点快照...[/cyan]")
            await scheduler._rebuild_midnight_snapshots(
                session=session,
                calc=calc,
                account_id=args.account_id,
                exchange=args.exchange,
                symbol=args.symbol,  # 只重建单个 symbol 更快；为 None 则全部
            )

        # 1) 计算该账号(+symbol)的最早成交日（用于日度累积）
        time_column = (
            calc.TradeModel.transaction_time
            if calc.exchange == "binance"
            else calc.TradeModel.update_time
        )
        earliest_query = select(func.min(cast(time_column, Date)))
        if calc.exchange == "binance":
            # 这里按你之前逻辑，binance 合约使用 binance_perp
            earliest_query = earliest_query.where(calc.TradeModel.exchange == "binance_perp")
        if calc.account_id:
            earliest_query = earliest_query.where(calc.TradeModel.account_id == calc.account_id)
        if args.symbol:
            earliest_query = earliest_query.where(calc.TradeModel.symbol == args.symbol)

        earliest_result = await session.execute(earliest_query)
        earliest_date: Optional[date] = earliest_result.scalar()

        if not earliest_date:
            console.print("[yellow]该账号(以及可选 symbol) 没有任何成交记录，无法验证零点快照[/yellow]")
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
            f"[cyan]trade_date 区间: {start_date} -> {end_date} (闭区间)，"
            "零点快照 timestamp = trade_date+1 00:00[/cyan]\n"
        )

        # 2) 获取日度成交统计 & 日度盈亏序列
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
            console.print("[red]calc_daily_realized_series 返回为空，检查实现[/red]")
            await db_manager.close()
            return

        # 3) 对每个 trade_date / symbol 做对比
        for trade_date in sorted(daily_series.keys()):
            if trade_date < start_date or trade_date > end_date:
                continue

            day_data: Dict[str, Dict[str, Decimal]] = daily_series.get(trade_date, {})
            if not day_data:
                continue

            for symbol, metrics in sorted(day_data.items()):
                if args.symbol and symbol != args.symbol:
                    continue

                # 对应零点快照时间：trade_date+1 00:00
                midnight_date = trade_date + timedelta(days=1)
                midnight_ts = datetime(
                    midnight_date.year,
                    midnight_date.month,
                    midnight_date.day,
                )  # naive，用于 TIMESTAMP WITHOUT TIME ZONE

                # 从 position_metrics 读取实际零点快照
                snap_query = (
                    select(PositionMetrics)
                    .where(PositionMetrics.account_id == args.account_id)
                    .where(PositionMetrics.exchange == args.exchange)
                    .where(PositionMetrics.symbol == symbol)
                    .where(PositionMetrics.timestamp == midnight_ts)
                    .limit(1)
                )
                snap_result = await session.execute(snap_query)
                snap_row: Optional[PositionMetrics] = snap_result.scalar_one_or_none()

                title = (
                    f"{symbol} - trade_date={trade_date} "
                    f"(零点快照 timestamp={midnight_date} 00:00)"
                )
                table = Table(title=title)
                table.add_column("field", justify="left")
                table.add_column("expected (daily_series)", justify="right")
                table.add_column("db (position_metrics)", justify="right")

                def add_row(field: str, expected: Optional[Decimal], db_val: Optional[Decimal], prec: int = 8):
                    table.add_row(field, _fmt_dec(expected, prec), _fmt_dec(db_val, prec))

                if not snap_row:
                    console.print(
                        f"[yellow]{title} - position_metrics 中没有找到对应零点快照记录[/yellow]"
                    )
                    # 仍然把 expected 打印出来，方便你看
                    add_row("pre_long_qty(open_left_long_qty)", metrics.get("open_left_long_qty"), None, 4)
                    add_row("pre_short_qty(open_left_short_qty)", metrics.get("open_left_short_qty"), None, 4)
                    add_row("left_long_qty(close_left_long_qty)", metrics.get("close_left_long_qty"), None, 4)
                    add_row("left_short_qty(close_left_short_qty)", metrics.get("close_left_short_qty"), None, 4)
                    add_row("daily_realized_pnl", metrics.get("daily_realized_pnl"), None, 8)
                    add_row("cumulative_realized_pnl", metrics.get("cumulative_realized_pnl"), None, 8)
                    console.print(table)
                    console.print("\n")
                    continue

                # 昨收持仓（快照开仓）
                add_row("pre_long_qty(open_left_long_qty)", metrics.get("open_left_long_qty"), snap_row.pre_long_qty, 4)
                add_row("pre_short_qty(open_left_short_qty)", metrics.get("open_left_short_qty"), snap_row.pre_short_qty, 4)
                add_row("pre_long_value(open_left_long_value)", metrics.get("open_left_long_value"), snap_row.pre_long_value, 8)
                add_row("pre_short_value(open_left_short_value)", metrics.get("open_left_short_value"), snap_row.pre_short_value, 8)

                # 当日累计成交
                add_row("total_long_qty", metrics.get("total_long_qty"), snap_row.long_qty, 4)
                add_row("total_short_qty", metrics.get("total_short_qty"), snap_row.short_qty, 4)
                add_row("total_long_value", metrics.get("total_long_value"), snap_row.long_value, 8)
                add_row("total_short_value", metrics.get("total_short_value"), snap_row.short_value, 8)
                add_row("avg_buy_prz", metrics.get("avg_buy_prz"), snap_row.avg_buy_prz, 8)
                add_row("avg_sell_prz", metrics.get("avg_sell_prz"), snap_row.avg_sell_prz, 8)
                add_row("matched_qty", metrics.get("matched_qty"), snap_row.matched_qty, 4)

                # 当日收盘持仓
                add_row("left_long_qty(close_left_long_qty)", metrics.get("close_left_long_qty"), snap_row.left_long_qty, 4)
                add_row("left_short_qty(close_left_short_qty)", metrics.get("close_left_short_qty"), snap_row.left_short_qty, 4)
                add_row("left_long_value(close_left_long_value)", metrics.get("close_left_long_value"), snap_row.left_long_value, 8)
                add_row("left_short_value(close_left_short_value)", metrics.get("close_left_short_value"), snap_row.left_short_value, 8)

                # PnL
                add_row("daily_realized_pnl", metrics.get("daily_realized_pnl"), getattr(snap_row, "daily_realized_pnl", None), 8)
                add_row("cumulative_realized_pnl", metrics.get("cumulative_realized_pnl"), getattr(snap_row, "cumulative_realized_pnl", None), 8)

                # 未实现 + 汇总 PnL
                # 理论未实现需要收盘价，daily_series 本身没有 close_prz，这里只对比快照中的值
                add_row("unrealized_pnl (DB)", None, snap_row.unrealized_pnl, 8)
                add_row("daily_pnl (DB)", None, snap_row.daily_pnl, 8)
                add_row("cumulative_pnl (DB)", None, snap_row.cumulative_pnl, 8)

                console.print(table)
                console.print("\n")

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
