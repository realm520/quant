"""XT WebSocket user data stream service.

Handles XT WebSocket connections for real-time account updates, position updates,
order updates, and trade updates with automatic reconnection and data synchronization.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException


class DecimalEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理Decimal类型"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_websocket_models import (
    XTAccountUpdate,
    XTOrderUpdate,
    XTPositionUpdate,
    XTSpotUpdate,
    XTTradeUpdate,
    XTTransfer,
    XTWebSocketConnection,
)
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.exchanges.xt_spot import XTSpotExchange
from tri_arb.metrics.prometheus import ensure_metrics_server, update_order_metrics

logger = logging.getLogger(__name__)


class XTUserStreamService:
    """XT WebSocket用户数据流服务.
    
    处理XT WebSocket连接，提供实时账户、持仓、订单和成交更新，
    支持自动重连和数据同步机制。
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        db_manager: DatabaseManager,
        auto_reconnect: bool = True,
        display_format: str = "table",
        enabled_channels: Optional[Set[str]] = None,
        enable_data_sync: bool = True,
    ):
        """初始化XT WebSocket服务.
        
        Args:
            api_key: XT API密钥
            api_secret: XT API密钥
            db_manager: 数据库管理器
            auto_reconnect: 是否自动重连
            display_format: 显示格式 (table, json)
            enabled_channels: 启用的频道 (account, position, order, trade)
            enable_data_sync: 是否启用数据同步（默认True，防止数据丢失）
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.db_manager = db_manager
        self.auto_reconnect = auto_reconnect
        self.display_format = display_format
        self.enable_data_sync = enable_data_sync

        # 默认启用所有频道（包括成交记录）
        default_channels = {"account", "position", "order", "trade"}
        if enabled_channels is None:
            self.enabled_channels = set(default_channels)
        else:
            self.enabled_channels = set(enabled_channels)
            unsupported = self.enabled_channels - default_channels
            if unsupported:
                logger.warning(
                    "Ignoring unsupported XT user stream channels",
                    extra={"unsupported_channels": list(unsupported)},
                )
                self.enabled_channels -= unsupported
            if not self.enabled_channels:
                logger.warning(
                    "No valid XT user stream channels provided; falling back to defaults",
                    extra={"default_channels": list(default_channels)},
                )
                self.enabled_channels = set(default_channels)
        
        # WebSocket连接状态
        self.websocket = None
        self.connection_id = None
        self.is_connected = False
        self.is_running = False
        
        # 重连配置
        self.reconnect_delay = 5  # 重连延迟（秒）
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0

        # 断线时间记录（用于补充断线期间的数据）
        self.disconnect_time = None
        self.reconnect_time = None

        # XT REST API客户端（用于获取listen_key和数据同步）
        # 即使禁用数据同步，也需要REST客户端来获取WebSocket的listen_key
        self.rest_client = XTPerpExchange(self.api_key, self.api_secret)
        # 现货交易所客户端（用于查询现货余额，分析划转）
        self.spot_client = XTSpotExchange(
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

        # XT WebSocket认证
        self.listen_key = None
        self._subscription_request_id: Optional[str] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        
        # 标记价格缓存（避免频繁调用 REST API）
        self._mark_price_cache: Dict[str, Dict[str, Any]] = {}  # {symbol: {"price": Decimal, "timestamp": datetime}}
        self._mark_price_cache_ttl = 5.0  # 缓存有效期（秒）
        self._mark_price_update_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = 15  # seconds

        # 数据缓存（用于检测变化）
        self._last_account_data = {}  # 存储上次账户数据，用于比较余额变化
        self._last_account_balances = {}  # 存储上次各币种余额，用于识别划转
        self._last_position_data = {}
        self._last_order_data = {}
        self._last_trade_data = {}
        self._recent_orders = {}  # 存储最近的订单，用于判断余额变化是否由交易引起
        self._recent_trades = {}  # 存储最近的成交，用于判断余额变化是否由交易引起
        self._last_spot_balances = {}  # 存储上次现货账户余额，用于划转分析
        self._supported_transfer_currencies = {"USDT"}
        
        # 账号ID和名称（用于区分多账号数据）
        self.account_id = None
        self.account_name = None
        
        # 消息队列（用于解耦消息接收和数据库写入）
        from tri_arb.utils.async_utils import AsyncBoundedQueue
        self._trade_queue = AsyncBoundedQueue(
            maxsize=1000,  # 最多缓冲 1000 条成交消息
            overflow_handler=self._handle_trade_queue_overflow
        )
        self._order_queue = AsyncBoundedQueue(
            maxsize=1000,  # 最多缓冲 1000 条订单消息
            overflow_handler=self._handle_order_queue_overflow
        )
        self._position_queue = AsyncBoundedQueue(
            maxsize=500,  # 最多缓冲 500 条持仓消息（持仓更新频率较低）
            overflow_handler=self._handle_position_queue_overflow
        )
        self._trade_writer_task: Optional[asyncio.Task] = None
        self._order_writer_task: Optional[asyncio.Task] = None
        self._position_writer_task: Optional[asyncio.Task] = None
        self._batch_size = 50  # 批量写入大小（优化：从10增加到50，减少数据库往返次数）
        self._batch_timeout = 0.5  # 批量写入超时（秒）（优化：从1.0减少到0.5，更频繁刷新批次）
        
        logger.debug("XT WebSocket service initialized",
                    extra={
                        "enabled_channels": list(self.enabled_channels),
                        "data_sync_enabled": self.enable_data_sync,
                        "fixed_lookback_hours": 1,
                        "trade_queue_enabled": True,
                        "trade_queue_maxsize": 1000,
                        "trade_batch_size": self._batch_size
                    })
    
    def _get_model(self, model_name: str):
        """获取表模型（统一表模型）.
        
        Args:
            model_name: 模型名称，如 'XTAccountUpdate', 'XTPositionUpdate' 等
        
        Returns:
            表模型类
        """
        # 直接返回统一表模型（不再使用按账号分表）
        from tri_arb.storage.xt_websocket_models import (
            XTAccountUpdate,
            XTSpotUpdate,
            XTPositionUpdate,
            XTOrderUpdate,
            XTTradeUpdate,
            XTTransfer,
        )
        model_map = {
            'XTAccountUpdate': XTAccountUpdate,
            'XTSpotUpdate': XTSpotUpdate,
            'XTPositionUpdate': XTPositionUpdate,
            'XTOrderUpdate': XTOrderUpdate,
            'XTTradeUpdate': XTTradeUpdate,
            'XTTransfer': XTTransfer,
        }
        return model_map.get(model_name)
    
    async def _ensure_account_tables_if_needed(self):
        """确保统一表已创建（不再需要按账号分表）."""
        # 统一表会在全局 create_tables() 时创建，这里不再需要特殊处理
        pass
    async def start(self) -> None:
        """启动WebSocket服务."""
        if self.is_running:
            logger.warning("XT WebSocket service is already running")
            return
        
        self.is_running = True
        self.connection_id = str(uuid.uuid4())

        # 初始化REST客户端（必需，用于获取listen_key）
        await self.rest_client.connect()
        logger.debug("REST API client initialized")

        # 记录连接开始
        await self._record_connection_start()

        logger.debug("Starting XT WebSocket service")
        
        # 启动数据写入后台任务
        if "trade" in self.enabled_channels:
            self._trade_writer_task = asyncio.create_task(self._trade_writer_loop())
            logger.info("Trade writer task started")
        
        if "order" in self.enabled_channels:
            self._order_writer_task = asyncio.create_task(self._order_writer_loop())
            logger.info("Order writer task started")
        
        if "position" in self.enabled_channels:
            self._position_writer_task = asyncio.create_task(self._position_writer_loop())
            logger.info("Position writer task started")
        
        # 启动标记价格更新后台任务
        self._mark_price_update_task = asyncio.create_task(self._mark_price_update_loop())
        logger.info("Mark price update task started")
        
        # 启动WebSocket连接循环
        while self.is_running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                
                if self.auto_reconnect and self.reconnect_attempts < self.max_reconnect_attempts:
                    self.reconnect_attempts += 1
                    logger.info(
                        f"Attempting to reconnect ({self.reconnect_attempts}/{self.max_reconnect_attempts})",
                        delay=self.reconnect_delay,
                    )
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    logger.error("Max reconnection attempts reached, stopping service")
                    break
        
        # 记录连接结束
        await self._record_connection_end()
        
        # 停止标记价格更新任务
        if self._mark_price_update_task:
            self._mark_price_update_task.cancel()
            try:
                await self._mark_price_update_task
            except asyncio.CancelledError:
                pass

        # 清理资源
        if self.rest_client:
            await self.rest_client.disconnect()

        logger.info("XT WebSocket service stopped")
    
    async def _handle_trade_queue_overflow(self, item: Any) -> None:
        """处理成交消息队列溢出."""
        logger.error(
            f"成交消息队列已满，丢弃消息: {item}",
            extra={"queue_size": self._trade_queue.qsize()}
        )
    
    async def _handle_order_queue_overflow(self, item: Any) -> None:
        """处理订单消息队列溢出."""
        logger.error(
            f"订单消息队列已满，丢弃消息: {item}",
            extra={"queue_size": self._order_queue.qsize()}
        )
    
    async def _handle_position_queue_overflow(self, item: Any) -> None:
        """处理持仓消息队列溢出."""
        logger.error(
            f"持仓消息队列已满，丢弃消息: {item}",
            extra={"queue_size": self._position_queue.qsize()}
        )
    
    async def stop(self) -> None:
        """停止WebSocket服务."""
        logger.info("Stopping XT WebSocket service")
        self.is_running = False
        
        # 停止数据写入任务
        if self._trade_writer_task and not self._trade_writer_task.done():
            logger.info("Stopping trade writer task")
            self._trade_writer_task.cancel()
            try:
                await self._trade_writer_task
            except asyncio.CancelledError:
                pass
        
        if self._order_writer_task and not self._order_writer_task.done():
            logger.info("Stopping order writer task")
            self._order_writer_task.cancel()
            try:
                await self._order_writer_task
            except asyncio.CancelledError:
                pass
        
        if self._position_writer_task and not self._position_writer_task.done():
            logger.info("Stopping position writer task")
            self._position_writer_task.cancel()
            try:
                await self._position_writer_task
            except asyncio.CancelledError:
                pass
        
        # 刷新队列中剩余的消息
        await self._flush_remaining_trades()
        await self._flush_remaining_orders()
        await self._flush_remaining_positions()
        
        if self.websocket:
            await self._stop_heartbeat()
            await self.websocket.close()
            self.websocket = None
        
        self.is_connected = False
    
    async def _connect_and_listen(self) -> None:
        """建立WebSocket连接并监听消息."""
        # XT WebSocket URL (根据官方文档)
        ws_url = "wss://fstream.xt.com/ws/user"
        
        try:
            logger.debug("Connecting to XT WebSocket")

            # 建立WebSocket连接，提升握手与读写容忍度
            self.websocket = await websockets.connect(
                ws_url,
                open_timeout=60,
                close_timeout=30,
                ping_interval=20,
                ping_timeout=20,
                max_queue=None,
            )
            self.is_connected = True
            self.reconnect_attempts = 0

            logger.debug("Connected to XT WebSocket")

            # 获取listen_key用于认证
            await self._get_listen_key()

            # 订阅用户数据流
            await self._subscribe_user_data()

            await self._start_heartbeat()
            
            # 记录重连时间
            self.reconnect_time = datetime.utcnow()
            logger.debug("Recorded reconnect time")

            # 重连后执行断线回补（固定1小时回补 + 账户/持仓最新状态）
            # 已禁用：用于测试时间戳对齐问题
            # try:
            #     logger.info(
            #         "Starting missing data sync after reconnect",
            #         extra={
            #             "disconnect_time": self.disconnect_time.isoformat() if self.disconnect_time else None,
            #             "reconnect_time": self.reconnect_time.isoformat() if self.reconnect_time else None,
            #         }
            #     )
            #     await self._sync_missing_data()
            #     logger.info("Missing data sync completed after reconnect")
            # except Exception as sync_exc:
            #     logger.error(f"Failed to run missing data sync after reconnect: {sync_exc}", exc_info=True)
            logger.info("Data sync disabled for testing - skipping missing data sync after reconnect")

            # 监听消息
            logger.debug("Starting WebSocket message loop")
            message_count = 0
            
            async for message in self.websocket:
                logger.debug("Received WebSocket message", extra={"message_length": len(message)})
                await self._handle_message(message)
                message_count += 1
                
        except ConnectionClosed as exc:
            logger.warning(
                "XT WebSocket connection closed",
                extra={"code": exc.code, "reason": exc.reason},
            )
            self.is_connected = False
            # 记录断线时间
            self.disconnect_time = datetime.utcnow()
            logger.info(
                "Recorded disconnect time - will sync missing data after reconnect",
                extra={"disconnect_time": self.disconnect_time.isoformat()}
            )
        except WebSocketException as e:
            logger.error(f"XT WebSocket error: {e}")
            self.is_connected = False
            # 记录断线时间
            self.disconnect_time = datetime.utcnow()
            logger.debug("Recorded disconnect time")
        except Exception as e:
            logger.error(f"Unexpected error in WebSocket connection: {e}")
            self.is_connected = False
            # 记录断线时间
            self.disconnect_time = datetime.utcnow()
            logger.debug("Recorded disconnect time")
        finally:
            await self._stop_heartbeat()
    
    async def _get_listen_key(self) -> None:
        """获取XT WebSocket listenKey."""
        api_key = self.api_key
        api_secret = self.api_secret
        if not api_key or not api_secret:
            raise RuntimeError("XT_API_KEY / XT_API_SECRET 未设置")

        if not self.rest_client:
            raise RuntimeError("XT REST client is not initialized")

        try:
            listen_key = await self.rest_client.create_user_stream_listen_key()
        except Exception as exc:
            logger.error("Failed to obtain XT listen key", extra={"error": str(exc)})
            raise

        if not listen_key:
            raise RuntimeError("Failed to obtain XT listen key: response was empty")

        self.listen_key = listen_key
        logger.debug(
            "Obtained XT listen key",
            extra={"listen_key_prefix": listen_key[:8]},
        )

    async def _subscribe_user_data(self) -> None:
        """订阅用户数据流."""
        if not self.listen_key:
            logger.error("Listen key not available, cannot subscribe")
            raise RuntimeError("Listen key not available")

        channel_map = {
            "account": "balance",
            "position": "position",
            "order": "order",
            "trade": "trade",
        }

        params = []
        for channel in sorted(self.enabled_channels):
            stream_name = channel_map.get(channel)
            if not stream_name:
                logger.warning(
                    "Skipping unsupported XT user stream channel",
                    extra={"channel": channel},
                )
                continue
            params.append(f"{stream_name}@{self.listen_key}")

        if not params:
            logger.error("No valid XT user stream channels configured")
            raise RuntimeError("No valid XT user stream channels configured")

        # 使用固定的订阅ID，符合XT API文档要求
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": params,
            "id": "test1",
        }
       
        await self.websocket.send(json.dumps(subscribe_message, cls=DecimalEncoder))
        logger.info(
            "Subscribed to XT user data stream with listenKey",
            extra={"channels": params},
        )
    
    async def _handle_message(self, message: str) -> None:
        
        """处理WebSocket消息."""
        try:
            # 检查消息是否为空或只包含空白字符
            if not message or not message.strip():
                logger.debug("Received empty WebSocket message")
                return

            normalized = message.strip().lower()

            if normalized == "ping":
                logger.debug("Received XT ping, sending pong response")
                await self._send_pong()
                return

            if normalized == "pong":
                logger.debug("Received XT pong response")
                return
            
            data = json.loads(message)
            logger.debug("Parsed WebSocket message", extra={"data_sample": str(data)[:200]})
            # 更新消息统计
            await self._update_message_stats()

            # XT WebSocket消息格式处理
            # 检查是否是订阅确认消息
            if data.get("id") == "test1":
                if "result" in data:
                    logger.info("Subscription confirmed", extra={"result": data.get("result")})
                elif data.get("code") == 0:
                    logger.info(
                        "Subscription confirmed",
                        extra={"confirmation_message": data.get("msg", "ok")},
                    )
                else:
                    logger.debug("Subscription response received", extra={"payload": data})
                return

            # 检查是否是错误消息
            if "error" in data:
                error_code = data.get("error", {}).get("code") if isinstance(data.get("error"), dict) else data.get("error")
                error_msg = data.get("error", {}).get("message", "") if isinstance(data.get("error"), dict) else str(data.get("error"))

                if "invalid_listen_key" in str(error_code) or "invalid_listen_key" in str(error_msg):
                    logger.error("Listen key expired or invalid, need to refresh", extra={"error": error_msg})
                    await self._get_listen_key()
                    await self._subscribe_user_data()
                    return
                else:
                    logger.error("WebSocket error", extra={"error_code": error_code, "error_msg": error_msg})
                    return

            # 处理数据推送消息 - XT格式
            topic = data.get("topic", "")
            event = data.get("event", "")
            
            if topic and event:
                logger.debug("XT message", extra={"topic": topic, "event": event})
                
                # 根据topic类型处理数据
                if topic == "balance" and "account" in self.enabled_channels:
                    await self._handle_account_update(data)
                elif topic == "position" and "position" in self.enabled_channels:
                    await self._handle_position_update(data)
                elif topic == "order" and "order" in self.enabled_channels:
                    await self._handle_order_update(data)
                elif topic == "trade" and "trade" in self.enabled_channels:
                    await self._handle_trade_update(data)
                else:
                    logger.debug("Unknown topic or channel disabled", extra={"topic": topic})
            else:
                # 兼容旧格式
                stream = data.get("stream", "")
                if "@" in stream:
                    channel = stream.split("@")[0]
                    listen_key = stream.split("@")[1]
                    
                    logger.debug("Legacy message", extra={"channel": channel, "stream": stream})
                    
                    # 根据频道类型处理数据
                    if channel == "balance" and "account" in self.enabled_channels:
                        await self._handle_account_update(data)
                    elif channel == "position" and "position" in self.enabled_channels:
                        await self._handle_position_update(data)
                    elif channel == "order" and "order" in self.enabled_channels:
                        await self._handle_order_update(data)
                    elif channel == "trade" and "trade" in self.enabled_channels:
                        await self._handle_trade_update(data)
                    else:
                        logger.debug("Unknown channel or channel disabled", extra={"channel": channel})
                else:
                    logger.debug("Unknown message format", extra={"data_sample": str(data)[:200]})
                
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse WebSocket message: {e}")
            # 记录原始消息内容以便调试
            logger.debug(f"Raw message content: {repr(message[:200])}")
            normalized = message.strip().lower()
            if normalized == "ping":
                await self._send_pong()
            elif normalized == "pong":
                logger.debug("Received raw pong text frame")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

    async def _send_pong(self) -> None:
        """Respond to XT ping with pong."""
        if not self.websocket:
            return
        try:
            await self.websocket.send("pong")
            logger.debug("Sent pong response to XT WebSocket")
        except Exception as exc:
            logger.debug("Failed to send pong response", extra={"error": str(exc)})

    async def _start_heartbeat(self) -> None:
        """Start periodic ping task to keep XT WebSocket alive."""
        await self._stop_heartbeat()

        if not self.websocket:
            return

        async def _heartbeat_loop() -> None:
            while self.is_running and self.is_connected and self.websocket:
                try:
                    await self.websocket.send("ping")
                    logger.debug("Sent heartbeat ping to XT WebSocket")
                except Exception as exc:
                    logger.debug("Heartbeat ping failed", extra={"error": str(exc)})
                    break
                await asyncio.sleep(self._heartbeat_interval)

        self._heartbeat_task = asyncio.create_task(_heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        """Stop heartbeat task if running."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            finally:
                self._heartbeat_task = None
    
    async def _handle_account_update(self, data: Dict[str, Any]) -> None:
        """处理账户更新消息."""
        if "account" not in self.enabled_channels:
            logger.debug("Account channel not enabled")
            return
        
        # 提取XT账户数据
        account_data = data.get("data", {})
        if not account_data:
            logger.warning("No account data in message")
            return
        
        logger.info(f"Processing account update: {account_data}")
        
        # 检查数据是否有变化
        if not self._has_account_changed(account_data):
            logger.debug("Account data unchanged, skipping display")
            return
        
        logger.info("Account data changed, displaying update")
        
        try:
            # 分析资金划转（在保存前，需要比较余额变化）
            await self._analyze_transfer(account_data)
            
            # 显示账户更新
            await self._display_account_update(account_data)
            
            # 保存到数据库
            await self._save_account_update(account_data)
            
            # 更新统计
            await self._update_account_stats()
            
        except Exception as e:
            logger.error(f"Error handling account update: {e}")
    
    async def _handle_position_update(self, data: Dict[str, Any]) -> None:
        """处理持仓更新消息."""
        if "position" not in self.enabled_channels:
            return
        
        # 提取XT持仓数据
        position_data = data.get("data", {})
        if not position_data:
            logger.warning("No position data in message")
            return
        
        # 检查数据是否有变化
        if not self._has_position_changed(position_data):
            return
        
        try:
            # 记录消息接收时间（用于延迟监控）
            message_received_at = datetime.utcnow()
            if isinstance(position_data, dict):
                position_data["_message_received_at"] = message_received_at.isoformat()
            
            # 显示持仓更新 - 【暂时禁用以避免阻塞WebSocket消息接收】
            # await self._display_position_update(position_data)
            
            # 将持仓数据放入队列（异步处理，不阻塞）
            await self._position_queue.put(position_data)
            
            # 更新统计
            await self._update_position_stats()
            
        except Exception as e:
            logger.error(f"Error handling position update: {e}")
    
    async def _handle_order_update(self, data: Dict[str, Any]) -> None:
        """处理订单更新消息."""
        if "order" not in self.enabled_channels:
            return
        
        # 提取XT订单数据
        order_data = data.get("data", {})
        if not order_data:
            logger.warning("No order data in message")
            return
        
        # 检查数据是否有变化
        if not self._has_order_changed(order_data):
            return
        
        try:
            # 记录订单信息（用于划转分析）
            self._record_order_for_transfer_analysis(order_data)
            
            # 记录消息接收时间（用于延迟监控）
            message_received_at = datetime.utcnow()
            if isinstance(order_data, dict):
                order_data["_message_received_at"] = message_received_at.isoformat()
            
            # 显示订单更新 - 【暂时禁用以避免阻塞WebSocket消息接收】
            # await self._display_order_update(order_data)
            
            # 将订单数据放入队列（异步处理，不阻塞）
            await self._order_queue.put(order_data)
            
            # 更新 Prometheus metrics
            if self.account_id:
                account_id = self.account_id
            else:
                account_id = "default"
            
            # 订阅服务使用端口 9601
            ensure_metrics_server(9601)
            try:
                # 添加详细日志以便调试
                order_id = order_data.get('orderId') or order_data.get('order_id', 'unknown')
                logger.info(f"Updating order metrics for order {order_id}: symbol={order_data.get('symbol')}, side={order_data.get('orderSide')}, state={order_data.get('state')}")
                update_order_metrics(
                    exchange="xt",
                    exchange_type="perp",
                    account_id=account_id,
                    order_data=order_data,
                )
                logger.info(f"Order metrics updated successfully for order {order_id}")
            except Exception as metric_error:
                logger.error(f"Failed to update order metrics: {metric_error}", exc_info=True)
            
            # 更新统计
            await self._update_order_stats()
            
        except Exception as e:
            logger.error(f"Error handling order update: {e}", exc_info=True)
    
    async def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """处理成交更新消息."""
        if "trade" not in self.enabled_channels:
            return
        
        # 记录消息接收时间（用于延迟监控）
        message_received_at = datetime.utcnow()
        
        # 提取XT成交数据
        trade_data = data.get("data", {})
        if not trade_data:
            logger.warning("No trade data in message")
            logger.debug(f"Raw trade message: {json.dumps(data, cls=DecimalEncoder)[:500]}")
            return
        
        # 调试：记录收到的成交数据格式
        logger.debug(f"Received trade data: {json.dumps(trade_data, cls=DecimalEncoder)[:500]}")
        
        # 检查数据是否有变化
        if not self._has_trade_changed(trade_data):
            return
        
        try:
            # 在数据中添加消息接收时间（用于延迟分析）
            if isinstance(trade_data, dict):
                trade_data["_message_received_at"] = message_received_at.isoformat()
            elif isinstance(trade_data, list):
                for item in trade_data:
                    if isinstance(item, dict):
                        item["_message_received_at"] = message_received_at.isoformat()
            
            # 记录成交信息（用于划转分析）
            self._record_trade_for_transfer_analysis(trade_data)
            
            # 显示成交更新 - 【暂时禁用以避免阻塞WebSocket消息接收】
            # await self._display_trade_update(trade_data)
            
            # 将成交数据放入队列（异步处理，不阻塞）
            await self._trade_queue.put(trade_data)
            
            # 更新 Prometheus metrics
            if self.account_id:
                account_id = self.account_id
            else:
                account_id = "default"
            
            # 订阅服务使用端口 9601
            ensure_metrics_server(9601)
            try:
                from tri_arb.metrics.prometheus import update_trade_metrics
                update_trade_metrics(
                    exchange="xt",
                    exchange_type="perp",
                    account_id=account_id,
                    trade_data=trade_data,
                )
                logger.debug(f"成功更新成交 metrics (account_id={account_id})")
            except Exception as metric_error:
                logger.error(f"Failed to update trade metrics: {metric_error}", exc_info=True)
            
            # 更新统计
            await self._update_trade_stats()
            
        except Exception as e:
            logger.error(f"Error handling trade update: {e}", exc_info=True)
    
    async def _display_account_update(self, data: Dict[str, Any]) -> None:
        """显示账户更新."""
        if self.display_format == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False, cls=DecimalEncoder))
        else:
            # 表格格式显示
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            account_label = f"{self.account_id} ({self.account_name})" if self.account_name else (self.account_id or "默认账号")
            table = Table(title=f"XT账户更新 - {account_label}")
            
            table.add_column("币种", style="cyan")
            table.add_column("可用余额", style="green")
            table.add_column("冻结余额", style="yellow")
            table.add_column("总余额", style="blue")
            table.add_column("更新时间", style="dim")
            
            # XT数据格式：单个余额对象
            if "coin" in data:
                # 单个余额对象
                currency = data.get("coin", "")
                available = data.get("availableBalance", "0")
                frozen = data.get("openOrderMarginFrozen", "0")
                total = data.get("walletBalance", "0")
                update_time = datetime.now().strftime("%H:%M:%S")
                
                table.add_row(
                    currency,
                    f"{available}",
                    f"{frozen}",
                    f"{total}",
                    update_time,
                )
            else:
                # 兼容旧格式：多个余额对象
                balances = data.get("balances", [])
                for balance in balances:
                    currency = balance.get("currency", "")
                    available = balance.get("available", "0")
                    frozen = balance.get("frozen", "0")
                    total = balance.get("total", "0")
                    update_time = datetime.now().strftime("%H:%M:%S")
                    
                    table.add_row(
                        currency,
                        f"{available}",
                        f"{frozen}",
                        f"{total}",
                        update_time,
                    )
            
            console.print(table)
    
    async def _display_position_update(self, data: Dict[str, Any]) -> None:
        """显示持仓更新."""
        if self.display_format == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False, cls=DecimalEncoder))
        else:
            # 表格格式显示
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            account_label = f"{self.account_id} ({self.account_name})" if self.account_name else (self.account_id or "默认账号")
            table = Table(title=f"XT持仓更新 - {account_label}")
            
            table.add_column("交易对", style="cyan")
            table.add_column("方向", style="green")
            table.add_column("数量", style="yellow")
            table.add_column("开仓价", style="blue")
            table.add_column("标记价", style="magenta")
            table.add_column("未实现盈亏", style="red")
            table.add_column("已实现盈亏", style="green")
            table.add_column("杠杆", style="dim")
            
            # XT数据格式：单个持仓对象
            # XT WebSocket 使用 positionSide, positionSize, entryPrice, realizedProfit 等字段
            # 注意：WebSocket数据中没有floatingPL和markPrice，需要通过REST API获取标记价来计算未实现盈亏
            if "symbol" in data:
                # 单个持仓对象
                symbol = data.get("symbol", "")
                # XT API uses positionSide, fallback to side
                side = data.get("positionSide") or data.get("side", "")
                # XT API uses positionSize, fallback to quantity or positionAmt
                quantity_raw = data.get("positionSize") or data.get("quantity") or data.get("positionAmt", "0")
                quantity = self._safe_decimal(quantity_raw)
                entry_price_raw = data.get("entryPrice", "0")
                entry_price = self._safe_decimal(entry_price_raw)
                
                # 已实现盈亏（WebSocket数据中有此字段）
                realized_pnl_raw = data.get("realizedProfit") or data.get("realizedPnl") or "0"
                realized_pnl = self._safe_decimal(realized_pnl_raw)
                
                # 标记价：WebSocket数据中没有，需要通过REST API获取
                mark_price = Decimal("0")
                unrealized_pnl = Decimal("0")
                
                # 尝试从REST API获取标记价（如果交易所已连接）
                if self.rest_client and self.rest_client.is_connected and quantity > 0:
                    try:
                        # 查询持仓信息获取标记价
                        positions = await self.rest_client.get_positions(symbol=symbol)
                        for pos in positions:
                            if pos.symbol == symbol and pos.position_side == side:
                                mark_price = pos.mark_price
                                # 如果REST API返回了未实现盈亏，使用它；否则计算
                                if pos.unrealized_pnl and pos.unrealized_pnl != Decimal("0"):
                                    unrealized_pnl = pos.unrealized_pnl
                                else:
                                    # 计算未实现盈亏：(标记价 - 开仓价) * 数量 * 方向系数
                                    if side.upper() == "SHORT":
                                        unrealized_pnl = (entry_price - mark_price) * quantity
                                    else:
                                        unrealized_pnl = (mark_price - entry_price) * quantity
                                break
                    except Exception as e:
                        logger.debug(f"Failed to get mark price from REST API for {symbol}: {e}")
                
                leverage = data.get("leverage", "1")
                
                # 调试日志：记录实际收到的数据
                logger.debug(
                    f"Position update data for {symbol}",
                    extra={
                        "symbol": symbol,
                        "realizedProfit": str(realized_pnl),
                        "entryPrice": str(entry_price),
                        "markPrice": str(mark_price),
                        "calculated_unrealized_pnl": str(unrealized_pnl),
                        "raw_data_keys": list(data.keys()),
                    }
                )
                
                table.add_row(
                    symbol,
                    side,
                    f"{quantity}",
                    f"{entry_price}",
                    f"{mark_price}",
                    f"{unrealized_pnl}",
                    f"{realized_pnl}",
                    f"{leverage}x",
                )
            else:
                # 兼容旧格式：多个持仓对象
                positions = data.get("positions", [])
                for position in positions:
                    symbol = position.get("symbol", "")
                    # XT API uses positionSide, fallback to side
                    side = position.get("positionSide") or position.get("side", "")
                    # XT API uses positionSize, fallback to quantity or positionAmt
                    quantity_raw = position.get("positionSize") or position.get("quantity") or position.get("positionAmt", "0")
                    quantity = self._safe_decimal(quantity_raw)
                    entry_price_raw = position.get("entryPrice") or position.get("entry_price", "0")
                    entry_price = self._safe_decimal(entry_price_raw)
                    
                    # 已实现盈亏
                    realized_pnl_raw = position.get("realizedProfit") or position.get("realizedPnl") or "0"
                    realized_pnl = self._safe_decimal(realized_pnl_raw)
                    
                    # 标记价：尝试从REST API获取
                    mark_price = Decimal("0")
                    unrealized_pnl = Decimal("0")
                    
                    if self.rest_client and self.rest_client.is_connected and quantity > 0:
                        try:
                            positions_rest = await self.rest_client.get_positions(symbol=symbol)
                            for pos in positions_rest:
                                if pos.symbol == symbol and pos.position_side == side:
                                    mark_price = pos.mark_price
                                    if pos.unrealized_pnl and pos.unrealized_pnl != Decimal("0"):
                                        unrealized_pnl = pos.unrealized_pnl
                                    else:
                                        if side.upper() == "SHORT":
                                            unrealized_pnl = (entry_price - mark_price) * quantity
                                        else:
                                            unrealized_pnl = (mark_price - entry_price) * quantity
                                    break
                        except Exception as e:
                            logger.debug(f"Failed to get mark price from REST API for {symbol}: {e}")
                    
                    leverage = position.get("leverage", "1")
                    
                    table.add_row(
                        symbol,
                        side,
                        f"{quantity}",
                        f"{entry_price}",
                        f"{mark_price}",
                        f"{unrealized_pnl}",
                        f"{realized_pnl}",
                        f"{leverage}x",
                    )
            
            console.print(table)
    
    async def _display_order_update(self, data: Dict[str, Any]) -> None:
        """显示订单更新."""
        if self.display_format == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False, cls=DecimalEncoder))
        else:
            # 表格格式显示
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            account_label = f"{self.account_id} ({self.account_name})" if self.account_name else (self.account_id or "默认账号")
            table = Table(title=f"XT订单更新 - {account_label}")
            
            table.add_column("订单ID", style="cyan")
            table.add_column("交易对", style="green")
            table.add_column("方向", style="yellow")
            table.add_column("多空", style="bright_cyan")
            table.add_column("类型", style="blue")
            table.add_column("数量", style="magenta")
            table.add_column("价格", style="red")
            table.add_column("状态", style="dim")
            
            # XT数据格式：单个订单对象
            # XT WebSocket 使用 orderSide, orderType, state, origQty, executedQty 等字段
            if "orderId" in data or "order_id" in data:
                # 单个订单对象
                order_id = data.get("orderId") or data.get("order_id", "")
                symbol = data.get("symbol", "")
                # XT API uses orderSide, fallback to side
                side = data.get("orderSide") or data.get("side", "")
                # 持仓方向（多空）
                position_side = data.get("positionSide") or data.get("position_side") or "NET"
                # XT API uses orderType, fallback to type
                order_type = data.get("orderType") or data.get("type", "")
                # XT API uses origQty, fallback to quantity
                quantity = data.get("origQty") or data.get("quantity", "0")
                price = data.get("price", "0")
                # XT API uses state, fallback to status
                status = data.get("state") or data.get("status", "")
                
                # 多空方向颜色
                position_color = "bright_green" if position_side.upper() in ["LONG", "多"] else "bright_red" if position_side.upper() in ["SHORT", "空"] else "white"
                
                table.add_row(
                    str(order_id),
                    symbol,
                    side,
                    f"[{position_color}]{position_side}[/{position_color}]",
                    order_type,
                    f"{quantity}",
                    f"{price}",
                    status,
                )
            else:
                # 兼容旧格式：多个订单对象
                orders = data.get("orders", [])
                for order in orders:
                    order_id = order.get("orderId") or order.get("order_id", "")
                    symbol = order.get("symbol", "")
                    # XT API uses orderSide, fallback to side
                    side = order.get("orderSide") or order.get("side", "")
                    # 持仓方向（多空）
                    position_side = order.get("positionSide") or order.get("position_side") or "NET"
                    # XT API uses orderType, fallback to order_type or type
                    order_type = order.get("orderType") or order.get("order_type") or order.get("type", "")
                    # XT API uses origQty, fallback to quantity
                    quantity = order.get("origQty") or order.get("quantity", "0")
                    price = order.get("price", "0")
                    # XT API uses state, fallback to status
                    status = order.get("state") or order.get("status", "")
                    
                    # 多空方向颜色
                    position_color = "bright_green" if position_side.upper() in ["LONG", "多"] else "bright_red" if position_side.upper() in ["SHORT", "空"] else "white"
                    
                    table.add_row(
                        str(order_id),
                        symbol,
                        side,
                        f"[{position_color}]{position_side}[/{position_color}]",
                        order_type,
                        f"{quantity}",
                        f"{price}",
                        status,
                    )
            
            console.print(table)
    
    async def _display_trade_update(self, data: Dict[str, Any]) -> None:
        """显示成交更新."""
        if self.display_format == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False, cls=DecimalEncoder))
        else:
            # 表格格式显示
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            account_label = f"{self.account_id} ({self.account_name})" if self.account_name else (self.account_id or "默认账号")
            table = Table(title=f"XT成交更新 - {account_label}")
            
            table.add_column("成交ID", style="cyan")
            table.add_column("订单ID", style="green")
            table.add_column("交易对", style="yellow")
            table.add_column("方向", style="blue")
            table.add_column("价格", style="magenta")
            table.add_column("数量", style="red")
            table.add_column("金额", style="dim")
            
            # 解析成交数据 - 支持多种格式：
            # 1. trades 列表格式: {"trades": [...]}
            # 2. 单个成交对象格式: {"trade_id": "...", "order_id": "...", ...}
            # 3. XT WebSocket 格式: {"orderId": "...", "orderSide": "...", "price": "...", "quantity": "...", ...}
            #    根据文档: https://doc.xt.com/zh-Hans/docs/futures/UserWebsocket/Transactions
            trades = []
            if "trades" in data and isinstance(data.get("trades"), list):
                trades = data.get("trades", [])
            elif isinstance(data, list):
                # 如果 data 本身就是列表
                trades = data
            elif "orderId" in data or "order_id" in data or "trade_id" in data or "tradeId" in data:
                # 单个成交对象（包括 XT 格式），转换为列表
                trades = [data]
            
            # 如果没有成交数据，不显示表格
            if len(trades) == 0:
                logger.debug(f"No trade data found in message: {json.dumps(data, cls=DecimalEncoder)[:200]}")
                return
            
            # 处理成交数据
            for trade in trades:
                # XT 格式：orderId, orderSide, price, quantity, symbol, positionSide
                # 其他格式：trade_id/tradeId, order_id/orderId, side, price, quantity, symbol
                order_id = trade.get("orderId") or trade.get("order_id") or ""
                trade_id = trade.get("trade_id") or trade.get("tradeId") or trade.get("id") or ""
                # XT 使用 orderSide，其他使用 side
                side = trade.get("orderSide") or trade.get("side") or trade.get("S") or ""
                symbol = trade.get("symbol") or trade.get("s") or ""
                price = trade.get("price") or trade.get("p") or trade.get("executedPrice") or "0"
                quantity = trade.get("quantity") or trade.get("qty") or trade.get("q") or trade.get("executedQty") or "0"
                quote_quantity = trade.get("quote_quantity") or trade.get("quoteQuantity") or trade.get("amount") or trade.get("notional") or "0"
                
                # 如果没有 quote_quantity，计算它
                if quote_quantity == "0" or quote_quantity == 0:
                    try:
                        price_val = float(price) if price else 0
                        qty_val = float(quantity) if quantity else 0
                        quote_quantity = str(price_val * qty_val)
                    except (ValueError, TypeError):
                        quote_quantity = "0"
                
                # 只显示有效的成交数据（至少要有 orderId 或 trade_id）
                if order_id or trade_id:
                    # 使用 orderId 作为成交ID（如果没有 trade_id，用 orderId 代替）
                    display_trade_id = trade_id or order_id or ""
                    table.add_row(
                        str(display_trade_id),
                        str(order_id),
                        str(symbol),
                        str(side),
                        str(price),
                        str(quantity),
                        str(quote_quantity),
                    )
            
            # 如果表格有数据，才显示
            if len(table.rows) > 0:
                console.print(table)
            else:
                logger.debug(f"Trade data found but no valid trades to display: {json.dumps(data, cls=DecimalEncoder)[:200]}")
    
    async def _save_account_update(self, data: Dict[str, Any]) -> None:
        """保存账户更新到数据库."""
        try:
            # 确保账号特定的表已创建（如果是新账号）
            await self._ensure_account_tables_if_needed()
            
            async with self.db_manager.session() as session:
                update_time = datetime.utcnow()
                
                # XT数据格式：单个余额对象
                if "coin" in data:
                    # 单个余额对象
                    currency = data.get("coin", "")
                    if not currency:
                        logger.warning("No currency found in account data")
                        return
                    
                    available = self._safe_decimal(data.get("availableBalance", "0"))
                    frozen = self._safe_decimal(data.get("openOrderMarginFrozen", "0"))
                    total = self._safe_decimal(data.get("walletBalance", "0"))
                    
                    AccountUpdateModel = self._get_model('XTAccountUpdate')
                    record = AccountUpdateModel(
                        update_time=update_time,
                        account_id=self.account_id,
                        currency=currency,
                        available=available,
                        frozen=frozen,
                        total=total,
                        raw_data=json.dumps(data, cls=DecimalEncoder),
                    )
                    session.add(record)
                    logger.info(f"Added account update for {currency}: available={available}, frozen={frozen}, total={total}")
                else:
                    # 兼容旧格式：多个余额对象
                    balances = data.get("balances", [])
                    for balance in balances:
                        currency = balance.get("currency", "")
                        if not currency:
                            continue
                        
                        available = self._safe_decimal(balance.get("available", "0"))
                        frozen = self._safe_decimal(balance.get("frozen", "0"))
                        total = available + frozen
                        
                        AccountUpdateModel = self._get_model('XTAccountUpdate')
                        record = AccountUpdateModel(
                            update_time=update_time,
                            account_id=self.account_id,
                            currency=currency,
                            available=available,
                            frozen=frozen,
                            total=total,
                            raw_data=json.dumps(balance, cls=DecimalEncoder),
                        )
                        session.add(record)
                        logger.info(f"Added account update for {currency}: available={available}, frozen={frozen}, total={total}")
                
                await session.commit()
                logger.info("Successfully saved account update to database")
                
        except Exception as e:
            logger.error(f"Failed to save account update: {e}")
    
    async def _save_position_update(self, data: Dict[str, Any]) -> None:
        """保存持仓更新到数据库."""
        try:
            # 确保账号特定的表已创建（如果是新账号）
            await self._ensure_account_tables_if_needed()
            
            async with self.db_manager.session() as session:
                update_time = datetime.utcnow()
                
                # XT数据格式：单个持仓对象
                # XT WebSocket 使用 positionSide, positionSize, calMarkPrice, floatingPL 等字段
                if "symbol" in data:
                    # 单个持仓对象
                    symbol = data.get("symbol", "")
                    if not symbol:
                        logger.warning("No symbol found in position data")
                        return
                    
                    # XT API uses positionSide, fallback to side
                    side = data.get("positionSide") or data.get("side", "")
                    # XT API uses positionSize, fallback to quantity or positionAmt
                    quantity_raw = data.get("positionSize") or data.get("quantity") or data.get("positionAmt", "0")
                    quantity = self._safe_decimal(quantity_raw)
                    
                    # 跳过持仓量为0的记录
                    if quantity == 0:
                        logger.debug(f"Position quantity is 0 for {symbol}, skipping")
                        return
                    
                    entry_price = self._safe_decimal(data.get("entryPrice", "0"))
                    
                    # 已实现盈亏（WebSocket数据中有此字段）
                    realized_pnl_raw = data.get("realizedProfit") or data.get("realizedPnl") or "0"
                    realized_pnl = self._safe_decimal(realized_pnl_raw)
                    
                    # 标记价和未实现盈亏：WebSocket数据中没有，从缓存或REST API获取
                    mark_price = Decimal("0")
                    unrealized_pnl = Decimal("0")
                    
                    # 优先从缓存获取标记价格
                    cache_key = f"{symbol}_{side}"
                    cached_data = self._mark_price_cache.get(cache_key)
                    use_cache = False
                    
                    if cached_data:
                        cache_age = (datetime.utcnow() - cached_data["timestamp"]).total_seconds()
                        if cache_age < self._mark_price_cache_ttl:
                            mark_price = cached_data["price"]
                            use_cache = True
                    
                    # 如果缓存不可用，尝试从REST API获取（但不阻塞，使用缓存中的旧值）
                    if not use_cache and self.rest_client and self.rest_client.is_connected and quantity > 0:
                        try:
                            positions_rest = await self.rest_client.get_positions(symbol=symbol)
                            for pos in positions_rest:
                                if pos.symbol == symbol and pos.position_side == side:
                                    mark_price = pos.mark_price
                                    # 更新缓存
                                    self._mark_price_cache[cache_key] = {
                                        "price": mark_price,
                                        "timestamp": datetime.utcnow()
                                    }
                                    # 如果REST API返回了未实现盈亏，使用它；否则计算
                                    if pos.unrealized_pnl and pos.unrealized_pnl != Decimal("0"):
                                        unrealized_pnl = pos.unrealized_pnl
                                    else:
                                        # 计算未实现盈亏
                                        if side.upper() == "SHORT":
                                            unrealized_pnl = (entry_price - mark_price) * quantity
                                        else:
                                            unrealized_pnl = (mark_price - entry_price) * quantity
                                    break
                        except Exception as e:
                            logger.debug(f"Failed to get mark price from REST API for {symbol}: {e}")
                            # 如果 REST API 失败，尝试使用缓存中的旧值
                            if cached_data:
                                mark_price = cached_data["price"]
                                use_cache = True
                    
                    # 如果有标记价格，计算未实现盈亏
                    if mark_price > 0 and not unrealized_pnl:
                        if side.upper() == "SHORT":
                            unrealized_pnl = (entry_price - mark_price) * quantity
                        else:
                            unrealized_pnl = (mark_price - entry_price) * quantity
                    
                    # XT API uses breakPrice, fallback to liquidationPrice
                    liquidation_price_raw = data.get("breakPrice") or data.get("liquidationPrice", "0")
                    
                    PositionUpdateModel = self._get_model('XTPositionUpdate')
                    record = PositionUpdateModel(
                        update_time=update_time,
                        account_id=self.account_id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        entry_price=entry_price,
                        mark_price=mark_price,
                        liquidation_price=self._safe_decimal(liquidation_price_raw),
                        unrealized_pnl=unrealized_pnl,
                        leverage=int(data.get("leverage", "1")),
                        margin=self._safe_decimal(data.get("isolatedMargin") or data.get("margin", "0")),
                        raw_data=json.dumps(data, cls=DecimalEncoder),
                    )
                    session.add(record)
                    logger.info(
                        f"Added position update for {symbol}: {side} {quantity}, unrealized_pnl={unrealized_pnl}, realized_pnl={realized_pnl}"
                    )
                else:
                    # 兼容旧格式：多个持仓对象
                    positions = data.get("positions", [])
                    for position in positions:
                        symbol = position.get("symbol", "")
                        if not symbol:
                            continue
                        
                        # XT API uses positionSide, fallback to side
                        side = position.get("positionSide") or position.get("side", "")
                        # XT API uses positionSize, fallback to quantity or positionAmt
                        quantity_raw = position.get("positionSize") or position.get("quantity") or position.get("positionAmt", "0")
                        quantity = self._safe_decimal(quantity_raw)
                        
                        # 跳过持仓量为0的记录
                        if quantity == 0:
                            continue
                        
                        entry_price = self._safe_decimal(position.get("entryPrice") or position.get("entry_price", "0"))
                        
                        # 已实现盈亏
                        realized_pnl_raw = position.get("realizedProfit") or position.get("realizedPnl") or "0"
                        realized_pnl = self._safe_decimal(realized_pnl_raw)
                        
                        # 标记价和未实现盈亏：尝试从REST API获取
                        mark_price = Decimal("0")
                        unrealized_pnl = Decimal("0")
                        
                        if self.rest_client and self.rest_client.is_connected and quantity > 0:
                            try:
                                positions_rest = await self.rest_client.get_positions(symbol=symbol)
                                for pos in positions_rest:
                                    if pos.symbol == symbol and pos.position_side == side:
                                        mark_price = pos.mark_price
                                        if pos.unrealized_pnl and pos.unrealized_pnl != Decimal("0"):
                                            unrealized_pnl = pos.unrealized_pnl
                                        else:
                                            if side.upper() == "SHORT":
                                                unrealized_pnl = (entry_price - mark_price) * quantity
                                            else:
                                                unrealized_pnl = (mark_price - entry_price) * quantity
                                        break
                            except Exception as e:
                                logger.debug(f"Failed to get mark price from REST API for {symbol}: {e}")
                        
                        # XT API uses breakPrice, fallback to liquidationPrice
                        liquidation_price_raw = position.get("breakPrice") or position.get("liquidationPrice") or position.get("liquidation_price", "0")
                        
                        PositionUpdateModel = self._get_model('XTPositionUpdate')
                        record = PositionUpdateModel(
                            update_time=update_time,
                            account_id=self.account_id,
                            symbol=symbol,
                            side=side,
                            quantity=quantity,
                            entry_price=entry_price,
                            mark_price=mark_price,
                            liquidation_price=self._safe_decimal(liquidation_price_raw),
                            unrealized_pnl=unrealized_pnl,
                            leverage=int(position.get("leverage", "1")),
                            margin=self._safe_decimal(position.get("isolatedMargin") or position.get("margin", "0")),
                            raw_data=json.dumps(position, cls=DecimalEncoder),
                        )
                        session.add(record)
                
                await session.commit()
                logger.debug("Saved position update to database")
                
        except Exception as e:
            logger.error(f"Failed to save position update: {e}")
    
    async def _save_order_update(self, data: Dict[str, Any]) -> None:
        """保存订单更新到数据库."""
        try:
            # 确保账号特定的表已创建（如果是新账号）
            await self._ensure_account_tables_if_needed()
            
            async with self.db_manager.session() as session:
                update_time = datetime.utcnow()
                
                # XT数据格式：单个订单对象
                # XT WebSocket 使用 orderSide, orderType, state, origQty, executedQty 等字段
                if "orderId" in data or "order_id" in data:
                    # 单个订单对象
                    order_id = data.get("orderId") or data.get("order_id", "")
                    if not order_id:
                        logger.warning("No order ID found in order data")
                        return
                    
                    symbol = data.get("symbol", "")
                    # XT API uses orderSide, fallback to side
                    side = data.get("orderSide") or data.get("side", "")
                    # XT API uses orderType, fallback to type
                    order_type = data.get("orderType") or data.get("type", "")
                    # XT API uses origQty, fallback to quantity
                    quantity_raw = data.get("origQty") or data.get("quantity", "0")
                    quantity = self._safe_decimal(quantity_raw)
                    price = self._safe_decimal(data.get("price", "0"))
                    # XT API uses executedQty, fallback to filledQuantity or filled_quantity
                    filled_quantity_raw = data.get("executedQty") or data.get("filledQuantity") or data.get("filled_quantity", "0")
                    filled_quantity = self._safe_decimal(filled_quantity_raw)
                    # XT API uses state, fallback to status
                    status = data.get("state") or data.get("status", "")
                    
                    OrderUpdateModel = self._get_model('XTOrderUpdate')
                    record = OrderUpdateModel(
                        update_time=update_time,
                        account_id=self.account_id,
                        symbol=symbol,
                        order_id=str(order_id),
                        client_order_id=data.get("clientOrderId") or data.get("client_order_id", ""),
                        side=side,
                        order_type=order_type,
                        position_side=data.get("positionSide") or data.get("position_side", ""),
                        quantity=quantity,
                        price=price,
                        filled_quantity=filled_quantity,
                        status=status,
                        time_in_force=data.get("timeInForce") or data.get("time_in_force", ""),
                        create_time=self._parse_timestamp(data.get("createdTime") or data.get("createTime") or data.get("created_time")),
                        update_time_order=self._parse_timestamp(data.get("updatedTime") or data.get("updateTime") or data.get("updated_time")),
                        raw_data=json.dumps(data, cls=DecimalEncoder),
                    )
                    session.add(record)
                    logger.info(f"Added order update for {symbol}: {order_id} - {side} {quantity} @ {price} ({status})")
                else:
                    # 兼容旧格式：多个订单对象
                    orders = data.get("orders", [])
                    for order in orders:
                        order_id = order.get("orderId") or order.get("order_id", "")
                        if not order_id:
                            continue
                        
                        symbol = order.get("symbol", "")
                        # XT API uses orderSide, fallback to side
                        side = order.get("orderSide") or order.get("side", "")
                        # XT API uses orderType, fallback to order_type or type
                        order_type = order.get("orderType") or order.get("order_type") or order.get("type", "")
                        # XT API uses origQty, fallback to quantity
                        quantity_raw = order.get("origQty") or order.get("quantity", "0")
                        quantity = self._safe_decimal(quantity_raw)
                        price = self._safe_decimal(order.get("price", "0"))
                        # XT API uses executedQty, fallback to filled_quantity or filledQuantity
                        filled_quantity_raw = order.get("executedQty") or order.get("filled_quantity") or order.get("filledQuantity", "0")
                        filled_quantity = self._safe_decimal(filled_quantity_raw)
                        # XT API uses state, fallback to status
                        status = order.get("state") or order.get("status", "")
                        
                        OrderUpdateModel = self._get_model('XTOrderUpdate')
                        record = OrderUpdateModel(
                            update_time=update_time,
                            account_id=self.account_id,
                            symbol=symbol,
                            order_id=str(order_id),
                            client_order_id=order.get("clientOrderId") or order.get("client_order_id", ""),
                            side=side,
                            order_type=order_type,
                            position_side=order.get("positionSide") or order.get("position_side", ""),
                            quantity=quantity,
                            price=price,
                            filled_quantity=filled_quantity,
                            status=status,
                            time_in_force=order.get("timeInForce") or order.get("time_in_force", ""),
                            create_time=self._parse_timestamp(order.get("createdTime") or order.get("createTime") or order.get("created_time")),
                            update_time_order=self._parse_timestamp(order.get("updatedTime") or order.get("updateTime") or order.get("updated_time")),
                            raw_data=json.dumps(order, cls=DecimalEncoder),
                        )
                        session.add(record)
                        logger.info(f"Added order update for {symbol}: {order_id} - {side} {quantity} @ {price} ({status})")
                
                await session.commit()
                logger.info("Successfully saved order update to database")
                logger.debug("Saved order update to database")
                
        except Exception as e:
            logger.error(f"Failed to save order update: {e}")
    
    async def _trade_writer_loop(self) -> None:
        """成交数据写入后台任务循环.
        
        从队列中取出成交数据，批量写入数据库。
        """
        batch = []
        last_flush_time = datetime.utcnow()
        
        logger.info("Trade writer loop started")
        
        while self.is_running:
            try:
                # 尝试从队列获取数据，设置超时以便定期刷新批次
                try:
                    trade_data = await asyncio.wait_for(
                        self._trade_queue.get(),
                        timeout=self._batch_timeout
                    )
                    batch.append(trade_data)
                except asyncio.TimeoutError:
                    # 超时：如果批次不为空，刷新批次
                    if batch:
                        await self._save_trade_batch(batch)
                        batch = []
                        last_flush_time = datetime.utcnow()
                    continue
                
                # 如果批次达到大小，立即写入
                if len(batch) >= self._batch_size:
                    await self._save_trade_batch(batch)
                    batch = []
                    last_flush_time = datetime.utcnow()
                
                # 标记任务完成
                self._trade_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Trade writer loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in trade writer loop: {e}", exc_info=True)
                # 发生错误时，尝试保存当前批次
                if batch:
                    try:
                        await self._save_trade_batch(batch)
                        batch = []
                    except Exception as batch_error:
                        logger.error(f"Failed to save batch after error: {batch_error}", exc_info=True)
        
        # 退出前刷新剩余批次
        if batch:
            logger.info(f"Flushing remaining {len(batch)} trades before exit")
            try:
                await self._save_trade_batch(batch)
            except Exception as e:
                logger.error(f"Failed to flush remaining trades: {e}", exc_info=True)
        
        logger.info("Trade writer loop stopped")
    
    async def _order_writer_loop(self) -> None:
        """订单数据写入后台任务循环.
        
        从队列中取出订单数据，批量写入数据库。
        """
        batch = []
        last_flush_time = datetime.utcnow()
        
        logger.info("Order writer loop started")
        
        while self.is_running:
            try:
                # 尝试从队列获取数据，设置超时以便定期刷新批次
                try:
                    order_data = await asyncio.wait_for(
                        self._order_queue.get(),
                        timeout=self._batch_timeout
                    )
                    batch.append(order_data)
                except asyncio.TimeoutError:
                    # 超时：如果批次不为空，刷新批次
                    if batch:
                        await self._save_order_batch(batch)
                        batch = []
                        last_flush_time = datetime.utcnow()
                    continue
                
                # 如果批次达到大小，立即写入
                if len(batch) >= self._batch_size:
                    await self._save_order_batch(batch)
                    batch = []
                    last_flush_time = datetime.utcnow()
                
                # 标记任务完成
                self._order_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Order writer loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in order writer loop: {e}", exc_info=True)
                # 发生错误时，尝试保存当前批次
                if batch:
                    try:
                        await self._save_order_batch(batch)
                        batch = []
                    except Exception as batch_error:
                        logger.error(f"Failed to save batch after error: {batch_error}", exc_info=True)
        
        # 退出前刷新剩余批次
        if batch:
            logger.info(f"Flushing remaining {len(batch)} orders before exit")
            try:
                await self._save_order_batch(batch)
            except Exception as e:
                logger.error(f"Failed to flush remaining orders: {e}", exc_info=True)
        
        logger.info("Order writer loop stopped")
    
    async def _position_writer_loop(self) -> None:
        """持仓数据写入后台任务循环.
        
        从队列中取出持仓数据，批量写入数据库。
        """
        batch = []
        last_flush_time = datetime.utcnow()
        
        logger.info("Position writer loop started")
        
        while self.is_running:
            try:
                # 尝试从队列获取数据，设置超时以便定期刷新批次
                try:
                    position_data = await asyncio.wait_for(
                        self._position_queue.get(),
                        timeout=self._batch_timeout
                    )
                    batch.append(position_data)
                except asyncio.TimeoutError:
                    # 超时：如果批次不为空，刷新批次
                    if batch:
                        await self._save_position_batch(batch)
                        batch = []
                        last_flush_time = datetime.utcnow()
                    continue
                
                # 如果批次达到大小，立即写入
                if len(batch) >= self._batch_size:
                    await self._save_position_batch(batch)
                    batch = []
                    last_flush_time = datetime.utcnow()
                
                # 标记任务完成
                self._position_queue.task_done()
                
            except asyncio.CancelledError:
                logger.info("Position writer loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in position writer loop: {e}", exc_info=True)
                # 发生错误时，尝试保存当前批次
                if batch:
                    try:
                        await self._save_position_batch(batch)
                        batch = []
                    except Exception as batch_error:
                        logger.error(f"Failed to save batch after error: {batch_error}", exc_info=True)
        
        # 退出前刷新剩余批次
        if batch:
            logger.info(f"Flushing remaining {len(batch)} positions before exit")
            try:
                await self._save_position_batch(batch)
            except Exception as e:
                logger.error(f"Failed to flush remaining positions: {e}", exc_info=True)
        
        logger.info("Position writer loop stopped")
    
    async def _flush_remaining_trades(self) -> None:
        """刷新队列中剩余的所有成交数据."""
        remaining = []
        try:
            while True:
                try:
                    trade_data = await asyncio.wait_for(
                        self._trade_queue.get(),
                        timeout=0.1
                    )
                    remaining.append(trade_data)
                    self._trade_queue.task_done()
                except asyncio.TimeoutError:
                    break
        except Exception as e:
            logger.error(f"Error flushing remaining trades: {e}", exc_info=True)
        
        if remaining:
            logger.info(f"Flushing {len(remaining)} remaining trades from queue")
            try:
                await self._save_trade_batch(remaining)
            except Exception as e:
                logger.error(f"Failed to flush remaining trades: {e}", exc_info=True)
    
    async def _flush_remaining_orders(self) -> None:
        """刷新队列中剩余的所有订单数据."""
        remaining = []
        try:
            while True:
                try:
                    order_data = await asyncio.wait_for(
                        self._order_queue.get(),
                        timeout=0.1
                    )
                    remaining.append(order_data)
                    self._order_queue.task_done()
                except asyncio.TimeoutError:
                    break
        except Exception as e:
            logger.error(f"Error flushing remaining orders: {e}", exc_info=True)
        
        if remaining:
            logger.info(f"Flushing {len(remaining)} remaining orders from queue")
            try:
                await self._save_order_batch(remaining)
            except Exception as e:
                logger.error(f"Failed to flush remaining orders: {e}", exc_info=True)
    
    async def _flush_remaining_positions(self) -> None:
        """刷新队列中剩余的所有持仓数据."""
        remaining = []
        try:
            while True:
                try:
                    position_data = await asyncio.wait_for(
                        self._position_queue.get(),
                        timeout=0.1
                    )
                    remaining.append(position_data)
                    self._position_queue.task_done()
                except asyncio.TimeoutError:
                    break
        except Exception as e:
            logger.error(f"Error flushing remaining positions: {e}", exc_info=True)
        
        if remaining:
            logger.info(f"Flushing {len(remaining)} remaining positions from queue")
            try:
                await self._save_position_batch(remaining)
            except Exception as e:
                logger.error(f"Failed to flush remaining positions: {e}", exc_info=True)
    
    async def _save_trade_batch(self, batch: list[Dict[str, Any]]) -> None:
        """批量保存成交数据到数据库.
        
        Args:
            batch: 成交数据列表
        """
        if not batch:
            return
        
        save_start_time = datetime.utcnow()
        logger.debug(f"Saving batch of {len(batch)} trades to database")
        
        try:
            # 确保账号特定的表已创建（如果是新账号）
            await self._ensure_account_tables_if_needed()
            
            async with self.db_manager.session() as session:
                # 处理批次中的所有成交数据
                all_trades = []
                for data in batch:
                    # 支持多种格式：
                    # 1. trades 列表格式: {"trades": [...]}
                    # 2. 单个成交对象格式: {"trade_id": "...", "order_id": "...", ...}
                    # 3. XT WebSocket 格式: {"orderId": "...", "orderSide": "...", ...}
                    trades = []
                    if "trades" in data and isinstance(data.get("trades"), list):
                        trades = data.get("trades", [])
                    elif isinstance(data, list):
                        trades = data
                    elif "orderId" in data or "order_id" in data or "trade_id" in data or "tradeId" in data:
                        # 单个成交对象（包括 XT 格式），转换为列表
                        trades = [data]
                    
                    all_trades.extend(trades)
                
                if not all_trades:
                    logger.debug("No trades data to save in batch")
                    return
                
                for trade in all_trades:
                    # 支持不同的字段名
                    # XT 格式没有 trade_id，使用 orderId + timestamp 作为 trade_id
                    trade_id = trade.get("trade_id") or trade.get("tradeId") or ""
                    order_id = trade.get("orderId") or trade.get("order_id") or ""
                    
                    # 如果没有 trade_id，使用 orderId + timestamp 生成一个
                    if not trade_id and order_id:
                        timestamp = trade.get("timestamp")
                        if timestamp:
                            trade_id = f"{order_id}_{timestamp}"
                        else:
                            trade_id = order_id
                    
                    if not trade_id:
                        logger.debug("Trade missing trade_id and orderId, skipping")
                        continue
                    
                    symbol = trade.get("symbol") or ""
                    # XT 使用 orderSide，其他使用 side
                    side = trade.get("orderSide") or trade.get("side") or ""
                    price = self._safe_decimal(trade.get("price") or "0")
                    quantity = self._safe_decimal(trade.get("quantity") or trade.get("qty") or "0")
                    quote_quantity = self._safe_decimal(
                        trade.get("quote_quantity") or 
                        trade.get("quoteQuantity") or 
                        trade.get("amount") or 
                        str(price * quantity)  # 如果没有提供，计算它
                    )
                    
                    # 使用 XT 的 timestamp（如果存在），否则使用当前时间
                    # 注意：数据库字段是 TIMESTAMP WITHOUT TIME ZONE，需要 naive datetime（不带时区）
                    timestamp = trade.get("timestamp")
                    message_received_at_str = trade.get("_message_received_at")
                    message_received_at = None
                    if message_received_at_str:
                        try:
                            message_received_at = datetime.fromisoformat(message_received_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
                        except (ValueError, AttributeError):
                            pass
                    
                    if timestamp:
                        try:
                            # XT timestamp 是毫秒级时间戳，需要除以 1000
                            if isinstance(timestamp, (int, float)):
                                # 先转换为 UTC 时间，然后去掉时区信息（转为 naive datetime）
                                update_time = datetime.fromtimestamp(timestamp/1000.0, tz=timezone.utc).replace(tzinfo=None)
                                
                                # 计算延迟：消息接收时间 vs timestamp（用于监控）
                                if message_received_at:
                                    delay_from_timestamp = (message_received_at - update_time).total_seconds()
                                    # 记录详细的时间信息（用于诊断）
                                    logger.debug(
                                        f"成交时间分析: trade_id={trade_id}, "
                                        f"timestamp={update_time}, "
                                        f"消息接收时间={message_received_at}, "
                                        f"延迟={delay_from_timestamp:.2f}秒"
                                    )
                                    # 如果延迟超过阈值，记录警告
                                    if abs(delay_from_timestamp) > 300:  # 超过5分钟
                                        logger.warning(
                                            f"⚠️ 成交数据时间延迟较大: trade_id={trade_id}, "
                                            f"timestamp={update_time}, "
                                            f"消息接收时间={message_received_at}, "
                                            f"延迟={delay_from_timestamp:.2f}秒 ({delay_from_timestamp/60:.2f}分钟) - "
                                            f"可能原因: WebSocket推送延迟、消息处理积压或数据库写入延迟"
                                        )
                            else:
                                update_time = datetime.utcnow()
                        except (ValueError, OSError):
                            update_time = datetime.utcnow()
                    else:
                        update_time = datetime.utcnow()
                    
                    TradeUpdateModel = self._get_model('XTTradeUpdate')
                    record = TradeUpdateModel(
                        update_time=update_time,
                        account_id=self.account_id,
                        symbol=symbol,
                        order_id=str(order_id),
                        trade_id=str(trade_id),
                        side=side,
                        price=price,
                        quantity=quantity,
                        quote_quantity=quote_quantity,
                        commission=self._safe_decimal(trade.get("commission") or trade.get("fee") or "0"),
                        commission_asset=trade.get("commission_asset") or trade.get("feeCurrency") or "",
                        is_maker=trade.get("is_maker") or trade.get("isMaker") or False,
                        position_side=trade.get("position_side") or trade.get("positionSide") or "",
                        raw_data=json.dumps(trade, cls=DecimalEncoder),
                    )
                    session.add(record)
                    logger.info(
                        f"保存成交记录: trade_id={trade_id}, order_id={order_id}, symbol={symbol}, "
                        f"side={side}, price={price}, quantity={quantity},timestamp={timestamp},update_time={update_time}"
                    )
                
                commit_start = datetime.utcnow()
                await session.commit()
                commit_duration = (datetime.utcnow() - commit_start).total_seconds()
                total_duration = (datetime.utcnow() - save_start_time).total_seconds()
                created_at_time = datetime.utcnow()
                
                logger.info(
                    f"成功批量保存 {len(all_trades)} 条成交记录到数据库 "
                    f"(总耗时: {total_duration:.3f}秒, 提交耗时: {commit_duration:.3f}秒, "
                    f"平均每条: {total_duration/len(all_trades)*1000:.2f}ms, "
                    f"队列剩余: {self._trade_queue.qsize()})"
                )
                
                # 监控数据库写入性能
                if commit_duration > 1.0:
                    logger.warning(
                        f"⚠️ 数据库写入延迟: 提交耗时 {commit_duration:.2f} 秒，可能影响消息处理速度。"
                        f"建议检查: 数据库连接池、网络延迟、数据库性能"
                    )
                
                # 监控队列积压
                queue_size = self._trade_queue.qsize()
                if queue_size > 100:
                    logger.warning(
                        f"⚠️ 成交消息队列积压: {queue_size} 条消息待处理，"
                        f"可能原因: 数据库写入速度跟不上消息接收速度"
                    )
                
                # 对于每条成交记录，记录时间差异（用于诊断）
                for trade in all_trades:
                    trade_timestamp = trade.get("timestamp")
                    trade_message_received_at_str = trade.get("_message_received_at")
                    trade_message_received_at = None
                    if trade_message_received_at_str:
                        try:
                            trade_message_received_at = datetime.fromisoformat(trade_message_received_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
                        except (ValueError, AttributeError):
                            pass
                    
                    if trade_timestamp and trade_message_received_at:
                        try:
                            if isinstance(trade_timestamp, (int, float)):
                                timestamp_dt = datetime.fromtimestamp(trade_timestamp/1000.0, tz=timezone.utc).replace(tzinfo=None)
                                # 计算各个时间点的差异
                                timestamp_to_received = (trade_message_received_at - timestamp_dt).total_seconds()
                                timestamp_to_created = (created_at_time - timestamp_dt).total_seconds()
                                
                                # 如果延迟超过阈值，记录详细信息
                                if abs(timestamp_to_created) > 300:  # 超过5分钟
                                    logger.warning(
                                        f"⚠️ 成交记录时间链分析: "
                                        f"timestamp={timestamp_dt}, "
                                        f"消息接收={trade_message_received_at}, "
                                        f"数据库创建={created_at_time}, "
                                        f"timestamp→接收延迟={timestamp_to_received:.2f}秒, "
                                        f"timestamp→创建延迟={timestamp_to_created:.2f}秒, "
                                        f"处理耗时={total_duration:.3f}秒"
                                    )
                        except (ValueError, OSError):
                            pass
                
        except Exception as e:
            logger.error(f"Failed to save trade batch: {e}", exc_info=True)
    
    async def _save_order_batch(self, batch: list[Dict[str, Any]]) -> None:
        """批量保存订单数据到数据库.
        
        Args:
            batch: 订单数据列表
        """
        if not batch:
            return
        
        save_start_time = datetime.utcnow()
        logger.debug(f"Saving batch of {len(batch)} orders to database")
        
        try:
            # 确保账号特定的表已创建（如果是新账号）
            await self._ensure_account_tables_if_needed()
            
            async with self.db_manager.session() as session:
                OrderUpdateModel = self._get_model('XTOrderUpdate')
                records = []
                
                for order_data in batch:
                    if "orderId" not in order_data and "order_id" not in order_data:
                        continue
                    
                    order_id = order_data.get("orderId") or order_data.get("order_id", "")
                    if not order_id:
                        continue
                    
                    symbol = order_data.get("symbol", "")
                    side = order_data.get("orderSide") or order_data.get("side", "")
                    order_type = order_data.get("orderType") or order_data.get("type", "")
                    quantity_raw = order_data.get("origQty") or order_data.get("quantity", "0")
                    quantity = self._safe_decimal(quantity_raw)
                    price = self._safe_decimal(order_data.get("price", "0"))
                    filled_quantity_raw = order_data.get("executedQty") or order_data.get("filledQuantity") or order_data.get("filled_quantity", "0")
                    filled_quantity = self._safe_decimal(filled_quantity_raw)
                    status = order_data.get("state") or order_data.get("status", "")
                    
                    # 解析时间戳
                    timestamp = order_data.get("timestamp") or order_data.get("updatedTime") or order_data.get("updateTime") or order_data.get("createdTime") or order_data.get("createTime")
                    if timestamp:
                        try:
                            if isinstance(timestamp, (int, float)):
                                update_time = datetime.fromtimestamp(timestamp/1000.0, tz=timezone.utc).replace(tzinfo=None)
                            else:
                                update_time = datetime.utcnow()
                        except (ValueError, OSError):
                            update_time = datetime.utcnow()
                    else:
                        update_time = datetime.utcnow()
                    
                    record = OrderUpdateModel(
                        update_time=update_time,
                        account_id=self.account_id,
                        symbol=symbol,
                        order_id=str(order_id),
                        client_order_id=order_data.get("clientOrderId") or order_data.get("client_order_id", ""),
                        side=side,
                        order_type=order_type,
                        position_side=order_data.get("positionSide") or order_data.get("position_side", ""),
                        quantity=quantity,
                        price=price,
                        filled_quantity=filled_quantity,
                        status=status,
                        time_in_force=order_data.get("timeInForce") or order_data.get("time_in_force", ""),
                        create_time=self._parse_timestamp(order_data.get("createdTime") or order_data.get("createTime") or order_data.get("created_time")),
                        update_time_order=self._parse_timestamp(order_data.get("updatedTime") or order_data.get("updateTime") or order_data.get("updated_time")),
                        raw_data=json.dumps(order_data, cls=DecimalEncoder),
                    )
                    records.append(record)
                
                if records:
                    session.add_all(records)
                    commit_start = datetime.utcnow()
                    await session.commit()
                    commit_duration = (datetime.utcnow() - commit_start).total_seconds()
                    total_duration = (datetime.utcnow() - save_start_time).total_seconds()
                    
                    logger.debug(
                        f"Saved {len(records)} orders in batch: "
                        f"total={total_duration:.3f}s, commit={commit_duration:.3f}s"
                    )
                    
                    # 监控数据库写入延迟
                    if commit_duration > 1.0:
                        logger.warning(
                            f"⚠️ 订单数据库写入延迟: 提交耗时 {commit_duration:.2f} 秒"
                        )
                    
                    # 监控队列积压
                    queue_size = self._order_queue.qsize()
                    if queue_size > 100:
                        logger.warning(
                            f"⚠️ 订单消息队列积压: {queue_size} 条消息待处理"
                        )
                
        except Exception as e:
            logger.error(f"Failed to save order batch: {e}", exc_info=True)
    
    async def _save_position_batch(self, batch: list[Dict[str, Any]]) -> None:
        """批量保存持仓数据到数据库.
        
        Args:
            batch: 持仓数据列表
        """
        if not batch:
            return
        
        save_start_time = datetime.utcnow()
        logger.debug(f"Saving batch of {len(batch)} positions to database")
        
        try:
            # 确保账号特定的表已创建（如果是新账号）
            await self._ensure_account_tables_if_needed()
            
            async with self.db_manager.session() as session:
                PositionUpdateModel = self._get_model('XTPositionUpdate')
                records = []
                
                for position_data in batch:
                    if "symbol" not in position_data:
                        continue
                    
                    symbol = position_data.get("symbol", "")
                    if not symbol:
                        continue
                    
                    side = position_data.get("positionSide") or position_data.get("side", "")
                    quantity_raw = position_data.get("positionSize") or position_data.get("quantity") or position_data.get("positionAmt", "0")
                    quantity = self._safe_decimal(quantity_raw)
                    
                    # 跳过持仓量为0的记录
                    if quantity == 0:
                        continue
                    
                    entry_price = self._safe_decimal(position_data.get("entryPrice", "0"))
                    realized_pnl_raw = position_data.get("realizedProfit") or position_data.get("realizedPnl") or "0"
                    realized_pnl = self._safe_decimal(realized_pnl_raw)
                    
                    # 标记价和未实现盈亏：从缓存获取
                    mark_price = Decimal("0")
                    unrealized_pnl = Decimal("0")
                    
                    cache_key = f"{symbol}_{side}"
                    cached_data = self._mark_price_cache.get(cache_key)
                    
                    if cached_data:
                        cache_age = (datetime.utcnow() - cached_data["timestamp"]).total_seconds()
                        if cache_age < self._mark_price_cache_ttl:
                            mark_price = cached_data["price"]
                            # 计算未实现盈亏
                            if side.upper() == "SHORT":
                                unrealized_pnl = (entry_price - mark_price) * quantity
                            else:
                                unrealized_pnl = (mark_price - entry_price) * quantity
                    
                    # 解析时间戳
                    timestamp = position_data.get("timestamp") or position_data.get("updateTime")
                    if timestamp:
                        try:
                            if isinstance(timestamp, (int, float)):
                                update_time = datetime.fromtimestamp(timestamp/1000.0, tz=timezone.utc).replace(tzinfo=None)
                            else:
                                update_time = datetime.utcnow()
                        except (ValueError, OSError):
                            update_time = datetime.utcnow()
                    else:
                        update_time = datetime.utcnow()
                    
                    liquidation_price_raw = position_data.get("breakPrice") or position_data.get("liquidationPrice", "0")
                    
                    record = PositionUpdateModel(
                        update_time=update_time,
                        account_id=self.account_id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        entry_price=entry_price,
                        mark_price=mark_price,
                        liquidation_price=self._safe_decimal(liquidation_price_raw),
                        unrealized_pnl=unrealized_pnl,
                        leverage=int(position_data.get("leverage", "1")),
                        margin=self._safe_decimal(position_data.get("isolatedMargin") or position_data.get("margin", "0")),
                        raw_data=json.dumps(position_data, cls=DecimalEncoder),
                    )
                    records.append(record)
                
                if records:
                    session.add_all(records)
                    commit_start = datetime.utcnow()
                    await session.commit()
                    commit_duration = (datetime.utcnow() - commit_start).total_seconds()
                    total_duration = (datetime.utcnow() - save_start_time).total_seconds()
                    
                    logger.debug(
                        f"Saved {len(records)} positions in batch: "
                        f"total={total_duration:.3f}s, commit={commit_duration:.3f}s"
                    )
                    
                    # 监控数据库写入延迟
                    if commit_duration > 1.0:
                        logger.warning(
                            f"⚠️ 持仓数据库写入延迟: 提交耗时 {commit_duration:.2f} 秒"
                        )
                    
                    # 监控队列积压
                    queue_size = self._position_queue.qsize()
                    if queue_size > 50:
                        logger.warning(
                            f"⚠️ 持仓消息队列积压: {queue_size} 条消息待处理"
                        )
                
        except Exception as e:
            logger.error(f"Failed to save position batch: {e}", exc_info=True)
    
    async def _sync_missing_data(self) -> None:
        """补充断线期间缺失的数据.

        仅在重连后调用，从断开时间往前回补1小时内的订单和成交数据。
        账户和持仓数据直接获取最新状态。
        """
        if not self.enable_data_sync:
            logger.info("Data sync is disabled, skipping missing data sync")
            return
        
        if not self.rest_client:
            logger.warning("REST client not available, cannot sync missing data")
            return

        try:
            # 固定回补时间为1小时
            lookback_hours = 1
            
            # 如果记录了断开时间，使用断开时间作为结束时间，往前推1小时
            # 如果只有重连时间，使用重连时间作为结束时间，往前推1小时
            # 否则使用当前时间往前推1小时
            if self.disconnect_time:
                end_time = self.disconnect_time
                start_time = end_time - timedelta(hours=lookback_hours)
                logger.info(
                    "Syncing missing data from disconnect time (1-hour lookback)",
                    extra={
                        "disconnect_time": self.disconnect_time.isoformat(),
                        "reconnect_time": self.reconnect_time.isoformat() if self.reconnect_time else None,
                        "lookback_hours": lookback_hours,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat()
                    }
                )
            elif self.reconnect_time:
                # 如果没有断开时间但有重连时间，使用重连时间作为结束时间，往前推1小时
                # 这样可以确保重连时也会回补数据，即使没有检测到断线
                end_time = self.reconnect_time
                start_time = end_time - timedelta(hours=lookback_hours)
                logger.info(
                    "Syncing missing data from reconnect time (1-hour lookback, no disconnect time recorded)",
                    extra={
                        "reconnect_time": self.reconnect_time.isoformat(),
                        "lookback_hours": lookback_hours,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat()
                    }
                )
            else:
                # 如果既没有断开时间也没有重连时间，使用当前时间往前推1小时（兼容旧逻辑）
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(hours=lookback_hours)
                logger.info(
                    "Syncing missing data for fixed 1-hour lookback period (no disconnect/reconnect time recorded)",
                    extra={
                        "lookback_hours": lookback_hours,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat()
                    }
                )

            # 同步账户余额（总是同步最新状态）
            if "account" in self.enabled_channels:
                await self._sync_account_data()

            # 同步持仓数据（总是同步最新状态）
            if "position" in self.enabled_channels:
                await self._sync_position_data()

            # 同步订单数据（从断开时间往前回补1小时）
            if "order" in self.enabled_channels:
                await self._sync_order_data_fixed_lookback(start_time, end_time)

            # 同步成交数据（从断开时间往前回补1小时）
            # 已禁用：REST API 返回的成交数据缺少 side 字段，暂时禁用回补功能
            # if "trade" in self.enabled_channels:
            #     await self._sync_trade_data_fixed_lookback(start_time, end_time)

            # 清除断线时间记录
            if self.disconnect_time:
                logger.debug("Clearing disconnect time after sync")
                self.disconnect_time = None

            # 更新同步统计（记录重连补充数据的次数）
            await self._update_sync_stats()

            logger.info("Missing data sync completed successfully")

        except Exception as e:
            logger.error(f"Failed to sync missing data: {e}")
    
    async def _sync_account_data(self) -> None:
        """同步账户数据."""
        try:
            balances = await self.rest_client.get_balance()
            
            # 初始化余额缓存（用于快速查询，但划转分析主要依赖数据库）
            for currency, balance_data in balances.items():
                currency_key = currency.lower()
                self._last_account_balances[currency_key] = {
                    "available": balance_data.get("available", Decimal("0")),
                    "frozen": balance_data.get("frozen", Decimal("0")),
                    "total": balance_data.get("total", Decimal("0")),
                }
            
            logger.info(
                "Initialized balance cache (transfer analysis uses database records)",
                extra={
                    "currencies": list(self._last_account_balances.keys()),
                    "currency_count": len(self._last_account_balances)
                }
            )
            
            # 保存到数据库
            async with self.db_manager.session() as session:
                update_time = datetime.utcnow()
                
                AccountUpdateModel = self._get_model('XTAccountUpdate')
                for currency, balance_data in balances.items():
                    record = AccountUpdateModel(
                        update_time=update_time,
                        currency=currency,
                        available=balance_data.get("available", Decimal("0")),
                        frozen=balance_data.get("frozen", Decimal("0")),
                        total=balance_data.get("total", Decimal("0")),
                        raw_data=json.dumps({
                            "source": "rest_sync",
                            "currency": currency,
                            "balance_data": {
                                "available": str(balance_data.get("available", Decimal("0"))),
                                "frozen": str(balance_data.get("frozen", Decimal("0"))),
                                "total": str(balance_data.get("total", Decimal("0"))),
                            },
                        }, cls=DecimalEncoder),
                    )
                    session.add(record)
                
                await session.commit()
                logger.debug("Synced account data from REST API")
                
        except Exception as e:
            logger.error(f"Failed to sync account data: {e}")
    
    async def _sync_position_data(self) -> None:
        """同步持仓数据."""
        try:
            positions = await self.rest_client.get_positions(None)
            
            # 保存到数据库
            async with self.db_manager.session() as session:
                update_time = datetime.utcnow()
                
                PositionUpdateModel = self._get_model('XTPositionUpdate')
                for position in positions:
                    record = PositionUpdateModel(
                        update_time=update_time,
                        account_id=self.account_id,
                        symbol=position.symbol,
                        side=position.side,
                        quantity=position.quantity,
                        entry_price=position.entry_price,
                        mark_price=position.mark_price,
                        liquidation_price=position.liquidation_price,
                        unrealized_pnl=position.unrealized_pnl,
                        leverage=position.leverage,
                        margin=position.margin,
                        roe=position.roe,
                        raw_data=json.dumps({
                            "source": "rest_sync",
                            "position": position.__dict__,
                        }, cls=DecimalEncoder),
                    )
                    session.add(record)
                
                await session.commit()
                logger.debug("Synced position data from REST API")
                
        except Exception as e:
            logger.error(f"Failed to sync position data: {e}")
    
    async def _sync_order_data(self, use_disconnect_period: bool = False) -> None:
        """同步订单数据.

        使用 REST API 查询订单历史，补充断线期间的订单数据。

        Args:
            use_disconnect_period: 是否使用断线时间区间查询
        """
        try:
            # 如果需要使用断线时间区间，且有断线时间记录，查询断线期间的订单
            start_time = None
            end_time = None

            if use_disconnect_period and self.disconnect_time and self.reconnect_time:
                # 转换为毫秒时间戳
                start_time = int(self.disconnect_time.timestamp() * 1000)
                end_time = int(self.reconnect_time.timestamp() * 1000)
                logger.info(
                    "Syncing orders for disconnection period",
                    extra={
                        "start_time": self.disconnect_time.isoformat(),
                        "end_time": self.reconnect_time.isoformat()
                    }
                )
            else:
                logger.info("Syncing recent orders")

            # 查询订单列表
            orders = await self.rest_client.get_order_list(
                symbol=None,  # 查询所有交易对
                start_time=start_time,
                end_time=end_time,
                limit=500,  # 最多查询500条
            )

            # 保存到数据库
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                update_time = datetime.utcnow()
                saved_count = 0
                skipped_count = 0

                for order in orders:
                    try:
                        symbol = f"{order.trading_pair.base_currency}_{order.trading_pair.quote_currency}".lower()
                        order_id = order.exchange_order_id

                        # 检查订单是否已存在（去重）
                        OrderUpdateModel = self._get_model('XTOrderUpdate')
                        existing_result = await session.execute(
                            select(OrderUpdateModel).where(
                                OrderUpdateModel.order_id == order_id,
                                OrderUpdateModel.symbol == symbol
                            ).limit(1)
                        )
                        existing_order = existing_result.scalar_one_or_none()

                        if existing_order:
                            logger.debug(f"Order {order_id} already exists, skipping")
                            skipped_count += 1
                            continue

                        OrderUpdateModel = self._get_model('XTOrderUpdate')
                        client_order_id = order.order_id if order.order_id else ""
                        record = OrderUpdateModel(
                            update_time=update_time,
                            account_id=self.account_id,
                            symbol=symbol,
                            order_id=order_id,
                            client_order_id=client_order_id,
                            side=order.side.value,
                            order_type=order.order_type.value,
                            position_side=order.position_side or "LONG",
                            quantity=order.quantity,
                            price=order.price or Decimal("0"),
                            filled_quantity=Decimal("0"),  # 填充数量需要从详细信息获取
                            status=order.status.value,
                            time_in_force="GTC",
                            create_time=order.created_at,
                            update_time_order=order.updated_at,
                            raw_data=json.dumps({
                                "source": "rest_sync",
                                "order_id": order.exchange_order_id,
                            }, cls=DecimalEncoder),
                        )
                        session.add(record)
                        saved_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to save order: {e}")
                        continue

                await session.commit()
                logger.debug("Synced order data from REST API", extra={"saved": saved_count, "skipped": skipped_count})

        except Exception as e:
            logger.error(f"Failed to sync order data: {e}")
    
    async def _sync_trade_data(self, use_disconnect_period: bool = False) -> None:
        """同步成交数据.

        使用 REST API 查询成交历史，补充断线期间的成交数据。

        Args:
            use_disconnect_period: 是否使用断线时间区间查询
        """
        try:
            # 如果需要使用断线时间区间，且有断线时间记录，查询断线期间的成交
            start_time = None
            end_time = None

            if use_disconnect_period and self.disconnect_time and self.reconnect_time:
                # 转换为毫秒时间戳
                start_time = int(self.disconnect_time.timestamp() * 1000)
                end_time = int(self.reconnect_time.timestamp() * 1000)
                logger.info(
                    "Syncing trades for disconnection period",
                    extra={
                        "start_time": self.disconnect_time.isoformat(),
                        "end_time": self.reconnect_time.isoformat(),
                    }
                )
            else:
                logger.info("Syncing recent trades")

            # 查询成交列表
            trades = await self.rest_client.get_user_trades(
                symbol=None,  # 查询所有交易对
                start_time=start_time,
                end_time=end_time,
                limit=500,  # 最多查询500条
            )

            # 保存到数据库
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                saved_count = 0
                skipped_count = 0

                for trade in trades:
                    try:
                        symbol = trade.get("symbol", "")
                        trade_id = trade.get("id", "")

                        if not trade_id:
                            continue

                        # 从 trade 数据中提取时间（REST API 返回的 time 字段是毫秒级时间戳）
                        trade_time = trade.get("time") or trade.get("timestamp")
                        if trade_time:
                            try:
                                # XT REST API 返回的 time 是毫秒级时间戳，需要除以 1000
                                update_time = datetime.fromtimestamp(int(trade_time) / 1000.0, tz=timezone.utc)
                            except (ValueError, TypeError, OSError):
                                update_time = datetime.utcnow()
                        else:
                            update_time = datetime.utcnow()

                        # 检查成交是否已存在（去重）
                        TradeUpdateModel = self._get_model('XTTradeUpdate')
                        existing_result = await session.execute(
                            select(TradeUpdateModel).where(
                                TradeUpdateModel.trade_id == str(trade_id),
                                TradeUpdateModel.symbol == symbol
                            ).limit(1)
                        )
                        existing_trade = existing_result.scalar_one_or_none()

                        if existing_trade:
                            logger.debug(f"Trade {trade_id} already exists, skipping")
                            skipped_count += 1
                            continue

                        record = XTTradeUpdate(
                            update_time=update_time,
                            symbol=symbol,
                            order_id=str(trade.get("orderId", "")),
                            trade_id=str(trade_id),
                            side=trade.get("side", ""),
                            price=self._safe_decimal(trade.get("price", "0")),
                            quantity=self._safe_decimal(trade.get("qty", "0")),
                            quote_quantity=self._safe_decimal(trade.get("quoteQty", "0")),
                            commission=self._safe_decimal(trade.get("commission", "0")),
                            commission_asset=trade.get("commissionAsset", ""),
                            is_maker=trade.get("isMaker", False),
                            position_side=trade.get("positionSide", ""),
                            raw_data=json.dumps({
                                "source": "rest_sync",
                                "trade": trade,
                            }, cls=DecimalEncoder),
                        )
                        session.add(record)
                        saved_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to save trade: {e}", extra={"trade_id": trade.get("id")})
                        continue

                await session.commit()
                logger.debug("Synced trade data from REST API", extra={"saved": saved_count, "skipped": skipped_count})

        except Exception as e:
            logger.error(f"Failed to sync trade data: {e}")
    
    async def _sync_order_data_fixed_lookback(self, start_time: datetime, end_time: datetime) -> None:
        """同步订单数据（固定回补时间）.

        使用 REST API 查询指定时间范围内的订单历史。

        Args:
            start_time: 开始时间
            end_time: 结束时间
        """
        try:
            # 转换为毫秒时间戳
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(end_time.timestamp() * 1000)
            
            logger.info(
                "Syncing orders for fixed lookback period",
                extra={
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "start_timestamp": start_timestamp,
                    "end_timestamp": end_timestamp
                }
            )

            # 查询订单列表
            orders = await self.rest_client.get_order_list(
                symbol=None,  # 查询所有交易对
                start_time=start_timestamp,
                end_time=end_timestamp,
                limit=1000,  # 增加查询限制
            )

            # 保存到数据库
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                update_time = datetime.utcnow()
                saved_count = 0
                skipped_count = 0

                for order in orders:
                    try:
                        symbol = f"{order.trading_pair.base_currency}_{order.trading_pair.quote_currency}".lower()
                        order_id = order.exchange_order_id

                        # 检查订单是否已存在（去重）
                        OrderUpdateModel = self._get_model('XTOrderUpdate')
                        existing_result = await session.execute(
                            select(OrderUpdateModel).where(
                                OrderUpdateModel.order_id == order_id,
                                OrderUpdateModel.symbol == symbol
                            ).limit(1)
                        )
                        existing_order = existing_result.scalar_one_or_none()

                        if existing_order:
                            logger.debug(f"Order {order_id} already exists, skipping")
                            skipped_count += 1
                            continue

                        create_time = (
                            order.created_at.astimezone(timezone.utc).replace(tzinfo=None)
                            if order.created_at
                            else None
                        )
                        update_time_order = (
                            order.updated_at.astimezone(timezone.utc).replace(tzinfo=None)
                            if order.updated_at
                            else create_time
                        )

                        OrderUpdateModel = self._get_model('XTOrderUpdate')
                        record = OrderUpdateModel(
                            update_time=update_time,
                            account_id=self.account_id,
                            symbol=symbol,
                            order_id=order_id,
                            client_order_id=order.order_id or "",
                            side=order.side.value,
                            order_type=order.order_type.value,
                            position_side=order.position_side or "LONG",
                            quantity=order.quantity,
                            price=order.price or Decimal("0"),
                            filled_quantity=Decimal("0"),  # 填充数量需要从详细信息获取
                            status=order.status.value,
                            time_in_force="GTC",
                            create_time=create_time,
                            update_time_order=update_time_order,
                            raw_data=json.dumps({
                                "source": "rest_sync_fixed_lookback",
                                "order_id": order.exchange_order_id,
                                "lookback_hours": 1,
                            }, cls=DecimalEncoder),
                        )
                        session.add(record)
                        saved_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to save order: {e}")
                        continue

                await session.commit()
                logger.info("Synced order data from REST API (fixed lookback)", extra={"saved": saved_count, "skipped": skipped_count})

        except Exception as e:
            logger.error(f"Failed to sync order data (fixed lookback): {e}")
    
    async def _sync_trade_data_fixed_lookback(self, start_time: datetime, end_time: datetime) -> None:
        """同步成交数据（固定回补时间）.

        使用 REST API 查询指定时间范围内的成交历史。

        Args:
            start_time: 开始时间
            end_time: 结束时间
        """
        try:
            # 转换为毫秒时间戳
            start_timestamp = int(start_time.timestamp() * 1000)
            end_timestamp = int(end_time.timestamp() * 1000)
            
            logger.info(
                "Syncing trades for fixed lookback period",
                extra={
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "start_timestamp": start_timestamp,
                    "end_timestamp": end_timestamp
                }
            )

            # 查询成交列表
            trades = await self.rest_client.get_user_trades(
                symbol=None,  # 查询所有交易对
                start_time=start_timestamp,
                end_time=end_timestamp,
                limit=1000,  # 增加查询限制
            )

            # 保存到数据库
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                update_time = datetime.utcnow()
                saved_count = 0
                skipped_count = 0

                for trade in trades:
                    try:
                        symbol = trade.get("symbol", "")
                        trade_id = trade.get("id", "")

                        if not trade_id:
                            continue

                        # 检查成交是否已存在（去重）
                        TradeUpdateModel = self._get_model('XTTradeUpdate')
                        existing_result = await session.execute(
                            select(TradeUpdateModel).where(
                                TradeUpdateModel.trade_id == str(trade_id),
                                TradeUpdateModel.symbol == symbol
                            ).limit(1)
                        )
                        existing_trade = existing_result.scalar_one_or_none()

                        if existing_trade:
                            logger.debug(f"Trade {trade_id} already exists, skipping")
                            skipped_count += 1
                            continue

                        record = XTTradeUpdate(
                            update_time=update_time,
                            account_id=self.account_id,
                            symbol=symbol,
                            order_id=str(trade.get("orderId", "")),
                            trade_id=str(trade_id),
                            side=trade.get("side", ""),
                            price=self._safe_decimal(trade.get("price", "0")),
                            quantity=self._safe_decimal(trade.get("qty", "0")),
                            quote_quantity=self._safe_decimal(trade.get("quoteQty", "0")),
                            commission=self._safe_decimal(trade.get("commission", "0")),
                            commission_asset=trade.get("commissionAsset", ""),
                            is_maker=trade.get("isMaker", False),
                            position_side=trade.get("positionSide", ""),
                            raw_data=json.dumps({
                                "source": "rest_sync_fixed_lookback",
                                "trade": trade,
                                "lookback_hours": 1,
                            }, cls=DecimalEncoder),
                        )
                        session.add(record)
                        saved_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to save trade: {e}", extra={"trade_id": trade.get("id")})
                        continue

                await session.commit()
                logger.info("Synced trade data from REST API (fixed lookback)", extra={"saved": saved_count, "skipped": skipped_count})

        except Exception as e:
            logger.error(f"Failed to sync trade data (fixed lookback): {e}")
    
    async def _display_test_data(self) -> None:
        """显示测试数据以验证表格功能."""
        logger.debug("Displaying test data to verify table functionality")
        
        # 测试账户数据
        test_account_data = {
            "balances": [
                {
                    "currency": "USDT",
                    "available": "9.99",
                    "frozen": "0.00",
                    "total": "9.99"
                },
                {
                    "currency": "BTC",
                    "available": "0.0001",
                    "frozen": "0.0000",
                    "total": "0.0001"
                }
            ]
        }
        await self._display_account_update(test_account_data)
        
        # 测试持仓数据
        test_position_data = {
            "positions": [
                {
                    "symbol": "BTC_USDT",
                    "side": "LONG",
                    "quantity": "0.001",
                    "entry_price": "45000.00",
                    "mark_price": "45100.00",
                    "unrealized_pnl": "0.10"
                }
            ]
        }
        await self._display_position_update(test_position_data)
        
        # 测试订单数据
        test_order_data = {
            "orders": [
                {
                    "order_id": "123456789",
                    "symbol": "BTC_USDT",
                    "side": "BUY",
                    "quantity": "0.001",
                    "price": "45000.00",
                    "status": "NEW"
                }
            ]
        }
        await self._display_order_update(test_order_data)
        
        # 测试成交数据
        test_trade_data = {
            "trades": [
                {
                    "trade_id": "987654321",
                    "order_id": "123456789",
                    "symbol": "BTC_USDT",
                    "side": "BUY",
                    "price": "45000.00",
                    "quantity": "0.001",
                    "quote_quantity": "45.00"
                }
            ]
        }
        await self._display_trade_update(test_trade_data)

    # 数据变化检查方法

    def _has_account_changed(self, account_data: Dict[str, Any]) -> bool:
        """检查账户数据是否有变化."""
        # 将数据转换为可比较的格式，处理Decimal类型
        try:
            data_key = json.dumps(account_data, sort_keys=True, cls=DecimalEncoder)
        except (TypeError, ValueError):
            # 如果JSON序列化失败，使用字符串表示
            data_key = str(sorted(account_data.items()))

        # 比较是否有变化
        if data_key == self._last_account_data.get("key"):
            logger.debug("Account data unchanged, skipping")
            return False

        # 更新缓存
        self._last_account_data["key"] = data_key
        return True

    async def _mark_price_update_loop(self):
        """后台任务：定期更新标记价格缓存."""
        while self.is_running:
            try:
                await asyncio.sleep(self._mark_price_cache_ttl)  # 每5秒更新一次
                
                if not self.rest_client or not self.rest_client.is_connected:
                    continue
                
                try:
                    # 获取所有持仓的标记价格
                    positions = await self.rest_client.get_positions(None)
                    now = datetime.utcnow()
                    
                    for pos in positions:
                        cache_key = f"{pos.symbol}_{pos.position_side}"
                        self._mark_price_cache[cache_key] = {
                            "price": pos.mark_price,
                            "timestamp": now
                        }
                    
                    logger.debug(f"Updated mark price cache for {len(positions)} positions")
                except Exception as e:
                    logger.debug(f"Failed to update mark price cache: {e}")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in mark price update loop: {e}")
                await asyncio.sleep(1)  # 出错后等待1秒再重试
    
    def _has_position_changed(self, position_data: Dict[str, Any]) -> bool:
        """检查持仓数据是否有变化."""
        # 将数据转换为可比较的格式，处理Decimal类型
        try:
            data_key = json.dumps(position_data, sort_keys=True, cls=DecimalEncoder)
        except (TypeError, ValueError):
            # 如果JSON序列化失败，使用字符串表示
            data_key = str(sorted(position_data.items()))

        # 比较是否有变化
        if data_key == self._last_position_data.get("key"):
            logger.debug("Position data unchanged, skipping")
            return False

        # 更新缓存
        self._last_position_data["key"] = data_key
        return True

    def _has_order_changed(self, order_data: Dict[str, Any]) -> bool:
        """检查订单数据是否有变化."""
        # 订单数据通常每次都是新的或更新的，所以总是返回True
        # 除非订单ID和状态都相同
        # 支持多种字段名（XT, Binance, OKX, Gate）
        order_id = (
            order_data.get("order_id")
            or order_data.get("orderId")  # XT
            or order_data.get("i")  # Binance
            or order_data.get("ordId")  # OKX
            or order_data.get("id")  # Gate
            or (order_data.get("orders", [{}])[0].get("order_id") if order_data.get("orders") else None)
        )
        status = (
            order_data.get("status")
            or order_data.get("state")  # XT, OKX
            or order_data.get("X")  # Binance
            or (order_data.get("orders", [{}])[0].get("status") if order_data.get("orders") else None)
        )

        if not order_id:
            return True  # 无法识别订单，视为新数据

        cache_key = f"{order_id}:{status}"

        # 检查是否已处理过相同状态的订单
        if cache_key == self._last_order_data.get("key"):
            logger.debug("Order data unchanged")
            return False

        # 更新缓存
        self._last_order_data["key"] = cache_key
        return True

    def _has_trade_changed(self, trade_data: Dict[str, Any]) -> bool:
        """检查成交数据是否有变化."""
        # 成交数据每次都是新的，总是返回True
        # 除非trade_id或orderId+timestamp完全相同
        # XT 格式使用 orderId + timestamp 作为唯一标识
        trade_id = None
        if "trades" in trade_data and isinstance(trade_data.get("trades"), list) and len(trade_data.get("trades", [])) > 0:
            trade_id = trade_data.get("trades", [{}])[0].get("trade_id")
        else:
            # 单个成交对象
            trade_id = trade_data.get("trade_id") or trade_data.get("tradeId")
            # XT 格式：使用 orderId + timestamp 作为唯一标识
            if not trade_id:
                order_id = trade_data.get("orderId") or trade_data.get("order_id")
                timestamp = trade_data.get("timestamp")
                if order_id and timestamp:
                    trade_id = f"{order_id}_{timestamp}"
                elif order_id:
                    trade_id = order_id

        if not trade_id:
            return True  # 无法识别成交，视为新数据

        cache_key = str(trade_id)

        # 检查是否已处理过相同的成交
        if cache_key == self._last_trade_data.get("key"):
            logger.debug("Trade data unchanged")
            return False

        # 更新缓存
        self._last_trade_data["key"] = cache_key
        return True

    # 辅助方法

    def _generate_signature(self, message: str) -> str:
        """生成HMAC-SHA256签名."""
        import hmac
        import hashlib
        
        return hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
    
    def _safe_decimal(self, value: Any) -> Decimal:
        """安全转换为Decimal."""
        if value is None or value == "":
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (ValueError, TypeError):
            return Decimal("0")
    
    def _safe_int(self, value: Any) -> int:
        """安全转换为int."""
        if value is None or value == "":
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    
    def _parse_timestamp(self, timestamp: Any) -> Optional[datetime]:
        """解析时间戳."""
        if not timestamp:
            return None
        try:
            if isinstance(timestamp, (int, float)):
                return datetime.fromtimestamp(timestamp / 1000)
            elif isinstance(timestamp, str):
                return datetime.fromtimestamp(int(timestamp) / 1000)
            else:
                return None
        except (ValueError, TypeError):
            return None
    
    # 数据库记录方法
    
    async def _record_connection_start(self) -> None:
        """记录连接开始."""
        try:
            async with self.db_manager.session() as session:
                record = XTWebSocketConnection(
                    connection_id=self.connection_id,
                    start_time=datetime.utcnow(),
                    is_active=True,
                    raw_data=json.dumps({
                        "enabled_channels": list(self.enabled_channels),
                        "auto_reconnect": self.auto_reconnect,
                    }, cls=DecimalEncoder),
                )
                session.add(record)
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to record connection start: {e}")
    
    async def _record_connection_end(self) -> None:
        """记录连接结束."""
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(XTWebSocketConnection).where(
                        XTWebSocketConnection.connection_id == self.connection_id
                    )
                )
                record = result.scalar_one_or_none()
                
                if record:
                    record.end_time = datetime.utcnow()
                    record.is_active = False
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"Failed to record connection end: {e}")
    
    async def _update_message_stats(self) -> None:
        """更新消息统计."""
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(XTWebSocketConnection).where(
                        XTWebSocketConnection.connection_id == self.connection_id
                    )
                )
                record = result.scalar_one_or_none()
                
                if record:
                    record.total_messages += 1
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"Failed to update message stats: {e}")
    
    async def _update_account_stats(self) -> None:
        """更新账户统计."""
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(XTWebSocketConnection).where(
                        XTWebSocketConnection.connection_id == self.connection_id
                    )
                )
                record = result.scalar_one_or_none()
                
                if record:
                    record.account_updates += 1
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"Failed to update account stats: {e}")
    
    async def _update_position_stats(self) -> None:
        """更新持仓统计."""
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(XTWebSocketConnection).where(
                        XTWebSocketConnection.connection_id == self.connection_id
                    )
                )
                record = result.scalar_one_or_none()
                
                if record:
                    record.position_updates += 1
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"Failed to update position stats: {e}")
    
    async def _update_order_stats(self) -> None:
        """更新订单统计."""
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(XTWebSocketConnection).where(
                        XTWebSocketConnection.connection_id == self.connection_id
                    )
                )
                record = result.scalar_one_or_none()
                
                if record:
                    record.order_updates += 1
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"Failed to update order stats: {e}")
    
    async def _update_trade_stats(self) -> None:
        """更新成交统计."""
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(XTWebSocketConnection).where(
                        XTWebSocketConnection.connection_id == self.connection_id
                    )
                )
                record = result.scalar_one_or_none()
                
                if record:
                    record.trade_updates += 1
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"Failed to update trade stats: {e}")
    
    async def _update_sync_stats(self) -> None:
        """更新数据补充统计（仅在重连补充数据时调用）."""
        try:
            async with self.db_manager.session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(XTWebSocketConnection).where(
                        XTWebSocketConnection.connection_id == self.connection_id
                    )
                )
                record = result.scalar_one_or_none()

                if record:
                    record.data_sync_count += 1
                    record.last_sync_time = datetime.utcnow()
                    await session.commit()

        except Exception as e:
            logger.error(f"Failed to update sync stats: {e}")
    
    def _record_order_for_transfer_analysis(self, order_data: Dict[str, Any]) -> None:
        """记录订单信息用于划转分析."""
        try:
            # 提取订单ID和时间
            order_id = order_data.get("orderId") or order_data.get("order_id")
            if not order_id:
                return
            
            # 记录订单信息（保留最近100个订单，用于判断余额变化是否由交易引起）
            self._recent_orders[order_id] = {
                "order_id": order_id,
                "symbol": order_data.get("symbol", ""),
                "side": order_data.get("side", ""),
                "quantity": self._safe_decimal(order_data.get("quantity", "0")),
                "price": self._safe_decimal(order_data.get("price", "0")),
                "status": order_data.get("status", ""),
                "timestamp": datetime.utcnow(),
            }
            
            # 只保留最近100个订单
            if len(self._recent_orders) > 100:
                # 删除最旧的订单
                oldest_order_id = min(
                    self._recent_orders.keys(),
                    key=lambda k: self._recent_orders[k]["timestamp"]
                )
                del self._recent_orders[oldest_order_id]
                
        except Exception as e:
            logger.debug(f"Failed to record order for transfer analysis: {e}")
    
    def _record_trade_for_transfer_analysis(self, trade_data: Dict[str, Any]) -> None:
        """记录成交信息用于划转分析."""
        try:
            # 提取成交ID和时间
            trade_id = trade_data.get("tradeId") or trade_data.get("trade_id")
            if not trade_id:
                return
            
            # 记录成交信息（保留最近100个成交）
            self._recent_trades[trade_id] = {
                "trade_id": trade_id,
                "order_id": trade_data.get("orderId") or trade_data.get("order_id", ""),
                "symbol": trade_data.get("symbol", ""),
                "side": trade_data.get("side", ""),
                "quantity": self._safe_decimal(trade_data.get("quantity", "0")),
                "price": self._safe_decimal(trade_data.get("price", "0")),
                "quote_quantity": self._safe_decimal(trade_data.get("quoteQuantity") or trade_data.get("quote_quantity", "0")),
                "timestamp": datetime.utcnow(),
            }
            
            # 只保留最近100个成交
            if len(self._recent_trades) > 100:
                # 删除最旧的成交
                oldest_trade_id = min(
                    self._recent_trades.keys(),
                    key=lambda k: self._recent_trades[k]["timestamp"]
                )
                del self._recent_trades[oldest_trade_id]
                
        except Exception as e:
            logger.debug(f"Failed to record trade for transfer analysis: {e}")
    
    async def _get_latest_balance_from_db(self, currency: str) -> Optional[Dict[str, Decimal]]:
        """从数据库获取指定币种的最新余额记录."""
        try:
            from sqlalchemy import select, func
            
            async with self.db_manager.session() as session:
                # 查询该币种的最新记录（按update_time降序）
                currency_key = currency.lower()
                AccountUpdateModel = self._get_model('XTAccountUpdate')
                stmt = (
                    select(AccountUpdateModel)
                    .where(AccountUpdateModel.currency == currency_key)
                    .order_by(AccountUpdateModel.update_time.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                latest_record = result.scalar_one_or_none()
                
                if latest_record:
                    return {
                        "available": Decimal(str(latest_record.available)),
                        "frozen": Decimal(str(latest_record.frozen)),
                        "total": Decimal(str(latest_record.total)),
                        "update_time": latest_record.update_time,
                    }
                return None
        except Exception as e:
            logger.debug(f"Failed to get latest balance from DB for {currency}: {e}")
            return None
    
    async def _get_latest_spot_balance_from_db(self, currency: str) -> Optional[Dict[str, Decimal]]:
        """从数据库获取指定币种的最新现货余额快照."""
        try:
            from sqlalchemy import select
            
            async with self.db_manager.session() as session:
                stmt = (
                    select(XTSpotUpdate)
                    .where(XTSpotUpdate.currency == currency.lower())
                    .order_by(XTSpotUpdate.update_time.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                latest_record = result.scalar_one_or_none()
                
                if latest_record:
                    return {
                        "available": Decimal(str(latest_record.available)),
                        "frozen": Decimal(str(latest_record.frozen)),
                        "total": Decimal(str(latest_record.total)),
                        "update_time": latest_record.update_time,
                    }
                return None
        except Exception as e:
            logger.debug(f"Failed to get latest spot balance from DB for {currency}: {e}")
            return None
    
    async def _save_spot_balance_snapshot(self, spot_balances: Dict[str, Dict[str, Any]]) -> None:
        """保存现货账户余额快照到数据库."""
        if not spot_balances:
            return
        
        # 确保账号特定的表已创建（如果是新账号）
        await self._ensure_account_tables_if_needed()
        
        snapshot_time = datetime.utcnow()
        normalized_balances: Dict[str, Dict[str, str]] = {}
        
        for currency, data in spot_balances.items():
            try:
                if currency.upper() not in self._supported_transfer_currencies:
                    continue
                normalized_balances[currency] = {
                    "available": str(self._safe_decimal(data.get("available", "0"))),
                    "frozen": str(self._safe_decimal(data.get("frozen", "0"))),
                    "total": str(self._safe_decimal(data.get("total", "0"))),
                }
            except Exception as e:
                logger.debug(
                    "Failed to normalize spot balance data",
                    extra={"currency": currency, "error": str(e)}
                )
                continue
        
        if not normalized_balances:
            return
        
        raw_payload = json.dumps(normalized_balances, cls=DecimalEncoder)
        records = []
        for currency, values in normalized_balances.items():
            records.append(
                {
                    "update_time": snapshot_time,
                    "account_id": self.account_id,
                    "currency": currency.lower(),
                    "available": self._safe_decimal(values["available"]),
                    "frozen": self._safe_decimal(values["frozen"]),
                    "total": self._safe_decimal(values["total"]),
                    "raw_data": raw_payload,
                }
            )
        
        if not records:
            return
        
        try:
            SpotUpdateModel = self._get_model('XTSpotUpdate')
            async with self.db_manager.session() as session:
                for payload in records:
                    session.add(SpotUpdateModel(**payload))
                await session.commit()
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg or "UndefinedTableError" in error_msg:
                logger.error(
                    "数据库表 xt_spot_updates 不存在。请运行以下命令创建表：",
                    extra={"command": "cextools subscribe user-stream -x xt -c account --create-tables"}
                )
                try:
                    logger.info("尝试自动创建缺失的 XT WebSocket 数据库表...")
                    from tri_arb.storage.xt_websocket_models import Base as XTWebSocketBase
                    async with self.db_manager.async_engine.begin() as conn:
                        await conn.run_sync(lambda sync_conn: XTWebSocketBase.metadata.create_all(sync_conn, checkfirst=True))
                    logger.info("XT WebSocket 数据库表创建成功，重试保存现货余额快照...")
                    async with self.db_manager.session() as session:
                        for payload in records:
                            session.add(XTSpotUpdate(**payload))
                        await session.commit()
                except Exception as create_error:
                    logger.error(f"自动创建现货余额快照表失败: {create_error}")
            else:
                logger.error(f"Failed to save spot balance snapshot: {e}")
    
    async def _check_recent_trade_activity(self, currency: str, time_threshold: datetime) -> tuple[Optional[str], Optional[str], bool]:
        """检查最近的交易活动（使用REST API查询成交记录）.
        
        注意：如果只订阅account频道，订单和成交数据不会插入到数据库，
        因此需要使用REST API查询最近的成交记录。
        
        Returns:
            (related_trade_id, related_order_id, is_trade): 如果检测到交易活动，返回相关信息
        """
        try:
            if not self.rest_client:
                logger.debug("REST client not available, skipping trade activity check")
                return None, None, False
            
            # 1. 检查内存中的最近成交记录（快速检查）
            for trade_id, trade_info in self._recent_trades.items():
                if trade_info["timestamp"] >= time_threshold:
                    symbol = trade_info.get("symbol", "")
                    # 解析交易对，检查是否影响该币种
                    if self._trade_affects_currency(symbol, currency, trade_info):
                        return trade_id, trade_info.get("order_id"), True
            
            # 2. 使用REST API查询最近的成交记录（30秒内）
            try:
                # 计算时间戳（毫秒）
                start_time_ms = int(time_threshold.timestamp() * 1000)
                end_time_ms = int(datetime.utcnow().timestamp() * 1000)
                
                logger.debug(
                    f"Querying recent trades via REST API for {currency}",
                    extra={
                        "currency": currency,
                        "start_time_ms": start_time_ms,
                        "end_time_ms": end_time_ms,
                        "time_window_seconds": (end_time_ms - start_time_ms) / 1000,
                    }
                )
                
                # 查询最近的成交记录（最多查询50条）
                recent_trades = await self.rest_client.get_user_trades(
                    symbol=None,  # 查询所有交易对
                    start_time=start_time_ms,
                    end_time=end_time_ms,
                    limit=50
                )
                
                logger.debug(
                    f"Retrieved {len(recent_trades)} recent trades",
                    extra={
                        "currency": currency,
                        "trade_count": len(recent_trades),
                        "first_trade_sample": recent_trades[0] if recent_trades else None,
                    }
                )
                
                # 检查成交是否影响该币种余额
                for trade in recent_trades:
                    symbol = trade.get("symbol", "")
                    if not symbol:
                        continue
                    
                    # 解析成交数据
                    trade_info = {
                        "quantity": self._safe_decimal(trade.get("quantity", "0")),
                        "price": self._safe_decimal(trade.get("price", "0")),
                        "quote_quantity": self._safe_decimal(trade.get("quoteQuantity") or trade.get("quote_quantity") or trade.get("quoteQty", "0")),
                    }
                    
                    affects = self._trade_affects_currency(symbol, currency, trade_info)
                    logger.debug(
                        f"Checking if trade affects {currency}",
                        extra={
                            "currency": currency,
                            "symbol": symbol,
                            "quantity": str(trade_info["quantity"]),
                            "price": str(trade_info["price"]),
                            "quote_quantity": str(trade_info["quote_quantity"]),
                            "affects": affects,
                        }
                    )
                    
                    if affects:
                        trade_id = trade.get("tradeId") or trade.get("trade_id", "")
                        order_id = trade.get("orderId") or trade.get("order_id", "")
                        logger.info(
                            f"Found matching trade for {currency}",
                            extra={
                                "currency": currency,
                                "symbol": symbol,
                                "trade_id": trade_id,
                                "order_id": order_id,
                            }
                        )
                        return str(trade_id), str(order_id) if order_id else None, True
                        
            except Exception as e:
                logger.warning(f"Failed to query recent trades via REST API: {e}", exc_info=True)
            
            return None, None, False
            
        except Exception as e:
            logger.debug(f"Failed to check recent trade activity for {currency}: {e}")
            return None, None, False
    
    def _trade_affects_currency(self, symbol: str, currency: str, trade_info: Dict[str, Any]) -> bool:
        """判断交易是否影响指定币种的余额."""
        try:
            currency_upper = currency.upper()
            symbol_upper = symbol.upper()
            
            # 解析交易对（格式：BTC_USDT, ETH_USDT等）
            if "_" in symbol_upper:
                base, quote = symbol_upper.split("_", 1)
                
                # 如果是USDT交易对，且币种是USDT，检查成交金额
                if quote == "USDT" and currency_upper == "USDT":
                    quote_quantity = trade_info.get("quote_quantity", Decimal("0"))
                    if quote_quantity and quote_quantity > Decimal("0.0001"):  # 最小阈值
                        return True
                
                # 如果是base currency，检查成交数量
                if base == currency_upper:
                    quantity = trade_info.get("quantity", Decimal("0"))
                    if quantity and quantity > Decimal("0.00000001"):  # 最小阈值
                        return True
                
                # 如果是quote currency，检查成交金额
                if quote == currency_upper:
                    quote_quantity = trade_info.get("quote_quantity", Decimal("0"))
                    if quote_quantity and quote_quantity > Decimal("0.0001"):  # 最小阈值
                        return True
            
            return False
        except Exception as e:
            logger.debug(f"Failed to check if trade affects currency: {e}")
            return False
    
    def _position_affects_currency(self, symbol: str, currency: str) -> bool:
        """判断持仓变化是否影响指定币种的余额（平仓会导致余额变化）."""
        try:
            currency_upper = currency.upper()
            symbol_upper = symbol.upper()
            
            # 解析交易对（格式：BTC_USDT, ETH_USDT等）
            if "_" in symbol_upper:
                base, quote = symbol_upper.split("_", 1)
                
                # 持仓变化（特别是平仓）会影响quote currency（通常是USDT）的余额
                if quote == currency_upper or base == currency_upper:
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"Failed to check if position affects currency: {e}")
            return False
    
    async def _check_balance_changes_across_accounts(self, currency: str, balance_change: Decimal) -> tuple[Optional[str], Optional[str], bool]:
        """通过查询现货和合约账户余额变化来判断是划转还是交易.
        
        策略：
        1. 如果合约账户余额增加，现货账户余额减少，且金额相等，可能是从现货划转到合约
        2. 如果现货账户余额增加，合约账户余额减少，且金额相等，可能是从合约划转到现货
        3. 如果余额变化与成交记录匹配，则是交易导致的
        
        Returns:
            (related_trade_id, related_order_id, is_trade): 如果检测到交易活动，返回相关信息
        """
        try:
            if currency.upper() not in self._supported_transfer_currencies:
                logger.debug(
                    "Skipping transfer analysis for unsupported currency",
                    extra={"currency": currency}
                )
                return None, None, True

            if not self.rest_client or not self.spot_client:
                logger.debug("REST clients not available, skipping balance change analysis")
                return None, None, False
            
            # 确保交易所已连接
            if not self.rest_client.is_connected:
                await self.rest_client.connect()
            if not self.spot_client.is_connected:
                await self.spot_client.connect()
            
            # 1. 查询现货账户余额（并获取数据库中的上一条记录）
            previous_spot_record = await self._get_latest_spot_balance_from_db(currency)
            spot_balances: Dict[str, Dict[str, Any]] = {}
            try:
                spot_balances = await self.spot_client.get_balance()
                spot_balance = spot_balances.get(currency.upper(), {})
                spot_total = self._safe_decimal(spot_balance.get("total", "0"))
                await self._save_spot_balance_snapshot(spot_balances)
            except Exception as e:
                logger.debug(f"Failed to get spot balance for {currency}: {e}")
                spot_total = None
            
            # 2. 查询合约账户余额
            try:
                perp_balances = await self.rest_client.get_balance()
                perp_balance = perp_balances.get(currency.upper(), {})
                perp_total = self._safe_decimal(perp_balance.get("total", "0"))
            except Exception as e:
                logger.debug(f"Failed to get perp balance for {currency}: {e}")
                perp_total = None
            
            # 3. 从内存缓存获取上次的余额记录
            currency_key = currency.lower()
            last_perp_balance = self._last_account_balances.get(currency_key)
            
            # 如果内存缓存中没有记录，尝试从数据库获取
            if last_perp_balance is None:
                last_perp_balance_record = await self._get_latest_balance_from_db(currency)
                if last_perp_balance_record:
                    last_perp_balance = last_perp_balance_record
                elif perp_total is not None:
                    # 首次记录，使用当前余额作为基准
                    last_perp_balance = {"total": perp_total}
            
            # 现货账户余额需要单独缓存
            spot_cache_key = f"{currency_key}_spot"
            last_spot_balance = self._last_spot_balances.get(spot_cache_key)
            if last_spot_balance is None and spot_total is not None:
                # 首次记录，使用当前余额作为基准
                self._last_spot_balances[spot_cache_key] = {"total": spot_total}
                last_spot_balance = {"total": spot_total}
            
            # 4. 计算余额变化
            spot_change = None
            perp_change = None
            if spot_total is not None:
                if previous_spot_record:
                    spot_change = spot_total - previous_spot_record.get("total", Decimal("0"))
                elif last_spot_balance:
                    spot_change = spot_total - last_spot_balance.get("total", Decimal("0"))
            if perp_total is not None and last_perp_balance:
                perp_change = perp_total - last_perp_balance.get("total", Decimal("0"))
            
            logger.info(
                f"Balance changes across accounts for {currency}",
                extra={
                    "currency": currency,
                    "spot_total": str(spot_total) if spot_total is not None else None,
                    "perp_total": str(perp_total) if perp_total is not None else None,
                    "spot_change": str(spot_change) if spot_change is not None else None,
                    "perp_change": str(perp_change) if perp_change is not None else None,
                    "account_balance_change": str(balance_change),
                }
            )
            
            transfer_detected = False
            tolerance = Decimal("0.01")

            if spot_change is not None and perp_change is not None:
                if balance_change > 0 and spot_change < 0 and abs(balance_change + spot_change) <= tolerance:
                    transfer_detected = True
                elif balance_change < 0 and spot_change > 0 and abs(balance_change + spot_change) <= tolerance:
                    transfer_detected = True
                elif abs(perp_change - balance_change) <= tolerance and abs(spot_change) <= tolerance:
                    transfer_detected = True
            elif spot_change is not None:
                if balance_change > 0 and spot_change < 0 and abs(balance_change + spot_change) <= tolerance:
                    transfer_detected = True
                elif balance_change < 0 and spot_change > 0 and abs(balance_change + spot_change) <= tolerance:
                    transfer_detected = True
            elif perp_change is not None and abs(perp_change - balance_change) <= tolerance and abs(balance_change) > tolerance:
                transfer_detected = True

            if spot_total is not None:
                self._last_spot_balances[spot_cache_key] = {"total": spot_total}
            if perp_total is not None:
                self._last_account_balances[currency_key] = {"total": perp_total}

            if transfer_detected:
                logger.info(
                    "Detected transfer via balance comparison",
                    extra={
                        "currency": currency,
                        "balance_change": str(balance_change),
                        "spot_change": str(spot_change),
                        "perp_change": str(perp_change),
                    }
                )
                return None, None, False

            logger.debug(
                "Balance change treated as trade",
                extra={
                    "currency": currency,
                    "balance_change": str(balance_change),
                }
            )
            return None, None, True
            
        except Exception as e:
            logger.warning(f"Failed to check balance changes across accounts: {e}", exc_info=True)
            return None, None, False
    
    async def _analyze_transfer(self, account_data: Dict[str, Any]) -> None:
        """分析账户余额变化，识别资金划转.
        
        从数据库中获取最新的余额记录作为基准，与当前WebSocket推送的余额进行对比。
        这样可以避免服务重启后丢失缓存，以及数据同步时的余额不准确问题。
        """
        try:
            transfer_time = datetime.utcnow()
            
            # 提取当前余额信息
            current_balances = {}
            if "coin" in account_data:
                # 单个余额对象
                currency = account_data.get("coin", "")
                if currency:
                    if currency.upper() not in self._supported_transfer_currencies:
                        logger.debug(
                            "Skipping balance change analysis for unsupported currency",
                            extra={"currency": currency}
                        )
                        return
                    current_balances[currency] = {
                        "available": self._safe_decimal(account_data.get("availableBalance", "0")),
                        "frozen": self._safe_decimal(account_data.get("openOrderMarginFrozen", "0")),
                        "total": self._safe_decimal(account_data.get("walletBalance", "0")),
                    }
            else:
                # 多个余额对象
                balances = account_data.get("balances", [])
                for balance in balances:
                    currency = balance.get("currency", "")
                    if currency:
                        if currency.upper() not in self._supported_transfer_currencies:
                            logger.debug(
                                "Skipping balance change analysis for unsupported currency",
                                extra={"currency": currency}
                            )
                            continue
                        current_balances[currency] = {
                            "available": self._safe_decimal(balance.get("available", "0")),
                            "frozen": self._safe_decimal(balance.get("frozen", "0")),
                            "total": self._safe_decimal(balance.get("total", "0")) or 
                                    (self._safe_decimal(balance.get("available", "0")) + 
                                     self._safe_decimal(balance.get("frozen", "0"))),
                        }
            
            # 比较余额变化（从数据库获取最新记录作为基准）
            for currency, current_balance in current_balances.items():
                # 统一使用小写币种名
                currency_key = currency.lower()
                current_total = current_balance["total"]
                
                # 从数据库获取最新的余额记录
                last_balance_record = await self._get_latest_balance_from_db(currency)
                
                if last_balance_record is None:
                    # 数据库中没有记录，跳过划转检测（不插入和输出划转记录）
                    logger.debug(
                        f"数据库无 {currency} 余额记录，跳过划转检测",
                        extra={
                            "currency": currency,
                            "total": str(current_total),
                        }
                    )
                    # 更新内存缓存（用于后续快速查询）
                    self._last_account_balances[currency_key] = current_balance
                    continue
                
                last_total = last_balance_record["total"]
                last_update_time = last_balance_record.get("update_time")
                balance_change = current_total - last_total
                
                # 如果当前余额与数据库最新记录相同，跳过（可能是重复推送）
                if abs(balance_change) < Decimal("0.00000001"):
                    logger.debug(
                        f"余额无变化: {currency}",
                        extra={
                            "currency": currency,
                            "total": str(current_total),
                        }
                    )
                    # 更新内存缓存
                    self._last_account_balances[currency_key] = current_balance
                    continue
                
                logger.info(
                    f"余额变化检测: {currency}",
                    extra={
                        "currency": currency,
                        "last_total": str(last_total),
                        "last_update_time": last_update_time.isoformat() if last_update_time else None,
                        "current_total": str(current_total),
                        "balance_change": str(balance_change),
                    }
                )
                
                # 通过查询现货和合约账户余额变化来判断是划转还是交易
                related_trade_id, related_order_id, is_trade = await self._check_balance_changes_across_accounts(currency, balance_change)
                
                # 判断划转类型
                if is_trade:
                    transfer_type = "TRADE"  # 由交易引起的余额变化（包括平仓）
                else:
                    # 如果没有找到对应的交易活动，则可能是资金划转
                    if balance_change > 0:
                        transfer_type = "DEPOSIT"  # 充值或转入
                    else:
                        transfer_type = "WITHDRAW"  # 提现或转出
                
                if transfer_type != "TRADE":
                    # 保存划转记录（仅限真实划转）
                    await self._save_transfer(
                        transfer_time=transfer_time,
                        currency=currency,
                        amount=balance_change,
                        transfer_type=transfer_type,
                        balance_before=last_total,
                        balance_after=current_total,
                        related_order_id=related_order_id,
                        related_trade_id=related_trade_id,
                        raw_data=account_data,
                    )

                    # 显示划转信息
                    if self.display_format != "none":
                        await self._display_transfer(
                            currency=currency,
                            amount=balance_change,
                            transfer_type=transfer_type,
                            balance_before=last_total,
                            balance_after=current_total,
                        )
                else:
                    logger.debug(
                        "Balance change attributed to trade; skipping transfer record",
                        extra={
                            "currency": currency,
                            "balance_change": str(balance_change),
                            "related_order_id": related_order_id,
                            "related_trade_id": related_trade_id,
                        }
                    )
                
                # 更新缓存的余额（使用小写币种名）
                self._last_account_balances[currency_key] = current_balance
                
                logger.info(
                    f"检测到余额变化: {currency}",
                    extra={
                        "currency": currency,
                        "amount": str(balance_change),
                        "transfer_type": transfer_type,
                        "balance_before": str(last_total),
                        "balance_after": str(current_total),
                    }
                )
                
        except Exception as e:
            logger.error(f"Failed to analyze transfer: {e}", exc_info=True)
    
    async def _save_transfer(
        self,
        transfer_time: datetime,
        currency: str,
        amount: Decimal,
        transfer_type: str,
        balance_before: Decimal,
        balance_after: Decimal,
        related_order_id: Optional[str] = None,
        related_trade_id: Optional[str] = None,
        raw_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """保存资金划转记录到数据库."""
        try:
            # 确保账号特定的表已创建（如果是新账号）
            await self._ensure_account_tables_if_needed()
            
            async with self.db_manager.session() as session:
                TransferModel = self._get_model('XTTransfer')
                transfer_record = TransferModel(
                    transfer_time=transfer_time,
                    account_id=self.account_id,
                    currency=currency,
                    amount=amount,
                    transfer_type=transfer_type,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    related_order_id=related_order_id,
                    related_trade_id=related_trade_id,
                    raw_data=json.dumps(raw_data, cls=DecimalEncoder) if raw_data else None,
                )
                session.add(transfer_record)
                await session.commit()
                logger.info(
                    f"Transfer recorded: {currency} {amount:+.8f} ({transfer_type})",
                    extra={
                        "currency": currency,
                        "amount": str(amount),
                        "transfer_type": transfer_type,
                    }
                )
                logger.info("Successfully saved transfer to database")
        except Exception as e:
            error_msg = str(e)
            # 检查是否是表不存在的错误
            if "does not exist" in error_msg or "UndefinedTableError" in error_msg:
                logger.error(
                    "数据库表 xt_transfers 不存在。请运行以下命令创建表：",
                    extra={"command": "cextools subscribe user-stream -x xt -c account --create-tables"}
                )
                logger.error(
                    "或者手动创建表：",
                    extra={"error": error_msg}
                )
                # 尝试自动创建 XT WebSocket 表（只创建 XT 相关的表）
                try:
                    logger.info("尝试自动创建缺失的 XT WebSocket 数据库表...")
                    # 只创建 XT WebSocket 相关的表，避免与其他表的索引冲突
                    from tri_arb.storage.xt_websocket_models import Base as XTWebSocketBase
                    async with self.db_manager.async_engine.begin() as conn:
                        # 使用 checkfirst=True 避免重复创建已存在的表/索引
                        await conn.run_sync(lambda sync_conn: XTWebSocketBase.metadata.create_all(sync_conn, checkfirst=True))
                    logger.info("XT WebSocket 数据库表创建成功，重试保存划转记录...")
                    # 重试保存
                    TransferModel = self._get_model('XTTransfer')
                    async with self.db_manager.session() as session:
                        transfer_record = TransferModel(
                            transfer_time=transfer_time,
                            account_id=self.account_id,
                            currency=currency,
                            amount=amount,
                            transfer_type=transfer_type,
                            balance_before=balance_before,
                            balance_after=balance_after,
                            related_order_id=related_order_id,
                            related_trade_id=related_trade_id,
                            raw_data=json.dumps(raw_data, cls=DecimalEncoder) if raw_data else None,
                        )
                        session.add(transfer_record)
                        await session.commit()
                        logger.info(
                            f"Transfer recorded (after auto-create): {currency} {amount:+.8f} ({transfer_type})",
                            extra={
                                "currency": currency,
                                "amount": str(amount),
                                "transfer_type": transfer_type,
                            }
                        )
                        logger.info("Successfully saved transfer to database")
                except Exception as create_error:
                    error_msg = str(create_error)
                    # 如果是表/索引已存在的错误，尝试直接保存（表可能已经存在）
                    if "already exists" in error_msg or "DuplicateTableError" in error_msg:
                        logger.debug(
                            "表或索引已存在，尝试直接保存划转记录...",
                            extra={"error": error_msg[:200]}
                        )
                        try:
                            # 直接尝试保存，可能表已经存在了
                            async with self.db_manager.session() as session:
                                transfer_record = XTTransfer(
                                    transfer_time=transfer_time,
                                    currency=currency,
                                    amount=amount,
                                    transfer_type=transfer_type,
                                    balance_before=balance_before,
                                    balance_after=balance_after,
                                    related_order_id=related_order_id,
                                    related_trade_id=related_trade_id,
                                    raw_data=json.dumps(raw_data, cls=DecimalEncoder) if raw_data else None,
                                )
                                session.add(transfer_record)
                                await session.commit()
                                logger.info(
                                    f"Transfer recorded: {currency} {amount:+.8f} ({transfer_type})",
                                    extra={
                                        "currency": currency,
                                        "amount": str(amount),
                                        "transfer_type": transfer_type,
                                    }
                                )
                                logger.info("Successfully saved transfer to database")
                        except Exception as save_error:
                            logger.error(f"保存划转记录失败: {save_error}")
                    else:
                        logger.error(f"自动创建表失败: {create_error}")
            else:
                logger.error(f"Failed to save transfer: {e}")
    
    async def _display_transfer(
        self,
        currency: str,
        amount: Decimal,
        transfer_type: str,
        balance_before: Decimal,
        balance_after: Decimal,
    ) -> None:
        """显示资金划转信息."""
        try:
            if self.display_format == "json":
                transfer_info = {
                    "currency": currency,
                    "amount": str(amount),
                    "transfer_type": transfer_type,
                    "balance_before": str(balance_before),
                    "balance_after": str(balance_after),
                }
                print(json.dumps(transfer_info, indent=2, ensure_ascii=False))
            else:
                # 表格格式显示
                from rich.console import Console
                from rich.table import Table
                
                console = Console()
                account_label = f"{self.account_id} ({self.account_name})" if self.account_name else (self.account_id or "默认账号")
                table = Table(title=f"💰 资金划转 - {account_label}", show_header=True, header_style="bold magenta")
                
                table.add_column("币种", style="cyan")
                table.add_column("划转金额", justify="right")
                table.add_column("类型", style="yellow")
                table.add_column("划转前余额", justify="right", style="dim")
                table.add_column("划转后余额", justify="right", style="green")
                
                # 格式化金额显示
                amount_str = f"{amount:+.8f}"
                amount_style = "green" if amount > 0 else "red"
                
                # 类型显示
                type_map = {
                    "DEPOSIT": "充值/转入",
                    "WITHDRAW": "提现/转出",
                    "TRADE": "交易",
                    "UNKNOWN": "未知",
                }
                type_display = type_map.get(transfer_type, transfer_type)
                
                table.add_row(
                    currency,
                    f"[{amount_style}]{amount_str}[/{amount_style}]",
                    type_display,
                    f"{balance_before:.8f}",
                    f"{balance_after:.8f}",
                )
                
                console.print(table)
                
        except Exception as e:
            logger.error(f"Failed to display transfer: {e}")
