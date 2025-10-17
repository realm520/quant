# 下单功能完整指南

## 🎯 功能概述

已为 **Binance** 和 **OKX** 永续合约实现完整的下单功能，支持限价单、市价单、Post-only等多种订单类型。

## ✅ 已实现功能

| 交易所 | 限价单 | 市价单 | Post-only | 止损单 | 止盈单 |
|--------|-------|--------|-----------|--------|--------|
| Binance | ✅ | ✅ | ✅ | ✅ | ✅ |
| OKX | ✅ | ✅ | ✅ | ⏳ | ⏳ |

## 🚀 CLI使用方法

### Binance 下单

```bash
# 限价开多单
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

# 限价开空单
cextools order place -x binance -e perp -s BTC/USDT --side sell -q 0.001 -p 70000 --position-side SHORT

# 市价开多单（⚠️会立即成交）
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 --type market --position-side LONG

# 市价平多单（仅减仓）
cextools order place -x binance -e perp -s BTC/USDT --side sell -q 0.001 --type market --position-side LONG
```

### OKX 下单

```bash
# 限价开多单
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

# 限价开空单
cextools order place -x okx -e perp -s ETH/USDT --side sell -q 0.01 -p 5000 --position-side SHORT

# Post-only订单（只做Maker，不会立即成交）
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --type post_only --position-side LONG

# 市价开多单（⚠️会立即成交）
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 --type market --position-side LONG
```

## 📖 参数说明

### 必需参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `-x, --exchange` | 交易所 | `binance`, `okx` |
| `-e, --exchange-type` | 交易类型 | `perp` (永续合约) |
| `-s, --symbol` | 交易对 | `BTC/USDT` |
| `--side` | 方向 | `buy` (买入/做多), `sell` (卖出/做空) |
| `-q, --quantity` | 数量 | `0.001` |
| `--position-side` | 持仓方向 | `LONG` (多仓), `SHORT` (空仓) |

### 可选参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `-t, --type` | 订单类型 | `limit` | `limit`, `market`, `post_only` |
| `-p, --price` | 价格 | - | `50000` (限价单必需) |
| `-o, --output` | 输出格式 | `table` | `table`, `json`, `csv` |
| `--debug` | 调试模式 | false | - |

## 🔍 订单类型详解

### 1. 限价单 (LIMIT)

**特点**：
- 需要指定价格
- 不会立即成交（除非价格达到市价）
- 可能部分成交或完全不成交

**使用场景**：
- 想以指定价格买入/卖出
- 不着急成交
- 避免滑点

**示例**：
```bash
# 在30000价格挂买单
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG
```

### 2. 市价单 (MARKET)

**特点**：
- 不需要指定价格
- 立即以当前市价成交
- 可能有滑点

**使用场景**：
- 需要立即成交
- 对价格不敏感
- 追踪趋势

**示例**：
```bash
# 以市价立即买入
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 --type market --position-side LONG
```

⚠️ **警告**：市价单会立即成交，请谨慎使用！

### 3. Post-only订单 (仅OKX)

**特点**：
- 只做Maker（提供流动性）
- 如果会立即成交，订单会被拒绝
- 享受Maker手续费优惠

**使用场景**：
- 想要获得Maker费率
- 不想支付Taker费用
- 提供流动性

**示例**：
```bash
# OKX Post-only订单
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --type post_only --position-side LONG
```

## 🆚 交易所差异对比

### 1. Symbol格式

| 交易所 | CLI输入 | API转换后 |
|--------|---------|-----------|
| Binance | `BTC/USDT` | `BTCUSDT` |
| OKX | `BTC/USDT` | `BTC-USDT-SWAP` |

CLI会自动转换，你只需要输入 `BTC/USDT` 即可！

### 2. 参数大小写

| 交易所 | side | order_type | position_side |
|--------|------|------------|---------------|
| Binance | `BUY`/`SELL` | `LIMIT`/`MARKET` | `LONG`/`SHORT` |
| OKX | `buy`/`sell` | `limit`/`market` | `long`/`short` |

CLI会自动转换，你输入大小写都可以！

### 3. 订单类型支持

| 订单类型 | Binance | OKX |
|---------|---------|-----|
| LIMIT | ✅ | ✅ |
| MARKET | ✅ | ✅ |
| POST_ONLY | ✅ (GTX) | ✅ |
| STOP | ✅ | ⏳ |
| TAKE_PROFIT | ✅ | ⏳ |

## 💡 使用建议

### 1. 测试流程

```bash
# 步骤1：查询当前价格
cextools market ticker -x binance -s BTC/USDT

# 步骤2：下单（使用不会成交的价格测试）
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 10000 --position-side LONG

# 步骤3：查询挂单确认
cextools account orders -x binance -e perp --symbol BTC/USDT

# 步骤4：撤销测试订单（待实现）
# cextools order cancel -x binance -e perp --order-id 123456789
```

### 2. 安全建议

⚠️ **重要**：
1. **先用小额测试**：使用最小交易量测试
2. **使用限价单测试**：不会立即成交，可以撤销
3. **设置合理价格**：避免意外成交
4. **检查余额**：确保有足够余额
5. **启用API权限**：确保API有"交易"权限

### 3. 风险控制

```bash
# ✅ 推荐：限价单 + 不会成交的价格
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 10000 --position-side LONG

# ⚠️  谨慎：市价单会立即成交
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 --type market --position-side LONG

# ✅ 推荐：Post-only不会立即成交
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --type post_only --position-side LONG
```

## 📊 Python API使用

### Binance下单

```python
from tri_arb.exchanges.binance_perp import BinancePerpExchange

exchange = BinancePerpExchange(api_key="...", api_secret="...")
await exchange.connect()

# 限价单
result = await exchange.place_order(
    symbol="BTCUSDT",
    side="BUY",
    order_type="LIMIT",
    quantity="0.001",
    price="30000",
    position_side="LONG",
    time_in_force="GTC",
)

print(f"订单ID: {result['orderId']}")
print(f"状态: {result['status']}")

await exchange.disconnect()
```

### OKX下单

```python
from tri_arb.exchanges.okx_perp import OKXPerpExchange

exchange = OKXPerpExchange(
    api_key="...",
    api_secret="...",
    passphrase="..."
)
await exchange.connect()

# 限价单
result = await exchange.place_order(
    symbol="BTC-USDT-SWAP",
    side="buy",
    order_type="limit",
    quantity="0.001",
    price="30000",
    position_side="long",
)

print(f"订单ID: {result['ordId']}")
print(f"执行结果: {result['sMsg']}")

await exchange.disconnect()
```

## 🐛 常见错误

### 1. 余额不足

**错误信息**：
- Binance: `Insufficient balance`
- OKX: `Insufficient account balance`

**解决方法**：
- 查询余额：`cextools account balance -x okx -e perp`
- 确保有足够的USDT

### 2. 数量不符合要求

**错误信息**：
- `Quantity less than minimum`
- `Invalid quantity precision`

**解决方法**：
- 查询交易对最小数量要求
- 调整数量和精度

### 3. 价格精度错误

**错误信息**：
- `Invalid price precision`

**解决方法**：
- 使用正确的价格精度
- BTC通常2位小数，ETH通常2位小数

### 4. 缺少交易权限

**错误信息**：
- `API-key doesn't have permission`

**解决方法**：
- 确认API权限包含"交易"
- 重新创建API并勾选交易权限

## 📋 下单检查清单

下单前请确认：

- [ ] API凭证已正确设置
- [ ] API权限包含"交易"
- [ ] 账户有足够余额
- [ ] 交易对格式正确
- [ ] 数量符合最小要求
- [ ] 价格合理（限价单）
- [ ] 持仓方向正确（LONG/SHORT）
- [ ] 使用小额测试
- [ ] 准备好撤单（如果需要）

## 🎓 高级用法

### 1. 批量下单

使用Python脚本批量下单：

```python
import asyncio
from tri_arb.exchanges.okx_perp import OKXPerpExchange

async def batch_orders():
    exchange = OKXPerpExchange(...)
    await exchange.connect()
    
    orders = [
        {"symbol": "BTC-USDT-SWAP", "side": "buy", "price": "30000", "qty": "0.001"},
        {"symbol": "ETH-USDT-SWAP", "side": "buy", "price": "2000", "qty": "0.01"},
    ]
    
    for order in orders:
        result = await exchange.place_order(
            symbol=order["symbol"],
            side=order["side"],
            order_type="limit",
            quantity=order["qty"],
            price=order["price"],
            position_side="long",
        )
        print(f"订单已提交: {result['ordId']}")
    
    await exchange.disconnect()

asyncio.run(batch_orders())
```

### 2. 条件下单

根据价格条件下单：

```python
async def conditional_order():
    exchange = OKXPerpExchange(...)
    await exchange.connect()
    
    # 获取当前价格
    positions = await exchange.get_positions("BTC-USDT-SWAP")
    current_price = positions[0]['markPx'] if positions else Decimal("0")
    
    # 如果价格低于某个值，下单
    if current_price < Decimal("50000"):
        result = await exchange.place_order(
            symbol="BTC-USDT-SWAP",
            side="buy",
            order_type="limit",
            quantity="0.001",
            price=str(current_price * Decimal("0.95")),  # 低5%挂单
            position_side="long",
        )
        print(f"订单已提交: {result['ordId']}")
    
    await exchange.disconnect()
```

## 📚 相关文档

- [CEXTools使用指南](cextools-usage.md)
- [Binance API实现](binance-api-implementation.md)
- [OKX实现文档](okx-implementation.md)
- [下单示例代码](../examples/place_order_example.py)

## 🎉 总结

下单功能已完整实现：

1. ✅ Binance永续合约下单
2. ✅ OKX永续合约下单
3. ✅ CLI命令支持
4. ✅ Python API支持
5. ✅ 多种订单类型
6. ✅ 自动格式转换
7. ✅ 完整错误处理

**开始下单前请**：
- 📖 阅读本指南
- 🧪 使用小额测试
- ⚠️ 谨慎使用市价单
- ✅ 确认API权限

祝交易顺利！🚀

---

**最后更新**：2025-10-17  
**状态**：✅ 已完成并可用

