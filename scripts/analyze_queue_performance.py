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
    import argparse
    
    parser = argparse.ArgumentParser(description="分析消息队列性能测试结果")
    parser.add_argument("--hours", type=int, default=1, help="分析最近N小时的数据（默认: 1）")
    parser.add_argument("--minutes", type=int, default=None, help="分析最近N分钟的数据（如果指定，会覆盖--hours）")
    
    args = parser.parse_args()
    
    # 确定时间间隔
    if args.minutes:
        interval = f"INTERVAL '{args.minutes} minutes'"
        time_desc = f"最近 {args.minutes} 分钟"
    else:
        interval = f"INTERVAL '{args.hours} hour'"
        time_desc = f"最近 {args.hours} 小时"
    
    conn = psycopg2.connect(**db_params)
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 整体统计
            print("=" * 80)
            print(f"消息队列性能分析 ({time_desc})")
            print("=" * 80)
            
            cur.execute(f"""
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
                WHERE created_at >= NOW() - {interval}
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
            cur.execute(f"""
                SELECT 
                    DATE_TRUNC('minute', created_at) + 
                    INTERVAL '1 minute' * (EXTRACT(MINUTE FROM created_at)::int / 5 * 5) as time_slot,
                    COUNT(*) as count,
                    AVG(queue_wait_time_ms) as avg_queue_wait,
                    MAX(queue_wait_time_ms) as max_queue_wait,
                    AVG(delay_from_timestamp_ms) as avg_delay_from_timestamp
                FROM xt_trade_update_test
                WHERE created_at >= NOW() - {interval}
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
            cur.execute(f"""
                WITH wait_ranges AS (
                    SELECT 
                        CASE 
                            WHEN queue_wait_time_ms < 100 THEN '< 100ms'
                            WHEN queue_wait_time_ms < 500 THEN '100-500ms'
                            WHEN queue_wait_time_ms < 1000 THEN '500ms-1s'
                            WHEN queue_wait_time_ms < 5000 THEN '1s-5s'
                            WHEN queue_wait_time_ms < 10000 THEN '5s-10s'
                            ELSE '> 10s'
                        END as wait_range,
                        COUNT(*) as count
                    FROM xt_trade_update_test
                    WHERE created_at >= NOW() - {interval}
                    GROUP BY 
                        CASE 
                            WHEN queue_wait_time_ms < 100 THEN '< 100ms'
                            WHEN queue_wait_time_ms < 500 THEN '100-500ms'
                            WHEN queue_wait_time_ms < 1000 THEN '500ms-1s'
                            WHEN queue_wait_time_ms < 5000 THEN '1s-5s'
                            WHEN queue_wait_time_ms < 10000 THEN '5s-10s'
                            ELSE '> 10s'
                        END
                )
                SELECT 
                    wait_range,
                    count,
                    ROUND(100.0 * count / SUM(count) OVER (), 2) as percentage
                FROM wait_ranges
                ORDER BY 
                    CASE 
                        WHEN wait_range = '< 100ms' THEN 1
                        WHEN wait_range = '100-500ms' THEN 2
                        WHEN wait_range = '500ms-1s' THEN 3
                        WHEN wait_range = '1s-5s' THEN 4
                        WHEN wait_range = '5s-10s' THEN 5
                        ELSE 6
                    END
            """)
            
            rows = cur.fetchall()
            print(f"{'等待时间范围':<15} {'记录数':<10} {'占比':<10}")
            print("-" * 80)
            for row in rows:
                print(f"{row['wait_range']:<15} {row['count']:<10} {row['percentage']:<10.2f}%")
            
            # 消息接收延迟分析（timestamp vs message_received_at）
            print(f"\n【消息接收延迟分析】")
            print("-" * 80)
            print("说明: delay_from_timestamp_ms = message_received_at - timestamp_from_raw")
            print("如果延迟很大，可能是 WebSocket 连接断开重连导致的消息积压")
            print("-" * 80)
            
            cur.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN delay_from_timestamp_ms < 1000 THEN 1 END) as delay_lt_1s,
                    COUNT(CASE WHEN delay_from_timestamp_ms >= 1000 AND delay_from_timestamp_ms < 5000 THEN 1 END) as delay_1s_5s,
                    COUNT(CASE WHEN delay_from_timestamp_ms >= 5000 AND delay_from_timestamp_ms < 60000 THEN 1 END) as delay_5s_1m,
                    COUNT(CASE WHEN delay_from_timestamp_ms >= 60000 AND delay_from_timestamp_ms < 300000 THEN 1 END) as delay_1m_5m,
                    COUNT(CASE WHEN delay_from_timestamp_ms >= 300000 THEN 1 END) as delay_gt_5m,
                    ROUND(AVG(delay_from_timestamp_ms), 2) as avg_delay_ms,
                    ROUND(MAX(delay_from_timestamp_ms), 2) as max_delay_ms,
                    ROUND(MIN(delay_from_timestamp_ms), 2) as min_delay_ms
                FROM xt_trade_update_test
                WHERE created_at >= NOW() - {interval}
                AND delay_from_timestamp_ms IS NOT NULL
            """)
            
            delay_stats = cur.fetchone()
            if delay_stats and delay_stats['total'] > 0:
                print(f"总记录数: {delay_stats['total']}")
                print(f"延迟 < 1秒: {delay_stats['delay_lt_1s']} ({100.0 * delay_stats['delay_lt_1s'] / delay_stats['total']:.2f}%)")
                print(f"延迟 1-5秒: {delay_stats['delay_1s_5s']} ({100.0 * delay_stats['delay_1s_5s'] / delay_stats['total']:.2f}%)")
                print(f"延迟 5秒-1分钟: {delay_stats['delay_5s_1m']} ({100.0 * delay_stats['delay_5s_1m'] / delay_stats['total']:.2f}%)")
                print(f"延迟 1-5分钟: {delay_stats['delay_1m_5m']} ({100.0 * delay_stats['delay_1m_5m'] / delay_stats['total']:.2f}%)")
                print(f"延迟 > 5分钟: {delay_stats['delay_gt_5m']} ({100.0 * delay_stats['delay_gt_5m'] / delay_stats['total']:.2f}%)")
                avg_delay_ms = float(delay_stats['avg_delay_ms']) if delay_stats['avg_delay_ms'] else 0.0
                max_delay_ms = float(delay_stats['max_delay_ms']) if delay_stats['max_delay_ms'] else 0.0
                min_delay_ms = float(delay_stats['min_delay_ms']) if delay_stats['min_delay_ms'] else 0.0
                print(f"\n平均延迟: {avg_delay_ms:.2f} ms ({avg_delay_ms/1000:.2f} 秒)")
                print(f"最大延迟: {max_delay_ms:.2f} ms ({max_delay_ms/1000:.2f} 秒)")
                print(f"最小延迟: {min_delay_ms:.2f} ms ({min_delay_ms/1000:.2f} 秒)")
                
                if delay_stats['delay_gt_5m'] > 0:
                    print(f"\n⚠️  警告: 发现 {delay_stats['delay_gt_5m']} 条记录延迟超过 5 分钟！")
                    print("   这可能表明 WebSocket 连接断开重连，导致消息积压。")
            
            # 查找延迟最大的记录
            cur.execute(f"""
                SELECT 
                    trade_id,
                    symbol,
                    timestamp_from_raw,
                    message_received_at,
                    delay_from_timestamp_ms,
                    queue_wait_time_ms,
                    database_write_duration_ms,
                    created_at
                FROM xt_trade_update_test
                WHERE created_at >= NOW() - {interval}
                AND delay_from_timestamp_ms IS NOT NULL
                ORDER BY delay_from_timestamp_ms DESC
                LIMIT 10
            """)
            
            max_delay_rows = cur.fetchall()
            if max_delay_rows:
                print(f"\n【延迟最大的 10 条记录】")
                print("-" * 80)
                print(f"{'交易ID':<30} {'延迟(秒)':<12} {'队列等待(ms)':<15} {'DB写入(ms)':<12} {'时间戳':<20} {'接收时间':<20}")
                print("-" * 80)
                for row in max_delay_rows:
                    delay_ms = float(row['delay_from_timestamp_ms']) if row['delay_from_timestamp_ms'] else 0.0
                    delay_sec = delay_ms / 1000.0
                    ts_str = str(row['timestamp_from_raw'])[:19] if row['timestamp_from_raw'] else 'N/A'
                    recv_str = str(row['message_received_at'])[:19] if row['message_received_at'] else 'N/A'
                    queue_wait = float(row['queue_wait_time_ms']) if row['queue_wait_time_ms'] else 0.0
                    db_write = float(row['database_write_duration_ms']) if row['database_write_duration_ms'] else 0.0
                    print(f"{row['trade_id']:<30} {delay_sec:<12.2f} {queue_wait:<15.2f} {db_write:<12.2f} {ts_str:<20} {recv_str:<20}")
            
            # 按时间段分析延迟趋势
            cur.execute(f"""
                SELECT 
                    DATE_TRUNC('minute', created_at) as time_slot,
                    COUNT(*) as count,
                    ROUND(AVG(delay_from_timestamp_ms), 2) as avg_delay_ms,
                    ROUND(MAX(delay_from_timestamp_ms), 2) as max_delay_ms,
                    ROUND(AVG(queue_wait_time_ms), 2) as avg_queue_wait_ms
                FROM xt_trade_update_test
                WHERE created_at >= NOW() - {interval}
                AND delay_from_timestamp_ms IS NOT NULL
                GROUP BY DATE_TRUNC('minute', created_at)
                ORDER BY time_slot DESC
                LIMIT 20
            """)
            
            trend_rows = cur.fetchall()
            if trend_rows:
                print(f"\n【延迟趋势（最近 20 分钟）】")
                print("-" * 80)
                print(f"{'时间段':<20} {'记录数':<10} {'平均延迟(秒)':<15} {'最大延迟(秒)':<15} {'平均队列等待(ms)':<15}")
                print("-" * 80)
                for row in trend_rows:
                    time_str = row['time_slot'].strftime('%Y-%m-%d %H:%M') if row['time_slot'] else 'N/A'
                    avg_delay_ms = float(row['avg_delay_ms']) if row['avg_delay_ms'] else 0.0
                    max_delay_ms = float(row['max_delay_ms']) if row['max_delay_ms'] else 0.0
                    avg_queue_wait = float(row['avg_queue_wait_ms']) if row['avg_queue_wait_ms'] else 0.0
                    avg_delay_sec = avg_delay_ms / 1000.0
                    max_delay_sec = max_delay_ms / 1000.0
                    print(f"{time_str:<20} {row['count']:<10} {avg_delay_sec:<15.2f} {max_delay_sec:<15.2f} {avg_queue_wait:<15.2f}")
            
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
            
            # WebSocket 连接事件分析
            print(f"\n【WebSocket 连接事件分析】")
            print("-" * 80)
            cur.execute(f"""
                SELECT 
                    event_type,
                    COUNT(*) as count,
                    MIN(event_time) as first_event,
                    MAX(event_time) as last_event,
                    AVG(disconnect_duration_seconds) as avg_disconnect_duration,
                    MAX(disconnect_duration_seconds) as max_disconnect_duration
                FROM xt_websocket_connection_events_test
                WHERE event_time >= NOW() - {interval}
                GROUP BY event_type
                ORDER BY event_type
            """)
            
            event_rows = cur.fetchall()
            if event_rows:
                print(f"{'事件类型':<20} {'次数':<10} {'首次时间':<20} {'最后时间':<20} {'平均断开时长(秒)':<20} {'最大断开时长(秒)':<20}")
                print("-" * 80)
                for row in event_rows:
                    first_str = row['first_event'].strftime('%Y-%m-%d %H:%M:%S') if row['first_event'] else 'N/A'
                    last_str = row['last_event'].strftime('%Y-%m-%d %H:%M:%S') if row['last_event'] else 'N/A'
                    avg_dur = f"{row['avg_disconnect_duration']:.2f}" if row['avg_disconnect_duration'] else 'N/A'
                    max_dur = f"{row['max_disconnect_duration']:.2f}" if row['max_disconnect_duration'] else 'N/A'
                    print(f"{row['event_type']:<20} {row['count']:<10} {first_str:<20} {last_str:<20} {avg_dur:<20} {max_dur:<20}")
                
                # 查找重连事件
                reconnect_count = sum(1 for r in event_rows if r['event_type'] == 'reconnect')
                disconnect_count = sum(1 for r in event_rows if r['event_type'] == 'disconnect')
                
                if reconnect_count > 0 or disconnect_count > 0:
                    print(f"\n⚠️  检测到 {disconnect_count} 次断开和 {reconnect_count} 次重连")
                    print("   这可能是导致消息接收延迟的主要原因")
            
            # 关联重连事件和消息延迟
            cur.execute(f"""
                WITH reconnect_events AS (
                    SELECT 
                        event_time as reconnect_time,
                        disconnect_duration_seconds
                    FROM xt_websocket_connection_events_test
                    WHERE event_type = 'reconnect'
                    AND event_time >= NOW() - {interval}
                ),
                delayed_messages AS (
                    SELECT 
                        message_received_at,
                        delay_from_timestamp_ms,
                        timestamp_from_raw
                    FROM xt_trade_update_test
                    WHERE created_at >= NOW() - {interval}
                    AND delay_from_timestamp_ms IS NOT NULL
                    AND delay_from_timestamp_ms > 60000  -- 延迟超过1分钟
                )
                SELECT 
                    COUNT(DISTINCT r.reconnect_time) as reconnect_count,
                    COUNT(dm.message_received_at) as delayed_message_count,
                    AVG(dm.delay_from_timestamp_ms) as avg_delay_after_reconnect,
                    MAX(dm.delay_from_timestamp_ms) as max_delay_after_reconnect
                FROM reconnect_events r
                LEFT JOIN delayed_messages dm ON 
                    dm.message_received_at >= r.reconnect_time 
                    AND dm.message_received_at <= r.reconnect_time + INTERVAL '5 minutes'
            """)
            
            correlation = cur.fetchone()
            if correlation and correlation['reconnect_count'] > 0:
                print(f"\n【重连事件与消息延迟关联分析】")
                print("-" * 80)
                print(f"重连次数: {correlation['reconnect_count']}")
                print(f"重连后5分钟内的延迟消息数: {correlation['delayed_message_count']}")
                if correlation['avg_delay_after_reconnect']:
                    avg_delay = float(correlation['avg_delay_after_reconnect'])
                    max_delay = float(correlation['max_delay_after_reconnect']) if correlation['max_delay_after_reconnect'] else 0.0
                    print(f"重连后平均延迟: {avg_delay/1000:.2f} 秒")
                    print(f"重连后最大延迟: {max_delay/1000:.2f} 秒")
                    if avg_delay > 300000:  # 5分钟
                        print("\n⚠️  重连后消息延迟严重，说明服务器在重连时推送了积压的消息")
            
            # 消息接收延迟诊断
            if delay_stats and delay_stats['total'] > 0:
                print(f"\n【消息接收延迟诊断】")
                print("-" * 80)
                
                avg_delay_ms = float(delay_stats['avg_delay_ms']) if delay_stats['avg_delay_ms'] else 0.0
                max_delay_ms = float(delay_stats['max_delay_ms']) if delay_stats['max_delay_ms'] else 0.0
                avg_delay_min = avg_delay_ms / 60000.0
                max_delay_min = max_delay_ms / 60000.0
                
                if avg_delay_min > 5:
                    print(f"⚠️  严重问题: 平均消息接收延迟 {avg_delay_min:.1f} 分钟")
                    print("   可能原因:")
                    print("   1. WebSocket 连接频繁断开重连，导致消息积压")
                    print("   2. 服务器端延迟推送消息")
                    print("   3. 网络不稳定导致消息延迟")
                    print("\n   建议:")
                    print("   1. 检查 WebSocket 连接稳定性（查看日志中的重连记录）")
                    print("   2. 检查网络连接质量")
                    print("   3. 考虑增加心跳检测频率，及时发现连接问题")
                    print("   4. 如果延迟是服务器端问题，可能需要联系 XT 技术支持")
                elif avg_delay_min > 1:
                    print(f"⚠️  警告: 平均消息接收延迟 {avg_delay_min:.1f} 分钟")
                    print("   建议检查 WebSocket 连接稳定性")
                else:
                    print(f"✅ 消息接收延迟正常（平均 {avg_delay_min*60:.1f} 秒）")
                
                if max_delay_min > 10:
                    print(f"\n⚠️  严重: 最大延迟 {max_delay_min:.1f} 分钟，存在严重的消息积压")
                    print("   这通常发生在 WebSocket 连接断开后重连时")
                    print("   服务器会一次性推送所有积压的消息")
            
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
                
                # 分析消息接收延迟对处理速度的影响
                avg_delay_ms = float(delay_stats['avg_delay_ms']) if delay_stats and delay_stats['avg_delay_ms'] else 0.0
                if delay_stats and avg_delay_ms > 60000:
                    print(f"\n💡 注意: 消息接收延迟较大（平均 {avg_delay_ms/1000:.1f} 秒）")
                    print("   这不会影响队列处理速度，但会影响数据的实时性")
                    print("   建议优先解决 WebSocket 连接稳定性问题")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
