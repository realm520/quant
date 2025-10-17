# 多交易所支持总结

## 🎉 已实现功能概览

本项目现已支持3个主要加密货币交易所：**XT**、**Binance** 和 **OKX**。

## 📊 功能对比表

| 功能 | XT | Binance | OKX |
|------|-----|---------|-----|
| **现货余额** | ✅ | ✅ | ⏳ |
| **合约余额** | ✅ | ✅ | ✅ |
| **持仓查询** | ✅ | ✅ | ✅ |
| **挂单查询** | ✅ | ✅ | ✅ |
| **行情查询** | ✅ | ✅ | ⏳ |
| **下单功能** | ✅ | ✅ | ✅ |
| **撤单功能** | ✅ | ⏳ | ⏳ |

**图例**：
- ✅ 已完整实现
- ⏳ 待实现

## 🔑 API认证对比

### 认证参数

| 交易所 | 认证参数数量 | 必需参数 |
|--------|-------------|---------|
| XT | 2个 | API Key + Secret Key |
| Binance | 2个 | API Key + Secret Key |
| OKX | 3个 | API Key + Secret Key + **Passphrase** |

### 环境变量配置

**XT**：
```bash
export XT_API_KEY="..."
export XT_API_SECRET="..."
```

**Binance**：
```bash
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
```

**OKX**（需要额外的Passphrase）：
```bash
export OKX_API_KEY="..."
export OKX_API_SECRET="..."
export OKX_PASSPHRASE="..."  # 创建API时自己设置的密码
```

## 📝 Symbol格式对比

不同交易所使用不同的交易对格式：

| 交易所 | 永续合约格式 | 示例 |
|--------|-------------|------|
| XT | `base_quote` | `btc_usdt` |
| Binance | `BASEQUOTE` | `BTCUSDT` |
| OKX | `BASE-QUOTE-SWAP` | `BTC-USDT-SWAP` |

### CLI使用说明

我们的CLI会自动处理格式转换（通过本地筛选），你可以使用任意格式：

```bash
# 以下格式都能正确工作
cextools account positions -x binance -e perp --symbol BTC/USDT
cextools account positions -x binance -e perp --symbol BTCUSDT
cextools account positions -x binance -e perp --symbol btc_usdt
```

## 🎨 输出格式统一

所有交易所都支持3种输出格式：

### 1. Table（表格）- 默认
```bash
cextools account positions -x okx -e perp
```
美观的表格显示，带颜色和格式化。

### 2. JSON（JSON）
```bash
cextools account positions -x okx -e perp -o json
```
完整的API响应数据，适合程序处理。

### 3. CSV（CSV）
```bash
cextools account positions -x okx -e perp -o csv
```
表格数据，可以导入Excel。

## 🔧 统一的命令格式

### 查询余额
```bash
cextools account balance -x <exchange> -e <type>

# 示例
cextools account balance -x xt -e perp
cextools account balance -x binance -e perp
cextools account balance -x okx -e perp
```

### 查询持仓
```bash
cextools account positions -x <exchange> -e perp [--symbol SYMBOL]

# 示例
cextools account positions -x xt -e perp
cextools account positions -x binance -e perp --symbol BTC/USDT
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP
```

### 查询挂单
```bash
cextools account orders -x <exchange> -e perp [--symbol SYMBOL]

# 示例
cextools account orders -x xt -e perp
cextools account orders -x binance -e perp --symbol BTC/USDT
cextools account orders -x okx -e perp --symbol BTC-USDT-SWAP
```

## 🌟 特色功能

### 1. 本地筛选机制
所有交易所都采用本地筛选，避免格式转换问题：
```python
# 始终获取所有数据
data = await exchange.get_positions(None)

# 在本地筛选
if symbol:
    filtered = [d for d in data if matches(d, symbol)]
```

### 2. 统一的数据格式
虽然不同交易所API返回格式不同，但我们的格式化函数会自动适配：
- 余额：统一为 `{currency: {available, frozen, total}}`
- 持仓：自动识别OKX/Binance/XT格式
- 挂单：自动识别不同字段名称

### 3. 智能字段识别
```python
# 自动检测交易所格式
if 'instId' in data:
    # OKX格式
    symbol = data['instId']
elif 'symbol' in data:
    # Binance格式
    symbol = data['symbol']
else:
    # XT对象格式
    symbol = data.symbol
```

## 📚 文档索引

### 快速开始
- [OKX快速开始](okx-quickstart.md)
- [CEXTools使用指南](cextools-usage.md)

### 技术文档
- [OKX实现文档](okx-implementation.md)
- [Binance实现文档](binance-api-implementation.md)
- [Binance持仓功能](binance-positions-feature.md)
- [Binance挂单功能](binance-orders-feature.md)

### 示例代码
- [OKX使用示例](../examples/okx_example.py)
- [Binance持仓示例](../examples/binance_positions_example.py)
- [Binance挂单示例](../examples/binance_orders_example.py)
- [示例代码说明](../examples/README.md)

## 🎯 下一步计划

### Binance
- [ ] 实现下单功能
- [ ] 实现撤单功能
- [ ] 实现杠杆设置

### OKX
- [ ] 实现现货交易
- [ ] 实现下单功能
- [ ] 实现撤单功能
- [ ] 实现行情查询
- [ ] 实现杠杆设置

### 通用功能
- [ ] WebSocket实时订阅
- [ ] 批量操作支持
- [ ] 错误重试机制
- [ ] 速率限制管理

## 🏆 最佳实践

### 1. 环境变量管理
建议使用 `.env` 文件：
```bash
# .env
XT_API_KEY=...
XT_API_SECRET=...
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
```

然后使用 `source .env` 加载。

### 2. API权限最小化
- 只开启需要的权限
- 不要开启提币权限
- 定期轮换API密钥

### 3. IP白名单
- 生产环境强烈建议设置IP白名单
- 提高账户安全性

### 4. 监控和日志
```bash
# 使用debug模式查看详细日志
cextools account positions -x okx -e perp --debug
```

## 📈 性能建议

### 1. 批量查询
优先使用批量查询，然后本地筛选：
```bash
# ✅ 推荐：一次获取所有持仓
cextools account positions -x okx -e perp -o json | jq '.[] | select(.instId == "BTC-USDT-SWAP")'

# ⚠️ 效果相同但实现更优雅
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP
```

### 2. 缓存策略
对于不频繁变化的数据，考虑本地缓存：
```bash
# 缓存余额数据
cextools account balance -x okx -e perp -o json > /tmp/okx_balance.json
```

### 3. 并发查询
使用Python异步API同时查询多个交易所：
```python
async def get_all_positions():
    xt = XTPerpExchange(...)
    binance = BinancePerpExchange(...)
    okx = OKXPerpExchange(...)
    
    await asyncio.gather(
        xt.connect(),
        binance.connect(),
        okx.connect(),
    )
    
    positions = await asyncio.gather(
        xt.get_positions(),
        binance.get_positions(),
        okx.get_positions(),
    )
    
    return positions
```

## 🎊 总结

通过统一的CLI和Python API，现在可以轻松管理多个交易所的账户：

- ✅ **3个交易所**：XT、Binance、OKX
- ✅ **统一接口**：相同的命令格式
- ✅ **智能适配**：自动识别不同格式
- ✅ **多种输出**：table、json、csv
- ✅ **完整文档**：详细的使用说明和示例

开始你的多交易所量化交易之旅吧！🚀

---

**版本**：1.0.0  
**最后更新**：2025-10-16  
**状态**：✅ 生产就绪

