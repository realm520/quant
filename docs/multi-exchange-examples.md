# 多交易所支持示例

本文档展示如何使用 cextools 的多交易所支持功能。

## 基本用法

### 查询不同交易所的价格

```bash
# XT 交易所永续合约（默认）
cextools market ticker -s BTC/USDT

# 显式指定 XT 交易所永续合约
cextools market ticker --exchange xt -s BTC/USDT

# 币安交易所永续合约（占位符模式）
cextools market ticker --exchange binance -s BTC/USDT

# 查询现货需要显式指定
cextools market ticker -x binance -e spot -s ETH/USDT
```

## 支持的交易所

| 交易所 | 标识符 | 现货 | 永续合约 | 状态 |
|--------|--------|------|----------|------|
| XT | `xt` | ✅ | ✅ | 完整实现 |
| Binance | `binance` | 🔄 | 🔄 | 占位符 |

**说明**：
- ✅ **完整实现**：连接真实 API，可正常交易
- 🔄 **占位符**：返回模拟数据，用于测试架构

## 环境变量配置

### XT 交易所
```bash
# XT 现货和永续合约共用同一个 API key
export XT_API_KEY="your_xt_api_key"
export XT_API_SECRET="your_xt_api_secret"
```

### Binance 交易所
```bash
# 币安现货和永续合约共用同一个 API key
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
```

**重要说明**：现货和永续合约使用相同的 API key，只是连接不同的 API 端点。

## 常见使用场景

### 1. 对比不同交易所的价格

```bash
#!/bin/bash
# compare_prices.sh

echo "=== BTC/USDT 价格对比 ==="
echo ""

echo "XT 交易所:"
cextools market ticker -x xt -e spot -s BTC/USDT

echo ""
echo "币安交易所 (占位符):"
cextools market ticker -x binance -e spot -s BTC/USDT
```

### 2. 查询多个交易所的余额

```bash
#!/bin/bash
# check_balances.sh

echo "=== 账户余额对比 ==="
echo ""

echo "XT 现货余额:"
cextools account balance -x xt -e spot -o table

echo ""
echo "币安现货余额 (占位符):"
cextools account balance -x binance -e spot -o table

echo ""
echo "XT 永续合约余额:"
cextools account balance -x xt -e perp -o table

echo ""
echo "币安永续合约余额 (占位符):"
cextools account balance -x binance -e perp -o table
```

### 3. JSON 格式输出用于数据分析

```bash
# 导出 XT 交易所数据
cextools market ticker -x xt -e spot -s BTC/USDT -o json > xt_btc.json
cextools market ticker -x xt -e spot -s ETH/USDT -o json > xt_eth.json

# 导出币安交易所数据（占位符）
cextools market ticker -x binance -e spot -s BTC/USDT -o json > binance_btc.json

# 使用 jq 处理 JSON 数据
cat xt_btc.json | jq '.bid_price'
cat binance_btc.json | jq '.mid_price'
```

### 4. 循环查询多个交易所（现货和永续合约）

```bash
#!/bin/bash
# monitor_exchanges.sh

SYMBOLS=("BTC/USDT" "ETH/USDT" "BNB/USDT")
EXCHANGES=("xt" "binance")
TYPES=("spot" "perp")

for exchange in "${EXCHANGES[@]}"; do
    echo "=== $exchange 交易所 ==="
    for type in "${TYPES[@]}"; do
        echo "  [$type]"
        for symbol in "${SYMBOLS[@]}"; do
            echo "    $symbol:"
            cextools market ticker -x "$exchange" -e "$type" -s "$symbol" -o json | jq -r '.mid_price'
        done
    done
    echo ""
done
```

## 占位符模式说明

当前币安交易所（现货和永续合约）都处于占位符模式，这意味着：

1. **返回固定数据**：所有查询返回预设的模拟数据
2. **不发起真实 API 调用**：不会连接到币安服务器
3. **用于测试和开发**：可以测试多交易所架构

### 占位符数据示例

#### 币安现货（Binance Spot）
```bash
$ cextools market ticker -x binance -e spot -s BTC/USDT

# 输出（模拟数据）:
┌─────────────────┬──────────────────┐
│ Field           │ Value            │
├─────────────────┼──────────────────┤
│ Exchange        │ BINANCE_SPOT     │
│ Symbol          │ BTC/USDT         │
│ Bid Price       │ 50000.00000000   │
│ Ask Price       │ 50010.00000000   │
│ Mid Price       │ 50005.00000000   │
│ Spread          │ 10.00000000      │
│ Spread %        │ 0.0200%          │
└─────────────────┴──────────────────┘
```

#### 币安永续合约（Binance Perp）
```bash
$ cextools market ticker -x binance -e perp -s BTC/USDT

# 输出（模拟数据）:
┌─────────────────┬──────────────────┐
│ Field           │ Value            │
├─────────────────┼──────────────────┤
│ Exchange        │ BINANCE_PERP     │
│ Symbol          │ BTC/USDT         │
│ Bid Price       │ 50005.00000000   │
│ Ask Price       │ 50015.00000000   │
│ Mid Price       │ 50010.00000000   │
│ Spread          │ 10.00000000      │
│ Spread %        │ 0.0200%          │
└─────────────────┴──────────────────┘
```

**注意**：永续合约的价格略有不同（50005/50015），以区别于现货价格。

## 实现真实币安集成

要将币安从占位符模式升级到完整实现，需要分别实现现货和永续合约：

### 1. 实现币安现货 REST API
```python
# src/tri_arb/exchanges/binance_spot.py

class BinanceSpotExchange(BaseExchange):
    BASE_URL = "https://api.binance.com"
    
    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        # 调用币安现货 REST API
        url = f"{self.BASE_URL}/api/v3/ticker/bookTicker"
        params = {"symbol": f"{trading_pair.base_currency}{trading_pair.quote_currency}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
        
        # 转换为统一的 Price 对象
        return Price(
            trading_pair=trading_pair,
            bid_price=Decimal(data['bidPrice']),
            ask_price=Decimal(data['askPrice']),
            bid_volume=Decimal(data['bidQty']),
            ask_volume=Decimal(data['askQty']),
            ...
        )
```

### 1b. 实现币安永续合约 REST API
```python
# src/tri_arb/exchanges/binance_perp.py

class BinancePerpExchange(BaseExchange):
    BASE_URL = "https://fapi.binance.com"  # 注意：永续合约使用不同的域名
    
    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        # 调用币安永续合约 REST API
        url = f"{self.BASE_URL}/fapi/v1/ticker/bookTicker"
        params = {"symbol": f"{trading_pair.base_currency}{trading_pair.quote_currency}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            data = response.json()
        
        # 转换为统一的 Price 对象
        return Price(...)
```

### 2. 实现 WebSocket 连接

#### 现货 WebSocket
```python
# src/tri_arb/exchanges/binance_spot.py
async def subscribe_ticker(self, trading_pair: TradingPair):
    symbol = f"{trading_pair.base_currency}{trading_pair.quote_currency}".lower()
    uri = f"wss://stream.binance.com:9443/ws/{symbol}@bookTicker"
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            yield self._parse_ticker(data)
```

#### 永续合约 WebSocket
```python
# src/tri_arb/exchanges/binance_perp.py
async def subscribe_ticker(self, trading_pair: TradingPair):
    symbol = f"{trading_pair.base_currency}{trading_pair.quote_currency}".lower()
    uri = f"wss://fstream.binance.com/ws/{symbol}@bookTicker"  # 注意：不同的域名
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            yield self._parse_ticker(data)
```

### 3. 添加签名认证
```python
def _sign_request(self, params: dict) -> dict:
    query_string = urlencode(params)
    signature = hmac.new(
        self.api_secret.encode(),
        query_string.encode(),
        hashlib.sha256
    ).hexdigest()
    params["signature"] = signature
    return params
```

### 4. 注册到工厂
代码已在 `src/tri_arb/exchanges/factory.py` 中完成：
```python
exchange_factory.register("binance", BinanceExchange)
```

## 添加新的交易所

要添加其他交易所（如 OKX、Bybit 等），按以下步骤：

1. **创建交易所适配器**
```python
# src/tri_arb/exchanges/okx.py
class OKXExchange(BaseExchange):
    async def connect(self): ...
    async def get_ticker(self, trading_pair): ...
    # 实现其他必需方法
```

2. **注册到工厂**
```python
# src/tri_arb/exchanges/factory.py
from tri_arb.exchanges.okx import OKXExchange

exchange_factory.register("okx", OKXExchange)
```

3. **更新 CLI 枚举**
```python
# src/tri_arb/cli/utils/exchange_factory.py
class ExchangeName(str, Enum):
    XT = "xt"
    BINANCE = "binance"
    OKX = "okx"  # 添加新交易所
```

4. **更新文档**
在 `docs/cextools-usage.md` 中添加新交易所的说明。

## 参考资料

- [XT API 文档](https://doc.xt.com)
- [Binance API 文档](https://binance-docs.github.io/apidocs/)
- [项目架构文档](architecture.md)
- [CEXTools 使用指南](cextools-usage.md)

