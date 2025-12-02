# 基于成交记录的持仓量计算

## 需求说明

**多头持仓量** = 区间内所有买单的成交量 + 之前遗留的未平仓的买单
**空头持仓量** = 区间内所有卖单的成交量 + 之前遗留的未平仓的卖单

## 计算逻辑

### 公式

```
pre_long_qty = initial_long_qty + buy_volume
pre_short_qty = initial_short_qty + sell_volume

其中：
- initial_long_qty: 区间开始时的多头持仓（之前遗留的未平仓的买单）
- initial_short_qty: 区间开始时的空头持仓（之前遗留的未平仓的卖单）
- buy_volume: 区间内所有 BUY 订单的成交量
- sell_volume: 区间内所有 SELL 订单的成交量
```

### 计算步骤

1. **获取区间开始时的持仓**（之前遗留的未平仓持仓）
   - 查询持仓表，找到区间开始时间之前最后一次持仓更新
   - 分别统计多头和空头持仓

2. **统计区间内所有成交记录**
   - 查询成交表，统计区间内所有 BUY 订单的成交量
   - 查询成交表，统计区间内所有 SELL 订单的成交量

3. **计算总持仓量**
   - 多头持仓量 = 区间开始时多头持仓 + 区间内所有 BUY 订单的成交量
   - 空头持仓量 = 区间开始时空头持仓 + 区间内所有 SELL 订单的成交量

4. **计算持仓市值**
   - 使用区间内成交的加权平均价格
   - 多头持仓市值 = 区间开始时多头持仓市值 + (区间内 BUY 成交量 × 平均买入价格)
   - 空头持仓市值 = 区间开始时空头持仓市值 + (区间内 SELL 成交量 × 平均卖出价格)

## 数据表结构

### Binance

**成交表**: `binance_trade_update`
- `side`: BUY/SELL
- `quantity`: 成交数量
- `price`: 成交价格
- `transaction_time`: 交易时间
- `symbol`: 交易对
- `account_id`: 账号ID

**持仓表**: `binance_account_update`
- `position_side`: LONG/SHORT
- `position_amount`: 持仓数量
- `entry_price`: 开仓均价
- `event_time`: 事件时间
- `symbol`: 交易对
- `account_id`: 账号ID

### XT

**成交表**: `xt_trade_update`
- `side`: BUY/SELL
- `quantity`: 成交数量
- `price`: 成交价格
- `update_time`: 更新时间
- `symbol`: 交易对
- `account_id`: 账号ID

**持仓表**: `xt_position_update`
- `side`: LONG/SHORT
- `quantity`: 持仓数量
- `entry_price`: 开仓均价
- `update_time`: 更新时间
- `symbol`: 交易对
- `account_id`: 账号ID

## 使用示例

### Binance

```python
from datetime import datetime, timedelta
from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator

db_manager = DatabaseManager()
async with db_manager.session() as session:
    calculator = PositionCalculator(
        session,
        exchange="binance",
        account_id="binance_main_001"
    )
    
    # 计算过去24小时的持仓量
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=24)
    
    metrics = await calculator.calculate_position_from_trades(
        start_time=start_time,
        end_time=end_time,
        symbol=None  # 如果不指定，统计所有交易对
    )
    
    print(f"多头持仓量: {metrics['pre_long_qty']}")
    print(f"空头持仓量: {metrics['pre_short_qty']}")
    print(f"多头持仓市值: {metrics['pre_long_value']}")
    print(f"空头持仓市值: {metrics['pre_short_value']}")
    print(f"区间内 BUY 成交量: {metrics['buy_volume']}")
    print(f"区间内 SELL 成交量: {metrics['sell_volume']}")
    print(f"区间开始时多头持仓: {metrics['initial_long_qty']}")
    print(f"区间开始时空头持仓: {metrics['initial_short_qty']}")
```

### XT

```python
calculator = PositionCalculator(
    session,
    exchange="xt",
    account_id="xt_main_001"
)

metrics = await calculator.calculate_position_from_trades(
    start_time=start_time,
    end_time=end_time
)
```

## 注意事项

### 1. 买单和卖单的含义

在永续合约中：
- **BUY 订单**：可能是开多（增加多头持仓）或平空（减少空头持仓）
- **SELL 订单**：可能是开空（增加空头持仓）或平多（减少多头持仓）

**当前实现**：
- 将所有 BUY 订单的成交量计入多头持仓量
- 将所有 SELL 订单的成交量计入空头持仓量

**如果需要更精确的计算**，可以根据 `position_side` 字段判断：
- BUY + LONG position_side = 开多（增加多头持仓）
- SELL + LONG position_side = 平多（减少多头持仓）
- BUY + SHORT position_side = 平空（减少空头持仓）
- SELL + SHORT position_side = 开空（增加空头持仓）

### 2. 区间开始时的持仓

- 如果区间开始之前没有持仓记录，`initial_long_qty` 和 `initial_short_qty` 为 0
- 这是正确的行为：如果之前没有持仓，就从 0 开始计算

### 3. 数据完整性

- 确保 WebSocket 连接稳定，避免成交记录丢失
- 如果成交记录不完整，计算结果会不准确

### 4. 时间范围

- 使用 UTC 时间，确保跨时区一致性
- `start_time` 和 `end_time` 应该是 UTC 时间

## 与快照方法的对比

| 特性 | 基于成交记录 | 基于快照 |
|------|------------|---------|
| 计算方式 | 成交记录 + 初始持仓 | 快照时刻的持仓 |
| 实时性 | ✅ 每次成交都有记录 | ⚠️ 定时快照 |
| 准确性 | ✅ 不会丢失交易 | ❌ 可能丢失快照间隔内的交易 |
| 复杂度 | ⚠️ 需要统计成交记录 | ✅ 直接查询快照 |
| 适用场景 | ✅ 需要精确统计区间内交易 | ✅ 需要某个时间点的持仓状态 |

## 相关文件

- `src/tri_arb/services/position_calculator.py` - 持仓量计算器实现
- `src/tri_arb/storage/models.py` - Binance 数据模型
- `src/tri_arb/storage/xt_websocket_models.py` - XT 数据模型

