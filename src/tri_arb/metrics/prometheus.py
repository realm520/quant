"""Prometheus metrics helpers for exchange monitoring."""

from __future__ import annotations

import os
import socket
import threading
from decimal import Decimal
from typing import Any, Mapping

from prometheus_client import Counter, Gauge, start_http_server

from tri_arb.config.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_PORT = int(os.getenv("PROM_METRICS_PORT", "9500"))
_SERVER_STARTED = False
_SERVER_LOCK = threading.Lock()

# 跟踪每个账户的当前仓位标签，用于清除已平仓的仓位
_position_labels_cache: dict[tuple[str, str, str], set[tuple[str, str]]] = {}
_position_cache_lock = threading.Lock()

_balance_available = Gauge(
    "exchange_balance_available",
    "Available balance of each asset per account and exchange.",
    ["exchange", "exchange_type", "account_id", "asset"],
)
_balance_frozen = Gauge(
    "exchange_balance_frozen",
    "Frozen / margin balance of each asset per account and exchange.",
    ["exchange", "exchange_type", "account_id", "asset"],
)
_balance_total = Gauge(
    "exchange_balance_total",
    "Total balance of each asset per account and exchange.",
    ["exchange", "exchange_type", "account_id", "asset"],
)
_query_status_counter = Counter(
    "exchange_balance_query_total",
    "Number of balance query attempts grouped by result.",
    ["exchange", "exchange_type", "account_id", "status"],
)

# 订单相关指标
_order_count = Gauge(
    "exchange_order_count",
    "Number of active orders per account, exchange, symbol, side, and position side.",
    ["exchange", "exchange_type", "account_id", "symbol", "side", "position_side", "status"],
)

_order_notional = Gauge(
    "exchange_order_notional",
    "Total notional value of orders per account, exchange, symbol, side, and position side.",
    ["exchange", "exchange_type", "account_id", "symbol", "side", "position_side"],
)

_order_update_total = Counter(
    "exchange_order_update_total",
    "Total number of order updates received.",
    ["exchange", "exchange_type", "account_id", "order_status", "side", "position_side"],
)

# 成交相关指标
_trade_update_total = Counter(
    "exchange_trade_update_total",
    "Total number of trade updates received.",
    ["exchange", "exchange_type", "account_id", "symbol", "side", "position_side"],
)

_position_quantity = Gauge(
    "exchange_position_quantity",
    "Current position size (signed) per account, symbol, and side.",
    ["exchange", "exchange_type", "account_id", "symbol", "position_side"],
)

_position_entry_price = Gauge(
    "exchange_position_entry_price",
    "Entry price of each position.",
    ["exchange", "exchange_type", "account_id", "symbol", "position_side"],
)

_position_mark_price = Gauge(
    "exchange_position_mark_price",
    "Mark price of each position.",
    ["exchange", "exchange_type", "account_id", "symbol", "position_side"],
)

_position_unrealized_pnl = Gauge(
    "exchange_position_unrealized_pnl",
    "Unrealized PnL of each position.",
    ["exchange", "exchange_type", "account_id", "symbol", "position_side"],
)

_position_leverage = Gauge(
    "exchange_position_leverage",
    "Configured leverage for each position.",
    ["exchange", "exchange_type", "account_id", "symbol", "position_side"],
)


def _is_port_available(port: int) -> bool:
    """Check if a port is available for binding.
    
    Checks if the port is available on 0.0.0.0 (all interfaces),
    which is what prometheus_client.start_http_server uses by default.
    
    Args:
        port: Port number to check
        
    Returns:
        True if port is available, False otherwise
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


def ensure_metrics_server(port: int | None = None) -> None:
    """Start the Prometheus HTTP server if it hasn't been started yet.
    
    If the port is already in use (e.g., by another process), this function
    will skip starting the server and log a warning. This allows multiple
    processes to share the same metrics endpoint.
    """
    global _SERVER_STARTED
    if _SERVER_STARTED:
        return
    with _SERVER_LOCK:
        if _SERVER_STARTED:
            return
        
        target_port = port or _DEFAULT_PORT
        
        # Check if port is already in use
        if not _is_port_available(target_port):
            logger.warning(
                f"Prometheus metrics port {target_port} is already in use. "
                "Skipping server start (assuming another process is providing metrics)."
            )
            # Still mark as started to avoid repeated checks
            _SERVER_STARTED = True
            return
        
        try:
            start_http_server(target_port)
            _SERVER_STARTED = True
            logger.info(f"Prometheus metrics server started on port {target_port}")
        except OSError as e:
            logger.warning(
                f"Failed to start Prometheus metrics server on port {target_port}: {e}. "
                "Another process may already be using this port."
            )
            # Mark as started anyway to avoid repeated attempts
            _SERVER_STARTED = True


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def update_balance_metrics(
    exchange: str,
    exchange_type: str,
    account_id: str,
    balances: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    """Update Prometheus gauges using the latest balance snapshot."""
    if not balances:
        return

    for asset, data in balances.items():
        asset_label = (asset or "").upper()
        labels = (exchange, exchange_type, account_id, asset_label)
        available = _to_float(data.get("available"))
        frozen = _to_float(data.get("frozen"))
        total = _to_float(data.get("total"))

        _balance_available.labels(*labels).set(available)
        _balance_frozen.labels(*labels).set(frozen)
        _balance_total.labels(*labels).set(total)


def record_balance_query_status(
    exchange: str,
    exchange_type: str,
    account_id: str,
    *,
    success: bool,
) -> None:
    """Increment counters for balance query success/failure."""
    status = "success" if success else "failure"
    _query_status_counter.labels(exchange, exchange_type, account_id, status).inc()


def update_order_metrics(
    exchange: str,
    exchange_type: str,
    account_id: str,
    order_data: Mapping[str, Any],
) -> None:
    """Update Prometheus metrics for order updates.
    
    Args:
        exchange: Exchange name (e.g., "binance", "xt")
        exchange_type: Exchange type (e.g., "perp", "spot")
        account_id: Account ID
        order_data: Order data dictionary
    """
    # 提取订单信息（支持不同交易所格式）
    symbol = (
        order_data.get("symbol") 
        or order_data.get("s")  # Binance
        or order_data.get("instId")  # OKX
        or order_data.get("contract")  # Gate
        or ""
    ).upper()
    
    side = (
        order_data.get("side") 
        or order_data.get("S")  # Binance
        or order_data.get("orderSide")  # XT
        or ""
    ).upper()
    
    # 持仓方向（多空）
    position_side = (
        order_data.get("positionSide")
        or order_data.get("ps")  # Binance
        or order_data.get("posSide")  # OKX
        or order_data.get("position_side")
        or "NET"  # 默认
    ).upper()
    
    status = (
        order_data.get("status")
        or order_data.get("X")  # Binance
        or order_data.get("state")  # OKX
        or ""
    ).upper()
    
    # 订单数量
    quantity = _to_float(
        order_data.get("quantity")
        or order_data.get("q")  # Binance
        or order_data.get("sz")  # OKX
        or order_data.get("size")  # Gate
        or order_data.get("origQty")  # XT
        or 0
    )
    
    # 订单价格
    price = _to_float(
        order_data.get("price")
        or order_data.get("p")  # Binance
        or order_data.get("px")  # OKX
        or 0
    )
    
    notional = abs(quantity) * price if price > 0 else 0
    
    # 更新指标
    labels = (exchange, exchange_type, account_id, symbol, side, position_side)
    
    # 活跃订单状态列表
    active_statuses = ["NEW", "LIVE", "PARTIALLY_FILLED", "OPEN"]
    is_active = status in active_statuses
    
    # 更新订单数量（活跃订单为1，非活跃为0）
    # 注意：这里使用 Gauge，每次更新都会覆盖之前的值
    # 如果需要跟踪总活跃订单数，需要维护一个状态映射
    for active_status in active_statuses:
        _order_count.labels(*labels, active_status).set(0)
    if is_active:
        _order_count.labels(*labels, status).set(1)
    else:
        _order_count.labels(*labels, status).set(0)
    
    # 更新订单名义价值（仅活跃订单）
    if is_active and notional > 0:
        _order_notional.labels(*labels).set(notional)
    elif not is_active:
        # 订单已完成或取消，清除名义价值
        _order_notional.labels(*labels).set(0)
    
    # 记录订单更新计数
    _order_update_total.labels(exchange, exchange_type, account_id, status, side, position_side).inc()


def update_trade_metrics(
    exchange: str,
    exchange_type: str,
    account_id: str,
    trade_data: Mapping[str, Any],
) -> None:
    """Update Prometheus metrics for trade updates.
    
    Args:
        exchange: Exchange name (e.g., "binance", "xt")
        exchange_type: Exchange type (e.g., "perp", "spot")
        account_id: Account ID
        trade_data: Trade data dictionary (may be single trade or dict with 'trades' list)
    """
    # 支持两种格式：
    # 1. trades 列表格式: {"trades": [...]}
    # 2. 单个成交对象格式: {"trade_id": "...", "symbol": "...", ...}
    trades = []
    if "trades" in trade_data and isinstance(trade_data.get("trades"), list):
        trades = trade_data.get("trades", [])
    elif "trade_id" in trade_data or "tradeId" in trade_data:
        # 单个成交对象，转换为列表
        trades = [trade_data]
    
    for trade in trades:
        # 提取成交信息（支持不同交易所格式）
        symbol = (
            trade.get("symbol") 
            or trade.get("s")  # Binance
            or trade.get("instId")  # OKX
            or ""
        ).upper()
        
        if not symbol:
            continue  # 跳过没有交易对的成交
        
        side = (
            trade.get("side") 
            or trade.get("S")  # Binance
            or ""
        ).upper()
        
        # 持仓方向（多空）
        position_side = (
            trade.get("positionSide")
            or trade.get("ps")  # Binance
            or trade.get("posSide")  # OKX
            or trade.get("position_side")
            or "NET"  # 默认
        ).upper()
        
        # 记录成交更新计数
        _trade_update_total.labels(exchange, exchange_type, account_id, symbol, side, position_side).inc()


def update_position_metrics(
    exchange: str,
    exchange_type: str,
    account_id: str,
    positions: Mapping[str, Any] | list[Mapping[str, Any]] | None,
) -> None:
    """Update Prometheus gauges for position snapshots.
    
    This function will:
    1. Clear metrics for positions that no longer exist (closed positions)
    2. Update metrics for current positions
    """
    account_key = (exchange, exchange_type, account_id)
    current_labels: set[tuple[str, str]] = set()
    
    if positions:
        if isinstance(positions, Mapping):
            iterable = [positions]
        else:
            iterable = positions

        for position in iterable:
            symbol = (
                position.get("symbol")
                or position.get("instId")
                or position.get("contract")
                or ""
            ).upper()
            if not symbol:
                continue

            position_side = (
                position.get("positionSide")
                or position.get("posSide")
                or position.get("side")
                or position.get("position_side")
                or "BOTH"
            ).upper()

            labels = (exchange, exchange_type, account_id, symbol, position_side)
            current_labels.add((symbol, position_side))

            quantity = _to_float(
                position.get("positionSize")
                or position.get("positionAmt")
                or position.get("qty")
                or position.get("quantity")
                or 0
            )
            entry_price = _to_float(
                position.get("entryPrice")
                or position.get("avgEntryPrice")
                or position.get("entry_price")
                or 0
            )
            mark_price = _to_float(
                position.get("calMarkPrice")
                or position.get("markPrice")
                or position.get("mark_price")
                or 0
            )
            unrealized = _to_float(
                position.get("floatingPL")
                or position.get("unRealizedProfit")
                or position.get("unrealizedPnl")
                or position.get("unrealized_pnl")
                or 0
            )
            leverage = _to_float(position.get("leverage") or 0)

            _position_quantity.labels(*labels).set(quantity)
            _position_entry_price.labels(*labels).set(entry_price)
            _position_mark_price.labels(*labels).set(mark_price)
            _position_unrealized_pnl.labels(*labels).set(unrealized)
            if leverage:
                _position_leverage.labels(*labels).set(leverage)
            else:
                _position_leverage.labels(*labels).set(0)
    
    # 清除已平仓的仓位指标
    with _position_cache_lock:
        previous_labels = _position_labels_cache.get(account_key, set())
        closed_labels = previous_labels - current_labels
        
        for symbol, position_side in closed_labels:
            labels = (exchange, exchange_type, account_id, symbol, position_side)
            # 将已平仓的仓位指标设置为 0
            _position_quantity.labels(*labels).set(0)
            _position_entry_price.labels(*labels).set(0)
            _position_mark_price.labels(*labels).set(0)
            _position_unrealized_pnl.labels(*labels).set(0)
            _position_leverage.labels(*labels).set(0)
        
        # 更新缓存
        _position_labels_cache[account_key] = current_labels


__all__ = [
    "ensure_metrics_server",
    "update_balance_metrics",
    "record_balance_query_status",
    "update_order_metrics",
    "update_trade_metrics",
    "update_position_metrics",
]


