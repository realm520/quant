"""Parameter validators for CLI input validation."""

import re
from typing import Optional


def validate_symbol(symbol: str) -> str:
    """验证交易对格式（BTC/USDT）.

    Args:
        symbol: 交易对字符串

    Returns:
        标准化的交易对字符串（大写，斜杠分隔）

    Raises:
        ValueError: 如果格式无效
    """
    # 移除空格并转大写
    symbol = symbol.strip().upper()

    # 检查格式：XXX/YYY
    pattern = r'^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$'
    if not re.match(pattern, symbol):
        raise ValueError(
            f"交易对格式无效: {symbol}\n"
            f"正确格式: BTC/USDT, ETH/BTC 等（字母/数字组合，斜杠分隔）"
        )

    return symbol


def validate_leverage(leverage: int) -> int:
    """验证杠杆范围（1-125）.

    Args:
        leverage: 杠杆倍数

    Returns:
        验证后的杠杆倍数

    Raises:
        ValueError: 如果超出范围
    """
    if not isinstance(leverage, int):
        raise ValueError(f"杠杆倍数必须是整数，收到: {type(leverage).__name__}")

    if leverage < 1 or leverage > 125:
        raise ValueError(
            f"杠杆倍数超出范围: {leverage}\n"
            f"有效范围: 1-125"
        )

    return leverage


def validate_interval(interval: int) -> int:
    """验证刷新间隔（1-60 秒）.

    Args:
        interval: 刷新间隔（秒）

    Returns:
        验证后的刷新间隔

    Raises:
        ValueError: 如果超出范围
    """
    if not isinstance(interval, int):
        raise ValueError(f"刷新间隔必须是整数，收到: {type(interval).__name__}")

    if interval < 1 or interval > 60:
        raise ValueError(
            f"刷新间隔超出范围: {interval} 秒\n"
            f"有效范围: 1-60 秒"
        )

    return interval


def validate_limit(limit: int, min_limit: int = 5, max_limit: int = 50) -> int:
    """验证档数/数量限制（默认 5-50）.

    Args:
        limit: 档数/数量
        min_limit: 最小值（默认 5）
        max_limit: 最大值（默认 50）

    Returns:
        验证后的档数

    Raises:
        ValueError: 如果超出范围
    """
    if not isinstance(limit, int):
        raise ValueError(f"档数必须是整数，收到: {type(limit).__name__}")

    if limit < min_limit or limit > max_limit:
        raise ValueError(
            f"档数超出范围: {limit}\n"
            f"有效范围: {min_limit}-{max_limit}"
        )

    return limit


def validate_price(price: Optional[float]) -> Optional[float]:
    """验证价格参数.

    Args:
        price: 价格（可选）

    Returns:
        验证后的价格

    Raises:
        ValueError: 如果价格无效
    """
    if price is None:
        return None

    if not isinstance(price, (int, float)):
        raise ValueError(f"价格必须是数字，收到: {type(price).__name__}")

    if price <= 0:
        raise ValueError(f"价格必须大于 0，收到: {price}")

    return float(price)


def validate_quantity(quantity: float) -> float:
    """验证数量参数.

    Args:
        quantity: 数量

    Returns:
        验证后的数量

    Raises:
        ValueError: 如果数量无效
    """
    if not isinstance(quantity, (int, float)):
        raise ValueError(f"数量必须是数字，收到: {type(quantity).__name__}")

    if quantity <= 0:
        raise ValueError(f"数量必须大于 0，收到: {quantity}")

    return float(quantity)
