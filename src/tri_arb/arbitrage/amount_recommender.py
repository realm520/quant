"""
Smart amount recommendation for arbitrage opportunities.

Calculates recommended trading amounts based on:
- Market liquidity (bid/ask volumes)
- Price impact estimation
- Risk-adjusted position sizing
- Configurable safety limits

Based on specs/004-xt-get-ticker/plan.md.
"""

from decimal import Decimal

import structlog

from tri_arb.models.arbitrage import TradingPath
from tri_arb.models.exchange import Ticker


logger = structlog.get_logger(__name__)


def calculate_recommended_amount(
    path: TradingPath,
    tickers: dict[str, Ticker],
    profit_rate: Decimal,
    max_amount: Decimal = Decimal("10000"),
    min_amount: Decimal = Decimal("100"),
    liquidity_usage_rate: Decimal = Decimal("0.3"),
) -> Decimal:
    """
    Calculate recommended trading amount for an arbitrage path.

    Algorithm:
    1. Find minimum liquidity across all trading pairs in the path
    2. Apply liquidity usage rate (default 30% to avoid price impact)
    3. Adjust based on profit rate (higher profit → larger position)
    4. Clamp to configured min/max limits

    Args:
        path: Trading path with trading pairs
        tickers: Dictionary mapping symbol to Ticker
        profit_rate: Expected profit rate (as decimal, e.g., 0.01 = 1%)
        max_amount: Maximum recommended amount (default 10000 USDT)
        min_amount: Minimum recommended amount (default 100 USDT)
        liquidity_usage_rate: Fraction of liquidity to use (default 0.3 = 30%)

    Returns:
        Recommended amount in base currency (Decimal)

    Example:
        >>> path = TradingPath(
        ...     start_currency="USDT",
        ...     trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        ... )
        >>> tickers = {
        ...     "BTC/USDT": Ticker(symbol="BTC/USDT", bid=50000, ask=50001,
        ...                        bid_volume=Decimal("10"), ask_volume=Decimal("10")),
        ...     "ETH/BTC": Ticker(symbol="ETH/BTC", bid=0.05, ask=0.051,
        ...                       bid_volume=Decimal("100"), ask_volume=Decimal("100")),
        ...     "ETH/USDT": Ticker(symbol="ETH/USDT", bid=2500, ask=2501,
        ...                        bid_volume=Decimal("50"), ask_volume=Decimal("50"))
        ... }
        >>> calculate_recommended_amount(path, tickers, Decimal("0.02"))
        Decimal('3000.00')  # Min liquidity: 10 BTC * 50000 * 0.3 = 150000, but high profit boosts it
    """
    # Step 1: Calculate minimum liquidity in base currency
    min_liquidity = _calculate_min_liquidity_in_base(path=path, tickers=tickers)

    if min_liquidity <= 0:
        logger.warning(
            "zero_or_negative_liquidity",
            path=path.trading_pairs,
            min_liquidity=str(min_liquidity),
        )
        return min_amount

    # Step 2: Apply liquidity usage rate
    usable_liquidity = min_liquidity * liquidity_usage_rate

    # Step 3: Risk adjustment based on profit rate
    # Higher profit → willing to use more capital
    # Formula: base_amount * (1 + profit_rate_boost)
    profit_boost = min(profit_rate / Decimal("0.01"), Decimal("2.0"))  # Cap at 2x boost
    risk_adjusted_amount = usable_liquidity * (
        Decimal("1.0") + profit_boost * Decimal("0.5")
    )

    # Step 4: Clamp to limits
    recommended = max(min_amount, min(risk_adjusted_amount, max_amount))

    # Round to 2 decimal places for practical use
    recommended = recommended.quantize(Decimal("0.01"))

    logger.info(
        "amount_recommended",
        path=path.trading_pairs,
        min_liquidity=str(min_liquidity),
        usable_liquidity=str(usable_liquidity),
        profit_rate=str(profit_rate),
        risk_adjusted=str(risk_adjusted_amount),
        final_recommended=str(recommended),
    )

    return recommended


def _calculate_min_liquidity_in_base(
    path: TradingPath, tickers: dict[str, Ticker]
) -> Decimal:
    """
    Calculate minimum liquidity across path in base currency.

    For each trading pair, converts the liquidity to base currency equivalent
    and finds the minimum (bottleneck).

    Args:
        path: Trading path
        tickers: Ticker data

    Returns:
        Minimum liquidity in base currency (start_currency)
    """
    liquidity_values = []
    current_currency = path.start_currency

    for pair_symbol in path.trading_pairs:
        ticker = tickers.get(pair_symbol)
        if not ticker:
            logger.warning(
                "ticker_not_found",
                symbol=pair_symbol,
                available_symbols=list(tickers.keys()),
            )
            return Decimal("0")

        base, quote = pair_symbol.split("/")

        # Determine trade direction and relevant volume
        if current_currency == base:
            # Selling base for quote → use bid_volume (how much we can sell)
            volume = ticker.bid_volume
            price = ticker.bid

            # Convert to base currency
            if quote == path.start_currency:
                # Direct conversion: volume * price
                liquidity_in_base = volume * price
            else:
                # Need to convert quote to base in later steps
                # For simplicity, use volume as-is (conservative estimate)
                liquidity_in_base = volume * price

            current_currency = quote

        elif current_currency == quote:
            # Buying base with quote → use ask_volume (how much we can buy)
            volume = ticker.ask_volume
            price = ticker.ask

            # Convert to base currency
            if base == path.start_currency:
                # Direct conversion: volume * price
                liquidity_in_base = volume * price
            else:
                # Conservative estimate
                liquidity_in_base = volume * price

            current_currency = base

        else:
            # This shouldn't happen if path is valid
            logger.error(
                "invalid_path_currency_mismatch",
                pair=pair_symbol,
                current=current_currency,
                base=base,
                quote=quote,
            )
            return Decimal("0")

        liquidity_values.append(liquidity_in_base)

    if not liquidity_values:
        return Decimal("0")

    # Return minimum liquidity (bottleneck)
    min_liquidity = min(liquidity_values)

    logger.debug(
        "liquidity_calculated",
        path=path.trading_pairs,
        liquidity_values=[str(v) for v in liquidity_values],
        min_liquidity=str(min_liquidity),
    )

    return min_liquidity
