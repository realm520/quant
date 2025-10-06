# Data Model: XT Exchange Integration

**Feature**: 002-xt-spot-api  
**Phase**: 1 (Design & Contracts)  
**Date**: 2025-10-05

## Overview

This document defines the data models, class structures, and state management for the XT Exchange integration. All designs conform to the `BaseExchange` interface and project's type safety requirements (mypy strict mode).

---

## 1. XTExchange Class

### Class Definition

```python
from typing import AsyncIterator, Optional
from decimal import Decimal
from datetime import datetime
import httpx

from tri_arb.exchanges.base import BaseExchange
from tri_arb.core.models import (
    Order,
    OrderBook,
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
```

### Attributes

| Attribute | Type | Visibility | Description |
|-----------|------|------------|-------------|
| `name` | `str` | Public | Exchange identifier, inherited from BaseExchange |
| `api_key` | `str` | Public | XT API key for authentication |
| `api_secret` | `str` | Public | XT API secret for signature generation |
| `is_connected` | `bool` | Public | Connection state, inherited from BaseExchange |
| `_client` | `Optional[httpx.AsyncClient]` | Private | HTTP client instance for API calls |
| `BASE_URL` | `str` | Class | XT API base URL |
| `API_VERSION` | `str` | Class | XT API version (v4) |
| `RECV_WINDOW` | `int` | Class | Request validity window (5000ms) |

### State Transitions

```
┌─────────────┐
│ INITIALIZED │
│ (created)   │
└─────┬───────┘
      │ connect()
      ▼
┌─────────────┐
│  CONNECTED  │
│ (_client)   │
└─────┬───────┘
      │ disconnect()
      ▼
┌─────────────┐
│ DISCONNECTED│
│ (_client=None)
└─────────────┘
```

---

## 2. Internal Helper Models

### 2.1 XTOrderStatus Enum

```python
from enum import Enum

class XTOrderStatus(str, Enum):
    """XT exchange order status enumeration.
    
    Maps XT API order status strings to typed enum for type safety.
    """
    NEW = "NEW"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
```

**Status Mapping to Internal OrderStatus**:

| XTOrderStatus | OrderStatus | Description |
|--------------|-------------|-------------|
| `NEW` | `OPEN` | Order created, awaiting execution |
| `FILLED` | `FILLED` | Order completely executed |
| `CANCELED` | `CANCELLED` | Order cancelled by user |
| `PARTIALLY_FILLED` | `PARTIAL` | Order partially executed |
| `REJECTED` | `FAILED` | Order rejected by exchange |
| `EXPIRED` | `CANCELLED` | Order expired (time-in-force) |

### 2.2 XTOrderType Enum

```python
class XTOrderType(str, Enum):
    """XT exchange order type enumeration."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    # TODO: Verify if XT supports IOC, FOK, POST_ONLY
```

### 2.3 XTOrderSide Enum

```python
class XTOrderSide(str, Enum):
    """XT exchange order side enumeration."""
    BUY = "BUY"
    SELL = "SELL"
```

### 2.4 XTTimeInForce Enum

```python
class XTTimeInForce(str, Enum):
    """XT exchange time-in-force enumeration."""
    GTC = "GTC"  # Good-Till-Cancel
    IOC = "IOC"  # Immediate-Or-Cancel
    FOK = "FOK"  # Fill-Or-Kill
    # TODO: Verify supported values from XT API docs
```

---

## 3. Request/Response Models (Optional Pydantic)

### 3.1 XT API Response Wrapper

```python
from pydantic import BaseModel, Field
from typing import Any, Optional

class XTResponse(BaseModel):
    """Generic XT API response wrapper.
    
    All XT API responses follow this structure with status codes
    and optional result data.
    """
    rc: int = Field(description="Response code (0 = success)")
    mc: str = Field(description="Message code (SUCCESS, ERROR, etc)")
    ma: list[Any] = Field(default_factory=list, description="Message arguments")
    result: Optional[Any] = Field(None, description="Response data payload")
    
    @property
    def is_success(self) -> bool:
        """Check if response indicates success."""
        return self.rc == 0 and self.mc == "SUCCESS"
```

### 3.2 Ticker Response Model

```python
class XTTickerData(BaseModel):
    """XT API ticker data model.
    
    Fields based on analysis of xt_spot_api.py response format.
    TODO: Verify exact field names from official XT API documentation.
    """
    s: str = Field(description="Symbol (e.g., 'btc_usdt')")
    t: int = Field(description="Timestamp (milliseconds)")
    c: Decimal = Field(description="Close price (last)")
    o: Decimal = Field(description="Open price (24h)")
    h: Decimal = Field(description="High price (24h)")
    l: Decimal = Field(description="Low price (24h)")
    v: Decimal = Field(description="Volume (base currency)")
    q: Decimal = Field(description="Quote volume (quote currency)")
    # TODO: Determine bid/ask price fields
    # Possible fields: ap (average price), bp (bid price), sp (sell price)
```

### 3.3 Depth Response Model

```python
class XTDepthLevel(BaseModel):
    """Single order book price level."""
    price: Decimal = Field(description="Price level")
    quantity: Decimal = Field(description="Quantity at this level")

class XTDepthData(BaseModel):
    """XT API order book depth data model."""
    s: str = Field(description="Symbol (e.g., 'btc_usdt')")
    t: int = Field(description="Timestamp (milliseconds)")
    bids: list[list[Decimal]] = Field(description="Bid levels [[price, qty], ...]")
    asks: list[list[Decimal]] = Field(description="Ask levels [[price, qty], ...]")
```

### 3.4 Order Request Model

```python
class XTOrderRequest(BaseModel):
    """XT API order placement request model."""
    symbol: str = Field(description="Trading pair symbol")
    side: XTOrderSide = Field(description="Order side (BUY/SELL)")
    type: XTOrderType = Field(description="Order type (LIMIT/MARKET)")
    timeInForce: XTTimeInForce = Field(description="Time in force")
    bizType: str = Field(default="SPOT", description="Business type")
    quantity: Decimal = Field(description="Order quantity")
    price: Optional[Decimal] = Field(None, description="Limit price (LIMIT orders)")
    quoteQty: Optional[Decimal] = Field(None, description="Quote quantity (MARKET buy)")
```

### 3.5 Order Response Model

```python
class XTOrderData(BaseModel):
    """XT API order response data model."""
    orderId: str = Field(description="Exchange order ID")
    symbol: str = Field(description="Trading pair symbol")
    side: XTOrderSide = Field(description="Order side")
    type: XTOrderType = Field(description="Order type")
    price: Decimal = Field(description="Order price")
    origQty: Decimal = Field(description="Original quantity")
    executedQty: Decimal = Field(description="Executed quantity")
    status: XTOrderStatus = Field(description="Order status")
    transactTime: int = Field(description="Transaction timestamp (ms)")
    # TODO: Verify field names from XT API documentation
```

---

## 4. Helper Methods

### 4.1 Trading Pair Transformation

```python
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
        base, quote = symbol.split('_', 1)
        return base.upper(), quote.upper()
    except ValueError:
        raise ValueError(f"Invalid XT symbol format: {symbol}")
```

### 4.2 Signature Generation

```python
import hmac
import hashlib
import time

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
        self.api_secret.encode('utf-8'),
        sig_data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Build headers
    headers = {
        'validate-algorithms': 'HmacSHA256',
        'validate-appkey': self.api_key,
        'validate-recvwindow': str(self.RECV_WINDOW),
        'validate-timestamp': str(timestamp_ms),
        'validate-signature': signature,
        'Content-Type': 'application/json',
        'accept': '*/*'
    }
    
    return headers, signature
```

### 4.3 Query String Sorting

```python
import urllib.parse
import json

def _build_sorted_query(self, params: dict) -> str:
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
```

### 4.4 HTTP Request Helper

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
)
async def _request(
    self,
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_data: Optional[dict] = None,
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
    
    headers = {}
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
            headers=headers if authenticated else None
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
```

### 4.5 Response Parsing Helpers

```python
def _parse_xt_response(self, response: httpx.Response) -> dict:
    """Parse and validate XT API response.
    
    Args:
        response: HTTP response from XT API
        
    Returns:
        Parsed response data
        
    Raises:
        ValueError: If response indicates error
    """
    data = response.json()
    
    if data.get('rc') != 0 or data.get('mc') != 'SUCCESS':
        error_msg = data.get('mc', 'Unknown error')
        logger.error("XT API error", error_code=data.get('rc'), error_message=error_msg)
        raise ValueError(f"XT API error: {error_msg}")
    
    return data.get('result', {})

def _map_order_status(self, xt_status: str) -> OrderStatus:
    """Map XT order status to internal OrderStatus enum.
    
    Args:
        xt_status: XT order status string
        
    Returns:
        Internal OrderStatus enum value
    """
    from tri_arb.core.models import OrderStatus
    
    status_map = {
        XTOrderStatus.NEW: OrderStatus.OPEN,
        XTOrderStatus.FILLED: OrderStatus.FILLED,
        XTOrderStatus.CANCELED: OrderStatus.CANCELLED,
        XTOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIAL,
        XTOrderStatus.REJECTED: OrderStatus.FAILED,
        XTOrderStatus.EXPIRED: OrderStatus.CANCELLED,
    }
    
    try:
        xt_enum = XTOrderStatus(xt_status)
        return status_map[xt_enum]
    except (ValueError, KeyError):
        logger.warning("Unknown XT order status, defaulting to OPEN", xt_status=xt_status)
        return OrderStatus.OPEN
```

---

## 5. State Management

### Connection Lifecycle

```python
async def connect(self) -> None:
    """Establish connection to XT exchange.
    
    Creates HTTP client with connection pooling and timeout configuration.
    Validates API credentials if provided.
    
    Raises:
        ValueError: If already connected
        AuthenticationError: If credentials invalid (future enhancement)
    """
    if self._client:
        raise ValueError("Already connected")
    
    self._client = httpx.AsyncClient(
        base_url=self.BASE_URL,
        timeout=httpx.Timeout(10.0, connect=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
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
```

### Error State Handling

```python
# Error states are transient - no persistent error state tracking
# Errors are logged and raised immediately
# Retry logic handled by @retry decorator
# No circuit breaker pattern in initial implementation (future enhancement)
```

---

## 6. Validation Rules

### Trading Pair Validation

```python
def _validate_trading_pair(self, trading_pair: TradingPair) -> None:
    """Validate trading pair before API operations.
    
    Args:
        trading_pair: Trading pair to validate
        
    Raises:
        ValueError: If trading pair is invalid
        
    TODO: Fetch supported trading pairs from XT API for runtime validation
    """
    if not trading_pair.base_currency:
        raise ValueError("Trading pair must have base currency")
    if not trading_pair.quote_currency:
        raise ValueError("Trading pair must have quote currency")
    
    # Basic format validation
    symbol = self._to_xt_symbol(trading_pair)
    if not symbol or '_' not in symbol:
        raise ValueError(f"Invalid symbol format: {symbol}")
```

### Order Validation

```python
def _validate_order(self, order: Order) -> None:
    """Validate order before placement.
    
    Args:
        order: Order to validate
        
    Raises:
        ValueError: If order is invalid
        
    TODO: Validate against XT's min/max order size and price precision
    """
    if order.quantity <= 0:
        raise ValueError("Order quantity must be positive")
    
    if order.price and order.price <= 0:
        raise ValueError("Order price must be positive")
    
    self._validate_trading_pair(order.trading_pair)
```

---

## 7. Data Flow Diagrams

### Get Ticker Flow

```
User Request
    ↓
get_ticker(trading_pair)
    ↓
_to_xt_symbol(trading_pair) → "btc_usdt"
    ↓
_request(GET, "/v4/public/ticker/price", params={symbol})
    ↓
_parse_xt_response(response) → {ticker_data}
    ↓
_parse_ticker_data(data, trading_pair) → Price model
    ↓
Return Price
```

### Place Order Flow

```
User Request
    ↓
place_order(order)
    ↓
_validate_order(order)
    ↓
_to_xt_symbol(order.trading_pair) → "btc_usdt"
    ↓
_build_order_request(order) → XTOrderRequest
    ↓
_generate_signature(...) → headers
    ↓
_request(POST, "/v4/order", json=request, authenticated=True)
    ↓
_parse_xt_response(response) → {order_data}
    ↓
_parse_order_data(data, order) → Updated Order model
    ↓
Return Order
```

---

## 8. Type Annotations

All methods have complete type annotations for mypy strict mode:

```python
# Example method signatures with full type hints
async def get_ticker(self, trading_pair: TradingPair) -> Price: ...
async def get_orderbook(self, trading_pair: TradingPair, depth: int = 20) -> OrderBook: ...
async def place_order(self, order: Order) -> Order: ...
async def cancel_order(self, order_id: str) -> bool: ...
async def get_order_status(self, order_id: str) -> Order: ...
async def get_trade_history(self, trading_pair: TradingPair, limit: int = 100) -> list[Trade]: ...
async def subscribe_ticker(self, trading_pair: TradingPair) -> AsyncIterator[Price]: ...
async def subscribe_orderbook(self, trading_pair: TradingPair, depth: int = 20) -> AsyncIterator[OrderBook]: ...
```

---

## 9. Summary

### Core Models:
1. **XTExchange** - Main adapter class (10 BaseExchange methods)
2. **XTOrderStatus** - Order status enum with mapping
3. **XTOrderType** - Order type enum (LIMIT, MARKET)
4. **XTOrderSide** - Order side enum (BUY, SELL)
5. **XTTimeInForce** - Time-in-force enum (GTC, IOC, FOK)
6. **XTResponse** - API response wrapper (optional Pydantic)
7. **XTTickerData** - Ticker response model (optional Pydantic)
8. **XTDepthData** - Order book response model (optional Pydantic)
9. **XTOrderRequest** - Order placement request model (optional Pydantic)
10. **XTOrderData** - Order response model (optional Pydantic)

### Helper Methods:
- Trading pair transformation (`_to_xt_symbol`, `_from_xt_symbol`)
- Signature generation (`_generate_signature`)
- Query string building (`_build_sorted_query`)
- HTTP requests with retry (`_request`)
- Response parsing (`_parse_xt_response`)
- Order status mapping (`_map_order_status`)
- Validation (`_validate_trading_pair`, `_validate_order`)

### State Management:
- Connection lifecycle (connect/disconnect)
- HTTP client lifecycle
- No persistent error state tracking

### Validation:
- Type safety enforced via mypy strict mode
- Runtime validation for trading pairs and orders
- Pydantic models for API responses (optional, for extra safety)

---

**Document Status**: Complete  
**Ready for Contract Generation**: ✅ Yes
