#!/usr/bin/env python3
"""验证昨日持仓量的调试脚本。

用于验证"昨日持仓量"的计算是否正确：
- initial_long_qty = 昨日 00:00 之前的最后一笔多头持仓
- buy_volume = 昨日 00:00 ~ 昨日 24:00 的买单成交量
- pre_long_qty = initial_long_qty + buy_volume
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
    except Exception as e:
        console.print(f"[yellow]警告: 无法读取配置文件 {path}: {e}[/yellow]")
        return None


def _format_dec(value: Decimal, prec: int = 8) -> str:
    if value is None:
        return "0"
    q = value.quantize(Decimal("1e-%d" % prec))
    return format(q, "f")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="验证昨日持仓量的计算")
    parser.add_argument(
        "--account-id",
        type=str,
        required=True,
        help="账号ID，如 account_008",
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
        help="可选：指定单个交易对（如 iota_usdt），否则统计所有交易对",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/accounts.json",
        help="账号配置文件路径（默认 config/accounts.json）",
    )

    args = parser.parse_args()

    # 读取配置
    config = _load_config(args.config)
    if config and isinstance(config, dict):
        db_url = config.get("global_settings", {}).get("database_url")
        db_manager = DatabaseManager(database_url=db_url) if db_url else DatabaseManager()
    else:
        db_manager = DatabaseManager()

    # 计算昨日 UTC 区间（昨日 00:00 ~ 昨日 24:00）
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    start_time = datetime(yesterday.year, yesterday.month, yesterday.day)  # 昨日 00:00 UTC
    end_time = start_time + timedelta(days=1)  # 昨日 24:00 UTC（即今日 00:00）

    console.print(
        f"[cyan]统计区间 (UTC+0): {start_time.isoformat()} -> {end_time.isoformat()}[/cyan]"
    )
    console.print(f"[cyan]账号: {args.account_id}, 交易所: {args.exchange}[/cyan]")
    if args.symbol:
        console.print(f"[cyan]交易对: {args.symbol}[/cyan]")

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
        if symbol_key == "TOTAL":
            continue

        title = f"昨日持仓统计（{symbol_key}，基于成交记录）"
        table = Table(title=title, show_header=True, header_style="bold magenta")
        table.add_column("指标", justify="left")
        table.add_column("数值", justify="right")

        # 昨收持仓
        table.add_row("[bold cyan]--- 昨收持仓 ---[/bold cyan]", "")
        table.add_row("昨日多头持仓量 (pre_long_qty)", _format_dec(m.get("pre_long_qty", Decimal("0"))))
        table.add_row("昨日空头持仓量 (pre_short_qty)", _format_dec(m.get("pre_short_qty", Decimal("0"))))
        table.add_row("昨日多头市值 (pre_long_value)", _format_dec(m.get("pre_long_value", Decimal("0")), 4))
        table.add_row("昨日空头市值 (pre_short_value)", _format_dec(m.get("pre_short_value", Decimal("0")), 4))
        table.add_row("", "")
        
        # 区间开始持仓
        table.add_row("[bold cyan]--- 区间开始持仓 ---[/bold cyan]", "")
        table.add_row("区间开始多头持仓 (initial_long_qty)", _format_dec(m.get("initial_long_qty", Decimal("0"))))
        table.add_row("区间开始空头持仓 (initial_short_qty)", _format_dec(m.get("initial_short_qty", Decimal("0"))))
        table.add_row("", "")
        
        # 昨日成交
        table.add_row("[bold cyan]--- 昨日成交 ---[/bold cyan]", "")
        table.add_row("BUY 成交量 (buy_volume)", _format_dec(m.get("buy_volume", Decimal("0"))))
        table.add_row("SELL 成交量 (sell_volume)", _format_dec(m.get("sell_volume", Decimal("0"))))
        table.add_row("BUY 市值累加 (buy_trade_value)", _format_dec(m.get("buy_trade_value", Decimal("0")), 4))
        table.add_row("SELL 市值累加 (sell_trade_value)", _format_dec(m.get("sell_trade_value", Decimal("0")), 4))
        table.add_row("", "")
        
        # 验证公式
        table.add_row("[bold yellow]--- 验证公式 ---[/bold yellow]", "")
        initial_long_qty = m.get("initial_long_qty", Decimal("0"))
        buy_volume = m.get("buy_volume", Decimal("0"))
        pre_long_qty = m.get("pre_long_qty", Decimal("0"))
        calculated_pre_long_qty = initial_long_qty + buy_volume
        
        table.add_row("initial_long_qty + buy_volume", _format_dec(calculated_pre_long_qty))
        table.add_row("pre_long_qty (实际值)", _format_dec(pre_long_qty))
        
        if calculated_pre_long_qty == pre_long_qty:
            table.add_row("[green]✓ 公式验证通过[/green]", "")
        else:
            table.add_row(
                f"[red]✗ 公式验证失败，差异: {_format_dec(abs(calculated_pre_long_qty - pre_long_qty))}[/red]",
                ""
            )

        console.print()
        console.print(table)

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())

