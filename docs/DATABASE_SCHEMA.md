# 数据库表结构文档

本文档描述了交易系统使用的所有数据库表结构。所有表都使用统一表设计，通过 `account_id` 字段区分不同账号的数据。

## 目录

- [Binance WebSocket 数据表](#binance-websocket-数据表)
- [XT WebSocket 数据表](#xt-websocket-数据表)
- [XT REST API 数据表](#xt-rest-api-数据表)
- [OKX WebSocket 数据表](#okx-websocket-数据表)
- [Gate.io WebSocket 数据表](#gateio-websocket-数据表)
- [按交易所区分的 REST API 表](#按交易所区分的-rest-api-表)
- [系统表](#系统表)
- [表设计说明](#表设计说明)

---

## Binance WebSocket 数据表

### 1. binance_account_update

**用途**: 存储 Binance WebSocket 推送的账户余额和持仓变化。

**表名**: `binance_account_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| exchange | String(20) | 交易所名称（binance_perp） | ✓ |
| account_id | String(64) | 账号ID（多账号区分） | ✓ |
| event_type | String(20) | 事件类型（ACCOUNT_UPDATE） | |
| event_time | DateTime | 事件时间 | ✓ |
| transaction_time | DateTime | 交易时间 | |
| asset | String(20) | 资产类型（如USDT） | ✓ |
| wallet_balance | Numeric(30,10) | 钱包余额 | |
| cross_wallet_balance | Numeric(30,10) | 全仓余额 | |
| balance_change | Numeric(30,10) | 余额变化 | |
| symbol | String(20) | 交易对 | ✓ |
| position_side | String(10) | 持仓方向 | |
| position_amount | Numeric(30,10) | 持仓数量 | |
| entry_price | Numeric(30,10) | 开仓均价 | |
| unrealized_pnl | Numeric(30,10) | 未实现盈亏 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_exchange_event_time` (exchange, event_time)
- `idx_symbol_event_time` (symbol, event_time)
- `idx_account_event_time` (account_id, event_time)

---

### 2. binance_order_update

**用途**: 存储 Binance WebSocket 推送的订单状态变化。

**表名**: `binance_order_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| exchange | String(20) | 交易所名称（binance_perp） | ✓ |
| account_id | String(64) | 账号ID（多账号区分） | ✓ |
| event_type | String(20) | 事件类型（ORDER_TRADE_UPDATE） | |
| event_time | DateTime | 事件时间 | ✓ |
| transaction_time | DateTime | 交易时间 | |
| symbol | String(20) | 交易对 | ✓ |
| client_order_id | String(50) | 客户订单ID | ✓ |
| side | String(10) | 买卖方向（BUY/SELL） | |
| order_type | String(30) | 订单类型 | |
| time_in_force | String(10) | 有效方式 | |
| original_quantity | Numeric(30,10) | 原始数量 | |
| original_price | Numeric(30,10) | 原始价格 | |
| average_price | Numeric(30,10) | 平均成交价 | |
| order_status | String(20) | 订单状态 | ✓ |
| order_id | BigInteger | 订单ID | ✓ |
| last_filled_quantity | Numeric(30,10) | 最后成交数量 | |
| cumulative_filled_quantity | Numeric(30,10) | 累计成交数量 | |
| last_filled_price | Numeric(30,10) | 最后成交价格 | |
| commission_amount | Numeric(30,10) | 手续费数量 | |
| commission_asset | String(20) | 手续费资产 | |
| position_side | String(10) | 持仓方向（LONG/SHORT/BOTH） | |
| is_reduce_only | Boolean | 是否仅减仓 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_order_id_event_time` (order_id, event_time)
- `idx_symbol_status` (symbol, order_status)
- `idx_exchange_symbol_time` (exchange, symbol, event_time)
- `idx_account_symbol_time` (account_id, symbol, event_time)

**唯一约束**:
- `uq_order_update_event` (exchange, order_id, event_time)

---

### 3. binance_trade_update

**用途**: 存储 Binance WebSocket 推送的实时成交信息。

**表名**: `binance_trade_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| exchange | String(20) | 交易所名称（binance_perp） | ✓ |
| account_id | String(64) | 账号ID（多账号区分） | ✓ |
| event_type | String(20) | 事件类型（ORDER_TRADE_UPDATE） | |
| event_time | DateTime | 事件时间 | ✓ |
| transaction_time | DateTime | 交易时间 | |
| symbol | String(20) | 交易对 | ✓ |
| order_id | BigInteger | 订单ID | ✓ |
| trade_id | BigInteger | 成交ID | ✓ |
| side | String(10) | 买卖方向（BUY/SELL） | |
| price | Numeric(30,10) | 成交价格 | |
| quantity | Numeric(30,10) | 成交数量 | |
| quote_quantity | Numeric(30,10) | 成交金额 | |
| commission | Numeric(30,10) | 手续费 | |
| commission_asset | String(20) | 手续费资产 | |
| is_maker | Boolean | 是否为挂单方 | |
| position_side | String(10) | 持仓方向（LONG/SHORT/BOTH） | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_symbol_trade_time` (symbol, transaction_time)
- `idx_order_trade` (order_id, trade_id)
- `idx_account_trade_time` (account_id, transaction_time)

**唯一约束**:
- `uq_trade_id` (exchange, trade_id)

---

### 4. binance_account_snapshot

**用途**: 存储通过 REST/定时查询得到的 Binance 账户余额快照（按资产维度）。

**表名**: `binance_account_snapshot`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| account_id | String(64) | 账号ID（多账号区分） | ✓ |
| asset | String(20) | 币种 | ✓ |
| free | Numeric(30,10) | 可用余额 | |
| locked | Numeric(30,10) | 冻结余额 | |
| total | Numeric(30,10) | 总余额 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_binance_balance_asset_time` (asset, update_time)
- `idx_binance_balance_account_time` (account_id, update_time)

---

## XT WebSocket 数据表

### 5. xt_account_update

**用途**: 存储 XT WebSocket 推送的账户余额变化。

**表名**: `xt_account_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| currency | String(20) | 币种 | ✓ |
| available | Numeric(30,10) | 可用余额 | |
| frozen | Numeric(30,10) | 冻结余额 | |
| total | Numeric(30,10) | 总余额 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_account_currency_time` (currency, update_time)
- `idx_xt_account_time` (update_time)
- `idx_xt_account_account_time` (account_id, update_time)

---

### 6. xt_spot_update

**用途**: 在处理合约账户余额变化时，记录对应时间点的现货账户余额。

**表名**: `xt_spot_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 记录时间 | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| currency | String(20) | 币种 | ✓ |
| available | Numeric(30,10) | 可用余额 | |
| frozen | Numeric(30,10) | 冻结余额 | |
| total | Numeric(30,10) | 总余额 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_spot_currency_time` (currency, update_time)
- `idx_xt_spot_time` (update_time)
- `idx_xt_spot_account_time` (account_id, update_time)

---

### 7. xt_position_update

**用途**: 存储 XT WebSocket 推送的持仓变化。

**表名**: `xt_position_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| symbol | String(20) | 交易对 | ✓ |
| side | String(10) | 持仓方向（LONG/SHORT） | |
| quantity | Numeric(30,10) | 持仓数量 | |
| entry_price | Numeric(30,10) | 开仓均价 | |
| mark_price | Numeric(30,10) | 标记价格 | |
| liquidation_price | Numeric(30,10) | 强平价格 | |
| unrealized_pnl | Numeric(30,10) | 未实现盈亏 | |
| leverage | Integer | 杠杆倍数 | |
| margin | Numeric(30,10) | 保证金 | |
| roe | Numeric(10,4) | 收益率 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_position_symbol_time` (symbol, update_time)
- `idx_xt_position_side_time` (side, update_time)
- `idx_xt_position_time` (update_time)
- `idx_xt_position_account_time` (account_id, update_time)

---

### 8. xt_order_update

**用途**: 存储 XT WebSocket 推送的订单状态变化。

**表名**: `xt_order_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| symbol | String(20) | 交易对 | ✓ |
| order_id | String(50) | 订单ID | ✓ |
| client_order_id | String(50) | 客户订单ID | ✓ |
| side | String(10) | 买卖方向（BUY/SELL） | |
| order_type | String(30) | 订单类型 | |
| position_side | String(10) | 持仓方向 | |
| quantity | Numeric(30,10) | 订单数量 | |
| price | Numeric(30,10) | 订单价格 | |
| filled_quantity | Numeric(30,10) | 已成交数量 | |
| status | String(20) | 订单状态 | ✓ |
| time_in_force | String(10) | 有效方式 | |
| create_time | DateTime | 创建时间 | |
| update_time_order | DateTime | 订单更新时间 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_order_id_time` (order_id, update_time)
- `idx_xt_order_symbol_status_time` (symbol, status, update_time)
- `idx_xt_order_time` (update_time)
- `idx_xt_order_account_time` (account_id, update_time)

**唯一约束**:
- `uq_xt_order_id_time_account` (order_id, update_time, account_id)

---

### 9. xt_trade_update

**用途**: 存储 XT WebSocket 推送的实时成交信息。

**表名**: `xt_trade_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| symbol | String(20) | 交易对 | ✓ |
| order_id | String(50) | 订单ID | ✓ |
| trade_id | String(50) | 成交ID | ✓ |
| side | String(10) | 买卖方向（BUY/SELL） | |
| price | Numeric(30,10) | 成交价格 | |
| quantity | Numeric(30,10) | 成交数量 | |
| quote_quantity | Numeric(30,10) | 成交金额 | |
| commission | Numeric(30,10) | 手续费 | |
| commission_asset | String(20) | 手续费资产 | |
| is_maker | Boolean | 是否为挂单方 | |
| position_side | String(10) | 持仓方向（LONG/SHORT） | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_trade_symbol_time` (symbol, update_time)
- `idx_xt_trade_order_trade` (order_id, trade_id)
- `idx_xt_trade_time` (update_time)
- `idx_xt_trade_account_time` (account_id, update_time)

**唯一约束**:
- `uq_xt_trade_id_account` (trade_id, account_id)

---

### 10. xt_transfer_update

**用途**: 通过分析账户余额变化识别资金划转（充值、提现、账户间划转等）。

**表名**: `xt_transfer_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| transfer_time | DateTime | 划转时间 | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| currency | String(20) | 币种 | ✓ |
| amount | Numeric(30,10) | 划转金额（正数=转入，负数=转出） | |
| transfer_type | String(20) | 划转类型（DEPOSIT/WITHDRAW/TRANSFER/UNKNOWN） | ✓ |
| balance_before | Numeric(30,10) | 划转前余额 | |
| balance_after | Numeric(30,10) | 划转后余额 | |
| related_order_id | String(50) | 关联订单ID（如果有） | |
| related_trade_id | String(50) | 关联成交ID（如果有） | |
| notes | Text | 备注信息 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_transfer_currency_time` (currency, transfer_time)
- `idx_xt_transfer_time` (transfer_time)
- `idx_xt_transfer_type` (transfer_type)
- `idx_xt_transfer_account_time` (account_id, transfer_time)

---

### 11. xt_connection

**用途**: 存储 XT WebSocket 连接状态和重连信息。

**表名**: `xt_connection`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | Integer | 主键，自增 | PK |
| connection_id | String(100) | 连接ID（唯一） | UNIQUE |
| start_time | DateTime | 开始时间 | |
| end_time | DateTime | 结束时间 | |
| is_active | Boolean | 是否活跃 | ✓ |
| total_messages | Integer | 总消息数 | |
| account_updates | Integer | 账户更新数 | |
| position_updates | Integer | 持仓更新数 | |
| order_updates | Integer | 订单更新数 | |
| trade_updates | Integer | 成交更新数 | |
| reconnect_count | Integer | 重连次数 | |
| last_reconnect_time | DateTime | 最后重连时间 | |
| last_error | Text | 最后错误信息 | |
| data_sync_count | Integer | 数据同步次数 | |
| last_sync_time | DateTime | 最后同步时间 | |
| raw_data | Text | 配置信息 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_ws_active` (is_active)
- `idx_xt_ws_start_time` (start_time)

---

## XT REST API 数据表

### 12. xt_account_snapshot

**用途**: 存储 XT 账户余额快照（现货和合约，通过 exchange_type 字段区分）。

**表名**: `xt_account_snapshot`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| query_time | DateTime | 查询时间 | ✓ |
| query_type | String(20) | 查询类型（manual/scheduled） | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| asset | String(20) | 资产类型（如USDT, BTC） | ✓ |
| free | Numeric(30,10) | 可用余额 | |
| locked | Numeric(30,10) | 冻结余额 | |
| total | Numeric(30,10) | 总余额 | |
| raw_data | Text | 完整JSON原始数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_account_type_time` (exchange_type, query_time)
- `idx_xt_account_asset_time` (asset, query_time)
- `idx_xt_account_query_type_time` (query_type, query_time)
- `idx_xt_account_account_time` (account_id, query_time)

**说明**: 此表合并了原来的 `xt_spot_balances` 和 `xt_perp_balances`，通过 `exchange_type` 字段区分现货（spot）和合约（perp）。

---

### 13. xt_position_snapshot

**用途**: 存储 XT 永续合约账户的持仓快照（合并了原来的 `xt_perp_positions` 和 `xt_rest_position_updates`）。

**表名**: `xt_position_snapshot`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| query_time | DateTime | 查询时间 | ✓ |
| query_type | String(20) | 查询类型（manual/scheduled） | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| symbol | String(20) | 交易对（如BTC/USDT） | ✓ |
| position_side | String(10) | 持仓方向（LONG/SHORT） | |
| position_amount | Numeric(30,10) | 持仓数量 | |
| entry_price | Numeric(30,10) | 开仓均价 | |
| mark_price | Numeric(30,10) | 标记价格 | |
| unrealized_pnl | Numeric(30,10) | 未实现盈亏 | |
| realized_pnl | Numeric(30,10) | 已实现盈亏 | |
| percentage | Numeric(10,4) | 盈亏百分比 | |
| notional | Numeric(30,10) | 名义价值 | |
| isolated | Boolean | 是否逐仓 | |
| leverage | String(10) | 杠杆倍数 | |
| liquidation_price | Numeric(30,10) | 强平价格 | |
| margin | Numeric(30,10) | 保证金 | |
| roe | Numeric(10,4) | 收益率百分比 | |
| maintenance_margin | Numeric(30,10) | 维持保证金 | |
| raw_data | Text | 完整JSON原始数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_xt_position_symbol_time` (symbol, query_time)
- `idx_xt_position_side_time` (position_side, query_time)
- `idx_xt_position_query_type_time` (query_type, query_time)
- `idx_xt_position_account_time` (account_id, query_time)

---

## OKX WebSocket 数据表

### 30. okx_account_updates

**用途**: 存储 OKX WebSocket 推送的账户余额数据。

**表名**: `okx_account_updates`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| total_eq | Numeric(30,10) | 账户总权益(USD) | |
| iso_eq | Numeric(30,10) | 逐仓账户权益 | |
| adj_eq | Numeric(30,10) | 调整后的账户权益 | |
| notional_usd | Numeric(30,10) | 持仓折合USD | |
| currency | String(20) | 币种 | ✓ |
| available_bal | Numeric(30,10) | 可用余额 | |
| cash_bal | Numeric(30,10) | 现金余额 | |
| frozen_bal | Numeric(30,10) | 冻结余额 | |
| equity | Numeric(30,10) | 币种权益 | |
| upl | Numeric(30,10) | 未实现盈亏 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_okx_balance_currency_time` (currency, update_time)

---

### 31. okx_position_update

**用途**: 存储 OKX WebSocket 推送的持仓数据。

**表名**: `okx_position_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| inst_id | String(50) | 产品ID (如BTC-USDT-SWAP) | ✓ |
| inst_type | String(20) | 产品类型 (SWAP/FUTURES/SPOT) | |
| pos_side | String(10) | 持仓方向 (long/short/net) | |
| pos | Numeric(30,10) | 持仓数量 | |
| pos_ccy | String(20) | 持仓币种 | |
| avg_px | Numeric(30,10) | 开仓均价 | |
| mark_px | Numeric(30,10) | 标记价格 | |
| liq_px | Numeric(30,10) | 预估强平价 | |
| upl | Numeric(30,10) | 未实现盈亏 | |
| upl_ratio | Numeric(20,10) | 未实现盈亏比例 | |
| margin | Numeric(30,10) | 保证金 | |
| imr | Numeric(30,10) | 初始保证金 | |
| mmr | Numeric(30,10) | 维持保证金 | |
| lever | Numeric(10,2) | 杠杆倍数 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_okx_position_inst_time` (inst_id, update_time)
- `idx_okx_position_side` (pos_side)

---

### 32. okx_order_update

**用途**: 存储 OKX WebSocket 推送的订单数据。

**表名**: `okx_order_update`

**字段**: 包含订单ID、交易对、订单类型、状态、价格、数量等字段。

---

## Gate.io WebSocket 数据表

### 33. gate_account_update

**用途**: 存储 Gate.io WebSocket 推送的账户余额数据。

**表名**: `gate_account_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| user_id | BigInteger | 用户ID | |
| currency | String(20) | 币种 | ✓ |
| total | Numeric(30,10) | 总余额 | |
| available | Numeric(30,10) | 可用余额 | |
| unrealised_pnl | Numeric(30,10) | 未实现盈亏 | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_gate_balance_currency_time` (currency, update_time)

---

### 34. gate_position_update

**用途**: 存储 Gate.io WebSocket 推送的持仓数据。

**表名**: `gate_position_update`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| update_time | DateTime | 更新时间 | ✓ |
| contract | String(50) | 合约名称 | ✓ |
| size | Numeric(30,10) | 持仓数量 | |
| leverage | Numeric(10,2) | 杠杆倍数 | |
| margin | Numeric(30,10) | 保证金 | |
| entry_price | Numeric(30,10) | 开仓均价 | |
| mark_price | Numeric(30,10) | 标记价格 | |
| liq_price | Numeric(30,10) | 强平价格 | |
| unrealised_pnl | Numeric(30,10) | 未实现盈亏 | |
| realised_pnl | Numeric(30,10) | 已实现盈亏 | |
| mode | String(20) | 模式 (single/dual) | |
| raw_data | Text | 完整JSON数据 | |
| created_at | DateTime | 创建时间 | |

**索引**:
- `idx_gate_position_contract_time` (contract, update_time)

---

### 35. gate_order_update

**用途**: 存储 Gate.io WebSocket 推送的订单数据。

**表名**: `gate_order_update`

**字段**: 包含订单ID、合约、订单状态、价格、数量等字段。

**唯一约束**:
- `order_id` (unique)

---

## 按交易所区分的 REST API 表

这些表按交易所名称区分，用于存储 REST API 查询的数据。

### 16-18. Binance REST API 表

- **binance_balance_rest**: Binance 余额查询记录
- **binance_position_rest**: Binance 持仓查询记录
- **binance_order_rest**: Binance 订单查询记录

**通用字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | BigInteger | 主键，自增 | PK |
| exchange_type | String(10) | 账户类型（spot/perp） | ✓ |
| query_time | DateTime | 查询时间 | ✓ |
| query_type | String(20) | 查询类型（manual/scheduled） | ✓ |
| account_id | String(64) | 账号ID（用于区分多账号） | ✓ |
| asset/symbol | String(20) | 资产/交易对 | ✓ |
| ... | ... | 其他字段根据表类型而定 | |

**索引**:
- `idx_{exchange}_balance_type_time` (exchange_type, query_time)
- `idx_{exchange}_balance_asset_time` (asset, query_time)
- `idx_{exchange}_balance_query_type_time` (query_type, query_time)
- `idx_{exchange}_balance_account_time` (account_id, query_time)

### 19-21. XT REST API 表

- **xt_balance_rest**: XT 余额查询记录
- **xt_position_rest**: XT 持仓查询记录
- **xt_order_rest**: XT 订单查询记录

### 22-24. OKX REST API 表

- **okx_balance_rest**: OKX 余额查询记录
- **okx_position_rest**: OKX 持仓查询记录
- **okx_order_rest**: OKX 订单查询记录

### 25-27. Gate.io REST API 表

- **gate_balance_rest**: Gate.io 余额查询记录
- **gate_position_rest**: Gate.io 持仓查询记录
- **gate_order_rest**: Gate.io 订单查询记录

---

## 系统表

### 28. listen_keys

**用途**: 存储 Binance 用户数据流的 ListenKey，用于 WebSocket 连接。

**表名**: `listen_keys`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | Integer | 主键，自增 | PK |
| exchange | String(20) | 交易所名称 | ✓ |
| listen_key | String(100) | ListenKey（唯一） | UNIQUE |
| created_at | DateTime | 创建时间 | |
| expires_at | DateTime | 过期时间（60分钟后） | |
| is_active | Boolean | 是否活跃 | ✓ |
| last_keepalive | DateTime | 最后一次keepalive时间 | |

---

### 29. connection_status

**用途**: WebSocket 连接状态追踪，用于断线重连后补全丢失的数据。

**表名**: `connection_status`

**字段**:

| 字段名 | 类型 | 说明 | 索引 |
|--------|------|------|------|
| id | Integer | 主键，自增 | PK |
| exchange | String(20) | 交易所名称（唯一） | UNIQUE, ✓ |
| is_connected | Boolean | 当前连接状态 | |
| last_connected_at | DateTime | 最后连接时间 | |
| last_disconnected_at | DateTime | 最后断线时间 | |
| last_order_event_time | DateTime | 最后处理的订单事件时间 | ✓ |
| last_trade_event_time | DateTime | 最后处理的成交事件时间 | ✓ |
| last_account_event_time | DateTime | 最后处理的账户事件时间 | ✓ |
| last_order_id | BigInteger | 最后处理的订单ID | |
| last_trade_id | BigInteger | 最后处理的成交ID | |
| total_reconnect_count | Integer | 总重连次数 | |
| last_data_gap_seconds | Integer | 最后一次断线时长（秒） | |
| updated_at | DateTime | 更新时间 | |

**索引**:
- `idx_exchange_connected` (exchange, is_connected)

---

## 表设计说明

### 统一表设计

所有表都采用**统一表 + account_id 字段**的设计，而不是按账号分表。这种设计的优势：

1. **维护简单**: 不需要为每个新账号创建新表
2. **查询灵活**: 可以轻松查询单个账号或跨账号数据
3. **扩展性好**: 支持任意数量的账号
4. **一致性**: 所有交易所使用相同的设计模式

### account_id 字段

- **类型**: `String(64)`
- **可空**: `nullable=True`（兼容历史数据）
- **索引**: 所有表都有 `account_id` 相关的索引
- **用途**: 区分不同账号的数据

### 查询示例

**查询单个账号的数据**:
```sql
SELECT * FROM xt_account_update 
WHERE account_id = 'account_001' 
ORDER BY update_time DESC;
```

**查询多个账号的数据**:
```sql
SELECT * FROM xt_account_update 
WHERE account_id IN ('account_001', 'account_002') 
ORDER BY update_time DESC;
```

**跨账号统计**:
```sql
SELECT account_id, COUNT(*) as update_count 
FROM xt_account_update 
GROUP BY account_id;
```

### 唯一约束

- **Binance**: `uq_order_update_event` (exchange, order_id, event_time) - 在 `binance_order_update` 表
- **Binance**: `uq_trade_id` (exchange, trade_id) - 在 `binance_trade_update` 表
- **XT**: `uq_xt_order_id_time_account` (order_id, update_time, account_id) - 在 `xt_order_update` 表
- **XT**: `uq_xt_trade_id_account` (trade_id, account_id) - 在 `xt_trade_update` 表

注意：唯一约束都包含了 `account_id` 或 `exchange`，确保不同账号的数据可以共存。

### 时间字段

- **WebSocket 数据**: 使用 `update_time` 或 `event_time` 记录事件发生时间
- **REST API 数据**: 使用 `query_time` 记录查询时间
- **系统字段**: `created_at` 记录数据插入时间

### 原始数据

所有表都包含 `raw_data` 字段（Text 类型），存储完整的 JSON 原始数据，便于：
- 调试和问题排查
- 数据回放和重放
- 未来字段扩展

---

## 表关系图

```
┌─────────────────────────────────────────────────────────┐
│                    WebSocket 数据流                       │
├─────────────────────────────────────────────────────────┤
│  Binance: account_updates, binance_order_updates,       │
│           binance_trade_updates                          │
│  XT:      xt_account_updates, xt_order_updates,         │
│           xt_trade_updates, xt_position_updates          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    REST API 数据                         │
├─────────────────────────────────────────────────────────┤
│  XT:      xt_spot_balances, xt_perp_balances,           │
│           xt_perp_positions                              │
│  按交易所: {exchange}_balance_rest,                     │
│           {exchange}_position_rest,                      │
│           {exchange}_order_rest                         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                    系统表                                │
├─────────────────────────────────────────────────────────┤
│  listen_keys, connection_status                         │
└─────────────────────────────────────────────────────────┘
```

---

## 更新日志

- **2025-12-01**: 统一表设计，所有表添加 `account_id` 字段
- **2025-12-01**: 更新唯一约束，包含 `account_id` 或 `exchange`
- **2025-12-01**: 表名规范化，WebSocket 数据使用 `_update` 后缀，REST 数据使用 `_snapshot` 后缀
  - WebSocket 表：`{exchange}_{type}_update`（如 `binance_account_update`）
  - REST 表：`{exchange}_{type}_snapshot`（如 `binance_account_snapshot`）
  - XT REST 表合并：`xt_spot_balances` 和 `xt_perp_balances` 合并为 `xt_account_snapshot`（通过 `exchange_type` 区分）

---

## 相关文档

- [多账号使用指南](../docs/MULTI_ACCOUNT_USAGE.md)
- [数据库迁移指南](../docs/MIGRATION_GUIDE.md)
- [API 文档](../docs/API.md)

