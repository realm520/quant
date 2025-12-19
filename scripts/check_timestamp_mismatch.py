#!/usr/bin/env python3
"""查询 update_time 和 raw_data 中 timestamp 不匹配的成交记录.

使用方法:
    1. 在 EC2 服务器上运行（已安装 psycopg2）:
       python3 scripts/check_timestamp_mismatch.py
    
    2. 或者直接使用 SQL 脚本:
       psql -h <host> -U <user> -d <database> -f scripts/check_timestamp_mismatch.sql
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
    print("或者使用 SQL 脚本: scripts/check_timestamp_mismatch.sql")
    sys.exit(1)

# 读取数据库配置
project_root = Path(__file__).parent.parent
config_path = project_root / "config" / "accounts.json"
with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

database_url = config["global_settings"]["database_url"]
# 解析数据库 URL
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
        
        # XT timestamp 是毫秒级时间戳，需要除以 1000
        if isinstance(timestamp, (int, float)):
            ts_sec = timestamp / 1000.0
            return datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
        return None
    except (json.JSONDecodeError, ValueError, TypeError, OSError) as e:
        return None

def main():
    """查询并显示不匹配的记录."""
    conn = psycopg2.connect(**db_params)
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 查询所有成交记录
            cur.execute("""
                SELECT 
                    id,
                    update_time,
                    account_id,
                    symbol,
                    order_id,
                    trade_id,
                    side,
                    price,
                    quantity,
                    raw_data,
                    created_at
                FROM xt_trade_update
                WHERE raw_data IS NOT NULL
                ORDER BY update_time DESC
                LIMIT 1000
            """)
            
            rows = cur.fetchall()
        
        mismatches = []
        for row in rows:
            raw_data_str = row["raw_data"]
            if not raw_data_str:
                continue
            
            # 解析 raw_data 中的 timestamp
            timestamp_dt = parse_timestamp_from_raw_data(raw_data_str)
            if timestamp_dt is None:
                continue
            
            # 比较 update_time 和 timestamp 转换后的时间
            update_time = row["update_time"]
            if isinstance(update_time, datetime):
                # 计算时间差（秒）
                time_diff = abs((update_time - timestamp_dt).total_seconds())
                
                # 如果时间差超过 1 秒，认为不匹配
                if time_diff > 1.0:
                    mismatches.append({
                        "id": row["id"],
                        "update_time": update_time,
                        "timestamp_from_raw": timestamp_dt,
                        "time_diff_seconds": time_diff,
                        "account_id": row["account_id"],
                        "symbol": row["symbol"],
                        "order_id": row["order_id"],
                        "trade_id": row["trade_id"],
                        "side": row["side"],
                        "price": row["price"],
                        "quantity": row["quantity"],
                        "raw_data": raw_data_str,
                        "created_at": row["created_at"],
                    })
        
        # 按 update_time 降序排列，取最新的10条
        mismatches.sort(key=lambda x: x["update_time"], reverse=True)
        top_mismatches = mismatches[:10]
        
        print(f"总共找到 {len(mismatches)} 条不匹配的记录")
        print(f"显示最新的 {len(top_mismatches)} 条：\n")
        print("=" * 120)
        
        for idx, record in enumerate(top_mismatches, 1):
            print(f"\n【记录 {idx}】")
            print(f"ID: {record['id']}")
            print(f"账户: {record['account_id']}")
            print(f"交易对: {record['symbol']}")
            print(f"订单ID: {record['order_id']}")
            print(f"成交ID: {record['trade_id']}")
            print(f"方向: {record['side']}")
            print(f"价格: {record['price']}")
            print(f"数量: {record['quantity']}")
            print(f"数据库 update_time: {record['update_time']}")
            print(f"raw_data timestamp 转换后: {record['timestamp_from_raw']}")
            print(f"时间差: {record['time_diff_seconds']:.2f} 秒 ({record['time_diff_seconds']/60:.2f} 分钟)")
            print(f"创建时间: {record['created_at']}")
            print(f"原始数据: {record['raw_data'][:200]}...")  # 只显示前200个字符
            print("-" * 120)
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()
