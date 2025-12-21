#!/usr/bin/env python3
"""测试所有频道（trade、order、position）的延迟趋势.

监控数据插入到数据库的时间减去数据实际时间的延迟趋势，
确保延迟不会累积。
"""

import asyncio
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any
from decimal import Decimal
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tri_arb.config.account_manager import AccountManager
from tri_arb.services.xt_user_stream import XTUserStreamService
from tri_arb.storage.database import DatabaseManager

logger = None


class DelayMonitor:
    """延迟监控器，实时统计延迟趋势."""
    
    def __init__(self, db_manager: DatabaseManager, account_id: str, window_minutes: int = 5):
        self.db_manager = db_manager
        self.account_id = account_id
        self.window_minutes = window_minutes
        self.trade_delays = defaultdict(list)  # {time_slot: [delays]}
        self.order_delays = defaultdict(list)
        self.position_delays = defaultdict(list)
        self.monitor_task = None
        self.pending_records = []  # 待查询的记录 {(channel, id_key, timestamp_from_raw, message_received_at)}
    
    def record_pending(self, channel: str, id_key: str, timestamp_from_raw: datetime, message_received_at: datetime):
        """记录待查询的记录（等待数据库写入后查询实际的 created_at）."""
        if not timestamp_from_raw or not message_received_at:
            return
        
        self.pending_records.append({
            "channel": channel,
            "id_key": id_key,
            "timestamp_from_raw": timestamp_from_raw,
            "message_received_at": message_received_at,
            "recorded_at": datetime.utcnow()
        })
    
    async def query_delays_from_db(self):
        """从数据库查询实际的延迟."""
        if not self.pending_records:
            return
        
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import text
                
                # 查询最近写入的记录（每次最多查询50条，避免查询太慢）
                records_to_query = self.pending_records[:50]
                processed_ids = set()
                processed_records = []
                
                for record in records_to_query:
                    channel = record["channel"]
                    id_key = record["id_key"]
                    timestamp_from_raw = record["timestamp_from_raw"]
                    
                    # 避免重复查询
                    query_key = f"{channel}_{id_key}"
                    if query_key in processed_ids:
                        continue
                    processed_ids.add(query_key)
                    
                    try:
                        if channel == "trade":
                            # 查询成交记录
                            query = text("""
                                SELECT created_at 
                                FROM xt_trade_update 
                                WHERE trade_id = :id_key 
                                AND account_id = :account_id
                                ORDER BY created_at DESC 
                                LIMIT 1
                            """)
                            result = await session.execute(query, {"id_key": id_key, "account_id": self.account_id})
                        elif channel == "order":
                            # 查询订单记录
                            query = text("""
                                SELECT created_at 
                                FROM xt_order_update 
                                WHERE order_id = :id_key 
                                AND account_id = :account_id
                                ORDER BY created_at DESC 
                                LIMIT 1
                            """)
                            result = await session.execute(query, {"id_key": id_key, "account_id": self.account_id})
                        elif channel == "position":
                            # 查询持仓记录（需要 symbol + side）
                            parts = id_key.split("_", 1)
                            if len(parts) == 2:
                                symbol = parts[0]
                                side = parts[1]
                                query = text("""
                                    SELECT created_at 
                                    FROM xt_position_update 
                                    WHERE symbol = :symbol 
                                    AND side = :side
                                    AND account_id = :account_id
                                    ORDER BY created_at DESC 
                                    LIMIT 1
                                """)
                                result = await session.execute(
                                    query,
                                    {"symbol": symbol, "side": side, "account_id": self.account_id}
                                )
                            else:
                                continue
                        else:
                            continue
                        
                        row = result.fetchone()
                        if row and row[0]:
                            created_at = row[0]
                            delay_seconds = (created_at - timestamp_from_raw).total_seconds()
                            
                            # 按时间窗口分组
                            time_slot = created_at.replace(second=0, microsecond=0)
                            time_slot = time_slot.replace(minute=(time_slot.minute // self.window_minutes) * self.window_minutes)
                            
                            if channel == "trade":
                                self.trade_delays[time_slot].append(delay_seconds)
                            elif channel == "order":
                                self.order_delays[time_slot].append(delay_seconds)
                            elif channel == "position":
                                self.position_delays[time_slot].append(delay_seconds)
                            
                            processed_records.append(record)
                    except Exception as e:
                        # 查询失败，跳过这条记录
                        pass
                
                # 清理已查询的记录（保留最近5分钟的，以防数据库写入延迟）
                cutoff_time = datetime.utcnow() - timedelta(minutes=5)
                self.pending_records = [
                    r for r in self.pending_records 
                    if r not in processed_records and r["recorded_at"] > cutoff_time
                ]
                
        except Exception as e:
            print(f"查询延迟失败: {e}")
    
    async def start_monitoring(self):
        """启动延迟监控任务."""
        self.monitor_task = asyncio.create_task(self._monitor_loop())
    
    async def stop_monitoring(self):
        """停止监控任务."""
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
    
    async def _monitor_loop(self):
        """定期输出延迟统计."""
        while True:
            try:
                await asyncio.sleep(30)  # 每30秒查询一次数据库并输出统计
                await self.query_delays_from_db()
                self._print_statistics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"监控任务错误: {e}")
    
    def _print_statistics(self):
        """打印延迟统计."""
        print("\n" + "=" * 80)
        print(f"延迟趋势统计 ({datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')})")
        print("=" * 80)
        
        # 成交延迟
        if self.trade_delays:
            print("\n【成交延迟趋势】")
            print("-" * 80)
            print(f"{'时间段':<20} {'记录数':<10} {'平均延迟(秒)':<15} {'最大延迟(秒)':<15} {'最小延迟(秒)':<15}")
            print("-" * 80)
            for time_slot in sorted(self.trade_delays.keys(), reverse=True)[:10]:
                delays = self.trade_delays[time_slot]
                avg_delay = sum(delays) / len(delays)
                max_delay = max(delays)
                min_delay = min(delays)
                time_str = time_slot.strftime('%Y-%m-%d %H:%M')
                print(f"{time_str:<20} {len(delays):<10} {avg_delay:<15.2f} {max_delay:<15.2f} {min_delay:<15.2f}")
                
                # 检查是否有累积趋势
                if avg_delay > 60:
                    print(f"  ⚠️  警告: 平均延迟 {avg_delay:.1f} 秒，可能存在延迟累积")
        
        # 订单延迟
        if self.order_delays:
            print("\n【订单延迟趋势】")
            print("-" * 80)
            print(f"{'时间段':<20} {'记录数':<10} {'平均延迟(秒)':<15} {'最大延迟(秒)':<15} {'最小延迟(秒)':<15}")
            print("-" * 80)
            for time_slot in sorted(self.order_delays.keys(), reverse=True)[:10]:
                delays = self.order_delays[time_slot]
                avg_delay = sum(delays) / len(delays)
                max_delay = max(delays)
                min_delay = min(delays)
                time_str = time_slot.strftime('%Y-%m-%d %H:%M')
                print(f"{time_str:<20} {len(delays):<10} {avg_delay:<15.2f} {max_delay:<15.2f} {min_delay:<15.2f}")
                
                if avg_delay > 60:
                    print(f"  ⚠️  警告: 平均延迟 {avg_delay:.1f} 秒，可能存在延迟累积")
        
        # 持仓延迟
        if self.position_delays:
            print("\n【持仓延迟趋势】")
            print("-" * 80)
            print(f"{'时间段':<20} {'记录数':<10} {'平均延迟(秒)':<15} {'最大延迟(秒)':<15} {'最小延迟(秒)':<15}")
            print("-" * 80)
            for time_slot in sorted(self.position_delays.keys(), reverse=True)[:10]:
                delays = self.position_delays[time_slot]
                avg_delay = sum(delays) / len(delays)
                max_delay = max(delays)
                min_delay = min(delays)
                time_str = time_slot.strftime('%Y-%m-%d %H:%M')
                print(f"{time_str:<20} {len(delays):<10} {avg_delay:<15.2f} {max_delay:<15.2f} {min_delay:<15.2f}")
                
                if avg_delay > 60:
                    print(f"  ⚠️  警告: 平均延迟 {avg_delay:.1f} 秒，可能存在延迟累积")
        
        print("=" * 80 + "\n")


class TestXTUserStreamService(XTUserStreamService):
    """测试用的 XT 用户流服务，监控延迟趋势."""
    
    def __init__(self, *args, delay_monitor: DelayMonitor = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.delay_monitor = delay_monitor
    
    async def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """处理成交更新，记录延迟."""
        if "trade" not in self.enabled_channels:
            return
        
        # 记录消息接收时间
        message_received_at = datetime.utcnow()
        
        # 提取XT成交数据
        trade_data = data.get("data", {})
        if not trade_data:
            return
        
        # 检查数据是否有变化
        if not self._has_trade_changed(trade_data):
            return
        
        try:
            # 记录待查询的延迟（等待数据库写入后查询）
            timestamp = trade_data.get("timestamp")
            order_id = trade_data.get("orderId", "")
            if timestamp and order_id and self.delay_monitor:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0
                        timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        trade_id = f"{order_id}_{timestamp}"
                        self.delay_monitor.record_pending("trade", trade_id, timestamp_from_raw, message_received_at)
                except (ValueError, OSError):
                    pass
            
            # 显示成交更新（简化输出）
            timestamp = trade_data.get("timestamp")
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0
                        timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        delay_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                        delay_sec = delay_ms / 1000.0
                        
                        recv_str = message_received_at.strftime('%H:%M:%S.%f')[:-3]
                        event_str = timestamp_from_raw.strftime('%H:%M:%S.%f')[:-3]
                        
                        if delay_sec > 60:
                            delay_str = f"{delay_sec/60:.1f}分钟"
                        elif delay_sec > 1:
                            delay_str = f"{delay_sec:.1f}秒"
                        else:
                            delay_str = f"{delay_ms:.0f}ms"
                        
                        print(f"成交 | 接收: {recv_str} | 事件: {event_str} | 延迟: {delay_str}")
                except (ValueError, OSError):
                    pass
            
            # 调用父类方法（会放入队列）
            await super()._handle_trade_update(data)
            
        except Exception as e:
            print(f"Error handling trade update: {e}")
            import traceback
            traceback.print_exc()
    
    async def _handle_order_update(self, data: Dict[str, Any]) -> None:
        """处理订单更新，记录延迟."""
        if "order" not in self.enabled_channels:
            return
        
        # 记录消息接收时间
        message_received_at = datetime.utcnow()
        
        # 提取XT订单数据
        order_data = data.get("data", {})
        if not order_data:
            return
        
        # 检查数据是否有变化
        if not self._has_order_changed(order_data):
            return
        
        try:
            # 记录待查询的延迟
            timestamp = order_data.get("timestamp") or order_data.get("updatedTime") or order_data.get("updateTime") or order_data.get("createdTime") or order_data.get("createTime")
            order_id = order_data.get("orderId", "")
            if timestamp and order_id and self.delay_monitor:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0 if timestamp > 1e12 else timestamp
                        timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        self.delay_monitor.record_pending("order", str(order_id), timestamp_from_raw, message_received_at)
                except (ValueError, OSError):
                    pass
            
            # 显示订单更新（简化输出）
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0 if timestamp > 1e12 else timestamp
                        timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        delay_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                        delay_sec = delay_ms / 1000.0
                        
                        recv_str = message_received_at.strftime('%H:%M:%S.%f')[:-3]
                        event_str = timestamp_from_raw.strftime('%H:%M:%S.%f')[:-3]
                        
                        if delay_sec > 60:
                            delay_str = f"{delay_sec/60:.1f}分钟"
                        elif delay_sec > 1:
                            delay_str = f"{delay_sec:.1f}秒"
                        else:
                            delay_str = f"{delay_ms:.0f}ms"
                        
                        print(f"订单 | 接收: {recv_str} | 事件: {event_str} | 延迟: {delay_str}")
                except (ValueError, OSError):
                    pass
            
            # 调用父类方法（会放入队列）
            await super()._handle_order_update(data)
            
        except Exception as e:
            print(f"Error handling order update: {e}")
            import traceback
            traceback.print_exc()
    
    async def _handle_position_update(self, data: Dict[str, Any]) -> None:
        """处理持仓更新，记录延迟."""
        if "position" not in self.enabled_channels:
            return
        
        # 记录消息接收时间
        message_received_at = datetime.utcnow()
        
        # 提取XT持仓数据
        position_data = data.get("data", {})
        if not position_data:
            return
        
        # 检查数据是否有变化
        if not self._has_position_changed(position_data):
            return
        
        try:
            # 记录待查询的延迟
            timestamp = position_data.get("timestamp") or position_data.get("updateTime")
            symbol = position_data.get("symbol", "")
            side = position_data.get("positionSide") or position_data.get("side", "")
            if timestamp and symbol and side and self.delay_monitor:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0 if timestamp > 1e12 else timestamp
                        timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        id_key = f"{symbol}_{side}"
                        self.delay_monitor.record_pending("position", id_key, timestamp_from_raw, message_received_at)
                except (ValueError, OSError):
                    pass
            
            # 显示持仓更新（简化输出）
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0 if timestamp > 1e12 else timestamp
                        timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        delay_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                        delay_sec = delay_ms / 1000.0
                        
                        recv_str = message_received_at.strftime('%H:%M:%S.%f')[:-3]
                        event_str = timestamp_from_raw.strftime('%H:%M:%S.%f')[:-3]
                        
                        if delay_sec > 60:
                            delay_str = f"{delay_sec/60:.1f}分钟"
                        elif delay_sec > 1:
                            delay_str = f"{delay_sec:.1f}秒"
                        else:
                            delay_str = f"{delay_ms:.0f}ms"
                        
                        print(f"持仓 | 接收: {recv_str} | 事件: {event_str} | 延迟: {delay_str}")
                except (ValueError, OSError):
                    pass
            
            # 调用父类方法（会放入队列）
            await super()._handle_position_update(data)
            
        except Exception as e:
            print(f"Error handling position update: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数."""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试所有频道的延迟趋势")
    parser.add_argument("--config", type=str, default="config/accounts.json", help="配置文件路径")
    parser.add_argument("--account-id", type=str, help="账号ID（可选）")
    parser.add_argument("--duration", type=int, default=1200, help="测试持续时间（秒，默认: 1200，即20分钟）")
    
    args = parser.parse_args()
    
    # 加载配置
    config_path = project_root / args.config
    account_manager = AccountManager(config_path)
    
    # 获取账号
    if args.account_id:
        account_config = account_manager.get_account(args.account_id)
    else:
        accounts = account_manager.get_enabled_accounts()
        if not accounts:
            print("错误: 没有可用的账号")
            return
        account_config = accounts[0]
    
    duration_min = args.duration // 60
    duration_sec = args.duration % 60
    print(f"使用账号: {account_config.account_id} ({account_config.name})")
    print(f"测试持续时间: {args.duration} 秒 ({duration_min} 分 {duration_sec} 秒)")
    print(f"订阅频道: trade, order, position")
    print("=" * 80)
    print("实时消息输出（接收时间 | 事件时间 | 延迟）:")
    print("-" * 80)
    
    # 创建数据库管理器
    db_manager = DatabaseManager()
    
    # 创建延迟监控器
    delay_monitor = DelayMonitor(
        db_manager=db_manager,
        account_id=account_config.account_id,
        window_minutes=5
    )
    await delay_monitor.start_monitoring()
    
    # 创建测试服务
    channels = {"trade", "order", "position"}
    service = TestXTUserStreamService(
        api_key=account_config.api_key,
        api_secret=account_config.api_secret,
        db_manager=db_manager,
        auto_reconnect=True,
        display_format="none",  # 不显示详细表格，只显示简化输出
        enabled_channels=channels,
        enable_data_sync=False,  # 禁用数据同步，只测试实时消息
        delay_monitor=delay_monitor,
    )
    service.account_id = account_config.account_id
    service.account_name = account_config.name
    
    # 启动服务
    print("开始订阅 WebSocket 消息...")
    
    try:
        # 在后台运行服务
        service_task = asyncio.create_task(service.start())
        
        # 等待指定时间
        await asyncio.sleep(args.duration)
        
        print("\n" + "=" * 80)
        print(f"测试时间到，停止服务...")
        await delay_monitor.stop_monitoring()
        await service.stop()
        service_task.cancel()
        
        try:
            await service_task
        except asyncio.CancelledError:
            pass
        
        # 最后查询一次数据库
        await delay_monitor.query_delays_from_db()
        
        # 输出最终统计
        print("\n" + "=" * 80)
        print("最终延迟统计:")
        delay_monitor._print_statistics()
        
        print("=" * 80)
        print("测试完成！")
        print("=" * 80)
        print(f"\n可以运行以下命令查看详细分析:")
        print(f"  python3 scripts/analyze_queue_performance.py --minutes {duration_min}")
        
    except KeyboardInterrupt:
        print("\n\n收到停止信号，正在停止服务...")
        await delay_monitor.stop_monitoring()
        await service.stop()
        service_task.cancel()
        try:
            await service_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
