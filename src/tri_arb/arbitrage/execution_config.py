"""
Arbitrage execution configuration.

Defines configuration parameters for automated arbitrage execution.
Based on specs/005-usdt/spec.md.
"""

from decimal import Decimal

from pydantic import BaseModel, Field


class ExecutionConfig(BaseModel):
    """Configuration for arbitrage execution.

    Controls behavior of automated trading execution including timeout,
    minimum amounts, and retry logic.

    Attributes:
        min_initial_amount: Minimum initial investment amount in USDT
        order_timeout_seconds: Maximum wait time for single order
        poll_interval_seconds: Order status polling interval
        max_retries: Maximum retries for network errors
    """

    min_initial_amount: Decimal = Field(
        default=Decimal("10"),
        gt=0,
        description="Minimum initial investment amount (USDT)"
    )

    order_timeout_seconds: int = Field(
        default=30,
        gt=0,
        le=300,
        description="Order timeout in seconds (max 5 minutes)"
    )

    poll_interval_seconds: float = Field(
        default=0.5,
        gt=0,
        le=5,
        description="Order status polling interval in seconds"
    )

    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retries for network errors"
    )
