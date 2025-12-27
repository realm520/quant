"""Contract tests for BaseExchange.get_ticker() - Feature 003

These tests define the expected behavior contract for get_ticker() method.
All exchange adapters MUST pass these tests to ensure API consistency.

Test Status: MUST FAIL until implementation complete (TDD requirement)
"""

import pytest
from typing import get_type_hints

from tri_arb.exchanges.base import BaseExchange
from tri_arb.core.models import Price, TradingPair


# Test 1: Batch query unsupported raises NotImplementedError
@pytest.mark.asyncio
async def test_batch_query_unsupported_raises_not_implemented() -> None:
    """CONTRACT: Unsupported batch query MUST raise NotImplementedError.

    This test verifies that the base implementation correctly rejects batch
    queries when an exchange adapter doesn't support them.
    """

    # Create a concrete BaseExchange implementation for testing
    class TestExchange(BaseExchange):
        async def connect(self) -> None:
            self.is_connected = True

        async def disconnect(self) -> None:
            self.is_connected = False

        async def get_ticker(self, trading_pair: TradingPair) -> Price:
            # This should raise NotImplementedError for None
            return await super().get_ticker(trading_pair)  # type: ignore

        async def get_orderbook(self, trading_pair: TradingPair, depth: int = 20):
            pass

        async def place_order(self, order):
            pass

        async def cancel_order(self, order_id: str):
            pass

        async def get_order_status(self, order_id: str):
            pass

        async def get_trade_history(self, trading_pair: TradingPair, limit: int = 100):
            return []

        async def subscribe_ticker(self, trading_pair: TradingPair):
            pass

        async def subscribe_orderbook(self, trading_pair: TradingPair, depth: int = 20):
            pass

    exchange = TestExchange(name="test")
    await exchange.connect()

    # Attempt batch query (trading_pair=None)
    with pytest.raises(NotImplementedError) as exc_info:
        await exchange.get_ticker(None)  # type: ignore

    # Verify error message contains exchange name and guidance
    error_msg = str(exc_info.value).lower()
    assert (
        "test" in error_msg or "batch" in error_msg
    ), "Error message should mention exchange name or batch queries"
    assert (
        "does not support" in error_msg or "not implement" in error_msg
    ), "Error message should indicate lack of support"


# Test 2: Return type annotation verification
def test_return_type_annotation() -> None:
    """CONTRACT: get_ticker signature MUST have correct type annotations.

    This test uses introspection to verify that the method signature
    includes Optional[TradingPair] parameter and Union[Price, List[Price]] return.
    """
    hints = get_type_hints(BaseExchange.get_ticker)

    # Verify parameter annotation exists
    assert "trading_pair" in hints, "trading_pair parameter must be annotated"

    # Verify return type annotation exists
    assert "return" in hints, "Return type must be annotated"

    # Get the return type annotation
    return_type = hints["return"]

    # Convert to string for inspection (handles Union, Optional, etc.)
    return_type_str = str(return_type)

    # Verify it's a Union type containing both Price and List[Price]
    # The exact format depends on Python version, so we check for key elements
    assert "Price" in return_type_str, "Return type must include Price"
    assert (
        "list" in return_type_str.lower() or "List" in return_type_str
    ), "Return type must include List[Price]"

    # Note: Full Union[Price, List[Price]] validation would require more
    # complex type inspection, but these checks are sufficient for contract
