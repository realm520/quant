# WebSocket 持仓计算原理

## 问题：WebSocket 只在仓位变化时推送数据

WebSocket 数据的特点是：**只有当仓位发生变化时，才会推送更新**。这带来一个问题：

**如何计算某个时间点的持仓量？**

例如：
- 24小时前持仓是 1 BTC（有推送记录）
- 20小时前持仓变为 2 BTC（有推送记录）
- 现在要查询"24小时前的持仓"

## 计算逻辑

### 核心思路：找到"最后一次变化"的记录

使用 SQL 查询找到**每个 symbol+side 组合在目标时间之前的最新记录**：

```python
# 子查询：找到每个 symbol+side 组合在目标时间之前的最新记录
subquery = (
    select(
        XTPositionUpdate.symbol,
        XTPositionUpdate.side,
        func.max(XTPositionUpdate.update_time).label('max_time')
    )
    .where(XTPositionUpdate.update_time <= target_date)  # 只查询目标时间之前的记录
    .group_by(XTPositionUpdate.symbol, XTPositionUpdate.side)
    .subquery()
)

# 主查询：获取这些最新记录的完整信息
query = (
    select(XTPositionUpdate)
    .join(
        subquery,
        (XTPositionUpdate.symbol == subquery.c.symbol) &
        (XTPositionUpdate.side == subquery.c.side) &
        (XTPositionUpdate.update_time == subquery.c.max_time)
    )
    .where(XTPositionUpdate.quantity > 0)  # 只查询有持仓的记录
)
```

### 示例场景

假设目标时间是 24小时前（T-24h），有以下推送记录：

```
时间线：
T-30h: BTC LONG 持仓变为 1.0（有推送）
T-24h: （目标时间，无推送）
T-20h: BTC LONG 持仓变为 2.0（有推送）
T-10h: BTC LONG 持仓变为 1.5（有推送）
现在: T
```

**查询逻辑**：
1. 找到 `update_time <= T-24h` 的最大值 → `T-30h`
2. 返回 `T-30h` 的持仓记录 → `1.0 BTC`

**结果**：24小时前的持仓是 `1.0 BTC`（这是24小时前最后一次变化的记录）

## 潜在问题

### 问题1：目标时间之前没有记录

**场景**：
- 持仓在 T-10h 才开仓（第一次推送）
- 目标时间是 T-24h
- 查询 T-24h 的持仓

**结果**：
- 子查询 `max(update_time) where update_time <= T-24h` → `NULL`
- 主查询找不到记录
- **该持仓在24小时前不存在，返回空**

**这是正确的行为**：如果24小时前没有持仓，就应该返回空。

### 问题2：持仓在目标时间之后才变化

**场景**：
- T-30h: BTC LONG 持仓变为 1.0
- T-24h: （目标时间）
- T-20h: BTC LONG 持仓变为 2.0
- 查询 T-24h 的持仓

**结果**：
- 找到 `T-30h` 的记录（这是 T-24h 之前最后一次变化）
- 返回 `1.0 BTC`

**这是正确的行为**：24小时前的持仓确实是 `1.0 BTC`。

### 问题3：持仓在目标时间之后被平仓

**场景**：
- T-30h: BTC LONG 持仓变为 1.0
- T-24h: （目标时间）
- T-20h: BTC LONG 持仓变为 0.0（平仓）
- 查询 T-24h 的持仓

**结果**：
- 找到 `T-30h` 的记录（持仓 1.0）
- 但查询条件 `.where(XTPositionUpdate.quantity > 0)` 会过滤掉平仓记录
- 如果 T-24h 之前没有其他变化，返回 `1.0 BTC`

**这是正确的行为**：24小时前确实有持仓。

## Binance 的特殊情况

### Binance WebSocket 数据结构

Binance 的 `binance_account_update` 表中：
- `event_type = 'POSITION_UPDATE'` 表示持仓更新
- `position_amount` 可能是 0（平仓）
- `entry_price` 可能为空

### 查询逻辑

```python
from tri_arb.storage.models import AccountUpdate

# 子查询：找到每个 symbol+position_side 组合在目标时间之前的最新记录
subquery = (
    select(
        AccountUpdate.symbol,
        AccountUpdate.position_side,
        func.max(AccountUpdate.event_time).label('max_time')
    )
    .where(AccountUpdate.event_time <= target_date)
    .where(AccountUpdate.event_type == 'POSITION_UPDATE')
    .where(AccountUpdate.exchange == 'binance_perp')
    .group_by(AccountUpdate.symbol, AccountUpdate.position_side)
    .subquery()
)

# 主查询：获取这些最新记录的完整信息
query = (
    select(AccountUpdate)
    .join(
        subquery,
        (AccountUpdate.symbol == subquery.c.symbol) &
        (AccountUpdate.position_side == subquery.c.position_side) &
        (AccountUpdate.event_time == subquery.c.max_time)
    )
    .where(AccountUpdate.event_type == 'POSITION_UPDATE')
    .where(AccountUpdate.exchange == 'binance_perp')
    .where(AccountUpdate.position_amount != 0)  # 只查询有持仓的记录
)
```

## 与快照表的对比

### WebSocket 数据的优势

1. ✅ **实时性**：每次变化都有记录
2. ✅ **完整性**：不会丢失交易
3. ✅ **准确性**：反映真实的持仓变化历史

### WebSocket 数据的限制

1. ⚠️ **需要历史数据**：如果 WebSocket 连接中断，可能丢失数据
2. ⚠️ **查询复杂度**：需要找到"最后一次变化"的记录
3. ⚠️ **初始状态**：如果持仓在目标时间之前没有变化，可能找不到记录

### 快照表的优势

1. ✅ **简单直接**：直接查询目标时间附近的快照
2. ✅ **完整状态**：快照包含所有持仓的完整状态
3. ✅ **不依赖变化**：即使持仓没有变化，也有记录

### 快照表的限制

1. ❌ **可能丢失交易**：快照间隔内的交易会丢失
2. ❌ **时间精度**：只能知道快照时刻的状态
3. ❌ **依赖定时任务**：如果任务失败，数据会缺失

## 最佳实践

### 推荐方案：WebSocket + 快照表结合

1. **主要使用 WebSocket 数据**：
   - 用于精确计算昨日持仓
   - 实时追踪持仓变化

2. **快照表作为补充**：
   - 用于数据验证
   - 当 WebSocket 数据缺失时作为备选
   - 用于历史趋势分析

3. **容错处理**：
   ```python
   # 先尝试使用 WebSocket 数据
   try:
       metrics = await calculator.calculate_pre_position_metrics_from_websocket(
           hours_back=24
       )
   except Exception:
       # 如果 WebSocket 数据不可用，使用快照数据
       metrics = await calculator.calculate_pre_position_metrics(
           hours_back=24,
           use_websocket=False
       )
   ```

## 总结

**WebSocket 持仓计算的核心**：
1. 找到目标时间之前最后一次变化的记录
2. 该记录反映了目标时间点的持仓状态
3. 如果目标时间之前没有记录，说明该持仓在目标时间不存在

**适用场景**：
- ✅ 需要精确计算某个时间点的持仓
- ✅ 需要追踪持仓变化历史
- ✅ 需要实时性

**不适用场景**：
- ❌ WebSocket 连接中断，数据缺失
- ❌ 需要所有持仓的完整快照（即使没有变化）

