"""
Arbitrage monitor configuration.

Defines MonitorConfig with validation for all parameters.
Based on specs/004-xt-get-ticker/data-model.md.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MonitorConfig(BaseModel, frozen=True):
    """
    Configuration for arbitrage monitoring system.
    
    All fields are validated according to FR-018 requirements.
    """
    
    min_profit_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=100.0,
        description="Minimum profit threshold (%) to display opportunities"
    )
    
    fee_rate_per_trade: float = Field(
        default=0.1,
        ge=0.0,
        le=10.0,
        description="Trading fee rate per trade (%)"
    )
    
    base_currency_whitelist: list[str] = Field(
        default_factory=list,
        description="Base currency whitelist (empty = all currencies)"
    )
    
    refresh_interval_seconds: int = Field(
        default=10,
        ge=1,
        le=3600,
        description="Refresh interval in seconds (realtime mode)"
    )
    
    run_mode: Literal["once", "realtime"] = Field(
        default="once",
        description="Running mode: 'once' for single scan, 'realtime' for continuous"
    )

    # Amount recommendation settings
    max_recommended_amount: float = Field(
        default=10000.0,
        ge=1.0,
        le=1000000.0,
        description="Maximum recommended trading amount (in base currency)"
    )

    min_recommended_amount: float = Field(
        default=100.0,
        ge=1.0,
        le=100000.0,
        description="Minimum recommended trading amount (in base currency)"
    )

    liquidity_usage_rate: float = Field(
        default=0.3,
        ge=0.01,
        le=1.0,
        description="Fraction of available liquidity to use (0.3 = 30%)"
    )

    @field_validator("base_currency_whitelist")
    @classmethod
    def validate_currency_list(cls, v: list[str]) -> list[str]:
        """Validate each currency in whitelist is uppercase letters."""
        for currency in v:
            if not currency.isupper() or not currency.isalpha():
                raise ValueError(f"Currency must be uppercase letters: {currency}")
        return v
