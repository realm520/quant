
# Implementation Plan: Get All Market Tickers

**Branch**: `003-get-ticker-trading` | **Date**: 2025-10-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-get-ticker-trading/spec.md`

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
扩展 `BaseExchange.get_ticker()` 方法以支持批量获取所有市场ticker数据。当 `trading_pair` 参数为 `None` 时，返回交易所所有活跃市场的价格列表；当传入具体交易对时，保持现有单个市场查询行为。目标是将全市场扫描的API调用次数从 N 次降低到 1 次，并在1秒内完成批量查询，同时支持部分失败时的优雅降级。

## Technical Context
**Language/Version**: Python 3.11+ (required for performance and modern typing)
**Primary Dependencies**: httpx (async HTTP client), pydantic (data validation), structlog (logging)
**Storage**: N/A (stateless API operation)
**Testing**: pytest + pytest-asyncio (async testing), respx (httpx mocking)
**Target Platform**: Linux/macOS server environment (async I/O optimized)
**Project Type**: single (backend trading system)
**Performance Goals**: <1 second for batch ticker query (all markets), <10ms for price data parsing
**Constraints**: <50ms p95 for single ticker query (backward compatibility), support ≥500 trading pairs
**Scale/Scope**: 2 exchange adapters (BaseExchange, XTExchange), affects core trading loop performance

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Type Safety & Error Handling
- ✅ **Type annotations**: `Optional[TradingPair]` for parameter, `Union[Price, List[Price]]` for return
- ✅ **Exception handling**: Specific errors (NotImplementedError, ValueError, httpx errors)
- ✅ **Input validation**: None check, trading_pair validation in existing code
- ✅ **Immutable data**: Pydantic models already immutable
- ✅ **Null safety**: Explicit Optional type, None checks before processing

### II. Test-Driven Development
- ✅ **TDD enforced**: Contract tests MUST be written first (failing tests before implementation)
- ✅ **Contract tests**: BaseExchange interface tests for both single/batch ticker scenarios
- ✅ **Integration tests**: XTExchange batch ticker API integration tests
- ✅ **Performance tests**: <1s batch query, <50ms single query benchmarks required

### III. Performance-First Architecture
- ✅ **Latency targets**: <1s for batch (NFR-001), <50ms single query (existing)
- ✅ **Async-first**: Existing httpx async client, no synchronous blocking
- ✅ **Memory efficiency**: Streaming response parsing, no unbounded list growth
- ✅ **Performance metrics**: Latency logging required (NFR-005)

### IV. Observability & Audit Trail
- ✅ **Structured logging**: Record batch query performance, partial failures (FR-008, FR-012)
- ✅ **Performance metrics**: Response time tracking for >1s queries (NFR-005)
- ✅ **Error context**: Failed markets list in logs (FR-008, FR-012)
- ✅ **Correlation**: Existing structlog context preservation

### V. Simplicity & Maintainability
- ✅ **YAGNI**: Only implementing required batch query, no caching (FR-011 clarified)
- ✅ **Complexity**: Simple None check → batch path vs single path logic
- ✅ **Documentation**: Docstring updates required (FR-005)
- ✅ **Dependencies**: No new dependencies, using existing httpx + pydantic

**Constitutional Status**: ✅ PASS - No violations detected. All NON-NEGOTIABLE principles satisfied.

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
src/tri_arb/
├── exchanges/
│   ├── base.py               # Modified: get_ticker signature change
│   └── xt.py                 # Modified: batch ticker implementation
├── core/
│   └── models.py             # Existing: Price, TradingPair models
└── config/
    └── logging.py            # Existing: structlog configuration

tests/
├── unit/
│   └── test_exchanges/
│       ├── test_base_contract.py      # New: BaseExchange contract tests
│       └── test_xt_contract.py        # Modified: Add batch ticker tests
└── integration/
    └── test_xt_integration.py         # Modified: Add batch integration tests
```

**Structure Decision**: Single project structure (Option 1). This feature modifies existing exchange adapters (`base.py`, `xt.py`) and adds contract/integration tests. No new modules required - all changes are extensions to existing exchange infrastructure.

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
1. Load `.specify/templates/tasks-template.md` as base
2. Generate tasks from Phase 1 artifacts:
   - `contracts/base_exchange_get_ticker.md` → Contract test tasks
   - `data-model.md` → Interface modification tasks
   - `quickstart.md` → Integration test scenarios
3. Task categories:
   - **Contract Tests** [P]: Write failing tests for BaseExchange/XTExchange
   - **Interface Updates** [P]: Modify base.py signature, add type hints
   - **Implementation**: XTExchange batch ticker logic (depends on contract tests)
   - **Integration Tests**: Real XT API integration scenarios
   - **Performance Tests**: Benchmark <1s batch, <50ms single query
   - **Documentation**: Update docstrings (FR-005)

**Ordering Strategy (TDD Workflow)**:
```
1. [P] Write BaseExchange contract tests (MUST fail)
2. [P] Write XTExchange contract tests (MUST fail)
3. Update BaseExchange.get_ticker signature (makes some tests pass)
4. Implement XTExchange batch query logic (makes rest pass)
5. Add integration tests for real XT API
6. Add performance benchmarks
7. Update documentation
```

**Parallelization Opportunities** (marked [P]):
- Contract test files (independent)
- Interface vs implementation updates (after tests)
- Documentation can be done alongside implementation

**Estimated Task Count**: 18-22 tasks
- 6 test tasks (contract + integration + performance)
- 4 implementation tasks (signature + batch logic + helpers + error handling)
- 4 documentation tasks (docstrings + CLAUDE.md + quickstart + API docs)
- 2 validation tasks (manual testing + performance validation)

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

**No constitutional violations detected** - This feature follows all NON-NEGOTIABLE principles:
- Type safety maintained with `Optional[TradingPair]` and `Union[Price, List[Price]]`
- TDD enforced with contract tests written first
- Performance targets explicit (<1s batch, <50ms single)
- Observability via structured logging for failures
- Simplicity preserved (no new dependencies, minimal complexity)

No complexity tracking entries required.


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none required)

**Generated Artifacts**:
- [x] research.md - API signature, XT API research, performance strategy
- [x] data-model.md - Interface signature changes, data flow diagrams
- [x] contracts/base_exchange_get_ticker.md - API contract specification
- [x] contracts/test_get_ticker_contract.py - Contract test suite (failing)
- [x] quickstart.md - Usage examples and troubleshooting guide
- [x] CLAUDE.md - Agent context updated with feature 003 details

**Ready for**: `/tasks` command to generate tasks.md

---
*Based on Constitution v2.1.1 - See `/memory/constitution.md`*
