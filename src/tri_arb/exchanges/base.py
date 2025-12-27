"""Base exchange interface definition.

Defines abstract base class for all exchange adapters to ensure consistent
interface across different cryptocurrency exchanges.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from tri_arb.config.logging import get_logger
from tri_arb.core.models import Order, OrderBook, Price, Trade, TradingPair


logger = get_logger(__name__)


class BaseExchange(ABC):
    """Abstract base class for cryptocurrency exchange adapters.

    All exchange implementations must inherit from this class and implement
    the required methods for market data retrieval and order management.

    Attributes:
        name: Exchange name identifier
        is_connected: Connection status flag
    """

    def __init__(self, name: str) -> None:
        """Initialize exchange adapter.

        Args:
            name: Exchange name identifier
        """
        self.name = name
        self.is_connected = False
        logger.info("Exchange adapter initialized", exchange=name)

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to exchange.

        Initializes API clients and establishes WebSocket connections if needed.

        Raises:
            ExchangeConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to exchange.

        Cleanly shuts down API clients and WebSocket connections.
        """
        pass

    @abstractmethod
    async def get_ticker(
        self, trading_pair: TradingPair | None = None
    ) -> Price | list[Price]:
        """Get current ticker price for a trading pair or all markets.

        Supports both single-pair queries and batch queries for all active markets.

        Args:
            trading_pair: Trading pair to get ticker for. If None, returns all
                         active markets (batch query). Default is None.

        Returns:
            - If trading_pair is provided: Single Price object
            - If trading_pair is None: List of Price objects for all active markets

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
            NotImplementedError: If batch queries are not supported by this exchange

        Examples:
            Single pair query (backward compatible):
                >>> ticker = await exchange.get_ticker(btc_usdt_pair)
                >>> print(f"BTC/USDT: {ticker.bid_price}")

            Batch query for all markets:
                >>> tickers = await exchange.get_ticker(None)
                >>> print(f"Retrieved {len(tickers)} markets")
        """
        # Default implementation for exchanges that don't support batch queries
        if trading_pair is None:
            raise NotImplementedError(
                f"{self.name} exchange does not support batch ticker queries. "
                "Please provide a specific trading pair or upgrade to an exchange "
                "adapter that implements batch query support."
            )
        # Concrete implementations must override this method
        raise NotImplementedError(
            f"{self.name} exchange must implement get_ticker() method"
        )

    @abstractmethod
    async def get_orderbook(
        self, trading_pair: TradingPair, depth: int = 20
    ) -> OrderBook:
        """Get order book for a trading pair.

        Args:
            trading_pair: Trading pair to get order book for
            depth: Number of price levels to retrieve (default 20)

        Returns:
            Order book with bids and asks

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
        """
        pass

    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """Place a new order on the exchange.

        Args:
            order: Order to place

        Returns:
            Order with updated status and exchange order ID

        Raises:
            ExchangeConnectionError: If exchange is not connected
            OrderExecutionError: If order placement fails
            InsufficientLiquidityError: If insufficient liquidity
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.

        Args:
            order_id: Exchange order ID to cancel

        Returns:
            True if order was cancelled, False otherwise

        Raises:
            ExchangeConnectionError: If exchange is not connected
            OrderExecutionError: If cancellation fails
        """
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        """Get current status of an order.

        Args:
            order_id: Exchange order ID to query

        Returns:
            Order with current status

        Raises:
            ExchangeConnectionError: If exchange is not connected
            OrderExecutionError: If order not found
        """
        pass

    @abstractmethod
    async def get_trade_history(
        self, trading_pair: TradingPair, limit: int = 100
    ) -> list[Trade]:
        """Get recent trade history for a trading pair.

        Args:
            trading_pair: Trading pair to get trades for
            limit: Maximum number of trades to retrieve

        Returns:
            List of recent trades

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
        """
        pass

    @abstractmethod
    async def get_balance(self) -> dict[str, dict[str, Any]]:
        """Get account balances for all assets.

        Retrieves current balance information including available, frozen,
        and total amounts for each currency in the account.

        Returns:
            Dictionary mapping currency code to balance details:
            {
                "BTC": {
                    "available": Decimal("1.5"),    # Available for trading
                    "frozen": Decimal("0.5"),       # Locked in orders
                    "total": Decimal("2.0")         # Total balance
                },
                "USDT": {
                    "available": Decimal("50000.0"),
                    "frozen": Decimal("10000.0"),
                    "total": Decimal("60000.0")
                }
            }

        Raises:
            ExchangeConnectionError: If exchange is not connected
            AuthenticationError: If API credentials are invalid

        Note:
            - Currency codes are uppercase (BTC, USDT, ETH, etc.)
            - All amounts are Decimal type for precision
            - Implementations may filter out zero balances
            - total = available + frozen

        Examples:
            >>> balances = await exchange.get_balance()
            >>> btc_available = balances["BTC"]["available"]
            >>> print(f"Available BTC: {btc_available}")
        """
        pass

    @abstractmethod
    async def subscribe_ticker(self, trading_pair: TradingPair) -> AsyncIterator[Price]:
        """Subscribe to real-time ticker updates.

        Args:
            trading_pair: Trading pair to subscribe to

        Yields:
            Real-time price updates

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
        """
        pass

    @abstractmethod
    async def subscribe_orderbook(
        self, trading_pair: TradingPair, depth: int = 20
    ) -> AsyncIterator[OrderBook]:
        """Subscribe to real-time order book updates.

        Args:
            trading_pair: Trading pair to subscribe to
            depth: Number of price levels to stream

        Yields:
            Real-time order book updates

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
        """
        pass

    async def get_supported_pairs(self) -> list[TradingPair]:
        """Get list of supported trading pairs on this exchange.

        Returns:
            List of supported trading pairs

        Note:
            Default implementation returns empty list.
            Concrete implementations should override this method.
        """
        logger.debug(
            "get_supported_pairs called (default implementation)",
            exchange=self.name,
        )
        return []

    async def get_exchange_info(self) -> dict[str, Any]:
        """Get exchange metadata and configuration.

        Returns:
            Dictionary with exchange information (fees, limits, etc.)

        Note:
            Default implementation returns minimal info.
            Concrete implementations should override this method.
        """
        logger.debug(
            "get_exchange_info called (default implementation)",
            exchange=self.name,
        )
        return {
            "name": self.name,
            "is_connected": self.is_connected,
        }

    @abstractmethod
    async def get_trading_pair_info(
        self, trading_pair: TradingPair | None = None
    ) -> TradingPair | list[TradingPair]:
        """Get detailed trading pair information from exchange.

        Retrieves complete trading pair configuration including precision,
        trading limits, fees, and filters. Essential for validating orders
        before submission.

        Args:
            trading_pair: Trading pair to get info for. If None, returns all
                         supported trading pairs (batch query). Default is None.

        Returns:
            - If trading_pair is provided: Single TradingPair object with full info
            - If trading_pair is None: List of TradingPair objects for all supported pairs

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
            NotImplementedError: If batch queries are not supported by this exchange

        Examples:
            Single pair query:
                >>> pair_info = await exchange.get_trading_pair_info(btc_usdt_pair)
                >>> print(f"Maker fee: {pair_info.maker_fee}")

            Batch query for all pairs:
                >>> all_pairs = await exchange.get_trading_pair_info(None)
                >>> print(f"Exchange supports {len(all_pairs)} trading pairs")

        Note:
            The returned TradingPair objects include optional fields populated
            from exchange API:
            - maker_fee, taker_fee: Fee rates
            - price_min, price_max, price_step: Price constraints
            - quantity_min, quantity_max, quantity_step: Quantity constraints
            - min_notional: Minimum order value
            - trading_state: Current trading status
        """
        pass

    # ============================================================================
    # Helper Methods for CLI and String-based Queries
    # ============================================================================

    async def get_trading_pair_by_symbol(self, symbol: str) -> TradingPair:
        """Convert symbol string to TradingPair object.

        Helper method for CLI tools and string-based queries. Looks up the
        trading pair from cached exchange information.

        Args:
            symbol: Trading pair symbol in format "BASE/QUOTE" (e.g., "BTC/USDT")

        Returns:
            TradingPair object with complete exchange information

        Raises:
            ValueError: If symbol format is invalid or trading pair not found
            ExchangeConnectionError: If exchange is not connected

        Examples:
            >>> pair = await exchange.get_trading_pair_by_symbol("BTC/USDT")
            >>> price = await exchange.get_ticker(pair)

        Note:
            This method uses cached trading pair information from connect().
            If the trading pair list has changed, call refresh_trading_pairs()
            or reconnect to the exchange.
        """
        if not self.is_connected:
            raise ValueError(f"{self.name} exchange is not connected")

        # Parse symbol
        if "/" not in symbol:
            raise ValueError(
                f"Invalid symbol format: {symbol}. Expected format: BASE/QUOTE (e.g., BTC/USDT)"
            )

        base, quote = symbol.upper().split("/", 1)

        # Get all trading pairs (should use cache from connect())
        result = await self.get_trading_pair_info(None)

        # Type assertion: batch query returns list
        if not isinstance(result, list):
            raise ValueError(f"Expected list from batch query, got {type(result)}")

        all_pairs = result

        # Find matching pair
        for pair in all_pairs:
            if pair.base_currency == base and pair.quote_currency == quote:
                logger.debug(
                    "Trading pair found",
                    symbol=symbol,
                    exchange=self.name,
                )
                return pair

        # Not found
        raise ValueError(
            f"Trading pair not found: {symbol}. "
            f"Use get_supported_pairs() to see available pairs on {self.name}."
        )

    async def get_ticker_by_symbol(self, symbol: str) -> Price:
        """Get ticker by symbol string.

        Convenience method for CLI tools. Converts symbol to TradingPair
        and calls get_ticker().

        Args:
            symbol: Trading pair symbol in format "BASE/QUOTE" (e.g., "BTC/USDT")

        Returns:
            Price object with current market prices

        Raises:
            ValueError: If symbol invalid or trading pair not found
            ExchangeConnectionError: If exchange is not connected

        Examples:
            >>> price = await exchange.get_ticker_by_symbol("BTC/USDT")
            >>> print(f"Bid: {price.bid_price}, Ask: {price.ask_price}")

        Note:
            This is a convenience wrapper around get_ticker(). For batch queries
            or performance-critical code, use get_ticker() directly.
        """
        pair = await self.get_trading_pair_by_symbol(symbol)
        result = await self.get_ticker(pair)

        # Type assertion: single pair query returns Price
        if isinstance(result, list):
            raise ValueError(
                f"Unexpected batch result for single symbol query: {symbol}"
            )

        return result

    async def get_orderbook_by_symbol(self, symbol: str, depth: int = 20) -> OrderBook:
        """Get order book by symbol string.

        Convenience method for CLI tools. Converts symbol to TradingPair
        and calls get_orderbook().

        Args:
            symbol: Trading pair symbol in format "BASE/QUOTE" (e.g., "BTC/USDT")
            depth: Number of price levels to retrieve (default 20)

        Returns:
            OrderBook with bids and asks

        Raises:
            ValueError: If symbol invalid or trading pair not found
            ExchangeConnectionError: If exchange is not connected

        Examples:
            >>> orderbook = await exchange.get_orderbook_by_symbol("BTC/USDT", depth=50)
            >>> best_bid = orderbook.bids[0]
            >>> print(f"Best bid: {best_bid[0]} @ {best_bid[1]}")
        """
        pair = await self.get_trading_pair_by_symbol(symbol)
        return await self.get_orderbook(pair, depth)
