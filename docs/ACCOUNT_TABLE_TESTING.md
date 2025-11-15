# 账号特定表功能测试指南

本文档列出所有支持账号特定表的命令，方便在服务器上测试。

---

## 📋 前置准备

### 1. 环境变量设置

```bash
# 设置数据库连接
export DATABASE_URL="postgresql+asyncpg://postgres:password@localhost:5432/trading"

# 设置 XT API 密钥（可选，也可以通过命令行参数提供）
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
```

### 2. 账号ID命名规则

- 使用字母、数字和下划线
- 示例：`account_001`, `main_account`, `test_001`
- 避免特殊字符（`-`, `.`, 空格等）

---

## 🧪 测试命令清单

### 1. 单账号 WebSocket 订阅

**命令**: `cextools subscribe user-stream`

**功能**: 实时订阅账户、持仓、订单、成交等 WebSocket 数据流

**测试命令**:

```bash
# 订阅所有频道（account, position, order, trade）
cextools subscribe user-stream -x xt --account-id account_001

# 只订阅账户和持仓
cextools subscribe user-stream -x xt --account-id account_001 -c account,position

# 只订阅账户
cextools subscribe user-stream -x xt --account-id account_001 -c account

# 使用 JSON 输出格式
cextools subscribe user-stream -x xt --account-id account_001 --output json

# 禁用数据同步（不推荐）
cextools subscribe user-stream -x xt --account-id account_001 --disable-data-sync
```

**验证表**:
- `xt_account_updates_account_001`
- `xt_spot_updates_account_001`
- `xt_position_updates_account_001`
- `xt_order_updates_account_001`
- `xt_trade_updates_account_001`
- `xt_transfers_account_001`

**验证 SQL**:
```sql
-- 查看账户余额更新
SELECT * FROM xt_account_updates_account_001 ORDER BY update_time DESC LIMIT 10;

-- 查看持仓更新
SELECT * FROM xt_position_updates_account_001 ORDER BY update_time DESC LIMIT 10;

-- 查看资金划转
SELECT * FROM xt_transfers_account_001 ORDER BY transfer_time DESC LIMIT 10;
```

---

### 2. 定时账户数据监控

**命令**: `cextools account watch-account`

**功能**: 定时获取现货余额、合约余额、合约仓位，并保存到数据库

**测试命令**:

```bash
# 默认 10 分钟间隔
cextools account watch-account -x xt --account-id account_001

# 5 分钟间隔
cextools account watch-account -x xt --account-id account_001 --interval 5

# 启用 Lark 告警
cextools account watch-account -x xt --account-id account_001 --enable-lark --lark-webhook "https://..."

# 指定指标配置文件
cextools account watch-account -x xt --account-id account_001 --metrics-config config/metrics.yaml

# 禁用指标评估
cextools account watch-account -x xt --account-id account_001 --disable-metrics
```

**使用配置文件方式**:

```bash
# 从配置文件读取单个账号信息（API密钥、Lark配置等）
cextools account watch-account -x xt --config config/accounts.json --account-id account_001

# 同时监控多个账号（只监控 enabled: true 的账号）
cextools account watch-account -x xt --config config/accounts.json --accounts account_001,account_002

# 监控配置文件中所有启用的账号
cextools account watch-account -x xt --config config/accounts.json --all-accounts

# 从配置文件读取并启用 Lark 告警
cextools account watch-account -x xt --config config/accounts.json --account-id account_001 --enable-lark

# 自定义间隔
cextools account watch-account -x xt --config config/accounts.json --account-id account_001 --interval 5
```

**多账号模式说明**:
- `--accounts account_001,account_002`: 同时监控指定的多个账号（逗号分隔），只监控 `enabled: true` 的账号
- `--all-accounts`: 监控配置文件中所有 `enabled: true` 的账号
- 多账号模式下，每个账号使用独立的数据库表和连接
- 所有账号的查询间隔相同，但查询时间可能略有差异（避免同时连接过多）
- 输出会显示账号标识，便于区分不同账号的数据
- **重要**: 只有 `enabled: true` 的账号才会被监控，`enabled: false` 的账号会被自动跳过

**验证表**:
- `xt_spot_balances_account_001`
- `xt_perp_balances_account_001`
- `xt_perp_positions_account_001`

**验证 SQL**:
```sql
-- 查看现货余额
SELECT * FROM xt_spot_balances_account_001 
WHERE asset = 'USDT' 
ORDER BY query_time DESC LIMIT 10;

-- 查看合约余额
SELECT * FROM xt_perp_balances_account_001 
WHERE asset = 'USDT' 
ORDER BY query_time DESC LIMIT 10;

-- 查看合约仓位
SELECT * FROM xt_perp_positions_account_001 
ORDER BY query_time DESC LIMIT 10;
```

---

### 3. 定时余额监控

**命令**: `cextools account watch-balance`

**功能**: 定时查询账户余额，持续监控账户变化

**测试命令**:

```bash
# 合约账户余额，默认 5 分钟间隔
cextools account watch-balance -x xt -e perp --account-id account_001

# 现货账户余额，1 分钟间隔
cextools account watch-balance -x xt -e spot --account-id account_001 --interval 1

# 10 分钟间隔
cextools account watch-balance -x xt -e perp --account-id account_001 --interval 10

# JSON 输出格式
cextools account watch-balance -x xt -e perp --account-id account_001 --output json
```

**使用配置文件方式**:

```bash
# 从配置文件读取账号信息（API密钥等）
cextools account watch-balance -x xt -e perp --config config/accounts.json --account-id account_001

# 同时监控多个账号（只监控 enabled: true 的账号）
cextools account watch-balance -x xt -e perp --config config/accounts.json --accounts account_001,account_002

# 监控配置文件中所有启用的账号
cextools account watch-balance -x xt -e perp --config config/accounts.json --all-accounts

# 自定义间隔
cextools account watch-balance -x xt -e perp --config config/accounts.json --account-id account_001 --interval 5
```

**多账号模式说明**:
- `--accounts account_001,account_002`: 同时监控指定的多个账号（逗号分隔），只监控 `enabled: true` 的账号
- `--all-accounts`: 监控配置文件中所有 `enabled: true` 的账号
- 多账号模式下，每个账号使用独立的数据库表和连接
- 所有账号的查询间隔相同，但查询时间可能略有差异（避免同时连接过多）
- 输出会显示账号标识，便于区分不同账号的数据

**验证表**:
- `xt_account_updates_account_001`（复用 WebSocket 表）

**验证 SQL**:
```sql
-- 查看余额更新记录
SELECT * FROM xt_account_updates_account_001 
WHERE currency = 'USDT' 
ORDER BY update_time DESC LIMIT 10;
```

---

### 4. 定时持仓监控

**命令**: `cextools account watch-positions`

**功能**: 定时查询永续合约持仓，持续监控持仓变化

**测试命令**:

```bash
# 默认 1 分钟间隔
cextools account watch-positions -x xt -e perp --account-id account_001

# 5 分钟间隔
cextools account watch-positions -x xt -e perp --account-id account_001 --interval 5

# 只监控特定交易对
cextools account watch-positions -x xt -e perp --account-id account_001 -s BTC/USDT

# 启用 Lark 告警
cextools account watch-positions -x xt -e perp --account-id account_001 --enable-lark --lark-webhook "https://..."

# JSON 输出格式
cextools account watch-positions -x xt -e perp --account-id account_001 --output json
```

**使用配置文件方式**:

`watch-positions` 命令支持从配置文件读取账号信息，并支持同时监控多个账号：

```bash
# 从配置文件读取单个账号信息（API密钥、Lark配置等）
cextools account watch-positions -x xt -e perp --config config/accounts.json --account-id account_001

# 从配置文件读取并启用 Lark 告警
cextools account watch-positions -x xt -e perp --config config/accounts.json --account-id account_001 --enable-lark

# 同时监控多个账号（指定账号列表，只监控 enabled: true 的账号）
cextools account watch-positions -x xt -e perp --config config/accounts.json --accounts account_001,account_002

# 监控配置文件中所有启用的账号（enabled: true）
cextools account watch-positions -x xt -e perp --config config/accounts.json --all-accounts

# 自定义间隔
cextools account watch-positions -x xt -e perp --config config/accounts.json --account-id account_001 --interval 5
```

**多账号模式说明**:
- `--accounts account_001,account_002`: 同时监控指定的多个账号（逗号分隔），只监控 `enabled: true` 的账号
- `--all-accounts`: 监控配置文件中所有 `enabled: true` 的账号
- 多账号模式下，每个账号使用独立的数据库表和连接
- 所有账号的查询间隔相同，但查询时间可能略有差异（避免同时连接过多）
- 输出会显示账号标识，便于区分不同账号的数据
- **重要**: 只有 `enabled: true` 的账号才会被监控，`enabled: false` 的账号会被自动跳过

**配置文件示例** (`config/accounts.json`):
```json
{
  "accounts": {
    "account_001": {
      "name": "主账号",
      "exchange": "xt",
      "api_key": "your_api_key",
      "api_secret": "your_api_secret",
      "enabled": true,
      "lark_webhook": "https://open.larksuite.com/open-apis/bot/v2/hook/...",
      "lark_secret": "optional_secret"
    },
    "account_002": {
      "name": "测试账号",
      "exchange": "xt",
      "api_key": "another_api_key",
      "api_secret": "another_api_secret",
      "enabled": false
    }
  }
}
```

**配置字段说明**:

1. **`enabled` 字段的作用**:
   - `enabled: true`: 账号启用，可以被使用
   - `enabled: false`: 账号禁用，主要用于 `multi-account` 命令中过滤账号
   - 对于单个 `watch-*` 命令，即使 `enabled: false`，只要指定了 `--account-id`，仍然可以使用该账号（但建议保持 `enabled: true`）

2. **为什么需要 `--account-id` 参数**:
   - 配置文件中可能包含多个账号（如上面的 `account_001` 和 `account_002`）
   - `--account-id` 用于指定从配置文件中读取哪个账号的信息
   - 如果不提供 `--account-id`，系统不知道应该使用哪个账号的配置
   - 示例：`--account-id account_001` 会读取 `accounts.account_001` 下的配置

**使用说明**:
- 如果提供了 `--config` 和 `--account-id`，将从配置文件读取该账号的 API 密钥和 Lark 配置
- 命令行参数会覆盖配置文件中的值
- 如果配置文件中没有找到账号，会使用命令行参数或环境变量
- 配置文件可以同时管理多个账号，通过 `--account-id` 切换使用不同的账号

**验证表**:
- `xt_rest_position_updates_account_001`

**验证 SQL**:
```sql
-- 查看仓位更新记录
SELECT * FROM xt_rest_position_updates_account_001 
ORDER BY query_time DESC LIMIT 10;

-- 查看特定交易对的仓位
SELECT * FROM xt_rest_position_updates_account_001 
WHERE symbol = 'BTC_USDT' 
ORDER BY query_time DESC LIMIT 10;
```

---

### 5. 多账号订阅（配置文件方式）

**命令**: `cextools subscribe multi-account`

**功能**: 从配置文件加载多个账号，同时订阅它们的 WebSocket 数据流

**测试命令**:

```bash
# 使用默认配置文件
cextools subscribe multi-account

# 指定配置文件
cextools subscribe multi-account --config config/accounts.json

# 只启动指定的账号
cextools subscribe multi-account --accounts account_001,account_002

# 首次运行，创建数据库表
cextools subscribe multi-account --create-tables

# JSON 输出格式
cextools subscribe multi-account --output json

# 禁用数据同步
cextools subscribe multi-account --disable-data-sync
```

**配置文件示例** (`config/accounts.json`):
```json
{
  "accounts": {
    "account_001": {
      "name": "主账号",
      "exchange": "xt",
      "api_key": "your_api_key_1",
      "api_secret": "your_api_secret_1",
      "enabled": true,
      "channels": ["account", "position", "order"]
    },
    "account_002": {
      "name": "测试账号",
      "exchange": "xt",
      "api_key": "your_api_key_2",
      "api_secret": "your_api_secret_2",
      "enabled": true,
      "channels": ["account", "position"]
    }
  },
  "global_settings": {
    "default_interval_minutes": 10,
    "database_url": "${DATABASE_URL}"
  }
}
```

**验证表**: 每个账号会创建独立的表，例如：
- `xt_account_updates_account_001`
- `xt_account_updates_account_002`
- `xt_position_updates_account_001`
- `xt_position_updates_account_002`
- ... 等等

---

## 🔍 验证步骤

### 步骤 1: 检查表是否创建

```sql
-- 查看所有账号特定的表
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name LIKE 'xt_%_account_001'
ORDER BY table_name;
```

**预期结果**: 应该看到约 10 个表（WebSocket + REST API）

### 步骤 2: 检查数据是否插入

```sql
-- 检查账户余额更新
SELECT COUNT(*) as count, MAX(update_time) as latest 
FROM xt_account_updates_account_001;

-- 检查合约余额
SELECT COUNT(*) as count, MAX(query_time) as latest 
FROM xt_perp_balances_account_001;

-- 检查持仓更新
SELECT COUNT(*) as count, MAX(query_time) as latest 
FROM xt_rest_position_updates_account_001;
```

### 步骤 3: 验证数据隔离

```sql
-- 如果有多个账号，验证数据是否正确隔离
SELECT 
  'account_001' as account,
  COUNT(*) as records,
  MAX(update_time) as latest
FROM xt_account_updates_account_001
UNION ALL
SELECT 
  'account_002' as account,
  COUNT(*) as records,
  MAX(update_time) as latest
FROM xt_account_updates_account_002;
```

---

## 🧪 完整测试流程

### 测试场景 1: 单账号完整监控

```bash
# 终端 1: WebSocket 订阅
cextools subscribe user-stream -x xt --account-id account_001 -c account,position,order,trade

# 终端 2: 定时账户监控
cextools account watch-account -x xt --account-id account_001 --interval 10

# 终端 3: 定时持仓监控
cextools account watch-positions -x xt -e perp --account-id account_001 --interval 1
```

**验证**: 所有数据应该保存到 `account_001` 的独立表中

### 测试场景 2: 多账号同时监控

```bash
# 终端 1: 账号 1 的 WebSocket 订阅
cextools subscribe user-stream -x xt --account-id account_001

# 终端 2: 账号 2 的 WebSocket 订阅
cextools subscribe user-stream -x xt --account-id account_002

# 终端 3: 账号 1 的定时监控
cextools account watch-account -x xt --account-id account_001 --interval 10

# 终端 4: 账号 2 的定时监控
cextools account watch-account -x xt --account-id account_002 --interval 10
```

**验证**: 每个账号的数据应该保存到各自的独立表中

### 测试场景 3: 表自动创建

```bash
# 第一次运行（会自动创建表）
cextools subscribe user-stream -x xt --account-id account_001

# 停止后再次运行（不会重复创建，不会报错）
cextools subscribe user-stream -x xt --account-id account_001
```

**验证**: 第一次运行会创建表，第二次运行不会报错

---

## 📊 快速验证 SQL

### 查看所有账号的表

```sql
SELECT 
  table_name,
  (SELECT COUNT(*) FROM information_schema.columns 
   WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public' 
  AND table_name LIKE 'xt_%_account_%'
ORDER BY table_name;
```

### 查看最新数据

```sql
-- 账号 1 的最新账户余额
SELECT currency, total, update_time 
FROM xt_account_updates_account_001 
ORDER BY update_time DESC LIMIT 5;

-- 账号 1 的最新合约余额
SELECT asset, total, unrealized_pnl, query_time 
FROM xt_perp_balances_account_001 
ORDER BY query_time DESC LIMIT 5;

-- 账号 1 的最新持仓
SELECT symbol, position_side, position_amount, unrealized_pnl, query_time 
FROM xt_perp_positions_account_001 
ORDER BY query_time DESC LIMIT 5;
```

### 统计各账号的数据量

```sql
-- 统计各账号的账户更新记录数
SELECT 
  'account_001' as account_id,
  COUNT(*) as account_updates,
  MAX(update_time) as latest_update
FROM xt_account_updates_account_001
UNION ALL
SELECT 
  'account_002' as account_id,
  COUNT(*) as account_updates,
  MAX(update_time) as latest_update
FROM xt_account_updates_account_002;
```

---

## ⚠️ 常见问题

### 问题 1: 表未创建

**现象**: 运行命令后没有数据

**检查**:
```sql
-- 检查表是否存在
SELECT table_name 
FROM information_schema.tables 
WHERE table_name LIKE 'xt_%_account_001';
```

**解决**: 确保提供了 `--account-id` 参数，或使用 `--create-tables` 显式创建

### 问题 2: 数据保存到默认表

**现象**: 数据出现在 `xt_account_updates` 而不是 `xt_account_updates_account_001`

**检查**: 确认命令中包含了 `--account-id account_001` 参数

**解决**: 重新运行命令，确保包含 `--account-id` 参数

### 问题 3: 账号ID包含特殊字符

**现象**: 表创建失败或表名异常

**解决**: 使用字母、数字和下划线，例如 `account_001` 而不是 `account-001`

---

## 📝 测试检查清单

- [ ] 单账号 WebSocket 订阅（所有频道）
- [ ] 单账号 WebSocket 订阅（指定频道）
- [ ] 单账号定时账户监控
- [ ] 单账号定时余额监控
- [ ] 单账号定时持仓监控
- [ ] 多账号同时订阅
- [ ] 表自动创建（首次运行）
- [ ] 表不重复创建（再次运行）
- [ ] 数据正确保存到账号特定的表
- [ ] 不同账号的数据隔离
- [ ] 查询数据验证

---

## 🚀 快速开始

### 1. 测试单账号订阅

```bash
# 启动订阅（会自动创建表）
cextools subscribe user-stream -x xt --account-id account_001

# 等待几分钟后，在另一个终端验证数据
psql -d trading -c "SELECT COUNT(*) FROM xt_account_updates_account_001;"
```

### 2. 测试定时监控

```bash
# 启动定时账户监控
cextools account watch-account -x xt --account-id account_001 --interval 1

# 等待几分钟后验证数据
psql -d trading -c "SELECT * FROM xt_perp_balances_account_001 ORDER BY query_time DESC LIMIT 5;"
```

### 3. 测试多账号

```bash
# 创建配置文件 config/accounts.json（参考上面的示例）

# 启动多账号订阅
cextools subscribe multi-account --create-tables

# 验证各账号的表
psql -d trading -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'xt_%_account_%' ORDER BY table_name;"
```

---

## 📚 相关文档

- [账号特定表支持清单](ACCOUNT_TABLE_SUPPORT.md) - 详细的功能说明
- [单账号独立表使用指南](SINGLE_ACCOUNT_TABLES.md) - 使用说明
- [多账号订阅使用指南](MULTI_ACCOUNT_USAGE.md) - 多账号配置说明
- [XT 数据库表结构](XT_DATABASE_SCHEMA.md) - 表结构详情

---

**提示**: 在服务器上测试时，建议先用一个测试账号验证功能正常，然后再扩展到多个账号。

