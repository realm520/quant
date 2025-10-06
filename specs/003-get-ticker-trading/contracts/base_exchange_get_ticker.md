# API Contract: BaseExchange.get_ticker()

**Feature**: 003-get-ticker-trading | **Interface**: BaseExchange | **Method**: get_ticker

## Contract Overview
`BaseExchange.get_ticker()` provides ticker price data for cryptocurrency trading pairs. Supports both single-pair queries and batch queries for all active markets.

## Method Signature
```python
async def get_ticker(
    self,
    trading_pair: Optional[TradingPair] = None
) -> Union[Price, List[Price]]:
    """Get current ticker price for a trading pair or all markets."""
```

## Request Contract

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `trading_pair` | `Optional[TradingPair]` | No (default: None) | Trading pair to query. If `None`, returns all active markets. |

### Valid Input Scenarios
1. **Single Ticker Query**: `trading_pair=TradingPair(...)` → Query specific market
2. **Batch Ticker Query**: `trading_pair=None` or omitted → Query all markets

### Invalid Inputs
- Any value other than `None` or valid `TradingPair` instance → Type error

## Response Contract

### Return Type
`Union[Price, List[Price]]` - Type depends on input parameter:
- `trading_pair` provided → Returns single `Price` object
- `trading_pair=None` → Returns `List[Price]` (may be empty)

### Single Ticker Response (trading_pair provided)
```python
Price(
    trading_pair=TradingPair(...),  # Same as input
    bid_price=Decimal("50000.00"),
    ask_price=Decimal("50001.00"),
    bid_volume=Decimal("10.5"),
    ask_volume=Decimal("8.3"),
    timestamp=datetime(2025, 10, 6, 12, 0, 0),
    exchange="xt"
)
```

**Constraints**:
- `bid_price` > 0
- `ask_price` > 0
- `ask_price` ≥ `bid_price` (normal market condition)
- `bid_volume` ≥ 0
- `ask_volume` ≥ 0
- `timestamp` is recent (< 5 seconds old for real-time data)
- `exchange` matches adapter name

### Batch Ticker Response (trading_pair=None)
```python
[
    Price(
        trading_pair=TradingPair(base_currency="BTC", quote_currency="USDT", ...),
        bid_price=Decimal("50000.00"),
        ask_price=Decimal("50001.00"),
        bid_volume=Decimal("10.5"),
        ask_volume=Decimal("8.3"),
        timestamp=datetime(2025, 10, 6, 12, 0, 0),
        exchange="xt"
    ),
    Price(
        trading_pair=TradingPair(base_currency="ETH", quote_currency="USDT", ...),
        bid_price=Decimal("3000.00"),
        ask_price=Decimal("3001.00"),
        bid_volume=Decimal("50.0"),
        ask_volume=Decimal("45.2"),
        timestamp=datetime(2025, 10, 6, 12, 0, 0),
        exchange="xt"
    )
    // ... more Price objects for each active market
]
```

**Constraints**:
- Each `Price` object satisfies single ticker constraints
- Each `Price.trading_pair` is unique (no duplicates)
- List may be empty if exchange has no active markets
- All timestamps are close to current time (data freshness)

## Error Contract

### Exception Types
| Exception | Condition | Example Message |
|-----------|-----------|-----------------|
| `NotImplementedError` | Batch query not supported | `"{exchange_name} exchange does not support batch ticker queries. Please provide a specific trading_pair parameter."` |
| `ExchangeConnectionError` | Exchange not connected | Inherited from existing contract |
| `InvalidTradingPairError` | Invalid trading pair (when provided) | Inherited from existing contract |
| `httpx.TimeoutException` | Network timeout | Inherited from HTTP client |
| `httpx.HTTPStatusError` | HTTP error (4xx/5xx) | Inherited from HTTP client |

### Error Scenarios
1. **Batch Query Unsupported**:
   ```python
   await base_exchange.get_ticker(None)
   # Raises: NotImplementedError("{name} does not support batch ticker queries...")
   ```

2. **Not Connected**:
   ```python
   exchange = XTExchange()  # Not connected
   await exchange.get_ticker(trading_pair)
   # Raises: ExchangeConnectionError("Exchange not connected. Call connect() first.")
   ```

3. **Invalid Trading Pair**:
   ```python
   invalid_pair = TradingPair(base_currency="", quote_currency="USDT", ...)
   await exchange.get_ticker(invalid_pair)
   # Raises: InvalidTradingPairError (from validation)
   ```

4. **API Timeout**:
   ```python
   await exchange.get_ticker(None)  # Network issues
   # Raises: httpx.TimeoutException (after retry exhaustion)
   ```

## Performance Contract

### Latency Requirements
- **Single ticker query**: <50ms p95 (existing contract, unchanged)
- **Batch ticker query**: <1000ms p95 (NFR-001)

### Scalability Requirements
- **Batch query**: Support ≥500 trading pairs (NFR-002)
- **Memory**: No unbounded list growth, streaming parse recommended

## Behavior Contract

### Partial Failure Handling (Batch Query)
When parsing batch ticker data:
- **Success subset**: Include all successfully parsed `Price` objects
- **Failed tickers**: Log failure with context, do not halt execution
- **Empty result**: Return `[]` if all tickers fail parsing (edge case)

**Example**:
```python
# XT returns 100 tickers, 2 fail to parse
result = await xt_exchange.get_ticker(None)
len(result)  # Returns 98, not 100
# Logs contain 2 warning entries with failure details
```

### Caching Behavior
- **No caching** (FR-011): Each call queries exchange API, returns fresh data
- **Timestamp**: Reflects actual data retrieval time, not cached time

### Connection State
- MUST be called after `connect()` (pre-condition)
- Connection state unchanged after call (stateless operation)

## Contract Tests

### Test File Location
- `tests/unit/test_exchanges/test_base_contract.py`
- `tests/unit/test_exchanges/test_xt_contract.py`

### Test Coverage Requirements
1. **Single ticker query** (backward compatibility):
   - ✅ Valid trading pair → Returns Price
   - ✅ Response time <50ms p95
   - ✅ Price data valid (bid/ask/volume constraints)

2. **Batch ticker query** (new feature):
   - ✅ trading_pair=None → Returns List[Price]
   - ✅ Each Price object valid
   - ✅ No duplicate trading pairs
   - ✅ Response time <1000ms
   - ✅ ≥500 trading pairs handled

3. **Error handling**:
   - ✅ Unsupported exchange raises NotImplementedError
   - ✅ Not connected raises ExchangeConnectionError
   - ✅ Network timeout raises httpx.TimeoutException

4. **Partial failure** (batch):
   - ✅ Some failed tickers → Returns successful subset
   - ✅ Failures logged with structured context
   - ✅ Empty list if all fail

## Version History
- **v1.0** (Feature 002): Initial single ticker contract
- **v2.0** (Feature 003): Added batch ticker support with Optional parameter

## Related Contracts
- `BaseExchange.connect()` - Pre-requisite for get_ticker
- `BaseExchange.get_orderbook()` - Similar batch pattern (future)
- `Price` model validation - Pydantic constraints
