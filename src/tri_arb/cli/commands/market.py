"""Market data commands."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live

from tri_arb.cli.utils.exchange_factory import ExchangeType, create_exchange
from tri_arb.cli.formatters.table import (
    format_ticker_table,
    format_orderbook_table,
)
from tri_arb.cli.formatters.json import print_json
from tri_arb.cli.formatters.csv import print_csv
from tri_arb.cli.utils.validators import validate_symbol, validate_interval, validate_limit

app = typer.Typer(help="市场行情命令")
console = Console()


@app.command("ticker")
def ticker(
    exchange_type: ExchangeType = typer.Option(
        ExchangeType.SPOT,
        "--exchange-type",
        "-e",
        help="交易类型 (spot 或 perp，默认 spot)"
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
    """查询实时价格.
    
    示例:
        cextools market ticker
        cextools market ticker --symbol BTC/USDT
        cextools market ticker -e perp -s ETH/USDT -o json
    """
    try:
        # 验证 symbol 格式（如果提供）
        if symbol:
            symbol = validate_symbol(symbol)

        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步获取行情
        async def get_ticker_data():
            await exchange.connect()
            try:
                if symbol:
                    ticker_data = await exchange.get_ticker_by_symbol(symbol)
                    return [ticker_data] if ticker_data else []
                else:
                    tickers_data = await exchange.get_all_tickers()
                    return tickers_data
            finally:
                await exchange.disconnect()

        tickers = asyncio.run(get_ticker_data())

        if not tickers:
            console.print("[yellow]未获取到行情数据[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(tickers)
        elif output == "csv":
            csv_data = []
            for t in tickers:
                if hasattr(t, 'trading_pair'):
                    # Price object
                    csv_data.append({
                        "symbol": f"{t.trading_pair.base_currency}/{t.trading_pair.quote_currency}",
                        "bid": str(t.bid_price),
                        "ask": str(t.ask_price),
                        "last": str(t.mid_price),
                        "change_24h": "0",
                        "volume_24h": str(t.bid_volume + t.ask_volume)
                    })
                else:
                    # Dict format
                    csv_data.append({
                        "symbol": t.get("symbol", ""),
                        "bid": str(t.get("bid", 0)),
                        "ask": str(t.get("ask", 0)),
                        "last": str(t.get("last", 0)),
                        "change_24h": str(t.get("change_24h", 0)),
                        "volume_24h": str(t.get("volume_24h", 0))
                    })
            print_csv(csv_data)
        else:  # table (default)
            format_ticker_table(tickers)

    except ValueError as e:
        console.print(f"[red]参数错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("depth")
def depth(
    symbol: str = typer.Option(
        ...,
        "--symbol",
        "-s",
        help="交易对（例如 BTC/USDT）"
    ),
    exchange_type: ExchangeType = typer.Option(
        ExchangeType.SPOT,
        "--exchange-type",
        "-e",
        help="交易类型 (spot 或 perp，默认 spot)"
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-l",
        help="档数 (5-50，默认 10)"
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
    """查询订单簿深度.
    
    示例:
        cextools market depth --symbol BTC/USDT
        cextools market depth -s ETH/USDT -e perp --limit 20
    """
    try:
        # 验证参数
        symbol = validate_symbol(symbol)
        limit = validate_limit(limit)

        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步获取深度
        async def get_depth_data():
            await exchange.connect()
            try:
                depth_data = await exchange.get_order_book(symbol, limit)
                return depth_data
            finally:
                await exchange.disconnect()

        orderbook = asyncio.run(get_depth_data())

        if not orderbook:
            console.print("[yellow]未获取到订单簿数据[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(orderbook)
        elif output == "csv":
            # 分别输出 bids 和 asks
            bids_data = [
                {"type": "bid", "price": str(bid[0]), "quantity": str(bid[1])}
                for bid in orderbook.get("bids", [])
            ]
            asks_data = [
                {"type": "ask", "price": str(ask[0]), "quantity": str(ask[1])}
                for ask in orderbook.get("asks", [])
            ]
            print_csv(bids_data + asks_data)
        else:  # table (default)
            format_orderbook_table(orderbook)

    except ValueError as e:
        console.print(f"[red]参数错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("funding")
def funding(
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
    """查询资金费率（仅永续合约）.
    
    示例:
        cextools market funding -s BTC/USDT -e perp
        cextools market funding --symbol ETH/USDT -e perp -o json
    """
    try:
        # 验证 exchange_type
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] funding 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        # 验证 symbol
        symbol = validate_symbol(symbol)

        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步获取资金费率
        async def get_funding_data():
            await exchange.connect()
            try:
                funding_data = await exchange.get_funding_rate(symbol)
                return funding_data
            finally:
                await exchange.disconnect()

        funding_info = asyncio.run(get_funding_data())

        if not funding_info:
            console.print("[yellow]未获取到资金费率数据[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(funding_info)
        elif output == "csv":
            csv_data = [{
                "symbol": funding_info.get("symbol", ""),
                "funding_rate": str(funding_info.get("funding_rate", 0)),
                "next_funding_time": str(funding_info.get("next_funding_time", ""))
            }]
            print_csv(csv_data)
        else:  # table (default)
            from rich.table import Table
            table = Table(title="Funding Rate", show_header=True, header_style="bold magenta")
            table.add_column("Symbol", style="cyan")
            table.add_column("Funding Rate", justify="right", style="green")
            table.add_column("Next Funding Time", style="yellow")
            table.add_row(
                funding_info.get("symbol", ""),
                f"{float(funding_info.get('funding_rate', 0)) * 100:.4f}%",
                str(funding_info.get("next_funding_time", ""))
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


@app.command("watch")
def watch(
    symbol: str = typer.Option(
        ...,
        "--symbol",
        "-s",
        help="交易对（例如 BTC/USDT）"
    ),
    exchange_type: ExchangeType = typer.Option(
        ExchangeType.SPOT,
        "--exchange-type",
        "-e",
        help="交易类型 (spot 或 perp，默认 spot)"
    ),
    interval: int = typer.Option(
        5,
        "--interval",
        "-i",
        help="刷新间隔（秒，1-60，默认 5）"
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
    """实时监控价格变化.
    
    示例:
        cextools market watch --symbol BTC/USDT
        cextools market watch -s ETH/USDT -e perp --interval 10
    """
    try:
        # 验证参数
        symbol = validate_symbol(symbol)
        interval = validate_interval(interval)

        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        console.print(f"[cyan]开始监控 {symbol} (刷新间隔: {interval}秒，按 Ctrl+C 退出)[/cyan]\n")

        # 实时刷新显示
        async def watch_ticker():
            await exchange.connect()
            try:
                with Live(console=console, refresh_per_second=1) as live:
                    while True:
                        ticker_data = await exchange.get_ticker(symbol)
                        if ticker_data:
                            from rich.table import Table
                            table = Table(show_header=True, header_style="bold magenta")
                            table.add_column("Symbol", style="cyan")
                            table.add_column("Bid", justify="right", style="green")
                            table.add_column("Ask", justify="right", style="red")
                            table.add_column("Last", justify="right", style="white")
                            table.add_column("24h Change", justify="right")

                            change = float(ticker_data.get("change_24h", 0))
                            change_style = "green" if change >= 0 else "red"
                            change_text = f"[{change_style}]{change:+.2f}%[/{change_style}]"

                            table.add_row(
                                ticker_data.get("symbol", ""),
                                str(ticker_data.get("bid", 0)),
                                str(ticker_data.get("ask", 0)),
                                str(ticker_data.get("last", 0)),
                                change_text
                            )
                            live.update(table)

                        await asyncio.sleep(interval)
            finally:
                await exchange.disconnect()

        asyncio.run(watch_ticker())

    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
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
