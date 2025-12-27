"""OKX User Data Stream WebSocket service.

Subscribe to OKX WebSocket user data stream for real-time account and order updates.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Literal

from websockets import exceptions as ws_exceptions
from websockets.legacy.client import connect as ws_connect, WebSocketClientProtocol
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tri_arb.config.logging import get_logger
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.okx_models import (
    OKXAccountBalance,
    OKXPosition,
    OKXOrder,
    OKXTrade,
)
from tri_arb.storage.models import ConnectionStatus
from tri_arb.exchanges.okx_perp import OKXPerpExchange
from tri_arb.services.okx_reconciliation import OKXReconciliationService
from tri_arb.metrics.prometheus import ensure_metrics_server, update_order_metrics

logger = get_logger(__name__)
console = Console()


def _safe_float(value, default=0.0) -> float:
    """安全转换为float，处理空字符串和None.

    Args:
        value: 要转换的值
        default: 默认值

    Returns:
        转换后的float值
    """
    if value is None or value == "" or value == "null":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _safe_decimal(value, default="0") -> Decimal:
    """安全转换为Decimal，处理空字符串和None.

    Args:
        value: 要转换的值
        default: 默认值

    Returns:
        转换后的Decimal值
    """
    if value is None or value == "" or value == "null":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, Exception):
        return Decimal(default)


def _safe_json_dumps(data) -> str:
    """安全的JSON序列化，处理Decimal类型.

    Args:
        data: 要序列化的数据

    Returns:
        JSON字符串
    """

    def decimal_default(obj):
        if isinstance(obj, Decimal):
            return str(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return json.dumps(data, default=decimal_default)


class OKXUserStreamService:
    """OKX用户数据流订阅服务.

    订阅OKX WebSocket用户数据流，接收账户更新、订单更新和成交信息。
    将接收到的数据存储到PostgreSQL数据库。
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        db_manager: DatabaseManager,
        auto_reconnect: bool = True,
        display_format: Literal["table", "json", "none"] = "table",
        inst_type: str = "SWAP",  # SWAP, FUTURES, SPOT
        skip_duplicate_updates: bool = True,  # 跳过重复的快照更新
        enabled_channels: list[str] | None = None,
    ):
        """初始化OKX用户数据流服务.

        Args:
            api_key: OKX API key
            api_secret: OKX API secret
            passphrase: OKX API passphrase
            db_manager: 数据库管理器
            auto_reconnect: 是否自动重连
            display_format: 显示格式 (table/json/none)
            inst_type: 产品类型 (SWAP/FUTURES/SPOT)
            skip_duplicate_updates: 跳过重复的快照更新（OKX每5秒推送一次）
            enabled_channels: 启用的频道列表，如["account", "position"]，None表示全部
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.db_manager = db_manager
        self.auto_reconnect = auto_reconnect
        self.display_format = display_format
        self.inst_type = inst_type
        self.skip_duplicate_updates = skip_duplicate_updates

        # 设置启用的频道
        if enabled_channels is None:
            self.enabled_channels = {"account", "position", "order"}
        else:
            self.enabled_channels = set(enabled_channels)

        # OKX WebSocket URL (私有频道)
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/private"
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.is_running = False

        # 缓存上次的账户和持仓数据，用于检测变化
        self.last_account_data = None
        self.last_position_data = None

        # 创建 exchange 实例用于数据恢复
        self.exchange = OKXPerpExchange(
            api_key=api_key, api_secret=api_secret, passphrase=passphrase
        )

        # 断线重连相关
        self.last_message_time: Optional[datetime] = None
        self.disconnect_time: Optional[datetime] = None

        # 后台任务
        self._monitor_task: Optional[asyncio.Task] = None

        # 对账服务（按需对账，仅在重连时触发）
        self.reconciliation_service = OKXReconciliationService(
            exchange=self.exchange,
            db_manager=db_manager,
            poll_interval=0,  # 只在断线恢复时手动触发
            lookback_window=7200,  # 默认回溯2小时
        )

        logger.info(
            "OKXUserStreamService initialized",
            display_format=display_format,
            inst_type=inst_type,
            skip_duplicate_updates=skip_duplicate_updates,
            enabled_channels=list(self.enabled_channels),
            reconciliation_mode="on_reconnect",
        )

    def _generate_signature(
        self, timestamp: str, method: str, request_path: str
    ) -> str:
        """生成OKX WebSocket认证签名.

        Args:
            timestamp: ISO 8601时间戳
            method: HTTP方法（WebSocket用GET）
            request_path: 请求路径（WebSocket用/users/self/verify）

        Returns:
            Base64编码的签名
        """
        # 构造签名消息
        message = timestamp + method + request_path

        # HMAC-SHA256签名
        mac = hmac.new(
            self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        )

        # Base64编码
        signature = base64.b64encode(mac.digest()).decode("utf-8")

        return signature

    def _get_timestamp(self) -> str:
        """获取OKX要求格式的时间戳.

        Returns:
            Unix时间戳字符串（秒，带小数），例如: 1729497614.558
        """
        # OKX要求: Unix时间戳（秒）
        # JavaScript示例: const timestamp = '' + Date.now() / 1000
        timestamp = str(time.time())
        return timestamp

    async def login(self):
        """WebSocket登录认证."""
        # 获取OKX标准格式的时间戳
        timestamp = self._get_timestamp()
        method = "GET"
        request_path = "/users/self/verify"

        signature = self._generate_signature(timestamp, method, request_path)

        logger.debug(
            "OKX login attempt",
            timestamp=timestamp,
            method=method,
            path=request_path,
            api_key=self.api_key[:8] + "...",
        )

        login_msg = {
            "op": "login",
            "args": [
                {
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": signature,
                }
            ],
        }

        logger.debug("Sending login message", message=login_msg)
        await self.websocket.send(json.dumps(login_msg))

        # 等待登录响应
        response = await self.websocket.recv()
        data = json.loads(response)

        if data.get("event") == "login" and data.get("code") == "0":
            logger.info("OKX WebSocket login successful")
            return True
        else:
            error_msg = data.get("msg", "Unknown error")
            error_code = data.get("code", "Unknown")
            logger.error(
                "OKX WebSocket login failed",
                error_code=error_code,
                error_msg=error_msg,
                timestamp_used=timestamp,
                response=data,
            )

            # 如果是时间戳错误，提供帮助信息
            if error_code == "60004":
                logger.warning("Timestamp error detected. Please ensure:")
                logger.warning("1. Your system time is synchronized (use NTP)")
                logger.warning("2. System time difference with OKX server < 30 seconds")
                logger.warning(f"3. Current timestamp format: {timestamp}")

            return False

    async def subscribe_channels(self):
        """订阅用户数据频道（根据enabled_channels选择性订阅）."""
        channels = []

        # 根据enabled_channels添加频道
        if "account" in self.enabled_channels:
            channels.append(
                {
                    "channel": "account",
                    "ccy": "USDT",  # 可以订阅特定币种或不指定订阅所有
                }
            )

        if "position" in self.enabled_channels:
            channels.append({"channel": "positions", "instType": self.inst_type})

        if "order" in self.enabled_channels:
            channels.append({"channel": "orders", "instType": self.inst_type})

        if not channels:
            logger.warning("No channels to subscribe")
            return

        subscribe_msg = {"op": "subscribe", "args": channels}

        await self.websocket.send(json.dumps(subscribe_msg))
        logger.info(
            "Subscribed to OKX channels",
            channels=[c["channel"] for c in channels],
            count=len(channels),
        )

    def _has_account_changed(self, data: dict) -> bool:
        """检测账户数据是否有变化.

        只对比关键业务数据（余额），忽略时间戳等元数据。

        Args:
            data: 新的账户数据

        Returns:
            True表示数据有变化，False表示无变化
        """
        if not self.skip_duplicate_updates:
            return True  # 不跳过重复更新

        # 提取关键业务数据：各币种的余额
        account_snapshot = {}
        account_data = data.get("data", [])

        for account in account_data:
            details = account.get("details", [])
            for detail in details:
                ccy = detail.get("ccy")
                # 只对比关键字段：可用余额、权益、未实现盈亏
                account_snapshot[ccy] = {
                    "availBal": detail.get("availBal"),
                    "eq": detail.get("eq"),
                    "upl": detail.get("upl"),
                    "frozenBal": detail.get("frozenBal"),
                }

        current_data = json.dumps(account_snapshot, sort_keys=True)

        if self.last_account_data == current_data:
            return False  # 数据未变化

        self.last_account_data = current_data
        return True  # 数据有变化

    def _has_position_changed(self, data: dict) -> bool:
        """检测持仓数据是否有变化.

        只对比关键业务数据（持仓量、均价、盈亏），忽略时间戳等元数据。

        Args:
            data: 新的持仓数据

        Returns:
            True表示数据有变化，False表示无变化
        """
        if not self.skip_duplicate_updates:
            return True  # 不跳过重复更新

        # 提取关键业务数据：各产品的持仓
        position_snapshot = {}
        positions = data.get("data", [])

        for pos in positions:
            inst_id = pos.get("instId")
            pos_side = pos.get("posSide")
            key = f"{inst_id}_{pos_side}"

            # 只对比关键字段：持仓量、均价、盈亏
            position_snapshot[key] = {
                "pos": pos.get("pos"),
                "avgPx": pos.get("avgPx"),
                "upl": pos.get("upl"),
                "uplRatio": pos.get("uplRatio"),
                "margin": pos.get("margin"),
            }

        current_data = json.dumps(position_snapshot, sort_keys=True)

        if self.last_position_data == current_data:
            return False  # 数据未变化

        self.last_position_data = current_data
        return True  # 数据有变化

    def display_account_update(self, data: dict):
        """显示账户更新信息.

        Args:
            data: 账户更新数据
        """
        if self.display_format == "none":
            return

        if self.display_format == "json":
            console.print(
                Panel(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    title="[cyan]OKX 账户更新 (account)[/cyan]",
                    border_style="cyan",
                )
            )
            return

        # 表格显示
        arg = data.get("arg", {})
        account_data = data.get("data", [])

        if not account_data:
            return

        for account in account_data:
            # 账户总览信息
            total_eq = _safe_float(account.get("totalEq"), 0)
            iso_eq = _safe_float(account.get("isoEq"), 0)
            adj_eq = _safe_float(account.get("adjEq"), 0)

            details = account.get("details", [])
            if not details:
                continue

            # 创建账户总览表
            overview_table = Table(
                title=f"💰 OKX账户总览 - {datetime.now().strftime('%H:%M:%S')}",
                box=box.ROUNDED,
                show_header=False,
            )
            overview_table.add_column("", style="cyan", justify="left")
            overview_table.add_column("", style="green bold", justify="right")

            overview_table.add_row("总权益(USD)", f"{total_eq:.2f}")
            if iso_eq > 0:
                overview_table.add_row("逐仓权益", f"{iso_eq:.2f}")
            if adj_eq > 0:
                overview_table.add_row("调整后权益", f"{adj_eq:.2f}")

            console.print(overview_table)

            # 创建币种详情表
            detail_table = Table(title=f"💵 币种余额详情", box=box.ROUNDED)
            detail_table.add_column("币种", style="cyan bold", justify="center")
            detail_table.add_column("权益", style="white", justify="right")
            detail_table.add_column("可用余额", style="green", justify="right")
            detail_table.add_column("冻结余额", style="yellow", justify="right")
            detail_table.add_column("未实现盈亏", style="white", justify="right")
            detail_table.add_column("现金余额", style="white", justify="right")

            for detail in details:
                ccy = detail.get("ccy", "")
                eq = _safe_float(detail.get("eq"), 0)
                avail_bal = _safe_float(detail.get("availBal"), 0)
                frozen_bal = _safe_float(detail.get("frozenBal"), 0)
                upl = _safe_float(detail.get("upl"), 0)
                cash_bal = _safe_float(detail.get("cashBal"), 0)

                if eq == 0 and avail_bal == 0:
                    continue

                # 盈亏颜色
                upl_str = f"+{upl:.4f}" if upl > 0 else f"{upl:.4f}"
                upl_style = "green" if upl > 0 else "red" if upl < 0 else "white"

                detail_table.add_row(
                    ccy,
                    f"{eq:.4f}",
                    f"{avail_bal:.4f}",
                    f"{frozen_bal:.4f}",
                    f"[{upl_style}]{upl_str}[/{upl_style}]",
                    f"{cash_bal:.4f}",
                )

            if detail_table.row_count > 0:
                console.print(detail_table)

    def display_position_update(self, data: dict):
        """显示持仓更新信息.

        Args:
            data: 持仓更新数据
        """
        if self.display_format == "none":
            return

        if self.display_format == "json":
            console.print(
                Panel(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    title="[cyan]OKX 持仓更新 (positions)[/cyan]",
                    border_style="cyan",
                )
            )
            return

        # 表格显示
        positions = data.get("data", [])
        if not positions:
            return

        table = Table(
            title=f"📊 OKX持仓更新 - {datetime.now().strftime('%H:%M:%S')}",
            box=box.ROUNDED,
        )
        table.add_column("产品", style="cyan bold", justify="center")
        table.add_column("方向", style="yellow", justify="center")
        table.add_column("持仓量", style="white", justify="right")
        table.add_column("开仓均价", style="white", justify="right")
        table.add_column("标记价格", style="cyan", justify="right")
        table.add_column("强平价", style="red", justify="right")
        table.add_column("未实现盈亏", style="white", justify="right")
        table.add_column("收益率", style="white", justify="right")
        table.add_column("保证金", style="magenta", justify="right")
        table.add_column("杠杆", style="yellow", justify="center")

        for pos in positions:
            pos_qty = _safe_float(pos.get("pos"), 0)
            if pos_qty == 0:
                continue

            inst_id = pos.get("instId", "")
            pos_side = pos.get("posSide", "")
            avg_px = _safe_float(pos.get("avgPx"), 0)
            mark_px = _safe_float(pos.get("markPx"), 0)
            liq_px = _safe_float(pos.get("liqPx"), 0)
            upl = _safe_float(pos.get("upl"), 0)
            upl_ratio = _safe_float(pos.get("uplRatio"), 0)
            margin = _safe_float(pos.get("margin"), 0)
            lever = _safe_float(pos.get("lever"), 0)

            # 盈亏显示
            upl_str = f"+{upl:.4f}" if upl > 0 else f"{upl:.4f}"
            upl_style = "green" if upl > 0 else "red" if upl < 0 else "white"

            # 收益率显示
            ratio_str = (
                f"+{upl_ratio*100:.2f}%" if upl_ratio > 0 else f"{upl_ratio*100:.2f}%"
            )
            ratio_style = (
                "green" if upl_ratio > 0 else "red" if upl_ratio < 0 else "white"
            )

            # 强平价显示（如果接近当前价格，显示警告）
            liq_str = f"{liq_px:.4f}" if liq_px > 0 else "N/A"
            if liq_px > 0 and mark_px > 0:
                liq_distance = abs(liq_px - mark_px) / mark_px
                if liq_distance < 0.1:  # 距离强平价<10%
                    liq_str = f"[red bold]{liq_px:.4f} ⚠️[/red bold]"

            table.add_row(
                inst_id,
                pos_side.upper(),
                f"{pos_qty}",
                f"{avg_px:.4f}",
                f"{mark_px:.4f}",
                liq_str,
                f"[{upl_style}]{upl_str}[/{upl_style}]",
                f"[{ratio_style}]{ratio_str}[/{ratio_style}]",
                f"{margin:.4f}",
                f"{lever:.0f}x",
            )

        if table.row_count > 0:
            console.print(table)

    def display_order_update(self, data: dict):
        """显示订单更新信息.

        Args:
            data: 订单更新数据
        """
        if self.display_format == "none":
            return

        if self.display_format == "json":
            console.print(
                Panel(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    title="[yellow]OKX 订单更新 (orders)[/yellow]",
                    border_style="yellow",
                )
            )
            return

        # 表格显示
        orders = data.get("data", [])
        if not orders:
            return

        for order in orders:
            state = order.get("state", "")

            # 状态颜色
            status_colors = {
                "live": "blue",
                "partially_filled": "yellow",
                "filled": "green",
                "canceled": "red",
            }
            status_color = status_colors.get(state, "white")

            table = Table(
                title=f"📝 OKX订单更新 - {datetime.now().strftime('%H:%M:%S')}",
                box=box.ROUNDED,
            )
            table.add_column("字段", style="cyan", justify="left", width=15)
            table.add_column("值", style="white", justify="left")

            # 基本信息
            table.add_row("产品", order.get("instId", ""))
            table.add_row("订单ID", order.get("ordId", ""))

            # 客户订单ID（如果有）
            if order.get("clOrdId"):
                table.add_row("客户订单ID", order.get("clOrdId", ""))

            table.add_row("状态", f"[{status_color}]{state.upper()}[/{status_color}]")

            # 订单详情
            side = order.get("side", "")
            side_color = "green" if side == "buy" else "red"
            table.add_row("方向", f"[{side_color}]{side.upper()}[/{side_color}]")
            table.add_row("类型", order.get("ordType", "").upper())

            # 持仓方向（多空）- 高亮显示
            position_side = order.get("posSide", "NET")
            if position_side:
                position_color = (
                    "bright_green"
                    if position_side.upper() == "LONG"
                    else "bright_red" if position_side.upper() == "SHORT" else "white"
                )
                table.add_row(
                    "持仓方向（多空）",
                    f"[{position_color}]{position_side.upper()}[/{position_color}]",
                )
            table.add_row("交易模式", order.get("tdMode", "").upper())

            # 价格和数量
            px = _safe_float(order.get("px"), 0)
            sz = _safe_float(order.get("sz"), 0)
            acc_fill = _safe_float(order.get("accFillSz"), 0)

            table.add_row("委托价格", f"{px:.4f}" if px > 0 else "市价")
            table.add_row("委托数量", f"{sz:.8f}")
            table.add_row("已成交数量", f"{acc_fill:.8f}")

            # 成交进度
            if sz > 0:
                fill_percent = (acc_fill / sz) * 100
                fill_bar = "█" * int(fill_percent / 10) + "░" * (
                    10 - int(fill_percent / 10)
                )
                table.add_row("成交进度", f"{fill_bar} {fill_percent:.1f}%")

            # 平均成交价
            avg_px = _safe_float(order.get("avgPx"), 0)
            if avg_px > 0:
                table.add_row("平均成交价", f"{avg_px:.4f}")

                # 如果有委托价，显示滑点
                if px > 0:
                    slippage = ((avg_px - px) / px) * 100
                    slippage_str = f"{slippage:+.4f}%"
                    slippage_style = "red" if abs(slippage) > 0.1 else "green"
                    table.add_row(
                        "滑点", f"[{slippage_style}]{slippage_str}[/{slippage_style}]"
                    )

            # 最后成交
            last_fill_sz = _safe_float(order.get("fillSz"), 0)
            last_fill_px = _safe_float(order.get("fillPx"), 0)
            if last_fill_sz > 0:
                table.add_row("最后成交量", f"{last_fill_sz:.8f}")
                table.add_row("最后成交价", f"{last_fill_px:.4f}")

            # 手续费和返佣
            fee = _safe_float(order.get("fee"), 0)
            if fee != 0:
                fee_str = f"{abs(fee):.8f} {order.get('feeCcy', '')}"
                table.add_row("手续费", fee_str)

            rebate = _safe_float(order.get("rebate"), 0)
            if rebate != 0:
                rebate_str = f"{abs(rebate):.8f} {order.get('rebateCcy', '')}"
                table.add_row("返佣", f"[green]{rebate_str}[/green]")

            # 时间信息
            if order.get("cTime"):
                c_time = datetime.fromtimestamp(int(order.get("cTime")) / 1000)
                table.add_row("创建时间", c_time.strftime("%Y-%m-%d %H:%M:%S"))

            if order.get("uTime"):
                u_time = datetime.fromtimestamp(int(order.get("uTime")) / 1000)
                table.add_row("更新时间", u_time.strftime("%Y-%m-%d %H:%M:%S"))

            # 只减仓标识
            if order.get("reduceOnly") == "true":
                table.add_row("只减仓", "[yellow]是[/yellow]")

            console.print(table)

            # 如果完全成交，显示成交摘要
            if state == "filled" and avg_px > 0 and acc_fill > 0:
                trade_value = acc_fill * avg_px
                fee_total = abs(fee) if fee != 0 else 0
                net_value = trade_value - fee_total

                console.print(f"[green]✅ 订单完全成交[/green]")
                console.print(f"   成交: {acc_fill:.8f} @ {avg_px:.4f}")
                console.print(f"   金额: {trade_value:.4f} USDT")
                if fee_total > 0:
                    console.print(
                        f"   手续费: -{fee_total:.4f} {order.get('feeCcy', '')}"
                    )
                if rebate != 0:
                    console.print(
                        f"   返佣: +{abs(rebate):.4f} {order.get('rebateCcy', '')}"
                    )

    def _display_recovered_order(self, order_data: dict):
        """显示恢复的订单（数据恢复时使用）.

        Args:
            order_data: OKX API 返回的订单数据
        """
        if self.display_format == "none":
            return

        state = order_data.get("state", "")
        status_colors = {
            "live": "blue",
            "partially_filled": "yellow",
            "filled": "green",
            "canceled": "red",
        }
        status_color = status_colors.get(state, "white")

        table = Table(
            title=f"🔄 [bold cyan]恢复订单[/bold cyan] - {datetime.now().strftime('%H:%M:%S')}",
            box=box.ROUNDED,
        )
        table.add_column("字段", style="cyan", justify="left", width=15)
        table.add_column("值", style="white", justify="left")

        # 基本信息
        table.add_row("产品", order_data.get("instId", ""))
        table.add_row("订单ID", order_data.get("ordId", ""))
        table.add_row("状态", f"[{status_color}]{state.upper()}[/{status_color}]")

        # 订单详情
        side = order_data.get("side", "")
        side_color = "green" if side == "buy" else "red"
        table.add_row("方向", f"[{side_color}]{side.upper()}[/{side_color}]")
        table.add_row("类型", order_data.get("ordType", "").upper())

        # 价格和数量
        px = _safe_float(order_data.get("px"), 0)
        sz = _safe_float(order_data.get("sz"), 0)
        acc_fill = _safe_float(order_data.get("accFillSz"), 0)

        table.add_row("委托价格", f"{px:.4f}" if px > 0 else "市价")
        table.add_row("委托数量", f"{sz:.8f}")
        table.add_row("已成交", f"{acc_fill:.8f}")

        # 平均成交价
        avg_px = _safe_float(order_data.get("avgPx"), 0)
        if avg_px > 0:
            table.add_row("平均价", f"{avg_px:.4f}")

        # 时间
        u_time = order_data.get("uTime", "0")
        if u_time != "0":
            u_dt = datetime.fromtimestamp(int(u_time) / 1000)
            table.add_row("更新时间", u_dt.strftime("%Y-%m-%d %H:%M:%S"))

        console.print(table)
        console.print(f"[green]✅ 订单已恢复到数据库[/green]")

    def _display_recovered_trade(self, trade_data: dict):
        """显示恢复的成交（数据恢复时使用）.

        Args:
            trade_data: OKX API 返回的成交数据
        """
        if self.display_format == "none":
            return

        table = Table(
            title=f"🔄 [bold green]恢复成交[/bold green] - {datetime.now().strftime('%H:%M:%S')}",
            box=box.ROUNDED,
        )
        table.add_column("字段", style="cyan", justify="left", width=15)
        table.add_column("值", style="white", justify="left")

        # 基本信息
        table.add_row("产品", trade_data.get("instId", ""))
        table.add_row("成交ID", trade_data.get("tradeId", ""))
        table.add_row("订单ID", trade_data.get("ordId", ""))

        # 成交详情
        side = trade_data.get("side", "")
        side_color = "green" if side == "buy" else "red"
        table.add_row("方向", f"[{side_color}]{side.upper()}[/{side_color}]")

        # 价格和数量
        fill_px = _safe_float(trade_data.get("fillPx"), 0)
        fill_sz = _safe_float(trade_data.get("fillSz"), 0)
        table.add_row("成交价", f"{fill_px:.4f}")
        table.add_row("成交量", f"{fill_sz:.8f}")

        # 金额
        trade_value = fill_px * fill_sz
        table.add_row("成交额", f"{trade_value:.4f} USDT")

        # 手续费
        fee = _safe_float(trade_data.get("fee"), 0)
        if fee != 0:
            table.add_row("手续费", f"{abs(fee):.8f} {trade_data.get('feeCcy', '')}")

        # 时间
        ts = trade_data.get("ts", "0")
        if ts != "0":
            ts_dt = datetime.fromtimestamp(int(ts) / 1000)
            table.add_row("成交时间", ts_dt.strftime("%Y-%m-%d %H:%M:%S"))

        console.print(table)
        console.print(f"[green]✅ 成交已恢复到数据库[/green]")

    async def _monitor_connection_health(self):
        """监控WebSocket连接健康状态，仅记录状态不强制重连."""
        logger.info(
            "Starting connection health monitor (monitoring only, no forced reconnection)"
        )

        while self.is_running:
            await asyncio.sleep(30)  # 每30秒检查一次，减少检查频率

            if self.last_message_time:
                time_since_last_msg = (
                    datetime.now() - self.last_message_time
                ).total_seconds()

                # 仅记录连接状态，不强制重连
                if time_since_last_msg > 300:  # 5分钟没有消息才记录警告
                    logger.warning(
                        "⚠️ No message received for a long time (monitoring only)",
                        seconds=time_since_last_msg,
                        minutes=round(time_since_last_msg / 60, 1),
                    )
                elif time_since_last_msg > 60:  # 1分钟没有消息记录信息
                    logger.info(
                        "Connection status: no recent messages",
                        seconds=time_since_last_msg,
                        minutes=round(time_since_last_msg / 60, 1),
                    )
                else:
                    logger.debug(
                        "Connection healthy",
                        seconds_since_last_msg=time_since_last_msg,
                    )
            else:
                logger.debug("No message time recorded yet")

    async def handle_message(self, message: str):
        """处理WebSocket消息.

        Args:
            message: WebSocket接收到的消息
        """
        try:
            # 更新最后消息时间
            self.last_message_time = datetime.now()

            data = json.loads(message)

            # 处理事件消息（登录、订阅等）
            if "event" in data:
                event = data.get("event")
                if event == "error":
                    logger.error("OKX WebSocket error", data=data)
                elif event == "subscribe":
                    logger.info("Channel subscribed", channel=data.get("arg"))
                return

            # 处理数据推送
            if "arg" in data and "data" in data:
                arg = data.get("arg", {})
                channel = arg.get("channel")

                if channel == "account":
                    # 先检测是否有变化
                    if self._has_account_changed(data):
                        self.display_account_update(data)
                        await self.save_account_update(data)
                    else:
                        logger.debug(
                            "Account data unchanged, skipping save and display"
                        )

                elif channel == "positions":
                    # 检测持仓是否有变化
                    if self._has_position_changed(data):
                        self.display_position_update(data)
                        await self.save_position_update(data)
                    else:
                        logger.debug(
                            "Position data unchanged, skipping save and display"
                        )

                elif channel == "orders":
                    # 订单更新通常都是有意义的变化，不需要过滤
                    self.display_order_update(data)
                    await self.save_order_update(data)

                else:
                    logger.debug("Unknown channel", channel=channel)

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to decode message", error=str(e), message=message[:200]
            )
        except Exception as e:
            logger.error("Failed to handle message", error=str(e))

    async def save_account_update(self, data: dict):
        """保存账户更新到数据库（使用OKX专用表）."""
        try:
            account_data = data.get("data", [])
            for account in account_data:
                # 账户总览数据
                total_eq = account.get("totalEq")
                iso_eq = account.get("isoEq")
                adj_eq = account.get("adjEq")
                notional_usd = account.get("notionalUsd")

                details = account.get("details", [])
                for detail in details:
                    async with self.db_manager.session() as session:
                        balance = OKXAccountBalance(
                            update_time=datetime.utcnow(),
                            total_eq=_safe_decimal(total_eq) if total_eq else None,
                            iso_eq=_safe_decimal(iso_eq) if iso_eq else None,
                            adj_eq=_safe_decimal(adj_eq) if adj_eq else None,
                            notional_usd=(
                                _safe_decimal(notional_usd) if notional_usd else None
                            ),
                            currency=detail.get("ccy"),
                            available_bal=_safe_decimal(detail.get("availBal")),
                            cash_bal=_safe_decimal(detail.get("cashBal")),
                            frozen_bal=_safe_decimal(detail.get("frozenBal")),
                            equity=_safe_decimal(detail.get("eq")),
                            upl=_safe_decimal(detail.get("upl")),
                            raw_data=_safe_json_dumps(data),
                        )
                        session.add(balance)

            logger.info("OKX account update saved to okx_account_balances")
        except Exception as e:
            logger.error("Failed to save account update", error=str(e))

    async def save_position_update(self, data: dict):
        """保存持仓更新到数据库（使用OKX专用表）."""
        try:
            positions = data.get("data", [])
            for pos in positions:
                async with self.db_manager.session() as session:
                    position = OKXPosition(
                        update_time=datetime.utcnow(),
                        inst_id=pos.get("instId"),
                        inst_type=pos.get("instType"),
                        pos_side=pos.get("posSide"),
                        pos=_safe_decimal(pos.get("pos")),
                        pos_ccy=pos.get("posCcy"),
                        avg_px=(
                            _safe_decimal(pos.get("avgPx"))
                            if pos.get("avgPx")
                            else None
                        ),
                        mark_px=(
                            _safe_decimal(pos.get("markPx"))
                            if pos.get("markPx")
                            else None
                        ),
                        liq_px=(
                            _safe_decimal(pos.get("liqPx"))
                            if pos.get("liqPx")
                            else None
                        ),
                        upl=_safe_decimal(pos.get("upl")) if pos.get("upl") else None,
                        upl_ratio=(
                            _safe_decimal(pos.get("uplRatio"))
                            if pos.get("uplRatio")
                            else None
                        ),
                        margin=(
                            _safe_decimal(pos.get("margin"))
                            if pos.get("margin")
                            else None
                        ),
                        imr=_safe_decimal(pos.get("imr")) if pos.get("imr") else None,
                        mmr=_safe_decimal(pos.get("mmr")) if pos.get("mmr") else None,
                        lever=(
                            _safe_decimal(pos.get("lever"))
                            if pos.get("lever")
                            else None
                        ),
                        raw_data=_safe_json_dumps(data),
                    )
                    session.add(position)

            logger.info(
                "OKX position update saved to okx_positions", count=len(positions)
            )
        except Exception as e:
            logger.error("Failed to save position update", error=str(e))

    async def save_order_update(self, data: dict):
        """保存订单更新到数据库（使用OKX专用表）."""
        orders = data.get("data", [])
        saved_count = 0
        duplicate_count = 0

        for order in orders:
            try:
                async with self.db_manager.session() as session:
                    okx_order = OKXOrder(
                        inst_id=order.get("instId"),
                        inst_type=order.get("instType"),
                        ord_id=order.get("ordId"),
                        cl_ord_id=order.get("clOrdId"),
                        ord_type=order.get("ordType"),
                        side=order.get("side"),
                        pos_side=order.get("posSide"),
                        sz=_safe_decimal(order.get("sz")),
                        px=_safe_decimal(order.get("px")) if order.get("px") else None,
                        avg_px=(
                            _safe_decimal(order.get("avgPx"))
                            if order.get("avgPx")
                            else None
                        ),
                        acc_fill_sz=(
                            _safe_decimal(order.get("accFillSz"))
                            if order.get("accFillSz")
                            else None
                        ),
                        fill_sz=(
                            _safe_decimal(order.get("fillSz"))
                            if order.get("fillSz")
                            else None
                        ),
                        fill_px=(
                            _safe_decimal(order.get("fillPx"))
                            if order.get("fillPx")
                            else None
                        ),
                        state=order.get("state"),
                        fee=(
                            _safe_decimal(order.get("fee"))
                            if order.get("fee")
                            else None
                        ),
                        fee_ccy=order.get("feeCcy"),
                        rebate=(
                            _safe_decimal(order.get("rebate"))
                            if order.get("rebate")
                            else None
                        ),
                        rebate_ccy=order.get("rebateCcy"),
                        c_time=(
                            datetime.fromtimestamp(
                                _safe_float(order.get("cTime")) / 1000
                            )
                            if order.get("cTime")
                            else None
                        ),
                        u_time=(
                            datetime.fromtimestamp(
                                _safe_float(order.get("uTime")) / 1000
                            )
                            if order.get("uTime")
                            else datetime.utcnow()
                        ),
                        fill_time=(
                            datetime.fromtimestamp(
                                _safe_float(order.get("fillTime")) / 1000
                            )
                            if order.get("fillTime")
                            else None
                        ),
                        reduce_only=order.get("reduceOnly") == "true",
                        td_mode=order.get("tdMode"),
                        raw_data=_safe_json_dumps(data),
                    )
                    session.add(okx_order)
                    await session.commit()
                    saved_count += 1

                    # 更新 Prometheus metrics
                    try:
                        # 订阅服务使用端口 9601
                        ensure_metrics_server(9601)
                        update_order_metrics(
                            exchange="okx",
                            exchange_type="perp",
                            account_id="default",  # OKX 暂不支持多账号
                            order_data=order,
                        )
                    except Exception as metric_error:
                        logger.debug(f"Failed to update order metrics: {metric_error}")

            except IntegrityError:
                # 订单已存在（重复推送），跳过
                duplicate_count += 1
                logger.debug(
                    "Duplicate OKX order update, skipping",
                    ord_id=order.get("ordId"),
                    u_time=order.get("uTime"),
                )
            except Exception as e:
                logger.error(
                    "Failed to save OKX order update",
                    error=str(e),
                    ord_id=order.get("ordId"),
                )

        if saved_count > 0:
            logger.info(
                "OKX order updates saved", saved=saved_count, duplicates=duplicate_count
            )
        elif duplicate_count > 0:
            logger.debug(
                "All OKX order updates were duplicates", duplicates=duplicate_count
            )

    async def get_or_create_connection_status(self) -> ConnectionStatus:
        """获取或创建连接状态记录.

        Returns:
            ConnectionStatus对象
        """
        async with self.db_manager.session() as session:
            result = await session.execute(
                select(ConnectionStatus).where(ConnectionStatus.exchange == "okx_perp")
            )
            status = result.scalar_one_or_none()

            if status is None:
                status = ConnectionStatus(exchange="okx_perp")
                session.add(status)
                await session.commit()
                await session.refresh(status)
                logger.info("Created new connection status record for OKX")
            else:
                logger.info(
                    "Loaded existing OKX connection status",
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
        order_id: str | None = None,
        trade_id: str | None = None,
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
                select(ConnectionStatus).where(ConnectionStatus.exchange == "okx_perp")
            )
            status = result.scalar_one_or_none()

            if status is None:
                status = ConnectionStatus(exchange="okx_perp")
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
                            "Reconnected after disconnection",
                            gap_seconds=gap_seconds,
                            total_reconnects=status.total_reconnect_count,
                        )

                status.last_connected_at = datetime.now()
                status.is_connected = True

            else:
                # 断线状态
                if status.is_connected:
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

            # 更新ID（OKX使用字符串ID，需要转换）
            if order_id:
                try:
                    status.last_order_id = int(order_id)
                except (ValueError, TypeError):
                    pass
            if trade_id:
                try:
                    status.last_trade_id = int(trade_id)
                except (ValueError, TypeError):
                    pass

            await session.commit()

    async def query_missing_data(self, symbols: list[str] | None = None):
        """查询断线期间丢失的订单数据并补全到数据库.

        专注于订单功能的断线回补，不处理成交数据。

        Args:
            symbols: 要查询的交易对列表，如["BTC-USDT-SWAP", "ETH-USDT-SWAP"]，None表示查询所有活跃交易对
        """
        logger.info("=== Starting OKX order data recovery process ===")

        # 确保 exchange 已连接
        if not self.exchange.is_connected:
            logger.info(
                "Exchange not connected, connecting now for order data recovery"
            )
            await self.exchange.connect()

        # 获取连接状态
        status = await self.get_or_create_connection_status()

        if status.last_disconnected_at is None:
            logger.info("No disconnection detected, skipping order data recovery")
            return

        # 计算查询时间范围
        start_time = status.last_disconnected_at
        end_time = datetime.now()
        gap_seconds = int((end_time - start_time).total_seconds())

        logger.info(
            "OKX order data recovery time range",
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
                    "No active symbols found in OKX database (last 24 hours). "
                    "Order data recovery skipped."
                )
                return
            logger.info(f"Auto-detected {len(symbols)} active OKX symbols: {symbols}")
        else:
            logger.info(f"Using provided OKX symbols: {symbols}")

        if not symbols:
            logger.warning("No symbols to query for OKX order data recovery")
            return

        # 转换为毫秒时间戳
        start_time_ms = int(start_time.timestamp() * 1000)
        end_time_ms = int(end_time.timestamp() * 1000)

        total_orders = 0
        recovered_orders = 0

        # 对每个交易对只查询订单数据
        for symbol in symbols:
            logger.info(f"Processing OKX symbol: {symbol}")
            try:
                # 只查询订单，不查询成交
                logger.debug(f"Querying orders for {symbol}...")
                orders = await self.exchange.get_all_orders(
                    symbol=symbol,
                    start_time=start_time_ms,
                    end_time=end_time_ms,
                )

                logger.info(f"Retrieved {len(orders)} orders for {symbol}")
                total_orders += len(orders)

                # 保存订单到数据库（带去重）并显示
                for order_data in orders:
                    saved = await self._save_order_with_dedup(order_data)
                    if saved:
                        recovered_orders += 1
                        # ✅ 在控制台显示恢复的订单
                        self._display_recovered_order(order_data)

            except Exception as e:
                logger.error(
                    f"Failed to query OKX order data for {symbol}",
                    error=str(e),
                    exc_info=True,
                )
                continue

        # 计算去重统计
        duplicate_orders = total_orders - recovered_orders

        logger.info(
            "=== OKX order data recovery completed ===",
            total_orders_retrieved=total_orders,
            new_orders_saved=recovered_orders,
            duplicate_orders_skipped=duplicate_orders,
            gap_seconds=gap_seconds,
            gap_minutes=round(gap_seconds / 60, 2),
        )

        # ✅ 在控制台显示恢复总结
        if self.display_format != "none":
            summary_table = Table(
                title=f"📊 [bold magenta]订单数据恢复总结[/bold magenta]",
                box=box.DOUBLE,
            )
            summary_table.add_column("项目", style="cyan", justify="left")
            summary_table.add_column("数量", style="yellow", justify="right")

            summary_table.add_row(
                "断线时长", f"{gap_seconds} 秒 ({round(gap_seconds / 60, 2)} 分钟)"
            )
            summary_table.add_row("查询交易对", str(len(symbols)))
            summary_table.add_row("━" * 20, "━" * 10)
            summary_table.add_row("查询到的订单", str(total_orders))
            summary_table.add_row("恢复到数据库", f"[green]{recovered_orders}[/green]")
            summary_table.add_row(
                "跳过重复订单", f"[yellow]{duplicate_orders}[/yellow]"
            )

            console.print(summary_table)

            if recovered_orders > 0:
                console.print(
                    f"\n[bold green]✅ 订单数据恢复成功！恢复了 {recovered_orders} 个订单[/bold green]\n"
                )
            elif total_orders == 0:
                console.print(f"\n[yellow]ℹ️  断线期间没有新的订单[/yellow]\n")
            else:
                console.print(f"\n[yellow]ℹ️  所有订单数据已存在，无需恢复[/yellow]\n")

    async def _get_active_symbols(self) -> list[str]:
        """从数据库中获取最近活跃的交易对.

        Returns:
            交易对列表，如["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
        """
        async with self.db_manager.session() as session:
            cutoff_time = datetime.now() - timedelta(hours=24)

            # 从OKX订单表获取
            result = await session.execute(
                select(OKXOrder.inst_id)
                .where(OKXOrder.u_time >= cutoff_time)
                .distinct()
            )
            symbols = [row[0] for row in result.fetchall()]

            if symbols:
                logger.info(
                    f"Found {len(symbols)} active OKX symbols in last 24 hours",
                    symbols=symbols,
                )
            else:
                logger.warning("No active OKX symbols found in last 24 hours")

            return symbols

    async def _save_order_with_dedup(self, order_data: dict) -> bool:
        """保存订单数据，自动去重.

        Args:
            order_data: OKX API返回的订单数据

        Returns:
            bool: True 表示新数据已保存，False 表示数据已存在（去重）
        """
        order_id = order_data.get("ordId", "")
        update_time = (
            datetime.fromtimestamp(int(order_data.get("uTime", 0)) / 1000)
            if order_data.get("uTime")
            else datetime.utcnow()
        )

        try:
            async with self.db_manager.session() as session:
                okx_order = OKXOrder(
                    inst_id=order_data.get("instId"),
                    inst_type=order_data.get("instType"),
                    ord_id=order_id,
                    cl_ord_id=order_data.get("clOrdId"),
                    ord_type=order_data.get("ordType"),
                    side=order_data.get("side"),
                    pos_side=order_data.get("posSide"),
                    sz=_safe_decimal(order_data.get("sz")),
                    px=(
                        _safe_decimal(order_data.get("px"))
                        if order_data.get("px")
                        else None
                    ),
                    avg_px=(
                        _safe_decimal(order_data.get("avgPx"))
                        if order_data.get("avgPx")
                        else None
                    ),
                    acc_fill_sz=(
                        _safe_decimal(order_data.get("accFillSz"))
                        if order_data.get("accFillSz")
                        else None
                    ),
                    state=order_data.get("state"),
                    fee=(
                        _safe_decimal(order_data.get("fee"))
                        if order_data.get("fee")
                        else None
                    ),
                    fee_ccy=order_data.get("feeCcy"),
                    rebate=(
                        _safe_decimal(order_data.get("rebate"))
                        if order_data.get("rebate")
                        else None
                    ),
                    rebate_ccy=order_data.get("rebateCcy"),
                    c_time=(
                        datetime.fromtimestamp(
                            _safe_float(order_data.get("cTime")) / 1000
                        )
                        if order_data.get("cTime")
                        else None
                    ),
                    u_time=update_time,
                    reduce_only=order_data.get("reduceOnly") == "true",
                    td_mode=order_data.get("tdMode"),
                    raw_data=_safe_json_dumps(order_data),
                )
                session.add(okx_order)
                await session.commit()

                logger.debug(
                    "Saved recovered OKX order",
                    order_id=order_id,
                    inst_id=order_data.get("instId"),
                    state=order_data.get("state"),
                )
                return True
        except IntegrityError:
            logger.debug(
                f"OKX order {order_id} at {update_time} already exists, skipping"
            )
            return False

    async def _save_trade_with_dedup(self, trade_data: dict) -> bool:
        """保存成交数据，自动去重.

        Args:
            trade_data: OKX API返回的成交数据

        Returns:
            bool: True 表示新数据已保存，False 表示数据已存在（去重）
        """
        trade_id = trade_data.get("tradeId", "")
        ord_id = trade_data.get("ordId", "")

        try:
            async with self.db_manager.session() as session:
                # 解析时间戳
                fill_time = (
                    datetime.fromtimestamp(int(trade_data.get("ts", 0)) / 1000)
                    if trade_data.get("ts")
                    else datetime.utcnow()
                )

                # ✅ 保存到 OKXTrade 表
                okx_trade = OKXTrade(
                    inst_id=trade_data.get("instId"),
                    ord_id=ord_id,
                    trade_id=trade_id,
                    side=trade_data.get("side"),
                    fill_px=_safe_decimal(trade_data.get("fillPx")),
                    fill_sz=_safe_decimal(trade_data.get("fillSz")),
                    fee=(
                        _safe_decimal(trade_data.get("fee"))
                        if trade_data.get("fee")
                        else None
                    ),
                    fee_ccy=trade_data.get("feeCcy"),
                    fill_time=fill_time,
                    raw_data=_safe_json_dumps(trade_data),
                )
                session.add(okx_trade)
                await session.commit()

                logger.debug(
                    "Saved recovered OKX trade",
                    trade_id=trade_id,
                    ord_id=ord_id,
                    inst_id=trade_data.get("instId"),
                    fill_px=trade_data.get("fillPx"),
                    fill_sz=trade_data.get("fillSz"),
                )
                return True

        except IntegrityError:
            logger.debug(f"OKX trade {trade_id} already exists, skipping")
            return False
        except Exception as e:
            logger.error(
                f"Failed to save OKX trade {trade_id}", error=str(e), exc_info=True
            )
            return False

    async def _check_needs_recovery(
        self, status: ConnectionStatus
    ) -> tuple[bool, str, datetime | None]:
        """检查是否需要订单数据恢复.

        Args:
            status: 连接状态对象

        Returns:
            (需要恢复, 原因, 断线时间)
        """
        if status.last_disconnected_at is None:
            return False, "", None

        # 检查是否需要恢复
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
                    "Attempting OKX order data recovery",
                    attempt=attempt,
                    max_retries=max_retries,
                )

                # 确保 exchange 已连接
                if not self.exchange.is_connected:
                    await self.exchange.connect()

                # 执行订单数据恢复
                await self.query_missing_data()
                logger.info(
                    "OKX order data recovery completed successfully", attempt=attempt
                )
                return  # 成功，退出

            except Exception as e:
                logger.warning(
                    "OKX order data recovery failed",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(e),
                )

                if attempt < max_retries:
                    logger.info(
                        f"Retrying OKX order data recovery in {retry_delay} seconds..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        "OKX order data recovery failed after all retries",
                        max_retries=max_retries,
                        error=str(e),
                    )

    async def start(self):
        """启动OKX用户数据流订阅."""
        self.is_running = True

        try:
            # 获取或创建连接状态记录
            status = await self.get_or_create_connection_status()

            # 检查是否需要订单数据恢复（但不立即执行）
            needs_recovery, recovery_reason, disconnect_time = (
                await self._check_needs_recovery(status)
            )

            if needs_recovery and disconnect_time:
                gap_seconds = int((datetime.now() - disconnect_time).total_seconds())
                logger.info(
                    "Detected previous OKX disconnection, will recover order data after WebSocket connection",
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
                    "No OKX order data recovery needed",
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

            logger.info("Connecting to OKX WebSocket with heartbeat", url=self.ws_url)

            # 添加 WebSocket ping/pong 心跳机制
            async with ws_connect(
                self.ws_url,
                ping_interval=20,  # 每20秒发送ping
                ping_timeout=10,  # ping超时10秒认为断线
                close_timeout=5,  # 关闭超时5秒
            ) as websocket:
                self.websocket = websocket
                logger.info("OKX WebSocket connected with heartbeat enabled")

                # 登录认证
                if not await self.login():
                    logger.error("Failed to login")
                    return

                # 订阅频道
                await self.subscribe_channels()

                # 更新连接状态
                await self.update_connection_status(is_connected=True)

                # 在WebSocket连接成功后执行订单数据恢复（如果需要）
                if needs_recovery and disconnect_time:
                    disconnect_duration = int(
                        (datetime.now() - disconnect_time).total_seconds()
                    )
                    logger.info(
                        "Reconnected after disconnection, starting REST backfill",
                        disconnect_duration=disconnect_duration,
                    )

                    try:
                        await self._recover_data_with_retry(
                            max_retries=3, retry_delay=2
                        )
                        logger.info("OKX REST backfill completed after reconnect")
                    except Exception as recovery_error:
                        logger.error(
                            "OKX REST backfill failed after reconnect",
                            error=str(recovery_error),
                            exc_info=True,
                        )

                    lookback = max(disconnect_duration + 300, 600)
                    try:
                        await self.reconciliation_service.reconcile_once(
                            lookback_seconds=lookback
                        )
                        logger.info(
                            "OKX reconciliation completed after reconnect",
                            lookback_seconds=lookback,
                        )
                    except Exception as recon_error:
                        logger.error(
                            "OKX reconciliation failed after reconnect",
                            error=str(recon_error),
                            exc_info=True,
                        )

                    # 清除断线时间记录
                    self.disconnect_time = None

                # 启动后台监控任务
                self._monitor_task = asyncio.create_task(
                    self._monitor_connection_health()
                )
                logger.info("Started connection health monitor")

                # 接收消息循环
                try:
                    async for message in websocket:
                        if not self.is_running:
                            break

                        await self.handle_message(message)
                finally:
                    # 取消后台任务
                    if self._monitor_task:
                        self._monitor_task.cancel()
                        try:
                            await self._monitor_task
                        except asyncio.CancelledError:
                            pass

        except ws_exceptions.ConnectionClosed:
            logger.warning("OKX WebSocket connection closed")

            # 记录断线时间
            self.disconnect_time = datetime.now()
            await self.update_connection_status(is_connected=False)

            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect OKX in 5 seconds...")
                await asyncio.sleep(5)
                await self.start()
        except Exception as e:
            logger.error("OKX WebSocket error", error=str(e), exc_info=True)

            # 记录断线
            await self.update_connection_status(is_connected=False)

            # 不要直接raise，而是尝试重连
            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect OKX after error in 5 seconds...")
                await asyncio.sleep(5)
                await self.start()
            else:
                raise

    async def stop(self):
        """停止用户数据流订阅."""
        self.is_running = False

        # 注意：不需要停止对账服务，因为我们使用按需对账而非定时对账

        # 取消后台任务
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # 关闭WebSocket
        if self.websocket:
            await self.websocket.close()

        logger.info("OKX user data stream stopped")
