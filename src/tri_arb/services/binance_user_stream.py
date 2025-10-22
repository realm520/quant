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
from tri_arb.storage.models import AccountUpdate, OrderUpdate, TradeUpdate

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
            
            order = event.get("o", {})
            
            async with self.db_manager.session() as session:
                # 保存订单更新
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
            
            logger.info(
                "Order update saved",
                order_id=order.get("i"),
                symbol=order.get("s"),
                status=order.get("X"),
                side=order.get("S"),
            )
            
            # 如果有成交，保存成交记录
            if order.get("l") and Decimal(order.get("l", "0")) > 0:
                # 注意：Binance的trade ID在订单更新中不直接提供
                # 需要从trade stream获取，这里暂时用order_id作为标识
                async with self.db_manager.session() as session:
                    trade = TradeUpdate(
                        exchange="binance_perp",
                        event_type="TRADE",
                        event_time=event_time,
                        transaction_time=transaction_time,
                        symbol=order.get("s"),
                        order_id=int(order.get("i", 0)),
                        trade_id=int(order.get("t", 0)),  # trade ID
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
                
                logger.info(
                    "Trade saved",
                    order_id=order.get("i"),
                    symbol=order.get("s"),
                    quantity=order.get("l"),
                    price=order.get("L"),
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
            # 获取listen key
            self.listen_key = await self.get_listen_key()
            self.ws_url = f"wss://fstream.binance.com/ws/{self.listen_key}"
            
            logger.info("Starting user data stream", ws_url=self.ws_url)
            
            # 启动keepalive任务
            keepalive_task = asyncio.create_task(self.keepalive_task())
            
            # 连接WebSocket
            async with websockets.connect(self.ws_url) as websocket:
                self.websocket = websocket
                logger.info("WebSocket connected")
                
                # 接收消息循环
                async for message in websocket:
                    if not self.is_running:
                        break
                    
                    await self.process_message(message)
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect...")
                await asyncio.sleep(5)
                await self.start()
        except Exception as e:
            logger.error("User data stream error", error=str(e))
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

