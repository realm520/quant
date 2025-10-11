"""XT Exchange adapter for tri-arb trading system.

Provides async interface to XT Exchange REST API v4.
"""

import hashlib
import hmac
import json
import time
import urllib.parse
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from tri_arb.config.logging import get_logger
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
from tri_arb.data.cache import cache_manager
from tri_arb.exchanges.base import BaseExchange


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
    CACHE_KEY_PREFIX: str = "xt:trading_pair:"  # Cache key prefix for trading pairs

    def __init__(
        self,
        name: str = "xt",
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        """Initialize XT Exchange adapter.

        Args:
            name: Exchange identifier (default: "xt")
            api_key: XT API key (optional, required only for trading operations)
            api_secret: XT API secret (optional, required only for trading operations)
            
        Note:
            Public API operations (get_ticker, get_orderbook, get_trading_pair_info)
            work without credentials. Trading operations require valid credentials.
        """
        super().__init__(name)
        self.api_key = api_key
        self.api_secret = api_secret
        self._client: httpx.AsyncClient | None = None
        self._trading_pairs_cache: dict[str, TradingPair] = {}  # In-memory cache

        logger.info(
            "XTExchange initialized",
            has_api_key=bool(api_key),
            has_api_secret=bool(api_secret),
        )

    async def connect(self) -> None:
        """Establish connection to XT exchange and load trading pair information.

        Creates HTTP client with connection pooling and timeout configuration,
        then loads and caches all trading pair information for optimal performance.

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

        # Load and cache all trading pair information
        try:
            logger.info("Loading trading pair information from XT exchange")
            result = await self.get_trading_pair_info(None)  # Get all pairs

            # Type assertion: batch query returns list
            if not isinstance(result, list):
                raise ValueError(f"Expected list from batch query, got {type(result)}")
            trading_pairs = result

            # Cache to memory
            for pair in trading_pairs:
                symbol = self._to_xt_symbol(pair)
                self._trading_pairs_cache[symbol] = pair

                # Cache to LRU cache (long-term storage)
                cache_key = f"{self.CACHE_KEY_PREFIX}{symbol}"
                await cache_manager.set_lru(cache_key, pair)

            logger.info(
                "Trading pair information loaded and cached",
                count=len(trading_pairs),
                exchange=self.name,
            )
        except Exception as e:
            logger.warning(
                "Failed to load trading pair information",
                error=str(e),
                exchange=self.name,
            )
            # Don't fail connection - allow system to continue with degraded functionality

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

    def _require_credentials(self) -> None:
        """Check if API credentials are available.
        
        Raises:
            ValueError: If API key or secret is missing
            
        Note:
            This method should be called at the start of all trading operations
            (place_order, cancel_order, get_order_status, get_trade_history).
        """
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "Trading operations require API credentials. "
                "Please set XT_API_KEY and XT_API_SECRET environment variables."
            )

    async def get_ticker(self, trading_pair: TradingPair | None = None) -> Price | list[Price]:
        """Get current ticker price for a trading pair or all markets.

        Args:
            trading_pair: Trading pair to get ticker for. If None, returns all
                         active markets (batch query). Default is None.

        Returns:
            - If trading_pair is provided: Single Price object
            - If trading_pair is None: List of Price objects for all active markets

        Raises:
            ValueError: If not connected or trading pair invalid
            httpx.HTTPStatusError: If API request fails
        """
        # Batch query: Get all market tickers
        if trading_pair is None:
            response = await self._request(
                method="GET",
                path=f"/{self.API_VERSION}/public/ticker/book",
                params=None,  # No symbol param for batch query
                authenticated=False,
            )

            data = response.json()
            result_raw = data.get("result", [])

            # Result should be a list of tickers for batch query
            if not isinstance(result_raw, list):
                raise ValueError(f"Expected list result for batch query, got {type(result_raw)}")

            # Parse each ticker to Price object
            prices: list[Price] = []
            failed_markets: list[str] = []
            seen_symbols: set[str] = set()  # Track seen symbols for deduplication

            for ticker_data in result_raw:
                try:
                    symbol = ticker_data.get("s", "unknown")

                    # Skip duplicate symbols (XT API may return duplicates)
                    if symbol in seen_symbols:
                        logger.debug(
                            "Skipping duplicate symbol in batch query",
                            symbol=symbol,
                        )
                        continue

                    seen_symbols.add(symbol)
                    price = self._parse_ticker_to_price(ticker_data, trading_pair=None)
                    prices.append(price)
                except Exception as e:
                    symbol = ticker_data.get("s", "unknown")
                    failed_markets.append(symbol)

            # Log partial failures if any
            if failed_markets:
                logger.info(
                    "Batch ticker query completed with partial failures",
                    total_markets=len(result_raw),
                    successful=len(prices),
                    failed=len(failed_markets),
                    failed_symbols=failed_markets[:10],  # Log first 10 failures
                )

            return prices

        # Single pair query: Get specific ticker
        symbol = self._to_xt_symbol(trading_pair)

        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/public/ticker/book",
            params={"symbol": symbol},
            authenticated=False,
        )

        data = response.json()

        # Handle XT API response format variations
        # API may return result as list or dict depending on endpoint/query
        result_raw = data.get("result", {})

        # If result is a list, extract first element (single symbol query)
        if isinstance(result_raw, list):
            if not result_raw:
                raise ValueError(f"Empty ticker result for {symbol}")
            result = result_raw[0]
        else:
            result = result_raw

        # Use helper method to parse ticker data to Price object
        return self._parse_ticker_to_price(result, trading_pair)

    async def get_orderbook(self, trading_pair: TradingPair, depth: int = 20) -> OrderBook:
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
        self._require_credentials()  # Check credentials before trading
        
        symbol = self._to_xt_symbol(order.trading_pair)

        # Build request body for XT API
        # CRITICAL: Key order must match xt_spot_api.py for signature consistency
        body = {
            "symbol": symbol,
            "side": order.side.value.upper(),  # BUY/SELL
            "type": order.order_type.value.upper(),  # MARKET/LIMIT
            "timeInForce": "GTC",  # Good Till Cancel (must be here for order match)
            "bizType": "SPOT",
            "quantity": str(order.quantity),
        }

        # Add price for limit orders (added last to match xt_spot_api.py)
        if order.order_type == OrderType.LIMIT:
            if order.price is None:
                raise ValueError("Limit order requires price")
            body["price"] = str(order.price)

        response = await self._request(
            method="POST",
            path=f"/{self.API_VERSION}/order",
            json_data=body,
            authenticated=True,
        )

        data = response.json()
        result = self._check_response(data)

        # Ensure result is a dict (some endpoints return lists)
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict result for order placement, got {type(result)}")

        # Update order with exchange order ID and status
        order.exchange_order_id = str(result.get("orderId"))
        order.order_id = str(result.get("orderId", order.order_id))

        # Map XT status to internal OrderStatus
        # NOTE: POST /v4/order response does NOT include status/state field
        # Default to NEW status for newly created orders
        xt_status = result.get("state", result.get("status", "NEW"))
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
        self._require_credentials()  # Check credentials before trading
        
        # XT API DELETE uses query parameters (similar to GET), not body
        params = {
            "orderId": order_id,
            "bizType": "SPOT",
        }

        try:
            response = await self._request(
                method="DELETE",
                path=f"/{self.API_VERSION}/order",
                params=params,
                json_data=None,
                authenticated=True,
            )

            data = response.json()
            result = self._check_response(data)

            # Check if cancellation was successful
            # Result might be dict with status field or other format
            success = (
                result.get("status") == "CANCELED"
                if isinstance(result, dict) and "status" in result
                else True  # If no status field, consider successful (rc=0 already checked)
            )

            return success

        except (httpx.HTTPStatusError, ValueError) as e:
            logger.error(
                "Failed to cancel order",
                order_id=order_id,
                error=str(e),
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
        self._require_credentials()  # Check credentials before querying orders
        
        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/order",
            params={"orderId": order_id, "bizType": "SPOT"},
            authenticated=True,
        )

        data = response.json()
        result = self._check_response(data)

        # Ensure result is a dict
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict result for order status, got {type(result)}")

        # Parse XT symbol to trading pair
        symbol = result.get("symbol", "")
        base, quote = self._from_xt_symbol(symbol)

        # Map XT status to internal OrderStatus
        # NOTE: XT API uses 'state' field, not 'status'
        xt_status = result.get("state", "")
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
            exchange_order_id=str(result.get("orderId", order_id)),
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

    async def get_trade_history(self, trading_pair: TradingPair, limit: int = 100) -> list[Trade]:
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
        self._require_credentials()  # Check credentials before querying trade history
        
        symbol = self._to_xt_symbol(trading_pair)

        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/trade",
            params={"bizType": "SPOT", "symbol": symbol, "limit": limit},
            authenticated=True,
        )

        data = response.json()

        # Debug: Log raw API response (using info level to ensure visibility)
        logger.info("XT API /v4/trade response structure",
                    data_type=type(data).__name__,
                    data_keys=list(data.keys()) if isinstance(data, dict) else None,
                    result_type=type(data.get("result")).__name__ if isinstance(data, dict) else None,
                    full_response=data)

        # Handle None or missing result (empty trade history)
        trades_data = data.get("result") or []

        # Debug: Check result structure (using info level)
        logger.info("Trades data details",
                    is_list=isinstance(trades_data, list),
                    is_string=isinstance(trades_data, str),
                    length=len(trades_data) if isinstance(trades_data, (list, str)) else None,
                    first_item_type=type(trades_data[0]).__name__ if isinstance(trades_data, list) and trades_data else None,
                    first_3_items=trades_data[:3] if isinstance(trades_data, list) else str(trades_data)[:300])

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

    async def get_trading_pair_info(
        self, trading_pair: TradingPair | None = None
    ) -> TradingPair | list[TradingPair]:
        """Get detailed trading pair information from XT exchange.

        Calls XT API `/v4/public/symbol` endpoint to retrieve complete trading
        pair configuration including precision, limits, fees, and filters.
        Uses cache-first strategy for optimal performance.

        Args:
            trading_pair: Trading pair to get info for. If None, returns all
                         supported trading pairs (batch query). Default is None.

        Returns:
            - If trading_pair is provided: Single TradingPair object with full info
            - If trading_pair is None: List of TradingPair objects for all supported pairs

        Raises:
            ValueError: If not connected or trading pair invalid
            httpx.HTTPStatusError: If API request fails

        Examples:
            >>> # Single pair query
            >>> pair = TradingPair(base_currency="BTC", quote_currency="USDT", ...)
            >>> info = await exchange.get_trading_pair_info(pair)
            >>> print(f"Maker fee: {info.maker_fee}, Min qty: {info.quantity_min}")
            >>>
            >>> # Batch query for all pairs
            >>> all_pairs = await exchange.get_trading_pair_info(None)
            >>> print(f"XT supports {len(all_pairs)} trading pairs")
        """
        # Batch query: Return cached if available
        if trading_pair is None:
            if self._trading_pairs_cache:
                logger.debug(
                    "Trading pair cache hit (batch query)",
                    count=len(self._trading_pairs_cache),
                    exchange=self.name,
                )
                return list(self._trading_pairs_cache.values())

            # Cache miss - fetch from API
            response = await self._request(
                method="GET",
                path=f"/{self.API_VERSION}/public/symbol",
                params=None,  # No params for batch query
                authenticated=False,
            )

            data = response.json()
            result = self._check_response(data)

            # Handle XT API response format: may return dict with 'symbols' key or direct list
            if isinstance(result, dict):
                # Extract symbols array from dict
                result = result.get("symbols", [])
            
            # Result should be a list for batch query
            if not isinstance(result, list):
                raise ValueError(f"Expected list result for batch query, got {type(result)}")

            # Parse each symbol info to TradingPair
            trading_pairs: list[TradingPair] = []
            failed_symbols: list[str] = []

            for symbol_data in result:
                try:
                    pair_info = self._parse_symbol_info(symbol_data)
                    trading_pairs.append(pair_info)
                except Exception as e:
                    symbol = symbol_data.get("symbol", "unknown")
                    failed_symbols.append(symbol)
                    logger.warning(
                        "Failed to parse trading pair info",
                        symbol=symbol,
                        error=str(e),
                    )

            # Log partial failures if any
            if failed_symbols:
                logger.info(
                    "Batch trading pair query completed with partial failures",
                    total_symbols=len(result),
                    successful=len(trading_pairs),
                    failed=len(failed_symbols),
                    failed_symbols=failed_symbols[:10],  # Log first 10 failures
                )

            return trading_pairs

        # Single pair query: Check caches first
        symbol = self._to_xt_symbol(trading_pair)

        # Check memory cache
        if symbol in self._trading_pairs_cache:
            logger.debug(
                "Trading pair cache hit (memory)",
                symbol=symbol,
                exchange=self.name,
            )
            return self._trading_pairs_cache[symbol]

        # Check LRU cache
        cache_key = f"{self.CACHE_KEY_PREFIX}{symbol}"
        cached = await cache_manager.get_lru(cache_key)
        if cached:
            # Type assertion: cached value should be TradingPair
            if not isinstance(cached, TradingPair):
                logger.warning(
                    "Invalid cached type in LRU cache",
                    symbol=symbol,
                    cached_type=type(cached).__name__,
                    exchange=self.name,
                )
            else:
                logger.debug(
                    "Trading pair cache hit (LRU)",
                    symbol=symbol,
                    exchange=self.name,
                )
                # Update memory cache
                self._trading_pairs_cache[symbol] = cached
                return cached

        # Cache miss - fetch from API
        logger.debug(
            "Trading pair cache miss, fetching from API",
            symbol=symbol,
            exchange=self.name,
        )

        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/public/symbol",
            params={"symbol": symbol},
            authenticated=False,
        )

        data = response.json()
        result = self._check_response(data)

        # Handle XT API response format variations
        # API may return result as list or dict
        if isinstance(result, list):
            if not result:
                raise ValueError(f"Trading pair not found: {symbol}")
            symbol_data = result[0]
        else:
            symbol_data = result

        # Parse symbol info to TradingPair
        pair_info = self._parse_symbol_info(symbol_data)

        # Cache the result
        self._trading_pairs_cache[symbol] = pair_info
        cache_key = f"{self.CACHE_KEY_PREFIX}{symbol}"
        await cache_manager.set_lru(cache_key, pair_info)

        logger.debug(
            "Trading pair info cached",
            symbol=symbol,
            exchange=self.name,
        )

        return pair_info

    async def refresh_trading_pairs(self) -> int:
        """Refresh trading pair cache by fetching latest data from XT exchange.

        Forces a reload of all trading pair information from the exchange,
        updating both in-memory and LRU caches. Useful for ensuring cache
        consistency after exchange updates or when detecting stale data.

        Returns:
            Number of trading pairs loaded and cached

        Raises:
            ValueError: If not connected
            httpx.HTTPStatusError: If API request fails

        Examples:
            >>> await exchange.connect()
            >>> # ... later when cache might be stale
            >>> count = await exchange.refresh_trading_pairs()
            >>> print(f"Refreshed {count} trading pairs")

        Note:
            This method clears existing cache before loading new data to
            ensure consistency. Consider rate limits when calling frequently.
        """
        if not self.is_connected:
            raise ValueError("Exchange not connected. Call connect() first.")

        logger.info("Refreshing trading pair cache", exchange=self.name)

        # Clear existing cache
        self._trading_pairs_cache.clear()

        # Fetch all trading pairs (bypass cache)
        response = await self._request(
            method="GET",
            path=f"/{self.API_VERSION}/public/symbol",
            params=None,
            authenticated=False,
        )

        data = response.json()
        result = self._check_response(data)

        # Handle XT API response format: may return dict with 'symbols' key or direct list
        if isinstance(result, dict):
            result = result.get("symbols", [])
        
        if not isinstance(result, list):
            raise ValueError(f"Expected list result for batch query, got {type(result)}")

        # Parse and cache each trading pair
        cached_count = 0
        failed_symbols: list[str] = []

        for symbol_data in result:
            try:
                pair_info = self._parse_symbol_info(symbol_data)
                symbol = self._to_xt_symbol(pair_info)

                # Cache to memory
                self._trading_pairs_cache[symbol] = pair_info

                # Cache to LRU
                cache_key = f"{self.CACHE_KEY_PREFIX}{symbol}"
                await cache_manager.set_lru(cache_key, pair_info)

                cached_count += 1
            except Exception as e:
                symbol = symbol_data.get("symbol", "unknown")
                failed_symbols.append(symbol)
                logger.warning(
                    "Failed to cache trading pair during refresh",
                    symbol=symbol,
                    error=str(e),
                    exchange=self.name,
                )

        # Log refresh results
        logger.info(
            "Trading pair cache refreshed",
            cached=cached_count,
            failed=len(failed_symbols),
            exchange=self.name,
        )

        if failed_symbols:
            logger.debug(
                "Failed symbols during refresh",
                failed_symbols=failed_symbols[:10],
                exchange=self.name,
            )

        return cached_count

    # Helper methods

    def _check_response(self, data: dict[str, Any]) -> Any:
        """Validate XT API response and extract result.

        Args:
            data: Parsed JSON response from XT API

        Returns:
            The result dict from the API response

        Raises:
            ValueError: If API returned an error or null result

        Note:
            XT API response format:
            - rc=0: success
            - rc≠0: error, check mc (error code) and ma (error messages)
            - result: may be dict, list, or None
        """
        rc = data.get("rc", -1)
        if rc != 0:
            error_code = data.get("mc", "UNKNOWN")
            error_messages = data.get("ma", [])
            error_detail = (
                ", ".join(str(msg) for msg in error_messages) if error_messages else "No details"
            )
            raise ValueError(f"XT API error [rc={rc}]: {error_code} - {error_detail}")

        result = data.get("result")
        if result is None:
            raise ValueError("XT API returned null result")

        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
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

        headers: dict[str, str] = {}
        query_string = ""
        body_string = ""

        if authenticated:
            query_string = self._build_sorted_query(params or {})
            # Serialize JSON with default format (with spaces) to match xt_spot_api.py
            body_string = json.dumps(json_data) if json_data else ""
            headers, _ = self._generate_signature(method, path, query_string, body_string)

        try:
            # For POST/DELETE authenticated requests, use content= to ensure
            # the exact same JSON string used in signature is sent
            if method.upper() in ("POST", "DELETE") and authenticated and body_string:
                logger.debug(
                    "Sending POST/DELETE request",
                    method=method,
                    path=path,
                    content_length=len(body_string),
                    content_bytes_length=len(body_string.encode("utf-8")),
                    body_preview=body_string[:200] if len(body_string) > 200 else body_string,
                    headers_keys=list(headers.keys()),
                    all_headers=headers,
                )

                response = await self._client.request(
                    method,
                    path,
                    params=params,
                    content=body_string.encode("utf-8"),
                    headers=headers,
                )
            else:
                # For GET or non-authenticated requests, use json= parameter
                response = await self._client.request(
                    method,
                    path,
                    params=params,
                    json=json_data,
                    headers=headers if authenticated else None,
                )
            response.raise_for_status()

            # Log response for debugging API format mismatches
            try:
                response_data = response.json()
                logger.debug(
                    "XT API response received",
                    method=method,
                    path=path,
                    response_data=response_data,
                )
            except Exception:
                pass  # Ignore JSON parsing errors for logging

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

    def _parse_ticker_to_price(
        self, ticker_data: dict[str, Any], trading_pair: TradingPair | None = None
    ) -> Price:
        """Parse XT API ticker data to Price object.

        Extracts price information from XT API ticker response and converts
        to internal Price model. Handles both single and batch query responses.

        Args:
            ticker_data: Raw ticker data from XT API (single ticker dict)
                        Expected fields: bp (bid price), ap (ask price),
                        bq (bid quantity), aq (ask quantity)
            trading_pair: Optional trading pair. If None, will be created from
                         ticker symbol using _create_minimal_trading_pair()

        Returns:
            Price object with bid/ask prices and volumes

        Raises:
            ValueError: If ticker data is missing required fields or has invalid prices
            KeyError: If symbol field 's' is missing when trading_pair is None

        Examples:
            >>> ticker_data = {"s": "btc_usdt", "bp": "50000.00", "ap": "50001.00", "bq": "10.5", "aq": "8.3"}
            >>> price = self._parse_ticker_to_price(ticker_data)
            >>> print(price.bid_price)
        """
        # Create trading pair from symbol if not provided (batch query case)
        if trading_pair is None:
            symbol = ticker_data.get("s")
            if not symbol:
                raise ValueError("Ticker data missing symbol field 's'")
            trading_pair = self._create_minimal_trading_pair(symbol)

        # Extract price data from XT API fields
        # XT API /v4/public/ticker/book returns:
        # - bp: bid price (best buy price)
        # - ap: ask price (best sell price)
        # - bq: bid quantity (volume at best bid)
        # - aq: ask quantity (volume at best ask)
        bid_price_raw = ticker_data.get("bp")
        ask_price_raw = ticker_data.get("ap")
        bid_volume_raw = ticker_data.get("bq")
        ask_volume_raw = ticker_data.get("aq")

        # Handle null values (some trading pairs may have null prices)
        if bid_price_raw is None or ask_price_raw is None:
            raise ValueError(
                f"Missing price data for {trading_pair.base_currency}/"
                f"{trading_pair.quote_currency}: bp={bid_price_raw}, ap={ask_price_raw}"
            )

        # Convert to Decimal for precise arithmetic
        bid_price = Decimal(str(bid_price_raw))
        ask_price = Decimal(str(ask_price_raw))
        bid_volume = Decimal(str(bid_volume_raw or "0"))
        ask_volume = Decimal(str(ask_volume_raw or "0"))

        # Validate price data
        if bid_price <= 0 or ask_price <= 0:
            raise ValueError(
                f"Invalid price for {trading_pair.base_currency}/"
                f"{trading_pair.quote_currency}: bid={bid_price}, ask={ask_price}"
            )

        return Price(
            trading_pair=trading_pair,
            bid_price=bid_price,
            ask_price=ask_price,
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            timestamp=datetime.now(tz=datetime.now().astimezone().tzinfo),
            exchange="xt",
        )

    def _create_minimal_trading_pair(self, symbol: str) -> TradingPair:
        """Create minimal TradingPair from XT symbol.

        Creates a TradingPair object with minimal configuration for batch queries.
        Real trading constraints (min/max order size, precision) should be fetched
        from exchange info API for actual trading.

        Args:
            symbol: XT symbol format (e.g., "btc_usdt")

        Returns:
            TradingPair with minimal configuration

        Raises:
            ValueError: If symbol format is invalid

        Examples:
            >>> pair = self._create_minimal_trading_pair("btc_usdt")
            >>> print(f"{pair.base_currency}/{pair.quote_currency}")
            "BTC/USDT"
        """
        base, quote = self._from_xt_symbol(symbol)

        return TradingPair(
            base_currency=base,
            quote_currency=quote,
            exchange="xt",
            # Use conservative defaults for batch queries
            # These should be overridden with actual exchange info for trading
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1000000"),
            price_precision=8,
            quantity_precision=8,
        )

    def _parse_symbol_info(self, symbol_data: dict[str, Any]) -> TradingPair:
        """Parse XT API symbol data to TradingPair object.

        Extracts complete trading pair configuration from XT API `/v4/public/symbol`
        response, including precision, limits, fees, and filters.

        Args:
            symbol_data: Raw symbol data from XT API
                Expected fields:
                - symbol: Trading pair symbol (e.g., "btc_usdt")
                - pricePrecision: Price decimal places
                - quantityPrecision: Quantity decimal places
                - tradeFee: Fee structure {makerFeeRate, takerFeeRate}
                - state: Trading state (ONLINE/OFFLINE/HALT)
                - filters: Trading filters (PRICE_FILTER, LOT_SIZE, etc.)

        Returns:
            TradingPair object with complete configuration

        Raises:
            ValueError: If symbol data is missing required fields
            KeyError: If critical fields are not found

        Examples:
            >>> symbol_data = {
            ...     "symbol": "btc_usdt",
            ...     "pricePrecision": 2,
            ...     "quantityPrecision": 6,
            ...     "tradeFee": {"makerFeeRate": "0.001", "takerFeeRate": "0.001"},
            ...     "state": "ONLINE"
            ... }
            >>> pair = self._parse_symbol_info(symbol_data)
            >>> print(f"Maker fee: {pair.maker_fee}")
        """
        # Extract basic symbol info
        symbol = symbol_data.get("symbol")
        if not symbol:
            raise ValueError("Symbol data missing 'symbol' field")

        base, quote = self._from_xt_symbol(symbol)

        # Extract precision
        price_precision = symbol_data.get("pricePrecision", 8)
        quantity_precision = symbol_data.get("quantityPrecision", 8)

        # Extract fee structure
        trade_fee = symbol_data.get("tradeFee", {})
        maker_fee_str = trade_fee.get("makerFeeRate")
        taker_fee_str = trade_fee.get("takerFeeRate")

        maker_fee = Decimal(str(maker_fee_str)) if maker_fee_str else None
        taker_fee = Decimal(str(taker_fee_str)) if taker_fee_str else None

        # Extract trading state
        trading_state = symbol_data.get("state")

        # Extract filters
        filters = symbol_data.get("filters", [])

        # Parse PRICE_FILTER
        price_filter = next((f for f in filters if f.get("filter") == "PRICE_FILTER"), None)
        price_min = None
        price_max = None
        price_step = None
        if price_filter:
            price_min = (
                Decimal(str(price_filter["minPrice"])) if price_filter.get("minPrice") else None
            )
            price_max = (
                Decimal(str(price_filter["maxPrice"])) if price_filter.get("maxPrice") else None
            )
            price_step = (
                Decimal(str(price_filter["tickSize"])) if price_filter.get("tickSize") else None
            )

        # Parse LOT_SIZE filter
        lot_size_filter = next((f for f in filters if f.get("filter") == "LOT_SIZE"), None)
        quantity_min = None
        quantity_max = None
        quantity_step = None
        min_order_size = Decimal("0.001")  # Default
        max_order_size = Decimal("1000000")  # Default

        if lot_size_filter:
            quantity_min = (
                Decimal(str(lot_size_filter["minQty"])) if lot_size_filter.get("minQty") else None
            )
            quantity_max = (
                Decimal(str(lot_size_filter["maxQty"])) if lot_size_filter.get("maxQty") else None
            )
            quantity_step = (
                Decimal(str(lot_size_filter["stepSize"]))
                if lot_size_filter.get("stepSize")
                else None
            )

            # Use quantity_min as min_order_size if available
            if quantity_min:
                min_order_size = quantity_min
            if quantity_max:
                max_order_size = quantity_max

        # Parse MIN_NOTIONAL filter
        min_notional_filter = next((f for f in filters if f.get("filter") == "MIN_NOTIONAL"), None)
        min_notional = None
        if min_notional_filter:
            min_notional = (
                Decimal(str(min_notional_filter["minNotional"]))
                if min_notional_filter.get("minNotional")
                else None
            )

        # Create TradingPair with complete configuration
        return TradingPair(
            base_currency=base,
            quote_currency=quote,
            exchange="xt",
            # Basic constraints
            min_order_size=min_order_size,
            max_order_size=max_order_size,
            price_precision=price_precision,
            quantity_precision=quantity_precision,
            # Fee structure
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            # Trading constraints
            min_notional=min_notional,
            trading_state=trading_state,
            # Price filter
            price_min=price_min,
            price_max=price_max,
            price_step=price_step,
            # Quantity filter
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            quantity_step=quantity_step,
        )

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
        except ValueError as e:
            raise ValueError(f"Invalid XT symbol format: {symbol}") from e

    def _generate_signature(
        self,
        method: str,
        path: str,
        query: str = "",
        body: str = "",
    ) -> tuple[dict[str, str], str]:
        """Generate XT API HMAC-SHA256 signature and headers.

        XT uses different signature methods for different HTTP methods:
        - GET: lowercase signature, X-based format
        - POST/DELETE: uppercase signature, sorted headers format

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

        if method.upper() == "GET":
            # GET requests use X-based signature (lowercase)
            signature = self._generate_get_signature(
                self.api_key, self.RECV_WINDOW, timestamp_ms, method, path, query, body
            )
        else:
            # POST/DELETE requests use sorted headers signature (uppercase)
            signature = self._generate_post_signature(
                self.api_key, self.RECV_WINDOW, timestamp_ms, method, path, query, body
            )

        # Build complete headers (convert integers to strings for HTTP)
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

    def _generate_get_signature(
        self,
        api_key: str,
        recv_window: int,
        timestamp: int,
        method: str,
        path: str,
        query: str,
        body: str,
    ) -> str:
        """Generate signature for GET requests (lowercase hexdigest).

        Args:
            api_key: XT API key
            recv_window: Receive window in milliseconds (integer)
            timestamp: Timestamp in milliseconds (integer)
            method: HTTP method
            path: API endpoint path
            query: URL query string
            body: Request body (usually empty for GET)

        Returns:
            Lowercase hex signature
        """
        # Build X string with integer values (X is XT API standard terminology)
        X = (  # noqa: N806
            f"validate-algorithms=HmacSHA256"
            f"&validate-appkey={api_key}"
            f"&validate-recvwindow={recv_window}"
            f"&validate-timestamp={timestamp}"
        )

        # Build signature data
        sig_data = f"{X}#{method}#{path}"
        if query:
            sig_data += f"#{query}"
        if body:
            sig_data += f"#{body}"

        # Generate lowercase signature
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            sig_data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        logger.debug(
            "Generated GET signature",
            method=method,
            path=path,
            X=X,
            sig_data=sig_data,
            signature=signature[:8] + "..." + signature[-8:],
        )

        return signature

    def _generate_post_signature(
        self,
        api_key: str,
        recv_window: int,
        timestamp: int,
        method: str,
        path: str,
        query: str,
        body: str,
    ) -> str:
        """Generate signature for POST/DELETE requests (uppercase hexdigest).

        Follows xt_spot_api.py create_sign() logic exactly:
        - Build headers dict and sort by key (line 32)
        - Build signature string: {sorted_headers}#{method}#{path}[#query][#body]
        - Return uppercase hexdigest (line 36-37)

        Args:
            api_key: XT API key
            recv_window: Receive window in milliseconds (integer)
            timestamp: Timestamp in milliseconds (integer)
            method: HTTP method
            path: API endpoint path
            query: URL query string
            body: Request body (JSON string)

        Returns:
            Uppercase hex signature
        """
        # Create headers dict (matching xt_spot_api.py line 286-291)
        headers = {
            "validate-algorithms": "HmacSHA256",
            "validate-appkey": api_key,
            "validate-recvwindow": str(recv_window),
            "validate-timestamp": str(timestamp),
        }

        # Sort headers by key and build x string (matching line 32)
        x = "&".join([f"{key}={headers[key]}" for key in sorted(headers)])

        # Build y string with non-empty components (matching line 31)
        components = [i for i in [method, path, query, body] if i]
        y = "#" + "#".join(components)

        # Combine x and y
        sig_data = f"{x}{y}"

        # Generate uppercase signature
        signature = (
            hmac.new(
                self.api_secret.encode("utf-8"),
                sig_data.encode("utf-8"),
                hashlib.sha256,
            )
            .hexdigest()
            .upper()
        )

        logger.debug(
            "Generated POST/DELETE signature",
            method=method,
            path=path,
            x=x,
            y=y,
            sig_data=sig_data,
            signature=signature[:8] + "..." + signature[-8:],
        )

        return signature

    def _build_sorted_query(self, params: dict[str, Any]) -> str:
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
