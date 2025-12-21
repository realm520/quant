# 消息队列性能测试脚本使用说明

## 脚本功能

`test_trade_queue_performance.py` 用于测试成交消息队列的性能，模拟完整的消息接收和数据库写入流程。

## 使用方法

### 基本使用

```bash
# 测试 100 条消息（默认）
python3 scripts/test_trade_queue_performance.py

# 测试 1000 条消息
python3 scripts/test_trade_queue_performance.py --messages 1000

# 自定义批量大小和超时
python3 scripts/test_trade_queue_performance.py --messages 500 --batch-size 20 --batch-timeout 0.5

# 模拟不同的数据库延迟
python3 scripts/test_trade_queue_performance.py --messages 200 --db-delay 0.1
```

### 参数说明

- `--messages`: 要处理的消息数量（默认: 100）
- `--batch-size`: 批量写入大小（默认: 10）
- `--batch-timeout`: 批量写入超时（秒，默认: 1.0）
- `--db-delay`: 模拟数据库写入延迟（秒，默认: 0.05）

## 测试流程

1. **阶段 1: 消息接收**
   - 快速生成消息并放入队列
   - 模拟 WebSocket 消息接收速度

2. **阶段 2: 批量处理**
   - 从队列取出消息
   - 批量写入数据库（每 N 条或每 T 秒）
   - 记录各种延迟指标

3. **统计输出**
   - 队列等待时间统计
   - 数据库写入时间统计
   - 总体性能指标

## 输出示例

```
开始模拟处理 100 条消息...
批量大小: 10, 超时: 1.0秒, 模拟DB延迟: 0.05秒

阶段 1: 模拟消息接收...
✓ 消息接收完成: 100 条消息, 耗时 0.123秒

阶段 2: 模拟批量处理...
  批次 1: 写入 10 条, 耗时 52.34ms, 已处理 10/100
  批次 2: 写入 10 条, 耗时 51.89ms, 已处理 20/100
  ...

============================================================
处理完成统计:
============================================================
总消息数: 100
总批次数: 10
平均每批: 10.0 条

队列等待时间:
  总等待时间: 5234.56ms
  平均等待时间: 52.35ms
  最大等待时间: 156.78ms

数据库写入时间:
  总写入时间: 523.45ms
  平均每批: 52.35ms
  平均每条: 5.23ms
  最大批次耗时: 78.90ms

总处理时间: 0.646秒
消息接收速度: 813.0 条/秒
数据库写入速度: 191.0 条/秒
```

## 查看测试结果

测试数据会写入 `xt_trade_update_test` 表，可以通过 SQL 查询分析：

```sql
-- 查看最近的测试数据
SELECT 
    trade_id,
    message_received_at,
    queue_wait_time_ms,
    delay_from_timestamp_ms,
    created_at
FROM xt_trade_update_test
ORDER BY created_at DESC
LIMIT 20;

-- 统计延迟情况
SELECT 
    AVG(queue_wait_time_ms) as avg_queue_wait,
    MAX(queue_wait_time_ms) as max_queue_wait,
    AVG(delay_from_timestamp_ms) as avg_delay_from_timestamp,
    MAX(delay_from_timestamp_ms) as max_delay_from_timestamp
FROM xt_trade_update_test
WHERE created_at >= NOW() - INTERVAL '1 hour';
```

## 性能分析

通过调整参数，可以测试不同场景：

1. **高吞吐量测试**
   ```bash
   python3 scripts/test_trade_queue_performance.py --messages 10000 --batch-size 50
   ```

2. **低延迟测试**
   ```bash
   python3 scripts/test_trade_queue_performance.py --messages 1000 --batch-size 5 --batch-timeout 0.1
   ```

3. **数据库压力测试**
   ```bash
   python3 scripts/test_trade_queue_performance.py --messages 5000 --db-delay 0.2
   ```

## 注意事项

1. 确保测试表已创建（执行 `create_test_tables.sql`）
2. 测试数据会写入 `xt_trade_update_test` 表
3. 可以通过 `--db-delay` 参数模拟不同的数据库性能
4. 建议在不同参数下多次测试，观察性能变化
