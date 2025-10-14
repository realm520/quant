"""Perpetual futures specific data models.

Data models for XT perpetual futures trading, including positions,
funding rates, leverage brackets, and conditional orders.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass
class Position:
    """Perpetual futures position information.

    Represents an open position in perpetual futures trading, including
    entry price, current P&L, leverage, and liquidation risk.

    Attributes:
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        side: Position direction - LONG (bullish) or SHORT (bearish)
        quantity: Position size in base currency (e.g., BTC amount)
        entry_price: Average entry price for the position
        mark_price: Current mark price (fair price for liquidation calculation)
        liquidation_price: Price at which position will be force-closed
        unrealized_pnl: Unrealized profit/loss based on mark price
        leverage: Leverage multiplier (1x to 125x)
        margin: Margin amount locked for this position
        roe: Return on equity percentage (unrealized_pnl / margin * 100)
    """

    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    liquidation_price: Decimal
    unrealized_pnl: Decimal
    leverage: int
    margin: Decimal
    roe: Decimal  # Return on Equity %

    def __post_init__(self) -> None:
        """Validate position data after initialization."""
        if self.leverage < 1 or self.leverage > 125:
            raise ValueError(f"Invalid leverage: {self.leverage}. Must be between 1 and 125.")
        if self.quantity <= 0:
            raise ValueError(f"Invalid quantity: {self.quantity}. Must be positive.")


@dataclass
class FundingRate:
    """Funding rate information for perpetual futures.

    Perpetual futures use funding rates to anchor contract prices to spot prices.
    Positive rates mean longs pay shorts; negative rates mean shorts pay longs.
    Funding is typically settled every 8 hours.

    Attributes:
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        rate: Current funding rate (e.g., 0.0001 = 0.01%)
        next_funding_time: Timestamp for next funding rate settlement
    """

    symbol: str
    rate: Decimal
    next_funding_time: datetime


@dataclass
class LeverageBracket:
    """Leverage bracket defining maximum leverage based on position size.

    Different notional values have different maximum leverage limits to manage risk.
    Larger positions require lower leverage to prevent excessive liquidations.

    Attributes:
        min_notional: Minimum notional value for this bracket (price * quantity)
        max_notional: Maximum notional value for this bracket
        max_leverage: Maximum allowed leverage for this notional range
    """

    min_notional: Decimal
    max_notional: Decimal
    max_leverage: int

    def __post_init__(self) -> None:
        """Validate bracket data after initialization."""
        if self.min_notional >= self.max_notional:
            raise ValueError(
                f"Invalid notional range: min={self.min_notional}, max={self.max_notional}"
            )
        if self.max_leverage < 1:
            raise ValueError(f"Invalid max leverage: {self.max_leverage}")


@dataclass
class PlanOrder:
    """Conditional order (plan order) that triggers at a specific price.

    Plan orders are not active orders - they become active market/limit orders
    when the trigger condition is met. Used for stop-loss and take-profit strategies.

    Attributes:
        order_id: Unique order identifier from exchange
        symbol: Trading pair symbol (e.g., "BTC/USDT")
        position_side: Position direction this order applies to
        trigger_price: Price at which order activates
        order_type: Type of order to place when triggered (MARKET, LIMIT)
        order_side: Buy or sell direction when triggered
        quantity: Order quantity in base currency
        order_price: Limit price if order_type is LIMIT (optional)
        status: Current order status (PENDING, TRIGGERED, CANCELLED, EXPIRED)
    """

    order_id: str
    symbol: str
    position_side: Literal["LONG", "SHORT"]
    trigger_price: Decimal
    order_type: Literal["MARKET", "LIMIT"]
    order_side: Literal["BUY", "SELL"]
    quantity: Decimal
    order_price: Decimal | None = None
    status: Literal["PENDING", "TRIGGERED", "CANCELLED", "EXPIRED"] = "PENDING"


@dataclass
class StopProfit:
    """Stop-profit (take-profit) configuration for a position.

    Automatically closes position when target price is reached to lock in profits.
    Can use market orders (immediate execution) or limit orders (better price).

    Attributes:
        trigger_price: Price at which to trigger take-profit
        order_price: Limit price for execution (None for market order)
        order_type: MARKET for immediate execution, LIMIT for limit order
    """

    trigger_price: Decimal
    order_price: Decimal | None
    order_type: Literal["MARKET", "LIMIT"]

    def __post_init__(self) -> None:
        """Validate stop-profit configuration."""
        if self.order_type == "LIMIT" and self.order_price is None:
            raise ValueError("order_price is required for LIMIT order type")
        if self.order_type == "MARKET" and self.order_price is not None:
            raise ValueError("order_price should be None for MARKET order type")
