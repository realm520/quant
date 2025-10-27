# 币安用户数据流断线重连与数据补全指南

## 概述

本文档介绍币安永续合约用户数据流的断线重连和数据补全功能。该功能确保在WebSocket连接意外断开后，能够自动重连并补全断线期间丢失的订单和成交数据，保证数据的完整性和连续性。

## 核心特性

### 1. 自动断线检测
- 实时监控WebSocket连接状态
- 记录断线时间和重连时间
- 统计断线时长和重连次数

### 2. 数据补全机制
- 断线重连后自动查询缺失数据
- 支持订单和成交数据的完整恢复
- 智能识别活跃交易对

### 3. 数据去重保障
- 数据库级别的唯一性约束
- 订单：基于 `(exchange, order_id, event_time)` 去重
- 成交：基于 `(exchange, trade_id)` 去重
- 使用IntegrityError捕获重复插入

### 4. 状态追踪
- 记录最后处理的订单时间和ID
- 记录最后处理的成交时间和ID
- 记录最后处理的账户更新时间
- 统计总重连次数和数据间隙

## 数据库架构

### ConnectionStatus表

```sql
CREATE TABLE connection_status (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL UNIQUE,              -- 交易所名称
    is_connected BOOLEAN DEFAULT FALSE,                -- 当前连接状态
    last_connected_at TIMESTAMP,                       -- 最后连接时间
    last_disconnected_at TIMESTAMP,                    -- 最后断线时间

    -- 最后处理的事件时间戳
    last_order_event_time TIMESTAMP,                   -- 最后订单事件
    last_trade_event_time TIMESTAMP,                   -- 最后成交事件
    last_account_event_time TIMESTAMP,                 -- 最后账户事件

    -- 最后处理的ID
    last_order_id BIGINT,                              -- 最后订单ID
    last_trade_id BIGINT,                              -- 最后成交ID

    -- 统计信息
    total_reconnect_count INTEGER DEFAULT 0,           -- 总重连次数
    last_data_gap_seconds INTEGER,                     -- 最后断线时长(秒)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 唯一性约束

```sql
-- OrderUpdate表唯一性约束
ALTER TABLE order_updates
ADD CONSTRAINT uq_order_update_event
UNIQUE (exchange, order_id, event_time);

-- TradeUpdate表唯一性约束
ALTER TABLE trade_updates
ADD CONSTRAINT uq_trade_id
UNIQUE (exchange, trade_id);
```

## 使用方法

### 1. 运行数据库迁移

首次使用前，需要运行迁移脚本创建ConnectionStatus表并添加唯一性约束：

```bash
# 运行迁移脚本
uv run python scripts/migrate_add_connection_status.py
```

### 2. 启动用户数据流订阅

```bash
# 启动币安永续合约用户数据流
uv run tri-arb subscribe --exchange binance_perp --channels account order
```

### 3. 自动重连流程

当WebSocket连接断开时，系统会：

1. **记录断线时间**
   ```python
   # 自动记录断线时间到数据库
   self.disconnect_time = datetime.now()
   await self.update_connection_status(is_connected=False)
   ```

2. **等待5秒后重连**
   ```python
   if self.auto_reconnect and self.is_running:
       logger.info("Attempting to reconnect in 5 seconds...")
       await asyncio.sleep(5)
       await self.start()
   ```

3. **启动数据补全**
   ```python
   # 检测到上次断线，自动补全数据
   if status.last_disconnected_at is not None and not status.is_connected:
       await self.query_missing_data()
   ```

4. **恢复正常订阅**
   ```python
   # 更新连接状态为已连接
   await self.update_connection_status(is_connected=True)
   ```

## 实现细节

### 1. 历史数据查询API

在 `BinancePerpExchange` 中实现了两个关键方法：

#### get_all_orders()

查询所有订单（包括历史订单）：

```python
async def get_all_orders(
    self,
    symbol: str,
    start_time: int | None = None,  # 毫秒时间戳
    end_time: int | None = None,    # 毫秒时间戳
    limit: int = 500,               # 最多1000
) -> list[dict[str, Any]]:
    """查询所有订单（包括历史订单）."""
```

**API端点**: `GET /fapi/v1/allOrders`

#### get_user_trades()

查询账户成交历史：

```python
async def get_user_trades(
    self,
    symbol: str,
    start_time: int | None = None,  # 毫秒时间戳
    end_time: int | None = None,    # 毫秒时间戳
    from_id: int | None = None,     # Trade ID起点
    limit: int = 500,               # 最多1000
) -> list[dict[str, Any]]:
    """查询账户成交历史."""
```

**API端点**: `GET /fapi/v1/userTrades`

### 2. 数据补全逻辑

#### query_missing_data()

主要补全流程：

```python
async def query_missing_data(self, symbols: list[str] | None = None):
    """查询断线期间丢失的数据并补全到数据库."""

    # 1. 获取连接状态，确定断线时间范围
    status = await self.get_or_create_connection_status()
    start_time = status.last_disconnected_at
    end_time = datetime.now()

    # 2. 获取活跃交易对（如果未指定）
    if symbols is None:
        symbols = await self._get_active_symbols()

    # 3. 对每个交易对查询订单和成交
    for symbol in symbols:
        # 查询订单
        orders = await self.exchange.get_all_orders(
            symbol=symbol,
            start_time=start_time_ms,
            end_time=end_time_ms,
        )

        # 保存订单（带去重）
        for order_data in orders:
            await self._save_order_with_dedup(order_data)

        # 查询成交
        trades = await self.exchange.get_user_trades(
            symbol=symbol,
            start_time=start_time_ms,
            end_time=end_time_ms,
        )

        # 保存成交（带去重）
        for trade_data in trades:
            await self._save_trade_with_dedup(trade_data)
```

#### _get_active_symbols()

自动识别活跃交易对：

```python
async def _get_active_symbols(self) -> list[str]:
    """从数据库中获取最近24小时内有订单或成交的交易对."""

    # 查询最近24小时的交易对
    cutoff_time = datetime.now() - timedelta(hours=24)

    # 从订单表和成交表获取
    symbols = list(set(symbols_from_orders + symbols_from_trades))

    return symbols
```

### 3. 去重机制

#### 订单去重

使用数据库唯一约束 `(exchange, order_id, event_time)`：

```python
async def _save_order_with_dedup(self, order_data: dict):
    """保存订单数据，自动去重（使用数据库唯一约束）."""
    try:
        async with self.db_manager.session() as session:
            order_update = OrderUpdate(...)
            session.add(order_update)
            await session.commit()
    except IntegrityError:
        # 违反唯一性约束，说明记录已存在
        logger.debug(f"Order already exists, skipping")
```

#### 成交去重

使用数据库唯一约束 `(exchange, trade_id)`：

```python
async def _save_trade_with_dedup(self, trade_data: dict):
    """保存成交数据，自动去重（使用数据库唯一约束）."""
    try:
        async with self.db_manager.session() as session:
            trade_update = TradeUpdate(...)
            session.add(trade_update)
            await session.commit()
    except IntegrityError:
        # 违反唯一性约束，说明记录已存在
        logger.debug(f"Trade already exists, skipping")
```

### 4. 实时数据去重

WebSocket实时数据也使用相同的去重机制：

```python
async def handle_order_update(self, event: dict):
    """处理订单更新事件."""
    try:
        async with self.db_manager.session() as session:
            order_update = OrderUpdate(...)
            session.add(order_update)
            await session.commit()
    except IntegrityError:
        logger.debug("Order update duplicate detected, skipping")
```

### 5. 连接状态更新

每次收到消息时更新连接状态：

```python
# 在handle_order_update中
await self.update_connection_status(
    is_connected=True,
    order_event_time=event_time,
    order_id=int(order.get("i", 0)),
    trade_event_time=event_time if has_trade else None,
    trade_id=int(order.get("t", 0)) if has_trade else None,
)

# 在handle_account_update中
await self.update_connection_status(
    is_connected=True,
    account_event_time=event_time,
)
```

## 数据完整性保障

### 1. 时间戳追踪
- **订单**: 记录最后处理的订单事件时间和订单ID
- **成交**: 记录最后处理的成交事件时间和成交ID
- **账户**: 记录最后处理的账户更新时间

### 2. 唯一性约束
- **订单**: `(exchange, order_id, event_time)` 三元组唯一
- **成交**: `(exchange, trade_id)` 二元组唯一

### 3. 断线间隙计算
```python
if status.last_disconnected_at:
    gap_seconds = int((reconnect_time - disconnect_time).total_seconds())
    status.last_data_gap_seconds = gap_seconds
```

### 4. 重连计数
```python
status.total_reconnect_count = (status.total_reconnect_count or 0) + 1
```

## 监控与日志

### 关键日志事件

1. **连接建立**
   ```
   INFO: WebSocket connected successfully
   INFO: Reconnected after disconnection, gap_seconds=120, total_reconnects=3
   ```

2. **断线检测**
   ```
   WARNING: WebSocket connection closed
   WARNING: Connection lost, last_connected_at=2025-01-15 10:30:00
   ```

3. **数据补全**
   ```
   INFO: Starting data recovery, start_time=..., end_time=..., gap_seconds=120
   INFO: Retrieved 15 orders for BTCUSDT
   INFO: Retrieved 8 trades for BTCUSDT
   INFO: Data recovery completed, total_orders=30, total_trades=15
   ```

4. **去重检测**
   ```
   DEBUG: Order 123456 at 2025-01-15 10:31:00 already exists (IntegrityError), skipping
   DEBUG: Trade 789012 already exists (IntegrityError), skipping
   ```

## 性能优化

### 1. 批量查询
- 每个交易对最多查询500条订单/成交（可调整为1000）
- 支持时间范围过滤，减少不必要的查询

### 2. 数据库索引
```sql
-- 订单索引
CREATE INDEX idx_order_id_event_time ON order_updates (order_id, event_time);
CREATE INDEX idx_exchange_symbol_time ON order_updates (exchange, symbol, event_time);

-- 成交索引
CREATE INDEX idx_symbol_trade_time ON trade_updates (symbol, transaction_time);
CREATE INDEX idx_order_trade ON trade_updates (order_id, trade_id);

-- 连接状态索引
CREATE INDEX idx_exchange_connected ON connection_status (exchange, is_connected);
```

### 3. 智能交易对选择
- 仅查询最近24小时内有活动的交易对
- 避免查询无活动的交易对，减少API调用

## 故障处理

### 1. 数据补全失败
如果数据补全失败，系统会记录错误但不会中断连接：

```python
try:
    await self.query_missing_data()
except Exception as e:
    logger.error("Failed to recover missing data", error=str(e))
    # 继续连接，不因为数据补全失败而中断
```

### 2. API限流
币安API有速率限制，建议：
- 控制并发查询数量
- 在查询之间添加延迟
- 监控返回的 `429 Too Many Requests` 错误

### 3. 数据库连接失败
- 使用连接池管理数据库连接
- 自动重试失败的数据库操作
- 记录失败的数据插入

## 最佳实践

### 1. 定期检查连接状态
```sql
-- 查询连接状态
SELECT exchange, is_connected, last_disconnected_at,
       total_reconnect_count, last_data_gap_seconds
FROM connection_status
WHERE exchange = 'binance_perp';
```

### 2. 监控数据完整性
```sql
-- 检查订单数据连续性
SELECT symbol, COUNT(*) as order_count,
       MIN(event_time) as first_order,
       MAX(event_time) as last_order
FROM order_updates
WHERE exchange = 'binance_perp'
  AND event_time >= NOW() - INTERVAL '1 day'
GROUP BY symbol;

-- 检查成交数据连续性
SELECT symbol, COUNT(*) as trade_count,
       MIN(event_time) as first_trade,
       MAX(event_time) as last_trade
FROM trade_updates
WHERE exchange = 'binance_perp'
  AND event_time >= NOW() - INTERVAL '1 day'
GROUP BY symbol;
```

### 3. 清理历史数据
```sql
-- 删除30天前的订单更新记录
DELETE FROM order_updates
WHERE exchange = 'binance_perp'
  AND event_time < NOW() - INTERVAL '30 days';

-- 删除30天前的成交记录
DELETE FROM trade_updates
WHERE exchange = 'binance_perp'
  AND event_time < NOW() - INTERVAL '30 days';
```

## 故障排查

### 问题1: 重复数据插入
**症状**: 日志中大量 `IntegrityError` 警告

**原因**:
- 数据补全与实时数据重叠
- 多次运行补全逻辑

**解决**:
- 正常现象，唯一性约束会自动去重
- 如果担心性能，可以在补全前先检查时间范围

### 问题2: 数据缺失
**症状**: 某些订单或成交未记录

**排查**:
1. 检查连接状态表的断线时间
2. 检查日志中的数据补全记录
3. 手动查询API确认数据是否存在

**解决**:
- 手动调用 `query_missing_data(symbols=['BTCUSDT'])`
- 检查API权限和密钥有效性

### 问题3: 连接频繁断开
**症状**: `total_reconnect_count` 持续增加

**排查**:
1. 检查网络连接稳定性
2. 检查ListenKey是否正常keepalive
3. 检查币安API服务状态

**解决**:
- 增加keepalive频率（当前30分钟）
- 检查防火墙和代理设置
- 联系币安技术支持

## 总结

币安用户数据流断线补全功能提供了完整的数据保障机制：

✅ **自动检测断线** - 实时监控连接状态
✅ **自动重连** - 5秒后自动尝试重连
✅ **数据补全** - 查询并恢复断线期间的数据
✅ **去重保障** - 数据库级别的唯一性约束
✅ **状态追踪** - 记录所有关键时间戳和ID
✅ **性能优化** - 智能选择交易对和批量处理

通过这些机制，确保即使在网络不稳定的情况下，也能保证数据的完整性和连续性。
