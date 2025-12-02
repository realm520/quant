"""合约乘数服务.

负责为不同交易所提供合约乘数 (contract_size / contract multiplier) 查询能力。

设计目标：
- 对外暴露统一接口：get_multiplier(exchange, symbol)
- 内部使用交易所适配器（目前支持 xt_perp），并带有简单缓存
- Binance USDT 永续：默认 1（1 张合约 = 1 个币）
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Tuple

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.core.models import TradingPair


logger = get_logger(__name__)


@dataclass
class ContractMultiplierService:
    """合约乘数查询服务.

    注意：此服务本身不持有数据库会话，只依赖交易所 REST API。
    """

    xt_exchange: XTPerpExchange | None = None

    def __post_init__(self) -> None:
        # 简单缓存：key = (exchange, symbol)，value = Decimal
        self._cache: Dict[Tuple[str, str], Decimal] = {}

    async def get_multiplier(self, exchange: str, symbol: str) -> Decimal:
        """获取指定交易所、交易对的合约乘数.

        Args:
            exchange: 交易所标识，例如 "binance", "xt"
            symbol: 交易对，例如 "BTCUSDT" / "BTC/USDT" / "btc_usdt"
        """
        ex = exchange.lower()
        cache_key = (ex, symbol)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if ex == "binance":
            # Binance USDT 线性永续：1 张合约 = 1 个币
            multiplier = Decimal("1")
        elif ex == "xt":
            multiplier = await self._get_xt_multiplier(symbol)
        else:
            logger.warning("Unsupported exchange for contract multiplier, using 1", exchange=exchange, symbol=symbol)
            multiplier = Decimal("1")

        self._cache[cache_key] = multiplier
        return multiplier

    async def _get_xt_multiplier(self, symbol: str) -> Decimal:
        """从 XT 永续合约配置中获取合约乘数 (contractSize)."""
        if not self.xt_exchange:
            logger.warning("XTPerpExchange not provided, using multiplier 1 for xt", symbol=symbol)
            return Decimal("1")

        # 归一化 symbol 到 BASE/QUOTE
        try:
            base, quote = self._normalize_symbol_to_base_quote(symbol)
        except ValueError as e:
            logger.warning("Failed to normalize XT symbol, using multiplier 1", symbol=symbol, error=str(e))
            return Decimal("1")

        try:
            # XTPerpExchange 要求先 connect
            if not getattr(self.xt_exchange, "is_connected", False):
                await self.xt_exchange.connect()

            pair = TradingPair(
                base_currency=base,
                quote_currency=quote,
                exchange="xt_perp",
                # 下面这些字段只是为了构造 TradingPair 对象，实际会在 get_trading_pair 中被完整替换
                min_order_size=Decimal("0.001"),
                max_order_size=Decimal("1000000"),
                price_precision=8,
                quantity_precision=8,
            )
            trading_pair = await self.xt_exchange.get_trading_pair(pair)
            if trading_pair.contract_size and trading_pair.contract_size > 0:
                return trading_pair.contract_size

            logger.warning(
                "XT trading pair has no valid contract_size, using 1",
                symbol=symbol,
                base=base,
                quote=quote,
            )
            return Decimal("1")
        except Exception as e:
            logger.warning("Failed to fetch XT contract multiplier, using 1", symbol=symbol, error=str(e))
            return Decimal("1")

    @staticmethod
    def _normalize_symbol_to_base_quote(symbol: str) -> Tuple[str, str]:
        """将 symbol 归一化为 (BASE, QUOTE)，例如:

        - BTCUSDT -> (BTC, USDT)
        - btc_usdt -> (BTC, USDT)
        - BTC/USDT -> (BTC, USDT)
        """
        s = symbol.replace("_", "").replace("-", "").replace("/", "").upper()

        # 目前主要支持 USDT 永续
        if s.endswith("USDT"):
            return s[:-4], "USDT"

        raise ValueError(f"Unsupported XT symbol format: {symbol}")


