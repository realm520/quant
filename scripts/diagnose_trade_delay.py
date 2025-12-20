#!/usr/bin/env python3
"""诊断成交数据延迟问题.

分析：
1. 消息接收时间 vs timestamp 字段的差异
2. 数据库写入时间 vs 消息接收时间的差异
3. 最近成交记录的时间分布
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

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
db_params = {
    "host": parsed.hostname,
    "port": parsed.port or 5432,
    "database": parsed.path.lstrip("/"),
    "user": parsed.username,
    "password": parsed.password,
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

def main():
    """诊断成交数据延迟."""
    conn = psycopg2.connect(**db_params)
    current_time = datetime.utcnow()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 查询最近 100 条成交记录
            cur.execute("""
                SELECT 
                    id,
                    update_time,
                    account_id,
                    symbol,
                    trade_id,
                    order_id,
                    created_at,
                    raw_data
                FROM xt_trade_update
                WHERE raw_data IS NOT NULL
                  AND raw_data::json->>'timestamp' IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 100
            """)
            
            rows = cur.fetchall()
        
        if not rows:
            print("没有找到成交记录")
            return
        
        print(f"分析最近 {len(rows)} 条成交记录\n")
        print("=" * 120)
        
        delays = []
        timestamp_delays = []
        
        for idx, row in enumerate(rows, 1):
            raw_data_str = row["raw_data"]
            timestamp_dt = parse_timestamp_from_raw_data(raw_data_str)
            
            if timestamp_dt is None:
                continue
            
            update_time = row["update_time"]
            created_at = row["created_at"]
            
            # 1. timestamp 字段与当前时间的差异
            if isinstance(timestamp_dt, datetime):
                timestamp_delay = (current_time - timestamp_dt).total_seconds()
                timestamp_delays.append(timestamp_delay)
            
            # 2. 数据库写入时间（created_at）与 timestamp 的差异
            if isinstance(created_at, datetime) and isinstance(timestamp_dt, datetime):
                write_delay = (created_at - timestamp_dt).total_seconds()
                delays.append(write_delay)
            
            # 3. update_time 与 timestamp 的差异
            if isinstance(update_time, datetime) and isinstance(timestamp_dt, datetime):
                update_delay = (update_time - timestamp_dt).total_seconds()
            
            # 显示前 10 条的详细信息
            if idx <= 10:
                print(f"\n【记录 {idx}】")
                print(f"账户: {row['account_id']}, 交易对: {row['symbol']}")
                print(f"成交ID: {row['trade_id']}, 订单ID: {row['order_id']}")
                print(f"raw_data.timestamp 转换后: {timestamp_dt}")
                print(f"数据库 update_time: {update_time}")
                print(f"数据库 created_at: {created_at}")
                print(f"当前时间: {current_time}")
                
                if isinstance(timestamp_dt, datetime):
                    print(f"timestamp 与当前时间差: {timestamp_delay:.2f} 秒 ({timestamp_delay/60:.2f} 分钟)")
                if isinstance(created_at, datetime) and isinstance(timestamp_dt, datetime):
                    print(f"写入延迟 (created_at - timestamp): {write_delay:.2f} 秒")
                if isinstance(update_time, datetime) and isinstance(timestamp_dt, datetime):
                    print(f"update_time 与 timestamp 差异: {update_delay:.2f} 秒")
                print("-" * 120)
        
        # 统计信息
        print("\n" + "=" * 120)
        print("统计信息:")
        print("=" * 120)
        
        if timestamp_delays:
            avg_timestamp_delay = sum(timestamp_delays) / len(timestamp_delays)
            max_timestamp_delay = max(timestamp_delays)
            min_timestamp_delay = min(timestamp_delays)
            print(f"\n1. timestamp 字段与当前时间的差异:")
            print(f"   平均延迟: {avg_timestamp_delay:.2f} 秒 ({avg_timestamp_delay/60:.2f} 分钟)")
            print(f"   最大延迟: {max_timestamp_delay:.2f} 秒 ({max_timestamp_delay/60:.2f} 分钟)")
            print(f"   最小延迟: {min_timestamp_delay:.2f} 秒 ({min_timestamp_delay/60:.2f} 分钟)")
        
        if delays:
            avg_write_delay = sum(delays) / len(delays)
            max_write_delay = max(delays)
            min_write_delay = min(delays)
            print(f"\n2. 数据库写入延迟 (created_at - timestamp):")
            print(f"   平均延迟: {avg_write_delay:.2f} 秒")
            print(f"   最大延迟: {max_write_delay:.2f} 秒 ({max_write_delay/60:.2f} 分钟)")
            print(f"   最小延迟: {min_write_delay:.2f} 秒")
            
            # 检查是否有严重延迟
            if max_write_delay > 60:
                print(f"\n   ⚠️  警告: 检测到严重的写入延迟（> 1 分钟）")
                print(f"   可能原因:")
                print(f"   - 数据库连接池耗尽")
                print(f"   - 数据库写入性能问题")
                print(f"   - 网络延迟")
                print(f"   - 消息处理队列积压")
        
        # 分析时间分布
        print(f"\n3. 时间分布分析:")
        if timestamp_delays:
            recent_delays = [d for d in timestamp_delays if d < 3600]  # 1小时内
            old_delays = [d for d in timestamp_delays if d >= 3600]  # 超过1小时
            
            print(f"   最近1小时内的记录: {len(recent_delays)} 条")
            print(f"   超过1小时的记录: {len(old_delays)} 条")
            
            if old_delays:
                print(f"   ⚠️  警告: 有 {len(old_delays)} 条记录的 timestamp 超过1小时")
                print(f"   这可能表明:")
                print(f"   - timestamp 字段不是实际成交时间")
                print(f"   - 数据是从历史回补的")
                print(f"   - WebSocket 推送延迟")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
