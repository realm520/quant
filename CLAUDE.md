# tri-arb Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-05

## Active Technologies
- Python 3.11+ (required for performance improvements and modern typing features) + uv (package management), uvloop (async optimization), httpx (HTTP client), websockets (WebSocket), aiosqlite (database), cachetools (caching), pydantic (validation), pydantic-settings (config), typer (CLI), structlog (logging), prometheus-client (metrics), PyInstaller (packaging) (001-python)
- Python 3.11+ (required for performance and modern typing) + httpx (async HTTP client), pydantic (data validation), structlog (logging) (003-get-ticker-trading)
- N/A (stateless API operation) (003-get-ticker-trading)
- Python 3.11+ (required for performance and modern typing) + httpx (async HTTP), pydantic (validation), structlog (logging), colorama/rich (彩色输出), typer (CLI), asyncio (异步) (004-xt-get-ticker)
- N/A (无持久化，仅内存计算和实时输出) (004-xt-get-ticker)
- Python 3.11+ (已确定,项目要求) + httpx (async HTTP), pydantic (validation), structlog (logging), pytest (testing) (007-xtexhcnage-xtspotexchange-xt)
- N/A (无存储变更) (007-xtexhcnage-xtspotexchange-xt)
- Python 3.11+ + httpx (async HTTP, connection pooling), pydantic (data validation), tenacity (retry logic), pytest + pytest-asyncio + respx (testing) (008-xt-perp-api)
- N/A (无持久化需求，仅内存管理持仓和订单状态) (008-xt-perp-api)
- Python 3.11+ (项目标准) + yper (CLI框架), rich (终端UI), httpx (已有), pydantic (已有), structlog (已有) (009-xt-perp-api)
- N/A (无状态CLI工具) (009-xt-perp-api)

## Project Structure
```
src/
tests/
```

## Commands
cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style
Python 3.11+ (required for performance improvements and modern typing features): Follow standard conventions

## Recent Changes
- 009-xt-perp-api: Added Python 3.11+ (项目标准) + yper (CLI框架), rich (终端UI), httpx (已有), pydantic (已有), structlog (已有)
- 008-xt-perp-api: Added XT perpetual futures integration - XTPerpExchange adapter with position management, leverage control, funding rate tracking, dual-direction trading (LONG/SHORT), plan orders (stop-profit/stop-loss), extended data models (Position, FundingRate, LeverageBracket), performance target <50ms p95 order submission
- 007-xtexhcnage-xtspotexchange-xt: Added Python 3.11+ (已确定,项目要求) + httpx (async HTTP), pydantic (validation), structlog (logging), pytest (testing)

<!-- MANUAL ADDITIONS START -->
## XT Exchange Integration (Feature 002)

### Technical Stack
- **HTTP Client**: httpx (async, connection pooling, HTTP/2 support)
- **Authentication**: HMAC-SHA256 signature with custom headers (validate-*)
- **Retry Logic**: tenacity (exponential backoff for network errors)
- **Testing**: pytest + pytest-asyncio + respx (httpx mocking)

### Key Files
- `src/tri_arb/exchanges/xt_spot.py` - XTSpotExchange adapter (NOT YET IMPLEMENTED)
- `tests/unit/test_exchanges/test_xt_contract.py` - Contract tests (MUST FAIL until implementation)
- `tests/integration/test_xt_integration.py` - Integration tests (requires XT_API_KEY, XT_API_SECRET)
- `specs/002-xt-spot-api/` - Design documents (research.md, data-model.md, contracts/, quickstart.md)

### Architecture Patterns
- **Async/await**: All I/O operations use async pattern for performance
- **Connection pooling**: httpx.AsyncClient with max_connections=100, max_keepalive=20
- **Trading pair transformation**: `BTC/USDT` (internal) ↔ `btc_usdt` (XT format)
- **Order status mapping**: XT statuses (NEW, FILLED, CANCELED) → Internal OrderStatus enum
- **Error handling**: Retry transient errors (timeout, network), fail fast on auth/validation errors
- **Two-tier caching**: In-memory dict + LRU cache for trading pair information
  - Auto-loaded on `connect()` for optimal startup performance
  - Cache-first reads to minimize API calls
  - Manual refresh via `refresh_trading_pairs()` method

### Performance Requirements (NON-NEGOTIABLE)
- Order execution: <50ms p95 (from signal to order submission)
- Price processing: <10ms p95 (parsing only, not network)
- Ticker retrieval: <2 seconds (including network)
- Order placement: <3 seconds (including network)

### Security Considerations
- API credentials NEVER logged or exposed in error messages
- Signature generation uses millisecond timestamp (5-second window)
- All API calls use HTTPS with certificate verification
- Input validation at system boundaries (trading pairs, order params)

### Testing Strategy
1. **Contract tests** (Priority 1): Verify BaseExchange interface compliance
2. **Unit tests** (Priority 2): Test helpers (signature, format conversion, parsing)
3. **Integration tests** (Priority 3): Real XT API calls (requires credentials, marked @pytest.mark.integration)
4. **Performance tests** (Priority 4): Benchmark latency targets (use pytest-benchmark)

### TODO Items (From Research)
- Verify exact field names from XT API documentation (bid/ask prices, volume fields)
- Determine XT rate limits (requests per second/minute per endpoint)
- Confirm order status enum values (NEW, FILLED, CANCELED, PARTIALLY_FILLED, REJECTED, EXPIRED)
- Test WebSocket support availability (future enhancement)
- Verify supported order types beyond LIMIT and MARKET (IOC, FOK, POST_ONLY?)

### Common Pitfalls
- **Trading pair format**: Must use lowercase with underscore (`btc_usdt`), not uppercase or hyphen
- **Timestamp**: XT uses milliseconds, not seconds - `int(time.time() * 1000)`
- **Signature case sensitivity**: 🚨 **CRITICAL** - GET uses lowercase, POST/DELETE use UPPERCASE hexdigest
- **Signature format differences**:
  - GET: `X#METHOD#PATH[#QUERY][#BODY]` (X = auth params string)
  - POST/DELETE: `{sorted_headers}#METHOD#PATH[#QUERY][#BODY]` (headers sorted alphabetically)
- **Connection state**: Must call `connect()` before any operations, `disconnect()` after
- **Decimal precision**: Always use `Decimal` type, never float for money/quantities
- **Cache usage**: `get_trading_pair_info()` uses cache-first strategy, refresh cache via `refresh_trading_pairs()` if needed

### Implemented Features
- ✅ **get_balance()** - Account balance query (T017)
  - Endpoint: `GET /v4/balances`
  - Returns: `dict[str, dict[str, Decimal]]` with available, frozen, and total amounts
  - Filters out zero balances automatically
  - Requires authentication

### Quick Commands
```bash
# Run XT contract tests
pytest tests/unit/test_exchanges/test_xt_contract.py -v

# Run XT integration tests (requires credentials)
export XT_API_KEY=your_key
export XT_API_SECRET=your_secret
pytest tests/integration/test_xt_integration.py --run-integration -v

# Test balance command via CLI
export XT_API_KEY=your_key
export XT_API_SECRET=your_secret
cextools account balance --exchange-type spot

# Type check XT adapter
mypy src/tri_arb/exchanges/xt_spot.py --strict

# Lint XT adapter
ruff check src/tri_arb/exchanges/xt_spot.py

# Format XT adapter
black src/tri_arb/exchanges/xt_spot.py
```
<!-- MANUAL ADDITIONS END -->

## XT Perpetual Futures Integration (Feature 008)

### Technical Stack
- **HTTP Client**: httpx (async, connection pooling, HTTP/2 support)
- **Authentication**: HMAC-SHA256 signature (same as spot, different base URL)
- **Base URL**: `https://fapi.xt.com` (vs `https://sapi.xt.com` for spot)
- **Retry Logic**: tenacity (exponential backoff for network errors)
- **Testing**: pytest + pytest-asyncio + respx (httpx mocking)

### Key Files
- `src/tri_arb/exchanges/xt_perp.py` - XTPerpExchange adapter (NOT YET IMPLEMENTED)
- `tests/unit/test_exchanges/test_xt_perp_contract.py` - Contract tests (MUST FAIL until implementation)
- `tests/integration/test_xt_perp_integration.py` - Integration tests (requires XT_PERP_API_KEY, XT_PERP_API_SECRET)
- `specs/008-xt-perp-api/` - Design documents (research.md, data-model.md, contracts/, quickstart.md)

### Architecture Patterns
- **Async/await**: All I/O operations use async pattern for performance
- **Connection pooling**: httpx.AsyncClient with max_connections=100, max_keepalive=20
- **Dual-direction trading**: Position side (LONG/SHORT) + Order side (BUY/SELL)
- **Position tracking**: In-memory position management with real-time updates
- **Leverage management**: Per-symbol leverage configuration (1-125x)
- **Funding rate tracking**: Periodic funding rate queries for cost calculation
- **Error handling**: Retry transient errors (timeout, network), fail fast on auth/validation errors

### Data Model Extensions
- **TradingPair**: Added `leverage_brackets`, `contract_size`, `contract_type`
- **Order**: Added `position_side`, `time_in_force`, `trade_action` property
- **Position** (NEW): `symbol`, `side`, `quantity`, `entry_price`, `unrealized_pnl`, `leverage`, `liquidation_price`, `margin`, `roe`
- **FundingRate** (NEW): `symbol`, `rate`, `next_funding_time`
- **LeverageBracket** (NEW): `min_notional`, `max_notional`, `max_leverage`
- **PlanOrder** (NEW): Conditional orders (stop-profit, stop-loss)
- **StopProfit** (NEW): Take-profit configuration

### Performance Requirements (NON-NEGOTIABLE)
- Order execution: <50ms p95 (from signal to order submission)
- Position query: <100ms p95 (from request to response)
- Price processing: <10ms p95 (parsing only, not network)
- Funding rate query: <2 seconds (including network)

### Security Considerations
- API credentials NEVER logged or exposed in error messages
- Signature generation uses millisecond timestamp (5-second window)
- All API calls use HTTPS with certificate verification
- Input validation at system boundaries (leverage limits, position sizes)
- Liquidation price monitoring to prevent forced closure

### Trading Logic
- **Open Long**: `BUY` + `LONG` position_side
- **Open Short**: `SELL` + `SHORT` position_side
- **Close Long**: `SELL` + `LONG` position_side
- **Close Short**: `BUY` + `SHORT` position_side
- **Trade Action Property**: Auto-derives intent (OPEN_LONG, CLOSE_SHORT, etc.)

### Testing Strategy
1. **Contract tests** (Priority 1): Verify BaseExchange interface compliance + perpetual-specific methods
2. **Unit tests** (Priority 2): Test position tracking, leverage validation, funding rate calculations
3. **Integration tests** (Priority 3): Real XT perpetual API calls (requires credentials, marked @pytest.mark.integration)
4. **Performance tests** (Priority 4): Benchmark latency targets (use pytest-benchmark)

### Common Pitfalls
- **Position Side Confusion**: Must specify both `side` (BUY/SELL) and `position_side` (LONG/SHORT)
- **Leverage Limits**: Different symbols have different max leverage based on notional value
- **Funding Rate Timing**: Charged every 8 hours, can significantly impact P&L for long-held positions
- **Liquidation Risk**: High leverage increases liquidation risk, monitor `liquidation_price` closely
- **Margin Requirements**: Initial margin vs maintenance margin, understand the difference
- **Position Quantity**: Always in base currency (BTC for BTC/USDT), not quote currency

### Quick Commands
```bash
# Run XT perpetual contract tests (will fail until XTPerpExchange implemented)
uv run pytest tests/unit/test_exchanges/test_xt_perp_contract.py -v

# Run XT perpetual integration tests (requires credentials)
export XT_PERP_API_KEY=your_key
export XT_PERP_API_SECRET=your_secret
uv run pytest tests/integration/test_xt_perp_integration.py --run-integration -v

# Type check XT perpetual adapter
mypy src/tri_arb/exchanges/xt_perp.py --strict

# Lint XT perpetual adapter
ruff check src/tri_arb/exchanges/xt_perp.py

# Format XT perpetual adapter
black src/tri_arb/exchanges/xt_perp.py

# Test with quickstart example
uv run python examples/xt_perp_quickstart.py
```

## Automated Arbitrage Execution (Feature 005)

### Technical Stack
- **Execution Engine**: ArbitrageExecutor (async, sequential order execution)
- **Data Models**: ExecutionConfig, ExecutionStatus, ExecutionStep, ArbitrageExecution (Pydantic)
- **Order Management**: Market orders only, asyncio polling for order fills
- **Session Tracking**: UUID-based session IDs for complete arbitrage tracking
- **Testing**: pytest + pytest-asyncio + AsyncMock (mock exchange)

### Key Files
- `src/tri_arb/arbitrage/executor.py` - Core execution engine
- `src/tri_arb/arbitrage/execution_config.py` - Execution configuration model
- `src/tri_arb/models/execution.py` - Execution data models (ExecutionStatus, ExecutionStep, ArbitrageExecution)
- `src/tri_arb/cli/commands/monitor.py` - CLI integration with --execute and --dry-run flags
- `tests/unit/test_arbitrage/test_executor.py` - Unit tests for executor
- `specs/005-usdt/spec.md` - Complete functional specification (30 requirements)

### Architecture Patterns
- **Sequential Execution**: Complete one opportunity fully before moving to next (no parallelism)
- **Market Orders**: Immediate execution at current market price (no limit orders)
- **Order Polling**: Poll order status at 0.5s intervals with 30s timeout
- **Session Tracking**: Unique UUID session ID for each arbitrage execution
- **Three-Step Execution**: USDT → BTC → ETH → USDT (or similar triangular path)
- **P&L Calculation**: Net profit = final amount - initial amount, profit rate = (profit / initial) * 100

### Key Requirements (From spec.md)
- **FR-001**: Market orders only (no limit orders)
- **FR-002**: First trade amount ≥ 10 USDT minimum
- **FR-003**: Sequential execution (complete current opportunity before next)
- **FR-004**: Three sequential trades per opportunity
- **FR-006**: Unique session ID (UUID v4) for tracking
- **FR-007**: Session ID in all log messages
- **FR-014**: Calculate net profit (final - initial)
- **FR-015**: Calculate profit rate percentage
- **FR-023**: 30-second order timeout per trade
- **FR-024**: 0.5-second polling interval for order status

### Execution Flow
1. **Validation**: Check initial amount ≥ 10 USDT
2. **Create Execution**: Generate session ID, initialize execution record
3. **Step 1**: Submit market order → poll status → wait for fill → record results
4. **Step 2**: Use filled quantity from Step 1 → submit order → poll → fill → record
5. **Step 3**: Use filled quantity from Step 2 → submit order → poll → fill → record
6. **Calculate P&L**: Final amount vs initial amount, calculate profit rate
7. **Log Results**: Session ID, profit/loss, execution time

### CLI Usage
```bash
# Monitor only (no execution)
uv run tri-arb monitor

# Monitor with dry-run (simulate execution)
uv run tri-arb monitor --dry-run

# Monitor with real execution
uv run tri-arb monitor --execute

# Real execution in realtime mode
uv run tri-arb monitor --mode realtime --execute

# Execution with profit filter
uv run tri-arb monitor --min-profit 1.0 --execute
```

### Error Handling
- **Below Minimum**: Raise ValueError if initial amount < 10 USDT
- **Order Timeout**: Cancel order after 30s, raise TimeoutError
- **Order Rejected**: Raise RuntimeError with order status
- **Network Error**: Retry with exponential backoff (from exchange adapter)
- **Partial Execution**: Mark execution as FAILED, preserve completed steps

### Testing Strategy
1. **Unit Tests**: Mock exchange, test success/failure scenarios
2. **Integration Tests**: Real exchange API (future enhancement)
3. **Test Coverage**: Success, timeout, rejection, partial execution, validation

### Common Pitfalls
- **Amount Propagation**: Must use filled_quantity from previous step for next step
- **Currency Conversion**: Step 1 output currency must match Step 2 input currency
- **Session ID**: Must be included in all log messages for traceability
- **Market Orders**: price=None for market orders, quantity is in base currency
- **Order Polling**: Must handle transient network errors during polling
- **Execution State**: Mark status as FAILED on any exception, preserve completed steps

### Quick Commands
```bash
# Run executor unit tests
uv run pytest tests/unit/test_arbitrage/test_executor.py -v

# Test with real exchange (requires credentials)
export XT_API_KEY=your_key
export XT_API_SECRET=your_secret
uv run tri-arb monitor --execute

# Dry-run test (no real orders)
uv run tri-arb monitor --dry-run

# Monitor and execute with debug logs
uv run tri-arb monitor --execute --debug
```

- 所有python虚拟环境下的命令都要用uv来执行
