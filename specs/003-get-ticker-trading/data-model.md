# Data Model: Get All Market Tickers

**Feature**: 003-get-ticker-trading | **Phase**: 1 (Design) | **Date**: 2025-10-06

## Overview
此功能不引入新的数据模型，而是扩展现有 `BaseExchange` 接口和 `Price`/`TradingPair` 模型的使用方式。数据模型层面的主要变化是方法签名和返回类型。

## Modified Interfaces

### BaseExchange.get_ticker() Signature
**Location**: `src/tri_arb/exchanges/base.py`

**Before** (Feature 002):
```python
async def get_ticker(self, trading_pair: TradingPair) -> Price:
    """Get current ticker price for a trading pair."""
    pass
```

**After** (Feature 003):
```python
async def get_ticker(
    self,
    trading_pair: Optional[TradingPair] = None
) -> Union[Price, List[Price]]:
    """Get current ticker price for a trading pair or all markets.

    Args:
        trading_pair: Trading pair to query. If None, returns all active markets.

    Returns:
        - Single Price object if trading_pair is provided
        - List[Price] for all markets if trading_pair is None

    Raises:
        NotImplementedError: If trading_pair is None and exchange doesn't support batch queries
        ExchangeConnectionError: If exchange is not connected
        InvalidTradingPairError: If trading_pair is invalid (when provided)
    """
    pass
```

**Type Signature Changes**:
- **Parameter**: `TradingPair` → `Optional[TradingPair]`
- **Return**: `Price` → `Union[Price, List[Price]]`
- **New Exception**: `NotImplementedError` for unsupported batch queries

## Existing Models (No Changes)

### Price Model
**Location**: `src/tri_arb/core/models.py`

```python
class Price(BaseModel):
    """Market price data with bid/ask spread."""

    trading_pair: TradingPair
    bid_price: Decimal
    ask_price: Decimal
    bid_volume: Decimal
    ask_volume: Decimal
    timestamp: datetime
    exchange: str
```

**Usage in Feature 003**:
- Single ticker query: Returns one `Price` instance (unchanged)
- Batch ticker query: Returns list of `Price` instances (new usage pattern)
- Each `Price` object MUST have valid `trading_pair` reference
- `timestamp` indicates data freshness (no caching per FR-011)

### TradingPair Model
**Location**: `src/tri_arb/core/models.py`

```python
class TradingPair(BaseModel):
    """Trading pair configuration."""

    base_currency: str
    quote_currency: str
    exchange: str
    min_order_size: Decimal
    max_order_size: Decimal
    price_precision: int
    quantity_precision: int
```

**Usage in Feature 003**:
- Batch query: Need to create `TradingPair` objects from exchange symbol strings
- Example: XT symbol `"btc_usdt"` → `TradingPair(base="BTC", quote="USDT", ...)`
- Minimal object creation during parsing (precision/size from exchange info or defaults)

## Data Flow Diagrams

### Single Ticker Query (Existing, Unchanged)
```
User Code
  └─> exchange.get_ticker(trading_pair=BTC_USDT)
        └─> XTExchange._to_xt_symbol("BTC_USDT") → "btc_usdt"
              └─> HTTP GET /v4/public/ticker/book?symbol=btc_usdt
                    └─> Parse JSON → Price(trading_pair=BTC_USDT, ...)
                          └─> Return Price
```

### Batch Ticker Query (New)
```
User Code
  └─> exchange.get_ticker(trading_pair=None)
        └─> XTExchange checks: trading_pair is None?
              ├─ YES → Batch query path
              │   └─> HTTP GET /v4/public/ticker/book (no symbol param)
              │         └─> Parse JSON array → List[Dict]
              │               └─> For each ticker_data:
              │                     ├─ Create TradingPair from symbol
              │                     ├─ Create Price object
              │                     └─ Append to results (or log failure)
              │                           └─> Return List[Price]
              │
              └─ NO → Single query path (existing logic)
```

### Error Flow (Unsupported Exchange)
```
User Code
  └─> unsupported_exchange.get_ticker(trading_pair=None)
        └─> BaseExchange.get_ticker() checks: trading_pair is None?
              └─ YES → raise NotImplementedError(
                    "{exchange_name} does not support batch ticker queries"
                )
```

## Validation Rules

### Input Validation
- **trading_pair = None**: Valid input, triggers batch query mode
- **trading_pair = TradingPair(...)**: Valid input, single query mode (existing)
- No other values allowed (Optional type enforces this)

### Output Validation
- **Single query**: MUST return exactly one `Price` object
- **Batch query**: MUST return `List[Price]` (may be empty if no markets)
- **Partial failure**: Return successful `Price` objects, log failures
- Each `Price` object MUST pass pydantic validation (existing rules)

### Performance Constraints
- **Batch query**: Total time <1000ms (measured end-to-end)
- **Single query**: Total time <50ms p95 (existing constraint, unchanged)
- **Memory**: No unbounded list growth during parsing

## State Transitions
N/A - This feature is stateless. Each `get_ticker()` call is independent, no state maintained between calls (per FR-011 no caching requirement).

## Data Relationships

```
BaseExchange (abstract)
    └─> get_ticker(trading_pair: Optional[TradingPair])
          └─> Returns: Union[Price, List[Price]]
                ├─ trading_pair is None → List[Price]
                │     └─ Each Price.trading_pair is a distinct market
                │
                └─ trading_pair is TradingPair → Price
                      └─ Price.trading_pair == input trading_pair
```

## Implementation Notes

### XTExchange-Specific Details
**Symbol Parsing** (`_from_xt_symbol` helper):
```python
def _from_xt_symbol(self, symbol: str) -> Tuple[str, str]:
    """Convert XT symbol to (base, quote) currencies.

    Args:
        symbol: XT format (e.g., "btc_usdt")

    Returns:
        Tuple of (base_currency, quote_currency) in uppercase

    Raises:
        ValueError: If symbol format invalid
    """
    base, quote = symbol.split("_", 1)
    return base.upper(), quote.upper()
```

**TradingPair Construction** (minimal for batch query performance):
```python
def _create_minimal_trading_pair(
    self,
    base: str,
    quote: str
) -> TradingPair:
    """Create minimal TradingPair for batch query results.

    Uses default precision/size values since detailed exchange info
    not needed for price scanning use case.
    """
    return TradingPair(
        base_currency=base,
        quote_currency=quote,
        exchange=self.name,
        min_order_size=Decimal("0.001"),     # Conservative default
        max_order_size=Decimal("1000000"),   # Large default
        price_precision=8,                    # Common crypto precision
        quantity_precision=8,                 # Common crypto precision
    )
```

**Batch Response Parsing**:
```python
# XT API response structure (batch query)
{
    "rc": 0,
    "result": [
        {
            "s": "btc_usdt",      # symbol
            "c": "50000.00",      # close price
            "v": "123.456",       # volume (24h)
            "t": 1696512000000    # timestamp (ms)
        },
        {
            "s": "eth_usdt",
            "c": "3000.00",
            "v": "456.789",
            "t": 1696512000000
        }
        // ... more tickers
    ]
}
```

## Migration Impact

### Backward Compatibility
✅ **FULLY BACKWARD COMPATIBLE**
- Existing code: `get_ticker(trading_pair)` → Returns `Price` (unchanged)
- New code: `get_ticker()` or `get_ticker(None)` → Returns `List[Price]`
- Type checkers will infer correct return type based on parameter

### Type Narrowing Example
```python
from typing import TYPE_CHECKING

# Type checker understands both cases
result = await exchange.get_ticker(trading_pair)  # Type: Price
result = await exchange.get_ticker(None)          # Type: List[Price]

# Runtime type check if needed
if isinstance(result, list):
    # Batch result
    for price in result:
        process_price(price)
else:
    # Single result
    process_price(result)
```

## Summary
- ✅ No new data models required
- ✅ Signature change fully backward compatible
- ✅ Existing `Price`/`TradingPair` models sufficient
- ✅ Type-safe Union return based on parameter
- ✅ Clear error handling for unsupported exchanges
- ✅ Performance constraints satisfied by design

**Next Step**: Generate API contracts and contract tests.
