"""Core data models for triangle arbitrage trading system.

This module defines the primary data structures used throughout the application:
- TradingPair: Currency pair configuration
- Price: Market price data with bid/ask spreads
- OrderBook: Order book depth data
- Order: Trading order representation
- Trade: Executed trade details
- ArbitrageOpportunity: Detected triangle arbitrage opportunity

All models use pydantic for validation and type safety.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator


# ============================================================================
# Enums
# ============================================================================


class OrderSide(str, Enum):
    """Order side: buy or sell."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type: market or limit."""

    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    """Order status lifecycle."""

    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# ============================================================================
# Core Models
# ============================================================================


class TradingPair(BaseModel):
    """Trading pair configuration.

    Represents a currency pair (e.g., BTC/USDT) with exchange-specific constraints.
    Includes trading rules, precision, and fee structure from exchange API.
    """

    base_currency: str = Field(..., min_length=1, max_length=32, description="Base currency symbol")
    quote_currency: str = Field(
        ..., min_length=1, max_length=32, description="Quote currency symbol"
    )
    exchange: str = Field(..., min_length=1, description="Exchange identifier")

    # Basic trading constraints
    min_order_size: Decimal = Field(..., gt=0, description="Minimum order size")
    max_order_size: Decimal = Field(..., gt=0, description="Maximum order size")
    price_precision: int = Field(..., ge=0, description="Number of decimal places for price")
    quantity_precision: int = Field(
        ..., ge=0, description="Number of decimal places for quantity"
    )

    # Fee structure (optional, from exchange API)
    maker_fee: Decimal | None = Field(
        default=None, ge=0, le=1, description="Maker fee rate (e.g., 0.001 for 0.1%)"
    )
    taker_fee: Decimal | None = Field(
        default=None, ge=0, le=1, description="Taker fee rate (e.g., 0.001 for 0.1%)"
    )

    # Trading constraints (optional, from exchange API)
    min_notional: Decimal | None = Field(
        default=None, gt=0, description="Minimum notional value (price * quantity)"
    )
    trading_state: str | None = Field(
        default=None, description="Trading state (e.g., ONLINE, OFFLINE, HALT)"
    )

    # Price filter (optional, from exchange API)
    price_min: Decimal | None = Field(
        default=None, gt=0, description="Minimum allowed price"
    )
    price_max: Decimal | None = Field(
        default=None, gt=0, description="Maximum allowed price"
    )
    price_step: Decimal | None = Field(
        default=None, gt=0, description="Price tick size (minimum price increment)"
    )

    # Quantity filter (optional, from exchange API)
    quantity_min: Decimal | None = Field(
        default=None, gt=0, description="Minimum allowed quantity"
    )
    quantity_max: Decimal | None = Field(
        default=None, gt=0, description="Maximum allowed quantity"
    )
    quantity_step: Decimal | None = Field(
        default=None, gt=0, description="Quantity step size (minimum quantity increment)"
    )

    # Perpetual futures specific (optional, for perpetual contracts)
    leverage_brackets: list[dict[str, Any]] | None = Field(
        default=None,
        description="Leverage brackets defining max leverage based on notional value"
    )
    contract_size: Decimal | None = Field(
        default=None, gt=0, description="Contract face value (e.g., 1 BTC = 1 contract)"
    )
    contract_type: str | None = Field(
        default=None, description="Contract type (e.g., PERPETUAL, FUTURES)"
    )

    @field_validator("base_currency", "quote_currency")
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        """Convert currency symbols to uppercase."""
        return v.upper()

    @field_validator("max_order_size")
    @classmethod
    def max_gte_min(cls, v: Decimal, info: Any) -> Decimal:
        """Validate max_order_size >= min_order_size."""
        if "min_order_size" in info.data and v < info.data["min_order_size"]:
            raise ValueError("max_order_size must be >= min_order_size")
        return v


class Price(BaseModel):
    """Market price data with bid/ask spread.

    Represents current market price for a trading pair including volume data.
    """

    trading_pair: TradingPair = Field(..., description="Associated trading pair")
    bid_price: Decimal = Field(..., gt=0, description="Best bid price")
    ask_price: Decimal = Field(..., gt=0, description="Best ask price")
    bid_volume: Decimal = Field(..., ge=0, description="Volume at bid price")
    ask_volume: Decimal = Field(..., ge=0, description="Volume at ask price")
    timestamp: datetime = Field(..., description="When price was captured")
    exchange: str = Field(..., min_length=1, description="Source exchange")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mid_price(self) -> Decimal:
        """Mid price: (bid_price + ask_price) / 2."""
        return (self.bid_price + self.ask_price) / Decimal("2")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_stale(self) -> bool:
        """Check if price is stale (> 5 minutes old)."""
        return datetime.utcnow() - self.timestamp > timedelta(minutes=5)

    @field_validator("ask_price")
    @classmethod
    def ask_gt_bid(cls, v: Decimal, info: Any) -> Decimal:
        """Validate ask_price > bid_price."""
        if "bid_price" in info.data and v <= info.data["bid_price"]:
            raise ValueError("ask_price must be > bid_price")
        return v


class OrderBook(BaseModel):
    """Order book depth data.

    Represents current order book state with bid/ask levels.
    """

    trading_pair: TradingPair = Field(..., description="Associated trading pair")
    bids: list[tuple[Decimal, Decimal]] = Field(
        default_factory=list, description="Bid levels (price, quantity)"
    )
    asks: list[tuple[Decimal, Decimal]] = Field(
        default_factory=list, description="Ask levels (price, quantity)"
    )
    timestamp: datetime = Field(..., description="When snapshot was taken")
    exchange: str = Field(..., min_length=1, description="Source exchange")

    @field_validator("bids")
    @classmethod
    def bids_descending(
        cls, v: list[tuple[Decimal, Decimal]]
    ) -> list[tuple[Decimal, Decimal]]:
        """Validate bids are sorted descending by price."""
        if len(v) > 1:
            for i in range(len(v) - 1):
                if v[i][0] < v[i + 1][0]:
                    raise ValueError("Bids must be sorted descending by price")
        return v

    @field_validator("asks")
    @classmethod
    def asks_ascending(
        cls, v: list[tuple[Decimal, Decimal]]
    ) -> list[tuple[Decimal, Decimal]]:
        """Validate asks are sorted ascending by price."""
        if len(v) > 1:
            for i in range(len(v) - 1):
                if v[i][0] > v[i + 1][0]:
                    raise ValueError("Asks must be sorted ascending by price")
        return v


class Order(BaseModel):
    """Trading order.

    Represents a trading order with full lifecycle tracking.
    """

    order_id: str = Field(..., min_length=1, description="Unique order identifier")
    exchange_order_id: str | None = Field(
        None, description="Exchange-specific order ID (from API response)"
    )
    trading_pair: TradingPair = Field(..., description="Trading pair for order")
    side: OrderSide = Field(..., description="Buy or sell")
    order_type: OrderType = Field(..., description="Market, limit, etc.")
    price: Decimal | None = Field(None, gt=0, description="Limit price (None for market orders)")
    quantity: Decimal = Field(..., gt=0, description="Order quantity")
    status: OrderStatus = Field(default=OrderStatus.PENDING, description="Order status")
    created_at: datetime = Field(..., description="When order was created")
    updated_at: datetime = Field(..., description="Last status update")
    exchange: str = Field(..., min_length=1, description="Target exchange")

    # Perpetual futures specific (optional, for perpetual contracts)
    position_side: str | None = Field(
        default=None, description="Position direction (LONG or SHORT) for perpetual futures"
    )
    time_in_force: str | None = Field(
        default="GTC",
        description="Time in force (GTC, IOC, FOK, POST_ONLY) - defaults to GTC"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trade_action(self) -> str | None:
        """Determine trade action from side and position_side.

        Returns:
            - "OPEN_LONG": BUY + LONG (open long position)
            - "CLOSE_LONG": SELL + LONG (close long position)
            - "OPEN_SHORT": SELL + SHORT (open short position)
            - "CLOSE_SHORT": BUY + SHORT (close short position)
            - None: If position_side is not set (spot trading)
        """
        if self.position_side is None:
            return None

        if self.side == OrderSide.BUY:
            if self.position_side == "LONG":
                return "OPEN_LONG"
            elif self.position_side == "SHORT":
                return "CLOSE_SHORT"
        elif self.side == OrderSide.SELL:
            if self.position_side == "LONG":
                return "CLOSE_LONG"
            elif self.position_side == "SHORT":
                return "OPEN_SHORT"

        return None

    @field_validator("price")
    @classmethod
    def limit_requires_price(cls, v: Decimal | None, info: Any) -> Decimal | None:
        """Validate limit orders must have a price."""
        if "order_type" in info.data and info.data["order_type"] == OrderType.LIMIT and v is None:
            raise ValueError("Limit orders must have a price")
        return v


class Trade(BaseModel):
    """Executed trade.

    Represents a completed trade execution with fees.
    """

    trade_id: str = Field(..., min_length=1, description="Unique trade identifier")
    order_id: str = Field(..., min_length=1, description="Associated order ID")
    trading_pair: TradingPair = Field(..., description="Trading pair")
    side: OrderSide = Field(..., description="Buy or sell")
    price: Decimal = Field(..., gt=0, description="Execution price")
    quantity: Decimal = Field(..., gt=0, description="Executed quantity")
    fee: Decimal = Field(..., ge=0, description="Trading fee")
    fee_currency: str = Field(..., min_length=1, description="Fee currency")
    timestamp: datetime = Field(..., description="Execution time")
    exchange: str = Field(..., min_length=1, description="Execution exchange")


class Balance(BaseModel):
    """账户余额数据结构"""
    
    accountAlias: str = Field(..., description="账户唯一识别码")
    asset: str = Field(..., description="资产（如 USDT, BTC）")
    balance: Decimal = Field(..., description="总余额")
    crossWalletBalance: Decimal = Field(..., description="全仓余额")
    crossUnPnl: Decimal = Field(..., description="全仓持仓未实现盈亏")
    availableBalance: Decimal = Field(..., description="下单可用余额")
    maxWithdrawAmount: Decimal = Field(..., description="最大可转出余额")
    marginAvailable: bool = Field(..., description="是否可用作联合保证金")
    updateTime: int = Field(..., description="更新时间（时间戳）")
    
    class Config:
        # 将字符串转为 Decimal 类型，并保证小数精度
        str_strip_whitespace = True
    
    def to_dict(self):
        """将余额数据转换为字典形式"""
        return {
            "currency": self.asset,
            "available": str(self.availableBalance),
            "frozen": str(self.balance - self.availableBalance),
            "total": str(self.balance)
        }
        
        
class ArbitrageOpportunity(BaseModel):
    """Triangular arbitrage opportunity.

    Represents a detected arbitrage opportunity across three trading pairs.
    """

    opportunity_id: str = Field(..., min_length=1, description="Unique identifier")
    path: list[TradingPair] = Field(
        ..., min_length=3, max_length=3, description="Three trading pairs forming the triangle"
    )
    prices: list[Price] = Field(
        ..., min_length=3, max_length=3, description="Current prices for each pair"
    )
    estimated_profit: Decimal = Field(..., ge=0, description="Expected profit (percentage)")
    estimated_profit_amount: Decimal = Field(..., ge=0, description="Absolute profit amount")
    required_capital: Decimal = Field(..., gt=0, description="Initial capital needed")
    slippage_tolerance: Decimal = Field(
        ..., ge=0, le=1, description="Maximum acceptable slippage"
    )
    detected_at: datetime = Field(..., description="When opportunity was detected")
    expires_at: datetime = Field(..., description="When opportunity likely expires")
    exchange: str = Field(..., min_length=1, description="Exchange where opportunity exists")
    is_viable: bool = Field(default=False, description="Whether opportunity meets minimum criteria")

    @field_validator("path")
    @classmethod
    def validate_triangle(cls, v: list[TradingPair]) -> list[TradingPair]:
        """Validate that pairs form a valid triangle.

        Note: This is a placeholder validation for MVP.
        Full triangle validation (A→B, B→C, C→A) would be implemented later.
        """
        if len(v) != 3:
            raise ValueError("Path must contain exactly 3 trading pairs")
        return v
