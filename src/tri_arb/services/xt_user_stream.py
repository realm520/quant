"""XT WebSocket user data stream service.

Handles XT WebSocket connections for real-time account updates, position updates,
order updates, and trade updates with automatic reconnection and data synchronization.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_websocket_models import (
    XTAccountUpdate,
    XTOrderUpdate,
    XTPositionUpdate,
    XTTradeUpdate,
    XTWebSocketConnection,
)
from tri_arb.exchanges.xt_perp import XTPerpExchange

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
        
        # 默认启用所有频道
        self.enabled_channels = enabled_channels or {"account", "position", "order", "trade"}
        
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

        # XT REST API客户端（用于数据同步，默认使用永续合约）
        self.rest_client = None

        # XT WebSocket认证
        self.listen_key = None

        # 数据缓存（用于检测变化）
        self._last_account_data = {}
        self._last_position_data = {}
        self._last_order_data = {}
        self._last_trade_data = {}
        
        logger.info("XT WebSocket service initialized")
    
    async def start(self) -> None:
        """启动WebSocket服务."""
        if self.is_running:
            logger.warning("XT WebSocket service is already running")
            return
        
        self.is_running = True
        self.connection_id = str(uuid.uuid4())
        
        # 初始化REST客户端用于数据同步（如果启用）
        if self.enable_data_sync:
            self.rest_client = XTPerpExchange(self.api_key, self.api_secret)
            await self.rest_client.connect()
            logger.info("REST API client initialized for data synchronization")
        
        # 记录连接开始
        await self._record_connection_start()
        
        logger.info("Starting XT WebSocket service")
        
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
        
        # 清理资源
        if self.rest_client and self.enable_data_sync:
            await self.rest_client.disconnect()
        
        logger.info("XT WebSocket service stopped")
    
    async def stop(self) -> None:
        """停止WebSocket服务."""
        logger.info("Stopping XT WebSocket service")
        self.is_running = False
        
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        
        self.is_connected = False
    
    async def _connect_and_listen(self) -> None:
        """建立WebSocket连接并监听消息."""
        # XT WebSocket URL (根据官方文档)
        ws_url = "wss://fstream.xt.com/ws/user"
        
        try:
            logger.info("Connecting to XT WebSocket")
            
            # 建立WebSocket连接，添加必需的请求头
            self.websocket = await websockets.connect(ws_url)
            self.is_connected = True
            self.reconnect_attempts = 0
            
            logger.info("Connected to XT WebSocket")
            
            # 暂时跳过listenKey获取，直接尝试订阅
            # await self._get_listen_key()
            
            # 订阅用户数据流
            await self._subscribe_user_data()
            
            # 记录重连时间
            self.reconnect_time = datetime.utcnow()
            logger.info("Recorded reconnect time")
            
            # 显示测试数据以验证表格功能
            await self._display_test_data()

            # 连接成功后立即进行数据同步（如果启用）
            if self.enable_data_sync:
                logger.info("Performing initial data synchronization after reconnection")

                # 如果有断线时间记录，说明是重连，需要补充断线期间的数据
                if self.disconnect_time:
                    disconnect_duration = (self.reconnect_time - self.disconnect_time).total_seconds()
                    logger.info(
                        "Reconnected after disconnection, will sync missing data",
                        disconnect_duration=disconnect_duration
                    )

                # 补充断线期间的缺失数据
                await self._sync_missing_data()
            
            # 监听消息
            logger.info("Starting WebSocket message loop")
            message_count = 0
            last_test_display = datetime.utcnow()
            
            async for message in self.websocket:
                logger.debug("Received WebSocket message", message_length=len(message))
                await self._handle_message(message)
                message_count += 1

                # 如果没有收到消息，每30秒显示一次测试数据
                if message_count == 0 and (datetime.utcnow() - last_test_display).seconds > 30:
                    await self._display_test_data()
                    last_test_display = datetime.utcnow()
                
        except ConnectionClosed:
            logger.warning("XT WebSocket connection closed")
            self.is_connected = False
            # 记录断线时间
            self.disconnect_time = datetime.utcnow()
            logger.info("Recorded disconnect time")
        except WebSocketException as e:
            logger.error(f"XT WebSocket error: {e}")
            self.is_connected = False
            # 记录断线时间
            self.disconnect_time = datetime.utcnow()
            logger.info("Recorded disconnect time")
        except Exception as e:
            logger.error(f"Unexpected error in WebSocket connection: {e}")
            self.is_connected = False
            # 记录断线时间
            self.disconnect_time = datetime.utcnow()
            logger.info("Recorded disconnect time")
    
    async def _get_listen_key(self) -> None:
        """获取XT WebSocket listenKey."""
        if not self.rest_client:
            logger.error("REST client not initialized, cannot get listen key")
            return
        
        try:
            # 调用XT API获取listenKey
            path = "/v1/user/listen-key"
            data = await self.rest_client._request("POST", path, params=None, body=None, require_auth=True)
            
            self.listen_key = data.get("listenKey")
            if self.listen_key:
                logger.info("Successfully obtained listen key")
            else:
                logger.error("Failed to get listen key from API response")
                
        except Exception as e:
            logger.error(f"Failed to get listen key: {e}")
            raise
    
    async def _subscribe_user_data(self) -> None:
        """订阅用户数据流."""
        # 构建订阅参数列表
        params = []
        
        # 根据启用的频道添加订阅，使用正确的格式：channel@{listenKey}
        if "account" in self.enabled_channels:
            params.append("balance@test")  # 暂时使用test作为listenKey
        
        if "position" in self.enabled_channels:
            params.append("position@test")
        
        if "order" in self.enabled_channels:
            params.append("order@test")
        
        if "trade" in self.enabled_channels:
            params.append("trade@test")
        
        if not params:
            logger.warning("No channels enabled for subscription")
            return
        
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": params,
            "id": "xt_user_stream_1"
        }
        
        await self.websocket.send(json.dumps(subscribe_message))
        logger.info("Subscribed to XT user data channels")
    
    async def _handle_message(self, message: str) -> None:
        """处理WebSocket消息."""
        try:
            data = json.loads(message)
            
            # 更新消息统计
            await self._update_message_stats()
            
            # XT WebSocket消息格式处理
            # 检查是否是订阅确认消息
            if "result" in data and data.get("id") == "xt_user_stream_1":
                logger.info("Subscription confirmed", result=data.get("result"))
                return
            
            # 检查是否是错误消息
            if "error" in data:
                error_code = data.get("error", {}).get("code")
                error_msg = data.get("error", {}).get("message", "")
                
                if error_code == "invalid_listen_key":
                    logger.error("Listen key expired or invalid, need to refresh", error=error_msg)
                    await self._get_listen_key()
                    await self._subscribe_user_data()
                    return
                else:
                    logger.error("WebSocket error")
                    return
            
            # 处理数据推送消息
            stream = data.get("stream", "")
            if "@" in stream:
                channel = stream.split("@")[0]
                listen_key = stream.split("@")[1]
                
                # 暂时跳过listenKey验证，因为我们现在使用test
                logger.info("Received WebSocket message", channel=channel, stream=stream)
                
                # 根据频道类型处理数据
                if channel == "balance":
                    await self._handle_account_update(data)
                elif channel == "position":
                    await self._handle_position_update(data)
                elif channel == "order":
                    await self._handle_order_update(data)
                elif channel == "trade":
                    await self._handle_trade_update(data)
                else:
                    logger.debug("Unknown channel")
            else:
                logger.debug("Unknown message format")
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    async def _handle_account_update(self, data: Dict[str, Any]) -> None:
        """处理账户更新消息."""
        if "account" not in self.enabled_channels:
            return
        
        # 提取XT账户数据
        account_data = data.get("data", {})
        if not account_data:
            logger.warning("No account data in message")
            return
        
        # 检查数据是否有变化
        if not self._has_account_changed(account_data):
            return
        
        try:
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
            # 显示持仓更新
            await self._display_position_update(position_data)
            
            # 保存到数据库
            await self._save_position_update(position_data)
            
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
            # 显示订单更新
            await self._display_order_update(order_data)
            
            # 保存到数据库
            await self._save_order_update(order_data)
            
            # 更新统计
            await self._update_order_stats()
            
        except Exception as e:
            logger.error(f"Error handling order update: {e}")
    
    async def _handle_trade_update(self, data: Dict[str, Any]) -> None:
        """处理成交更新消息."""
        if "trade" not in self.enabled_channels:
            return
        
        # 提取XT成交数据
        trade_data = data.get("data", {})
        if not trade_data:
            logger.warning("No trade data in message")
            return
        
        # 检查数据是否有变化
        if not self._has_trade_changed(trade_data):
            return
        
        try:
            # 显示成交更新
            await self._display_trade_update(trade_data)
            
            # 保存到数据库
            await self._save_trade_update(trade_data)
            
            # 更新统计
            await self._update_trade_stats()
            
        except Exception as e:
            logger.error(f"Error handling trade update: {e}")
    
    async def _display_account_update(self, data: Dict[str, Any]) -> None:
        """显示账户更新."""
        if self.display_format == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            # 表格格式显示
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="XT账户更新")
            
            table.add_column("币种", style="cyan")
            table.add_column("可用余额", style="green")
            table.add_column("冻结余额", style="yellow")
            table.add_column("总余额", style="blue")
            table.add_column("更新时间", style="dim")
            
            # 解析账户数据
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
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            # 表格格式显示
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="XT持仓更新")
            
            table.add_column("交易对", style="cyan")
            table.add_column("方向", style="green")
            table.add_column("数量", style="yellow")
            table.add_column("开仓价", style="blue")
            table.add_column("标记价", style="magenta")
            table.add_column("未实现盈亏", style="red")
            table.add_column("杠杆", style="dim")
            
            # 解析持仓数据
            positions = data.get("positions", [])
            for position in positions:
                symbol = position.get("symbol", "")
                side = position.get("side", "")
                quantity = position.get("quantity", "0")
                entry_price = position.get("entry_price", "0")
                mark_price = position.get("mark_price", "0")
                unrealized_pnl = position.get("unrealized_pnl", "0")
                leverage = position.get("leverage", "1")
                
                table.add_row(
                    symbol,
                    side,
                    f"{quantity}",
                    f"{entry_price}",
                    f"{mark_price}",
                    f"{unrealized_pnl}",
                    f"{leverage}x",
                )
            
            console.print(table)
    
    async def _display_order_update(self, data: Dict[str, Any]) -> None:
        """显示订单更新."""
        if self.display_format == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            # 表格格式显示
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="XT订单更新")
            
            table.add_column("订单ID", style="cyan")
            table.add_column("交易对", style="green")
            table.add_column("方向", style="yellow")
            table.add_column("类型", style="blue")
            table.add_column("数量", style="magenta")
            table.add_column("价格", style="red")
            table.add_column("状态", style="dim")
            
            # 解析订单数据
            orders = data.get("orders", [])
            for order in orders:
                order_id = order.get("order_id", "")
                symbol = order.get("symbol", "")
                side = order.get("side", "")
                order_type = order.get("order_type", "")
                quantity = order.get("quantity", "0")
                price = order.get("price", "0")
                status = order.get("status", "")
                
                table.add_row(
                    order_id,
                    symbol,
                    side,
                    order_type,
                    f"{quantity}",
                    f"{price}",
                    status,
                )
            
            console.print(table)
    
    async def _display_trade_update(self, data: Dict[str, Any]) -> None:
        """显示成交更新."""
        if self.display_format == "json":
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            # 表格格式显示
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title="XT成交更新")
            
            table.add_column("成交ID", style="cyan")
            table.add_column("订单ID", style="green")
            table.add_column("交易对", style="yellow")
            table.add_column("方向", style="blue")
            table.add_column("价格", style="magenta")
            table.add_column("数量", style="red")
            table.add_column("金额", style="dim")
            
            # 解析成交数据
            trades = data.get("trades", [])
            for trade in trades:
                trade_id = trade.get("trade_id", "")
                order_id = trade.get("order_id", "")
                symbol = trade.get("symbol", "")
                side = trade.get("side", "")
                price = trade.get("price", "0")
                quantity = trade.get("quantity", "0")
                quote_quantity = trade.get("quote_quantity", "0")
                
                table.add_row(
                    trade_id,
                    order_id,
                    symbol,
                    side,
                    f"{price}",
                    f"{quantity}",
                    f"{quote_quantity}",
                )
            
            console.print(table)
    
    async def _save_account_update(self, data: Dict[str, Any]) -> None:
        """保存账户更新到数据库."""
        try:
            async with self.db_manager.session() as session:
                balances = data.get("balances", [])
                update_time = datetime.utcnow()
                
                for balance in balances:
                    currency = balance.get("currency", "")
                    if not currency:
                        continue
                    
                    available = self._safe_decimal(balance.get("available", "0"))
                    frozen = self._safe_decimal(balance.get("frozen", "0"))
                    total = available + frozen
                    
                    record = XTAccountUpdate(
                        update_time=update_time,
                        currency=currency,
                        available=available,
                        frozen=frozen,
                        total=total,
                        raw_data=json.dumps(balance),
                    )
                    session.add(record)
                
                await session.commit()
                logger.debug("Saved account update to database")
                
        except Exception as e:
            logger.error(f"Failed to save account update: {e}")
    
    async def _save_position_update(self, data: Dict[str, Any]) -> None:
        """保存持仓更新到数据库."""
        try:
            async with self.db_manager.session() as session:
                positions = data.get("positions", [])
                update_time = datetime.utcnow()
                
                for position in positions:
                    symbol = position.get("symbol", "")
                    if not symbol:
                        continue
                    
                    side = position.get("side", "")
                    quantity = self._safe_decimal(position.get("quantity", "0"))
                    
                    # 跳过持仓量为0的记录
                    if quantity == 0:
                        continue
                    
                    record = XTPositionUpdate(
                        update_time=update_time,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        entry_price=self._safe_decimal(position.get("entry_price", "0")),
                        mark_price=self._safe_decimal(position.get("mark_price", "0")),
                        liquidation_price=self._safe_decimal(position.get("liquidation_price", "0")),
                        unrealized_pnl=self._safe_decimal(position.get("unrealized_pnl", "0")),
                        leverage=self._safe_int(position.get("leverage", "1")),
                        margin=self._safe_decimal(position.get("margin", "0")),
                        roe=self._safe_decimal(position.get("roe", "0")),
                        raw_data=json.dumps(position),
                    )
                    session.add(record)
                
                await session.commit()
                logger.debug("Saved position update to database")
                
        except Exception as e:
            logger.error(f"Failed to save position update: {e}")
    
    async def _save_order_update(self, data: Dict[str, Any]) -> None:
        """保存订单更新到数据库."""
        try:
            async with self.db_manager.session() as session:
                orders = data.get("orders", [])
                update_time = datetime.utcnow()
                
                for order in orders:
                    order_id = order.get("order_id", "")
                    if not order_id:
                        continue
                    
                    symbol = order.get("symbol", "")
                    side = order.get("side", "")
                    order_type = order.get("order_type", "")
                    quantity = self._safe_decimal(order.get("quantity", "0"))
                    price = self._safe_decimal(order.get("price", "0"))
                    filled_quantity = self._safe_decimal(order.get("filled_quantity", "0"))
                    status = order.get("status", "")
                    
                    record = XTOrderUpdate(
                        update_time=update_time,
                        symbol=symbol,
                        order_id=order_id,
                        client_order_id=order.get("client_order_id", ""),
                        side=side,
                        order_type=order_type,
                        position_side=order.get("position_side", ""),
                        quantity=quantity,
                        price=price,
                        filled_quantity=filled_quantity,
                        status=status,
                        time_in_force=order.get("time_in_force", ""),
                        create_time=self._parse_timestamp(order.get("create_time")),
                        update_time_order=self._parse_timestamp(order.get("update_time")),
                        raw_data=json.dumps(order),
                    )
                    session.add(record)
                
                await session.commit()
                logger.debug("Saved order update to database")
                
        except Exception as e:
            logger.error(f"Failed to save order update: {e}")
    
    async def _save_trade_update(self, data: Dict[str, Any]) -> None:
        """保存成交更新到数据库."""
        try:
            async with self.db_manager.session() as session:
                trades = data.get("trades", [])
                update_time = datetime.utcnow()
                
                for trade in trades:
                    trade_id = trade.get("trade_id", "")
                    if not trade_id:
                        continue
                    
                    order_id = trade.get("order_id", "")
                    symbol = trade.get("symbol", "")
                    side = trade.get("side", "")
                    price = self._safe_decimal(trade.get("price", "0"))
                    quantity = self._safe_decimal(trade.get("quantity", "0"))
                    quote_quantity = price * quantity
                    
                    record = XTTradeUpdate(
                        update_time=update_time,
                        symbol=symbol,
                        order_id=order_id,
                        trade_id=trade_id,
                        side=side,
                        price=price,
                        quantity=quantity,
                        quote_quantity=quote_quantity,
                        commission=self._safe_decimal(trade.get("commission", "0")),
                        commission_asset=trade.get("commission_asset", ""),
                        is_maker=trade.get("is_maker", False),
                        position_side=trade.get("position_side", ""),
                        raw_data=json.dumps(trade),
                    )
                    session.add(record)
                
                await session.commit()
                logger.debug("Saved trade update to database")
                
        except Exception as e:
            logger.error(f"Failed to save trade update: {e}")
    
    async def _sync_missing_data(self) -> None:
        """补充断线期间缺失的数据.

        仅在重连后调用，使用断线时间区间查询订单和成交数据。
        账户和持仓数据直接获取最新状态。
        """
        if not self.enable_data_sync or not self.rest_client:
            logger.debug("Data sync is disabled or REST client not available")
            return

        try:
            # 判断是否有断线时间记录
            has_disconnect_period = bool(self.disconnect_time and self.reconnect_time)

            if has_disconnect_period:
                disconnect_duration = (self.reconnect_time - self.disconnect_time).total_seconds()
                logger.info(
                    "Syncing missing data for disconnection period",
                    duration_seconds=disconnect_duration,
                    start=self.disconnect_time.isoformat(),
                    end=self.reconnect_time.isoformat()
                )
            else:
                logger.info("Syncing current state (no disconnection period)")

            # 同步账户余额（总是同步最新状态）
            if "account" in self.enabled_channels:
                await self._sync_account_data()

            # 同步持仓数据（总是同步最新状态）
            if "position" in self.enabled_channels:
                await self._sync_position_data()

            # 同步订单数据（如果有断线期间，使用时间区间查询）
            if "order" in self.enabled_channels:
                await self._sync_order_data(use_disconnect_period=has_disconnect_period)

            # 同步成交数据（如果有断线期间，使用时间区间查询）
            if "trade" in self.enabled_channels:
                await self._sync_trade_data(use_disconnect_period=has_disconnect_period)

            # 清除断线时间记录
            if self.disconnect_time:
                logger.info("Clearing disconnect time after sync")
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
            
            # 保存到数据库
            async with self.db_manager.session() as session:
                update_time = datetime.utcnow()
                
                for currency, balance_data in balances.items():
                    record = XTAccountUpdate(
                        update_time=update_time,
                        currency=currency,
                        available=balance_data.get("available", Decimal("0")),
                        frozen=balance_data.get("frozen", Decimal("0")),
                        total=balance_data.get("total", Decimal("0")),
                        raw_data=json.dumps({
                            "source": "rest_sync",
                            "currency": currency,
                            "balance_data": balance_data,
                        }),
                    )
                    session.add(record)
                
                await session.commit()
                logger.info("Synced account data from REST API")
                
        except Exception as e:
            logger.error(f"Failed to sync account data: {e}")
    
    async def _sync_position_data(self) -> None:
        """同步持仓数据."""
        try:
            positions = await self.rest_client.get_positions(None)
            
            # 保存到数据库
            async with self.db_manager.session() as session:
                update_time = datetime.utcnow()
                
                for position in positions:
                    record = XTPositionUpdate(
                        update_time=update_time,
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
                        }),
                    )
                    session.add(record)
                
                await session.commit()
                logger.info("Synced position data from REST API")
                
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
                    start_time=self.disconnect_time.isoformat(),
                    end_time=self.reconnect_time.isoformat()
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
                        existing_result = await session.execute(
                            select(XTOrderUpdate).where(
                                XTOrderUpdate.order_id == order_id,
                                XTOrderUpdate.symbol == symbol
                            ).limit(1)
                        )
                        existing_order = existing_result.scalar_one_or_none()

                        if existing_order:
                            logger.debug(f"Order {order_id} already exists, skipping")
                            skipped_count += 1
                            continue

                        record = XTOrderUpdate(
                            update_time=update_time,
                            symbol=symbol,
                            order_id=order_id,
                            client_order_id="",
                            side=order.side.value,
                            order_type=order.order_type.value,
                            position_side=order.position_side or "LONG",
                            quantity=order.quantity,
                            price=order.price or Decimal("0"),
                            filled_quantity=Decimal("0"),  # 填充数量需要从详细信息获取
                            status=order.status.value,
                            time_in_force="GTC",
                            create_time=order.timestamp,
                            update_time_order=order.timestamp,
                            raw_data=json.dumps({
                                "source": "rest_sync",
                                "order_id": order.exchange_order_id,
                            }),
                        )
                        session.add(record)
                        saved_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to save order: {e}")
                        continue

                await session.commit()
                logger.info("Synced order data from REST API", saved=saved_count, skipped=skipped_count)

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
                    start_time=self.disconnect_time.isoformat(),
                    end_time=self.reconnect_time.isoformat(),
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
                        existing_result = await session.execute(
                            select(XTTradeUpdate).where(
                                XTTradeUpdate.trade_id == str(trade_id),
                                XTTradeUpdate.symbol == symbol
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
                            }),
                        )
                        session.add(record)
                        saved_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to save trade: {e}", trade_id=trade.get("id"))
                        continue

                await session.commit()
                logger.info("Synced trade data from REST API", saved=saved_count, skipped=skipped_count)

        except Exception as e:
            logger.error(f"Failed to sync trade data: {e}")
    
    async def _display_test_data(self) -> None:
        """显示测试数据以验证表格功能."""
        logger.info("Displaying test data to verify table functionality")
        
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

    # 数据变化检查方法

    def _has_account_changed(self, account_data: Dict[str, Any]) -> bool:
        """检查账户数据是否有变化."""
        # 将数据转换为可比较的格式，处理Decimal类型
        try:
            data_key = json.dumps(account_data, sort_keys=True, default=str)
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

    def _has_position_changed(self, position_data: Dict[str, Any]) -> bool:
        """检查持仓数据是否有变化."""
        # 将数据转换为可比较的格式，处理Decimal类型
        try:
            data_key = json.dumps(position_data, sort_keys=True, default=str)
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
        order_id = order_data.get("order_id") or order_data.get("orders", [{}])[0].get("order_id") if order_data.get("orders") else None
        status = order_data.get("status") or order_data.get("orders", [{}])[0].get("status") if order_data.get("orders") else None

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
        # 除非trade_id完全相同
        trade_id = trade_data.get("trade_id") or trade_data.get("trades", [{}])[0].get("trade_id") if trade_data.get("trades") else None

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
                    }),
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
