#!/usr/bin/env python3
"""分析消息队列性能测试结果."""

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
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

def main():
    """分析队列性能."""
    conn = psycopg2.connect(**db_params)
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 整体统计
            print("=" * 80)
            print("消息队列性能分析")
            print("=" * 80)
            
            cur.execute("""
                SELECT 
                    COUNT(*) as total_count,
                    AVG(queue_wait_time_ms) as avg_queue_wait,
                    MIN(queue_wait_time_ms) as min_queue_wait,
                    MAX(queue_wait_time_ms) as max_queue_wait,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY queue_wait_time_ms) as median_queue_wait,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY queue_wait_time_ms) as p95_queue_wait,
                    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY queue_wait_time_ms) as p99_queue_wait,
                    AVG(delay_from_timestamp_ms) as avg_delay_from_timestamp,
                    MAX(delay_from_timestamp_ms) as max_delay_from_timestamp
                FROM xt_trade_update_test
                WHERE created_at >= NOW() - INTERVAL '1 hour'
            """)
            
            result = cur.fetchone()
            if not result or result['total_count'] == 0:
                print("没有找到测试数据")
                return
            
            print(f"\n【整体统计】")
            print(f"总记录数: {result['total_count']}")
            print(f"\n队列等待时间（毫秒）:")
            print(f"  平均: {result['avg_queue_wait']:.2f}ms ({result['avg_queue_wait']/1000:.2f}秒)")
            print(f"  最小: {result['min_queue_wait']:.2f}ms")
            print(f"  最大: {result['max_queue_wait']:.2f}ms ({result['max_queue_wait']/1000:.2f}秒)")
            print(f"  中位数: {result['median_queue_wait']:.2f}ms ({result['median_queue_wait']/1000:.2f}秒)")
            print(f"  P95: {result['p95_queue_wait']:.2f}ms ({result['p95_queue_wait']/1000:.2f}秒)")
            print(f"  P99: {result['p99_queue_wait']:.2f}ms ({result['p99_queue_wait']/1000:.2f}秒)")
            
            print(f"\ntimestamp 延迟（毫秒）:")
            print(f"  平均: {result['avg_delay_from_timestamp']:.2f}ms")
            print(f"  最大: {result['max_delay_from_timestamp']:.2f}ms")
            
            # 按时间段分析（每5分钟）
            print(f"\n【按时间段分析（每5分钟）】")
            print("-" * 80)
            cur.execute("""
                SELECT 
                    DATE_TRUNC('minute', created_at) + 
                    INTERVAL '1 minute' * (EXTRACT(MINUTE FROM created_at)::int / 5 * 5) as time_slot,
                    COUNT(*) as count,
                    AVG(queue_wait_time_ms) as avg_queue_wait,
                    MAX(queue_wait_time_ms) as max_queue_wait,
                    AVG(delay_from_timestamp_ms) as avg_delay_from_timestamp
                FROM xt_trade_update_test
                WHERE created_at >= NOW() - INTERVAL '1 hour'
                GROUP BY time_slot
                ORDER BY time_slot DESC
                LIMIT 12
            """)
            
            rows = cur.fetchall()
            print(f"{'时间段':<20} {'记录数':<10} {'平均等待(ms)':<15} {'最大等待(ms)':<15} {'平均延迟(ms)':<15}")
            print("-" * 80)
            for row in rows:
                print(f"{row['time_slot'].strftime('%Y-%m-%d %H:%M'):<20} "
                      f"{row['count']:<10} "
                      f"{row['avg_queue_wait']:<15.2f} "
                      f"{row['max_queue_wait']:<15.2f} "
                      f"{row['avg_delay_from_timestamp']:<15.2f}")
            
            # 队列等待时间分布
            print(f"\n【队列等待时间分布】")
            print("-" * 80)
            cur.execute("""
                SELECT 
                    CASE 
                        WHEN queue_wait_time_ms < 100 THEN '< 100ms'
                        WHEN queue_wait_time_ms < 500 THEN '100-500ms'
                        WHEN queue_wait_time_ms < 1000 THEN '500ms-1s'
                        WHEN queue_wait_time_ms < 5000 THEN '1s-5s'
                        WHEN queue_wait_time_ms < 10000 THEN '5s-10s'
                        ELSE '> 10s'
                    END as wait_range,
                    COUNT(*) as count,
                    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
                FROM xt_trade_update_test
                WHERE created_at >= NOW() - INTERVAL '1 hour'
                GROUP BY wait_range
                ORDER BY 
                    CASE wait_range
                        WHEN '< 100ms' THEN 1
                        WHEN '100-500ms' THEN 2
                        WHEN '500ms-1s' THEN 3
                        WHEN '1s-5s' THEN 4
                        WHEN '5s-10s' THEN 5
                        ELSE 6
                    END
            """)
            
            rows = cur.fetchall()
            print(f"{'等待时间范围':<15} {'记录数':<10} {'占比':<10}")
            print("-" * 80)
            for row in rows:
                print(f"{row['wait_range']:<15} {row['count']:<10} {row['percentage']:<10.2f}%")
            
            # 性能诊断
            print(f"\n【性能诊断】")
            print("-" * 80)
            
            avg_wait = result['avg_queue_wait']
            max_wait = result['max_queue_wait']
            
            if avg_wait > 10000:
                print("⚠️  严重问题: 平均队列等待时间超过 10 秒")
                print("   建议:")
                print("   1. 增加批量写入大小（--batch-size 20 或更大）")
                print("   2. 减少批量写入超时（--batch-timeout 0.5）")
                print("   3. 检查数据库写入性能（--db-delay 参数）")
                print("   4. 考虑增加数据库连接池大小")
            elif avg_wait > 5000:
                print("⚠️  警告: 平均队列等待时间超过 5 秒")
                print("   建议:")
                print("   1. 增加批量写入大小")
                print("   2. 优化数据库写入性能")
            elif avg_wait > 1000:
                print("⚠️  注意: 平均队列等待时间超过 1 秒")
                print("   建议:")
                print("   1. 可以适当增加批量写入大小以提高效率")
            else:
                print("✅ 队列等待时间正常")
            
            if max_wait > 20000:
                print(f"\n⚠️  严重: 最大队列等待时间 {max_wait/1000:.2f} 秒，存在严重积压")
                print("   可能原因:")
                print("   - 数据库写入速度远低于消息接收速度")
                print("   - 批量写入参数设置不合理")
                print("   - 数据库连接池耗尽")
            
            # 计算理论性能
            print(f"\n【理论性能分析】")
            print("-" * 80)
            if result['total_count'] > 0:
                # 假设批量大小为 10，数据库写入延迟为 50ms
                batch_size = 10
                db_delay_ms = 50
                messages_per_second = 1000.0 / (db_delay_ms / batch_size)
                print(f"假设批量大小: {batch_size}, 数据库写入延迟: {db_delay_ms}ms")
                print(f"理论最大处理速度: {messages_per_second:.1f} 条/秒")
                print(f"实际处理速度: {result['total_count'] / 3600:.1f} 条/秒（基于1小时数据）")
                
                if result['total_count'] / 3600 < messages_per_second * 0.5:
                    print("⚠️  实际处理速度远低于理论值，可能存在性能瓶颈")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
