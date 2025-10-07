# Tasks: 三角套利机会监测系统

**Feature**: 004-xt-get-ticker
**Input**: Design documents from `/specs/004-xt-get-ticker/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/monitor_api.md

---

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions
- All paths relative to repository root: `/Users/harry/code/quants/tri-arb/`

---

## Phase 3.1: Setup

- [ ] **T001** 创建 arbitrage 模块目录结构
  - 创建 `src/tri_arb/arbitrage/` 目录
  - 创建 `src/tri_arb/arbitrage/__init__.py`
  - 创建 `tests/contract/test_arbitrage/` 目录
  - 创建 `tests/unit/test_arbitrage/` 目录
  - 创建 `tests/integration/test_arbitrage/` 目录
  - **Files**: 目录创建，无代码

- [ ] **T002** [P] 添加 rich 依赖到 pyproject.toml
  - 在 `pyproject.toml` 的 dependencies 中添加 `rich>=13.0.0`
  - 运行 `uv pip install -e ".[dev]"` 验证安装
  - **Files**: `pyproject.toml`
  - **Validation**: `uv run python -c "import rich; print(rich.__version__)"`

---

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3

**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

- [ ] **T003** [P] Contract test: ArbitrageMonitor API
  - 文件: `tests/contract/test_arbitrage/test_monitor_contracts.py`
  - 测试 `ArbitrageMonitor.scan_once()` 契约:
    - 返回列表按 `expected_profit_rate` 降序排序
    - 所有机会 `profit_rate >= min_profit_threshold`
    - 空结果返回 `[]` 不抛异常
    - 完成时间 < 1秒
  - 测试 `ArbitrageMonitor.scan_realtime()` 契约:
    - 每隔 `refresh_interval_seconds` 执行扫描
    - 监听 SIGINT 优雅退出
    - 内存稳定 <100MB
  - **Must FAIL**: ArbitrageMonitor 未实现
  - **Dependencies**: 需要 MonitorConfig, ArbitrageOpportunity 模型（T007, T008）

- [ ] **T004** [P] Contract test: Feature 003 集成
  - 文件: `tests/contract/test_arbitrage/test_ticker_integration.py`
  - 测试与 `exchange.get_ticker()` 的集成:
    - 调用 `get_ticker(None)` 返回所有市场
    - 过滤无效价格 (`bid > ask`, `price <= 0`)
    - 网络失败重试 3 次（指数退避 1s, 2s, 4s）
  - Mock XT Exchange 返回测试数据
  - **Must FAIL**: 集成逻辑未实现
  - **Dependencies**: 依赖 Feature 003 的 XTExchange

- [ ] **T005** [P] Contract test: 路径发现算法
  - 文件: `tests/contract/test_arbitrage/test_path_finder_contracts.py`
  - 测试 `find_arbitrage_paths()` 契约:
    - 输入: 500 个 Ticker 对象
    - 输出: 所有闭环三角路径（`is_closed_loop == True`）
    - 性能: 处理 500 交易对 < 100ms
    - 白名单: 只返回 `start_currency` 在白名单的路径
  - 测试用例:
    - 3 个货币形成 1 条路径: USDT→BTC→ETH→USDT
    - 无闭环路径返回 `[]`
    - 空 Ticker 列表抛 `ValueError`
  - **Must FAIL**: find_arbitrage_paths() 未实现
  - **Dependencies**: 需要 TradingPath 模型（T008）

- [ ] **T006** [P] Contract test: 收益率计算
  - 文件: `tests/contract/test_arbitrage/test_calculator_contracts.py`
  - 测试 `calculate_profit_rate()` 契约:
    - 计算公式: `最终金额 = 初始 × p1 × p2 × p3 × (1-fee)³`
    - 收益率: `(最终 - 初始) / 初始 × 100`
    - 精度: 使用 `Decimal` 类型
    - 性能: 单次计算 < 10ms
  - 测试用例:
    - 正收益路径: 1000 USDT → 1012.5 USDT (1.25%)
    - 负收益路径: 1000 USDT → 998 USDT (-0.2%)
    - 缺失交易对抛 `KeyError`
  - **Must FAIL**: calculate_profit_rate() 未实现
  - **Dependencies**: 需要 TradingPath 模型（T008）

---

## Phase 3.3: Core Implementation (ONLY after T003-T006 are FAILING)

- [ ] **T007** [P] 实现 MonitorConfig 数据模型
  - 文件: `src/tri_arb/arbitrage/config.py`
  - 实现 Pydantic model（frozen=True）:
    - `min_profit_threshold: float = Field(default=0.5, ge=0.0, le=100.0)`
    - `fee_rate_per_trade: float = Field(default=0.1, ge=0.0, le=10.0)`
    - `base_currency_whitelist: list[str] = Field(default_factory=list)`
    - `refresh_interval_seconds: int = Field(default=10, ge=1, le=3600)`
    - `run_mode: str = Field(default="once", pattern="^(once|realtime)$")`
  - Validator: `base_currency_whitelist` 每个货币大写字母
  - **Validation**: `MonitorConfig()` 创建默认配置成功
  - **Validation**: `MonitorConfig(min_profit_threshold=150)` 抛 ValidationError

- [ ] **T008** [P] 实现 TradingPath 和 ArbitrageOpportunity 模型
  - 文件: `src/tri_arb/models/arbitrage.py`
  - 实现 `TradingPath`（frozen=True）:
    - `start_currency: str`
    - `trading_pairs: tuple[str, str, str]`
    - `@property is_closed_loop() -> bool`: 验证闭环
  - 实现 `ArbitrageOpportunity`:
    - `path: TradingPath`
    - `expected_profit_rate: Decimal`
    - `prices: list[dict]` (长度=3)
    - `recommended_amount: Decimal`
    - `discovered_at: datetime`
    - `status: str = "new"` (enum: new/printed/expired)
  - Validators: 验证 prices 长度和结构
  - **Validation**: 创建测试对象成功，验证失败数据抛异常

- [ ] **T009** [P] 实现路径发现算法
  - 文件: `src/tri_arb/arbitrage/path_finder.py`
  - 实现 `find_arbitrage_paths(tickers, base_currencies)`:
    - 构建货币邻接图: `dict[str, set[str]]`
    - DFS 深度限制为 3
    - 过滤非闭环路径
    - 白名单筛选
  - 辅助函数:
    - `_build_currency_graph(tickers) -> dict`
    - `_dfs_find_paths(graph, start, depth) -> list[TradingPath]`
    - `_is_closed_loop(path) -> bool`
  - **Validation**: T005 契约测试通过
  - **Performance**: 处理 500 交易对 < 100ms (pytest-benchmark)
  - **Dependencies**: 依赖 T008 (TradingPath)

- [ ] **T010** [P] 实现收益率计算器
  - 文件: `src/tri_arb/arbitrage/calculator.py`
  - 实现 `calculate_profit_rate(path, tickers, fee_rate)`:
    - 解析路径中的交易方向（buy/sell）
    - 选择对应价格（ask for buy, bid for sell）
    - 链式乘法计算最终金额
    - 扣除 3 次手续费: `(1 - fee_rate)³`
    - 返回 `(收益率%, 价格详情列表)`
  - 使用 `Decimal` 类型保证精度
  - 辅助函数:
    - `_parse_trade_direction(pair, path) -> str`
    - `_get_price(ticker, direction) -> Decimal`
  - **Validation**: T006 契约测试通过
  - **Performance**: 单次计算 < 10ms (pytest-benchmark)
  - **Dependencies**: 依赖 T008 (TradingPath)

- [ ] **T011** 实现 ArbitrageMonitor 核心逻辑
  - 文件: `src/tri_arb/arbitrage/monitor.py`
  - 实现 `ArbitrageMonitor` 类:
    - `__init__(config, exchange_name)`
    - `async scan_once() -> list[ArbitrageOpportunity]`:
      - 调用 `exchange.get_ticker(None)`
      - 过滤无效价格（调用 `_filter_valid_tickers`）
      - 调用 `find_arbitrage_paths`
      - 并发计算收益率（`asyncio.gather`）
      - 筛选 + 排序（降序）
      - 返回结果
    - `async scan_realtime() -> AsyncGenerator`:
      - 循环调用 `scan_once()`
      - `asyncio.sleep(refresh_interval)`
      - 监听 SIGINT/SIGTERM 信号
  - 异常处理:
    - 网络失败重试 3 次（指数退避）
    - 价格无效记录警告继续
  - 结构化日志（structlog）
  - **Validation**: T003, T004 契约测试通过
  - **Dependencies**: 依赖 T007 (MonitorConfig), T008 (模型), T009 (path_finder), T010 (calculator)

- [ ] **T012** 导出 arbitrage 模块 API
  - 文件: `src/tri_arb/arbitrage/__init__.py`
  - 导出:
    - `from .monitor import ArbitrageMonitor`
    - `from .config import MonitorConfig`
    - `from .path_finder import find_arbitrage_paths`
    - `from .calculator import calculate_profit_rate`
  - 定义 `__all__`
  - **Validation**: `from tri_arb.arbitrage import ArbitrageMonitor` 成功

---

## Phase 3.4: Integration

- [ ] **T013** [P] 集成测试: 完整监控流程
  - 文件: `tests/integration/test_arbitrage/test_monitor_flow.py`
  - 测试场景（基于 quickstart.md）:
    - 场景 1: 单次扫描默认配置
    - 场景 2: 自定义盈利阈值（1%）
    - 场景 3: 基础货币白名单（USDT）
    - 场景 4: 实时监控 5 秒间隔（运行 20 秒后停止）
    - 场景 5: 调试模式记录所有路径
    - 场景 8.1: 没有套利机会（极高阈值 50%）
    - 场景 8.2: 价格数据无效（mock bid > ask）
  - Mock XT Exchange 返回测试数据（500 个 Ticker）
  - 验证输出格式、排序、筛选逻辑
  - **Dependencies**: 依赖 T011 (ArbitrageMonitor)

- [ ] **T014** [P] 性能基准测试
  - 文件: `tests/integration/test_arbitrage/test_performance.py`
  - 使用 pytest-benchmark 测试:
    - NFR-001: 全市场扫描 < 1s
    - NFR-002: 处理 ≥500 交易对
    - NFR-003: 内存使用 <100MB（实时监控 5 分钟）
  - 测试数据:
    - 500 个有效 Ticker
    - 预期发现 10-20 条套利路径
  - 内存监控: 使用 `memory_profiler` 或 `tracemalloc`
  - **Dependencies**: 依赖 T011 (ArbitrageMonitor)

- [ ] **T015** 实现 CLI 命令 `tri-arb monitor`
  - 文件: `src/tri_arb/cli/monitor.py` (新建)
  - 使用 Typer 实现命令:
    ```python
    @app.command()
    def monitor(
        min_profit: float = 0.5,
        fee_rate: float = 0.1,
        base_currencies: str = "",
        refresh_interval: int = 10,
        mode: str = "once",
        debug: bool = False
    ):
    ```
  - 参数解析:
    - `base_currencies` 逗号分隔 → `list[str]`
    - 创建 `MonitorConfig` 对象
  - 调用 `ArbitrageMonitor`:
    - 单次模式: `await monitor.scan_once()`
    - 实时模式: `async for opps in monitor.scan_realtime()`
  - 输出格式化（使用 rich.table.Table）:
    - 彩色表格显示机会列表
    - 详细信息（路径、价格、建议金额）
  - 信号处理: 捕获 SIGINT/SIGTERM
  - 退出码: 0/1/2/130
  - **Validation**: 场景 1-8 手动测试通过（quickstart.md）
  - **Dependencies**: 依赖 T011 (ArbitrageMonitor), T012 (API 导出)

- [ ] **T016** 集成 CLI 命令到主入口
  - 文件: `src/tri_arb/cli/__init__.py` 或 `src/tri_arb/__main__.py`
  - 注册 `monitor` 命令到 Typer app
  - 确保 `tri-arb monitor` 可执行
  - **Validation**: `tri-arb monitor --help` 显示帮助
  - **Dependencies**: 依赖 T015 (monitor CLI)

---

## Phase 3.5: Polish

- [ ] **T017** [P] 单元测试: 配置验证
  - 文件: `tests/unit/test_arbitrage/test_config.py`
  - 测试 MonitorConfig 验证规则:
    - 有效配置创建成功
    - 无效阈值（<0, >100）抛异常
    - 无效手续费率（<0, >10）抛异常
    - 无效运行模式抛异常
    - 无效刷新间隔（<1, >3600）抛异常
    - 白名单货币非大写抛异常
  - **Dependencies**: 依赖 T007 (MonitorConfig)

- [ ] **T018** [P] 单元测试: 路径发现算法
  - 文件: `tests/unit/test_arbitrage/test_path_finder.py`
  - 测试边界情况:
    - 空 Ticker 列表
    - 单个交易对（无法形成三角）
    - 两个货币（无法形成闭环）
    - 多条路径排序
    - 白名单过滤
  - **Dependencies**: 依赖 T009 (path_finder)

- [ ] **T019** [P] 单元测试: 收益率计算
  - 文件: `tests/unit/test_arbitrage/test_calculator.py`
  - 测试精度和边界:
    - Decimal 精度保证（与 float 对比）
    - 零手续费情况
    - 极高手续费（接近 10%）
    - 价格为 0 或负数处理
    - 交易对缺失处理
  - **Dependencies**: 依赖 T010 (calculator)

- [ ] **T020** 更新项目文档
  - 文件: `CLAUDE.md` (已更新), `README.md`, `specs/004-xt-get-ticker/quickstart.md`
  - 添加到 README:
    - 三角套利监控功能说明
    - `tri-arb monitor` 命令用法
    - 示例输出
  - 验证 quickstart.md 所有场景可执行
  - **Dependencies**: 依赖 T015 (CLI 实现)

- [ ] **T021** 代码质量检查
  - 运行 `ruff check src/tri_arb/arbitrage/`
  - 运行 `mypy src/tri_arb/arbitrage/ --strict`
  - 修复所有 lint 和类型错误
  - 确保循环复杂度 <10（使用 `radon cc`）
  - **Dependencies**: 依赖所有实现任务（T007-T016）

- [ ] **T022** 运行完整测试套件
  - 契约测试: `pytest tests/contract/test_arbitrage/ -v`
  - 单元测试: `pytest tests/unit/test_arbitrage/ -v`
  - 集成测试: `pytest tests/integration/test_arbitrage/ -v`
  - 性能测试: `pytest tests/integration/test_arbitrage/test_performance.py --benchmark-only`
  - 测试覆盖率: `pytest --cov=src/tri_arb/arbitrage --cov-report=term-missing`
  - **Target**: 覆盖率 ≥90% 核心逻辑，≥80% 整体
  - **Dependencies**: 依赖所有测试任务（T003-T006, T013-T014, T017-T019）

---

## Dependencies

### Critical Path (TDD)
```
Setup (T001-T002) → Tests (T003-T006) → Implementation (T007-T016) → Polish (T017-T022)
```

### Detailed Dependencies
- **T003-T006** (契约测试): 独立并发 [P]，但依赖部分模型类型定义
- **T007-T008** (模型): 独立并发 [P]
- **T009-T010** (算法): 依赖 T008，可并发 [P]
- **T011** (监控器): 依赖 T007, T008, T009, T010
- **T012** (导出): 依赖 T011
- **T013-T014** (集成测试): 依赖 T011，可并发 [P]
- **T015** (CLI): 依赖 T011, T012
- **T016** (CLI 集成): 依赖 T015
- **T017-T019** (单元测试): 依赖各自实现，可并发 [P]
- **T020-T022** (文档/质量): 依赖所有实现

---

## Parallel Execution Examples

### Wave 1: Setup
```bash
# T001-T002 可串行（快速）
Task: "创建 arbitrage 模块目录结构"
Task: "添加 rich 依赖到 pyproject.toml"
```

### Wave 2: Contract Tests (MUST FAIL)
```bash
# T003-T006 并发执行
Task agent 1: "Contract test ArbitrageMonitor API in tests/contract/test_arbitrage/test_monitor_contracts.py"
Task agent 2: "Contract test Feature 003 integration in tests/contract/test_arbitrage/test_ticker_integration.py"
Task agent 3: "Contract test path finder in tests/contract/test_arbitrage/test_path_finder_contracts.py"
Task agent 4: "Contract test calculator in tests/contract/test_arbitrage/test_calculator_contracts.py"
```

### Wave 3: Data Models
```bash
# T007-T008 并发执行
Task agent 1: "Implement MonitorConfig in src/tri_arb/arbitrage/config.py"
Task agent 2: "Implement TradingPath and ArbitrageOpportunity in src/tri_arb/models/arbitrage.py"
```

### Wave 4: Core Algorithms
```bash
# T009-T010 并发执行（依赖 T008）
Task agent 1: "Implement find_arbitrage_paths in src/tri_arb/arbitrage/path_finder.py"
Task agent 2: "Implement calculate_profit_rate in src/tri_arb/arbitrage/calculator.py"
```

### Wave 5: Monitor Implementation
```bash
# T011-T012 串行（T012 依赖 T011）
Task: "Implement ArbitrageMonitor in src/tri_arb/arbitrage/monitor.py"
Task: "Export arbitrage module API in src/tri_arb/arbitrage/__init__.py"
```

### Wave 6: Integration Tests
```bash
# T013-T014 并发执行
Task agent 1: "Integration test monitor flow in tests/integration/test_arbitrage/test_monitor_flow.py"
Task agent 2: "Performance benchmark tests in tests/integration/test_arbitrage/test_performance.py"
```

### Wave 7: CLI & Unit Tests
```bash
# T015 单独，T017-T019 并发
Task: "Implement CLI command tri-arb monitor in src/tri_arb/cli/monitor.py"

# 然后并发单元测试
Task agent 1: "Unit test MonitorConfig in tests/unit/test_arbitrage/test_config.py"
Task agent 2: "Unit test path_finder in tests/unit/test_arbitrage/test_path_finder.py"
Task agent 3: "Unit test calculator in tests/unit/test_arbitrage/test_calculator.py"
```

---

## Validation Checklist
*GATE: Check before marking Phase 3 complete*

- [ ] 所有契约测试（T003-T006）先失败后通过
- [ ] 所有实体模型（T007-T008）已实现并验证
- [ ] 核心算法（T009-T010）通过契约测试和性能测试
- [ ] 监控器（T011）通过所有契约和集成测试
- [ ] CLI（T015-T016）通过 quickstart.md 所有场景
- [ ] 单元测试（T017-T019）覆盖边界情况
- [ ] 代码质量（T021）: ruff + mypy + radon 通过
- [ ] 测试覆盖率（T022）: ≥90% 核心，≥80% 整体
- [ ] 性能目标（T014）: 全部达成（<1s, ≥500, <100MB）
- [ ] 文档（T020）: README 和 quickstart 已更新

---

## Notes

- **TDD 强制**: T003-T006 必须在实现前失败
- **并发优化**: 使用 [P] 标记的任务可同时执行
- **性能验证**: T014 必须在真实环境验证（不能 mock）
- **手动测试**: T015 需要运行 quickstart.md 所有 8 个场景
- **质量门禁**: T021-T022 不通过则 Feature 不完成

---

*Generated from plan.md, data-model.md, contracts/monitor_api.md*
*Based on Constitution v1.0.0 TDD principles*
*Total tasks: 22 (Setup: 2, Tests: 4, Core: 9, Integration: 2, Polish: 5)*
