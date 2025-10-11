# Data Model: 重命名XTExchange为XTSpotExchange

**Feature**: 007-xtexhcnage-xtspotexchange-xt
**Date**: 2025-10-11

## Overview

本特性为纯重构操作,不涉及数据模型变更。所有现有数据结构、类型定义和数据流保持不变,仅修改类名和文件名。

## Entity: XTSpotExchange (原XTExchange)

### 类定义
```python
class XTSpotExchange(BaseExchange):
    """XT Exchange adapter implementation.

    Provides async interface to XT Exchange REST API v4, conforming to
    BaseExchange protocol for triangle arbitrage trading system.
    """
```

### 属性 (保持不变)
- `name: str` - 交易所标识符 (值保持为"xt")
- `api_key: str` - XT API密钥
- `api_secret: str` - XT API密钥
- `is_connected: bool` - 连接状态标志
- `_client: httpx.AsyncClient | None` - HTTP客户端
- `_trading_pairs_cache: dict[str, TradingPair]` - 交易对缓存

### 常量 (保持不变)
- `BASE_URL: str = "https://sapi.xt.com"`
- `API_VERSION: str = "v4"`
- `RECV_WINDOW: int = 5000`
- `CACHE_KEY_PREFIX: str = "xt:trading_pair:"`

### 方法签名 (保持不变)
所有方法的签名、参数、返回值保持完全不变:
- `async def connect() -> None`
- `async def disconnect() -> None`
- `async def get_ticker(trading_pair: TradingPair | None = None) -> Price | list[Price]`
- `async def get_orderbook(trading_pair: TradingPair, depth: int = 20) -> OrderBook`
- `async def place_order(order: Order) -> Order`
- `async def cancel_order(order_id: str) -> bool`
- `async def get_order_status(order_id: str) -> Order`
- `async def get_trade_history(trading_pair: TradingPair, limit: int = 100) -> list[Trade]`
- `async def get_trading_pair_info(trading_pair: TradingPair | None = None) -> TradingPair | list[TradingPair]`
- `async def refresh_trading_pairs() -> int`

## 不变的数据结构

### TradingPair
```python
@dataclass
class TradingPair:
    base_currency: str
    quote_currency: str
    exchange: str  # 值保持为"xt"
    min_order_size: Decimal
    max_order_size: Decimal
    price_precision: int
    quantity_precision: int
    # ... 其他字段保持不变
```

### Price
```python
@dataclass
class Price:
    trading_pair: TradingPair
    bid_price: Decimal
    ask_price: Decimal
    bid_volume: Decimal
    ask_volume: Decimal
    timestamp: datetime
    exchange: str  # 值保持为"xt"
```

### Order, OrderBook, Trade
所有其他数据模型保持完全不变,不受重命名影响。

## 类型注解变更

### 需要更新的类型引用
```python
# 旧的类型注解
exchange: XTExchange
exchanges: list[XTExchange]
factory_result: XTExchange | None

# 新的类型注解
exchange: XTSpotExchange
exchanges: list[XTSpotExchange]
factory_result: XTSpotExchange | None
```

### 文件路径
- `src/tri_arb/exchanges/xt.py` → `src/tri_arb/exchanges/xt_spot.py`

## 数据流 (保持不变)

```
外部API请求 → XTSpotExchange._request() → HTTP响应
                     ↓
            _parse_ticker_to_price()
                     ↓
              Price对象 → 返回给调用者
```

所有数据流、转换逻辑、验证规则保持不变。

## 验证规则 (保持不变)

- 输入验证: 现有的参数验证逻辑不变
- 类型安全: 所有类型注解保持,仅类名更新
- 异常处理: 所有异常处理逻辑不变

## Summary

**变更内容**: 仅类名和文件名
**不变内容**: 所有属性、方法、数据结构、业务逻辑、数据流、验证规则

这是一个完全的重构操作,对数据模型的影响仅限于命名,无任何功能性或结构性变更。
