#!/usr/bin/env python3
"""
实时监控订单更新频率
"""

import asyncio
import sys
from datetime import datetime, timedelta
from tri_arb.storage.database import DatabaseManager
from sqlalchemy import text
import json

async def monitor_orders():
    """实时监控订单更新"""
    db_manager = DatabaseManager()
    
    print("=" * 80)
    print("实时监控订单更新")
    print("=" * 80)
    print("按 Ctrl+C 停止监控")
    print()
    
    last_count = 0
    last_check_time = datetime.utcnow()
    
    try:
        while True:
            now = datetime.utcnow()
            # 统计最近10秒的订单
            start_time = now - timedelta(seconds=10)
            
            total_count = 0
            order_details = []
            
            async with db_manager.session() as session:
                result = await session.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name LIKE 'xt_order_updates_account%'
                    ORDER BY table_name
                """))
                tables = [row[0] for row in result.fetchall()]
                
                for table in tables:
                    try:
                        result = await session.execute(text(f'''
                            SELECT order_id, symbol, create_time, status, side, position_side, raw_data
                            FROM {table}
                            WHERE create_time >= :start_time
                            ORDER BY create_time DESC
                            LIMIT 50
                        '''), {'start_time': start_time})
                        rows = result.fetchall()
                        
                        for row in rows:
                            total_count += 1
                            order_id = str(row[0])
                            symbol = row[1]
                            create_time = row[2]
                            status = row[3]
                            side = row[4]
                            position_side = row[5]
                            raw_data = row[6]
                            
                            # 判断来源
                            source = "WebSocket"
                            if raw_data:
                                try:
                                    data = json.loads(raw_data)
                                    if isinstance(data, dict):
                                        source_type = data.get('source', '')
                                        if 'rest_sync' in source_type:
                                            source = "REST回补"
                                except:
                                    pass
                            
                            order_details.append({
                                'order_id': order_id,
                                'symbol': symbol,
                                'create_time': create_time,
                                'status': status,
                                'side': side,
                                'position_side': position_side,
                                'source': source
                            })
                    except Exception as e:
                        pass
            
            # 计算更新速率
            time_diff = (now - last_check_time).total_seconds()
            if time_diff > 0:
                rate = (total_count - last_count) / time_diff
            else:
                rate = 0
            
            # 清屏并显示
            sys.stdout.write("\033[2J\033[H")  # 清屏
            sys.stdout.flush()
            
            print("=" * 80)
            print(f"实时订单更新监控 - {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print("=" * 80)
            print()
            print(f"时间窗口: 最近10秒")
            print(f"订单总数: {total_count} 条")
            if last_count > 0:
                print(f"新增订单: {total_count - last_count} 条")
                print(f"更新速率: {rate:.2f} 条/秒")
            print()
            
            # 统计来源
            ws_count = sum(1 for o in order_details if o['source'] == 'WebSocket')
            rest_count = sum(1 for o in order_details if o['source'] == 'REST回补')
            print(f"订单来源:")
            print(f"  - WebSocket 实时: {ws_count} 条")
            print(f"  - REST API 回补: {rest_count} 条")
            print()
            
            # 统计状态分布
            status_counts = {}
            for order in order_details:
                status = order['status']
                status_counts[status] = status_counts.get(status, 0) + 1
            
            if status_counts:
                print("订单状态分布:")
                for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
                    print(f"  {status:20s}: {count:4d} 条")
                print()
            
            # 显示最新的订单
            print("最新订单（前10条）:")
            for i, order in enumerate(sorted(order_details, key=lambda x: x['create_time'], reverse=True)[:10], 1):
                create_time_str = order['create_time'].strftime('%H:%M:%S') if order['create_time'] else 'N/A'
                print(f"  [{i:2d}] {order['order_id'][:20]:20s} | {order['symbol']:15s} | {order['status']:20s} | {order['side']:4s} {order['position_side']:6s} | {order['source']:10s} | {create_time_str}")
            
            print()
            print("按 Ctrl+C 停止监控...")
            
            last_count = total_count
            last_check_time = now
            
            await asyncio.sleep(5)  # 每5秒更新一次
            
    except KeyboardInterrupt:
        print("\n\n监控已停止")

if __name__ == "__main__":
    asyncio.run(monitor_orders())

