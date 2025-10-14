# Implementation Plan: XT 交易所统一 CLI 工具 (CEXTools)

**Branch**: `009-xt-perp-api` | **Date**: 2025-10-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/009-xt-perp-api/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path ✓
2. Fill Technical Context ✓
3. Fill Constitution Check section ✓
4. Evaluate Constitution Check → PASS ✓
5. Execute Phase 0 → research.md (in progress)
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, CLAUDE.md
7. Re-evaluate Constitution Check
8. Plan Phase 2 → Describe task generation approach
9. STOP - Ready for /tasks command
```

## Summary
基于现有的 XTSpotExchange 和 XTPerpExchange API 实现，创建统一的 `cextools` CLI 工具，支持通过 `--exchange-type` 参数在现货和永续合约之间切换。实现账户查询、市场行情、订单管理和杠杆设置四大功能模块，使用 Typer 框架和 Rich 库提供友好的命令行交互体验。

## Technical Context
**Language/Version**: Python 3.11+ (项目标准)
**Primary Dependencies**: typer (CLI框架), rich (终端UI), httpx (已有), pydantic (已有), structlog (已有)
**Storage**: N/A (无状态CLI工具)
**Testing**: pytest + pytest-asyncio (项目标准)
**Target Platform**: Linux, macOS, Windows (跨平台CLI)
**Project Type**: single (CLI扩展，集成到现有项目)
**Performance Goals**: 命令响应 <2s (不含网络), 表格渲染 <100ms
**Constraints**: 使用现有的 XTSpotExchange 和 XTPerpExchange，不修改交易所适配器
**Scale/Scope**: 4个命令组 (account/market/order/leverage)，约15个子命令

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Type Safety & Error Handling ✅
- **Status**: PASS
- **Evidence**: CLI commands 使用 Typer 的类型注解，API 调用复用已验证的 XTSpotExchange/XTPerpExchange（已有完整类型覆盖）
- **Actions**: 为 CLI 命令参数添加完整类型注解，使用 pydantic 验证用户输入

### Test-Driven Development ✅
- **Status**: PASS
- **Evidence**: 将编写 contract tests 验证 CLI 命令行为，integration tests 验证与交易所适配器集成
- **Actions**: Phase 1 生成 contract tests（测试 CLI 参数解析和命令路由），Phase 2 实现前测试必须失败

### Performance-First Architecture ✅
- **Status**: PASS
- **Evidence**: CLI 工具复用已优化的异步 API 适配器，无新的 I/O 路径
- **Targets**: 命令响应 <2s（主要是网络延迟），表格渲染 <100ms
- **Actions**: 使用 Rich 的高效表格渲染，避免不必要的数据转换

### Observability & Audit Trail ✅
- **Status**: PASS
- **Evidence**: 继承现有的 structlog 日志系统，--debug 模式显示完整 API 交互
- **Actions**: 为每个命令添加结构化日志，记录命令参数和执行结果

### Simplicity & Maintainability ✅
- **Status**: PASS
- **Evidence**: 统一的 cextools 命令结构，清晰的命令组划分，不引入新的架构模式
- **YAGNI Check**: 只实现 spec 中定义的功能，不添加高级功能（TUI、配置文件管理等）
- **Actions**: 保持命令处理函数简单（<50行），复杂逻辑委托给交易所适配器

## Project Structure

### Documentation (this feature)
```
specs/009-xt-perp-api/
├── plan.md              # This file
├── research.md          # Phase 0 output (技术选型和最佳实践)
├── data-model.md        # Phase 1 output (CLI数据结构)
├── quickstart.md        # Phase 1 output (用户快速上手指南)
├── contracts/           # Phase 1 output (CLI contract tests)
│   ├── test_account_commands.py
│   ├── test_market_commands.py
│   ├── test_order_commands.py
│   └── test_leverage_commands.py
└── tasks.md             # Phase 2 output (/tasks command)
```

### Source Code (repository root)
```
src/tri_arb/
├── cli/
│   ├── __init__.py
│   ├── main.py              # cextools 主入口
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── account.py       # account 子命令组
│   │   ├── market.py        # market 子命令组
│   │   ├── order.py         # order 子命令组
│   │   └── leverage.py      # leverage 子命令组
│   ├── formatters/
│   │   ├── __init__.py
│   │   ├── table.py         # Rich 表格格式化
│   │   ├── json.py          # JSON 输出
│   │   └── csv.py           # CSV 输出
│   └── utils/
│       ├── __init__.py
│       ├── exchange_factory.py  # 根据 exchange-type 创建适配器
│       └── validators.py    # 输入参数验证
├── exchanges/
│   ├── xt_spot.py          # 已有 (XTSpotExchange)
│   └── xt_perp.py          # 已有 (XTPerpExchange)
└── models/
    └── cli.py              # CLI 专用数据模型 (如果需要)

tests/
├── contract/
│   └── test_cli/
│       ├── test_account_commands.py
│       ├── test_market_commands.py
│       ├── test_order_commands.py
│       └── test_leverage_commands.py
└── integration/
    └── test_cli/
        └── test_cextools_integration.py
```

**Structure Decision**: 采用 single project 结构，扩展现有的 `src/tri_arb/cli/` 目录。新增 `commands/` 子目录组织四大命令组，新增 `formatters/` 支持多种输出格式。保持与现有代码库一致的目录结构和命名规范。

## Phase 0: Outline & Research

### Research Tasks
1. **Typer Framework Best Practices**
   - 研究 Typer 的命令组织模式（主命令 + 子命令组）
   - 研究全局参数的最佳实践（--exchange-type, --debug, --output）
   - 研究参数验证和错误处理模式

2. **Rich Terminal UI Patterns**
   - 研究 Rich 的 Table 组件最佳实践（自适应宽度、颜色主题）
   - 研究实时刷新模式（watch 命令的实现）
   - 研究多种输出格式的切换机制

3. **CLI Testing Strategies**
   - 研究 Typer 应用的 contract testing 模式
   - 研究 CLI 输出的断言方式（stdout/stderr 捕获）
   - 研究 mock 外部依赖的最佳实践

4. **Exchange Type Routing**
   - 设计 exchange_factory 模式：根据 --exchange-type 创建对应的 exchange 实例
   - 研究参数验证：某些命令只支持特定 exchange-type
   - 研究错误提示的友好性

**Output**: research.md 包含以上四个主题的研究结果和决策

## Phase 1: Design & Contracts

### 1. Data Model (`data-model.md`)

从 spec 中提取的关键实体：

**CLI Command Structure**
- 主命令: `cextools`
- 全局参数: `--exchange-type`, `--debug`, `--output`, `--api-key`, `--api-secret`
- 命令组: `account`, `market`, `order`, `leverage`

**Command Groups**
- **account**: `balance`, `positions`
- **market**: `ticker`, `depth`, `funding`, `watch`
- **order**: `place`, `status`, `cancel`, `cancel-all`
- **leverage**: `set`, `info`

**Output Models**
- AccountBalanceDisplay: 币种、可用、冻结、总额
- PositionDisplay: 交易对、方向、数量、开仓价、当前价、PnL、ROE、杠杆
- TickerDisplay: 交易对、买一、卖一、最新、涨跌幅、成交量
- OrderSummary: ID、交易对、方向、类型、数量、价格、状态

### 2. API Contracts (`/contracts/`)

为每个命令组生成 contract tests：

**test_account_commands.py**
- test_account_balance_requires_exchange_type()
- test_account_balance_spot_success()
- test_account_balance_perp_success()
- test_account_positions_only_perp()
- test_account_positions_with_symbol_filter()

**test_market_commands.py**
- test_market_ticker_defaults_to_spot()
- test_market_ticker_perp_with_symbol()
- test_market_depth_requires_symbol()
- test_market_funding_only_perp()
- test_market_watch_real_time_updates()

**test_order_commands.py**
- test_order_place_requires_exchange_type()
- test_order_place_perp_requires_position_side()
- test_order_place_limit_requires_price()
- test_order_status_by_order_id()
- test_order_cancel_all_with_confirmation()

**test_leverage_commands.py**
- test_leverage_set_only_perp()
- test_leverage_set_validates_range()
- test_leverage_info_shows_current_and_range()

### 3. Quickstart (`quickstart.md`)

用户快速上手指南，包含：
- 环境变量配置（XT_API_KEY, XT_PERP_API_KEY 等）
- 基础命令示例（查询余额、查看价格、下单）
- 常见错误排查（凭证未配置、交易对不存在等）

### 4. Update CLAUDE.md

执行 `.specify/scripts/bash/update-agent-context.sh claude`，添加：
- 新技术栈: typer, rich
- 项目结构: src/tri_arb/cli/ 扩展
- 最近变更: 009-xt-perp-api - 统一 CLI 工具

**Output**: data-model.md, /contracts/test_*.py (failing tests), quickstart.md, CLAUDE.md updated

## Phase 2: Task Planning Approach

**Task Generation Strategy**:
按 TDD 顺序生成任务，从 Phase 1 的设计文档提取：

1. **Setup Tasks** (2 tasks)
   - 安装依赖: typer, rich
   - 创建基础目录结构

2. **Contract Test Tasks** (4 tasks, [P] parallel)
   - 编写 test_account_commands.py
   - 编写 test_market_commands.py
   - 编写 test_order_commands.py
   - 编写 test_leverage_commands.py

3. **Core Infrastructure Tasks** (3 tasks)
   - 实现 exchange_factory (路由 spot/perp)
   - 实现 formatters (table/json/csv)
   - 实现 validators (参数验证)

4. **Command Implementation Tasks** (4 tasks)
   - 实现 account 命令组
   - 实现 market 命令组
   - 实现 order 命令组
   - 实现 leverage 命令组

5. **Integration Tasks** (2 tasks)
   - 集成到主 CLI (cextools 入口)
   - 编写 integration tests

6. **Documentation Tasks** (1 task)
   - 完善 quickstart.md 和用户文档

**Ordering Strategy**:
- Contract tests 优先（Phase 1 输出，必须失败）
- Infrastructure before commands（factory, formatters, validators 先行）
- Commands 可并行实现（独立模块）
- Integration 最后（依赖所有命令完成）

**Estimated Output**: 16 tasks in tasks.md

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)
**Phase 4**: Implementation (execute tasks.md following TDD)
**Phase 5**: Validation (run all tests, execute quickstart.md, performance benchmarks)

## Complexity Tracking
*No violations - all Constitution checks PASS*

N/A

## Progress Tracking

**Phase Status**:
- [x] Phase 0: Research complete (research.md generated)
- [x] Phase 1: Design complete (data-model.md, contracts/*, quickstart.md, CLAUDE.md updated)
- [x] Phase 2: Task planning complete (described approach in plan.md)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (N/A)

**Deliverables**:
- [x] research.md: Typer, Rich, testing strategies, exchange routing
- [x] data-model.md: CLI structure, parameters, output models
- [x] contracts/test_*.py: 4 contract test files (account, market, order, leverage)
- [x] quickstart.md: User guide with examples and troubleshooting
- [x] CLAUDE.md: Updated with typer, rich, CLI structure

**Ready for**: /tasks command to generate tasks.md

---
*Based on Constitution v1.0.0 - See `.specify/memory/constitution.md`*
