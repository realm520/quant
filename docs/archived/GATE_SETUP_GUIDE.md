# Gate.io 完整配置指南

## 📋 目录

1. [获取API凭证](#获取api凭证)
2. [配置环境变量](#配置环境变量)
3. [测试连接](#测试连接)
4. [REST API使用](#rest-api使用)
5. [WebSocket订阅](#websocket订阅)
6. [常见问题](#常见问题)

---

## 🔑 获取API凭证

### 步骤1：注册Gate.io账户

访问 https://www.gate.io 注册账户

### 步骤2：创建API Key

1. 登录Gate.io
2. 进入 **我的** → **API管理** → **创建API Key**
3. 设置API Key名称
4. 选择权限：
   - ✅ **读取** (必需)
   - ✅ **交易** (如需下单)
   - ❌ **提现** (不建议)
5. 设置IP白名单（可选但推荐）
6. 完成2FA验证
7. **重要**：保存好API Key和API Secret（Secret只显示一次）

### Gate.io API权限说明

| 功能 | 需要的权限 |
|------|-----------|
| 查询余额/持仓/订单 | 读取 |
| 下单/撤单 | 读取 + 交易 |
| WebSocket订阅 | 读取 |

---

## ⚙️ 配置环境变量

### 方式1：临时配置

```bash
export GATE_API_KEY="your_api_key"
export GATE_API_SECRET="your_api_secret"
```

### 方式2：配置文件

```bash
# 创建.env.gate
cat > .env.gate << 'EOF'
export GATE_API_KEY="your_api_key_here"
export GATE_API_SECRET="your_api_secret_here"
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
EOF

# 加载配置
source .env.gate
```

### 方式3：永久配置

```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
echo 'export GATE_API_KEY="your_key"' >> ~/.bashrc
echo 'export GATE_API_SECRET="your_secret"' >> ~/.bashrc

# 重新加载
source ~/.bashrc
```

### 验证配置

```bash
# 检查环境变量
echo "API Key: $GATE_API_KEY"
echo "API Secret: ${GATE_API_SECRET:0:10}..."
```

---

## 🧪 测试连接

### 使用测试脚本

```bash
cd /home/w_zy/crypto/xt/quant
source .venv/bin/activate
python scripts/test_gate_connection.py
```

**成功输出示例**：
```
Gate.io API连接测试
API Key: abcd1234...
Signature: def567...
Response Status: 200
✅ 连接成功！
```

**失败输出**：
```
❌ 连接失败: 401
可能的问题:
  1. API Key或Secret错误
  2. 签名格式不对
  3. API权限不足
  4. IP未加入白名单
```

---

## 📊 REST API使用

### 查询账户信息

```bash
# 查询余额
cextools account balance -x gate -e perp

# 查询持仓
cextools account positions -x gate -e perp

# 查询特定合约持仓
cextools account positions -x gate -e perp --symbol BTC/USDT

# 查询挂单
cextools account orders -x gate -e perp
```

### 下单交易

```bash
# 限价买入
cextools order place -x gate -e perp \
  -s BTC/USDT \
  --side buy \
  -q 1 \
  -p 50000

# 限价卖出
cextools order place -x gate -e perp \
  -s BTC/USDT \
  --side sell \
  -q 1 \
  -p 60000

# 只减仓订单
cextools order place -x gate -e perp \
  -s BTC/USDT \
  --side sell \
  -q 1 \
  -p 55000 \
  --reduce-only
```

---

## 🌐 WebSocket订阅

### 配置数据库

```bash
# 1. 配置PostgreSQL（如未配置）
bash scripts/configure_postgres_trust.sh

# 2. 初始化数据库表
psql -U postgres -d trading -f scripts/init_database.sql

# 3. 设置数据库URL
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
```

### 启动订阅

```bash
# 订阅所有频道
cextools subscribe user-stream -x gate

# 选择性订阅
cextools subscribe user-stream -x gate -c account          # 只账户
cextools subscribe user-stream -x gate -c position         # 只持仓
cextools subscribe user-stream -x gate -c order            # 只订单
cextools subscribe user-stream -x gate -c position,order   # 持仓+订单

# 指定显示格式
cextools subscribe user-stream -x gate -o table  # 表格（默认）
cextools subscribe user-stream -x gate -o json   # JSON
cextools subscribe user-stream -x gate -o none   # 静默
```

### 查询订阅的数据

```bash
# 连接数据库
psql -U postgres -d trading

# 查询Gate.io数据
SELECT * FROM gate_latest_positions;
SELECT * FROM gate_latest_orders;
SELECT * FROM gate_daily_trade_stats WHERE trade_date = CURRENT_DATE;
```

---

## 🎯 Gate.io特点

### API特性

| 特性 | 说明 |
|------|------|
| **基础URL** | https://api.gateio.ws/api/v4 |
| **签名算法** | HMAC SHA-512 |
| **签名格式** | `METHOD\nPATH\nQUERY\nBODY_HASH\nTIMESTAMP` |
| **合约格式** | `BTC_USDT`（下划线） |
| **仓位模式** | single（单向）/ dual（双向） |

### WebSocket特性

| 特性 | 说明 |
|------|------|
| **URL** | wss://fx-ws.gateio.ws/v4/ws/usdt |
| **频道** | futures.balances, futures.positions, futures.orders |
| **推送模式** | 快照式（类似OKX） |
| **认证** | 每个频道单独认证 |

### 与其他交易所对比

| 特性 | Binance | OKX | Gate.io |
|------|---------|-----|---------|
| 认证 | Key+Secret | Key+Secret+Passphrase | Key+Secret |
| 签名 | HMAC-SHA256 | HMAC-SHA256+Base64 | HMAC-SHA512 |
| 合约格式 | BTCUSDT | BTC-USDT-SWAP | BTC_USDT |
| 仓位 | LONG/SHORT | long/short | size正负 |

---

## 🐛 常见问题

### 1. 401 Unauthorized

**原因**：
- API Key或Secret错误
- 签名计算错误
- API权限不足

**解决**：
```bash
# 1. 验证凭证
echo $GATE_API_KEY
echo ${GATE_API_SECRET:0:10}...

# 2. 测试连接
python scripts/test_gate_connection.py

# 3. 检查API权限
# 登录Gate.io → API管理 → 确认有"读取"权限
```

### 2. IP限制

如果设置了IP白名单：
- 确保当前IP在白名单中
- 或临时移除IP白名单限制

### 3. 时间同步

Gate.io也需要时间同步（通常要求<1分钟误差）：

```bash
# 检查系统时间
date

# 同步时间
sudo ntpdate pool.ntp.org
```

---

## 📚 相关文档

- [Gate.io快速开始](GATE_QUICKSTART.md) ⭐
- [WebSocket完整指南](WEBSOCKET_COMPLETE_GUIDE.md)
- [快速参考手册](../QUICK_REFERENCE.md)

---

## 🎉 完整使用流程

```bash
# 1. 配置API凭证
export GATE_API_KEY="your_key"
export GATE_API_SECRET="your_secret"
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"

# 2. 测试连接
python scripts/test_gate_connection.py

# 3. 查询账户
cextools account balance -x gate -e perp
cextools account positions -x gate -e perp

# 4. 启动WebSocket
cextools subscribe user-stream -x gate -o table

# 5. 查询数据库
psql -U postgres -d trading -c "SELECT * FROM gate_latest_positions;"
```

---

**Gate.io配置完成！** 🚀

