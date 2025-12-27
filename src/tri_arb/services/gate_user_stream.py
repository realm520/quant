"""Gate.io User Data Stream WebSocket service.

Subscribe to Gate.io WebSocket user data stream for real-time account and order updates.
"""

import asyncio
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Literal

import websockets
from websockets.legacy.client import connect as ws_connect
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tri_arb.config.logging import get_logger
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.gate_models import (
    GateAccountBalance,
    GatePosition,
    GateOrder,
    GateTrade,
)
from tri_arb.storage.models import ConnectionStatus
from tri_arb.exchanges.gate_perp import GatePerpExchange
from tri_arb.services.gate_reconciliation import GateReconciliationService
from tri_arb.metrics.prometheus import ensure_metrics_server, update_order_metrics

logger = get_logger(__name__)
console = Console()


def _safe_float(value, default=0.0) -> float:
    """安全转换为float."""
    if value is None or value == "" or value == "null":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_decimal(value, default="0") -> Decimal:
    """安全转换为Decimal."""
    if value is None or value == "" or value == "null":
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

        # 创建 exchange 实例用于数据恢复
        self.exchange = GatePerpExchange(api_key=api_key, api_secret=api_secret)

        # 断线重连相关
        self.last_message_time: Optional[datetime] = None
        self.disconnect_time: Optional[datetime] = None

        # 对账服务（按需对账，仅在重连时触发）
        self.reconciliation_service = GateReconciliationService(
            exchange=self.exchange,
            db_manager=db_manager,
            poll_interval=60,  # 保留参数但不启动定时任务
            lookback_window=3600,  # 重连时回溯1小时
        )

        logger.info(
            "GateUserStreamService initialized",
            display_format=display_format,
            enabled_channels=list(self.enabled_channels),
            reconciliation_mode="on_reconnect",
        )

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
            self.api_secret.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha512
        ).hexdigest()

        headers = {
            "KEY": self.api_key,
            "Timestamp": timestamp,
            "SIGN": signature,
        }

        try:
            logger.debug(
                "Attempting to get Gate.io user_id",
                url=url,
                api_key=self.api_key[:8] + "...",
            )

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)

                logger.debug(
                    "Gate.io API response",
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

                if response.status_code != 200:
                    logger.error(
                        "Gate.io API returned non-200 status",
                        status_code=response.status_code,
                        response_text=response.text[:500],
                    )
                    self.user_id = 0
                    return 0

                data = response.json()
                logger.debug("Gate.io API response data", data=data)

                # 从响应中提取user_id
                # Gate.io账户数据中应该包含user字段
                if isinstance(data, dict) and "user" in data:
                    self.user_id = int(data["user"])
                    logger.info("Got Gate.io user_id", user_id=self.user_id)
                    return self.user_id
                elif isinstance(data, list) and len(data) > 0:
                    # 如果返回的是数组，尝试从第一个元素中获取user_id
                    first_item = data[0]
                    if isinstance(first_item, dict) and "user" in first_item:
                        self.user_id = int(first_item["user"])
                        logger.info(
                            "Got Gate.io user_id from array", user_id=self.user_id
                        )
                        return self.user_id

                # 如果没有user字段，尝试使用默认值
                logger.warning(
                    "Could not extract user_id from API response, using 0",
                    response_keys=(
                        list(data.keys()) if isinstance(data, dict) else "not_dict"
                    ),
                )
                self.user_id = 0
                return 0

        except httpx.TimeoutException as e:
            logger.error("Gate.io API timeout", error=str(e))
            self.user_id = 0
            return 0
        except httpx.HTTPStatusError as e:
            logger.error(
                "Gate.io API HTTP error",
                status_code=e.response.status_code,
                response_text=e.response.text[:500],
            )
            self.user_id = 0
            return 0
        except Exception as e:
            logger.error(
                "Failed to get user_id from futures API", error=str(e), exc_info=True
            )
            # 尝试备用方法
            return await self._get_user_id_fallback()

    async def _get_user_id_fallback(self) -> int:
        """备用的 user_id 获取方法，使用现货账户 API."""
        try:
            import httpx

            # 使用现货账户 API 作为备用
            url = "https://api.gateio.ws/api/v4/spot/accounts"
            timestamp = str(int(time.time()))

            # 生成签名
            query_string = ""
            body_hash = hashlib.sha512(b"").hexdigest()
            url_path = "/api/v4/spot/accounts"
            payload_str = f"GET\n{url_path}\n{query_string}\n{body_hash}\n{timestamp}"

            signature = hmac.new(
                self.api_secret.encode("utf-8"),
                payload_str.encode("utf-8"),
                hashlib.sha512,
            ).hexdigest()

            headers = {
                "KEY": self.api_key,
                "Timestamp": timestamp,
                "SIGN": signature,
            }

            logger.debug("Trying fallback method to get user_id", url=url)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    logger.debug("Fallback API response", data=data)

                    # 尝试从现货账户响应中提取 user_id
                    if isinstance(data, dict) and "user" in data:
                        self.user_id = int(data["user"])
                        logger.info(
                            "Got Gate.io user_id from fallback API",
                            user_id=self.user_id,
                        )
                        return self.user_id
                    elif isinstance(data, list) and len(data) > 0:
                        first_item = data[0]
                        if isinstance(first_item, dict) and "user" in first_item:
                            self.user_id = int(first_item["user"])
                            logger.info(
                                "Got Gate.io user_id from fallback array",
                                user_id=self.user_id,
                            )
                            return self.user_id

                logger.warning("Fallback method also failed to get user_id")
                self.user_id = 0
                return 0

        except Exception as e:
            logger.error("Fallback method failed", error=str(e))
            self.user_id = 0
            return 0

    def _generate_signature(
        self, channel: str, event: str, timestamp: int, payload: str = ""
    ) -> str:
        """生成Gate.io WebSocket签名.

        签名格式: channel={channel}&event={event}&time={timestamp}
        如果有payload，不包含在签名中
        """
        message = f"channel={channel}&event={event}&time={timestamp}"
        signature = hmac.new(
            self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha512
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
            try:
                user_id = await self._get_user_id()
                payload = [str(user_id), "!all"]  # user_id + !all(所有合约)
            except Exception as e:
                logger.warning(
                    "Failed to get user_id, using default payload", error=str(e)
                )
                # 如果无法获取 user_id，尝试使用默认值或跳过该频道
                payload = ["0", "!all"]  # 使用默认值

        subscribe_msg = {
            "time": timestamp,
            "channel": channel,
            "event": "subscribe",
            "auth": {"method": "api_key", "KEY": self.api_key, "SIGN": signature},
            "payload": payload,
        }

        logger.debug(
            "Sending Gate subscription",
            channel=channel,
            timestamp=timestamp,
            payload=payload,
        )
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

        logger.info(
            "All Gate channels subscribed", channels=list(self.enabled_channels)
        )

    def display_account_update(self, data: dict):
        """显示账户更新."""
        if self.display_format == "none":
            return

        if self.display_format == "json":
            console.print(
                Panel(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    title="[cyan]Gate.io 账户更新[/cyan]",
                    border_style="cyan",
                )
            )
            return

        # 表格显示
        result = data.get("result", [])
        if not result:
            return

        table = Table(
            title=f"💰 Gate.io账户余额 - {datetime.now().strftime('%H:%M:%S')}",
            box=box.ROUNDED,
        )
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
                update_type,
            )

        if table.row_count > 0:
            console.print(table)

    def display_position_update(self, data: dict):
        """显示持仓更新."""
        if self.display_format == "none":
            return

        if self.display_format == "json":
            console.print(
                Panel(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    title="[cyan]Gate.io 持仓更新[/cyan]",
                    border_style="cyan",
                )
            )
            return

        # 表格显示
        result = data.get("result", [])
        if not result:
            return

        table = Table(
            title=f"📊 Gate.io持仓更新 - {datetime.now().strftime('%H:%M:%S')}",
            box=box.ROUNDED,
        )
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
            mode_map = {"single": "单向", "dual": "双向"}
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
            pnl_str = (
                f"+{realised_pnl:.4f}" if realised_pnl > 0 else f"{realised_pnl:.4f}"
            )
            pnl_style = (
                "green" if realised_pnl > 0 else "red" if realised_pnl < 0 else "white"
            )

            close_pnl_str = (
                f"+{last_close_pnl:.4f}"
                if last_close_pnl > 0
                else f"{last_close_pnl:.4f}"
            )
            close_pnl_style = (
                "green"
                if last_close_pnl > 0
                else "red" if last_close_pnl < 0 else "white"
            )

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
                f"[{close_pnl_style}]{close_pnl_str}[/{close_pnl_style}]",
            )

        if table.row_count > 0:
            console.print(table)

    def display_order_update(self, data: dict):
        """显示订单更新."""
        if self.display_format == "none":
            return

        if self.display_format == "json":
            console.print(
                Panel(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    title="[cyan]Gate.io 订单更新[/cyan]",
                    border_style="cyan",
                )
            )
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
            role_display = (
                "Maker" if role == "maker" else "Taker" if role == "taker" else role
            )

            status = order.get("status", "")
            status_map = {
                "open": "🟢 挂单中",
                "finished": "✅ 已完成",
                "cancelled": "❌ 已取消",
            }
            status_display = status_map.get(status, status)

            # 创建订单表格
            table = Table(
                title=f"📝 Gate.io订单更新 - {datetime.now().strftime('%H:%M:%S')}",
                box=box.ROUNDED,
            )
            table.add_column("字段", style="cyan", width=12)
            table.add_column("值", style="white")

            table.add_row("订单ID", str(order_id))
            table.add_row("合约", contract)
            table.add_row("方向", f"[{side_style}]{side}[/{side_style}]")

            # Gate.io 通过 size 正负表示多空：正数=多，负数=空
            position_side = "LONG" if size > 0 else "SHORT" if size < 0 else "NET"
            position_color = (
                "bright_green"
                if position_side == "LONG"
                else "bright_red" if position_side == "SHORT" else "white"
            )
            table.add_row(
                "持仓方向（多空）",
                f"[{position_color}]{position_side}[/{position_color}]",
            )

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
                    logger.info(
                        "✅ Channel subscribed successfully",
                        channel=data.get("channel"),
                    )
                else:
                    logger.error(
                        "❌ Channel subscription failed",
                        channel=data.get("channel"),
                        error=data.get("error"),
                    )
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
                        unrealised_pnl=_safe_decimal(
                            balance.get("change")
                        ),  # 使用change字段
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
                    from sqlalchemy.dialects.postgresql import insert

                    # 准备订单数据
                    order_data = {
                        "order_id": str(order.get("id")),
                        "contract": order.get("contract"),
                        "size": _safe_decimal(order.get("size")),
                        "price": _safe_decimal(order.get("price")),
                        "left": _safe_decimal(order.get("left")),
                        "filled_total": _safe_decimal(order.get("fill_price")),
                        "status": order.get("status"),
                        "create_time": (
                            datetime.fromtimestamp(order.get("create_time", 0))
                            if order.get("create_time")
                            else None
                        ),
                        "finish_time": (
                            datetime.fromtimestamp(order.get("finish_time", 0))
                            if order.get("finish_time")
                            else None
                        ),
                        "update_time": datetime.utcnow(),
                        "reduce_only": order.get("reduce_only", False),
                        "tif": order.get("tif"),
                        "text": order.get("text"),
                        "raw_data": json.dumps(data),
                    }

                    # 使用 INSERT ... ON CONFLICT 处理重复的 order_id + update_time
                    stmt = insert(GateOrder).values(**order_data)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["order_id", "update_time"],
                        set_={
                            "contract": stmt.excluded.contract,
                            "size": stmt.excluded.size,
                            "price": stmt.excluded.price,
                            "left": stmt.excluded.left,
                            "filled_total": stmt.excluded.filled_total,
                            "status": stmt.excluded.status,
                            "create_time": stmt.excluded.create_time,
                            "finish_time": stmt.excluded.finish_time,
                            "reduce_only": stmt.excluded.reduce_only,
                            "tif": stmt.excluded.tif,
                            "text": stmt.excluded.text,
                            "raw_data": stmt.excluded.raw_data,
                        },
                    )
                    await session.execute(stmt)
                    await session.commit()

                    # 更新 Prometheus metrics
                    try:
                        # 订阅服务使用端口 9601
                        ensure_metrics_server(9601)
                        # Gate.io 通过 size 正负表示多空
                        order_with_position = order.copy()
                        order_with_position["positionSide"] = (
                            "LONG"
                            if _safe_float(order.get("size"), 0) > 0
                            else (
                                "SHORT"
                                if _safe_float(order.get("size"), 0) < 0
                                else "NET"
                            )
                        )
                        order_with_position["side"] = (
                            "BUY" if _safe_float(order.get("size"), 0) > 0 else "SELL"
                        )
                        update_order_metrics(
                            exchange="gate",
                            exchange_type="perp",
                            account_id="default",  # Gate.io 暂不支持多账号
                            order_data=order_with_position,
                        )
                    except Exception as metric_error:
                        logger.debug(f"Failed to update order metrics: {metric_error}")

            logger.info("Gate order update saved", count=len(result))
        except Exception as e:
            logger.error("Failed to save order update", error=str(e))

    async def get_or_create_connection_status(self) -> ConnectionStatus:
        """获取或创建连接状态记录.

        Returns:
            ConnectionStatus对象
        """
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(ConnectionStatus).where(ConnectionStatus.exchange == "gate_perp")
            )
            status = result.scalar_one_or_none()

            if status is None:
                status = ConnectionStatus(exchange="gate_perp")
                session.add(status)
                await session.commit()
                await session.refresh(status)
                logger.info("Created new connection status record for Gate")
            else:
                logger.info(
                    "Loaded existing Gate connection status",
                    last_order_time=status.last_order_event_time,
                    reconnect_count=status.total_reconnect_count,
                )

            return status

    async def update_connection_status(
        self,
        is_connected: bool,
        order_event_time: datetime | None = None,
        account_event_time: datetime | None = None,
    ):
        """更新连接状态.

        Args:
            is_connected: 是否已连接
            order_event_time: 订单事件时间
            account_event_time: 账户事件时间
        """
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(ConnectionStatus).where(ConnectionStatus.exchange == "gate_perp")
            )
            status = result.scalar_one_or_none()

            if status is None:
                status = ConnectionStatus(exchange="gate_perp")
                session.add(status)

            # 更新连接状态
            if is_connected:
                if not status.is_connected:
                    logger.info(
                        "Gate reconnecting after disconnection",
                        was_connected=status.is_connected,
                        last_disconnected_at=status.last_disconnected_at,
                    )
                    if status.last_disconnected_at:
                        gap_seconds = int(
                            (
                                datetime.now() - status.last_disconnected_at
                            ).total_seconds()
                        )
                        status.last_data_gap_seconds = gap_seconds
                        status.total_reconnect_count = (
                            status.total_reconnect_count or 0
                        ) + 1
                        logger.info(
                            "Gate reconnected after disconnection",
                            gap_seconds=gap_seconds,
                            total_reconnects=status.total_reconnect_count,
                        )

                status.last_connected_at = datetime.now()
                status.is_connected = True
            else:
                if status.is_connected:
                    status.last_disconnected_at = datetime.now()
                    logger.warning(
                        "Gate connection lost",
                        last_connected_at=status.last_connected_at,
                        disconnect_time=status.last_disconnected_at,
                    )
                status.is_connected = False

            # 更新事件时间戳
            if order_event_time:
                status.last_order_event_time = order_event_time
            if account_event_time:
                status.last_account_event_time = account_event_time

            await session.commit()

    async def query_missing_data(self, symbols: list[str] | None = None):
        """查询断线期间丢失的订单数据并补全到数据库.

        Args:
            symbols: 要查询的交易对列表，如["BTC_USDT", "ETH_USDT"]，None表示查询所有活跃交易对
        """
        logger.info("=== Starting Gate order data recovery process ===")

        # 确保 exchange 已连接
        await self.exchange.connect()

        # 获取连接状态
        status = await self.get_or_create_connection_status()

        if status.last_disconnected_at is None:
            logger.info("No Gate disconnection detected, skipping order data recovery")
            return

        # 计算查询时间范围
        start_time = status.last_disconnected_at
        end_time = datetime.now()
        gap_seconds = int((end_time - start_time).total_seconds())

        logger.info(
            "Gate order data recovery time range",
            start_time=start_time.strftime("%Y-%m-%d %H:%M:%S"),
            end_time=end_time.strftime("%Y-%m-%d %H:%M:%S"),
            gap_seconds=gap_seconds,
            gap_minutes=round(gap_seconds / 60, 2),
        )

        # 如果没有指定交易对，从数据库中获取最近活跃的交易对
        if symbols is None:
            symbols = await self._get_active_symbols()
            if not symbols:
                logger.warning(
                    "No active symbols found in Gate database (last 24 hours). "
                    "Order data recovery skipped."
                )
                return
            logger.info(f"Auto-detected {len(symbols)} active Gate symbols: {symbols}")
        else:
            logger.info(f"Using provided Gate symbols: {symbols}")

        if not symbols:
            logger.warning("No symbols to query for Gate order data recovery")
            return

        # 转换为秒级时间戳（Gate.io使用秒）
        start_time_sec = int(start_time.timestamp())
        end_time_sec = int(end_time.timestamp())

        total_orders = 0
        recovered_orders = 0

        # 对每个交易对查询订单数据
        for symbol in symbols:
            logger.info(f"Processing Gate symbol: {symbol}")
            try:
                # 查询订单
                logger.debug(f"Querying orders for {symbol}...")
                orders = await self.exchange.get_all_orders(
                    symbol=symbol,
                    start_time=start_time_sec,
                    end_time=end_time_sec,
                )

                logger.info(f"Retrieved {len(orders)} orders for {symbol}")
                total_orders += len(orders)

                # 保存订单到数据库（带去重）
                for order_data in orders:
                    saved = await self._save_order_with_dedup(order_data)
                    if saved:
                        recovered_orders += 1

            except Exception as e:
                logger.error(
                    f"Failed to query Gate order data for {symbol}",
                    error=str(e),
                    exc_info=True,
                )
                continue

        # 计算去重统计
        duplicate_orders = total_orders - recovered_orders

        logger.info(
            "=== Gate order data recovery completed ===",
            total_orders_retrieved=total_orders,
            new_orders_saved=recovered_orders,
            duplicate_orders_skipped=duplicate_orders,
            gap_seconds=gap_seconds,
            gap_minutes=round(gap_seconds / 60, 2),
        )

    async def _get_active_symbols(self) -> list[str]:
        """从数据库中获取最近活跃的交易对.

        Returns:
            交易对列表，如["BTC_USDT", "ETH_USDT"]
        """
        async with self.db_manager.session() as session:
            cutoff_time = datetime.now() - timedelta(hours=24)

            # 从Gate订单表获取
            result = await session.execute(
                select(GateOrder.contract)
                .where(GateOrder.update_time >= cutoff_time)
                .distinct()
            )
            symbols = [row[0] for row in result.fetchall()]

            if symbols:
                logger.info(
                    f"Found {len(symbols)} active Gate symbols in last 24 hours",
                    symbols=symbols,
                )
            else:
                logger.warning("No active Gate symbols found in last 24 hours")

            return symbols

    async def _save_order_with_dedup(self, order_data: dict) -> bool:
        """保存订单数据，自动去重.

        Args:
            order_data: Gate API返回的订单数据

        Returns:
            bool: True 表示新数据已保存，False 表示数据已存在（去重）
        """
        order_id = str(order_data.get("id", ""))
        finish_time = (
            datetime.fromtimestamp(order_data.get("finish_time", 0))
            if order_data.get("finish_time")
            else None
        )

        try:
            async with self.db_manager.session() as session:
                from sqlalchemy.dialects.postgresql import insert

                # 准备订单数据
                order_record = {
                    "order_id": order_id,
                    "contract": order_data.get("contract"),
                    "size": _safe_decimal(order_data.get("size")),
                    "price": _safe_decimal(order_data.get("price")),
                    "left": _safe_decimal(order_data.get("left")),
                    "filled_total": _safe_decimal(order_data.get("fill_price")),
                    "status": order_data.get("status"),
                    "create_time": (
                        datetime.fromtimestamp(order_data.get("create_time", 0))
                        if order_data.get("create_time")
                        else None
                    ),
                    "finish_time": finish_time,
                    "update_time": datetime.utcnow(),
                    "reduce_only": order_data.get("reduce_only", False),
                    "tif": order_data.get("tif"),
                    "text": order_data.get("text"),
                    "raw_data": json.dumps(order_data),
                }

                # 使用 INSERT ... ON CONFLICT 处理重复的 order_id + update_time
                stmt = insert(GateOrder).values(**order_record)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["order_id", "update_time"],
                    set_={
                        "contract": stmt.excluded.contract,
                        "size": stmt.excluded.size,
                        "price": stmt.excluded.price,
                        "left": stmt.excluded.left,
                        "filled_total": stmt.excluded.filled_total,
                        "status": stmt.excluded.status,
                        "create_time": stmt.excluded.create_time,
                        "finish_time": stmt.excluded.finish_time,
                        "reduce_only": stmt.excluded.reduce_only,
                        "tif": stmt.excluded.tif,
                        "text": stmt.excluded.text,
                        "raw_data": stmt.excluded.raw_data,
                    },
                )
                result = await session.execute(stmt)
                await session.commit()

                logger.debug(
                    "Saved recovered Gate order",
                    order_id=order_id,
                    contract=order_data.get("contract"),
                    status=order_data.get("status"),
                )
                return True
        except Exception as e:
            logger.debug(f"Gate order {order_id} save failed: {e}")
            return False

    async def _check_needs_recovery(
        self, status: ConnectionStatus
    ) -> tuple[bool, str, datetime | None]:
        """检查是否需要数据恢复.

        Args:
            status: 连接状态对象

        Returns:
            (需要恢复, 原因, 断线时间)
        """
        if status.last_disconnected_at is None:
            return False, "", None

        if not status.is_connected:
            return (
                True,
                "connection status shows disconnected",
                status.last_disconnected_at,
            )
        elif status.last_connected_at is None:
            return (
                True,
                "never connected but has disconnection record",
                status.last_disconnected_at,
            )
        elif status.last_disconnected_at > status.last_connected_at:
            return (
                True,
                "disconnection time is later than last connection time",
                status.last_disconnected_at,
            )

        return False, "", None

    async def _recover_data_with_retry(
        self, max_retries: int = 3, retry_delay: int = 2
    ):
        """带重试机制的订单数据恢复.

        Args:
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Attempting Gate order data recovery",
                    attempt=attempt,
                    max_retries=max_retries,
                )

                # 执行订单数据恢复
                await self.query_missing_data()
                logger.info(
                    "Gate order data recovery completed successfully", attempt=attempt
                )
                return

            except Exception as e:
                logger.warning(
                    "Gate order data recovery failed",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(e),
                )

                if attempt < max_retries:
                    logger.info(
                        f"Retrying Gate order data recovery in {retry_delay} seconds..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        "Gate order data recovery failed after all retries",
                        max_retries=max_retries,
                        error=str(e),
                    )

    async def start(self):
        """启动Gate.io用户数据流订阅."""
        self.is_running = True

        try:
            # 获取或创建连接状态记录
            status = await self.get_or_create_connection_status()

            # 检查是否需要数据恢复（但不立即执行）
            needs_recovery, recovery_reason, disconnect_time = (
                await self._check_needs_recovery(status)
            )

            if needs_recovery and disconnect_time:
                gap_seconds = int((datetime.now() - disconnect_time).total_seconds())
                logger.info(
                    "Detected previous Gate disconnection, will recover order data after WebSocket connection",
                    reason=recovery_reason,
                    last_disconnected_at=disconnect_time.strftime("%Y-%m-%d %H:%M:%S"),
                    last_connected_at=(
                        status.last_connected_at.strftime("%Y-%m-%d %H:%M:%S")
                        if status.last_connected_at
                        else "Never"
                    ),
                    gap_seconds=gap_seconds,
                    gap_minutes=round(gap_seconds / 60, 2),
                )
                self.disconnect_time = disconnect_time
            else:
                logger.info(
                    "No Gate order data recovery needed",
                    last_disconnected_at=(
                        status.last_disconnected_at.strftime("%Y-%m-%d %H:%M:%S")
                        if status.last_disconnected_at
                        else "Never"
                    ),
                    last_connected_at=(
                        status.last_connected_at.strftime("%Y-%m-%d %H:%M:%S")
                        if status.last_connected_at
                        else "Never"
                    ),
                )

            logger.info("Connecting to Gate WebSocket", url=self.ws_url)

            async with ws_connect(self.ws_url) as websocket:
                self.websocket = websocket
                logger.info("Gate WebSocket connected")

                # 订阅频道
                await self.subscribe_all_channels()

                # 更新连接状态
                await self.update_connection_status(is_connected=True)

                # 在WebSocket连接成功后执行订单数据恢复（如果需要）
                if needs_recovery and disconnect_time:
                    disconnect_duration = int(
                        (datetime.now() - disconnect_time).total_seconds()
                    )
                    logger.info(
                        "Reconnected after disconnection, triggering order data reconciliation",
                        disconnect_duration=disconnect_duration,
                    )

                    try:
                        # 回溯时间为断线时长 + 额外缓冲时间（300秒）
                        lookback = max(disconnect_duration + 300, 600)  # 至少回溯10分钟
                        await self.reconciliation_service.reconcile_once(
                            lookback_seconds=lookback
                        )
                        logger.info(
                            "Gate reconnection order data reconciliation completed",
                            lookback_seconds=lookback,
                        )
                    except Exception as e:
                        logger.error(
                            "Gate reconnection order data reconciliation failed",
                            error=str(e),
                            exc_info=True,
                        )

                    # 清除断线时间记录
                    self.disconnect_time = None

                # 接收消息循环
                async for message in websocket:
                    if not self.is_running:
                        break
                    await self.handle_message(message)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("Gate WebSocket connection closed")

            # 记录断线时间
            self.disconnect_time = datetime.now()
            await self.update_connection_status(is_connected=False)

            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect Gate in 5 seconds...")
                await asyncio.sleep(5)
                await self.start()
        except Exception as e:
            logger.error("Gate WebSocket error", error=str(e), exc_info=True)

            # 记录断线
            await self.update_connection_status(is_connected=False)

            # 不要直接raise，而是尝试重连
            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect Gate after error in 5 seconds...")
                await asyncio.sleep(5)
                await self.start()
            else:
                raise

    async def stop(self):
        """停止用户数据流订阅."""
        self.is_running = False

        # 注意：不需要停止对账服务，因为我们使用按需对账而非定时对账

        if self.websocket:
            await self.websocket.close()
        logger.info("Gate user data stream stopped")
