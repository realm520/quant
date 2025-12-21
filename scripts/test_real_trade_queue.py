#!/usr/bin/env python3
"""测试真实成交消息队列性能.

从真实的 WebSocket 消息中获取数据，记录真实的延迟情况到测试表。
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
from decimal import Decimal

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tri_arb.config.account_manager import AccountManager
from tri_arb.services.xt_user_stream import XTUserStreamService
from tri_arb.storage.database import DatabaseManager

logger = None

class TestTradeWriter:
    """测试用的成交写入器，写入到测试表."""
    
    def __init__(self, db_manager: DatabaseManager, account_id: str):
        self.db_manager = db_manager
        self.account_id = account_id
        self.batch = []
        self.batch_size = 50
        self.batch_timeout = 0.5
        self.last_flush_time = datetime.utcnow()
        self.write_task = None
    
    async def start(self):
        """启动后台写入任务."""
        self.write_task = asyncio.create_task(self._write_loop())
    
    async def stop(self):
        """停止写入任务并刷新剩余数据."""
        if self.write_task:
            self.write_task.cancel()
            try:
                await self.write_task
            except asyncio.CancelledError:
                pass
        
        # 刷新剩余批次
        if self.batch:
            await self._flush_batch()
    
    async def add_trade(self, trade_data: Dict[str, Any], message_received_at: datetime):
        """添加成交数据到批次."""
        trade_data["_message_received_at"] = message_received_at.isoformat()
        self.batch.append({
            "data": trade_data,
            "message_received_at": message_received_at,
        })
        
        # 如果批次达到大小，立即刷新
        if len(self.batch) >= self.batch_size:
            await self._flush_batch()
    
    async def _write_loop(self):
        """后台写入循环."""
        while True:
            try:
                await asyncio.sleep(self.batch_timeout)
                
                # 检查是否需要刷新
                if self.batch and (datetime.utcnow() - self.last_flush_time).total_seconds() >= self.batch_timeout:
                    await self._flush_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in write loop: {e}")
    
    async def _flush_batch(self):
        """刷新批次到数据库."""
        if not self.batch:
            return
        
        batch_start = datetime.utcnow()
        batch_to_write = self.batch.copy()
        self.batch = []
        self.last_flush_time = datetime.utcnow()
        
        try:
            async with self.db_manager.session() as session:
                records = []
                
                for message in batch_to_write:
                    trade_data = message["data"]
                    message_received_at = message["message_received_at"]
                    
                    # 解析成交数据
                    order_id = trade_data.get("orderId", "")
                    timestamp = trade_data.get("timestamp")
                    trade_id = f"{order_id}_{timestamp}" if order_id and timestamp else order_id
                    
                    if not trade_id:
                        continue
                    
                    # 计算时间
                    timestamp_from_raw = None
                    if timestamp:
                        try:
                            ts_sec = timestamp / 1000.0
                            timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        except (ValueError, OSError):
                            pass
                    
                    # 计算延迟
                    queue_wait_time_ms = (batch_start - message_received_at).total_seconds() * 1000
                    delay_from_timestamp_ms = None
                    if timestamp_from_raw and message_received_at:
                        delay_from_timestamp_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                    
                    # 计算数值
                    price = Decimal(trade_data.get("price", "0"))
                    quantity = Decimal(trade_data.get("quantity", "0"))
                    quote_quantity = price * quantity
                    
                    # 创建记录字典（用于批量插入）
                    record = {
                        "update_time": timestamp_from_raw or datetime.utcnow(),
                        "account_id": self.account_id,
                        "symbol": trade_data.get("symbol", ""),
                        "order_id": str(order_id),
                        "trade_id": str(trade_id),
                        "side": trade_data.get("orderSide", ""),
                        "price": price,
                        "quantity": quantity,
                        "quote_quantity": quote_quantity,
                        "commission": Decimal("0"),
                        "commission_asset": "",
                        "is_maker": trade_data.get("isMaker", False),
                        "position_side": trade_data.get("positionSide", ""),
                        "message_received_at": message_received_at,
                        "queue_wait_time_ms": queue_wait_time_ms,
                        "timestamp_from_raw": timestamp_from_raw,
                        "delay_from_timestamp_ms": delay_from_timestamp_ms,
                        "raw_data": json.dumps(trade_data, ensure_ascii=False),
                    }
                    records.append(record)
                
                if records:
                    # 使用 SQLAlchemy 批量插入到测试表
                    from sqlalchemy import text
                    
                    commit_start = datetime.utcnow()
                    current_time = datetime.utcnow()
                    
                    # 准备插入数据
                    insert_data = []
                    for record in records:
                        # 计算 processing_duration_ms
                        processing_duration_ms = (current_time - record["message_received_at"]).total_seconds() * 1000
                        
                        insert_data.append({
                            "update_time": record["update_time"],
                            "account_id": record["account_id"],
                            "symbol": record["symbol"],
                            "order_id": record["order_id"],
                            "trade_id": record["trade_id"],
                            "side": record["side"],
                            "price": float(record["price"]),
                            "quantity": float(record["quantity"]),
                            "quote_quantity": float(record["quote_quantity"]),
                            "commission": float(record["commission"]),
                            "commission_asset": record["commission_asset"],
                            "is_maker": record["is_maker"],
                            "position_side": record["position_side"] or "",
                            "message_received_at": record["message_received_at"],
                            "queue_wait_time_ms": float(record["queue_wait_time_ms"]),
                            "processing_duration_ms": processing_duration_ms,
                            "database_write_duration_ms": None,  # 稍后更新
                            "timestamp_from_raw": record["timestamp_from_raw"],
                            "delay_from_timestamp_ms": float(record["delay_from_timestamp_ms"]) if record["delay_from_timestamp_ms"] is not None else None,
                            "raw_data": record["raw_data"],
                            "created_at": current_time,
                        })
                    
                    # 使用 SQLAlchemy 的 text() 循环插入（简单可靠）
                    from sqlalchemy import text
                    
                    insert_sql = text("""
                        INSERT INTO xt_trade_update_test (
                            update_time, account_id, symbol, order_id, trade_id, side, price, quantity,
                            quote_quantity, commission, commission_asset, is_maker, position_side,
                            message_received_at, queue_wait_time_ms, processing_duration_ms,
                            database_write_duration_ms, timestamp_from_raw, delay_from_timestamp_ms,
                            raw_data, created_at
                        ) VALUES (
                            :update_time, :account_id, :symbol, :order_id, :trade_id, :side, :price, :quantity,
                            :quote_quantity, :commission, :commission_asset, :is_maker, :position_side,
                            :message_received_at, :queue_wait_time_ms, :processing_duration_ms,
                            :database_write_duration_ms, :timestamp_from_raw, :delay_from_timestamp_ms,
                            :raw_data, :created_at
                        )
                    """)
                    
                    # 循环插入（对于批量大小 50，性能可接受）
                    for r in insert_data:
                        await session.execute(insert_sql, r)
                    
                    await session.commit()
                    
                    commit_duration = (datetime.utcnow() - commit_start).total_seconds() * 1000
                    
                    # 更新 database_write_duration_ms
                    if insert_data:
                        trade_ids = [r["trade_id"] for r in insert_data]
                        update_sql = text("""
                            UPDATE xt_trade_update_test
                            SET database_write_duration_ms = :duration
                            WHERE created_at >= :created_at_start
                            AND created_at <= :created_at_end
                            AND trade_id = ANY(:trade_ids)
                        """)
                        
                        await session.execute(
                            update_sql,
                            {
                                "duration": commit_duration,
                                "created_at_start": current_time,
                                "created_at_end": datetime.utcnow(),
                                "trade_ids": trade_ids
                            }
                        )
                        await session.commit()
                    
                    print(f"✓ 批量写入 {len(records)} 条成交记录到测试表 "
                          f"(耗时: {commit_duration:.2f}ms, 队列剩余: {len(self.batch)})")
        
        except Exception as e:
            print(f"✗ 写入失败: {e}")
            import traceback
            traceback.print_exc()


class TestXTUserStreamService(XTUserStreamService):
    """测试用的 XT 用户流服务，写入到测试表."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_writer = None
    
    async def start(self) -> None:
        """启动服务并初始化测试写入器."""
        # 初始化测试写入器
        self.test_writer = TestTradeWriter(self.db_manager, self.account_id or "test")
        await self.test_writer.start()
        
        # 调用父类启动
        await super().start()
    
    async def stop(self) -> None:
        """停止服务并刷新测试数据."""
        if self.test_writer:
            await self.test_writer.stop()
        await super().stop()
    
    async def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """处理成交更新，写入测试表."""
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
            # 显示成交更新（可选）
            await self._display_trade_update(trade_data)
            
            # 添加到测试写入器（记录真实的消息接收时间）
            if self.test_writer:
                await self.test_writer.add_trade(trade_data, message_received_at)
            
            # 不调用父类的保存方法（避免写入正式表，只写入测试表）
            # await self._save_trade_update(trade_data)
            
        except Exception as e:
            print(f"Error handling trade update: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数."""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试真实成交消息队列性能")
    parser.add_argument("--config", type=str, default="config/accounts.json", help="配置文件路径")
    parser.add_argument("--account-id", type=str, help="账号ID（可选）")
    parser.add_argument("--duration", type=int, default=300, help="测试持续时间（秒，默认: 300）")
    parser.add_argument("--channels", type=str, default="trade", help="订阅的频道（默认: trade）")
    
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
    
    print(f"使用账号: {account_config.account_id} ({account_config.name})")
    print(f"测试持续时间: {args.duration} 秒")
    print(f"订阅频道: {args.channels}")
    print(f"数据将写入测试表: xt_trade_update_test\n")
    
    # 创建数据库管理器（会自动初始化）
    db_manager = DatabaseManager()
    
    # 创建测试服务
    channels = set(args.channels.split(",")) if args.channels else {"trade"}
    service = TestXTUserStreamService(
        api_key=account_config.api_key,
        api_secret=account_config.api_secret,
        db_manager=db_manager,
        auto_reconnect=True,
        display_format="table",
        enabled_channels=channels,
        enable_data_sync=False,  # 禁用数据同步，只测试实时消息
    )
    service.account_id = account_config.account_id
    service.account_name = account_config.name
    
    # 启动服务
    print("开始订阅 WebSocket 消息...")
    print("=" * 80)
    
    try:
        # 在后台运行服务
        service_task = asyncio.create_task(service.start())
        
        # 等待指定时间
        await asyncio.sleep(args.duration)
        
        print(f"\n测试时间到，停止服务...")
        await service.stop()
        service_task.cancel()
        
        try:
            await service_task
        except asyncio.CancelledError:
            pass
        
        print("\n" + "=" * 80)
        print("测试完成！")
        print("=" * 80)
        print(f"\n可以运行以下命令查看测试结果:")
        print(f"  python3 scripts/analyze_queue_performance.py")
        
    except KeyboardInterrupt:
        print("\n\n收到停止信号，正在停止服务...")
        await service.stop()
        service_task.cancel()
        try:
            await service_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
