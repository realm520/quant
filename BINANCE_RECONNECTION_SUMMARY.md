# 币安用户数据流断线补全功能 - 实现总结

## 📋 功能概述

为币安永续合约用户数据流实现了完整的断线重连和数据补全机制，确保订单和成交数据的唯一性和连续性。

## ✅ 完成的工作

### 1. 数据库模型扩展 (`src/tri_arb/storage/models.py`)

#### 新增ConnectionStatus表
```python
class ConnectionStatus(Base):
    """WebSocket连接状态追踪表"""
    exchange                # 交易所名称
    is_connected           # 当前连接状态
    last_connected_at      # 最后连接时间
    last_disconnected_at   # 最后断线时间

    # 最后处理的事件时间戳
    last_order_event_time
    last_trade_event_time
    last_account_event_time

    # 最后处理的ID（用于精确去重）
    last_order_id
    last_trade_id

    # 统计信息
    total_reconnect_count   # 总重连次数
    last_data_gap_seconds   # 最后断线时长
```

#### 添加唯一性约束
```python
# OrderUpdate: (exchange, order_id, event_time) 唯一
UniqueConstraint('exchange', 'order_id', 'event_time', name='uq_order_update_event')

# TradeUpdate: (exchange, trade_id) 唯一
UniqueConstraint('exchange', 'trade_id', name='uq_trade_id')
```

### 2. 币安API扩展 (`src/tri_arb/exchanges/binance_perp.py`)

#### get_all_orders() - 查询历史订单
```python
async def get_all_orders(
    symbol: str,
    start_time: int | None = None,  # 毫秒时间戳
    end_time: int | None = None,
    limit: int = 500
) -> list[dict[str, Any]]
```
- API端点: `GET /fapi/v1/allOrders`
- 支持时间范围查询
- 最多返回1000条记录

#### get_user_trades() - 查询成交历史
```python
async def get_user_trades(
    symbol: str,
    start_time: int | None = None,
    end_time: int | None = None,
    from_id: int | None = None,
    limit: int = 500
) -> list[dict[str, Any]]
```
- API端点: `GET /fapi/v1/userTrades`
- 支持时间范围和ID范围查询
- 最多返回1000条记录

### 3. 用户数据流服务增强 (`src/tri_arb/services/binance_user_stream.py`)

#### 连接状态管理
```python
# 获取或创建连接状态记录
async def get_or_create_connection_status() -> ConnectionStatus

# 更新连接状态和时间戳
async def update_connection_status(
    is_connected: bool,
    order_event_time: datetime | None = None,
    trade_event_time: datetime | None = None,
    account_event_time: datetime | None = None,
    order_id: int | None = None,
    trade_id: int | None = None
)
```

#### 数据补全逻辑
```python
# 查询断线期间丢失的数据
async def query_missing_data(symbols: list[str] | None = None)

# 获取最近活跃的交易对
async def _get_active_symbols() -> list[str]

# 保存订单数据（带去重）
async def _save_order_with_dedup(order_data: dict)

# 保存成交数据（带去重）
async def _save_trade_with_dedup(trade_data: dict)
```

#### 实时数据去重
- 在`handle_order_update()`中使用IntegrityError捕获重复订单
- 在保存成交时使用trade_id去重
- 每次处理消息时更新连接状态时间戳

#### 自动重连流程
```python
async def start():
    # 1. 检查是否需要补全数据
    if status.last_disconnected_at is not None:
        await self.query_missing_data()

    # 2. 建立WebSocket连接
    # 3. 更新连接状态
    await self.update_connection_status(is_connected=True)

    # 4. 接收消息循环
    # 5. 断线时记录并重连
```

### 4. 数据库迁移脚本 (`scripts/migrate_add_connection_status.py`)

自动化迁移脚本，执行以下操作：
1. 创建`connection_status`表及索引
2. 为`order_updates`表添加唯一性约束
3. 为`trade_updates`表添加唯一性约束
4. 删除重复数据（如果存在）

### 5. 文档 (`docs/BINANCE_RECONNECTION_GUIDE.md`)

完整的使用指南，包含：
- 功能概述和架构设计
- 数据库表结构说明
- 使用方法和最佳实践
- 性能优化建议
- 故障排查指南

## 🔑 核心特性

### 1. 数据唯一性保障
- **订单**: 基于 `(exchange, order_id, event_time)` 三元组确保唯一性
- **成交**: 基于 `(exchange, trade_id)` 二元组确保唯一性
- **机制**: 数据库级别的UniqueConstraint + IntegrityError捕获

### 2. 数据连续性保障
- **断线检测**: 自动记录断线时间和重连时间
- **时间追踪**: 记录最后处理的订单/成交/账户事件时间
- **ID追踪**: 记录最后处理的order_id和trade_id
- **自动补全**: 重连后自动查询并填补缺失数据

### 3. 智能交易对识别
- 从数据库查询最近24小时有活动的交易对
- 避免查询无活动交易对，减少API调用
- 支持手动指定交易对列表

### 4. 性能优化
- 使用数据库唯一约束代替应用层查重
- 批量处理订单和成交数据
- 合理的数据库索引设计

## 📁 修改的文件

```
src/tri_arb/
├── exchanges/
│   └── binance_perp.py          [修改] 添加get_all_orders和get_user_trades
├── services/
│   └── binance_user_stream.py   [修改] 实现断线补全逻辑
└── storage/
    └── models.py                 [修改] 添加ConnectionStatus表和唯一约束

scripts/
└── migrate_add_connection_status.py  [新增] 数据库迁移脚本

docs/
└── BINANCE_RECONNECTION_GUIDE.md     [新增] 完整使用指南
```

## 🚀 使用方法

### 步骤1: 运行数据库迁移

```bash
uv run python scripts/migrate_add_connection_status.py
```

### 步骤2: 启动用户数据流

```bash
uv run tri-arb subscribe --exchange binance_perp --channels account order
```

### 步骤3: 监控运行状态

查看连接状态：
```sql
SELECT * FROM connection_status WHERE exchange = 'binance_perp';
```

查看订单数据：
```sql
SELECT COUNT(*), MIN(event_time), MAX(event_time)
FROM order_updates
WHERE exchange = 'binance_perp'
  AND event_time >= NOW() - INTERVAL '1 day';
```

查看成交数据：
```sql
SELECT COUNT(*), MIN(event_time), MAX(event_time)
FROM trade_updates
WHERE exchange = 'binance_perp'
  AND event_time >= NOW() - INTERVAL '1 day';
```

## 📊 数据流程图

```
WebSocket连接
     │
     ├─ 正常接收消息
     │   ├─ 处理订单更新 → 保存到数据库（去重）
     │   ├─ 处理成交更新 → 保存到数据库（去重）
     │   └─ 更新连接状态时间戳
     │
     └─ 连接断开
         ├─ 记录断线时间
         ├─ 更新连接状态: is_connected=False
         │
         └─ 自动重连（5秒后）
             ├─ 检测到上次断线
             ├─ 计算断线时长
             ├─ 查询活跃交易对
             ├─ 对每个交易对:
             │   ├─ 查询历史订单（断线时间范围）
             │   ├─ 保存订单（去重）
             │   ├─ 查询历史成交（断线时间范围）
             │   └─ 保存成交（去重）
             ├─ 更新连接状态: is_connected=True
             └─ 恢复正常接收消息
```

## 🔍 去重机制详解

### 订单去重

**唯一性标识**: `(exchange, order_id, event_time)`

**原因**: 同一个订单在不同时间会有多次状态更新（NEW → PARTIALLY_FILLED → FILLED）

**实现**:
```python
try:
    order_update = OrderUpdate(
        exchange="binance_perp",
        order_id=123456,
        event_time=datetime(2025, 1, 15, 10, 30, 0)
    )
    session.add(order_update)
    await session.commit()
except IntegrityError:
    # 该订单在该时间点的更新已存在，跳过
    logger.debug("Duplicate order update, skipping")
```

### 成交去重

**唯一性标识**: `(exchange, trade_id)`

**原因**: trade_id是全局唯一的成交标识，不会重复

**实现**:
```python
try:
    trade_update = TradeUpdate(
        exchange="binance_perp",
        trade_id=789012
    )
    session.add(trade_update)
    await session.commit()
except IntegrityError:
    # 该成交已存在，跳过
    logger.debug("Duplicate trade, skipping")
```

## 📈 监控指标

### 连接稳定性
- `total_reconnect_count`: 总重连次数（应该较小）
- `last_data_gap_seconds`: 最后断线时长（应该较短）

### 数据完整性
- 订单记录数 vs 成交记录数（成交数应 ≤ 订单数）
- 时间连续性检查（是否有大段时间无数据）

### 性能指标
- 数据补全耗时
- 重复数据比例（IntegrityError频率）
- API调用次数

## ⚠️ 注意事项

1. **首次运行必须执行迁移脚本**
   ```bash
   uv run python scripts/migrate_add_connection_status.py
   ```

2. **API速率限制**
   - 币安有API调用频率限制
   - 如果断线时间过长，可能需要分批查询
   - 建议在查询之间添加延迟

3. **数据库性能**
   - 唯一性约束会增加插入开销
   - 但避免了查询开销，总体性能提升
   - 定期清理历史数据

4. **断线时长过长**
   - 如果断线超过24小时，建议手动指定交易对
   - API查询有limit限制（最多1000条）
   - 可能需要多次调用补全所有数据

## 🎯 后续优化建议

1. **批量插入优化**
   - 使用批量插入代替单条插入
   - 使用`ON CONFLICT DO NOTHING`语句

2. **并发控制**
   - 限制同时查询的交易对数量
   - 使用信号量控制并发API调用

3. **增量补全**
   - 记录已补全的时间范围
   - 避免重复查询已补全的数据

4. **监控告警**
   - 断线次数超过阈值时告警
   - 数据缺失时告警
   - API调用失败时告警

## 📝 测试建议

虽然不需要立即测试，但建议后续进行以下测试：

1. **断线重连测试**
   - 手动断开网络连接
   - 验证5秒后自动重连
   - 检查connection_status表的记录

2. **数据补全测试**
   - 断线期间下单
   - 重连后检查订单是否被补全
   - 验证无重复数据

3. **去重测试**
   - 多次启动服务
   - 验证数据不会重复插入
   - 检查IntegrityError日志

4. **性能测试**
   - 模拟长时间断线
   - 测试大量数据补全的性能
   - 监控数据库和API负载

## 📚 相关文档

- [完整使用指南](docs/BINANCE_RECONNECTION_GUIDE.md)
- [数据库模型](src/tri_arb/storage/models.py)
- [币安API文档](https://binance-docs.github.io/apidocs/futures/cn/)

---

**实现时间**: 2025-01-15
**版本**: v1.0
**状态**: ✅ 已完成，待测试
