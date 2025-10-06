# Implementation Plan: XT Exchange Spot Market Integration

**Branch**: `002-xt-spot-api` | **Date**: 2025-10-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-xt-spot-api/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → ✅ Loaded spec.md with 8 user scenarios, 20+ requirements
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → ✅ All technical decisions made in research.md
3. Fill Constitution Check section
   → ✅ Evaluated against Constitution v1.0.0
4. Evaluate Constitution Check section
   → ✅ PASS - No violations detected
5. Execute Phase 0 → research.md
   → ✅ Completed - 16 sections, all unknowns resolved
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, CLAUDE.md
   → ✅ Completed - All artifacts created
7. Re-evaluate Constitution Check section
   → ✅ PASS - Design complies with all principles
8. Plan Phase 2 → Describe task generation approach
   → ✅ Completed - See Phase 2 section below
9. STOP - Ready for /tasks command
   → ✅ All Phase 0-1 deliverables complete
```

**STATUS**: ✅ Phase 0-1 Complete | Ready for `/tasks` command

## Summary

**Primary Requirement**: Transform synchronous `xt_spot_api.py` (requests-based) into async XT exchange adapter that integrates with tri-arb system's BaseExchange interface.

**Technical Approach** (from research.md):
- **HTTP Client**: httpx (async, already in dependencies, HTTP/2 support)
- **Architecture**: BaseExchange adapter pattern with 10 required methods
- **Authentication**: HMAC-SHA256 with XT's custom validate-* headers
- **Testing**: TDD approach - contract tests created first (must fail until implementation)
- **Performance**: <50ms p95 order execution, <2s ticker retrieval
- **Error Handling**: Exponential backoff retry with tenacity library

## Technical Context

**Language/Version**: Python 3.11+ (project standard)
**Primary Dependencies**: 
- httpx >= 0.27.0 (async HTTP client with connection pooling)
- pydantic >= 2.0 (data validation and settings)
- structlog (structured JSON logging)
- tenacity (retry logic with exponential backoff)
- pytest + pytest-asyncio (testing framework)

**Storage**: N/A (stateless exchange adapter)
**Testing**: pytest + pytest-asyncio + respx (httpx mocking)
**Target Platform**: Linux/macOS (asyncio + uvloop runtime)
**Project Type**: single (Python package with src/ layout)

**Performance Goals**:
- Order execution: <50ms p95 latency
- Price data processing: <10ms p95 latency
- Ticker retrieval: <2 seconds end-to-end
- Order placement: <3 seconds end-to-end
- Concurrent operations: 100 max connections, 20 keepalive

**Constraints**:
- Async/await pattern (no blocking I/O)
- Decimal precision (no float for monetary values)
- UTC timezone-aware timestamps
- BaseExchange interface compliance (10 abstract methods)
- XT API rate limits (TBD - marked as TODO)

**Scale/Scope**:
- 1 new exchange adapter module (xt.py)
- 8 REST API endpoints integration
- 8 user scenarios with test coverage
- 2 test files (contract + integration)
- 4 design documents (research, data-model, contracts, quickstart)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Evaluation Against Constitution v1.0.0

**✅ Type Safety**
- All methods use type hints with Pydantic models
- TradingPair, Price, OrderBook, Order models from tri_arb.core.models
- Decimal type for monetary values (no float)

**✅ Test-Driven Development**
- Contract tests created in test_xt_contract.py (must fail initially)
- Integration tests created in test_xt_integration.py
- Quickstart manual validation guide created

**✅ Performance-First**
- httpx with connection pooling (max_connections=100)
- Async/await pattern throughout
- Performance targets defined: <50ms order execution, <2s ticker

**✅ Observability**
- structlog integration for structured logging
- Error context preservation in exceptions
- Performance metrics tracking capability

**✅ Simplicity**
- Direct BaseExchange implementation (no additional abstractions)
- Synchronous HMAC signature (CPU-bound <1ms, simpler than async)
- Minimal helper methods (2 for trading pair transformation)

**Result**: ✅ PASS - All constitutional principles satisfied

## Project Structure

### Documentation (this feature)
```
specs/002-xt-spot-api/
├── plan.md              # ✅ This file (Phase 0-1 complete)
├── spec.md              # ✅ Feature specification (8 scenarios, requirements)
├── research.md          # ✅ Phase 0 output (16 sections, 400+ lines)
├── data-model.md        # ✅ Phase 1 output (9 sections, class designs)
├── quickstart.md        # ✅ Phase 1 output (8 scenario validation guide)
├── contracts/           # ✅ Phase 1 output (OpenAPI specs)
│   ├── xt-api.yaml      # ✅ 8 endpoints documented
│   └── README.md        # ✅ Usage guide
└── tasks.md             # ⏳ Phase 2 output (/tasks command - NOT YET CREATED)
```

### Source Code (repository root)
```
src/tri_arb/
├── exchanges/
│   ├── __init__.py
│   ├── base.py          # BaseExchange interface
│   ├── binance.py       # Reference implementation
│   ├── okx.py           # Reference implementation
│   └── xt.py            # ⏳ NEW - To be implemented (Phase 3)
│
├── core/
│   └── models.py        # TradingPair, Price, OrderBook, Order
│
└── config/
    ├── settings.py      # ⏳ Add XT_API_KEY, XT_API_SECRET
    └── logging.py       # structlog configuration

tests/
├── unit/
│   └── test_exchanges/
│       ├── test_binance.py
│       ├── test_okx.py
│       └── test_xt_contract.py  # ✅ Created (must fail initially)
│
├── integration/
│   ├── test_binance_integration.py
│   ├── test_okx_integration.py
│   └── test_xt_integration.py   # ✅ Created (requires credentials)
│
└── contract/
    └── test_exchange_interface.py  # Existing BaseExchange tests
```

**Structure Decision**: Single project type (Python package). This is a standard exchange adapter following the existing pattern established by binance.py and okx.py adapters. No frontend, backend, or mobile components required.

## Phase 0: Outline & Research

### Unknowns Extracted and Resolved

**✅ All Technical Context unknowns resolved in research.md**:

1. **HTTP Client Selection** → httpx (Section 1)
   - Decision: httpx (async native, already in dependencies)
   - Alternatives: aiohttp (requires new dependency)

2. **Authentication Implementation** → HMAC-SHA256 (Section 2)
   - Decision: Synchronous signature generation
   - Pattern: XT custom headers (validate-algorithms, validate-appkey, etc.)

3. **Trading Pair Transformation** → Bidirectional helpers (Section 4)
   - Decision: `_to_xt_symbol()` and `_from_xt_symbol()` methods
   - Format: BTC/USDT ↔ btc_usdt

4. **Error Handling Strategy** → tenacity retry (Section 5)
   - Decision: Exponential backoff for network errors
   - Pattern: 3 retries, 1s base delay, 2x multiplier

5. **Performance Optimization** → Connection pooling (Section 6)
   - Decision: httpx.AsyncClient with 100 max connections
   - Rationale: Reuse connections for <50ms order execution

6. **Testing Strategy** → TDD with contract tests (Section 7)
   - Decision: Contract tests must fail initially
   - Pattern: pytest.mark.contract + pytest.mark.skipif

**Output**: ✅ research.md created (16 sections, all NEEDS CLARIFICATION resolved)

## Phase 1: Design & Contracts

*Prerequisites: ✅ research.md complete*

### 1. Entity Extraction → data-model.md

**✅ Completed** - 9 sections documenting:
- XTExchange class design (fields, methods, lifecycle)
- Helper models (XTAuthHeaders, signature generation)
- Trading pair transformation logic
- Validation rules (price precision, lot sizes)
- Error handling patterns (XTAPIError class)

### 2. API Contracts Generation

**✅ Completed** - contracts/xt-api.yaml:
- OpenAPI 3.0 specification
- 8 endpoints documented:
  * GET /v4/public/ticker/price
  * GET /v4/public/depth
  * POST /v4/order
  * DELETE /v4/open-order
  * GET /v4/balances
  * GET /v4/trade
  * GET /v4/open-order
  * GET /v4/order (single order status)

### 3. Contract Tests Generation

**✅ Completed** - tests/unit/test_exchanges/test_xt_contract.py:
- 4 test classes with comprehensive coverage
- TestXTExchangeImportability (must fail until implementation exists)
- TestXTExchangeContract (verify BaseExchange interface compliance)
- TestXTTradingPairTransformation (format conversion logic)
- TestXTSignatureGeneration (authentication mechanism)

**TDD Requirement**: These tests MUST FAIL initially until XTExchange is implemented.

### 4. Test Scenarios Extraction

**✅ Completed** - tests/integration/test_xt_integration.py:
- 2 test classes with 8 scenario mappings
- TestXTIntegration (real API calls, requires credentials)
- TestXTOrderFlow (complete order lifecycle testing)
- Safety warnings and skip conditions for production protection

**✅ Completed** - quickstart.md:
- 8 manual validation scenarios
- Direct mapping to spec.md user scenarios
- Code examples and validation checklists
- Performance target verification steps

### 5. Agent File Update

**✅ Completed** - CLAUDE.md updated:
- Executed `.specify/scripts/bash/update-agent-context.sh claude`
- Added 73-line XT Exchange Integration section
- Documented technical stack, performance requirements, TODO items
- Included common pitfalls and troubleshooting guidance

**Output**: ✅ All Phase 1 deliverables complete

## Phase 2: Task Planning Approach

*This section describes what the /tasks command will do - DO NOT execute during /plan*

### Task Generation Strategy

**Source Documents**:
- Load `.specify/templates/tasks-template.md` as base structure
- Extract from contracts/xt-api.yaml (8 endpoints)
- Extract from data-model.md (XTExchange class design)
- Extract from quickstart.md (8 validation scenarios)
- Extract from test_xt_contract.py (test requirements)

**Task Categories**:

1. **Contract Test Tasks** [P] (Parallel):
   - Verify test_xt_contract.py fails (TDD validation)
   - Run pytest with -v flag to see expected failures
   - Document baseline test output

2. **Model Creation Tasks** [P] (Parallel):
   - Create src/tri_arb/exchanges/xt.py skeleton
   - Implement XTExchange.__init__() method
   - Implement helper methods (_to_xt_symbol, _from_xt_symbol, _generate_signature)

3. **Connection Management Tasks** (Sequential):
   - Implement connect() method (httpx.AsyncClient initialization)
   - Implement disconnect() method (cleanup resources)
   - Implement is_connected property

4. **Public API Tasks** [P] (Parallel):
   - Implement get_ticker() - ticker price retrieval
   - Implement get_orderbook() - order book depth

5. **Private API Tasks** (Sequential - depend on auth):
   - Implement place_order() - order creation
   - Implement cancel_order() - order cancellation
   - Implement get_order_status() - order tracking

6. **Account Operations Tasks** [P] (Parallel):
   - Implement get_balance() - account balances
   - Implement get_trade_history() - historical trades

7. **Integration Tasks** (Sequential - depend on implementation):
   - Update settings.py with XT_API_KEY, XT_API_SECRET
   - Run contract tests → verify all pass
   - Run integration tests with test credentials (if available)
   - Execute quickstart.md validation (manual)

8. **Documentation Tasks** [P] (Parallel):
   - Add docstrings to all public methods
   - Update module-level documentation
   - Verify type hints coverage

### Ordering Strategy

**TDD Order**: Tests → Implementation → Validation
- Contract tests created first (already done in Phase 1)
- Implementation tasks in dependency order
- Validation tasks last

**Dependency Order**:
1. Helper methods (no dependencies)
2. Connection management (uses helpers)
3. Public API methods (uses connection)
4. Private API methods (uses connection + auth helpers)
5. Integration and validation (uses all above)

**Parallel Execution Markers**:
- [P] indicates tasks that can run in parallel
- Model creation, helper methods, and public/private API groups are parallelizable
- Connection lifecycle and integration tasks must be sequential

### Estimated Output

**Task Count**: 20-25 numbered tasks in tasks.md

**Task Structure**:
```markdown
## Task 1: Verify Contract Tests Fail (TDD Baseline)
**Type**: Contract Test | **Priority**: Critical | **Parallel**: No
**Description**: Run pytest on test_xt_contract.py to confirm tests fail as expected before implementation.
**Acceptance Criteria**: All contract tests show "Expected to FAIL" status

## Task 2-4: Create XTExchange Class Skeleton [P]
**Type**: Implementation | **Priority**: High | **Parallel**: Yes
...
```

**IMPORTANT**: This phase is executed by the `/tasks` command, NOT by /plan

## Phase 3+: Future Implementation

*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution 
- `/tasks` command creates tasks.md with 20-25 numbered tasks
- Tasks follow TDD order: Verify tests fail → Implement → Tests pass

**Phase 4**: Implementation 
- Execute tasks.md following constitutional principles
- Implement src/tri_arb/exchanges/xt.py
- Update configuration files (settings.py)
- Run tests continuously (TDD red-green-refactor)

**Phase 5**: Validation
- Run full test suite: `pytest tests/unit/test_exchanges/test_xt_contract.py -v`
- Execute manual validation: Follow quickstart.md scenarios
- Performance validation: Measure latencies against targets
- Integration validation: Test with real XT API (if credentials available)

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

**No violations detected** - This section left empty per constitution compliance.

## Progress Tracking

*This checklist is updated during execution flow*

### Phase Status
- [x] Phase 0: Research complete (/plan command)
  - ✅ research.md created with 16 sections
  - ✅ All NEEDS CLARIFICATION resolved
  - ✅ Technical decisions documented with rationale

- [x] Phase 1: Design complete (/plan command)
  - ✅ data-model.md created (9 sections, class designs)
  - ✅ contracts/xt-api.yaml created (8 endpoints)
  - ✅ test_xt_contract.py created (must fail initially)
  - ✅ test_xt_integration.py created (requires credentials)
  - ✅ quickstart.md created (8 validation scenarios)
  - ✅ CLAUDE.md updated (73-line integration section)

- [x] Phase 2: Task planning complete (/plan command - describe approach only)
  - ✅ Task generation strategy documented
  - ✅ Ordering strategy defined (TDD + dependency + parallel)
  - ✅ Estimated 20-25 tasks

- [ ] Phase 3: Tasks generated (/tasks command)
  - ⏳ Awaiting `/tasks` command execution
  
- [ ] Phase 4: Implementation complete
  - ⏳ Awaiting task execution
  
- [ ] Phase 5: Validation passed
  - ⏳ Awaiting implementation completion

### Gate Status
- [x] Initial Constitution Check: PASS
  - ✅ Type Safety confirmed
  - ✅ TDD approach validated
  - ✅ Performance-First verified
  - ✅ Observability ensured
  - ✅ Simplicity maintained

- [x] Post-Design Constitution Check: PASS
  - ✅ No new violations introduced during design
  - ✅ Architecture complies with all 5 principles

- [x] All NEEDS CLARIFICATION resolved
  - ✅ HTTP client decision: httpx
  - ✅ Authentication approach: HMAC-SHA256
  - ✅ Trading pair format: Bidirectional transformation
  - ✅ Error handling: tenacity retry
  - ✅ Performance optimization: Connection pooling
  - ✅ Testing strategy: TDD with contract tests

- [x] Complexity deviations documented
  - ✅ No deviations - section left empty

### TODO Items for Future Iterations

**API Documentation Verification** (marked in research.md):
- [ ] Verify exact field names for ticker response (bid/ask prices)
- [ ] Determine XT rate limits per endpoint and IP address
- [ ] Confirm order status enum values (NEW, FILLED, CANCELED, etc.)
- [ ] Test WebSocket support availability for real-time data
- [ ] Verify additional order types support (IOC, FOK, POST_ONLY)
- [ ] Confirm pagination mechanism for trade history

**These items do not block Phase 3-4 implementation** - can be resolved in subsequent feature iterations.

---
*Based on Constitution v1.0.0 - See `.specify/memory/constitution.md`*
*Ready for `/tasks` command execution*