# Symbol格式使用指南

## 📋 统一格式

**推荐使用统一格式**：`BTC/USDT`（斜杠分隔）

CLI会自动转换为各交易所的格式！

## ✅ 正确用法

### 查询持仓和挂单

```bash
# ✅ 推荐：使用统一格式（斜杠分隔）
cextools account positions -x binance -e perp --symbol BTC/USDT
cextools account positions -x okx -e perp --symbol BTC/USDT
cextools account orders -x okx -e perp --symbol ETH/USDT

# ✅ 也支持：不带斜杠
cextools account positions -x binance -e perp --symbol BTCUSDT

# ✅ 也支持：下划线分隔
cextools account positions -x xt -e perp --symbol btc_usdt
```

### ❌ 不支持的格式

```bash
# ❌ 错误：直接使用OKX原生格式
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP
# 错误信息：交易对格式无效: BTC-USDT-SWAP

# 原因：CLI验证器不接受横杠格式
# 解决：使用 BTC/USDT，CLI会自动转换
```

## 🔄 自动格式转换

CLI会根据交易所自动转换symbol格式：

| 你输入 | XT | Binance | OKX |
|--------|-----|---------|-----|
| `BTC/USDT` | `btc_usdt` | `BTCUSDT` | `BTC-USDT-SWAP` |
| `BTCUSDT` | `btc_usdt` | `BTCUSDT` | `BTC-USDT-SWAP` |
| `btc_usdt` | `btc_usdt` | `BTCUSDT` | `BTC-USDT-SWAP` |

**转换规则**：
- 移除所有分隔符（`/`, `-`, `_`）
- 转为大写
- 智能匹配交易所格式

## 📖 各交易所原生格式

仅供参考，**不需要手动转换**！

### XT格式
- 永续合约：`btc_usdt`
- 特点：小写 + 下划线

### Binance格式
- 永续合约：`BTCUSDT`
- 特点：大写 + 直接拼接

### OKX格式
- 永续合约：`BTC-USDT-SWAP`
- 特点：大写 + 横杠 + SWAP后缀

## 💡 使用建议

### 推荐方式

**始终使用斜杠格式**：`BTC/USDT`

```bash
# 所有交易所都用这个格式
cextools account positions -x binance -e perp --symbol BTC/USDT
cextools account positions -x okx -e perp --symbol BTC/USDT
cextools account positions -x xt -e perp --symbol BTC/USDT
```

**优点**：
- ✅ 最直观易读
- ✅ 适用所有交易所
- ✅ 不需要记忆各交易所格式
- ✅ 自动转换处理

### 查询所有持仓

不指定symbol，查询所有：

```bash
# 查询所有持仓
cextools account positions -x okx -e perp

# 查询所有挂单
cextools account orders -x okx -e perp
```

## 🔍 匹配机制

CLI使用智能匹配：

```python
# 标准化输入
normalized_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
# 结果：BTCUSDT

# 标准化数据
# OKX: "BTC-USDT-SWAP" -> 移除"-"和"SWAP" -> "BTCUSDT"
# Binance: "BTCUSDT" -> "BTCUSDT"  
# XT: "btc_usdt" -> 移除"_"并大写 -> "BTCUSDT"

# 匹配：normalized_symbol == normalized_data
```

## 🎯 实际使用示例

### 场景1：查询BTC持仓

```bash
# 方式1（推荐）
cextools account positions -x okx -e perp --symbol BTC/USDT

# 方式2（也可以）
cextools account positions -x okx -e perp --symbol BTCUSDT

# 两种方式结果相同！
```

### 场景2：查询ETH挂单

```bash
# Binance
cextools account orders -x binance -e perp --symbol ETH/USDT

# OKX
cextools account orders -x okx -e perp --symbol ETH/USDT

# 两个交易所使用相同的格式！
```

### 场景3：下单

```bash
# Binance下单（使用BTC/USDT）
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

# OKX下单（也使用BTC/USDT）
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG
```

## ⚠️ 常见错误

### 错误1：使用OKX原生格式

```bash
# ❌ 错误
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP

# 错误信息：交易对格式无效: BTC-USDT-SWAP

# ✅ 正确
cextools account positions -x okx -e perp --symbol BTC/USDT
```

### 错误2：混淆symbol格式

```bash
# ❌ 错误：在Binance使用OKX格式
cextools account positions -x binance -e perp --symbol BTC-USDT-SWAP

# ✅ 正确：使用统一格式
cextools account positions -x binance -e perp --symbol BTC/USDT
```

## 📚 相关文档

- [CEXTools使用指南](cextools-usage.md)
- [多交易所对比](multi-exchange-summary.md)
- [OKX快速开始](okx-quickstart.md)

## 🎯 记住这一点

**无论什么交易所，始终使用 `BTC/USDT` 格式！**

CLI会自动处理格式转换，你不需要关心各交易所的差异。

---

**最后更新**：2025-10-17

