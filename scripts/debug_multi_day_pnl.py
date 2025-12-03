#!/usr/bin/env python3
"""累计 PnL 计算调试脚本。

计算逻辑：
- 累计已实现盈亏 = 从起始日期到结束日期的所有已实现盈亏累加
- 当前未实现盈亏 = 结束日期时刻的未实现盈亏
- 累计 PnL = 累计已实现盈亏 + 当前未实现盈亏
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


def _format_dec(value: Decimal, prec: int = 4) -> str:
    if value is None:
        return "0"
    # 不四舍五入，只做字符串格式化
    q = value.quantize(Decimal("1e-%d" % prec))
    return format(q, "f")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="计算累计 PnL（从数据库所有数据中获取）"
    )
    parser.add_argument(
        "--account-id",
        type=str,
        required=True,
        help="账号ID，如 account_006ktmm1 或 binance_main_001",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        choices=["binance", "xt"],
        required=True,
        help="交易所标识（binance 或 xt）",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="计算过去多少天的 PnL（默认 30 天）",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="可选：指定单个交易对（如 BTCUSDT），否则统计所有交易对",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/accounts.json",
        help="账号配置文件路径（默认 config/accounts.json）",
    )
    parser.add_argument(
        "--output",
        type=str,
        choices=["table", "json"],
        default="table",
        help="输出格式（table, json），默认 table",
    )

    args = parser.parse_args()

    # 读取配置
    config = _load_config(args.config)
    if config and isinstance(config, dict):
        db_url = config.get("global_settings", {}).get("database_url")
        db_manager = DatabaseManager(database_url=db_url) if db_url else DatabaseManager()
    else:
        db_manager = DatabaseManager()

    # 计算时间区间
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=args.days)

    console.print(
        f"[cyan]计算区间 (UTC+0): {start_date.date().isoformat()} -> {end_date.date().isoformat()}（{args.days} 天）[/cyan]"
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
        cumulative_pnl_by_symbol = await calc.calculate_cumulative_pnl(
            start_date=start_date,
            end_date=end_date,
            symbol=args.symbol,
        )

    # 输出结果
    if args.output == "json":
        output = {
            "start_date": start_date.date().isoformat(),
            "end_date": end_date.date().isoformat(),
            "days": args.days,
            "account_id": args.account_id,
            "exchange": args.exchange,
            "symbol": args.symbol,
            "by_symbol": {
                s: {
                    "cumulative_realized_pnl": str(v["cumulative_realized_pnl"]),
                    "current_unrealized_pnl": str(v["current_unrealized_pnl"]),
                    "cumulative_pnl": str(v["cumulative_pnl"]),
                }
                for s, v in cumulative_pnl_by_symbol.items()
            },
        }
        console.print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        # 按币种输出表格（不包含 TOTAL）
        for symbol_key, pnl_data in cumulative_pnl_by_symbol.items():
            if symbol_key == "TOTAL":
                continue
            
            title = f"累计 PnL 统计（{symbol_key}，{args.days} 天）"
            table = Table(
                title=title,
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("指标", justify="left", style="cyan")
            table.add_column("数值", justify="right", style="green")

            table.add_row(
                "累计已实现盈亏",
                _format_dec(pnl_data["cumulative_realized_pnl"]),
            )
            table.add_row(
                "当前未实现盈亏",
                _format_dec(pnl_data["current_unrealized_pnl"]),
            )
            table.add_row(
                "[bold]累计 PnL[/bold]",
                f"[bold green]{_format_dec(pnl_data['cumulative_pnl'])}[/bold green]",
            )

            console.print()
            console.print(table)
        
        console.print()
        console.print(
            f"[dim]（公式：累计 PnL = 累计已实现盈亏 + 当前未实现盈亏）[/dim]"
        )

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())

