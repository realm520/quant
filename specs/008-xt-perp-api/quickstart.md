# XTPerpExchange 快速入门指南

本指南帮助你快速开始使用 XTPerpExchange 进行 XT 永续合约交易。

## 前置条件

- Python 3.11+
- XT 交易所永续合约账户
- API Key 和 API Secret（需要开启合约交易权限）

## 安装

```bash
# 克隆项目
git clone <repository-url>
cd tri-arb

# 使用 uv 设置环境
uv venv --python 3.11
source .venv/bin/activate

# 安装依赖
uv pip install -e ".[dev]"
```

## 环境配置

创建 `.env` 文件并配置 API 凭证：

```bash
# XT 永续合约 API 凭证
XT_PERP_API_KEY=your_api_key_here
XT_PERP_API_SECRET=your_api_secret_here

# 可选：日志级别
LOG_LEVEL=INFO
```

⚠️ **安全提示**：
- 永远不要将 API 密钥提交到版本控制系统
- 使用只读或交易权限的 API Key，避免使用提现权限
- 建议先在测试网练习

## 基础使用

### 1. 创建交易所实例并连接

```python
import asyncio
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.config import load_config

async def main():
    # 加载配置
    config = load_config()
    
    # 创建交易所实例
    exchange = XTPerpExchange(
        api_key=config.xt_perp_api_key,
        api_secret=config.xt_perp_api_secret
    )
    
    # 连接交易所（加载交易对信息、资金费率等）
    await exchange.connect()
    
    try:
        # 这里执行交易操作
        print("✅ 连接成功")
    finally:
        # 断开连接
        await exchange.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. 获取市场数据

```python
# 获取最新价格
ticker = await exchange.get_ticker("BTC/USDT")
print(f"BTC/USDT 最新价: {ticker.last_price}")
print(f"24h 涨跌幅: {ticker.change_24h}%")

# 获取订单簿
orderbook = await exchange.get_orderbook("BTC/USDT", depth=10)
print(f"最佳买价: {orderbook.bids[0].price}")
print(f"最佳卖价: {orderbook.asks[0].price}")

# 获取资金费率
funding_rate = await exchange.get_funding_rate("BTC/USDT")
print(f"当前资金费率: {funding_rate.rate * 100:.4f}%")
print(f"下次结算时间: {funding_rate.next_funding_time}")
```

### 3. 查询账户信息

```python
# 获取账户余额
balance = await exchange.get_balance()
print(f"USDT 可用余额: {balance.available['USDT']}")
print(f"USDT 冻结余额: {balance.frozen['USDT']}")

# 获取当前持仓
positions = await exchange.get_positions()
for position in positions:
    print(f"交易对: {position.symbol}")
    print(f"持仓方向: {position.side}")
    print(f"持仓数量: {position.quantity}")
    print(f"未实现盈亏: {position.unrealized_pnl}")
    print(f"杠杆倍数: {position.leverage}x")
```

### 4. 下单交易

#### 开仓做多（市价单）

```python
from decimal import Decimal

# 开多仓：买入 BTC，方向为 LONG
order = await exchange.place_order(
    symbol="BTC/USDT",
    side="BUY",
    order_type="MARKET",
    quantity=Decimal("0.01"),
    position_side="LONG"  # 永续合约特有参数
)

print(f"订单ID: {order.id}")
print(f"订单状态: {order.status}")
print(f"成交数量: {order.filled_quantity}")
print(f"成交均价: {order.average_price}")
```

#### 开仓做空（限价单）

```python
# 开空仓：卖出 BTC，方向为 SHORT
order = await exchange.place_order(
    symbol="BTC/USDT",
    side="SELL",
    order_type="LIMIT",
    quantity=Decimal("0.01"),
    price=Decimal("45000"),  # 限价
    position_side="SHORT",
    time_in_force="GTC"  # Good Till Cancel
)
```

#### 平仓

```python
# 平多仓：卖出 BTC，针对 LONG 仓位
close_order = await exchange.place_order(
    symbol="BTC/USDT",
    side="SELL",
    order_type="MARKET",
    quantity=Decimal("0.01"),
    position_side="LONG"  # 指定平多仓
)

# 平空仓：买入 BTC，针对 SHORT 仓位
close_order = await exchange.place_order(
    symbol="BTC/USDT",
    side="BUY",
    order_type="MARKET",
    quantity=Decimal("0.01"),
    position_side="SHORT"  # 指定平空仓
)
```

### 5. 订单管理

```python
# 查询订单详情
order_detail = await exchange.get_order("BTC/USDT", order_id="12345")
print(f"订单状态: {order_detail.status}")

# 取消订单
success = await exchange.cancel_order("BTC/USDT", order_id="12345")
print(f"取消成功: {success}")

# 批量取消订单
cancel_results = await exchange.cancel_all_orders("BTC/USDT")
print(f"取消了 {len(cancel_results)} 个订单")
```

### 6. 杠杆和仓位模式

```python
# 调整杠杆倍数
await exchange.set_leverage("BTC/USDT", leverage=10)
print("✅ 杠杆已调整为 10x")

# 查询当前杠杆
trading_pair = await exchange.get_trading_pair_info("BTC/USDT")
print(f"当前杠杆: {trading_pair.leverage}x")
```

## 完整示例：简单做多策略

```python
import asyncio
from decimal import Decimal
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.config import load_config

async def simple_long_strategy():
    """简单做多策略示例"""
    config = load_config()
    exchange = XTPerpExchange(
        api_key=config.xt_perp_api_key,
        api_secret=config.xt_perp_api_secret
    )
    
    await exchange.connect()
    
    try:
        symbol = "BTC/USDT"
        
        # 1. 获取当前价格
        ticker = await exchange.get_ticker(symbol)
        current_price = ticker.last_price
        print(f"📊 当前价格: {current_price}")
        
        # 2. 检查账户余额
        balance = await exchange.get_balance()
        available_usdt = balance.available["USDT"]
        print(f"💰 可用余额: {available_usdt} USDT")
        
        if available_usdt < Decimal("100"):
            print("❌ 余额不足 100 USDT")
            return
        
        # 3. 设置杠杆
        await exchange.set_leverage(symbol, leverage=5)
        print("⚙️  杠杆设置为 5x")
        
        # 4. 开多仓（市价单）
        quantity = Decimal("0.01")  # 0.01 BTC
        open_order = await exchange.place_order(
            symbol=symbol,
            side="BUY",
            order_type="MARKET",
            quantity=quantity,
            position_side="LONG"
        )
        print(f"✅ 开仓成功: {open_order.id}")
        print(f"   成交价: {open_order.average_price}")
        print(f"   成交量: {open_order.filled_quantity}")
        
        # 5. 设置止盈止损（示例：止盈 +5%, 止损 -2%）
        entry_price = open_order.average_price
        take_profit_price = entry_price * Decimal("1.05")
        stop_loss_price = entry_price * Decimal("0.98")
        
        # 止盈单
        tp_order = await exchange.place_order(
            symbol=symbol,
            side="SELL",
            order_type="LIMIT",
            quantity=quantity,
            price=take_profit_price,
            position_side="LONG"
        )
        print(f"🎯 止盈单: {take_profit_price}")
        
        # 止损单（使用计划委托）
        # 注意：止损单需要使用专门的 API，这里仅作示例
        print(f"🛑 止损价: {stop_loss_price}")
        
        # 6. 监控持仓
        print("\n📈 持仓信息:")
        positions = await exchange.get_positions()
        for pos in positions:
            if pos.symbol == symbol and pos.side == "LONG":
                print(f"   持仓量: {pos.quantity}")
                print(f"   开仓价: {pos.entry_price}")
                print(f"   未实现盈亏: {pos.unrealized_pnl}")
                print(f"   收益率: {pos.roe}%")
        
    finally:
        await exchange.disconnect()

if __name__ == "__main__":
    asyncio.run(simple_long_strategy())
```

## 测试验证

### 运行合约测试

```bash
# 运行所有合约测试（测试 BaseExchange 接口实现）
uv run pytest tests/unit/test_exchanges/test_xt_perp_contract.py -v

# 运行集成测试（需要真实 API 凭证）
export XT_PERP_API_KEY=your_key
export XT_PERP_API_SECRET=your_secret
uv run pytest tests/integration/test_xt_perp_integration.py --run-integration -v
```

### 使用 Mock 模式测试

```python
import asyncio
from tri_arb.exchanges.xt_perp import XTPerpExchange

async def test_with_mock():
    """使用模拟模式测试（不需要真实 API）"""
    exchange = XTPerpExchange(
        api_key="test_key",
        api_secret="test_secret",
        use_mock=True  # 启用模拟模式
    )
    
    await exchange.connect()
    
    # 模拟模式下的操作不会发送真实请求
    ticker = await exchange.get_ticker("BTC/USDT")
    print(f"模拟价格: {ticker.last_price}")
    
    await exchange.disconnect()

asyncio.run(test_with_mock())
```

## 错误处理

```python
from tri_arb.exceptions import (
    ExchangeError,
    InsufficientBalanceError,
    OrderNotFoundError,
    NetworkError
)

async def safe_trading_example():
    exchange = XTPerpExchange(api_key="...", api_secret="...")
    await exchange.connect()
    
    try:
        # 下单
        order = await exchange.place_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("0.01"),
            position_side="LONG"
        )
    except InsufficientBalanceError:
        print("❌ 余额不足")
    except NetworkError as e:
        print(f"🌐 网络错误: {e}")
    except ExchangeError as e:
        print(f"⚠️  交易所错误: {e}")
    finally:
        await exchange.disconnect()
```

## 性能优化建议

1. **复用连接**：使用同一个 `XTPerpExchange` 实例处理多个请求
2. **批量操作**：使用 `cancel_all_orders()` 而不是逐个取消
3. **缓存交易对信息**：`connect()` 会自动缓存，避免重复调用 `get_trading_pair_info()`
4. **合理使用 WebSocket**：频繁获取价格时，考虑使用 WebSocket 订阅（未来支持）

## 常见问题

### Q: 如何区分开仓和平仓？
A: 通过 `position_side` 和 `side` 组合判断：
- 开多：`BUY + LONG`
- 平多：`SELL + LONG`
- 开空：`SELL + SHORT`
- 平空：`BUY + SHORT`

### Q: 资金费率是什么？
A: 永续合约每 8 小时结算一次的费用，用于锚定合约价格到现货价格。正费率时多头支付，负费率时空头支付。

### Q: 如何设置止盈止损？
A: 有两种方式：
1. 使用限价单设置目标价位
2. 使用计划委托（触发条件单）在特定价格自动触发

### Q: 杠杆倍数如何选择？
A: 根据风险承受能力：
- 新手：1-3x（低风险）
- 有经验：5-10x（中等风险）
- 专业：10x+（高风险，不建议）

## 下一步

- 阅读 [data-model.md](./data-model.md) 了解完整数据模型
- 查看 [contracts/](./contracts/) 了解 API 端点详情
- 运行 [research.md](./research.md) 中的性能测试
- 实现自己的交易策略

## 安全提醒

⚠️ **风险警告**：
- 永续合约是高风险金融衍生品
- 杠杆会放大盈亏，可能导致爆仓
- 请确保充分理解风险后再进行实盘交易
- 建议从小额资金和低杠杆开始
- 永远不要投入超过你能承受损失的资金

---

**需要帮助？** 
- 查看项目文档：`docs/`
- 提交 Issue：[GitHub Issues]
- 参考 XT 官方文档：https://doc.xt.com
