"""OKX exchange adapter placeholder implementation.

Provides stub implementation of OKX exchange integration for MVP scaffold.
This is a placeholder that returns mock data and logs operations.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator, List
from uuid import uuid4

from tri_arb.config.logging import get_logger
from tri_arb.core.models import Order, OrderBook, OrderSide, OrderStatus, Price, Trade, TradingPair
from tri_arb.exchanges.base import BaseExchange

logger = get_logger(__name__)


class OKXExchange(BaseExchange):
    """OKX exchange adapter placeholder implementation.

    This is a stub implementation for MVP scaffold that returns placeholder
    responses for all operations. Actual OKX API integration will be
    implemented in future iterations.

    Attributes:
        api_key: API key for authentication (placeholder)
        api_secret: API secret for authentication (placeholder)
        passphrase: API passphrase for authentication (placeholder)
    """

    def __init__(
        self,
        name: str = "okx",
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
    ) -> None:
        """Initialize OKX exchange adapter.

        Args:
            name: Exchange name identifier
            api_key: OKX API key (placeholder for MVP)
            api_secret: OKX API secret (placeholder for MVP)
            passphrase: OKX API passphrase (placeholder for MVP)
        """
        super().__init__(name)
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        logger.info(
            "OKXExchange initialized (placeholder mode)",
            has_api_key=bool(api_key),
        )

    async def connect(self) -> None:
        """Establish connection to OKX (placeholder).

        Note:
            This is a placeholder implementation for MVP scaffold.
        """
        logger.info("connect called (placeholder mode)", exchange=self.name)
        self.is_connected = True
        logger.debug("Connection established (placeholder)", exchange=self.name)

    async def disconnect(self) -> None:
        """Close connection to OKX (placeholder).

        Note:
            This is a placeholder implementation for MVP scaffold.
        """
        logger.info("disconnect called (placeholder mode)", exchange=self.name)
        self.is_connected = False
        logger.debug("Connection closed (placeholder)", exchange=self.name)

    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        """Get current ticker price (placeholder).

        Args:
            trading_pair: Trading pair to get ticker for

        Returns:
            Placeholder price with mock bid/ask values

        Note:
            This is a placeholder implementation for MVP scaffold.
        """
        logger.info(
            "get_ticker called (placeholder mode)",
            pair=f"{trading_pair.base_currency}/{trading_pair.quote_currency}",
        )

        # Placeholder: Return mock price data
        bid_price = Decimal("49995.00")
        ask_price = Decimal("50005.00")

        price = Price(
            trading_pair=trading_pair,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_volume=Decimal("12.0"),
            ask_volume=Decimal("18.0"),
            exchange=self.name,
            timestamp=datetime.now(timezone.utc),
        )

        logger.debug(
            "Returning placeholder price",
            bid=float(bid_price),
            ask=float(ask_price),
        )
        return price

    async def get_orderbook(
        self, trading_pair: TradingPair, depth: int = 20
    ) -> OrderBook:
        """Get order book (placeholder).

        Args:
            trading_pair: Trading pair to get order book for
            depth: Number of price levels to retrieve

        Returns:
            Placeholder order book with mock data

        Note:
            This is a placeholder implementation for MVP scaffold.
        """
        logger.info(
            "get_orderbook called (placeholder mode)",
            pair=f"{trading_pair.base_currency}/{trading_pair.quote_currency}",
            depth=depth,
        )

        # Placeholder: Return mock order book
        bids = [(Decimal("49995.00"), Decimal("1.8"))]
        asks = [(Decimal("50005.00"), Decimal("2.2"))]

        orderbook = OrderBook(
            trading_pair=trading_pair,
            bids=bids,
            asks=asks,
            exchange=self.name,
            timestamp=datetime.now(timezone.utc),
        )

        logger.debug("Returning placeholder order book", bids_count=1, asks_count=1)
        return orderbook

    async def place_order(self, order: Order) -> Order:
        """Place order (placeholder).

        Args:
            order: Order to place

        Returns:
            Order with mock exchange order ID

        Note:
            This is a placeholder implementation for MVP scaffold.
        """
        logger.info(
            "place_order called (placeholder mode)",
            pair=f"{order.trading_pair.base_currency}/{order.trading_pair.quote_currency}",
            side=order.side.value,
            quantity=float(order.quantity),
        )

        # Placeholder: Generate mock order ID and mark as filled
        order.exchange_order_id = f"okx_{uuid4().hex[:16]}"
        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.updated_at = datetime.now(timezone.utc)

        logger.debug(
            "Order placed (placeholder)",
            order_id=order.exchange_order_id,
            status=order.status.value,
        )
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order (placeholder).

        Args:
            order_id: Exchange order ID to cancel

        Returns:
            Always True in placeholder mode

        Note:
            This is a placeholder implementation for MVP scaffold.
        """
        logger.info("cancel_order called (placeholder mode)", order_id=order_id)
        logger.debug("Order cancelled (placeholder)", order_id=order_id)
        return True

    async def get_order_status(self, order_id: str) -> Order:
        """Get order status (placeholder).

        Args:
            order_id: Exchange order ID to query

        Returns:
            Placeholder order with FILLED status

        Note:
            This is a placeholder implementation for MVP scaffold.
        """
        logger.info("get_order_status called (placeholder mode)", order_id=order_id)

        # Placeholder: Create mock order
        trading_pair = TradingPair(
            base_currency="BTC",
            quote_currency="USDT",
            exchange=self.name,
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1000"),
            price_precision=2,
            quantity_precision=8,
        )

        order = Order(
            id=order_id,
            exchange_order_id=order_id,
            trading_pair=trading_pair,
            side=OrderSide.BUY,
            quantity=Decimal("1.0"),
            price=Decimal("49995.00"),
            status=OrderStatus.FILLED,
            filled_quantity=Decimal("1.0"),
        )

        logger.debug("Returning placeholder order", status=order.status.value)
        return order

    async def get_trade_history(
        self, trading_pair: TradingPair, limit: int = 100
    ) -> List[Trade]:
        """Get trade history (placeholder).

        Args:
            trading_pair: Trading pair to get trades for
            limit: Maximum number of trades to retrieve

        Returns:
            Empty list in placeholder mode

        Note:
            This is a placeholder implementation for MVP scaffold.
        """
        logger.info(
            "get_trade_history called (placeholder mode)",
            pair=f"{trading_pair.base_currency}/{trading_pair.quote_currency}",
            limit=limit,
        )

        logger.debug("Returning empty trade history (placeholder)")
        return []

    async def subscribe_ticker(
        self, trading_pair: TradingPair
    ) -> AsyncIterator[Price]:
        """Subscribe to ticker updates (placeholder).

        Args:
            trading_pair: Trading pair to subscribe to

        Yields:
            Placeholder price updates

        Note:
            This is a placeholder implementation for MVP scaffold.
            Does not actually stream real-time data.
        """
        logger.info(
            "subscribe_ticker called (placeholder mode)",
            pair=f"{trading_pair.base_currency}/{trading_pair.quote_currency}",
        )

        # Placeholder: Yield nothing, actual WebSocket streaming will be implemented later
        logger.debug("Ticker subscription (placeholder - no streaming)")
        return
        yield  # Make this a generator

    async def subscribe_orderbook(
        self, trading_pair: TradingPair, depth: int = 20
    ) -> AsyncIterator[OrderBook]:
        """Subscribe to order book updates (placeholder).

        Args:
            trading_pair: Trading pair to subscribe to
            depth: Number of price levels to stream

        Yields:
            Placeholder order book updates

        Note:
            This is a placeholder implementation for MVP scaffold.
            Does not actually stream real-time data.
        """
        logger.info(
            "subscribe_orderbook called (placeholder mode)",
            pair=f"{trading_pair.base_currency}/{trading_pair.quote_currency}",
            depth=depth,
        )

        # Placeholder: Yield nothing, actual WebSocket streaming will be implemented later
        logger.debug("Order book subscription (placeholder - no streaming)")
        return
        yield  # Make this a generator
