"""Exchange factory for routing spot/perp exchange types across multiple exchanges.

根据 --exchange 和 --exchange-type 参数创建对应的 exchange 实例。
"""

import os
from enum import Enum
from typing import Optional

from tri_arb.exchanges.base import BaseExchange
from tri_arb.exchanges.xt_spot import XTSpotExchange
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.exchanges.binance_spot import BinanceSpotExchange
from tri_arb.exchanges.binance_perp import BinancePerpExchange
from tri_arb.exchanges.okx_perp import OKXPerpExchange
from tri_arb.exchanges.gate_perp import GatePerpExchange


class ExchangeName(str, Enum):
    """交易所名称枚举"""
    XT = "xt"
    BINANCE = "binance"
    OKX = "okx"
    GATE = "gate"


class ExchangeType(str, Enum):
    """交易类型枚举"""
    SPOT = "spot"
    PERP = "perp"


def create_exchange(
    exchange_type: ExchangeType,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    exchange_name: ExchangeName = ExchangeName.XT
) -> BaseExchange:
    """根据 exchange 和 exchange-type 创建对应的 exchange 实例.

    Args:
        exchange_type: 交易类型 (spot 或 perp)
        api_key: API 密钥（可选，默认从环境变量读取）
        api_secret: API 密钥（可选，默认从环境变量读取）
        exchange_name: 交易所名称 (xt 或 binance)，默认 xt

    Returns:
        对应的 Exchange 实例

    Raises:
        ValueError: 如果 exchange_type 无效或 API 凭证缺失
    """
    # 根据交易所和交易类型获取环境变量前缀
    env_prefix = _get_env_prefix(exchange_name, exchange_type)
    
    # 从环境变量或参数获取 API 凭证
    key = api_key or os.getenv(f'{env_prefix}_API_KEY', '')
    secret = api_secret or os.getenv(f'{env_prefix}_API_SECRET', '')

    # XT 交易所
    if exchange_name == ExchangeName.XT:
        if exchange_type == ExchangeType.SPOT:
            if not key or not secret:
                raise ValueError(
                    f"XT 现货交易需要配置 {env_prefix}_API_KEY 和 {env_prefix}_API_SECRET 环境变量\n"
                    "或使用 --api-key 和 --api-secret 参数"
                )
            return XTSpotExchange(api_key=key, api_secret=secret)
        
        elif exchange_type == ExchangeType.PERP:
            if not key or not secret:
                raise ValueError(
                    f"XT 永续合约需要配置 {env_prefix}_API_KEY 和 {env_prefix}_API_SECRET 环境变量\n"
                    "或使用 --api-key 和 --api-secret 参数"
                )
            return XTPerpExchange(api_key=key, api_secret=secret)

    # Binance 交易所
    elif exchange_name == ExchangeName.BINANCE:
        if exchange_type == ExchangeType.SPOT:
            # Binance 现货不强制要求 API 凭证（公开 API 可用，占位符模式）
            return BinanceSpotExchange(api_key=key, api_secret=secret)
        
        elif exchange_type == ExchangeType.PERP:
            # Binance 永续合约（占位符实现）
            return BinancePerpExchange(api_key=key, api_secret=secret)

    # OKX 交易所
    elif exchange_name == ExchangeName.OKX:
        # OKX 需要额外的 passphrase
        passphrase = os.getenv(f'{env_prefix}_PASSPHRASE', '')
        
        if exchange_type == ExchangeType.PERP:
            # OKX 永续合约
            return OKXPerpExchange(api_key=key, api_secret=secret, passphrase=passphrase)
        elif exchange_type == ExchangeType.SPOT:
            raise ValueError(
                "OKX 现货交易暂未实现\n"
                "请使用永续合约: --exchange-type perp"
            )
    
    # Gate.io 交易所
    elif exchange_name == ExchangeName.GATE:
        if exchange_type == ExchangeType.PERP:
            # Gate.io 永续合约
            return GatePerpExchange(api_key=key, api_secret=secret)
        elif exchange_type == ExchangeType.SPOT:
            raise ValueError(
                "Gate.io 现货交易暂未实现\n"
                "请使用永续合约: --exchange-type perp"
            )

    raise ValueError(f"不支持的交易所或交易类型: {exchange_name.value}/{exchange_type.value}")


def _get_env_prefix(exchange_name: ExchangeName, exchange_type: ExchangeType) -> str:
    """获取环境变量前缀.
    
    Args:
        exchange_name: 交易所名称
        exchange_type: 交易类型
        
    Returns:
        环境变量前缀字符串
        
    Note:
        现货和永续合约使用相同的 API key，只需要根据交易所名称区分环境变量。
    """
    # 现货和永续合约共用同一个 API key
    return exchange_name.value.upper()
