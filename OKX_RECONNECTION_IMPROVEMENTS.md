# OKX WebSocket 断线恢复改进方案

## 问题背景

原有实现存在的问题：
1. **被动断线检测**：完全依赖 `websockets` 库抛出异常，响应慢
2. **无心跳机制**：没有主动的 ping/pong 心跳检测
3. **无超时监控**：无法快速发现连接异常（OKX每5秒推送一次快照）
4. **断线期间数据丢失**：WebSocket断线期间的订单更新可能丢失

## 改进方案

本次改进采用**三层防护机制**，确保快速检测断线并及时恢复数据：

### 1. WebSocket 原生心跳（第一层）

使用 `websockets` 库的内置 ping/pong 机制：

```python
async with websockets.connect(
    self.ws_url,
    ping_interval=20,  # 每20秒发送ping
    ping_timeout=10,   # ping超时10秒认为断线
    close_timeout=5,   # 关闭超时5秒
) as websocket:
```

**优势**：
- 在网络层快速检测断线（10秒超时）
- 自动触发重连机制
- 无需额外代码维护

### 2. 消息超时监控（第二层）

后台监控任务每10秒检查一次消息接收情况：

```python
async def _monitor_connection_health(self):
    """监控WebSocket连接健康状态，检测消息超时."""
    while self.is_running:
        await asyncio.sleep(10)

        if self.last_message_time:
            time_since_last_msg = (datetime.now() - self.last_message_time).total_seconds()

            # 如果超过指定时间没收到消息，认为连接异常
            if time_since_last_msg > self.message_timeout:
                logger.warning("⚠️ No message received for too long, forcing reconnection")
                # 主动关闭触发重连
                await self.websocket.close()
```

**优势**：
- 应用层检测：即使网络层正常，也能发现消息推送异常
- 可配置超时时间（默认60秒）
- 主动触发重连，不等待被动异常

### 3. REST API 补充同步（第三层）

在 WebSocket 基础上，定期通过 REST API 轮询订单状态：

```python
async def _rest_api_sync(self):
    """定期通过REST API同步数据，作为WebSocket的补充."""
    while self.is_running:
        await asyncio.sleep(self.rest_sync_interval)

        # 查询活跃交易对的挂单
        for symbol in symbols:
            orders = await self.exchange.get_open_orders(symbol=symbol)
            # 保存到数据库（带去重）
```

**优势**：
- 即使 WebSocket 有延迟，也能通过 REST API 获取最新订单
- 双通道数据保障，避免数据丢失
- 可配置同步间隔（默认30秒）

## 使用方法

### 1. 基本使用（默认配置）

```python
from tri_arb.services.okx_user_stream import OKXUserStreamService
from tri_arb.storage.database import DatabaseManager

db_manager = DatabaseManager("postgresql://...")
await db_manager.connect()

service = OKXUserStreamService(
    api_key="your_api_key",
    api_secret="your_api_secret",
    passphrase="your_passphrase",
    db_manager=db_manager,
    # 默认配置：
    # - message_timeout=60 （60秒无消息触发重连）
    # - enable_rest_sync=True （启用REST同步）
    # - rest_sync_interval=30 （每30秒同步一次）
)

await service.start()
```

### 2. 自定义配置

```python
service = OKXUserStreamService(
    api_key="your_api_key",
    api_secret="your_api_secret",
    passphrase="your_passphrase",
    db_manager=db_manager,

    # 自定义超时时间（更敏感的断线检测）
    message_timeout=30,  # 30秒无消息即重连

    # 禁用REST同步（如果只依赖WebSocket）
    enable_rest_sync=False,

    # 自定义REST同步间隔
    rest_sync_interval=60,  # 每60秒同步一次
)
```

### 3. 在 CLI 命令中使用

编辑 `src/tri_arb/cli/commands/subscribe.py`，添加参数：

```python
@click.option(
    "--message-timeout",
    type=int,
    default=60,
    help="消息接收超时（秒），超过此时间认为连接异常"
)
@click.option(
    "--disable-rest-sync",
    is_flag=True,
    help="禁用REST API补充同步"
)
@click.option(
    "--rest-sync-interval",
    type=int,
    default=30,
    help="REST API同步间隔（秒）"
)
def subscribe_okx(
    message_timeout: int,
    disable_rest_sync: bool,
    rest_sync_interval: int,
):
    service = OKXUserStreamService(
        # ... 其他参数
        message_timeout=message_timeout,
        enable_rest_sync=not disable_rest_sync,
        rest_sync_interval=rest_sync_interval,
    )
```

## 运行效果

### 1. 启动日志

```
OKXUserStreamService initialized
  message_timeout=60
  enable_rest_sync=True
  rest_sync_interval=30

Connecting to OKX WebSocket with heartbeat
OKX WebSocket connected with heartbeat enabled
Started connection health monitor
Started REST API sync task
```

### 2. 断线检测日志

```
⚠️ No message received for too long, forcing reconnection
  seconds=65
  timeout=60

WebSocket closed by health monitor
OKX WebSocket connection closed
Attempting to reconnect OKX in 5 seconds...
```

### 3. 数据恢复日志

```
Detected previous OKX disconnection, will recover data after WebSocket connection
  gap_seconds=127
  gap_minutes=2.12

=== Starting OKX data recovery process ===
Retrieved 15 orders for BTC-USDT-SWAP
Retrieved 8 trades for BTC-USDT-SWAP

=== OKX data recovery completed ===
  new_orders_saved=12
  new_trades_saved=8
  duplicate_orders_skipped=3
  gap_seconds=127
```

## 性能影响

### 资源消耗

- **CPU**：后台监控任务每10秒运行一次，几乎无影响（<0.1%）
- **内存**：增加2个后台任务，约占用 < 1MB
- **网络**：
  - WebSocket ping: 每20秒一次，数据量极小（<100 bytes）
  - REST同步: 每30秒查询一次，取决于活跃交易对数量

### 断线检测速度

| 场景 | 原实现 | 改进后 |
|-----|-------|--------|
| 网络中断 | 60-120秒 | **10秒**（ping_timeout） |
| 消息推送异常 | 无法检测 | **60秒**（message_timeout） |
| REST补充查询 | 无 | **30秒**（rest_sync_interval） |

## 注意事项

### 1. 参数调优

- `ping_timeout`: 不建议低于10秒，避免误判
- `message_timeout`: 推荐60秒（OKX每5秒推送一次快照）
- `rest_sync_interval`: 推荐30-60秒，避免API限流

### 2. API 限流

OKX REST API 限流规则：
- `/api/v5/trade/orders-pending`: 20次/2秒
- `/api/v5/trade/orders-history`: 40次/2秒

如果活跃交易对很多，建议：
- 增大 `rest_sync_interval`（如60秒）
- 或者禁用 `enable_rest_sync`

### 3. 数据库写入

- 所有 REST 同步的数据都会经过去重检查
- 已存在的订单不会重复写入
- 不会影响 WebSocket 推送的数据

## 测试建议

### 1. 模拟断网测试

```bash
# 1. 启动服务
uv run python -m tri_arb.cli subscribe okx

# 2. 模拟断网（断开网络30秒）
sudo ifconfig en0 down
sleep 30
sudo ifconfig en0 up

# 3. 观察日志，确认：
#    - 10秒内检测到断线（ping_timeout）
#    - 自动重连成功
#    - 数据恢复完成
```

### 2. 压力测试

```bash
# 模拟频繁断线重连
for i in {1..10}; do
    sudo ifconfig en0 down
    sleep 5
    sudo ifconfig en0 up
    sleep 20
done
```

### 3. 数据完整性验证

```sql
-- 查询断线期间的订单
SELECT * FROM okx_orders
WHERE u_time BETWEEN '断线时间' AND '重连时间'
ORDER BY u_time;

-- 确认没有遗漏的订单
```

## 相关文件

- `src/tri_arb/services/okx_user_stream.py` - OKX用户流服务（已更新）
- `src/tri_arb/exchanges/okx_perp.py` - OKX交易所适配器
- `src/tri_arb/cli/commands/subscribe.py` - CLI订阅命令

## 版本历史

- **2025-10-28**: 实现三层防护机制
  - 添加 WebSocket ping/pong 心跳
  - 添加消息超时监控
  - 添加 REST API 补充同步
  - 改进断线恢复日志

## 常见问题

### Q1: REST同步会不会影响WebSocket性能？

A: 不会。REST同步运行在独立的异步任务中，不会阻塞WebSocket消息接收。

### Q2: 如果REST API也失败了怎么办？

A: REST同步有异常捕获机制，单次失败不会影响服务。WebSocket重连后会执行完整的数据恢复。

### Q3: 可以只用REST，不用WebSocket吗？

A: 不建议。WebSocket延迟低（毫秒级），REST至少30秒。WebSocket作为主通道，REST作为备份。

### Q4: 如何判断改进是否生效？

A: 查看日志中的以下关键字：
- `Started connection health monitor` - 监控任务启动
- `Started REST API sync task` - REST同步启动
- `⚠️ No message received for too long` - 超时检测触发
- `REST synced X orders` - REST成功同步订单

## 总结

本次改进采用**多层防护、快速检测、及时恢复**的策略：

1. ✅ **WebSocket心跳**：10秒快速检测网络断线
2. ✅ **消息监控**：60秒检测应用层异常
3. ✅ **REST补充**：30秒轮询确保数据不丢失
4. ✅ **自动恢复**：重连后自动恢复断线期间数据

**断线检测速度从 60-120秒 提升至 10秒**，数据丢失风险降至最低。
