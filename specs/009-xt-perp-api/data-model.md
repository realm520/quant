# Data Model: CLI 数据结构设计

**Feature**: 009-xt-perp-api | **Date**: 2025-10-12

## Overview

本文档定义 CEXTools CLI 工具使用的数据模型，包括命令结构、输入参数、输出格式等。所有模型复用现有的核心数据模型（TradingPair, Price, Order 等），CLI 层只负责格式化展示。

---

## 1. CLI Command Structure

### 主命令
```
cextools [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS] [ARGS]
```

### 全局选项 (Global Options)
| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `--exchange-type` | Enum(spot, perp) | Conditional* | None | 交易类型：spot（现货）或 perp（永续合约） |
| `--debug` | bool | No | False | 启用调试模式，显示详细日志和 API 请求 |
| `--output` | Enum(table, json, csv) | No | table | 输出格式 |
| `--api-key` | str | No | None | API 密钥（覆盖环境变量） |
| `--api-secret` | str | No | None | API 密钥（覆盖环境变量） |
| `--help` | bool | No | False | 显示帮助信息 |

*Conditional: account 和 order 命令组必须指定，market 命令组可选（默认 spot），leverage 命令组必须为 perp

### 命令组 (Command Groups)

#### account - 账户管理
- `balance`: 查询账户余额
- `positions`: 查询持仓列表（仅 perp）

#### market - 市场行情
- `ticker`: 查询实时价格
- `depth`: 查询订单簿深度
- `funding`: 查询资金费率（仅 perp）
- `watch`: 实时监控价格变化

#### order - 订单管理
- `place`: 提交订单
- `status`: 查询订单状态
- `cancel`: 取消单个订单
- `cancel-all`: 批量取消订单

#### leverage - 杠杆管理（仅 perp）
- `set`: 设置杠杆倍数
- `info`: 查询当前杠杆设置

---

## 2. Input Parameters

### account balance
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | spot 或 perp |

### account positions
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | 必须为 perp |
| `--symbol` | str | No | None | 格式：BTC/USDT |

### market ticker
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | No | spot | spot 或 perp |
| `--symbol` | str | No | None | 不指定则显示所有 |

### market depth
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | No | spot | spot 或 perp |
| `--symbol` | str | Yes | - | 格式：BTC/USDT |
| `--limit` | int | No | 10 | 5-50 |

### market funding
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | 必须为 perp |
| `--symbol` | str | Yes | - | 格式：BTC/USDT |

### market watch
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | No | spot | spot 或 perp |
| `--symbol` | str | Yes | - | 格式：BTC/USDT |
| `--interval` | int | No | 5 | 1-60 秒 |

### order place
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | spot 或 perp |
| `--symbol` | str | Yes | - | 格式：BTC/USDT |
| `--side` | Enum | Yes | - | BUY 或 SELL |
| `--position-side` | Enum | Conditional* | - | LONG 或 SHORT（perp 必须） |
| `--quantity` | Decimal | Yes | - | > 0 |
| `--order-type` | Enum | Yes | - | MARKET 或 LIMIT |
| `--price` | Decimal | Conditional** | - | > 0（LIMIT 必须） |
| `--yes` | bool | No | False | 跳过确认 |

*perp 必须指定，spot 不需要
**LIMIT 订单必须指定

### order status
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | spot 或 perp |
| `--order-id` | str | Yes | - | 订单 ID |

### order cancel
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | spot 或 perp |
| `--order-id` | str | Yes | - | 订单 ID |

### order cancel-all
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | spot 或 perp |
| `--symbol` | str | No | None | 不指定则取消所有 |
| `--yes` | bool | No | False | 跳过确认 |

### leverage set
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | 必须为 perp |
| `--symbol` | str | Yes | - | 格式：BTC/USDT |
| `--leverage` | int | Yes | - | 1-125 |

### leverage info
| Parameter | Type | Required | Default | Validation |
|-----------|------|----------|---------|------------|
| `--exchange-type` | Enum | Yes | - | 必须为 perp |
| `--symbol` | str | Yes | - | 格式：BTC/USDT |

---

## 3. Output Models

### AccountBalanceDisplay
用于展示账户余额信息（复用 exchange.get_balance() 返回的数据）

```python
# 输入数据结构（来自 XTSpotExchange/XTPerpExchange）
{
    'USDT': {
        'available': Decimal('1000.00000000'),
        'frozen': Decimal('50.00000000')
    },
    'BTC': {
        'available': Decimal('0.05000000'),
        'frozen': Decimal('0.01000000')
    }
}

# Table 输出格式
┏━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Currency ┃    Available ┃       Frozen ┃        Total ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ USDT     │ 1000.00000000│   50.00000000│ 1050.00000000│
│ BTC      │    0.05000000│    0.01000000│    0.06000000│
└──────────┴──────────────┴──────────────┴──────────────┘
Data fetched at: 2025-10-12 14:30:00 UTC

# JSON 输出格式
[
  {
    "currency": "USDT",
    "available": "1000.00000000",
    "frozen": "50.00000000",
    "total": "1050.00000000"
  },
  ...
]
```

**字段说明**:
- Currency: 币种符号
- Available: 可用余额（8 位小数）
- Frozen: 冻结余额（8 位小数）
- Total: 总余额 = Available + Frozen

### PositionDisplay
用于展示持仓信息（复用 XTPerpExchange.get_positions() 返回的 Position 模型）

```python
# 输入数据结构（来自 models/perpetual.py Position）
[
    Position(
        symbol='BTC/USDT',
        position_side='LONG',
        quantity=Decimal('0.10'),
        entry_price=Decimal('50000.00'),
        current_price=Decimal('51000.00'),
        unrealized_pnl=Decimal('100.00'),
        leverage=10,
        liquidation_price=Decimal('45000.00'),
        margin=Decimal('500.00'),
    ),
    ...
]

# Table 输出格式
┏━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Symbol    ┃ Side   ┃ Quantity ┃ Entry Price┃ Current Price┃ PnL      ┃ ROE     ┃Leverage┃
┡━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ BTC/USDT  │ LONG   │     0.10 │  50000.00  │   51000.00   │ +100.00  │ +20.00% │  10x   │
│ ETH/USDT  │ SHORT  │     1.50 │   3000.00  │    3050.00   │  -75.00  │  -5.00% │  20x   │
└───────────┴────────┴──────────┴────────────┴──────────────┴──────────┴─────────┴────────┘
Data fetched at: 2025-10-12 14:30:00 UTC
```

**字段说明**:
- Symbol: 交易对
- Side: 持仓方向（LONG/SHORT）
- Quantity: 持仓数量（合约张数）
- Entry Price: 开仓均价
- Current Price: 当前标记价格
- PnL: 未实现盈亏（绿色为正，红色为负）
- ROE: 收益率（Return on Equity，相对于保证金的百分比）
- Leverage: 杠杆倍数

**颜色规则**:
- PnL > 0: 绿色 `[green]+100.00[/green]`
- PnL < 0: 红色 `[red]-75.00[/red]`
- PnL = 0: 白色 `[white]0.00[/white]`

### TickerDisplay
用于展示市场价格（复用 exchange.get_ticker() 返回的 Price 模型）

```python
# 输入数据结构（来自 core/models.py Price）
[
    Price(
        trading_pair=TradingPair(...),
        bid_price=Decimal('50000.00'),
        ask_price=Decimal('50001.00'),
        last_price=Decimal('50000.50'),
        volume_24h=Decimal('1234.56'),
        change_24h=Decimal('2.5'),  # 百分比
        timestamp=datetime(...),
    ),
    ...
]

# Table 输出格式
┏━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Symbol    ┃    Bid     ┃    Ask     ┃   Last     ┃ 24h Change ┃ 24h Volume  ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ BTC/USDT  │  50000.00  │  50001.00  │  50000.50  │   +2.50%   │   1234.56   │
│ ETH/USDT  │   3000.00  │   3001.00  │   3000.50  │   -1.20%   │  12345.67   │
└───────────┴────────────┴────────────┴────────────┴────────────┴─────────────┘
Data fetched at: 2025-10-12 14:30:00 UTC
```

**字段说明**:
- Symbol: 交易对
- Bid: 买一价
- Ask: 卖一价
- Last: 最新成交价
- 24h Change: 24 小时涨跌幅（绿色为涨，红色为跌）
- 24h Volume: 24 小时成交量

### OrderBookDisplay
用于展示订单簿深度（复用 exchange.get_orderbook() 返回的 OrderBook 模型）

```python
# 输入数据结构（来自 core/models.py OrderBook）
OrderBook(
    trading_pair=TradingPair(...),
    bids=[
        (Decimal('50000.00'), Decimal('1.5')),
        (Decimal('49999.00'), Decimal('2.0')),
        ...
    ],
    asks=[
        (Decimal('50001.00'), Decimal('1.2')),
        (Decimal('50002.00'), Decimal('1.8')),
        ...
    ],
    timestamp=datetime(...),
)

# Table 输出格式（分两列显示）
Order Book: BTC/USDT (Limit: 10)

         Bids                              Asks
┏━━━━━━━━━━━━┳━━━━━━━━━━┓    ┏━━━━━━━━━━━━┳━━━━━━━━━━┓
┃    Price   ┃ Quantity ┃    ┃    Price   ┃ Quantity ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━┩    ┡━━━━━━━━━━━━╇━━━━━━━━━━┩
│  50000.00  │     1.50 │    │  50001.00  │     1.20 │
│  49999.00  │     2.00 │    │  50002.00  │     1.80 │
│  49998.00  │     1.80 │    │  50003.00  │     2.50 │
└────────────┴──────────┘    └────────────┴──────────┘

Spread: 1.00 (0.002%)
Data fetched at: 2025-10-12 14:30:00 UTC
```

### OrderSummary
用于展示订单信息（复用 core/models.py Order 模型）

```python
# 输入数据结构（来自 Order 模型）
Order(
    order_id='12345',
    exchange_order_id='XT_67890',
    trading_pair=TradingPair(...),
    side=OrderSide.BUY,
    order_type=OrderType.LIMIT,
    price=Decimal('50000.00'),
    quantity=Decimal('0.10'),
    filled_quantity=Decimal('0.05'),
    status=OrderStatus.PARTIALLY_FILLED,
    created_at=datetime(...),
    position_side='LONG',  # perp only
)

# Table 输出格式
Order Details
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Field            ┃ Value                        ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Order ID         │ 12345                        │
│ Exchange ID      │ XT_67890                     │
│ Symbol           │ BTC/USDT                     │
│ Side             │ BUY                          │
│ Position Side    │ LONG                         │
│ Type             │ LIMIT                        │
│ Price            │ 50000.00                     │
│ Quantity         │ 0.10                         │
│ Filled           │ 0.05 (50.00%)                │
│ Status           │ PARTIALLY_FILLED             │
│ Created At       │ 2025-10-12 14:25:00 UTC      │
└──────────────────┴──────────────────────────────┘
```

### FundingRateDisplay
用于展示资金费率（复用 models/perpetual.py FundingRate 模型）

```python
# 输入数据结构（来自 FundingRate 模型）
FundingRate(
    symbol='BTC/USDT',
    rate=Decimal('0.0001'),  # 0.01%
    next_funding_time=datetime(...),
)

# Table 输出格式
Funding Rate: BTC/USDT
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Field            ┃ Value                        ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Current Rate     │ 0.01% (0.0001)               │
│ Next Funding     │ 2025-10-12 16:00:00 UTC      │
│ Time Until       │ 1h 25m                       │
└──────────────────┴──────────────────────────────┘
```

---

## 4. Error Messages

### 友好错误消息设计

**示例 1: 缺少必选参数**
```
Error: --exchange-type is required for account commands

Please specify the exchange type:
  --exchange-type spot    # For spot trading
  --exchange-type perp    # For perpetual futures

Example:
  cextools account balance --exchange-type spot
```

**示例 2: 参数验证失败**
```
Error: leverage 命令仅适用于永续合约（perp），现货交易不支持杠杆

正确用法:
  cextools leverage set --exchange-type perp --symbol BTC/USDT --leverage 10
```

**示例 3: API 错误（用户友好）**
```
Error: 账户余额不足

可用保证金: 100.00 USDT
所需保证金: 500.00 USDT (开仓 0.1 BTC，杠杆 10x)

建议:
  1. 充值至少 400 USDT 到永续合约账户
  2. 或降低开仓数量至 0.02 BTC
  3. 或降低杠杆倍数至 2x
```

**示例 4: API 错误（调试模式）**
```
Error: 账户余额不足

可用保证金: 100.00 USDT
所需保证金: 500.00 USDT

[DEBUG] API Response:
  Status Code: 400
  Error Code: INSUFFICIENT_BALANCE
  Message: "Available margin 100.00 USDT is less than required margin 500.00 USDT"
  Request ID: req_abc123
  Timestamp: 2025-10-12 14:30:00.123

[DEBUG] Request Details:
  Endpoint: POST /future/trade/v1/order/create
  Headers: {validate-appkey: XT123..., validate-timestamp: 1728745800000}
  Body: {"symbol": "btc_usdt", "side": "BUY", "quantity": "0.1", ...}
```

---

## 5. Validation Rules

### 全局验证
- `--exchange-type`: 必须为 `spot` 或 `perp`（Enum 自动验证）
- `--output`: 必须为 `table`, `json`, `csv`（Enum 自动验证）

### 命令级验证
- `account positions`: `--exchange-type` 必须为 `perp`
- `market funding`: `--exchange-type` 必须为 `perp`
- `leverage set/info`: `--exchange-type` 必须为 `perp`
- `order place` (perp): 必须提供 `--position-side`
- `order place` (LIMIT): 必须提供 `--price`

### 参数值验证
- `--symbol`: 格式 `BASE/QUOTE`（如 `BTC/USDT`）
- `--leverage`: 1-125 之间的整数
- `--interval`: 1-60 之间的整数
- `--limit`: 5-50 之间的整数
- `--quantity`: 必须 > 0
- `--price`: 必须 > 0

### API 凭证验证
- `spot`: 检查 `XT_API_KEY` 和 `XT_API_SECRET` 环境变量
- `perp`: 检查 `XT_PERP_API_KEY` 和 `XT_PERP_API_SECRET` 环境变量
- 如果使用 `--api-key` 和 `--api-secret`，则覆盖环境变量

---

## Summary

### 数据流
1. **用户输入** → Typer 参数解析 → Enum/类型验证
2. **验证通过** → exchange_factory 创建适配器 → API 调用
3. **API 响应** → 复用现有数据模型 → formatter 格式化 → 输出

### 关键设计原则
- **复用现有模型**: 不创建重复的数据结构，直接使用 core/models.py 和 models/perpetual.py
- **类型安全**: 使用 Enum 限制参数值，编译时发现错误
- **友好提示**: 清晰的错误消息 + 解决方案 + 示例命令
- **多格式输出**: 统一的数据结构，支持 table/json/csv 切换

### 与现有系统集成
- **XTSpotExchange**: 提供 get_balance(), get_ticker(), get_orderbook() 等方法
- **XTPerpExchange**: 提供永续合约特有方法（get_positions(), get_funding_rate(), set_leverage()）
- **core/models.py**: 提供 Price, OrderBook, Order 等通用模型
- **models/perpetual.py**: 提供 Position, FundingRate 等永续合约模型

---
**Data Model Complete** ✓ | **Ready for Contracts Generation** ✓
