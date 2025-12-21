# XT 数据库写入优化方案

## 问题分析

### 当前实现的问题

1. **串行处理消息**
   ```python
   async for message in self.websocket:
       await self._handle_message(message)  # 必须等待完成
   ```

2. **同步数据库写入**
   ```python
   await session.commit()  # 阻塞，等待数据库写入完成
   ```

3. **累积延迟**
   - 如果每条消息写入耗时 100ms
   - 处理 100 条消息需要 10 秒
   - 导致消息积压，延迟越来越大

### 延迟影响

- **实时性下降**：消息处理延迟，数据不实时
- **内存占用**：消息积压占用内存
- **数据库压力**：频繁的小事务增加数据库负载

## 优化方案

### 方案 1: 批量写入（推荐，简单有效）

**原理**：收集多条消息后批量提交，减少数据库往返次数

**优点**：
- 实现简单，改动小
- 显著减少数据库写入次数
- 提高写入效率

**缺点**：
- 需要缓冲消息（少量内存）
- 可能丢失最后一批未提交的数据（如果程序崩溃）

**实现思路**：
```python
# 在类中初始化
self._trade_buffer = []
self._buffer_size = 10  # 每 10 条消息批量写入
self._buffer_timeout = 1.0  # 或每 1 秒写入一次

# 在 _save_trade_update 中
self._trade_buffer.append(record)
if len(self._trade_buffer) >= self._buffer_size:
    await self._flush_trade_buffer()

# 后台任务定期刷新
async def _periodic_flush(self):
    while self.is_running:
        await asyncio.sleep(self._buffer_timeout)
        if self._trade_buffer:
            await self._flush_trade_buffer()
```

### 方案 2: 消息队列 + 后台写入（更彻底）

**原理**：使用异步队列，消息接收和数据库写入分离

**优点**：
- 完全解耦消息接收和数据库写入
- 消息接收不阻塞
- 可以控制写入速度

**缺点**：
- 实现复杂，需要管理队列和后台任务
- 需要处理队列溢出

**实现思路**：
```python
# 使用已有的 AsyncBoundedQueue
from tri_arb.utils.async_utils import AsyncBoundedQueue

# 初始化
self._trade_queue = AsyncBoundedQueue(maxsize=1000)

# 消息接收：快速放入队列
async def _handle_trade_update(self, data):
    await self._trade_queue.put(data)  # 不阻塞

# 后台任务：从队列取出并写入数据库
async def _trade_writer_task(self):
    batch = []
    while self.is_running:
        try:
            trade_data = await asyncio.wait_for(
                self._trade_queue.get(), 
                timeout=1.0
            )
            batch.append(trade_data)
            
            if len(batch) >= 10:  # 批量写入
                await self._save_trade_batch(batch)
                batch = []
        except asyncio.TimeoutError:
            if batch:  # 超时也写入
                await self._save_trade_batch(batch)
                batch = []
```

### 方案 3: 异步写入（最简单，但可能丢数据）

**原理**：使用 `asyncio.create_task` 后台写入，不等待完成

**优点**：
- 实现最简单
- 消息接收完全不阻塞

**缺点**：
- 可能丢失数据（如果程序崩溃）
- 无法控制写入速度
- 可能导致数据库连接池耗尽

**不推荐使用**

## 推荐实施方案

### 阶段 1: 批量写入（立即实施）

1. 添加缓冲区
2. 批量提交（每 10 条或每 1 秒）
3. 程序退出时刷新缓冲区

### 阶段 2: 消息队列（如果需要）

如果批量写入还不够，再实施消息队列方案。

## 性能预期

### 当前性能
- 每条消息：~100ms（包含数据库写入）
- 100 条消息：~10 秒

### 批量写入后
- 每 10 条消息：~150ms（一次批量写入）
- 100 条消息：~1.5 秒（提升 6-7 倍）

### 消息队列后
- 消息接收：几乎不耗时（只放入队列）
- 数据库写入：后台异步进行
- 100 条消息：消息接收 < 1 秒

## 注意事项

1. **数据一致性**：批量写入时，如果程序崩溃，可能丢失最后一批数据
2. **内存使用**：缓冲区会占用内存，需要设置合理的缓冲区大小
3. **数据库连接**：确保数据库连接池足够大
4. **监控**：添加监控，观察缓冲区大小和写入延迟
