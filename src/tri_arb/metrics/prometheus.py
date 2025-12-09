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

# 跟踪每个账户的当前订单标签，用于清除已取消/成交的订单
# 标签格式: (exchange, exchange_type, account_id, symbol, side, position_side, order_type)
_order_labels_cache: dict[tuple[str, str, str], set[tuple[str, str, str, str, str, str, str]]] = {}
_order_cache_lock = threading.Lock()

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

_margin_usage_ratio = Gauge(
    "exchange_margin_usage_ratio",
    "Margin usage ratio (percentage) per account and exchange. For Binance: (balance - maxWithdrawAmount) / balance. For XT: (openOrderMarginFrozen + isolatedMargin + crossedMargin) / totalAmount * 100%.",
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
    "Number of active orders per account, exchange, symbol, side, position side, and order type.",
    ["exchange", "exchange_type", "account_id", "symbol", "side", "position_side", "order_type", "status"],
)

_order_notional = Gauge(
    "exchange_order_notional",
    "Total notional value of orders per account, exchange, symbol, side, position side, and order type.",
    ["exchange", "exchange_type", "account_id", "symbol", "side", "position_side", "order_type"],
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
    
    Note: This function uses a global lock to prevent multiple threads from
    starting the server simultaneously. However, if the server fails to start,
    it will still mark as started to avoid repeated attempts. In this case,
    you may need to restart the process or check the logs for errors.
    """
    global _SERVER_STARTED
    if _SERVER_STARTED:
        # Double-check if server is actually running by trying to connect
        # This helps recover from cases where the server was marked as started
        # but actually failed to start
        target_port = port or _DEFAULT_PORT
        try:
            import socket
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(0.1)
            result = test_socket.connect_ex(('localhost', target_port))
            test_socket.close()
            if result == 0:
                # Port is open, server is likely running
        return
            else:
                # Port is not open, but we marked as started - reset and retry
                logger.warning(
                    f"Metrics server was marked as started but port {target_port} is not accessible. "
                    "Resetting state and retrying..."
                )
                _SERVER_STARTED = False
        except Exception:
            # If check fails, assume server might be running and return
            pass
    
    with _SERVER_LOCK:
        # Check again after acquiring lock
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
            # Verify server is actually accessible
            try:
                import socket
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(0.5)
                result = test_socket.connect_ex(('localhost', target_port))
                test_socket.close()
                if result == 0:
                    logger.info(f"Verified: Metrics server is accessible on port {target_port}")
                else:
                    logger.warning(f"Metrics server started but port {target_port} is not accessible")
            except Exception as verify_error:
                logger.warning(f"Could not verify metrics server accessibility: {verify_error}")
        except OSError as e:
            logger.error(
                f"Failed to start Prometheus metrics server on port {target_port}: {e}. "
                "Another process may already be using this port. "
                "Please check if another instance is running or if the port is blocked."
            )
            # Don't mark as started if we failed - allow retry on next call
            # This helps recover from transient errors
            _SERVER_STARTED = False
            raise


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
        # 调试：记录 XT 账号的原始数据（用于排查保证金占用率计算问题）
        if exchange.lower() == "xt" and asset.upper() == "USDT":
            logger.info(
                "XT balance data for margin usage calculation",
                account_id=account_id,
                asset=asset,
                data_keys=list(data.keys()),
                totalAmount_raw=data.get("totalAmount"),
                totalAmount_type=type(data.get("totalAmount")).__name__ if data.get("totalAmount") is not None else None,
                openOrderMarginFrozen=data.get("openOrderMarginFrozen"),
                isolatedMargin=data.get("isolatedMargin"),
                crossedMargin=data.get("crossedMargin"),
                walletBalance=data.get("walletBalance"),
                marginBalance=data.get("marginBalance"),
            )
        asset_label = (asset or "").upper()
        labels = (exchange, exchange_type, account_id, asset_label)
        available = _to_float(data.get("available"))
        frozen = _to_float(data.get("frozen"))
        total = _to_float(data.get("total"))

        _balance_available.labels(*labels).set(available)
        _balance_frozen.labels(*labels).set(frozen)
        _balance_total.labels(*labels).set(total)
        
        # 计算保证金占用率
        margin_usage_ratio = 0.0
        if exchange.lower() == "binance":
            # Binance: 保证金占用率 ≈ (balance - maxWithdrawAmount) / balance
            # 如果没有 maxWithdrawAmount，用 frozen / total 近似
            max_withdraw = _to_float(data.get("maxWithdrawAmount"))
            if max_withdraw is not None and max_withdraw >= 0 and total > 0:
                margin_usage_ratio = ((total - max_withdraw) / total) * 100.0
            elif total > 0:
                # 使用 frozen / total 作为近似值
                margin_usage_ratio = (frozen / total) * 100.0
        elif exchange.lower() == "xt":
            # XT: 保证金占有率 = (openOrderMarginFrozen + isolatedMargin + crossedMargin) / totalAmount × 100%
            # 注意：只有 USDT 等保证金资产才需要计算保证金占用率，其他资产（如 BTC、TRUMP、XRP）通常不需要
            # 如果数据缺少必要字段，跳过计算（避免错误日志）
            if asset_label != "USDT":
                # 非 USDT 资产通常不需要计算保证金占用率，跳过
                continue
            
            open_order_margin_frozen = _to_float(data.get("openOrderMarginFrozen", data.get("frozen", 0)))
            isolated_margin = _to_float(data.get("isolatedMargin", 0))
            crossed_margin = _to_float(data.get("crossedMargin", 0))
            # totalAmount 是 API 返回的总权益，必须使用 API 返回的 totalAmount 字段
            # 注意：不要使用 marginBalance，因为 marginBalance 是保证金余额，不是总权益
            # 也不要使用 walletBalance，因为 walletBalance 是钱包余额，不是总权益
            total_amount_raw = data.get("totalAmount")
            total_amount = _to_float(total_amount_raw) if total_amount_raw is not None else 0.0
            
            if total_amount <= 0:
                # 如果 totalAmount 不存在或为 0，记录错误并尝试使用 walletBalance 作为备选
                logger.warning(
                    "XT balance data missing or zero totalAmount, trying walletBalance as fallback",
                    account_id=account_id,
                    asset=asset_label,
                    has_totalAmount="totalAmount" in data,
                    totalAmount_value=total_amount_raw,
                    totalAmount_float=total_amount,
                    available_keys=list(data.keys())[:10],  # 只显示前10个键，避免日志过长
                )
                # 尝试使用 walletBalance 作为备选（虽然不准确，但比 0 好）
                wallet_balance = _to_float(data.get("walletBalance", 0))
                if wallet_balance > 0:
                    total_amount = wallet_balance
                    logger.info(
                        "Using walletBalance as fallback for totalAmount",
                        account_id=account_id,
                        asset=asset_label,
                        walletBalance=wallet_balance,
                    )
                else:
                    margin_usage_ratio = 0.0
                    logger.error(
                        "Cannot calculate XT margin usage ratio: totalAmount and walletBalance are both 0",
                        account_id=account_id,
                        asset=asset_label,
                    )
                    _margin_usage_ratio.labels(*labels).set(margin_usage_ratio)
                    continue  # 跳过这个资产
            
            if total_amount > 0:
                margin_usage = open_order_margin_frozen + isolated_margin + crossed_margin
                margin_usage_ratio = (margin_usage / total_amount) * 100.0
                logger.info(
                    "Calculated XT margin usage ratio",
                    account_id=account_id,
                    asset=asset_label,
                    open_order_margin_frozen=open_order_margin_frozen,
                    isolated_margin=isolated_margin,
                    crossed_margin=crossed_margin,
                    margin_usage=margin_usage,
                    total_amount=total_amount,
                    margin_usage_ratio=margin_usage_ratio,
                )
            else:
                margin_usage_ratio = 0.0
                logger.warning(
                    "XT total_amount is 0, cannot calculate margin usage ratio",
                    account_id=account_id,
                    asset=asset_label,
                    total_amount_raw=total_amount_raw,
                    total_amount=total_amount,
                )
        
        _margin_usage_ratio.labels(*labels).set(margin_usage_ratio)


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
    
    # 订单类型（LIMIT, MARKET, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET 等）
    order_type = (
        order_data.get("orderType")
        or order_data.get("type")  # Binance
        or order_data.get("ordType")  # OKX
        or order_data.get("order_type")
        or "LIMIT"  # 默认
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
    
    # 更新指标（包含订单类型）
    labels = (exchange, exchange_type, account_id, symbol, side, position_side, order_type)
    
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


def update_active_orders_metrics(
    exchange: str,
    exchange_type: str,
    account_id: str,
    orders: list[Mapping[str, Any]],
) -> None:
    """批量更新所有活跃订单的 Prometheus metrics.
    
    这个函数用于定期查询所有活跃订单并更新 metrics，确保 metrics 反映当前实际的挂单数量。
    
    Args:
        exchange: Exchange name (e.g., "binance", "xt")
        exchange_type: Exchange type (e.g., "perp", "spot")
        account_id: Account ID
        orders: List of active order dictionaries
    """
    # 活跃订单状态列表
    active_statuses = ["NEW", "LIVE", "PARTIALLY_FILLED", "OPEN"]
    
    # 用于跟踪所有订单的标签组合（包含订单类型）
    # 标签格式: (exchange, exchange_type, account_id, symbol, side, position_side, order_type)
    all_order_labels: set[tuple[str, str, str, str, str, str, str]] = set()
    
    # 处理每个订单
    for order_data in orders:
        # 提取订单信息（支持不同交易所格式）
        symbol = (
            order_data.get("symbol") 
            or order_data.get("s")  # Binance
            or order_data.get("instId")  # OKX
            or order_data.get("contract")  # Gate
            or ""
        ).upper()
        
        if not symbol:
            continue  # 跳过没有交易对的订单
        
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
        
        # 订单类型（LIMIT, MARKET, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET 等）
        order_type = (
            order_data.get("orderType")
            or order_data.get("type")  # Binance
            or order_data.get("ordType")  # OKX
            or order_data.get("order_type")
            or "LIMIT"  # 默认
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
        
        # 更新指标（包含订单类型）
        labels = (exchange, exchange_type, account_id, symbol, side, position_side, order_type)
        all_order_labels.add(labels)
        
        is_active = status in active_statuses
        
        # 更新订单数量（活跃订单为1，非活跃为0）
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
            _order_notional.labels(*labels).set(0)
    
    # 清除不再存在的订单的 metrics（设置为 0）
    # 使用缓存机制跟踪当前活跃的订单，清除已取消/成交的订单
    account_key = (exchange, exchange_type, account_id)
    with _order_cache_lock:
        # 获取之前缓存的订单标签
        previous_labels = _order_labels_cache.get(account_key, set())
        
        # 清除不再存在的订单的 metrics
        for old_labels in previous_labels:
            if old_labels not in all_order_labels:
                # 订单已不存在，清除所有状态的 metrics
                for active_status in active_statuses:
                    _order_count.labels(*old_labels, active_status).set(0)
                _order_notional.labels(*old_labels).set(0)
        
        # 更新缓存
        _order_labels_cache[account_key] = all_order_labels


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
    # 支持多种格式：
    # 1. trades 列表格式: {"trades": [...]}
    # 2. 单个成交对象格式: {"trade_id": "...", "symbol": "...", ...}
    # 3. XT WebSocket 格式: {"orderId": "...", "orderSide": "...", ...}
    trades = []
    if "trades" in trade_data and isinstance(trade_data.get("trades"), list):
        trades = trade_data.get("trades", [])
    elif isinstance(trade_data, list):
        # 如果 trade_data 本身就是列表
        trades = trade_data
    elif "orderId" in trade_data or "order_id" in trade_data or "trade_id" in trade_data or "tradeId" in trade_data:
        # 单个成交对象（包括 XT 格式），转换为列表
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
        
        # XT 使用 orderSide，其他使用 side
        side = (
            trade.get("orderSide")  # XT
            or trade.get("side") 
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
    "update_active_orders_metrics",
    "update_trade_metrics",
    "update_position_metrics",
]


