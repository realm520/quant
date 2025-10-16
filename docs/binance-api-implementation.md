# 币安API实现状态

## 🎉 币安真实API已实现

币安交易所（现货和永续合约）已经实现了真实的API调用，可以查询实时数据和账户余额！

## ✅ 已实现功能

### 现货 (Binance Spot)
- ✅ 账户余额查询 - `GET /api/v3/account`
- ✅ 实时价格查询 - `GET /api/v3/ticker/bookTicker`
- ✅ 订单簿深度 - `GET /api/v3/depth`
- ✅ HMAC-SHA256 签名认证

### 永续合约 (Binance Futures)
- ✅ 账户余额查询 - `GET /fapi/v2/balance`
- ✅ 持仓查询 - `GET /fapi/v2/positionRisk`
- ✅ 实时价格查询 - `GET /fapi/v1/ticker/bookTicker`
- ✅ 订单簿深度 - `GET /fapi/v1/depth`
- ✅ HMAC-SHA256 签名认证

## 🔄 待实现功能

以下功能尚未实现，调用时会抛出 `NotImplementedError`：
- ⏳ 下单功能 (`place_order`)
- ⏳ 撤单功能 (`cancel_order`)
- ⏳ 订单状态查询 (`get_order_status`)
- ⏳ 交易历史查询 (`get_trade_history`)
- ⏳ WebSocket 实时订阅 (`subscribe_ticker`, `subscribe_orderbook`)

## 🚀 使用方法

### 1. 配置API凭证

```bash
# 币安现货和永续合约共用同一个API key
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
```

### 2. 查询账户余额

```bash
# 查询币安现货余额
cextools account balance -x binance -e spot

# 查询币安永续合约余额
cextools account balance -x binance -e perp
```

### 3. 查询持仓（永续合约）

```bash
# 查询所有持仓
cextools account positions -x binance -e perp

# 查询特定合约持仓
cextools account positions -x binance -e perp --symbol BTC/USDT

# JSON格式输出（包含完整API数据）
cextools account positions -x binance -e perp -o json
```

### 4. 查询实时价格（无需API密钥）

```bash
# 查询币安现货价格
cextools market ticker -x binance -e spot -s BTC/USDT

# 查询币安永续合约价格（默认）
cextools market ticker -x binance -s BTC/USDT
```

### 4. 查询订单簿深度（无需API密钥）

```bash
# 币安现货订单簿
cextools market depth -x binance -e spot -s BTC/USDT

# 币安永续合约订单簿（默认）
cextools market depth -x binance -s BTC/USDT --limit 50
```

## 💡 实现细节

### 签名认证

币安API使用HMAC-SHA256签名方式：

```python
# 生成签名
def _generate_signature(self, query_string: str) -> str:
    return hmac.new(
        self.api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
```

### API端点

| 交易类型 | BASE_URL | WebSocket URL |
|---------|----------|---------------|
| 现货 | `https://api.binance.com` | `wss://stream.binance.com:9443` |
| 永续合约 | `https://fapi.binance.com` | `wss://fstream.binance.com` |

### 余额数据格式

**现货余额响应**：
```json
{
  "balances": [
    {"asset": "BTC", "free": "1.5", "locked": "0.5"},
    {"asset": "USDT", "free": "10000.0", "locked": "0.0"}
  ]
}
```

**永续合约余额响应**：
```json
[
  {
    "asset": "USDT",
    "balance": "10000.0",
    "availableBalance": "9500.0"
  }
]
```

**统一输出格式**：
```python
{
    "BTC": {
        "available": Decimal("1.5"),
        "frozen": Decimal("0.5"),
        "total": Decimal("2.0")
    }
}
```

### 持仓数据格式

**永续合约持仓响应** (`/fapi/v2/positionRisk`)：
```json
[
  {
    "symbol": "BTCUSDT",
    "positionSide": "BOTH",
    "positionAmt": "0.001",
    "entryPrice": "50000.00",
    "breakEvenPrice": "50001.00",
    "markPrice": "51000.00",
    "unRealizedProfit": "1.00",
    "liquidationPrice": "45000.00",
    "leverage": "10",
    "marginType": "cross",
    "isolatedMargin": "0.00",
    "isAutoAddMargin": "false",
    "notional": "51.00",
    "isolatedWallet": "0",
    "maxNotionalValue": "20000000",
    "updateTime": 1625474304765
  }
]
```

**字段说明**：
- `symbol`: 交易对
- `positionSide`: 持仓方向 (BOTH/LONG/SHORT)
  - BOTH: 单向持仓模式
  - LONG: 双向持仓的多仓
  - SHORT: 双向持仓的空仓
- `positionAmt`: 持仓数量（正数为多，负数为空）
- `entryPrice`: 开仓均价
- `breakEvenPrice`: 盈亏平衡价
- `markPrice`: 标记价格（用于计算未实现盈亏）
- `unRealizedProfit`: 持仓未实现盈亏
- `liquidationPrice`: 参考强平价格
- `leverage`: 当前杠杆倍数
- `marginType`: 保证金类型
  - isolated: 逐仓模式
  - cross: 全仓模式
- `isolatedMargin`: 逐仓保证金
- `isAutoAddMargin`: 是否自动追加保证金（逐仓模式）
- `notional`: 名义价值
- `isolatedWallet`: 逐仓钱包余额
- `maxNotionalValue`: 当前杠杆倍数允许的名义价值上限
- `updateTime`: 更新时间戳

**注意**：
- 建议配合账户推送信息 `ACCOUNT_UPDATE` 使用，以满足及时性和准确性需求
- V2 API 直接返回杠杆倍数和保证金类型，无需计算

## 📊 API限制

### 现货API限制
- 请求频率：1200 请求/分钟
- IP限制：根据账户等级不同
- 签名有效期：默认5000ms

### 永续合约API限制
- 请求频率：2400 请求/分钟
- IP限制：根据账户等级不同
- 签名有效期：默认5000ms

## 🔒 安全建议

1. **API密钥权限**
   - 只读权限适用于余额和行情查询
   - 交易权限用于下单和撤单
   - 不要启用提币权限

2. **IP白名单**
   - 建议在币安后台设置IP白名单
   - 限制API密钥只能从特定IP访问

3. **密钥存储**
   - 使用环境变量存储密钥
   - 不要将密钥硬编码在代码中
   - 不要提交密钥到版本控制

## 🧪 测试示例

### 测试余额查询

```bash
# 设置测试环境变量
export BINANCE_API_KEY="your_test_api_key"
export BINANCE_API_SECRET="your_test_api_secret"

# 测试现货余额
cextools account balance -x binance -e spot -o json

# 测试永续合约余额
cextools account balance -x binance -e perp -o json

# 测试持仓查询
cextools account positions -x binance -e perp -o json

# 测试特定合约持仓
cextools account positions -x binance -e perp -s BTC/USDT -o table
```

### 测试行情查询

```bash
# 测试现货价格（公开API）
cextools market ticker -x binance -e spot -s BTC/USDT -o json

# 测试永续合约价格（公开API）
cextools market ticker -x binance -s ETH/USDT -o json

# 测试订单簿
cextools market depth -x binance -s BTC/USDT --limit 20
```

## 🐛 常见错误

### 1. 签名错误 (HTTP 401)

**问题**：API密钥或签名不正确

**解决**：
```bash
# 检查环境变量
echo $BINANCE_API_KEY
echo $BINANCE_API_SECRET

# 确保密钥正确且有权限
```

### 2. 时间戳错误 (HTTP 400)

**问题**：本地时间与币安服务器时间差距过大

**解决**：
```bash
# 同步系统时间
sudo ntpdate -s time.nist.gov
```

### 3. IP限制 (HTTP 403)

**问题**：IP不在白名单中

**解决**：
- 在币安后台添加当前IP到白名单
- 或删除IP白名单限制（不推荐）

### 4. 请求频率限制 (HTTP 429)

**问题**：请求过于频繁

**解决**：
- 减少请求频率
- 添加请求间隔
- 使用WebSocket代替频繁的REST请求

## 📚 参考资料

- [币安现货API文档](https://binance-docs.github.io/apidocs/spot/en/)
- [币安永续合约API文档](https://binance-docs.github.io/apidocs/futures/en/)
- [项目README](../README.md)
- [CEXTools使用指南](cextools-usage.md)

## 🔜 下一步计划

1. **完善订单功能**
   - 实现下单接口
   - 实现撤单接口
   - 实现订单查询

2. **添加WebSocket支持**
   - 实时价格订阅
   - 实时订单簿订阅
   - 用户数据流订阅

3. **增强功能**
   - 批量订单操作
   - ✅ 持仓查询（永续合约）- 已实现
   - 杠杆设置（永续合约）
   - 持仓模式切换（单向/双向）
   - 调整保证金

---

**状态**：部分实现 ⚡  
**最后更新**：2025-10-16  
**贡献者**：欢迎PR完善更多功能！

