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


def format_positions_table(positions: List[Any], exchange) -> None:
    """Format positions as Rich table.
    
    Supports both Position objects (XT) and position dicts (Binance).
    
    Args:
        positions: List of Position objects or position dictionaries
    """
    if not positions:
        console.print("[yellow]当前无持仓[/yellow]")
        return
    exchange_name = exchange.name
    table = Table(title="Positions", show_header=True, header_style="bold magenta")
    table.add_column("Exchange", style="cyan")
    table.add_column("Symbol", style="cyan")
    table.add_column("Side", style="white")
    table.add_column("Quantity", justify="right")
    table.add_column("Entry Price", justify="right")
    table.add_column("Current Price", justify="right")
    table.add_column("Liquidation Price", justify="right")
    table.add_column("PnL", justify="right")
    table.add_column("ROE", justify="right")
    table.add_column("Leverage", justify="right")
    

    for pos in positions:
        # Handle both Position object and dict formats
        if isinstance(pos, dict):
            # Binance dict format (from V2 API)
            symbol = pos.get('symbol', '')
            side = "Long" if pos.get('positionAmt') > 0 else "Short"
            quantity = abs(pos.get('positionAmt', Decimal('0')))
            entry_price = pos.get('entryPrice', Decimal('0'))
            mark_price = pos.get('markPrice', Decimal('0'))
            unrealized_pnl = pos.get('unRealizedProfit', Decimal('0'))
            
            # V2 API provides leverage directly
            leverage = pos.get('leverage', '1')
            
            # Calculate ROE: use notional/leverage to get margin
            notional = abs(pos.get('notional', Decimal('0')))
            leverage_num = Decimal(leverage) if leverage else Decimal('1')
            margin = notional / leverage_num if leverage_num > 0 and notional  > 0 else Decimal('0')
            roe = (unrealized_pnl / margin * 100) if margin > 0 else Decimal('0')
            liquidation_price = pos.get('liquidationPrice', Decimal('0'))
        else:
            # Position object format (XT)
            symbol = pos.symbol
            side = pos.side
            quantity = pos.quantity
            entry_price = pos.entry_price
            mark_price = pos.mark_price
            unrealized_pnl = pos.unrealized_pnl
            roe = (pos.unrealized_pnl / pos.margin * 100) if hasattr(pos, 'margin') and pos.margin > 0 else Decimal('0')
            leverage = f"{pos.leverage}" if hasattr(pos, 'leverage') else "N/A"
            liquidation_price = pos.liquidation_price if hasattr(pos, 'liquidation_price') else Decimal('0')
            

        table.add_row(
            exchange_name,
            symbol,
            side,
            f"{quantity:.8f}",
            f"{entry_price:.8f}",
            f"{mark_price:.8f}",
            f"{liquidation_price:.8f}",
            format_pnl(unrealized_pnl),
            format_percentage(roe),
            f"{leverage}x" if leverage != "N/A" else leverage,
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
        # Handle both Price object and dict formats
        if hasattr(ticker, 'trading_pair'):
            # Price object from exchange
            symbol = f"{ticker.trading_pair.base_currency}/{ticker.trading_pair.quote_currency}"
            bid = ticker.bid_price
            ask = ticker.ask_price
            # Price model doesn't have last_price, use mid_price
            last = ticker.mid_price
            # Price model doesn't have 24h stats
            change = Decimal('0')
            volume = ticker.bid_volume + ticker.ask_volume
        else:
            # Dict format (legacy or other sources)
            symbol = ticker.get('symbol', '')
            bid = Decimal(str(ticker.get('bid', 0)))
            ask = Decimal(str(ticker.get('ask', 0)))
            last = Decimal(str(ticker.get('last', 0)))
            change = Decimal(str(ticker.get('change_24h', 0)))
            volume = Decimal(str(ticker.get('volume_24h', 0)))

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
