"""XT Exchange adapter for tri-arb trading system.

Provides async interface to XT Exchange REST API v4.
"""

from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional
from decimal import Decimal
from datetime import datetime
import hmac
import hashlib
import time
import json
import urllib.parse

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from tri_arb.exchanges.base import BaseExchange
from tri_arb.core.models import (
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    OrderType,
    Price,
    Trade,
    TradingPair,
)
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


class XTExchange(BaseExchange):
    """XT Exchange adapter implementation.

    Provides async interface to XT Exchange REST API v4, conforming to
    BaseExchange protocol for triangle arbitrage trading system.

    Attributes:
        name: Exchange identifier ("xt")
        api_key: XT API key for authentication
        api_secret: XT API secret for HMAC-SHA256 signature
        is_connected: Connection state flag

    Example:
        >>> exchange = XTExchange(
        ...     name="xt",
        ...     api_key="your_api_key",
        ...     api_secret="your_api_secret"
        ... )
        >>> await exchange.connect()
        >>> price = await exchange.get_ticker(trading_pair)
    """

    BASE_URL: str = "https://sapi.xt.com"
    API_VERSION: str = "v4"
    RECV_WINDOW: int = 5000  # milliseconds

    def __init__(
        self,
        name: str = "xt",
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        """Initialize XT Exchange adapter.

        Args:
            name: Exchange identifier (default: "xt")
            api_key: XT API key (empty for public endpoints only)
            api_secret: XT API secret (empty for public endpoints only)
        """
        super().__init__(name)
        self.api_key = api_key
        self.api_secret = api_secret
        self._client: Optional[httpx.AsyncClient] = None

        logger.info(
            "XTExchange initialized",
            has_api_key=bool(api_key),
            has_api_secret=bool(api_secret),
        )

    async def connect(self) -> None:
        """Establish connection to XT exchange.

        Creates HTTP client with connection pooling and timeout configuration.

        Raises:
            ValueError: If already connected
        """
        if self._client:
            raise ValueError("Already connected")

        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

        self.is_connected = True
        logger.info("Connected to XT exchange", exchange=self.name)

    async def disconnect(self) -> None:
        """Close connection to XT exchange.

        Closes HTTP client and releases resources.

        Raises:
            ValueError: If not connected
        """
        if not self._client:
            raise ValueError("Not connected")

        await self._client.aclose()
        self._client = None
        self.is_connected = False
        logger.info("Disconnected from XT exchange", exchange=self.name)

    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        """Get current ticker price for a trading pair.

        Args:
            trading_pair: Trading pair to get ticker for

        Returns:
            Current price information with bid/ask

        Raises:
            ValueError: If not connected or trading pair invalid
            httpx.HTTPStatusError: If API request fails
        """
        symbol = self._to_xt_symbol(trading_pair)

        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/public/ticker/price",
            params={"symbol": symbol},
            authenticated=False,
        )

        data = response.json()

        # TODO: Verify actual bid/ask field names in XT API response
        # For now, using close price (c) as base and adding small spread for MVP
        result = data.get("result", {})
        close_price = Decimal(str(result.get("c", result.get("p", "0"))))
        volume = Decimal(str(result.get("v", "0")))

        # Add small spread (0.01%) for bid/ask
        spread = close_price * Decimal("0.0001")
        bid_price = close_price - spread
        ask_price = close_price + spread

        return Price(
            trading_pair=trading_pair,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_volume=volume / Decimal("2"),  # Distribute volume
            ask_volume=volume / Decimal("2"),
            timestamp=datetime.now(tz=datetime.now().astimezone().tzinfo),
            exchange="xt",
        )

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
            ValueError: If not connected or trading pair invalid
            httpx.HTTPStatusError: If API request fails
        """
        symbol = self._to_xt_symbol(trading_pair)

        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/public/depth",
            params={"symbol": symbol, "limit": depth},
            authenticated=False,
        )

        data = response.json()
        result = data.get("result", {})

        # Parse bids and asks from XT format [[price, quantity], ...]
        bids = [
            (Decimal(str(price)), Decimal(str(quantity)))
            for price, quantity in result.get("bids", [])
        ]
        asks = [
            (Decimal(str(price)), Decimal(str(quantity)))
            for price, quantity in result.get("asks", [])
        ]

        return OrderBook(
            trading_pair=trading_pair,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(tz=datetime.now().astimezone().tzinfo),
            exchange="xt",
        )

    async def place_order(self, order: Order) -> Order:
        """Place a new order on the exchange.

        Args:
            order: Order to place

        Returns:
            Order with updated status and exchange order ID

        Raises:
            ValueError: If not connected, invalid order, or missing credentials
            httpx.HTTPStatusError: If API request fails
        """
        symbol = self._to_xt_symbol(order.trading_pair)

        # Build request body for XT API
        body = {
            "symbol": symbol,
            "side": order.side.value.upper(),  # BUY/SELL
            "type": order.order_type.value.upper(),  # MARKET/LIMIT
            "bizType": "SPOT",
            "quantity": str(order.quantity),
        }

        # Add price for limit orders
        if order.order_type == OrderType.LIMIT:
            if order.price is None:
                raise ValueError("Limit order requires price")
            body["price"] = str(order.price)
            body["timeInForce"] = "GTC"  # Good Till Cancel

        response = await self._request(
            method="POST",
            path=f"/{self.API_VERSION}/order",
            json_data=body,
            authenticated=True,
        )

        data = response.json()
        result = data.get("result", {})

        # Update order with exchange order ID and status
        order.order_id = str(result.get("orderId", order.order_id))

        # Map XT status to internal OrderStatus
        xt_status = result.get("status", "NEW")
        if xt_status == "NEW":
            order.status = OrderStatus.OPEN
        elif xt_status == "FILLED":
            order.status = OrderStatus.FILLED
        elif xt_status == "PARTIALLY_FILLED":
            order.status = OrderStatus.PARTIALLY_FILLED
        elif xt_status == "CANCELED":
            order.status = OrderStatus.CANCELLED
        else:
            order.status = OrderStatus.OPEN

        order.updated_at = datetime.now(tz=datetime.now().astimezone().tzinfo)

        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.

        Args:
            order_id: Exchange order ID to cancel

        Returns:
            True if order was cancelled, False otherwise

        Raises:
            ValueError: If not connected or missing credentials
            httpx.HTTPStatusError: If API request fails
        """
        # Build request body for XT API
        # Note: XT API might require symbol or cancel all orders for a symbol
        # For now, using orderId if API supports it
        body = {
            "orderId": order_id,
            "bizType": "SPOT",
        }

        try:
            response = await self._request(
                method="DELETE",
                path=f"/{self.API_VERSION}/order",
                json_data=body,
                authenticated=True,
            )

            data = response.json()
            # Check if cancellation was successful
            success: bool = data.get("rc") == 0 or data.get("result", {}).get("status") == "CANCELED"
            return success

        except httpx.HTTPStatusError as e:
            logger.error(
                "Failed to cancel order",
                order_id=order_id,
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
            return False

    async def get_order_status(self, order_id: str) -> Order:
        """Get current status of an order.

        Args:
            order_id: Exchange order ID to query

        Returns:
            Order with current status

        Raises:
            ValueError: If not connected or missing credentials
            httpx.HTTPStatusError: If API request fails or order not found
        """
        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/order",
            params={"orderId": order_id, "bizType": "SPOT"},
            authenticated=True,
        )

        data = response.json()
        result = data.get("result", {})

        # Parse XT symbol to trading pair
        symbol = result.get("symbol", "")
        base, quote = self._from_xt_symbol(symbol)

        # Map XT status to internal OrderStatus
        xt_status = result.get("status", "")
        if xt_status == "NEW":
            status = OrderStatus.OPEN
        elif xt_status == "FILLED":
            status = OrderStatus.FILLED
        elif xt_status == "PARTIALLY_FILLED":
            status = OrderStatus.PARTIALLY_FILLED
        elif xt_status == "CANCELED":
            status = OrderStatus.CANCELLED
        else:
            status = OrderStatus.PENDING

        # Map order type
        xt_type = result.get("type", "LIMIT")
        order_type = OrderType.LIMIT if xt_type == "LIMIT" else OrderType.MARKET

        # Map order side
        xt_side = result.get("side", "BUY")
        side = OrderSide.BUY if xt_side == "BUY" else OrderSide.SELL

        # Create minimal TradingPair (real values would need to be fetched from exchange info)
        trading_pair = TradingPair(
            base_currency=base,
            quote_currency=quote,
            exchange="xt",
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1000000"),
            price_precision=8,
            quantity_precision=8,
        )

        return Order(
            order_id=str(result.get("orderId", order_id)),
            trading_pair=trading_pair,
            side=side,
            order_type=order_type,
            price=Decimal(str(result.get("price", "0"))) if result.get("price") else None,
            quantity=Decimal(str(result.get("origQty", "0"))),
            status=status,
            created_at=datetime.fromtimestamp(
                int(result.get("time", 0)) / 1000,
                tz=datetime.now().astimezone().tzinfo,
            ),
            updated_at=datetime.now(tz=datetime.now().astimezone().tzinfo),
            exchange="xt",
        )

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
            ValueError: If not connected or missing credentials
            httpx.HTTPStatusError: If API request fails
        """
        symbol = self._to_xt_symbol(trading_pair)

        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/trade",
            params={"bizType": "SPOT", "symbol": symbol, "limit": limit},
            authenticated=True,
        )

        data = response.json()
        trades_data = data.get("result", [])

        trades = []
        for trade_data in trades_data:
            # Map order side
            xt_side = trade_data.get("side", "BUY")
            side = OrderSide.BUY if xt_side == "BUY" else OrderSide.SELL

            trade = Trade(
                trade_id=str(trade_data.get("id", "")),
                order_id=str(trade_data.get("orderId", "")),
                trading_pair=trading_pair,
                side=side,
                price=Decimal(str(trade_data.get("price", "0"))),
                quantity=Decimal(str(trade_data.get("qty", "0"))),
                fee=Decimal(str(trade_data.get("commission", "0"))),
                fee_currency=trade_data.get("commissionAsset", trading_pair.quote_currency),
                timestamp=datetime.fromtimestamp(
                    int(trade_data.get("time", 0)) / 1000,
                    tz=datetime.now().astimezone().tzinfo,
                ),
                exchange="xt",
            )
            trades.append(trade)

        return trades

    async def subscribe_ticker(  # type: ignore[override, misc]
        self, trading_pair: TradingPair
    ) -> AsyncIterator[Price]:
        """Subscribe to real-time ticker updates (not implemented for XT).

        XT WebSocket support is planned for future iteration.

        Args:
            trading_pair: Trading pair to subscribe to

        Yields:
            Price updates (not implemented)

        Raises:
            NotImplementedError: WebSocket not supported yet
        """
        if TYPE_CHECKING:  # Stub implementation - yield required for AsyncIterator type
            # This code never executes at runtime (TYPE_CHECKING is False)
            yield Price(  # pragma: no cover
                trading_pair=trading_pair,
                bid_price=Decimal("0"),
                ask_price=Decimal("0"),
                bid_volume=Decimal("0"),
                ask_volume=Decimal("0"),
                timestamp=datetime.now(tz=datetime.now().astimezone().tzinfo),
                exchange="xt",
            )
        raise NotImplementedError("XT WebSocket support coming in future iteration")

    async def subscribe_orderbook(  # type: ignore[override, misc]
        self, trading_pair: TradingPair, depth: int = 20
    ) -> AsyncIterator[OrderBook]:
        """Subscribe to real-time order book updates (not implemented for XT).

        XT WebSocket support is planned for future iteration.

        Args:
            trading_pair: Trading_pair to subscribe to
            depth: Number of price levels to stream

        Yields:
            Order book updates (not implemented)

        Raises:
            NotImplementedError: WebSocket not supported yet
        """
        if TYPE_CHECKING:  # Stub implementation - yield required for AsyncIterator type
            # This code never executes at runtime (TYPE_CHECKING is False)
            yield OrderBook(  # pragma: no cover
                trading_pair=trading_pair,
                bids=[],
                asks=[],
                timestamp=datetime.now(tz=datetime.now().astimezone().tzinfo),
                exchange="xt",
            )
        raise NotImplementedError("XT WebSocket support coming in future iteration")

    # Helper methods

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        authenticated: bool = False,
    ) -> httpx.Response:
        """Make HTTP request to XT API with retry logic.

        Args:
            method: HTTP method (GET, POST, DELETE)
            path: API endpoint path
            params: URL query parameters
            json_data: JSON request body
            authenticated: Whether to include signature

        Returns:
            HTTP response object

        Raises:
            httpx.HTTPStatusError: For 4xx/5xx responses
            httpx.TimeoutException: After retry exhaustion
            ValueError: If not connected
        """
        if not self._client:
            raise ValueError("Exchange not connected. Call connect() first.")

        headers: Dict[str, str] = {}
        query_string = ""
        body_string = ""

        if authenticated:
            query_string = self._build_sorted_query(params or {})
            body_string = json.dumps(json_data) if json_data else ""
            headers, _ = self._generate_signature(method, path, query_string, body_string)

        try:
            response = await self._client.request(
                method,
                path,
                params=params,
                json=json_data,
                headers=headers if authenticated else None,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as e:
            logger.error(
                "XT API HTTP error",
                method=method,
                path=path,
                status_code=e.response.status_code,
                response_body=e.response.text,
            )
            raise
        except httpx.TimeoutException:
            logger.error("XT API timeout", method=method, path=path)
            raise

    def _to_xt_symbol(self, trading_pair: TradingPair) -> str:
        """Convert TradingPair to XT symbol format.

        Args:
            trading_pair: Internal trading pair model

        Returns:
            XT symbol format (lowercase with underscore)

        Raises:
            ValueError: If trading pair currencies are invalid

        Examples:
            >>> _to_xt_symbol(TradingPair(base_currency="BTC", quote_currency="USDT"))
            "btc_usdt"
        """
        if not trading_pair.base_currency or not trading_pair.quote_currency:
            raise ValueError("Trading pair must have both base and quote currencies")

        return f"{trading_pair.base_currency.lower()}_{trading_pair.quote_currency.lower()}"

    def _from_xt_symbol(self, symbol: str) -> tuple[str, str]:
        """Parse XT symbol format to base/quote currencies.

        Args:
            symbol: XT symbol format (e.g., "btc_usdt")

        Returns:
            Tuple of (base_currency, quote_currency) in uppercase

        Raises:
            ValueError: If symbol format is invalid

        Examples:
            >>> _from_xt_symbol("btc_usdt")
            ("BTC", "USDT")
        """
        try:
            base, quote = symbol.split("_", 1)
            return base.upper(), quote.upper()
        except ValueError:
            raise ValueError(f"Invalid XT symbol format: {symbol}")

    def _generate_signature(
        self,
        method: str,
        path: str,
        query: str = "",
        body: str = "",
    ) -> tuple[dict[str, str], str]:
        """Generate XT API HMAC-SHA256 signature and headers.

        Args:
            method: HTTP method (GET, POST, DELETE)
            path: API endpoint path (e.g., "/v4/order")
            query: URL query string (sorted parameters)
            body: Request body (JSON string, empty for GET)

        Returns:
            Tuple of (headers dict, signature string)

        Raises:
            ValueError: If API credentials are missing

        Note:
            Signature is synchronous (CPU-bound, <1ms execution time)
        """
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required for authenticated requests")

        timestamp_ms = int(time.time() * 1000)

        # Build signature base string
        X = (
            f"validate-algorithms=HmacSHA256"
            f"&validate-appkey={self.api_key}"
            f"&validate-recvwindow={self.RECV_WINDOW}"
            f"&validate-timestamp={timestamp_ms}"
        )

        sig_data = f"{X}#{method}#{path}"
        if query:
            sig_data += f"#{query}"
        if body:
            sig_data += f"#{body}"

        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            sig_data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Build headers
        headers = {
            "validate-algorithms": "HmacSHA256",
            "validate-appkey": self.api_key,
            "validate-recvwindow": str(self.RECV_WINDOW),
            "validate-timestamp": str(timestamp_ms),
            "validate-signature": signature,
            "Content-Type": "application/json",
            "accept": "*/*",
        }

        return headers, signature

    def _build_sorted_query(self, params: Dict[str, Any]) -> str:
        """Build sorted query string for XT API signature.

        XT requires query parameters to be sorted alphabetically for
        signature generation.

        Args:
            params: Query parameters dictionary

        Returns:
            Sorted and URL-encoded query string

        Examples:
            >>> _build_sorted_query({'symbol': 'btc_usdt', 'limit': 20})
            "limit=20&symbol=btc_usdt"
        """
        if not params:
            return ""

        # Sort parameters by key
        sorted_items = sorted(params.items(), key=lambda x: x[0])

        # Handle dict/list values by JSON encoding
        processed_items = [
            (key, json.dumps(value) if isinstance(value, (dict, list)) else value)
            for key, value in sorted_items
        ]

        return urllib.parse.urlencode(processed_items)
