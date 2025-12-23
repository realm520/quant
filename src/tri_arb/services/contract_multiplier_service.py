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

import httpx

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
        # 同步 HTTP 客户端（用于公开 API 调用）
        self._sync_client: httpx.Client | None = None
        # XT 交易对配置缓存（批量获取后缓存）
        self._xt_symbol_configs: Dict[str, Decimal] = {}
        self._xt_configs_loaded: bool = False

    def get_multiplier_sync(self, exchange: str, symbol: str) -> Decimal:
        """同步获取指定交易所、交易对的合约乘数（用于同步上下文）.
        
        Args:
            exchange: 交易所标识，例如 "binance", "xt"
            symbol: 交易对，例如 "BTCUSDT" / "BTC/USDT" / "btc_usdt"
        
        Returns:
            合约乘数（Decimal）
        """
        ex = exchange.lower()
        cache_key = (ex, symbol)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if ex == "binance":
            # Binance USDT 线性永续：1 张合约 = 1 个币
            multiplier = Decimal("1")
        elif ex == "xt":
            multiplier = self._get_xt_multiplier_sync(symbol)
        else:
            logger.warning("Unsupported exchange for contract multiplier, using 1", exchange=exchange, symbol=symbol)
            multiplier = Decimal("1")

        self._cache[cache_key] = multiplier
        return multiplier

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

    def _load_xt_symbol_configs(self) -> None:
        """批量加载所有 XT 交易对的配置信息（包括合约乘数）.
        
        使用公开 API: https://fapi.xt.com/future/market/v3/public/symbol/list
        不需要 API key，一次性获取所有交易对的配置。
        """
        if self._xt_configs_loaded:
            return
        
        try:
            # 初始化同步 HTTP 客户端（如果还没有）
            if self._sync_client is None:
                self._sync_client = httpx.Client(
                    base_url="https://fapi.xt.com",
                    timeout=httpx.Timeout(10.0, connect=5.0),
                )
            
            # 调用批量获取 API
            response = self._sync_client.get(
                "/future/market/v3/public/symbol/list",
            )
            response.raise_for_status()
            data = response.json()
            
            # 检查返回码
            if data.get("returnCode") != 0:
                error_msg = data.get("msgInfo", "Unknown error")
                logger.warning(
                    f"XT API 返回错误，无法加载交易对配置",
                    error=error_msg,
                )
                self._xt_configs_loaded = True  # 标记为已尝试加载，避免重复请求
                return
            
            # 解析所有交易对的配置
            symbols = data.get("result", [])
            
            # 类型检查：确保 result 是列表
            if not isinstance(symbols, list):
                logger.warning(
                    f"XT API 返回的 result 不是列表类型，无法加载交易对配置",
                    result_type=type(symbols).__name__,
                    result_value=str(symbols)[:100] if isinstance(symbols, str) else symbols,
                )
                self._xt_configs_loaded = True
                return
            
            loaded_count = 0
            for symbol_config in symbols:
                # 类型检查：确保每个元素是字典
                if not isinstance(symbol_config, dict):
                    logger.debug(
                        f"跳过非字典类型的交易对配置项",
                        item_type=type(symbol_config).__name__,
                    )
                    continue
                
                # 存储时也使用与查找时相同的归一化逻辑，确保一致性
                original_symbol = symbol_config.get("symbol", "")
                symbol = original_symbol.lower().replace("/", "_").replace("-", "_")
                contract_size = symbol_config.get("contractSize")
                
                if symbol and contract_size is not None:
                    try:
                        multiplier = Decimal(str(contract_size))
                        if multiplier > 0:
                            self._xt_symbol_configs[symbol] = multiplier
                            loaded_count += 1
                    except (ValueError, TypeError):
                        pass
            
            self._xt_configs_loaded = True
            logger.info(
                f"成功加载 {loaded_count} 个 XT 交易对的合约乘数配置",
                loaded_count=loaded_count,
            )
            
        except httpx.HTTPError as e:
            logger.warning(
                f"批量获取 XT 交易对配置失败（HTTP 错误）",
                error=str(e),
            )
            self._xt_configs_loaded = True  # 标记为已尝试加载，避免重复请求
        except Exception as e:
            logger.warning(
                f"批量获取 XT 交易对配置失败",
                error=str(e),
            )
            self._xt_configs_loaded = True  # 标记为已尝试加载，避免重复请求

    def _get_xt_multiplier_sync(self, symbol: str) -> Decimal:
        """同步从缓存或批量配置中获取 XT 合约乘数 (contractSize).
        
        首次调用时会批量加载所有交易对的配置，后续直接从缓存读取。
        """
        # 确保已加载配置
        if not self._xt_configs_loaded:
            self._load_xt_symbol_configs()
        
        # 归一化 symbol 格式（XT API 使用小写下划线格式，如 iota_usdt）
        normalized_symbol = symbol.lower().replace("/", "_").replace("-", "_")
        
        # 从缓存中查找
        if normalized_symbol in self._xt_symbol_configs:
            return self._xt_symbol_configs[normalized_symbol]
        
        # 如果缓存中没有，记录警告并使用默认值
        logger.debug(
            f"XT 交易对 {symbol} 的合约乘数未找到，使用默认值 1",
            symbol=symbol,
            normalized_symbol=normalized_symbol,
        )
        return Decimal("1")

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


