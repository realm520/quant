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

class TestDataWriter:
    """测试数据写入器基类."""
    
    def __init__(self, db_manager: DatabaseManager, account_id: str, table_name: str, batch_size: int = 50, batch_timeout: float = 0.5):
        self.db_manager = db_manager
        self.account_id = account_id
        self.table_name = table_name
        self.batch = []
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
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
                print(f"Error in {self.table_name} write loop: {e}")
    
    async def _flush_batch(self):
        """刷新批次到数据库（子类实现）."""
        raise NotImplementedError
    
    def get_queue_size(self) -> int:
        """获取当前队列大小."""
        return len(self.batch)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取写入器统计信息."""
        return {
            "table_name": self.table_name,
            "queue_size": len(self.batch),
            "batch_size": self.batch_size,
            "last_flush_time": self.last_flush_time.isoformat() if self.last_flush_time else None,
        }


class TestTradeWriter(TestDataWriter):
    """测试用的成交写入器，写入到测试表."""
    
    def __init__(self, db_manager: DatabaseManager, account_id: str):
        super().__init__(db_manager, account_id, "xt_trade_update_test", batch_size=50, batch_timeout=0.5)
    
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
                    
                    # 简化输出，不显示批量写入信息
                    pass
        
        except Exception as e:
            print(f"✗ 写入失败: {e}")
            import traceback
            traceback.print_exc()


class TestOrderWriter(TestDataWriter):
    """测试用的订单写入器，写入到测试表."""
    
    def __init__(self, db_manager: DatabaseManager, account_id: str):
        super().__init__(db_manager, account_id, "xt_order_update_test", batch_size=50, batch_timeout=0.5)
    
    async def add_order(self, order_data: Dict[str, Any], message_received_at: datetime):
        """添加订单数据到批次."""
        order_data["_message_received_at"] = message_received_at.isoformat()
        self.batch.append({
            "data": order_data,
            "message_received_at": message_received_at,
        })
        
        if len(self.batch) >= self.batch_size:
            await self._flush_batch()
    
    async def _flush_batch(self):
        """刷新订单批次到数据库."""
        if not self.batch:
            return
        
        batch_start = datetime.utcnow()
        batch_to_write = self.batch.copy()
        self.batch = []
        self.last_flush_time = datetime.utcnow()
        
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import text
                
                commit_start = datetime.utcnow()
                current_time = datetime.utcnow()
                
                insert_data = []
                for message in batch_to_write:
                    order_data = message["data"]
                    message_received_at = message["message_received_at"]
                    
                    order_id = order_data.get("orderId", "")
                    if not order_id:
                        continue
                    
                    timestamp = order_data.get("timestamp") or order_data.get("createdTime") or order_data.get("createTime")
                    timestamp_from_raw = None
                    if timestamp:
                        try:
                            if isinstance(timestamp, (int, float)):
                                ts_sec = timestamp / 1000.0 if timestamp > 1e12 else timestamp
                                timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        except (ValueError, OSError):
                            pass
                    
                    queue_wait_time_ms = (batch_start - message_received_at).total_seconds() * 1000
                    delay_from_timestamp_ms = None
                    if timestamp_from_raw and message_received_at:
                        delay_from_timestamp_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                    
                    insert_data.append({
                        "update_time": timestamp_from_raw or current_time,
                        "account_id": self.account_id,
                        "symbol": order_data.get("symbol", ""),
                        "order_id": str(order_id),
                        "client_order_id": order_data.get("clientOrderId", ""),
                        "side": order_data.get("orderSide", ""),
                        "order_type": order_data.get("orderType", ""),
                        "position_side": order_data.get("positionSide", ""),
                        "quantity": float(Decimal(order_data.get("origQty", "0"))),
                        "price": float(Decimal(order_data.get("price", "0"))) if order_data.get("price") else None,
                        "filled_quantity": float(Decimal(order_data.get("executedQty", "0"))),
                        "status": order_data.get("state", ""),
                        "time_in_force": order_data.get("timeInForce", ""),
                        "create_time": self._parse_timestamp(order_data.get("createdTime") or order_data.get("createTime")),
                        "update_time_order": self._parse_timestamp(order_data.get("updatedTime") or order_data.get("updateTime")),
                        "message_received_at": message_received_at,
                        "queue_wait_time_ms": queue_wait_time_ms,
                        "processing_duration_ms": None,
                        "database_write_duration_ms": None,
                        "timestamp_from_raw": timestamp_from_raw,
                        "delay_from_timestamp_ms": delay_from_timestamp_ms,
                        "raw_data": json.dumps(order_data, ensure_ascii=False),
                        "created_at": current_time,
                    })
                
                if insert_data:
                    insert_sql = text("""
                        INSERT INTO xt_order_update_test (
                            update_time, account_id, symbol, order_id, client_order_id, side, order_type,
                            position_side, quantity, price, filled_quantity, status, time_in_force,
                            create_time, update_time_order, message_received_at, queue_wait_time_ms,
                            processing_duration_ms, database_write_duration_ms, timestamp_from_raw,
                            delay_from_timestamp_ms, raw_data, created_at
                        ) VALUES (
                            :update_time, :account_id, :symbol, :order_id, :client_order_id, :side, :order_type,
                            :position_side, :quantity, :price, :filled_quantity, :status, :time_in_force,
                            :create_time, :update_time_order, :message_received_at, :queue_wait_time_ms,
                            :processing_duration_ms, :database_write_duration_ms, :timestamp_from_raw,
                            :delay_from_timestamp_ms, :raw_data, :created_at
                        )
                    """)
                    
                    for r in insert_data:
                        await session.execute(insert_sql, r)
                    
                    await session.commit()
                    commit_duration = (datetime.utcnow() - commit_start).total_seconds() * 1000
                    
                    # 更新 processing_duration_ms 和 database_write_duration_ms
                    if insert_data:
                        order_ids = [r["order_id"] for r in insert_data]
                        update_sql = text("""
                            UPDATE xt_order_update_test
                            SET processing_duration_ms = (EXTRACT(EPOCH FROM (NOW() - message_received_at)) * 1000),
                                database_write_duration_ms = :duration
                            WHERE created_at >= :created_at_start
                            AND created_at <= :created_at_end
                            AND order_id = ANY(:order_ids)
                        """)
                        
                        await session.execute(
                            update_sql,
                            {
                                "duration": commit_duration,
                                "created_at_start": current_time,
                                "created_at_end": datetime.utcnow(),
                                "order_ids": order_ids
                            }
                        )
                        await session.commit()
                    
                    # 简化输出，不显示批量写入信息
                    pass
        
        except Exception as e:
            print(f"✗ 订单写入失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _parse_timestamp(self, value):
        """解析时间戳."""
        if not value:
            return None
        try:
            if isinstance(value, (int, float)):
                ts_sec = value / 1000.0 if value > 1e12 else value
                return datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, OSError):
            pass
        return None


class TestPositionWriter(TestDataWriter):
    """测试用的持仓写入器，写入到测试表."""
    
    def __init__(self, db_manager: DatabaseManager, account_id: str):
        super().__init__(db_manager, account_id, "xt_position_update_test", batch_size=50, batch_timeout=0.5)
    
    async def add_position(self, position_data: Dict[str, Any], message_received_at: datetime):
        """添加持仓数据到批次."""
        position_data["_message_received_at"] = message_received_at.isoformat()
        self.batch.append({
            "data": position_data,
            "message_received_at": message_received_at,
        })
        
        if len(self.batch) >= self.batch_size:
            await self._flush_batch()
    
    async def _flush_batch(self):
        """刷新持仓批次到数据库."""
        if not self.batch:
            return
        
        batch_start = datetime.utcnow()
        batch_to_write = self.batch.copy()
        self.batch = []
        self.last_flush_time = datetime.utcnow()
        
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import text
                
                commit_start = datetime.utcnow()
                current_time = datetime.utcnow()
                
                insert_data = []
                for message in batch_to_write:
                    position_data = message["data"]
                    message_received_at = message["message_received_at"]
                    
                    symbol = position_data.get("symbol", "")
                    if not symbol:
                        continue
                    
                    quantity = Decimal(position_data.get("positionSize", "0"))
                    if quantity == 0:
                        continue
                    
                    timestamp = position_data.get("timestamp") or position_data.get("updateTime")
                    timestamp_from_raw = None
                    if timestamp:
                        try:
                            if isinstance(timestamp, (int, float)):
                                ts_sec = timestamp / 1000.0 if timestamp > 1e12 else timestamp
                                timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        except (ValueError, OSError):
                            pass
                    
                    queue_wait_time_ms = (batch_start - message_received_at).total_seconds() * 1000
                    delay_from_timestamp_ms = None
                    if timestamp_from_raw and message_received_at:
                        delay_from_timestamp_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                    
                    insert_data.append({
                        "update_time": timestamp_from_raw or current_time,
                        "account_id": self.account_id,
                        "symbol": symbol,
                        "side": position_data.get("positionSide", ""),
                        "quantity": float(quantity),
                        "entry_price": float(Decimal(position_data.get("entryPrice", "0"))) if position_data.get("entryPrice") else None,
                        "mark_price": float(Decimal(position_data.get("markPrice", "0"))) if position_data.get("markPrice") else None,
                        "liquidation_price": float(Decimal(position_data.get("liquidationPrice", "0"))) if position_data.get("liquidationPrice") else None,
                        "unrealized_pnl": float(Decimal(position_data.get("unrealizedPnl", "0"))) if position_data.get("unrealizedPnl") else None,
                        "leverage": int(position_data.get("leverage", 1)) if position_data.get("leverage") else None,
                        "margin": float(Decimal(position_data.get("margin", "0"))) if position_data.get("margin") else None,
                        "roe": float(Decimal(position_data.get("roe", "0"))) if position_data.get("roe") else None,
                        "message_received_at": message_received_at,
                        "queue_wait_time_ms": queue_wait_time_ms,
                        "processing_duration_ms": None,
                        "database_write_duration_ms": None,
                        "timestamp_from_raw": timestamp_from_raw,
                        "delay_from_timestamp_ms": delay_from_timestamp_ms,
                        "raw_data": json.dumps(position_data, ensure_ascii=False),
                        "created_at": current_time,
                    })
                
                if insert_data:
                    insert_sql = text("""
                        INSERT INTO xt_position_update_test (
                            update_time, account_id, symbol, side, quantity, entry_price, mark_price,
                            liquidation_price, unrealized_pnl, leverage, margin, roe,
                            message_received_at, queue_wait_time_ms, processing_duration_ms,
                            database_write_duration_ms, timestamp_from_raw, delay_from_timestamp_ms,
                            raw_data, created_at
                        ) VALUES (
                            :update_time, :account_id, :symbol, :side, :quantity, :entry_price, :mark_price,
                            :liquidation_price, :unrealized_pnl, :leverage, :margin, :roe,
                            :message_received_at, :queue_wait_time_ms, :processing_duration_ms,
                            :database_write_duration_ms, :timestamp_from_raw, :delay_from_timestamp_ms,
                            :raw_data, :created_at
                        )
                    """)
                    
                    for r in insert_data:
                        await session.execute(insert_sql, r)
                    
                    await session.commit()
                    commit_duration = (datetime.utcnow() - commit_start).total_seconds() * 1000
                    
                    # 更新 processing_duration_ms 和 database_write_duration_ms
                    if insert_data:
                        symbols = [r["symbol"] for r in insert_data]
                        update_sql = text("""
                            UPDATE xt_position_update_test
                            SET processing_duration_ms = (EXTRACT(EPOCH FROM (NOW() - message_received_at)) * 1000),
                                database_write_duration_ms = :duration
                            WHERE created_at >= :created_at_start
                            AND created_at <= :created_at_end
                            AND symbol = ANY(:symbols)
                        """)
                        
                        await session.execute(
                            update_sql,
                            {
                                "duration": commit_duration,
                                "created_at_start": current_time,
                                "created_at_end": datetime.utcnow(),
                                "symbols": symbols
                            }
                        )
                        await session.commit()
                    
                    # 简化输出，不显示批量写入信息
                    pass
        
        except Exception as e:
            print(f"✗ 持仓写入失败: {e}")
            import traceback
            traceback.print_exc()


class TestXTUserStreamService(XTUserStreamService):
    """测试用的 XT 用户流服务，写入到测试表."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_trade_writer = None
        self.test_order_writer = None
        self.test_position_writer = None
        self.monitor_task = None
        self.start_time = None
        self.message_count = 0
        self.last_disconnect_time = None
    
    async def start(self) -> None:
        """启动服务并初始化测试写入器."""
        self.start_time = datetime.utcnow()
        
        # 初始化测试写入器
        if "trade" in self.enabled_channels:
            self.test_trade_writer = TestTradeWriter(self.db_manager, self.account_id or "test")
            await self.test_trade_writer.start()
        
        if "order" in self.enabled_channels:
            self.test_order_writer = TestOrderWriter(self.db_manager, self.account_id or "test")
            await self.test_order_writer.start()
        
        if "position" in self.enabled_channels:
            self.test_position_writer = TestPositionWriter(self.db_manager, self.account_id or "test")
            await self.test_position_writer.start()
        
        # 启动队列监控任务
        self.monitor_task = asyncio.create_task(self._monitor_queues())
        
        # 记录初始连接事件
        await self._record_connection_event("connect", notes="Initial connection")
        
        # 调用父类启动
        await super().start()
    
    async def stop(self) -> None:
        """停止服务并刷新测试数据."""
        # 停止监控任务
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        if self.test_trade_writer:
            await self.test_trade_writer.stop()
        if self.test_order_writer:
            await self.test_order_writer.stop()
        if self.test_position_writer:
            await self.test_position_writer.stop()
        
        # 记录断开连接事件
        await self._record_connection_event("disconnect", notes="Service stopped")
        
        await super().stop()
    
    async def _record_connection_event(self, event_type: str, reconnect_attempt_number: int = None, 
                                       disconnect_duration_seconds: float = None, notes: str = None):
        """记录 WebSocket 连接事件到测试表."""
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import text
                
                insert_sql = text("""
                    INSERT INTO xt_websocket_connection_events_test (
                        event_time, account_id, event_type, reconnect_attempt_number,
                        disconnect_duration_seconds, message_count_before_event, notes, created_at
                    ) VALUES (
                        :event_time, :account_id, :event_type, :reconnect_attempt_number,
                        :disconnect_duration_seconds, :message_count_before_event, :notes, :created_at
                    )
                """)
                
                await session.execute(insert_sql, {
                    "event_time": datetime.utcnow(),
                    "account_id": self.account_id or "test",
                    "event_type": event_type,
                    "reconnect_attempt_number": reconnect_attempt_number,
                    "disconnect_duration_seconds": disconnect_duration_seconds,
                    "message_count_before_event": self.message_count,
                    "notes": notes,
                    "created_at": datetime.utcnow(),
                })
                await session.commit()
                
                # 简化连接事件输出
                event_time_str = datetime.utcnow().strftime('%H:%M:%S')
                if event_type == "reconnect" and disconnect_duration_seconds:
                    print(f"📡 [{event_time_str}] 重连 (断开 {disconnect_duration_seconds:.1f}秒)")
                elif event_type == "disconnect":
                    print(f"📡 [{event_time_str}] 断开连接")
                elif event_type == "connect":
                    print(f"📡 [{event_time_str}] 连接成功")
                elif event_type == "reconnect_attempt":
                    print(f"📡 [{event_time_str}] 重连尝试 #{reconnect_attempt_number}")
        
        except Exception as e:
            print(f"✗ 记录连接事件失败: {e}")
    
    async def _connect_and_listen(self):
        """重写连接方法，记录重连事件."""
        from websockets.exceptions import ConnectionClosed
        
        # 检查是否是重连
        is_reconnect = self.last_disconnect_time is not None
        
        if is_reconnect:
            disconnect_duration = (datetime.utcnow() - self.last_disconnect_time).total_seconds()
            await self._record_connection_event(
                "reconnect",
                disconnect_duration_seconds=disconnect_duration,
                notes=f"Reconnected after {disconnect_duration:.1f} seconds"
            )
            self.last_disconnect_time = None
        
        # 调用父类方法
        try:
            await super()._connect_and_listen()
        except ConnectionClosed as exc:
            # 记录断开事件
            if not self.last_disconnect_time:
                self.last_disconnect_time = datetime.utcnow()
                await self._record_connection_event(
                    "disconnect",
                    notes=f"Connection closed: code={exc.code}, reason={exc.reason}"
                )
            raise
        except Exception as e:
            # 记录断开事件（如果还没有记录）
            if not self.last_disconnect_time:
                self.last_disconnect_time = datetime.utcnow()
                await self._record_connection_event(
                    "disconnect",
                    notes=f"Connection error: {str(e)[:100]}"
                )
            raise
    
    async def _monitor_queues(self):
        """定期监控队列状态."""
        while True:
            try:
                await asyncio.sleep(60)  # 每60秒输出一次状态
                
                elapsed = (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0
                elapsed_min = int(elapsed // 60)
                elapsed_sec = int(elapsed % 60)
                
                stats = []
                if self.test_trade_writer:
                    trade_stats = self.test_trade_writer.get_stats()
                    stats.append(f"成交队列: {trade_stats['queue_size']}/{trade_stats['batch_size']}")
                
                if self.test_order_writer:
                    order_stats = self.test_order_writer.get_stats()
                    stats.append(f"订单队列: {order_stats['queue_size']}/{order_stats['batch_size']}")
                
                if self.test_position_writer:
                    position_stats = self.test_position_writer.get_stats()
                    stats.append(f"持仓队列: {position_stats['queue_size']}/{position_stats['batch_size']}")
                
                # 检查是否有堵塞（队列大小超过批次大小的2倍）
                warnings = []
                if self.test_trade_writer and self.test_trade_writer.get_queue_size() > self.test_trade_writer.batch_size * 2:
                    warnings.append("⚠️  成交队列可能堵塞")
                if self.test_order_writer and self.test_order_writer.get_queue_size() > self.test_order_writer.batch_size * 2:
                    warnings.append("⚠️  订单队列可能堵塞")
                if self.test_position_writer and self.test_position_writer.get_queue_size() > self.test_position_writer.batch_size * 2:
                    warnings.append("⚠️  持仓队列可能堵塞")
                
                # 简化队列状态输出，每5分钟输出一次
                if elapsed_min % 5 == 0 and elapsed_sec < 10:
                    status_line = f"[{elapsed_min:02d}:{elapsed_sec:02d}] " + " | ".join(stats)
                    if warnings:
                        status_line += " | " + " | ".join(warnings)
                    print(status_line)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"监控任务错误: {e}")
    
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
            # 增加消息计数
            self.message_count += 1
            
            # 计算延迟并输出
            timestamp = trade_data.get("timestamp")
            if timestamp:
                try:
                    ts_sec = timestamp / 1000.0
                    timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                    delay_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                    delay_sec = delay_ms / 1000.0
                    
                    # 只输出关键信息：接收时间、事件时间、延迟
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
            
            # 添加到测试写入器（记录真实的消息接收时间）
            if self.test_trade_writer:
                await self.test_trade_writer.add_trade(trade_data, message_received_at)
            
            # 不调用父类的保存方法（避免写入正式表，只写入测试表）
            # await self._save_trade_update(trade_data)
            
        except Exception as e:
            print(f"Error handling trade update: {e}")
            import traceback
            traceback.print_exc()
    
    async def _handle_order_update(self, data: Dict[str, Any]) -> None:
        """处理订单更新，写入测试表."""
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
            # 增加消息计数
            self.message_count += 1
            
            # 计算延迟并输出
            timestamp = order_data.get("timestamp") or order_data.get("createdTime") or order_data.get("createTime")
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0 if timestamp > 1e12 else timestamp
                        timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        delay_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                        delay_sec = delay_ms / 1000.0
                        
                        # 只输出关键信息：接收时间、事件时间、延迟
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
            
            # 添加到测试写入器
            if self.test_order_writer:
                await self.test_order_writer.add_order(order_data, message_received_at)
            
            # 不调用父类的保存方法（避免写入正式表，只写入测试表）
            # await self._save_order_update(order_data)
            
        except Exception as e:
            print(f"Error handling order update: {e}")
            import traceback
            traceback.print_exc()
    
    async def _handle_position_update(self, data: Dict[str, Any]) -> None:
        """处理持仓更新，写入测试表."""
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
            # 增加消息计数
            self.message_count += 1
            
            # 计算延迟并输出
            timestamp = position_data.get("timestamp") or position_data.get("updateTime")
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0 if timestamp > 1e12 else timestamp
                        timestamp_from_raw = datetime.fromtimestamp(ts_sec, tz=timezone.utc).replace(tzinfo=None)
                        delay_ms = (message_received_at - timestamp_from_raw).total_seconds() * 1000
                        delay_sec = delay_ms / 1000.0
                        
                        # 只输出关键信息：接收时间、事件时间、延迟
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
            
            # 添加到测试写入器
            if self.test_position_writer:
                await self.test_position_writer.add_position(position_data, message_received_at)
            
            # 不调用父类的保存方法（避免写入正式表，只写入测试表）
            # await self._save_position_update(position_data)
            
        except Exception as e:
            print(f"Error handling position update: {e}")
            import traceback
            traceback.print_exc()


async def main():
    """主函数."""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试真实成交消息队列性能")
    parser.add_argument("--config", type=str, default="config/accounts.json", help="配置文件路径")
    parser.add_argument("--account-id", type=str, help="账号ID（可选）")
    parser.add_argument("--duration", type=int, default=1200, help="测试持续时间（秒，默认: 1200，即20分钟）")
    parser.add_argument("--channels", type=str, default="trade,order,position", help="订阅的频道，用逗号分隔（默认: trade,order,position）")
    
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
    print(f"订阅频道: {args.channels}")
    
    channels_list = args.channels.split(",") if args.channels else ["trade"]
    test_tables = []
    if "trade" in channels_list:
        test_tables.append("xt_trade_update_test")
    if "order" in channels_list:
        test_tables.append("xt_order_update_test")
    if "position" in channels_list:
        test_tables.append("xt_position_update_test")
    
    print(f"数据将写入测试表: {', '.join(test_tables)}\n")
    
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
    print("队列状态监控（每60秒输出一次）:")
    print("-" * 80)
    
    try:
        # 在后台运行服务
        service_task = asyncio.create_task(service.start())
        
        # 等待指定时间
        await asyncio.sleep(args.duration)
        
        print("\n" + "-" * 80)
        print(f"测试时间到，停止服务...")
        await service.stop()
        service_task.cancel()
        
        try:
            await service_task
        except asyncio.CancelledError:
            pass
        
        # 输出最终队列状态
        print("\n最终队列状态:")
        if service.test_trade_writer:
            print(f"  成交队列剩余: {service.test_trade_writer.get_queue_size()} 条")
        if service.test_order_writer:
            print(f"  订单队列剩余: {service.test_order_writer.get_queue_size()} 条")
        if service.test_position_writer:
            print(f"  持仓队列剩余: {service.test_position_writer.get_queue_size()} 条")
        
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
