# XT 持仓量计算说明

## 概述

XT 交易所的"昨日"持仓量计算需要从数据库的历史持仓数据中查询。本文档说明如何计算以下指标：

- **昨日多头持仓量** (`pre_long_qty`)
- **昨日空头持仓量** (`pre_short_qty`)
- **昨日多头市值** (`pre_long_value`)
- **昨日空头市值** (`pre_short_value`)

## 数据来源

### ⭐ 推荐：WebSocket 持仓更新数据

**强烈推荐使用 WebSocket 持仓更新数据**，原因：

1. **实时性更好**：每次仓位变化都会立即推送并保存，数据更及时
2. **数据更准确**：反映真实的仓位变化历史，不会遗漏任何变化
3. **数据更完整**：可以追踪每次仓位变化的详细时间点
4. **减少 API 调用**：不需要定期轮询 REST API

**数据表**: `xt_position_updates`（WebSocket 持仓更新表）

### 备选：REST API 持仓快照数据

如果 WebSocket 数据不可用，可以使用 REST API 定期查询的持仓快照。

**数据表**: `xt_perp_positions`（REST API 持仓快照表）

## 计算方法

### 1. 使用 WebSocket 数据（推荐）

### 2. 计算逻辑

1. **查询昨日持仓快照**：
   - 查询目标时间点（默认：当前时间 - 24小时）之前最近的持仓记录
   - 按 `symbol` 和 `position_side` 分组，取每个组合的最新记录

2. **统计持仓量**：
   - `pre_long_qty` = 所有 `position_side = 'LONG'` 的 `position_amount` 之和
   - `pre_short_qty` = 所有 `position_side = 'SHORT'` 的 `position_amount` 之和

3. **计算持仓市值**：
   - `pre_long_value` = 所有多头持仓的市值之和
     - 优先使用 API 返回的 `notional`（名义价值）
     - 如果没有 `notional`，则使用 `position_amount × entry_price`
   - `pre_short_value` = 所有空头持仓的市值之和（计算方式同上）

## 使用示例

### 基本使用（推荐：使用 WebSocket 数据）

```python
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from tri_arb.services.xt_position_calculator import XTPositionCalculator

# 创建计算器实例
calculator = XTPositionCalculator(db_session=db_session, account_id="account_001")

# 计算昨日持仓指标（默认使用 WebSocket 数据，更实时、更准确）
metrics = await calculator.calculate_pre_position_metrics()

print(f"昨日多头持仓量: {metrics['pre_long_qty']}")
print(f"昨日空头持仓量: {metrics['pre_short_qty']}")
print(f"昨日多头市值: {metrics['pre_long_value']}")
print(f"昨日空头市值: {metrics['pre_short_value']}")
```

### 明确指定使用 WebSocket 数据

```python
# 明确指定使用 WebSocket 数据（推荐）
metrics = await calculator.calculate_pre_position_metrics(use_websocket=True)
```

### 使用 REST API 持仓快照数据（备选）

```python
# 如果 WebSocket 数据不可用，可以使用 REST API 数据
metrics = await calculator.calculate_pre_position_metrics(use_websocket=False)
```

### 直接使用 WebSocket 数据方法

```python
# 直接调用 WebSocket 数据计算方法
metrics = await calculator.calculate_pre_position_metrics_from_websocket()
```

### 指定目标日期

```python
from datetime import datetime, timedelta

# 计算特定日期的持仓指标
target_date = datetime.utcnow() - timedelta(days=1)
metrics = await calculator.calculate_pre_position_metrics(target_date=target_date)
```

### 自定义回溯时间

```python
# 计算12小时前的持仓指标
metrics = await calculator.calculate_pre_position_metrics(hours_back=12)
```

### 计算持仓变化

```python
from tri_arb.exchanges.xt_perp import XTPerpExchange

# 获取当前持仓
exchange = XTPerpExchange(api_key="...", api_secret="...")
await exchange.connect()
current_positions = await exchange.get_positions()

# 计算持仓变化（当前 vs 昨日）
changes = await calculator.calculate_position_change(current_positions)

print(f"多头持仓量变化: {changes['long_qty_change']}")
print(f"空头持仓量变化: {changes['short_qty_change']}")
print(f"多头市值变化: {changes['long_value_change']}")
print(f"空头市值变化: {changes['short_value_change']}")
```

## 在 watch-account 命令中使用

可以在 `watch-account` 命令中集成持仓量计算：

```python
from tri_arb.services.xt_position_calculator import XTPositionCalculator

# 在查询持仓后，计算昨日持仓指标
async with db_manager.session() as session:
    calculator = XTPositionCalculator(db_session=session, account_id=account_id)
    pre_metrics = await calculator.calculate_pre_position_metrics()
    
    # 显示昨日持仓信息
    console.print(f"昨日多头持仓量: {pre_metrics['pre_long_qty']}")
    console.print(f"昨日空头持仓量: {pre_metrics['pre_short_qty']}")
    console.print(f"昨日多头市值: {pre_metrics['pre_long_value']}")
    console.print(f"昨日空头市值: {pre_metrics['pre_short_value']}")
```

## 注意事项

1. **数据可用性**：
   - **WebSocket 数据（推荐）**：
     - 需要运行 `subscribe multi-account` 命令，启用 `position` 频道
     - WebSocket 会自动保存每次仓位变化到 `xt_position_updates` 表
     - 如果数据库中没有 WebSocket 数据，会自动回退到 REST API 数据
   - **REST API 数据（备选）**：
     - 需要确保 `watch-account` 或 `watch-positions` 命令定期运行，保存持仓快照
     - 如果数据库中没有历史数据，所有指标将返回 0

2. **时间定义**：
   - "昨日"默认定义为当前时间 - 24小时
   - 可以根据需要调整 `hours_back` 参数
   - 对于交易日概念，可能需要根据交易所的交易时间调整

3. **多账号支持**：
   - 如果使用多账号，需要为每个账号分别计算
   - 可以通过 `account_id` 参数区分不同账号的数据

4. **市值计算**：
   - 优先使用 API 返回的 `notional`（名义价值）
   - 如果没有 `notional`，使用 `持仓量 × 开仓价格`
   - 注意：市值计算可能因价格波动而不准确，仅供参考

5. **性能考虑**：
   - 如果历史数据量很大，查询可能需要一些时间
   - 建议在数据库的 `query_time` 字段上建立索引

## 数据库索引

确保以下索引存在以提高查询性能：

```sql
CREATE INDEX IF NOT EXISTS idx_xt_perp_position_symbol_time 
ON xt_perp_positions(symbol, query_time);

CREATE INDEX IF NOT EXISTS idx_xt_perp_position_side_time 
ON xt_perp_positions(position_side, query_time);

CREATE INDEX IF NOT EXISTS idx_xt_perp_position_query_type_time 
ON xt_perp_positions(query_type, query_time);
```

## 相关文件

- `src/tri_arb/services/xt_position_calculator.py`: 持仓量计算器实现
- `src/tri_arb/storage/xt_rest_models.py`: 持仓数据模型定义
- `src/tri_arb/exchanges/xt_perp.py`: XT 交易所适配器

