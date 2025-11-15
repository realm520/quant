# 账号特定表支持清单

本文档列出所有支持账号特定表的单账号操作，确保多账号功能完整。

---

## ✅ 已支持账号特定表的操作

### 1. WebSocket 订阅 (`subscribe user-stream`)

**命令**: `cextools subscribe user-stream -x xt --account-id account_001`

**支持的表**:
- ✅ `xt_account_updates_{account_id}` - 账户余额更新
- ✅ `xt_spot_updates_{account_id}` - 现货余额快照
- ✅ `xt_position_updates_{account_id}` - 持仓更新
- ✅ `xt_order_updates_{account_id}` - 订单更新
- ✅ `xt_trade_updates_{account_id}` - 成交记录
- ✅ `xt_transfers_{account_id}` - 资金划转记录

**实现位置**:
- `src/tri_arb/cli/commands/subscribe.py` - 添加了 `--account-id` 参数
- `src/tri_arb/services/xt_user_stream.py` - 所有保存方法使用 `_get_model()` 动态获取表模型

---

### 2. 定时账户监控 (`watch-account`)

**命令**: `cextools account watch-account -x xt --account-id account_001`

**支持的表**:
- ✅ `xt_spot_balances_{account_id}` - 现货余额记录
- ✅ `xt_perp_balances_{account_id}` - 合约余额记录
- ✅ `xt_perp_positions_{account_id}` - 合约仓位记录

**实现位置**:
- `src/tri_arb/cli/commands/account.py` - 添加了 `--account-id` 参数
- `src/tri_arb/services/xt_rest_data_service.py` - 所有保存方法支持账号特定的表模型

---

### 3. 定时余额监控 (`watch-balance`)

**命令**: `cextools account watch-balance -x xt -e perp --account-id account_001`

**支持的表**:
- ✅ `xt_account_updates_{account_id}` - 账户余额更新（复用 WebSocket 表）

**实现位置**:
- `src/tri_arb/cli/commands/account.py` - 添加了 `--account-id` 参数
- 使用动态表模型保存数据

---

### 4. 定时持仓监控 (`watch-positions`)

**命令**: `cextools account watch-positions -x xt -e perp --account-id account_001`

**支持的表**:
- ✅ `xt_rest_position_updates_{account_id}` - 仓位定时更新记录

**实现位置**:
- `src/tri_arb/cli/commands/account.py` - 添加了 `--account-id` 参数
- `src/tri_arb/services/xt_rest_data_service.py` - `save_position_updates()` 方法支持账号特定的表

---

## 📋 表创建机制

### 自动创建

所有命令在首次运行时都会自动创建账号特定的表：

1. **订阅命令**: 如果提供了 `--account-id`，会在启动时自动创建表
2. **watch-account**: 如果提供了 `--account-id`，会在首次运行时自动创建表
3. **watch-balance**: 如果提供了 `--account-id`，会在首次运行时自动创建表
4. **watch-positions**: 如果提供了 `--account-id`，会在首次运行时自动创建表

### 防重复创建

所有表创建都使用 `checkfirst=True`，确保：
- ✅ 如果表已存在，不会重复创建
- ✅ 不会报错，可以安全地多次运行
- ✅ 支持增量添加新账号

---

## 🔧 实现细节

### XTUserStreamService

**修改内容**:
- 添加了 `account_id` 和 `account_models` 属性
- 添加了 `_get_model()` 方法，动态获取表模型
- 所有保存方法都使用 `_get_model()` 获取表模型：
  - `_save_account_update()` → `XTAccountUpdate`
  - `_save_position_update()` → `XTPositionUpdate`
  - `_save_order_update()` → `XTOrderUpdate`
  - `_save_trade_update()` → `XTTradeUpdate`
  - `_save_transfer()` → `XTTransfer`
  - `_save_spot_update()` → `XTSpotUpdate`
- 所有查询语句也使用动态表模型

### XTRestDataService

**修改内容**:
- `__init__()` 方法接受 `account_id` 参数
- 如果提供了 `account_id`，加载账号特定的表模型
- 所有保存方法都支持账号特定的表：
  - `save_spot_balance()` → `XTSpotBalance`
  - `save_perp_balance()` → `XTPerpBalance`
  - `save_perp_positions()` → `XTPerpPosition`
  - `save_position_updates()` → `XTRestPositionUpdate`
- 添加了 `ensure_account_tables()` 方法，确保表已创建

---

## 📊 数据表映射

| 操作 | 默认表 | 账号特定表（account_001） |
|------|--------|---------------------------|
| WebSocket 账户更新 | `xt_account_updates` | `xt_account_updates_account_001` |
| WebSocket 现货快照 | `xt_spot_updates` | `xt_spot_updates_account_001` |
| WebSocket 持仓更新 | `xt_position_updates` | `xt_position_updates_account_001` |
| WebSocket 订单更新 | `xt_order_updates` | `xt_order_updates_account_001` |
| WebSocket 成交记录 | `xt_trade_updates` | `xt_trade_updates_account_001` |
| WebSocket 资金划转 | `xt_transfers` | `xt_transfers_account_001` |
| REST 现货余额 | `xt_spot_balances` | `xt_spot_balances_account_001` |
| REST 合约余额 | `xt_perp_balances` | `xt_perp_balances_account_001` |
| REST 合约仓位 | `xt_perp_positions` | `xt_perp_positions_account_001` |
| REST 仓位更新 | `xt_rest_position_updates` | `xt_rest_position_updates_account_001` |

---

## ✅ 验证清单

- [x] `subscribe user-stream` 支持账号ID
- [x] `watch-account` 支持账号ID
- [x] `watch-balance` 支持账号ID
- [x] `watch-positions` 支持账号ID
- [x] 所有保存方法使用动态表模型
- [x] 所有查询语句使用动态表模型
- [x] 表自动创建机制（checkfirst=True）
- [x] 不会重复创建表

---

## 🎯 使用示例

### 单账号订阅（所有频道）

```bash
cextools subscribe user-stream -x xt --account-id account_001 -c account,position,order,trade
```

### 单账号定时监控

```bash
# 账户数据（余额+仓位）
cextools account watch-account -x xt --account-id account_001 --interval 10

# 余额监控
cextools account watch-balance -x xt -e perp --account-id account_001 --interval 5

# 持仓监控
cextools account watch-positions -x xt -e perp --account-id account_001 --interval 1
```

### 多账号同时监控

```bash
# 账号 1
cextools subscribe user-stream -x xt --account-id account_001 &
cextools account watch-account -x xt --account-id account_001 --interval 10 &

# 账号 2
cextools subscribe user-stream -x xt --account-id account_002 &
cextools account watch-account -x xt --account-id account_002 --interval 10 &
```

---

## 📝 注意事项

1. **账号ID命名**: 使用字母、数字和下划线，例如 `account_001`
2. **仅支持 XT**: 账号特定表功能目前仅支持 XT 交易所
3. **表自动创建**: 每次运行会自动检查并创建表，不会重复创建
4. **数据隔离**: 每个账号的数据保存在独立的表中
5. **向后兼容**: 如果不提供 `--account-id`，数据仍保存到默认的共享表中

---

## 🔍 检查方法

### 验证表是否创建

```sql
-- 查看所有账号特定的表
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name LIKE 'xt_%_account_001'
ORDER BY table_name;
```

### 验证数据是否正确保存

```sql
-- 查询账号特定的账户余额
SELECT * FROM xt_account_updates_account_001
ORDER BY update_time DESC
LIMIT 10;

-- 查询账号特定的合约余额
SELECT * FROM xt_perp_balances_account_001
ORDER BY query_time DESC
LIMIT 10;
```

---

## 📚 相关文档

- [单账号独立表使用指南](SINGLE_ACCOUNT_TABLES.md)
- [多账号订阅使用指南](MULTI_ACCOUNT_USAGE.md)
- [XT 数据库表结构](XT_DATABASE_SCHEMA.md)

---

**最后更新**: 2025-01-XX  
**状态**: ✅ 所有单账号操作已支持账号特定表

