"""
Arbitrage execution engine.

Implements automated execution of triangular arbitrage opportunities.
Based on specs/005-usdt/spec.md.
"""

import asyncio
from datetime import datetime
from decimal import Decimal

import structlog

from tri_arb.arbitrage.execution_config import ExecutionConfig
from tri_arb.core.models import Order, OrderSide, OrderStatus, OrderType, TradingPair
from tri_arb.exchanges.base import BaseExchange
from tri_arb.models.arbitrage import ArbitrageOpportunity
from tri_arb.models.execution import ArbitrageExecution, ExecutionStatus, ExecutionStep


logger = structlog.get_logger(__name__)


class ArbitrageExecutor:
    """
    Arbitrage execution engine.

    Executes triangular arbitrage opportunities using market orders,
    tracking execution through unique session IDs and calculating
    profit/loss after completion.

    Example:
        >>> config = ExecutionConfig()
        >>> executor = ArbitrageExecutor(exchange=xt_exchange, config=config)
        >>> execution = await executor.execute_opportunity(opportunity)
        >>> print(f"Profit: {execution.net_profit} USDT")
    """

    def __init__(self, exchange: BaseExchange, config: ExecutionConfig):
        """Initialize arbitrage executor.

        Args:
            exchange: Exchange adapter for order execution
            config: Execution configuration parameters
        """
        self.exchange = exchange
        self.config = config
        self.logger = logger.bind(executor="ArbitrageExecutor")

    async def execute_opportunity(
        self,
        opportunity: ArbitrageOpportunity
    ) -> ArbitrageExecution:
        """Execute arbitrage opportunity with three sequential market orders.

        Validates initial amount, submits three orders sequentially waiting
        for each to fill before submitting next, calculates final profit/loss.

        Args:
            opportunity: Arbitrage opportunity to execute

        Returns:
            ArbitrageExecution record with results

        Raises:
            ValueError: If initial amount < minimum threshold
            RuntimeError: If order submission or fill fails

        Example:
            >>> execution = await executor.execute_opportunity(opportunity)
            >>> if execution.status == ExecutionStatus.COMPLETED:
            ...     print(f"Success! Profit: {execution.net_profit}")
        """
        # Validate initial amount against minimum threshold
        if opportunity.recommended_amount < self.config.min_initial_amount:
            raise ValueError(
                f"Initial amount {opportunity.recommended_amount} USDT < "
                f"minimum {self.config.min_initial_amount} USDT"
            )

        # Create execution record with unique session ID
        execution = ArbitrageExecution(
            opportunity=opportunity,
            initial_amount=opportunity.recommended_amount
        )

        self.logger.info(
            "arbitrage_execution_started",
            session_id=execution.session_id,
            path=" → ".join([opportunity.path.start_currency] + list(opportunity.path.trading_pairs)),
            initial_amount=float(execution.initial_amount)
        )

        try:
            execution.status = ExecutionStatus.IN_PROGRESS

            # Execute three trades sequentially
            current_amount = execution.initial_amount

            for step_num, price_info in enumerate(opportunity.prices, 1):
                step = await self._execute_step(
                    step_number=step_num,
                    price_info=price_info,
                    amount=current_amount,
                    execution=execution
                )

                execution.steps.append(step)

                # Update current amount to actual filled quantity for next step
                if step.filled_quantity:
                    # For next step, use filled quantity from this step
                    # Note: Need to handle currency conversion properly
                    current_amount = step.filled_quantity
                else:
                    raise RuntimeError(
                        f"Step {step_num} failed: no filled quantity recorded"
                    )

            # Calculate profit/loss after all three trades complete
            execution.final_amount = current_amount
            execution.calculate_profit()
            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = datetime.utcnow()

            self.logger.info(
                "arbitrage_execution_completed",
                session_id=execution.session_id,
                initial_amount=float(execution.initial_amount),
                final_amount=float(execution.final_amount),
                net_profit=float(execution.net_profit),
                profit_rate=float(execution.actual_profit_rate)
            )

        except Exception as e:
            # Mark execution as failed, preserve steps completed so far
            execution.status = ExecutionStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.utcnow()

            self.logger.error(
                "arbitrage_execution_failed",
                session_id=execution.session_id,
                error=str(e),
                steps_completed=len(execution.steps),
                exc_info=True
            )
            raise

        return execution

    async def _execute_step(
        self,
        step_number: int,
        price_info: dict,
        amount: Decimal,
        execution: ArbitrageExecution
    ) -> ExecutionStep:
        """Execute single trade step.

        Creates order, submits to exchange, waits for fill, records results.

        Args:
            step_number: Step sequence number (1, 2, or 3)
            price_info: Price information from opportunity
            amount: Amount to trade
            execution: Parent execution record (for logging)

        Returns:
            ExecutionStep with filled order details

        Raises:
            RuntimeError: If order submission or fill fails
            TimeoutError: If order times out
        """
        # Create order for this step
        order = self._create_order(
            step_number=step_number,
            price_info=price_info,
            amount=amount,
            execution=execution
        )

        step = ExecutionStep(step_number=step_number, order=order)

        # Submit order to exchange
        step.submitted_at = datetime.utcnow()

        try:
            submitted_order = await self.exchange.place_order(order)
            step.exchange_order_id = submitted_order.exchange_order_id or submitted_order.order_id
            step.status = "submitted"

            self.logger.info(
                "order_submitted",
                session_id=execution.session_id,
                step=step_number,
                order_id=step.exchange_order_id,
                pair=f"{order.trading_pair.base_currency}/{order.trading_pair.quote_currency}",
                side=order.side.value,
                quantity=float(order.quantity)
            )

        except Exception as e:
            step.status = "failed"
            self.logger.error(
                "order_submission_failed",
                session_id=execution.session_id,
                step=step_number,
                error=str(e),
                exc_info=True
            )
            raise RuntimeError(f"Order submission failed: {e}") from e

        # Wait for order to fill
        try:
            filled_order = await self._wait_for_fill(
                order_id=step.exchange_order_id,
                timeout=self.config.order_timeout_seconds
            )

            # Record fill details
            step.filled_at = datetime.utcnow()
            step.filled_quantity = filled_order.quantity  # Actual filled quantity
            step.filled_price = filled_order.price  # Actual execution price (if available)
            step.status = "filled"

            # TODO: Get fee from trade history (exchange.get_trade_history)
            # For now, fee calculation is deferred

            self.logger.info(
                "order_filled",
                session_id=execution.session_id,
                step=step_number,
                order_id=step.exchange_order_id,
                filled_quantity=float(step.filled_quantity),
                filled_price=float(step.filled_price) if step.filled_price else None
            )

        except TimeoutError as e:
            step.status = "failed"
            self.logger.error(
                "order_timeout",
                session_id=execution.session_id,
                step=step_number,
                order_id=step.exchange_order_id,
                timeout=self.config.order_timeout_seconds
            )
            raise RuntimeError(f"Order timed out after {self.config.order_timeout_seconds}s") from e

        except Exception as e:
            step.status = "failed"
            self.logger.error(
                "order_fill_failed",
                session_id=execution.session_id,
                step=step_number,
                order_id=step.exchange_order_id,
                error=str(e),
                exc_info=True
            )
            raise RuntimeError(f"Order fill failed: {e}") from e

        return step

    async def _wait_for_fill(
        self,
        order_id: str,
        timeout: int
    ) -> Order:
        """Wait for order to fill (market orders usually fill immediately).

        Polls order status at configured interval until filled or timeout.

        Args:
            order_id: Exchange order ID to monitor
            timeout: Maximum wait time in seconds

        Returns:
            Filled order with actual execution details

        Raises:
            TimeoutError: If order not filled within timeout
            RuntimeError: If order cancelled or rejected
        """
        start_time = datetime.utcnow()
        poll_interval = self.config.poll_interval_seconds

        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            # Query order status from exchange
            try:
                status_order = await self.exchange.get_order_status(order_id)

                # Check if order is filled
                if status_order.status == OrderStatus.FILLED:
                    return status_order

                # Check if order failed
                if status_order.status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
                    raise RuntimeError(
                        f"Order {order_id} failed with status: {status_order.status.value}"
                    )

                # Still pending/open, wait and retry
                await asyncio.sleep(poll_interval)

            except Exception as e:
                # Log error but continue polling (transient network errors)
                self.logger.warning(
                    "order_status_query_failed",
                    order_id=order_id,
                    error=str(e),
                    retrying=True
                )
                await asyncio.sleep(poll_interval)

        # Timeout reached - attempt to cancel order
        self.logger.warning(
            "order_timeout_cancelling",
            order_id=order_id,
            timeout=timeout
        )

        try:
            cancelled = await self.exchange.cancel_order(order_id)
            if cancelled:
                self.logger.info("order_cancelled", order_id=order_id)
        except Exception as e:
            self.logger.error(
                "order_cancellation_failed",
                order_id=order_id,
                error=str(e)
            )

        raise TimeoutError(f"Order {order_id} timed out after {timeout}s")

    def _create_order(
        self,
        step_number: int,
        price_info: dict,
        amount: Decimal,
        execution: ArbitrageExecution
    ) -> Order:
        """Create order for execution step.

        Builds Order object from price_info and execution context.
        Uses market order type for immediate execution.

        Args:
            step_number: Step sequence number (1, 2, or 3)
            price_info: Price information from opportunity (type, pair, price)
            amount: Amount to trade
            execution: Parent execution record (for order ID generation)

        Returns:
            Order ready for submission

        Raises:
            ValueError: If trading pair not found or invalid
        """
        trade_type = price_info["type"]  # "buy" or "sell"
        pair_symbol = price_info["pair"]  # e.g., "BTC/USDT"

        # Parse trading pair symbol
        base, quote = pair_symbol.split("/")

        # Get full trading pair info from opportunity
        # Note: ArbitrageOpportunity uses TradingPath which only has pair symbols
        # We need to construct a minimal TradingPair for the order
        trading_pair = self._get_trading_pair(pair_symbol, execution)

        # Determine order side
        side = OrderSide.BUY if trade_type == "buy" else OrderSide.SELL

        # Create market order
        order = Order(
            order_id=f"{execution.session_id}-step{step_number}",
            trading_pair=trading_pair,
            side=side,
            order_type=OrderType.MARKET,  # Always use market orders
            price=None,  # Market orders don't specify price
            quantity=amount,
            status=OrderStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            exchange=self.exchange.name
        )

        return order

    def _get_trading_pair(
        self,
        pair_symbol: str,
        execution: ArbitrageExecution
    ) -> TradingPair:
        """Get TradingPair object for given symbol.

        Creates minimal TradingPair for order creation.
        In production, should fetch full pair info from exchange.

        Args:
            pair_symbol: Trading pair symbol (e.g., "BTC/USDT")
            execution: Parent execution record (for opportunity context)

        Returns:
            TradingPair object (minimal config for MVP)

        Raises:
            ValueError: If pair symbol invalid
        """
        try:
            base, quote = pair_symbol.split("/")
        except ValueError as e:
            raise ValueError(f"Invalid trading pair symbol: {pair_symbol}") from e

        # Create minimal trading pair
        # TODO: Fetch actual trading pair info from exchange
        # For now, use conservative defaults
        return TradingPair(
            base_currency=base,
            quote_currency=quote,
            exchange=self.exchange.name,
            min_order_size=Decimal("0.00001"),  # Conservative minimum
            max_order_size=Decimal("1000000"),  # Conservative maximum
            price_precision=8,
            quantity_precision=8
        )
