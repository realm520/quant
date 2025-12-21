# 真实消息队列性能测试

## 脚本说明

`test_real_trade_queue.py` - 从真实的 WebSocket 消息中测试消息队列性能

### 特点

- ✅ **真实消息接收**：从实际的 XT WebSocket 订阅成交消息
- ✅ **真实延迟记录**：记录实际的消息接收时间和处理延迟
- ✅ **测试表写入**：数据写入 `xt_trade_update_test` 表，不影响正式数据
- ✅ **批量写入**：使用消息队列和批量写入，模拟真实场景

## 使用方法

### 基本使用

```bash
# 测试 5 分钟（默认）
python3 scripts/test_real_trade_queue.py

# 测试 10 分钟
python3 scripts/test_real_trade_queue.py --duration 600

# 指定账号
python3 scripts/test_real_trade_queue.py --account-id account_008

# 指定配置文件
python3 scripts/test_real_trade_queue.py --config config/accounts_test.json
```

### 参数说明

- `--config`: 配置文件路径（默认: `config/accounts.json`）
- `--account-id`: 账号ID（可选，不指定则使用第一个启用的账号）
- `--duration`: 测试持续时间（秒，默认: 300，即5分钟）
- `--channels`: 订阅的频道（默认: `trade`）

## 测试流程

1. **连接 WebSocket**：订阅真实的成交消息
2. **记录接收时间**：每条消息到达时记录 `message_received_at`
3. **放入队列**：消息放入队列，不阻塞接收
4. **批量写入**：后台任务批量写入测试表
5. **记录延迟**：记录所有延迟指标

## 查看测试结果

### 1. 运行分析脚本

```bash
python3 scripts/analyze_queue_performance.py
```

### 2. 直接查询数据库

```sql
-- 查看最近的测试数据
SELECT 
    trade_id,
    symbol,
    message_received_at,
    queue_wait_time_ms,
    processing_duration_ms,
    database_write_duration_ms,
    delay_from_timestamp_ms,
    created_at
FROM xt_trade_update_test
ORDER BY created_at DESC
LIMIT 20;

-- 统计延迟情况
SELECT 
    COUNT(*) as total,
    AVG(queue_wait_time_ms) as avg_queue_wait,
    MAX(queue_wait_time_ms) as max_queue_wait,
    AVG(processing_duration_ms) as avg_processing,
    AVG(database_write_duration_ms) as avg_db_write,
    AVG(delay_from_timestamp_ms) as avg_timestamp_delay
FROM xt_trade_update_test
WHERE created_at >= NOW() - INTERVAL '1 hour';
```

## 与模拟测试的区别

| 特性 | 模拟测试 | 真实测试 |
|------|---------|---------|
| 消息来源 | 脚本生成 | 真实 WebSocket |
| 接收速度 | 可控制（912条/秒） | 实际速度（可能更慢） |
| 延迟数据 | 模拟 | 真实 |
| 适用场景 | 压力测试 | 真实场景验证 |

## 注意事项

1. **测试表已创建**：确保已执行 `create_test_tables.sql`
2. **不影响正式数据**：数据只写入测试表，不会写入正式表
3. **测试时间**：建议测试至少 5-10 分钟，获取足够的样本
4. **消息频率**：真实的消息接收速度取决于实际交易频率

## 预期结果

根据真实场景，预期：
- **消息接收速度**：取决于实际交易频率（可能比模拟测试慢）
- **队列等待时间**：应该比模拟测试更合理（因为接收速度更慢）
- **数据库写入性能**：可以验证批量写入的实际效果

## 优化建议

根据真实测试结果，可以：
1. 调整批量大小（`_batch_size`）
2. 调整批量超时（`_batch_timeout`）
3. 优化数据库写入方式
4. 调整队列大小（`maxsize`）
