# 统一数据库初始化指南

## 🎯 概述

一个SQL脚本初始化Binance和OKX的所有表结构，包含：

- ✅ **Binance表**（4个）- 账户、订单、成交、ListenKey
- ✅ **OKX表**（4个）- 账户余额、持仓、订单、成交
- ✅ **视图**（5个）- 统计和查询视图
- ✅ **索引** - 完整的性能优化

## 📊 表结构总览

### Binance表（通用设计）

| 表名 | 用途 | 记录数据 |
|------|------|----------|
| `account_updates` | 账户和持仓更新 | 余额变化、持仓变化 |
| `order_updates` | 订单更新 | 订单状态、成交进度 |
| `trade_updates` | 成交记录 | 每笔成交详情 |
| `listen_keys` | ListenKey管理 | WebSocket连接密钥 |

### OKX表（专用设计）

| 表名 | 用途 | 特有字段 |
|------|------|----------|
| `okx_account_balances` | 账户余额 | 账户权益、现金余额、冻结余额 |
| `okx_positions` | 持仓 | 标记价格、强平价、保证金、杠杆 |
| `okx_orders` | 订单 | 返佣信息、交易模式 |
| `okx_trades` | 成交 | 成交详情 |

### 视图

| 视图名 | 用途 |
|--------|------|
| `latest_orders` | Binance最新订单状态 |
| `daily_trade_stats` | Binance每日成交统计 |
| `okx_latest_positions` | OKX最新持仓 |
| `okx_latest_orders` | OKX最新订单状态 |
| `okx_daily_trade_stats` | OKX每日成交统计 |

## 🚀 一键初始化

### 方法1：使用SQL脚本（推荐）

```bash
# 运行统一初始化脚本
psql -U postgres -d trading -f scripts/init_database.sql

# 应该看到所有表创建成功
```

### 方法2：使用CLI命令

```bash
# Binance和OKX都会自动创建表
cextools subscribe user-stream -x binance --create-tables

# 或
cextools subscribe user-stream -x okx --create-tables
```

### 方法3：使用Python

```python
import asyncio
from tri_arb.storage.database import DatabaseManager

async def init():
    db = DatabaseManager()
    await db.create_tables()  # 同时创建Binance和OKX表
    print("✅ 所有表创建成功")
    await db.close()

asyncio.run(init())
```

## ✅ 验证安装

### 查看所有表

```bash
psql -U postgres -d trading
```

```sql
-- 列出所有表
\dt

-- 应该看到：
-- account_updates          (Binance)
-- order_updates            (Binance)
-- trade_updates            (Binance)
-- listen_keys              (Binance)
-- okx_account_balances     (OKX)
-- okx_positions            (OKX)
-- okx_orders               (OKX)
-- okx_trades               (OKX)

-- 查看所有视图
\dv

-- 应该看到：
-- latest_orders            (Binance)
-- daily_trade_stats        (Binance)
-- okx_latest_positions     (OKX)
-- okx_latest_orders        (OKX)
-- okx_daily_trade_stats    (OKX)
```

### 查看表大小

```sql
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(tablename::regclass)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

## 📋 表字段说明

### Binance字段特点

- `exchange` - 标识交易所（binance_perp）
- `event_type` - 事件类型（ACCOUNT_UPDATE/ORDER_TRADE_UPDATE）
- `symbol` - 交易对格式：`BTCUSDT`
- `position_side` - 持仓方向：`LONG/SHORT/BOTH`
- `side` - 订单方向：`BUY/SELL`（大写）

### OKX字段特点

- 无exchange字段（专用表）
- `inst_id` - 产品ID格式：`BTC-USDT-SWAP`
- `pos_side` - 持仓方向：`long/short/net`
- `side` - 订单方向：`buy/sell`（小写）
- 额外保证金字段：`imr`, `mmr`, `margin`
- 额外价格字段：`mark_px`, `liq_px`
- 返佣字段：`rebate`, `rebate_ccy`

## 🔍 查询示例

### 查询Binance数据

```sql
-- 最新订单
SELECT * FROM order_updates 
WHERE exchange = 'binance_perp' 
ORDER BY event_time DESC LIMIT 10;

-- 今日成交统计
SELECT * FROM daily_trade_stats 
WHERE exchange = 'binance_perp' 
  AND trade_date = CURRENT_DATE;

-- 使用视图
SELECT * FROM latest_orders 
WHERE exchange = 'binance_perp' 
  AND symbol = 'BTCUSDT';
```

### 查询OKX数据

```sql
-- 最新持仓
SELECT * FROM okx_latest_positions;

-- 最新订单
SELECT * FROM okx_latest_orders 
WHERE inst_id = 'BTC-USDT-SWAP';

-- 今日成交统计
SELECT * FROM okx_daily_trade_stats 
WHERE trade_date = CURRENT_DATE;

-- 账户余额历史
SELECT * FROM okx_account_balances 
WHERE currency = 'USDT' 
ORDER BY update_time DESC LIMIT 10;
```

### 跨交易所对比

```sql
-- 对比两个交易所的订单数量
SELECT 
    'Binance' as exchange,
    COUNT(*) as order_count
FROM order_updates
WHERE exchange = 'binance_perp'
  AND DATE(event_time) = CURRENT_DATE

UNION ALL

SELECT 
    'OKX' as exchange,
    COUNT(*) as order_count
FROM okx_orders
WHERE DATE(u_time) = CURRENT_DATE;
```

## 🔧 数据库管理

### 清理旧数据

```sql
-- 清理30天前的Binance数据
DELETE FROM account_updates WHERE event_time < CURRENT_DATE - INTERVAL '30 days';
DELETE FROM order_updates WHERE event_time < CURRENT_DATE - INTERVAL '30 days';
DELETE FROM trade_updates WHERE transaction_time < CURRENT_DATE - INTERVAL '30 days';

-- 清理30天前的OKX数据
DELETE FROM okx_account_balances WHERE update_time < CURRENT_DATE - INTERVAL '30 days';
DELETE FROM okx_positions WHERE update_time < CURRENT_DATE - INTERVAL '30 days';
DELETE FROM okx_orders WHERE u_time < CURRENT_DATE - INTERVAL '30 days';
DELETE FROM okx_trades WHERE fill_time < CURRENT_DATE - INTERVAL '30 days';
```

### 数据备份

```bash
# 备份整个数据库
pg_dump -U postgres trading > backup_$(date +%Y%m%d).sql

# 仅备份Binance表
pg_dump -U postgres -t account_updates -t order_updates -t trade_updates trading > binance_backup.sql

# 仅备份OKX表
pg_dump -U postgres -t okx_* trading > okx_backup.sql
```

### 重建索引

```sql
-- 重建所有索引
REINDEX DATABASE trading;

-- 或单独重建
REINDEX TABLE account_updates;
REINDEX TABLE okx_orders;
```

## 📊 数据统计

### 查看所有表的记录数

```sql
SELECT 
    'Binance - account_updates' as table_name,
    COUNT(*) as records
FROM account_updates

UNION ALL

SELECT 
    'Binance - order_updates' as table_name,
    COUNT(*) as records
FROM order_updates

UNION ALL

SELECT 
    'OKX - okx_account_balances' as table_name,
    COUNT(*) as records
FROM okx_account_balances

UNION ALL

SELECT 
    'OKX - okx_positions' as table_name,
    COUNT(*) as records
FROM okx_positions

UNION ALL

SELECT 
    'OKX - okx_orders' as table_name,
    COUNT(*) as records
FROM okx_orders

ORDER BY table_name;
```

### 查看存储空间

```sql
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS index_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## 🎯 使用流程

### 完整启动流程

```bash
# 1. 配置PostgreSQL
bash scripts/configure_postgres_trust.sh

# 2. 初始化所有表
psql -U postgres -d trading -f scripts/init_database.sql

# 3. 配置环境变量
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
export OKX_API_KEY="..."
export OKX_API_SECRET="..."
export OKX_PASSPHRASE="..."
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"

# 4. 激活虚拟环境
source .venv/bin/activate

# 5. 启动Binance订阅
cextools subscribe user-stream -x binance --output table

# 6. 启动OKX订阅（另一个终端）
cextools subscribe user-stream -x okx --output table
```

## 🔄 OKX 5秒推送过滤

### 自动过滤（默认启用）

OKX每5秒会推送一次完整的账户快照，即使数据没有变化。代码已自动过滤：

```python
# 在okx_user_stream.py中
skip_duplicate_updates = True  # 默认启用

# 只在数据真正变化时才：
# 1. 显示在终端
# 2. 保存到数据库
# 3. 记录日志
```

### 查看过滤效果

```bash
# 启动订阅（会看到只在有变化时才显示）
cextools subscribe user-stream -x okx --output table

# 查看调试日志
tail -f logs/tri-arb.log | grep "Account data unchanged"
# 应该能看到多次"skipping display"
```

## 📚 相关文档

- [数据库结构对比](DATABASE_STRUCTURE_COMPARISON.md) - 详细对比
- [OKX WebSocket指南](OKX_WEBSOCKET_GUIDE.md) - OKX使用
- [Binance WebSocket指南](binance-websocket-subscription.md) - Binance使用

## 🎉 总结

### 统一初始化的优势

✅ **一个脚本** - 创建所有表
✅ **两个交易所** - Binance + OKX
✅ **独立结构** - 各自优化的表设计
✅ **完整索引** - 查询性能优化
✅ **便捷视图** - 快速查询最新数据

### 表数量统计

| 交易所 | 表数量 | 视图数量 |
|--------|--------|----------|
| Binance | 4 | 2 |
| OKX | 4 | 3 |
| **总计** | **8** | **5** |

### 快速开始

```bash
# 1. 初始化数据库
psql -U postgres -d trading -f scripts/init_database.sql

# 2. 验证
psql -U postgres -d trading -c "\dt"

# 3. 启动订阅
cextools subscribe user-stream -x binance
cextools subscribe user-stream -x okx
```

---

**所有表结构已统一！** 🎊

