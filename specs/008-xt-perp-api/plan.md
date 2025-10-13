# Implementation Plan: XT Perpetual Futures API Integration

**Branch**: `008-xt-perp-api` | **Date**: 2025-10-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-xt-perp-api/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → ✅ DONE: Loaded spec.md with 51 functional requirements
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → ✅ DONE: No NEEDS CLARIFICATION markers, all technical details specified
   → Project Type: Single project (existing tri-arb codebase)
3. Fill the Constitution Check section
   → ✅ DONE: TDD compliance checked, no violations
4. Evaluate Constitution Check section
   → ✅ PASS: Follows TDD principles, extends existing patterns
5. Execute Phase 0 → research.md
   → ✅ DONE: 7 key technical decisions documented
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, CLAUDE.md
   → ✅ DONE: All Phase 1 deliverables completed
7. Re-evaluate Constitution Check section
   → ✅ PASS: Design follows existing architecture patterns
8. Plan Phase 2 → Describe task generation approach
   → ✅ DONE: Task generation strategy documented below
9. STOP - Ready for /tasks command
   → ✅ READY: All prerequisites complete
```

**IMPORTANT**: The /plan command STOPS at step 9. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary

**Primary Requirement**: 集成 XT 交易所永续合约 API，实现 `XTPerpExchange` 类继承 `BaseExchange` 接口，支持永续合约特有功能（持仓管理、杠杆控制、资金费率查询、止盈止损单）。

**Technical Approach** (from research.md):
- 复用 `xt_perp_api.py` 的签名逻辑和 API 端点定义
- 扩展现有数据模型（TradingPair, Order）添加永续合约字段
- 新增专用数据模型（Position, FundingRate, LeverageBracket, PlanOrder, StopProfit）
- 使用 httpx 异步 HTTP 客户端，连接池优化（max_connections=100）
- 实现双向交易逻辑（position_side: LONG/SHORT + order_side: BUY/SELL）
- TDD 开发流程：合约测试 → 单元测试 → 集成测试 → 性能测试

## Technical Context

**Language/Version**: Python 3.11+ (项目现有要求)

**Primary Dependencies**: 
- httpx (异步 HTTP 客户端，连接池支持)
- pydantic (数据验证和模型定义)
- tenacity (重试逻辑，网络错误处理)
- structlog (结构化日志)
- pytest + pytest-asyncio + respx (测试框架)

**Storage**: N/A (无持久化需求，仅内存管理持仓和订单状态)

**Testing**: pytest + pytest-asyncio (异步测试) + respx (httpx mocking)

**Target Platform**: Linux/macOS (Python 3.11+ 异步运行时)

**Project Type**: Single project (tri-arb 现有单体架构)

**Performance Goals**: 
- 订单提交延迟: <50ms p95 (从信号到提交)
- 持仓查询延迟: <100ms p95 (请求到响应)
- 价格处理延迟: <10ms p95 (仅解析，不含网络)
- 资金费率查询: <2 seconds (含网络)

**Constraints**: 
- 必须继承 BaseExchange 接口保持一致性
- 必须复用 xt_perp_api.py 的签名逻辑
- 必须通过所有合约测试（BaseExchange 接口合规）
- API 凭证不得记录到日志或错误消息

**Scale/Scope**: 
- 支持所有 XT 永续合约交易对 (BTC/USDT, ETH/USDT 等)
- 支持 1-125x 杠杆倍数
- 支持市价单、限价单、条件单（止盈止损）
- 支持双向持仓（同时做多和做空）

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**TDD Compliance**:
- ✅ Tests before implementation (contract tests will fail until implementation)
- ✅ Extends existing patterns (BaseExchange interface)
- ✅ Incremental development (Phase 0 → Phase 1 → Phase 2)
- ✅ No premature optimization (focus on correctness first)

**Architecture Principles**:
- ✅ Single Responsibility (XTPerpExchange only handles perpetual futures)
- ✅ Open/Closed (extends BaseExchange without modifying it)
- ✅ Liskov Substitution (XTPerpExchange can replace any BaseExchange)
- ✅ Interface Segregation (BaseExchange has minimal required methods)
- ✅ Dependency Inversion (depends on abstractions, not implementations)

**Code Quality**:
- ✅ Type hints required (Python 3.11+ with strict mypy)
- ✅ Async/await pattern (performance requirement)
- ✅ Error handling with tenacity retry
- ✅ Comprehensive logging with structlog

**Security**:
- ✅ API credentials never logged
- ✅ HTTPS with certificate verification
- ✅ Input validation at boundaries
- ✅ HMAC-SHA256 signature authentication

**Initial Gate**: ✅ PASS (No constitution violations)

## Project Structure

### Documentation (this feature)
```
specs/008-xt-perp-api/
├── spec.md              # Feature specification (51 requirements)
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (7 technical decisions)
├── data-model.md        # Phase 1 output (7 data models)
├── quickstart.md        # Phase 1 output (user quick start guide)
├── contracts/           # Phase 1 output (API contracts)
│   ├── README.md        # API organization documentation
│   └── trading.yaml     # Trading endpoints OpenAPI spec
└── tasks.md             # Phase 2 output (NOT created yet, /tasks command)
```

### Source Code (repository root)
```
src/tri_arb/
├── exchanges/
│   ├── base.py              # BaseExchange interface (existing)
│   ├── xt_spot.py           # XTSpotExchange (existing reference)
│   └── xt_perp.py           # XTPerpExchange (TO BE IMPLEMENTED)
├── models/
│   ├── common.py            # Common models (existing)
│   ├── trading.py           # TradingPair, Order (TO BE EXTENDED)
│   └── perpetual.py         # Position, FundingRate, etc. (TO BE CREATED)
└── utils/
    └── xt_signature.py      # XT signature helpers (existing from xt_perp_api.py)

tests/
├── unit/
│   └── test_exchanges/
│       ├── test_xt_spot_contract.py      # Spot contract tests (existing)
│       └── test_xt_perp_contract.py      # Perp contract tests (TO BE CREATED)
├── integration/
│   └── test_xt_perp_integration.py       # Integration tests (TO BE CREATED)
└── performance/
    └── test_xt_perp_performance.py       # Performance benchmarks (TO BE CREATED)
```

**Structure Decision**: Single project architecture (Option 1) with modular exchange adapters. XTPerpExchange 作为新的 exchange adapter 添加到现有 `src/tri_arb/exchanges/` 目录，复用现有的 models 和 utils 模块，扩展必要的数据模型以支持永续合约特性。

## Phase 0: Outline & Research

### Research Execution

**Unknowns Identified** (from Technical Context):
- ✅ API signature mechanism → Researched: Use xt_perp_api.py signature logic
- ✅ Data model extensions → Researched: Extend TradingPair/Order, add Position/FundingRate
- ✅ BaseExchange interface adaptation → Researched: Add perpetual-specific methods
- ✅ Performance optimization strategies → Researched: Connection pooling, caching
- ✅ Error handling patterns → Researched: Tenacity retry with exponential backoff
- ✅ Testing strategy → Researched: 4-tier testing (contract → unit → integration → performance)

### Research Output

**Output**: [research.md](./research.md) completed with 7 key technical decisions:

1. **API Infrastructure**: Use xt_perp_api.py signature logic, base URL `https://fapi.xt.com`
2. **Data Model Strategy**: Extend existing + create new perpetual-specific models
3. **BaseExchange Adaptation**: Add perpetual-specific methods while maintaining interface
4. **Performance Optimization**: Connection pooling (100 max), LRU caching, async/await
5. **Error Handling**: Tenacity retry (max 3 attempts, exponential backoff)
6. **Testing Strategy**: TDD 4-tier approach (contract → unit → integration → performance)
7. **Security**: HMAC-SHA256, HTTPS, input validation, no credential logging

**All NEEDS CLARIFICATION resolved**: ✅ No blocking unknowns remain

## Phase 1: Design & Contracts

### Phase 1 Execution

1. **Extract entities from feature spec** → [data-model.md](./data-model.md): ✅ DONE
   - Extended entities: TradingPair (leverage_brackets), Order (position_side, trade_action)
   - New entities: Position, FundingRate, LeverageBracket, PlanOrder, StopProfit
   - Validation rules: Leverage limits, position size constraints, price validations
   - State transitions: Order states, position lifecycle

2. **Generate API contracts** → [contracts/](./contracts/): ✅ DONE
   - [contracts/README.md](./contracts/README.md): API organization, authentication, response format
   - [contracts/trading.yaml](./contracts/trading.yaml): Trading endpoints OpenAPI spec
   - Contract coverage: 6 trading endpoints (create, cancel, detail, list, history, trades)
   - Standard REST patterns with XT-specific authentication headers

3. **Generate contract tests**: ⏳ PENDING (Phase 2 task)
   - Test file: `tests/unit/test_exchanges/test_xt_perp_contract.py`
   - Assert BaseExchange interface compliance
   - Assert perpetual-specific method signatures
   - Tests MUST FAIL until XTPerpExchange implemented

4. **Extract test scenarios** → [quickstart.md](./quickstart.md): ✅ DONE
   - User scenarios: Connect, fetch data, query account, place orders, manage positions
   - Integration test scenarios: Open long, open short, close positions, leverage adjustment
   - Quick start validation: Complete trading workflow example

5. **Update agent file** → [CLAUDE.md](../../CLAUDE.md): ✅ DONE
   - Executed: `.specify/scripts/bash/update-agent-context.sh claude`
   - Added Feature 008 section with technical stack, patterns, pitfalls
   - Preserved manual additions for Feature 002 and Feature 005
   - Updated recent changes section

### Phase 1 Output Summary

**Deliverables**: ✅ All complete
- ✅ data-model.md (7 models, 40+ fields, validation rules)
- ✅ contracts/README.md + contracts/trading.yaml (6 endpoints)
- ✅ quickstart.md (complete user guide with examples)
- ✅ CLAUDE.md updated (Feature 008 section added)

**Constitution Re-check**: ✅ PASS
- Design follows existing architecture patterns
- Extends without modifying core abstractions
- Maintains separation of concerns
- No new violations introduced

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

### Task Generation Strategy

**Input Sources**:
1. Load `.specify/templates/tasks-template.md` as structural base
2. Extract tasks from [data-model.md](./data-model.md) (7 models to implement)
3. Extract tasks from [contracts/trading.yaml](./contracts/trading.yaml) (6 endpoints)
4. Extract tasks from [quickstart.md](./quickstart.md) (integration scenarios)
5. Extract tasks from [research.md](./research.md) (technical decisions to implement)

**Task Categories**:

1. **Contract Tests** (TDD Priority 1): [P]
   - Task: Create `test_xt_perp_contract.py` with BaseExchange interface tests
   - Expected: Tests MUST FAIL until implementation

2. **Data Models** (Foundation): [P]
   - Task: Extend TradingPair model with perpetual fields
   - Task: Extend Order model with position_side and trade_action
   - Task: Create Position model
   - Task: Create FundingRate model
   - Task: Create LeverageBracket model
   - Task: Create PlanOrder model
   - Task: Create StopProfit model

3. **Core Adapter** (Sequential dependency):
   - Task: Create XTPerpExchange class skeleton
   - Task: Implement connect() and disconnect() methods
   - Task: Implement signature generation helper
   - Task: Implement HTTP client with connection pooling

4. **Market Data Methods** (Can parallelize): [P]
   - Task: Implement get_ticker() method
   - Task: Implement get_orderbook() method
   - Task: Implement get_funding_rate() method

5. **Account Methods** (Can parallelize): [P]
   - Task: Implement get_balance() method
   - Task: Implement get_positions() method

6. **Trading Methods** (Sequential dependency):
   - Task: Implement place_order() method
   - Task: Implement cancel_order() method
   - Task: Implement get_order() method
   - Task: Implement cancel_all_orders() method

7. **Leverage Management**: [P]
   - Task: Implement set_leverage() method
   - Task: Implement get_trading_pair_info() with leverage brackets

8. **Unit Tests** (Parallel with implementation): [P]
   - Task: Unit tests for signature generation
   - Task: Unit tests for position tracking
   - Task: Unit tests for leverage validation
   - Task: Unit tests for order type conversion

9. **Integration Tests** (After implementation):
   - Task: Create integration test suite
   - Task: Test real API calls (requires credentials)
   - Task: Test order lifecycle (place → fill → query → cancel)
   - Task: Test position lifecycle (open → modify → close)

10. **Performance Tests** (Final validation):
    - Task: Benchmark order submission latency (<50ms p95)
    - Task: Benchmark position query latency (<100ms p95)
    - Task: Benchmark price processing (<10ms p95)

### Ordering Strategy

**Phase A: Foundation** (TDD first)
1. Contract tests (MUST be created and MUST FAIL)
2. Data models (parallel implementation)

**Phase B: Core Infrastructure** (Sequential)
1. XTPerpExchange skeleton
2. Connection management
3. Signature generation
4. HTTP client setup

**Phase C: Method Implementation** (Parallel where possible)
1. Market data methods [P]
2. Account methods [P]
3. Trading methods (sequential dependency within group)
4. Leverage management [P]

**Phase D: Testing** (Parallel with implementation)
1. Unit tests [P]
2. Integration tests (after implementation)
3. Performance tests (final validation)

**Parallelization Markers**:
- [P] = Can be executed in parallel (independent files/modules)
- No marker = Sequential dependency (must complete previous task first)

### Estimated Output

**Task Count**: 30-35 numbered, dependency-ordered tasks in tasks.md

**Estimated Breakdown**:
- Contract tests: 1 task
- Data models: 7 tasks [P]
- Core adapter: 4 tasks (sequential)
- Market data: 3 tasks [P]
- Account: 2 tasks [P]
- Trading: 4 tasks (sequential)
- Leverage: 2 tasks [P]
- Unit tests: 4 tasks [P]
- Integration tests: 4 tasks
- Performance tests: 3 tasks

**Total**: ~34 tasks with clear dependencies and parallelization opportunities

**IMPORTANT**: This phase is executed by the `/tasks` command, NOT by `/plan`

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution
- Command: `/tasks` creates tasks.md with 30-35 ordered tasks
- Execution: Manual or automated task execution
- Validation: Each task validated before moving to next

**Phase 4**: Implementation
- Execute tasks.md following TDD workflow
- Contract tests fail → Implement → Tests pass
- Continuous validation at each step
- Follow constitutional principles (SOLID, DRY, KISS)

**Phase 5**: Validation
- Run all tests (contract, unit, integration, performance)
- Execute quickstart.md scenarios
- Validate performance targets (<50ms p95, <100ms p95, <10ms p95)
- Integration testing with real XT perpetual API
- Documentation review and updates

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

**No violations**: This feature follows all constitutional principles:
- ✅ TDD approach (tests before implementation)
- ✅ Extends existing patterns (BaseExchange)
- ✅ No premature optimization
- ✅ SOLID principles maintained
- ✅ Clear separation of concerns

*No complexity deviations to document*

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
- [x] Complexity deviations documented (N/A - no deviations)

**Deliverables Status**:
- [x] spec.md created (51 functional requirements)
- [x] research.md created (7 technical decisions)
- [x] data-model.md created (7 models)
- [x] contracts/README.md created (API organization)
- [x] contracts/trading.yaml created (6 endpoints)
- [x] quickstart.md created (user guide)
- [x] CLAUDE.md updated (Feature 008 section)
- [x] plan.md completed (this file)
- [ ] tasks.md (awaiting /tasks command)

**Ready for Next Command**: ✅ `/tasks` command can now be executed

---
*Based on Constitution v2.1.1 - See `.specify/memory/constitution.md`*
*Generated by Claude Code on 2025-10-11*
