#!/usr/bin/env python3
"""基于成交记录的"今日"持仓与交易统计调试脚本（UTC+0）。

统计区间：当日 UTC 00:00 ~ 当前时间（左闭右开 [00:00, now)）。

输出内容（按币种分别显示）：
1. 昨收持仓：pre_long_qty, pre_short_qty, pre_long_value, pre_short_value
2. 今日交易：long_qty, short_qty, long_value, short_value, avg_buy_prz, avg_sell_prz
3. 已实现 Pnl：matched_qty, realized_pnl
4. 当日剩余仓位：left_long_qty, left_short_qty, left_long_value, left_short_value, close_prz, unrealized_pnl
5. Pnl 汇总：daily_pnl, cumulative_pnl
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator


console = Console()


def _load_config(path: str) -> Optional[dict]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        return None
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # pragma: no cover - 调试脚本容错
        console.print(f"[yellow]警告: 无法读取配置文件 {path}: {e}[/yellow]")
        return None


def _format_dec(value: Decimal, prec: int = 8) -> str:
    if value is None:
        return "0"
    # 不四舍五入，只做字符串格式化
    q = value.quantize(Decimal("1e-%d" % prec))
    return format(q, "f")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="调试单账号今日持仓与交易统计（UTC+0 当日 00:00~当前），支持按币种拆分。"
    )
    parser.add_argument(
        "--account-id",
        type=str,
        required=True,
        help="账号ID，如 account_006ktmm1 或 binance_main_001（将用于数据库中的 account_id 过滤）",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        choices=["binance", "xt"],
        required=True,
        help="交易所标识（binance 或 xt）",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="可选：指定单个交易对（如 BTCUSDT），否则统计该账号下所有交易对并逐币种展示",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/accounts.json",
        help="账号配置文件路径（默认 config/accounts.json，用于读取 database_url）",
    )

    args = parser.parse_args()

    # 读取配置，优先使用其中的 database_url
    config = _load_config(args.config)
    if config and isinstance(config, dict):
        db_url = config.get("global_settings", {}).get("database_url")
        db_manager = DatabaseManager(database_url=db_url) if db_url else DatabaseManager()
    else:
        db_manager = DatabaseManager()

    # 计算今日 UTC 区间
    today = datetime.utcnow().date()
    start_time = datetime(today.year, today.month, today.day)          # 今日 00:00 UTC
    end_time = datetime.utcnow()                                       # 当前 UTC

    # 计算昨日 UTC 区间（用于显示"昨收持仓"）
    yesterday = today - timedelta(days=1)
    yesterday_start = datetime(yesterday.year, yesterday.month, yesterday.day)  # 昨日 00:00 UTC
    yesterday_end = datetime(today.year, today.month, today.day)                # 昨日 24:00 UTC（即今日 00:00）

    console.print(
        f"[cyan]统计区间 (UTC+0): {start_time.isoformat()} -> {end_time.isoformat()}[/cyan]"
    )
    console.print(f"[cyan]账号: {args.account_id}, 交易所: {args.exchange}[/cyan]")

    # 计算多日 PnL 的起始日期（从月初开始，或从30天前开始）
    month_start = datetime(today.year, today.month, 1)  # 本月1日
    # 如果本月1日早于今日，则从本月1日开始；否则从30天前开始
    if month_start < start_time:
        cumulative_start = month_start
    else:
        cumulative_start = start_time - timedelta(days=30)
    
    async with db_manager.session() as session:
        calc = PositionCalculator(
            session,
            exchange=args.exchange,
            account_id=args.account_id,
        )
        # 计算昨日数据（用于显示"昨收持仓"）
        yesterday_metrics_by_symbol = await calc.calculate_positions_by_symbol(
            start_time=yesterday_start,
            end_time=yesterday_end,
            symbol=args.symbol,
        )
        
        # 计算今日指标
        metrics_by_symbol = await calc.calculate_positions_by_symbol(
            start_time=start_time,
            end_time=end_time,
            symbol=args.symbol,
        )
        
        # 计算多日 PnL
        cumulative_metrics = await calc.calculate_cumulative_pnl(
            start_date=cumulative_start,
            end_date=end_time,
            symbol=args.symbol,
        )

    # 逐币种输出（不包含 TOTAL）
    for symbol_key, m in metrics_by_symbol.items():
        if symbol_key == "TOTAL":
            continue
        
        # 获取昨日数据（用于显示"昨收持仓"）
        yesterday_m = yesterday_metrics_by_symbol.get(symbol_key, {})
        
        title = f"今日持仓与交易统计（{symbol_key}，基于成交记录）"
        table = Table(title=title, show_header=True, header_style="bold magenta")
        table.add_column("指标", justify="left")
        table.add_column("数值", justify="right")

        # 1. 昨收持仓（使用昨日的数据）
        table.add_row("[bold cyan]--- 1. 昨收持仓 ---[/bold cyan]", "")
        table.add_row("昨日多头持仓量 (pre_long_qty)", _format_dec(yesterday_m.get("pre_long_qty", Decimal("0"))))
        table.add_row("昨日空头持仓量 (pre_short_qty)", _format_dec(yesterday_m.get("pre_short_qty", Decimal("0"))))
        table.add_row("昨日多头市值 (pre_long_value)", _format_dec(yesterday_m.get("pre_long_value", Decimal("0")), 4))
        table.add_row("昨日空头市值 (pre_short_value)", _format_dec(yesterday_m.get("pre_short_value", Decimal("0")), 4))
        table.add_row("", "")  # 空行分隔

        # 2. 今日交易
        table.add_row("[bold cyan]--- 2. 今日交易 ---[/bold cyan]", "")
        table.add_row("多头交易量 (long_qty)", _format_dec(m.get("long_qty", Decimal("0"))))
        table.add_row("空头交易量 (short_qty)", _format_dec(m.get("short_qty", Decimal("0"))))
        table.add_row("多头市值 (long_value)", _format_dec(m.get("long_value", Decimal("0")), 4))
        table.add_row("空头市值 (short_value)", _format_dec(m.get("short_value", Decimal("0")), 4))
        table.add_row("买入平均价格 (avg_buy_prz)", _format_dec(m.get("avg_buy_prz", Decimal("0")), 8))
        table.add_row("卖出平均价格 (avg_sell_prz)", _format_dec(m.get("avg_sell_prz", Decimal("0")), 8))
        table.add_row("", "")  # 空行分隔

        # 3. 已实现 Pnl 计算
        table.add_row("[bold cyan]--- 3. 已实现 Pnl 计算 ---[/bold cyan]", "")
        table.add_row("轧差数量 (matched_qty)", _format_dec(m.get("matched_qty", Decimal("0"))))
        table.add_row("当日已实现盈亏 (realized_pnl)", _format_dec(m.get("realized_pnl", Decimal("0")), 4))
        table.add_row("", "")  # 空行分隔

        # 4. 当日剩余仓位
        table.add_row("[bold cyan]--- 4. 当日剩余仓位 ---[/bold cyan]", "")
        table.add_row("多头剩余持仓 (left_long_qty)", _format_dec(m.get("left_long_qty", Decimal("0"))))
        table.add_row("空头剩余持仓 (left_short_qty)", _format_dec(m.get("left_short_qty", Decimal("0"))))
        table.add_row("多头剩余市值 (left_long_value)", _format_dec(m.get("left_long_value", Decimal("0")), 4))
        table.add_row("空头剩余市值 (left_short_value)", _format_dec(m.get("left_short_value", Decimal("0")), 4))
        table.add_row("当日最后一笔成交价 (close_prz)", _format_dec(m.get("close_prz", Decimal("0")), 8))
        table.add_row("当日未实现盈亏 (unrealized_pnl)", _format_dec(m.get("unrealized_pnl", Decimal("0")), 4))
        table.add_row("", "")  # 空行分隔

        # 5. Pnl 汇总
        table.add_row("[bold cyan]--- 5. Pnl 汇总 ---[/bold cyan]", "")
        daily_pnl = m.get("daily_pnl", Decimal("0"))
        table.add_row("单日 pnl (realized_pnl + unrealized_pnl)", _format_dec(daily_pnl, 4))
        
        # 多日 pnl = sum(realized_pnl) + 最后一期 unrealized_pnl
        cumulative_pnl = Decimal("0")
        if symbol_key in cumulative_metrics:
            cum_data = cumulative_metrics[symbol_key]
            cumulative_pnl = cum_data.get("cumulative_pnl", Decimal("0"))
        table.add_row("多日 pnl (sum(realized_pnl) + 最后一期 unrealized_pnl)", _format_dec(cumulative_pnl, 4))

        console.print()
        console.print(table)

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())


