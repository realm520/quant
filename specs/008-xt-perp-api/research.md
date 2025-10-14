# Research: XT永续合约API集成

**Feature**: 008-xt-perp-api | **Date**: 2025-10-11 | **Phase**: 0

## Research Objectives

基于功能规格说明，本研究旨在解决以下技术决策和未知因素：

1. XT永续合约API的签名机制和端点规范
2. 永续合约特定数据模型与现有BaseExchange框架的适配方案
3. 仓位管理、杠杆调整、资金费率等永续合约特有功能的实现策略
4. 性能优化方案以满足<50ms p95订单提交要求

## Key Technical Decisions

### 1. API基础架构

**Decision**: 基于xt_perp_api.py的签名逻辑，创建XTPerpExchange类继承BaseExchange

**Rationale**:
- xt_perp_api.py已经实现了完整的HMAC-SHA256签名逻辑
- 包含了永续合约API的所有端点定义和参数格式
- 签名生成函数`_create_sign()`可直接复用
- API基础URL固定为`https://fapi.xt.com`（永续合约端点）

**Implementation Strategy**:
```python
# 签名方式（来自xt_perp_api.py line 17-46）
# 对于application/x-www-form-urlencoded:
signkey = f"xt-validate-appkey={apikey}&xt-validate-timestamp={timestamp}#{path}#{message}"

# 对于application/json:
signkey = f"xt-validate-appkey={apikey}&xt-validate-timestamp={timestamp}#{path}#{message}"

# HMAC-SHA256签名
sign = hmac.new(secret.encode("utf-8"), signkey.encode("utf-8"), digestmod=hashlib.sha256).hexdigest()
```

**Alternatives Considered**:
- 完全重新实现签名逻辑：拒绝，因为xt_perp_api.py已验证可用
- 直接使用xt_perp_api.py的Perp类：拒绝，不符合BaseExchange接口规范

### 2. 永续合约特有数据模型

**Decision**: 扩展TradingPair模型，新增永续合约特定字段；创建独立的Position和LeverageBracket模型

**Rationale**:
- TradingPair需要支持杠杆档位信息（leverage_brackets字段）
- 仓位管理需要专门的Position数据模型
- 资金费率、标记价格等概念需要新的数据结构

**Data Model Extensions**:
```python
# TradingPair扩展（用于永续合约）
@dataclass
class TradingPair:
    # ... 现有字段 ...

    # 永续合约特定字段
    leverage_brackets: list[LeverageBracket] | None = None  # 杠杆档位
    contract_size: Decimal | None = None  # 合约面值
    funding_rate: Decimal | None = None  # 当前资金费率

# 新增数据模型
@dataclass
class Position:
    trading_pair: TradingPair
    position_side: Literal["LONG", "SHORT"]  # 仓位方向
    quantity: Decimal  # 持仓数量
    entry_price: Decimal  # 开仓均价
    mark_price: Decimal  # 当前标记价格
    unrealized_pnl: Decimal  # 未实现盈亏
    margin: Decimal  # 已用保证金
    leverage: int  # 杠杆倍数
    liquidation_price: Decimal  # 强平价格
    margin_mode: Literal["ISOLATED", "CROSS"]  # 保证金模式

@dataclass
class LeverageBracket:
    max_leverage: int  # 最大杠杆倍数
    max_notional: Decimal  # 最大名义价值
    maintenance_margin_rate: Decimal  # 维持保证金率
```

**Alternatives Considered**:
- 创建完全独立的PerpetualTradingPair类：拒绝，增加复杂度且不利于代码复用
- 不扩展TradingPair，在adapter内部维护：拒绝，违背统一数据模型原则

### 3. BaseExchange接口适配

**Decision**: XTPerpExchange实现BaseExchange所有抽象方法，扩展永续合约特定方法

**Rationale**:
- 保持与现货交易所的接口一致性
- 永续合约特定功能作为扩展方法，不破坏接口约定
- Order模型需要新增position_side字段以支持开平仓方向

**Method Mapping**:
```python
# BaseExchange必须实现的方法（复用现货逻辑）
async def get_ticker(trading_pair) -> Price  # 使用/future/market/v1/public/q/ticker
async def get_orderbook(trading_pair, depth) -> OrderBook  # 使用/future/market/v1/public/q/depth
async def place_order(order) -> Order  # 使用/future/trade/v1/order/create，需传positionSide
async def cancel_order(order_id) -> bool  # 使用/future/trade/v1/order/cancel
async def get_order_status(order_id) -> Order  # 使用/future/trade/v1/order/detail
async def get_trade_history(trading_pair, limit) -> list[Trade]  # 使用/future/trade/v1/order/trade-list

# 永续合约扩展方法（新增）
async def get_position(symbol) -> list[Position]  # /future/user/v1/position/list
async def get_balance() -> dict  # /future/user/v1/balance/list
async def adjust_leverage(symbol, leverage, position_side) -> bool  # /future/user/v1/position/adjust-leverage
async def get_funding_rate(symbol) -> FundingRate  # /future/market/v1/public/q/funding-rate
async def get_mark_price(symbol) -> Decimal  # /future/market/v1/public/q/symbol-mark-price
async def create_plan_order(params) -> str  # /future/trade/v1/entrust/create-plan
async def create_stop_profit_loss(params) -> str  # /future/trade/v1/entrust/create-profit
async def close_all_positions() -> bool  # /future/user/v1/position/close-all
```

**Alternatives Considered**:
- 创建独立的PerpetualExchange基类：拒绝，破坏框架统一性
- 使用策略模式而非继承：拒绝，增加复杂度且不利于类型检查

### 4. 订单模型扩展

**Decision**: 在Order模型中新增position_side字段，用于区分开多/开空/平多/平空

**Rationale**:
- 永续合约的orderSide（BUY/SELL）和positionSide（LONG/SHORT）是两个维度
- BUY + LONG = 开多，SELL + SHORT = 开空
- BUY + SHORT = 平空，SELL + LONG = 平多
- 需要同时传递两个参数才能明确交易意图

**Order Model Extension**:
```python
@dataclass
class Order:
    # ... 现有字段 ...

    # 永续合约特定字段
    position_side: Literal["LONG", "SHORT"] | None = None  # 仓位方向（永续合约必填）

    # 派生字段（根据side和position_side计算）
    @property
    def trade_action(self) -> str:
        """返回交易动作：OPEN_LONG, OPEN_SHORT, CLOSE_LONG, CLOSE_SHORT"""
        if not self.position_side:
            return "SPOT"  # 现货交易

        if self.side == OrderSide.BUY and self.position_side == "LONG":
            return "OPEN_LONG"
        elif self.side == OrderSide.SELL and self.position_side == "SHORT":
            return "OPEN_SHORT"
        elif self.side == OrderSide.BUY and self.position_side == "SHORT":
            return "CLOSE_SHORT"
        else:  # SELL + LONG
            return "CLOSE_LONG"
```

**Alternatives Considered**:
- 创建独立的PerpetualOrder类：拒绝，增加类型系统复杂度
- 使用字符串枚举组合（如"BUY_LONG"）：拒绝，不符合XT API参数格式

### 5. 性能优化策略

**Decision**: 使用连接池、批量查询、缓存配置信息以满足<50ms p95订单提交要求

**Rationale**:
- 订单提交是关键路径，必须优化到极致
- 配置信息（杠杆档位、精度）变化频率低，适合缓存
- 批量查询可减少网络往返次数

**Optimization Techniques**:
```python
# 1. HTTP连接池复用（httpx配置）
self._client = httpx.AsyncClient(
    base_url="https://fapi.xt.com",
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(
        max_connections=100,  # 最大连接数
        max_keepalive_connections=20  # 保持连接数
    ),
)

# 2. 配置信息缓存（connect时加载）
self._symbol_config_cache: dict[str, TradingPair] = {}

async def connect(self):
    # 一次性加载所有合约配置
    symbols = await self._fetch_all_symbols()
    for symbol in symbols:
        self._symbol_config_cache[symbol.trading_pair.base_quote] = symbol

# 3. 批量查询优化
async def get_ticker(trading_pair: TradingPair | None = None) -> Price | list[Price]:
    if trading_pair is None:
        # 批量查询所有市场
        return await self._fetch("/future/market/v1/public/q/tickers")
    else:
        # 单个查询
        return await self._fetch(f"/future/market/v1/public/q/ticker?symbol={symbol}")

# 4. 签名生成优化（预计算常量）
def _generate_signature(self, method, path, query, body):
    # 时间戳只在调用时生成，避免提前计算导致过期
    timestamp_ms = int(time.time() * 1000)

    # 签名串拼接（最小化字符串操作）
    sig_data = f"xt-validate-appkey={self.api_key}&xt-validate-timestamp={timestamp_ms}#{method}#{path}"
    if query:
        sig_data += f"#{query}"
    if body:
        sig_data += f"#{body}"

    # HMAC-SHA256签名
    return hmac.new(
        self.api_secret.encode("utf-8"),
        sig_data.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
```

**Performance Targets**:
- 订单提交：<50ms p95（从调用到API请求发出）
- 价格查询：<10ms p95（解析响应到Price对象）
- 连接池命中率：>95%
- 配置缓存命中率：>99%

**Alternatives Considered**:
- 使用内存数据库（如Redis）缓存：拒绝，增加系统复杂度且引入外部依赖
- WebSocket实时推送：保留，作为后续优化方向

### 6. 错误处理和重试策略

**Decision**: 使用tenacity库实现指数退避重试，针对不同错误类型采取不同策略

**Rationale**:
- 网络临时性错误需要重试，但认证错误不应重试
- 指数退避避免对交易所API造成压力
- 记录详细的错误上下文以便事后分析

**Retry Configuration**:
```python
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

@retry(
    stop=stop_after_attempt(3),  # 最多重试3次
    wait=wait_exponential(multiplier=1, min=1, max=10),  # 指数退避：1s, 2s, 4s
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
)
async def _request(self, method, path, params, json_data, authenticated):
    # ... HTTP请求逻辑 ...
    pass

# 错误分类处理
def _handle_api_error(self, error_code, error_message):
    if error_code == "AUTH_FAILED":
        raise ValueError("API认证失败，请检查密钥配置")
    elif error_code == "INSUFFICIENT_BALANCE":
        raise ValueError("保证金不足，无法开仓")
    elif error_code == "RATE_LIMIT":
        raise ValueError("API限流，请降低请求频率")
    else:
        raise ValueError(f"XT API错误: {error_code} - {error_message}")
```

**Alternatives Considered**:
- 无限重试：拒绝，可能导致系统hang住
- 不区分错误类型：拒绝，浪费资源重试无法恢复的错误

### 7. 测试策略

**Decision**: TDD严格执行，合约测试优先，集成测试覆盖完整交易流程

**Rationale**:
- 合约测试确保与XT API的接口兼容性
- 集成测试验证多步骤交易流程（开仓→调整杠杆→平仓）
- 性能测试确保满足<50ms p95要求

**Testing Layers**:
```python
# 1. 合约测试（tests/unit/test_exchanges/test_xt_perp_contract.py）
def test_xt_perp_implements_base_exchange():
    """验证XTPerpExchange实现了BaseExchange所有抽象方法"""
    assert issubclass(XTPerpExchange, BaseExchange)
    # 验证所有抽象方法都有实现

def test_order_model_has_position_side():
    """验证Order模型包含position_side字段"""
    order = Order(position_side="LONG", ...)
    assert order.position_side == "LONG"

# 2. API签名测试（tests/unit/test_exchanges/test_xt_perp_signature.py）
def test_signature_generation_for_get_request():
    """验证GET请求的签名生成符合XT API规范"""
    signature = _generate_signature("GET", "/future/market/v1/public/q/ticker", ...)
    # 与xt_perp_api.py的结果对比

# 3. 集成测试（tests/integration/test_xt_perp_integration.py）
@pytest.mark.integration
async def test_complete_trading_workflow():
    """测试完整的交易流程：开仓→调整杠杆→平仓"""
    exchange = XTPerpExchange(api_key=..., api_secret=...)
    await exchange.connect()

    # 开多仓
    order = await exchange.place_order(Order(
        trading_pair=btc_usdt,
        side=OrderSide.BUY,
        position_side="LONG",
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01")
    ))
    assert order.status == OrderStatus.FILLED

    # 调整杠杆
    success = await exchange.adjust_leverage("btc_usdt", leverage=5, position_side="LONG")
    assert success

    # 平仓
    close_order = await exchange.place_order(Order(
        trading_pair=btc_usdt,
        side=OrderSide.SELL,
        position_side="LONG",
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01")
    ))
    assert close_order.status == OrderStatus.FILLED

# 4. 性能测试（tests/performance/test_xt_perp_performance.py）
@pytest.mark.benchmark
async def test_order_submission_latency(benchmark):
    """验证订单提交延迟<50ms p95"""
    result = benchmark(lambda: asyncio.run(exchange.place_order(order)))
    assert result.stats.percentile(95) < 0.050  # 50ms
```

**Alternatives Considered**:
- 跳过合约测试直接集成测试：拒绝，无法保证接口兼容性
- 使用mock对象而非真实API：部分采用，单元测试用mock，集成测试用真实API

## Implementation Checklist

### Phase 0 完成标准
- [x] 所有技术决策已记录并有明确理由
- [x] API端点和参数格式已从xt_perp_api.py提取
- [x] 数据模型扩展方案已设计
- [x] 性能优化策略已规划
- [x] 测试策略已制定

### 下一步（Phase 1）
1. 编写data-model.md，详细定义所有数据模型（Position, LeverageBracket等）
2. 生成OpenAPI contracts，定义所有API端点的请求/响应格式
3. 编写失败的合约测试（tests/unit/test_exchanges/test_xt_perp_contract.py）
4. 编写quickstart.md，提供快速上手指南

## References

- xt_perp_api.py: 永续合约API实现参考
- src/tri_arb/exchanges/xt_spot.py: 现货交易所实现参考
- src/tri_arb/exchanges/base.py: BaseExchange接口定义
- src/tri_arb/core/models.py: 核心数据模型定义
- specs/002-xt-spot-api/: 现货API集成文档

---
**Status**: Phase 0 Complete ✓ | **Next**: Phase 1 - Design & Contracts
