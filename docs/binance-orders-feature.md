# 币安合约挂单查询功能实现

## 📋 功能概述

为币安永续合约交易所添加了挂单查询功能，支持查询所有挂单和特定合约挂单。

## ✅ 实现内容

### 1. 核心API实现 (`src/tri_arb/exchanges/binance_perp.py`)

添加了 `get_open_orders()` 方法：

```python
async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]
```

**功能特性**：
- ✅ 支持查询所有挂单（`symbol=None`，权重40）
- ✅ 支持查询特定合约挂单（`symbol="BTCUSDT"`，权重1）
- ✅ 使用币安API v1 (`/fapi/v1/openOrders`)
- ✅ 完整的HMAC-SHA256签名认证
- ✅ 返回详细的订单信息
- ✅ 所有数值字段使用 Decimal 类型确保精度

**返回字段**：
- `orderId`: 系统订单号
- `symbol`: 交易对
- `status`: 订单状态
- `clientOrderId`: 用户自定义订单号
- `price`: 委托价格
- `avgPrice`: 平均成交价
- `origQty`: 原始委托数量
- `executedQty`: 成交量
- `cumQuote`: 成交金额
- `timeInForce`: 有效方法
- `type`: 订单类型（LIMIT, MARKET, STOP等）
- `reduceOnly`: 是否仅减仓
- `closePosition`: 是否条件全平仓
- `side`: 买卖方向（BUY/SELL）
- `positionSide`: 持仓方向（LONG/SHORT/BOTH）
- `stopPrice`: 触发价
- `workingType`: 条件价格触发类型
- `priceProtect`: 是否开启条件单触发保护
- `origType`: 触发前订单类型
- `priceMatch`: 盘口价格下单模式
- `selfTradePreventionMode`: 订单自成交保护模式
- `goodTillDate`: GTD订单自动取消时间
- `time`: 订单时间
- `updateTime`: 更新时间
- `activatePrice`: 跟踪止损激活价格（TRAILING_STOP_MARKET订单）
- `priceRate`: 跟踪止损回调比例（TRAILING_STOP_MARKET订单）

### 2. CLI命令支持

添加了 `cextools account orders` 命令：

```bash
# 查询所有挂单
cextools account orders -x binance -e perp

# 查询特定合约挂单
cextools account orders -x binance -e perp --symbol BTC/USDT

# JSON格式输出
cextools account orders -x binance -e perp -o json

# CSV格式输出
cextools account orders -x binance -e perp -o csv
```

### 3. 表格格式化输出

添加了 `format_open_orders_table()` 函数，显示：
- ✅ **Exchange** - 交易所名称
- ✅ **Symbol** - 交易对
- ✅ **Order ID** - 订单ID
- ✅ **Side** - 买卖方向（绿色BUY/红色SELL）
- ✅ **Type** - 订单类型
- ✅ **Price** - 委托价格（市价单显示"MARKET"）
- ✅ **Quantity** - 数量
- ✅ **Filled** - 已成交数量和百分比
- ✅ **Status** - 订单状态
- ✅ **Time** - 下单时间

### 4. 本地筛选机制

与持仓查询一样，采用本地筛选：
```python
# 1. 始终获取所有挂单
orders_data = await exchange_instance.get_open_orders(None)

# 2. 在本地筛选指定的 symbol
if symbol:
    normalized_symbol = symbol.replace("/", "").replace("_", "").upper()
    filtered_orders = [order for order in orders_data 
                      if order['symbol'] == normalized_symbol]
```

**优势**：
- ✅ 避免格式转换问题
- ✅ 支持任意格式：`BTC/USDT`、`btc_usdt`、`BTCUSDT`
- ✅ 更健壮的实现

### 5. 文档更新

**更新的文档**：
- ✅ `docs/cextools-usage.md` - 添加挂单查询使用示例
- ✅ `docs/binance-api-implementation.md` - 添加API说明
- ✅ `docs/binance-orders-feature.md` - 创建功能实现文档

### 6. 示例代码 (`examples/binance_orders_example.py`)

创建了完整的Python示例代码，包含3个场景：

**示例1：查询所有挂单**
- 连接币安合约交易所
- 查询所有挂单
- 显示详细信息

**示例2：查询特定交易对的挂单**
- 查询指定交易对
- 计算成交百分比
- 格式化显示

**示例3：挂单统计分析**
- 按买卖方向统计
- 按订单类型分组
- 按交易对分组
- 计算总价值
- 显示最近订单

## 🎯 API详细信息

### 接口端点
```
GET /fapi/v1/openOrders
```

### 请求参数
- `symbol` (可选): 交易对，如 "BTCUSDT"
- `timestamp` (必需): 时间戳
- `signature` (必需): HMAC-SHA256签名

### 请求权重
- **带symbol**: 1
- **不带symbol**: 40（请谨慎使用）

### 响应示例

```json
[
  {
    "orderId": 1917641,
    "symbol": "BTCUSDT",
    "status": "NEW",
    "clientOrderId": "abc",
    "price": "9300",
    "avgPrice": "0.00000",
    "origQty": "0.40",
    "executedQty": "0",
    "cumQuote": "0",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "reduceOnly": false,
    "closePosition": false,
    "side": "BUY",
    "positionSide": "SHORT",
    "stopPrice": "0",
    "workingType": "CONTRACT_PRICE",
    "priceProtect": false,
    "origType": "LIMIT",
    "priceMatch": "NONE",
    "selfTradePreventionMode": "NONE",
    "goodTillDate": 0,
    "time": 1579276756075,
    "updateTime": 1579276756075
  }
]
```

## 🚀 使用方法

### 1. 配置API凭证

```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
```

### 2. 使用CLI命令

```bash
# 查询所有挂单（表格格式）
cextools account orders -x binance -e perp

# 查询特定合约
cextools account orders -x binance -e perp -s BTC/USDT

# JSON格式输出（包含完整API数据）
cextools account orders -x binance -e perp -o json

# CSV格式输出
cextools account orders -x binance -e perp -o csv
```

### 3. 使用Python API

```python
import asyncio
from tri_arb.exchanges.binance_perp import BinancePerpExchange

async def main():
    exchange = BinancePerpExchange(
        api_key="your_key",
        api_secret="your_secret"
    )
    
    await exchange.connect()
    
    # 查询所有挂单
    orders = await exchange.get_open_orders()
    
    # 查询特定合约
    btc_orders = await exchange.get_open_orders(symbol="BTCUSDT")
    
    await exchange.disconnect()

asyncio.run(main())
```

### 4. 运行示例代码

```bash
python examples/binance_orders_example.py
```

## 📊 订单类型说明

### 基本订单类型
- `LIMIT`: 限价单
- `MARKET`: 市价单
- `STOP`: 止损限价单
- `STOP_MARKET`: 止损市价单
- `TAKE_PROFIT`: 止盈限价单
- `TAKE_PROFIT_MARKET`: 止盈市价单
- `TRAILING_STOP_MARKET`: 跟踪止损市价单

### 订单状态
- `NEW`: 新建订单
- `PARTIALLY_FILLED`: 部分成交
- `FILLED`: 完全成交
- `CANCELED`: 已取消
- `REJECTED`: 被拒绝
- `EXPIRED`: 已过期

### 有效方法 (timeInForce)
- `GTC`: Good Till Cancel - 一直有效直到取消
- `IOC`: Immediate or Cancel - 立即成交或取消
- `FOK`: Fill or Kill - 全部成交或全部取消
- `GTX`: Good Till Crossing - 只做Maker订单
- `GTD`: Good Till Date - 有效期至指定时间

## 🔍 技术细节

### 1. 数值精度处理

所有数值字段都使用 `Decimal` 类型：
```python
formatted_order = {
    "orderId": order.get("orderId", 0),
    "price": Decimal(order.get("price", "0")),
    "origQty": Decimal(order.get("origQty", "0")),
    "executedQty": Decimal(order.get("executedQty", "0")),
    # ...
}
```

### 2. 特殊订单字段处理

跟踪止损订单有额外字段：
```python
# 处理跟踪止损订单的特殊字段
if order.get("activatePrice"):
    formatted_order["activatePrice"] = Decimal(order.get("activatePrice", "0"))
if order.get("priceRate"):
    formatted_order["priceRate"] = Decimal(order.get("priceRate", "0"))
```

### 3. 时间戳处理

将毫秒时间戳转换为可读格式：
```python
order_time = order.get("time", 0)
if order_time:
    time_str = datetime.fromtimestamp(order_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
```

### 4. 成交百分比计算

```python
orig_qty = order.get("origQty", Decimal('0'))
executed_qty = order.get("executedQty", Decimal('0'))
filled_pct = (executed_qty / orig_qty * 100) if orig_qty > 0 else Decimal('0')
```

## 🎨 输出效果

### 表格格式
```
┏━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Exchange   ┃ Symbol   ┃ Order ID ┃ Side ┃ Type   ┃ Price    ┃ Quantity ┃ Filled           ┃ Status ┃ Time                ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ binance_.. │ BTCUSDT  │ 12345678 │ BUY  │ LIMIT  │ 50000.00 │ 0.001000 │ 0.000000 (0.0%)  │ NEW    │ 2025-10-16 10:30:00 │
└────────────┴──────────┴──────────┴──────┴────────┴──────────┴──────────┴──────────────────┴────────┴─────────────────────┘
```

### JSON格式
```json
[
  {
    "orderId": 12345678,
    "symbol": "BTCUSDT",
    "price": "50000.00",
    "side": "BUY",
    ...
  }
]
```

## 🧪 测试

### 功能测试
- ✅ 查询所有挂单
- ✅ 查询特定合约
- ✅ 空挂单处理
- ✅ 表格/JSON/CSV输出
- ✅ 不同订单类型显示

### 代码质量
- ✅ 无linter错误
- ✅ 类型注解完整
- ✅ Docstring文档
- ✅ 错误处理

## 📝 相关文档

- [币安永续合约挂单API文档](https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Current-All-Open-Orders)
- [CEXTools使用指南](cextools-usage.md)
- [币安API实现状态](binance-api-implementation.md)
- [示例代码说明](../examples/README.md)

## 💡 使用建议

### 性能优化

1. **谨慎使用全量查询**：
   - 查询所有挂单权重为40，可能导致限流
   - 优先使用带symbol参数的查询（权重仅1）
   
2. **本地缓存**：
   - 对于频繁查询，考虑使用本地缓存
   - 设置合理的缓存过期时间

3. **批量处理**：
   - 一次查询所有挂单，在本地进行筛选和分析
   - 避免多次API调用

### 实际应用场景

1. **监控挂单状态**：
   ```bash
   # 定时查询挂单，监控成交情况
   cextools account orders -x binance -e perp -o json
   ```

2. **分析交易策略**：
   ```python
   # 统计不同类型订单的分布
   orders = await exchange.get_open_orders()
   limit_orders = [o for o in orders if o['type'] == 'LIMIT']
   stop_orders = [o for o in orders if 'STOP' in o['type']]
   ```

3. **风险管理**：
   ```python
   # 检查是否有过多未成交订单
   orders = await exchange.get_open_orders()
   if len(orders) > 50:
       print("警告：挂单过多，请及时处理")
   ```

## 🎉 总结

本次实现完整地添加了币安合约挂单查询功能，包括：

1. ✅ 核心API实现
2. ✅ CLI命令集成
3. ✅ 多格式输出支持（table/json/csv）
4. ✅ 完整文档
5. ✅ 示例代码
6. ✅ 错误处理
7. ✅ 代码质量保证

用户现在可以通过命令行或Python API轻松查询币安永续合约的挂单信息！

---

**实现日期**：2025-10-16  
**API版本**：Binance Futures API V1  
**状态**：✅ 已完成并测试

