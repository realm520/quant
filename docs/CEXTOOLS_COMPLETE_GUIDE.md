# CEXTools 完整使用指南

CEXTools是一个功能完整的多交易所量化交易系统，支持XT、Binance、OKX、Gate.io四个主流交易所的REST API和WebSocket订阅功能。

## 📋 目录

- [快速开始](#快速开始)
- [环境配置](#环境配置)
- [账户管理](#账户管理)
- [订单交易](#订单交易)
- [WebSocket订阅](#websocket订阅)
- [定时查询](#定时查询)
- [数据库管理](#数据库管理)
- [输出格式](#输出格式)
- [故障排查](#故障排查)
- [最佳实践](#最佳实践)

## 🚀 快速开始

### 1. 安装依赖

```bash
# 基础依赖
pip install -r requirements.txt

# 数据库功能（WebSocket订阅需要）
pip install -r requirements-db.txt
```

### 2. 配置API凭证

```bash
# Binance
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# OKX
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_api_secret"
export OKX_PASSPHRASE="your_passphrase"

# Gate.io
export GATE_API_KEY="your_api_key"
export GATE_API_SECRET="your_api_secret"

# XT
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
```

### 3. 基本命令

```bash
# 查看帮助
python -m tri_arb.cli.main --help

# 查看账户命令
python -m tri_arb.cli.main account --help

# 查看订阅命令
python -m tri_arb.cli.main subscribe --help
```

## ⚙️ 环境配置

### PostgreSQL配置（WebSocket订阅需要）

```bash
# 1. 安装PostgreSQL
sudo apt install postgresql postgresql-contrib

# 2. 配置无密码连接（开发环境）
sudo bash scripts/configure_postgres_trust.sh

# 3. 创建数据库
sudo -u postgres createdb trading

# 4. 初始化表结构
psql -U postgres -d trading -f scripts/init_database.sql

# 5. 设置环境变量
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
```

### Docker方式（推荐）

```bash
# 启动PostgreSQL容器
docker run --name postgres-trading \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=trading \
  -p 5432:5432 \
  -d postgres:15

# 初始化数据库
psql -h localhost -U postgres -d trading -f scripts/init_database.sql
```

## 💰 账户管理

### 查询余额

```bash
# 查询永续合约余额
python -m tri_arb.cli.main account balance -x binance -e perp
python -m tri_arb.cli.main account balance -x okx -e perp
python -m tri_arb.cli.main account balance -x gate -e perp

# 查询现货余额
python -m tri_arb.cli.main account balance -x binance -e spot
python -m tri_arb.cli.main account balance -x okx -e spot

# JSON格式输出
python -m tri_arb.cli.main account balance -x binance -e perp --output json

# CSV格式输出
python -m tri_arb.cli.main account balance -x binance -e perp --output csv
```

### 查询持仓

```bash
# 查询所有持仓
python -m tri_arb.cli.main account positions -x binance -e perp
python -m tri_arb.cli.main account positions -x okx -e perp
python -m tri_arb.cli.main account positions -x gate -e perp

# 查询特定交易对持仓
python -m tri_arb.cli.main account positions -x binance -e perp --symbol BTC/USDT
python -m tri_arb.cli.main account positions -x okx -e perp --symbol ETH/USDT

# JSON格式输出
python -m tri_arb.cli.main account positions -x binance -e perp --output json
```

### 查询挂单

```bash
# 查询所有挂单
python -m tri_arb.cli.main account orders -x binance -e perp
python -m tri_arb.cli.main account orders -x okx -e perp
python -m tri_arb.cli.main account orders -x gate -e perp

# 查询特定交易对挂单
python -m tri_arb.cli.main account orders -x binance -e perp --symbol BTC/USDT

# JSON格式输出
python -m tri_arb.cli.main account orders -x binance -e perp --output json
```

## 📝 订单交易

### 下单

```bash
# 限价买单
python -m tri_arb.cli.main order place \
  -x binance \
  -e perp \
  -s BTC/USDT \
  --side buy \
  -q 0.001 \
  -p 50000 \
  --position-side LONG

# 市价买单
python -m tri_arb.cli.main order place \
  -x binance \
  -e perp \
  -s BTC/USDT \
  --side buy \
  -q 0.001 \
  --type market \
  --position-side LONG

# Post-only订单（OKX）
python -m tri_arb.cli.main order place \
  -x okx \
  -e perp \
  -s BTC/USDT \
  --side buy \
  -q 0.001 \
  -p 50000 \
  --type post_only \
  --position-side LONG

# 减仓订单
python -m tri_arb.cli.main order place \
  -x binance \
  -e perp \
  -s BTC/USDT \
  --side sell \
  -q 0.001 \
  -p 51000 \
  --position-side SHORT \
  --reduce-only
```

### 撤单

```bash
# 撤销特定订单
python -m tri_arb.cli.main order cancel \
  -x binance \
  -e perp \
  -s BTC/USDT \
  --order-id 123456789

# 撤销所有订单
python -m tri_arb.cli.main order cancel-all \
  -x binance \
  -e perp \
  -s BTC/USDT
```

## 📡 WebSocket订阅

### 统一订阅命令

```bash
# 订阅所有频道
python -m tri_arb.cli.main subscribe user-stream -x binance
python -m tri_arb.cli.main subscribe user-stream -x okx
python -m tri_arb.cli.main subscribe user-stream -x gate

# 选择性订阅
python -m tri_arb.cli.main subscribe user-stream -x binance -c account
python -m tri_arb.cli.main subscribe user-stream -x okx -c position,order
python -m tri_arb.cli.main subscribe user-stream -x gate -c account,position

# 指定输出格式
python -m tri_arb.cli.main subscribe user-stream -x binance -o table
python -m tri_arb.cli.main subscribe user-stream -x okx -o json
```

### 支持的频道

| 交易所 | 账户 | 持仓 | 订单 | 成交 |
|--------|------|------|------|------|
| Binance | ✅ | - | ✅ | ✅ |
| OKX | ✅ | ✅ | ✅ | ✅ |
| Gate.io | ✅ | ✅ | ✅ | ✅ |

### 频道说明

- **account**: 账户余额更新
- **position**: 持仓变化（仅OKX、Gate.io）
- **order**: 订单状态变化
- **trade**: 成交记录（仅Binance）

## ⏰ 定时查询

### 定时查询余额

```bash
# 每1分钟查询一次
python -m tri_arb.cli.main account watch-balance -x binance -e perp -i 1

# 每5分钟查询一次
python -m tri_arb.cli.main account watch-balance -x okx -e perp -i 5

# JSON格式输出
python -m tri_arb.cli.main account watch-balance -x gate -e perp -i 2 --output json
```

### 定时查询持仓

```bash
# 每2分钟查询一次所有持仓
python -m tri_arb.cli.main account watch-positions -x binance -e perp -i 2

# 每1分钟查询特定交易对持仓
python -m tri_arb.cli.main account watch-positions -x okx -e perp -s BTC/USDT -i 1

# JSON格式输出
python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 3 --output json
```

### 定时查询挂单

```bash
# 每1分钟查询一次所有挂单
python -m tri_arb.cli.main account watch-orders -x binance -e perp -i 1

# 每2分钟查询特定交易对挂单
python -m tri_arb.cli.main account watch-orders -x okx -e perp -s ETH/USDT -i 2

# JSON格式输出
python -m tri_arb.cli.main account watch-orders -x gate -e perp -i 1 --output json
```

## 🗄️ 数据库管理

### 连接数据库

```bash
psql -U postgres -d trading
```

### 查看数据

```sql
-- 查看最新订单
SELECT * FROM order_updates ORDER BY event_time DESC LIMIT 10;

-- 查看今日成交
SELECT * FROM trade_updates 
WHERE DATE(transaction_time) = CURRENT_DATE 
ORDER BY transaction_time DESC;

-- 查看账户余额变化
SELECT * FROM account_updates 
WHERE update_time >= NOW() - INTERVAL '1 hour'
ORDER BY update_time DESC;

-- 查看持仓变化
SELECT * FROM okx_positions 
WHERE update_time >= NOW() - INTERVAL '1 hour'
ORDER BY update_time DESC;
```

### 统计分析

```sql
-- 今日成交统计
SELECT 
    symbol,
    COUNT(*) as trade_count,
    SUM(quantity) as total_quantity,
    SUM(commission) as total_fee
FROM trade_updates
WHERE DATE(transaction_time) = CURRENT_DATE
GROUP BY symbol
ORDER BY total_fee DESC;

-- 订单执行分析
SELECT 
    symbol,
    order_status,
    COUNT(*) as count,
    AVG(cumulative_filled_quantity / original_quantity) as avg_fill_rate
FROM order_updates
WHERE DATE(event_time) = CURRENT_DATE
GROUP BY symbol, order_status;

-- 手续费统计
SELECT 
    commission_asset,
    SUM(commission) as total_fee,
    COUNT(*) as trade_count
FROM trade_updates
WHERE DATE(transaction_time) = CURRENT_DATE
GROUP BY commission_asset;
```

## 📊 输出格式

### 表格格式（默认）

- 彩色标识盈利/亏损
- 实时更新的表格
- 统计信息显示

### JSON格式

```bash
python -m tri_arb.cli.main account balance -x binance -e perp --output json
```

### CSV格式

```bash
python -m tri_arb.cli.main account positions -x binance -e perp --output csv > positions.csv
```

## 🔧 故障排查

### 常见错误

#### 1. API认证失败

```bash
# 检查环境变量
echo $BINANCE_API_KEY
echo $BINANCE_API_SECRET

# 测试连接
python -m tri_arb.cli.main account balance -x binance -e perp --debug
```

#### 2. WebSocket连接失败

```bash
# 检查数据库连接
psql -U postgres -d trading -c "SELECT 1;"

# 检查环境变量
echo $DATABASE_URL

# 重新初始化数据库
psql -U postgres -d trading -f scripts/init_database.sql
```

#### 3. 权限不足

确保API密钥有以下权限：
- ✅ 读取权限
- ✅ 交易权限（下单需要）
- ❌ 提币权限（不要开启）

### 调试模式

```bash
# 启用详细日志
python -m tri_arb.cli.main account balance -x binance -e perp --debug

# 查看日志文件
tail -f logs/tri-arb.log
```

## 🎯 最佳实践

### 1. 生产环境部署

```bash
# 后台运行WebSocket订阅
nohup python -m tri_arb.cli.main subscribe user-stream -x binance > binance-ws.log 2>&1 &

# 后台运行定时查询
nohup python -m tri_arb.cli.main account watch-balance -x okx -e perp -i 5 > okx-balance.log 2>&1 &

# 后台运行持仓监控
nohup python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 2 > gate-positions.log 2>&1 &
```

### 2. 监控脚本

```bash
#!/bin/bash
# monitor.sh

# 检查WebSocket进程
if ! pgrep -f "subscribe.*binance" > /dev/null; then
    echo "Binance WebSocket已停止，正在重启..."
    nohup python -m tri_arb.cli.main subscribe user-stream -x binance > binance-ws.log 2>&1 &
fi

# 检查定时查询进程
if ! pgrep -f "watch-balance.*okx" > /dev/null; then
    echo "OKX余额监控已停止，正在重启..."
    nohup python -m tri_arb.cli.main account watch-balance -x okx -e perp -i 5 > okx-balance.log 2>&1 &
fi
```

### 3. 数据备份

```bash
# 备份数据库
pg_dump -U postgres -d trading > backup_$(date +%Y%m%d_%H%M%S).sql

# 恢复数据库
psql -U postgres -d trading < backup_20250101_120000.sql
```

### 4. 性能优化

- **WebSocket订阅**: 使用选择性订阅减少数据量
- **定时查询**: 根据数据变化频率调整间隔
- **数据库**: 定期清理历史数据
- **日志**: 设置合适的日志级别

## 📚 参考资源

### 官方文档

- [Binance API文档](https://developers.binance.com/docs/derivatives/usds-margined-futures)
- [OKX API文档](https://www.okx.com/docs-v5/zh/)
- [Gate.io API文档](https://www.gate.io/docs/developers/apiv4/zh_CN/)

### 项目文档

- [QUICK_REFERENCE.md](../QUICK_REFERENCE.md) - 命令快速参考
- [FEATURES.md](../FEATURES.md) - 功能总览
- [docs/GATE.md](GATE.md) - Gate.io详细指南

### 技术支持

- 查看日志文件: `logs/tri-arb.log`
- 启用调试模式: `--debug`
- 检查数据库连接: `psql -U postgres -d trading`

---

**CEXTools** - 专业的多交易所量化交易工具  
**版本**: 2.0  
**支持交易所**: XT, Binance, OKX, Gate.io  
**功能**: REST API, WebSocket订阅, 定时查询, 数据库存储
