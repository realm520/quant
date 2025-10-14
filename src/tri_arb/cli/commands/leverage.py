"""Leverage management commands (perp only)."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from tri_arb.cli.utils.exchange_factory import ExchangeType, create_exchange
from tri_arb.cli.formatters.json import print_json
from tri_arb.cli.formatters.csv import print_csv
from tri_arb.cli.utils.validators import validate_symbol, validate_leverage

app = typer.Typer(help="杠杆管理命令（仅永续合约）")
console = Console()


@app.command("set")
def set_leverage(
    symbol: str = typer.Option(
        ...,
        "--symbol",
        "-s",
        help="交易对（例如 BTC/USDT）"
    ),
    leverage: int = typer.Option(
        ...,
        "--leverage",
        "-l",
        help="杠杆倍数 (1-125)"
    ),
    exchange_type: ExchangeType = typer.Option(
        ...,
        "--exchange-type",
        "-e",
        help="交易类型（必须为 perp）"
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
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    )
):
    """设置杠杆倍数（仅永续合约）.
    
    示例:
        cextools leverage set -s BTC/USDT -l 10 -e perp
        cextools leverage set --symbol ETH/USDT --leverage 20 -e perp
    """
    try:
        # 验证 exchange_type
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] leverage 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        # 验证参数
        symbol = validate_symbol(symbol)
        leverage = validate_leverage(leverage)

        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步设置杠杆
        async def set_leverage_async():
            await exchange.connect()
            try:
                result = await exchange.set_leverage(symbol, leverage)
                return result
            finally:
                await exchange.disconnect()

        result = asyncio.run(set_leverage_async())

        if result:
            console.print(
                f"[green]成功设置 {symbol} 的杠杆倍数为 {leverage}x[/green]"
            )
        else:
            console.print(f"[red]设置杠杆失败[/red]")
            raise typer.Exit(code=1)

    except ValueError as e:
        console.print(f"[red]参数错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("info")
def leverage_info(
    symbol: str = typer.Option(
        ...,
        "--symbol",
        "-s",
        help="交易对（例如 BTC/USDT）"
    ),
    exchange_type: ExchangeType = typer.Option(
        ...,
        "--exchange-type",
        "-e",
        help="交易类型（必须为 perp）"
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
    """查询当前杠杆设置（仅永续合约）.
    
    示例:
        cextools leverage info -s BTC/USDT -e perp
        cextools leverage info --symbol ETH/USDT -e perp -o json
    """
    try:
        # 验证 exchange_type
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] leverage 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        # 验证 symbol
        symbol = validate_symbol(symbol)

        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步查询杠杆信息
        async def get_leverage_info():
            await exchange.connect()
            try:
                leverage_data = await exchange.get_leverage(symbol)
                return leverage_data
            finally:
                await exchange.disconnect()

        leverage_data = asyncio.run(get_leverage_info())

        if not leverage_data:
            console.print(f"[yellow]未获取到 {symbol} 的杠杆信息[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(leverage_data)
        elif output == "csv":
            csv_data = [{
                "symbol": leverage_data.get("symbol", ""),
                "current_leverage": str(leverage_data.get("current_leverage", 0)),
                "max_leverage": str(leverage_data.get("max_leverage", 0)),
                "min_leverage": str(leverage_data.get("min_leverage", 1))
            }]
            print_csv(csv_data)
        else:  # table (default)
            table = Table(title="Leverage Information", show_header=True, header_style="bold magenta")
            table.add_column("Symbol", style="cyan", width=15)
            table.add_column("Current Leverage", justify="right", style="green")
            table.add_column("Min Leverage", justify="right", style="yellow")
            table.add_column("Max Leverage", justify="right", style="yellow")

            table.add_row(
                leverage_data.get("symbol", ""),
                f"{leverage_data.get('current_leverage', 0)}x",
                f"{leverage_data.get('min_leverage', 1)}x",
                f"{leverage_data.get('max_leverage', 125)}x"
            )
            console.print(table)

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
