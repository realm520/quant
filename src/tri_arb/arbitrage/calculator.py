"""
Arbitrage profit rate calculator.

Calculates expected profit rate for triangular arbitrage paths.
Based on specs/004-xt-get-ticker/contracts/monitor_api.md.
"""

from decimal import Decimal

from tri_arb.models.arbitrage import TradingPath
from tri_arb.models.exchange import Ticker


async def calculate_profit_rate(
    path: TradingPath,
    tickers: dict[str, Ticker],
    fee_rate: Decimal
) -> tuple[Decimal, list[dict[str, str | Decimal]]]:
    """
    Calculate expected profit rate for an arbitrage path.
    
    Implements formula from FR-004, FR-005:
    Final Amount = Initial × price1 × price2 × price3 × (1 - fee_rate)³
    Profit Rate = (Final - Initial) / Initial × 100
    
    Args:
        path: Trading path to calculate profit for
        tickers: Dictionary mapping trading pair symbols to Ticker objects
        fee_rate: Fee rate per trade (decimal form, e.g., 0.001 = 0.1%)
    
    Returns:
        Tuple of (profit_rate_percentage, price_details)
        - profit_rate: Expected profit rate as Decimal percentage
        - price_details: List of dicts with trade details (type, pair, price)
    
    Raises:
        KeyError: If any trading pair in path not found in tickers
        ValueError: If fee_rate is outside valid range [0.0, 0.1]
    
    Performance: < 10ms per calculation
    """
    # Validate fee rate
    if fee_rate < Decimal("0.0") or fee_rate > Decimal("0.1"):
        raise ValueError(f"fee_rate must be in [0.0, 0.1] range, got: {fee_rate}")
    
    # Check all tickers exist
    for pair in path.trading_pairs:
        if pair not in tickers:
            raise KeyError(f"Ticker not found for pair: {pair}")
    
    # Calculate profit by simulating the trading path
    current_currency = path.start_currency
    current_amount = Decimal("1000")  # Start with 1000 units (arbitrary)
    price_details: list[dict[str, str | Decimal]] = []
    
    for pair_symbol in path.trading_pairs:
        ticker = tickers[pair_symbol]
        base, quote = pair_symbol.split("/")
        
        # Determine trade direction
        if current_currency == quote:
            # We have quote, want to buy base
            # Use ask price (we're taking liquidity)
            price = ticker.ask
            trade_type = "buy"
            
            # Calculate how much base we get
            # current_amount (quote) / price = base_amount
            base_amount = current_amount / price
            
            # Apply fee
            base_amount = base_amount * (Decimal("1") - fee_rate)
            
            current_amount = base_amount
            current_currency = base
            
        elif current_currency == base:
            # We have base, want to sell for quote
            # Use bid price (we're taking liquidity)
            price = ticker.bid
            trade_type = "sell"
            
            # Calculate how much quote we get
            # current_amount (base) * price = quote_amount
            quote_amount = current_amount * price
            
            # Apply fee
            quote_amount = quote_amount * (Decimal("1") - fee_rate)
            
            current_amount = quote_amount
            current_currency = quote
            
        else:
            # Should not happen if path is valid
            raise ValueError(f"Invalid path: {current_currency} not in {pair_symbol}")
        
        price_details.append({
            "type": trade_type,
            "pair": pair_symbol,
            "price": price
        })
    
    # Calculate profit rate
    initial_amount = Decimal("1000")
    final_amount = current_amount
    
    profit_rate = ((final_amount - initial_amount) / initial_amount) * Decimal("100")
    
    return profit_rate, price_details
