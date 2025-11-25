# XT 数据库表结构文档

本文档详细列出了所有 XT 交易所相关的数据库表及其字段信息。

---

## 目录

- [REST API 相关表](#rest-api-相关表)
  - [xt_spot_balances](#xt_spot_balances)
  - [xt_perp_balances](#xt_perp_balances)
  - [xt_perp_positions](#xt_perp_positions)
  - [xt_rest_position_updates](#xt_rest_position_updates)
- [WebSocket 相关表](#websocket-相关表)
  - [xt_account_updates](#xt_account_updates)
  - [xt_spot_updates](#xt_spot_updates)
  - [xt_position_updates](#xt_position_updates)
  - [xt_order_updates](#xt_order_updates)
  - [xt_trade_updates](#xt_trade_updates)
  - [xt_transfers](#xt_transfers)
  - [xt_websocket_connections](#xt_websocket_connections)

---

## REST API 相关表

### xt_spot_balances

**表名**: `xt_spot_balances`  
**说明**: XT 现货账户余额记录，存储现货账户的余额快照。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| query_time | DateTime | NOT NULL, INDEX | 查询时间 |
| query_type | String(20) | NOT NULL, INDEX | 查询类型：manual（手动）、scheduled（定时） |
| asset | String(20) | NOT NULL, INDEX | 资产类型（如 USDT、BTC） |
| free | Numeric(30, 10) | NOT NULL | 可用余额 |
| locked | Numeric(30, 10) | NOT NULL | 冻结余额 |
| total | Numeric(30, 10) | NOT NULL | 总余额 |
| raw_data | Text | NULL | 完整 JSON 原始数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_spot_balance_asset_time` (asset, query_time)
- `idx_xt_spot_balance_query_type_time` (query_type, query_time)

---

### xt_perp_balances

**表名**: `xt_perp_balances`  
**说明**: XT 合约账户余额记录，存储永续合约账户的余额快照。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| query_time | DateTime | NOT NULL, INDEX | 查询时间 |
| query_type | String(20) | NOT NULL, INDEX | 查询类型：manual（手动）、scheduled（定时） |
| asset | String(20) | NOT NULL, INDEX | 资产类型（如 USDT、BTC） |
| free | Numeric(30, 10) | NOT NULL | 可用余额 |
| locked | Numeric(30, 10) | NOT NULL | 冻结余额 |
| total | Numeric(30, 10) | NOT NULL | 总余额 |
| unrealized_pnl | Numeric(30, 10) | NULL | 未实现盈亏 |
| realized_pnl | Numeric(30, 10) | NULL | 已实现盈亏 |
| equity | Numeric(30, 10) | NULL | 总权益（余额 + 未实现盈亏） |
| margin | Numeric(30, 10) | NULL | 保证金 |
| margin_ratio | Numeric(10, 4) | NULL | 保证金率 |
| raw_data | Text | NULL | 完整 JSON 原始数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_perp_balance_asset_time` (asset, query_time)
- `idx_xt_perp_balance_query_type_time` (query_type, query_time)

---

### xt_perp_positions

**表名**: `xt_perp_positions`  
**说明**: XT 合约账户仓位记录，存储永续合约账户的持仓快照。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| query_time | DateTime | NOT NULL, INDEX | 查询时间 |
| query_type | String(20) | NOT NULL, INDEX | 查询类型：manual（手动）、scheduled（定时） |
| symbol | String(20) | NOT NULL, INDEX | 交易对（如 BTC/USDT） |
| position_side | String(10) | NOT NULL | 持仓方向：LONG（做多）、SHORT（做空） |
| position_amount | Numeric(30, 10) | NOT NULL | 持仓数量 |
| entry_price | Numeric(30, 10) | NULL | 开仓均价 |
| mark_price | Numeric(30, 10) | NULL | 标记价格 |
| unrealized_pnl | Numeric(30, 10) | NULL | 未实现盈亏 |
| realized_pnl | Numeric(30, 10) | NULL | 已实现盈亏 |
| percentage | Numeric(10, 4) | NULL | 盈亏百分比 |
| notional | Numeric(30, 10) | NULL | 名义价值 |
| isolated | Boolean | DEFAULT False | 是否逐仓 |
| leverage | String(10) | NULL | 杠杆倍数 |
| liquidation_price | Numeric(30, 10) | NULL | 强平价格 |
| margin | Numeric(30, 10) | NULL | 保证金 |
| roe | Numeric(10, 4) | NULL | 收益率百分比 |
| maintenance_margin | Numeric(30, 10) | NULL | 维持保证金 |
| raw_data | Text | NULL | 完整 JSON 原始数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_perp_position_symbol_time` (symbol, query_time)
- `idx_xt_perp_position_side_time` (position_side, query_time)
- `idx_xt_perp_position_query_type_time` (query_type, query_time)

---

### xt_rest_position_updates

**表名**: `xt_rest_position_updates`  
**说明**: XT 永续仓位定时更新记录，用于 `watch-positions` 命令。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| query_time | DateTime | NOT NULL, INDEX | 查询时间 |
| query_type | String(20) | NOT NULL, INDEX | 查询类型：manual（手动）、scheduled（定时） |
| symbol | String(20) | NOT NULL, INDEX | 交易对 |
| position_side | String(10) | NOT NULL | 持仓方向：LONG、SHORT |
| position_amount | Numeric(30, 10) | NOT NULL | 持仓数量 |
| entry_price | Numeric(30, 10) | NULL | 开仓均价 |
| mark_price | Numeric(30, 10) | NULL | 标记价格 |
| liquidation_price | Numeric(30, 10) | NULL | 强平价格 |
| unrealized_pnl | Numeric(30, 10) | NULL | 未实现盈亏 |
| realized_pnl | Numeric(30, 10) | NULL | 已实现盈亏 |
| margin | Numeric(30, 10) | NULL | 保证金 |
| leverage | String(10) | NULL | 杠杆倍数 |
| roe | Numeric(10, 4) | NULL | 收益率百分比 |
| maintenance_margin | Numeric(30, 10) | NULL | 维持保证金 |
| raw_data | Text | NULL | 完整 JSON 原始数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_rest_position_symbol_time` (symbol, query_time)
- `idx_xt_rest_position_side_time` (position_side, query_time)
- `idx_xt_rest_position_query_type_time` (query_type, query_time)

---

## WebSocket 相关表

### xt_account_updates

**表名**: `xt_account_updates`  
**说明**: XT WebSocket 账户信息更新记录，存储 WebSocket 推送的账户余额变化。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| update_time | DateTime | NOT NULL, INDEX | 更新时间 |
| currency | String(20) | NOT NULL, INDEX | 币种 |
| available | Numeric(30, 10) | NOT NULL | 可用余额 |
| frozen | Numeric(30, 10) | NOT NULL | 冻结余额 |
| total | Numeric(30, 10) | NOT NULL | 总余额 |
| raw_data | Text | NULL | 完整 JSON 数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_account_currency_time` (currency, update_time)
- `idx_xt_account_time` (update_time)

---

### xt_spot_updates

**表名**: `xt_spot_updates`  
**说明**: XT 现货账户余额快照，在处理合约账户余额变化时，记录对应时间点的现货账户余额。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| update_time | DateTime | NOT NULL, INDEX | 记录时间 |
| currency | String(20) | NOT NULL, INDEX | 币种 |
| available | Numeric(30, 10) | NOT NULL | 可用余额 |
| frozen | Numeric(30, 10) | NOT NULL | 冻结余额 |
| total | Numeric(30, 10) | NOT NULL | 总余额 |
| raw_data | Text | NULL | 完整 JSON 数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_spot_currency_time` (currency, update_time)
- `idx_xt_spot_time` (update_time)

---

### xt_position_updates

**表名**: `xt_position_updates`  
**说明**: XT WebSocket 持仓更新记录，存储 WebSocket 推送的持仓变化。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| update_time | DateTime | NOT NULL, INDEX | 更新时间 |
| symbol | String(20) | NOT NULL, INDEX | 交易对 |
| side | String(10) | NOT NULL | 持仓方向：LONG、SHORT |
| quantity | Numeric(30, 10) | NOT NULL | 持仓数量 |
| entry_price | Numeric(30, 10) | NULL | 开仓均价 |
| mark_price | Numeric(30, 10) | NULL | 标记价格 |
| liquidation_price | Numeric(30, 10) | NULL | 强平价格 |
| unrealized_pnl | Numeric(30, 10) | NULL | 未实现盈亏 |
| leverage | Integer | NULL | 杠杆倍数 |
| margin | Numeric(30, 10) | NULL | 保证金 |
| roe | Numeric(10, 4) | NULL | 收益率 |
| raw_data | Text | NULL | 完整 JSON 数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_position_symbol_time` (symbol, update_time)
- `idx_xt_position_side_time` (side, update_time)
- `idx_xt_position_time` (update_time)

---

### xt_order_updates

**表名**: `xt_order_updates`  
**说明**: XT WebSocket 订单更新记录，存储 WebSocket 推送的订单状态变化。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| update_time | DateTime | NOT NULL, INDEX | 更新时间 |
| symbol | String(20) | NOT NULL, INDEX | 交易对 |
| order_id | String(50) | NOT NULL, INDEX | 订单ID |
| client_order_id | String(50) | NULL, INDEX | 客户订单ID |
| side | String(10) | NOT NULL | 买卖方向：BUY、SELL |
| order_type | String(30) | NOT NULL | 订单类型 |
| position_side | String(10) | NULL | 持仓方向 |
| quantity | Numeric(30, 10) | NOT NULL | 订单数量 |
| price | Numeric(30, 10) | NULL | 订单价格 |
| filled_quantity | Numeric(30, 10) | NOT NULL | 已成交数量 |
| status | String(20) | NOT NULL, INDEX | 订单状态 |
| time_in_force | String(10) | NULL | 有效方式 |
| create_time | DateTime | NULL | 创建时间 |
| update_time_order | DateTime | NULL | 订单更新时间 |
| raw_data | Text | NULL | 完整 JSON 数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_order_id_time` (order_id, update_time)
- `idx_xt_order_symbol_status_time` (symbol, status, update_time)
- `idx_xt_order_time` (update_time)
- **唯一约束**: `uq_xt_order_id_time` (order_id, update_time) - 防止重复订单记录

---

### xt_trade_updates

**表名**: `xt_trade_updates`  
**说明**: XT WebSocket 成交记录，存储 WebSocket 推送的实时成交信息。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| update_time | DateTime | NOT NULL, INDEX | 更新时间 |
| symbol | String(20) | NOT NULL, INDEX | 交易对 |
| order_id | String(50) | NOT NULL, INDEX | 订单ID |
| trade_id | String(50) | NOT NULL, UNIQUE, INDEX | 成交ID（唯一） |
| side | String(10) | NOT NULL | 买卖方向：BUY、SELL |
| price | Numeric(30, 10) | NOT NULL | 成交价格 |
| quantity | Numeric(30, 10) | NOT NULL | 成交数量 |
| quote_quantity | Numeric(30, 10) | NOT NULL | 成交金额 |
| commission | Numeric(30, 10) | NULL | 手续费 |
| commission_asset | String(20) | NULL | 手续费资产 |
| is_maker | Boolean | DEFAULT False | 是否为挂单方（Maker） |
| position_side | String(10) | NULL | 持仓方向：LONG、SHORT |
| raw_data | Text | NULL | 完整 JSON 数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_trade_symbol_time` (symbol, update_time)
- `idx_xt_trade_order_trade` (order_id, trade_id)
- `idx_xt_trade_time` (update_time)

---

### xt_transfers

**表名**: `xt_transfers`  
**说明**: XT 资金划转记录，通过分析账户余额变化识别资金划转（充值、提现、账户间划转等）。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigInteger | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| transfer_time | DateTime | NOT NULL, INDEX | 划转时间 |
| currency | String(20) | NOT NULL, INDEX | 币种 |
| amount | Numeric(30, 10) | NOT NULL | 划转金额（正数=转入，负数=转出） |
| transfer_type | String(20) | NULL, INDEX | 划转类型：DEPOSIT（充值）、WITHDRAW（提现）、TRANSFER（账户间划转）、UNKNOWN（未知） |
| balance_before | Numeric(30, 10) | NULL | 划转前余额 |
| balance_after | Numeric(30, 10) | NOT NULL | 划转后余额 |
| related_order_id | String(50) | NULL | 关联订单ID（如果有） |
| related_trade_id | String(50) | NULL | 关联成交ID（如果有） |
| notes | Text | NULL | 备注信息 |
| raw_data | Text | NULL | 完整 JSON 数据 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_transfer_currency_time` (currency, transfer_time)
- `idx_xt_transfer_time` (transfer_time)
- `idx_xt_transfer_type` (transfer_type)

---

### xt_websocket_connections

**表名**: `xt_websocket_connections`  
**说明**: XT WebSocket 连接记录，存储 WebSocket 连接状态和重连信息。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | Integer | PRIMARY KEY, AUTO_INCREMENT | 主键，自增 |
| connection_id | String(100) | NOT NULL, UNIQUE | 连接ID（唯一） |
| start_time | DateTime | NOT NULL | 开始时间 |
| end_time | DateTime | NULL | 结束时间 |
| is_active | Boolean | DEFAULT True, INDEX | 是否活跃 |
| total_messages | Integer | DEFAULT 0 | 总消息数 |
| account_updates | Integer | DEFAULT 0 | 账户更新数 |
| position_updates | Integer | DEFAULT 0 | 持仓更新数 |
| order_updates | Integer | DEFAULT 0 | 订单更新数 |
| trade_updates | Integer | DEFAULT 0 | 成交更新数 |
| reconnect_count | Integer | DEFAULT 0 | 重连次数 |
| last_reconnect_time | DateTime | NULL | 最后重连时间 |
| last_error | Text | NULL | 最后错误信息 |
| data_sync_count | Integer | DEFAULT 0 | 数据同步次数 |
| last_sync_time | DateTime | NULL | 最后同步时间 |
| raw_data | Text | NULL | 配置信息 |
| created_at | DateTime | NOT NULL, DEFAULT utcnow | 记录创建时间 |

**索引**:
- `idx_xt_ws_active` (is_active)
- `idx_xt_ws_start_time` (start_time)

---

## 数据类型说明

- **BigInteger**: 大整数类型，用于主键和 ID
- **Integer**: 整数类型
- **String(n)**: 字符串类型，n 为最大长度
- **Numeric(p, s)**: 精确数值类型，p 为总位数，s 为小数位数
- **Boolean**: 布尔类型
- **DateTime**: 日期时间类型
- **Text**: 文本类型，用于存储长文本或 JSON 数据

---

## 查询示例

### 查询最新的合约账户余额

```sql
SELECT * FROM xt_perp_balances 
WHERE asset = 'USDT' 
ORDER BY query_time DESC 
LIMIT 1;
```

### 查询所有持仓记录

```sql
SELECT symbol, position_side, position_amount, unrealized_pnl, roe 
FROM xt_perp_positions 
WHERE query_time >= NOW() - INTERVAL '1 day'
ORDER BY query_time DESC;
```

### 查询资金划转记录

```sql
SELECT transfer_time, currency, amount, transfer_type, balance_after 
FROM xt_transfers 
WHERE currency = 'USDT' 
  AND transfer_time >= NOW() - INTERVAL '7 days'
ORDER BY transfer_time DESC;
```

### 查询 WebSocket 订单更新

```sql
SELECT symbol, order_id, side, status, filled_quantity, update_time 
FROM xt_order_updates 
WHERE symbol = 'BTC_USDT' 
  AND status = 'FILLED'
ORDER BY update_time DESC;
```

---

## 注意事项

1. **时间字段**: 所有时间字段使用 UTC 时间，查询时请注意时区转换。
2. **数值精度**: `Numeric(30, 10)` 表示最多 30 位数字，其中 10 位为小数部分。
3. **原始数据**: `raw_data` 字段存储完整的 JSON 原始数据，可用于数据追溯和调试。
4. **索引优化**: 已为常用查询字段创建索引，请根据实际查询模式调整。
5. **唯一约束**: `xt_trade_updates.trade_id` 和 `xt_order_updates(order_id, update_time)` 有唯一约束，防止重复数据。

---

最后更新: 2025-11-11

