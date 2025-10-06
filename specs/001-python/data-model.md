# Data Model

**Feature**: Python Triangle Arbitrage Scaffold
**Date**: 2025-10-05
**Status**: MVP Scaffold - Placeholder Models

## Overview

This document defines the core data entities for the triangle arbitrage trading system. For the MVP scaffold, these are **placeholder models** with proper structure and type annotations, but without actual business logic implementation.

## Core Entities

### 1. TradingPair

**Purpose**: Represents a currency pair (e.g., BTC/USDT)

**Attributes**:
- `base_currency`: str - Base currency symbol (e.g., "BTC")
- `quote_currency`: str - Quote currency symbol (e.g., "USDT")
- `exchange`: str - Exchange identifier (e.g., "binance")
- `min_order_size`: Decimal - Minimum order size
- `max_order_size`: Decimal - Maximum order size
- `price_precision`: int - Number of decimal places for price
- `quantity_precision`: int - Number of decimal places for quantity

**Validation Rules**:
- Currency symbols must be uppercase, 2-10 characters
- Exchange must be non-empty string
- Min order size > 0
- Max order size >= min order size
- Precision values >= 0

**Relationships**:
- Referenced by `Price`, `Order`, `ArbitrageOpportunity`

**Pydantic Model**:
```python
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator

class TradingPair(BaseModel):
    base_currency: str = Field(..., min_length=2, max_length=10)
    quote_currency: str = Field(..., min_length=2, max_length=10)
    exchange: str = Field(..., min_length=1)
    min_order_size: Decimal = Field(..., gt=0)
    max_order_size: Decimal = Field(..., gt=0)
    price_precision: int = Field(..., ge=0)
    quantity_precision: int = Field(..., ge=0)

    @field_validator('base_currency', 'quote_currency')
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.upper()

    @field_validator('max_order_size')
    @classmethod
    def max_gte_min(cls, v: Decimal, info) -> Decimal:
        if 'min_order_size' in info.data and v < info.data['min_order_size']:
            raise ValueError('max_order_size must be >= min_order_size')
        return v
```

### 2. Price

**Purpose**: Represents a price quote for a trading pair

**Attributes**:
- `trading_pair`: TradingPair - Associated trading pair
- `bid_price`: Decimal - Best bid price
- `ask_price`: Decimal - Best ask price
- `mid_price`: Decimal - Mid price (calculated)
- `bid_volume`: Decimal - Volume at bid price
- `ask_volume`: Decimal - Volume at ask price
- `timestamp`: datetime - When price was captured
- `exchange`: str - Source exchange
- `is_stale`: bool - Whether price is too old (calculated)

**Validation Rules**:
- Bid price > 0
- Ask price > bid price
- Volumes >= 0
- Timestamp must be within last 5 minutes for freshness

**Relationships**:
- Contains one `TradingPair`
- Referenced by `ArbitrageOpportunity`

**Pydantic Model**:
```python
from datetime import datetime, timedelta
from decimal import Decimal
from pydantic import BaseModel, Field, computed_field, field_validator

class Price(BaseModel):
    trading_pair: TradingPair
    bid_price: Decimal = Field(..., gt=0)
    ask_price: Decimal = Field(..., gt=0)
    bid_volume: Decimal = Field(..., ge=0)
    ask_volume: Decimal = Field(..., ge=0)
    timestamp: datetime
    exchange: str = Field(..., min_length=1)

    @computed_field
    @property
    def mid_price(self) -> Decimal:
        return (self.bid_price + self.ask_price) / 2

    @computed_field
    @property
    def is_stale(self) -> bool:
        return datetime.utcnow() - self.timestamp > timedelta(minutes=5)

    @field_validator('ask_price')
    @classmethod
    def ask_gt_bid(cls, v: Decimal, info) -> Decimal:
        if 'bid_price' in info.data and v <= info.data['bid_price']:
            raise ValueError('ask_price must be > bid_price')
        return v
```

### 3. OrderBook

**Purpose**: Represents order book depth for a trading pair

**Attributes**:
- `trading_pair`: TradingPair - Associated trading pair
- `bids`: List[Tuple[Decimal, Decimal]] - Bid levels (price, quantity)
- `asks`: List[Tuple[Decimal, Decimal]] - Ask levels (price, quantity)
- `timestamp`: datetime - When snapshot was taken
- `exchange`: str - Source exchange

**Validation Rules**:
- Bids sorted descending by price
- Asks sorted ascending by price
- All prices > 0
- All quantities > 0

**Relationships**:
- Contains one `TradingPair`

**Pydantic Model**:
```python
from typing import List, Tuple
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class OrderBook(BaseModel):
    trading_pair: TradingPair
    bids: List[Tuple[Decimal, Decimal]] = Field(default_factory=list)
    asks: List[Tuple[Decimal, Decimal]] = Field(default_factory=list)
    timestamp: datetime
    exchange: str = Field(..., min_length=1)

    @field_validator('bids')
    @classmethod
    def bids_descending(cls, v: List[Tuple[Decimal, Decimal]]) -> List[Tuple[Decimal, Decimal]]:
        if len(v) > 1:
            for i in range(len(v) - 1):
                if v[i][0] < v[i + 1][0]:
                    raise ValueError('Bids must be sorted descending by price')
        return v

    @field_validator('asks')
    @classmethod
    def asks_ascending(cls, v: List[Tuple[Decimal, Decimal]]) -> List[Tuple[Decimal, Decimal]]:
        if len(v) > 1:
            for i in range(len(v) - 1):
                if v[i][0] > v[i + 1][0]:
                    raise ValueError('Asks must be sorted ascending by price')
        return v
```

### 4. Order

**Purpose**: Represents a trading order

**Attributes**:
- `order_id`: str - Unique order identifier
- `trading_pair`: TradingPair - Trading pair for order
- `side`: OrderSide - Buy or sell (enum)
- `order_type`: OrderType - Market, limit, etc. (enum)
- `price`: Optional[Decimal] - Limit price (None for market orders)
- `quantity`: Decimal - Order quantity
- `status`: OrderStatus - Order status (enum)
- `created_at`: datetime - When order was created
- `updated_at`: datetime - Last status update
- `exchange`: str - Target exchange

**Validation Rules**:
- Order ID must be unique
- Quantity > 0
- Price > 0 for limit orders
- Status transitions follow valid state machine

**Relationships**:
- Contains one `TradingPair`
- Referenced by `Trade`

**Pydantic Model**:
```python
from enum import Enum
from typing import Optional
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"

class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class Order(BaseModel):
    order_id: str = Field(..., min_length=1)
    trading_pair: TradingPair
    side: OrderSide
    order_type: OrderType
    price: Optional[Decimal] = Field(None, gt=0)
    quantity: Decimal = Field(..., gt=0)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime
    updated_at: datetime
    exchange: str = Field(..., min_length=1)

    @field_validator('price')
    @classmethod
    def limit_requires_price(cls, v: Optional[Decimal], info) -> Optional[Decimal]:
        if 'order_type' in info.data:
            if info.data['order_type'] == OrderType.LIMIT and v is None:
                raise ValueError('Limit orders must have a price')
        return v
```

### 5. Trade

**Purpose**: Represents an executed trade

**Attributes**:
- `trade_id`: str - Unique trade identifier
- `order_id`: str - Associated order ID
- `trading_pair`: TradingPair - Trading pair
- `side`: OrderSide - Buy or sell
- `price`: Decimal - Execution price
- `quantity`: Decimal - Executed quantity
- `fee`: Decimal - Trading fee
- `fee_currency`: str - Fee currency
- `timestamp`: datetime - Execution time
- `exchange`: str - Execution exchange

**Validation Rules**:
- Trade ID must be unique
- Price > 0
- Quantity > 0
- Fee >= 0

**Relationships**:
- References one `Order` (by order_id)
- Contains one `TradingPair`

**Pydantic Model**:
```python
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field

class Trade(BaseModel):
    trade_id: str = Field(..., min_length=1)
    order_id: str = Field(..., min_length=1)
    trading_pair: TradingPair
    side: OrderSide
    price: Decimal = Field(..., gt=0)
    quantity: Decimal = Field(..., gt=0)
    fee: Decimal = Field(..., ge=0)
    fee_currency: str = Field(..., min_length=1)
    timestamp: datetime
    exchange: str = Field(..., min_length=1)
```

### 6. ArbitrageOpportunity

**Purpose**: Represents a detected triangular arbitrage opportunity

**Attributes**:
- `opportunity_id`: str - Unique identifier
- `path`: List[TradingPair] - Three trading pairs forming the triangle
- `prices`: List[Price] - Current prices for each pair
- `estimated_profit`: Decimal - Expected profit (percentage)
- `estimated_profit_amount`: Decimal - Absolute profit amount
- `required_capital`: Decimal - Initial capital needed
- `slippage_tolerance`: Decimal - Maximum acceptable slippage
- `detected_at`: datetime - When opportunity was detected
- `expires_at`: datetime - When opportunity likely expires
- `exchange`: str - Exchange where opportunity exists
- `is_viable`: bool - Whether opportunity meets minimum criteria

**Validation Rules**:
- Path must contain exactly 3 trading pairs
- Path must form valid triangle (A→B→C→A)
- Estimated profit >= 0
- Required capital > 0
- Slippage tolerance >= 0 and <= 1 (100%)

**Relationships**:
- Contains 3 `TradingPair` instances (path)
- Contains 3 `Price` instances (prices)

**Pydantic Model**:
```python
from typing import List
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class ArbitrageOpportunity(BaseModel):
    opportunity_id: str = Field(..., min_length=1)
    path: List[TradingPair] = Field(..., min_length=3, max_length=3)
    prices: List[Price] = Field(..., min_length=3, max_length=3)
    estimated_profit: Decimal = Field(..., ge=0)
    estimated_profit_amount: Decimal = Field(..., ge=0)
    required_capital: Decimal = Field(..., gt=0)
    slippage_tolerance: Decimal = Field(..., ge=0, le=1)
    detected_at: datetime
    expires_at: datetime
    exchange: str = Field(..., min_length=1)
    is_viable: bool = False

    @field_validator('path')
    @classmethod
    def validate_triangle(cls, v: List[TradingPair]) -> List[TradingPair]:
        # Validate that pairs form a valid triangle
        # A→B, B→C, C→A
        if len(v) != 3:
            raise ValueError('Path must contain exactly 3 trading pairs')

        # Additional validation for triangle structure would go here
        # For MVP, placeholder validation
        return v
```

## Supporting Types

### Configuration Models

**Settings** (from config/settings.py):
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "tri-arb"
    log_level: str = "INFO"

    # Database
    db_path: str = "tri_arb.db"
    db_pool_size: int = 5

    # Cache
    cache_ttl: int = 60  # seconds
    cache_max_size: int = 1000

    # Performance
    max_concurrent_requests: int = 10
    request_timeout: int = 30  # seconds

    # Monitoring
    metrics_port: int = 9090
    health_check_interval: int = 30  # seconds

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )
```

### Exception Models

**Custom Exceptions** (from core/exceptions.py):
```python
class TriArbException(Exception):
    """Base exception for tri-arb application"""
    pass

class InvalidTradingPairError(TriArbException):
    """Raised when trading pair is invalid"""
    pass

class StalePriceError(TriArbException):
    """Raised when price data is too old"""
    pass

class InsufficientLiquidityError(TriArbException):
    """Raised when order book depth is insufficient"""
    pass

class ExchangeConnectionError(TriArbException):
    """Raised when exchange connection fails"""
    pass

class OrderExecutionError(TriArbException):
    """Raised when order execution fails"""
    pass
```

## Entity Relationship Diagram

```
TradingPair <--* Price
TradingPair <--* OrderBook
TradingPair <--* Order
TradingPair <--* Trade
TradingPair <--3 ArbitrageOpportunity (path)

Order --1 Trade (order_id)

Price --3 ArbitrageOpportunity (prices)
```

## State Machines

### Order Status Transitions

```
PENDING → OPEN → FILLED
         ↓       ↑
         ↓       ↓
    CANCELLED  PARTIALLY_FILLED
         ↓
    REJECTED
```

**Valid Transitions**:
- PENDING → OPEN (order accepted by exchange)
- PENDING → REJECTED (order rejected by exchange)
- OPEN → FILLED (order fully executed)
- OPEN → PARTIALLY_FILLED (partial execution)
- OPEN → CANCELLED (user cancellation)
- PARTIALLY_FILLED → FILLED (remaining quantity filled)
- PARTIALLY_FILLED → CANCELLED (cancel remaining quantity)

**Invalid Transitions**:
- FILLED → any other state (terminal)
- CANCELLED → any other state (terminal)
- REJECTED → any other state (terminal)

## MVP Implementation Notes

For the MVP scaffold, all models will be:
1. Fully type-annotated with pydantic
2. Validated with pydantic validators
3. Documented with docstrings
4. Tested with example data
5. **Not connected to actual business logic** (placeholder implementations)

Actual business logic (arbitrage calculations, order execution, etc.) will be implemented in future iterations after the scaffold is complete.
