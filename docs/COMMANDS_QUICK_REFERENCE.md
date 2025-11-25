# 命令快速参考

所有支持账号特定表的命令快速参考。

---

## 🔧 单账号命令

### 1. WebSocket 订阅

```bash
# 基本用法（所有频道）
cextools subscribe user-stream -x xt --account-id account_001

# 指定频道
cextools subscribe user-stream -x xt --account-id account_001 -c account,position,order,trade

# 指定输出格式
cextools subscribe user-stream -x xt --account-id account_001 --output json

# 禁用数据同步
cextools subscribe user-stream -x xt --account-id account_001 --disable-data-sync
```

**保存的表**: `xt_account_updates_{account_id}`, `xt_position_updates_{account_id}`, `xt_order_updates_{account_id}`, `xt_trade_updates_{account_id}`, `xt_transfers_{account_id}`, `xt_spot_updates_{account_id}`

---

### 2. 定时账户监控

```bash
# XT 单账号（10分钟间隔）
cextools account watch-account -x xt --account-id account_001

# Binance 单账号（命令行提供密钥）
cextools account watch-account -x binance --api-key YOUR_KEY --api-secret YOUR_SECRET

# 从配置文件读取账号信息（自动识别交易所）
cextools account watch-account --config config/accounts.json --account-id account_001

# 同时监控多个账号（可混合 XT / Binance）
cextools account watch-account --config config/accounts.json --accounts account_001,binance_main

# 监控配置文件中所有启用的账号
cextools account watch-account --config config/accounts.json --all-accounts

# 自定义间隔
cextools account watch-account -x xt --account-id account_001 --interval 5

# 启用 Lark 告警（从配置文件读取，仅 XT）
cextools account watch-account --config config/accounts.json --account-id account_001 --enable-lark

# 启用 Lark 告警（手动指定，仅 XT）
cextools account watch-account -x xt --account-id account_001 --enable-lark --lark-webhook "https://..."

# 指定指标配置（仅 XT）
cextools account watch-account -x xt --account-id account_001 --metrics-config config/metrics.yaml
```

**保存的表**: `xt_spot_balances_{account_id}`, `xt_perp_balances_{account_id}`, `xt_perp_positions_{account_id}`

---

### 3. 定时余额监控

```bash
# 合约账户（默认5分钟）
cextools account watch-balance -x xt -e perp --account-id account_001

# Binance 合约账户（命令行提供密钥）
cextools account watch-balance -x binance -e perp --api-key YOUR_KEY --api-secret YOUR_SECRET

# 从配置文件读取账号信息（自动识别交易所）
cextools account watch-balance --config config/accounts.json --account-id account_001 -e perp

# 同时监控多个账号（可混合交易所）
cextools account watch-balance --config config/accounts.json --accounts account_001,binance_main -e perp

# 监控配置文件中所有启用的账号
cextools account watch-balance --config config/accounts.json --all-accounts -e perp

# 现货账户
cextools account watch-balance -x xt -e spot --account-id account_001

# 自定义间隔
cextools account watch-balance -x xt -e perp --account-id account_001 --interval 1
```

**保存的表**: `xt_account_updates_{account_id}`

---

### 4. 定时持仓监控

```bash
# XT 基本用法（1分钟间隔）
cextools account watch-positions -x xt -e perp --account-id account_001

# 从配置文件读取 XT 账号信息
cextools account watch-positions --config config/accounts.json --account-id account_001

# 同时监控多个账号（可混合 XT / Binance）
cextools account watch-positions --config config/accounts.json --accounts account_001,binance_main_001

# 监控配置文件中所有启用的账号（自动按 exchange 路由）
cextools account watch-positions --config config/accounts.json --all-accounts

# 自定义间隔
cextools account watch-positions -x xt -e perp --account-id account_001 --interval 5

# 指定交易对
cextools account watch-positions -x xt -e perp --account-id account_001 -s BTC/USDT

# 启用 Lark 告警（从配置文件读取，仅 XT）
cextools account watch-positions --config config/accounts.json --account-id account_001 --enable-lark

# 启用 Lark 告警（手动指定，仅 XT）
cextools account watch-positions -x xt -e perp --account-id account_001 --enable-lark --lark-webhook "https://..."

# Binance 单账号（命令行提供密钥）
cextools account watch-positions -x binance --api-key YOUR_BINANCE_KEY --api-secret YOUR_BINANCE_SECRET
```

**保存的表**: 
- XT: `xt_rest_position_updates_{account_id}`
- Binance: `rest_positions`（按 `account_id` 区分）

---

## 🔧 多账号命令

### 多账号订阅（配置文件 + 多交易所）

```bash
# 使用默认配置文件（自动识别 XT / Binance / OKX / Gate）
cextools subscribe multi-account

# 指定配置文件
cextools subscribe multi-account --config config/accounts.json

# 只启动指定账号（逗号分隔）
cextools subscribe multi-account --accounts account_001,binance_main

# 首次运行创建表（XT 账号会自动生成账号特定表）
cextools subscribe multi-account --create-tables
```

---

## 📊 验证命令

### 检查表是否存在

```sql
-- 查看所有账号特定的表
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name LIKE 'xt_%_account_001'
ORDER BY table_name;
```

### 查看最新数据

```sql
-- 账户余额
SELECT * FROM xt_account_updates_account_001 ORDER BY update_time DESC LIMIT 5;

-- 合约余额
SELECT * FROM xt_perp_balances_account_001 ORDER BY query_time DESC LIMIT 5;

-- 持仓
SELECT * FROM xt_perp_positions_account_001 ORDER BY query_time DESC LIMIT 5;
```

### 统计数据量

```sql
-- 统计各表记录数
SELECT 
  'account_updates' as table_name,
  COUNT(*) as records,
  MAX(update_time) as latest
FROM xt_account_updates_account_001
UNION ALL
SELECT 
  'perp_balances',
  COUNT(*),
  MAX(query_time)
FROM xt_perp_balances_account_001
UNION ALL
SELECT 
  'perp_positions',
  COUNT(*),
  MAX(query_time)
FROM xt_perp_positions_account_001;
```

---

## 🎯 常用测试组合

### 单账号完整监控

```bash
# 终端 1: WebSocket 订阅
cextools subscribe user-stream -x xt --account-id account_001

# 终端 2: 定时账户监控
cextools account watch-account -x xt --account-id account_001 --interval 10

# 终端 3: 定时持仓监控
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

## 📝 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--account-id` / `-a` | 账号ID（可选；XT 使用账号特表，其他交易所用于区分 rest_* 记录） | `account_001` |
| `--interval` / `-i` | 查询间隔（分钟） | `10` |
| `--channels` / `-c` | 订阅频道（逗号分隔） | `account,position` |
| `--output` / `-o` | 输出格式 | `table`, `json`, `none` |
| `--create-tables` | 显式创建表 | - |
| `--enable-lark` | 启用 Lark 告警 | - |
| `--lark-webhook` | Lark Webhook URL | `https://...` |

---

## ⚠️ 注意事项

1. **账号ID命名**: 使用字母、数字和下划线（`account_001`）
2. **表支持范围**: 账号特定表功能目前仅适用于 XT，其他交易所写入 `rest_*` 通用表
3. **表自动创建**: 首次运行自动创建，不会重复创建
4. **数据隔离**: 每个账号的数据保存在独立的表中

---

**快速开始**: 选择一个账号ID（如 `account_001`），运行任意命令测试即可。

