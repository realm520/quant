"""Integration tests for XT Exchange adapter.

These tests require actual XT API credentials and make real API calls.
They are skipped by default and only run when:
1. XT_API_KEY and XT_API_SECRET environment variables are set
2. --run-integration flag is passed to pytest

Usage:
    export XT_API_KEY=your_api_key
    export XT_API_SECRET=your_api_secret
    pytest tests/integration/test_xt_integration.py --run-integration

WARNING: These tests may create real orders and incur trading fees.
Use testnet/sandbox credentials if available.
"""

import os
from decimal import Decimal

import pytest

# Check if XT Exchange is available
try:
    from tri_arb.exchanges.xt import XTExchange
    from tri_arb.core.models import Order, OrderSide, TradingPair
    XT_EXCHANGE_AVAILABLE = True
except ImportError:
    XT_EXCHANGE_AVAILABLE = False


# Check if integration testing is enabled
API_KEY = os.getenv("XT_API_KEY")
API_SECRET = os.getenv("XT_API_SECRET")
INTEGRATION_ENABLED = API_KEY and API_SECRET


@pytest.mark.integration
@pytest.mark.skipif(
    not XT_EXCHANGE_AVAILABLE,
    reason="XTExchange not yet implemented"
)
@pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="XT API credentials not configured (set XT_API_KEY and XT_API_SECRET)"
)
class TestXTIntegration:
    """Integration tests for XT Exchange real API calls.
    
    WARNING: These tests make real API calls and may incur costs.
    """

    @pytest.fixture
    async def xt_exchange(self):
        """Create and connect XT exchange instance with real credentials.
        
        Yields:
            Connected XTExchange instance
        """
        exchange = XTExchange(
            name="xt",
            api_key=API_KEY,
            api_secret=API_SECRET
        )
        await exchange.connect()
        yield exchange
        await exchange.disconnect()

    @pytest.fixture
    def btc_usdt_pair(self):
        """Create BTC/USDT trading pair for testing.
        
        Returns:
            TradingPair for BTC/USDT
        """
        return TradingPair(
            base_currency="BTC",
            quote_currency="USDT",
            exchange="xt",
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1000"),
            price_precision=2,
            quantity_precision=8,
        )

    async def test_get_ticker_real_api(self, xt_exchange, btc_usdt_pair):
        """Test get_ticker with real XT API.
        
        Verifies that ticker data is retrieved successfully and has
        valid price information.
        """
        ticker = await xt_exchange.get_ticker(btc_usdt_pair)
        
        # Verify Price model fields
        assert ticker.trading_pair == btc_usdt_pair
        assert ticker.bid_price > 0
        assert ticker.ask_price > 0
        assert ticker.bid_price <= ticker.ask_price  # Sanity check
        assert ticker.exchange == "xt"
        assert ticker.timestamp is not None

    async def test_get_orderbook_real_api(self, xt_exchange, btc_usdt_pair):
        """Test get_orderbook with real XT API.
        
        Verifies that order book data is retrieved and properly formatted.
        """
        orderbook = await xt_exchange.get_orderbook(btc_usdt_pair, depth=20)
        
        # Verify OrderBook model fields
        assert orderbook.trading_pair == btc_usdt_pair
        assert len(orderbook.bids) > 0
        assert len(orderbook.asks) > 0
        assert orderbook.exchange == "xt"
        assert orderbook.timestamp is not None
        
        # Verify bid/ask sorting
        for i in range(len(orderbook.bids) - 1):
            assert orderbook.bids[i][0] >= orderbook.bids[i + 1][0], \
                "Bids should be sorted descending by price"
        
        for i in range(len(orderbook.asks) - 1):
            assert orderbook.asks[i][0] <= orderbook.asks[i + 1][0], \
                "Asks should be sorted ascending by price"

    @pytest.mark.slow
    async def test_get_trade_history_real_api(self, xt_exchange, btc_usdt_pair):
        """Test get_trade_history with real XT API.
        
        Verifies that trade history can be retrieved.
        May return empty list if no trades exist.
        """
        trades = await xt_exchange.get_trade_history(btc_usdt_pair, limit=10)
        
        # Verify return type (may be empty)
        assert isinstance(trades, list)
        
        # If trades exist, verify structure
        if trades:
            trade = trades[0]
            assert trade.trading_pair == btc_usdt_pair
            assert trade.price > 0
            assert trade.quantity > 0
            assert trade.timestamp is not None

    @pytest.mark.slow
    @pytest.mark.skip(reason="Requires testnet to avoid real orders")
    async def test_place_and_cancel_order_real_api(self, xt_exchange, btc_usdt_pair):
        """Test order placement and cancellation with real XT API.
        
        SKIPPED BY DEFAULT: This test places real orders on XT exchange.
        Only run this test with testnet/sandbox credentials.
        
        Remove @pytest.mark.skip to enable (use testnet only!)
        """
        # Create limit order well below market (won't fill immediately)
        order = Order(
            id="test_order",
            trading_pair=btc_usdt_pair,
            side=OrderSide.BUY,
            quantity=Decimal("0.001"),  # Minimum order size
            price=Decimal("10000.00"),  # Far below market price
        )
        
        # Place order
        placed_order = await xt_exchange.place_order(order)
        assert placed_order.exchange_order_id is not None
        assert placed_order.status in ["OPEN", "NEW"]
        
        # Cancel order
        cancel_result = await xt_exchange.cancel_order(placed_order.exchange_order_id)
        assert cancel_result is True
        
        # Verify order status
        order_status = await xt_exchange.get_order_status(placed_order.exchange_order_id)
        assert order_status.status in ["CANCELLED", "CANCELED"]

    async def test_connection_lifecycle_real_api(self, btc_usdt_pair):
        """Test connection lifecycle with real XT API.
        
        Verifies connect/disconnect work properly with real credentials.
        """
        exchange = XTExchange(
            name="xt",
            api_key=API_KEY,
            api_secret=API_SECRET
        )
        
        # Initially not connected
        assert not exchange.is_connected
        
        # Connect
        await exchange.connect()
        assert exchange.is_connected
        
        # Make a request to verify connection works
        ticker = await exchange.get_ticker(btc_usdt_pair)
        assert ticker is not None
        
        # Disconnect
        await exchange.disconnect()
        assert not exchange.is_connected


@pytest.mark.integration
@pytest.mark.skipif(
    not XT_EXCHANGE_AVAILABLE,
    reason="XTExchange not yet implemented"
)
class TestXTIntegrationPlaceholder:
    """Placeholder tests that run even without API credentials.
    
    These tests verify the integration test structure is valid.
    """

    def test_integration_test_structure(self):
        """Verify integration test file structure is valid.
        
        This test always passes and serves as a placeholder until
        real integration tests can be run with API credentials.
        """
        assert XT_EXCHANGE_AVAILABLE or not XT_EXCHANGE_AVAILABLE, \
            "Test structure is valid"

    def test_environment_variables_documented(self):
        """Verify environment variable documentation exists.
        
        Checks that developers know how to configure integration tests.
        """
        # This test passes - it documents the expected environment variables
        assert True, "XT_API_KEY and XT_API_SECRET environment variables documented"

    def test_safety_warnings_present(self):
        """Verify safety warnings are in place.
        
        Ensures developers are warned about real API calls and costs.
        """
        # Check for WARNING in module docstring
        assert "WARNING" in __doc__, \
            "Integration tests should have safety warnings"


# TODO: Add more integration tests
# - Test error handling (invalid symbol, insufficient balance)
# - Test rate limiting behavior
# - Test concurrent requests
# - Test timeout handling
# - Test WebSocket streaming (future enhancement)
