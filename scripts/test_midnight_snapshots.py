#!/usr/bin/env python3
"""测试零点快照功能

用途：
    - 重建指定账号/交易所/日期的零点快照
    - 从 position_metrics 表查询并显示零点快照结果
    - 用于验证零点快照的计算是否正确
"""

import asyncio
import sys
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from sqlalchemy import select, func
from typing import Optional, Dict, List, Any

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.services.position_metrics_scheduler import PositionMetricsScheduler
from tri_arb.storage.position_metrics_models import PositionMetrics

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
        description="测试零点快照：重建并显示结果"
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
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="是否先重建零点快照（默认：只查询，不重建）",
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

        # 如果需要，先重建零点快照
        if args.rebuild:
            console.print("[cyan]正在重建零点快照...[/cyan]")
            await scheduler._rebuild_midnight_snapshots(
                session=session,
                calc=calc,
                account_id=args.account_id,
                exchange=args.exchange,
                symbol=args.symbol,
            )
            console.print("[green]重建完成！[/green]\n")

        # 查询零点快照（timestamp 为整点 00:00:00）
        console.print(
            f"[cyan]查询零点快照: account_id={args.account_id}, exchange={args.exchange}, "
            f"symbol={args.symbol or 'ALL'}[/cyan]\n"
        )

        query = (
            select(PositionMetrics)
            .where(PositionMetrics.account_id == args.account_id)
            .where(PositionMetrics.exchange == args.exchange)
            .where(
                # 只查询零点快照：小时、分钟、秒都是 0
                func.extract("hour", PositionMetrics.timestamp) == 0,
                func.extract("minute", PositionMetrics.timestamp) == 0,
                func.extract("second", PositionMetrics.timestamp) == 0,
            )
            .order_by(PositionMetrics.timestamp, PositionMetrics.symbol)
        )

        if args.symbol:
            query = query.where(PositionMetrics.symbol == args.symbol)

        if args.start_date:
            start_ts = datetime.combine(args.start_date, datetime.min.time())
            query = query.where(PositionMetrics.timestamp >= start_ts)

        if args.end_date:
            end_ts = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
            query = query.where(PositionMetrics.timestamp < end_ts)

        result = await session.execute(query)
        rows = result.scalars().all()

        if not rows:
            console.print("[yellow]没有找到零点快照记录[/yellow]")
            await db_manager.close()
            return

        # 按日期分组显示
        by_date: Dict[date, List[PositionMetrics]] = {}
        for row in rows:
            trade_date = row.timestamp.date() - timedelta(days=1)  # timestamp 是 trade_date+1 00:00
            if trade_date not in by_date:
                by_date[trade_date] = []
            by_date[trade_date].append(row)

        # 显示每个日期的快照
        for trade_date in sorted(by_date.keys()):
            day_rows = by_date[trade_date]
            midnight_ts = datetime.combine(trade_date + timedelta(days=1), datetime.min.time())

            console.print(f"\n[bold cyan]trade_date={trade_date} (零点快照 timestamp={midnight_ts})[/bold cyan]")

            for row in day_rows:
                if args.symbol and row.symbol != args.symbol:
                    continue

                table = Table(title=f"{row.symbol} - {trade_date} 收盘快照")
                table.add_column("字段", justify="left")
                table.add_column("值", justify="right")

                def add_row(field: str, value: Any, prec: int = 8):
                    if isinstance(value, Decimal):
                        table.add_row(field, _fmt_dec(value, prec))
                    else:
                        table.add_row(field, str(value))

                # 开盘持仓
                add_row("open_left_long_qty", row.open_left_long_qty, 4)
                add_row("open_left_short_qty", row.open_left_short_qty, 4)
                add_row("open_left_long_value", row.open_left_long_value, 8)
                add_row("open_left_short_value", row.open_left_short_value, 8)

                # 当日成交量
                add_row("daily_sum_buy_qty", row.daily_sum_buy_qty, 4)
                add_row("daily_sum_sell_qty", row.daily_sum_sell_qty, 4)
                add_row("daily_sum_buy_value", row.daily_sum_buy_value, 8)
                add_row("daily_sum_sell_value", row.daily_sum_sell_value, 8)

                # 总持仓
                add_row("long_qty", row.long_qty, 4)
                add_row("short_qty", row.short_qty, 4)
                add_row("long_value", row.long_value, 8)
                add_row("short_value", row.short_value, 8)

                # 平均价格
                add_row("avg_buy_prz", row.avg_buy_prz, 8)
                add_row("avg_sell_prz", row.avg_sell_prz, 8)

                # 轧差和已实现盈亏
                add_row("matched_qty", row.matched_qty, 4)
                add_row("daily_realized_pnl", row.daily_realized_pnl, 8)
                add_row("cumulative_realized_pnl", row.cumulative_realized_pnl, 8)

                # 收盘持仓
                add_row("left_long_qty", row.left_long_qty, 4)
                add_row("left_short_qty", row.left_short_qty, 4)
                add_row("left_long_value", row.left_long_value, 8)
                add_row("left_short_value", row.left_short_value, 8)

                # 收盘价和未实现盈亏
                add_row("close_prz", row.close_prz, 8)
                add_row("unrealized_pnl", row.unrealized_pnl, 8)

                # PnL 汇总
                add_row("daily_pnl", row.daily_pnl, 8)
                add_row("cumulative_pnl", row.cumulative_pnl, 8)

                console.print(table)
                console.print("")

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
