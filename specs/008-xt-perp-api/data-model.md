# Data Model: XT永续合约API集成

**Feature**: 008-xt-perp-api | **Date**: 2025-10-11 | **Phase**: 1

## Overview

本文档定义XT永续合约交易所集成所需的所有数据模型，包括对现有模型的扩展和新增的永续合约特定模型。所有模型均使用Python dataclass定义，确保类型安全和不可变性。

## Model Hierarchy

```
BaseExchange (abstract)
  ↓
XTPerpExchange (concrete)
  ↓
使用以下数据模型:
  - TradingPair (扩展)
  - Order (扩展)
  - Position (新增)
  - FundingRate (新增)
  - LeverageBracket (新增)
  - PlanOrder (新增)
  - StopProfit (新增)
```

## Core Models (Extended)

### 1. TradingPair (扩展)

**Purpose**: 交易对配置信息，扩展以支持永续合约特定字段

**Location**: `src/tri_arb/core/models.py`

**Definition**:
```python
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

@dataclass(frozen=True)
class TradingPair:
    """Trading pair configuration with perpetual futures extensions.

    Attributes:
        base_currency: Base currency symbol (e.g., "BTC")
        quote_currency: Quote currency symbol (e.g., "USDT")
        exchange: Exchange identifier (e.g., "xt")
        min_order_size: Minimum order quantity
        max_order_size: Maximum order quantity
        price_precision: Number of decimal places for price
        quantity_precision: Number of decimal places for quantity

        # Fee structure
        maker_fee: Maker fee rate (optional, e.g., 0.001 = 0.1%)
        taker_fee: Taker fee rate (optional, e.g., 0.001 = 0.1%)

        # Trading constraints
        min_notional: Minimum order value (price * quantity)
        trading_state: Current trading status (ONLINE/OFFLINE/HALT)

        # Price filter
        price_min: Minimum allowed price
        price_max: Maximum allowed price
        price_step: Price tick size

        # Quantity filter
        quantity_min: Minimum allowed quantity
        quantity_max: Maximum allowed quantity
        quantity_step: Quantity step size

        # Perpetual futures specific (new fields)
        leverage_brackets: Leverage tiers with margin requirements
        contract_size: Contract face value (e.g., 1 BTC = 1 contract)
        contract_type: Contract type (PERPETUAL only for now)
    """

    # Core attributes
    base_currency: str
    quote_currency: str
    exchange: str
    min_order_size: Decimal
    max_order_size: Decimal
    price_precision: int
    quantity_precision: int

    # Fee structure
    maker_fee: Decimal | None = None
    taker_fee: Decimal | None = None

    # Trading constraints
    min_notional: Decimal | None = None
    trading_state: str | None = None

    # Price filter
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    price_step: Decimal | None = None

    # Quantity filter
    quantity_min: Decimal | None = None
    quantity_max: Decimal | None = None
    quantity_step: Decimal | None = None

    # Perpetual futures specific (NEW)
    leverage_brackets: list["LeverageBracket"] = field(default_factory=list)
    contract_size: Decimal | None = None
    contract_type: Literal["PERPETUAL"] | None = None

    @property
    def symbol(self) -> str:
        """Return trading pair symbol in BASE/QUOTE format."""
        return f"{self.base_currency}/{self.quote_currency}"

    @property
    def xt_symbol(self) -> str:
        """Return XT API symbol format (e.g., btc_usdt)."""
        return f"{self.base_currency.lower()}_{self.quote_currency.lower()}"

    def validate_price(self, price: Decimal) -> bool:
        """Validate price against exchange constraints."""
        if self.price_min and price < self.price_min:
            return False
        if self.price_max and price > self.price_max:
            return False
        if self.price_step:
            # Check if price is aligned with step size
            remainder = (price - (self.price_min or Decimal("0"))) % self.price_step
            if remainder != Decimal("0"):
                return False
        return True

    def validate_quantity(self, quantity: Decimal) -> bool:
        """Validate quantity against exchange constraints."""
        if quantity < self.min_order_size or quantity > self.max_order_size:
            return False
        if self.quantity_min and quantity < self.quantity_min:
            return False
        if self.quantity_max and quantity > self.quantity_max:
            return False
        if self.quantity_step:
            # Check if quantity is aligned with step size
            remainder = (quantity - (self.quantity_min or Decimal("0"))) % self.quantity_step
            if remainder != Decimal("0"):
                return False
        return True

    def get_max_leverage_for_notional(self, notional: Decimal) -> int:
        """Get maximum allowed leverage for given notional value."""
        if not self.leverage_brackets:
            return 1  # No leverage if brackets not available

        for bracket in self.leverage_brackets:
            if notional <= bracket.max_notional:
                return bracket.max_leverage

        # Notional exceeds all brackets, return minimum leverage
        return self.leverage_brackets[-1].max_leverage
```

**Field Mapping (XT API → TradingPair)**:
```python
# From XT API /future/market/v3/public/symbol/list response:
{
    "symbol": "btc_usdt",                    → xt_symbol → split to base_currency/quote_currency
    "pricePrecision": 2,                     → price_precision
    "quantityPrecision": 6,                  → quantity_precision
    "tradeFee": {
        "makerFeeRate": "0.0002",            → maker_fee
        "takerFeeRate": "0.0005"             → taker_fee
    },
    "state": "ONLINE",                       → trading_state
    "filters": [
        {
            "filter": "PRICE_FILTER",
            "minPrice": "0.01",              → price_min
            "maxPrice": "1000000",           → price_max
            "tickSize": "0.01"               → price_step
        },
        {
            "filter": "LOT_SIZE",
            "minQty": "0.001",               → quantity_min (also min_order_size)
            "maxQty": "10000",               → quantity_max (also max_order_size)
            "stepSize": "0.001"              → quantity_step
        },
        {
            "filter": "MIN_NOTIONAL",
            "minNotional": "10"              → min_notional
        }
    ]
}

# Leverage brackets from /future/market/v1/public/leverage/bracket/detail:
{
    "brackets": [
        {
            "bracket": 1,
            "maxLeverage": 125,              → LeverageBracket.max_leverage
            "maxNominalValue": "50000",      → LeverageBracket.max_notional
            "maintenanceMarginRate": "0.004" → LeverageBracket.maintenance_margin_rate
        },
        ...
    ]
}
```

**Validation Rules**:
- `base_currency` and `quote_currency` MUST be non-empty strings
- `exchange` MUST be "xt" for XTPerpExchange
- `min_order_size` MUST be <= `max_order_size`
- `price_precision` and `quantity_precision` MUST be >= 0
- If `leverage_brackets` provided, MUST NOT be empty and MUST be sorted by max_notional ascending

### 2. Order (扩展)

**Purpose**: 订单模型，扩展以支持永续合约的仓位方向

**Location**: `src/tri_arb/core/models.py`

**Definition**:
```python
@dataclass
class Order:
    """Order model with perpetual futures position side support.

    Attributes:
        order_id: Internal order ID (UUID)
        exchange_order_id: Exchange-provided order ID
        trading_pair: Trading pair for this order
        side: Order side (BUY/SELL)
        order_type: Order type (MARKET/LIMIT)
        price: Order price (None for market orders)
        quantity: Order quantity
        status: Current order status
        created_at: Order creation timestamp
        updated_at: Last update timestamp
        exchange: Exchange identifier

        # Perpetual futures specific (NEW)
        position_side: Position side (LONG/SHORT) for perpetual futures
        time_in_force: Order time-in-force (GTC/IOC/FOK/POST_ONLY)
        client_order_id: Client-provided order ID (optional)
        filled_quantity: Quantity that has been filled
        average_price: Average fill price for partially filled orders

    Notes:
        - For spot trading: position_side is None
        - For perpetual futures:
          * BUY + LONG = Open long position
          * SELL + SHORT = Open short position
          * BUY + SHORT = Close short position
          * SELL + LONG = Close long position
    """

    order_id: str
    exchange_order_id: str
    trading_pair: TradingPair
    side: OrderSide
    order_type: OrderType
    price: Decimal | None
    quantity: Decimal
    status: OrderStatus
    created_at: datetime
    updated_at: datetime
    exchange: str

    # Perpetual futures specific (NEW)
    position_side: Literal["LONG", "SHORT"] | None = None
    time_in_force: Literal["GTC", "IOC", "FOK", "POST_ONLY"] | None = "GTC"
    client_order_id: str | None = None
    filled_quantity: Decimal = Decimal("0")
    average_price: Decimal | None = None

    @property
    def is_perpetual_order(self) -> bool:
        """Check if this is a perpetual futures order."""
        return self.position_side is not None

    @property
    def trade_action(self) -> str:
        """Return trade action description.

        Returns:
            - "SPOT": For spot trading
            - "OPEN_LONG": Open long position
            - "OPEN_SHORT": Open short position
            - "CLOSE_LONG": Close long position
            - "CLOSE_SHORT": Close short position
        """
        if not self.is_perpetual_order:
            return "SPOT"

        if self.side == OrderSide.BUY and self.position_side == "LONG":
            return "OPEN_LONG"
        elif self.side == OrderSide.SELL and self.position_side == "SHORT":
            return "OPEN_SHORT"
        elif self.side == OrderSide.BUY and self.position_side == "SHORT":
            return "CLOSE_SHORT"
        else:  # SELL + LONG
            return "CLOSE_LONG"

    @property
    def remaining_quantity(self) -> Decimal:
        """Calculate remaining unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.filled_quantity >= self.quantity

    @property
    def is_partially_filled(self) -> bool:
        """Check if order is partially filled."""
        return Decimal("0") < self.filled_quantity < self.quantity

    def validate(self) -> tuple[bool, str]:
        """Validate order data.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate price for limit orders
        if self.order_type == OrderType.LIMIT and self.price is None:
            return False, "Limit order requires price"

        # Validate market order has no price
        if self.order_type == OrderType.MARKET and self.price is not None:
            return False, "Market order must not have price"

        # Validate quantity
        if self.quantity <= Decimal("0"):
            return False, "Order quantity must be positive"

        # Validate trading pair constraints
        if not self.trading_pair.validate_quantity(self.quantity):
            return False, f"Quantity {self.quantity} violates exchange constraints"

        if self.price and not self.trading_pair.validate_price(self.price):
            return False, f"Price {self.price} violates exchange constraints"

        # Validate perpetual futures specific fields
        if self.is_perpetual_order:
            if self.position_side not in ("LONG", "SHORT"):
                return False, f"Invalid position_side: {self.position_side}"

        return True, ""
```

**Field Mapping (XT API → Order)**:
```python
# From XT API /future/trade/v1/order/detail response:
{
    "orderId": "123456789",                  → exchange_order_id (also order_id if not set)
    "clientOrderId": "my-order-1",           → client_order_id
    "symbol": "btc_usdt",                    → trading_pair (via symbol lookup)
    "orderType": "LIMIT",                    → order_type (LIMIT/MARKET)
    "orderSide": "BUY",                      → side (BUY/SELL)
    "positionSide": "LONG",                  → position_side (LONG/SHORT)
    "timeInForce": "GTC",                    → time_in_force
    "price": "50000.00",                     → price
    "origQty": "0.01",                       → quantity
    "executedQty": "0.005",                  → filled_quantity
    "avgPrice": "50010.00",                  → average_price
    "state": "PARTIALLY_FILLED",             → status (via mapping)
    "createdTime": 1609459200000,            → created_at (timestamp in ms)
    "updatedTime": 1609459300000             → updated_at (timestamp in ms)
}

# Status mapping:
XT API → OrderStatus
"NEW" → OrderStatus.OPEN
"PARTIALLY_FILLED" → OrderStatus.PARTIALLY_FILLED
"FILLED" → OrderStatus.FILLED
"CANCELED" → OrderStatus.CANCELLED
"REJECTED" → OrderStatus.FAILED
"EXPIRED" → OrderStatus.EXPIRED
```

**Validation Rules**:
- LIMIT order MUST have price, MARKET order MUST NOT have price
- `quantity` MUST be > 0
- `filled_quantity` MUST be >= 0 and <= `quantity`
- If `position_side` is set, MUST be either "LONG" or "SHORT"
- `time_in_force` MUST be one of GTC/IOC/FOK/POST_ONLY

## Perpetual Futures Models (New)

### 3. Position

**Purpose**: 永续合约仓位信息

**Location**: `src/tri_arb/core/models.py`

**Definition**:
```python
@dataclass
class Position:
    """Perpetual futures position model.

    Attributes:
        trading_pair: Trading pair for this position
        position_side: Position direction (LONG/SHORT)
        quantity: Position quantity (absolute value)
        entry_price: Average entry price
        mark_price: Current mark price
        unrealized_pnl: Unrealized profit/loss
        margin: Used margin
        leverage: Current leverage multiplier
        liquidation_price: Liquidation price
        margin_mode: Margin mode (ISOLATED/CROSS)
        timestamp: Position data timestamp
        exchange: Exchange identifier
    """

    trading_pair: TradingPair
    position_side: Literal["LONG", "SHORT"]
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    margin: Decimal
    leverage: int
    liquidation_price: Decimal
    margin_mode: Literal["ISOLATED", "CROSS"]
    timestamp: datetime
    exchange: str

    @property
    def notional_value(self) -> Decimal:
        """Calculate notional value (quantity * mark_price)."""
        return self.quantity * self.mark_price

    @property
    def margin_ratio(self) -> Decimal:
        """Calculate margin ratio (margin / notional_value)."""
        if self.notional_value == Decimal("0"):
            return Decimal("0")
        return self.margin / self.notional_value

    @property
    def pnl_percentage(self) -> Decimal:
        """Calculate P&L percentage."""
        if self.margin == Decimal("0"):
            return Decimal("0")
        return (self.unrealized_pnl / self.margin) * Decimal("100")

    @property
    def distance_to_liquidation(self) -> Decimal:
        """Calculate distance to liquidation price (percentage)."""
        if self.mark_price == Decimal("0"):
            return Decimal("0")

        distance = abs(self.mark_price - self.liquidation_price)
        return (distance / self.mark_price) * Decimal("100")

    def is_profitable(self) -> bool:
        """Check if position is currently profitable."""
        return self.unrealized_pnl > Decimal("0")

    def is_near_liquidation(self, threshold_percent: Decimal = Decimal("10")) -> bool:
        """Check if position is close to liquidation.

        Args:
            threshold_percent: Alert threshold (default 10%)

        Returns:
            True if distance to liquidation < threshold
        """
        return self.distance_to_liquidation < threshold_percent
```

**Field Mapping (XT API → Position)**:
```python
# From XT API /future/user/v1/position response:
{
    "symbol": "btc_usdt",                    → trading_pair (via symbol lookup)
    "positionSide": "LONG",                  → position_side
    "positionAmt": "0.01",                   → quantity
    "avgPrice": "50000.00",                  → entry_price
    "markPrice": "51000.00",                 → mark_price
    "unrealizedProfit": "10.00",             → unrealized_pnl
    "isolatedMargin": "500.00",              → margin
    "leverage": 10,                          → leverage
    "liquidationPrice": "45000.00",          → liquidation_price
    "marginType": "ISOLATED",                → margin_mode (ISOLATED/CROSS)
    "updateTime": 1609459200000              → timestamp (timestamp in ms)
}
```

**Validation Rules**:
- `quantity` MUST be >= 0
- `leverage` MUST be > 0 and <= trading_pair.leverage_brackets max
- `margin` MUST be > 0 for open positions
- `liquidation_price` MUST be between 0 and mark_price (for LONG) or > mark_price (for SHORT)

### 4. LeverageBracket

**Purpose**: 杠杆档位配置

**Location**: `src/tri_arb/core/models.py`

**Definition**:
```python
@dataclass(frozen=True)
class LeverageBracket:
    """Leverage bracket configuration.

    Attributes:
        bracket: Bracket tier number (1, 2, 3, ...)
        max_leverage: Maximum allowed leverage for this bracket
        max_notional: Maximum notional value for this leverage
        maintenance_margin_rate: Maintenance margin rate for this bracket
    """

    bracket: int
    max_leverage: int
    max_notional: Decimal
    maintenance_margin_rate: Decimal

    def __post_init__(self):
        """Validate bracket data."""
        if self.bracket < 1:
            raise ValueError("Bracket number must be >= 1")
        if self.max_leverage < 1:
            raise ValueError("Max leverage must be >= 1")
        if self.max_notional <= Decimal("0"):
            raise ValueError("Max notional must be > 0")
        if not (Decimal("0") <= self.maintenance_margin_rate <= Decimal("1")):
            raise ValueError("Maintenance margin rate must be between 0 and 1")

    @property
    def initial_margin_rate(self) -> Decimal:
        """Calculate initial margin rate (1 / leverage)."""
        return Decimal("1") / Decimal(str(self.max_leverage))

    def calculate_required_margin(self, notional: Decimal) -> Decimal:
        """Calculate required initial margin for given notional."""
        return notional * self.initial_margin_rate

    def calculate_maintenance_margin(self, notional: Decimal) -> Decimal:
        """Calculate required maintenance margin for given notional."""
        return notional * self.maintenance_margin_rate
```

**Field Mapping (XT API → LeverageBracket)**:
```python
# From XT API /future/market/v1/public/leverage/bracket/detail response:
{
    "bracket": 1,                            → bracket
    "maxLeverage": 125,                      → max_leverage
    "maxNominalValue": "50000",              → max_notional
    "maintenanceMarginRate": "0.004"         → maintenance_margin_rate
}
```

### 5. FundingRate

**Purpose**: 资金费率信息

**Location**: `src/tri_arb/core/models.py`

**Definition**:
```python
@dataclass(frozen=True)
class FundingRate:
    """Funding rate model.

    Attributes:
        trading_pair: Trading pair
        current_rate: Current funding rate
        next_rate: Predicted next funding rate
        next_funding_time: Next funding settlement time
        timestamp: Data timestamp
        exchange: Exchange identifier
    """

    trading_pair: TradingPair
    current_rate: Decimal
    next_rate: Decimal | None
    next_funding_time: datetime
    timestamp: datetime
    exchange: str

    @property
    def is_positive(self) -> bool:
        """Check if funding rate is positive (longs pay shorts)."""
        return self.current_rate > Decimal("0")

    @property
    def is_negative(self) -> bool:
        """Check if funding rate is negative (shorts pay longs)."""
        return self.current_rate < Decimal("0")

    @property
    def annual_rate(self) -> Decimal:
        """Calculate annualized funding rate (assuming 8h intervals, 3x per day)."""
        # funding_rate * 3 (times per day) * 365 days
        return self.current_rate * Decimal("3") * Decimal("365")

    def calculate_cost(self, position_value: Decimal) -> Decimal:
        """Calculate funding cost for given position value.

        Args:
            position_value: Notional value of position

        Returns:
            Funding cost (positive = pay, negative = receive)
        """
        return position_value * self.current_rate

    def time_until_next_funding(self) -> timedelta:
        """Calculate time remaining until next funding settlement."""
        now = datetime.now(tz=self.timestamp.tzinfo)
        return self.next_funding_time - now
```

**Field Mapping (XT API → FundingRate)**:
```python
# From XT API /future/market/v1/public/q/funding-rate response:
{
    "symbol": "btc_usdt",                    → trading_pair (via symbol lookup)
    "fundingRate": "0.0001",                 → current_rate
    "nextFundingRate": "0.00012",            → next_rate
    "nextFundingTime": 1609459200000,        → next_funding_time (timestamp in ms)
    "time": 1609459100000                    → timestamp (timestamp in ms)
}
```

### 6. PlanOrder (计划委托)

**Purpose**: 计划委托订单（触发价委托）

**Location**: `src/tri_arb/core/models.py`

**Definition**:
```python
@dataclass
class PlanOrder:
    """Plan order (trigger order) model.

    Attributes:
        entrust_id: Entrust order ID
        trading_pair: Trading pair
        trigger_price_type: Trigger price type (LAST/MARK)
        trigger_price: Trigger price
        order_type: Order type after trigger (LIMIT/MARKET)
        order_price: Order price (None for market)
        quantity: Order quantity
        side: Order side (BUY/SELL)
        position_side: Position side (LONG/SHORT)
        status: Current status (NOT_TRIGGERED/TRIGGERED/CANCELED)
        created_at: Creation timestamp
        exchange: Exchange identifier
    """

    entrust_id: str
    trading_pair: TradingPair
    trigger_price_type: Literal["LAST", "MARK"]
    trigger_price: Decimal
    order_type: OrderType
    order_price: Decimal | None
    quantity: Decimal
    side: OrderSide
    position_side: Literal["LONG", "SHORT"]
    status: Literal["NOT_TRIGGERED", "TRIGGERED", "CANCELED"]
    created_at: datetime
    exchange: str

    @property
    def is_triggered(self) -> bool:
        """Check if order has been triggered."""
        return self.status == "TRIGGERED"

    @property
    def is_active(self) -> bool:
        """Check if order is active (waiting for trigger)."""
        return self.status == "NOT_TRIGGERED"

    def will_trigger_at_price(self, current_price: Decimal) -> bool:
        """Check if order would trigger at given price.

        Logic:
        - BUY order triggers when current_price >= trigger_price
        - SELL order triggers when current_price <= trigger_price
        """
        if self.side == OrderSide.BUY:
            return current_price >= self.trigger_price
        else:  # SELL
            return current_price <= self.trigger_price
```

### 7. StopProfit (止盈止损)

**Purpose**: 止盈止损委托

**Location**: `src/tri_arb/core/models.py`

**Definition**:
```python
@dataclass
class StopProfit:
    """Stop profit/loss order model.

    Attributes:
        profit_id: Profit order ID
        trading_pair: Trading pair
        profit_price: Take profit price (optional)
        stop_price: Stop loss price (optional)
        quantity: Order quantity
        position_side: Position side to close (LONG/SHORT)
        expire_time: Order expiration time
        status: Current status (NOT_TRIGGERED/TRIGGERED/CANCELED)
        created_at: Creation timestamp
        exchange: Exchange identifier

    Notes:
        - At least one of profit_price or stop_price must be set
        - When triggered, will close position at market price
    """

    profit_id: str
    trading_pair: TradingPair
    profit_price: Decimal | None
    stop_price: Decimal | None
    quantity: Decimal
    position_side: Literal["LONG", "SHORT"]
    expire_time: datetime
    status: Literal["NOT_TRIGGERED", "TRIGGERED", "CANCELED"]
    created_at: datetime
    exchange: str

    def __post_init__(self):
        """Validate stop profit data."""
        if self.profit_price is None and self.stop_price is None:
            raise ValueError("At least one of profit_price or stop_price must be set")

    @property
    def has_take_profit(self) -> bool:
        """Check if take profit is set."""
        return self.profit_price is not None

    @property
    def has_stop_loss(self) -> bool:
        """Check if stop loss is set."""
        return self.stop_price is not None

    @property
    def is_expired(self) -> bool:
        """Check if order has expired."""
        now = datetime.now(tz=self.created_at.tzinfo)
        return now >= self.expire_time

    @property
    def is_active(self) -> bool:
        """Check if order is active (not triggered, not canceled, not expired)."""
        return self.status == "NOT_TRIGGERED" and not self.is_expired

    def will_trigger_at_price(self, current_price: Decimal) -> tuple[bool, str]:
        """Check if order would trigger at given price.

        Returns:
            Tuple of (will_trigger, reason)

        Logic for LONG position:
        - Take profit triggers when price >= profit_price
        - Stop loss triggers when price <= stop_price

        Logic for SHORT position:
        - Take profit triggers when price <= profit_price
        - Stop loss triggers when price >= stop_price
        """
        if self.position_side == "LONG":
            if self.profit_price and current_price >= self.profit_price:
                return True, "TAKE_PROFIT"
            if self.stop_price and current_price <= self.stop_price:
                return True, "STOP_LOSS"
        else:  # SHORT
            if self.profit_price and current_price <= self.profit_price:
                return True, "TAKE_PROFIT"
            if self.stop_price and current_price >= self.stop_price:
                return True, "STOP_LOSS"

        return False, ""
```

## Model Relationships

```
TradingPair
  ├── Used by Order
  ├── Used by Position
  ├── Used by FundingRate
  ├── Used by PlanOrder
  ├── Used by StopProfit
  └── Contains LeverageBracket[]

Order
  ├── References TradingPair
  └── Extended with position_side for perpetual futures

Position
  ├── References TradingPair
  └── Tracks open perpetual futures positions

FundingRate
  └── References TradingPair

PlanOrder
  ├── References TradingPair
  └── Creates Order when triggered

StopProfit
  ├── References TradingPair
  └── Creates close Order when triggered
```

## Validation Summary

### TradingPair
- All currency symbols non-empty
- Order size constraints: min <= max
- Precision values >= 0
- Leverage brackets sorted by notional value

### Order
- LIMIT orders must have price
- MARKET orders must not have price
- Quantity > 0 and within trading pair limits
- position_side required for perpetual futures

### Position
- Quantity >= 0
- Leverage > 0 and within limits
- Margin > 0 for open positions
- Liquidation price valid relative to mark price

### LeverageBracket
- Bracket number >= 1
- Max leverage >= 1
- Max notional > 0
- Maintenance margin rate between 0 and 1

### FundingRate
- Current rate can be positive, negative, or zero
- Next funding time in the future

### PlanOrder
- Trigger price > 0
- LIMIT orders must have order_price
- Quantity within trading pair limits

### StopProfit
- At least one of profit_price or stop_price must be set
- Expire time in the future
- Quantity within trading pair limits

---
**Status**: Phase 1 Data Model Complete ✓ | **Next**: Contracts Generation
