#!/usr/bin/env python3
"""测试成交消息队列性能.

模拟消息接收和数据库写入过程，记录延迟数据到测试表。
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote
from decimal import Decimal
import time

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor, execute_values
except ImportError:
    print("错误: 需要安装 psycopg2")
    print("请运行: pip install psycopg2-binary")
    sys.exit(1)

# 读取数据库配置
project_root = Path(__file__).parent.parent
config_path = project_root / "config" / "accounts.json"
with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

database_url = config["global_settings"]["database_url"]
parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://"))
password = unquote(parsed.password) if parsed.password else None

db_params = {
    "host": parsed.hostname,
    "port": parsed.port or 5432,
    "database": parsed.path.lstrip("/"),
    "user": parsed.username,
    "password": password,
    "sslmode": "require",
}

def parse_timestamp_from_raw_data(raw_data_str: str) -> datetime | None:
    """从 raw_data JSON 字符串中解析 timestamp 并转换为 datetime."""
    try:
        data = json.loads(raw_data_str)
        timestamp = data.get("timestamp")
        if timestamp is None:
            return None
        
        if isinstance(timestamp, (int, float)):
            ts_sec = timestamp / 1000.0
            return datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
        return None
    except (json.JSONDecodeError, ValueError, TypeError, OSError):
        return None

def simulate_trade_data(trade_id: int, order_id: int, symbol: str = "tradoor_usdt") -> dict:
    """模拟成交数据."""
    timestamp = int(datetime.utcnow().timestamp() * 1000)
    return {
        "orderId": str(order_id),
        "orderSide": "BUY" if trade_id % 2 == 0 else "SELL",
        "positionSide": "LONG",
        "price": str(1.0 + (trade_id % 100) / 100.0),
        "quantity": str(100 + (trade_id % 50)),
        "isMaker": trade_id % 3 == 0,
        "marginUnfrozen": "0",
        "fee": "0.00000000",
        "timestamp": timestamp,
        "clientOrderId": f"test_{order_id}",
        "symbol": symbol,
    }

async def simulate_message_queue_processing(
    conn: psycopg2.extensions.connection,
    num_messages: int = 100,
    batch_size: int = 10,
    batch_timeout: float = 1.0,
    simulate_db_delay: float = 0.05
):
    """模拟消息队列处理过程.
    
    Args:
        conn: 数据库连接
        num_messages: 要处理的消息数量
        batch_size: 批量写入大小
        batch_timeout: 批量写入超时（秒）
        simulate_db_delay: 模拟数据库写入延迟（秒）
    """
    from collections import deque
    
    # 模拟消息队列
    message_queue = deque()
    
    # 统计信息
    stats = {
        "total_messages": 0,
        "total_batches": 0,
        "total_db_time": 0.0,
        "total_queue_wait": 0.0,
        "max_queue_wait": 0.0,
        "max_db_time": 0.0,
    }
    
    print(f"开始模拟处理 {num_messages} 条消息...")
    print(f"批量大小: {batch_size}, 超时: {batch_timeout}秒, 模拟DB延迟: {simulate_db_delay}秒\n")
    
    # 模拟消息接收（快速放入队列）
    print("阶段 1: 模拟消息接收...")
    receive_start = datetime.utcnow()
    for i in range(num_messages):
        message_received_at = datetime.utcnow()
        trade_data = simulate_trade_data(i, i // 2, "tradoor_usdt")
        trade_data["_message_received_at"] = message_received_at.isoformat()
        message_queue.append({
            "data": trade_data,
            "message_received_at": message_received_at,
        })
        stats["total_messages"] += 1
        
        # 模拟消息接收间隔（很小，因为接收很快）
        await asyncio.sleep(0.001)
    
    receive_duration = (datetime.utcnow() - receive_start).total_seconds()
    print(f"✓ 消息接收完成: {num_messages} 条消息, 耗时 {receive_duration:.3f}秒\n")
    
    # 模拟批量处理（从队列取出并写入数据库）
    print("阶段 2: 模拟批量处理...")
    batch = []
    last_flush_time = datetime.utcnow()
    processed_count = 0
    
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        while message_queue or batch:
            # 从队列获取消息
            if message_queue:
                try:
                    message = message_queue.popleft()
                    queue_wait_time = (datetime.utcnow() - message["message_received_at"]).total_seconds() * 1000
                    stats["total_queue_wait"] += queue_wait_time
                    stats["max_queue_wait"] = max(stats["max_queue_wait"], queue_wait_time)
                    
                    batch.append(message)
                except IndexError:
                    pass
            
            # 检查是否需要刷新批次
            should_flush = False
            if len(batch) >= batch_size:
                should_flush = True
            elif batch and (datetime.utcnow() - last_flush_time).total_seconds() >= batch_timeout:
                should_flush = True
            elif not message_queue and batch:
                should_flush = True
            
            if should_flush:
                # 批量写入数据库（使用同步函数，在线程池中执行）
                batch_start = datetime.utcnow()
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    write_trade_batch_to_test_table_sync,
                    cur,
                    batch,
                    simulate_db_delay
                )
                batch_duration = (datetime.utcnow() - batch_start).total_seconds() * 1000
                
                stats["total_batches"] += 1
                stats["total_db_time"] += batch_duration
                stats["max_db_time"] = max(stats["max_db_time"], batch_duration)
                
                processed_count += len(batch)
                print(f"  批次 {stats['total_batches']}: 写入 {len(batch)} 条, "
                      f"耗时 {batch_duration:.2f}ms, 已处理 {processed_count}/{num_messages}")
                
                batch = []
                last_flush_time = datetime.utcnow()
            
            # 如果没有消息了，等待一下再检查
            if not message_queue and not batch:
                break
            
            await asyncio.sleep(0.01)  # 小延迟，避免CPU占用过高
        
        conn.commit()
    finally:
        cur.close()
    
    # 打印统计信息
    print(f"\n{'='*60}")
    print("处理完成统计:")
    print(f"{'='*60}")
    print(f"总消息数: {stats['total_messages']}")
    print(f"总批次数: {stats['total_batches']}")
    print(f"平均每批: {stats['total_messages'] / stats['total_batches']:.1f} 条")
    print(f"\n队列等待时间:")
    print(f"  总等待时间: {stats['total_queue_wait']:.2f}ms")
    print(f"  平均等待时间: {stats['total_queue_wait'] / stats['total_messages']:.2f}ms")
    print(f"  最大等待时间: {stats['max_queue_wait']:.2f}ms")
    print(f"\n数据库写入时间:")
    print(f"  总写入时间: {stats['total_db_time']:.2f}ms")
    print(f"  平均每批: {stats['total_db_time'] / stats['total_batches']:.2f}ms")
    print(f"  平均每条: {stats['total_db_time'] / stats['total_messages']:.2f}ms")
    print(f"  最大批次耗时: {stats['max_db_time']:.2f}ms")
    print(f"\n总处理时间: {receive_duration + (stats['total_db_time']/1000):.3f}秒")
    print(f"消息接收速度: {stats['total_messages'] / receive_duration:.1f} 条/秒")
    print(f"数据库写入速度: {stats['total_messages'] / (stats['total_db_time']/1000):.1f} 条/秒")

def write_trade_batch_to_test_table_sync(
    cur: psycopg2.extensions.cursor,
    batch: list,
    simulate_db_delay: float
):
    """批量写入成交数据到测试表（同步版本）."""
    if not batch:
        return
    
    # 模拟数据库写入延迟
    time.sleep(simulate_db_delay)
    
    records = []
    current_time = datetime.utcnow()
    batch_start_time = current_time
    
    for message in batch:
        trade_data = message["data"]
        message_received_at = message["message_received_at"]
        
        # 解析数据
        order_id = trade_data.get("orderId", "")
        timestamp = trade_data.get("timestamp")
        trade_id = f"{order_id}_{timestamp}" if order_id and timestamp else order_id
        
        # 计算时间
        timestamp_from_raw = None
        if timestamp:
            try:
                ts_sec = timestamp / 1000.0
                timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
            except (ValueError, OSError):
                pass
        
        # 计算延迟
        queue_wait_time_ms = (batch_start_time - message_received_at).total_seconds() * 1000
        delay_from_timestamp_ms = None
        if timestamp_from_raw and message_received_at:
            delay_from_timestamp_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
        
        # 准备记录
        record = (
            timestamp_from_raw or current_time,  # update_time
            "account_008",  # account_id
            trade_data.get("symbol", ""),  # symbol
            order_id,  # order_id
            trade_id,  # trade_id
            trade_data.get("orderSide", ""),  # side
            Decimal(trade_data.get("price", "0")),  # price
            Decimal(trade_data.get("quantity", "0")),  # quantity
            Decimal(trade_data.get("price", "0")) * Decimal(trade_data.get("quantity", "0")),  # quote_quantity
            Decimal("0"),  # commission
            "",  # commission_asset
            trade_data.get("isMaker", False),  # is_maker
            trade_data.get("positionSide", ""),  # position_side
            message_received_at,  # message_received_at
            queue_wait_time_ms,  # queue_wait_time_ms
            None,  # processing_duration_ms (在批量写入时计算)
            None,  # database_write_duration_ms (在批量写入时计算)
            timestamp_from_raw,  # timestamp_from_raw
            delay_from_timestamp_ms,  # delay_from_timestamp_ms
            json.dumps(trade_data),  # raw_data
            current_time,  # created_at
        )
        records.append(record)
    
    # 批量插入
    insert_sql = """
        INSERT INTO xt_trade_update_test (
            update_time, account_id, symbol, order_id, trade_id, side, price, quantity,
            quote_quantity, commission, commission_asset, is_maker, position_side,
            message_received_at, queue_wait_time_ms, processing_duration_ms,
            database_write_duration_ms, timestamp_from_raw, delay_from_timestamp_ms,
            raw_data, created_at
        ) VALUES %s
    """
    
    execute_values(cur, insert_sql, records)

async def main():
    """主函数."""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试成交消息队列性能")
    parser.add_argument("--messages", type=int, default=100, help="要处理的消息数量（默认: 100）")
    parser.add_argument("--batch-size", type=int, default=10, help="批量写入大小（默认: 10）")
    parser.add_argument("--batch-timeout", type=float, default=1.0, help="批量写入超时（秒，默认: 1.0）")
    parser.add_argument("--db-delay", type=float, default=0.05, help="模拟数据库写入延迟（秒，默认: 0.05）")
    
    args = parser.parse_args()
    
    conn = psycopg2.connect(**db_params)
    
    try:
        await simulate_message_queue_processing(
            conn,
            num_messages=args.messages,
            batch_size=args.batch_size,
            batch_timeout=args.batch_timeout,
            simulate_db_delay=args.db_delay
        )
        
        # 查询统计信息
        print(f"\n{'='*60}")
        print("数据库统计:")
        print(f"{'='*60}")
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_count,
                    AVG(queue_wait_time_ms) as avg_queue_wait,
                    MAX(queue_wait_time_ms) as max_queue_wait,
                    AVG(delay_from_timestamp_ms) as avg_delay_from_timestamp,
                    MAX(delay_from_timestamp_ms) as max_delay_from_timestamp
                FROM xt_trade_update_test
                WHERE created_at >= NOW() - INTERVAL '1 hour'
            """)
            
            result = cur.fetchone()
            if result:
                print(f"最近1小时记录数: {result['total_count']}")
                print(f"平均队列等待: {result['avg_queue_wait']:.2f}ms")
                print(f"最大队列等待: {result['max_queue_wait']:.2f}ms")
                print(f"平均timestamp延迟: {result['avg_delay_from_timestamp']:.2f}ms")
                print(f"最大timestamp延迟: {result['max_delay_from_timestamp']:.2f}ms")
        
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())
