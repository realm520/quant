# Gate.io 订单显示字段修复

## 🐛 问题

订单显示中价格字段不正确：
```
│ 价格   │ 0.0000   │  ← 错误！实际成交价是3862.53
```

## 🔍 根本原因

Gate.io订单有**两个价格字段**：
- `price`: 限价（市价单时为0）
- `fill_price`: **实际成交价格** ← 应该显示这个！

代码只使用了`price`字段，导致市价单和IOC订单显示为0。

## 📊 Gate.io订单字段说明

从实际API响应可以看到：

```json
{
  "id": 63894829872791034,
  "contract": "ETH_USDT",
  "size": -1,                    // 负数=卖单
  "price": 0,                    // 限价（市价/IOC单为0）
  "fill_price": 3862.53,         // ← 实际成交价格！
  "left": 0,                     // 剩余数量
  "status": "finished",          // 订单状态
  "tif": "ioc",                  // 订单类型
  "fee": 0.01931265,             // 手续费
  "role": "taker",               // 成交角色
  "create_time": 1761120139,
  "finish_time": 1761120139
}
```

### 重要字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `price` | 限价价格 | `3820.5` 或 `0`（市价） |
| `fill_price` | 实际成交均价 | `3862.53` |
| `size` | 数量（正=买，负=卖） | `-1` |
| `left` | 剩余未成交数量 | `0` |
| `tif` | 订单类型 | `gtc`/`ioc`/`fok`/`poc` |
| `fee` | 手续费（USDT） | `0.01931265` |
| `role` | 成交角色 | `maker`/`taker` |

### TIF类型说明

| TIF | 全称 | 说明 |
|-----|------|------|
| `gtc` | Good Till Cancel | 持续有效（直到取消） |
| `ioc` | Immediate Or Cancel | 立即成交或取消 |
| `fok` | Fill Or Kill | 全部成交或取消 |
| `poc` | Post Only Cancel | 被动委托（只做Maker） |

## ✅ 修复内容

### 文件: `src/tri_arb/services/gate_user_stream.py`

#### 1. 价格显示逻辑

```python
# ❌ 修复前
price = _safe_float(order.get("price"), 0)
table.add_row("价格", f"{price:.4f}")  # 市价单显示0.0000

# ✅ 修复后
limit_price = _safe_float(order.get("price"), 0)
fill_price = _safe_float(order.get("fill_price"), 0)

# 智能显示
if fill_price > 0:
    table.add_row("成交价", f"[green]{fill_price:.4f}[/green]")
    if limit_price > 0 and limit_price != fill_price:
        table.add_row("限价", f"{limit_price:.4f}")
elif limit_price > 0:
    table.add_row("限价", f"{limit_price:.4f}")
else:
    table.add_row("价格", "市价")
```

#### 2. 新增字段

```python
# 订单类型（TIF）
tif = order.get("tif", "")
order_type = tif_map.get(tif, tif.upper())  # GTC(持续有效) / IOC(立即成交)

# 手续费
fee = _safe_float(order.get("fee"), 0)
if fee > 0:
    table.add_row("手续费", f"[yellow]{fee:.6f} USDT[/yellow]")

# 成交角色
role = order.get("role", "")
role_display = "Maker" if role == "maker" else "Taker"
table.add_row("角色", role_display)
```

## 🎯 现在的显示效果

### 限价单（未成交）
```
📝 Gate.io订单更新 - 16:00:15
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ 字段       ┃ 值                ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ 订单ID     │ 63894829872732310 │
│ 合约       │ ETH_USDT          │
│ 方向       │ 买入              │
│ 类型       │ GTC(持续有效)     │
│ 限价       │ 3820.5000         │  ← 显示限价
│ 数量       │ 1                 │
│ 已成交     │ 0 (0.0%)          │
│ 剩余       │ 1                 │
│ 状态       │ 🟢 挂单中         │
└────────────┴───────────────────┘
```

### 市价单/IOC（已成交）
```
📝 Gate.io订单更新 - 16:00:39
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ 字段       ┃ 值                ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ 订单ID     │ 63894829872791034 │
│ 合约       │ ETH_USDT          │
│ 方向       │ 卖出              │
│ 类型       │ IOC(立即成交)     │
│ 成交价     │ 3862.5300         │  ← 显示成交价！
│ 数量       │ 1                 │
│ 已成交     │ 1 (100.0%)        │
│ 剩余       │ 0                 │
│ 手续费     │ 0.019313 USDT     │  ← 新增
│ 角色       │ Taker             │  ← 新增
│ 状态       │ ✅ 已完成         │
└────────────┴───────────────────┘
```

## 📈 改进亮点

1. **智能价格显示**
   - 已成交：显示实际成交价（绿色）
   - 挂单中：显示限价
   - 市价单：显示"市价"文字

2. **订单类型说明**
   - `GTC(持续有效)` - 清晰易懂
   - `IOC(立即成交)` - 中文说明

3. **新增重要信息**
   - 手续费（高亮黄色）
   - 成交角色（Maker/Taker）

4. **颜色标识**
   - 成交价：绿色
   - 买入：绿色
   - 卖出：红色
   - 手续费：黄色

## ✅ 验证

重新订阅并等待订单更新：

```bash
cextools subscribe user-stream -x gate -c order

# 创建订单（网页端或API）
# 观察订单推送显示

# 应该看到：
# ✅ 价格正确显示（成交价 or 限价）
# ✅ 订单类型说明清晰
# ✅ 手续费和角色信息
```

---

**所有订单显示字段已修复并优化！** 🎉

