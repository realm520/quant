# 币安现货和永续合约支持

本文档说明币安交易所现货和永续合约的支持情况。

## 概述

币安交易所已经实现了现货和永续合约的分离架构，与 XT 交易所保持一致：

- **BinanceSpotExchange** - 币安现货交易
- **BinancePerpExchange** - 币安永续合约

## 架构设计

### 文件结构

```
src/tri_arb/exchanges/
├── binance_spot.py      # 币安现货交易所（占位符）
├── binance_perp.py      # 币安永续合约（占位符）
├── xt_spot.py           # XT 现货交易所（完整实现）
└── xt_perp.py           # XT 永续合约（完整实现）
```

### CLI 工厂

`src/tri_arb/cli/utils/exchange_factory.py` 负责根据参数创建对应的交易所实例：

```python
def create_exchange(
    exchange_type: ExchangeType,    # spot 或 perp
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    exchange_name: ExchangeName = ExchangeName.XT  # xt 或 binance
) -> BaseExchange:
    ...
```

### 环境变量前缀

系统根据交易所名称选择环境变量，现货和永续合约共用同一个 API key：

| 交易所 | 类型 | 环境变量前缀 |
|--------|------|-------------|
| XT | 现货 / 永续合约 | `XT` |
| Binance | 现货 / 永续合约 | `BINANCE` |

**说明**：同一个 API key 可以访问现货和永续合约，只是连接不同的 API 端点。

## 使用示例

### 命令行使用

```bash
# XT 现货
cextools market ticker -x xt -e spot -s BTC/USDT

# XT 永续合约
cextools market ticker -x xt -e perp -s BTC/USDT

# 币安现货（占位符）
cextools market ticker -x binance -e spot -s BTC/USDT

# 币安永续合约（占位符）
cextools market ticker -x binance -e perp -s BTC/USDT
```

### 环境变量配置

```bash
# XT 交易所（现货和永续合约共用）
export XT_API_KEY="your_xt_api_key"
export XT_API_SECRET="your_xt_api_secret"

# 币安交易所（现货和永续合约共用）
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
```

**重要**：
- 同一个 API key 可以同时用于现货和永续合约
- 系统会根据 `--exchange-type` 参数自动选择正确的 API 端点
- 现货使用现货 API 端点，永续合约使用合约 API 端点

## 当前状态

### XT 交易所 ✅
- **现货** - 完整实现，连接真实 API
- **永续合约** - 完整实现，连接真实 API

### 币安交易所 🔄
- **现货** - 占位符实现，返回模拟数据
- **永续合约** - 占位符实现，返回模拟数据

## 占位符模式特点

### 币安现货
- 返回固定价格：Bid 50000, Ask 50010
- 不发起真实 API 调用
- 用于测试多交易所架构

### 币安永续合约
- 返回固定价格：Bid 50005, Ask 50015（略有不同以区分现货）
- 不发起真实 API 调用
- 用于测试多交易所架构

## API 端点差异

### 币安现货
- **REST API**: `https://api.binance.com`
- **WebSocket**: `wss://stream.binance.com:9443`
- **端点示例**: `/api/v3/ticker/bookTicker`

### 币安永续合约
- **REST API**: `https://fapi.binance.com`
- **WebSocket**: `wss://fstream.binance.com`
- **端点示例**: `/fapi/v1/ticker/bookTicker`

**重要**: 币安的现货和永续合约使用完全不同的 API 域名和端点！

## 实现真实 API 的步骤

### 1. 币安现货 API

```python
# src/tri_arb/exchanges/binance_spot.py

class BinanceSpotExchange(BaseExchange):
    BASE_URL = "https://api.binance.com"
    WS_URL = "wss://stream.binance.com:9443"
    
    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        # 实现币安现货 ticker API
        ...
    
    async def get_orderbook(self, trading_pair: TradingPair, depth: int) -> OrderBook:
        # 实现币安现货订单簿 API
        ...
    
    async def place_order(self, order: Order) -> Order:
        # 实现币安现货下单 API（需要签名）
        ...
```

### 2. 币安永续合约 API

```python
# src/tri_arb/exchanges/binance_perp.py

class BinancePerpExchange(BaseExchange):
    BASE_URL = "https://fapi.binance.com"
    WS_URL = "wss://fstream.binance.com"
    
    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        # 实现币安永续合约 ticker API
        ...
    
    async def get_positions(self, symbol: Optional[str]) -> list:
        # 实现币安永续合约持仓查询
        ...
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        # 实现币安永续合约杠杆设置
        ...
```

### 3. 签名认证

币安的私有 API 需要 HMAC-SHA256 签名：

```python
def _sign_request(self, params: dict) -> dict:
    """为币安 API 请求添加签名."""
    timestamp = int(time.time() * 1000)
    params['timestamp'] = timestamp
    
    query_string = urlencode(params)
    signature = hmac.new(
        self.api_secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    params['signature'] = signature
    return params
```

## 测试建议

### 单元测试

```python
# tests/exchanges/test_binance_spot.py
async def test_binance_spot_ticker():
    exchange = BinanceSpotExchange()
    await exchange.connect()
    
    pair = TradingPair(base_currency="BTC", quote_currency="USDT", ...)
    ticker = await exchange.get_ticker(pair)
    
    assert ticker.bid_price > 0
    assert ticker.ask_price > ticker.bid_price

# tests/exchanges/test_binance_perp.py
async def test_binance_perp_ticker():
    exchange = BinancePerpExchange()
    await exchange.connect()
    
    pair = TradingPair(base_currency="BTC", quote_currency="USDT", ...)
    ticker = await exchange.get_ticker(pair)
    
    assert ticker.bid_price > 0
    assert ticker.ask_price > ticker.bid_price
```

### 集成测试

```bash
# 测试币安现货
export BINANCE_API_KEY="test_key"
export BINANCE_API_SECRET="test_secret"
cextools market ticker -x binance -e spot -s BTC/USDT

# 测试币安永续合约
export BINANCE_PERP_API_KEY="test_key"
export BINANCE_PERP_API_SECRET="test_secret"
cextools market ticker -x binance -e perp -s BTC/USDT
```

## 参考资料

- [币安现货 API 文档](https://binance-docs.github.io/apidocs/spot/en/)
- [币安永续合约 API 文档](https://binance-docs.github.io/apidocs/futures/en/)
- [XT 现货实现参考](../src/tri_arb/exchanges/xt_spot.py)
- [XT 永续合约实现参考](../src/tri_arb/exchanges/xt_perp.py)
- [多交易所使用示例](multi-exchange-examples.md)
- [CEXTools 使用指南](cextools-usage.md)

## 常见问题

### Q: 为什么要分离现货和永续合约？
A: 因为现货和永续合约使用不同的 API 端点、不同的域名、不同的数据格式，分离后代码更清晰，维护更容易。

### Q: 如何切换交易所？
A: 使用 `--exchange` 或 `-x` 参数：
```bash
cextools market ticker -x xt -e spot -s BTC/USDT      # XT 现货
cextools market ticker -x binance -e spot -s BTC/USDT # 币安现货
```

### Q: 如何切换现货和永续合约？
A: 使用 `--exchange-type` 或 `-e` 参数：
```bash
cextools market ticker -x binance -e spot -s BTC/USDT  # 币安现货
cextools market ticker -x binance -e perp -s BTC/USDT  # 币安永续合约
```

### Q: 占位符模式什么时候会被替换？
A: 当实现真实的币安 API 调用后，占位符会被替换。具体时间取决于开发进度。

### Q: 如何添加其他交易所？
A: 按照同样的模式：
1. 创建 `exchange_spot.py` 和 `exchange_perp.py`
2. 在 CLI 工厂中添加支持
3. 更新环境变量前缀逻辑
4. 更新文档

## 总结

通过将币安交易所分离为现货和永续合约两个独立的类，我们实现了：

✅ **统一架构** - 与 XT 交易所保持一致的设计模式  
✅ **清晰分离** - 现货和合约逻辑完全独立  
✅ **灵活配置** - 支持独立的 API 凭证  
✅ **易于扩展** - 可以轻松添加更多交易所  
✅ **占位符模式** - 可以先测试架构，后实现真实 API  

这为未来实现真实的币安 API 集成打下了坚实的基础。

