
# Implementation Plan: Python Triangle Arbitrage Scaffold

**Branch**: `001-python` | **Date**: 2025-10-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/Users/harry/code/quants/tri-arb/specs/001-python/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from file system structure or context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code, or `AGENTS.md` for all other agents).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
构建一个可运行的 Python 三角套利项目脚手架，提供完整的项目基础设施（配置、日志、测试、CLI、部署）而不实现具体的交易逻辑。采用分层架构（core/exchanges/data/services/config/cli/utils），使用 uv 管理依赖，支持二进制打包和 systemd 部署。遵循 TDD、类型安全、性能优先的开发原则。

## Technical Context
**Language/Version**: Python 3.11+ (required for performance improvements and modern typing features)
**Primary Dependencies**: uv (package management), uvloop (async optimization), httpx (HTTP client), websockets (WebSocket), aiosqlite (database), cachetools (caching), pydantic (validation), pydantic-settings (config), typer (CLI), structlog (logging), prometheus-client (metrics), PyInstaller (packaging)
**Storage**: SQLite + aiosqlite (lightweight, single-machine, async database for historical data and configuration)
**Testing**: pytest with pytest-asyncio (async testing), pytest-benchmark (performance), pytest-mock (mocking)
**Target Platform**: Linux servers (cloud hosts or bare metal), systemd service management
**Project Type**: single (monorepo with src/ for source code, tests/ for tests, config/ for configuration files, scripts/ for deployment scripts, docs/ for documentation)
**Performance Goals**: <50ms p95 for arbitrage opportunity detection, <10ms p95 for price data processing, <500MB steady-state memory usage
**Constraints**: <50ms p95 latency for critical paths, async-first design for all I/O, 100% type annotations in core modules, ≥90% test coverage for core logic
**Scale/Scope**: MVP scaffold only - no actual trading logic, focus on infrastructure (7 core modules, ~20 source files, ~30 test files estimated)

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Type Safety & Error Handling (NON-NEGOTIABLE)
- ✅ **PASS**: MVP scope includes mypy strict mode configuration, 100% type annotations in core modules
- ✅ **PASS**: Custom exception classes planned in core/exceptions.py
- ✅ **PASS**: Pydantic for data validation at system boundaries
- ✅ **PASS**: Optional types for null safety

### II. Test-Driven Development (NON-NEGOTIABLE)
- ✅ **PASS**: pytest framework with pytest-asyncio, pytest-benchmark, pytest-mock configured
- ✅ **PASS**: Test structure (tests/unit, tests/integration, tests/contract) planned
- ✅ **PASS**: Target coverage ≥90% for core logic, ≥80% overall
- ⚠️ **NOTE**: MVP is scaffold only - tests will be placeholders/examples, actual TDD for business logic comes later

### III. Performance-First Architecture
- ✅ **PASS**: asyncio + uvloop for async runtime optimization
- ✅ **PASS**: Performance targets defined (<50ms p95 arbitrage detection, <10ms p95 price processing)
- ✅ **PASS**: Memory constraints specified (<500MB steady-state, <1GB peak)
- ✅ **PASS**: Caching strategy (cachetools for in-memory caching)
- ⚠️ **NOTE**: MVP is scaffold - actual performance optimization comes with business logic implementation

### IV. Observability & Audit Trail
- ✅ **PASS**: structlog for structured JSON logging with correlation IDs
- ✅ **PASS**: prometheus-client for metrics collection (Counter, Gauge, Histogram)
- ✅ **PASS**: Logging configuration in config/logging.py planned
- ✅ **PASS**: Health check mechanism in utils/health.py planned

### V. Simplicity & Maintainability
- ✅ **PASS**: MVP scope clearly defined - only scaffold, no trading logic (YAGNI principle)
- ✅ **PASS**: Minimal dependencies (15 core dependencies, justified in spec)
- ✅ **PASS**: Clear module organization (7 modules with single responsibilities)
- ✅ **PASS**: Documentation planned (README, quickstart, development guide)
- ✅ **PASS**: ruff for linting and code quality enforcement

### Quality Standards Alignment
- ✅ **PASS**: Python 3.11+ specified
- ✅ **PASS**: uv for package management
- ✅ **PASS**: mypy strict mode + ruff configured
- ✅ **PASS**: Test coverage targets aligned (≥90% core, ≥80% overall)

### Initial Assessment: **ALL GATES PASS** ✅
MVP scope is well-aligned with constitutional principles. No violations or complexity justifications needed.

### Post-Design Assessment: **ALL GATES PASS** ✅
After completing Phase 1 design (data-model.md, contracts, quickstart.md), all constitutional principles remain satisfied:
- ✅ **Type Safety**: Pydantic models with full validation (TradingPair, Price, Order, ArbitrageOpportunity)
- ✅ **TDD**: Test structure planned (unit/integration/contract), pytest configuration defined
- ✅ **Performance**: Async architecture validated, performance targets maintained
- ✅ **Observability**: Logging/metrics strategy confirmed (structlog + prometheus)
- ✅ **Simplicity**: MVP scope strictly maintained - scaffold only, no trading logic
- ✅ **Architecture**: 7-layer modular design prevents future refactoring
- ✅ **CLI Contracts**: Well-defined command interface (start, status, config, health-check)
- ✅ **Data Models**: Comprehensive with validation rules and state machines

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
tri-arb/
├── src/
│   └── tri_arb/              # Main Python package
│       ├── __init__.py
│       ├── __main__.py       # CLI entry point
│       ├── core/             # Core business logic (pure functions, no I/O)
│       │   ├── __init__.py
│       │   ├── models.py     # Data models (TradingPair, Order, ArbitrageOpportunity)
│       │   ├── arbitrage.py  # Arbitrage algorithm (placeholder)
│       │   ├── calculator.py # Price/fee calculations (placeholder)
│       │   └── exceptions.py # Custom exceptions
│       ├── exchanges/        # Exchange abstraction layer
│       │   ├── __init__.py
│       │   ├── base.py       # Abstract base class
│       │   ├── binance.py    # Binance adapter (placeholder)
│       │   ├── okx.py        # OKX adapter (placeholder)
│       │   └── factory.py    # Factory pattern for exchange creation
│       ├── data/             # Data access layer
│       │   ├── __init__.py
│       │   ├── database.py   # SQLite connection management
│       │   ├── cache.py      # Cachetools wrapper
│       │   └── repositories/ # Repository pattern
│       │       ├── __init__.py
│       │       ├── trade_repo.py  # Trade history repository (placeholder)
│       │       └── price_repo.py  # Price history repository (placeholder)
│       ├── services/         # Business service layer
│       │   ├── __init__.py
│       │   ├── market_data.py    # Market data service (placeholder)
│       │   ├── trading.py        # Trading execution service (placeholder)
│       │   ├── monitoring.py     # Monitoring service (placeholder)
│       │   └── risk.py           # Risk management service (placeholder)
│       ├── config/           # Configuration management
│       │   ├── __init__.py
│       │   ├── settings.py   # Pydantic Settings
│       │   └── logging.py    # Logging configuration
│       ├── cli/              # CLI command layer
│       │   ├── __init__.py
│       │   ├── app.py        # Typer main app
│       │   ├── commands/     # Command groups
│       │   │   ├── __init__.py
│       │   │   ├── start.py  # Start command
│       │   │   ├── status.py # Status command
│       │   │   └── config.py # Config command
│       │   └── utils.py      # CLI utilities
│       └── utils/            # General utilities
│           ├── __init__.py
│           ├── metrics.py    # Prometheus metrics
│           ├── health.py     # Health check
│           └── async_utils.py # Async utilities
│
├── tests/                    # Test directory
│   ├── __init__.py
│   ├── conftest.py           # Pytest configuration
│   ├── unit/                 # Unit tests
│   │   ├── __init__.py
│   │   ├── test_core/
│   │   ├── test_exchanges/
│   │   ├── test_data/
│   │   ├── test_services/
│   │   ├── test_config/
│   │   └── test_utils/
│   ├── integration/          # Integration tests
│   │   ├── __init__.py
│   │   ├── test_cli_flow.py
│   │   └── test_service_integration.py
│   └── contract/             # Contract tests
│       ├── __init__.py
│       └── test_exchange_interface.py
│
├── config/                   # Configuration files
│   ├── config.example.yaml   # Example configuration
│   ├── logging.yaml          # Logging configuration
│   └── .env.example          # Environment variables example
│
├── scripts/                  # Deployment and utility scripts
│   ├── build.sh              # PyInstaller build script
│   ├── deploy.sh             # Deployment script
│   └── systemd/
│       └── tri-arb.service   # systemd service file
│
├── docs/                     # Documentation
│   ├── README.md
│   ├── architecture.md
│   ├── quickstart.md
│   └── development.md
│
├── pyproject.toml            # uv project configuration
├── Makefile                  # Build automation
├── .gitignore
├── .env                      # Environment variables (gitignored)
├── ruff.toml                 # Ruff configuration
└── mypy.ini                  # mypy configuration
```

**Structure Decision**: Single project monorepo structure selected. This is appropriate for the MVP scaffold as:
- All code is Python-based with no frontend/backend split
- Single deployment artifact (CLI application)
- Clear separation of concerns through module organization (core/exchanges/data/services/config/cli/utils)
- Test directory mirrors source structure for easy navigation
- Configuration, scripts, and documentation organized at repository root

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh claude`
     **IMPORTANT**: Execute it exactly as specified above. Do not add or remove any arguments.
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
The /tasks command will generate tasks following strict TDD and dependency ordering:

1. **Infrastructure Setup** (Serial - Foundation):
   - Create project structure (src/, tests/, config/, scripts/, docs/)
   - Setup pyproject.toml with uv configuration
   - Configure mypy.ini (strict mode) and ruff.toml
   - Create Makefile for automation

2. **Configuration & Settings** (Serial - Core Dependencies):
   - Implement pydantic-settings configuration (config/settings.py)
   - Create logging configuration with structlog (config/logging.py)
   - Setup environment variable examples (.env.example, config.example.yaml)

3. **Core Data Models** (Parallel - Independent Models) [P]:
   - Implement TradingPair model with validation (core/models.py)
   - Implement Price model with computed fields
   - Implement OrderBook model with sorting validation
   - Implement Order model with state machine
   - Implement Trade model with fee tracking
   - Implement ArbitrageOpportunity model with triangle validation
   - Create custom exceptions hierarchy (core/exceptions.py)

4. **Data Layer** (Serial - Depends on Models):
   - Implement database connection manager (data/database.py)
   - Create cache wrapper with TTL support (data/cache.py)
   - Implement repository pattern base classes (data/repositories/)
   - Add trade history repository (data/repositories/trade_repo.py)
   - Add price history repository (data/repositories/price_repo.py)

5. **Exchange Integration** (Serial - Depends on Models):
   - Define BaseExchange abstract class (exchanges/base.py)
   - Create exchange factory pattern (exchanges/factory.py)
   - Implement Binance placeholder adapter (exchanges/binance.py)
   - Implement OKX placeholder adapter (exchanges/okx.py)

6. **Service Layer Placeholders** (Parallel - Independent Services) [P]:
   - Market data service stub (services/market_data.py)
   - Trading execution service stub (services/trading.py)
   - Monitoring service stub (services/monitoring.py)
   - Risk management service stub (services/risk.py)

7. **CLI Application** (Serial - Depends on Services):
   - Create Typer app structure (cli/app.py)
   - Implement start command (cli/commands/start.py)
   - Implement status command (cli/commands/status.py)
   - Implement config commands (cli/commands/config.py)
   - Add CLI utilities and helpers (cli/utils.py)
   - Create __main__.py entry point with uvloop

8. **Utilities** (Parallel - Independent Utilities) [P]:
   - Implement Prometheus metrics (utils/metrics.py)
   - Create health check system (utils/health.py)
   - Add async utilities (utils/async_utils.py)

9. **Testing Infrastructure** (Serial - Depends on All Above):
   - Setup pytest configuration (tests/conftest.py)
   - Create test fixtures for common mocks
   - Implement unit test examples for core models
   - Create integration test scaffolds
   - Add contract test examples for exchange interface

10. **Build & Deployment** (Serial - Final Stage):
    - Create PyInstaller build script (scripts/build.sh)
    - Generate systemd service file (scripts/systemd/tri-arb.service)
    - Write deployment script (scripts/deploy.sh)
    - Create comprehensive README.md
    - Add architecture documentation (docs/architecture.md)
    - Add development guide (docs/development.md)

**Ordering Strategy**:
- **TDD Cycle**: For each module: Write tests → User approval → Implementation → Validation
- **Dependency Chain**: Infrastructure → Config → Models → Data → Exchanges → Services → CLI → Utils → Tests → Deploy
- **Parallel Markers [P]**: Independent files within same layer can be developed in parallel
- **Validation Gates**: Each layer must pass tests before moving to next

**Task Complexity**:
- **Simple** (1-2 hours): Individual model implementations, placeholder services
- **Medium** (2-4 hours): Database layer, exchange abstractions, CLI commands
- **Complex** (4-8 hours): Full testing infrastructure, build scripts, documentation

**Estimated Output**: 35-40 numbered, dependency-ordered tasks in tasks.md

**Quality Gates**:
- Each task must have acceptance criteria
- Tests must be written before implementation
- All tasks must align with constitutional principles
- Code must pass mypy strict + ruff before marking complete

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command) - research.md created with 15 technology decisions
- [x] Phase 1: Design complete (/plan command) - data-model.md, contracts/README.md, quickstart.md, CLAUDE.md updated
- [x] Phase 2: Task planning complete (/plan command - describe approach only) - 10-stage task generation strategy defined
- [x] Phase 3: Tasks generated (/tasks command) - 57 tasks organized in 10 phases with dependency management
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS (all gates passed)
- [x] Post-Design Constitution Check: PASS (all principles satisfied)
- [x] All NEEDS CLARIFICATION resolved (no unknowns remaining)
- [x] Complexity deviations documented (none - no violations)

---
*Based on Constitution v2.1.1 - See `/memory/constitution.md`*
