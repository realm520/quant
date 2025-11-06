"""XT Perpetual Futures Exchange Adapter.

Implements BaseExchange interface for XT perpetual futures trading,
supporting position management, leverage control, and funding rate tracking.
"""

import asyncio
import decimal
import hashlib
import hmac
import time
import aiohttp
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from decimal import Decimal
from pyxt.perp import Perp
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
        self.perp = Perp("https://fapi.xt.com", api_key, api_secret)
    def get_name(self) -> str:
        """Get the name of the exchange."""
        return "xt_perp"
    
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

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as http_err:
                content_preview = response.text[:500] if response.text else ""
                logger.error(
                    "XT API HTTP error",
                    method=method,
                    path=path,
                    status_code=response.status_code,
                    response_text=content_preview,
                )
                raise

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
                error_msg = data.get("ma", ["Unknown error"])[0] if data.get("ma") else data.get("msg", "Unknown error")
                logger.error(
                    "XT API returned error code",
                    method=method,
                    path=path,
                    rc=rc,
                    message=error_msg,
                    raw_response=data,
                )
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
            # Note: _request() already extracts the "result" field, so data IS the result
            result = data
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
                try:
                    bp_str = item.get("bp", "")
                    ap_str = item.get("ap", "")
                    bq_str = item.get("bq", "")
                    aq_str = item.get("aq", "")
                    
                    # Skip if any field is empty or invalid
                    if not bp_str or not ap_str or not bq_str or not aq_str:
                        logger.debug("Skipping ticker with missing fields", symbol=symbol_str)
                        continue
                    
                    bid_price = Decimal(str(bp_str))
                    ask_price = Decimal(str(ap_str))
                    bid_volume = Decimal(str(bq_str))
                    ask_volume = Decimal(str(aq_str))
                except (ValueError, decimal.InvalidOperation, decimal.ConversionSyntax) as e:
                    logger.debug(
                        "Skipping ticker with invalid number format",
                        symbol=symbol_str,
                        error=str(e),
                        bp=item.get("bp"),
                        ap=item.get("ap"),
                    )
                    continue
                
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
            
            # Debug: Log what _request() returns
            logger.info(
                "Ticker book API response",
                symbol=symbol,
                data_type=type(data).__name__,
                data_keys=list(data.keys()) if isinstance(data, dict) else "not a dict",
                data_sample=str(data)[:300] if data else "None"
            )
            
            # Parse single book ticker response
            # Note: _request() already extracts the "result" field, so data IS the result
            # Expected format after _request(): {s, t, ap, aq, bp, bq}
            result = data
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
            
            return price

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
    async def create_user_stream_listen_key(self) -> str:
        """创建用户数据 WebSocket 流的 listen key"""
        try:
            # 使用 Perp 客户端获取 listen key
            status_code, response, headers = self.perp.get_listen_key()

            # 如果返回状态码不是 200 或者没有 'result' 字段，则抛出异常
            if status_code != 200 or 'result' not in response:
                raise RuntimeError(f"获取 listen key 失败，意外的响应: {response}")

            listen_key = response['result']
            logger.info(f"成功获取 XT listen key: {listen_key[:8]}...")

            return listen_key

        except Exception as exc:
            logger.error(f"创建 XT 用户流 listen key 失败: {str(exc)}")
            raise RuntimeError(f"创建 XT 用户流 listen key 失败: {str(exc)}") from exc
    # async def create_user_stream_listen_key(self) -> str:
    #     """创建用户数据 WebSocket 流的 listen key"""
    #     try:
    #         async with aiohttp.ClientSession() as session:
    #             # 构造请求头
    #             headers = {
    #                 'Content-Type': 'application/json',
    #                 'X-API-KEY': self._api_key
    #             }
    #             # 构造请求数据
    #             payload = {}

    #             # 发送 POST 请求来获取 listen key
    #             async with session.post(f"{self.BASE_URL}/future/user/v1/listen-key", headers=headers, json=payload) as response:
    #                 if response.status != 200:
    #                     raise RuntimeError(f"获取 listen key 失败，HTTP 状态码: {response.status}")

    #                 result = await response.json()
                    
    #                 # 检查响应是否包含 "result"
    #                 if 'result' not in result:
    #                     raise RuntimeError(f"获取 listen key 失败，响应内容: {result}")
                    
    #                 listen_key = result['result']
    #                 logger.info(f"成功获取 XT listen key: {listen_key[:8]}...")

    #                 return listen_key

    #     except Exception as exc:
    #         logger.error(f"创建 XT 用户流 listen key 失败: {str(exc)}")
    #         raise RuntimeError(f"创建 XT 用户流 listen key 失败: {str(exc)}") from exc

    @staticmethod
    def _extract_listen_key(response: Any) -> str | None:
        """Extract listen key from XT API response."""
        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            for key in ("listenKey", "listen_key", "result", "data"):
                if key not in response:
                    continue
                extracted = XTPerpExchange._extract_listen_key(response[key])
                if extracted:
                    return extracted
            return None

        if isinstance(response, list):
            for item in response:
                extracted = XTPerpExchange._extract_listen_key(item)
                if extracted:
                    return extracted

        return None

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

            # Debug: Log all PnL related fields
            not_profit = item.get("notProfit")
            profit = item.get("profit")
            margin_balance = item.get("marginBalance")
            logger.info(
                "Processing perp balance item",
                currency=currency,
                available=str(available),
                frozen=str(frozen),
                total=str(total),
                not_profit=str(not_profit) if not_profit is not None else "None",
                profit=str(profit) if profit is not None else "None",
                margin_balance=str(margin_balance) if margin_balance is not None else "None",
                will_include=total > 0
            )

            # Extract additional fields from API response
            # XT API balance endpoint uses:
            # - notProfit: 未实现盈亏（负数表示亏损）
            # - profit: 已实现盈亏
            # - marginBalance: 保证金余额（总权益）
            # - crossedMargin: 全仓保证金
            # - isolatedMargin: 逐仓保证金
            unrealized_pnl = Decimal(str(item.get("notProfit", item.get("unrealizedPnl", item.get("unrealizedProfit", "0")))))
            realized_pnl = Decimal(str(item.get("profit", item.get("realizedPnl", item.get("realizedProfit", "0")))))
            # marginBalance is the total equity (wallet balance + unrealized PnL)
            equity = Decimal(str(item.get("marginBalance", item.get("equity", item.get("totalEquity", str(total + unrealized_pnl))))))
            # Use crossedMargin + isolatedMargin as total margin
            crossed_margin = Decimal(str(item.get("crossedMargin", "0")))
            isolated_margin = Decimal(str(item.get("isolatedMargin", "0")))
            margin = crossed_margin + isolated_margin
            # Calculate margin ratio if we have marginBalance and margin
            margin_balance = Decimal(str(item.get("marginBalance", "0")))
            margin_ratio = (margin / margin_balance * Decimal("100")) if margin_balance > 0 else Decimal("0")
            
            # Only include non-zero balances
            if total > 0:
                balances[currency] = {
                    "available": available,
                    "frozen": frozen,
                    "total": total,
                    "unrealized_pnl": unrealized_pnl,
                    "realized_pnl": realized_pnl,
                    "equity": equity,
                    "margin": margin,
                    "margin_ratio": margin_ratio,
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

        # Use /future/user/v1/position endpoint (not /position/list)
        path = "/future/user/v1/position"
        params = {"symbol": symbol} if symbol else None
        data = await self._request("GET", path, params=params, body=None, require_auth=True)
        
        # XT API returns {result: [...]} format, extract result array
        if isinstance(data, dict) and "result" in data:
            data = data["result"]
        elif isinstance(data, dict) and "data" in data:
            data = data["data"]

        # Parse positions response
        # Expected format: [{"symbol": "btc_usdt", "positionSide": "LONG", "positionAmt": "0.5", ...}]
        positions: list[Position] = []

        if isinstance(data, list):
            logger.debug("Parsing positions list", total_items=len(data))

            for item in data:
                # Extract all fields from API response
                symbol_str = item.get("symbol", "")
                side = item.get("positionSide", "LONG")
                # XT API uses positionSize (in contracts/张)
                position_size_raw = item.get("positionSize")
                quantity = Decimal(str(position_size_raw)) if position_size_raw is not None else Decimal("0")
                
                # Extract all other fields
                entry_price_raw = item.get("entryPrice")
                cal_mark_price_raw = item.get("calMarkPrice")
                break_price_raw = item.get("breakPrice")
                floating_pl_raw = item.get("floatingPL")
                realized_profit_raw = item.get("realizedProfit")
                leverage_raw = item.get("leverage")
                isolated_margin_raw = item.get("isolatedMargin")

                # Skip closed positions (quantity = 0)
                # API may return historical positions with zero quantity
                if quantity <= 0:
                    logger.debug("Skipping closed position", symbol=symbol_str, quantity=str(quantity))
                    continue

                # Convert all fields to Decimal with proper handling
                entry_price = Decimal(str(entry_price_raw)) if entry_price_raw is not None else Decimal("0")
                # XT API uses calMarkPrice for mark price (计算标记价格)
                mark_price = Decimal(str(cal_mark_price_raw)) if cal_mark_price_raw is not None else Decimal("0")
                # XT API uses breakPrice for liquidation price (强平价格)
                liquidation_price = Decimal(str(break_price_raw)) if break_price_raw is not None else Decimal("0")
                
                # XT API uses floatingPL for unrealized PnL (未实现盈亏)
                if floating_pl_raw is not None:
                    unrealized_pnl = Decimal(str(floating_pl_raw))
                else:
                    logger.warning(
                        "floatingPL field not found",
                        symbol=symbol_str
                    )
                    unrealized_pnl = Decimal("0")
                
                # XT API uses realizedProfit for realized PnL (已实现盈亏)
                if realized_profit_raw is not None:
                    realized_pnl = Decimal(str(realized_profit_raw))
                else:
                    realized_pnl = Decimal("0")
                
                # XT API uses leverage (杠杆倍数)
                leverage_val = int(leverage_raw) if leverage_raw is not None else 1
                
                # XT API uses isolatedMargin for margin (仓位保证金)
                # For CROSSED position type, margin might be 0, use crossedMargin from balance instead
                if isolated_margin_raw is not None:
                    margin = Decimal(str(isolated_margin_raw))
                else:
                    margin = Decimal("0")
                
                # Log position summary (only key fields)
                logger.debug(
                    "Position parsed",
                    symbol=symbol_str,
                    quantity=str(quantity),
                    unrealized_pnl=str(unrealized_pnl),
                    realized_pnl=str(realized_pnl),
                )

                # Calculate ROE (Return on Equity)
                roe = (unrealized_pnl / margin * Decimal("100")) if margin > 0 else Decimal("0")

                # Create position with all fields including realized_pnl
                # Note: Position model may not have realized_pnl, so we'll store it separately
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
                # Store realized_pnl as an attribute for later use
                position.realized_pnl = realized_pnl
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

    async def get_order_list(
        self,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[Order]:
        """Query order history.

        Args:
            symbol: Trading pair symbol (optional, None for all symbols)
            start_time: Start timestamp in milliseconds (optional)
            end_time: End timestamp in milliseconds (optional)
            limit: Maximum number of orders to return (default: 100, max: 500)

        Returns:
            List of orders

        Raises:
            RuntimeError: If exchange is not connected
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        path = "/future/trade/v1/order/list-history"
        params = {"limit": min(limit, 500)}

        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        data = await self._request("GET", path, params=params, body=None, require_auth=True)

        orders = []
        order_list = data.get("result", {}).get("items", [])

        for order_data in order_list:
            try:
                # Parse trading pair from symbol
                symbol_str = order_data.get("symbol", "")
                if "_" in symbol_str:
                    base, quote = symbol_str.split("_", 1)
                    trading_pair = TradingPair(base_currency=base.upper(), quote_currency=quote.upper())
                else:
                    logger.warning("Invalid symbol format", symbol=symbol_str)
                    continue

                # Parse order data
                order = Order(
                    exchange_order_id=str(order_data.get("orderId", "")),
                    trading_pair=trading_pair,
                    side=OrderSide(order_data.get("orderSide", "BUY")),
                    order_type=OrderType(order_data.get("orderType", "LIMIT")),
                    quantity=Decimal(str(order_data.get("origQty", "0"))),
                    price=Decimal(str(order_data.get("price", "0"))) if order_data.get("price") else None,
                    status=self._parse_order_status(order_data.get("state", "")),
                    timestamp=datetime.fromtimestamp(
                        order_data.get("createTime", 0) / 1000, tz=timezone.utc
                    ) if order_data.get("createTime") else None,
                    position_side=order_data.get("positionSide", "LONG"),
                )
                orders.append(order)

            except (ValueError, KeyError, decimal.InvalidOperation) as e:
                logger.warning("Failed to parse order data", error=str(e), order_data=order_data)
                continue

        logger.info("Retrieved order list", count=len(orders), symbol=symbol)
        return orders

    async def get_user_trades(
        self,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query user trade history.

        Args:
            symbol: Trading pair symbol (optional, None for all symbols)
            start_time: Start timestamp in milliseconds (optional)
            end_time: End timestamp in milliseconds (optional)
            limit: Maximum number of trades to return (default: 100, max: 500)

        Returns:
            List of trade records

        Raises:
            RuntimeError: If exchange is not connected
        """
        if not self.is_connected or self._client is None:
            raise RuntimeError("Exchange is not connected. Call connect() first.")

        path = "/future/trade/v1/order/trade-list"
        params = {"limit": min(limit, 500)}

        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        data = await self._request("GET", path, params=params, body=None, require_auth=True)

        trades = data.get("result", {}).get("items", [])

        logger.info("Retrieved user trades", count=len(trades), symbol=symbol)
        return trades
