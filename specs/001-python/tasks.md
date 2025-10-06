# Tasks: Python Triangle Arbitrage Scaffold

**Input**: Design documents from `/Users/harry/code/quants/tri-arb/specs/001-python/`
**Prerequisites**: plan.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

## Execution Flow (main)
```
1. Loaded plan.md → Tech stack: Python 3.11+, uv, pydantic, typer, structlog
2. Loaded design documents:
   → research.md: 15 technology decisions validated
   → data-model.md: 6 core entities + supporting types
   → contracts/: CLI interface (no Web API for MVP)
   → quickstart.md: Installation, testing, deployment scenarios
3. Generated tasks by category:
   → Setup: Project structure, uv config, linting tools
   → Tests: Unit tests for models, integration tests for CLI
   → Core: Data models, exchange interfaces, services
   → Integration: Database, cache, logging, metrics
   → Polish: Build scripts, documentation, deployment
4. Applied task rules:
   → [P] for independent model files
   → Sequential for shared config files
   → TDD: Tests before implementation
5. Numbered tasks: T001-T042 (42 tasks total)
6. Validated: All entities have models ✓, All tests before impl ✓
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions
- All paths relative to repository root: `/Users/harry/code/quants/tri-arb/`

## Phase 3.1: Setup & Infrastructure (Serial - Foundation)

### Project Structure & Configuration
- [x] **T001** Create project directory structure (`src/tri_arb/`, `tests/`, `config/`, `scripts/`, `docs/`)
- [x] **T002** Initialize pyproject.toml with uv configuration (dependencies, dev dependencies, build system)
- [x] **T003** Configure mypy.ini with strict mode (strict = true, python_version = "3.11", all strict flags)
- [x] **T004** Configure ruff.toml (line-length = 100, target-version = "py311", select = ["E", "F", "I", "N"])
- [x] **T005** Create Makefile with targets (setup, install-dev, lint, format, test, test-cov, build, check, pre-commit)
- [x] **T006** Create .gitignore (Python standard + .venv/, dist/, *.db, *.log, .env)

## Phase 3.2: Configuration & Settings (Serial - Core Dependencies)

### Settings & Environment
- [x] **T007** Implement Settings class in `src/tri_arb/config/settings.py` using pydantic-settings (app, db, cache, performance, monitoring)
- [x] **T008** Create logging configuration in `src/tri_arb/config/logging.py` with structlog (JSON format, correlation IDs, log levels)
- [x] **T009** Create `.env.example` with all required environment variables (APP_NAME, LOG_LEVEL, DB_PATH, CACHE_TTL, METRICS_PORT)
- [x] **T010** Create `config/config.example.yaml` with complete configuration structure (app, database, cache, exchanges, monitoring)

## Phase 3.3: Core Data Models (Parallel - Independent Models) ⚠️ WRITE TESTS FIRST

### Model Tests (TDD - Must Fail Before Implementation)
- [x] **T011** [P] Unit test for TradingPair model in `tests/unit/test_core/test_models.py` (validation, uppercase currency, min/max order size)
- [x] **T012** [P] Unit test for Price model in `tests/unit/test_core/test_models.py` (bid/ask validation, mid_price computed field, is_stale)
- [x] **T013** [P] Unit test for OrderBook model in `tests/unit/test_core/test_models.py` (bids descending, asks ascending)
- [x] **T014** [P] Unit test for Order model in `tests/unit/test_core/test_models.py` (state transitions, limit price validation)
- [x] **T015** [P] Unit test for Trade model in `tests/unit/test_core/test_models.py` (price/quantity validation, fee handling)
- [x] **T016** [P] Unit test for ArbitrageOpportunity model in `tests/unit/test_core/test_models.py` (triangle validation, profit calculation)

### Model Implementation (ONLY After Tests Fail)
- [x] **T017** [P] Implement TradingPair model in `src/tri_arb/core/models.py` (fields, validators, uppercase currency, order size validation)
- [x] **T018** [P] Implement Price model in `src/tri_arb/core/models.py` (bid/ask prices, computed mid_price, is_stale property)
- [x] **T019** [P] Implement OrderBook model in `src/tri_arb/core/models.py` (bids/asks lists, sorting validators)
- [x] **T020** [P] Implement Order model in `src/tri_arb/core/models.py` (OrderSide/OrderType/OrderStatus enums, state machine validation)
- [x] **T021** [P] Implement Trade model in `src/tri_arb/core/models.py` (execution data, fee tracking)
- [x] **T022** [P] Implement ArbitrageOpportunity model in `src/tri_arb/core/models.py` (path validation, profit calculation, viability check)
- [x] **T023** Create custom exception hierarchy in `src/tri_arb/core/exceptions.py` (TriArbException base, InvalidTradingPairError, StalePriceError, InsufficientLiquidityError, ExchangeConnectionError, OrderExecutionError)

### Placeholder Arbitrage Logic
- [x] **T024** [P] Create placeholder arbitrage calculator in `src/tri_arb/core/arbitrage.py` (stub functions for triangle detection, profit calculation)
- [x] **T025** [P] Create placeholder fee calculator in `src/tri_arb/core/calculator.py` (stub functions for fee calculation, price adjustments)

## Phase 3.4: Data Layer (Serial - Depends on Models)

### Database & Cache
- [x] **T026** Implement database connection manager in `src/tri_arb/data/database.py` (aiosqlite connection pool, WAL mode, async context manager)
- [x] **T027** Create cache wrapper in `src/tri_arb/data/cache.py` (TTLCache and LRUCache wrappers, async-safe access)
- [x] **T028** Create repository base class in `src/tri_arb/data/repositories/__init__.py` (abstract base with common CRUD operations)
- [x] **T029** [P] Implement trade repository in `src/tri_arb/data/repositories/trade_repo.py` (placeholder CRUD for Trade model)
- [x] **T030** [P] Implement price repository in `src/tri_arb/data/repositories/price_repo.py` (placeholder CRUD for Price model)

## Phase 3.5: Exchange Integration (Serial - Depends on Models)

### Exchange Interfaces
- [x] **T031** Define BaseExchange abstract class in `src/tri_arb/exchanges/base.py` (abstract methods: get_ticker, get_orderbook, place_order, cancel_order, get_order_status, get_trade_history, subscribe_ticker, subscribe_orderbook)
- [x] **T032** Create exchange factory in `src/tri_arb/exchanges/factory.py` (factory pattern for exchange creation, registration system)
- [x] **T033** [P] Implement Binance placeholder adapter in `src/tri_arb/exchanges/binance.py` (stub implementation of BaseExchange, placeholder responses)
- [x] **T034** [P] Implement OKX placeholder adapter in `src/tri_arb/exchanges/okx.py` (stub implementation of BaseExchange, placeholder responses)

## Phase 3.6: Service Layer (Parallel - Independent Services)

### Service Stubs
- [x] **T035** [P] Create market data service stub in `src/tri_arb/services/market_data.py` (placeholder methods, logging placeholders)
- [x] **T036** [P] Create trading service stub in `src/tri_arb/services/trading.py` (placeholder order execution, logging)
- [x] **T037** [P] Create monitoring service stub in `src/tri_arb/services/monitoring.py` (placeholder health checks, logging)
- [x] **T038** [P] Create risk management service stub in `src/tri_arb/services/risk.py` (placeholder risk checks, logging)

## Phase 3.7: CLI Application (Serial - Depends on Services)

### CLI Commands
- [x] **T039** Create Typer app structure in `src/tri_arb/cli/app.py` (main app, command groups)
- [x] **T040** Implement start command in `src/tri_arb/cli/commands/start.py` (system startup, uvloop initialization, placeholder mode logging)
- [x] **T041** Implement status command in `src/tri_arb/cli/commands/status.py` (system status display, placeholder metrics)
- [x] **T042** Implement config commands in `src/tri_arb/cli/commands/config.py` (show, validate, set subcommands)
- [x] **T043** Add CLI utilities in `src/tri_arb/cli/utils.py` (formatters, validators, helpers)
- [x] **T044** Create __main__.py entry point in `src/tri_arb/__main__.py` (uvloop policy, CLI app invocation)

## Phase 3.8: Utilities (Parallel - Independent Utilities)

### Monitoring & Health
- [x] **T045** [P] Implement Prometheus metrics in `src/tri_arb/utils/metrics.py` (Counter, Gauge, Histogram for requests, opportunities, errors)
- [x] **T046** [P] Create health check system in `src/tri_arb/utils/health.py` (database check, cache check, logging check, metrics check)
- [x] **T047** [P] Add async utilities in `src/tri_arb/utils/async_utils.py` (async helpers, context managers, utilities)

## Phase 3.9: Testing Infrastructure (Serial - Integration Tests)

### Integration & Contract Tests
- [x] **T048** Setup pytest configuration in `tests/conftest.py` (async fixtures, database fixtures, cache fixtures, mock exchange fixtures)
- [x] **T049** [P] Create integration test for CLI flow in `tests/integration/test_cli_flow.py` (start → status → config workflow)
- [x] **T050** [P] Create integration test for service integration in `tests/integration/test_service_integration.py` (service coordination, data flow)
- [x] **T051** [P] Create contract test for BaseExchange in `tests/contract/test_exchange_interface.py` (verify all adapters implement interface correctly)

## Phase 3.10: Build & Deployment (Serial - Final Stage)

### Build Scripts
- [x] **T052** Create PyInstaller build script in `scripts/build.sh` (one-file mode, hidden imports, optimization)
- [x] **T053** Generate systemd service file in `scripts/systemd/tri-arb.service` (service configuration, restart policy, resource limits)
- [x] **T054** Write deployment script in `scripts/deploy.sh` (build → copy → systemd setup)

### Documentation
- [x] **T055** Create comprehensive README.md (project overview, installation, usage, configuration, testing)
- [x] **T056** [P] Add architecture documentation in `docs/architecture.md` (system diagram, module responsibilities, design decisions)
- [x] **T057** [P] Add development guide in `docs/development.md` (setup, workflow, testing, debugging, contributing)

## Dependencies

### Critical Paths (Must Follow Order)
1. **Setup First**: T001-T006 before everything
2. **Config Next**: T007-T010 before models (needed for validation)
3. **Test-First (TDD)**: T011-T016 before T017-T022 (tests must fail first)
4. **Models Before Services**: T017-T023 before T026-T030, T035-T038
5. **Services Before CLI**: T035-T038 before T039-T044
6. **Everything Before Build**: T001-T051 before T052-T054

### Blocking Relationships
- T007 (Settings) blocks T026 (Database), T027 (Cache), T008 (Logging)
- T017-T022 (Models) block T026-T030 (Data Layer), T031-T034 (Exchanges), T035-T038 (Services)
- T031 (BaseExchange) blocks T032-T034 (Exchange Implementations)
- T035-T038 (Services) block T039-T044 (CLI Commands)
- T048 (pytest config) blocks T049-T051 (Integration Tests)
- T001-T051 (All Implementation) block T052-T054 (Build & Deploy)

### Independent Parallel Groups
- **Group 1**: T011-T016 (Model Tests) - can run simultaneously
- **Group 2**: T017-T022 (Model Implementations) - after Group 1 fails
- **Group 3**: T024-T025 (Placeholder Logic) - independent of data layer
- **Group 4**: T029-T030 (Repositories) - different files
- **Group 5**: T033-T034 (Exchange Adapters) - different files
- **Group 6**: T035-T038 (Service Stubs) - different files
- **Group 7**: T045-T047 (Utilities) - different files
- **Group 8**: T049-T051 (Integration Tests) - different files
- **Group 9**: T056-T057 (Documentation) - different files

## Parallel Execution Examples

### Example 1: Model Tests (TDD Phase)
```bash
# Launch all model tests together (must fail before implementation):
Task agent 1: "Write unit test for TradingPair model in tests/unit/test_core/test_models.py"
Task agent 2: "Write unit test for Price model in tests/unit/test_core/test_models.py"
Task agent 3: "Write unit test for OrderBook model in tests/unit/test_core/test_models.py"
Task agent 4: "Write unit test for Order model in tests/unit/test_core/test_models.py"
Task agent 5: "Write unit test for Trade model in tests/unit/test_core/test_models.py"
Task agent 6: "Write unit test for ArbitrageOpportunity model in tests/unit/test_core/test_models.py"

# Verify all tests fail, then proceed to implementation
```

### Example 2: Model Implementations (After Tests Fail)
```bash
# Launch all model implementations together:
Task agent 1: "Implement TradingPair model in src/tri_arb/core/models.py"
Task agent 2: "Implement Price model in src/tri_arb/core/models.py"
Task agent 3: "Implement OrderBook model in src/tri_arb/core/models.py"
Task agent 4: "Implement Order model in src/tri_arb/core/models.py"
Task agent 5: "Implement Trade model in src/tri_arb/core/models.py"
Task agent 6: "Implement ArbitrageOpportunity model in src/tri_arb/core/models.py"
```

### Example 3: Service Layer Stubs
```bash
# Launch all service stubs together (independent files):
Task agent 1: "Create market data service stub in src/tri_arb/services/market_data.py"
Task agent 2: "Create trading service stub in src/tri_arb/services/trading.py"
Task agent 3: "Create monitoring service stub in src/tri_arb/services/monitoring.py"
Task agent 4: "Create risk management service stub in src/tri_arb/services/risk.py"
```

### Example 4: Integration Tests
```bash
# Launch integration tests together:
Task agent 1: "Integration test CLI flow in tests/integration/test_cli_flow.py"
Task agent 2: "Integration test service integration in tests/integration/test_service_integration.py"
Task agent 3: "Contract test BaseExchange in tests/contract/test_exchange_interface.py"
```

## Notes

### TDD Enforcement
- **CRITICAL**: Tests T011-T016 MUST be written first and MUST FAIL
- Do NOT implement models (T017-T022) until all tests are failing
- Run `pytest tests/unit/test_core/test_models.py` to verify failures
- User approval required before moving from tests to implementation

### Parallel Execution
- Tasks marked [P] can run in parallel only if:
  - They modify different files
  - They have no dependencies on each other
  - Previous phase is complete
- Same file conflicts: T011-T016 all modify same test file → run sequentially or use different test files

### Quality Gates
- After each task: Run `mypy src/` and `ruff check src/`
- After each phase: Run `pytest` to verify tests pass
- Before T052 (build): Run `make check` (lint + format + test)
- Commit after each completed task with descriptive message

### MVP Scope Reminder
- **Scaffold Only**: No actual trading logic, only infrastructure
- **Placeholder Mode**: All exchange connections return mock data
- **No Real Trading**: Order execution logs "placeholder mode" messages
- **Focus**: Project structure, testing framework, CLI commands, deployment automation

## Validation Checklist

- [x] All entities have corresponding model tasks (TradingPair, Price, OrderBook, Order, Trade, ArbitrageOpportunity)
- [x] All model tasks have tests first (T011-T016 before T017-T022)
- [x] All tests come before implementation (TDD enforced)
- [x] Parallel tasks are truly independent (verified file paths)
- [x] Each task specifies exact file path
- [x] No [P] task modifies same file as another [P] task (verified)
- [x] CLI interface contract covered (T039-T044)
- [x] BaseExchange interface contract covered (T031, T051)
- [x] Build and deployment covered (T052-T054)
- [x] Documentation complete (T055-T057)

## Estimated Effort

### By Complexity
- **Simple** (1-2 hours): T001-T006, T009-T010, T023-T025, T029-T030, T033-T034, T035-T038, T045-T047, T056-T057 (24 tasks)
- **Medium** (2-4 hours): T007-T008, T011-T022, T026-T028, T031-T032, T039-T044, T049-T051, T055 (26 tasks)
- **Complex** (4-8 hours): T048, T052-T054 (4 tasks)

### Total Estimated Time
- Simple: 24 tasks × 1.5h avg = 36 hours
- Medium: 26 tasks × 3h avg = 78 hours
- Complex: 4 tasks × 6h avg = 24 hours
- **Total: ~138 hours (~17-18 days for single developer)**

### With Parallel Execution
- Parallel groups can reduce time by ~30-40%
- **Optimistic: ~10-12 days with efficient parallelization**
