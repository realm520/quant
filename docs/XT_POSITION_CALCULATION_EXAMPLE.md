# XT 持仓量计算示例

## 实际数据示例

从 `xt_position_updates_account_006ktmm1` 表中的数据：

### 数据 1：多头持仓 (LONG)
```
symbol: trump_usdt
side: LONG
quantity: 306.0000000000 张
entry_price: 6.1640000000 USDT
margin: 188.5911665200 USDT
```

### 数据 2：空头持仓 (SHORT)
```
symbol: trump_usdt
side: SHORT
quantity: 314.0000000000 张
entry_price: 6.1680000000 USDT
margin: 193.6897658300 USDT
```

## 计算逻辑

### 1. 持仓量计算

```python
# 多头持仓量
pre_long_qty = 306.0000000000 张

# 空头持仓量
pre_short_qty = 314.0000000000 张

# 总持仓量
total_qty = pre_long_qty + pre_short_qty = 620.0000000000 张
```

### 2. 持仓市值计算

```python
# 多头持仓市值 = 持仓数量 × 开仓价格
pre_long_value = 306 × 6.164 = 1,886.184 USDT

# 空头持仓市值 = 持仓数量 × 开仓价格
pre_short_value = 314 × 6.168 = 1,936.752 USDT

# 总持仓市值
total_value = pre_long_value + pre_short_value = 3,822.936 USDT
```

## 使用 XTPositionCalculator 计算

```python
from tri_arb.services.xt_position_calculator import XTPositionCalculator
from sqlalchemy.ext.asyncio import AsyncSession

# 创建计算器
calculator = XTPositionCalculator(
    db_session=session,
    account_id="account_006ktmm1"  # 对应表名中的账号ID
)

# 计算昨日持仓指标（使用 WebSocket 数据）
metrics = await calculator.calculate_pre_position_metrics(
    hours_back=24,  # 24小时前
    use_websocket=True  # 使用 WebSocket 数据（推荐）
)

# 结果
print(f"昨日多头持仓量: {metrics['pre_long_qty']}")      # 306.0000000000
print(f"昨日空头持仓量: {metrics['pre_short_qty']}")    # 314.0000000000
print(f"昨日多头市值: {metrics['pre_long_value']}")      # 1886.184
print(f"昨日空头市值: {metrics['pre_short_value']}")     # 1936.752
```

## 数据字段说明

### WebSocket 持仓更新数据字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `symbol` | string | 交易对 | `trump_usdt` |
| `side` | string | 持仓方向 | `LONG` 或 `SHORT` |
| `quantity` | Decimal | 持仓数量（张） | `306.0000000000` |
| `entry_price` | Decimal | 开仓均价 | `6.1640000000` |
| `margin` | Decimal | 保证金 | `188.5911665200` |
| `leverage` | int | 杠杆倍数 | `10` |
| `update_time` | datetime | 更新时间 | `2025-11-26 15:27:01` |

### raw_data 中的额外字段

从 `raw_data` JSON 中可以提取更多信息：

```json
{
  "positionSize": "306",           // 持仓数量
  "entryPrice": "6.164",           // 开仓价格
  "realizedProfit": "-6.1370",     // 已实现盈亏
  "markPrice": "6.158",            // 标记价格
  "isolatedMargin": "188.59116652", // 保证金
  "leverage": 10,                  // 杠杆倍数
  "updatedTime": 1764170821078     // 更新时间戳（毫秒）
}
```

## 计算验证

### 手动计算验证

```python
from decimal import Decimal

# 多头持仓
long_qty = Decimal("306")
long_entry_price = Decimal("6.164")
long_value = long_qty * long_entry_price
# 结果: 1886.184 USDT

# 空头持仓
short_qty = Decimal("314")
short_entry_price = Decimal("6.168")
short_value = short_qty * short_entry_price
# 结果: 1936.752 USDT

# 总计
total_qty = long_qty + short_qty
total_value = long_value + short_value
# 结果: 620 张, 3822.936 USDT
```

### 使用测试脚本验证

```bash
python3 scripts/test_position_calculation.py
```

## 注意事项

1. **持仓数量单位**：XT 使用"张"作为持仓单位，不是币的数量
2. **开仓价格**：使用 `entry_price`（开仓均价），不是当前标记价格
3. **持仓市值**：计算方式是 `持仓数量 × 开仓价格`，不是 `持仓数量 × 标记价格`
4. **已实现盈亏**：虽然 `raw_data` 中有 `realizedProfit`，但计算持仓市值时不需要此字段
5. **多账号支持**：如果使用多账号，需要为每个账号分别计算，使用对应的账号ID

## 相关文件

- `src/tri_arb/services/xt_position_calculator.py`: 持仓量计算器实现
- `scripts/test_position_calculation.py`: 测试脚本
- `docs/XT_POSITION_CALCULATION.md`: 详细使用文档

