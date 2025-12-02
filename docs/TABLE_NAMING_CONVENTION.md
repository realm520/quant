# 数据库表命名规范

## 当前问题

当前表命名存在以下问题：
1. **WebSocket 和 REST 数据命名不一致**：
   - Binance WebSocket: `account_updates`, `binance_order_updates`
   - Binance REST: `binance_account_updates` (命名混乱)
   - XT WebSocket: `xt_account_updates`, `xt_order_updates`
   - XT REST: `xt_spot_balances`, `xt_perp_balances`, `xt_balance_rest` (混用)

2. **命名模式不统一**：
   - 有些用 `{exchange}_{type}`，有些用 `{type}_updates`
   - REST 数据有些用 `_balances`，有些用 `_rest`

## 命名规范方案

### 方案概述

使用统一的后缀来区分数据来源：
- **WebSocket 数据流**: `{exchange}_{type}_update`
- **REST API 快照**: `{exchange}_{type}_snapshot`

### 详细规范

#### 1. WebSocket 数据流表（实时推送）

格式：`{exchange}_{type}_update`

- `{exchange}`: 交易所名称（binance, xt, okx, gate）
- `{type}`: 数据类型（account, position, order, trade, spot, transfer）
- `_update`: WebSocket 实时更新后缀

**示例**：
- `binance_account_update` - Binance 账户更新（WebSocket）
- `binance_order_update` - Binance 订单更新（WebSocket）
- `binance_trade_update` - Binance 成交更新（WebSocket）
- `xt_account_update` - XT 账户更新（WebSocket）
- `xt_position_update` - XT 持仓更新（WebSocket）
- `xt_order_update` - XT 订单更新（WebSocket）
- `xt_trade_update` - XT 成交更新（WebSocket）
- `xt_spot_update` - XT 现货余额快照（WebSocket）
- `xt_transfer_update` - XT 资金划转（WebSocket）
- `okx_account_update` - OKX 账户更新（WebSocket）
- `okx_position_update` - OKX 持仓更新（WebSocket）
- `okx_order_update` - OKX 订单更新（WebSocket）
- `okx_trade_update` - OKX 成交更新（WebSocket）
- `gate_account_update` - Gate.io 账户更新（WebSocket）
- `gate_position_update` - Gate.io 持仓更新（WebSocket）
- `gate_order_update` - Gate.io 订单更新（WebSocket）
- `gate_trade_update` - Gate.io 成交更新（WebSocket）

#### 2. REST API 快照表（定时查询）

格式：`{exchange}_{type}_snapshot`

- `{exchange}`: 交易所名称（binance, xt, okx, gate）
- `{type}`: 数据类型（account, position, order）
- `_snapshot`: REST API 快照后缀

**示例**：
- `binance_account_snapshot` - Binance 账户余额快照（REST）
- `binance_position_snapshot` - Binance 持仓快照（REST）
- `binance_order_snapshot` - Binance 订单快照（REST）
- `xt_account_snapshot` - XT 账户余额快照（REST）
- `xt_position_snapshot` - XT 持仓快照（REST）
- `xt_order_snapshot` - XT 订单快照（REST）
- `okx_account_snapshot` - OKX 账户余额快照（REST）
- `okx_position_snapshot` - OKX 持仓快照（REST）
- `okx_order_snapshot` - OKX 订单快照（REST）
- `gate_account_snapshot` - Gate.io 账户余额快照（REST）
- `gate_position_snapshot` - Gate.io 持仓快照（REST）
- `gate_order_snapshot` - Gate.io 订单快照（REST）

#### 3. 系统表（保持不变）

- `listen_keys` - ListenKey 记录
- `connection_status` - WebSocket 连接状态
- `{exchange}_ws_connection` - 交易所 WebSocket 连接记录（如 `xt_ws_connection`）

## 命名对照表

### Binance

| 当前表名 | 新表名 | 说明 |
|---------|--------|------|
| `account_updates` | `binance_account_update` | WebSocket 账户更新 |
| `binance_order_updates` | `binance_order_update` | WebSocket 订单更新 |
| `binance_trade_updates` | `binance_trade_update` | WebSocket 成交更新 |
| `binance_account_updates` | `binance_account_snapshot` | REST 账户余额快照 |
| `binance_balance_rest` | `binance_account_snapshot` | REST 账户余额（合并） |
| `binance_position_rest` | `binance_position_snapshot` | REST 持仓快照 |
| `binance_order_rest` | `binance_order_snapshot` | REST 订单快照 |

### XT

| 当前表名 | 新表名 | 说明 |
|---------|--------|------|
| `xt_account_updates` | `xt_account_update` | WebSocket 账户更新 |
| `xt_spot_updates` | `xt_spot_update` | WebSocket 现货余额快照 |
| `xt_position_updates` | `xt_position_update` | WebSocket 持仓更新 |
| `xt_order_updates` | `xt_order_update` | WebSocket 订单更新 |
| `xt_trade_updates` | `xt_trade_update` | WebSocket 成交更新 |
| `xt_transfers` | `xt_transfer_update` | WebSocket 资金划转 |
| `xt_websocket_connections` | `xt_connection` | WebSocket 连接记录 |
| `xt_spot_balances` | `xt_account_snapshot` | REST 现货余额快照（合并到 account） |
| `xt_perp_balances` | `xt_account_snapshot` | REST 合约余额快照（合并到 account） |
| `xt_perp_positions` | `xt_position_snapshot` | REST 持仓快照 |
| `xt_rest_position_updates` | `xt_position_snapshot` | REST 持仓更新（合并） |
| `xt_balance_rest` | `xt_account_snapshot` | REST 账户余额（合并） |
| `xt_position_rest` | `xt_position_snapshot` | REST 持仓快照 |
| `xt_order_rest` | `xt_order_snapshot` | REST 订单快照 |

### OKX

| 当前表名 | 新表名 | 说明 |
|---------|--------|------|
| `okx_account_updates` | `okx_account_update` | WebSocket 账户更新 |
| `okx_position_updates` | `okx_position_update` | WebSocket 持仓更新 |
| `okx_order_updates` | `okx_order_update` | WebSocket 订单更新 |
| `okx_trade_updates` | `okx_trade_update` | WebSocket 成交更新 |
| `okx_balance_rest` | `okx_account_snapshot` | REST 账户余额快照 |
| `okx_position_rest` | `okx_position_snapshot` | REST 持仓快照 |
| `okx_order_rest` | `okx_order_snapshot` | REST 订单快照 |

### Gate.io

| 当前表名 | 新表名 | 说明 |
|---------|--------|------|
| `gate_account_updates` | `gate_account_update` | WebSocket 账户更新 |
| `gate_position_updates` | `gate_position_update` | WebSocket 持仓更新 |
| `gate_order_updates` | `gate_order_update` | WebSocket 订单更新 |
| `gate_trade_updates` | `gate_trade_update` | WebSocket 成交更新 |
| `gate_balance_rest` | `gate_account_snapshot` | REST 账户余额快照 |
| `gate_position_rest` | `gate_position_snapshot` | REST 持仓快照 |
| `gate_order_rest` | `gate_order_snapshot` | REST 订单快照 |

## 命名规则总结

1. **统一格式**：`{exchange}_{type}_{source}`
   - `{exchange}`: 交易所名称（小写，下划线分隔）
   - `{type}`: 数据类型（account, position, order, trade, spot, transfer）
   - `{source}`: 数据来源（`update` 或 `snapshot`）

2. **数据类型说明**：
   - `account`: 账户余额（包含所有资产）
   - `position`: 持仓信息
   - `order`: 订单信息
   - `trade`: 成交记录
   - `spot`: 现货余额（仅 XT 使用）
   - `transfer`: 资金划转（仅 XT 使用）

3. **数据来源说明**：
   - `_update`: WebSocket 实时推送数据
   - `_snapshot`: REST API 定时查询快照

4. **特殊表**：
   - 系统表保持原有命名（`listen_keys`, `connection_status`）
   - WebSocket 连接记录：`{exchange}_connection`（如 `xt_connection`）

## 优势

1. **语义清晰**：`update` 表示实时更新，`snapshot` 表示快照，更直观
2. **统一规范**：所有交易所使用相同的命名模式
3. **易于维护**：命名规则简单明了
4. **便于查询**：可以通过表名模式快速定位数据来源
5. **专业术语**：使用标准的数据库术语（snapshot）更专业

## 迁移建议

1. **创建新表**：按照新命名规范创建表
2. **数据迁移**：将旧表数据迁移到新表
3. **更新代码**：更新所有 SQLAlchemy 模型和查询代码
4. **测试验证**：确保数据迁移和代码更新正确
5. **删除旧表**：确认无误后删除旧表

## 注意事项

1. **向后兼容**：迁移期间可能需要同时支持新旧表名
2. **数据一致性**：确保迁移过程中数据不丢失
3. **索引重建**：新表需要重新创建索引
4. **查询更新**：所有查询代码需要更新表名

