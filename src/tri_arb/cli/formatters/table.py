"""Rich table formatters for CLI output."""

from decimal import Decimal
from typing import Any, Dict, List
from rich.console import Console
from rich.table import Table
from datetime import datetime


console = Console()


def format_pnl(value: Decimal) -> str:
    """Format PnL with color (green for profit, red for loss)."""
    if value > 0:
        return f"[green]+{value:.2f}[/green]"
    elif value < 0:
        return f"[red]{value:.2f}[/red]"
    else:
        return f"[white]{value:.2f}[/white]"


def format_percentage(value: Decimal) -> str:
    """Format percentage with color."""
    if value > 0:
        return f"[green]+{value:.2f}%[/green]"
    elif value < 0:
        return f"[red]{value:.2f}%[/red]"
    else:
        return f"[white]{value:.2f}%[/white]"


def format_balance_table(balances: Dict[str, Dict[str, Decimal]]) -> None:
    """Format account balance as Rich table.
    
    Args:
        balances: Dict of {currency: {available, frozen}}
    """
    table = Table(title="Account Balance", show_header=True, header_style="bold magenta")
    table.add_column("Currency", style="cyan", width=12)
    table.add_column("Available", justify="right", style="green")
    table.add_column("Frozen", justify="right", style="yellow")
    table.add_column("Total", justify="right", style="white")

    for currency, data in balances.items():
        available = data.get('available', Decimal('0'))
        frozen = data.get('frozen', Decimal('0'))
        total = available + frozen

        table.add_row(
            currency,
            f"{available:.8f}",
            f"{frozen:.8f}",
            f"{total:.8f}",
        )

    console.print(table)
    console.print(f"Data fetched at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")


def format_positions_table(positions: List[Any]) -> None:
    """Format positions as Rich table.
    
    Args:
        positions: List of Position objects
    """
    if not positions:
        console.print("[yellow]当前无持仓[/yellow]")
        return

    table = Table(title="Positions", show_header=True, header_style="bold magenta")
    table.add_column("Symbol", style="cyan")
    table.add_column("Side", style="white")
    table.add_column("Quantity", justify="right")
    table.add_column("Entry Price", justify="right")
    table.add_column("Current Price", justify="right")
    table.add_column("PnL", justify="right")
    table.add_column("ROE", justify="right")
    table.add_column("Leverage", justify="right")

    for pos in positions:
        roe = (pos.unrealized_pnl / pos.margin * 100) if hasattr(pos, 'margin') and pos.margin > 0 else Decimal('0')

        table.add_row(
            pos.symbol,
            pos.position_side,
            f"{pos.quantity:.8f}",
            f"{pos.entry_price:.2f}",
            f"{pos.current_price:.2f}",
            format_pnl(pos.unrealized_pnl),
            format_percentage(roe),
            f"{pos.leverage}x",
        )

    console.print(table)
    console.print(f"Data fetched at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")


def format_ticker_table(tickers: List[Any]) -> None:
    """Format market tickers as Rich table.
    
    Args:
        tickers: List of Price objects or ticker dicts
    """
    table = Table(title="Market Ticker", show_header=True, header_style="bold magenta")
    table.add_column("Symbol", style="cyan")
    table.add_column("Bid", justify="right")
    table.add_column("Ask", justify="right")
    table.add_column("Last", justify="right")
    table.add_column("24h Change", justify="right")
    table.add_column("24h Volume", justify="right")

    for ticker in tickers:
        # Handle both object and dict formats
        symbol = ticker.symbol if hasattr(ticker, 'symbol') else ticker.get('symbol')
        bid = ticker.bid_price if hasattr(ticker, 'bid_price') else ticker.get('bid')
        ask = ticker.ask_price if hasattr(ticker, 'ask_price') else ticker.get('ask')
        last = ticker.last_price if hasattr(ticker, 'last_price') else ticker.get('last')
        change = ticker.change_24h if hasattr(ticker, 'change_24h') else ticker.get('change_24h', Decimal('0'))
        volume = ticker.volume_24h if hasattr(ticker, 'volume_24h') else ticker.get('volume_24h', Decimal('0'))

        table.add_row(
            symbol,
            f"{bid:.8f}",
            f"{ask:.8f}",
            f"{last:.8f}",
            format_percentage(change),
            f"{volume:.2f}",
        )

    console.print(table)
    console.print(f"Data fetched at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")


def format_orderbook_table(orderbook: Any, symbol: str, limit: int = 10) -> None:
    """Format order book as Rich table.
    
    Args:
        orderbook: OrderBook object
        symbol: Trading pair symbol
        limit: Number of levels to display
    """
    console.print(f"\nOrder Book: {symbol} (Limit: {limit})\n")

    # Bids table
    bids_table = Table(title="Bids", show_header=True, header_style="bold green")
    bids_table.add_column("Price", justify="right", style="green")
    bids_table.add_column("Quantity", justify="right")

    for price, qty in orderbook.bids[:limit]:
        bids_table.add_column(f"{price:.8f}", f"{qty:.8f}")

    # Asks table
    asks_table = Table(title="Asks", show_header=True, header_style="bold red")
    asks_table.add_column("Price", justify="right", style="red")
    asks_table.add_column("Quantity", justify="right")

    for price, qty in orderbook.asks[:limit]:
        asks_table.add_row(f"{price:.8f}", f"{qty:.8f}")

    console.print(bids_table)
    console.print(asks_table)

    if orderbook.bids and orderbook.asks:
        spread = orderbook.asks[0][0] - orderbook.bids[0][0]
        spread_pct = (spread / orderbook.bids[0][0] * 100) if orderbook.bids[0][0] > 0 else Decimal('0')
        console.print(f"\nSpread: {spread:.8f} ({spread_pct:.3f}%)")

    console.print(f"Data fetched at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")


def format_order_summary(order: Any) -> None:
    """Format order summary as Rich table.
    
    Args:
        order: Order object
    """
    table = Table(title="Order Details", show_header=True, header_style="bold magenta")
    table.add_column("Field", style="cyan", width=18)
    table.add_column("Value", style="white")

    fields = [
        ("Order ID", order.order_id),
        ("Exchange ID", order.exchange_order_id if hasattr(order, 'exchange_order_id') else "N/A"),
        ("Symbol", order.symbol if hasattr(order, 'symbol') else order.trading_pair.symbol),
        ("Side", order.side.value if hasattr(order.side, 'value') else str(order.side)),
        ("Type", order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type)),
        ("Price", f"{order.price:.8f}" if order.price else "MARKET"),
        ("Quantity", f"{order.quantity:.8f}"),
        ("Filled", f"{order.filled_quantity:.8f}" if hasattr(order, 'filled_quantity') else "N/A"),
        ("Status", order.status.value if hasattr(order.status, 'value') else str(order.status)),
        ("Created At", order.created_at.strftime('%Y-%m-%d %H:%M:%S UTC') if hasattr(order, 'created_at') else "N/A"),
    ]

    if hasattr(order, 'position_side') and order.position_side:
        fields.insert(4, ("Position Side", order.position_side))

    for field, value in fields:
        table.add_row(field, str(value))

    console.print(table)
