# CEXTools 快速参考手册

## 📋 所有命令一览

### 账户管理

```bash
# 查询余额
cextools account balance -x <exchange> -e perp

# 定时查询余额（每N分钟）
cextools account watch-balance -x <exchange> -e perp -i <minutes>

# 查询持仓
cextools account positions -x <exchange> -e perp [--symbol SYMBOL]

# 查询挂单
cextools account orders -x <exchange> -e perp [--symbol SYMBOL]

# 定时查询挂单
cextools account watch-orders -x <exchange> -e perp [--symbol SYMBOL] -i <minutes>

# 定时查询持仓
cextools account watch-positions -x <exchange> -e perp [--symbol SYMBOL] -i <minutes>
```

### 订单交易

```bash
# 下单
cextools order place \
  -x <exchange> \
  -e perp \
  -s <symbol> \
  --side <buy|sell> \
  -q <quantity> \
  -p <price> \
  --position-side <LONG|SHORT> \
  [--type <limit|market|post_only>] \
  [--time-in-force <GTC|IOC|FOK>] \
  [--reduce-only]
```

### WebSocket订阅

```bash
# 统一命令（推荐）
cextools subscribe user-stream -x <exchange> [--channels <channels>] [--output <format>]

# Binance
cextools subscribe user-stream -x binance                    # 全部频道
cextools subscribe user-stream -x binance -c account         # 只订阅账户
cextools subscribe user-stream -x binance -c order           # 只订阅订单
cextools subscribe user-stream -x binance -c account,order   # 账户+订单

# OKX
cextools subscribe user-stream -x okx                        # 全部频道
cextools subscribe user-stream -x okx -c account             # 只订阅账户
cextools subscribe user-stream -x okx -c position            # 只订阅持仓
cextools subscribe user-stream -x okx -c order               # 只订阅订单
cextools subscribe user-stream -x okx -c position,order      # 持仓+订单

# Gate.io
cextools subscribe user-stream -x gate                       # 全部频道
cextools subscribe user-stream -x gate -c account            # 只订阅账户
cextools subscribe user-stream -x gate -c position           # 只订阅持仓
cextools subscribe user-stream -x gate -c order              # 只订阅订单
cextools subscribe user-stream -x gate -c position,order     # 持仓+订单
```

### 行情数据

```bash
# 实时价格
cextools market ticker -x <exchange> -s <symbol>

# 订单簿
cextools market depth -x <exchange> -s <symbol> [--limit 20]
```

## 🎯 常用示例

### Binance

```bash
# 环境变量
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."

# 查询余额
cextools account balance -x binance -e perp

# 查询BTC持仓
cextools account positions -x binance -e perp --symbol BTC/USDT

# 开多单
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

# 监控订单（每1分钟）
cextools account watch-orders -x binance -e perp -i 1

# 监控持仓（每2分钟）
cextools account watch-positions -x binance -e perp -i 2

# WebSocket订阅
cextools subscribe binance-user-stream
```

### OKX

```bash
# 环境变量
export OKX_API_KEY="..."
export OKX_API_SECRET="..."
export OKX_PASSPHRASE="..."

# 查询余额
cextools account balance -x okx -e perp

# 查询ETH持仓
cextools account positions -x okx -e perp --symbol ETH/USDT

# Post-only订单
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --type post_only --position-side LONG

# 监控余额（每5分钟）
cextools account watch-balance -x okx -e perp -i 5

# 监控持仓（每3分钟）
cextools account watch-positions -x okx -e perp -i 3
```

### XT

```bash
# 环境变量
export XT_API_KEY="..."
export XT_API_SECRET="..."

# 查询余额
cextools account balance -x xt -e perp

# 查询持仓
cextools account positions -x xt -e perp
```

### Gate.io

```bash
# 环境变量
export GATE_API_KEY="..."
export GATE_API_SECRET="..."

# 查询余额
cextools account balance -x gate -e perp

# 查询持仓
cextools account positions -x gate -e perp

# 下单
cextools order place -x gate -e perp -s BTC/USDT --side buy -q 1 -p 50000

# 监控持仓（每2分钟）
cextools account watch-positions -x gate -e perp -i 2

# 监控订单（每1分钟）
cextools account watch-orders -x gate -e perp -i 1

# WebSocket订阅
cextools subscribe user-stream -x gate -c position,order -o table
```

📚 **详细指南**：[docs/GATE.md](docs/GATE.md) - Gate.io 合并指南（快速开始/配置/REST/WS/定时/排错）

## 🗃️ PostgreSQL数据查询

### 连接数据库

```bash
psql -U postgres -d trading
```

### 常用SQL

```sql
-- 最新订单
SELECT * FROM order_updates ORDER BY event_time DESC LIMIT 10;

-- 查看订单执行过程
SELECT event_time, order_status, cumulative_filled_quantity
FROM order_updates 
WHERE order_id = 123456789 
ORDER BY event_time;

-- 今日成交
SELECT * FROM trade_updates 
WHERE DATE(transaction_time) = CURRENT_DATE 
ORDER BY transaction_time DESC;

-- 成交统计
SELECT * FROM daily_trade_stats WHERE trade_date = CURRENT_DATE;

-- 手续费总计
SELECT 
    commission_asset,
    SUM(commission) as total_fee,
    COUNT(*) as trade_count
FROM trade_updates
WHERE DATE(transaction_time) = CURRENT_DATE
GROUP BY commission_asset;

-- 最新订单状态（视图）
SELECT * FROM latest_orders WHERE symbol = 'BTCUSDT';
```

## 📊 输出格式

所有查询命令支持多种输出格式：

```bash
# 表格（默认）
cextools account balance -x binance -e perp

# JSON
cextools account balance -x binance -e perp --output json

# CSV
cextools account positions -x binance -e perp --output csv > positions.csv
```

## 🔧 调试模式

```bash
# 启用调试输出
cextools account balance -x okx -e perp --debug

# 查看日志
tail -f logs/tri-arb.log
```

## 🌐 Symbol格式

**统一输入格式**：`BTC/USDT`

自动转换为各交易所格式：
- Binance: `BTCUSDT`
- OKX: `BTC-USDT-SWAP`
- XT: `btc_usdt`

## 📁 文档索引

### 快速开始
- [CEXTools使用指南](docs/cextools-usage.md) ⭐ 主文档
- [Gate.io合并指南](docs/GATE.md) ⭐ Gate.io完整指南

### 功能指南
- [定时查询余额](docs/watch-balance-guide.md)
- [下单功能](docs/place-order-guide.md)
- [Binance WebSocket订阅](docs/binance-websocket-subscription.md)
- [Symbol格式指南](docs/SYMBOL_FORMAT_GUIDE.md)

### 配置指南
- [OKX配置](docs/okx-setup-guide.md)
- [OKX快速开始](docs/okx-quickstart.md)
- [Gate.io配置](docs/GATE.md)

### 技术文档
- [所有功能说明](ALL_FEATURES_COMPLETED.md)
- [WebSocket实现](docs/WEBSOCKET_IMPLEMENTATION_SUMMARY.md)
- [Binance API实现](docs/binance-api-implementation.md)
- [OKX实现](docs/okx-implementation.md)

### 问题排查
- [OKX问题排查](docs/okx-troubleshooting.md)
- [Gate.io问题排查](docs/GATE.md#常见问题排查)
- [调试日志](docs/debug-logging.md)

### 示例代码
- [OKX示例](examples/okx_example.py)
- [下单示例](examples/place_order_example.py)
- [Binance持仓](examples/binance_positions_example.py)
- [Binance挂单](examples/binance_orders_example.py)
- [WebSocket订阅](examples/binance_websocket_example.py)

## 🎯 使用场景

### 场景1：实时监控交易

```bash
# 终端1：WebSocket实时订阅
cextools subscribe binance-user-stream

# 终端2：监控OKX余额（每5分钟）
cextools account watch-balance -x okx -e perp -i 5

# 终端3：监控Binance订单（每1分钟）
cextools account watch-orders -x binance -e perp -i 1

# 终端4：监控Gate.io持仓（每2分钟）
cextools account watch-positions -x gate -e perp -i 2

# 终端5：实时查询数据库
watch -n 3 "psql -U postgres -d trading -c 'SELECT * FROM order_updates ORDER BY event_time DESC LIMIT 5;'"
```

### 场景2：下单并监控

```bash
# 1. 下单
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

# 2. 查看订单
cextools account orders -x binance -e perp --symbol BTC/USDT

# 3. 查询数据库
psql -U postgres -d trading -c "SELECT * FROM order_updates WHERE symbol = 'BTCUSDT' ORDER BY event_time DESC LIMIT 5;"
```

### 场景3：数据分析

```sql
-- 1. 连接数据库
psql -U postgres -d trading

-- 2. 今日交易统计
SELECT * FROM daily_trade_stats WHERE trade_date = CURRENT_DATE;

-- 3. 订单执行分析
SELECT 
    symbol,
    order_status,
    COUNT(*) as count,
    AVG(cumulative_filled_quantity / original_quantity) as avg_fill_rate
FROM order_updates
WHERE DATE(event_time) = CURRENT_DATE
GROUP BY symbol, order_status;

-- 4. 手续费分析
SELECT 
    DATE(transaction_time) as date,
    commission_asset,
    SUM(commission) as total_fee,
    COUNT(*) as trade_count
FROM trade_updates
WHERE transaction_time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(transaction_time), commission_asset
ORDER BY date DESC;
```

## 🚀 一键启动

### WebSocket订阅

```bash
# 自动安装和配置
bash scripts/setup_websocket.sh

# 按照提示完成配置，然后启动
cextools subscribe binance-user-stream
```

### 定时监控

```bash
# 后台运行多个监控任务
nohup cextools account watch-balance -x okx -e perp -i 5 > okx-balance.log 2>&1 &
nohup cextools account watch-orders -x binance -e perp -i 1 > binance-orders.log 2>&1 &
nohup cextools account watch-positions -x gate -e perp -i 2 > gate-positions.log 2>&1 &
nohup cextools subscribe binance-user-stream > websocket.log 2>&1 &
```

## ⚠️ 重要提示

### API权限

| 功能 | 需要的权限 |
|------|-----------|
| 查询余额/持仓/订单 | 读取 |
| 下单/撤单 | 读取 + 交易 |
| WebSocket订阅 | 读取 |

### 安全建议

- ✅ 启用IP白名单
- ✅ 不要开启"提币"权限
- ✅ 定期轮换API密钥
- ✅ 不要在公共环境暴露密钥

---

**项目状态**：✅ 功能完整，生产就绪  
**支持交易所**：XT, Binance, OKX, Gate.io  
**文档数量**：30+ 页面  
**代码量**：5000+ 行

