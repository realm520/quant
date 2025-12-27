"""OKX Perpetual Futures exchange adapter implementation.

Provides async interface to OKX Futures REST API v5.
"""

import base64
import decimal
import hashlib
import hmac
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

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


def _safe_decimal(value: Any, default: str = "0") -> Decimal:
    """Safely convert value to Decimal.

    Args:
        value: Value to convert
        default: Default value if conversion fails

    Returns:
        Decimal value
    """
    if value is None or value == "" or value == "null":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (ValueError, decimal.InvalidOperation):
        logger.warning(
            f"Failed to convert to Decimal: {value}, using default: {default}"
        )
        return Decimal(default)


class OKXPerpExchange(BaseExchange):
    """OKX Perpetual Futures exchange adapter implementation.

    Provides async interface to OKX Futures REST API v5.

    Attributes:
        api_key: OKX API key for authentication
        api_secret: OKX API secret for HMAC-SHA256 signature
        passphrase: OKX API passphrase
    """

    BASE_URL: str = "https://www.okx.com"
    WS_URL: str = "wss://ws.okx.com:8443/ws/v5/public"

    def __init__(
        self,
        name: str = "okx_perp",
        api_key: str = "",
        api_secret: str = "",
        passphrase: str = "",
    ) -> None:
        """Initialize OKX Perpetual Futures exchange adapter.

        Args:
            name: Exchange name identifier
            api_key: OKX API key
            api_secret: OKX API secret
            passphrase: OKX API passphrase
        """
        super().__init__(name)
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self._client: httpx.AsyncClient | None = None

        logger.info(
            "OKXPerpExchange initialized",
            has_api_key=bool(api_key),
            has_api_secret=bool(api_secret),
            has_passphrase=bool(passphrase),
        )

    def get_name(self) -> str:
        """Get the name of the exchange."""
        return "okx_perp"

    async def connect(self) -> None:
        """Establish connection to OKX Futures exchange."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )

        self.is_connected = True
        logger.info("Connected to OKX Perpetual Futures exchange", exchange=self.name)

    async def disconnect(self) -> None:
        """Close connection to OKX Futures exchange."""
        if self._client:
            await self._client.aclose()
            self._client = None

        self.is_connected = False
        logger.info(
            "Disconnected from OKX Perpetual Futures exchange", exchange=self.name
        )

    def _require_credentials(self) -> None:
        """Check if API credentials are available.

        Raises:
            ValueError: If API key, secret or passphrase is missing
        """
        if not self.api_key or not self.api_secret or not self.passphrase:
            raise ValueError(
                "Trading operations require API credentials. "
                "Please set OKX_API_KEY, OKX_API_SECRET and OKX_PASSPHRASE environment variables."
            )

    def _generate_signature(
        self, timestamp: str, method: str, request_path: str, body: str = ""
    ) -> str:
        """Generate OKX API signature.

        Args:
            timestamp: ISO timestamp
            method: HTTP method (GET, POST, etc.)
            request_path: API endpoint path with query params
            body: Request body (for POST requests)

        Returns:
            Base64 encoded signature string
        """
        message = timestamp + method + request_path + body
        mac = hmac.new(
            self.api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> httpx.Response:
        """Make HTTP request to OKX API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Query parameters
            body: Request body (for POST requests)
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
        headers = {
            "Content-Type": "application/json",
        }

        if authenticated:
            self._require_credentials()

            # Generate timestamp
            timestamp = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

            # Build request path with query params
            request_path = path
            if params:
                query_string = "&".join([f"{k}={v}" for k, v in params.items()])
                request_path = f"{path}?{query_string}"

            # Generate signature
            body_str = ""
            if body:
                import json

                body_str = json.dumps(body)

            signature = self._generate_signature(
                timestamp, method, request_path, body_str
            )

            # Add authentication headers
            headers["OK-ACCESS-KEY"] = self.api_key
            headers["OK-ACCESS-SIGN"] = signature
            headers["OK-ACCESS-TIMESTAMP"] = timestamp
            headers["OK-ACCESS-PASSPHRASE"] = self.passphrase

        logger.debug(
            "Making OKX API request",
            method=method,
            path=path,
            authenticated=authenticated,
        )

        response = await self._client.request(
            method=method,
            url=url,
            params=params,
            json=body if body else None,
            headers=headers,
        )

        # 记录响应信息（调试用）
        logger.info(
            "OKX API response",
            status_code=response.status_code,
            url=str(response.url),
            response_length=len(response.text) if response.text else 0,
        )

        # 如果有错误，记录详细信息
        if response.status_code != 200:
            logger.error(
                "OKX API error",
                status_code=response.status_code,
                response_body=response.text[:500],
                request_headers={
                    k: v for k, v in headers.items() if k != "OK-ACCESS-SIGN"
                },
            )

        response.raise_for_status()
        return response

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
            path="/api/v5/account/balance",
            authenticated=True,
        )

        data = response.json()
        logger.debug(
            "Raw OKX balance response",
            code=data.get("code"),
            msg=data.get("msg"),
        )

        # Check for API error
        if data.get("code") != "0":
            raise ValueError(f"OKX API error: {data.get('msg')}")

        balances: dict[str, dict[str, Any]] = {}

        # OKX response format: {"code":"0","msg":"","data":[{"details":[...]}]}
        if data.get("data") and isinstance(data["data"], list):
            for account_data in data["data"]:
                details = account_data.get("details", [])
                for balance_item in details:
                    currency = balance_item.get("ccy", "")
                    if not currency:
                        continue

                    # OKX provides: availEq (available equity), frozenBal (frozen), eq (total equity)
                    available = _safe_decimal(balance_item.get("availEq", "0"))
                    frozen = _safe_decimal(balance_item.get("frozenBal", "0"))
                    total = _safe_decimal(balance_item.get("eq", "0"))

                    # Only include assets with non-zero balances
                    if total > 0:
                        balances[currency] = {
                            "available": available,
                            "frozen": frozen,
                            "total": total,
                        }

        logger.info(
            "OKX perpetual futures balances retrieved",
            currencies_count=len(balances),
            currencies=list(balances.keys()) if balances else ["No balances"],
        )

        return balances

    async def get_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get position information for futures contracts.

        Query position information using OKX API v5/account/positions.

        Args:
            symbol: Optional trading pair symbol (e.g., "BTC-USDT-SWAP").
                   If None, returns all positions.

        Returns:
            List of position information dictionaries
        """
        self._require_credentials()

        params: dict[str, Any] = {"instType": "SWAP"}  # SWAP for perpetual futures
        if symbol:
            params["instId"] = symbol

        response = await self._request(
            method="GET",
            path="/api/v5/account/positions",
            params=params,
            authenticated=True,
        )

        data = response.json()

        logger.debug(
            "Raw OKX positions response",
            code=data.get("code"),
            msg=data.get("msg"),
        )

        # Check for API error
        if data.get("code") != "0":
            raise ValueError(f"OKX API error: {data.get('msg')}")

        positions = []

        if data.get("data") and isinstance(data["data"], list):
            for pos in data["data"]:
                # OKX返回的持仓数量，过滤掉空持仓
                pos_amt = _safe_decimal(pos.get("pos", "0"))
                if pos_amt == Decimal("0"):
                    continue

                position = {
                    "instId": pos.get("instId", ""),  # 产品ID，如 BTC-USDT-SWAP
                    "posId": pos.get("posId", ""),  # 持仓ID
                    "posSide": pos.get("posSide", ""),  # 持仓方向: long/short/net
                    "pos": _safe_decimal(pos.get("pos", "0")),  # 持仓数量
                    "availPos": _safe_decimal(pos.get("availPos", "0")),  # 可平仓数量
                    "avgPx": _safe_decimal(pos.get("avgPx", "0")),  # 开仓均价
                    "markPx": _safe_decimal(pos.get("markPx", "0")),  # 最新标记价格
                    "upl": _safe_decimal(pos.get("upl", "0")),  # 未实现收益
                    "uplRatio": _safe_decimal(pos.get("uplRatio", "0")),  # 未实现收益率
                    "lever": pos.get("lever", "0"),  # 杠杆倍数
                    "liqPx": _safe_decimal(pos.get("liqPx", "0")),  # 预估强平价
                    "imr": _safe_decimal(pos.get("imr", "0")),  # 初始保证金
                    "margin": _safe_decimal(pos.get("margin", "0")),  # 保证金余额
                    "mgnRatio": _safe_decimal(pos.get("mgnRatio", "0")),  # 保证金率
                    "mgnMode": pos.get("mgnMode", ""),  # 保证金模式: cross/isolated
                    "notionalUsd": _safe_decimal(
                        pos.get("notionalUsd", "0")
                    ),  # 持仓名义价值(USD)
                    "uTime": pos.get("uTime", ""),  # 更新时间
                    "cTime": pos.get("cTime", ""),  # 创建时间
                }
                positions.append(position)

        if symbol:
            logger.info(
                "OKX perpetual futures position retrieved",
                symbol=symbol,
                positions_count=len(positions),
            )
        else:
            logger.info(
                "OKX perpetual futures positions retrieved",
                positions_count=len(positions),
                symbols=[p["instId"] for p in positions] if positions else [],
            )

        return positions

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get current open orders for futures contracts.

        Query current open orders using OKX API v5/trade/orders-pending.

        Args:
            symbol: Optional trading pair symbol (e.g., "BTC-USDT-SWAP").
                   If None, returns all open orders.

        Returns:
            List of open order dictionaries
        """
        self._require_credentials()

        params: dict[str, Any] = {"instType": "SWAP"}  # SWAP for perpetual futures
        if symbol:
            params["instId"] = symbol

        response = await self._request(
            method="GET",
            path="/api/v5/trade/orders-pending",
            params=params,
            authenticated=True,
        )

        data = response.json()

        logger.debug(
            "Raw OKX open orders response",
            code=data.get("code"),
            msg=data.get("msg"),
        )

        # Check for API error
        if data.get("code") != "0":
            raise ValueError(f"OKX API error: {data.get('msg')}")

        orders = []

        if data.get("data") and isinstance(data["data"], list):
            for order in data["data"]:
                formatted_order = {
                    "instId": order.get("instId", ""),  # 产品ID
                    "ordId": order.get("ordId", ""),  # 订单ID
                    "clOrdId": order.get("clOrdId", ""),  # 客户自定义订单ID
                    "ordType": order.get(
                        "ordType", ""
                    ),  # 订单类型: limit/market/post_only等
                    "side": order.get("side", ""),  # 订单方向: buy/sell
                    "posSide": order.get("posSide", ""),  # 持仓方向: long/short/net
                    "px": _safe_decimal(order.get("px", "0")),  # 委托价格
                    "sz": _safe_decimal(order.get("sz", "0")),  # 委托数量
                    "avgPx": _safe_decimal(order.get("avgPx", "0")),  # 成交均价
                    "accFillSz": _safe_decimal(
                        order.get("accFillSz", "0")
                    ),  # 累计成交数量
                    "state": order.get(
                        "state", ""
                    ),  # 订单状态: live/partially_filled等
                    "lever": order.get("lever", "0"),  # 杠杆倍数
                    "tpTriggerPx": (
                        _safe_decimal(order.get("tpTriggerPx", "0"))
                        if order.get("tpTriggerPx")
                        else None
                    ),  # 止盈触发价
                    "slTriggerPx": (
                        _safe_decimal(order.get("slTriggerPx", "0"))
                        if order.get("slTriggerPx")
                        else None
                    ),  # 止损触发价
                    "fee": _safe_decimal(order.get("fee", "0")),  # 手续费
                    "rebate": _safe_decimal(order.get("rebate", "0")),  # 返佣
                    "cTime": order.get("cTime", ""),  # 创建时间
                    "uTime": order.get("uTime", ""),  # 更新时间
                }
                orders.append(formatted_order)

        if symbol:
            logger.info(
                "OKX perpetual futures open orders retrieved",
                symbol=symbol,
                orders_count=len(orders),
            )
        else:
            logger.info(
                "OKX perpetual futures open orders retrieved",
                orders_count=len(orders),
                symbols=[o["instId"] for o in orders] if orders else [],
            )

        return orders

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
            "Trading pair info query not yet implemented for OKX Futures"
        )

    async def get_ticker(self, trading_pair: TradingPair) -> Price:
        """Get current ticker price.

        Args:
            trading_pair: Trading pair to get ticker for

        Returns:
            Current price information

        Raises:
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError("Ticker query not yet implemented for OKX Futures")

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
            NotImplementedError: This method is not yet implemented
        """
        raise NotImplementedError(
            "Order book query not yet implemented for OKX Futures"
        )

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str | Decimal,
        price: str | Decimal | None = None,
        position_side: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Place order for OKX futures.

        Args:
            symbol: Trading pair symbol (e.g., "BTC-USDT-SWAP")
            side: Order side - "buy" or "sell"
            order_type: Order type - "limit", "market", "post_only", etc.
            quantity: Order quantity
            price: Order price (required for limit orders)
            position_side: Position side - "long", "short", or "net" (default: "net")
            client_order_id: Client order ID (optional)

        Returns:
            Order response dictionary with following structure:
            {
                "ordId": "123456789",           # 订单ID
                "clOrdId": "custom_id",         # 客户自定义ID
                "sCode": "0",                   # 事件执行结果code
                "sMsg": "",                     # 事件执行失败时的msg
            }

        Raises:
            ValueError: If not connected or missing credentials or invalid parameters
            httpx.HTTPStatusError: If API request fails
        """
        self._require_credentials()

        # 构造请求body
        order_data: dict[str, Any] = {
            "instId": symbol,
            "tdMode": "cross",  # 交易模式: cash(非保证金), cross(全仓), isolated(逐仓)
            "side": side.lower(),  # buy/sell
            "ordType": order_type.lower(),  # limit/market/post_only等
            "sz": str(quantity),  # 数量
        }

        # 持仓方向（双向持仓模式）
        if position_side:
            order_data["posSide"] = position_side.lower()  # long/short
        else:
            order_data["posSide"] = "net"  # 单向持仓

        # 限价单需要价格
        if order_type.lower() in ["limit", "post_only"]:
            if price is None:
                raise ValueError(f"Price is required for {order_type} orders")
            order_data["px"] = str(price)

        # 客户自定义订单ID
        if client_order_id:
            order_data["clOrdId"] = client_order_id

        response = await self._request(
            method="POST",
            path="/api/v5/trade/order",
            body=order_data,
            authenticated=True,
        )

        data = response.json()

        logger.debug(
            "Raw OKX place order response",
            code=data.get("code"),
            msg=data.get("msg"),
        )

        # Check for API error
        if data.get("code") != "0":
            raise ValueError(f"OKX API error: {data.get('msg')}")

        if (
            not data.get("data")
            or not isinstance(data["data"], list)
            or len(data["data"]) == 0
        ):
            raise ValueError("OKX API returned empty order data")

        order_result = data["data"][0]

        logger.info(
            "OKX perpetual futures order placed",
            symbol=symbol,
            side=side,
            order_type=order_type,
            order_id=order_result.get("ordId", ""),
            s_code=order_result.get("sCode", ""),
        )

        return order_result

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
            "Order cancellation not yet implemented for OKX Futures"
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
            "Order status query not yet implemented for OKX Futures"
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
        raise NotImplementedError("Trade history not yet implemented for OKX Futures")

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
            "Ticker subscription not yet implemented for OKX Futures"
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
            "Order book subscription not yet implemented for OKX Futures"
        )
        yield  # Make this a generator

    async def get_all_orders(
        self,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """查询所有订单（包括历史订单）.

        注意: OKX 区分不同时间范围的订单查询端点：
        - orders-history: 最近7天的订单（断线恢复场景）
        - orders-history-archive: 3个月前的归档订单

        重要: OKX API 的时间参数说明：
        - begin: 筛选的开始时间戳（毫秒）
        - end: 筛选的结束时间戳（毫秒）
        - 注意: begin < end，且时间范围不要超过90天

        Args:
            symbol: 交易对符号，如"BTC-USDT-SWAP"
            start_time: 起始时间戳（毫秒），可选
            end_time: 结束时间戳（毫秒），可选
            limit: 返回数量限制，默认100

        Returns:
            订单列表，每个订单包含完整信息

        Raises:
            ValueError: 缺少API凭证
        """
        self._require_credentials()

        params: dict[str, Any] = {
            "instType": "SWAP",
            "instId": symbol,
        }

        # OKX API 使用 begin/end 参数，单位是毫秒
        # 注意：OKX要求 begin < end，begin是筛选的开始时间，end是结束时间
        if start_time is not None:
            params["begin"] = str(start_time)
        if end_time is not None:
            params["end"] = str(end_time)

        # OKX limit 参数最大100
        params["limit"] = str(min(limit, 100))

        # ✅ 修复：根据时间范围选择正确的端点
        now_ms = int(time.time() * 1000)
        seven_days_ms = 7 * 24 * 60 * 60 * 1000

        # 如果查询时间在最近7天内，使用 orders-history（断线恢复场景）
        if start_time is None or (now_ms - start_time) < seven_days_ms:
            path = "/api/v5/trade/orders-history"  # ✅ 最近7天
            logger.info(
                "Using orders-history endpoint for recent orders",
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                params=params,
            )
        else:
            path = "/api/v5/trade/orders-history-archive"  # 归档订单
            logger.info(
                "Using orders-history-archive endpoint for archived orders",
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                params=params,
            )

        response = await self._request(
            method="GET",
            path=path,  # ✅ 动态选择端点
            params=params,
            authenticated=True,
        )

        data = response.json()

        logger.info(
            "OKX API response for orders",
            code=data.get("code"),
            msg=data.get("msg"),
            endpoint=path,
            data_count=len(data.get("data", [])),
        )

        # Check for API error
        if data.get("code") != "0":
            error_msg = f"OKX API error: code={data.get('code')}, msg={data.get('msg')}"
            logger.error(error_msg, endpoint=path, params=params, response=data)
            raise ValueError(error_msg)

        orders = data.get("data", [])
        logger.info(
            "Retrieved historical orders",
            symbol=symbol,
            count=len(orders),
            endpoint=path,
            start_time=start_time,
            end_time=end_time,
        )

        # 打印前几个订单的详细信息用于调试
        if orders:
            logger.debug("First order sample", order=orders[0])

        return orders

    async def get_user_trades(
        self,
        symbol: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """查询账户成交历史.

        Args:
            symbol: 交易对符号，如"BTC-USDT-SWAP"
            start_time: 起始时间戳（毫秒），可选
            end_time: 结束时间戳（毫秒），可选
            limit: 返回数量限制，默认100

        Returns:
            成交列表，每个成交包含完整信息

        Raises:
            ValueError: 缺少API凭证
        """
        self._require_credentials()

        params: dict[str, Any] = {
            "instType": "SWAP",
            "instId": symbol,
        }

        # OKX API 使用 begin/end 参数
        if start_time is not None:
            params["begin"] = str(start_time)
        if end_time is not None:
            params["end"] = str(end_time)

        params["limit"] = str(min(limit, 100))

        logger.info(
            "Querying OKX trades",
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            params=params,
        )

        response = await self._request(
            method="GET",
            path="/api/v5/trade/fills-history",
            params=params,
            authenticated=True,
        )

        data = response.json()

        logger.info(
            "OKX API response for trades",
            code=data.get("code"),
            msg=data.get("msg"),
            data_count=len(data.get("data", [])),
        )

        # Check for API error
        if data.get("code") != "0":
            error_msg = f"OKX API error: code={data.get('code')}, msg={data.get('msg')}"
            logger.error(
                error_msg,
                endpoint="/api/v5/trade/fills-history",
                params=params,
                response=data,
            )
            raise ValueError(error_msg)

        trades = data.get("data", [])
        logger.info(
            "Retrieved user trades",
            symbol=symbol,
            count=len(trades),
            start_time=start_time,
            end_time=end_time,
        )

        # 打印前几个成交的详细信息用于调试
        if trades:
            logger.debug("First trade sample", trade=trades[0])

        return trades
