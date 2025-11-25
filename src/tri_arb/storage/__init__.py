"""Storage module for database operations."""

from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.models import AccountUpdate, OrderUpdate, TradeUpdate, ListenKeyRecord
from tri_arb.storage.okx_models import OKXAccountBalance, OKXPosition, OKXOrder, OKXTrade
from tri_arb.storage.gate_models import GateAccountBalance, GatePosition, GateOrder, GateTrade
from tri_arb.storage.rest_models import RestBalance, RestPosition, RestOrder, ScheduledQuery
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
    # REST API models
    "RestBalance",
    "RestPosition",
    "RestOrder",
    "ScheduledQuery",
    # XT WebSocket models
    "XTAccountUpdate",
    "XTPositionUpdate",
    "XTOrderUpdate",
    "XTTradeUpdate",
    "XTWebSocketConnection",
]

