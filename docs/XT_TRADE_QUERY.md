# XT 成交记录查询说明

## 概述

XT 交易所提供了 RESTful API 来查询成交记录。本文档说明如何使用 `get_user_trades` 方法查询成交明细。

**API 文档**: [查看成交明细](https://doc.xt.com/zh-Hans/docs/futures/Order/see-transaction-details)

## API 端点

- **端点**: `/future/trade/v1/order/trade-list`
- **方法**: `GET`
- **限流**: 200/s/apikey

## 方法签名

```python
async def get_user_trades(
    self,
    symbol: str | None = None,
    order_id: int | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    page: int = 1,
    size: int = 10,
    limit: int | None = None,
) -> dict[str, Any]
```

## 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 | 范围 |
|------|------|------|--------|------|------|
| `symbol` | str | 否 | None | 交易对（如 "btc_usdt"） | - |
| `order_id` | int | 否 | None | 订单 ID，查询特定订单的成交记录 | - |
| `start_time` | int | 否 | None | 开始时间（毫秒时间戳） | - |
| `end_time` | int | 否 | None | 结束时间（毫秒时间戳） | - |
| `page` | int | 否 | 1 | 页码（必须为正整数） | >= 1 |
| `size` | int | 否 | 10 | 每页数量（最大 100） | 1-100 |
| `limit` | int | 否 | None | **已废弃**，使用 `size` 代替 | - |

## 返回值

返回字典，包含以下字段：

```python
{
    "items": [  # 成交记录列表
        {
            "fee": 0.0,              # 手续费
            "feeCoin": "USDT",       # 手续费币种
            "orderId": 123456,       # 订单 ID
            "execId": 789012,        # 成交 ID
            "price": 50000.0,        # 成交价格
            "quantity": 0.1,         # 成交量
            "symbol": "btc_usdt",    # 交易对
            "timestamp": 1234567890,  # 时间戳（毫秒）
            "takerMaker": "TAKER"    # "TAKER" 或 "MAKER"
        },
        ...
    ],
    "page": 1,      # 当前页码
    "ps": 10,       # 每页数量
    "total": 100    # 总记录数
}
```

## 使用示例

### 1. 基本查询（查询最近的成交记录）

```python
from tri_arb.exchanges.xt_perp import XTPerpExchange

# 创建交易所实例
exchange = XTPerpExchange(api_key="your_api_key", api_secret="your_api_secret")
await exchange.connect()

# 查询最近的成交记录（默认：第1页，每页10条）
result = await exchange.get_user_trades()

print(f"总记录数: {result['total']}")
print(f"当前页: {result['page']}")
print(f"每页数量: {result['ps']}")

for trade in result['items']:
    print(f"订单ID: {trade['orderId']}, 成交价: {trade['price']}, 成交量: {trade['quantity']}")
```

### 2. 查询特定交易对的成交记录

```python
# 查询 BTC/USDT 的成交记录
result = await exchange.get_user_trades(symbol="btc_usdt")

for trade in result['items']:
    print(f"{trade['symbol']}: {trade['quantity']} @ {trade['price']}")
```

### 3. 查询特定订单的成交记录

```python
# 查询订单 ID 为 123456 的所有成交记录
result = await exchange.get_user_trades(order_id=123456)

for trade in result['items']:
    print(f"成交ID: {trade['execId']}, 价格: {trade['price']}, 数量: {trade['quantity']}")
```

### 4. 按时间范围查询

```python
from datetime import datetime, timedelta

# 查询最近24小时的成交记录
end_time = int(datetime.now().timestamp() * 1000)
start_time = int((datetime.now() - timedelta(hours=24)).timestamp() * 1000)

result = await exchange.get_user_trades(
    symbol="btc_usdt",
    start_time=start_time,
    end_time=end_time
)

print(f"最近24小时成交记录数: {result['total']}")
```

### 5. 分页查询

```python
# 查询第1页，每页50条
result = await exchange.get_user_trades(
    symbol="btc_usdt",
    page=1,
    size=50
)

# 查询第2页
result = await exchange.get_user_trades(
    symbol="btc_usdt",
    page=2,
    size=50
)
```

### 6. 查询所有成交记录（分页遍历）

```python
async def get_all_trades(exchange, symbol=None, start_time=None, end_time=None):
    """获取所有成交记录（自动分页）"""
    all_trades = []
    page = 1
    size = 100  # 每页最大数量
    
    while True:
        result = await exchange.get_user_trades(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            page=page,
            size=size
        )
        
        all_trades.extend(result['items'])
        
        # 如果当前页的记录数小于每页数量，说明已经是最后一页
        if len(result['items']) < size:
            break
        
        # 如果已经获取了所有记录
        if len(all_trades) >= result['total']:
            break
        
        page += 1
    
    return all_trades

# 使用示例
all_trades = await get_all_trades(exchange, symbol="btc_usdt")
print(f"总共获取 {len(all_trades)} 条成交记录")
```

### 7. 计算总手续费

```python
result = await exchange.get_user_trades(symbol="btc_usdt", size=100)

total_fee = sum(trade['fee'] for trade in result['items'])
print(f"总手续费: {total_fee}")
```

### 8. 统计 Taker/Maker 成交

```python
result = await exchange.get_user_trades(symbol="btc_usdt", size=100)

taker_count = sum(1 for trade in result['items'] if trade['takerMaker'] == 'TAKER')
maker_count = sum(1 for trade in result['items'] if trade['takerMaker'] == 'MAKER')

print(f"Taker 成交: {taker_count} 笔")
print(f"Maker 成交: {maker_count} 笔")
```

## 在 CLI 命令中使用

可以在 `watch-account` 或自定义命令中集成成交记录查询：

```python
from tri_arb.exchanges.xt_perp import XTPerpExchange
from datetime import datetime, timedelta

async def query_recent_trades(api_key: str, api_secret: str, symbol: str = None):
    """查询最近的成交记录"""
    exchange = XTPerpExchange(api_key=api_key, api_secret=api_secret)
    await exchange.connect()
    
    # 查询最近1小时的成交记录
    end_time = int(datetime.utcnow().timestamp() * 1000)
    start_time = int((datetime.utcnow() - timedelta(hours=1)).timestamp() * 1000)
    
    result = await exchange.get_user_trades(
        symbol=symbol,
        start_time=start_time,
        end_time=end_time,
        size=100
    )
    
    return result
```

## 错误处理

```python
try:
    result = await exchange.get_user_trades(symbol="btc_usdt", page=1, size=100)
except ValueError as e:
    print(f"参数错误: {e}")
except RuntimeError as e:
    print(f"连接错误: {e}")
except Exception as e:
    print(f"其他错误: {e}")
```

## 常见错误码

根据 XT API 文档，可能的错误码：

| 错误码 | 描述 |
|--------|------|
| `invalid_page` | 页面需为正整数 |
| `invalid_size` | size 最大值为 100 |
| `invalid_symbol` | 交易对不存在 |

## 注意事项

1. **时间戳格式**: `start_time` 和 `end_time` 必须是毫秒时间戳（不是秒）
2. **分页限制**: `size` 最大值为 100，超过会抛出 `ValueError`
3. **页码限制**: `page` 必须为正整数（>= 1）
4. **限流**: API 限流为 200/s/apikey，注意控制请求频率
5. **向后兼容**: `limit` 参数已废弃，建议使用 `size` 参数

## 相关文件

- `src/tri_arb/exchanges/xt_perp.py`: XT 交易所适配器实现
- [XT API 文档](https://doc.xt.com/zh-Hans/docs/futures/Order/see-transaction-details): 官方 API 文档

