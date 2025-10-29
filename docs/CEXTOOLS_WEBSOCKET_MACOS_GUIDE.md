# CEXTools WebSocket 功能配置指南 (macOS)

本指南将帮助您在 macOS 上配置 CEXTools 的 WebSocket 功能，实现实时数据订阅和存储。

## 🎯 功能概述

CEXTools WebSocket 功能支持：
- **实时账户更新** - 余额变化、持仓变化
- **实时订单更新** - 订单状态变化、成交信息
- **数据存储** - 自动存储到 PostgreSQL 数据库
- **多交易所支持** - Binance、OKX、Gate.io、XT

## 📋 前置条件

### 1. 系统要求
- macOS 10.15+ 
- Python 3.11+
- PostgreSQL 15+

### 2. 已完成的配置
- ✅ PostgreSQL 已安装并运行
- ✅ 数据库 `trading` 已创建
- ✅ 数据库表结构已初始化
- ✅ 环境变量 `DATABASE_URL` 已设置

## 🚀 快速开始

### 1. 验证环境

```bash
# 检查 PostgreSQL 状态
brew services list | grep postgresql

# 检查数据库连接
psql -d trading -c "SELECT version();"

# 检查环境变量
echo $DATABASE_URL
```

### 2. 配置 API 凭证

#### Binance 配置
```bash
# 添加到 ~/.zshrc
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"

# 重新加载配置
source ~/.zshrc
```

#### OKX 配置
```bash
# OKX 需要三个参数
export OKX_API_KEY="your_okx_api_key"
export OKX_API_SECRET="your_okx_api_secret"
export OKX_PASSPHRASE="your_okx_passphrase"

# 重新加载配置
source ~/.zshrc
```

#### XT 配置
```bash
export XT_API_KEY="your_xt_api_key"
export XT_API_SECRET="your_xt_api_secret"

# 重新加载配置
source ~/.zshrc
```

### 3. 启动 WebSocket 订阅

#### Binance WebSocket
```bash
# 激活虚拟环境
cd /Users/oliver/work/quant
source .venv/bin/activate

# 订阅 Binance 用户数据流
cextools subscribe user-stream -x binance

# 选择性订阅（只订阅账户和订单）
cextools subscribe user-stream -x binance -c account,order

# JSON 格式输出
cextools subscribe user-stream -x binance --output json
```

#### OKX WebSocket
```bash
# 订阅 OKX 用户数据流
cextools subscribe user-stream -x okx

# 选择性订阅（账户、持仓、订单）
cextools subscribe user-stream -x okx -c account,position,order

# 不显示输出，只存储到数据库
cextools subscribe user-stream -x okx --output none
```

#### XT WebSocket
```bash
# 订阅 XT 用户数据流（默认交易所）
cextools subscribe user-stream -x xt

# 选择性订阅
cextools subscribe user-stream -x xt -c account,position,order
```

## 📊 数据存储

### 数据库表结构

WebSocket 数据会自动存储到以下表中：

#### Binance 数据表
- `account_updates` - 账户余额更新
- `order_updates` - 订单状态更新  
- `trade_updates` - 成交记录
- `listen_keys` - WebSocket 连接密钥

#### OKX 数据表
- `okx_account_balances` - 账户余额
- `okx_positions` - 持仓信息
- `okx_orders` - 订单信息
- `okx_trades` - 成交记录

#### XT 数据表
- `xt_account_updates` - 账户更新
- `xt_position_updates` - 持仓更新
- `xt_order_updates` - 订单更新
- `xt_trade_updates` - 成交更新

### 查看存储的数据

```bash
# 连接数据库
psql -d trading

# 查看最新的账户更新
SELECT * FROM account_updates ORDER BY event_time DESC LIMIT 10;

# 查看最新的订单更新
SELECT * FROM order_updates ORDER BY event_time DESC LIMIT 10;

# 查看今日成交统计
SELECT * FROM daily_trade_stats WHERE trade_date = CURRENT_DATE;

# 退出数据库
\q
```

## 🔧 高级配置

### 1. 后台运行

```bash
# 后台运行 Binance WebSocket
nohup cextools subscribe user-stream -x binance --output none > binance_ws.log 2>&1 &

# 后台运行 OKX WebSocket
nohup cextools subscribe user-stream -x okx --output none > okx_ws.log 2>&1 &

# 查看运行状态
ps aux | grep "subscribe user-stream"
```

### 2. 监控脚本

创建监控脚本 `monitor_websocket.sh`：

```bash
#!/bin/bash
# monitor_websocket.sh

# 激活虚拟环境
cd /Users/oliver/work/quant
source .venv/bin/activate

# 检查 Binance WebSocket
if ! pgrep -f "subscribe.*binance" > /dev/null; then
    echo "$(date): Binance WebSocket 已停止，正在重启..."
    nohup cextools subscribe user-stream -x binance --output none > binance_ws.log 2>&1 &
fi

# 检查 OKX WebSocket
if ! pgrep -f "subscribe.*okx" > /dev/null; then
    echo "$(date): OKX WebSocket 已停止，正在重启..."
    nohup cextools subscribe user-stream -x okx --output none > okx_ws.log 2>&1 &
fi

echo "$(date): WebSocket 监控完成"
```

```bash
# 使脚本可执行
chmod +x monitor_websocket.sh

# 添加到 crontab（每5分钟检查一次）
crontab -e
# 添加以下行：
# */5 * * * * /path/to/monitor_websocket.sh
```

### 3. 数据清理脚本

创建数据清理脚本 `cleanup_data.sh`：

```bash
#!/bin/bash
# cleanup_data.sh

# 连接数据库并清理30天前的数据
psql -d trading << EOF
-- 清理30天前的账户更新
DELETE FROM account_updates WHERE event_time < NOW() - INTERVAL '30 days';

-- 清理30天前的订单更新
DELETE FROM order_updates WHERE event_time < NOW() - INTERVAL '30 days';

-- 清理30天前的成交记录
DELETE FROM trade_updates WHERE transaction_time < NOW() - INTERVAL '30 days';

-- 清理过期的 ListenKey
DELETE FROM listen_keys WHERE expires_at < NOW();

-- 显示清理结果
SELECT 'account_updates' as table_name, COUNT(*) as remaining_records FROM account_updates
UNION ALL
SELECT 'order_updates', COUNT(*) FROM order_updates
UNION ALL
SELECT 'trade_updates', COUNT(*) FROM trade_updates;
EOF
```

## 📈 数据分析

### 1. 实时监控查询

```sql
-- 查看当前活跃持仓
SELECT * FROM okx_latest_positions WHERE pos > 0;

-- 查看当前挂单
SELECT * FROM okx_latest_orders WHERE state = 'live';

-- 查看今日交易统计
SELECT * FROM okx_daily_trade_stats WHERE trade_date = CURRENT_DATE;
```

### 2. 性能分析

```sql
-- WebSocket 连接统计
SELECT * FROM xt_websocket_stats;

-- 数据更新频率分析
SELECT 
    exchange,
    COUNT(*) as update_count,
    MIN(event_time) as first_update,
    MAX(event_time) as last_update
FROM account_updates 
WHERE event_time >= NOW() - INTERVAL '1 hour'
GROUP BY exchange;
```

## 🛠️ 故障排查

### 1. 常见问题

#### WebSocket 连接失败
```bash
# 检查 API 凭证
echo $BINANCE_API_KEY
echo $BINANCE_API_SECRET

# 测试 API 连接
cextools account balance -x binance -e perp --debug
```

#### 数据库连接问题
```bash
# 检查 PostgreSQL 状态
brew services list | grep postgresql

# 测试数据库连接
psql -d trading -c "SELECT 1;"

# 检查环境变量
echo $DATABASE_URL
```

#### 权限问题
```bash
# 检查 API 权限设置
# 确保 API 密钥有以下权限：
# ✅ 读取权限
# ✅ 交易权限（如果需要下单）
# ❌ 提币权限（不要开启）
```

### 2. 调试模式

```bash
# 启用调试模式查看详细日志
cextools subscribe user-stream -x binance --debug

# 查看日志文件
tail -f binance_ws.log
tail -f logs/tri-arb.log
```

### 3. 重新初始化

如果遇到严重问题，可以重新初始化：

```bash
# 停止所有 WebSocket 连接
pkill -f "subscribe user-stream"

# 重新创建数据库表
cextools subscribe user-stream -x binance --create-tables

# 重新启动订阅
cextools subscribe user-stream -x binance
```

## 📊 监控和告警

### 1. 系统监控

```bash
# 监控脚本
#!/bin/bash
# system_monitor.sh

# 检查 PostgreSQL 状态
if ! brew services list | grep postgresql | grep started > /dev/null; then
    echo "PostgreSQL 未运行，正在启动..."
    brew services start postgresql@15
fi

# 检查数据库连接
if ! psql -d trading -c "SELECT 1;" > /dev/null 2>&1; then
    echo "数据库连接失败"
    exit 1
fi

# 检查 WebSocket 进程
if ! pgrep -f "subscribe user-stream" > /dev/null; then
    echo "WebSocket 进程未运行"
    exit 1
fi

echo "系统状态正常"
```

### 2. 数据质量监控

```sql
-- 检查数据更新频率
SELECT 
    exchange,
    COUNT(*) as updates_last_hour,
    MAX(event_time) as last_update
FROM account_updates 
WHERE event_time >= NOW() - INTERVAL '1 hour'
GROUP BY exchange;

-- 检查数据完整性
SELECT 
    'account_updates' as table_name,
    COUNT(*) as total_records,
    COUNT(DISTINCT exchange) as exchanges,
    MIN(event_time) as earliest_record,
    MAX(event_time) as latest_record
FROM account_updates
UNION ALL
SELECT 
    'order_updates',
    COUNT(*),
    COUNT(DISTINCT exchange),
    MIN(event_time),
    MAX(event_time)
FROM order_updates;
```

## 🎯 最佳实践

### 1. 生产环境部署

```bash
# 使用 systemd 服务（推荐）
sudo cp scripts/systemd/tri-arb.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tri-arb
sudo systemctl start tri-arb

# 查看服务状态
sudo systemctl status tri-arb
```

### 2. 数据备份

```bash
# 每日备份脚本
#!/bin/bash
# backup_daily.sh

BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# 备份数据库
pg_dump -d trading > $BACKUP_DIR/trading_backup_$DATE.sql

# 压缩备份文件
gzip $BACKUP_DIR/trading_backup_$DATE.sql

# 删除7天前的备份
find $BACKUP_DIR -name "trading_backup_*.sql.gz" -mtime +7 -delete
```

### 3. 性能优化

```bash
# PostgreSQL 性能调优
# 编辑 postgresql.conf
sudo nano /opt/homebrew/var/postgresql@15/postgresql.conf

# 建议配置：
# shared_buffers = 256MB
# effective_cache_size = 1GB
# maintenance_work_mem = 64MB
# checkpoint_completion_target = 0.9
# wal_buffers = 16MB
# default_statistics_target = 100
```

## 📚 参考资源

### 官方文档
- [Binance WebSocket API](https://developers.binance.com/docs/derivatives/usds-margined-futures/user-data-stream)
- [OKX WebSocket API](https://www.okx.com/docs-v5/zh/#websocket-api)
- [PostgreSQL 文档](https://www.postgresql.org/docs/)

### 项目文档
- [CEXTools 完整指南](CEXTOOLS_COMPLETE_GUIDE.md)
- [WebSocket 完整指南](WEBSOCKET_COMPLETE_GUIDE.md)
- [macOS 部署指南](CEXTOOLS_MACOS_DEPLOYMENT_GUIDE.md)

---

**CEXTools WebSocket** - 实时数据订阅和存储  
**版本**: 2.0  
**支持交易所**: Binance, OKX, Gate.io, XT  
**数据库**: PostgreSQL 15+  
**平台**: macOS 10.15+

> ⚠️ **重要提示**: WebSocket 功能需要有效的 API 凭证和稳定的网络连接。请确保在生产环境中设置适当的监控和备份策略。
