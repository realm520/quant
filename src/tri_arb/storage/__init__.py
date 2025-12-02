"""Storage module for database operations."""

from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.models import AccountUpdate, OrderUpdate, TradeUpdate, ListenKeyRecord
from tri_arb.storage.okx_models import OKXAccountBalance, OKXPosition, OKXOrder, OKXTrade
from tri_arb.storage.gate_models import GateAccountBalance, GatePosition, GateOrder, GateTrade
from tri_arb.storage.rest_models import ScheduledQuery
from tri_arb.storage.exchange_rest_models import (
    BinanceBalanceRest,
    BinancePositionRest,
    BinanceOrderRest,
    XTBalanceRest,
    XTPositionRest,
    XTOrderRest,
    OKXBalanceRest,
    OKXPositionRest,
    OKXOrderRest,
    GateBalanceRest,
    GatePositionRest,
    GateOrderRest,
    get_balance_model,
    get_position_model,
    get_order_model,
)
from tri_arb.storage.xt_websocket_models import (
    XTAccountUpdate, XTPositionUpdate, XTOrderUpdate, XTTradeUpdate, XTWebSocketConnection
)

__all__ = [
    "DatabaseManager",
    # Binance models
    "AccountUpdate",
    "OrderUpdate",
    "TradeUpdate",
    "ListenKeyRecord",
    # OKX models
    "OKXAccountBalance",
    "OKXPosition",
    "OKXOrder",
    "OKXTrade",
    # Gate.io models
    "GateAccountBalance",
    "GatePosition",
    "GateOrder",
    "GateTrade",
    # REST API models (按交易所区分)
    "BinanceBalanceRest",
    "BinancePositionRest",
    "BinanceOrderRest",
    "XTBalanceRest",
    "XTPositionRest",
    "XTOrderRest",
    "OKXBalanceRest",
    "OKXPositionRest",
    "OKXOrderRest",
    "GateBalanceRest",
    "GatePositionRest",
    "GateOrderRest",
    "get_balance_model",
    "get_position_model",
    "get_order_model",
    "ScheduledQuery",
    # XT WebSocket models
    "XTAccountUpdate",
    "XTPositionUpdate",
    "XTOrderUpdate",
    "XTTradeUpdate",
    "XTConnection",
]

