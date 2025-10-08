# Monitor API Contract

**Feature**: 004-xt-get-ticker
**Purpose**: 定义套利监控系统的公共 API 契约（CLI 和 Python API）

---

## CLI Contract

### Command: `tri-arb monitor`

**用途**: 启动三角套利机会监控（FR-013, FR-014, FR-015, FR-016）

**Usage**:
```bash
tri-arb monitor [OPTIONS]
```

**Options**:

| Option | Type | Default | Description | FR |
|--------|------|---------|-------------|-----|
| `--min-profit` | `float` | `0.5` | 最低盈利阈值（%） | FR-007 |
| `--fee-rate` | `float` | `0.1` | 每笔交易手续费率（%） | FR-005 |
| `--base-currencies` | `str` | `""` | 基础货币白名单（逗号分隔） | FR-006 |
| `--refresh-interval` | `int` | `10` | 刷新间隔（秒） | FR-015 |
| `--mode` | `str` | `"once"` | 运行模式 (once/realtime) | FR-013/014 |
| `--debug` | `flag` | `False` | 调试模式（记录所有路径） | FR-020 |

**Examples**:
```bash
# 单次扫描，默认配置
tri-arb monitor

# 单次扫描，只监控 USDT 路径，盈利阈值 1%
tri-arb monitor --base-currencies USDT --min-profit 1.0

# 实时监控，每 5 秒刷新，监控 USDT 和 BTC 路径
tri-arb monitor --mode realtime --refresh-interval 5 --base-currencies USDT,BTC

# 调试模式（记录所有路径，包括不符合阈值的）
tri-arb monitor --debug
```

**Output Format** (FR-010, FR-011, FR-012):

```
[2025-10-06 10:00:00] 开始扫描市场...
[2025-10-06 10:00:01] 已获取 500 个市场价格

发现 3 条套利机会（按收益率排序）:

┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ 序号 ┃             路径             ┃ 收益率   ┃ 建议金额 ┃
┡━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│  1   │ USDT → BTC → ETH → USDT      │  1.25%   │  1000    │
│  2   │ USDT → ETH → BNB → USDT      │  0.85%   │  1500    │
│  3   │ BTC → ETH → USDT → BTC       │  0.65%   │  0.05    │
└──────┴──────────────────────────────┴──────────┴──────────┘

详细信息:
[1] USDT → BTC → ETH → USDT (收益率: 1.25%)
    Step 1: 买入 BTC/USDT @ 50000.0 USDT
    Step 2: 买入 ETH/BTC @ 0.05 BTC
    Step 3: 卖出 ETH/USDT @ 2600.0 USDT
    建议金额: 1000 USDT
    预期获利: 12.5 USDT (扣除手续费)

[实时模式] 下次刷新: 5 秒后...
```

**Exit Codes**:
- `0`: 成功（发现机会或未发现）
- `1`: 配置错误（FR-018）
- `2`: 网络错误（无法连接 XT API）
- `130`: 用户中断（Ctrl+C，FR-016）

**Signal Handling** (FR-016):
- `SIGINT` (Ctrl+C): 优雅退出，保存最后扫描结果到日志
- `SIGTERM`: 立即退出

---

## Python API Contract

### Class: `ArbitrageMonitor`

**用途**: 套利机会监控器（供其他模块调用）

```python
from tri_arb.arbitrage import ArbitrageMonitor
from tri_arb.arbitrage.config import MonitorConfig

# 创建监控器
config = MonitorConfig(
    min_profit_threshold=0.5,
    fee_rate_per_trade=0.1,
    base_currency_whitelist=["USDT"],
    refresh_interval_seconds=10,
    run_mode="once"
)
monitor = ArbitrageMonitor(config=config, exchange_name="xt")

# 单次扫描
opportunities = await monitor.scan_once()
for opp in opportunities:
    print(f"Path: {opp.path.trading_pairs}, Profit: {opp.expected_profit_rate}%")

# 实时监控（异步生成器）
async for opportunities in monitor.scan_realtime():
    for opp in opportunities:
        print(f"New opportunity: {opp.path.trading_pairs}")
```

### Method: `scan_once()`

**Signature**:
```python
async def scan_once(self) -> list[ArbitrageOpportunity]:
    """
    执行一次全市场扫描，返回所有符合条件的套利机会

    Returns:
        list[ArbitrageOpportunity]: 按收益率降序排序的机会列表

    Raises:
        NetworkError: 网络请求失败（重试 3 次后）
        ValidationError: 配置参数无效
    """
```

**Contract**:
- **前置条件**: `config` 已验证（MonitorConfig.model_validate）
- **后置条件**:
  - 返回列表按 `expected_profit_rate` 降序排序（FR-011）
  - 所有返回的机会满足 `profit_rate >= min_profit_threshold`（FR-008）
  - 如果没有机会，返回空列表（不抛出异常）
- **性能**: 完成时间 < 1秒（NFR-001）
- **日志**: 记录扫描时间、市场数量、发现机会数（FR-019）

---

### Method: `scan_realtime()`

**Signature**:
```python
async def scan_realtime(self) -> AsyncGenerator[list[ArbitrageOpportunity], None]:
    """
    实时监控模式，周期性扫描并生成新机会

    Yields:
        list[ArbitrageOpportunity]: 每次扫描发现的机会列表

    Raises:
        NetworkError: 网络请求失败（重试 3 次后）
    """
```

**Contract**:
- **前置条件**: `config.run_mode == "realtime"`
- **行为**:
  - 每隔 `refresh_interval_seconds` 秒执行一次扫描
  - 每次 `yield` 返回新发现的机会列表
  - 监听 `SIGINT`/`SIGTERM`，收到信号后优雅退出（FR-016）
- **性能**: 每次扫描 < 1秒（NFR-001）
- **内存**: 稳定在 <100MB（NFR-003）

---

## Internal Function Contracts

### Function: `find_arbitrage_paths()`

**Signature**:
```python
from tri_arb.models.exchange import Ticker

def find_arbitrage_paths(
    tickers: list[Ticker],
    base_currencies: list[str] | None = None
) -> list[TradingPath]:
    """
    从价格数据中发现所有可能的三角套利路径

    Args:
        tickers: 市场价格列表
        base_currencies: 基础货币白名单（None=全部）

    Returns:
        list[TradingPath]: 所有有效的三角路径（闭环）

    Raises:
        ValueError: tickers 为空或包含无效价格
    """
```

**Contract**:
- **前置条件**:
  - `tickers` 不为空
  - 所有 `ticker` 满足 `bid > 0 and ask > 0 and bid < ask`（调用前过滤）
- **后置条件**:
  - 所有返回的路径满足 `path.is_closed_loop == True`
  - 如果 `base_currencies` 非空，所有路径的 `start_currency` 在白名单中（FR-006）
- **性能**: 处理 500 个交易对 < 100ms
- **算法**: DFS 深度限制为 3

---

### Function: `calculate_profit_rate()`

**Signature**:
```python
from decimal import Decimal

async def calculate_profit_rate(
    path: TradingPath,
    tickers: dict[str, Ticker],
    fee_rate: Decimal
) -> tuple[Decimal, list[dict]]:
    """
    计算套利路径的预期收益率（扣除手续费）

    Args:
        path: 交易路径
        tickers: 交易对符号 → Ticker 映射
        fee_rate: 每笔交易手续费率（小数形式，如 0.001 = 0.1%）

    Returns:
        tuple[Decimal, list[dict]]: (收益率%, 价格详情列表)

    Raises:
        KeyError: 路径中的交易对在 tickers 中不存在
    """
```

**Contract**:
- **前置条件**:
  - `path` 中的所有交易对在 `tickers` 中存在
  - `fee_rate` 在 [0.0, 0.1] 范围内（0-10%）
- **计算公式** (FR-004, FR-005):
  ```
  最终金额 = 初始金额 × price1 × price2 × price3 × (1 - fee_rate)³
  收益率 = (最终金额 - 初始金额) / 初始金额 × 100
  ```
- **性能**: 单次计算 < 10ms
- **精度**: 使用 `Decimal` 类型，避免浮点误差

---

## Error Handling

### Exception Hierarchy

```python
class ArbitrageError(Exception):
    """套利模块基础异常"""
    pass

class ConfigError(ArbitrageError):
    """配置验证错误 (FR-018)"""
    pass

class NetworkError(ArbitrageError):
    """网络请求失败 (NFR-005)"""
    pass

class InvalidPriceError(ArbitrageError):
    """价格数据无效 (FR-002)"""
    pass
```

### Error Contract (NFR-005)

**网络失败重试策略**:
1. 捕获 `httpx.TimeoutException`, `httpx.NetworkError`
2. 指数退避重试：1s, 2s, 4s（最多 3 次）
3. 3 次失败后抛出 `NetworkError`
4. 记录每次重试到 `structlog`

**价格无效处理** (FR-002):
1. 过滤无效价格：`bid > ask`, `price <= 0`
2. 记录警告日志：`log.warning("invalid_price", symbol=ticker.symbol)`
3. 继续处理其他市场（不中断扫描）

---

## Test Contracts

所有契约必须有对应的失败测试（TDD 原则），位于：
- `tests/contract/test_arbitrage/test_monitor_contracts.py`
- `tests/contract/test_arbitrage/test_path_finder_contracts.py`
- `tests/contract/test_arbitrage/test_calculator_contracts.py`

测试必须在实现前编写并失败。

---

*Generated by Phase 1 design*
