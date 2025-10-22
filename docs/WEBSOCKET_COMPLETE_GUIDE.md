# WebSocket订阅完整指南

## 📋 目录

1. [快速开始](#快速开始)
2. [支持的交易所和频道](#支持的交易所和频道)
3. [数据库配置](#数据库配置)
4. [使用方法](#使用方法)
5. [显示格式](#显示格式)
6. [数据查询](#数据查询)
7. [常见问题](#常见问题)

---

## 🚀 快速开始

### 5分钟上手

```bash
# 1. 安装依赖
pip install -r requirements-db.txt

# 2. 配置PostgreSQL（选择一种方式）
## 方式A：配置无密码连接
bash scripts/configure_postgres_trust.sh

## 方式B：使用Docker
sudo docker run --name postgres-trading -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16

# 3. 初始化数据库
psql -U postgres -d trading -f scripts/init_database.sql

# 4. 配置环境变量
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"

## Binance
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."

## OKX
export OKX_API_KEY="..."
export OKX_API_SECRET="..."
export OKX_PASSPHRASE="..."

# 5. 启动订阅
source .venv/bin/activate
cextools subscribe user-stream -x binance  # Binance
cextools subscribe user-stream -x okx      # OKX
```

---

## 📡 支持的交易所和频道

### Binance

| 频道 | 说明 | 数据表 |
|------|------|--------|
| `account` | 账户余额和持仓 | `account_updates` |
| `order` | 订单状态 | `order_updates` |
| `trade` | 成交记录 | `trade_updates` |

**特点**：
- 推送模式：增量式（仅在变化时）
- 认证：ListenKey机制
- 产品格式：`BTCUSDT`

### OKX

| 频道 | 说明 | 数据表 |
|------|------|--------|
| `account` | 账户余额 | `okx_account_balances` |
| `position` | 持仓 | `okx_positions` |
| `order` | 订单 | `okx_orders` |

**特点**：
- 推送模式：快照式（每5秒，自动过滤重复）
- 认证：WebSocket登录
- 产品格式：`BTC-USDT-SWAP`

---

## 💾 数据库配置

### 方案1：无密码连接（推荐开发环境）

```bash
# 一键配置
bash scripts/configure_postgres_trust.sh

# 手动配置
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
```

### 方案2：有密码连接

```bash
export DATABASE_URL="postgresql+asyncpg://postgres:your_password@localhost:5432/trading"
```

### 初始化表结构

```bash
# 创建所有表（Binance + OKX，共8个表）
psql -U postgres -d trading -f scripts/init_database.sql

# 或使用CLI自动创建
cextools subscribe user-stream -x binance --create-tables
```

**创建的表**：
- Binance: `account_updates`, `order_updates`, `trade_updates`, `listen_keys`
- OKX: `okx_account_balances`, `okx_positions`, `okx_orders`, `okx_trades`

---

## 🎯 使用方法

### 基本命令

```bash
cextools subscribe user-stream -x <exchange> [options]
```

### 完整参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--exchange` | `-x` | 交易所 (binance/okx) | 必需 |
| `--channels` | `-c` | 订阅频道 | 全部 |
| `--output` | `-o` | 显示格式 (table/json/none) | table |
| `--create-tables` | - | 创建数据库表 | false |
| `--database-url` | - | 数据库URL | 环境变量 |
| `--api-key` | - | API Key | 环境变量 |
| `--api-secret` | - | API Secret | 环境变量 |
| `--passphrase` | - | Passphrase (OKX) | 环境变量 |
| `--debug` | - | 调试模式 | false |

### 常用组合

```bash
# 全部订阅，表格显示
cextools subscribe user-stream -x binance -o table

# 只订阅订单，JSON显示
cextools subscribe user-stream -x okx -c order -o json

# 账户+持仓，静默保存
cextools subscribe user-stream -x okx -c account,position -o none

# 首次运行
cextools subscribe user-stream -x binance --create-tables
```

---

## 🎨 显示格式

### 1. 表格模式 (table) - 推荐

```bash
cextools subscribe user-stream -x okx -o table
```

**特点**：
- ✅ 美观的表格
- ✅ 颜色高亮（盈亏、方向、状态）
- ✅ 成交进度条
- ✅ 强平价警告
- ✅ 滑点计算

**OKX账户显示**：
```
╭──── 💰 OKX账户总览 ────╮
│ 总权益(USD) │ 10000.00 │
╰────────────────────────╯

╭───── 💵 币种余额详情 ─────╮
│币种│权益│可用│冻结│盈亏│现金│
│USDT│10k │9.5k│500│+50│9.9k│
╰──────────────────────────╯
```

**OKX持仓显示（10列）**：
```
╭───────────── 📊 OKX持仓更新 ─────────────╮
│产品│方向│持仓│均价│标记价│强平价│盈亏│收益率│保证金│杠杆│
│BTC-USDT-SWAP│LONG│1│50k│51k│45k│+1k│+2%│5k│10x│
╰──────────────────────────────────────────╯
```

**OKX订单显示（15+字段）**：
```
╭───── 📝 OKX订单更新 ─────╮
│字段      │值              │
│产品      │BTC-USDT-SWAP  │
│订单ID    │123456789      │
│状态      │FILLED         │
│方向      │BUY            │
│成交进度  │██████████100%│
│滑点      │-0.0020%       │
╰──────────────────────────╯
✅ 订单完全成交
   成交: 1.00 @ 49999.00
   金额: 49999.00 USDT
```

### 2. JSON模式 (json) - 调试用

```bash
cextools subscribe user-stream -x okx -o json
```

显示完整的原始JSON数据。

### 3. 静默模式 (none) - 后台运行

```bash
cextools subscribe user-stream -x okx -o none
```

不显示，仅保存到数据库。

---

## 🔍 数据查询

### 连接数据库

```bash
psql -U postgres -d trading
```

### 常用查询

#### Binance

```sql
-- 最新订单
SELECT * FROM order_updates 
WHERE exchange = 'binance_perp' 
ORDER BY event_time DESC LIMIT 10;

-- 使用视图
SELECT * FROM latest_orders 
WHERE exchange = 'binance_perp';

-- 今日统计
SELECT * FROM daily_trade_stats 
WHERE trade_date = CURRENT_DATE;
```

#### OKX

```sql
-- 最新持仓
SELECT * FROM okx_latest_positions;

-- 最新订单
SELECT * FROM okx_latest_orders;

-- 账户余额历史
SELECT * FROM okx_account_balances 
WHERE currency = 'USDT' 
ORDER BY update_time DESC LIMIT 10;

-- 今日统计
SELECT * FROM okx_daily_trade_stats 
WHERE trade_date = CURRENT_DATE;
```

#### 跨交易所

```sql
-- 对比订单量
SELECT 'Binance' as exchange, COUNT(*) 
FROM order_updates 
WHERE exchange = 'binance_perp'
UNION ALL
SELECT 'OKX', COUNT(*) 
FROM okx_orders;
```

---

## 🐛 常见问题

### 1. OKX时间戳错误 (60004)

**错误**：`Invalid timestamp`

**解决**：
```bash
# 检查时间同步
python scripts/check_okx_time.py

# 同步时间
sudo ntpdate pool.ntp.org
```

### 2. PostgreSQL连接失败

**解决**：
```bash
# 配置无密码连接
bash scripts/configure_postgres_trust.sh

# 或启动Docker
sudo docker run --name postgres-trading -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16
```

### 3. OKX数据每5秒重复

**说明**：这是正常的，OKX采用快照式推送。

**解决**：代码已自动过滤重复数据，只在变化时保存。

### 4. 空字符串转换错误

**说明**：已修复，使用安全转换函数处理所有数据。

---

## 📚 快速命令参考

### Binance

```bash
# 全部频道
cextools subscribe user-stream -x binance

# 只订阅账户
cextools subscribe user-stream -x binance -c account

# 只订阅订单
cextools subscribe user-stream -x binance -c order

# 账户+订单，JSON显示
cextools subscribe user-stream -x binance -c account,order -o json
```

### OKX

```bash
# 全部频道
cextools subscribe user-stream -x okx

# 只订阅账户
cextools subscribe user-stream -x okx -c account

# 只订阅持仓
cextools subscribe user-stream -x okx -c position

# 只订阅订单
cextools subscribe user-stream -x okx -c order

# 持仓+订单
cextools subscribe user-stream -x okx -c position,order

# 全部，JSON显示
cextools subscribe user-stream -x okx -o json
```

### 同时监控

```bash
# 终端1：Binance
cextools subscribe user-stream -x binance -o table

# 终端2：OKX
cextools subscribe user-stream -x okx -o table

# 终端3：数据库查询
watch -n 3 "psql -U postgres -d trading -c 'SELECT exchange, symbol, order_status, event_time FROM order_updates ORDER BY event_time DESC LIMIT 5;'"
```

---

## 🎉 功能特性

### 核心功能

- ✅ 实时账户/持仓/订单更新
- ✅ PostgreSQL持久化存储
- ✅ 选择性频道订阅
- ✅ 三种显示模式
- ✅ 自动重连机制
- ✅ 智能重复数据过滤（OKX）
- ✅ 完整的字段显示
- ✅ 风险警告（强平价、滑点）

### 显示特性

- 🎨 颜色高亮（盈亏、方向、状态）
- 📊 成交进度条
- ⚠️ 强平价警告
- 📈 滑点自动计算
- 💰 成交摘要
- ⏱️ 时间戳显示

### 数据特性

- 💾 独立的表结构（Binance和OKX）
- 📊 预定义查询视图
- 🔍 完整的索引优化
- 🗃️ 原始JSON数据保存

---

## 🛠️ 工具脚本

| 脚本 | 用途 |
|------|------|
| `configure_postgres_trust.sh` | 配置PostgreSQL无密码 |
| `init_database.sql` | 初始化所有表 |
| `check_okx_time.py` | 检查OKX时间同步 |
| `selective_subscription_example.sh` | 交互式订阅示例 |

---

**详细文档**：
- [选择性订阅指南](SELECTIVE_SUBSCRIPTION_GUIDE.md)
- [数据库结构对比](DATABASE_STRUCTURE_COMPARISON.md)
- [OKX故障排查](OKX_WEBSOCKET_TROUBLESHOOTING.md)

---

**最后更新**：2024-10-21

