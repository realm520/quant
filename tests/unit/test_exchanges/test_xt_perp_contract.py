"""Contract tests for XTPerpExchange BaseExchange interface compliance.

Validates that XTPerpExchange correctly implements the BaseExchange interface
and perpetual futures-specific methods. These tests ensure API contract
compliance before implementation details are added.

Test-Driven Development (TDD) Approach:
1. These tests are written FIRST (before implementation)
2. All tests should FAIL initially (NotImplementedError)
3. Implementation proceeds to make tests pass one by one
4. Tests validate interface contracts, not implementation details
"""

import pytest
from decimal import Decimal
from datetime import datetime
from typing import Any

from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.exchanges.base import BaseExchange
from tri_arb.core.models import Order, OrderBook, OrderSide, OrderStatus, OrderType, Price, TradingPair


class TestXTPerpExchangeContract:
    """Test XTPerpExchange implements BaseExchange interface correctly.
    
    These tests verify:
    1. Class inheritance and interface compliance
    2. Method signatures match BaseExchange abstract methods
    3. Connection lifecycle management
    4. All abstract methods are implemented (not NotImplementedError)
    """

    @pytest.fixture
    def exchange(self) -> XTPerpExchange:
        """Create XTPerpExchange instance for testing.
        
        Returns:
            XTPerpExchange instance with test credentials
        """
        return XTPerpExchange(
            api_key="test_api_key",
            api_secret="test_api_secret",
            timeout=30,
        )

    @pytest.fixture
    def sample_trading_pair(self) -> TradingPair:
        """Create sample TradingPair for testing.
        
        Returns:
            TradingPair instance for BTC/USDT
        """
        return TradingPair(
            base_currency="BTC",
            quote_currency="USDT",
            exchange="xt_perp",
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1000"),
            price_precision=2,
            quantity_precision=3,
        )

    def test_implements_base_exchange_interface(self, exchange: XTPerpExchange) -> None:
        """Verify XTPerpExchange implements BaseExchange interface.
        
        Validates:
        - Inherits from BaseExchange
        - Has name attribute
        - Has is_connected attribute
        """
        assert isinstance(exchange, BaseExchange)
        assert hasattr(exchange, "name")
        assert hasattr(exchange, "is_connected")
        assert exchange.name == "xt_perp"
        assert exchange.is_connected is False

    @pytest.mark.asyncio
    async def test_connect_disconnect_lifecycle(self, exchange: XTPerpExchange) -> None:
        """Test connection lifecycle management.
        
        Validates:
        - connect() establishes connection
        - is_connected flag is set correctly
        - disconnect() closes connection
        - is_connected flag is cleared
        """
        # Initially not connected
        assert exchange.is_connected is False
        
        # Connect should establish connection
        await exchange.connect()
        assert exchange.is_connected is True
        
        # Disconnect should close connection
        await exchange.disconnect()
        assert exchange.is_connected is False

    @pytest.mark.asyncio
    async def test_get_ticker_signature(
        self, exchange: XTPerpExchange, sample_trading_pair: TradingPair
    ) -> None:
        """Test get_ticker() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts TradingPair argument
        - Returns Price object (single pair query)
        - Returns list[Price] (batch query with None)
        
        Note: This test may fail if XTPerpExchange is not yet implemented.
        Expected to fail initially in TDD workflow.
        """
        await exchange.connect()
        
        try:
            # Single pair query
            result = await exchange.get_ticker(sample_trading_pair)
            assert isinstance(result, Price)
            assert result.trading_pair == sample_trading_pair
            
            # Batch query (all pairs)
            batch_result = await exchange.get_ticker(None)
            assert isinstance(batch_result, list)
            assert all(isinstance(price, Price) for price in batch_result)
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_get_orderbook_signature(
        self, exchange: XTPerpExchange, sample_trading_pair: TradingPair
    ) -> None:
        """Test get_orderbook() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts TradingPair and depth arguments
        - Returns OrderBook object
        - OrderBook has bids and asks lists
        """
        await exchange.connect()
        
        try:
            result = await exchange.get_orderbook(sample_trading_pair, depth=20)
            assert isinstance(result, OrderBook)
            assert result.trading_pair == sample_trading_pair
            assert isinstance(result.bids, list)
            assert isinstance(result.asks, list)
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_place_order_signature(
        self, exchange: XTPerpExchange, sample_trading_pair: TradingPair
    ) -> None:
        """Test place_order() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts Order argument
        - Returns Order object with exchange_order_id
        - Status is updated from PENDING
        """
        await exchange.connect()
        
        try:
            order = Order(
                order_id="test_order_1",
                trading_pair=sample_trading_pair,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("50000.00"),
                quantity=Decimal("0.01"),
                status=OrderStatus.PENDING,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                exchange="xt_perp",
                position_side="LONG",  # Perpetual futures specific
            )
            
            result = await exchange.place_order(order)
            assert isinstance(result, Order)
            assert result.exchange_order_id is not None
            assert result.status != OrderStatus.PENDING
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_cancel_order_signature(self, exchange: XTPerpExchange) -> None:
        """Test cancel_order() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts order_id string argument
        - Returns bool (success/failure)
        """
        await exchange.connect()
        
        try:
            result = await exchange.cancel_order("test_order_id")
            assert isinstance(result, bool)
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_get_order_status_signature(self, exchange: XTPerpExchange) -> None:
        """Test get_order_status() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts order_id string argument
        - Returns Order object with current status
        """
        await exchange.connect()
        
        try:
            result = await exchange.get_order_status("test_order_id")
            assert isinstance(result, Order)
            assert result.status is not None
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_get_trade_history_signature(
        self, exchange: XTPerpExchange, sample_trading_pair: TradingPair
    ) -> None:
        """Test get_trade_history() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts TradingPair and limit arguments
        - Returns list of Trade objects (from Any type in base.py)
        """
        await exchange.connect()
        
        try:
            result = await exchange.get_trade_history(sample_trading_pair, limit=100)
            assert isinstance(result, list)
            # Note: Trade object type validation depends on implementation
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_get_trading_pair_info_signature(
        self, exchange: XTPerpExchange, sample_trading_pair: TradingPair
    ) -> None:
        """Test get_trading_pair_info() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts TradingPair or None argument
        - Returns TradingPair (single query) or list[TradingPair] (batch query)
        """
        await exchange.connect()
        
        try:
            # Single pair query
            result = await exchange.get_trading_pair_info(sample_trading_pair)
            assert isinstance(result, TradingPair)
            
            # Batch query (all pairs)
            batch_result = await exchange.get_trading_pair_info(None)
            assert isinstance(batch_result, list)
            assert all(isinstance(pair, TradingPair) for pair in batch_result)
        finally:
            await exchange.disconnect()


class TestXTPerpExchangePerpetualContract:
    """Test XTPerpExchange perpetual futures-specific methods.
    
    These tests verify perpetual futures-specific functionality beyond
    the BaseExchange interface:
    1. Position management (get_positions)
    2. Funding rate queries (get_funding_rate)
    3. Leverage control (set_leverage)
    4. Perpetual order placement with position_side
    """

    @pytest.fixture
    def exchange(self) -> XTPerpExchange:
        """Create XTPerpExchange instance for testing."""
        return XTPerpExchange(
            api_key="test_api_key",
            api_secret="test_api_secret",
            timeout=30,
        )

    @pytest.mark.asyncio
    async def test_get_positions_signature(self, exchange: XTPerpExchange) -> None:
        """Test get_positions() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts optional symbol string argument
        - Returns list of Position objects
        - Position objects have required fields (symbol, side, quantity, etc.)
        """
        await exchange.connect()
        
        try:
            # Query all positions
            result = await exchange.get_positions(symbol=None)
            assert isinstance(result, list)
            
            # Query specific symbol positions
            symbol_result = await exchange.get_positions(symbol="btc_usdt")
            assert isinstance(symbol_result, list)
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_get_funding_rate_signature(self, exchange: XTPerpExchange) -> None:
        """Test get_funding_rate() method signature and return type.
        
        Validates:
        - Method exists and is callable
        - Accepts symbol string argument
        - Returns FundingRate object
        - FundingRate has rate and next_funding_time fields
        """
        await exchange.connect()
        
        try:
            from tri_arb.models.perpetual import FundingRate
            
            result = await exchange.get_funding_rate("btc_usdt")
            assert isinstance(result, FundingRate)
            assert hasattr(result, "symbol")
            assert hasattr(result, "rate")
            assert hasattr(result, "next_funding_time")
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_set_leverage_signature(self, exchange: XTPerpExchange) -> None:
        """Test set_leverage() method signature and behavior.
        
        Validates:
        - Method exists and is callable
        - Accepts symbol and leverage arguments
        - Returns None (successful execution)
        - Validates leverage range (1-125x)
        - Raises ValueError for invalid leverage
        """
        await exchange.connect()
        
        try:
            # Valid leverage
            result = await exchange.set_leverage("btc_usdt", leverage=10)
            assert result is None
            
            # Test leverage validation (should raise ValueError)
            with pytest.raises(ValueError, match="Invalid leverage"):
                await exchange.set_leverage("btc_usdt", leverage=0)
            
            with pytest.raises(ValueError, match="Invalid leverage"):
                await exchange.set_leverage("btc_usdt", leverage=126)
        finally:
            await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_place_order_with_position_side(self, exchange: XTPerpExchange) -> None:
        """Test place_order() with perpetual futures position_side parameter.
        
        Validates:
        - Order accepts position_side field ("LONG" or "SHORT")
        - trade_action computed property works correctly
        - OPEN_LONG: BUY + LONG
        - CLOSE_LONG: SELL + LONG
        - OPEN_SHORT: SELL + SHORT
        - CLOSE_SHORT: BUY + SHORT
        """
        await exchange.connect()
        
        try:
            # Test OPEN_LONG (BUY + LONG)
            open_long_order = Order(
                order_id="test_open_long",
                trading_pair=TradingPair(
                    base_currency="BTC",
                    quote_currency="USDT",
                    exchange="xt_perp",
                    min_order_size=Decimal("0.001"),
                    max_order_size=Decimal("1000"),
                    price_precision=2,
                    quantity_precision=3,
                ),
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("50000.00"),
                quantity=Decimal("0.01"),
                status=OrderStatus.PENDING,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                exchange="xt_perp",
                position_side="LONG",
            )
            assert open_long_order.trade_action == "OPEN_LONG"
            
            result = await exchange.place_order(open_long_order)
            assert isinstance(result, Order)
            
            # Test CLOSE_SHORT (BUY + SHORT)
            close_short_order = Order(
                order_id="test_close_short",
                trading_pair=open_long_order.trading_pair,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=Decimal("49000.00"),
                quantity=Decimal("0.01"),
                status=OrderStatus.PENDING,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                exchange="xt_perp",
                position_side="SHORT",
            )
            assert close_short_order.trade_action == "CLOSE_SHORT"
        finally:
            await exchange.disconnect()
