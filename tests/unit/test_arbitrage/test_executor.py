"""Unit tests for ArbitrageExecutor.

Tests the automated arbitrage execution engine.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from tri_arb.arbitrage.execution_config import ExecutionConfig
from tri_arb.arbitrage.executor import ArbitrageExecutor
from tri_arb.core.models import Order, OrderSide, OrderStatus, OrderType, TradingPair
from tri_arb.models.arbitrage import ArbitrageOpportunity, TradingPath
from tri_arb.models.execution import ArbitrageExecution, ExecutionStatus


@pytest.fixture
def mock_exchange():
    """Create mock exchange adapter."""
    exchange = AsyncMock()
    exchange.name = "test_exchange"

    # Mock place_order to return order with exchange_order_id
    async def mock_place_order(order: Order) -> Order:
        order.exchange_order_id = f"EXCHANGE-{order.order_id}"
        order.status = OrderStatus.OPEN
        return order

    exchange.place_order = AsyncMock(side_effect=mock_place_order)

    # Mock get_order_status to return filled order immediately
    async def mock_get_order_status(order_id: str) -> Order:
        order = Order(
            order_id=order_id,
            exchange_order_id=order_id,
            trading_pair=TradingPair(
                base_currency="BTC",
                quote_currency="USDT",
                exchange="test_exchange",
                min_order_size=Decimal("0.001"),
                max_order_size=Decimal("1000"),
                price_precision=2,
                quantity_precision=6,
            ),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=Decimal("100"),
            status=OrderStatus.FILLED,
            created_at=None,
            updated_at=None,
            exchange="test_exchange",
        )
        return order

    exchange.get_order_status = AsyncMock(side_effect=mock_get_order_status)
    exchange.cancel_order = AsyncMock(return_value=True)

    return exchange


@pytest.fixture
def execution_config():
    """Create execution config with default settings."""
    return ExecutionConfig(
        min_initial_amount=Decimal("10"),
        order_timeout_seconds=30,
        poll_interval_seconds=0.5,
        max_retries=3,
    )


@pytest.fixture
def sample_opportunity():
    """Create sample arbitrage opportunity."""
    path = TradingPath(
        start_currency="USDT",
        trading_pairs=["BTC/USDT", "ETH/BTC", "ETH/USDT"],
    )

    opportunity = ArbitrageOpportunity(
        path=path,
        prices=[
            {"type": "buy", "pair": "BTC/USDT", "price": Decimal("50000")},
            {"type": "buy", "pair": "ETH/BTC", "price": Decimal("0.05")},
            {"type": "sell", "pair": "ETH/USDT", "price": Decimal("2550")},
        ],
        expected_profit_rate=Decimal("2.0"),
        recommended_amount=Decimal("100"),
    )

    return opportunity


@pytest.mark.asyncio
async def test_execute_opportunity_success(
    mock_exchange, execution_config, sample_opportunity
):
    """Test successful arbitrage execution."""
    executor = ArbitrageExecutor(exchange=mock_exchange, config=execution_config)

    execution = await executor.execute_opportunity(sample_opportunity)

    # Verify execution completed
    assert execution.status == ExecutionStatus.COMPLETED
    assert execution.initial_amount == Decimal("100")
    assert execution.final_amount is not None
    assert execution.net_profit is not None
    assert execution.actual_profit_rate is not None

    # Verify three steps executed
    assert len(execution.steps) == 3

    # Verify each step was filled
    for step in execution.steps:
        assert step.status == "filled"
        assert step.filled_quantity is not None
        assert step.exchange_order_id is not None

    # Verify exchange calls
    assert mock_exchange.place_order.call_count == 3
    assert mock_exchange.get_order_status.call_count >= 3


@pytest.mark.asyncio
async def test_execute_opportunity_below_minimum(mock_exchange, execution_config):
    """Test execution fails when amount below minimum."""
    executor = ArbitrageExecutor(exchange=mock_exchange, config=execution_config)

    # Create opportunity with amount below minimum (10 USDT)
    path = TradingPath(
        start_currency="USDT",
        trading_pairs=["BTC/USDT", "ETH/BTC", "ETH/USDT"],
    )

    low_amount_opportunity = ArbitrageOpportunity(
        path=path,
        prices=[
            {"type": "buy", "pair": "BTC/USDT", "price": Decimal("50000")},
            {"type": "buy", "pair": "ETH/BTC", "price": Decimal("0.05")},
            {"type": "sell", "pair": "ETH/USDT", "price": Decimal("2550")},
        ],
        expected_profit_rate=Decimal("2.0"),
        recommended_amount=Decimal("5"),  # Below 10 USDT minimum
    )

    with pytest.raises(ValueError, match="Initial amount.*< minimum"):
        await executor.execute_opportunity(low_amount_opportunity)


@pytest.mark.asyncio
async def test_execute_opportunity_order_timeout(
    mock_exchange, execution_config, sample_opportunity
):
    """Test execution fails when order times out."""

    # Mock get_order_status to never return FILLED status
    async def mock_timeout_status(order_id: str) -> Order:
        order = Order(
            order_id=order_id,
            exchange_order_id=order_id,
            trading_pair=TradingPair(
                base_currency="BTC",
                quote_currency="USDT",
                exchange="test_exchange",
                min_order_size=Decimal("0.001"),
                max_order_size=Decimal("1000"),
                price_precision=2,
                quantity_precision=6,
            ),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=Decimal("100"),
            status=OrderStatus.OPEN,  # Never becomes FILLED
            created_at=None,
            updated_at=None,
            exchange="test_exchange",
        )
        return order

    mock_exchange.get_order_status = AsyncMock(side_effect=mock_timeout_status)

    # Use very short timeout for test
    short_timeout_config = ExecutionConfig(
        min_initial_amount=Decimal("10"),
        order_timeout_seconds=1,
        poll_interval_seconds=0.1,
    )

    executor = ArbitrageExecutor(exchange=mock_exchange, config=short_timeout_config)

    with pytest.raises(RuntimeError, match="timed out"):
        await executor.execute_opportunity(sample_opportunity)


@pytest.mark.asyncio
async def test_execute_opportunity_order_rejected(
    mock_exchange, execution_config, sample_opportunity
):
    """Test execution fails when order is rejected."""

    # Mock get_order_status to return REJECTED
    async def mock_rejected_status(order_id: str) -> Order:
        order = Order(
            order_id=order_id,
            exchange_order_id=order_id,
            trading_pair=TradingPair(
                base_currency="BTC",
                quote_currency="USDT",
                exchange="test_exchange",
                min_order_size=Decimal("0.001"),
                max_order_size=Decimal("1000"),
                price_precision=2,
                quantity_precision=6,
            ),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=Decimal("100"),
            status=OrderStatus.REJECTED,
            created_at=None,
            updated_at=None,
            exchange="test_exchange",
        )
        return order

    mock_exchange.get_order_status = AsyncMock(side_effect=mock_rejected_status)

    executor = ArbitrageExecutor(exchange=mock_exchange, config=execution_config)

    with pytest.raises(RuntimeError, match="failed with status"):
        await executor.execute_opportunity(sample_opportunity)


@pytest.mark.asyncio
async def test_execute_opportunity_partial_execution(
    mock_exchange, execution_config, sample_opportunity
):
    """Test execution handles partial completion correctly."""
    # Mock first order succeeds, second order fails
    order_count = 0

    async def mock_partial_status(order_id: str) -> Order:
        nonlocal order_count
        order_count += 1

        # First order fills successfully
        if order_count == 1:
            status = OrderStatus.FILLED
        else:
            # Second order gets rejected
            status = OrderStatus.REJECTED

        order = Order(
            order_id=order_id,
            exchange_order_id=order_id,
            trading_pair=TradingPair(
                base_currency="BTC",
                quote_currency="USDT",
                exchange="test_exchange",
                min_order_size=Decimal("0.001"),
                max_order_size=Decimal("1000"),
                price_precision=2,
                quantity_precision=6,
            ),
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=Decimal("100"),
            status=status,
            created_at=None,
            updated_at=None,
            exchange="test_exchange",
        )
        return order

    mock_exchange.get_order_status = AsyncMock(side_effect=mock_partial_status)

    executor = ArbitrageExecutor(exchange=mock_exchange, config=execution_config)

    with pytest.raises(RuntimeError):
        await executor.execute_opportunity(sample_opportunity)


@pytest.mark.asyncio
async def test_create_order_with_correct_parameters(
    mock_exchange, execution_config, sample_opportunity
):
    """Test order creation with correct parameters."""
    executor = ArbitrageExecutor(exchange=mock_exchange, config=execution_config)

    # Create mock execution for context
    execution = ArbitrageExecution(
        opportunity=sample_opportunity,
        initial_amount=Decimal("100"),
    )

    # Test order creation for first step (buy)
    price_info = sample_opportunity.prices[0]
    order = executor._create_order(
        step_number=1,
        price_info=price_info,
        amount=Decimal("100"),
        execution=execution,
    )

    # Verify order properties
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.price is None  # Market orders have no price
    assert order.quantity == Decimal("100")
    assert order.trading_pair.base_currency == "BTC"
    assert order.trading_pair.quote_currency == "USDT"
    assert execution.session_id in order.order_id


@pytest.mark.asyncio
async def test_session_id_tracking(mock_exchange, execution_config, sample_opportunity):
    """Test that session ID is properly tracked throughout execution."""
    executor = ArbitrageExecutor(exchange=mock_exchange, config=execution_config)

    execution = await executor.execute_opportunity(sample_opportunity)

    # Verify session ID exists and is UUID format
    assert execution.session_id is not None
    assert len(execution.session_id) == 36  # UUID length with hyphens

    # Verify all order IDs contain session ID
    for step in execution.steps:
        assert execution.session_id in step.order.order_id


def test_execution_config_validation():
    """Test execution config parameter validation."""
    # Valid config
    config = ExecutionConfig(
        min_initial_amount=Decimal("10"),
        order_timeout_seconds=30,
        poll_interval_seconds=0.5,
    )
    assert config.min_initial_amount == Decimal("10")

    # Invalid: negative minimum amount
    with pytest.raises(ValueError):
        ExecutionConfig(min_initial_amount=Decimal("-10"))

    # Invalid: zero timeout
    with pytest.raises(ValueError):
        ExecutionConfig(order_timeout_seconds=0)

    # Invalid: timeout > 300 seconds
    with pytest.raises(ValueError):
        ExecutionConfig(order_timeout_seconds=400)
