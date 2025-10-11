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
trading_app = typer.Typer(help="Trading commands")
account_app = typer.Typer(help="Account commands")


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
    from decimal import Decimal
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
            table.add_row("Spread %", f"{((price.ask_price - price.bid_price) / price.mid_price * 100):.4f}%")
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
        logger.info("Fetching orderbook", exchange=exchange_name, symbol=symbol, depth=depth)
    
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
                bid_price = f"{orderbook.bids[i][0]:.8f}" if i < len(orderbook.bids) else ""
                bid_qty = f"{orderbook.bids[i][1]:.8f}" if i < len(orderbook.bids) else ""
                ask_price = f"{orderbook.asks[i][0]:.8f}" if i < len(orderbook.asks) else ""
                ask_qty = f"{orderbook.asks[i][1]:.8f}" if i < len(orderbook.asks) else ""
                
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


# Register command groups
app.add_typer(market_app, name="market")
app.add_typer(trading_app, name="trading")
app.add_typer(account_app, name="account")


if __name__ == "__main__":
    app()
