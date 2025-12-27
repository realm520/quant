"""
Arbitrage execution data models.

Defines entities for tracking automated arbitrage execution.
Based on specs/005-usdt/spec.md.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from tri_arb.core.models import Order
from tri_arb.models.arbitrage import ArbitrageOpportunity


class ExecutionStatus(str, Enum):
    """Execution status lifecycle.

    Tracks overall status of arbitrage execution across three trades.
    """

    PENDING = "pending"  # Execution created but not started
    IN_PROGRESS = "in_progress"  # Currently executing trades
    COMPLETED = "completed"  # All three trades completed successfully
    FAILED = "failed"  # Execution failed at some step
    PARTIAL = "partial"  # Some trades completed but not all


class ExecutionStep(BaseModel):
    """Single trade execution step.

    Represents one of the three trades in triangular arbitrage execution.
    Tracks submission, filling, and results for a single order.

    Attributes:
        step_number: Step sequence number (1, 2, or 3)
        order: Associated order object
        exchange_order_id: Exchange-specific order ID
        status: Step status (pending/submitted/filled/failed)
        submitted_at: When order was submitted
        filled_at: When order was filled
        filled_quantity: Actual filled quantity
        filled_price: Actual execution price
        fee: Trading fee paid
        fee_currency: Fee currency symbol
    """

    step_number: int = Field(..., ge=1, le=3, description="Step sequence (1/2/3)")

    order: Order = Field(..., description="Associated order")

    exchange_order_id: str | None = Field(
        None, description="Exchange order ID from API response"
    )

    status: str = Field(
        default="pending", description="Step status: pending/submitted/filled/failed"
    )

    submitted_at: datetime | None = Field(
        None, description="Order submission timestamp"
    )

    filled_at: datetime | None = Field(None, description="Order fill timestamp")

    filled_quantity: Decimal | None = Field(
        None, gt=0, description="Actual filled quantity"
    )

    filled_price: Decimal | None = Field(
        None, gt=0, description="Actual execution price"
    )

    fee: Decimal | None = Field(None, ge=0, description="Trading fee amount")

    fee_currency: str | None = Field(
        None, description="Fee currency symbol (e.g., BTC, ETH, USDT)"
    )


class ArbitrageExecution(BaseModel):
    """Complete arbitrage execution record.

    Tracks full lifecycle of triangular arbitrage execution including
    all three trades, profit/loss calculation, and session tracking.

    Attributes:
        session_id: Unique session identifier (UUID v4)
        opportunity: Associated arbitrage opportunity
        status: Execution status (pending/in_progress/completed/failed/partial)
        steps: Three execution steps (one per trade)
        initial_amount: Initial investment in USDT
        final_amount: Final amount received in USDT
        net_profit: Net profit (final - initial)
        actual_profit_rate: Actual profit rate percentage
        started_at: Execution start time
        completed_at: Execution completion time
        error_message: Error details if failed
    """

    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique session ID (UUID v4)",
    )

    opportunity: ArbitrageOpportunity = Field(
        ..., description="Associated arbitrage opportunity"
    )

    status: ExecutionStatus = Field(
        default=ExecutionStatus.PENDING, description="Execution status"
    )

    steps: list[ExecutionStep] = Field(
        default_factory=list, description="Three execution steps"
    )

    # Profit/loss tracking
    initial_amount: Decimal = Field(
        ..., gt=0, description="Initial investment amount (USDT)"
    )

    final_amount: Decimal | None = Field(
        None, ge=0, description="Final amount received (USDT)"
    )

    net_profit: Decimal | None = Field(None, description="Net profit (final - initial)")

    actual_profit_rate: Decimal | None = Field(
        None, description="Actual profit rate percentage"
    )

    # Timestamps
    started_at: datetime = Field(
        default_factory=datetime.utcnow, description="Execution start time"
    )

    completed_at: datetime | None = Field(None, description="Execution completion time")

    # Error tracking
    error_message: str | None = Field(
        None, description="Error message if execution failed"
    )

    def calculate_profit(self) -> None:
        """Calculate profit/loss from final and initial amounts.

        Updates net_profit and actual_profit_rate fields based on
        initial_amount and final_amount.

        Raises:
            ValueError: If final_amount is None
        """
        if self.final_amount is None:
            raise ValueError("Cannot calculate profit: final_amount is None")

        self.net_profit = self.final_amount - self.initial_amount
        self.actual_profit_rate = (self.net_profit / self.initial_amount) * Decimal(
            "100"
        )
