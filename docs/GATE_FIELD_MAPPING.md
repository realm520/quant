# Gate.io API字段映射修复

## 🐛 问题

订阅成功并保存数据，但**不显示**账户余额表格。

## 🔍 原因

代码中使用的字段名与Gate.io实际返回的字段名不匹配：

### ❌ 代码中期望的字段

```python
balance.get("total")           # 总额
balance.get("available")       # 可用
balance.get("unrealised_pnl")  # 未实现盈亏
```

### ✅ Gate.io实际返回的字段

```json
{
  "currency": "usdt",
  "balance": 35.22208045,    // ← 余额（不是total）
  "change": -0.01928575,     // ← 变动（不是unrealised_pnl）
  "text": "ETH_USDT:...",
  "time": 1761119295,
  "time_ms": 1761119295721,
  "type": "fee",             // ← 类型（如fee/dnw/pnl等）
  "user": "15762235"
}
```

**结果**: `balance.get("total")` 返回 `None`，`_safe_float(None, 0)` 返回 `0`，触发了 `if total == 0 and available == 0: continue` 的过滤逻辑，数据被跳过不显示。

---

## ✅ 修复

### 文件: `src/tri_arb/services/gate_user_stream.py`

#### 1. 显示方法 (`display_account_update`)

```python
# ❌ 修复前
total = _safe_float(balance.get("total"), 0)
available = _safe_float(balance.get("available"), 0)
unrealised_pnl = _safe_float(balance.get("unrealised_pnl"), 0)

# ✅ 修复后
balance_amount = _safe_float(balance.get("balance"), 0)
change = _safe_float(balance.get("change"), 0)
update_type = balance.get("type", "")
```

#### 2. 表格列名

```python
# ❌ 修复前
table.add_column("总额")
table.add_column("可用")
table.add_column("未实现盈亏")

# ✅ 修复后
table.add_column("余额")
table.add_column("变动")
table.add_column("类型")
```

#### 3. 保存方法 (`save_account_update`)

```python
# ✅ 修复后
balance_amount = _safe_decimal(balance.get("balance"))

record = GateAccountBalance(
    total=balance_amount,
    available=balance_amount,  # Gate.io没有分离的available字段
    unrealised_pnl=_safe_decimal(balance.get("change")),  # 使用change
    # ...
)
```

#### 4. 变化检测 (`_has_account_changed`)

```python
# ✅ 修复后
account_snapshot[currency] = {
    "balance": balance.get("balance"),
    "change": balance.get("change"),
    "type": balance.get("type"),
}
```

---

## 📊 Gate.io字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `currency` | string | 结算货币 | `"usdt"` |
| `balance` | float | 当前余额 | `35.22208045` |
| `change` | float | 本次变动 | `-0.01928575` |
| `type` | string | 变动类型 | `"fee"`, `"dnw"`, `"pnl"` |
| `text` | string | 关联信息 | 订单ID等 |
| `time` | int | 时间戳（秒） | `1761119295` |
| `time_ms` | int | 时间戳（毫秒） | `1761119295721` |
| `user` | string | 用户ID | `"15762235"` |

### 变动类型 (`type`)

| 类型 | 说明 |
|------|------|
| `fee` | 手续费 |
| `dnw` | 入金/出金 |
| `pnl` | 已实现盈亏 |
| `refr` | 返佣 |
| `fund` | 资金费 |

---

## 🎯 现在应该正常显示了！

### 预期输出

```
💰 Gate.io账户余额 - 15:48:14
┏━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━┓
┃ 币种 ┃ 余额       ┃ 变动       ┃ 类型 ┃
┡━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━┩
│ USDT │ 35.2221    │ -0.0193    │ fee  │
└──────┴────────────┴────────────┴──────┘
✅ Gate account update saved
```

---

## 🔄 与其他交易所的对比

| 交易所 | 余额字段 | 可用余额字段 | 未实现盈亏字段 |
|--------|---------|-------------|---------------|
| **Binance** | ✅ `balance` | ✅ `availableBalance` | ✅ `crossUnPnl` |
| **OKX** | ✅ `eq` (总权益) | ✅ `availBal` | ✅ `upl` |
| **Gate.io** | ✅ `balance` | ❌ 无 | ❌ 无 (有`change`) |

**说明**: Gate.io的账户余额推送是**事件驱动**的，每次推送一个变动事件，不是完整的账户快照。

---

## ✅ 验证

```bash
# 重新测试订阅
cextools subscribe user-stream -x gate -c account

# 应该看到：
# ✅ Channel subscribed successfully
# 💰 Gate.io账户余额表格（有数据）
# ✅ Gate account update saved
```

---

**所有字段映射已修复！Gate.io账户余额现在可以正常显示。** 🎉

