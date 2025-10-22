"""Gate.io User Data Stream WebSocket service.

Subscribe to Gate.io WebSocket user data stream for real-time account and order updates.
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Literal

import websockets
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from tri_arb.config.logging import get_logger
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.gate_models import GateAccountBalance, GatePosition, GateOrder, GateTrade

logger = get_logger(__name__)
console = Console()


def _safe_float(value, default=0.0) -> float:
    """安全转换为float."""
    if value is None or value == '' or value == 'null':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_decimal(value, default="0") -> Decimal:
    """安全转换为Decimal."""
    if value is None or value == '' or value == 'null':
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, Exception):
        return Decimal(default)


class GateUserStreamService:
    """Gate.io用户数据流订阅服务."""
    
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        db_manager: DatabaseManager,
        auto_reconnect: bool = True,
        display_format: Literal["table", "json", "none"] = "table",
        enabled_channels: list[str] | None = None,
        skip_duplicate_updates: bool = True,
    ):
        """初始化Gate.io用户数据流服务."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.db_manager = db_manager
        self.auto_reconnect = auto_reconnect
        self.display_format = display_format
        self.skip_duplicate_updates = skip_duplicate_updates
        
        # 设置启用的频道
        if enabled_channels is None:
            self.enabled_channels = {"account", "position", "order"}
        else:
            self.enabled_channels = set(enabled_channels)
        
        # Gate.io WebSocket URL
        self.ws_url = "wss://fx-ws.gateio.ws/v4/ws/usdt"
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False
        
        # 缓存数据用于检测变化
        self.last_account_data = None
        self.last_position_data = None
        
        # 用户ID（从REST API获取）
        self.user_id: Optional[int] = None
        
        logger.info("GateUserStreamService initialized",
                   display_format=display_format,
                   enabled_channels=list(self.enabled_channels))
    
    def _has_account_changed(self, data: dict) -> bool:
        """检查账户数据是否有变化."""
        if not self.skip_duplicate_updates:
            return True
        
        # 提取关键业务数据（使用Gate.io实际字段）
        account_snapshot = {}
        for balance in data.get("result", []):
            currency = balance.get("currency")
            account_snapshot[currency] = {
                "balance": balance.get("balance"),
                "change": balance.get("change"),
                "type": balance.get("type"),
            }
        
        current_data = json.dumps(account_snapshot, sort_keys=True)
        if self.last_account_data == current_data:
            return False
        
        self.last_account_data = current_data
        return True
    
    def _has_position_changed(self, data: dict) -> bool:
        """检查持仓数据是否有变化."""
        if not self.skip_duplicate_updates:
            return True
        
        # 提取关键业务数据
        position_snapshot = {}
        for pos in data.get("result", []):
            contract = pos.get("contract")
            position_snapshot[contract] = {
                "size": pos.get("size"),
                "entry_price": pos.get("entry_price"),
                "mark_price": pos.get("mark_price"),
                "unrealised_pnl": pos.get("unrealised_pnl"),
            }
        
        current_data = json.dumps(position_snapshot, sort_keys=True)
        if self.last_position_data == current_data:
            return False
        
        self.last_position_data = current_data
        return True
    
    async def _get_user_id(self) -> int:
        """通过REST API获取Gate.io用户ID.
        
        Returns:
            用户ID（整数）
        """
        if self.user_id is not None:
            return self.user_id
        
        import httpx
        
        # Gate.io REST API获取账户信息
        url = "https://api.gateio.ws/api/v4/futures/usdt/accounts"
        timestamp = str(int(time.time()))
        
        # 生成REST API签名
        query_string = ""
        body_hash = hashlib.sha512(b"").hexdigest()
        url_path = "/api/v4/futures/usdt/accounts"
        payload_str = f"GET\n{url_path}\n{query_string}\n{body_hash}\n{timestamp}"
        
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        headers = {
            "KEY": self.api_key,
            "Timestamp": timestamp,
            "SIGN": signature,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()
                
                # 从响应中提取user_id
                # Gate.io账户数据中应该包含user字段
                if isinstance(data, dict) and "user" in data:
                    self.user_id = int(data["user"])
                    logger.info("Got Gate.io user_id", user_id=self.user_id)
                    return self.user_id
                else:
                    # 如果没有user字段，尝试使用默认值
                    # 某些API可能不返回user_id，这种情况下使用0作为占位符
                    logger.warning("Could not extract user_id from API response, using 0")
                    self.user_id = 0
                    return 0
                    
        except Exception as e:
            logger.error("Failed to get user_id", error=str(e))
            # 使用0作为fallback
            self.user_id = 0
            return 0
    
    def _generate_signature(self, channel: str, event: str, timestamp: int, payload: str = "") -> str:
        """生成Gate.io WebSocket签名.
        
        签名格式: channel={channel}&event={event}&time={timestamp}
        如果有payload，不包含在签名中
        """
        message = f"channel={channel}&event={event}&time={timestamp}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        return signature
    
    async def subscribe_channel(self, channel: str):
        """订阅频道."""
        timestamp = int(time.time())
        
        # Gate.io的签名不包含payload
        signature = self._generate_signature(channel, "subscribe", timestamp)
        
        # 根据频道类型决定payload格式
        # Gate.io私有频道格式:
        # - futures.balances: ["USDT"] - 结算货币
        # - futures.positions: [user_id, "!all"] - user_id + 市场标识
        # - futures.orders: [user_id, "!all"] - user_id + 市场标识（!all表示所有合约）
        
        if "balances" in channel:
            # 账户余额频道使用结算货币
            payload = ["USDT"]
        else:
            # 持仓和订单频道需要user_id + 市场参数
            user_id = await self._get_user_id()
            payload = [str(user_id), "!all"]  # user_id + !all(所有合约)
        
        subscribe_msg = {
            "time": timestamp,
            "channel": channel,
            "event": "subscribe",
            "auth": {
                "method": "api_key",
                "KEY": self.api_key,
                "SIGN": signature
            },
            "payload": payload
        }
        
        logger.debug("Sending Gate subscription", 
                    channel=channel, 
                    timestamp=timestamp,
                    payload=payload)
        await self.websocket.send(json.dumps(subscribe_msg))
        logger.debug("Subscribed to Gate channel", channel=channel)
    
    async def subscribe_all_channels(self):
        """订阅所有启用的频道."""
        # Gate.io频道名称
        channel_mapping = {
            "account": "futures.balances",
            "position": "futures.positions",
            "order": "futures.orders",
        }
        
        for enabled in self.enabled_channels:
            if enabled in channel_mapping:
                await self.subscribe_channel(channel_mapping[enabled])
                await asyncio.sleep(0.1)  # 避免发送太快
        
        logger.info("All Gate channels subscribed",
                   channels=list(self.enabled_channels))
    
    def display_account_update(self, data: dict):
        """显示账户更新."""
        if self.display_format == "none":
            return
        
        if self.display_format == "json":
            console.print(Panel(
                json.dumps(data, indent=2, ensure_ascii=False),
                title="[cyan]Gate.io 账户更新[/cyan]",
                border_style="cyan"
            ))
            return
        
        # 表格显示
        result = data.get("result", [])
        if not result:
            return
        
        table = Table(title=f"💰 Gate.io账户余额 - {datetime.now().strftime('%H:%M:%S')}", box=box.ROUNDED)
        table.add_column("币种", style="cyan bold")
        table.add_column("余额", style="white", justify="right")
        table.add_column("变动", style="white", justify="right")
        table.add_column("类型", style="cyan", justify="left")
        
        for balance in result:
            currency = balance.get("currency", "")
            # Gate.io字段: balance, change, type
            balance_amount = _safe_float(balance.get("balance"), 0)
            change = _safe_float(balance.get("change"), 0)
            update_type = balance.get("type", "")
            
            if balance_amount == 0:
                continue
            
            change_str = f"+{change:.4f}" if change > 0 else f"{change:.4f}"
            change_style = "green" if change > 0 else "red" if change < 0 else "white"
            
            table.add_row(
                currency.upper(),
                f"{balance_amount:.4f}",
                f"[{change_style}]{change_str}[/{change_style}]",
                update_type
            )
        
        if table.row_count > 0:
            console.print(table)
    
    def display_position_update(self, data: dict):
        """显示持仓更新."""
        if self.display_format == "none":
            return
        
        if self.display_format == "json":
            console.print(Panel(
                json.dumps(data, indent=2, ensure_ascii=False),
                title="[cyan]Gate.io 持仓更新[/cyan]",
                border_style="cyan"
            ))
            return
        
        # 表格显示
        result = data.get("result", [])
        if not result:
            return
        
        table = Table(title=f"📊 Gate.io持仓更新 - {datetime.now().strftime('%H:%M:%S')}", box=box.ROUNDED)
        table.add_column("合约", style="cyan bold")
        table.add_column("方向", style="yellow", justify="center")
        table.add_column("持仓量", style="white", justify="right")
        table.add_column("开仓均价", style="white", justify="right")
        table.add_column("模式", style="cyan", justify="center")
        table.add_column("杠杆", style="yellow", justify="center")
        table.add_column("强平价", style="red", justify="right")
        table.add_column("已实现盈亏", style="white", justify="right")
        table.add_column("最后平仓", style="white", justify="right")
        
        for pos in result:
            size = _safe_float(pos.get("size"), 0)
            if size == 0:
                continue
            
            contract = pos.get("contract", "")
            # Gate.io用size正负表示方向
            side = "多" if size > 0 else "空"
            side_style = "green" if size > 0 else "red"
            
            # Gate.io字段:
            # - entry_price: 开仓均价
            # - leverage: 杠杆（全仓模式为0）
            # - leverage_max: 最大杠杆
            # - mode: single(单向)/dual(双向)
            # - margin: 保证金（全仓模式为0，因为是共享保证金）
            # - realised_pnl: 已实现盈亏
            # - last_close_pnl: 最后一次平仓盈亏
            entry_price = _safe_float(pos.get("entry_price"), 0)
            leverage = _safe_float(pos.get("leverage"), 0)
            leverage_max = _safe_float(pos.get("leverage_max"), 0)
            cross_leverage_limit = _safe_float(pos.get("cross_leverage_limit"), 0)
            realised_pnl = _safe_float(pos.get("realised_pnl"), 0)
            last_close_pnl = _safe_float(pos.get("last_close_pnl"), 0)
            liq_price = _safe_float(pos.get("liq_price"), 0)
            
            # 持仓模式
            mode = pos.get("mode", "")
            mode_map = {
                "single": "单向",
                "dual": "双向"
            }
            mode_display = mode_map.get(mode, mode)
            
            # 杠杆显示（leverage=0通常表示全仓模式）
            if leverage > 0:
                leverage_str = f"{leverage:.0f}x"
            elif cross_leverage_limit > 0:
                leverage_str = f"全仓{int(cross_leverage_limit)}x"
            elif leverage_max > 0:
                leverage_str = f"全仓(max {leverage_max:.0f}x)"
            else:
                leverage_str = "全仓"
            
            # 格式化盈亏
            pnl_str = f"+{realised_pnl:.4f}" if realised_pnl > 0 else f"{realised_pnl:.4f}"
            pnl_style = "green" if realised_pnl > 0 else "red" if realised_pnl < 0 else "white"
            
            close_pnl_str = f"+{last_close_pnl:.4f}" if last_close_pnl > 0 else f"{last_close_pnl:.4f}"
            close_pnl_style = "green" if last_close_pnl > 0 else "red" if last_close_pnl < 0 else "white"
            
            liq_str = f"{liq_price:.2f}" if liq_price > 0 else "N/A"
            
            table.add_row(
                contract,
                f"[{side_style}]{side}[/{side_style}]",
                f"{abs(size):.0f}",
                f"{entry_price:.4f}",
                mode_display,
                leverage_str,
                liq_str,
                f"[{pnl_style}]{pnl_str}[/{pnl_style}]",
                f"[{close_pnl_style}]{close_pnl_str}[/{close_pnl_style}]"
            )
        
        if table.row_count > 0:
            console.print(table)
    
    def display_order_update(self, data: dict):
        """显示订单更新."""
        if self.display_format == "none":
            return
        
        if self.display_format == "json":
            console.print(Panel(
                json.dumps(data, indent=2, ensure_ascii=False),
                title="[cyan]Gate.io 订单更新[/cyan]",
                border_style="cyan"
            ))
            return
        
        # 表格显示
        result = data.get("result", [])
        if not result:
            return
        
        for order in result:
            order_id = order.get("id", "")
            contract = order.get("contract", "")
            size = _safe_float(order.get("size"), 0)
            side = "买入" if size > 0 else "卖出"
            side_style = "green" if size > 0 else "red"
            
            # Gate.io字段:
            # - price: 限价（市价单为0）
            # - fill_price: 实际成交价格（已成交时）
            limit_price = _safe_float(order.get("price"), 0)
            fill_price = _safe_float(order.get("fill_price"), 0)
            display_price = fill_price if fill_price > 0 else limit_price
            
            left = _safe_float(order.get("left"), 0)
            filled = abs(size) - abs(left)
            fill_pct = (filled / abs(size) * 100) if size != 0 else 0
            
            # 订单类型
            tif = order.get("tif", "")
            tif_map = {
                "gtc": "GTC(持续有效)",
                "ioc": "IOC(立即成交)",
                "poc": "POC(被动委托)",
                "fok": "FOK(全部成交)",
            }
            order_type = tif_map.get(tif, tif.upper())
            
            # 手续费和角色
            fee = _safe_float(order.get("fee"), 0)
            role = order.get("role", "")
            role_display = "Maker" if role == "maker" else "Taker" if role == "taker" else role
            
            status = order.get("status", "")
            status_map = {
                "open": "🟢 挂单中",
                "finished": "✅ 已完成",
                "cancelled": "❌ 已取消",
            }
            status_display = status_map.get(status, status)
            
            # 创建订单表格
            table = Table(title=f"📝 Gate.io订单更新 - {datetime.now().strftime('%H:%M:%S')}", box=box.ROUNDED)
            table.add_column("字段", style="cyan", width=12)
            table.add_column("值", style="white")
            
            table.add_row("订单ID", str(order_id))
            table.add_row("合约", contract)
            table.add_row("方向", f"[{side_style}]{side}[/{side_style}]")
            table.add_row("类型", order_type)
            
            # 价格显示逻辑
            if fill_price > 0:
                table.add_row("成交价", f"[green]{fill_price:.4f}[/green]")
                if limit_price > 0 and limit_price != fill_price:
                    table.add_row("限价", f"{limit_price:.4f}")
            elif limit_price > 0:
                table.add_row("限价", f"{limit_price:.4f}")
            else:
                table.add_row("价格", "市价")
            
            table.add_row("数量", f"{abs(size):.0f}")
            table.add_row("已成交", f"{filled:.0f} ({fill_pct:.1f}%)")
            table.add_row("剩余", f"{abs(left):.0f}")
            
            if fee > 0:
                table.add_row("手续费", f"[yellow]{fee:.6f} USDT[/yellow]")
            if role:
                table.add_row("角色", role_display)
            
            table.add_row("状态", status_display)
            
            console.print(table)
    
    async def handle_message(self, message: str):
        """处理WebSocket消息."""
        try:
            data = json.loads(message)
            logger.debug("Gate message received", data=data)
            
            # 处理订阅响应
            if data.get("event") == "subscribe":
                status = data.get("result", {}).get("status", "unknown")
                if status == "success":
                    logger.info("✅ Channel subscribed successfully", channel=data.get("channel"))
                else:
                    logger.error("❌ Channel subscription failed", 
                                channel=data.get("channel"), 
                                error=data.get("error"))
                return
            
            # 处理数据推送
            channel = data.get("channel", "")
            
            if "futures.balances" in channel and "account" in self.enabled_channels:
                if self._has_account_changed(data):
                    self.display_account_update(data)
                    await self.save_account_update(data)
                else:
                    logger.debug("Account data unchanged, skipping")
                
            elif "futures.positions" in channel and "position" in self.enabled_channels:
                if self._has_position_changed(data):
                    self.display_position_update(data)
                    await self.save_position_update(data)
                else:
                    logger.debug("Position data unchanged, skipping")
                
            elif "futures.orders" in channel and "order" in self.enabled_channels:
                # 订单更新通常都是重要的，不跳过
                self.display_order_update(data)
                await self.save_order_update(data)
        
        except json.JSONDecodeError as e:
            logger.error("Failed to decode message", error=str(e))
        except Exception as e:
            logger.error("Failed to handle message", error=str(e))
    
    async def save_account_update(self, data: dict):
        """保存账户更新."""
        try:
            result = data.get("result", [])
            for balance in result:
                async with self.db_manager.session() as session:
                    # Gate.io字段映射:
                    # balance -> total (余额)
                    # change -> available (变动，暂存到available字段)
                    # 没有unrealised_pnl字段
                    balance_amount = _safe_decimal(balance.get("balance"))
                    
                    record = GateAccountBalance(
                        update_time=datetime.utcnow(),
                        user_id=int(balance.get("user", 0)),
                        currency=balance.get("currency"),
                        total=balance_amount,
                        available=balance_amount,  # Gate.io没有分离的available
                        unrealised_pnl=_safe_decimal(balance.get("change")),  # 使用change字段
                        raw_data=json.dumps(data),
                    )
                    session.add(record)
            logger.info("Gate account update saved")
        except Exception as e:
            logger.error("Failed to save account update", error=str(e))
    
    async def save_position_update(self, data: dict):
        """保存持仓更新."""
        try:
            result = data.get("result", [])
            for pos in result:
                async with self.db_manager.session() as session:
                    record = GatePosition(
                        update_time=datetime.utcnow(),
                        contract=pos.get("contract"),
                        size=_safe_decimal(pos.get("size")),
                        leverage=_safe_decimal(pos.get("leverage")),
                        margin=_safe_decimal(pos.get("margin")),
                        entry_price=_safe_decimal(pos.get("entry_price")),
                        mark_price=_safe_decimal(pos.get("mark_price")),
                        liq_price=_safe_decimal(pos.get("liq_price")),
                        unrealised_pnl=_safe_decimal(pos.get("unrealised_pnl")),
                        realised_pnl=_safe_decimal(pos.get("realised_pnl")),
                        mode=pos.get("mode"),
                        raw_data=json.dumps(data),
                    )
                    session.add(record)
            logger.info("Gate position update saved", count=len(result))
        except Exception as e:
            logger.error("Failed to save position update", error=str(e))
    
    async def save_order_update(self, data: dict):
        """保存订单更新."""
        try:
            result = data.get("result", [])
            for order in result:
                async with self.db_manager.session() as session:
                    record = GateOrder(
                        order_id=str(order.get("id")),
                        contract=order.get("contract"),
                        size=_safe_decimal(order.get("size")),
                        price=_safe_decimal(order.get("price")),
                        left=_safe_decimal(order.get("left")),
                        filled_total=_safe_decimal(order.get("fill_price")),
                        status=order.get("status"),
                        create_time=datetime.fromtimestamp(order.get("create_time", 0)) if order.get("create_time") else None,
                        finish_time=datetime.fromtimestamp(order.get("finish_time", 0)) if order.get("finish_time") else None,
                        update_time=datetime.utcnow(),
                        reduce_only=order.get("reduce_only", False),
                        tif=order.get("tif"),
                        text=order.get("text"),
                        raw_data=json.dumps(data),
                    )
                    session.add(record)
            logger.info("Gate order update saved", count=len(result))
        except Exception as e:
            logger.error("Failed to save order update", error=str(e))
    
    async def start(self):
        """启动Gate.io用户数据流订阅."""
        self.is_running = True
        
        try:
            logger.info("Connecting to Gate WebSocket", url=self.ws_url)
            
            async with websockets.connect(self.ws_url) as websocket:
                self.websocket = websocket
                logger.info("Gate WebSocket connected")
                
                # 订阅频道
                await self.subscribe_all_channels()
                
                # 接收消息循环
                async for message in websocket:
                    if not self.is_running:
                        break
                    await self.handle_message(message)
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Gate WebSocket connection closed")
            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect...")
                await asyncio.sleep(5)
                await self.start()
        except Exception as e:
            logger.error("Gate WebSocket error", error=str(e))
            raise
    
    async def stop(self):
        """停止用户数据流订阅."""
        self.is_running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("Gate user data stream stopped")

