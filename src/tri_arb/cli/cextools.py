"""CEX Tools CLI - Universal cryptocurrency exchange API tool.

Provides command-line interface for interacting with cryptocurrency exchanges
using the unified BaseExchange interface. Supports market data queries,
trading operations, and account management.
"""

import typer
from rich.console import Console

from tri_arb.config.logging import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger(__name__)
console = Console()


# Create main app
app = typer.Typer(
    name="cextools",
    help="CEX Tools: Universal Cryptocurrency Exchange API Tool",
    add_completion=False,
    no_args_is_help=True,
)


# Global options callback
@app.callback()
def main(
    ctx: typer.Context,
    exchange: str = typer.Option(
        "xt",
        "--exchange",
        "-e",
        help="Exchange name (xt, binance, etc.)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """CEX Tools: Universal Cryptocurrency Exchange API Tool.

    Interact with cryptocurrency exchanges through a unified interface.
    Supports market data, trading, and account management operations.
    """
    # Store options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["exchange"] = exchange
    ctx.obj["verbose"] = verbose

    if verbose:
        logger.info("CEX Tools initialized", exchange=exchange)


# Command groups
market_app = typer.Typer(help="Market data commands")
trading_app = typer.Typer(help="Trading commands (planned)")
account_app = typer.Typer(help="Account management commands")


@market_app.command("ticker")
def ticker(
    ctx: typer.Context,
    symbol: str = typer.Argument(..., help="Trading pair symbol (e.g., BTC/USDT)"),
) -> None:
    """Get current ticker price for a trading pair.

    Example:
        cextools market ticker BTC/USDT
    """
    import asyncio
    from rich.table import Table

    exchange_name = ctx.obj["exchange"]
    verbose = ctx.obj["verbose"]

    if verbose:
        logger.info("Fetching ticker", exchange=exchange_name, symbol=symbol)

    # Import exchange factory
    from tri_arb.exchanges.factory import create_exchange

    async def fetch_ticker():
        # Create exchange instance
        exchange = create_exchange(exchange_name)

        try:
            await exchange.connect()

            # Use helper method to get ticker by symbol string
            price = await exchange.get_ticker_by_symbol(symbol)

            # Create rich table for output
            table = Table(title=f"Ticker: {symbol}", show_header=True)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="green")

            table.add_row("Exchange", exchange_name.upper())
            table.add_row("Symbol", symbol)
            table.add_row("Bid Price", f"{price.bid_price:.8f}")
            table.add_row("Ask Price", f"{price.ask_price:.8f}")
            table.add_row("Mid Price", f"{price.mid_price:.8f}")
            table.add_row("Spread", f"{(price.ask_price - price.bid_price):.8f}")
            table.add_row(
                "Spread %",
                f"{((price.ask_price - price.bid_price) / price.mid_price * 100):.4f}%",
            )
            table.add_row("Bid Volume", f"{price.bid_volume:.8f}")
            table.add_row("Ask Volume", f"{price.ask_volume:.8f}")
            table.add_row("Timestamp", str(price.timestamp))

            console.print(table)

            if verbose:
                logger.info("Ticker fetched successfully", symbol=symbol)

        except Exception as e:
            logger.error("Failed to fetch ticker", error=str(e), symbol=symbol)
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            await exchange.disconnect()

    # Run async function
    asyncio.run(fetch_ticker())


@market_app.command("orderbook")
def orderbook(
    ctx: typer.Context,
    symbol: str = typer.Argument(..., help="Trading pair symbol (e.g., BTC/USDT)"),
    depth: int = typer.Option(20, "--depth", "-d", help="Number of price levels"),
) -> None:
    """Get order book depth for a trading pair.

    Example:
        cextools market orderbook BTC/USDT --depth 50
    """
    import asyncio
    from rich.table import Table

    exchange_name = ctx.obj["exchange"]
    verbose = ctx.obj["verbose"]

    if verbose:
        logger.info(
            "Fetching orderbook", exchange=exchange_name, symbol=symbol, depth=depth
        )

    from tri_arb.exchanges.factory import create_exchange

    async def fetch_orderbook():
        exchange = create_exchange(exchange_name)

        try:
            await exchange.connect()

            # Use helper method
            orderbook = await exchange.get_orderbook_by_symbol(symbol, depth)

            # Create table for bids and asks
            table = Table(title=f"Order Book: {symbol}", show_header=True)
            table.add_column("Bid Price", style="green", justify="right")
            table.add_column("Bid Qty", style="green", justify="right")
            table.add_column("Ask Price", style="red", justify="right")
            table.add_column("Ask Qty", style="red", justify="right")

            # Show top depth levels
            max_rows = min(depth, len(orderbook.bids), len(orderbook.asks))

            for i in range(max_rows):
                bid_price = (
                    f"{orderbook.bids[i][0]:.8f}" if i < len(orderbook.bids) else ""
                )
                bid_qty = (
                    f"{orderbook.bids[i][1]:.8f}" if i < len(orderbook.bids) else ""
                )
                ask_price = (
                    f"{orderbook.asks[i][0]:.8f}" if i < len(orderbook.asks) else ""
                )
                ask_qty = (
                    f"{orderbook.asks[i][1]:.8f}" if i < len(orderbook.asks) else ""
                )

                table.add_row(bid_price, bid_qty, ask_price, ask_qty)

            console.print(table)

            # Show summary
            if orderbook.bids and orderbook.asks:
                best_bid = orderbook.bids[0][0]
                best_ask = orderbook.asks[0][0]
                spread = best_ask - best_bid
                mid_price = (best_bid + best_ask) / 2
                spread_pct = (spread / mid_price) * 100

                console.print(f"\n[cyan]Best Bid:[/cyan] {best_bid:.8f}")
                console.print(f"[cyan]Best Ask:[/cyan] {best_ask:.8f}")
                console.print(f"[cyan]Spread:[/cyan] {spread:.8f} ({spread_pct:.4f}%)")

            if verbose:
                logger.info("Orderbook fetched successfully", symbol=symbol)

        except Exception as e:
            logger.error("Failed to fetch orderbook", error=str(e), symbol=symbol)
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            await exchange.disconnect()

    asyncio.run(fetch_orderbook())


@account_app.command("balance")
def balance(
    ctx: typer.Context,
    currency: str = typer.Option(
        None,
        "--currency",
        "-c",
        help="Specific currency (e.g., BTC, USDT). If not provided, shows all.",
    ),
) -> None:
    """Get account balance for all currencies or a specific currency.

    Requires API credentials set as environment variables:
    - XT_API_KEY
    - XT_API_SECRET

    Examples:
        # All balances
        cextools account balance

        # Specific currency
        cextools account balance --currency USDT
    """
    import asyncio
    from rich.table import Table

    exchange_name = ctx.obj["exchange"]
    verbose = ctx.obj["verbose"]

    if verbose:
        logger.info(
            "Fetching account balance",
            exchange=exchange_name,
            currency=currency or "all",
        )

    from tri_arb.exchanges.factory import create_exchange

    async def fetch_balance():
        exchange = create_exchange(exchange_name)

        # Check if credentials are available
        if not exchange.api_key or not exchange.api_secret:
            console.print("[red]Error: API credentials not found![/red]")
            console.print("\nPlease set environment variables:")
            console.print(f"  export {exchange_name.upper()}_API_KEY=your_api_key")
            console.print(
                f"  export {exchange_name.upper()}_API_SECRET=your_api_secret"
            )
            raise typer.Exit(code=1)

        try:
            await exchange.connect()

            # Note: BaseExchange doesn't have get_balance method yet
            # This is a placeholder showing the expected interface
            console.print(
                "[yellow]Note: Account balance command is under development.[/yellow]"
            )
            console.print("\n[cyan]Expected API:[/cyan]")
            console.print("  exchange.get_balance(currency=None) -> dict")
            console.print("\n[cyan]Example output:[/cyan]")

            # Create example table
            table = Table(title="Account Balance (Example)", show_header=True)
            table.add_column("Currency", style="cyan")
            table.add_column("Available", style="green", justify="right")
            table.add_column("Frozen", style="yellow", justify="right")
            table.add_column("Total", style="white", justify="right")

            table.add_row("USDT", "1000.50000000", "0.00000000", "1000.50000000")
            table.add_row("BTC", "0.50000000", "0.10000000", "0.60000000")
            table.add_row("ETH", "5.25000000", "0.00000000", "5.25000000")

            console.print(table)
            console.print(
                "\n[yellow]This feature requires implementing get_balance() method in BaseExchange.[/yellow]"
            )

            if verbose:
                logger.info("Balance command executed (placeholder)")

        except Exception as e:
            logger.error("Failed to fetch balance", error=str(e))
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            await exchange.disconnect()

    asyncio.run(fetch_balance())


# Register command groups
app.add_typer(market_app, name="market")
app.add_typer(trading_app, name="trading")


@account_app.command("history")
def history(
    ctx: typer.Context,
    symbol: str = typer.Argument(..., help="Trading pair symbol (e.g., BTC/USDT)"),
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum number of trades to retrieve (default: 50, max: 100)",
    ),
) -> None:
    """Get recent trade history for a trading pair.

    Requires API credentials set as environment variables:
    - XT_API_KEY
    - XT_API_SECRET

    Examples:
        # Get last 50 trades for BTC/USDT
        cextools account history BTC/USDT

        # Get last 100 trades
        cextools account history BTC/USDT --limit 100

        # Remote execution
        uvx --from git+https://github.com/realm520/quant.git@006-api-xt \\
            cextools account history BTC/USDT --limit 50
    """
    import asyncio
    from rich.table import Table

    exchange_name = ctx.obj["exchange"]
    verbose = ctx.obj["verbose"]

    # Validate limit
    if limit < 1 or limit > 100:
        console.print("[red]Error: Limit must be between 1 and 100[/red]")
        raise typer.Exit(code=1)

    if verbose:
        logger.info(
            "Fetching trade history", exchange=exchange_name, symbol=symbol, limit=limit
        )

    from tri_arb.exchanges.factory import create_exchange

    async def fetch_history():
        exchange = create_exchange(exchange_name)

        # Check if credentials are available
        if not exchange.api_key or not exchange.api_secret:
            console.print("[red]Error: API credentials not found![/red]")
            console.print("\nPlease set environment variables:")
            console.print(f"  export {exchange_name.upper()}_API_KEY=your_api_key")
            console.print(
                f"  export {exchange_name.upper()}_API_SECRET=your_api_secret"
            )
            raise typer.Exit(code=1)

        try:
            await exchange.connect()

            # Get trading pair by symbol (uses helper method from BaseExchange)
            trading_pair = await exchange.get_trading_pair_by_symbol(symbol)

            # Fetch trade history
            trades = await exchange.get_trade_history(trading_pair, limit=limit)

            if not trades:
                console.print(f"[yellow]No trade history found for {symbol}[/yellow]")
                return

            # Create table
            table = Table(
                title=f"Trade History: {symbol} (Last {len(trades)} trades)",
                show_header=True,
            )
            table.add_column("Time", style="cyan")
            table.add_column("Trade ID", style="dim")
            table.add_column("Order ID", style="dim")
            table.add_column("Side", style="white")
            table.add_column("Price", style="yellow", justify="right")
            table.add_column("Quantity", style="green", justify="right")
            table.add_column("Fee", style="red", justify="right")
            table.add_column("Fee Currency", style="dim")

            # Add rows
            for trade in trades:
                # Format timestamp
                time_str = trade.timestamp.strftime("%Y-%m-%d %H:%M:%S")

                # Color code side
                side_color = "green" if trade.side.value == "BUY" else "red"
                side_str = f"[{side_color}]{trade.side.value}[/{side_color}]"

                # Format numbers
                price_str = f"{trade.price:.8f}".rstrip("0").rstrip(".")
                qty_str = f"{trade.quantity:.8f}".rstrip("0").rstrip(".")
                fee_str = f"{trade.fee:.8f}".rstrip("0").rstrip(".")

                table.add_row(
                    time_str,
                    (
                        trade.trade_id[:8] + "..."
                        if len(trade.trade_id) > 8
                        else trade.trade_id
                    ),
                    (
                        trade.order_id[:8] + "..."
                        if len(trade.order_id) > 8
                        else trade.order_id
                    ),
                    side_str,
                    price_str,
                    qty_str,
                    fee_str,
                    trade.fee_currency,
                )

            console.print(table)

            # Calculate summary
            total_buy_qty = sum(t.quantity for t in trades if t.side.value == "buy")
            total_sell_qty = sum(t.quantity for t in trades if t.side.value == "sell")

            # Group fees by currency
            from collections import defaultdict

            fees_by_currency = defaultdict(float)
            for trade in trades:
                fees_by_currency[trade.fee_currency] += float(trade.fee)

            console.print(f"\n[cyan]Summary:[/cyan]")
            console.print(
                f"  Total BUY:  {total_buy_qty:.8f} {trading_pair.base_currency}".rstrip(
                    "0"
                ).rstrip(
                    "."
                )
            )
            console.print(
                f"  Total SELL: {total_sell_qty:.8f} {trading_pair.base_currency}".rstrip(
                    "0"
                ).rstrip(
                    "."
                )
            )

            console.print(f"\n  [cyan]Fees by Currency:[/cyan]")
            for currency, fee_amount in sorted(fees_by_currency.items()):
                fee_str = f"{fee_amount:.8f}".rstrip("0").rstrip(".")
                console.print(f"    {currency}: {fee_str}")

            if verbose:
                logger.info("Trade history retrieved", trade_count=len(trades))

        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)
        except Exception as e:
            logger.error("Failed to fetch trade history", error=str(e), exc_info=True)
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            await exchange.disconnect()

    asyncio.run(fetch_history())


app.add_typer(account_app, name="account")

# 添加subscribe命令组
try:
    from tri_arb.cli.commands import subscribe

    app.add_typer(subscribe.app, name="subscribe")
except ImportError as e:
    # 如果subscribe模块不可用，跳过
    import sys

    print(f"Warning: subscribe command not available: {e}", file=sys.stderr)
except Exception as e:
    import sys

    print(f"Error loading subscribe command: {e}", file=sys.stderr)

# 添加trading-monitor命令组
try:
    from tri_arb.cli.commands import position_metrics

    app.add_typer(position_metrics.app, name="trading-monitor")
except ImportError as e:
    # 如果position_metrics模块不可用，跳过
    import sys

    print(f"Warning: trading-monitor command not available: {e}", file=sys.stderr)
except Exception as e:
    import sys

    print(f"Error loading trading-monitor command: {e}", file=sys.stderr)


if __name__ == "__main__":
    app()
