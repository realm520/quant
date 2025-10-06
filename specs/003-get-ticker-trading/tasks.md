# Tasks: Get All Market Tickers (Feature 003)

**Input**: Design documents from `/specs/003-get-ticker-trading/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/, quickstart.md

## Execution Flow (main)
```
1. Load plan.md ✓ - Tech stack: Python 3.11+, httpx, pydantic, pytest
2. Load design documents ✓:
   - data-model.md: Interface signature change (no new models)
   - contracts/: BaseExchange.get_ticker() contract
   - research.md: API design, XT batch API, performance strategy
3. Generate tasks by category:
   - Setup: Dependencies (no new deps), linting
   - Tests: Contract tests (BaseExchange, XTExchange), integration tests
   - Core: Interface update (base.py), batch implementation (xt.py)
   - Integration: Performance logging, partial failure handling
   - Polish: Documentation, performance validation
4. Task rules applied:
   - Contract test files = [P] (independent)
   - Interface update + implementation = sequential (same repo)
   - Documentation tasks = [P] (different files)
5. Tasks numbered T001-T020
6. Dependencies mapped (TDD order)
7. Parallel examples generated
8. Validation complete ✓
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- All paths relative to repository root

## Path Conventions
Project structure (from plan.md):
- **Source**: `src/tri_arb/exchanges/` (base.py, xt.py)
- **Tests**: `tests/unit/test_exchanges/`, `tests/integration/`
- **Docs**: `specs/003-get-ticker-trading/`, `CLAUDE.md`

---

## Phase 3.1: Setup & Prerequisites

- [ ] **T001** Verify Python 3.11+ and all dependencies installed
  - Check: `python --version` (≥3.11), `uv pip list` includes httpx, pydantic, pytest, pytest-asyncio, respx
  - No new dependencies required (using existing stack)
  - **Exit Criteria**: All dependencies present, `uv run pytest --version` succeeds

- [ ] **T002** [P] Run linting and type checking on existing exchange code
  - Commands: `uv run ruff check src/tri_arb/exchanges/`, `uv run mypy src/tri_arb/exchanges/ --strict`
  - **Exit Criteria**: Zero ruff errors, mypy passes (baseline before changes)

---

## Phase 3.2: Tests First (TDD) ⚠️ **MUST COMPLETE BEFORE Phase 3.3**

**CRITICAL**: These tests MUST be written and MUST FAIL before ANY implementation begins.

### Contract Tests (Parallel Execution)

- [ ] **T003** [P] Write BaseExchange.get_ticker() contract tests
  - **File**: `tests/unit/test_exchanges/test_base_contract.py`
  - **Contract Reference**: `specs/003-get-ticker-trading/contracts/test_get_ticker_contract.py` (lines 42-135)
  - **Test Cases**:
    1. `test_batch_query_unsupported_raises_not_implemented()` - Verify default BaseExchange raises NotImplementedError for `trading_pair=None`
    2. `test_return_type_annotation()` - Verify signature has `Optional[TradingPair]` parameter and `Union[Price, List[Price]]` return
  - **Expected Outcome**: Tests MUST FAIL (BaseExchange.get_ticker not yet modified)
  - **Validation**: `uv run pytest tests/unit/test_exchanges/test_base_contract.py -v` shows 2 failures

- [ ] **T004** [P] Write XTExchange single ticker contract tests (backward compatibility)
  - **File**: `tests/unit/test_exchanges/test_xt_contract.py`
  - **Contract Reference**: `specs/003-get-ticker-trading/contracts/test_get_ticker_contract.py` (lines 30-92)
  - **Test Cases**:
    1. `test_single_ticker_returns_price_object()` - trading_pair → Price (not list)
    2. `test_single_ticker_price_data_valid()` - Validate bid/ask/volume constraints
    3. `test_single_ticker_performance()` - <50ms p95 benchmark
  - **Mock Strategy**: Use respx to mock XT API `/v4/public/ticker/book?symbol=btc_usdt`
  - **Expected Outcome**: Tests MUST PASS (single ticker already implemented in Feature 002)
  - **Validation**: `uv run pytest tests/unit/test_exchanges/test_xt_contract.py::test_single_ticker* -v` shows 3 passes

- [ ] **T005** [P] Write XTExchange batch ticker contract tests
  - **File**: `tests/unit/test_exchanges/test_xt_contract.py` (add to existing file)
  - **Contract Reference**: `specs/003-get-ticker-trading/contracts/test_get_ticker_contract.py` (lines 97-176)
  - **Test Cases**:
    1. `test_batch_ticker_returns_list()` - trading_pair=None → List[Price]
    2. `test_batch_ticker_no_duplicates()` - No duplicate trading pairs
    3. `test_batch_ticker_each_price_valid()` - Validate all Price objects
    4. `test_batch_ticker_performance()` - <1000ms p95 benchmark
    5. `test_batch_ticker_scalability()` - Handle ≥500 trading pairs
  - **Mock Strategy**: Use respx to mock `/v4/public/ticker/book` (no params) with array response
  - **Expected Outcome**: Tests MUST FAIL (batch ticker not yet implemented)
  - **Validation**: `uv run pytest tests/unit/test_exchanges/test_xt_contract.py::test_batch_ticker* -v` shows 5 failures

- [ ] **T006** [P] Write partial failure contract tests
  - **File**: `tests/unit/test_exchanges/test_xt_contract.py` (add to existing file)
  - **Contract Reference**: `specs/003-get-ticker-trading/contracts/test_get_ticker_contract.py` (lines 231-264)
  - **Test Cases**:
    1. `test_batch_partial_failure_returns_success_subset()` - Some failed → return successful
    2. `test_batch_all_failures_returns_empty_list()` - All failed → return []
  - **Mock Strategy**: Use monkeypatch to inject parse failures
  - **Expected Outcome**: Tests MUST FAIL (partial failure handling not yet implemented)
  - **Validation**: `uv run pytest tests/unit/test_exchanges/test_xt_contract.py::test_batch_partial* -v` shows 2 failures

### Integration Tests (Parallel Execution)

- [ ] **T007** [P] Write XT batch ticker integration test (real API)
  - **File**: `tests/integration/test_xt_integration.py` (add to existing file)
  - **Scenario Reference**: `specs/003-get-ticker-trading/quickstart.md` (lines 61-86)
  - **Test Case**: `test_get_all_tickers_real_api()`
    - Connect to XT Exchange
    - Call `get_ticker(None)`
    - Verify: List[Price] returned, ≥10 markets, all valid, <1s response time
  - **Requirements**: `XT_API_KEY` and `XT_API_SECRET` environment variables
  - **Markers**: `@pytest.mark.integration`, `@pytest.mark.skipif(not has_xt_credentials)`
  - **Expected Outcome**: Test MUST FAIL (batch ticker not implemented)
  - **Validation**: `uv run pytest tests/integration/test_xt_integration.py::test_get_all_tickers_real_api --run-integration -v` shows 1 failure

---

## Phase 3.3: Core Implementation (ONLY after tests are failing)

**Prerequisite Gate**: ALL tests in Phase 3.2 (T003-T007) must be written and failing.

### Interface Updates

- [ ] **T008** Update BaseExchange.get_ticker() signature
  - **File**: `src/tri_arb/exchanges/base.py`
  - **Changes**:
    1. Import: Add `from typing import Optional, Union, List`
    2. Signature: Change parameter to `trading_pair: Optional[TradingPair] = None`
    3. Return type: Change to `Union[Price, List[Price]]`
    4. Docstring: Update with batch query behavior (see `data-model.md` lines 20-40)
    5. Default implementation: Add `if trading_pair is None: raise NotImplementedError(...)`
  - **Reference**: `specs/003-get-ticker-trading/research.md` (lines 108-123 for error message)
  - **Validation**: `uv run pytest tests/unit/test_exchanges/test_base_contract.py -v` → T003 tests PASS
  - **Type Check**: `uv run mypy src/tri_arb/exchanges/base.py --strict` → No errors

### XTExchange Batch Implementation

- [ ] **T009** Implement XTExchange._parse_ticker_to_price() helper
  - **File**: `src/tri_arb/exchanges/xt.py` (add new private method)
  - **Purpose**: Parse single ticker dict → Price object (extract from existing get_ticker logic)
  - **Reference**: `specs/003-get-ticker-trading/data-model.md` (lines 155-175 for parsing logic)
  - **Method Signature**:
    ```python
    def _parse_ticker_to_price(
        self,
        ticker_data: dict[str, Any],
        trading_pair: Optional[TradingPair] = None
    ) -> Price:
        """Parse XT ticker data to Price object.

        Args:
            ticker_data: Raw XT ticker dict (e.g., {"s": "btc_usdt", "c": "50000", ...})
            trading_pair: Pre-created TradingPair or None (create from symbol)

        Returns:
            Price object with bid/ask/volume data

        Raises:
            ValueError: If ticker_data invalid or missing required fields
        """
    ```
  - **Implementation**:
    - Extract symbol, close price, volume from ticker_data
    - Create TradingPair if not provided (use `_from_xt_symbol` + `_create_minimal_trading_pair`)
    - Calculate bid/ask with small spread (existing logic from get_ticker)
    - Return Price object
  - **Validation**: Unit test this helper (optional, covered by contract tests)

- [ ] **T010** Implement XTExchange batch ticker query logic
  - **File**: `src/tri_arb/exchanges/xt.py` (modify get_ticker method)
  - **Reference**: `specs/003-get-ticker-trading/research.md` (lines 50-72 for implementation pattern)
  - **Changes**:
    1. Add None check at beginning: `if trading_pair is None:`
    2. Batch query path:
       - Call `_request()` with empty params
       - Parse response array: `result = data.get("result", [])`
       - Loop through `result`, parse each ticker with try/except
       - Collect successes in `prices` list, log failures
       - Return `prices`
    3. Single query path: Keep existing logic (already working)
  - **Partial Failure Handling** (FR-008, FR-012):
    ```python
    prices = []
    failed_markets = []

    for ticker_data in result:
        try:
            price = self._parse_ticker_to_price(ticker_data)
            prices.append(price)
        except Exception as e:
            symbol = ticker_data.get("s", "unknown")
            failed_markets.append(symbol)
            logger.warning(
                "Ticker parse failed",
                symbol=symbol,
                error=str(e),
                error_type=type(e).__name__,
            )

    if failed_markets:
        logger.info(
            "Batch ticker query completed with partial failures",
            total_markets=len(result),
            successful=len(prices),
            failed=len(failed_markets),
            failed_symbols=failed_markets[:10],
        )

    return prices
    ```
  - **Validation**: `uv run pytest tests/unit/test_exchanges/test_xt_contract.py::test_batch* -v` → T005 tests PASS

- [ ] **T011** Add performance logging for batch queries
  - **File**: `src/tri_arb/exchanges/xt.py` (add to get_ticker batch path)
  - **Requirement**: NFR-005 - Log performance warning if >1s
  - **Implementation**:
    ```python
    import time

    # In batch query path, after if trading_pair is None:
    start_time = time.perf_counter()

    # ... batch query logic ...

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    if elapsed_ms > 1000:
        logger.warning(
            "Batch ticker query exceeded performance target",
            elapsed_ms=elapsed_ms,
            target_ms=1000,
            market_count=len(prices),
        )
    else:
        logger.debug(
            "Batch ticker query completed",
            elapsed_ms=elapsed_ms,
            market_count=len(prices),
        )
    ```
  - **Validation**: Check logs during integration test run

- [ ] **T012** Implement _create_minimal_trading_pair() helper
  - **File**: `src/tri_arb/exchanges/xt.py` (add new private method)
  - **Reference**: `specs/003-get-ticker-trading/data-model.md` (lines 143-156)
  - **Purpose**: Create minimal TradingPair for batch query performance
  - **Method Signature**:
    ```python
    def _create_minimal_trading_pair(
        self,
        base: str,
        quote: str
    ) -> TradingPair:
        """Create minimal TradingPair for batch query results."""
        return TradingPair(
            base_currency=base,
            quote_currency=quote,
            exchange=self.name,
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1000000"),
            price_precision=8,
            quantity_precision=8,
        )
    ```
  - **Validation**: Used by _parse_ticker_to_price(), tested via contract tests

---

## Phase 3.4: Integration & Error Handling

- [ ] **T013** Verify backward compatibility with existing code
  - **Test**: Run ALL existing XTExchange tests (not just new batch tests)
  - **Command**: `uv run pytest tests/unit/test_exchanges/test_xt_contract.py -v`
  - **Expected**: All tests PASS (single ticker tests + new batch ticker tests)
  - **Validation**: Confirm no regressions in Feature 002 functionality

- [ ] **T014** Run integration tests with real XT API
  - **Setup**: Export `XT_API_KEY` and `XT_API_SECRET`
  - **Command**: `uv run pytest tests/integration/test_xt_integration.py --run-integration -v`
  - **Expected**: T007 integration test PASS, <1s response time
  - **Validation**: Review logs for performance metrics and any partial failures

---

## Phase 3.5: Polish & Documentation

- [ ] **T015** [P] Update BaseExchange.get_ticker() docstring
  - **File**: `src/tri_arb/exchanges/base.py`
  - **Requirement**: FR-005 - Document optional parameter behavior
  - **Content**: See `data-model.md` lines 26-40 for complete docstring
  - **Include**:
    - Parameter description for `Optional[TradingPair]`
    - Return type explanation (Union behavior)
    - Examples of single vs batch query
    - All exception types (NotImplementedError, ExchangeConnectionError, etc.)
  - **Validation**: `uv run ruff check src/tri_arb/exchanges/base.py` → No D* warnings

- [ ] **T016** [P] Update XTExchange.get_ticker() docstring
  - **File**: `src/tri_arb/exchanges/xt.py`
  - **Content**: Explain XT-specific batch query behavior
  - **Include**:
    - XT API endpoint used (`/v4/public/ticker/book`)
    - Response format differences (single vs batch)
    - Performance characteristics (<1s for 500+ pairs)
    - Partial failure behavior
  - **Validation**: `uv run ruff check src/tri_arb/exchanges/xt.py` → No D* warnings

- [ ] **T017** [P] Update quickstart.md with tested examples
  - **File**: `specs/003-get-ticker-trading/quickstart.md`
  - **Action**: Verify all code examples work with implementation
  - **Test**: Manually run examples from quickstart.md sections 1-5
  - **Expected**: All examples execute without errors, output matches expected
  - **Update**: Fix any discrepancies between examples and actual API behavior

- [ ] **T018** Run performance benchmarks
  - **Reference**: `specs/003-get-ticker-trading/quickstart.md` (lines 88-113 for benchmark script)
  - **Test Cases**:
    1. Single ticker query: 10 iterations, measure p95 latency (<50ms target)
    2. Batch ticker query: 10 iterations, measure p95 latency (<1000ms target)
  - **Command**: `uv run pytest tests/unit/test_exchanges/test_xt_contract.py::test_*_performance --benchmark-only -v`
  - **Validation**: p95 metrics meet or exceed targets
  - **Deliverable**: Performance report (log output or summary comment)

- [ ] **T019** Run final type checking and linting
  - **Files**: All modified files in `src/tri_arb/exchanges/`
  - **Commands**:
    - `uv run mypy src/tri_arb/exchanges/ --strict`
    - `uv run ruff check src/tri_arb/exchanges/`
  - **Expected**: Zero mypy errors, zero ruff errors
  - **Fix**: Address any newly introduced issues

- [ ] **T020** Verify all tests pass (full test suite)
  - **Command**: `uv run pytest tests/ -v -m "not integration"` (unit + contract tests)
  - **Expected**: 100% pass rate
  - **Integration**: `uv run pytest tests/integration/ --run-integration -v` (requires credentials)
  - **Deliverable**: Test report confirming all phases complete

---

## Dependencies

### Critical Path (TDD Workflow)
```
T001-T002 (Setup)
   ↓
T003-T007 (Write Failing Tests) [PARALLEL]
   ↓
T008 (BaseExchange Signature) → T003 tests PASS
   ↓
T009-T012 (XTExchange Implementation) → T005-T006 tests PASS
   ↓
T013-T014 (Integration Validation) → T007 test PASS
   ↓
T015-T020 (Polish) [MOSTLY PARALLEL]
```

### Detailed Dependencies
- **T003-T007**: No dependencies (parallel execution)
- **T008**: Depends on T003 (tests must exist to verify fix)
- **T009**: Independent helper (can be parallel with T008 theoretically, but same repo)
- **T010**: Depends on T009 (uses _parse_ticker_to_price helper)
- **T011**: Depends on T010 (adds logging to batch query path)
- **T012**: Independent helper (used by T009)
- **T013**: Depends on T008-T012 (all implementation complete)
- **T014**: Depends on T010-T011 (batch implementation + logging)
- **T015-T017**: Can run in parallel (different files)
- **T018**: Depends on T010-T011 (performance tests need implementation)
- **T019**: Depends on T015-T016 (docstrings affect linting)
- **T020**: Depends on all previous tasks (final validation)

---

## Parallel Execution Examples

### Phase 3.2: Write All Contract Tests in Parallel
```bash
# Launch T003-T006 together (4 test files/sections, independent):
uv run pytest tests/unit/test_exchanges/test_base_contract.py -v &
uv run pytest tests/unit/test_exchanges/test_xt_contract.py::test_single_ticker* -v &
uv run pytest tests/unit/test_exchanges/test_xt_contract.py::test_batch_ticker* -v &
uv run pytest tests/unit/test_exchanges/test_xt_contract.py::test_batch_partial* -v &
wait

# Verify all tests FAIL (as expected in TDD)
```

### Phase 3.5: Documentation Tasks in Parallel
```bash
# Launch T015-T017 together (3 different files):
# Terminal 1:
vim src/tri_arb/exchanges/base.py  # Update docstring (T015)

# Terminal 2:
vim src/tri_arb/exchanges/xt.py  # Update docstring (T016)

# Terminal 3:
python examples/verify_quickstart.py  # Test quickstart examples (T017)
```

---

## Validation Checklist

*GATE: Verify before marking feature complete*

- [x] All contracts have corresponding tests (T003-T006 cover BaseExchange contract)
- [x] All interface changes have tests (get_ticker signature tested)
- [x] All tests written before implementation (T003-T007 before T008-T012)
- [x] Parallel tasks truly independent (T003-T006 different test scopes, T015-T017 different files)
- [x] Each task specifies exact file path (all tasks include file paths)
- [x] No task modifies same file as another [P] task (verified - no conflicts)
- [x] TDD workflow enforced (Phase 3.2 MUST complete before 3.3)
- [x] Performance targets explicit (T018 benchmarks)
- [x] Backward compatibility verified (T013)
- [x] Documentation updated (T015-T017)

---

## Notes

### Implementation Tips
1. **TDD Discipline**: Do NOT skip Phase 3.2. Tests MUST fail first.
2. **Performance Focus**: Monitor `elapsed_ms` in logs during T014.
3. **Partial Failures**: Test T006 carefully - common edge case in production.
4. **Type Safety**: Use mypy after EVERY implementation task (T008-T012).
5. **Commit Frequently**: Commit after each task completion with descriptive messages.

### Common Pitfalls
- ❌ Implementing before writing failing tests
- ❌ Forgetting to handle `trading_pair is None` check
- ❌ Not logging partial failures (FR-008, FR-012 requirement)
- ❌ Hardcoding precision values (use minimal defaults from data-model.md)
- ❌ Skipping performance benchmarks (NFR-001 is NON-NEGOTIABLE)

### Success Criteria
- ✅ All contract tests pass (T003-T006)
- ✅ Integration test passes with real XT API (T007)
- ✅ Performance targets met: <50ms single, <1000ms batch (T018)
- ✅ Zero type errors, zero linting errors (T019)
- ✅ Backward compatibility maintained (T013)
- ✅ Documentation complete and accurate (T015-T017)

---

**Estimated Completion Time**: 6-8 hours
- Phase 3.2 (Tests): 2-3 hours
- Phase 3.3 (Implementation): 2-3 hours
- Phase 3.4-3.5 (Integration & Polish): 2 hours

**Ready for Execution**: Yes - All tasks are specific, ordered, and validated.
