#!/usr/bin/env python3
"""计算昨日持仓量和市值的脚本.

用法:
    python scripts/calculate_daily_positions.py
    python scripts/calculate_daily_positions.py --hours-back 48
    python scripts/calculate_daily_positions.py --account-id binance_main_001
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.table import Table

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.daily_position_calculator import DailyPositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.exchanges.xt_perp import XTPerpExchange

console = Console()


def format_decimal(value: Decimal, precision: int = 2) -> str:
    """格式化 Decimal 值."""
    if value is None:
        return "0.00"
    return f"{float(value):,.{precision}f}"


async def main():
    """主函数."""
    import argparse

    parser = argparse.ArgumentParser(description="计算昨日持仓量和市值")
    parser.add_argument(
        "--hours-back",
        type=int,
        default=24,
        help="往前回溯的小时数（默认24小时，即昨日）",
    )
    parser.add_argument(
        "--account-id",
        type=str,
        nargs="+",
        help="账号ID列表，格式：--account-id binance_main_001 xt_main_001",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        choices=["binance", "xt", "all"],
        default="all",
        help="交易所（binance, xt, all），默认 all",
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

    config = None
    db_manager: DatabaseManager
    account_ids = None
    xt_api_key: str | None = None
    xt_api_secret: str | None = None

    # 如果有配置文件，优先从配置读取数据库 URL 和账号列表
    if Path(args.config).exists():
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            console.print(f"[yellow]警告: 无法读取配置文件 {args.config}: {e}[/yellow]")
            config = None

    # 初始化数据库管理器（如果配置中提供 database_url，则优先使用）
    if config and isinstance(config, dict):
        db_url = config.get("global_settings", {}).get("database_url")
        if db_url:
            db_manager = DatabaseManager(database_url=db_url)
        else:
            db_manager = DatabaseManager()
    else:
        db_manager = DatabaseManager()

    # 准备账号ID
    if args.account_id:
        # 从命令行参数解析账号ID
        account_ids = {"binance": [], "xt": []}
        for acc_id in args.account_id:
            if acc_id.startswith("binance_"):
                account_ids["binance"].append(acc_id)
            elif acc_id.startswith("xt_"):
                account_ids["xt"].append(acc_id)
            else:
                console.print(f"[yellow]警告: 无法识别账号ID {acc_id}，跳过[/yellow]")
    elif config and isinstance(config, dict):
        # 从配置文件读取账号ID（支持当前的 dict 结构：accounts 是一个以 account_id 为 key 的对象）
        accounts_obj = config.get("accounts") or {}
        if isinstance(accounts_obj, dict):
            account_ids = {"binance": [], "xt": []}
            for acc_id, acc_cfg in accounts_obj.items():
                if not isinstance(acc_cfg, dict):
                    continue
                exchange = str(acc_cfg.get("exchange", "")).lower()
                enabled = bool(acc_cfg.get("enabled", True))
                if not enabled:
                    continue
                if exchange not in ["binance", "xt"]:
                    continue
                # 使用配置 key 作为 account_id（与系统中 account_id 用法一致）
                account_ids[exchange].append(acc_id)
                # 记录一个 XT 账号的 API 凭证，用于后续获取合约乘数
                if (
                    exchange == "xt"
                    and not xt_api_key
                    and acc_cfg.get("api_key")
                    and acc_cfg.get("api_secret")
                ):
                    xt_api_key = acc_cfg.get("api_key")
                    xt_api_secret = acc_cfg.get("api_secret")

    # 过滤交易所
    if args.exchange != "all":
        if account_ids:
            account_ids = {args.exchange: account_ids.get(args.exchange, [])}
        else:
            account_ids = {args.exchange: [None]}

    # 创建合约乘数服务（如有可用的 XT 凭证）
    multiplier_service = None
    if xt_api_key and xt_api_secret:
        xt_exchange = XTPerpExchange(api_key=xt_api_key, api_secret=xt_api_secret)
        multiplier_service = ContractMultiplierService(xt_exchange=xt_exchange)

    # 创建计算器（如果 multiplier_service 为 None，则内部会默认使用乘数 1）
    calculator = DailyPositionCalculator(
        db_manager,
        contract_multiplier_service=multiplier_service,
    )

    # 计算持仓
    console.print(f"[cyan]正在计算过去 {args.hours_back} 小时的持仓量...[/cyan]")

    try:
        results = await calculator.calculate_daily_positions(
            hours_back=args.hours_back, account_ids=account_ids
        )

        # 输出结果
        if args.output == "json":
            # JSON 格式输出
            output = {
                "timestamp": datetime.utcnow().isoformat(),
                "hours_back": args.hours_back,
                "results": {
                    k: (
                        {k2: str(v2) for k2, v2 in v.items()}
                        if isinstance(v, dict)
                        else str(v)
                    )
                    for k, v in results.items()
                },
            }
            console.print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            # 表格格式输出
            table = Table(
                title=f"持仓量统计（过去 {args.hours_back} 小时）",
                show_header=True,
                header_style="bold magenta",
            )
            table.add_column("交易所", justify="left", style="cyan")
            table.add_column("多头持仓量", justify="right", style="green")
            table.add_column("空头持仓量", justify="right", style="red")
            table.add_column("多头市值 (USDT)", justify="right", style="green")
            table.add_column("空头市值 (USDT)", justify="right", style="red")
            table.add_column("BUY 成交量", justify="right")
            table.add_column("SELL 成交量", justify="right")

            # Binance
            table.add_row(
                "Binance",
                format_decimal(results["binance"]["pre_long_qty"], 8),
                format_decimal(results["binance"]["pre_short_qty"], 8),
                format_decimal(results["binance"]["pre_long_value"], 2),
                format_decimal(results["binance"]["pre_short_value"], 2),
                format_decimal(results["binance"]["buy_volume"], 8),
                format_decimal(results["binance"]["sell_volume"], 8),
            )

            # XT
            table.add_row(
                "XT",
                format_decimal(results["xt"]["pre_long_qty"], 8),
                format_decimal(results["xt"]["pre_short_qty"], 8),
                format_decimal(results["xt"]["pre_long_value"], 2),
                format_decimal(results["xt"]["pre_short_value"], 2),
                format_decimal(results["xt"]["buy_volume"], 8),
                format_decimal(results["xt"]["sell_volume"], 8),
            )

            # 总计
            table.add_row(
                "[bold]总计[/bold]",
                f"[bold green]{format_decimal(results['total']['pre_long_qty'], 8)}[/bold green]",
                f"[bold red]{format_decimal(results['total']['pre_short_qty'], 8)}[/bold red]",
                f"[bold green]{format_decimal(results['total']['pre_long_value'], 2)}[/bold green]",
                f"[bold red]{format_decimal(results['total']['pre_short_value'], 2)}[/bold red]",
                "-",
                "-",
            )

            console.print("\n")
            console.print(table)

            # 详细信息
            detail_table = Table(
                title="详细信息", show_header=True, header_style="bold blue"
            )
            detail_table.add_column("交易所", justify="left")
            detail_table.add_column("指标", justify="left")
            detail_table.add_column("值", justify="right")

            for exchange in ["binance", "xt"]:
                detail_table.add_row(
                    exchange.upper(),
                    "区间开始时多头持仓",
                    format_decimal(results[exchange]["initial_long_qty"], 8),
                )
                detail_table.add_row(
                    exchange.upper(),
                    "区间开始时空头持仓",
                    format_decimal(results[exchange]["initial_short_qty"], 8),
                )

            console.print("\n")
            console.print(detail_table)

        console.print(f"\n[green]✓[/green] 计算完成")

    except Exception as e:
        console.print(f"[red]错误:[/red] {e}")
        import traceback

        console.print_exception()
        sys.exit(1)
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
