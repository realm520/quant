# Tasks: XT 交易所统一 CLI 工具 (CEXTools)

**Feature Branch**: `009-xt-perp-api`
**Input**: Design documents from `/Users/harry/code/quants/tri-arb/specs/009-xt-perp-api/`
**Prerequisites**: plan.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

## Execution Status
```
1. Load plan.md ✓ - Tech stack: Python 3.11+, typer, rich
2. Load design documents ✓
   - research.md: Typer patterns, Rich UI, testing strategies
   - data-model.md: 4 command groups, 15 subcommands, output models
   - contracts/: 4 test files with 40+ test cases
   - quickstart.md: User scenarios and examples
3. Generate tasks by category ✓
4. Apply task rules ✓
5. Number tasks ✓
6. Dependencies identified ✓
7. Parallel execution examples ✓
8. Ready for execution ✓
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- All paths are absolute from repository root `/Users/harry/code/quants/tri-arb/`

---

## Phase 3.1: Setup (2 tasks) ✅

### T001 - Install CLI dependencies ✅
**File**: `pyproject.toml` (update dependencies)
**Action**: 添加 typer 和 rich 依赖
```bash
uv add typer rich
```
**Verification**: `uv pip list | grep -E "(typer|rich)"`
**Dependencies**: None
**Parallel**: No (modifies single file)

### T002 - Create CLI directory structure ✅
**Files**: Create empty `__init__.py` in new directories
```
src/tri_arb/cli/
├── __init__.py
├── commands/
│   └── __init__.py
├── formatters/
│   └── __init__.py
└── utils/
    └── __init__.py
```
**Action**: 使用 `mkdir -p` 和 `touch` 创建目录结构
**Verification**: 目录和 `__init__.py` 文件存在
**Dependencies**: None
**Parallel**: No (sequential after T001)

---

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3

**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

所有契约测试已在 Phase 1 生成，位于 `specs/009-xt-perp-api/contracts/`。需要复制到项目测试目录并验证失败。

### T003 [P] - Copy and verify account commands contract tests
**Source**: `specs/009-xt-perp-api/contracts/test_account_commands.py`
**Target**: `tests/contract/test_cli/test_account_commands.py`
**Action**:
1. 创建目标目录 `tests/contract/test_cli/`
2. 复制测试文件
3. 取消 `pytest.skip`，验证测试失败（因为 CLI 未实现）
**Verification**: `pytest tests/contract/test_cli/test_account_commands.py` 应该失败
**Test Count**: 7 test cases
**Dependencies**: T002 (需要目录结构)
**Parallel**: Yes (独立文件)

### T004 [P] - Copy and verify market commands contract tests
**Source**: `specs/009-xt-perp-api/contracts/test_market_commands.py`
**Target**: `tests/contract/test_cli/test_market_commands.py`
**Action**: 复制并取消 skip，验证失败
**Verification**: `pytest tests/contract/test_cli/test_market_commands.py` 应该失败
**Test Count**: 13 test cases
**Dependencies**: T002
**Parallel**: Yes (独立文件)

### T005 [P] - Copy and verify order commands contract tests
**Source**: `specs/009-xt-perp-api/contracts/test_order_commands.py`
**Target**: `tests/contract/test_cli/test_order_commands.py`
**Action**: 复制并取消 skip，验证失败
**Verification**: `pytest tests/contract/test_cli/test_order_commands.py` 应该失败
**Test Count**: 13 test cases
**Dependencies**: T002
**Parallel**: Yes (独立文件)

### T006 [P] - Copy and verify leverage commands contract tests
**Source**: `specs/009-xt-perp-api/contracts/test_leverage_commands.py`
**Target**: `tests/contract/test_cli/test_leverage_commands.py`
**Action**: 复制并取消 skip，验证失败
**Verification**: `pytest tests/contract/test_cli/test_leverage_commands.py` 应该失败
**Test Count**: 7 test cases
**Dependencies**: T002
**Parallel**: Yes (独立文件)

---

## Phase 3.3: Core Infrastructure (ONLY after tests are failing)

**GATE**: Phase 3.2 必须完成且所有测试失败才能开始

### T007 - Implement exchange factory
**File**: `src/tri_arb/cli/utils/exchange_factory.py`
**Action**: 实现 `ExchangeType` Enum 和 `create_exchange()` 工厂函数
**Reference**: `specs/009-xt-perp-api/research.md` Section 4
**Key Features**:
- `ExchangeType` enum (SPOT, PERP)
- `create_exchange()` 根据 type 返回 XTSpotExchange 或 XTPerpExchange
- 从环境变量读取 API 凭证（XT_API_KEY/XT_PERP_API_KEY）
- 友好的错误提示
**Verification**: 单元测试 factory 逻辑
**Dependencies**: T002
**Parallel**: No (被后续任务依赖)

### T008 [P] - Implement table formatter
**File**: `src/tri_arb/cli/formatters/table.py`
**Action**: 使用 Rich 实现表格格式化
**Reference**: `specs/009-xt-perp-api/research.md` Section 2
**Key Features**:
- `format_balance_table()` - 余额表格
- `format_positions_table()` - 持仓表格
- `format_ticker_table()` - 行情表格
- `format_orderbook_table()` - 订单簿表格
- 颜色支持（盈亏红绿）
**Verification**: 单元测试各格式化函数
**Dependencies**: T001 (需要 rich)
**Parallel**: Yes (独立文件)

### T009 [P] - Implement JSON formatter
**File**: `src/tri_arb/cli/formatters/json.py`
**Action**: JSON 序列化格式化器
**Key Features**:
- `format_json()` - 通用 JSON 格式化
- Decimal 类型处理（转字符串）
- 缩进和可读性
**Verification**: 单元测试 JSON 输出
**Dependencies**: T001
**Parallel**: Yes (独立文件)

### T010 [P] - Implement CSV formatter
**File**: `src/tri_arb/cli/formatters/csv.py`
**Action**: CSV 格式化器
**Key Features**:
- `format_csv()` - 通用 CSV 格式化
- 处理表格数据
**Verification**: 单元测试 CSV 输出
**Dependencies**: T001
**Parallel**: Yes (独立文件)

### T011 [P] - Implement parameter validators ✅
**File**: `src/tri_arb/cli/utils/validators.py`
**Action**: 输入参数验证函数
**Key Features**:
- `validate_symbol()` - 验证交易对格式（BTC/USDT）
- `validate_leverage()` - 验证杠杆范围（1-125）
- `validate_interval()` - 验证刷新间隔（1-60）
- `validate_limit()` - 验证档数（5-50）
**Verification**: 单元测试各验证函数
**Dependencies**: T001
**Parallel**: Yes (独立文件)

---

## Phase 3.4: Command Implementation

**GATE**: T007-T011 必须完成

### T012 - Implement account commands ✅
**File**: `src/tri_arb/cli/commands/account.py`
**Action**: 实现 account 命令组（balance, positions）
**Reference**:
- `specs/009-xt-perp-api/data-model.md` Section 2 (parameters)
- `tests/contract/test_cli/test_account_commands.py` (test cases)
**Key Features**:
- `account_app = typer.Typer()` 命令组
- `@account_app.command("balance")` - 查询余额
- `@account_app.command("positions")` - 查询持仓（仅 perp）
- 参数验证（exchange-type 必须）
- 调用 exchange_factory
- 使用 formatters 输出
**Verification**: `pytest tests/contract/test_cli/test_account_commands.py` 应该通过
**Dependencies**: T007, T008, T009, T010
**Parallel**: No (依赖多个任务)

### T013 - Implement market commands ✅
**File**: `src/tri_arb/cli/commands/market.py`
**Action**: 实现 market 命令组（ticker, depth, funding, watch）
**Reference**:
- `specs/009-xt-perp-api/data-model.md` Section 2
- `tests/contract/test_cli/test_market_commands.py`
**Key Features**:
- `market_app = typer.Typer()` 命令组
- `ticker` - 查询价格（默认 spot）
- `depth` - 订单簿深度
- `funding` - 资金费率（仅 perp）
- `watch` - 实时监控（使用 Rich Live）
**Verification**: `pytest tests/contract/test_cli/test_market_commands.py` 应该通过
**Dependencies**: T007, T008, T009, T010, T011
**Parallel**: No (依赖多个任务)

### T014 - Implement order commands ✅
**File**: `src/tri_arb/cli/commands/order.py`
**Action**: 实现 order 命令组（place, status, cancel, cancel-all）
**Reference**:
- `specs/009-xt-perp-api/data-model.md` Section 2
- `tests/contract/test_cli/test_order_commands.py`
**Key Features**:
- `order_app = typer.Typer()` 命令组
- `place` - 下单（带确认）
- `status` - 查询订单状态
- `cancel` - 取消单个订单
- `cancel-all` - 批量取消（带确认）
- perp 必须 position-side
**Verification**: `pytest tests/contract/test_cli/test_order_commands.py` 应该通过
**Dependencies**: T007, T008, T009, T010, T011
**Parallel**: No

### T015 - Implement leverage commands ✅
**File**: `src/tri_arb/cli/commands/leverage.py`
**Action**: 实现 leverage 命令组（set, info）
**Reference**:
- `specs/009-xt-perp-api/data-model.md` Section 2
- `tests/contract/test_cli/test_leverage_commands.py`
**Key Features**:
- `leverage_app = typer.Typer()` 命令组
- `set` - 设置杠杆（仅 perp）
- `info` - 查询杠杆信息
- 验证 exchange-type 必须为 perp
**Verification**: `pytest tests/contract/test_cli/test_leverage_commands.py` 应该通过
**Dependencies**: T007, T008, T009, T010, T011
**Parallel**: No

---

## Phase 3.5: Integration

**GATE**: T012-T015 必须完成

### T016 - Implement CLI main entry point ✅
**File**: `src/tri_arb/cli/main.py`
**Action**: 创建 cextools 主命令，整合所有子命令组
**Reference**: `specs/009-xt-perp-api/research.md` Section 1
**Key Features**:
- `app = typer.Typer()` 主命令
- `@app.callback()` 全局参数（--debug, --output, --api-key）
- `app.add_typer(account_app, name="account")`
- `app.add_typer(market_app, name="market")`
- `app.add_typer(order_app, name="order")`
- `app.add_typer(leverage_app, name="leverage")`
- 错误处理和日志配置
**Verification**: `cextools --help` 显示所有命令组
**Dependencies**: T012, T013, T014, T015
**Parallel**: No

### T017 - Create CLI entry point script ✅
**File**: `src/tri_arb/cli/__main__.py` (或更新现有)
**Action**: 添加 cextools 命令入口
```python
if __name__ == "__main__":
    from tri_arb.cli.main import app
    app()
```
**Verification**: `python -m tri_arb.cli` 可执行
**Dependencies**: T016
**Parallel**: No

### T018 - Add CLI console script to pyproject.toml ✅
**File**: `pyproject.toml`
**Action**: 添加 console_scripts entry point
```toml
[project.scripts]
cextools = "tri_arb.cli.main:app"
```
**Verification**: `uv pip install -e .` 后 `cextools --help` 可用
**Dependencies**: T016, T017
**Parallel**: No

---

## Phase 3.6: Integration Tests

**GATE**: T016-T018 必须完成

### T019 - Integration test: account workflow
**File**: `tests/integration/test_cli/test_account_integration.py`
**Action**: 端到端测试账户查询流程
**Test Scenarios**:
- 使用 mock XTSpotExchange 测试 balance 命令
- 使用 mock XTPerpExchange 测试 positions 命令
- 验证 API 调用和格式化输出
**Reference**: `specs/009-xt-perp-api/quickstart.md` Section 2.1
**Verification**: `pytest tests/integration/test_cli/test_account_integration.py -v`
**Dependencies**: T016
**Parallel**: No (需要完整 CLI)

### T020 - Integration test: market workflow
**File**: `tests/integration/test_cli/test_market_integration.py`
**Action**: 端到端测试市场查询流程
**Test Scenarios**:
- ticker 命令（spot/perp）
- depth 命令
- funding 命令（perp only）
- watch 命令（实时刷新）
**Reference**: `specs/009-xt-perp-api/quickstart.md` Section 2.2
**Verification**: `pytest tests/integration/test_cli/test_market_integration.py -v`
**Dependencies**: T016
**Parallel**: No

### T021 - Integration test: order workflow
**File**: `tests/integration/test_cli/test_order_integration.py`
**Action**: 端到端测试订单管理流程
**Test Scenarios**:
- place 命令（spot/perp，market/limit）
- status 命令
- cancel 命令
- cancel-all 命令（带确认）
**Reference**: `specs/009-xt-perp-api/quickstart.md` Section 2.3
**Verification**: `pytest tests/integration/test_cli/test_order_integration.py -v`
**Dependencies**: T016
**Parallel**: No

---

## Phase 3.7: Polish

**GATE**: T019-T021 必须完成

### T022 [P] - Unit tests for exchange factory ✅
**File**: `tests/unit/test_cli/test_exchange_factory.py`
**Action**: 完善 exchange_factory 单元测试
**Test Coverage**:
- 测试 SPOT 和 PERP 路由
- 测试环境变量读取
- 测试错误处理（缺少凭证）
- 测试 --api-key 覆盖逻辑
**Verification**: `pytest tests/unit/test_cli/test_exchange_factory.py --cov`
**Dependencies**: T007
**Parallel**: Yes

### T023 [P] - Unit tests for formatters ✅
**File**: `tests/unit/test_cli/test_formatters.py`
**Action**: 完善 formatters 单元测试
**Test Coverage**:
- 测试 table formatter 各函数
- 测试 JSON formatter
- 测试 CSV formatter
- 测试 Decimal 序列化
**Verification**: `pytest tests/unit/test_cli/test_formatters.py --cov`
**Dependencies**: T008, T009, T010
**Parallel**: Yes

### T024 [P] - Unit tests for validators ✅
**File**: `tests/unit/test_cli/test_validators.py`
**Action**: 完善 validators 单元测试
**Test Coverage**:
- 测试 symbol 格式验证
- 测试 leverage 范围验证
- 测试 interval 范围验证
- 测试 limit 范围验证
**Verification**: `pytest tests/unit/test_cli/test_validators.py --cov`
**Dependencies**: T011
**Parallel**: Yes

### T025 - Performance validation
**Action**: 验证性能目标
**Performance Targets** (from plan.md):
- 命令响应 <2s（不含网络延迟）
- 表格渲染 <100ms
**Tests**:
```bash
# 使用 pytest-benchmark
pytest tests/performance/test_cli_performance.py
```
**Verification**: 所有性能测试通过
**Dependencies**: T016
**Parallel**: No

### T026 - Update documentation
**Files**:
- `CLAUDE.md` (已自动更新)
- `specs/009-xt-perp-api/quickstart.md` (验证示例)
**Action**:
1. 验证 quickstart.md 所有命令示例可执行
2. 添加实际输出截图（可选）
3. 更新故障排查部分
**Verification**: 手动执行 quickstart.md 所有示例
**Dependencies**: T016
**Parallel**: No

### T027 - Code quality check ✅
**Action**: 运行代码质量工具
```bash
# Type checking
mypy src/tri_arb/cli --strict

# Linting
ruff check src/tri_arb/cli

# Formatting
black src/tri_arb/cli --check
```
**Verification**: 无 type errors，无 linting violations
**Dependencies**: All implementation tasks
**Parallel**: No

---

## Dependencies Graph

```
Setup Phase:
T001 (dependencies) → T002 (structure)
                          ↓
Tests Phase:
                 T003, T004, T005, T006 [P]
                          ↓
Infrastructure Phase:
       T007 (factory) ←─────┐
            ↓                │
       T008, T009, T010, T011 [P]
            ↓                │
Commands Phase:            │
       T012, T013, T014, T015 (依赖 T007-T011)
            ↓
Integration Phase:
       T016 → T017 → T018
            ↓
Integration Tests:
       T019, T020, T021
            ↓
Polish Phase:
       T022, T023, T024 [P] → T025 → T026 → T027
```

---

## Parallel Execution Examples

### Example 1: Contract Tests (Phase 3.2)
```bash
# 在同一消息中启动 4 个并行任务：
Task: "Copy and verify account commands contract tests from specs/009-xt-perp-api/contracts/test_account_commands.py to tests/contract/test_cli/test_account_commands.py"
Task: "Copy and verify market commands contract tests from specs/009-xt-perp-api/contracts/test_market_commands.py to tests/contract/test_cli/test_market_commands.py"
Task: "Copy and verify order commands contract tests from specs/009-xt-perp-api/contracts/test_order_commands.py to tests/contract/test_cli/test_order_commands.py"
Task: "Copy and verify leverage commands contract tests from specs/009-xt-perp-api/contracts/test_leverage_commands.py to tests/contract/test_cli/test_leverage_commands.py"
```

### Example 2: Formatters (Phase 3.3)
```bash
# 3 个格式化器可并行实现：
Task: "Implement table formatter in src/tri_arb/cli/formatters/table.py using Rich"
Task: "Implement JSON formatter in src/tri_arb/cli/formatters/json.py"
Task: "Implement CSV formatter in src/tri_arb/cli/formatters/csv.py"
```

### Example 3: Unit Tests (Phase 3.7)
```bash
# 3 个单元测试可并行编写：
Task: "Write unit tests for exchange factory in tests/unit/test_cli/test_exchange_factory.py"
Task: "Write unit tests for formatters in tests/unit/test_cli/test_formatters.py"
Task: "Write unit tests for validators in tests/unit/test_cli/test_validators.py"
```

---

## Validation Checklist

**GATE: Checked before marking tasks complete**

- [x] All contracts have corresponding tests (T003-T006)
- [x] All commands have implementation tasks (T012-T015)
- [x] All tests come before implementation (Phase 3.2 before 3.3)
- [x] Parallel tasks truly independent (marked [P])
- [x] Each task specifies exact file path
- [x] No task modifies same file as another [P] task
- [x] Dependencies explicitly documented

---

## Notes

### TDD Enforcement
- **Phase 3.2 tests MUST fail** before starting Phase 3.3
- Run `pytest tests/contract/test_cli/` 验证失败
- 每完成一个命令，对应的 contract tests 应该通过

### Commit Strategy
建议每完成一个 Phase 就提交：
```bash
git add .
git commit -m "feat(cli): complete Phase 3.X - [phase description]"
```

### Testing Strategy
1. **Contract Tests**: 验证 CLI 接口契约
2. **Integration Tests**: 验证端到端流程
3. **Unit Tests**: 验证独立模块逻辑
4. **Performance Tests**: 验证性能目标

### Error Handling
所有命令必须：
- 提供友好的错误消息（非技术用户可理解）
- 在 --debug 模式显示详细错误
- 正确的退出码（0=成功，1=失败）

---

## Task Summary

**Total Tasks**: 27
- Setup: 2 tasks
- Tests: 4 tasks [P]
- Infrastructure: 5 tasks (1 sequential, 4 parallel)
- Commands: 4 tasks (sequential)
- Integration: 3 tasks (sequential)
- Integration Tests: 3 tasks (sequential)
- Polish: 6 tasks (3 parallel, 3 sequential)

**Estimated Effort**: 16-20 hours
**Critical Path**: T001 → T002 → T003-T006 → T007 → T012-T015 → T016-T018 → T019-T021 → T025-T027

---

**Ready for execution** ✓ | **All validation checks passed** ✓
