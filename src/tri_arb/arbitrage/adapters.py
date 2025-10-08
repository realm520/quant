"""Exchange adapters for arbitrage monitoring.

Provides lightweight adapters to convert between different exchange interfaces
and the ExchangeProtocol expected by ArbitrageMonitor.
"""

from decimal import Decimal

from tri_arb.config.logging import get_logger
from tri_arb.core.models import Price, TradingPair
from tri_arb.exchanges.xt import XTExchange
from tri_arb.models.exchange import Ticker


logger = get_logger(__name__)


class XTExchangeAdapter:
    """Adapter for XTExchange to ExchangeProtocol interface.

    Converts between:
    - XTExchange (returns Price objects with TradingPair)
    - ExchangeProtocol (expects Ticker objects with symbol strings)

    This adapter provides a lightweight conversion layer without caching.
    """

    def __init__(self, api_key: str, api_secret: str):
        """Initialize XTExchange adapter.

        Args:
            api_key: XT API key for authentication
            api_secret: XT API secret for HMAC signature
        """
        self._xt = XTExchange(
            name="xt",
            api_key=api_key,
            api_secret=api_secret,
        )
        logger.info("XTExchangeAdapter initialized")

    async def connect(self) -> None:
        """Connect to XT Exchange."""
        await self._xt.connect()
        logger.info("XTExchangeAdapter connected")

    async def disconnect(self) -> None:
        """Disconnect from XT Exchange."""
        if self._xt.is_connected:
            await self._xt.disconnect()
            logger.info("XTExchangeAdapter disconnected")

    async def get_ticker(self, symbol: str | None = None) -> list[Ticker]:
        """Get ticker data from XT Exchange.

        Converts XTExchange.get_ticker() (Price) to ExchangeProtocol (Ticker).

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT").
                   If None, returns all active markets.

        Returns:
            List of Ticker objects

        Raises:
            ValueError: If exchange not connected or symbol invalid
            httpx.HTTPStatusError: If API request fails
            httpx.TimeoutException: If request times out
        """
        # Convert symbol string to TradingPair if provided
        trading_pair = self._symbol_to_trading_pair(symbol) if symbol else None

        # Call XTExchange.get_ticker()
        prices = await self._xt.get_ticker(trading_pair)

        # Ensure we have a list (single Price -> list[Price])
        if isinstance(prices, Price):
            prices = [prices]

        # Convert Price objects to Ticker objects
        tickers = [self._price_to_ticker(price) for price in prices]

        logger.info(
            "Tickers retrieved",
            symbol=symbol,
            count=len(tickers),
        )

        return tickers

    def _symbol_to_trading_pair(self, symbol: str) -> TradingPair:
        """Convert symbol string to TradingPair object.

        Creates a minimal TradingPair with conservative defaults.

        Args:
            symbol: Trading pair symbol (e.g., "BTC/USDT")

        Returns:
            TradingPair object with minimal configuration

        Raises:
            ValueError: If symbol format is invalid

        Examples:
            >>> adapter._symbol_to_trading_pair("BTC/USDT")
            TradingPair(base_currency="BTC", quote_currency="USDT", ...)
        """
        if "/" not in symbol:
            raise ValueError(
                f"Invalid symbol format: {symbol}. Expected format: BASE/QUOTE (e.g., BTC/USDT)"
            )

        base, quote = symbol.split("/", 1)

        # Create minimal TradingPair with conservative defaults
        # These values are safe for read-only ticker queries
        return TradingPair(
            base_currency=base.upper(),
            quote_currency=quote.upper(),
            exchange="xt",
            min_order_size=Decimal("0.00001"),  # Conservative minimum
            max_order_size=Decimal("1000000"),  # Conservative maximum
            price_precision=8,                  # Standard precision
            quantity_precision=8,               # Standard precision
        )

    def _price_to_ticker(self, price: Price) -> Ticker:
        """Convert Price object to Ticker object.

        Extracts ticker data from Price and converts TradingPair to symbol string.

        Args:
            price: Price object from XTExchange

        Returns:
            Ticker object for ArbitrageMonitor

        Examples:
            >>> price = Price(
            ...     trading_pair=TradingPair(base_currency="BTC", quote_currency="USDT", ...),
            ...     bid_price=Decimal("50000"),
            ...     ask_price=Decimal("50001"),
            ...     bid_volume=Decimal("10.5"),
            ...     ask_volume=Decimal("8.3"),
            ...     timestamp=datetime.utcnow(),
            ...     exchange="xt"
            ... )
            >>> ticker = adapter._price_to_ticker(price)
            >>> ticker.symbol
            'BTC/USDT'
        """
        # Convert TradingPair to symbol string
        symbol = f"{price.trading_pair.base_currency}/{price.trading_pair.quote_currency}"

        return Ticker(
            symbol=symbol,
            bid=price.bid_price,
            ask=price.ask_price,
            bid_volume=price.bid_volume,
            ask_volume=price.ask_volume,
            timestamp=price.timestamp,
        )
