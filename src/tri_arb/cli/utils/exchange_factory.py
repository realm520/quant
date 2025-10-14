"""Exchange factory for routing spot/perp exchange types.

根据 --exchange-type 参数创建对应的 exchange 实例。
"""

import os
from enum import Enum
from typing import Optional

from tri_arb.exchanges.xt_spot import XTSpotExchange
from tri_arb.exchanges.xt_perp import XTPerpExchange


class ExchangeType(str, Enum):
    """交易类型枚举"""
    SPOT = "spot"
    PERP = "perp"


def create_exchange(
    exchange_type: ExchangeType,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None
):
    """根据 exchange-type 创建对应的 exchange 实例.

    Args:
        exchange_type: 交易类型 (spot 或 perp)
        api_key: API 密钥（可选，默认从环境变量读取）
        api_secret: API 密钥（可选，默认从环境变量读取）

    Returns:
        XTSpotExchange 或 XTPerpExchange 实例

    Raises:
        ValueError: 如果 exchange_type 无效或 API 凭证缺失
    """
    if exchange_type == ExchangeType.SPOT:
        key = api_key or os.getenv('XT_API_KEY')
        secret = api_secret or os.getenv('XT_API_SECRET')

        if not key or not secret:
            raise ValueError(
                "现货交易需要配置 XT_API_KEY 和 XT_API_SECRET 环境变量\n"
                "或使用 --api-key 和 --api-secret 参数"
            )

        return XTSpotExchange(api_key=key, api_secret=secret)

    elif exchange_type == ExchangeType.PERP:
        key = api_key or os.getenv('XT_PERP_API_KEY')
        secret = api_secret or os.getenv('XT_PERP_API_SECRET')

        if not key or not secret:
            raise ValueError(
                "永续合约交易需要配置 XT_PERP_API_KEY 和 XT_PERP_API_SECRET 环境变量\n"
                "或使用 --api-key 和 --api-secret 参数"
            )

        return XTPerpExchange(api_key=key, api_secret=secret)

    else:
        raise ValueError(f"不支持的交易类型: {exchange_type}")
