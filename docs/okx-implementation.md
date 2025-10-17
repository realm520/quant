# OKX交易所实现文档

## 📋 功能概述

为OKX永续合约交易所实现了完整的查询功能，包括余额查询、持仓查询和挂单查询。

## ✅ 已实现功能

### 永续合约 (OKX Futures)
- ✅ 账户余额查询 - `GET /api/v5/account/balance`
- ✅ 持仓查询 - `GET /api/v5/account/positions`
- ✅ 挂单查询 - `GET /api/v5/trade/orders-pending`
- ✅ 下单功能 - `POST /api/v5/trade/order`
- ✅ HMAC-SHA256 签名认证

## 🎯 核心特性

### 1. 三要素认证
OKX API 需要三个认证参数：
- `OK-ACCESS-KEY`: API Key
- `OK-ACCESS-SIGN`: HMAC-SHA256签名
- `OK-ACCESS-PASSPHRASE`: API密码（创建API时设置）
- `OK-ACCESS-TIMESTAMP`: ISO时间戳

### 2. 产品ID格式
OKX使用特殊的产品ID格式：
- 永续合约：`BTC-USDT-SWAP`
- 交割合约：`BTC-USDT-250328`

与其他交易所的区别：
- 币安：`BTCUSDT`
- XT：`btc_usdt`

### 3. 持仓方向
OKX支持三种持仓方向：
- `long`: 多仓
- `short`: 空仓
- `net`: 单向持仓

## 🚀 使用方法

### 1. 配置API凭证

```bash
# OKX需要3个参数
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_api_secret"
export OKX_PASSPHRASE="your_passphrase"
```

### 2. 使用CLI命令

```bash
# 查询账户余额
cextools account balance -x okx -e perp

# 查询所有持仓
cextools account positions -x okx -e perp

# 查询特定合约持仓
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP

# 查询所有挂单
cextools account orders -x okx -e perp

# JSON格式输出
cextools account positions -x okx -e perp -o json

# CSV格式输出
cextools account positions -x okx -e perp -o csv
```

### 3. 使用Python API

```python
import asyncio
from tri_arb.exchanges.okx_perp import OKXPerpExchange

async def main():
    exchange = OKXPerpExchange(
        api_key="your_key",
        api_secret="your_secret",
        passphrase="your_passphrase"
    )
    
    await exchange.connect()
    
    # 查询余额
    balances = await exchange.get_balance()
    
    # 查询所有持仓
    positions = await exchange.get_positions()
    
    # 查询特定合约持仓
    btc_positions = await exchange.get_positions(symbol="BTC-USDT-SWAP")
    
    # 查询挂单
    orders = await exchange.get_open_orders()
    
    await exchange.disconnect()

asyncio.run(main())
```

## 📊 数据格式

### 余额数据格式

**API响应**：
```json
{
  "code": "0",
  "msg": "",
  "data": [
    {
      "details": [
        {
          "ccy": "USDT",
          "eq": "10000.5",
          "availEq": "9500.3",
          "frozenBal": "500.2"
        }
      ]
    }
  ]
}
```

**统一输出格式**：
```python
{
    "USDT": {
        "available": Decimal("9500.3"),
        "frozen": Decimal("500.2"),
        "total": Decimal("10000.5")
    }
}
```

### 持仓数据格式

**API响应**：
```json
{
  "code": "0",
  "msg": "",
  "data": [
    {
      "instId": "BTC-USDT-SWAP",
      "posId": "123456",
      "posSide": "long",
      "pos": "0.1",
      "availPos": "0.1",
      "avgPx": "50000",
      "markPx": "51000",
      "upl": "100",
      "uplRatio": "0.02",
      "lever": "10",
      "liqPx": "45000",
      "imr": "500",
      "margin": "500",
      "mgnMode": "cross",
      "notionalUsd": "5100",
      "uTime": "1634025600000"
    }
  ]
}
```

**字段说明**：
- `instId`: 产品ID
- `posId`: 持仓ID
- `posSide`: 持仓方向 (long/short/net)
- `pos`: 持仓数量
- `availPos`: 可平仓数量
- `avgPx`: 开仓均价
- `markPx`: 最新标记价格
- `upl`: 未实现收益
- `uplRatio`: 未实现收益率
- `lever`: 杠杆倍数
- `liqPx`: 预估强平价
- `imr`: 初始保证金
- `margin`: 保证金余额
- `mgnMode`: 保证金模式 (cross/isolated)
- `notionalUsd`: 持仓名义价值(USD)

### 挂单数据格式

**API响应**：
```json
{
  "code": "0",
  "msg": "",
  "data": [
    {
      "instId": "BTC-USDT-SWAP",
      "ordId": "123456789",
      "clOrdId": "custom_id",
      "ordType": "limit",
      "side": "buy",
      "posSide": "long",
      "px": "50000",
      "sz": "0.1",
      "avgPx": "0",
      "accFillSz": "0",
      "state": "live",
      "lever": "10",
      "fee": "0",
      "cTime": "1634025600000",
      "uTime": "1634025600000"
    }
  ]
}
```

**字段说明**：
- `instId`: 产品ID
- `ordId`: 订单ID
- `clOrdId`: 客户自定义订单ID
- `ordType`: 订单类型 (limit/market/post_only等)
- `side`: 订单方向 (buy/sell)
- `posSide`: 持仓方向 (long/short/net)
- `px`: 委托价格
- `sz`: 委托数量
- `avgPx`: 成交均价
- `accFillSz`: 累计成交数量
- `state`: 订单状态 (live/partially_filled/filled/canceled)
- `lever`: 杠杆倍数

## 🔒 安全建议

### 1. API权限设置
- **只读权限**：适用于余额、持仓、挂单查询
- **交易权限**：用于下单和撤单
- **提币权限**：不要启用（除非必要）

### 2. IP白名单
- 建议在OKX后台设置IP白名单
- 限制API密钥只能从特定IP访问

### 3. Passphrase安全
- Passphrase是创建API时自己设置的密码
- 不同于账户登录密码
- 妥善保管，不要分享

## 🔍 技术细节

### 1. 签名生成

```python
def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
    """Generate OKX API signature."""
    message = timestamp + method + request_path + body
    mac = hmac.new(
        self.api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    )
    return base64.b64encode(mac.digest()).decode()
```

签名步骤：
1. 拼接：`timestamp + method + request_path + body`
2. HMAC-SHA256 加密
3. Base64 编码

### 2. 时间戳格式

OKX要求ISO格式时间戳：
```python
timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
# 例如：2023-10-16T10:30:00.123Z
```

### 3. 本地筛选机制

与Binance类似，采用本地筛选：
```python
# 1. 始终获取所有数据
positions = await exchange.get_positions()

# 2. 在本地筛选
if symbol:
    filtered = [p for p in positions if p['instId'] == symbol]
```

优势：
- ✅ 避免symbol格式转换问题
- ✅ 统一的实现逻辑
- ✅ 更灵活的筛选

### 4. 错误处理

OKX API返回格式：
```json
{
  "code": "0",    // "0"表示成功
  "msg": "",
  "data": [...]
}
```

错误检查：
```python
if data.get("code") != "0":
    raise ValueError(f"OKX API error: {data.get('msg')}")
```

## 📝 代码实现

### 文件清单

1. **核心实现**：
   - `src/tri_arb/exchanges/okx_perp.py` - OKX永续合约适配器

2. **CLI集成**：
   - `src/tri_arb/cli/utils/exchange_factory.py` - 添加OKX支持
   - `src/tri_arb/cli/formatters/table.py` - 表格格式化（支持OKX格式）
   - `src/tri_arb/cli/commands/account.py` - CSV导出（支持OKX格式）

3. **示例代码**：
   - `examples/okx_example.py` - 完整使用示例

4. **文档**：
   - `docs/okx-implementation.md` - 本文档
   - `docs/cextools-usage.md` - 已更新OKX使用说明

### 代码特点

- ✅ 无linter错误
- ✅ 完整的类型注解
- ✅ 详细的中文注释
- ✅ 完整的错误处理
- ✅ 统一的数据格式

## 🆚 与其他交易所的对比

| 特性 | OKX | Binance | XT |
|------|-----|---------|-----|
| API版本 | V5 | V2/V3 | V1 |
| 认证参数 | 3个(Key+Secret+Pass) | 2个(Key+Secret) | 2个(Key+Secret) |
| Symbol格式 | BTC-USDT-SWAP | BTCUSDT | btc_usdt |
| 持仓方向 | long/short/net | LONG/SHORT/BOTH | LONG/SHORT |
| 时间戳格式 | ISO | Unix毫秒 | Unix毫秒 |
| 响应包装 | {"code","msg","data"} | 直接数组 | 直接数组 |

## 🧪 测试

### 功能测试
- ✅ 查询余额
- ✅ 查询所有持仓
- ✅ 查询特定合约持仓
- ✅ 查询所有挂单
- ✅ 查询特定合约挂单
- ✅ 表格/JSON/CSV输出

### 代码质量
- ✅ 无linter错误
- ✅ 类型注解完整
- ✅ Docstring文档
- ✅ 错误处理

## 🔜 待实现功能

### 近期计划
1. **现货交易支持**
   - 余额查询
   - 订单管理
   
2. ✅ **下单功能**（已完成）
   - ✅ 限价单
   - ✅ 市价单
   - ✅ Post-only订单
   
3. **撤单功能**
   - 单个撤单
   - 批量撤单

### 长期计划
1. **行情数据**
   - 实时价格
   - 订单簿
   - K线数据

2. **WebSocket支持**
   - 实时行情订阅
   - 账户推送

3. **高级功能**
   - 杠杆设置
   - 保证金模式切换

## 📚 相关文档

- [OKX API官方文档](https://www.okx.com/docs-v5/zh/)
- [CEXTools使用指南](cextools-usage.md)
- [示例代码](../examples/okx_example.py)

## 💡 使用建议

### 1. Symbol格式注意
```bash
# ❌ 错误（Binance格式）
cextools account positions -x okx -e perp --symbol BTCUSDT

# ✅ 正确（OKX格式）
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP
```

### 2. Passphrase保管
```bash
# Passphrase是创建API时设置的密码，不是登录密码
export OKX_PASSPHRASE="your_custom_passphrase"
```

### 3. 权限设置
- 查询功能只需要"读取"权限
- 不要开启"提币"权限
- 建议设置IP白名单

## 🎉 总结

OKX交易所集成已完成基础功能：

1. ✅ 完整的认证机制（三要素）
2. ✅ 余额查询功能
3. ✅ 持仓查询功能
4. ✅ 挂单查询功能
5. ✅ CLI命令集成
6. ✅ 多格式输出（table/json/csv）
7. ✅ 完整文档和示例

用户现在可以通过命令行或Python API轻松查询OKX永续合约的账户信息！

---

**实现日期**：2025-10-16  
**API版本**：OKX API V5  
**状态**：✅ 已完成并测试

