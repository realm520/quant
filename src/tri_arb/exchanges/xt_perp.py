"""XT Perpetual Futures Exchange Adapter.

Implements BaseExchange interface for XT perpetual futures trading,
supporting position management, leverage control, and funding rate tracking.
"""

import asyncio
import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from tri_arb.core.models import Order, OrderBook, OrderSide, OrderStatus, OrderType, Price, TradingPair
from tri_arb.exchanges.base import BaseExchange
from tri_arb.models.perpetual import FundingRate, Position


logger = structlog.get_logger(__name__)


class XTPerpExchange(BaseExchange):
    """XT Perpetual Futures Exchange Adapter.

    Implements perpetual futures trading on XT exchange with support for:
    - Dual-direction positions (LONG/SHORT)
    - Leverage management (1x-125x)
    - Funding rate tracking
    - Conditional orders (stop-profit/stop-loss)

    Attributes:
        BASE_URL: XT perpetual futures API base URL
        _client: Async HTTP client with connection pooling
        _trading_pairs: Cached trading pair information
        _api_key: XT API key
        _api_secret: XT API secret
    """

    BASE_URL = "https://fapi.xt.com"

    def __init__(self, api_key: str, api_secret: str, timeout: int = 30) -> None:
        """Initialize XT perpetual futures exchange adapter.

        Args:
            api_key: XT API key
            api_secret: XT API secret
            timeout: HTTP request timeout in seconds (default: 30)
        """
        super().__init__(name="xt_perp")
        self._api_key = api_key
        self._api_secret = api_secret
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._trading_pairs: dict[str, TradingPair] = {}

    async def connect(self) -> None:
        """Establish connection to XT perpetual futures exchange.

        Creates HTTP client with connection pooling and loads trading pair information.
        """
        if self.is_connected:
            logger.warning("Already connected to XT perpetual exchange")
            return

        # Create async HTTP client with connection pooling
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(self._timeout),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

        # Mark as connected immediately after client creation
        # This allows API calls to work even if trading pair loading fails
        self.is_connected = True

        # Load trading pairs (cache for performance)
        try:
            await self._load_trading_pairs()
            logger.info("Connected to XT perpetual futures exchange", pairs_loaded=len(self._trading_pairs))
        except Exception as e:
            logger.warning(
                "Failed to load trading pairs, but connection is still usable",
                error=str(e),
                error_type=type(e).__name__
            )

    async def disconnect(self) -> None:
        """Close connection to XT perpetual futures exchange."""
        if not self.is_connected:
            logger.warning("Not connected to XT perpetual exchange")
            return

        if self._client:
            await self._client.aclose()
            self._client = None

        self._trading_pairs.clear()
        self.is_connected = False
        logger.info("Disconnected from XT perpetual futures exchange")

    def _generate_signature(
        self, method: str, path: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """Generate HMAC-SHA256 signature for XT API authentication.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Query parameters (for form-urlencoded)
            body: Request body (for JSON)

        Returns:
            Headers dict with signature and authentication fields
        """
        timestamp = str(int(time.time() * 1000))

        # Build signature string based on content type
        if body is not None:
            # JSON body
            import json
            message = json.dumps(body)
            signkey = f"xt-validate-appkey={self._api_key}&xt-validate-timestamp={timestamp}#{path}#{message}"
        elif params is not None:
            # Form-urlencoded params
            sorted_params = dict(sorted(params.items(), key=lambda e: e[0]))
            message = "&".join([f"{arg}={sorted_params[arg]}" for arg in sorted_params])
            signkey = f"xt-validate-appkey={self._api_key}&xt-validate-timestamp={timestamp}#{path}#{message}"
        else:
            # No params or body
            signkey = f"xt-validate-appkey={self._api_key}&xt-validate-timestamp={timestamp}#{path}"

        # Generate HMAC-SHA256 signature
        sign = hmac.new(
            self._api_secret.encode("utf-8"),
            signkey.encode("utf-8"),
            digestmod=hashlib.sha256
        ).hexdigest()

        # Return headers with signature
        return {
            "validate-signversion": "2",
            "xt-validate-appkey": self._api_key,
            "xt-validate-timestamp": timestamp,
            "xt-validate-signature": sign,
            "xt-validate-algorithms": "HmacSHA256",
            "Content-Type": "application/json" if body is not None else "application/x-www-form-urlencoded",
        }

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> dict[str, Any]:
        """Make HTTP request to XT API with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Query parameters
            body: Request body
            require_auth: Whether to include authentication headers

        Returns:
            Response data dict

        Raises:
            RuntimeError: If exchange is not connected
            httpx.HTTPError: On network errors
            ValueError: On API errors (non-zero rc)
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        # Generate signature headers if auth required
        headers = self._generate_signature(method, path, params, body) if require_auth else {}

        # Make request
        try:
            if method == "GET":
                response = await self._client.get(path, params=params, headers=headers)
            elif method == "POST":
                response = await self._client.post(path, params=params, json=body, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            data = response.json()

            # Debug: Log full response for balance endpoint
            if "balance" in path:
                logger.info(
                    "Full API response for balance endpoint",
                    path=path,
                    status_code=response.status_code,
                    has_rc=("rc" in data),
                    has_result=("result" in data),
                    has_data=("data" in data),
                    full_response=data
                )

            # Check XT API response code
            # Note: Some endpoints return rc=0, some return rc=null, some omit rc entirely
            # Only treat as error if rc is explicitly non-zero (not null/None)
            rc = data.get("rc")
            if rc is not None and rc != 0:
                error_msg = data.get("ma", ["Unknown error"])[0] if data.get("ma") else "Unknown error"
                raise ValueError(f"XT API error (code {rc}): {error_msg}")

            # Return result field if present, otherwise return entire data
            # Some endpoints return data directly without wrapping in "result"
            result = data.get("result", data.get("data", data))

            # Debug: Log extracted result
            if "balance" in path:
                logger.info(
                    "Extracted result from response",
                    result_type=type(result).__name__,
                    result_is_none=(result is None),
                    result_sample=str(result)[:300] if result else "None"
                )

            return result

        except httpx.HTTPError as e:
            logger.error(
                "HTTP request failed",
                method=method,
                path=path,
                error=str(e),
            )
            raise

    async def _load_trading_pairs(self) -> None:
        """Load and cache all trading pair information from XT API.
        
        Fetches list of all available perpetual contract symbols and populates
        the internal trading pairs cache for efficient lookups.
        
        Raises:
            RuntimeError: If exchange client is not initialized
            httpx.HTTPError: If API request fails
        """
        if self._client is None:
            raise RuntimeError("Exchange client not initialized")
        
        logger.debug("Loading trading pairs from XT API")
        
        # Fetch all trading pair symbols
        path = "/future/market/v1/public/symbol/list"
        data = await self._request("GET", path, params=None, body=None, require_auth=False)
        
        # Parse response and populate cache
        if not isinstance(data, list):
            logger.warning("Unexpected response format from symbol/list endpoint", data_type=type(data).__name__)
            return
        
        pairs_loaded = 0
        for item in data:
            symbol = item.get("symbol", "")
            if not symbol:
                continue
            
            # Parse symbol format: "btc_usdt" -> BTC/USDT
            parts = symbol.lower().split("_")
            if len(parts) != 2:
                continue
            
            base, quote = parts[0].upper(), parts[1].upper()
            
            # Parse trading pair details
            min_order_size = Decimal(str(item.get("minOrderQuantity", "0")))
            max_order_size = Decimal(str(item.get("maxOrderQuantity", "0")))

            # Use default values if API returns 0 (similar to XTSpotExchange)
            # Some symbols may have 0 values which violate TradingPair validation (gt=0)
            if min_order_size <= 0:
                min_order_size = Decimal("0.001")
                logger.debug("Using default min_order_size for symbol", symbol=symbol)
            if max_order_size <= 0:
                max_order_size = Decimal("1000000")
                logger.debug("Using default max_order_size for symbol", symbol=symbol)

            price_precision = int(item.get("pricePrecision", 8))
            quantity_precision = int(item.get("quantityPrecision", 8))
            contract_size = Decimal(str(item.get("contractSize", "1")))
            
            # Parse leverage brackets if available
            leverage_brackets_data = item.get("leverageBrackets", [])
            leverage_brackets_list = []
            if leverage_brackets_data:
                for bracket in leverage_brackets_data:
                    from tri_arb.models.perpetual import LeverageBracket
                    bracket_obj = LeverageBracket(
                        min_notional=Decimal(str(bracket.get("minNotional", "0"))),
                        max_notional=Decimal(str(bracket.get("maxNotional", "0"))),
                        max_leverage=int(bracket.get("maxLeverage", 1)),
                    )
                    leverage_brackets_list.append(bracket_obj)
            
            # Create TradingPair object
            pair = TradingPair(
                base_currency=base,
                quote_currency=quote,
                exchange="xt_perp",
                min_order_size=min_order_size,
                max_order_size=max_order_size,
                price_precision=price_precision,
                quantity_precision=quantity_precision,
                leverage_brackets=leverage_brackets_list,
                contract_size=contract_size,
                contract_type="PERPETUAL",
            )
            
            # Add to cache
            pair_key = f"{base}/{quote}"
            self._trading_pairs[pair_key] = pair
            pairs_loaded += 1
        
        logger.info("Trading pairs loaded successfully", pairs_count=pairs_loaded)

    # ============================================================================
    # BaseExchange Abstract Methods - Market Data
    # ============================================================================

    async def get_ticker(self, trading_pair: TradingPair | None = None) -> Price | list[Price]:
        """Get current ticker price for a trading pair or all markets.
        
        Fetches best bid/ask prices from XT Perp book ticker API.
        
        Args:
            trading_pair: Trading pair to get ticker for. If None, returns all
                         active markets (batch query). Default is None.
        
        Returns:
            - If trading_pair is provided: Single Price object
            - If trading_pair is None: List of Price objects for all active markets
        
        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
            
        Example:
            >>> # Single pair query
            >>> price = await exchange.get_ticker(trading_pair)
            >>> print(f"Bid: {price.bid_price}, Ask: {price.ask_price}")
            >>> 
            >>> # Batch query (all pairs)
            >>> prices = await exchange.get_ticker(None)
            >>> print(f"Total markets: {len(prices)}")
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")
        
        if trading_pair is None:
            # Batch query: Get all market book tickers
            path = "/future/market/v1/public/q/ticker/books"
            data = await self._request("GET", path, params=None, body=None, require_auth=False)
            
            # Parse response
            result = data.get("result", [])
            if not isinstance(result, list):
                raise ValueError(f"Expected list result for batch query, got {type(result)}")
            
            # Parse each ticker to Price object
            prices: list[Price] = []
            for item in result:
                symbol_str = item.get("s", "")
                if not symbol_str:
                    continue
                
                # Convert XT symbol format to TradingPair
                parts = symbol_str.lower().split("_")
                if len(parts) != 2:
                    continue
                
                base, quote = parts[0].upper(), parts[1].upper()
                
                # Find or create TradingPair
                pair_key = f"{base}/{quote}"
                if pair_key in self._trading_pairs:
                    pair = self._trading_pairs[pair_key]
                else:
                    # Create minimal TradingPair for unknown pairs
                    pair = TradingPair(
                        base_currency=base,
                        quote_currency=quote,
                        exchange="xt_perp",
                        min_order_size=Decimal("0.001"),
                        max_order_size=Decimal("1000000"),
                        price_precision=8,
                        quantity_precision=8,
                    )
                
                # Parse book ticker data
                # API fields: ap (ask price), aq (ask quantity), bp (bid price), bq (bid quantity)
                bid_price = Decimal(str(item.get("bp", "0")))
                ask_price = Decimal(str(item.get("ap", "0")))
                bid_volume = Decimal(str(item.get("bq", "0")))
                ask_volume = Decimal(str(item.get("aq", "0")))
                
                # Skip invalid tickers (price must be > 0)
                if bid_price <= 0 or ask_price <= 0:
                    logger.debug(
                        "Skipping invalid ticker",
                        symbol=symbol_str,
                        bid=str(bid_price),
                        ask=str(ask_price)
                    )
                    continue
                
                price = Price(
                    trading_pair=pair,
                    bid_price=bid_price,
                    ask_price=ask_price,
                    bid_volume=bid_volume,
                    ask_volume=ask_volume,
                    timestamp=datetime.utcnow(),
                    exchange="xt_perp",
                )
                prices.append(price)
            
            return prices
        else:
            # Single pair query: Get specific book ticker
            symbol = f"{trading_pair.base_currency}_{trading_pair.quote_currency}".lower()
            
            path = "/future/market/v1/public/q/ticker/book"
            params = {"symbol": symbol}
            data = await self._request("GET", path, params=params, body=None, require_auth=False)
            
            # Parse single book ticker response
            # Expected format: {returnCode: 0, result: {s, t, ap, aq, bp, bq}}
            result = data.get("result", {})
            if not isinstance(result, dict):
                raise ValueError(f"Expected dict result for single query, got {type(result)}")
            
            # Parse book ticker data
            bid_price = Decimal(str(result.get("bp", "0")))
            ask_price = Decimal(str(result.get("ap", "0")))
            bid_volume = Decimal(str(result.get("bq", "0")))
            ask_volume = Decimal(str(result.get("aq", "0")))
            
            # Validate prices (must be > 0)
            if bid_price <= 0 or ask_price <= 0:
                raise ValueError(
                    f"Invalid ticker data for {trading_pair.base_currency}/"
                    f"{trading_pair.quote_currency}: bid={bid_price}, ask={ask_price}"
                )
            
            price = Price(
                trading_pair=trading_pair,
                bid_price=bid_price,
                ask_price=ask_price,
                bid_volume=bid_volume,
                ask_volume=ask_volume,
                timestamp=datetime.utcnow(),
                exchange="xt_perp",
            )
            
            return price is not supported for XT Perpetual Futures. "
            "XT Perp API '/future/market/v1/public/q/ticker' only provides "
            "24h statistics (high/low/volume) without bid/ask prices. "
            "Use get_orderbook(trading_pair, depth=1) to get best bid/ask prices instead."
        )

    async def get_orderbook(self, trading_pair: TradingPair, depth: int = 20) -> OrderBook:
        """Get order book for a trading pair.

        Args:
            trading_pair: Trading pair to get order book for
            depth: Number of price levels to retrieve (default 20)

        Returns:
            OrderBook with bids and asks

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        # Convert trading pair to XT format: "BTC/USDT" -> "btc_usdt"
        symbol = f"{trading_pair.base_currency}_{trading_pair.quote_currency}".lower()
        
        path = "/future/market/v1/public/q/depth"
        params = {"symbol": symbol, "level": depth}
        data = await self._request("GET", path, params=params, body=None, require_auth=False)
        
        # Parse orderbook response
        # Expected format: {"b": [["49990", "1.5"], ["49980", "2.0"]], "a": [["50010", "1.2"], ["50020", "1.8"]]}
        bids_data = data.get("b", [])
        asks_data = data.get("a", [])
        
        # Convert to PriceLevel format: (price, quantity)
        bids = [(Decimal(str(price)), Decimal(str(qty))) for price, qty in bids_data]
        asks = [(Decimal(str(price)), Decimal(str(qty))) for price, qty in asks_data]
        
        orderbook = OrderBook(
            trading_pair=trading_pair,
            bids=bids,
            asks=asks,
            timestamp=datetime.utcnow(),
        )
        
        return orderbook

    async def get_trade_history(self, trading_pair: TradingPair, limit: int = 100) -> list[Any]:
        """Get recent trade history.

        Args:
            trading_pair: Trading pair
            limit: Maximum number of trades

        Returns:
            List of trades
        """
        raise NotImplementedError("get_trade_history not yet implemented")

    # ============================================================================
    # BaseExchange Abstract Methods - Order Management
    # ============================================================================

    async def place_order(self, order: Order) -> Order:
        """Place a new order on the exchange.

        Args:
            order: Order to place (must include position_side for perpetual futures)

        Returns:
            Order with updated exchange_order_id and status

        Raises:
            ExchangeConnectionError: If exchange is not connected
            OrderExecutionError: If order placement fails
            ValueError: If position_side is not set for perpetual orders
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        # Validate position_side for perpetual futures
        if not order.position_side:
            raise ValueError("position_side is required for perpetual futures orders")

        # Convert trading pair to XT format
        symbol = f"{order.trading_pair.base_currency}_{order.trading_pair.quote_currency}".lower()
        
        # Build request body
        body = {
            "symbol": symbol,
            "orderSide": order.side.value,
            "orderType": order.order_type.value,
            "positionSide": order.position_side,
            "origQty": str(order.quantity),
        }
        
        # Add price for LIMIT orders
        if order.order_type == OrderType.LIMIT and order.price:
            body["price"] = str(order.price)
        
        # Add time in force if specified
        if order.time_in_force:
            body["timeInForce"] = order.time_in_force
        
        # Add client order ID if specified
        if order.order_id:
            body["clientOrderId"] = order.order_id
        
        path = "/future/trade/v1/order/create"
        data = await self._request("POST", path, params=None, body=body, require_auth=True)
        
        # Parse response and update order
        order.exchange_order_id = str(data.get("orderId", ""))
        order.status = OrderStatus.PENDING  # Will be updated by order status query
        order.updated_at = datetime.utcnow()
        
        logger.info(
            "Order placed successfully",
            symbol=symbol,
            order_id=order.exchange_order_id,
            side=order.side.value,
            position_side=order.position_side,
            quantity=str(order.quantity),
        )
        
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order.

        Args:
            order_id: Exchange order ID

        Returns:
            True if cancelled successfully

        Raises:
            ExchangeConnectionError: If exchange is not connected
            OrderExecutionError: If cancellation fails
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        path = "/future/trade/v1/order/cancel"
        body = {"orderId": order_id}
        await self._request("POST", path, params=None, body=body, require_auth=True)
        
        logger.info("Order cancelled successfully", order_id=order_id)
        return True

    async def cancel_all_orders(self, trading_pair: TradingPair | None = None) -> int:
        """Cancel all open orders for a trading pair or all markets.

        Args:
            trading_pair: Trading pair to cancel orders for. If None, cancels all orders.

        Returns:
            Number of orders cancelled

        Raises:
            ExchangeConnectionError: If exchange is not connected
            OrderExecutionError: If cancellation fails
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        if trading_pair is None:
            # Cancel all orders across all markets
            path = "/future/trade/v1/order/cancel-all"
            body = {}
            await self._request("POST", path, params=None, body=body, require_auth=True)
            
            logger.info("All orders cancelled successfully")
            # API doesn't return count, so we return 0 to indicate unknown count
            return 0
        else:
            # Cancel all orders for specific trading pair
            symbol = f"{trading_pair.base_currency}_{trading_pair.quote_currency}".lower()
            path = "/future/trade/v1/order/cancel-all"
            body = {"symbol": symbol}
            await self._request("POST", path, params=None, body=body, require_auth=True)
            
            logger.info("All orders cancelled for trading pair", symbol=symbol)
            # API doesn't return count, so we return 0 to indicate unknown count
            return 0

    async def get_order_status(self, order_id: str) -> Order:
        """Get order status.

        Args:
            order_id: Exchange order ID

        Returns:
            Order with current status

        Raises:
            ExchangeConnectionError: If exchange is not connected
            OrderExecutionError: If order not found
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        path = "/future/trade/v1/order/detail"
        params = {"orderId": order_id}
        data = await self._request("GET", path, params=params, body=None, require_auth=True)
        
        # Parse order detail response
        symbol = data.get("symbol", "")
        parts = symbol.split("_")
        base = parts[0].upper() if len(parts) > 0 else "BTC"
        quote = parts[1].upper() if len(parts) > 1 else "USDT"
        
        # Create TradingPair
        trading_pair = TradingPair(
            base_currency=base,
            quote_currency=quote,
            exchange="xt_perp",
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1000000"),
            price_precision=8,
            quantity_precision=8,
        )
        
        # Map XT order status to OrderStatus enum
        xt_status = data.get("state", "NEW")
        status_map = {
            "NEW": OrderStatus.PENDING,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELED,
            "REJECTED": OrderStatus.FAILED,
            "EXPIRED": OrderStatus.CANCELED,
        }
        status = status_map.get(xt_status, OrderStatus.PENDING)
        
        # Parse order side and type
        order_side_str = data.get("orderSide", "BUY")
        order_side = OrderSide.BUY if order_side_str == "BUY" else OrderSide.SELL
        
        order_type_str = data.get("orderType", "LIMIT")
        order_type = OrderType.LIMIT if order_type_str == "LIMIT" else OrderType.MARKET
        
        # Create Order object
        order = Order(
            order_id=data.get("clientOrderId", order_id),
            exchange_order_id=order_id,
            trading_pair=trading_pair,
            side=order_side,
            order_type=order_type,
            price=Decimal(str(data.get("price", "0"))),
            quantity=Decimal(str(data.get("origQty", "0"))),
            filled_quantity=Decimal(str(data.get("executedQty", "0"))),
            status=status,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            exchange="xt_perp",
            position_side=data.get("positionSide"),
            time_in_force=data.get("timeInForce", "GTC"),
        )
        
        return order

    # ============================================================================
    # BaseExchange Abstract Methods - Streaming (WebSocket)
    # ============================================================================

    async def subscribe_ticker(self, trading_pair: TradingPair) -> AsyncIterator[Price]:
        """Subscribe to ticker updates.

        Args:
            trading_pair: Trading pair to subscribe to

        Yields:
            Real-time price updates
        """
        raise NotImplementedError("WebSocket streaming not yet implemented")
        yield  # Make this a generator

    async def subscribe_orderbook(self, trading_pair: TradingPair, depth: int = 20) -> AsyncIterator[OrderBook]:
        """Subscribe to orderbook updates.

        Args:
            trading_pair: Trading pair to subscribe to
            depth: Number of price levels

        Yields:
            Real-time orderbook updates
        """
        raise NotImplementedError("WebSocket streaming not yet implemented")
        yield  # Make this a generator

    # ============================================================================
    # BaseExchange Method - Trading Pair Info
    # ============================================================================

    async def get_trading_pair_info(
        self, trading_pair: TradingPair | None = None
    ) -> TradingPair | list[TradingPair]:
        """Get detailed trading pair information from exchange.

        Args:
            trading_pair: Trading pair to get info for. If None, returns all
                         supported trading pairs (batch query).

        Returns:
            - If trading_pair is provided: Single TradingPair object with full info
            - If trading_pair is None: List of TradingPair objects for all supported pairs

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        if trading_pair is None:
            # Batch query - return all trading pairs from cache
            return list(self._trading_pairs.values())
        else:
            # Single pair query
            pair_key = f"{trading_pair.base_currency}/{trading_pair.quote_currency}"
            
            # Check cache first
            if pair_key in self._trading_pairs:
                return self._trading_pairs[pair_key]
            
            # If not in cache, fetch from API
            symbol = f"{trading_pair.base_currency}_{trading_pair.quote_currency}".lower()
            path = "/future/market/v1/public/symbol/detail"
            params = {"symbol": symbol}
            data = await self._request("GET", path, params=params, body=None, require_auth=False)
            
            # Parse trading pair detail
            # Expected format: {"symbol": "btc_usdt", "pricePrecision": 2, "quantityPrecision": 3, ...}
            base = trading_pair.base_currency
            quote = trading_pair.quote_currency
            
            price_precision = int(data.get("pricePrecision", 8))
            quantity_precision = int(data.get("quantityPrecision", 8))
            min_order_size = Decimal(str(data.get("minQty", "0.001")))
            max_order_size = Decimal(str(data.get("maxQty", "1000000")))
            
            # Parse leverage brackets if available
            leverage_brackets_data = data.get("leverageBrackets", [])
            leverage_brackets_list = []
            if leverage_brackets_data:
                for bracket in leverage_brackets_data:
                    from tri_arb.models.perpetual import LeverageBracket
                    bracket_obj = LeverageBracket(
                        min_notional=Decimal(str(bracket.get("minNotional", "0"))),
                        max_notional=Decimal(str(bracket.get("maxNotional", "0"))),
                        max_leverage=int(bracket.get("maxLeverage", 1)),
                    )
                    leverage_brackets_list.append(bracket_obj)
            
            # Create TradingPair with full info
            pair = TradingPair(
                base_currency=base,
                quote_currency=quote,
                exchange="xt_perp",
                min_order_size=min_order_size,
                max_order_size=max_order_size,
                price_precision=price_precision,
                quantity_precision=quantity_precision,
                leverage_brackets=leverage_brackets_list,
                contract_size=Decimal(str(data.get("contractSize", "1"))),
                contract_type="PERPETUAL",
            )
            
            # Update cache
            self._trading_pairs[pair_key] = pair
            
            return pair

    # ============================================================================
    # Perpetual Futures Specific Methods
    # ============================================================================

    async def get_balance(self) -> dict[str, dict[str, Decimal]]:
        """Get account balance for perpetual futures.

        Returns:
            Dictionary with balance information:
            {
                "USDT": {
                    "available": Decimal("1000.0"),
                    "frozen": Decimal("100.0"),
                    "total": Decimal("1100.0")
                },
                "BTC": {
                    "available": Decimal("0.5"),
                    "frozen": Decimal("0.1"),
                    "total": Decimal("0.6")
                },
                ...
            }

        Raises:
            ExchangeConnectionError: If exchange is not connected
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        # Use compat endpoint based on xt_perp_api.py implementation
        path = "/future/user/v1/compat/balance/list"
        data = await self._request("GET", path, params=None, body=None, require_auth=True)

        # Debug: Log raw API response
        logger.info(
            "Raw balance API response (perp)",
            response_type=type(data).__name__,
            is_list=isinstance(data, list),
            sample_data=str(data)[:500] if data else "empty"
        )

        # Parse balance response
        # Handle two possible formats:
        # 1. Direct list: [{"currency": "USDT", "available": "1000.0", "frozen": "100.0"}, ...]
        # 2. Dict with data field: {"data": [...]}
        balances: dict[str, dict[str, Decimal]] = {}

        # Extract balance items
        if isinstance(data, list):
            items = data
            logger.info("Using direct list format (perp)", item_count=len(items))
        elif isinstance(data, dict):
            items = data.get("data", [])
            logger.info("Extracting from dict format (perp)", item_count=len(items))
        else:
            logger.error("Unexpected perp balance response type", response_type=type(data).__name__)
            return balances

        # Parse each balance item
        # XT perp API uses different field names:
        # - coin (not currency)
        # - amount (available balance)
        # - openOrderMarginFrozen (frozen balance)
        for item in items:
            currency = item.get("coin", "").upper()
            if not currency:
                continue

            # Use 'amount' for available balance
            available = Decimal(str(item.get("amount", "0")))
            # Use 'openOrderMarginFrozen' for frozen balance
            frozen = Decimal(str(item.get("openOrderMarginFrozen", "0")))
            total = available + frozen

            logger.info(
                "Processing perp balance item",
                currency=currency,
                available=str(available),
                frozen=str(frozen),
                total=str(total),
                will_include=total > 0
            )

            # Only include non-zero balances
            if total > 0:
                balances[currency] = {
                    "available": available,
                    "frozen": frozen,
                    "total": total,
                }

        logger.info("Perp balance retrieved", currency_count=len(balances), currencies=list(balances.keys()))
        return balances

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        """Get current positions for a trading pair or all positions.

        Args:
            symbol: Trading pair symbol in XT format (e.g., "btc_usdt").
                   If None, returns all open positions.

        Returns:
            List of Position objects

        Raises:
            ExchangeConnectionError: If exchange is not connected
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        path = "/future/user/v1/position/list"
        params = {"symbol": symbol} if symbol else None
        data = await self._request("GET", path, params=params, body=None, require_auth=True)

        # Debug: Log raw API response
        logger.info(
            "Raw positions API response",
            response_type=type(data).__name__,
            is_list=isinstance(data, list),
            item_count=len(data) if isinstance(data, list) else "N/A",
            sample_data=str(data)[:500] if data else "empty"
        )

        # Parse positions response
        # Expected format: [{"symbol": "btc_usdt", "positionSide": "LONG", "positionAmt": "0.5", ...}]
        positions: list[Position] = []

        if isinstance(data, list):
            logger.info("Parsing positions list", total_items=len(data))

            for item in data:
                symbol_str = item.get("symbol", "")
                side = item.get("positionSide", "LONG")
                quantity = Decimal(str(item.get("positionSize", "0")))

                # Log every position item (including zero quantity)
                logger.info(
                    "Processing position item",
                    symbol=symbol_str,
                    side=side,
                    quantity=str(quantity),
                    entry_price=str(item.get("entryPrice", "0")),
                    unrealized_pnl=str(item.get("unrealizedProfit", "0")),
                    will_skip=(quantity <= 0)
                )

                # Skip closed positions (quantity = 0)
                # API may return historical positions with zero quantity
                if quantity <= 0:
                    logger.info("Skipping closed position", symbol=symbol_str, quantity=str(quantity))
                    continue

                entry_price = Decimal(str(item.get("entryPrice", "0")))
                mark_price = Decimal(str(item.get("markPrice", "0")))
                liquidation_price = Decimal(str(item.get("liquidationPrice", "0")))
                unrealized_pnl = Decimal(str(item.get("unrealizedProfit", "0")))
                leverage_val = int(item.get("leverage", 1))
                margin = Decimal(str(item.get("isolatedMargin", "0")))

                # Calculate ROE (Return on Equity)
                roe = (unrealized_pnl / margin * Decimal("100")) if margin > 0 else Decimal("0")

                position = Position(
                    symbol=symbol_str,
                    side=side,
                    quantity=quantity,
                    entry_price=entry_price,
                    mark_price=mark_price,
                    liquidation_price=liquidation_price,
                    unrealized_pnl=unrealized_pnl,
                    leverage=leverage_val,
                    margin=margin,
                    roe=roe,
                )
                positions.append(position)
        else:
            logger.warning(
                "Unexpected positions response format",
                response_type=type(data).__name__,
                data=data
            )

        logger.info(
            "Positions query completed",
            total_api_items=len(data) if isinstance(data, list) else 0,
            valid_positions=len(positions),
            position_symbols=[p.symbol for p in positions]
        )

        return positions

    async def get_funding_rate(self, symbol: str) -> FundingRate:
        """Get current funding rate for a trading pair.

        Args:
            symbol: Trading pair symbol in XT format (e.g., "btc_usdt")

        Returns:
            FundingRate object with current rate and next funding time

        Raises:
            ExchangeConnectionError: If exchange is not connected
            InvalidTradingPairError: If trading pair is not supported
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        path = "/future/market/v1/public/q/funding-rate"
        params = {"symbol": symbol}
        data = await self._request("GET", path, params=params, body=None, require_auth=False)
        
        # Parse funding rate response
        # Expected format: {"symbol": "btc_usdt", "rate": "0.0001", "nextFundingTime": 1234567890000}
        rate = Decimal(str(data.get("rate", "0")))
        next_funding_time_ms = data.get("nextFundingTime", 0)
        
        # Convert milliseconds to datetime
        next_funding_time = datetime.fromtimestamp(next_funding_time_ms / 1000, tz=timezone.utc)
        
        funding_rate = FundingRate(
            symbol=symbol,
            rate=rate,
            next_funding_time=next_funding_time,
        )
        
        return funding_rate

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """Set leverage for a trading pair.

        Args:
            symbol: Trading pair symbol
            leverage: Leverage multiplier (1-125)

        Raises:
            ValueError: If leverage is out of range
        """
        if leverage < 1 or leverage > 125:
            raise ValueError(f"Invalid leverage: {leverage}. Must be between 1 and 125.")

        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        path = "/future/user/v1/position/leverage"
        body = {"symbol": symbol, "leverage": leverage}
        await self._request("POST", path, params=None, body=body, require_auth=True)
        
        logger.info("Leverage set successfully", symbol=symbol, leverage=leverage)
