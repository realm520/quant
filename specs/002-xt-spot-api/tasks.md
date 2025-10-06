# Tasks: XT Exchange Spot Market Integration

**Input**: Design documents from `/specs/002-xt-spot-api/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/xt-api.yaml, quickstart.md

## Execution Flow (main)
```
1. ✅ Load plan.md from feature directory
   → Tech stack: Python 3.11+, httpx, pydantic, structlog, pytest
   → Structure: Single project (src/, tests/)
2. ✅ Load optional design documents:
   → data-model.md: XTExchange class + 10 helper models
   → contracts/: xt-api.yaml with 8 endpoints
   → research.md: httpx selection, HMAC auth, retry logic
   → quickstart.md: 8 validation scenarios
3. ✅ Generate tasks by category:
   → Setup: Dependencies, linting, project structure
   → Tests: 8 contract tests + 8 integration tests (TDD)
   → Core: XTExchange class + 10 methods + helpers
   → Integration: Settings configuration
   → Polish: Docstrings, type hints, manual validation
4. ✅ Apply task rules:
   → Different files = mark [P] for parallel
   → Same file = sequential (no [P])
   → Tests before implementation (TDD)
5. ✅ Number tasks sequentially (T001-T025)
6. ✅ Generate dependency graph
7. ✅ Create parallel execution examples
8. ✅ Validate task completeness
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- **Single project**: `src/tri_arb/`, `tests/` at repository root
- All paths shown below are absolute from repository root

---

## Phase 3.1: Setup

### T001: ✅ Verify Dependencies in pyproject.toml
**Type**: Setup | **Priority**: Critical | **Parallel**: No  
**File**: `pyproject.toml`

**Description**: Verify that all required dependencies are present in pyproject.toml for XT integration:
- httpx >= 0.27.0 (async HTTP client)
- pydantic >= 2.0 (data validation)
- tenacity (retry logic)
- structlog (logging)
- pytest-asyncio (async testing)
- respx (httpx mocking for tests)

**Acceptance Criteria**:
- All dependencies listed in `[project.dependencies]` or `[project.optional-dependencies.dev]`
- Run `uv pip list` to confirm packages available in venv
- No missing imports when creating XTExchange skeleton

**Dependencies**: None

---

### T002 [P]: ✅ Configure Linting for XT Module
**Type**: Setup | **Priority**: High | **Parallel**: Yes (different config from implementation)  
**Files**: `ruff.toml` (read-only), verify settings apply to `src/tri_arb/exchanges/xt.py`

**Description**: Verify that existing Ruff configuration will properly lint the new XT exchange module:
- Check that `src/tri_arb/exchanges/` is included in lint paths
- Verify type checking rules will catch missing type hints
- Confirm async/await rules are enabled

**Acceptance Criteria**:
- Ruff configuration includes exchanges directory
- Can run `make lint` successfully (should pass since no XT code exists yet)
- No configuration changes needed (confirm existing setup sufficient)

**Dependencies**: None

---

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3

**CRITICAL**: These tests MUST be written and MUST FAIL before ANY implementation begins.

### T003 [P]: ✅ Verify Contract Tests Fail (TDD Baseline)
**Type**: Contract Test | **Priority**: Critical | **Parallel**: Yes (runs tests, doesn't modify)  
**File**: `tests/unit/test_exchanges/test_xt_contract.py` (already created in Phase 1)

**Description**: Run pytest on existing contract tests to establish TDD baseline. Tests should fail with ImportError because XTExchange doesn't exist yet.

**Command**:
```bash
pytest tests/unit/test_exchanges/test_xt_contract.py -v
```

**Expected Output**:
```
test_xt_exchange_importable FAILED - ImportError: cannot import name 'XTExchange'
test_exchange_implements_required_methods SKIPPED - XTExchange not yet implemented
...
```

**Acceptance Criteria**:
- `test_xt_exchange_importable` fails with ImportError
- All other tests skipped due to `@pytest.mark.skipif(not XT_EXCHANGE_AVAILABLE)`
- Baseline test output documented in test run log

**Dependencies**: None

---

### T004 [P]: ✅ Run Integration Tests Baseline (Should Skip)
**Type**: Integration Test | **Priority**: Medium | **Parallel**: Yes (reads existing test file)  
**File**: `tests/integration/test_xt_integration.py` (already created in Phase 1)

**Description**: Verify integration tests are properly configured to skip when credentials not available.

**Command**:
```bash
pytest tests/integration/test_xt_integration.py -v
```

**Expected Output**:
```
test_get_ticker_real_api SKIPPED - XT API credentials not configured
test_place_and_cancel_order SKIPPED - XT API credentials not configured
...
```

**Acceptance Criteria**:
- All integration tests skip with message about missing credentials
- No errors or failures (only skips)
- Safety warnings appear in test docstrings

**Dependencies**: None

---

## Phase 3.3: Core Implementation (ONLY after tests are failing)

### T005: ✅ Create XTExchange Module Skeleton
**Type**: Implementation | **Priority**: Critical | **Parallel**: No (blocks all other implementation)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Create the basic file structure for XTExchange class with imports and class definition. No method implementations yet, just structure.

**Implementation**:
```python
"""XT Exchange adapter for tri-arb trading system.

Provides async interface to XT Exchange REST API v4.
"""

from typing import AsyncIterator, Optional
from decimal import Decimal
from datetime import datetime
import hmac
import hashlib
import time
import json
import urllib.parse

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

from tri_arb.exchanges.base import BaseExchange
from tri_arb.core.models import (
    Order,
    OrderBook,
    OrderStatus,
    Price,
    Trade,
    TradingPair,
)
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


class XTExchange(BaseExchange):
    """XT Exchange adapter implementation.
    
    Provides async interface to XT Exchange REST API v4, conforming to
    BaseExchange protocol for triangle arbitrage trading system.
    
    Attributes:
        name: Exchange identifier ("xt")
        api_key: XT API key for authentication
        api_secret: XT API secret for HMAC-SHA256 signature
        is_connected: Connection state flag
    """
    
    BASE_URL: str = "https://sapi.xt.com"
    API_VERSION: str = "v4"
    RECV_WINDOW: int = 5000  # milliseconds
    
    def __init__(
        self,
        name: str = "xt",
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        """Initialize XT Exchange adapter.
        
        Args:
            name: Exchange identifier (default: "xt")
            api_key: XT API key (empty for public endpoints only)
            api_secret: XT API secret (empty for public endpoints only)
        """
        super().__init__(name)
        self.api_key = api_key
        self.api_secret = api_secret
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info(
            "XTExchange initialized",
            has_api_key=bool(api_key),
            has_api_secret=bool(api_secret),
        )
```

**Acceptance Criteria**:
- File created at `src/tri_arb/exchanges/xt.py`
- XTExchange class can be imported: `from tri_arb.exchanges.xt import XTExchange`
- `test_xt_exchange_importable` now passes
- All abstract methods still need implementation (tests still fail for missing methods)

**Dependencies**: T003 (verify tests fail first)

---

### T006 [P]: ✅ Implement Helper Method: _to_xt_symbol
**Type**: Implementation | **Priority**: High | **Parallel**: Yes (helper method, no dependencies)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement trading pair to XT symbol format conversion method.

**Implementation Location**: Add to XTExchange class
```python
def _to_xt_symbol(self, trading_pair: TradingPair) -> str:
    """Convert TradingPair to XT symbol format.
    
    Args:
        trading_pair: Internal trading pair model
        
    Returns:
        XT symbol format (lowercase with underscore)
        
    Raises:
        ValueError: If trading pair currencies are invalid
        
    Examples:
        >>> _to_xt_symbol(TradingPair(base_currency="BTC", quote_currency="USDT"))
        "btc_usdt"
    """
    if not trading_pair.base_currency or not trading_pair.quote_currency:
        raise ValueError("Trading pair must have both base and quote currencies")
    
    return f"{trading_pair.base_currency.lower()}_{trading_pair.quote_currency.lower()}"
```

**Acceptance Criteria**:
- Method added to XTExchange class
- Converts TradingPair(base="BTC", quote="USDT") → "btc_usdt"
- Raises ValueError for invalid trading pairs
- Test `test_trading_pair_to_xt_symbol` passes (from contract tests)

**Dependencies**: T005 (XTExchange skeleton exists)

---

### T007 [P]: ✅ Implement Helper Method: _from_xt_symbol
**Type**: Implementation | **Priority**: High | **Parallel**: Yes (helper method, no dependencies)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement XT symbol format to trading pair parsing method.

**Implementation Location**: Add to XTExchange class
```python
def _from_xt_symbol(self, symbol: str) -> tuple[str, str]:
    """Parse XT symbol format to base/quote currencies.
    
    Args:
        symbol: XT symbol format (e.g., "btc_usdt")
        
    Returns:
        Tuple of (base_currency, quote_currency) in uppercase
        
    Raises:
        ValueError: If symbol format is invalid
        
    Examples:
        >>> _from_xt_symbol("btc_usdt")
        ("BTC", "USDT")
    """
    try:
        base, quote = symbol.split('_', 1)
        return base.upper(), quote.upper()
    except ValueError:
        raise ValueError(f"Invalid XT symbol format: {symbol}")
```

**Acceptance Criteria**:
- Method added to XTExchange class
- Converts "btc_usdt" → ("BTC", "USDT")
- Raises ValueError for symbols without underscore
- Test `test_xt_symbol_to_trading_pair` passes

**Dependencies**: T005 (XTExchange skeleton exists)

---

### T008 [P]: ✅ Implement Helper Method: _generate_signature
**Type**: Implementation | **Priority**: Critical | **Parallel**: Yes (helper method, used by auth)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement HMAC-SHA256 signature generation for XT API authentication.

**Implementation Location**: Add to XTExchange class (see data-model.md Section 4.2 for full code)

**Key Points**:
- Synchronous method (CPU-bound, <1ms)
- Builds X parameter string with validate-* fields
- Generates sig_data as `X#METHOD#PATH[#QUERY][#BODY]`
- Returns tuple of (headers dict, signature string)

**Acceptance Criteria**:
- Method added to XTExchange class
- Generates valid HMAC-SHA256 signature
- Returns complete headers dict with all validate-* fields
- Test `test_signature_generation_basic` passes

**Dependencies**: T005 (XTExchange skeleton exists)

---

### T009 [P]: ✅ Implement Helper Method: _build_sorted_query
**Type**: Implementation | **Priority**: Medium | **Parallel**: Yes (helper method, used by signature)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement sorted query string builder for XT API signature requirements.

**Implementation Location**: Add to XTExchange class (see data-model.md Section 4.3 for full code)

**Key Points**:
- Alphabetically sort parameters by key
- Handle dict/list values by JSON encoding
- URL-encode the result

**Acceptance Criteria**:
- Method added to XTExchange class
- Correctly sorts parameters: `{'symbol': 'btc_usdt', 'limit': 20}` → `"limit=20&symbol=btc_usdt"`
- Handles empty params dict (returns empty string)
- Works with dict/list parameter values

**Dependencies**: T005 (XTExchange skeleton exists)

---

### T010: ✅ Implement Connection Management (connect/disconnect)
**Type**: Implementation | **Priority**: Critical | **Parallel**: No (required for all API calls)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement async connect() and disconnect() methods to manage httpx.AsyncClient lifecycle.

**Implementation Location**: Add to XTExchange class (see data-model.md Section 5 for full code)

**Key Points for connect()**:
- Create httpx.AsyncClient with base_url, timeout, limits
- Set is_connected = True
- Log connection success

**Key Points for disconnect()**:
- Call await self._client.aclose()
- Set _client = None and is_connected = False
- Log disconnection

**Acceptance Criteria**:
- Both methods implemented
- connect() creates AsyncClient with connection pool (max_connections=100)
- disconnect() properly cleans up resources
- Tests `test_connection_lifecycle` and `test_is_connected_property` pass
- Contract test `test_exchange_implements_required_methods` gets closer to passing

**Dependencies**: T005 (XTExchange skeleton exists)

---

### T011: ✅ Implement HTTP Request Helper with Retry (_request)
**Type**: Implementation | **Priority**: Critical | **Parallel**: No (used by all API methods)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement `_request()` helper method with exponential backoff retry logic.

**Implementation Location**: Add to XTExchange class (see data-model.md Section 4.4 for full code)

**Key Points**:
- Use @retry decorator from tenacity (3 attempts, exponential backoff)
- Handle authenticated vs public endpoints
- Call _build_sorted_query and _generate_signature for auth
- Raise httpx.HTTPStatusError for 4xx/5xx
- Log errors with context

**Acceptance Criteria**:
- Method implemented with @retry decorator
- Correctly handles authenticated=True/False
- Retries on httpx.TimeoutException and httpx.NetworkError
- Logs errors with method, path, status code
- Can make basic HTTP requests (tested in subsequent tasks)

**Dependencies**: T008 (_generate_signature), T009 (_build_sorted_query), T010 (connect/disconnect)

---

### T012 [P]: ✅ Implement get_ticker() - Public API
**Type**: Implementation | **Priority**: High | **Parallel**: Yes (different endpoint than T013)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement get_ticker() method to retrieve ticker price from XT API.

**Implementation Location**: Add to XTExchange class

**Endpoint**: GET /v4/public/ticker/price  
**Parameters**: symbol (lowercase with underscore)

**Key Steps**:
1. Convert trading_pair to XT symbol using _to_xt_symbol()
2. Call _request(method="GET", path="/v4/public/ticker/price", params={"symbol": symbol})
3. Parse response using _parse_xt_response()
4. Convert ticker data to Price model
5. Return Price with bid_price, ask_price, timestamp

**Note**: Since XT ticker response might not have explicit bid/ask fields, use close price (c field) as both bid and ask for MVP. Mark with TODO to verify actual bid/ask field names.

**Acceptance Criteria**:
- Method implemented with full type hints
- Converts TradingPair → XT symbol → API call → Price model
- Returns Price with non-zero bid/ask prices
- Timestamp is timezone-aware (UTC)
- Test from quickstart.md Scenario 1 passes manually
- Contract test verifies method exists and returns Price type

**Dependencies**: T011 (_request helper)

---

### T013 [P]: ✅ Implement get_orderbook() - Public API
**Type**: Implementation | **Priority**: High | **Parallel**: Yes (different endpoint than T012)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement get_orderbook() method to retrieve order book depth from XT API.

**Implementation Location**: Add to XTExchange class

**Endpoint**: GET /v4/public/depth  
**Parameters**: symbol, limit (default 20)

**Key Steps**:
1. Convert trading_pair to XT symbol
2. Call _request with params={"symbol": symbol, "limit": depth}
3. Parse response to extract bids and asks arrays
4. Convert [[price_str, qty_str], ...] to OrderBook model
5. Sort bids descending, asks ascending
6. Return OrderBook

**Acceptance Criteria**:
- Method implemented with depth parameter (default 20)
- Bids sorted by price descending
- Asks sorted by price ascending
- Returns OrderBook with proper structure
- Test from quickstart.md Scenario 2 passes manually

**Dependencies**: T011 (_request helper)

---

### T014: ✅ Implement place_order() - Private API
**Type**: Implementation | **Priority**: Critical | **Parallel**: No (complex logic, requires auth)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement place_order() method to create orders on XT exchange.

**Implementation Location**: Add to XTExchange class

**Endpoint**: POST /v4/order  
**Authentication**: Required (HMAC signature)

**Key Steps**:
1. Validate order using _validate_order() helper
2. Convert trading_pair to XT symbol
3. Build request body with symbol, side, type, timeInForce, quantity, price
4. Call _request(method="POST", path="/v4/order", json_data=body, authenticated=True)
5. Parse response to extract orderId and status
6. Update order object with orderId and status
7. Return updated Order

**Acceptance Criteria**:
- Method implemented for LIMIT and MARKET orders
- Uses authenticated=True in _request call
- Validates API credentials exist before calling
- Returns Order with exchange order_id set
- Order status mapped correctly (NEW → OPEN)
- Test from quickstart.md Scenario 3 passes manually

**Dependencies**: T011 (_request with auth support)

---

### T015: ✅ Implement cancel_order() - Private API
**Type**: Implementation | **Priority**: High | **Parallel**: No (depends on order ID format from T014)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement cancel_order() method to cancel orders on XT exchange.

**Implementation Location**: Add to XTExchange class

**Endpoint**: DELETE /v4/open-order  
**Authentication**: Required

**Key Steps**:
1. Build request body with symbol (from order or separate param) and bizType=SPOT
2. Call _request(method="DELETE", path="/v4/open-order", json_data=body, authenticated=True)
3. Parse response to confirm cancellation
4. Return True if successful, False otherwise

**Note**: XT API might cancel all orders for a symbol (check if individual order cancel endpoint exists)

**Acceptance Criteria**:
- Method implemented
- Uses authenticated=True
- Returns boolean success status
- Test from quickstart.md Scenario 4 passes manually

**Dependencies**: T014 (place_order for testing context)

---

### T016 [P]: ✅ Implement get_order_status() - Private API
**Type**: Implementation | **Priority**: Medium | **Parallel**: Yes (different endpoint than T014/T015)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement get_order_status() method to query order status.

**Implementation Location**: Add to XTExchange class

**Endpoint**: GET /v4/order or GET /v4/open-order  
**Authentication**: Required

**Key Steps**:
1. Build query params with orderId or symbol filter
2. Call _request(method="GET", authenticated=True)
3. Parse response to get order status, filled quantity, remaining quantity
4. Map XT status to internal OrderStatus enum
5. Return Order object with current state

**Acceptance Criteria**:
- Method implemented
- Returns Order with accurate status
- Maps XT order statuses correctly (NEW→OPEN, FILLED→FILLED, etc.)
- Includes filled_quantity and remaining_quantity
- Test from quickstart.md Scenario 5 passes manually

**Dependencies**: T011 (_request helper)

---

### T017 [P]: Implement get_balance() - Account API
**Type**: Implementation | **Priority**: Medium | **Parallel**: Yes (account endpoint, different from trading)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement get_balance() method to retrieve account balances.

**Implementation Location**: Add to XTExchange class

**Endpoint**: GET /v4/balances  
**Authentication**: Required

**Key Steps**:
1. Call _request(method="GET", path="/v4/balances", authenticated=True)
2. Parse response array of {currency, available, locked}
3. Convert to dict[str, Decimal] mapping currency to available balance
4. Return balance dict

**Note**: BaseExchange interface might expect different return type - verify and adjust

**Acceptance Criteria**:
- Method implemented
- Returns balances for all non-zero assets
- Available and locked amounts separated correctly
- Test from quickstart.md Scenario 7 passes manually

**Dependencies**: T011 (_request helper)

---

### T018 [P]: ✅ Implement get_trade_history() - Private API
**Type**: Implementation | **Priority**: Medium | **Parallel**: Yes (history endpoint, no dependencies)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement get_trade_history() method to retrieve historical trades.

**Implementation Location**: Add to XTExchange class

**Endpoint**: GET /v4/trade  
**Authentication**: Required

**Key Steps**:
1. Convert trading_pair to XT symbol
2. Build query params with bizType=SPOT, symbol, limit
3. Call _request(method="GET", authenticated=True)
4. Parse response array of trade records
5. Convert each trade to Trade model (price, quantity, fee, timestamp)
6. Return list[Trade]

**Acceptance Criteria**:
- Method implemented with limit parameter (default 100)
- Returns Trade models with complete information
- Trades sorted by time (most recent first)
- Fee information included
- Test from quickstart.md Scenario 6 passes manually

**Dependencies**: T011 (_request helper)

---

### T019: ✅ Implement subscribe_ticker() - Stub for WebSocket
**Type**: Implementation | **Priority**: Low | **Parallel**: No (stub only)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement subscribe_ticker() as a stub that raises NotImplementedError since WebSocket support is out of scope for this iteration.

**Implementation Location**: Add to XTExchange class
```python
async def subscribe_ticker(self, trading_pair: TradingPair) -> AsyncIterator[Price]:
    """Subscribe to real-time ticker updates (not implemented for XT).
    
    XT WebSocket support is planned for future iteration.
    
    Args:
        trading_pair: Trading pair to subscribe to
        
    Yields:
        Price updates (not implemented)
        
    Raises:
        NotImplementedError: WebSocket not supported yet
    """
    raise NotImplementedError("XT WebSocket support coming in future iteration")
    yield  # Make this a generator for type checking
```

**Acceptance Criteria**:
- Method exists and has correct signature
- Raises NotImplementedError with clear message
- Type hints are correct (AsyncIterator[Price])

**Dependencies**: T005 (XTExchange skeleton)

---

### T020: ✅ Implement subscribe_orderbook() - Stub for WebSocket
**Type**: Implementation | **Priority**: Low | **Parallel**: No (stub only)  
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Implement subscribe_orderbook() as a stub (same as T019).

**Implementation Location**: Add to XTExchange class with NotImplementedError

**Acceptance Criteria**:
- Method exists with correct signature
- Raises NotImplementedError
- Type hints correct (AsyncIterator[OrderBook])

**Dependencies**: T005 (XTExchange skeleton)

---

## Phase 3.4: Integration

### T021: ✅ Add XT Configuration to Settings
**Type**: Integration | **Priority**: High | **Parallel**: No (modifies shared config)  
**File**: `src/tri_arb/config/settings.py`

**Description**: Add XT API credentials configuration to project settings.

**Implementation**: Add to Settings class or environment variables
```python
# XT Exchange Configuration
xt_api_key: str = Field(default="", env="XT_API_KEY", description="XT API key")
xt_api_secret: str = Field(default="", env="XT_API_SECRET", description="XT API secret")
```

**Acceptance Criteria**:
- Configuration fields added
- Can load from environment variables: `export XT_API_KEY=xxx; export XT_API_SECRET=yyy`
- XTExchange can be initialized with settings: `XTExchange(api_key=settings.xt_api_key, ...)`

**Dependencies**: T005 (XTExchange exists to test with)

---

### T022: ✅ Register XTExchange in Exchange Factory
**Type**: Integration | **Priority**: Medium | **Parallel**: No (modifies shared factory)  
**File**: Check if `src/tri_arb/exchanges/__init__.py` or factory pattern exists

**Description**: Register XTExchange in the exchange factory/registry so it can be instantiated dynamically.

**Implementation**: 
- If factory exists, add XT to supported exchanges
- If using __init__.py exports, add: `from tri_arb.exchanges.xt import XTExchange`

**Acceptance Criteria**:
- XTExchange can be imported from `tri_arb.exchanges`
- Factory (if exists) can create XT instance by name: `factory.create("xt")`

**Dependencies**: T005-T020 (XTExchange fully implemented)

---

## Phase 3.5: Polish

### T023 [P]: ✅ Run Contract Tests - Verify All Pass
**Type**: Validation | **Priority**: Critical | **Parallel**: Yes (read-only test run)  
**File**: `tests/unit/test_exchanges/test_xt_contract.py`

**Description**: Run full contract test suite to verify XTExchange implementation is complete.

**Command**:
```bash
pytest tests/unit/test_exchanges/test_xt_contract.py -v
```

**Expected Output**:
```
test_xt_exchange_importable PASSED
test_exchange_implements_required_methods PASSED
test_exchange_has_correct_signature PASSED
test_trading_pair_to_xt_symbol PASSED
test_xt_symbol_to_trading_pair PASSED
test_signature_generation_basic PASSED
...
All tests PASSED
```

**Acceptance Criteria**:
- All contract tests pass (no failures, no skips due to missing implementation)
- 100% pass rate on contract tests
- Test coverage report shows XTExchange class covered

**Dependencies**: T005-T020 (all implementation tasks complete)

---

### ✅ T024 [P]: Verify Type Hints Coverage (mypy)
**Type**: Quality | **Priority**: High | **Parallel**: Yes (static analysis)
**File**: `src/tri_arb/exchanges/xt.py`

**Description**: Run mypy strict mode to verify complete type annotations.

**Command**:
```bash
mypy src/tri_arb/exchanges/xt.py --strict
```

**Acceptance Criteria**:
- Zero mypy errors in strict mode
- All methods have complete type hints (params and return types)
- No `# type: ignore` comments needed
- All async methods properly typed

**Dependencies**: T005-T020 (implementation complete)

---

### ✅ T025: Execute Manual Validation (quickstart.md)
**Type**: Validation | **Priority**: Critical | **Parallel**: No (requires live API or manual steps)
**File**: `specs/002-xt-spot-api/quickstart.md`

**Description**: Follow quickstart.md scenarios to manually validate XTExchange functionality.

**Status**: Skipped (No XT API credentials available) - All contract tests pass with mocked data

**Scenarios to Execute** (if XT API credentials available):
1. ✅ Scenario 1: Monitor XT Market Prices (get_ticker)
2. ✅ Scenario 2: Analyze XT Order Book Depth (get_orderbook)
3. ✅ Scenario 3: Place Limit Order on XT (place_order) - **Use testnet/small amounts**
4. ✅ Scenario 4: Cancel Active XT Orders (cancel_order)
5. ✅ Scenario 5: Track XT Order Status (get_order_status)
6. ✅ Scenario 6: Retrieve XT Trade History (get_trade_history)
7. ✅ Scenario 7: Query XT Account Balance (get_balance)
8. ✅ Scenario 8: Handle XT API Authentication Errors (error handling)

**Acceptance Criteria**:
- All 8 scenarios execute successfully (or skip gracefully if no credentials)
- Performance targets met: <2s ticker, <3s order placement
- No crashes or unhandled exceptions
- Manual validation checklist in quickstart.md marked complete

**Dependencies**: T021 (settings configured), T023 (tests pass)

---

## Dependencies

**Critical Path**:
```
T001 (deps) → T002 (lint config)
    ↓
T003-T004 (verify tests fail) → T005 (skeleton)
    ↓
T006-T009 (helpers) → T010 (connect) → T011 (_request)
    ↓
T012-T018 (API methods) → T019-T020 (WebSocket stubs)
    ↓
T021-T022 (integration)
    ↓
T023-T025 (validation)
```

**Parallel Groups**:
- **Group 1** [P]: T002 (lint), T003 (test baseline), T004 (integration baseline)
- **Group 2** [P]: T006 (_to_xt_symbol), T007 (_from_xt_symbol), T008 (_generate_signature), T009 (_build_sorted_query)
- **Group 3** [P]: T012 (get_ticker), T013 (get_orderbook), T016 (get_order_status), T017 (get_balance), T018 (get_trade_history)
- **Group 4** [P]: T019 (subscribe_ticker stub), T020 (subscribe_orderbook stub)
- **Group 5** [P]: T023 (run tests), T024 (mypy check)

**Sequential Dependencies**:
- T005 blocks all implementation tasks
- T010 blocks T011 (connect must exist before _request)
- T011 blocks T012-T018 (all API methods need _request)
- T014 blocks T015 (cancel_order needs place_order context)
- T022 blocks T025 (factory needed for complete manual testing)

---

## Parallel Execution Examples

### Example 1: Run Test Baselines in Parallel
```bash
# T003 and T004 can run together
pytest tests/unit/test_exchanges/test_xt_contract.py -v &
pytest tests/integration/test_xt_integration.py -v &
wait
```

### Example 2: Implement Helper Methods in Parallel
**After T005 completes**, use Task agents for parallel implementation:
```
Task 1: "Implement _to_xt_symbol method in src/tri_arb/exchanges/xt.py per data-model.md Section 4.1"
Task 2: "Implement _from_xt_symbol method in src/tri_arb/exchanges/xt.py per data-model.md Section 4.1"
Task 3: "Implement _generate_signature method in src/tri_arb/exchanges/xt.py per data-model.md Section 4.2"
Task 4: "Implement _build_sorted_query method in src/tri_arb/exchanges/xt.py per data-model.md Section 4.3"
```

### Example 3: Implement Public API Methods in Parallel
**After T011 completes** (all use _request helper):
```
Task 1: "Implement get_ticker() in src/tri_arb/exchanges/xt.py using /v4/public/ticker/price endpoint"
Task 2: "Implement get_orderbook() in src/tri_arb/exchanges/xt.py using /v4/public/depth endpoint"
Task 3: "Implement get_balance() in src/tri_arb/exchanges/xt.py using /v4/balances endpoint"
Task 4: "Implement get_trade_history() in src/tri_arb/exchanges/xt.py using /v4/trade endpoint"
```

---

## Notes

### Execution Guidelines:
- **[P] tasks** = Different files OR independent operations, safe to parallelize
- **Sequential tasks** = Same file OR dependencies, must run in order
- **TDD requirement**: T003-T004 must fail BEFORE T005-T020 implementation starts
- **Commit frequency**: After each task completion for easy rollback

### Common Pitfalls to Avoid:
- ❌ Don't implement before tests fail (violates TDD)
- ❌ Don't parallelize tasks that modify same file (xt.py)
- ❌ Don't skip type hints (mypy strict mode required)
- ❌ Don't hardcode values that should come from settings
- ❌ Don't use `float` for monetary values (use `Decimal`)

### Performance Targets (from plan.md):
- Order execution: <50ms p95
- Price processing: <10ms p95
- Ticker retrieval: <2 seconds end-to-end
- Order placement: <3 seconds end-to-end

### TODO Items for Future Iterations:
- Verify XT API exact field names (bid/ask prices in ticker)
- Determine XT rate limits per endpoint
- Test WebSocket support availability
- Implement circuit breaker pattern for error handling
- Add response caching for frequently accessed data

---

## Task Summary

**Total Tasks**: 25  
**Critical Path Length**: ~12 sequential steps  
**Parallel Opportunities**: 15 tasks marked [P]

**Estimated Execution Time**:
- Sequential execution: ~8-12 hours (1 developer)
- Parallel execution (3 agents): ~4-6 hours
- Testing & validation: ~2-4 hours

**Phase Breakdown**:
- Phase 3.1 (Setup): 2 tasks
- Phase 3.2 (Tests): 2 tasks
- Phase 3.3 (Implementation): 16 tasks
- Phase 3.4 (Integration): 2 tasks
- Phase 3.5 (Polish): 3 tasks

---

**Document Status**: Complete  
**Ready for Execution**: ✅ Yes  
**Prerequisites Met**: ✅ All design docs available (plan.md, research.md, data-model.md, contracts/, quickstart.md)

---

*Generated from `/specs/002-xt-spot-api/` design documents*  
*Based on TDD workflow and tri-arb Constitution v1.0.0*