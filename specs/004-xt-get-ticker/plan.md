
# Implementation Plan: 三角套利机会监测系统

**Branch**: `004-xt-get-ticker` | **Date**: 2025-10-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-xt-get-ticker/spec.md`

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
集成 XT 交易所的 get_ticker 批量接口，实时监测三角套利机会（如 USDT→BTC→ETH→USDT），计算预期收益率并筛选符合盈利阈值的机会打印到控制台。系统支持单次查询和实时监控两种模式，仅提供信息不自动执行交易。技术方案：基于 Feature 003 的批量价格查询，使用图算法发现三角路径，异步计算收益率，通过结构化日志和彩色控制台输出结果。

## Technical Context
**Language/Version**: Python 3.11+ (required for performance and modern typing)
**Primary Dependencies**: httpx (async HTTP), pydantic (validation), structlog (logging), colorama/rich (彩色输出), typer (CLI), asyncio (异步)
**Storage**: N/A (无持久化，仅内存计算和实时输出)
**Testing**: pytest + pytest-asyncio (异步测试), pytest-benchmark (性能测试)
**Target Platform**: Linux/macOS server (命令行工具)
**Project Type**: single (单体 Python 项目)
**Performance Goals**: 全市场扫描 <1s (NFR-001), 处理 ≥500 交易对 (NFR-002)
**Constraints**: 内存使用 <100MB (NFR-003), 网络失败自动重试 ≤3 次 (NFR-005), 三角路径限制为 3 环节
**Scale/Scope**: 监控 XT 交易所所有交易对，支持基础货币白名单筛选，盈利阈值可配置
## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Type Safety & Error Handling (NON-NEGOTIABLE)
- [x] **Mandatory type annotations**: ArbitrageOpportunity, TradingPath, MarketPrice 等所有数据模型使用 Pydantic
- [x] **Comprehensive exception handling**: 网络失败、价格无效、路径计算异常均有具体异常类型
- [x] **Input validation**: 配置参数（盈利阈值、手续费率、刷新间隔）在启动时验证 (FR-018)
- [x] **Immutable data structures**: 使用 Pydantic frozen models 保证价格数据不可变
- [x] **Null safety**: Optional 类型处理缺失市场数据 (FR-002)

### II. Test-Driven Development (NON-NEGOTIABLE)
- [x] **TDD strictly enforced**: 所有功能先写失败测试，用户审批后实现
- [x] **Contract tests**: 验证与 Feature 003 get_ticker() 的集成契约
- [x] **Integration tests**: 完整套利监测流程测试（获取价格→计算路径→筛选→输出）
- [x] **Performance tests**: 使用 pytest-benchmark 验证 <1s 扫描时间 (NFR-001)

### III. Performance-First Architecture
- [x] **Latency targets**: 全市场扫描 <1s (NFR-001), 单次路径计算 <10ms
- [x] **Async-first design**: 所有网络 I/O 和路径计算使用 asyncio
- [x] **Memory efficiency**: 流式处理价格数据，避免缓存所有历史价格 (NFR-003)
- [x] **Batching strategy**: 批量获取所有市场价格（Feature 003），减少 API 调用

### IV. Observability & Audit Trail
- [x] **Structured logging**: 使用 structlog 记录扫描活动、发现机会、错误 (FR-019, FR-020)
- [x] **Performance metrics**: 记录扫描时间、市场数量、机会数量
- [x] **Audit trail**: 每个套利机会包含时间戳和计算详情 (FR-010)
- [x] **Error context**: 价格无效、网络失败时记录完整上下文

### V. Simplicity & Maintainability
- [x] **YAGNI principle**: 仅支持三角套利（3环节路径），不实现更复杂路径
- [x] **Cyclomatic complexity <10**: 路径发现和收益率计算拆分为小函数
- [x] **Dependency discipline**: 最小依赖（仅新增 colorama/rich 用于彩色输出）
- [x] **Documentation**: 套利算法和收益率计算公式需详细注释

### Initial Gate Result: ✅ PASS
所有检查项符合 Constitution 要求，无需记录偏差。

## Project Structure

### Documentation (this feature)
```
specs/004-xt-get-ticker/
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
├── arbitrage/           # 新建：套利相关功能
│   ├── __init__.py
│   ├── monitor.py       # 监控主逻辑（CLI入口）
│   ├── calculator.py    # 收益率计算
│   ├── path_finder.py   # 三角路径发现算法
│   └── config.py        # 配置管理（MonitorConfig）
├── models/
│   ├── arbitrage.py     # 新建：套利数据模型
│   │                    # - ArbitrageOpportunity
│   │                    # - TradingPath
│   │                    # - MarketPrice (复用 Feature 003 Ticker)
│   └── ...
├── exchanges/
│   └── xt.py            # 已存在（Feature 002+003）

tests/
├── contract/
│   └── test_arbitrage/  # 新建：契约测试
│       ├── test_ticker_integration.py  # 验证与 get_ticker() 集成
│       └── test_path_contracts.py      # 路径计算契约
├── unit/
│   └── test_arbitrage/  # 新建：单元测试
│       ├── test_calculator.py          # 收益率计算测试
│       ├── test_path_finder.py         # 路径发现测试
│       └── test_config.py              # 配置验证测试
└── integration/
    └── test_arbitrage/  # 新建：集成测试
        ├── test_monitor_flow.py        # 完整监控流程测试
        └── test_performance.py         # 性能基准测试
```

**Structure Decision**: 单体 Python 项目（Option 1），新增 `src/tri_arb/arbitrage/` 模块用于套利功能，复用现有 `exchanges/xt.py` 的 get_ticker() 接口。测试按照 TDD 原则组织为契约测试、单元测试和集成测试三层。

## Phase 0: Outline & Research

1. **Extract unknowns from Technical Context** above:
   - ✅ 三角套利算法选择 → 图遍历 + DFS
   - ✅ 收益率计算公式 → 链式乘法 + 手续费扣除
   - ✅ 彩色输出库选择 → rich（表格 + 彩色）
   - ✅ 异步处理策略 → 单次批量获取 + 流式处理
   - ✅ 性能优化策略 → 内存 <1MB，计算 <50ms

2. **Research完成状态**:
   - ✅ 所有技术决策已记录在 research.md
   - ✅ 无 NEEDS CLARIFICATION 残留
   - ✅ 依赖更新：新增 rich (>=13.0.0)

3. **Output**: ✅ research.md (已生成)

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

**执行状态**: ✅ COMPLETED

1. ✅ **Extract entities from feature spec** → `data-model.md`:
   - MonitorConfig, TradingPath, ArbitrageOpportunity
   - 复用 Feature 003 Ticker（MarketPrice）
   - 所有验证规则和关系已定义

2. ✅ **Generate API contracts** → `contracts/monitor_api.md`:
   - CLI contract: `tri-arb monitor` 命令
   - Python API: `ArbitrageMonitor` 类
   - 内部函数: `find_arbitrage_paths()`, `calculate_profit_rate()`
   - 错误处理契约和重试策略

3. ✅ **Generate contract tests** (需在 /tasks 命令中生成):
   - tests/contract/test_arbitrage/test_monitor_contracts.py
   - tests/contract/test_arbitrage/test_path_finder_contracts.py
   - tests/contract/test_arbitrage/test_calculator_contracts.py
   - 所有测试必须失败（未实现）

4. ✅ **Extract test scenarios** → `quickstart.md`:
   - 8 个场景 + 性能验证 + Python API 测试
   - 覆盖所有 FR 和 NFR

5. ✅ **Update agent file** → `CLAUDE.md`:
   - 新增 Python 3.11+ + rich 依赖
   - 更新 recent changes（Feature 004）

**Output**: ✅ data-model.md, contracts/, quickstart.md, CLAUDE.md (已生成)

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
1. **从 contracts/ 生成契约测试任务** (Priority 1, TDD):
   - `test_monitor_contracts.py`: 验证 ArbitrageMonitor API 契约
   - `test_ticker_integration.py`: 验证与 Feature 003 get_ticker() 集成
   - `test_path_finder_contracts.py`: 验证路径发现算法契约
   - `test_calculator_contracts.py`: 验证收益率计算契约
   - 每个契约测试 1 个任务，标记 [P] 并发执行

2. **从 data-model.md 生成模型创建任务** (Priority 2):
   - `models/arbitrage.py`: ArbitrageOpportunity, TradingPath
   - `arbitrage/config.py`: MonitorConfig
   - 2 个任务，标记 [P] 并发执行

3. **从 contracts/ 生成核心算法实现任务** (Priority 3, 依赖模型):
   - `arbitrage/path_finder.py`: find_arbitrage_paths()
   - `arbitrage/calculator.py`: calculate_profit_rate()
   - 2 个任务，标记 [P] 并发执行

4. **从 contracts/ 生成监控器实现任务** (Priority 4, 依赖算法):
   - `arbitrage/monitor.py`: ArbitrageMonitor 类
   - 1 个任务

5. **从 quickstart.md 生成集成测试任务** (Priority 5, 依赖监控器):
   - `test_monitor_flow.py`: 场景 1-8 端到端测试
   - `test_performance.py`: NFR-001, 002, 003 性能验证
   - 2 个任务，标记 [P] 并发执行

6. **CLI 入口任务** (Priority 6, 最后):
   - 集成 `tri-arb monitor` 命令到 typer CLI
   - 1 个任务

**Ordering Strategy**:
- TDD 顺序: 契约测试 → 模型 → 算法 → 监控器 → 集成测试 → CLI
- 依赖顺序: 模型先于算法，算法先于监控器
- 并发标记: 独立文件标记 [P]（契约测试、模型、算法、集成测试）

**Estimated Output**: ~15 任务（4 契约测试 + 2 模型 + 2 算法 + 1 监控器 + 2 集成测试 + 1 CLI + 3 文档/验证）

**IMPORTANT**: 此阶段由 /tasks 命令执行，/plan 命令在此停止。

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

无偏差。所有检查项通过。

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [x] Phase 3: Tasks generated (/tasks command) - 22 tasks
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (无偏差)

**Artifacts Generated**:
- [x] plan.md (此文件)
- [x] research.md (Phase 0)
- [x] data-model.md (Phase 1)
- [x] contracts/monitor_api.md (Phase 1)
- [x] quickstart.md (Phase 1)
- [x] CLAUDE.md updated (Phase 1)
- [x] tasks.md (Phase 3) - 22 任务

---

## Next Steps

**Ready for implementation**:
```bash
# 开始实现（按 TDD 顺序）
# Wave 1: Setup
Task: T001-T002 (创建目录结构 + 依赖)

# Wave 2: Contract Tests (必须先失败)
Task: T003-T006 (并发执行契约测试)

# Wave 3-7: Implementation + Tests
# 详见 tasks.md
```

**Branch Status**: `004-xt-get-ticker` (已创建)
**Spec Files**: `/Users/harry/code/quants/tri-arb/specs/004-xt-get-ticker/`
**Tasks**: 22 任务（Setup: 2, Tests: 4, Core: 9, Integration: 2, Polish: 5）

---
*Based on Constitution v1.0.0 - See `.specify/memory/constitution.md`*
*Phase 0-2 completed: 2025-10-06*
*Phase 3 completed: 2025-10-06 (tasks.md generated)*
