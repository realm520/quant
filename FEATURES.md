# CEXTools 功能总览

## 🎯 核心功能

### 支持的交易所

- **XT** - 现货+永续合约
- **Binance** - 永续合约 + WebSocket
- **OKX** - 永续合约 + WebSocket
- **Gate.io** - 永续合约 + WebSocket

### 功能矩阵

| 功能 | XT | Binance | OKX | Gate.io |
|------|-----|---------|-----|---------|
| **REST API** |
| 查询余额 | ✅ | ✅ | ✅ | ✅ |
| 查询持仓 | ✅ | ✅ | ✅ | ✅ |
| 查询订单 | ✅ | ✅ | ✅ | ✅ |
| 下单 | ✅ | ✅ | ✅ | ✅ |
| 定时查询 | ✅ | ✅ | ✅ | ✅ |
| **WebSocket** |
| 实时账户 | - | ✅ | ✅ | ✅ |
| 实时持仓 | - | ✅ | ✅ | ✅ |
| 实时订单 | - | ✅ | ✅ | ✅ |
| 选择性订阅 | - | ✅ | ✅ | ✅ |
| **数据存储** |
| PostgreSQL | - | ✅ | ✅ | ✅ |
| 独立表结构 | - | ✅ | ✅ | ✅ |

---

## 📋 核心命令

### REST API

```bash
# 账户
cextools account balance -x <exchange> -e perp
cextools account positions -x <exchange> -e perp [--symbol SYMBOL]
cextools account orders -x <exchange> -e perp [--symbol SYMBOL]
cextools account watch-balance -x <exchange> -e perp -i <minutes>

# 下单
cextools order place -x <exchange> -e perp -s <symbol> --side <side> -q <qty> -p <price>
```

### WebSocket

```bash
# 全部订阅
cextools subscribe user-stream -x <exchange>

# 选择性订阅
cextools subscribe user-stream -x binance -c account,order
cextools subscribe user-stream -x okx -c position,order

# 指定显示格式
cextools subscribe user-stream -x okx -o table  # 表格
cextools subscribe user-stream -x okx -o json   # JSON
cextools subscribe user-stream -x okx -o none   # 静默
```

---

## 🌟 亮点功能

### WebSocket订阅

- ⚡ **实时推送** - 毫秒级延迟
- 🎯 **选择性订阅** - 只订阅需要的频道
- 📊 **美观显示** - 表格/JSON/静默三种模式
- 💾 **数据存储** - PostgreSQL持久化
- 🔄 **自动重连** - 连接断开自动恢复
- 🎨 **丰富展示** - 10-20个字段，进度条，颜色高亮
- ⚠️ **风险警告** - 强平价警告，滑点提示

### 数据过滤

- ✅ OKX重复数据智能过滤（减少99%存储）
- ✅ 只在数据真正变化时保存

### 显示特性

- 📊 成交进度条
- 💰 完全成交摘要
- ⚠️ 强平价警告
- 📈 滑点自动计算
- 🎨 颜色高亮

---

## 📊 数据库表结构

### Binance (4张表)

- `account_updates` - 账户和持仓
- `order_updates` - 订单
- `trade_updates` - 成交
- `listen_keys` - ListenKey管理

### OKX (4张表)

- `okx_account_balances` - 账户余额
- `okx_positions` - 持仓
- `okx_orders` - 订单
- `okx_trades` - 成交

### Gate.io (4张表)

- `gate_account_balances` - 账户余额
- `gate_positions` - 持仓
- `gate_orders` - 订单
- `gate_trades` - 成交

### 查询视图 (11个)

**Binance (2个)**：
- `latest_orders` - 最新订单
- `daily_trade_stats` - 每日统计

**OKX (3个)**：
- `okx_latest_positions` - 最新持仓
- `okx_latest_orders` - 最新订单
- `okx_daily_trade_stats` - 每日统计

**Gate.io (3个)**：
- `gate_latest_positions` - 最新持仓
- `gate_latest_orders` - 最新订单
- `gate_daily_trade_stats` - 每日统计

**总计**：12张表，11个视图

---

## 📚 文档索引

### 核心文档

1. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** ⭐ - 所有命令参考
2. **[docs/WEBSOCKET_COMPLETE_GUIDE.md](docs/WEBSOCKET_COMPLETE_GUIDE.md)** ⭐ - WebSocket指南
3. **[docs/README.md](docs/README.md)** - 文档中心

### 专题文档

- [WebSocket选择性订阅](docs/SELECTIVE_SUBSCRIPTION_GUIDE.md)
- [PostgreSQL配置](docs/POSTGRES_NO_PASSWORD_SETUP.md)
- [数据库结构](docs/UNIFIED_DATABASE_INIT.md)
- [OKX故障排查](docs/OKX_WEBSOCKET_TROUBLESHOOTING.md)

---

## 🚀 典型使用场景

### 场景1：实时监控交易

```bash
# 终端1：Binance订单
cextools subscribe user-stream -x binance -c order -o table

# 终端2：OKX持仓+订单
cextools subscribe user-stream -x okx -c position,order -o table

# 终端3：数据库查询
watch -n 3 "psql -U postgres -d trading -c 'SELECT * FROM okx_orders ORDER BY u_time DESC LIMIT 5;'"
```

### 场景2：数据分析

```bash
# 后台收集数据
nohup cextools subscribe user-stream -x okx -o none > okx.log 2>&1 &
nohup cextools subscribe user-stream -x binance -o none > binance.log 2>&1 &

# 数据库分析
psql -U postgres -d trading
SELECT * FROM okx_daily_trade_stats WHERE trade_date = CURRENT_DATE;
```

### 场景3：风险监控

```bash
# 只监控持仓和账户
cextools subscribe user-stream -x okx -c account,position -o table
```

---

## 💡 项目统计

- **代码量**：~6000行
- **文件数**：50+
- **文档数**：15个（精简后）
- **支持交易所**：3个
- **数据库表**：8个
- **WebSocket频道**：6个

---

**开始使用**：[QUICK_REFERENCE.md](QUICK_REFERENCE.md) ⭐

