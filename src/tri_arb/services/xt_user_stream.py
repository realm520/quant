"""XT WebSocket user data stream service - Simplified.

Handles XT WebSocket connections for real-time account updates, position updates,
order updates, and trade updates with automatic reconnection and data synchronization.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.metrics.prometheus import (
    ensure_metrics_server,
    update_order_metrics,
    update_trade_metrics,
)
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_websocket_models import (
    XTAccountUpdate,
    XTOrderUpdate,
    XTPositionUpdate,
    XTTradeUpdate,
    XTWebSocketConnection,
)
from tri_arb.utils.async_utils import AsyncBoundedQueue

logger = get_logger(__name__)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder for Decimal types."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


class XTUserStreamService:
    """Simplified XT WebSocket user data stream service.

    Core features:
    - WebSocket subscription for account/position/order/trade updates
    - Async queue-based batch database writes
    - Automatic reconnection with data sync
    - Prometheus metrics updates
    """

    WS_URL = "wss://fstream.xt.com/ws/user"
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        db_manager: DatabaseManager,
        account_id: Optional[str] = None,
        account_name: Optional[str] = None,
        auto_reconnect: bool = True,
        max_reconnect_attempts: int = 10,
        reconnect_delay: float = 5.0,
        enabled_channels: Optional[Set[str]] = None,
        enable_data_sync: bool = True,
    ) -> None:
        """Initialize XT WebSocket service."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.db_manager = db_manager
        self.account_id = account_id
        self.account_name = account_name
        self.auto_reconnect = auto_reconnect
        self.max_reconnect_attempts = max_reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.enable_data_sync = enable_data_sync

        # Enabled channels
        default_channels = {"account", "position", "order", "trade"}
        self.enabled_channels = (
            enabled_channels if enabled_channels else default_channels
        )

        # Connection state
        self.is_running = False
        self.reconnect_attempts = 0
        self.ws = None
        self.listen_key: Optional[str] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._listen_key_refresh_task: Optional[asyncio.Task] = None
        self._connection_id: Optional[str] = None

        # Disconnect tracking for data sync
        self.disconnect_time: Optional[datetime] = None
        self.reconnect_time: Optional[datetime] = None

        # REST client for data sync
        self.rest_client: Optional[XTPerpExchange] = None

        # Change detection caches
        self._last_account_data: Dict[str, str] = {}
        self._last_position_data: Dict[str, str] = {}
        self._last_order_data: Dict[str, str] = {}
        self._last_trade_data: Dict[str, str] = {}

        # Async queues for batch processing
        self._trade_queue = AsyncBoundedQueue(
            maxsize=1000,
            overflow_handler=lambda item: self._handle_queue_overflow(item, "trade"),
        )
        self._order_queue = AsyncBoundedQueue(
            maxsize=1000,
            overflow_handler=lambda item: self._handle_queue_overflow(item, "order"),
        )
        self._position_queue = AsyncBoundedQueue(
            maxsize=500,
            overflow_handler=lambda item: self._handle_queue_overflow(item, "position"),
        )

        # Writer tasks
        self._trade_writer_task: Optional[asyncio.Task] = None
        self._order_writer_task: Optional[asyncio.Task] = None
        self._position_writer_task: Optional[asyncio.Task] = None

        # Batch settings
        self._batch_size = 50
        self._batch_timeout = 0.5
    
    def _get_model(self, model_name: str):
        """Get SQLAlchemy model by name."""
        models = {
            "XTAccountUpdate": XTAccountUpdate,
            "XTOrderUpdate": XTOrderUpdate,
            "XTPositionUpdate": XTPositionUpdate,
            "XTTradeUpdate": XTTradeUpdate,
            "XTWebSocketConnection": XTWebSocketConnection,
        }
        return models.get(model_name)

    # ========================================
    # SERVICE LIFECYCLE
    # ========================================

    async def start(self) -> None:
        """Start WebSocket service and background tasks."""
        if self.is_running:
            logger.warning("WS: Service already running")
            return
        
        self.is_running = True
        logger.info(f"WS: Starting service account={self.account_id}")

        # Initialize REST client for data sync
        if self.enable_data_sync:
            self.rest_client = XTPerpExchange(self.api_key, self.api_secret)
            await self.rest_client.connect()

        # Start batch writer tasks
        if "trade" in self.enabled_channels:
            self._trade_writer_task = asyncio.create_task(
                self._batch_writer_loop(
                    self._trade_queue, self._save_trade_batch, "trade"
                )
            )
        if "order" in self.enabled_channels:
            self._order_writer_task = asyncio.create_task(
                self._batch_writer_loop(
                    self._order_queue, self._save_order_batch, "order"
                )
            )
        if "position" in self.enabled_channels:
            self._position_writer_task = asyncio.create_task(
                self._batch_writer_loop(
                    self._position_queue, self._save_position_batch, "position"
                )
            )

        # Main WebSocket loop
        while self.is_running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"WS: Connection error: {e}")
                
                if (
                    self.auto_reconnect
                    and self.reconnect_attempts < self.max_reconnect_attempts
                ):
                    self.reconnect_attempts += 1
                    logger.info(
                        f"WS: Reconnecting {self.reconnect_attempts}/{self.max_reconnect_attempts}"
                    )
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    logger.error("WS: Max reconnect attempts reached")
                    break
        
        # Cleanup
        await self._record_connection_end()
        if self.rest_client:
            await self.rest_client.disconnect()

        logger.info("WS: Service stopped")
    
    async def stop(self) -> None:
        """Stop service and flush remaining data."""
        if not self.is_running:
            return

        logger.info("WS: Stopping service...")
        self.is_running = False
        
        # Stop heartbeat and listen key refresh
        await self._stop_heartbeat()
        await self._stop_listen_key_refresh()

        # Close WebSocket
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

        # Cancel and flush writer tasks
        for task, queue, save_fn, name in [
            (
                self._trade_writer_task,
                self._trade_queue,
                self._save_trade_batch,
                "trade",
            ),
            (
                self._order_writer_task,
                self._order_queue,
                self._save_order_batch,
                "order",
            ),
            (
                self._position_writer_task,
                self._position_queue,
                self._save_position_batch,
                "position",
            ),
        ]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await self._flush_queue(queue, save_fn, name)

        logger.info("WS: Service stopped completely")
    
    async def _connect_and_listen(self) -> None:
        """Establish WebSocket connection and message loop."""
        # Get listen key
        await self._get_listen_key()

        ws_url = f"{self.WS_URL}?listenKey={self.listen_key}"
        logger.info(f"WS: Connecting to {self.WS_URL[:30]}...")

        async with websockets.connect(
            ws_url, ping_interval=None, close_timeout=10
        ) as ws:
            self.ws = ws
            self.reconnect_attempts = 0

            # Record connection and sync if reconnecting
            is_reconnect = self.disconnect_time is not None
            self.reconnect_time = datetime.utcnow()
            await self._record_connection_start()

            if is_reconnect and self.enable_data_sync:
                asyncio.create_task(self._run_missing_data_sync())

            logger.info(f"WS: Connected key={self.listen_key[:8]}...")

            # Subscribe to channels
            await self._subscribe_user_data()

            # Start heartbeat
            await self._start_heartbeat()
            
            # Start listen key refresh task
            await self._start_listen_key_refresh()

            # Message loop
            try:
                async for message in ws:
                    if not self.is_running:
                        break
                    await self._handle_message(message)
            except ConnectionClosed as e:
                self.disconnect_time = datetime.utcnow()
                logger.warning(f"WS: Disconnected code={e.code}")
            except WebSocketException as e:
                self.disconnect_time = datetime.utcnow()
                logger.error(f"WS: WebSocket error: {e}")
            finally:
                await self._stop_heartbeat()
                await self._stop_listen_key_refresh()
                self.ws = None

    # ========================================
    # WEBSOCKET MANAGEMENT
    # ========================================

    async def _get_listen_key(self) -> None:
        """Obtain XT listen key for authentication."""
        if not self.rest_client:
            self.rest_client = XTPerpExchange(self.api_key, self.api_secret)
            await self.rest_client.connect()

        self.listen_key = await self.rest_client.create_user_stream_listen_key()

    async def _subscribe_user_data(self) -> None:
        """Subscribe to user data channels."""
        if not self.ws:
            return

        # XT subscription format
        sub_msg = {
            "method": "subscribe",
            "params": [f"user.{ch}" for ch in self.enabled_channels],
            "id": 1,
        }
        await self.ws.send(json.dumps(sub_msg))
        logger.info(f"WS: Subscribed channels={list(self.enabled_channels)}")

    async def _start_heartbeat(self) -> None:
        """Start periodic ping task.
        
        According to XT documentation:
        - Client must send text "ping" message periodically
        - Server will reply with text "pong" message
        - If server doesn't receive ping within 30 seconds, it will disconnect
        """
        if self._heartbeat_task:
            return

        async def heartbeat_loop():
            # XT 文档要求：客户端必须定期发送文本 "ping" 消息
            # 服务器会在 30 秒内未收到 ping 时断开连接
            while self.is_running and self.ws:
                try:
                    await asyncio.sleep(20)  # 每20秒发送一次 ping（小于30秒限制）
                    if self.ws:
                        # XT WebSocket 需要发送纯文本 "ping"，不是 JSON
                        # 根据文档：https://doc.xt.com/zh-CN/docs/futures/UserWebsocket/General_WSS_information
                        await self.ws.send("ping")
                        logger.debug("WS: Sent text ping message")
                except Exception as e:
                    logger.debug(f"WS: Failed to send ping: {e}")
                    break

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        """Stop heartbeat task."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _start_listen_key_refresh(self) -> None:
        """Start periodic listen key refresh task."""
        if self._listen_key_refresh_task:
            return

        async def refresh_loop():
            # 每50分钟刷新一次 listen key（XT listen key 通常60分钟过期）
            while self.is_running and self.ws:
                try:
                    await asyncio.sleep(50 * 60)  # 50分钟
                    if self.is_running and self.rest_client and self.listen_key:
                        try:
                            # 尝试刷新 listen key
                            new_key = await self.rest_client.create_user_stream_listen_key()
                            if new_key and new_key != self.listen_key:
                                old_key = self.listen_key[:8]
                                self.listen_key = new_key
                                logger.info(
                                    f"WS: Refreshed listen key {old_key}... -> {new_key[:8]}..."
                                )
                                # 刷新 listen key 后需要重新连接 WebSocket
                                # 因为 listen key 是通过 URL 参数传递的
                                if self.ws:
                                    logger.info("WS: Closing connection to reconnect with new listen key")
                                    await self.ws.close()
                        except Exception as e:
                            logger.warning(f"WS: Failed to refresh listen key: {e}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"WS: Listen key refresh loop error: {e}")
                    await asyncio.sleep(60)  # 出错后等待1分钟再继续

        self._listen_key_refresh_task = asyncio.create_task(refresh_loop())

    async def _stop_listen_key_refresh(self) -> None:
        """Stop listen key refresh task."""
        if self._listen_key_refresh_task:
            self._listen_key_refresh_task.cancel()
            try:
                await self._listen_key_refresh_task
            except asyncio.CancelledError:
                pass
            self._listen_key_refresh_task = None

    async def _send_pong(self) -> None:
        """Respond to server ping with text format.
        
        According to XT docs, pong should be plain text "pong", not JSON.
        However, XT typically only requires client to send ping, server replies with pong.
        """
        if self.ws:
            try:
                # XT WebSocket 需要发送纯文本 "pong"，不是 JSON
                # 根据文档：服务器会回复文本 "pong" 响应客户端的 "ping"
                await self.ws.send("pong")
                logger.debug("WS: Sent text pong message")
            except Exception as e:
                logger.debug(f"WS: Failed to send pong: {e}")

    # ========================================
    # MESSAGE HANDLING
    # ========================================

    async def _handle_message(self, message: str) -> None:
        """Route incoming WebSocket messages."""
        # 记录所有收到的原始消息（用于调试）
        logger.info(f"WS: RAW MESSAGE: {message[:500]}")

        # XT WebSocket 可能发送纯文本 "pong" 或 JSON 格式的消息
        # 根据文档：服务器会回复文本 "pong" 响应客户端的 "ping"
        if message.strip() == "pong":
            logger.debug("WS: Received text pong from server")
            return

        # 尝试解析 JSON 消息
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            # 如果不是 JSON，可能是其他文本消息，记录一下
            logger.warning(f"WS: Received non-JSON message: {message[:100]}")
            return

        # Handle ping/pong (JSON format, if server sends it)
        if isinstance(data, dict) and data.get("ping"):
            await self._send_pong()
            return

        # Handle subscription confirmation
        if "result" in data or "id" in data:
            logger.info(f"WS: Subscription confirmation: {data}")
            return

        # Route by topic/channel
        topic = data.get("topic", "")
        
        # 记录收到的消息（用于调试）
        if topic:
            logger.info(f"WS: Received message with topic: {topic}")

        if "account" in topic:
            await self._handle_account_update(data)
        elif "position" in topic:
            await self._handle_position_update(data)
        elif "order" in topic:
            await self._handle_order_update(data)
        elif "trade" in topic:
            await self._handle_trade_update(data)
    
    async def _handle_account_update(self, data: Dict[str, Any]) -> None:
        """Process account balance updates - save immediately."""
        if "account" not in self.enabled_channels:
            return
        
        account_data = data.get("data", {})
        if not account_data:
            return
        
        if not self._has_data_changed(
            account_data, self._last_account_data, self._json_key
        ):
            return
        
        # Log summary
        currency = account_data.get("coin", "")
        available = account_data.get("availableBalance") or account_data.get(
            "amount", ""
        )
        total = account_data.get("walletBalance") or account_data.get("totalAmount", "")
        logger.info(f"ACCT: {currency} avail={available} total={total}")

        # Save immediately (low volume)
        await self._save_account_update(account_data)
    
    async def _handle_position_update(self, data: Dict[str, Any]) -> None:
        """Process position updates - queue for batch write."""
        if "position" not in self.enabled_channels:
            return
        
        position_data = data.get("data", {})
        if not position_data:
            return
        
        if not self._has_data_changed(
            position_data, self._last_position_data, self._json_key
        ):
            return
        
        # Log summary
        symbol = position_data.get("symbol", "")
        side = position_data.get("positionSide", "")
        qty = position_data.get("positionSize", "")
        entry = position_data.get("entryPrice", "")
        pnl = position_data.get("floatingPL", "")
        logger.info(f"POS: {symbol} {side} qty={qty} entry={entry} pnl={pnl}")

        # Queue for batch write
        await self._position_queue.put(position_data, block=False)
    
    async def _handle_order_update(self, data: Dict[str, Any]) -> None:
        """Process order updates - queue for batch write + metrics."""
        if "order" not in self.enabled_channels:
            return
        
        order_data = data.get("data", {})
        if not order_data:
            return
        
        if not self._has_data_changed(
            order_data, self._last_order_data, self._order_key
        ):
            return
        
        # Log summary
        order_id = order_data.get("orderId", "")
        symbol = order_data.get("symbol", "")
        side = order_data.get("orderSide", "")
        qty = order_data.get("origQty", "")
        price = order_data.get("price", "")
        status = order_data.get("state", "")
        logger.info(f"ORDER: {symbol} {side} {qty}@{price} {status} id={order_id}")

        # Queue for batch write (non-blocking)
        if not await self._order_queue.put(order_data, block=False):
            return

        # Update Prometheus metrics in background
        asyncio.create_task(self._update_order_metrics_async(order_data))
    
    async def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """Process trade updates - queue for batch write + metrics."""
        if "trade" not in self.enabled_channels:
            return
        
        trade_data = data.get("data", {})
        if not trade_data:
            return
        
        if not self._has_data_changed(
            trade_data, self._last_trade_data, self._trade_key
        ):
            return
        
        # Log summary
        trade_id = trade_data.get("tradeId") or trade_data.get("execId", "")
        symbol = trade_data.get("symbol", "")
        side = trade_data.get("orderSide") or trade_data.get("side", "")
        qty = trade_data.get("quantity", "")
        price = trade_data.get("price", "")
        logger.info(f"TRADE: {symbol} {side} {qty}@{price} id={trade_id}")

        # Queue for batch write (non-blocking)
        if not await self._trade_queue.put(trade_data, block=False):
            return

        # Update Prometheus metrics in background
        asyncio.create_task(self._update_trade_metrics_async(trade_data))

    # ========================================
    # GENERIC BATCH WRITER
    # ========================================

    async def _batch_writer_loop(
        self,
        queue: AsyncBoundedQueue,
        save_batch_fn: Callable[[list], Awaitable[None]],
        name: str,
    ) -> None:
        """Generic batch writer loop."""
        batch = []
        logger.info(f"WS: {name} writer started")
        
        while self.is_running:
            try:
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=self._batch_timeout
                    )
                    batch.append(item)
                except asyncio.TimeoutError:
                    if batch:
                        await save_batch_fn(batch)
                        batch = []
                    continue
                
                if len(batch) >= self._batch_size:
                    await save_batch_fn(batch)
                    batch = []
                
                queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"WS: {name} writer error: {e}")
                if batch:
                    try:
                        await save_batch_fn(batch)
                    except Exception:
                        pass
                    batch = []
        
        # Flush remaining on exit
        if batch:
            await save_batch_fn(batch)

        logger.info(f"WS: {name} writer stopped")

    async def _flush_queue(
        self,
        queue: AsyncBoundedQueue,
        save_batch_fn: Callable[[list], Awaitable[None]],
        name: str,
    ) -> None:
        """Flush all remaining items from queue."""
        remaining = []
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                remaining.append(item)
                queue.task_done()
            except asyncio.TimeoutError:
                break
        
        if remaining:
            logger.info(f"WS: Flushing {len(remaining)} {name}s")
            try:
                await save_batch_fn(remaining)
            except Exception as e:
                logger.error(f"WS: Failed to flush {name}s: {e}")

    async def _handle_queue_overflow(self, item: Any, name: str) -> None:
        """Generic queue overflow handler."""
        logger.error(f"WS: {name} queue full, dropping message")

    # ========================================
    # BATCH SAVE METHODS
    # ========================================

    async def _save_trade_batch(self, batch: list) -> None:
        """Save trades to database."""
        if not batch:
            return
        
        start = datetime.utcnow()
        count = 0
        
        try:
            async with self.db_manager.session() as session:
                TradeModel = self._get_model("XTTradeUpdate")

                for data in batch:
                    # Extract trade(s) from data
                    trades = self._extract_trades(data)

                    for trade in trades:
                        trade_id = trade.get("tradeId") or trade.get("execId")
                        if not trade_id:
                            order_id = trade.get("orderId", "")
                            ts = trade.get("timestamp", "")
                            trade_id = f"{order_id}_{ts}" if order_id else None

                        if not trade_id:
                            continue

                        record = TradeModel(
                            update_time=self._parse_timestamp(trade.get("timestamp")),
                            account_id=self.account_id,
                            symbol=trade.get("symbol", ""),
                            order_id=str(trade.get("orderId", "")),
                            trade_id=str(trade_id),
                            side=trade.get("orderSide") or trade.get("side", ""),
                            price=self._safe_decimal(trade.get("price")),
                            quantity=self._safe_decimal(trade.get("quantity")),
                            quote_quantity=self._safe_decimal(
                                trade.get("quoteQuantity", 0)
                            ),
                            commission=self._safe_decimal(
                                trade.get("fee") or trade.get("commission", 0)
                            ),
                            commission_asset=trade.get("feeCoin")
                            or trade.get("feeCurrency", ""),
                            is_maker=trade.get("takerMaker") == "MAKER",
                            position_side=trade.get("positionSide", ""),
                            raw_data=json.dumps(trade, cls=DecimalEncoder),
                        )
                        session.add(record)
                        count += 1

                await session.commit()
                
            duration = (datetime.utcnow() - start).total_seconds()
            logger.info(
                f"BATCH: {count} trades in {duration:.2f}s q={self._trade_queue.qsize()}"
            )

        except Exception as e:
            logger.error(f"WS: Failed to save trade batch: {e}")

    async def _save_order_batch(self, batch: list) -> None:
        """Save orders to database with ON CONFLICT handling."""
        if not batch:
            return
        
        start = datetime.utcnow()
        count = 0
        
        try:
            from sqlalchemy.dialects.postgresql import insert  # type: ignore[import-untyped]
            
            async with self.db_manager.session() as session:
                OrderModel = self._get_model("XTOrderUpdate")

                for data in batch:
                    order_id = data.get("orderId") or data.get("order_id")
                    if not order_id:
                        continue
                    
                    values = {
                        "update_time": self._parse_timestamp(
                            data.get("updatedTime") or data.get("createdTime")
                        ),
                        "account_id": self.account_id,
                        "symbol": data.get("symbol", ""),
                        "order_id": str(order_id),
                        "client_order_id": data.get("clientOrderId", ""),
                        "price": self._safe_decimal(data.get("price")),
                        "quantity": self._safe_decimal(data.get("origQty")),
                        "filled_quantity": self._safe_decimal(
                            data.get("executedQty", 0)
                        ),
                        "status": data.get("state") or data.get("status", ""),
                        "order_type": data.get("orderType", ""),
                        "side": data.get("orderSide") or data.get("side", ""),
                        "position_side": data.get("positionSide", ""),
                        "time_in_force": data.get("timeInForce", "GTC"),
                        "raw_data": json.dumps(data, cls=DecimalEncoder),
                    }

                    stmt = insert(OrderModel).values(**values)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["account_id", "order_id"],
                        set_={
                            "update_time": stmt.excluded.update_time,
                            "filled_quantity": stmt.excluded.filled_quantity,
                            "status": stmt.excluded.status,
                            "raw_data": stmt.excluded.raw_data,
                        },
                    )
                    await session.execute(stmt)
                    count += 1

                await session.commit()

            duration = (datetime.utcnow() - start).total_seconds()
            logger.info(
                f"BATCH: {count} orders in {duration:.2f}s q={self._order_queue.qsize()}"
                        )
                
        except Exception as e:
            logger.error(f"WS: Failed to save order batch: {e}")

    async def _save_position_batch(self, batch: list) -> None:
        """Save positions to database."""
        if not batch:
            return
        
        start = datetime.utcnow()
        count = 0
        
        try:
            async with self.db_manager.session() as session:
                PositionModel = self._get_model("XTPositionUpdate")

                for data in batch:
                    symbol = data.get("symbol", "")
                    side = data.get("positionSide", "")
                    if not symbol:
                        continue
                    
                    record = PositionModel(
                        update_time=datetime.utcnow(),
                        account_id=self.account_id,
                        symbol=symbol,
                        side=side,
                        quantity=self._safe_decimal(data.get("positionSize")),
                        entry_price=self._safe_decimal(data.get("entryPrice")),
                        mark_price=self._safe_decimal(data.get("calMarkPrice")),
                        unrealized_pnl=self._safe_decimal(data.get("floatingPL", 0)),
                        leverage=self._safe_int(data.get("leverage", 1)),
                        liquidation_price=self._safe_decimal(data.get("breakPrice", 0)),
                        margin=self._safe_decimal(data.get("isolatedMargin", 0)),
                        raw_data=json.dumps(data, cls=DecimalEncoder),
                    )
                    session.add(record)
                    count += 1

                await session.commit()

            duration = (datetime.utcnow() - start).total_seconds()
            logger.info(
                f"BATCH: {count} positions in {duration:.2f}s q={self._position_queue.qsize()}"
            )

        except Exception as e:
            logger.error(f"WS: Failed to save position batch: {e}")

    async def _save_account_update(self, data: Dict[str, Any]) -> None:
        """Save account update immediately (low volume)."""
        try:
            async with self.db_manager.session() as session:
                AccountModel = self._get_model("XTAccountUpdate")

                wallet_balance = self._safe_decimal(
                    data.get("walletBalance") or data.get("totalAmount")
                )
                available = self._safe_decimal(
                    data.get("availableBalance") or data.get("amount")
                )
                frozen = wallet_balance - available

                record = AccountModel(
                    update_time=datetime.utcnow(),
                    account_id=self.account_id,
                    currency=data.get("coin", ""),
                    available=available,
                    frozen=frozen,
                    total=wallet_balance,
                    raw_data=json.dumps(data, cls=DecimalEncoder),
                )
                session.add(record)
                await session.commit()
                
        except Exception as e:
            logger.error(f"WS: Failed to save account update: {e}")

    # ========================================
    # RECONNECTION DATA SYNC
    # ========================================

    async def _run_missing_data_sync(self) -> None:
        """Background task wrapper for missing data sync."""
        try:
            logger.info("WS: Starting data sync after reconnect")
            await self._sync_missing_data()
            logger.info("WS: Data sync completed")
        except Exception as e:
            logger.error(f"WS: Data sync failed: {e}")

    async def _sync_missing_data(self) -> None:
        """Sync missing data for disconnect period."""
        if not self.enable_data_sync or not self.rest_client:
            return

        # Calculate sync time range
        if self.disconnect_time and self.reconnect_time:
            start_time = self.disconnect_time - timedelta(minutes=1)  # Buffer
            end_time = self.reconnect_time + timedelta(minutes=1)
        else:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)

        logger.info(f"WS: Sync range {start_time} to {end_time}")

        # Sync account data
        try:
            await self._sync_account_data()
        except Exception as e:
            logger.error(f"WS: Account sync failed: {e}")

        # Sync position data
        try:
            await self._sync_position_data()
        except Exception as e:
            logger.error(f"WS: Position sync failed: {e}")

        # Sync order data
        try:
            await self._sync_order_data_fixed_lookback(start_time, end_time)
        except Exception as e:
            logger.error(f"WS: Order sync failed: {e}")

        # Reset disconnect tracking
        self.disconnect_time = None

    async def _sync_account_data(self) -> None:
        """Sync account balances via REST API."""
        balances = await self.rest_client.get_balance()

        async with self.db_manager.session() as session:
            AccountModel = self._get_model("XTAccountUpdate")

            for currency, balance_info in balances.items():
                total = balance_info.get("total", Decimal("0"))
                available = balance_info.get("available", Decimal("0"))
                frozen = total - available

                record = AccountModel(
                    update_time=datetime.utcnow(),
                    account_id=self.account_id,
                    currency=currency,
                    available=available,
                    frozen=frozen,
                    total=total,
                    raw_data=json.dumps(balance_info, cls=DecimalEncoder),
                )
                session.add(record)

            await session.commit()

        logger.info(f"WS: Synced {len(balances)} account balances")

    async def _sync_position_data(self) -> None:
        """Sync positions via REST API."""
        positions = await self.rest_client.get_positions()

        async with self.db_manager.session() as session:
            PositionModel = self._get_model("XTPositionUpdate")

            for pos in positions:
                # pos is a Position object, not a dict
                record = PositionModel(
                    update_time=datetime.utcnow(),
                    account_id=self.account_id,
                    symbol=pos.symbol if hasattr(pos, "symbol") else "",
                    side=pos.side if hasattr(pos, "side") else "",
                    quantity=self._safe_decimal(
                        pos.quantity if hasattr(pos, "quantity") else 0
                    ),
                    entry_price=self._safe_decimal(
                        pos.entry_price if hasattr(pos, "entry_price") else 0
                    ),
                    mark_price=self._safe_decimal(
                        pos.mark_price if hasattr(pos, "mark_price") else 0
                    ),
                    unrealized_pnl=self._safe_decimal(
                        pos.unrealized_pnl if hasattr(pos, "unrealized_pnl") else 0
                    ),
                    leverage=self._safe_int(pos.leverage if hasattr(pos, "leverage") else 1),
                    liquidation_price=self._safe_decimal(
                        pos.liquidation_price if hasattr(pos, "liquidation_price") else 0
                    ),
                    margin=self._safe_decimal(
                        pos.margin if hasattr(pos, "margin") else 0
                    ),
                    raw_data=json.dumps(
                        {
                            "symbol": pos.symbol if hasattr(pos, "symbol") else "",
                            "side": pos.side if hasattr(pos, "side") else "",
                            "quantity": str(pos.quantity) if hasattr(pos, "quantity") else "0",
                        },
                        cls=DecimalEncoder,
                    ),
                )
                session.add(record)

            await session.commit()

        logger.info(f"WS: Synced {len(positions)} positions")

    async def _sync_order_data_fixed_lookback(
        self, start_time: datetime, end_time: datetime
    ) -> None:
        """Sync orders via paginated REST API."""
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        duration_seconds = (end_time - start_time).total_seconds()
        max_pages = min(20, max(5, int(duration_seconds / 60)))

        total_saved = 0

        async for order_batch in self.rest_client.get_order_history_paginated(
            start_time_ms=start_ms,
            end_time_ms=end_ms,
            max_pages=max_pages,
            limit_per_page=200,
        ):
            saved = await self._save_order_batch_from_rest(order_batch)
            total_saved += saved

        logger.info(f"WS: Synced {total_saved} orders")

    async def _save_order_batch_from_rest(self, orders: list) -> int:
        """Batch save REST orders with ON CONFLICT DO NOTHING."""
        if not orders:
            return 0

        saved = 0

        try:
            from sqlalchemy.dialects.postgresql import insert  # type: ignore[import-untyped]

            async with self.db_manager.session() as session:
                OrderModel = self._get_model("XTOrderUpdate")

                for data in orders:
                    order_id = data.get("orderId")
                    if not order_id:
                        continue
                
                    values = {
                        "update_time": self._parse_timestamp(
                            data.get("updatedTime") or data.get("createdTime")
                        ),
                        "account_id": self.account_id,
                        "symbol": data.get("symbol", ""),
                        "order_id": str(order_id),
                        "client_order_id": data.get("clientOrderId", ""),
                        "price": self._safe_decimal(data.get("price")),
                        "quantity": self._safe_decimal(data.get("origQty")),
                        "filled_quantity": self._safe_decimal(
                            data.get("executedQty", 0)
                        ),
                        "status": data.get("state", ""),
                        "order_type": data.get("orderType", ""),
                        "side": data.get("orderSide", ""),
                        "position_side": data.get("positionSide", ""),
                        "time_in_force": data.get("timeInForce", "GTC"),
                        "raw_data": json.dumps(data, cls=DecimalEncoder),
                    }

                    stmt = insert(OrderModel).values(**values)
                    stmt = stmt.on_conflict_do_nothing(
                        constraint="uq_xt_order_id_time_account"
                    )
                    await session.execute(stmt)
                    saved += 1

                await session.commit()
        except Exception as e:
            logger.error(f"WS: Failed to save REST orders: {e}")

        return saved

    # ========================================
    # CHANGE DETECTION
    # ========================================

    def _has_data_changed(
        self,
        data: Dict[str, Any],
        cache: Dict[str, str],
        key_fn: Callable[[Dict[str, Any]], str],
    ) -> bool:
        """Generic change detection."""
        try:
            key = key_fn(data)
        except Exception:
            return True

        if not key:
            return True

        if key == cache.get("key"):
            return False

        cache["key"] = key
        return True

    @staticmethod
    def _order_key(data: Dict[str, Any]) -> str:
        """Extract order cache key (order_id:status)."""
        order_id = data.get("orderId") or data.get("order_id") or ""
        status = data.get("state") or data.get("status") or ""
        return f"{order_id}:{status}"

    @staticmethod
    def _trade_key(data: Dict[str, Any]) -> str:
        """Extract trade cache key."""
        trade_id = data.get("tradeId") or data.get("execId")
        if trade_id:
            return str(trade_id)
        order_id = data.get("orderId") or data.get("order_id") or ""
        timestamp = data.get("timestamp") or ""
        return f"{order_id}_{timestamp}" if order_id else ""

    @staticmethod
    def _json_key(data: Dict[str, Any]) -> str:
        """Extract JSON-based cache key."""
        return json.dumps(data, sort_keys=True, cls=DecimalEncoder)

    # ========================================
    # UTILITIES
    # ========================================
    
    def _safe_decimal(self, value: Any) -> Decimal:
        """Safe Decimal conversion."""
        if value is None:
            return Decimal("0")
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")
    
    def _safe_int(self, value: Any) -> int:
        """Safe int conversion."""
        if value is None:
            return 0
        try:
            return int(value)
        except Exception:
            return 0
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """Parse millisecond timestamp to datetime."""
        if not timestamp:
            return datetime.utcnow()
        try:
            ts = int(timestamp)
            return datetime.fromtimestamp(ts / 1000)
        except Exception:
            return datetime.utcnow()

    def _extract_trades(self, data: Dict[str, Any]) -> list:
        """Extract trade records from message data."""
        # Single trade
        if "tradeId" in data or "execId" in data or "orderId" in data:
            return [data]

        # Multiple trades in list
        if "trades" in data:
            return data["trades"]

        return [data]

    # ========================================
    # CONNECTION TRACKING
    # ========================================

    async def _record_connection_start(self) -> None:
        """Record connection start in database."""
        try:
            from uuid import uuid4

            self._connection_id = str(uuid4())

            async with self.db_manager.session() as session:
                ConnectionModel = self._get_model("XTWebSocketConnection")

                # XTWebSocketConnection 模型字段检查
                # 使用不带时区的 datetime（数据库字段是 TIMESTAMP WITHOUT TIME ZONE）
                record = ConnectionModel(
                    connection_id=self._connection_id,
                    start_time=datetime.utcnow(),
                    is_active=True,
                )
                session.add(record)
                await session.commit()
        except Exception as e:
            logger.error(f"WS: Failed to record connection start: {e}")

    async def _record_connection_end(self) -> None:
        """Record connection end in database."""
        if not self._connection_id:
            return

        try:
            from sqlalchemy import update
            
            async with self.db_manager.session() as session:
                ConnectionModel = self._get_model("XTWebSocketConnection")

                stmt = (
                    update(ConnectionModel)
                    .where(ConnectionModel.connection_id == self._connection_id)
                    .values(
                        end_time=datetime.utcnow(),
                        is_active=False,
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            logger.error(f"WS: Failed to record connection end: {e}")

    # ========================================
    # METRICS
    # ========================================

    async def _update_order_metrics_async(self, order_data: Dict[str, Any]) -> None:
        """Update Prometheus order metrics in background."""
        try:
            account_id = self.account_id or "default"
            ensure_metrics_server(9601)

            update_order_metrics(
                exchange="xt",
                exchange_type="perp",
                account_id=account_id,
                order_data=order_data,
            )
        except Exception as e:
            logger.debug(f"WS: Metrics update error: {e}")

    async def _update_trade_metrics_async(self, trade_data: Dict[str, Any]) -> None:
        """Update Prometheus trade metrics in background."""
        try:
            account_id = self.account_id or "default"
            ensure_metrics_server(9601)

            update_trade_metrics(
                exchange="xt",
                exchange_type="perp",
                account_id=account_id,
                trade_data=trade_data,
            )
        except Exception as e:
            logger.debug(f"WS: Metrics update error: {e}")
