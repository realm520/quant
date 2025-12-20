#!/usr/bin/env python3
"""监控成交数据延迟趋势.

定期检查最近成交记录的时间延迟情况，帮助诊断"运行久了之后"的延迟问题。
"""

import json
import sys
from datetime import datetime, timezone, timedelta
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
    """监控成交数据延迟趋势."""
    conn = psycopg2.connect(**db_params)
    current_time = datetime.utcnow()
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 查询最近 1 小时内的成交记录
            one_hour_ago = current_time - timedelta(hours=1)
            
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
                WHERE created_at >= %s
                  AND raw_data IS NOT NULL
                  AND raw_data::json->>'timestamp' IS NOT NULL
                ORDER BY created_at DESC
            """, (one_hour_ago,))
            
            rows = cur.fetchall()
        
        if not rows:
            print(f"最近 1 小时内没有成交记录（查询时间: {current_time}）")
            return
        
        print(f"分析最近 1 小时内的 {len(rows)} 条成交记录（查询时间: {current_time}）\n")
        print("=" * 120)
        
        # 按时间段分组统计
        time_slots = {}
        delays = []
        write_delays = []
        
        for row in rows:
            raw_data_str = row["raw_data"]
            timestamp_dt = parse_timestamp_from_raw_data(raw_data_str)
            
            if timestamp_dt is None:
                continue
            
            update_time = row["update_time"]
            created_at = row["created_at"]
            
            # 计算延迟
            timestamp_to_current = (current_time - timestamp_dt).total_seconds()
            timestamp_to_created = (created_at - timestamp_dt).total_seconds()
            update_to_created = (created_at - update_time).total_seconds() if isinstance(update_time, datetime) else 0
            
            delays.append(timestamp_to_current)
            write_delays.append(timestamp_to_created)
            
            # 按 10 分钟时间段分组
            slot_key = created_at.replace(second=0, microsecond=0)
            slot_key = slot_key.replace(minute=(slot_key.minute // 10) * 10)
            
            if slot_key not in time_slots:
                time_slots[slot_key] = {
                    "count": 0,
                    "delays": [],
                    "write_delays": [],
                }
            
            time_slots[slot_key]["count"] += 1
            time_slots[slot_key]["delays"].append(timestamp_to_current)
            time_slots[slot_key]["write_delays"].append(timestamp_to_created)
        
        # 整体统计
        print("\n【整体统计】")
        print("-" * 120)
        if delays:
            avg_delay = sum(delays) / len(delays)
            max_delay = max(delays)
            min_delay = min(delays)
            print(f"timestamp 与当前时间差异:")
            print(f"  平均: {avg_delay:.2f} 秒 ({avg_delay/60:.2f} 分钟)")
            print(f"  最大: {max_delay:.2f} 秒 ({max_delay/60:.2f} 分钟)")
            print(f"  最小: {min_delay:.2f} 秒 ({min_delay/60:.2f} 分钟)")
        
        if write_delays:
            avg_write_delay = sum(write_delays) / len(write_delays)
            max_write_delay = max(write_delays)
            min_write_delay = min(write_delays)
            print(f"\n数据库写入延迟 (created_at - timestamp):")
            print(f"  平均: {avg_write_delay:.2f} 秒 ({avg_write_delay/60:.2f} 分钟)")
            print(f"  最大: {max_write_delay:.2f} 秒 ({max_write_delay/60:.2f} 分钟)")
            print(f"  最小: {min_write_delay:.2f} 秒 ({min_write_delay/60:.2f} 分钟)")
            
            # 检查是否有延迟趋势
            if max_write_delay > 300:  # 超过5分钟
                print(f"\n  ⚠️  警告: 检测到较大的写入延迟")
                if max_write_delay > 3600:  # 超过1小时
                    print(f"  ⚠️  严重: 最大延迟超过 1 小时，可能存在严重问题")
        
        # 按时间段统计（查看延迟趋势）
        print("\n【按时间段统计（每 10 分钟）】")
        print("-" * 120)
        print(f"{'时间段':<20} {'记录数':<10} {'平均延迟(秒)':<15} {'最大延迟(秒)':<15} {'平均写入延迟(秒)':<20}")
        print("-" * 120)
        
        sorted_slots = sorted(time_slots.keys(), reverse=True)
        for slot in sorted_slots[:12]:  # 显示最近 12 个时间段（2小时）
            slot_data = time_slots[slot]
            avg_delay = sum(slot_data["delays"]) / len(slot_data["delays"])
            max_delay = max(slot_data["delays"])
            avg_write_delay = sum(slot_data["write_delays"]) / len(slot_data["write_delays"])
            
            print(f"{slot.strftime('%Y-%m-%d %H:%M'):<20} "
                  f"{slot_data['count']:<10} "
                  f"{avg_delay:.2f:<15} "
                  f"{max_delay:.2f:<15} "
                  f"{avg_write_delay:.2f:<20}")
        
        # 延迟趋势分析
        if len(sorted_slots) >= 2:
            recent_avg = sum(time_slots[sorted_slots[0]]["write_delays"]) / len(time_slots[sorted_slots[0]]["write_delays"])
            older_avg = sum(time_slots[sorted_slots[-1]]["write_delays"]) / len(time_slots[sorted_slots[-1]]["write_delays"])
            
            trend = recent_avg - older_avg
            print(f"\n【延迟趋势分析】")
            print("-" * 120)
            print(f"最近时间段平均延迟: {recent_avg:.2f} 秒")
            print(f"最早时间段平均延迟: {older_avg:.2f} 秒")
            if trend > 60:
                print(f"⚠️  延迟呈上升趋势: 增加了 {trend:.2f} 秒 ({trend/60:.2f} 分钟)")
                print(f"   可能原因: 消息处理积压、数据库写入性能下降、连接池耗尽")
            elif trend < -60:
                print(f"✅ 延迟呈下降趋势: 减少了 {abs(trend):.2f} 秒")
            else:
                print(f"📊 延迟基本稳定: 变化 {trend:.2f} 秒")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
