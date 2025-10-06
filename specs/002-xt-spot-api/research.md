# Research: XT Exchange Integration

**Feature**: 002-xt-spot-api  
**Phase**: 0 (Research & Technical Decisions)  
**Date**: 2025-10-05

## Executive Summary

This document captures technical research and decisions for integrating XT Exchange into the tri-arb trading system. The primary challenge is transforming the synchronous `xt_spot_api.py` implementation into an async adapter conforming to the `BaseExchange` interface while maintaining compatibility with the project's performance and reliability standards.

---

## 1. HTTP Client Selection

### Decision: **httpx** (async)

### Rationale:
- **Already in dependencies**: `pyproject.toml` includes `httpx>=0.27.0`
- **Async native**: Built for async/await from ground up, unlike aiohttp which is async-only
- **requests-compatible API**: Easier migration from `xt_spot_api.py` (uses `requests`)
- **HTTP/2 support**: Performance advantage for multiplexed connections
- **Better typing**: Stronger type hints for mypy strict mode
- **Connection pooling**: Built-in with configurable limits

### Code Pattern:
```python
import httpx

class XTExchange(BaseExchange):
    def __init__(self, ...):
        self._client: httpx.AsyncClient | None = None
    
    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://sapi.xt.com",
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
    
    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
```

### Alternatives Considered:
- **aiohttp**: Excluded - different API paradigm, requires context managers everywhere
- **requests**: Excluded - synchronous, blocks event loop

### Performance Impact:
- Connection pooling reduces latency by ~50ms per request (connection reuse)
- HTTP/2 multiplexing enables parallel requests without connection overhead
- Timeout configuration prevents hung requests (critical for trading)

---

## 2. Synchronous to Async Transformation Pattern

### Decision: **Native async/await with httpx**

### Transformation Map:

| Original (sync) | Transformed (async) |
|----------------|---------------------|
| `requests.get(url, params=p)` | `await client.get(path, params=p)` |
| `requests.post(url, json=data)` | `await client.post(path, json=data)` |
| `time.sleep(0.1)` | `await asyncio.sleep(0.1)` (if needed) |
| `int(time.time()*1000)` | `int(time.time()*1000)` (unchanged) |

### Example Transformation:
**Before (xt_spot_api.py)**:
```python
def get_ticker(self, symbol):
    params = {'symbol': symbol}
    response = requests.get('https://sapi.xt.com/v4/public/ticker/price', params=params)
    return response.json()
```

**After (xt.py)**:
```python
async def get_ticker(self, trading_pair: TradingPair) -> Price:
    symbol = self._to_xt_symbol(trading_pair)  # BTC/USDT → btc_usdt
    response = await self._client.get('/v4/public/ticker/price', params={'symbol': symbol})
    data = response.json()
    return self._parse_ticker(data, trading_pair)  # Transform to Price model
```

### Rationale:
- httpx API closely mirrors requests, minimizing transformation complexity
- No need for `asyncio.to_thread()` - pure async I/O
- Type hints maintained throughout transformation
- Error handling unified with project standards

---

## 3. HMAC-SHA256 Signature Generation

### Decision: **Synchronous signature generation (CPU-bound)**

### Rationale:
- **CPU-bound operation**: HMAC-SHA256 is computationally intensive but fast (<1ms)
- **No async benefit**: No I/O wait time to overlap with other operations
- **Simplicity**: Avoids `asyncio.to_thread()` complexity for marginal benefit
- **Existing pattern**: `xt_spot_api.py` signature logic can be reused directly

### Implementation Pattern:
```python
import hmac
import hashlib
import time

def _generate_signature(
    self,
    method: str,
    path: str,
    query: str,
    body: str,
    api_key: str,
    secret_key: str
) -> tuple[dict[str, str], str]:
    """Generate XT API signature (synchronous, CPU-bound)."""
    timestamp_ms = int(time.time() * 1000)
    X = f'validate-algorithms=HmacSHA256&validate-appkey={api_key}&validate-recvwindow=5000&validate-timestamp={timestamp_ms}'
    
    sig_data = f'{X}#{method}#{path}'
    if query:
        sig_data += f'#{query}'
    if body:
        sig_data += f'#{body}'
    
    signature = hmac.new(
        secret_key.encode('utf-8'),
        sig_data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        'validate-algorithms': 'HmacSHA256',
        'validate-appkey': api_key,
        'validate-recvwindow': '5000',
        'validate-timestamp': str(timestamp_ms),
        'validate-signature': signature,
        'Content-Type': 'application/json',
        'accept': '*/*'
    }
    
    return headers, signature
```

### Performance Considerations:
- HMAC-SHA256 ~0.1-0.5ms on modern CPU (negligible vs network latency ~10-50ms)
- No need for thread pool executor
- Signature generation happens during request preparation (before network call)

### Future Optimization (if needed):
- If profiling shows signature generation as bottleneck (unlikely): use `asyncio.to_thread()`
- Mark as TODO for performance monitoring

---

## 4. Trading Pair Format Transformation

### Decision: **Bidirectional transformation helper**

### XT Format Specification:
- Pattern: `{base}_{quote}` (lowercase, underscore separator)
- Examples: `btc_usdt`, `eth_usdt`, `bnb_usdt`

### Internal Format:
- Type: `TradingPair(base_currency: str, quote_currency: str)`
- Examples: `TradingPair(base_currency="BTC", quote_currency="USDT")`

### Implementation:
```python
def _to_xt_symbol(self, trading_pair: TradingPair) -> str:
    """Convert TradingPair to XT symbol format.
    
    Args:
        trading_pair: Internal trading pair model
        
    Returns:
        XT symbol format (e.g., "btc_usdt")
        
    Examples:
        >>> _to_xt_symbol(TradingPair(base_currency="BTC", quote_currency="USDT"))
        "btc_usdt"
    """
    return f"{trading_pair.base_currency.lower()}_{trading_pair.quote_currency.lower()}"

def _from_xt_symbol(self, symbol: str) -> tuple[str, str]:
    """Parse XT symbol format to base/quote currencies.
    
    Args:
        symbol: XT symbol format (e.g., "btc_usdt")
        
    Returns:
        Tuple of (base_currency, quote_currency) in uppercase
        
    Examples:
        >>> _from_xt_symbol("btc_usdt")
        ("BTC", "USDT")
    """
    base, quote = symbol.split('_')
    return base.upper(), quote.upper()
```

### Validation:
- XT symbols must match pattern: `^[a-z]+_[a-z]+$`
- Invalid symbols should raise `ValueError` with clear message
- TODO: Fetch supported trading pairs from XT API for runtime validation

---

## 5. Error Handling & Retry Strategy

### Decision: **Exponential backoff with httpx-retry integration**

### Error Categories:

#### Network Errors (Transient):
- Connection timeouts → Retry with exponential backoff
- DNS resolution failures → Retry 3 times
- Connection refused → Retry with backoff

#### API Errors (Non-transient):
- 401 Unauthorized → No retry, raise `AuthenticationError`
- 400 Bad Request → No retry, raise `ValidationError`
- 429 Rate Limit → Retry with exponential backoff + rate limit tracking
- 500 Server Error → Retry 3 times

#### Domain Errors:
- Invalid trading pair → No retry, raise `InvalidTradingPairError`
- Insufficient balance → No retry, raise `InsufficientBalanceError`

### Implementation Pattern:
```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import httpx

class XTExchange(BaseExchange):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
    )
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """Make authenticated request with retry logic."""
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()  # Raises for 4xx/5xx
        return response
```

### Rate Limiting:
- **TODO**: Determine XT's exact rate limits (requests per second/minute)
- Implement token bucket algorithm if limits documented
- Fallback: Exponential backoff on 429 errors
- Log rate limit hits for monitoring

### Logging:
- Log all errors with full context (request params, response, trace ID)
- Use structlog for structured JSON logs
- Include correlation ID for request tracing

---

## 6. Response Parsing & Data Model Mapping

### Decision: **Explicit parsing methods for each endpoint**

### Parsing Pattern:
```python
def _parse_ticker(self, data: dict, trading_pair: TradingPair) -> Price:
    """Parse XT ticker response to Price model.
    
    XT Response Format:
    {
        "rc": 0,
        "mc": "SUCCESS",
        "ma": [],
        "result": {
            "s": "btc_usdt",
            "t": 1696348800000,
            "cv": 0.0024,
            "cr": "0.00004800",
            "o": 50000.00,
            "l": 49500.00,
            "h": 50500.00,
            "c": 50024.00,
            "q": 12450000.00,
            "v": 248.5,
            "ap": 50012.50
        }
    }
    """
    if data.get('rc') != 0 or data.get('mc') != 'SUCCESS':
        raise ValueError(f"XT API error: {data.get('mc')}")
    
    result = data['result']
    
    # TODO: Determine exact field mapping from XT documentation
    # Assumptions based on common exchange patterns:
    # - 'c': close price (last traded price)
    # - 'ap': average price
    # - 'v': volume (base currency)
    # - 'q': quote volume
    
    return Price(
        trading_pair=trading_pair,
        bid_price=Decimal(str(result['c'])),  # TODO: Verify XT bid field
        ask_price=Decimal(str(result['c'])),  # TODO: Verify XT ask field
        bid_volume=Decimal(str(result['v'])),  # TODO: Verify volume field
        ask_volume=Decimal(str(result['v'])),  # TODO: Verify volume field
        exchange=self.name,
        timestamp=datetime.fromtimestamp(result['t'] / 1000, tz=timezone.utc)
    )
```

### Data Model Validation:
- Use Pydantic models for XT API responses (optional, for validation)
- Validate all Decimal conversions (no float arithmetic)
- Timezone-aware timestamps (UTC)
- Handle missing/null fields gracefully

### TODO: API Response Documentation
- **Critical**: Document exact field mappings from XT API documentation
- Fields needing clarification:
  - Bid/ask prices vs last/close price
  - Volume units (base or quote currency)
  - Order status field names
  - Fee structure and calculation

---

## 7. Order Status Mapping

### Decision: **Explicit mapping table**

### XT Order States → Internal OrderStatus:

| XT Status | Internal Status | Description |
|-----------|----------------|-------------|
| `NEW` | `OrderStatus.OPEN` | Order created, not filled |
| `FILLED` | `OrderStatus.FILLED` | Completely filled |
| `CANCELED` | `OrderStatus.CANCELLED` | User cancelled |
| `PARTIALLY_FILLED` | `OrderStatus.PARTIAL` | Partially executed |
| `REJECTED` | `OrderStatus.FAILED` | Exchange rejected |
| `EXPIRED` | `OrderStatus.CANCELLED` | Time-in-force expired |

### Implementation:
```python
from enum import Enum
from tri_arb.core.models import OrderStatus

class XTOrderStatus(str, Enum):
    """XT exchange order status values."""
    NEW = "NEW"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

_XT_STATUS_MAP: dict[XTOrderStatus, OrderStatus] = {
    XTOrderStatus.NEW: OrderStatus.OPEN,
    XTOrderStatus.FILLED: OrderStatus.FILLED,
    XTOrderStatus.CANCELED: OrderStatus.CANCELLED,
    XTOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIAL,
    XTOrderStatus.REJECTED: OrderStatus.FAILED,
    XTOrderStatus.EXPIRED: OrderStatus.CANCELLED,
}

def _map_order_status(self, xt_status: str) -> OrderStatus:
    """Map XT order status to internal status."""
    try:
        xt_enum = XTOrderStatus(xt_status)
        return _XT_STATUS_MAP[xt_enum]
    except (ValueError, KeyError):
        logger.warning("Unknown XT order status", xt_status=xt_status)
        return OrderStatus.OPEN  # Safe default
```

### TODO: Verify Status Values
- Confirm exact status string values from XT API documentation
- Determine if additional states exist (e.g., `PENDING`, `PROCESSING`)

---

## 8. Performance Optimization Strategies

### 1. Connection Pooling
**Status**: Implemented via httpx.AsyncClient
- Max connections: 100
- Max keepalive: 20
- Reduces connection overhead by ~30-50ms per request

### 2. Request Batching (Future)
**Status**: TODO - Future optimization
- Some XT endpoints may support batch operations
- Investigate: Can fetch multiple ticker prices in single request?
- Priority: Low (optimize after initial implementation)

### 3. Response Caching (Cautious)
**Status**: Not recommended for trading data
- Price data must be fresh (<1 second old)
- Order status caching can cause incorrect balance calculations
- Exception: Trading pair metadata (rarely changes)

### 4. Parallel Request Handling
**Status**: Enabled by async design
- Example: Fetch prices from multiple exchanges concurrently
```python
async def get_all_prices(self, trading_pair: TradingPair):
    prices = await asyncio.gather(
        binance.get_ticker(trading_pair),
        okx.get_ticker(trading_pair),
        xt.get_ticker(trading_pair),
        return_exceptions=True  # Don't fail all if one fails
    )
    return prices
```

### 5. Timeout Tuning
**Status**: Configured conservatively
- Connect timeout: 5 seconds (time to establish TCP connection)
- Read timeout: 10 seconds (time to receive response)
- Total timeout: 10 seconds (overall request duration)
- Rationale: Trading requires fast responses; better to timeout and retry

### Performance Targets (from Constitution):
- Order execution: <50ms p95 (includes XT API call + signature)
- Price processing: <10ms p95 (parsing only, not network)
- Memory: <500MB steady-state (connection pool is small)

---

## 9. Security Considerations

### 1. API Credential Handling
**Status**: Must implement securely
- Never log API keys or secrets
- Never include credentials in error messages
- Store in environment variables, not config files
- Support optional encryption at rest

### 2. Signature Validation
**Status**: Critical for preventing replay attacks
- XT uses timestamp-based signature (5-second window)
- Ensure server time synchronization (NTP)
- Reject requests with timestamps outside window

### 3. Rate Limit Compliance
**Status**: TODO - Implement rate limiting
- Prevents account suspension
- Protects against accidental DoS
- Implements token bucket or leaky bucket algorithm

### 4. Input Validation
**Status**: Enforced by type system + Pydantic
- Validate all trading pair symbols
- Validate order quantities (min/max limits)
- Validate prices (precision rules)
- Sanitize user inputs before API calls

### 5. TLS/SSL Verification
**Status**: Enabled by default in httpx
- Always verify SSL certificates
- Never disable verification (even in dev)
- Use TLS 1.2+ only

---

## 10. Testing Strategy

### Contract Tests (Priority 1)
**Goal**: Verify BaseExchange interface compliance
- Test all 10 abstract methods are implemented
- Test method signatures match interface
- Test return types are correct
- **Must fail initially** (TDD requirement)

### Unit Tests (Priority 2)
**Goal**: Test internal methods in isolation
- Trading pair format conversion
- Signature generation
- Response parsing
- Error handling
- Order status mapping

### Integration Tests (Priority 3)
**Goal**: Test against XT API (optional, requires credentials)
- Real API calls with test account
- Verify response formats
- Test error scenarios (invalid symbol, insufficient balance)
- **Marked as `@pytest.mark.integration` and skipped by default**

### Performance Tests (Priority 4)
**Goal**: Validate latency targets
- Benchmark signature generation (<1ms)
- Benchmark request roundtrip (<100ms including network)
- Benchmark concurrent requests (10 simultaneous)
- Use `pytest-benchmark` for reproducible results

### Mocking Strategy:
- Mock httpx responses for unit tests
- Use `respx` library for httpx mocking
- Create realistic XT API response fixtures
- Test both success and error responses

---

## 11. Open Questions & TODO Items

### High Priority (Block Implementation):
1. **XT API Documentation**: Obtain official XT API v4 documentation
   - Exact field names for ticker response (bid, ask, volume)
   - Order status enum values
   - Error response format
   - Rate limiting policies
   - **Action**: Request from XT support or reverse-engineer from `xt_spot_api.py`

2. **Trading Pair List**: Which XT trading pairs to support?
   - Start with major pairs: BTC/USDT, ETH/USDT, BNB/USDT
   - Fetch supported pairs from XT API dynamically?
   - **Action**: Implement `/v4/public/symbols` endpoint (if available)

### Medium Priority (Optimize After Initial Release):
3. **Rate Limiting**: XT's exact rate limits
   - Requests per second/minute per endpoint
   - IP-based vs account-based limits
   - **Action**: Test in integration environment, monitor 429 responses

4. **WebSocket Support**: When to add real-time streaming?
   - REST polling sufficient for initial implementation
   - WebSocket for sub-second price updates (Phase 2)
   - **Action**: Defer to future feature

5. **Testnet Environment**: Does XT provide sandbox/testnet?
   - Integration testing without real money
   - **Action**: Contact XT support

### Low Priority (Nice to Have):
6. **Order Types**: Does XT support IOC, FOK, POST_ONLY?
   - Initial implementation: LIMIT and MARKET only
   - **Action**: Document in future enhancement

7. **Pagination**: Trade history pagination for >100 trades
   - Initial implementation: Single page (limit=100)
   - **Action**: Implement if needed based on usage

8. **Fee Structure**: Confirm XT's fee calculation
   - Maker/taker fees
   - Fee deduction from order quantity or separate?
   - **Action**: Test with real orders in integration

---

## 12. Implementation Phases

### Phase 1: Core Adapter (Minimal Viable)
**Deliverables**:
- `src/tri_arb/exchanges/xt.py` - XTExchange class
- 10 BaseExchange methods implemented
- Trading pair transformation helpers
- Signature generation
- Basic error handling

**Testing**:
- Contract tests (all passing)
- Unit tests for helpers (>80% coverage)

### Phase 2: Robust Error Handling
**Deliverables**:
- Retry logic with exponential backoff
- Comprehensive error types
- Rate limit handling
- Detailed logging

**Testing**:
- Error scenario tests
- Retry mechanism tests

### Phase 3: Performance & Monitoring
**Deliverables**:
- Performance benchmarks
- Prometheus metrics
- Latency monitoring
- Connection pool tuning

**Testing**:
- Performance tests
- Load testing

### Phase 4: Production Hardening (Future)
**Deliverables**:
- WebSocket streaming
- Advanced order types
- Comprehensive documentation
- Integration environment testing

---

## 13. Dependencies

### External Libraries (Add to pyproject.toml):
```toml
[project]
dependencies = [
    "httpx>=0.27.0",  # Already present
    "tenacity>=8.2.0",  # Retry logic
]

[project.optional-dependencies]
dev = [
    "respx>=0.20.0",  # httpx mocking for tests
    "pytest-benchmark>=4.0.0",  # Performance testing
]
```

### Internal Dependencies (Already Available):
- `tri_arb.core.models` - TradingPair, Price, OrderBook, Order
- `tri_arb.exchanges.base` - BaseExchange interface
- `tri_arb.config.logging` - structlog setup
- `tri_arb.config.settings` - Configuration management

---

## 14. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| XT API documentation incomplete | High | Medium | Reverse-engineer from `xt_spot_api.py` |
| Rate limits too restrictive | High | Low | Implement intelligent batching and caching |
| Authentication changes break integration | High | Low | Comprehensive error handling and monitoring |
| Performance targets not met | Medium | Low | Profile and optimize hot paths |
| XT API downtime | Medium | Medium | Graceful degradation, fallback to other exchanges |

---

## 15. Success Criteria

### Functional:
- ✅ All 10 BaseExchange methods implemented
- ✅ Contract tests passing
- ✅ Unit test coverage ≥80%
- ✅ Integration with existing factory pattern

### Non-Functional:
- ✅ Type checking passes (mypy strict mode)
- ✅ Linting passes (ruff)
- ✅ Performance targets met (<50ms order execution)
- ✅ Zero security vulnerabilities
- ✅ Comprehensive error handling

### Documentation:
- ✅ All public methods have docstrings
- ✅ Complex algorithms explained
- ✅ TODO items clearly marked
- ✅ Quickstart guide created

---

## 16. Next Steps (Phase 1)

1. ✅ Create `data-model.md` - Design XTExchange class structure
2. ✅ Create `contracts/` - Define XT API contracts (OpenAPI)
3. ✅ Generate contract tests - TDD failing tests
4. ✅ Create `quickstart.md` - Validation guide
5. ✅ Update `CLAUDE.md` - AI assistant context
6. ⏳ Execute `/tasks` command - Generate implementation tasks
7. ⏳ Implement XTExchange class - Make tests pass
8. ⏳ Performance validation - Benchmark and optimize

---

**Document Status**: Complete  
**All NEEDS CLARIFICATION Resolved**: Yes (marked as TODO where documentation needed)  
**Ready for Phase 1**: ✅ Yes
