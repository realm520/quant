"""
Exchange data models for Feature 004 compatibility.

Provides Ticker model that wraps core.models.Price for backward compatibility.
"""

from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field


class Ticker(BaseModel):
    """
    Market ticker data compatible with Feature 003 specification.

    This is a simplified model focused on arbitrage monitoring needs.
    """

    symbol: str = Field(..., description="Trading pair symbol (e.g., 'BTC/USDT')")
    bid: Decimal = Field(..., gt=0, description="Best bid price")
    ask: Decimal = Field(..., gt=0, description="Best ask price")
    bid_volume: Decimal = Field(..., ge=0, description="Volume available at bid price")
    ask_volume: Decimal = Field(..., ge=0, description="Volume available at ask price")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when ticker was retrieved",
    )
