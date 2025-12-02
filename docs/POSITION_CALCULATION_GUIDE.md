# 昨日持仓计算指南

本文档说明如何计算昨日持仓量（pre_long_qty, pre_short_qty）和昨日持仓市值（pre_long_value, pre_short_value）。

## ⚠️ 重要：数据源选择

### 快照表 vs WebSocket 数据

**快照表（Snapshot）的潜在问题**：

1. **可能丢失交易**：
   - 如果快照间隔是5分钟，在这5分钟内发生的多次交易只会看到**最终结果**
   - 无法追踪中间的交易过程
   - 如果快照任务失败或延迟，可能会丢失数据

2. **时间精度问题**：
   - 只能知道快照时刻的持仓状态
   - 无法知道具体在哪个时间点发生了交易

3. **数据完整性**：
   - 依赖定时任务的稳定性
   - 如果任务停止，数据就会缺失

**WebSocket 数据的优势**：

1. ✅ **实时性**：每次仓位变化都会立即推送并保存
2. ✅ **完整性**：记录所有交易事件，不会丢失
3. ✅ **准确性**：反映真实的仓位变化历史
4. ✅ **可追溯性**：可以追踪每次仓位变化的详细时间

## 推荐方案

### Binance

**推荐使用：WebSocket 数据（`binance_account_update` 表）**

- **表名**: `binance_account_update`
- **模型**: `AccountUpdate` (来自 `models.py`)
- **字段**:
  - `position_amount`: 持仓数量
  - `entry_price`: 开仓均价
  - `unrealized_pnl`: 未实现盈亏
  - `event_time`: 事件时间（精确到毫秒）
- **计算 notional**: `notional = position_amount × entry_price`

**不推荐：快照表（`binance_position_snapshot`）**
- ❌ 可能丢失快照间隔内的交易
- ❌ 时间精度不够
- ❌ 依赖定时任务稳定性

### XT

**推荐使用：WebSocket 数据**

- **表名**: `xt_position_update`
- **模型**: `XTPositionUpdate` (来自 `xt_websocket_models.py`)
- **优势**:
  - ✅ 实时性好：每次仓位变化都会立即推送并保存
  - ✅ 数据准确：反映真实的仓位变化历史
  - ✅ 已有现成工具：`XTPositionCalculator` 类已实现

**备选：REST API 快照数据**

- **表名**: `xt_position_snapshot`
- **模型**: `XTPerpPosition` (来自 `xt_rest_models.py`)
- **使用场景**: 当 WebSocket 数据不可用时作为备选

## 计算逻辑

### 1. 查询昨日持仓快照（WebSocket 数据）

查询目标时间点（如24小时前）之前最近的持仓记录：

```python
from datetime import datetime, timedelta
from sqlalchemy import select, func
from tri_arb.storage.models import AccountUpdate

# 计算目标时间（24小时前）
target_date = datetime.utcnow() - timedelta(hours=24)

# 子查询：找到每个 symbol+position_side 组合在目标时间之前的最新记录
subquery = (
    select(
        AccountUpdate.symbol,
        AccountUpdate.position_side,
        func.max(AccountUpdate.event_time).label('max_time')
    )
    .where(AccountUpdate.event_time <= target_date)
    .where(AccountUpdate.event_type == 'POSITION_UPDATE')  # 只查询持仓更新
    .where(AccountUpdate.account_id == account_id)  # 过滤账号
    .where(AccountUpdate.position_amount != 0)  # 只查询有持仓的记录
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
    .where(AccountUpdate.account_id == account_id)
)
```

### 2. 计算持仓量和市值

```python
from decimal import Decimal

pre_long_qty = Decimal("0")
pre_short_qty = Decimal("0")
pre_long_value = Decimal("0")
pre_short_value = Decimal("0")

for pos in positions:
    side = pos.position_side.upper()  # LONG 或 SHORT
    quantity = abs(pos.position_amount)  # 取绝对值
    entry_price = pos.entry_price or Decimal("0")
    
    # 计算名义价值（notional）
    notional = quantity * entry_price
    
    if side == "LONG":
        pre_long_qty += quantity
        pre_long_value += notional
    elif side == "SHORT":
        pre_short_qty += quantity
        pre_short_value += notional
```

### 3. 使用现有工具（XT）

对于 XT，可以直接使用 `XTPositionCalculator`：

```python
from tri_arb.services.xt_position_calculator import XTPositionCalculator
from tri_arb.storage.database import DatabaseManager

db_manager = DatabaseManager()
async with db_manager.session() as session:
    calculator = XTPositionCalculator(session, account_id="xt_main_001")
    
    # 使用 WebSocket 数据（推荐）
    metrics = await calculator.calculate_pre_position_metrics_from_websocket(
        hours_back=24
    )
    
    pre_long_qty = metrics["pre_long_qty"]
    pre_short_qty = metrics["pre_short_qty"]
    pre_long_value = metrics["pre_long_value"]
    pre_short_value = metrics["pre_short_value"]
```

## 实现示例

### Binance 持仓计算器（使用 WebSocket 数据）

```python
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from tri_arb.storage.models import AccountUpdate

class BinancePositionCalculator:
    """Binance 持仓计算器（使用 WebSocket 数据）.
    
    推荐使用 WebSocket 数据而不是快照数据，因为：
    1. 实时性好：每次仓位变化都会立即推送并保存
    2. 完整性：记录所有交易事件，不会丢失
    3. 准确性：反映真实的仓位变化历史
    """
    
    def __init__(self, db_session: AsyncSession, account_id: Optional[str] = None):
        self.db_session = db_session
        self.account_id = account_id
    
    async def calculate_pre_position_metrics(
        self,
        target_date: Optional[datetime] = None,
        hours_back: int = 24
    ) -> Dict[str, Decimal]:
        """计算昨日持仓指标（使用 WebSocket 数据）.
        
        Args:
            target_date: 目标日期（UTC时间），如果为None则使用当前时间减去hours_back小时
            hours_back: 往前回溯的小时数（默认24小时，即昨日）
        
        Returns:
            字典，包含以下指标：
            - pre_long_qty: 昨日多头持仓量（所有symbol的多头持仓量之和）
            - pre_short_qty: 昨日空头持仓量（所有symbol的空头持仓量之和）
            - pre_long_value: 昨日多头持仓市值（所有symbol的多头持仓市值之和）
            - pre_short_value: 昨日空头持仓市值（所有symbol的空头持仓市值之和）
        """
        if target_date is None:
            target_date = datetime.utcnow() - timedelta(hours=hours_back)
        
        # 查询昨日持仓快照（使用 WebSocket 数据）
        subquery = (
            select(
                AccountUpdate.symbol,
                AccountUpdate.position_side,
                func.max(AccountUpdate.event_time).label('max_time')
            )
            .where(AccountUpdate.event_time <= target_date)
            .where(AccountUpdate.event_type == 'POSITION_UPDATE')
            .where(AccountUpdate.exchange == 'binance_perp')
            .where(AccountUpdate.position_amount != 0)
        )
        if self.account_id:
            subquery = subquery.where(AccountUpdate.account_id == self.account_id)
        
        subquery = subquery.group_by(
            AccountUpdate.symbol, 
            AccountUpdate.position_side
        ).subquery()
        
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
        )
        if self.account_id:
            query = query.where(AccountUpdate.account_id == self.account_id)
        
        result = await self.db_session.execute(query)
        positions = result.scalars().all()
        
        # 计算指标
        pre_long_qty = Decimal("0")
        pre_short_qty = Decimal("0")
        pre_long_value = Decimal("0")
        pre_short_value = Decimal("0")
        
        for pos in positions:
            side = pos.position_side.upper()
            quantity = abs(pos.position_amount)  # 取绝对值
            entry_price = pos.entry_price or Decimal("0")
            
            # 计算名义价值（notional = quantity × entry_price）
            notional = quantity * entry_price
            
            if side == "LONG":
                pre_long_qty += quantity
                pre_long_value += notional
            elif side == "SHORT":
                pre_short_qty += quantity
                pre_short_value += notional
        
        return {
            "pre_long_qty": pre_long_qty,
            "pre_short_qty": pre_short_qty,
            "pre_long_value": pre_long_value,
            "pre_short_value": pre_short_value,
        }
```

## 注意事项

1. **时间精度**: 使用 UTC 时间，确保跨时区一致性
2. **数据完整性**: 确保 WebSocket 连接稳定，实时保存所有持仓变化
3. **多账号支持**: 通过 `account_id` 过滤，确保计算的是指定账号的数据
4. **空值处理**: 对于 `entry_price` 为空的情况，使用备选计算方式
5. **持仓方向**: SHORT 持仓的 `position_amount` 可能是负数，计算时使用 `abs()` 取绝对值
6. **WebSocket 连接状态**: 确保 WebSocket 服务正常运行，避免数据丢失

## 快照表的适用场景

快照表（`binance_position_snapshot`）适合以下场景：

1. **数据验证**：作为 WebSocket 数据的补充验证
2. **历史分析**：需要定期快照进行趋势分析
3. **容灾备份**：当 WebSocket 数据丢失时作为备选
4. **性能优化**：对于不需要实时性的分析场景

但对于**精确计算昨日持仓**的场景，**强烈推荐使用 WebSocket 数据**。

## 相关文件

- `src/tri_arb/services/xt_position_calculator.py` - XT 持仓计算器实现
- `src/tri_arb/storage/models.py` - Binance WebSocket 数据模型
- `src/tri_arb/storage/exchange_rest_models.py` - Binance 持仓快照模型
- `src/tri_arb/storage/xt_websocket_models.py` - XT WebSocket 持仓模型
- `src/tri_arb/storage/xt_rest_models.py` - XT REST API 持仓模型
