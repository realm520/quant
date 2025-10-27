"""Binance User Data Stream WebSocket service.

Subscribe to Binance user data stream for real-time account and order updates.
"""

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Literal

import websockets
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.binance_perp import BinancePerpExchange
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.models import AccountUpdate, OrderUpdate, TradeUpdate, ConnectionStatus
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = get_logger(__name__)
console = Console()


class BinanceUserStreamService:
    """Binance用户数据流订阅服务.
    
    订阅Binance WebSocket用户数据流，接收账户更新、订单更新和成交信息。
    将接收到的数据存储到PostgreSQL数据库。
    """
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        db_manager: DatabaseManager,
        auto_reconnect: bool = True,
        display_format: Literal["table", "json", "none"] = "table",
        enabled_channels: list[str] | None = None,
    ):
        """初始化用户数据流服务.
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            db_manager: 数据库管理器
            auto_reconnect: 是否自动重连
            display_format: 显示格式 (table/json/none)
            enabled_channels: 启用的频道列表，如["account", "order"]，None表示全部
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.db_manager = db_manager
        self.auto_reconnect = auto_reconnect
        self.display_format = display_format
        
        # 设置启用的频道（Binance推送所有数据，这里仅用于过滤）
        if enabled_channels is None:
            self.enabled_channels = {"account", "order", "trade"}
        else:
            self.enabled_channels = set(enabled_channels)
        
        self.exchange = BinancePerpExchange(api_key=api_key, api_secret=api_secret)
        self.listen_key: Optional[str] = None
        self.ws_url: Optional[str] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False

        # 断线重连相关
        self.last_message_time: Optional[datetime] = None
        self.disconnect_time: Optional[datetime] = None

        logger.info("BinanceUserStreamService initialized",
                   display_format=display_format,
                   enabled_channels=list(self.enabled_channels))
    
    async def get_listen_key(self) -> str:
        """获取ListenKey用于WebSocket连接.
        
        Returns:
            ListenKey字符串
        """
        await self.exchange.connect()
        
        response = await self.exchange._request(
            method="POST",
            path="/fapi/v1/listenKey",
            authenticated=True,
        )
        
        data = response.json()
        listen_key = data.get("listenKey")
        
        if not listen_key:
            raise ValueError("Failed to get listen key from Binance")
        
        logger.info("Listen key obtained", listen_key_prefix=listen_key[:8])
        return listen_key
    
    async def keepalive_listen_key(self, listen_key: str):
        """保持ListenKey有效.
        
        ListenKey每60分钟过期，需要定期发送keepalive请求。
        
        Args:
            listen_key: 要保持活跃的ListenKey
        """
        response = await self.exchange._request(
            method="PUT",
            path="/fapi/v1/listenKey",
            authenticated=True,
        )
        
        if response.status_code == 200:
            logger.debug("Listen key keepalive sent", listen_key_prefix=listen_key[:8])
        else:
            logger.warning("Listen key keepalive failed", status=response.status_code)
    
    async def close_listen_key(self, listen_key: str):
        """关闭ListenKey.

        Args:
            listen_key: 要关闭的ListenKey
        """
        try:
            await self.exchange._request(
                method="DELETE",
                path="/fapi/v1/listenKey",
                authenticated=True,
            )
            logger.info("Listen key closed", listen_key_prefix=listen_key[:8])
        except Exception as e:
            logger.error("Failed to close listen key", error=str(e))

    async def get_or_create_connection_status(self) -> ConnectionStatus:
        """获取或创建连接状态记录.

        Returns:
            ConnectionStatus对象
        """
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(ConnectionStatus).where(ConnectionStatus.exchange == "binance_perp")
            )
            status = result.scalar_one_or_none()

            if status is None:
                status = ConnectionStatus(exchange="binance_perp")
                session.add(status)
                await session.commit()
                await session.refresh(status)
                logger.info("Created new connection status record")
            else:
                logger.info(
                    "Loaded existing connection status",
                    last_order_time=status.last_order_event_time,
                    last_trade_time=status.last_trade_event_time,
                    reconnect_count=status.total_reconnect_count,
                )

            return status

    async def update_connection_status(
        self,
        is_connected: bool,
        order_event_time: datetime | None = None,
        trade_event_time: datetime | None = None,
        account_event_time: datetime | None = None,
        order_id: int | None = None,
        trade_id: int | None = None,
    ):
        """更新连接状态.

        Args:
            is_connected: 是否已连接
            order_event_time: 订单事件时间
            trade_event_time: 成交事件时间
            account_event_time: 账户事件时间
            order_id: 订单ID
            trade_id: 成交ID
        """
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(ConnectionStatus).where(ConnectionStatus.exchange == "binance_perp")
            )
            status = result.scalar_one_or_none()

            if status is None:
                status = ConnectionStatus(exchange="binance_perp")
                session.add(status)

            # 更新连接状态
            if is_connected:
                # 连接状态
                if not status.is_connected:
                    # 从断线恢复
                    logger.info(
                        "Reconnecting after disconnection",
                        was_connected=status.is_connected,
                        last_disconnected_at=status.last_disconnected_at,
                    )
                    if status.last_disconnected_at:
                        gap_seconds = int((datetime.now() - status.last_disconnected_at).total_seconds())
                        status.last_data_gap_seconds = gap_seconds
                        status.total_reconnect_count = (status.total_reconnect_count or 0) + 1
                        logger.info(
                            "Reconnected after disconnection",
                            gap_seconds=gap_seconds,
                            total_reconnects=status.total_reconnect_count,
                        )

                # 无论之前状态如何，都更新连接时间（确保时间戳是最新的）
                status.last_connected_at = datetime.now()
                status.is_connected = True

            else:
                # 断线状态
                if status.is_connected:
                    # 记录断线时间
                    status.last_disconnected_at = datetime.now()
                    logger.warning(
                        "Connection lost",
                        last_connected_at=status.last_connected_at,
                        disconnect_time=status.last_disconnected_at,
                    )
                status.is_connected = False

            # 更新事件时间戳
            if order_event_time:
                status.last_order_event_time = order_event_time
            if trade_event_time:
                status.last_trade_event_time = trade_event_time
            if account_event_time:
                status.last_account_event_time = account_event_time

            # 更新ID
            if order_id:
                status.last_order_id = order_id
            if trade_id:
                status.last_trade_id = trade_id

            await session.commit()

    async def query_missing_data(self, symbols: list[str] | None = None):
        """查询断线期间丢失的数据并补全到数据库.

        Args:
            symbols: 要查询的交易对列表，如["BTCUSDT", "ETHUSDT"]，None表示查询所有活跃交易对
        """
        logger.info("=== Starting data recovery process ===")

        # 获取连接状态
        status = await self.get_or_create_connection_status()

        if status.last_disconnected_at is None:
            logger.info("No disconnection detected, skipping data recovery")
            return

        # 计算查询时间范围
        start_time = status.last_disconnected_at
        end_time = datetime.now()
        gap_seconds = int((end_time - start_time).total_seconds())

        logger.info(
            "Data recovery time range",
            start_time=start_time,
            end_time=end_time,
            gap_seconds=gap_seconds,
        )

        # 如果没有指定交易对，从数据库中获取最近活跃的交易对
        if symbols is None:
            symbols = await self._get_active_symbols()
            logger.info(f"Auto-detected {len(symbols)} active symbols: {symbols}")
        else:
            logger.info(f"Using provided symbols: {symbols}")

        if not symbols:
            logger.warning("No symbols to query for data recovery")
            return

        # 转换为毫秒时间戳
        start_time_ms = int(start_time.timestamp() * 1000)
        end_time_ms = int(end_time.timestamp() * 1000)

        logger.info(
            "Query parameters",
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )

        total_orders = 0
        total_trades = 0
        recovered_orders = 0
        recovered_trades = 0

        # 对每个交易对查询订单和成交
        for symbol in symbols:
            logger.info(f"Processing symbol: {symbol}")
            try:
                # 查询订单
                logger.debug(f"Querying orders for {symbol}...")
                orders = await self.exchange.get_all_orders(
                    symbol=symbol,
                    start_time=start_time_ms,
                    end_time=end_time_ms,
                )

                logger.info(f"Retrieved {len(orders)} orders for {symbol}")
                total_orders += len(orders)

                # 保存订单到数据库（带去重）
                for order_data in orders:
                    saved = await self._save_order_with_dedup(order_data)
                    if saved:
                        recovered_orders += 1

                # 查询成交
                logger.debug(f"Querying trades for {symbol}...")
                trades = await self.exchange.get_user_trades(
                    symbol=symbol,
                    start_time=start_time_ms,
                    end_time=end_time_ms,
                )

                logger.info(f"Retrieved {len(trades)} trades for {symbol}")
                total_trades += len(trades)

                # 保存成交到数据库（带去重）
                for trade_data in trades:
                    saved = await self._save_trade_with_dedup(trade_data)
                    if saved:
                        recovered_trades += 1

            except Exception as e:
                logger.error(f"Failed to query data for {symbol}", error=str(e), exc_info=True)
                continue

        logger.info(
            "=== Data recovery completed ===",
            total_orders_retrieved=total_orders,
            total_trades_retrieved=total_trades,
            new_orders_saved=recovered_orders,
            new_trades_saved=recovered_trades,
            gap_seconds=gap_seconds,
        )

    async def _get_active_symbols(self) -> list[str]:
        """从数据库中获取最近活跃的交易对.

        Returns:
            交易对列表，如["BTCUSDT", "ETHUSDT"]
        """
        async with self.db_manager.session() as session:
            # 查询最近24小时内有订单或成交的交易对
            cutoff_time = datetime.now() - timedelta(hours=24)

            # 从订单表获取
            result = await session.execute(
                select(OrderUpdate.symbol)
                .where(OrderUpdate.exchange == "binance_perp")
                .where(OrderUpdate.event_time >= cutoff_time)
                .distinct()
            )
            symbols_from_orders = [row[0] for row in result.fetchall()]

            # 从成交表获取
            result = await session.execute(
                select(TradeUpdate.symbol)
                .where(TradeUpdate.exchange == "binance_perp")
                .where(TradeUpdate.event_time >= cutoff_time)
                .distinct()
            )
            symbols_from_trades = [row[0] for row in result.fetchall()]

            # 合并去重
            symbols = list(set(symbols_from_orders + symbols_from_trades))

            logger.info(f"Found {len(symbols)} active symbols in last 24 hours")
            return symbols

    async def _save_order_with_dedup(self, order_data: dict):
        """保存订单数据，自动去重（使用数据库唯一约束）.

        Args:
            order_data: Binance API返回的订单数据
        """
        order_id = int(order_data.get("orderId", 0))
        update_time = datetime.fromtimestamp(order_data.get("updateTime", 0) / 1000)

        try:
            async with self.db_manager.session() as session:
                # 创建新的订单更新记录
                order_update = OrderUpdate(
                    exchange="binance_perp",
                    event_type="ORDER_TRADE_UPDATE",
                    event_time=update_time,
                    transaction_time=update_time,
                    symbol=order_data.get("symbol"),
                    client_order_id=order_data.get("clientOrderId"),
                    side=order_data.get("side"),
                    order_type=order_data.get("type"),
                    time_in_force=order_data.get("timeInForce"),
                    original_quantity=Decimal(str(order_data.get("origQty", "0"))),
                    original_price=Decimal(str(order_data.get("price", "0"))),
                    average_price=Decimal(str(order_data.get("avgPrice", "0"))),
                    order_status=order_data.get("status"),
                    order_id=order_id,
                    last_filled_quantity=Decimal("0"),
                    cumulative_filled_quantity=Decimal(str(order_data.get("executedQty", "0"))),
                    last_filled_price=Decimal("0"),
                    commission_amount=Decimal("0"),
                    commission_asset=None,
                    position_side=order_data.get("positionSide"),
                    is_reduce_only=order_data.get("reduceOnly", False),
                    raw_data=json.dumps(order_data),
                )
                session.add(order_update)
                await session.commit()

                logger.debug(
                    "Saved recovered order",
                    order_id=order_id,
                    symbol=order_data.get("symbol"),
                    status=order_data.get("status"),
                )
        except IntegrityError:
            # 违反唯一性约束，说明记录已存在
            logger.debug(
                f"Order {order_id} at {update_time} already exists (IntegrityError), skipping"
            )

    async def _save_trade_with_dedup(self, trade_data: dict):
        """保存成交数据，自动去重（使用数据库唯一约束）.

        Args:
            trade_data: Binance API返回的成交数据
        """
        trade_id = int(trade_data.get("id", 0))

        try:
            async with self.db_manager.session() as session:
                # 创建新的成交记录
                trade_time = datetime.fromtimestamp(trade_data.get("time", 0) / 1000)

                trade_update = TradeUpdate(
                    exchange="binance_perp",
                    event_type="TRADE",
                    event_time=trade_time,
                    transaction_time=trade_time,
                    symbol=trade_data.get("symbol"),
                    order_id=int(trade_data.get("orderId", 0)),
                    trade_id=trade_id,
                    side=trade_data.get("side"),
                    price=Decimal(str(trade_data.get("price", "0"))),
                    quantity=Decimal(str(trade_data.get("qty", "0"))),
                    quote_quantity=Decimal(str(trade_data.get("quoteQty", "0"))),
                    commission=Decimal(str(trade_data.get("commission", "0"))),
                    commission_asset=trade_data.get("commissionAsset"),
                    is_maker=trade_data.get("maker", False),
                    position_side=trade_data.get("positionSide"),
                    raw_data=json.dumps(trade_data),
                )
                session.add(trade_update)
                await session.commit()

                logger.debug(
                    "Saved recovered trade",
                    trade_id=trade_id,
                    order_id=trade_data.get("orderId"),
                    symbol=trade_data.get("symbol"),
                )
        except IntegrityError:
            # 违反唯一性约束，说明记录已存在
            logger.debug(f"Trade {trade_id} already exists (IntegrityError), skipping")

    def display_account_update(self, event: dict):
        """显示账户更新信息.
        
        Args:
            event: 账户更新事件数据
        """
        if self.display_format == "none":
            return
        
        if self.display_format == "json":
            console.print(Panel(
                json.dumps(event, indent=2, ensure_ascii=False),
                title="[cyan]账户更新 (ACCOUNT_UPDATE)[/cyan]",
                border_style="cyan"
            ))
            return
        
        # 表格显示
        event_time = datetime.fromtimestamp(event.get("E", 0) / 1000)
        
        # 余额更新表格
        if "a" in event and "B" in event["a"] and event["a"]["B"]:
            table = Table(title=f"💰 账户余额更新 - {event_time.strftime('%H:%M:%S')}", box=box.ROUNDED)
            table.add_column("资产", style="cyan", justify="center")
            table.add_column("钱包余额", style="green", justify="right")
            table.add_column("可用余额", style="yellow", justify="right")
            table.add_column("余额变化", style="magenta", justify="right")
            
            for balance in event["a"]["B"]:
                wallet_bal = float(balance.get("wb", 0))
                cross_bal = float(balance.get("cw", 0))
                change = float(balance.get("bc", 0))
                
                change_str = f"+{change:.4f}" if change > 0 else f"{change:.4f}"
                change_style = "green" if change > 0 else "red" if change < 0 else "white"
                
                table.add_row(
                    balance.get("a", ""),
                    f"{wallet_bal:.4f}",
                    f"{cross_bal:.4f}",
                    f"[{change_style}]{change_str}[/{change_style}]"
                )
            
            console.print(table)
        
        # 持仓更新表格
        if "a" in event and "P" in event["a"] and event["a"]["P"]:
            table = Table(title=f"📊 持仓更新 - {event_time.strftime('%H:%M:%S')}", box=box.ROUNDED)
            table.add_column("交易对", style="cyan", justify="center")
            table.add_column("方向", style="yellow", justify="center")
            table.add_column("持仓量", style="white", justify="right")
            table.add_column("开仓均价", style="white", justify="right")
            table.add_column("未实现盈亏", style="white", justify="right")
            
            for position in event["a"]["P"]:
                pos_amt = float(position.get("pa", 0))
                if pos_amt == 0:
                    continue  # 跳过零持仓
                
                symbol = position.get("s", "")
                pos_side = position.get("ps", "")
                entry_price = float(position.get("ep", 0))
                unrealized_pnl = float(position.get("up", 0))
                
                pnl_str = f"+{unrealized_pnl:.4f}" if unrealized_pnl > 0 else f"{unrealized_pnl:.4f}"
                pnl_style = "green" if unrealized_pnl > 0 else "red" if unrealized_pnl < 0 else "white"
                
                table.add_row(
                    symbol,
                    pos_side,
                    f"{pos_amt:.8f}",
                    f"{entry_price:.4f}",
                    f"[{pnl_style}]{pnl_str}[/{pnl_style}]"
                )
            
            if table.row_count > 0:
                console.print(table)
    
    def display_order_update(self, event: dict):
        """显示订单更新信息.
        
        Args:
            event: 订单更新事件数据
        """
        if self.display_format == "none":
            return
        
        if self.display_format == "json":
            console.print(Panel(
                json.dumps(event, indent=2, ensure_ascii=False),
                title="[yellow]订单更新 (ORDER_TRADE_UPDATE)[/yellow]",
                border_style="yellow"
            ))
            return
        
        # 表格显示
        event_time = datetime.fromtimestamp(event.get("E", 0) / 1000)
        order = event.get("o", {})
        
        # 订单状态颜色
        status = order.get("X", "")
        status_colors = {
            "NEW": "blue",
            "PARTIALLY_FILLED": "yellow",
            "FILLED": "green",
            "CANCELED": "red",
            "REJECTED": "red",
            "EXPIRED": "red"
        }
        status_color = status_colors.get(status, "white")
        
        table = Table(title=f"📝 订单更新 - {event_time.strftime('%H:%M:%S')}", box=box.ROUNDED)
        table.add_column("字段", style="cyan", justify="left")
        table.add_column("值", style="white", justify="left")
        
        # 订单基本信息
        table.add_row("交易对", order.get("s", ""))
        table.add_row("订单ID", str(order.get("i", "")))
        table.add_row("客户订单ID", order.get("c", ""))
        table.add_row("状态", f"[{status_color}]{status}[/{status_color}]")
        
        # 订单详情
        side = order.get("S", "")
        side_color = "green" if side == "BUY" else "red"
        table.add_row("方向", f"[{side_color}]{side}[/{side_color}]")
        table.add_row("类型", order.get("o", ""))
        table.add_row("持仓方向", order.get("ps", ""))
        
        # 价格和数量
        table.add_row("价格", f"{float(order.get('p', 0)):.4f}")
        table.add_row("数量", f"{float(order.get('q', 0)):.8f}")
        table.add_row("已成交", f"{float(order.get('z', 0)):.8f}")
        
        # 成交信息
        if float(order.get("l", 0)) > 0:
            table.add_row("最后成交量", f"{float(order.get('l', 0)):.8f}")
            table.add_row("最后成交价", f"{float(order.get('L', 0)):.4f}")
        
        # 平均价格
        if float(order.get("ap", 0)) > 0:
            table.add_row("平均成交价", f"{float(order.get('ap', 0)):.4f}")
        
        # 手续费
        if float(order.get("n", 0)) > 0:
            table.add_row("手续费", f"{float(order.get('n', 0)):.8f} {order.get('N', '')}")
        
        console.print(table)
        
        # 如果有成交，额外显示成交信息
        if status in ["PARTIALLY_FILLED", "FILLED"] and float(order.get("l", 0)) > 0:
            trade_value = float(order.get("l", 0)) * float(order.get("L", 0))
            console.print(f"[green]✅ 成交: {float(order.get('l', 0)):.8f} @ {float(order.get('L', 0)):.4f} = {trade_value:.4f} USDT[/green]")
    
    async def handle_account_update(self, event: dict):
        """处理账户更新事件.

        Args:
            event: 账户更新事件数据
        """
        try:
            # 显示更新信息
            self.display_account_update(event)

            event_time = datetime.fromtimestamp(event.get("E", 0) / 1000)
            transaction_time = datetime.fromtimestamp(event.get("T", 0) / 1000)

            # 更新最后消息时间
            self.last_message_time = event_time
            
            # 处理余额更新
            if "a" in event and "B" in event["a"]:
                for balance in event["a"]["B"]:
                    async with self.db_manager.session() as session:
                        update = AccountUpdate(
                            exchange="binance_perp",
                            event_type="ACCOUNT_UPDATE",
                            event_time=event_time,
                            transaction_time=transaction_time,
                            asset=balance.get("a"),
                            wallet_balance=Decimal(balance.get("wb", "0")),
                            cross_wallet_balance=Decimal(balance.get("cw", "0")),
                            balance_change=Decimal(balance.get("bc", "0")),
                            raw_data=json.dumps(event),
                        )
                        session.add(update)
                
                logger.info("Account balance update saved", assets_count=len(event["a"]["B"]))
            
            # 处理持仓更新
            if "a" in event and "P" in event["a"]:
                for position in event["a"]["P"]:
                    async with self.db_manager.session() as session:
                        update = AccountUpdate(
                            exchange="binance_perp",
                            event_type="POSITION_UPDATE",
                            event_time=event_time,
                            transaction_time=transaction_time,
                            symbol=position.get("s"),
                            position_side=position.get("ps"),
                            position_amount=Decimal(position.get("pa", "0")),
                            entry_price=Decimal(position.get("ep", "0")),
                            unrealized_pnl=Decimal(position.get("up", "0")),
                            raw_data=json.dumps(event),
                        )
                        session.add(update)
                
                logger.info("Position update saved", positions_count=len(event["a"]["P"]))

            # 更新连接状态时间戳
            await self.update_connection_status(
                is_connected=True,
                account_event_time=event_time,
            )

        except Exception as e:
            logger.error("Failed to handle account update", error=str(e))
    
    async def handle_order_update(self, event: dict):
        """处理订单更新事件.

        Args:
            event: 订单更新事件数据
        """
        try:
            # 显示更新信息
            self.display_order_update(event)

            event_time = datetime.fromtimestamp(event.get("E", 0) / 1000)
            transaction_time = datetime.fromtimestamp(event.get("T", 0) / 1000)

            # 更新最后消息时间
            self.last_message_time = event_time

            order = event.get("o", {})

            # 保存订单更新（带去重）
            try:
                async with self.db_manager.session() as session:
                    order_update = OrderUpdate(
                        exchange="binance_perp",
                        event_type="ORDER_TRADE_UPDATE",
                        event_time=event_time,
                        transaction_time=transaction_time,
                        symbol=order.get("s"),
                        client_order_id=order.get("c"),
                        side=order.get("S"),
                        order_type=order.get("o"),
                        time_in_force=order.get("f"),
                        original_quantity=Decimal(order.get("q", "0")),
                        original_price=Decimal(order.get("p", "0")),
                        average_price=Decimal(order.get("ap", "0")),
                        order_status=order.get("X"),
                        order_id=int(order.get("i", 0)),
                        last_filled_quantity=Decimal(order.get("l", "0")),
                        cumulative_filled_quantity=Decimal(order.get("z", "0")),
                        last_filled_price=Decimal(order.get("L", "0")),
                        commission_amount=Decimal(order.get("n", "0")),
                        commission_asset=order.get("N"),
                        position_side=order.get("ps"),
                        is_reduce_only=order.get("R", False),
                        raw_data=json.dumps(event),
                    )
                    session.add(order_update)
                    await session.commit()

                logger.info(
                    "Order update saved",
                    order_id=order.get("i"),
                    symbol=order.get("s"),
                    status=order.get("X"),
                    side=order.get("S"),
                )
            except IntegrityError:
                logger.debug(
                    f"Order update duplicate detected (order_id={order.get('i')}, event_time={event_time}), skipping"
                )

            # 如果有成交，保存成交记录（带去重）
            if order.get("l") and Decimal(order.get("l", "0")) > 0 and order.get("t"):
                trade_id = int(order.get("t", 0))
                try:
                    async with self.db_manager.session() as session:
                        trade = TradeUpdate(
                            exchange="binance_perp",
                            event_type="TRADE",
                            event_time=event_time,
                            transaction_time=transaction_time,
                            symbol=order.get("s"),
                            order_id=int(order.get("i", 0)),
                            trade_id=trade_id,
                            side=order.get("S"),
                            price=Decimal(order.get("L", "0")),  # 最后成交价
                            quantity=Decimal(order.get("l", "0")),  # 最后成交量
                            quote_quantity=Decimal(order.get("L", "0")) * Decimal(order.get("l", "0")),
                            commission=Decimal(order.get("n", "0")),
                            commission_asset=order.get("N"),
                            is_maker=order.get("m", False),
                            position_side=order.get("ps"),
                            raw_data=json.dumps(event),
                        )
                        session.add(trade)
                        await session.commit()

                    logger.info(
                        "Trade saved",
                        trade_id=trade_id,
                        order_id=order.get("i"),
                        symbol=order.get("s"),
                        quantity=order.get("l"),
                        price=order.get("L"),
                    )
                except IntegrityError:
                    logger.debug(f"Trade duplicate detected (trade_id={trade_id}), skipping")

            # 更新连接状态时间戳
            await self.update_connection_status(
                is_connected=True,
                order_event_time=event_time,
                order_id=int(order.get("i", 0)),
                trade_event_time=event_time if order.get("l") and Decimal(order.get("l", "0")) > 0 else None,
                trade_id=int(order.get("t", 0)) if order.get("t") else None,
            )

        except Exception as e:
            logger.error("Failed to handle order update", error=str(e))
    
    async def process_message(self, message: str):
        """处理WebSocket消息.
        
        Args:
            message: WebSocket接收到的消息
        """
        try:
            data = json.loads(message)
            event_type = data.get("e")
            
            if event_type == "ACCOUNT_UPDATE":
                # 检查是否启用了account频道
                if "account" in self.enabled_channels:
                    await self.handle_account_update(data)
                else:
                    logger.debug("Account update received but channel disabled")
                    
            elif event_type == "ORDER_TRADE_UPDATE":
                # 检查是否启用了order频道
                if "order" in self.enabled_channels:
                    await self.handle_order_update(data)
                else:
                    logger.debug("Order update received but channel disabled")
            else:
                logger.debug("Received unknown event type", event_type=event_type)
                
        except json.JSONDecodeError as e:
            logger.error("Failed to decode message", error=str(e), message=message[:200])
        except Exception as e:
            logger.error("Failed to process message", error=str(e))
    
    async def keepalive_task(self):
        """定期发送keepalive保持ListenKey有效."""
        while self.is_running:
            try:
                await asyncio.sleep(30 * 60)  # 每30分钟发送一次keepalive
                if self.listen_key:
                    await self.keepalive_listen_key(self.listen_key)
            except Exception as e:
                logger.error("Keepalive task error", error=str(e))
    
    async def start(self):
        """启动用户数据流订阅."""
        self.is_running = True

        try:
            # 获取或创建连接状态记录
            status = await self.get_or_create_connection_status()

            # 检查是否需要补全数据（从上次断线恢复）
            # 条件：有断线记录 AND (状态为断开 OR 断线时间晚于连接时间)
            needs_recovery = False
            if status.last_disconnected_at is not None:
                if not status.is_connected:
                    # 状态显示未连接
                    needs_recovery = True
                elif status.last_connected_at is None or status.last_disconnected_at > status.last_connected_at:
                    # 断线时间晚于连接时间，说明有一次断线还未处理
                    needs_recovery = True

            if needs_recovery:
                logger.info(
                    "Detected previous disconnection, starting data recovery",
                    last_disconnected_at=status.last_disconnected_at,
                    last_connected_at=status.last_connected_at,
                    is_connected=status.is_connected,
                )
                self.disconnect_time = status.last_disconnected_at

                # 补全断线期间的数据
                try:
                    await self.query_missing_data()
                    logger.info("Data recovery completed successfully")
                except Exception as e:
                    logger.error("Failed to recover missing data", error=str(e))
                    # 继续连接，不因为数据补全失败而中断
            else:
                logger.info(
                    "No data recovery needed",
                    last_disconnected_at=status.last_disconnected_at,
                    last_connected_at=status.last_connected_at,
                )

            # 获取listen key
            self.listen_key = await self.get_listen_key()
            self.ws_url = f"wss://fstream.binance.com/ws/{self.listen_key}"

            logger.info("Starting user data stream", ws_url=self.ws_url)

            # 更新连接状态为已连接
            await self.update_connection_status(is_connected=True)

            # 启动keepalive任务
            keepalive_task = asyncio.create_task(self.keepalive_task())

            # 连接WebSocket
            async with websockets.connect(self.ws_url) as websocket:
                self.websocket = websocket
                logger.info("WebSocket connected successfully")

                # 接收消息循环
                async for message in websocket:
                    if not self.is_running:
                        break

                    await self.process_message(message)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")

            # 记录断线时间
            self.disconnect_time = datetime.now()
            await self.update_connection_status(is_connected=False)

            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect in 5 seconds...")
                await asyncio.sleep(5)
                await self.start()
        except Exception as e:
            logger.error("User data stream error", error=str(e))

            # 记录断线
            await self.update_connection_status(is_connected=False)
            raise
        finally:
            keepalive_task.cancel()
            if self.listen_key:
                await self.close_listen_key(self.listen_key)
            await self.exchange.disconnect()
    
    async def stop(self):
        """停止用户数据流订阅."""
        self.is_running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("User data stream stopped")

