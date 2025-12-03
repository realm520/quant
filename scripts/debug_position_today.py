#!/usr/bin/env python3
"""基于成交记录的“今日”持仓与交易统计调试脚本（UTC+0）。

统计区间：当日 UTC 00:00 ~ 当前时间（左闭右开 [00:00, now)）。

输出字段（单账号、单交易所聚合）：
- long_qty       今日多头交易量 = pre_long_qty + buy_volume
- short_qty      今日空头交易量 = pre_short_qty + sell_volume
- long_value     今日多头市值   = pre_long_value + buy_trade_value
- short_value    今日空头市值   = pre_short_value + sell_trade_value
- avg_buy_prz    买入平均价格   = long_value / long_qty
- avg_sell_prz   卖出平均价格   = short_value / short_qty
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

    console.print(
        f"[cyan]统计区间 (UTC+0): {start_time.isoformat()} -> {end_time.isoformat()}[/cyan]"
    )
    console.print(f"[cyan]账号: {args.account_id}, 交易所: {args.exchange}[/cyan]")

    async with db_manager.session() as session:
        calc = PositionCalculator(
            session,
            exchange=args.exchange,
            account_id=args.account_id,
        )
        metrics_by_symbol = await calc.calculate_positions_by_symbol(
            start_time=start_time,
            end_time=end_time,
            symbol=args.symbol,
        )

    # 逐币种输出
    for symbol_key, m in metrics_by_symbol.items():
        title = (
            f"今日持仓与交易统计（{symbol_key}，基于成交记录）"
            if symbol_key != "TOTAL"
            else "今日持仓与交易统计（TOTAL 汇总，基于成交记录）"
        )
        table = Table(title=title, show_header=True, header_style="bold magenta")
        table.add_column("指标", justify="left")
        table.add_column("数值", justify="right")

        long_qty = m.get("long_qty", Decimal("0"))
        short_qty = m.get("short_qty", Decimal("0"))
        long_value = m.get("long_value", Decimal("0"))
        short_value = m.get("short_value", Decimal("0"))
        avg_buy_prz = m.get("avg_buy_prz", Decimal("0"))
        avg_sell_prz = m.get("avg_sell_prz", Decimal("0"))

        # 昨收持仓（区间结束时的持仓）
        table.add_row("[bold cyan]--- 昨收持仓 ---[/bold cyan]", "")
        table.add_row("昨日多头持仓量 (pre_long_qty)", _format_dec(m.get("pre_long_qty", Decimal("0"))))
        table.add_row("昨日空头持仓量 (pre_short_qty)", _format_dec(m.get("pre_short_qty", Decimal("0"))))
        table.add_row("昨日多头市值 (pre_long_value)", _format_dec(m.get("pre_long_value", Decimal("0")), 4))
        table.add_row("昨日空头市值 (pre_short_value)", _format_dec(m.get("pre_short_value", Decimal("0")), 4))
        table.add_row("", "")  # 空行分隔
        table.add_row("[bold cyan]--- 区间开始持仓 ---[/bold cyan]", "")
        table.add_row("区间开始多头持仓 (initial_long_qty)", _format_dec(m.get("initial_long_qty", Decimal("0"))))
        table.add_row("区间开始空头持仓 (initial_short_qty)", _format_dec(m.get("initial_short_qty", Decimal("0"))))
        table.add_row("buy_volume (BUY 成交量)", _format_dec(m.get("buy_volume", Decimal("0"))))
        table.add_row("sell_volume (SELL 成交量)", _format_dec(m.get("sell_volume", Decimal("0"))))
        table.add_row("buy_trade_value (BUY 市值累加)", _format_dec(m.get("buy_trade_value", Decimal("0")), 4))
        table.add_row("sell_trade_value (SELL 市值累加)", _format_dec(m.get("sell_trade_value", Decimal("0")), 4))
        table.add_row("long_qty (多头交易量)", _format_dec(long_qty))
        table.add_row("short_qty (空头交易量)", _format_dec(short_qty))
        table.add_row("long_value (多头市值)", _format_dec(long_value, 4))
        table.add_row("short_value (空头市值)", _format_dec(short_value, 4))
        table.add_row("avg_buy_prz (买入均价)", _format_dec(avg_buy_prz, 8))
        table.add_row("avg_sell_prz (卖出均价)", _format_dec(avg_sell_prz, 8))
        table.add_row("matched_qty (轧差数量)", _format_dec(m.get("matched_qty", Decimal("0"))))
        table.add_row("realized_pnl (当日已实现盈亏)", _format_dec(m.get("realized_pnl", Decimal("0")), 4))
        table.add_row("left_long_qty (多头剩余持仓)", _format_dec(m.get("left_long_qty", Decimal("0"))))
        table.add_row("left_short_qty (空头剩余持仓)", _format_dec(m.get("left_short_qty", Decimal("0"))))
        table.add_row("left_long_value (多头剩余市值)", _format_dec(m.get("left_long_value", Decimal("0")), 4))
        table.add_row("left_short_value (空头剩余市值)", _format_dec(m.get("left_short_value", Decimal("0")), 4))
        table.add_row("close_prz (当日最后一笔成交价)", _format_dec(m.get("close_prz", Decimal("0")), 8))
        table.add_row("unrealized_pnl (当日未实现盈亏)", _format_dec(m.get("unrealized_pnl", Decimal("0")), 4))
        table.add_row("daily_pnl (单日 PnL)", _format_dec(m.get("daily_pnl", Decimal("0")), 4))

        console.print()
        console.print(table)

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())


