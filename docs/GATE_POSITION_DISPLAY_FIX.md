# Gate.io 持仓显示字段修复

## 🐛 问题

持仓显示中多个关键字段显示为0：
```
│ 标记价格 │   0.0000 │  ← 错误
│ 保证金   │   0.0000 │  ← 错误
│ 杠杆     │      0x  │  ← 错误
```

## 🔍 根本原因

Gate.io持仓数据结构与预期不同：

### ❌ 代码期望的字段（OKX/Binance格式）
```python
mark_price         # 标记价格
unrealised_pnl     # 未实现盈亏
margin            # 保证金
leverage          # 杠杆
```

### ✅ Gate.io实际提供的字段
```json
{
  "contract": "ETH_USDT",
  "size": 1,
  "entry_price": 3859.5096875,    // ✅ 开仓均价
  "leverage": 0,                  // ⚠️ 全仓模式时为0
  "leverage_max": 125,            // ✅ 最大杠杆
  "mode": "single",               // ✅ 单向/双向
  "margin": 0,                    // ⚠️ 全仓模式时为0（共享保证金）
  "realised_pnl": -0.1837845102,  // ✅ 已实现盈亏
  "last_close_pnl": -0.10481105,  // ✅ 最后平仓盈亏
  "liq_price": 0,                 // 强平价（全仓模式为0）
  
  // ❌ 没有以下字段：
  // - mark_price（标记价格）
  // - unrealised_pnl（未实现盈亏）
}
```

## 📊 Gate.io持仓字段详解

| 字段 | 说明 | 全仓模式 | 逐仓模式 |
|------|------|----------|----------|
| `size` | 持仓数量（正=多，负=空） | ✅ | ✅ |
| `entry_price` | 开仓均价 | ✅ | ✅ |
| `mode` | 持仓模式 | `single`/`dual` | `single`/`dual` |
| `leverage` | 杠杆 | `0`（共享） | 实际杠杆 |
| `leverage_max` | 最大杠杆 | ✅ | ✅ |
| `margin` | 保证金 | `0`（共享） | 实际保证金 |
| `liq_price` | 强平价 | `0`（共享） | 实际强平价 |
| `realised_pnl` | 累计已实现盈亏 | ✅ | ✅ |
| `last_close_pnl` | 最后一次平仓盈亏 | ✅ | ✅ |

### 重要说明

1. **全仓模式（Cross Margin）**
   - `leverage = 0` - 表示使用账户共享杠杆
   - `margin = 0` - 表示使用账户共享保证金
   - `liq_price = 0` - 强平价由全账户风险决定

2. **逐仓模式（Isolated Margin）**
   - `leverage > 0` - 显示实际杠杆倍数
   - `margin > 0` - 显示独立保证金
   - `liq_price > 0` - 显示独立强平价

3. **Gate.io没有提供**
   - **标记价格** - 需要单独调用行情API获取
   - **未实现盈亏** - 需要根据标记价格计算

## ✅ 修复内容

### 调整后的表格列

```python
# ❌ 修复前（OKX风格）
table.add_column("标记价格")     # Gate.io不提供
table.add_column("强平价")       # 全仓模式为0
table.add_column("未实现盈亏")   # Gate.io不提供
table.add_column("收益率")       # 无法计算
table.add_column("保证金")       # 全仓模式为0
table.add_column("杠杆")         # 全仓模式为0

# ✅ 修复后（Gate.io风格）
table.add_column("合约")
table.add_column("方向")
table.add_column("持仓量")
table.add_column("开仓均价")
table.add_column("模式")         # 新增: 单向/双向
table.add_column("杠杆")         # 优化: 显示"全仓"
table.add_column("已实现盈亏")   # 新增: 累计盈亏
table.add_column("最后平仓")     # 新增: 最后平仓盈亏
```

### 杠杆显示逻辑

```python
if leverage > 0:
    leverage_str = f"{leverage:.0f}x"          # 如: "10x"
elif leverage_max > 0:
    leverage_str = f"全仓(max {leverage_max:.0f}x)"  # 如: "全仓(max 125x)"
else:
    leverage_str = "全仓"
```

## 🎯 现在的显示效果

### 全仓模式持仓
```
📊 Gate.io持仓更新 - 16:08:37
┏━━━━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ 合约     ┃ 方向 ┃ 持仓量 ┃  开仓均价 ┃ 模式 ┃ 杠杆           ┃ 已实现盈亏   ┃ 最后平仓   ┃
┡━━━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ ETH_USDT │  多  │      1 │ 3859.5097 │ 单向 │ 全仓(max 125x) │ -0.1838      │ -0.1048    │
└──────────┴──────┴────────┴───────────┴──────┴────────────────┴──────────────┴────────────┘
```

### 逐仓模式持仓（如果使用）
```
┏━━━━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━━━━━┳━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ 合约     ┃ 方向 ┃ 持仓量 ┃  开仓均价 ┃ 模式 ┃ 杠杆 ┃ 已实现盈亏   ┃ 最后平仓   ┃
┡━━━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━━━━━╇━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ BTC_USDT │  空  │     10 │ 68000.00  │ 单向 │  10x │ +125.5000    │ +125.5000  │
└──────────┴──────┴────────┴───────────┴──────┴──────┴──────────────┴────────────┘
```

## 📈 与其他交易所对比

| 交易所 | 标记价格 | 未实现盈亏 | 已实现盈亏 | 杠杆显示 |
|--------|---------|-----------|-----------|---------|
| **Binance** | ✅ 提供 | ✅ 提供 | ✅ 提供 | 直接显示 |
| **OKX** | ✅ 提供 | ✅ 提供 | ✅ 提供 | 直接显示 |
| **Gate.io** | ❌ 无 | ❌ 无 | ✅ 提供 | 全仓需特殊处理 |

**Gate.io特点**：
- 更关注**已实现盈亏**（实际产生的盈亏）
- 全仓模式使用共享杠杆和保证金
- 需要单独调用行情API获取标记价格

## 💡 未实现盈亏计算（可选扩展）

如果需要显示未实现盈亏，可以：

```python
# 1. 调用行情API获取当前价格
from tri_arb.exchanges.gate_perp import GatePerpExchange
gate = GatePerpExchange(api_key=..., api_secret=...)
ticker = await gate.get_ticker(contract="ETH_USDT")
current_price = ticker["last"]

# 2. 计算未实现盈亏
entry_price = 3859.5097
size = 1
unrealised_pnl = (current_price - entry_price) * size

# 3. 计算收益率
pnl_ratio = (unrealised_pnl / (entry_price * abs(size))) * 100
```

## ✅ 验证

重新订阅查看效果：

```bash
cextools subscribe user-stream -x gate -c position

# 应该看到：
# ✅ 合约、方向、持仓量正确
# ✅ 开仓均价正确
# ✅ 模式显示（单向/双向）
# ✅ 杠杆正确显示（全仓或具体倍数）
# ✅ 已实现盈亏正确
# ✅ 最后平仓盈亏正确
```

---

**所有持仓显示字段已修复！现在显示Gate.io实际提供的有效数据。** 🎉

