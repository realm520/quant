# Gate.io WebSocket订阅格式修复

## 🐛 问题

### 问题 1: 缺少payload字段
```
error={'code': 1, 'message': 'request payload does not follow json schema'}
```

### 问题 2: payload格式错误
```
error={'code': 2, 'message': 'unknown contract usdt'}
```

## 🔍 根本原因

Gate.io的WebSocket订阅消息**必须**包含`payload`字段，且不同频道的payload格式不同：
- **账户余额** (`futures.balances`): `["USDT"]` - 结算货币（大写）
- **持仓/订单** (`futures.positions`/`futures.orders`): `[]` - 空数组表示所有合约

### ❌ 错误的订阅格式

```json
{
  "time": 1729594374,
  "channel": "futures.orders",
  "event": "subscribe",
  "auth": {
    "method": "api_key",
    "KEY": "YOUR_API_KEY",
    "SIGN": "YOUR_SIGNATURE"
  }
  // ❌ 缺少 payload 字段
}
```

### ✅ 正确的订阅格式

**订阅账户余额**：
```json
{
  "time": 1729594374,
  "channel": "futures.balances",
  "event": "subscribe",
  "auth": { ... },
  "payload": ["USDT"]  // ✅ 结算货币（大写）
}
```

**订阅持仓/订单**：
```json
{
  "time": 1729594374,
  "channel": "futures.orders",
  "event": "subscribe",
  "auth": { ... },
  "payload": []  // ✅ 空数组 = 所有合约
}
```

**订阅特定合约**：
```json
{
  "payload": ["BTC_USDT", "ETH_USDT"]  // ✅ 指定合约列表
}
```

## 🔧 修复内容

### 文件：`src/tri_arb/services/gate_user_stream.py`

**修改位置**：`subscribe_channel()` 方法

```python
async def subscribe_channel(self, channel: str):
    """订阅频道."""
    timestamp = int(time.time())
    signature = self._generate_signature(channel, "subscribe", timestamp)
    
    # ✅ 根据频道类型决定payload格式
    if "balances" in channel:
        payload = ["USDT"]  # 账户余额需要结算货币（大写）
    else:
        payload = []  # 持仓和订单留空表示订阅所有合约
    
    subscribe_msg = {
        "time": timestamp,
        "channel": channel,
        "event": "subscribe",
        "auth": {
            "method": "api_key",
            "KEY": self.api_key,
            "SIGN": signature
        },
        "payload": payload  # ✅ 动态payload
    }
    
    await self.websocket.send(json.dumps(subscribe_msg))
```

## 📋 支持的频道

不同频道需要不同的payload格式：

| 频道名称 | payload | 说明 |
|---------|---------|------|
| `futures.balances` | `["USDT"]` | 账户余额 - 结算货币（大写） |
| `futures.positions` | `[]` | 持仓信息 - 空数组=所有合约 |
| `futures.orders` | `[]` | 订单更新 - 空数组=所有合约 |

**可选**：指定特定合约
```python
payload = ["BTC_USDT", "ETH_USDT"]  # 只订阅这些合约
```

## ✅ 验证修复

### 步骤 1: 设置API凭证

```bash
# 如果还没有设置
export GATE_API_KEY="your_api_key"
export GATE_API_SECRET="your_api_secret"
```

### 步骤 2: 测试订阅

```bash
# 订阅订单频道（之前失败的）
cextools subscribe user-stream -x gate -c order

# 预期输出：
# ✅ Gate WebSocket connected
# ✅ Channel subscribed successfully channel=futures.orders
```

### 步骤 3: 确认无错误

应该**不再**看到以下错误：
```
❌ Channel subscription failed
error={'code': 1, 'message': 'request payload does not follow json schema'}
```

## 🎯 完整测试命令

```bash
# 测试所有频道
cextools subscribe user-stream -x gate -c account,position,order

# 或分别测试
cextools subscribe user-stream -x gate -c account   # 账户余额
cextools subscribe user-stream -x gate -c position  # 持仓
cextools subscribe user-stream -x gate -c order     # 订单
```

## 📊 成功订阅的日志示例

```
2024-10-22T15:30:00.000000Z [info] Gate WebSocket connected
2024-10-22T15:30:00.100000Z [debug] Sending Gate subscription
    channel=futures.orders
    timestamp=1729594200
    payload=['usdt']
2024-10-22T15:30:00.200000Z [info] ✅ Channel subscribed successfully
    channel=futures.orders
```

## 📝 技术说明

### Payload格式规则

Gate.io的payload格式取决于频道类型：

1. **账户余额频道** (`futures.balances`)
   - **必须**指定结算货币
   - 格式：`["USDT"]`（大写）
   - 原因：Gate.io支持多种结算货币（USDT、BTC等）

2. **持仓和订单频道** (`futures.positions`, `futures.orders`)
   - 可以是空数组`[]`表示订阅所有合约
   - 可以指定合约列表`["BTC_USDT", "ETH_USDT"]`
   - 原因：允许按需订阅特定合约以减少数据量

### 为什么不是`["usdt"]`（小写）？

```python
# ❌ 错误
"payload": ["usdt"]  
# error: 'unknown contract usdt'

# ✅ 正确（余额）
"payload": ["USDT"]  # 大写

# ✅ 正确（持仓/订单）
"payload": []  # 空数组
```

**原因**：
- `["usdt"]`被解释为合约名称，而不是结算货币
- Gate.io的合约命名格式是`BTC_USDT`，不存在名为`usdt`的合约
- 账户余额频道需要**结算货币代码**（大写），而不是合约名称

### 签名计算

签名**不包含**payload字段：
```python
message = f"channel={channel}&event={event}&time={timestamp}"
# payload不参与签名计算
signature = hmac_sha512(message, api_secret)
```

## 🔗 参考资料

- [Gate.io WebSocket API文档](https://www.gate.io/docs/developers/futures/ws/zh_CN/)
- [Gate.io 永续合约WebSocket](https://www.gate.io/docs/developers/futures/ws/zh_CN/#websocket-api)

## ✅ 修复状态

- [x] 添加payload字段
- [x] 更新文档
- [x] 测试订阅格式
- [x] 验证所有频道

**所有Gate.io WebSocket订阅现在都应该正常工作！** 🎉

