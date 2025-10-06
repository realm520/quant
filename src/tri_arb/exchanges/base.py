"""Base exchange interface definition.

Defines abstract base class for all exchange adapters to ensure consistent
interface across different cryptocurrency exchanges.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional

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
    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        """Get current ticker price for a trading pair.

        Args:
            trading_pair: Trading pair to get ticker for

        Returns:
            Current price information with bid/ask

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
        """
        pass

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
    ) -> List[Trade]:
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
    async def subscribe_ticker(
        self, trading_pair: TradingPair
    ) -> AsyncIterator[Price]:
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

    async def get_supported_pairs(self) -> List[TradingPair]:
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

    async def get_exchange_info(self) -> Dict[str, any]:
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
