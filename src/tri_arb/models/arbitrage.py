"""
Arbitrage data models.

Defines entities for triangular arbitrage opportunity monitoring system.
Based on specs/004-xt-get-ticker/data-model.md.
"""

from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
from datetime import datetime
from typing import Literal


class TradingPath(BaseModel, frozen=True):
    """
    Represents a complete triangular arbitrage path (A→B→C→A).

    Example: USDT → BTC → ETH → USDT
    """

    start_currency: str = Field(..., description="Starting currency (e.g., USDT)")
    trading_pairs: tuple[str, str, str] = Field(
        ..., description="Three trading pair symbols in order"
    )

    @field_validator("start_currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """Validate currency is uppercase letters only."""
        if not v.isupper() or not v.isalpha():
            raise ValueError(f"Currency must be uppercase letters: {v}")
        return v

    @field_validator("trading_pairs")
    @classmethod
    def validate_path_length(cls, v: tuple[str, str, str]) -> tuple[str, str, str]:
        """Validate path has exactly 3 trading pairs."""
        if len(v) != 3:
            raise ValueError("Trading path must have exactly 3 pairs")
        return v

    @property
    def is_closed_loop(self) -> bool:
        """
        Check if the trading path returns to the starting currency.

        Returns:
            True if path is closed loop, False otherwise
        """
        # Parse the third trading pair to determine final currency
        third_pair = self.trading_pairs[2]

        # Trading pairs are in format "BASE/QUOTE"
        base, quote = third_pair.split("/")

        # After 3 trades, we need to check if we end up with start_currency
        # This requires simulating the full path:
        # 1. Start with start_currency
        # 2. Trade pair 1: determine if we buy or sell
        # 3. Trade pair 2: determine next currency
        # 4. Trade pair 3: determine final currency
        # 5. Check if final == start_currency

        current = self.start_currency

        for pair in self.trading_pairs:
            base_curr, quote_curr = pair.split("/")

            if current == base_curr:
                # We sell base, get quote
                current = quote_curr
            elif current == quote_curr:
                # We buy base with quote
                current = base_curr
            else:
                # Invalid path: current currency not in this pair
                return False

        return current == self.start_currency


class ArbitrageOpportunity(BaseModel):
    """
    Represents a profitable triangular arbitrage opportunity.

    Includes path, profit rate, prices, and metadata.
    """

    path: TradingPath = Field(..., description="The arbitrage trading path")
    expected_profit_rate: Decimal = Field(
        ..., description="Expected profit rate (%) after fees"
    )
    prices: list[dict] = Field(
        ..., description="Price details for each step (type, pair, price)"
    )
    recommended_amount: Decimal = Field(
        ..., gt=0, description="Recommended initial investment amount"
    )
    discovered_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when opportunity was discovered",
    )
    status: Literal["new", "printed", "expired"] = Field(
        default="new", description="Opportunity status"
    )

    @field_validator("prices")
    @classmethod
    def validate_prices_length(cls, v: list[dict]) -> list[dict]:
        """Validate prices list has exactly 3 entries."""
        if len(v) != 3:
            raise ValueError("Prices must contain exactly 3 entries")

        required_keys = {"type", "pair", "price"}
        for price in v:
            if not required_keys.issubset(price.keys()):
                raise ValueError("Each price must have 'type', 'pair', 'price' keys")
            if price["type"] not in ["buy", "sell"]:
                raise ValueError(
                    f"Price type must be 'buy' or 'sell', got: {price['type']}"
                )

        return v
