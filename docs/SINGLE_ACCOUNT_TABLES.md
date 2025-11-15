# 单账号独立表功能说明

本文档说明如何使用单账号独立表功能，支持订阅、watch-account、watch-balance 等命令。

---

## 1. 功能特性

- ✅ **单账号订阅**: 支持单账号的所有种类订阅（account, position, order, trade）
- ✅ **watch-account**: 支持账号特定的表
- ✅ **watch-balance**: 支持账号特定的表
- ✅ **自动创建表**: 每次运行自动创建表，使用 `checkfirst=True` 避免重复创建
- ✅ **表命名规则**: `{base_table_name}_{account_id}`，例如 `xt_account_updates_account_001`

---

## 2. 使用方法

### 2.1 单账号订阅

```bash
# 订阅所有频道（account, position, order, trade）
cextools subscribe user-stream -x xt --account-id account_001

# 只订阅账户和持仓
cextools subscribe user-stream -x xt --account-id account_001 -c account,position

# 订阅所有频道，自动创建表
cextools subscribe user-stream -x xt --account-id account_001
```

**说明**:
- 如果提供 `--account-id`，数据会保存到账号特定的表中
- 表会在首次运行时自动创建，不会重复创建
- 支持所有频道：`account`, `position`, `order`, `trade`

### 2.2 watch-account 命令

```bash
# 使用账号特定的表
cextools account watch-account -x xt --account-id account_001

# 指定查询间隔
cextools account watch-account -x xt --account-id account_001 --interval 5

# 启用 Lark 告警
cextools account watch-account -x xt --account-id account_001 --enable-lark
```

**说明**:
- 如果提供 `--account-id`，数据会保存到账号特定的表中：
  - `xt_spot_balances_{account_id}`
  - `xt_perp_balances_{account_id}`
  - `xt_perp_positions_{account_id}`
- 表会在首次运行时自动创建

### 2.3 watch-balance 命令

```bash
# 使用账号特定的表（XT）
cextools account watch-balance -x xt -e perp --account-id account_001

# 指定查询间隔
cextools account watch-balance -x xt -e perp --account-id account_001 --interval 10
```

**说明**:
- 仅 XT 交易所支持账号特定的表
- 数据会保存到 `xt_account_updates_{account_id}` 表中
- 表会在首次运行时自动创建

---

## 3. 数据库表结构

### 3.1 WebSocket 数据表（订阅命令）

对于账号 `account_001`，会创建以下表：

- `xt_account_updates_account_001` - 账户余额更新
- `xt_spot_updates_account_001` - 现货余额快照
- `xt_position_updates_account_001` - 持仓更新
- `xt_order_updates_account_001` - 订单更新
- `xt_trade_updates_account_001` - 成交记录
- `xt_transfers_account_001` - 资金划转记录

### 3.2 REST API 数据表（watch-account 命令）

- `xt_spot_balances_account_001` - 现货余额记录
- `xt_perp_balances_account_001` - 合约余额记录
- `xt_perp_positions_account_001` - 合约仓位记录
- `xt_rest_position_updates_account_001` - 仓位定时更新（watch-positions）

### 3.3 watch-balance 数据表

- `xt_account_updates_account_001` - 账户余额更新（复用 WebSocket 表）

---

## 4. 表自动创建机制

### 4.1 创建时机

- **订阅命令**: 如果提供了 `--account-id`，会在启动时自动创建表
- **watch-account**: 如果提供了 `--account-id`，会在首次运行时自动创建表
- **watch-balance**: 如果提供了 `--account-id`，会在首次运行时自动创建表

### 4.2 防重复创建

所有表创建都使用 `checkfirst=True`，确保：
- 如果表已存在，不会重复创建
- 不会报错，可以安全地多次运行

### 4.3 创建逻辑

```python
# 示例代码
from tri_arb.storage.xt_multi_account_models import create_account_table_models

account_models = create_account_table_models(account_id)
async with db_manager.async_engine.begin() as conn:
    for model_class in account_models.values():
        await conn.run_sync(
            lambda sync_conn, m=model_class: m.metadata.create_all(
                sync_conn, checkfirst=True
            )
        )
```

---

## 5. 查询数据示例

### 5.1 查询账号特定的账户余额

```sql
-- 查询 account_001 的最新余额
SELECT * FROM xt_account_updates_account_001
ORDER BY update_time DESC
LIMIT 10;
```

### 5.2 查询账号特定的合约余额

```sql
-- 查询 account_001 的合约余额
SELECT * FROM xt_perp_balances_account_001
WHERE asset = 'USDT'
ORDER BY query_time DESC
LIMIT 10;
```

### 5.3 查询账号特定的持仓

```sql
-- 查询 account_001 的持仓
SELECT * FROM xt_perp_positions_account_001
ORDER BY query_time DESC
LIMIT 10;
```

---

## 6. 注意事项

### 6.1 账号ID命名

- 使用字母、数字和下划线
- 避免特殊字符（`-`, `.`, 空格等）
- 建议使用有意义的命名，如 `account_001`, `main_account`

### 6.2 表数量

- 每个账号创建约 10 个表
- 10 个账号 = 100 个表
- 确保数据库支持足够的表数量

### 6.3 兼容性

- **账号特定表**: 仅支持 XT 交易所
- **其他交易所**: 仍使用共享表（Binance、OKX、Gate.io）

### 6.4 数据隔离

- 每个账号的数据完全隔离
- 不同账号的数据不会混淆
- 便于多账号管理和查询

---

## 7. 命令参数总结

### 7.1 subscribe user-stream

| 参数 | 说明 | 示例 |
|------|------|------|
| `--account-id` / `-a` | 账号ID（可选，仅XT） | `account_001` |
| `--channels` / `-c` | 订阅频道 | `account,position,order,trade` |
| `--create-tables` | 显式创建表 | - |

### 7.2 watch-account

| 参数 | 说明 | 示例 |
|------|------|------|
| `--account-id` / `-a` | 账号ID（可选，仅XT） | `account_001` |
| `--interval` / `-i` | 查询间隔（分钟） | `10` |
| `--enable-lark` | 启用 Lark 告警 | - |

### 7.3 watch-balance

| 参数 | 说明 | 示例 |
|------|------|------|
| `--account-id` / `-a` | 账号ID（可选，仅XT） | `account_001` |
| `--interval` / `-i` | 查询间隔（分钟） | `5` |
| `--exchange-type` / `-e` | 交易类型 | `perp` |

---

## 8. 完整示例

### 8.1 场景：监控单个账号

```bash
# 1. 订阅 WebSocket 数据流（所有频道）
cextools subscribe user-stream -x xt --account-id account_001 -c account,position,order,trade

# 2. 定时查询账户数据（每10分钟）
cextools account watch-account -x xt --account-id account_001 --interval 10

# 3. 定时查询余额（每5分钟）
cextools account watch-balance -x xt -e perp --account-id account_001 --interval 5
```

### 8.2 场景：监控多个账号

```bash
# 账号 1
cextools subscribe user-stream -x xt --account-id account_001 &
cextools account watch-account -x xt --account-id account_001 --interval 10 &

# 账号 2
cextools subscribe user-stream -x xt --account-id account_002 &
cextools account watch-account -x xt --account-id account_002 --interval 10 &
```

---

## 9. 与多账号订阅的区别

| 特性 | 单账号订阅 | 多账号订阅 |
|------|-----------|-----------|
| 配置文件 | 不需要 | 需要 JSON 配置文件 |
| 账号数量 | 1 个 | 多个（建议 10-50 个） |
| 命令 | `subscribe user-stream -a account_001` | `subscribe multi-account` |
| 使用场景 | 单个账号监控 | 批量账号监控 |

---

## 10. 故障排查

### 10.1 表创建失败

**错误**: `relation "xt_account_updates_xxx" already exists`

**解决**: 这是正常的，表已存在时不会重复创建（使用 `checkfirst=True`）

### 10.2 账号ID无效

**错误**: 账号ID包含特殊字符

**解决**: 使用字母、数字和下划线，例如 `account_001`

### 10.3 数据未保存到账号表

**原因**: 未提供 `--account-id` 参数

**解决**: 添加 `--account-id account_001` 参数

---

## 11. 总结

单账号独立表功能提供了：

- ✅ **灵活的订阅**: 支持所有频道（account, position, order, trade）
- ✅ **完整的命令支持**: subscribe、watch-account、watch-balance
- ✅ **自动表管理**: 自动创建表，不会重复创建
- ✅ **数据隔离**: 每个账号的数据完全独立
- ✅ **易于查询**: 账号特定的表便于查询和管理

如有问题，请参考主文档或提交 Issue。

