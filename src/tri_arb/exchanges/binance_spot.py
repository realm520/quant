"""Binance Spot exchange adapter implementation.

Provides async interface to Binance Spot REST API v3.
"""

import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx

from tri_arb.config.logging import get_logger
from tri_arb.core.models import (
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    Price,
    Trade,
    TradingPair,
)
from tri_arb.exchanges.base import BaseExchange


logger = get_logger(__name__)


class BinanceSpotExchange(BaseExchange):
    """Binance Spot exchange adapter implementation.

    Provides async interface to Binance Spot REST API v3.

    Attributes:
        api_key: Binance API key for authentication
        api_secret: Binance API secret for HMAC-SHA256 signature
    """

    BASE_URL: str = "https://api.binance.com"
    WS_URL: str = "wss://stream.binance.com:9443"

    def __init__(
        self,
        name: str = "binance_spot",
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        """Initialize Binance Spot exchange adapter.

        Args:
            name: Exchange name identifier
            api_key: Binance API key
            api_secret: Binance API secret
        """
        super().__init__(name)
        self.api_key = api_key
        self.api_secret = api_secret
        self._client: httpx.AsyncClient | None = None

        logger.info(
            "BinanceSpotExchange initialized",
            has_api_key=bool(api_key),
            has_api_secret=bool(api_secret),
        )

    async def connect(self) -> None:
        """Establish connection to Binance Spot exchange."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )

        self.is_connected = True
        logger.info("Connected to Binance Spot exchange", exchange=self.name)

    async def disconnect(self) -> None:
        """Close connection to Binance Spot exchange."""
        if self._client:
            await self._client.aclose()
            self._client = None

        self.is_connected = False
        logger.info("Disconnected from Binance Spot exchange", exchange=self.name)

    def _require_credentials(self) -> None:
        """Check if API credentials are available.

        Raises:
            ValueError: If API key or secret is missing
        """
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Trading operations require API credentials. "
                "Please set BINANCE_API_KEY and BINANCE_API_SECRET environment variables."
            )

    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for Binance API.

        Args:
            query_string: URL query string to sign

        Returns:
            Hex signature string
        """
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> httpx.Response:
        """Make HTTP request to Binance API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Query parameters
            authenticated: Whether to sign the request

        Returns:
            HTTP response object

        Raises:
            ValueError: If not connected
            httpx.HTTPStatusError: If API request fails
        """
        if not self._client:
            raise ValueError("Not connected to exchange")

        url = f"{self.BASE_URL}{path}"
        headers = {}

        if authenticated:
            self._require_credentials()
            headers["X-MBX-APIKEY"] = self.api_key

            # Add timestamp
            if params is None:
                params = {}
            params["timestamp"] = int(time.time() * 1000)

            # Generate signature
            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
            signature = self._generate_signature(query_string)
            params["signature"] = signature

        logger.debug(
            "Making Binance API request",
            method=method,
            path=path,
            authenticated=authenticated,
        )

        response = await self._client.request(
            method=method,
            url=url,
            params=params,
            headers=headers,
        )

        response.raise_for_status()
        return response

    async def get_trading_pair_info(
        self, trading_pair: TradingPair | None = None
    ) -> TradingPair | list[TradingPair]:
        """Get detailed trading pair information from exchange.

        Args:
            trading_pair: Trading pair to get info for. If None, returns all pairs.

        Returns:
            Single TradingPair or list of TradingPairs

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "Trading pair info query not yet implemented for Binance Spot"
        )

    async def get_balance(self) -> dict[str, dict[str, Any]]:
        """Get account balances for all assets.

        Returns:
            Dictionary mapping currency code to balance details:
            {
                "BTC": {
                    "available": Decimal("1.5"),
                    "frozen": Decimal("0.5"),
                    "total": Decimal("2.0")
                },
                ...
            }

        Raises:
            ValueError: If not connected or missing credentials
            httpx.HTTPStatusError: If API request fails
        """
        self._require_credentials()

        response = await self._request(
            method="GET",
            path="/api/v3/account",
            authenticated=True,
        )

        data = response.json()

        logger.debug(
            "Raw Binance balance response",
            response_keys=list(data.keys()) if isinstance(data, dict) else "not_dict",
        )

        balances: dict[str, dict[str, Any]] = {}

        # Binance response format: {balances: [{asset: "BTC", free: "1.0", locked: "0.5"}, ...]}
        if "balances" in data:
            for balance_item in data["balances"]:
                asset = balance_item.get("asset", "")
                if not asset:
                    continue

                free = Decimal(balance_item.get("free", "0"))
                locked = Decimal(balance_item.get("locked", "0"))

                # Only include assets with non-zero balances
                if free > 0 or locked > 0:
                    balances[asset] = {
                        "available": free,
                        "frozen": locked,
                        "total": free + locked,
                    }
        else:
            # Handle unexpected response format
            logger.error(
                "Unexpected Binance Spot balance response format",
                response_keys=(
                    list(data.keys()) if isinstance(data, dict) else "not_dict"
                ),
                data=str(data)[:500],
            )
            raise ValueError(
                f"Unexpected response format from Binance Spot API: missing 'balances' key"
            )

        logger.info(
            "Binance spot balances retrieved",
            currencies_count=len(balances),
            currencies=(
                list(balances.keys())[:10]
                if balances
                else ["No balances with non-zero amounts"]
            ),
        )

        return balances

    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        """Get current ticker price.

        Args:
            trading_pair: Trading pair to get ticker for

        Returns:
            Current price information

        Raises:
            ValueError: If not connected
            httpx.HTTPStatusError: If API request fails
        """
        symbol = f"{trading_pair.base_currency}{trading_pair.quote_currency}"

        response = await self._request(
            method="GET",
            path="/api/v3/ticker/bookTicker",
            params={"symbol": symbol},
            authenticated=False,
        )

        data = response.json()

        price = Price(
            trading_pair=trading_pair,
            bid_price=Decimal(data["bidPrice"]),
            ask_price=Decimal(data["askPrice"]),
            bid_volume=Decimal(data["bidQty"]),
            ask_volume=Decimal(data["askQty"]),
            exchange=self.name,
            timestamp=datetime.now(UTC),
        )

        logger.debug(
            "Binance spot ticker retrieved",
            symbol=symbol,
            bid=float(price.bid_price),
            ask=float(price.ask_price),
        )

        return price

    async def get_orderbook(
        self, trading_pair: TradingPair, depth: int = 20
    ) -> OrderBook:
        """Get order book.

        Args:
            trading_pair: Trading pair to get order book for
            depth: Number of price levels to retrieve

        Returns:
            Order book with bids and asks

        Raises:
            ValueError: If not connected
            httpx.HTTPStatusError: If API request fails
        """
        symbol = f"{trading_pair.base_currency}{trading_pair.quote_currency}"

        # Binance supports depth levels: 5, 10, 20, 50, 100, 500, 1000, 5000
        limit = min(depth, 5000)

        response = await self._request(
            method="GET",
            path="/api/v3/depth",
            params={"symbol": symbol, "limit": limit},
            authenticated=False,
        )

        data = response.json()

        bids = [(Decimal(price), Decimal(qty)) for price, qty in data["bids"][:depth]]
        asks = [(Decimal(price), Decimal(qty)) for price, qty in data["asks"][:depth]]

        orderbook = OrderBook(
            trading_pair=trading_pair,
            bids=bids,
            asks=asks,
            exchange=self.name,
            timestamp=datetime.now(UTC),
        )

        logger.debug(
            "Binance spot orderbook retrieved",
            symbol=symbol,
            bids_count=len(bids),
            asks_count=len(asks),
        )

        return orderbook

    async def place_order(self, order: Order) -> Order:
        """Place order (not implemented yet).

        Args:
            order: Order to place

        Returns:
            Order with exchange order ID

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "Order placement not yet implemented for Binance Spot"
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order (not implemented yet).

        Args:
            order_id: Exchange order ID to cancel

        Returns:
            True if cancelled successfully

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "Order cancellation not yet implemented for Binance Spot"
        )

    async def get_order_status(self, order_id: str) -> Order:
        """Get order status (not implemented yet).

        Args:
            order_id: Exchange order ID to query

        Returns:
            Order with current status

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "Order status query not yet implemented for Binance Spot"
        )

    async def get_trade_history(
        self, trading_pair: TradingPair, limit: int = 100
    ) -> list[Trade]:
        """Get trade history (not implemented yet).

        Args:
            trading_pair: Trading pair to get trades for
            limit: Maximum number of trades to retrieve

        Returns:
            List of trades

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError("Trade history not yet implemented for Binance Spot")

    async def subscribe_ticker(self, trading_pair: TradingPair) -> AsyncIterator[Price]:
        """Subscribe to ticker updates (not implemented yet).

        Args:
            trading_pair: Trading pair to subscribe to

        Yields:
            Price updates

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "Ticker subscription not yet implemented for Binance Spot"
        )
        yield  # Make this a generator

    async def subscribe_orderbook(
        self, trading_pair: TradingPair, depth: int = 20
    ) -> AsyncIterator[OrderBook]:
        """Subscribe to order book updates (not implemented yet).

        Args:
            trading_pair: Trading pair to subscribe to
            depth: Number of price levels to stream

        Yields:
            Order book updates

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "Order book subscription not yet implemented for Binance Spot"
        )
        yield  # Make this a generator
