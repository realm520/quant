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
from tri_arb.storage.models import (
    AccountUpdate,
    OrderUpdate,
    TradeUpdate,
    ConnectionStatus,
)
from tri_arb.services.binance_reconciliation import BinanceReconciliationService
from tri_arb.metrics.prometheus import (
    ensure_metrics_server,
    update_order_metrics,
    update_trade_metrics,
)
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
        self.account_id: Optional[str] = None
        self.account_name: Optional[str] = None
        self.listen_key: Optional[str] = None
        self.ws_url: Optional[str] = None
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False

        # 对账服务（按需对账，仅在重连时触发）
        self.reconciliation_service = BinanceReconciliationService(
            exchange=self.exchange,
            db_manager=db_manager,
            poll_interval=60,  # 保留参数但不启动定时任务
            lookback_window=3600,  # 重连时回溯1小时
        )

        # 记录断线时间，用于重连后计算回溯时间
        self.disconnect_time: Optional[datetime] = None

        logger.info(
            "BinanceUserStreamService initialized",
            display_format=display_format,
            enabled_channels=list(self.enabled_channels),
            reconciliation_mode="on_reconnect",
        )
    
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

        # 显示数据恢复开始信息
        if self.display_format != "none":
            console.print(Panel(
                "[yellow]⏳ 正在启动数据恢复流程...[/yellow]",
                title="[bold cyan]📦 数据恢复[/bold cyan]",
                border_style="cyan"
            ))

        # 确保 exchange 已连接（数据恢复需要调用 API）
        if not self.exchange.is_connected:
            logger.info("Exchange not connected, connecting now for data recovery")
            await self.exchange.connect()

        # 获取连接状态
        status = await self.get_or_create_connection_status()

        if status.last_disconnected_at is None:
            logger.info("No disconnection detected, skipping data recovery")
            if self.display_format != "none":
                console.print("[green]✅ 无需数据恢复（未检测到断线）[/green]")
            return

        # 计算查询时间范围
        start_time = status.last_disconnected_at
        end_time = datetime.now()
        gap_seconds = int((end_time - start_time).total_seconds())

        logger.info(
            "Data recovery time range",
            start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=end_time.strftime("%Y-%m-%d %H:%M:%S"),
            gap_seconds=gap_seconds,
            gap_minutes=round(gap_seconds / 60, 2),
        )

        # 显示断线时间信息
        if self.display_format != "none":
            console.print(f"[cyan]断线开始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]")
            console.print(f"[cyan]恢复时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]")
            console.print(f"[yellow]断线时长: {gap_seconds} 秒 ({round(gap_seconds / 60, 2)} 分钟)[/yellow]\n")

        # 如果没有指定交易对，从数据库中获取最近活跃的交易对
        if symbols is None:
            symbols = await self._get_active_symbols()
            if not symbols:
                logger.warning(
                    "No active symbols found in database (last 24 hours). "
                    "Data recovery skipped. If you need to recover specific symbols, "
                    "call query_missing_data(symbols=['BTCUSDT', 'ETHUSDT'])"
                )
                return
            logger.info(f"Auto-detected {len(symbols)} active symbols: {symbols}")
        else:
            logger.info(f"Using provided symbols: {symbols}")

        if not symbols:
            logger.warning("No symbols to query for data recovery")
            return

        # 转换为毫秒时间戳
        start_time_ms = int(start_time.timestamp() * 1000)
        end_time_ms = int(end_time.timestamp() * 1000)

        logger.debug(
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

        # 计算去重统计
        duplicate_orders = total_orders - recovered_orders
        duplicate_trades = total_trades - recovered_trades

        logger.info(
            "=== Data recovery completed ===",
            total_orders_retrieved=total_orders,
            total_trades_retrieved=total_trades,
            new_orders_saved=recovered_orders,
            new_trades_saved=recovered_trades,
            duplicate_orders_skipped=duplicate_orders,
            duplicate_trades_skipped=duplicate_trades,
            gap_seconds=gap_seconds,
            gap_minutes=round(gap_seconds / 60, 2),
        )

        # 显示数据恢复汇总表格
        if self.display_format != "none":
            console.print()  # 空行
            table = Table(title="📊 数据恢复汇总", box=box.ROUNDED, border_style="green")
            table.add_column("项目", style="cyan", justify="left", width=20)
            table.add_column("数量", style="white", justify="right", width=15)

            # 断线时长
            table.add_row(
                "断线时长",
                f"{gap_seconds} 秒 ({round(gap_seconds / 60, 2)} 分钟)"
            )

            # 订单统计
            table.add_row("", "")  # 空行分隔
            table.add_row("检索订单总数", f"[yellow]{total_orders}[/yellow]")
            table.add_row("新增订单", f"[green]{recovered_orders}[/green]")
            table.add_row("重复订单(跳过)", f"[red]{duplicate_orders}[/red]")

            # 成交统计
            table.add_row("", "")  # 空行分隔
            table.add_row("检索成交总数", f"[yellow]{total_trades}[/yellow]")
            table.add_row("新增成交", f"[green]{recovered_trades}[/green]")
            table.add_row("重复成交(跳过)", f"[red]{duplicate_trades}[/red]")

            console.print(table)
            console.print(Panel(
                "[green]✅ 数据恢复完成！所有丢失的订单和成交已恢复。[/green]",
                border_style="green"
            ))

    async def _get_active_symbols(self) -> list[str]:
        """从数据库中获取最近活跃的交易对.

        Returns:
            交易对列表，如["BTCUSDT", "ETHUSDT"]
        """
        async with self.db_manager.session() as session:
            # 先尝试最近24小时
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

            if symbols:
                logger.info(
                    f"Found {len(symbols)} active symbols in last 24 hours",
                    symbols=symbols,
                    from_orders=len(symbols_from_orders),
                    from_trades=len(symbols_from_trades),
                )
            else:
                # 如果24小时内没有数据，尝试扩展到7天
                logger.info("No symbols found in last 24 hours, extending search to 7 days")
                cutoff_time = datetime.now() - timedelta(days=7)

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

                if symbols:
                    logger.info(
                        f"Found {len(symbols)} active symbols in last 7 days",
                        symbols=symbols,
                        from_orders=len(symbols_from_orders),
                        from_trades=len(symbols_from_trades),
                    )
                else:
                    logger.warning(
                        "No active symbols found in last 7 days. "
                        "This may indicate:\n"
                        "  1. First time running (no historical data)\n"
                        "  2. No trading activity in the past week\n"
                        "  3. Database was recently cleared\n"
                        "Consider manually specifying symbols for data recovery."
                    )

            return symbols

    async def _save_order_with_dedup(self, order_data: dict) -> bool:
        """保存订单数据，自动去重（使用数据库唯一约束）.

        Args:
            order_data: Binance API返回的订单数据

        Returns:
            bool: True 表示新数据已保存，False 表示数据已存在（去重）
        """
        order_id = int(order_data.get("orderId", 0))
        update_time = datetime.fromtimestamp(order_data.get("updateTime", 0) / 1000)

        try:
            async with self.db_manager.session() as session:
                # 创建新的订单更新记录
                order_update = OrderUpdate(
                    exchange="binance_perp",
                    account_id=self.account_id or None,
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

                # 显示恢复的订单信息
                if self.display_format != "none":
                    status = order_data.get("status", "")
                    side = order_data.get("side", "")
                    symbol = order_data.get("symbol", "")

                    # 订单状态颜色
                    status_colors = {
                        "NEW": "blue",
                        "PARTIALLY_FILLED": "yellow",
                        "FILLED": "green",
                        "CANCELED": "red",
                        "REJECTED": "red",
                        "EXPIRED": "red"
                    }
                    status_color = status_colors.get(status, "white")
                    side_color = "green" if side == "BUY" else "red"

                    # 简洁的订单信息输出
                    console.print(
                        f"[green]✅ 恢复订单:[/green] "
                        f"[{side_color}]{side}[/{side_color}] "
                        f"[cyan]{symbol}[/cyan] "
                        f"ID:{order_id} "
                        f"状态:[{status_color}]{status}[/{status_color}] "
                        f"价格:{float(order_data.get('price', 0)):.4f} "
                        f"数量:{float(order_data.get('origQty', 0)):.8f} "
                        f"成交:{float(order_data.get('executedQty', 0)):.8f}"
                    )

                return True
        except IntegrityError:
            # 违反唯一性约束，说明记录已存在
            logger.debug(
                f"Order {order_id} at {update_time} already exists (IntegrityError), skipping"
            )
            return False

    async def _save_trade_with_dedup(self, trade_data: dict) -> bool:
        """保存成交数据，自动去重（使用数据库唯一约束）.

        Args:
            trade_data: Binance API返回的成交数据

        Returns:
            bool: True 表示新数据已保存，False 表示数据已存在（去重）
        """
        trade_id = int(trade_data.get("id", 0))

        try:
            async with self.db_manager.session() as session:
                # 创建新的成交记录
                trade_time = datetime.fromtimestamp(trade_data.get("time", 0) / 1000)

                trade_update = TradeUpdate(
                    exchange="binance_perp",
                    account_id=self.account_id or None,
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

                # 显示恢复的成交信息
                if self.display_format != "none":
                    side = trade_data.get("side", "")
                    symbol = trade_data.get("symbol", "")
                    price = float(trade_data.get("price", 0))
                    qty = float(trade_data.get("qty", 0))
                    quote_qty = float(trade_data.get("quoteQty", 0))
                    commission = float(trade_data.get("commission", 0))
                    commission_asset = trade_data.get("commissionAsset", "")
                    is_maker = trade_data.get("maker", False)

                    side_color = "green" if side == "BUY" else "red"
                    maker_str = "Maker" if is_maker else "Taker"

                    # 简洁的成交信息输出
                    console.print(
                        f"[green]💰 恢复成交:[/green] "
                        f"[{side_color}]{side}[/{side_color}] "
                        f"[cyan]{symbol}[/cyan] "
                        f"ID:{trade_id} "
                        f"价格:{price:.4f} "
                        f"数量:{qty:.8f} "
                        f"金额:{quote_qty:.4f} "
                        f"[yellow]{maker_str}[/yellow] "
                        f"手续费:{commission:.8f} {commission_asset}"
                    )

                return True
        except IntegrityError:
            # 违反唯一性约束，说明记录已存在
            logger.debug(f"Trade {trade_id} already exists (IntegrityError), skipping")
            return False

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
        
        # 持仓方向（多空）- 高亮显示
        position_side = order.get("ps", "NET")
        position_color = "bright_green" if position_side == "LONG" else "bright_red" if position_side == "SHORT" else "white"
        table.add_row("持仓方向（多空）", f"[{position_color}]{position_side}[/{position_color}]")
        
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
            
            account_id = self.account_id or None

            # 处理余额更新
            if "a" in event and "B" in event["a"]:
                for balance in event["a"]["B"]:
                    async with self.db_manager.session() as session:
                        update = AccountUpdate(
                            exchange="binance_perp",
                            account_id=account_id,
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
                            account_id=account_id,
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

            account_id = self.account_id or None

            # 保存订单更新（带去重）
            try:
                async with self.db_manager.session() as session:
                    order_update = OrderUpdate(
                        exchange="binance_perp",
                        account_id=account_id,
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
                            account_id=account_id,
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
                    
                    # 更新成交的 Prometheus metrics
                    try:
                        account_id = self.account_id or "default"
                        update_trade_metrics(
                            exchange="binance",
                            exchange_type="perp",
                            account_id=account_id,
                            trade_data={
                                "trade_id": trade_id,
                                "order_id": order.get("i"),
                                "symbol": order.get("s"),
                                "side": order.get("S"),
                                "price": order.get("L"),
                                "quantity": order.get("l"),
                                "positionSide": order.get("ps"),
                            },
                        )
                        logger.debug(f"成功更新成交 metrics (account_id={account_id}, trade_id={trade_id})")
                    except Exception as metric_error:
                        logger.error(f"Failed to update trade metrics: {metric_error}", exc_info=True)
                except IntegrityError:
                    logger.debug(f"Trade duplicate detected (trade_id={trade_id}), skipping")

            # 更新订单的 Prometheus metrics
            # 订阅服务使用端口 9601
            ensure_metrics_server(9601)
            account_id = self.account_id or "default"
            update_order_metrics(
                exchange="binance",
                exchange_type="perp",
                account_id=account_id,
                order_data=order,
            )

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
    
    async def _check_needs_recovery(self, status: ConnectionStatus) -> tuple[bool, str, datetime | None]:
        """检查是否需要数据恢复.

        Args:
            status: 连接状态对象

        Returns:
            (需要恢复, 原因, 断线时间)
        """
        if status.last_disconnected_at is None:
            return False, "", None

        # 检查是否需要恢复
        if not status.is_connected:
            return True, "connection status shows disconnected", status.last_disconnected_at
        elif status.last_connected_at is None:
            return True, "never connected but has disconnection record", status.last_disconnected_at
        elif status.last_disconnected_at > status.last_connected_at:
            return True, "disconnection time is later than last connection time", status.last_disconnected_at

        return False, "", None

    async def _recover_data_with_retry(self, max_retries: int = 3, retry_delay: int = 2):
        """带重试机制的数据恢复.

        Args:
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Attempting data recovery",
                    attempt=attempt,
                    max_retries=max_retries,
                )

                # 确保 exchange 已连接
                if not self.exchange.is_connected:
                    await self.exchange.connect()

                # 执行数据恢复
                await self.query_missing_data()
                logger.info("Data recovery completed successfully", attempt=attempt)
                return  # 成功，退出

            except Exception as e:
                logger.warning(
                    "Data recovery failed",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(e),
                )

                if attempt < max_retries:
                    logger.info(f"Retrying data recovery in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        "Data recovery failed after all retries",
                        max_retries=max_retries,
                        error=str(e),
                    )
                    # 不抛出异常，允许程序继续运行

    async def start(self):
        """启动用户数据流订阅."""
        self.is_running = True

        try:
            # 获取或创建连接状态记录
            status = await self.get_or_create_connection_status()

            # 获取listen key
            self.listen_key = await self.get_listen_key()
            self.ws_url = f"wss://fstream.binance.com/ws/{self.listen_key}"

            logger.info("Starting user data stream", ws_url=self.ws_url)

            # 启动keepalive任务
            keepalive_task = asyncio.create_task(self.keepalive_task())

            # 连接WebSocket
            async with websockets.connect(self.ws_url) as websocket:
                self.websocket = websocket
                logger.info("WebSocket connected successfully")

                # 更新连接状态
                await self.update_connection_status(is_connected=True)

                # 如果是重连（有断线时间记录），则触发对账
                if self.disconnect_time is not None:
                    disconnect_duration = int((datetime.now() - self.disconnect_time).total_seconds())
                    logger.info(
                        "Reconnected after disconnection, triggering reconciliation",
                        disconnect_duration=disconnect_duration,
                    )

                    try:
                        # 回溯时间为断线时长 + 额外缓冲时间（300秒）
                        lookback = max(disconnect_duration + 300, 600)  # 至少回溯10分钟
                        await self.reconciliation_service.reconcile_once(lookback_seconds=lookback)
                        logger.info("Reconnection reconciliation completed", lookback_seconds=lookback)
                    except Exception as e:
                        logger.error(
                            "Reconnection reconciliation failed",
                            error=str(e),
                            exc_info=True,
                        )

                    # 清除断线时间记录
                    self.disconnect_time = None

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
            logger.error("User data stream error", error=str(e), exc_info=True)

            # 记录断线
            await self.update_connection_status(is_connected=False)

            # 不要直接raise，而是尝试重连
            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect after error in 5 seconds...")
                await asyncio.sleep(5)
                await self.start()
            else:
                raise
        finally:
            # 安全取消 keepalive 任务（可能未创建）
            try:
                keepalive_task.cancel()
            except NameError:
                pass  # keepalive_task 未创建，忽略

            if self.listen_key:
                await self.close_listen_key(self.listen_key)
            await self.exchange.disconnect()
    
    async def stop(self):
        """停止用户数据流订阅."""
        self.is_running = False

        # 注意：不需要停止对账服务，因为我们使用按需对账而非定时对账

        if self.websocket:
            await self.websocket.close()
        logger.info("User data stream stopped")

