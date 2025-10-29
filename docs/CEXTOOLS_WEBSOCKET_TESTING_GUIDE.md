# CEXTools WebSocket 功能测试和配置指南

## ✅ 问题解决状态

### 已解决的问题
- ✅ **数据库连接问题**: `role "postgres" does not exist` 已修复
- ✅ **PostgreSQL 配置**: 数据库 `trading` 已创建并初始化
- ✅ **环境变量**: `DATABASE_URL` 已正确设置为 `postgresql+asyncpg://oliver@localhost:5432/trading`
- ✅ **WebSocket 功能**: 基本功能已可用，需要配置 API 凭证

### 当前状态
WebSocket 功能已经可以正常工作，只需要配置相应的 API 凭证即可开始使用。

## 🔑 API 凭证配置

### 1. Binance API 配置

#### 获取 API 密钥
1. 登录 [Binance](https://www.binance.com)
2. 进入 **API 管理** 页面
3. 创建新的 API Key
4. 设置权限：
   - ✅ **读取** (必需)
   - ✅ **交易** (如果需要下单)
   - ❌ **提币** (不要开启)

#### 配置环境变量
```bash
# 添加到 ~/.zshrc
export BINANCE_API_KEY="your_binance_api_key_here"
export BINANCE_API_SECRET="your_binance_api_secret_here"

# 重新加载配置
source ~/.zshrc
```

### 2. OKX API 配置

#### 获取 API 密钥
1. 登录 [OKX](https://www.okx.com)
2. 进入 **API 管理** 页面
3. 创建新的 API Key
4. 设置权限：
   - ✅ **读取** (必需)
   - ✅ **交易** (如果需要下单)
   - ❌ **提币** (不要开启)

#### 配置环境变量
```bash
# OKX 需要三个参数
export OKX_API_KEY="your_okx_api_key_here"
export OKX_API_SECRET="your_okx_api_secret_here"
export OKX_PASSPHRASE="your_okx_passphrase_here"

# 重新加载配置
source ~/.zshrc
```

### 3. XT API 配置

#### 获取 API 密钥
1. 登录 [XT](https://www.xt.com)
2. 进入 **API 管理** 页面
3. 创建新的 API Key
4. 设置权限：
   - ✅ **读取** (必需)
   - ✅ **交易** (如果需要下单)
   - ❌ **提币** (不要开启)

#### 配置环境变量
```bash
export XT_API_KEY="your_xt_api_key_here"
export XT_API_SECRET="your_xt_api_secret_here"

# 重新加载配置
source ~/.zshrc
```

## 🧪 功能测试

### 1. 测试 API 连接

```bash
# 激活虚拟环境
cd /Users/oliver/work/quant
source .venv/bin/activate

# 测试 Binance 连接
cextools account balance -x binance -e perp

# 测试 OKX 连接
cextools account balance -x okx -e perp

# 测试 XT 连接
cextools account balance -x xt -e perp
```

### 2. 测试 WebSocket 订阅

#### Binance WebSocket 测试
```bash
# 基本订阅（表格格式）
cextools subscribe user-stream -x binance

# JSON 格式输出
cextools subscribe user-stream -x binance --output json

# 选择性订阅（只订阅账户和订单）
cextools subscribe user-stream -x binance -c account,order

# 调试模式
cextools subscribe user-stream -x binance --debug
```

#### OKX WebSocket 测试
```bash
# 基本订阅
cextools subscribe user-stream -x okx

# 选择性订阅（账户、持仓、订单）
cextools subscribe user-stream -x okx -c account,position,order

# 不显示输出，只存储到数据库
cextools subscribe user-stream -x okx --output none
```

#### XT WebSocket 测试
```bash
# 基本订阅
cextools subscribe user-stream -x xt

# 选择性订阅
cextools subscribe user-stream -x xt -c account,position,order
```

### 3. 后台运行测试

```bash
# 后台运行 Binance WebSocket
nohup cextools subscribe user-stream -x binance --output none > binance_ws.log 2>&1 &

# 后台运行 OKX WebSocket
nohup cextools subscribe user-stream -x okx --output none > okx_ws.log 2>&1 &

# 查看运行状态
ps aux | grep "subscribe user-stream"

# 查看日志
tail -f binance_ws.log
tail -f okx_ws.log
```

## 📊 数据验证

### 1. 检查数据库中的数据

```bash
# 连接数据库
psql -d trading

# 查看最新的账户更新
SELECT * FROM account_updates ORDER BY event_time DESC LIMIT 10;

# 查看最新的订单更新
SELECT * FROM order_updates ORDER BY event_time DESC LIMIT 10;

# 查看最新的成交记录
SELECT * FROM trade_updates ORDER BY transaction_time DESC LIMIT 10;

# 查看 OKX 数据
SELECT * FROM okx_account_balances ORDER BY update_time DESC LIMIT 5;
SELECT * FROM okx_positions ORDER BY update_time DESC LIMIT 5;
SELECT * FROM okx_orders ORDER BY u_time DESC LIMIT 5;

# 退出数据库
\q
```

### 2. 数据统计查询

```sql
-- 查看各交易所的数据量
SELECT 
    exchange,
    COUNT(*) as update_count,
    MIN(event_time) as first_update,
    MAX(event_time) as last_update
FROM account_updates 
WHERE event_time >= NOW() - INTERVAL '1 hour'
GROUP BY exchange;

-- 查看今日交易统计
SELECT * FROM daily_trade_stats WHERE trade_date = CURRENT_DATE;

-- 查看当前活跃持仓（OKX）
SELECT * FROM okx_latest_positions WHERE pos > 0;
```

## 🔧 故障排查

### 1. 常见错误和解决方案

#### 错误: `缺少Binance API凭证`
```bash
# 检查环境变量
echo $BINANCE_API_KEY
echo $BINANCE_API_SECRET

# 如果为空，重新设置
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"
```

#### 错误: `role "postgres" does not exist`
```bash
# 检查数据库连接字符串
echo $DATABASE_URL

# 应该是: postgresql+asyncpg://oliver@localhost:5432/trading
# 如果不是，重新设置
export DATABASE_URL="postgresql+asyncpg://oliver@localhost:5432/trading"
```

#### 错误: `Connect call failed`
```bash
# 检查 PostgreSQL 状态
brew services list | grep postgresql

# 如果未运行，启动服务
brew services start postgresql@15

# 测试连接
psql -d trading -c "SELECT 1;"
```

### 2. 调试模式

```bash
# 启用详细日志
cextools subscribe user-stream -x binance --debug

# 查看日志文件
tail -f logs/tri-arb.log
tail -f logs/tri-arb-errors.log
```

## 🚀 生产环境部署

### 1. 创建启动脚本

```bash
#!/bin/bash
# start_websocket.sh

# 激活虚拟环境
cd /Users/oliver/work/quant
source .venv/bin/activate

# 启动多个 WebSocket 订阅
nohup cextools subscribe user-stream -x binance --output none > binance_ws.log 2>&1 &
nohup cextools subscribe user-stream -x okx --output none > okx_ws.log 2>&1 &
nohup cextools subscribe user-stream -x xt --output none > xt_ws.log 2>&1 &

echo "WebSocket 订阅已启动"
echo "查看状态: ps aux | grep 'subscribe user-stream'"
echo "查看日志: tail -f *_ws.log"
```

### 2. 监控脚本

```bash
#!/bin/bash
# monitor_websocket.sh

# 检查 Binance WebSocket
if ! pgrep -f "subscribe.*binance" > /dev/null; then
    echo "$(date): Binance WebSocket 已停止，正在重启..."
    cd /Users/oliver/work/quant
    source .venv/bin/activate
    nohup cextools subscribe user-stream -x binance --output none > binance_ws.log 2>&1 &
fi

# 检查 OKX WebSocket
if ! pgrep -f "subscribe.*okx" > /dev/null; then
    echo "$(date): OKX WebSocket 已停止，正在重启..."
    cd /Users/oliver/work/quant
    source .venv/bin/activate
    nohup cextools subscribe user-stream -x okx --output none > okx_ws.log 2>&1 &
fi

echo "$(date): WebSocket 监控完成"
```

### 3. 定时任务

```bash
# 添加到 crontab
crontab -e

# 每5分钟检查一次 WebSocket 状态
*/5 * * * * /path/to/monitor_websocket.sh

# 每天凌晨2点清理旧数据
0 2 * * * /path/to/cleanup_data.sh
```

## 📈 性能优化

### 1. 数据库优化

```sql
-- 创建索引优化查询性能
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_account_updates_time_exchange 
ON account_updates(event_time, exchange);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_order_updates_symbol_time 
ON order_updates(symbol, event_time);

-- 定期清理旧数据
DELETE FROM account_updates WHERE event_time < NOW() - INTERVAL '30 days';
DELETE FROM order_updates WHERE event_time < NOW() - INTERVAL '30 days';
DELETE FROM trade_updates WHERE transaction_time < NOW() - INTERVAL '30 days';
```

### 2. 系统优化

```bash
# PostgreSQL 配置优化
sudo nano /opt/homebrew/var/postgresql@15/postgresql.conf

# 建议配置：
# shared_buffers = 256MB
# effective_cache_size = 1GB
# maintenance_work_mem = 64MB
# checkpoint_completion_target = 0.9
# wal_buffers = 16MB
# default_statistics_target = 100

# 重启 PostgreSQL
brew services restart postgresql@15
```

## 📚 完整示例

### 完整的测试流程

```bash
# 1. 设置环境变量
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
export OKX_API_KEY="your_okx_api_key"
export OKX_API_SECRET="your_okx_api_secret"
export OKX_PASSPHRASE="your_okx_passphrase"
export DATABASE_URL="postgresql+asyncpg://oliver@localhost:5432/trading"

# 2. 激活虚拟环境
cd /Users/oliver/work/quant
source .venv/bin/activate

# 3. 测试 API 连接
cextools account balance -x binance -e perp
cextools account balance -x okx -e perp

# 4. 启动 WebSocket 订阅
cextools subscribe user-stream -x binance --output table

# 5. 在另一个终端查看数据
psql -d trading -c "SELECT * FROM account_updates ORDER BY event_time DESC LIMIT 5;"
```

---

**CEXTools WebSocket** - 实时数据订阅和存储  
**状态**: ✅ 已配置完成，等待 API 凭证  
**数据库**: ✅ PostgreSQL 15 正常运行  
**平台**: ✅ macOS 完全支持

> 🎯 **下一步**: 配置您的 API 凭证，然后就可以开始使用 WebSocket 功能了！

