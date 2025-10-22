"""OKX User Data Stream WebSocket service.

Subscribe to OKX WebSocket user data stream for real-time account and order updates.
"""

import asyncio
import base64
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
from tri_arb.storage.okx_models import OKXAccountBalance, OKXPosition, OKXOrder, OKXTrade

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
    if value is None or value == '' or value == 'null':
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
    if value is None or value == '' or value == 'null':
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, Exception):
        return Decimal(default)


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
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_running = False
        
        # 缓存上次的账户和持仓数据，用于检测变化
        self.last_account_data = None
        self.last_position_data = None
        
        logger.info("OKXUserStreamService initialized", 
                   display_format=display_format, 
                   inst_type=inst_type,
                   skip_duplicate_updates=skip_duplicate_updates,
                   enabled_channels=list(self.enabled_channels))
    
    def _generate_signature(self, timestamp: str, method: str, request_path: str) -> str:
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
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        
        # Base64编码
        signature = base64.b64encode(mac.digest()).decode('utf-8')
        
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
        method = 'GET'
        request_path = '/users/self/verify'
        
        signature = self._generate_signature(timestamp, method, request_path)
        
        logger.debug("OKX login attempt", 
                    timestamp=timestamp, 
                    method=method, 
                    path=request_path,
                    api_key=self.api_key[:8] + "...")
        
        login_msg = {
            "op": "login",
            "args": [
                {
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": signature
                }
            ]
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
            logger.error("OKX WebSocket login failed", 
                        error_code=error_code,
                        error_msg=error_msg,
                        timestamp_used=timestamp,
                        response=data)
            
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
            channels.append({
                "channel": "account",
                "ccy": "USDT"  # 可以订阅特定币种或不指定订阅所有
            })
        
        if "position" in self.enabled_channels:
            channels.append({
                "channel": "positions",
                "instType": self.inst_type
            })
        
        if "order" in self.enabled_channels:
            channels.append({
                "channel": "orders",
                "instType": self.inst_type
            })
        
        if not channels:
            logger.warning("No channels to subscribe")
            return
        
        subscribe_msg = {
            "op": "subscribe",
            "args": channels
        }
        
        await self.websocket.send(json.dumps(subscribe_msg))
        logger.info("Subscribed to OKX channels", 
                   channels=[c["channel"] for c in channels],
                   count=len(channels))
    
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
            console.print(Panel(
                json.dumps(data, indent=2, ensure_ascii=False),
                title="[cyan]OKX 账户更新 (account)[/cyan]",
                border_style="cyan"
            ))
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
                show_header=False
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
            detail_table = Table(
                title=f"💵 币种余额详情", 
                box=box.ROUNDED
            )
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
                    f"{cash_bal:.4f}"
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
            console.print(Panel(
                json.dumps(data, indent=2, ensure_ascii=False),
                title="[cyan]OKX 持仓更新 (positions)[/cyan]",
                border_style="cyan"
            ))
            return
        
        # 表格显示
        positions = data.get("data", [])
        if not positions:
            return
        
        table = Table(
            title=f"📊 OKX持仓更新 - {datetime.now().strftime('%H:%M:%S')}", 
            box=box.ROUNDED
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
            ratio_str = f"+{upl_ratio*100:.2f}%" if upl_ratio > 0 else f"{upl_ratio*100:.2f}%"
            ratio_style = "green" if upl_ratio > 0 else "red" if upl_ratio < 0 else "white"
            
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
                f"{lever:.0f}x"
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
            console.print(Panel(
                json.dumps(data, indent=2, ensure_ascii=False),
                title="[yellow]OKX 订单更新 (orders)[/yellow]",
                border_style="yellow"
            ))
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
                box=box.ROUNDED
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
            
            # 持仓方向和交易模式
            if order.get("posSide"):
                table.add_row("持仓方向", order.get("posSide", "").upper())
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
                fill_bar = "█" * int(fill_percent / 10) + "░" * (10 - int(fill_percent / 10))
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
                    table.add_row("滑点", f"[{slippage_style}]{slippage_str}[/{slippage_style}]")
            
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
                table.add_row("创建时间", c_time.strftime('%Y-%m-%d %H:%M:%S'))
            
            if order.get("uTime"):
                u_time = datetime.fromtimestamp(int(order.get("uTime")) / 1000)
                table.add_row("更新时间", u_time.strftime('%Y-%m-%d %H:%M:%S'))
            
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
                    console.print(f"   手续费: -{fee_total:.4f} {order.get('feeCcy', '')}")
                if rebate != 0:
                    console.print(f"   返佣: +{abs(rebate):.4f} {order.get('rebateCcy', '')}")
    
    async def handle_message(self, message: str):
        """处理WebSocket消息.
        
        Args:
            message: WebSocket接收到的消息
        """
        try:
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
                        logger.debug("Account data unchanged, skipping save and display")
                        
                elif channel == "positions":
                    # 检测持仓是否有变化
                    if self._has_position_changed(data):
                        self.display_position_update(data)
                        await self.save_position_update(data)
                    else:
                        logger.debug("Position data unchanged, skipping save and display")
                    
                elif channel == "orders":
                    # 订单更新通常都是有意义的变化，不需要过滤
                    self.display_order_update(data)
                    await self.save_order_update(data)
                    
                else:
                    logger.debug("Unknown channel", channel=channel)
        
        except json.JSONDecodeError as e:
            logger.error("Failed to decode message", error=str(e), message=message[:200])
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
                            notional_usd=_safe_decimal(notional_usd) if notional_usd else None,
                            currency=detail.get("ccy"),
                            available_bal=_safe_decimal(detail.get("availBal")),
                            cash_bal=_safe_decimal(detail.get("cashBal")),
                            frozen_bal=_safe_decimal(detail.get("frozenBal")),
                            equity=_safe_decimal(detail.get("eq")),
                            upl=_safe_decimal(detail.get("upl")),
                            raw_data=json.dumps(data),
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
                        avg_px=_safe_decimal(pos.get("avgPx")) if pos.get("avgPx") else None,
                        mark_px=_safe_decimal(pos.get("markPx")) if pos.get("markPx") else None,
                        liq_px=_safe_decimal(pos.get("liqPx")) if pos.get("liqPx") else None,
                        upl=_safe_decimal(pos.get("upl")) if pos.get("upl") else None,
                        upl_ratio=_safe_decimal(pos.get("uplRatio")) if pos.get("uplRatio") else None,
                        margin=_safe_decimal(pos.get("margin")) if pos.get("margin") else None,
                        imr=_safe_decimal(pos.get("imr")) if pos.get("imr") else None,
                        mmr=_safe_decimal(pos.get("mmr")) if pos.get("mmr") else None,
                        lever=_safe_decimal(pos.get("lever")) if pos.get("lever") else None,
                        raw_data=json.dumps(data),
                    )
                    session.add(position)
            
            logger.info("OKX position update saved to okx_positions", count=len(positions))
        except Exception as e:
            logger.error("Failed to save position update", error=str(e))
    
    async def save_order_update(self, data: dict):
        """保存订单更新到数据库（使用OKX专用表）."""
        try:
            orders = data.get("data", [])
            for order in orders:
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
                        avg_px=_safe_decimal(order.get("avgPx")) if order.get("avgPx") else None,
                        acc_fill_sz=_safe_decimal(order.get("accFillSz")) if order.get("accFillSz") else None,
                        fill_sz=_safe_decimal(order.get("fillSz")) if order.get("fillSz") else None,
                        fill_px=_safe_decimal(order.get("fillPx")) if order.get("fillPx") else None,
                        state=order.get("state"),
                        fee=_safe_decimal(order.get("fee")) if order.get("fee") else None,
                        fee_ccy=order.get("feeCcy"),
                        rebate=_safe_decimal(order.get("rebate")) if order.get("rebate") else None,
                        rebate_ccy=order.get("rebateCcy"),
                        c_time=datetime.fromtimestamp(_safe_float(order.get("cTime")) / 1000) if order.get("cTime") else None,
                        u_time=datetime.fromtimestamp(_safe_float(order.get("uTime")) / 1000) if order.get("uTime") else datetime.utcnow(),
                        fill_time=datetime.fromtimestamp(_safe_float(order.get("fillTime")) / 1000) if order.get("fillTime") else None,
                        reduce_only=order.get("reduceOnly") == "true",
                        td_mode=order.get("tdMode"),
                        raw_data=json.dumps(data),
                    )
                    session.add(okx_order)
            
            logger.info("OKX order update saved to okx_orders", count=len(orders))
        except Exception as e:
            logger.error("Failed to save order update", error=str(e))
    
    async def start(self):
        """启动OKX用户数据流订阅."""
        self.is_running = True
        
        try:
            logger.info("Connecting to OKX WebSocket", url=self.ws_url)
            
            async with websockets.connect(self.ws_url) as websocket:
                self.websocket = websocket
                logger.info("OKX WebSocket connected")
                
                # 登录认证
                if not await self.login():
                    logger.error("Failed to login")
                    return
                
                # 订阅频道
                await self.subscribe_channels()
                
                # 接收消息循环
                async for message in websocket:
                    if not self.is_running:
                        break
                    
                    await self.handle_message(message)
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("OKX WebSocket connection closed")
            if self.auto_reconnect and self.is_running:
                logger.info("Attempting to reconnect...")
                await asyncio.sleep(5)
                await self.start()
        except Exception as e:
            logger.error("OKX WebSocket error", error=str(e))
            raise
    
    async def stop(self):
        """停止用户数据流订阅."""
        self.is_running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("OKX user data stream stopped")

