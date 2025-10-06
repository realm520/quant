# tri-arb Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-05

## Active Technologies
- Python 3.11+ (required for performance improvements and modern typing features) + uv (package management), uvloop (async optimization), httpx (HTTP client), websockets (WebSocket), aiosqlite (database), cachetools (caching), pydantic (validation), pydantic-settings (config), typer (CLI), structlog (logging), prometheus-client (metrics), PyInstaller (packaging) (001-python)

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
- 002-xt-spot-api: Added XT Exchange integration - XTExchange adapter implementing BaseExchange interface, async REST API client with httpx, HMAC-SHA256 authentication, trading pair transformation (BTC/USDT ↔ btc_usdt), contract tests (TDD), OpenAPI specification, performance targets (<50ms order execution, <2s price retrieval)
- 001-python: Added Python 3.11+ (required for performance improvements and modern typing features) + uv (package management), uvloop (async optimization), httpx (HTTP client), websockets (WebSocket), aiosqlite (database), cachetools (caching), pydantic (validation), pydantic-settings (config), typer (CLI), structlog (logging), prometheus-client (metrics), PyInstaller (packaging)

<!-- MANUAL ADDITIONS START -->
## XT Exchange Integration (Feature 002)

### Technical Stack
- **HTTP Client**: httpx (async, connection pooling, HTTP/2 support)
- **Authentication**: HMAC-SHA256 signature with custom headers (validate-*)
- **Retry Logic**: tenacity (exponential backoff for network errors)
- **Testing**: pytest + pytest-asyncio + respx (httpx mocking)

### Key Files
- `src/tri_arb/exchanges/xt.py` - XTExchange adapter (NOT YET IMPLEMENTED)
- `tests/unit/test_exchanges/test_xt_contract.py` - Contract tests (MUST FAIL until implementation)
- `tests/integration/test_xt_integration.py` - Integration tests (requires XT_API_KEY, XT_API_SECRET)
- `specs/002-xt-spot-api/` - Design documents (research.md, data-model.md, contracts/, quickstart.md)

### Architecture Patterns
- **Async/await**: All I/O operations use async pattern for performance
- **Connection pooling**: httpx.AsyncClient with max_connections=100, max_keepalive=20
- **Trading pair transformation**: `BTC/USDT` (internal) ↔ `btc_usdt` (XT format)
- **Order status mapping**: XT statuses (NEW, FILLED, CANCELED) → Internal OrderStatus enum
- **Error handling**: Retry transient errors (timeout, network), fail fast on auth/validation errors

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
- **Signature order**: Must be exactly X#METHOD#PATH[#QUERY][#BODY]
- **Connection state**: Must call `connect()` before any operations, `disconnect()` after
- **Decimal precision**: Always use `Decimal` type, never float for money/quantities

### Quick Commands
```bash
# Run XT contract tests (will fail until XTExchange implemented)
pytest tests/unit/test_exchanges/test_xt_contract.py -v

# Run XT integration tests (requires credentials)
export XT_API_KEY=your_key
export XT_API_SECRET=your_secret
pytest tests/integration/test_xt_integration.py --run-integration -v

# Type check XT adapter
mypy src/tri_arb/exchanges/xt.py --strict

# Lint XT adapter
ruff check src/tri_arb/exchanges/xt.py

# Format XT adapter
black src/tri_arb/exchanges/xt.py
```
<!-- MANUAL ADDITIONS END -->
- 所有python虚拟环境下的命令都要用uv来执行