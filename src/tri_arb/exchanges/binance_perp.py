"""Binance Perpetual Futures exchange adapter implementation.

Provides async interface to Binance Futures REST API v1/v2.
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
from tri_arb.core.models import Order, OrderBook, OrderSide, OrderStatus, Price, Trade, TradingPair
from tri_arb.exchanges.base import BaseExchange


logger = get_logger(__name__)


class BinancePerpExchange(BaseExchange):
    """Binance Perpetual Futures exchange adapter implementation.

    Provides async interface to Binance Futures REST API.

    Attributes:
        api_key: Binance API key for authentication
        api_secret: Binance API secret for HMAC-SHA256 signature
    """

    BASE_URL: str = "https://fapi.binance.com"
    WS_URL: str = "wss://fstream.binance.com"

    def __init__(
        self,
        name: str = "binance_perp",
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        """Initialize Binance Perpetual Futures exchange adapter.

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
            "BinancePerpExchange initialized",
            has_api_key=bool(api_key),
            has_api_secret=bool(api_secret),
        )
    def get_name(self) -> str:
        return "binance_perp"
    async def connect(self) -> None:
        """Establish connection to Binance Futures exchange."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        
        self.is_connected = True
        logger.info("Connected to Binance Perpetual Futures exchange", exchange=self.name)

    async def disconnect(self) -> None:
        """Close connection to Binance Futures exchange."""
        if self._client:
            await self._client.aclose()
            self._client = None
        
        self.is_connected = False
        logger.info("Disconnected from Binance Perpetual Futures exchange", exchange=self.name)

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
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()


    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> httpx.Response:
        """Make HTTP request to Binance Futures API.

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
            "Making Binance Futures API request",
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
        raise NotImplementedError("Trading pair info query not yet implemented for Binance Futures")

    async def get_balance(self) -> dict[str, dict[str, Any]]:
        """Get account balances for all assets.

        Returns:
            Dictionary mapping currency code to balance details:
            {
                "USDT": {
                    "available": Decimal("1000.0"),
                    "frozen": Decimal("0.0"),
                    "total": Decimal("1000.0")
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
            path="/fapi/v2/balance",
            authenticated=True,
        )

        data = response.json()
        
        logger.debug(
            "Raw Binance Futures balance response",
            response_type=type(data).__name__,
            is_list=isinstance(data, list),
        )

        balances: dict[str, dict[str, Any]] = {}
        
        # Binance Futures response format: [{asset: "USDT", balance: "1000.0", crossUnPnl: "0.0", ...}, ...]
        if isinstance(data, list):
            for balance_item in data:
                asset = balance_item.get("asset", "")
                if not asset:
                    continue
                    
                total_balance = Decimal(balance_item.get("balance", "0"))
                available_balance = Decimal(balance_item.get("availableBalance", "0"))
                
                # Frozen = Total - Available
                frozen = max(Decimal("0"), total_balance - available_balance)
                
                # Only include assets with non-zero balances
                if total_balance > 0:
                    balances[asset] = {
                        "available": available_balance,
                        "frozen": frozen,
                        "total": total_balance
                    }
        else:
            # Handle unexpected response format
            logger.error(
                "Unexpected Binance Futures balance response format",
                response_type=type(data).__name__,
                data=str(data)[:500]
            )
            raise ValueError(f"Unexpected response format from Binance Futures API: {type(data).__name__}")
        
        logger.info(
            "Binance perpetual futures balances retrieved",
            currencies_count=len(balances),
            currencies=list(balances.keys()) if balances else ["No balances with non-zero amounts"]
        )

        return balances

    async def get_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get position risk information for futures contracts.

        Query position risk information using Binance Futures API v2/positionRisk endpoint.
        This method returns positions with leverage and margin type information.

        Args:
            symbol: Optional trading pair symbol (e.g., "BTCUSDT"). 
                   If None, returns all positions.

        Returns:
            List of position information dictionaries with the following structure:
            [
                {
                    "symbol": "BTCUSDT",           # 交易对
                    "positionSide": "BOTH",        # 持仓方向 (BOTH/LONG/SHORT)
                    "positionAmt": "0.001",        # 持仓数量（正数多，负数空）
                    "entryPrice": "50000.00",      # 开仓均价
                    "breakEvenPrice": "50001.00",  # 盈亏平衡价
                    "markPrice": "51000.00",       # 标记价格
                    "unRealizedProfit": "1.00",    # 持仓未实现盈亏
                    "liquidationPrice": "45000.0", # 参考强平价格
                    "leverage": "10",              # 当前杠杆倍数
                    "marginType": "cross",         # 逐仓模式(isolated)或全仓模式(cross)
                    "isolatedMargin": "0.00",      # 逐仓保证金
                    "isAutoAddMargin": "false",    # 是否自动追加保证金
                    "notional": "51.00",           # 名义价值
                    "isolatedWallet": "0",         # 逐仓钱包余额
                    "maxNotionalValue": "20000000",# 当前杠杆允许的名义价值上限
                    "updateTime": 1625474304765    # 更新时间
                },
                ...
            ]

        Raises:
            ValueError: If not connected or missing credentials
            httpx.HTTPStatusError: If API request fails

        Note:
            建议配合账户推送信息 ACCOUNT_UPDATE 使用，以满足及时性和准确性需求。
        """
        self._require_credentials()

        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol

        response = await self._request(
            method="GET",
            path="/fapi/v2/positionRisk",
            params=params,
            authenticated=True,
        )

        data = response.json()
        
        logger.debug(
            "Raw Binance Futures position response",
            response_type=type(data).__name__,
            is_list=isinstance(data, list),
            positions_count=len(data) if isinstance(data, list) else 0,
        )

        if not isinstance(data, list):
            logger.error(
                "Unexpected Binance Futures position response format",
                response_type=type(data).__name__,
                data=str(data)[:500]
            )
            raise ValueError(f"Unexpected response format from Binance Futures API: {type(data).__name__}")

        # Convert numeric string fields to Decimal for precision
        positions = []
        for pos in data:
            position_amt = Decimal(pos.get("positionAmt", "0"))
            
            # 只返回有实际持仓的数据（过滤掉空持仓）
            if position_amt != Decimal("0"):
                position = {
                    "symbol": pos.get("symbol", ""),
                    "positionSide": pos.get("positionSide", ""),
                    "positionAmt": position_amt,
                    "entryPrice": Decimal(pos.get("entryPrice", "0")),
                    "breakEvenPrice": Decimal(pos.get("breakEvenPrice", "0")),
                    "markPrice": Decimal(pos.get("markPrice", "0")),
                    "unRealizedProfit": Decimal(pos.get("unRealizedProfit", "0")),
                    "liquidationPrice": Decimal(pos.get("liquidationPrice", "0")),
                    "leverage": pos.get("leverage", "1"),
                    "marginType": pos.get("marginType", "cross"),
                    "isolatedMargin": Decimal(pos.get("isolatedMargin", "0")),
                    "isAutoAddMargin": pos.get("isAutoAddMargin", "false"),
                    "notional": Decimal(pos.get("notional", "0")),
                    "isolatedWallet": Decimal(pos.get("isolatedWallet", "0")),
                    "maxNotionalValue": Decimal(pos.get("maxNotionalValue", "0")),
                    "updateTime": pos.get("updateTime", 0),
                }
                positions.append(position)
        
        if symbol:
            logger.info(
                "Binance perpetual futures position retrieved",
                symbol=symbol,
                positions_count=len(positions),
            )
        else:
            logger.info(
                "Binance perpetual futures positions retrieved",
                positions_count=len(positions),
                symbols=[p["symbol"] for p in positions] if positions else [],
            )

        return positions

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get current open orders for futures contracts.

        Query current open orders using Binance Futures API v1/openOrders endpoint.

        Args:
            symbol: Optional trading pair symbol (e.g., "BTCUSDT"). 
                   If None, returns all open orders (weight: 40).
                   If provided, returns orders for specific symbol (weight: 1).

        Returns:
            List of open order dictionaries with the following structure:
            [
                {
                    "orderId": 1917641,                    # 系统订单号
                    "symbol": "BTCUSDT",                   # 交易对
                    "status": "NEW",                       # 订单状态
                    "clientOrderId": "abc",                # 用户自定义订单号
                    "price": "9300",                       # 委托价格
                    "avgPrice": "0.00000",                 # 平均成交价
                    "origQty": "0.40",                     # 原始委托数量
                    "executedQty": "0",                    # 成交量
                    "cumQuote": "0",                       # 成交金额
                    "timeInForce": "GTC",                  # 有效方法
                    "type": "LIMIT",                       # 订单类型
                    "reduceOnly": false,                   # 是否仅减仓
                    "closePosition": false,                # 是否条件全平仓
                    "side": "BUY",                         # 买卖方向
                    "positionSide": "LONG",                # 持仓方向
                    "stopPrice": "0",                      # 触发价
                    "workingType": "CONTRACT_PRICE",       # 条件价格触发类型
                    "priceProtect": false,                 # 是否开启条件单触发保护
                    "origType": "LIMIT",                   # 触发前订单类型
                    "priceMatch": "NONE",                  # 盘口价格下单模式
                    "selfTradePreventionMode": "NONE",     # 订单自成交保护模式
                    "goodTillDate": 0,                     # GTD订单自动取消时间
                    "time": 1579276756075,                 # 订单时间
                    "updateTime": 1579276756075,           # 更新时间
                },
                ...
            ]

        Raises:
            ValueError: If not connected or missing credentials
            httpx.HTTPStatusError: If API request fails

        Note:
            不带symbol参数会返回所有交易对的挂单，权重较高(40)，请谨慎使用。
        """
        self._require_credentials()

        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol

        response = await self._request(
            method="GET",
            path="/fapi/v1/openOrders",
            params=params,
            authenticated=True,
        )

        data = response.json()
        
        logger.debug(
            "Raw Binance Futures open orders response",
            response_type=type(data).__name__,
            is_list=isinstance(data, list),
            orders_count=len(data) if isinstance(data, list) else 0,
        )

        if not isinstance(data, list):
            logger.error(
                "Unexpected Binance Futures open orders response format",
                response_type=type(data).__name__,
                data=str(data)[:500]
            )
            raise ValueError(f"Unexpected response format from Binance Futures API: {type(data).__name__}")

        # Convert numeric string fields to Decimal for precision
        orders = []
        for order in data:
            formatted_order = {
                "orderId": order.get("orderId", 0),
                "symbol": order.get("symbol", ""),
                "status": order.get("status", ""),
                "clientOrderId": order.get("clientOrderId", ""),
                "price": Decimal(order.get("price", "0")),
                "avgPrice": Decimal(order.get("avgPrice", "0")),
                "origQty": Decimal(order.get("origQty", "0")),
                "executedQty": Decimal(order.get("executedQty", "0")),
                "cumQuote": Decimal(order.get("cumQuote", "0")),
                "timeInForce": order.get("timeInForce", ""),
                "type": order.get("type", ""),
                "reduceOnly": order.get("reduceOnly", False),
                "closePosition": order.get("closePosition", False),
                "side": order.get("side", ""),
                "positionSide": order.get("positionSide", ""),
                "stopPrice": Decimal(order.get("stopPrice", "0")),
                "workingType": order.get("workingType", ""),
                "priceProtect": order.get("priceProtect", False),
                "origType": order.get("origType", ""),
                "priceMatch": order.get("priceMatch", "NONE"),
                "selfTradePreventionMode": order.get("selfTradePreventionMode", "NONE"),
                "goodTillDate": order.get("goodTillDate", 0),
                "time": order.get("time", 0),
                "updateTime": order.get("updateTime", 0),
            }
            
            # 处理跟踪止损订单的特殊字段
            if order.get("activatePrice"):
                formatted_order["activatePrice"] = Decimal(order.get("activatePrice", "0"))
            if order.get("priceRate"):
                formatted_order["priceRate"] = Decimal(order.get("priceRate", "0"))
            
            orders.append(formatted_order)
        
        if symbol:
            logger.info(
                "Binance perpetual futures open orders retrieved",
                symbol=symbol,
                orders_count=len(orders),
            )
        else:
            logger.info(
                "Binance perpetual futures open orders retrieved",
                orders_count=len(orders),
                symbols=[o["symbol"] for o in orders] if orders else [],
            )

        return orders

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
            path="/fapi/v1/ticker/bookTicker",
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
            "Binance perpetual futures ticker retrieved",
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
        
        # Binance Futures supports depth levels: 5, 10, 20, 50, 100, 500, 1000
        limit = min(depth, 1000)
        
        response = await self._request(
            method="GET",
            path="/fapi/v1/depth",
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
            "Binance perpetual futures orderbook retrieved",
            symbol=symbol,
            bids_count=len(bids),
            asks_count=len(asks),
        )

        return orderbook

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str | Decimal,
        price: str | Decimal | None = None,
        position_side: str | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Place order for Binance futures.

        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
            side: Order side - "BUY" or "SELL"
            order_type: Order type - "LIMIT", "MARKET", "STOP", "TAKE_PROFIT", etc.
            quantity: Order quantity
            price: Order price (required for LIMIT orders)
            position_side: Position side - "LONG", "SHORT", or "BOTH" (default: "BOTH")
            time_in_force: Time in force - "GTC", "IOC", "FOK", "GTX"
            reduce_only: If true, order will only reduce position
            client_order_id: Client order ID (optional)

        Returns:
            Order response dictionary with following structure:
            {
                "orderId": 123456789,              # 系统订单号
                "symbol": "BTCUSDT",               # 交易对
                "status": "NEW",                   # 订单状态
                "clientOrderId": "custom_id",      # 用户自定义订单号
                "price": "50000",                  # 委托价格
                "avgPrice": "0",                   # 平均成交价
                "origQty": "0.001",                # 原始委托数量
                "executedQty": "0",                # 成交量
                "cumQuote": "0",                   # 成交金额
                "timeInForce": "GTC",              # 有效方法
                "type": "LIMIT",                   # 订单类型
                "reduceOnly": false,               # 是否仅减仓
                "side": "BUY",                     # 买卖方向
                "positionSide": "LONG",            # 持仓方向
                "updateTime": 1617788478000        # 更新时间
            }

        Raises:
            ValueError: If not connected or missing credentials or invalid parameters
            httpx.HTTPStatusError: If API request fails
        """
        self._require_credentials()

        # 构造请求参数
        order_params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
        }

        # 持仓方向
        if position_side:
            order_params["positionSide"] = position_side.upper()
        else:
            order_params["positionSide"] = "BOTH"  # 单向持仓模式

        # 限价单需要价格和时间有效性
        if order_type.upper() in ["LIMIT", "STOP", "TAKE_PROFIT"]:
            if price is None:
                raise ValueError(f"Price is required for {order_type} orders")
            order_params["price"] = str(price)
            order_params["timeInForce"] = time_in_force

        # 仅减仓
        if reduce_only:
            order_params["reduceOnly"] = "true"

        # 客户自定义订单ID
        if client_order_id:
            order_params["newClientOrderId"] = client_order_id

        response = await self._request(
            method="POST",
            path="/fapi/v1/order",
            params=order_params,
            authenticated=True,
        )

        data = response.json()
        
        logger.info(
            "Binance perpetual futures order placed",
            symbol=symbol,
            side=side,
            order_type=order_type,
            order_id=data.get("orderId", ""),
            status=data.get("status", ""),
        )

        return data

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order (not implemented yet).

        Args:
            order_id: Exchange order ID to cancel

        Returns:
            True if cancelled successfully

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError("Order cancellation not yet implemented for Binance Futures")

    async def get_order_status(self, order_id: str) -> Order:
        """Get order status (not implemented yet).

        Args:
            order_id: Exchange order ID to query

        Returns:
            Order with current status

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError("Order status query not yet implemented for Binance Futures")

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
        raise NotImplementedError("Trade history not yet implemented for Binance Futures")

    async def subscribe_ticker(
        self, trading_pair: TradingPair
    ) -> AsyncIterator[Price]:
        """Subscribe to ticker updates (not implemented yet).

        Args:
            trading_pair: Trading pair to subscribe to

        Yields:
            Price updates

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError("Ticker subscription not yet implemented for Binance Futures")
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
        raise NotImplementedError("Order book subscription not yet implemented for Binance Futures")
        yield  # Make this a generator
