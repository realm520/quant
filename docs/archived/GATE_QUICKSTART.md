# Gate.io 快速开始指南

## 🚀 5分钟上手

### 1. REST API查询

```bash
# 配置API凭证
export GATE_API_KEY="your_key"
export GATE_API_SECRET="your_secret"

# 查询余额
cextools account balance -x gate -e perp

# 查询持仓
cextools account positions -x gate -e perp

# 查询订单
cextools account orders -x gate -e perp

# 下单
cextools order place -x gate -e perp -s BTC/USDT --side buy -q 1 -p 50000
```

### 2. WebSocket实时订阅

```bash
# 配置环境
export GATE_API_KEY="..."
export GATE_API_SECRET="..."
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"

# 初始化数据库（首次）
psql -U postgres -d trading -f scripts/init_database.sql

# 启动订阅
source .venv/bin/activate
cextools subscribe user-stream -x gate                    # 全部频道
cextools subscribe user-stream -x gate -c position,order  # 持仓+订单
```

---

## 📊 支持的功能

| 功能 | 状态 | 命令 |
|------|------|------|
| 查询余额 | ✅ | `account balance -x gate -e perp` |
| 查询持仓 | ✅ | `account positions -x gate -e perp` |
| 查询订单 | ✅ | `account orders -x gate -e perp` |
| 下单 | ✅ | `order place -x gate -e perp ...` |
| WebSocket账户 | ✅ | `subscribe user-stream -x gate -c account` |
| WebSocket持仓 | ✅ | `subscribe user-stream -x gate -c position` |
| WebSocket订单 | ✅ | `subscribe user-stream -x gate -c order` |

---

## 🗄️ 数据库表

### Gate.io表（4张）

- `gate_account_balances` - 账户余额
- `gate_positions` - 持仓
- `gate_orders` - 订单
- `gate_trades` - 成交

### 查询视图（3个）

- `gate_latest_positions` - 最新持仓
- `gate_latest_orders` - 最新订单
- `gate_daily_trade_stats` - 每日统计

---

## 📝 数据查询

```sql
-- 连接数据库
psql -U postgres -d trading

-- 查询最新持仓
SELECT * FROM gate_latest_positions;

-- 查询最新订单
SELECT * FROM gate_latest_orders;

-- 今日成交统计
SELECT * FROM gate_daily_trade_stats WHERE trade_date = CURRENT_DATE;
```

---

## 🎯 完整示例

```bash
# 1. 配置环境
export GATE_API_KEY="your_key"
export GATE_API_SECRET="your_secret"
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"

# 2. 查询账户（REST）
cextools account balance -x gate -e perp
cextools account positions -x gate -e perp

# 3. 启动WebSocket监控
cextools subscribe user-stream -x gate -c position,order -o table

# 4. 查询数据库
psql -U postgres -d trading -c "SELECT * FROM gate_orders ORDER BY update_time DESC LIMIT 10;"
```

---

**Gate.io支持已完成！** 🎊

