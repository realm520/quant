"""Account management commands."""

import asyncio
from typing import Optional

import typer
from rich.console import Console

from tri_arb.cli.utils.exchange_factory import ExchangeType, create_exchange
from tri_arb.cli.formatters.table import format_balance_table, format_positions_table
from tri_arb.cli.formatters.json import print_json
from tri_arb.cli.formatters.csv import print_csv
from tri_arb.cli.utils.validators import validate_symbol

app = typer.Typer(help="账户管理命令")
console = Console()


@app.command("balance")
def balance(
    exchange_type: ExchangeType = typer.Option(
        ...,
        "--exchange-type",
        "-e",
        help="交易类型 (spot 或 perp)"
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API 密钥（覆盖环境变量）"
    ),
    api_secret: Optional[str] = typer.Option(
        None,
        "--api-secret",
        help="API 密钥（覆盖环境变量）"
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="输出格式 (table, json, csv)"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    )
):
    """查询账户余额.
    
    示例:
        cextools account balance --exchange-type spot
        cextools account balance -e perp --output json
    """
    try:
        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步获取余额
        async def get_balance():
            await exchange.connect()
            try:
                balance_data = await exchange.get_balance()
                return balance_data
            finally:
                await exchange.disconnect()

        balances = asyncio.run(get_balance())

        # 根据输出格式显示
        if output == "json":
            print_json(balances)
        elif output == "csv":
            # 转换为列表格式供 CSV 使用
            balance_list = [
                {
                    "currency": currency,
                    "available": str(data.get("available", 0)),
                    "frozen": str(data.get("frozen", 0)),
                    "total": str(data.get("total", 0))
                }
                for currency, data in balances.items()
            ]
            print_csv(balance_list)
        else:  # table (default)
            format_balance_table(balances)

    except ValueError as e:
        console.print(f"[red]配置错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("positions")
def positions(
    exchange_type: ExchangeType = typer.Option(
        ...,
        "--exchange-type",
        "-e",
        help="交易类型（必须为 perp）"
    ),
    symbol: Optional[str] = typer.Option(
        None,
        "--symbol",
        "-s",
        help="交易对（例如 BTC/USDT），不指定则显示所有"
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API 密钥（覆盖环境变量）"
    ),
    api_secret: Optional[str] = typer.Option(
        None,
        "--api-secret",
        help="API 密钥（覆盖环境变量）"
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="输出格式 (table, json, csv)"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    )
):
    """查询持仓列表（仅永续合约）.
    
    示例:
        cextools account positions -e perp
        cextools account positions -e perp --symbol BTC/USDT
        cextools account positions -e perp -o json
    """
    try:
        # 验证 exchange_type
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] positions 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        # 验证 symbol 格式（如果提供）
        if symbol:
            symbol = validate_symbol(symbol)

        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步获取持仓
        async def get_positions():
            await exchange.connect()
            try:
                if symbol:
                    # 获取特定交易对的持仓
                    position_data = await exchange.get_position(symbol)
                    return [position_data] if position_data else []
                else:
                    # 获取所有持仓
                    positions_data = await exchange.get_all_positions()
                    return positions_data
            finally:
                await exchange.disconnect()

        positions_list = asyncio.run(get_positions())

        if not positions_list:
            console.print("[yellow]未发现持仓[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(positions_list)
        elif output == "csv":
            # 转换为字典列表供 CSV 使用
            csv_data = [
                {
                    "symbol": pos.get("symbol", ""),
                    "side": pos.get("side", ""),
                    "quantity": str(pos.get("quantity", 0)),
                    "entry_price": str(pos.get("entry_price", 0)),
                    "current_price": str(pos.get("current_price", 0)),
                    "pnl": str(pos.get("pnl", 0)),
                    "roe": str(pos.get("roe", 0)),
                    "leverage": str(pos.get("leverage", 0))
                }
                for pos in positions_list
            ]
            print_csv(csv_data)
        else:  # table (default)
            format_positions_table(positions_list)

    except ValueError as e:
        console.print(f"[red]参数错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
