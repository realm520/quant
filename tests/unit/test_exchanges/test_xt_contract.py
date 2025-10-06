"""Contract test for XT Exchange adapter.

Verifies that XTExchange correctly implements the BaseExchange interface
and adheres to contract requirements.

These tests MUST FAIL initially (TDD requirement) until XTExchange is implemented.
"""

import inspect

import pytest
import respx
from httpx import Response

from tri_arb.exchanges.base import BaseExchange

# This import will fail until XT Exchange is implemented
try:
    from tri_arb.exchanges.xt import XTExchange
    XT_EXCHANGE_AVAILABLE = True
except ImportError:
    XT_EXCHANGE_AVAILABLE = False
    # Create placeholder for type checking
    class XTExchange:  # type: ignore
        pass


@pytest.mark.contract
@pytest.mark.skipif(not XT_EXCHANGE_AVAILABLE, reason="XTExchange not yet implemented")
class TestXTExchangeContract:
    """Test that XTExchange implements BaseExchange contract."""

    def test_exchange_inherits_base(self):
        """Verify XTExchange inherits from BaseExchange.

        XTExchange must inherit from BaseExchange to ensure consistent
        interface across all exchange adapters.
        """
        assert issubclass(
            XTExchange, BaseExchange
        ), "XTExchange must inherit from BaseExchange"

    def test_exchange_implements_required_methods(self):
        """Verify XTExchange implements all required abstract methods.

        XTExchange must implement all 10 abstract methods defined in
        BaseExchange for complete functionality.
        """
        # Get abstract methods from BaseExchange
        abstract_methods = {
            name
            for name, method in inspect.getmembers(BaseExchange, inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        }

        # Get implemented methods from XTExchange
        implemented_methods = {
            name
            for name, method in inspect.getmembers(XTExchange, inspect.isfunction)
        }

        # Verify all abstract methods are implemented
        missing_methods = abstract_methods - implemented_methods
        assert (
            not missing_methods
        ), f"XTExchange missing methods: {missing_methods}"

    def test_exchange_method_signatures(self):
        """Verify XTExchange method signatures match BaseExchange.

        All method signatures must match the base class interface to
        ensure type compatibility and correct usage.
        """
        # Define expected method signatures (param names)
        expected_signatures = {
            "connect": [],
            "disconnect": [],
            "get_ticker": ["trading_pair"],
            "get_orderbook": ["trading_pair", "depth"],
            "place_order": ["order"],
            "cancel_order": ["order_id"],
            "get_order_status": ["order_id"],
            "get_trade_history": ["trading_pair", "limit"],
            "subscribe_ticker": ["trading_pair"],
            "subscribe_orderbook": ["trading_pair", "depth"],
        }

        for method_name, expected_params in expected_signatures.items():
            # Get method
            method = getattr(XTExchange, method_name, None)
            assert (
                method is not None
            ), f"XTExchange missing method: {method_name}"

            # Get method parameters
            sig = inspect.signature(method)
            params = [
                p.name for p in sig.parameters.values() if p.name != "self"
            ]

            # Verify parameters match (at least the required ones)
            for expected_param in expected_params:
                assert (
                    expected_param in params
                ), f"XTExchange.{method_name} missing parameter: {expected_param}"


@pytest.mark.contract
@pytest.mark.asyncio
@pytest.mark.skipif(not XT_EXCHANGE_AVAILABLE, reason="XTExchange not yet implemented")
class TestXTExchangeConnectionContract:
    """Test XT exchange connection lifecycle contract."""

    @pytest.fixture
    def xt_exchange(self):
        """Create XT exchange instance for testing.

        Returns:
            XTExchange instance with test credentials
        """
        return XTExchange(
            name="xt_test",
            api_key="test_key",
            api_secret="test_secret"
        )

    async def test_connect_disconnect(self, xt_exchange):
        """Test connect and disconnect methods.

        Verifies that connect/disconnect work without errors and properly
        manage connection state.
        """
        # Initially not connected
        assert not xt_exchange.is_connected

        # Test connect
        await xt_exchange.connect()
        assert xt_exchange.is_connected

        # Test disconnect
        await xt_exchange.disconnect()
        assert not xt_exchange.is_connected

    async def test_exchange_initialization(self, xt_exchange):
        """Test exchange initialization.

        Verifies that exchange initializes with correct attributes.
        """
        assert xt_exchange.name == "xt_test"
        assert xt_exchange.api_key == "test_key"
        assert xt_exchange.api_secret == "test_secret"

    async def test_double_connect_raises_error(self, xt_exchange):
        """Test that connecting twice raises error.

        Connecting an already-connected exchange should raise ValueError
        to prevent resource leaks.
        """
        await xt_exchange.connect()
        
        with pytest.raises(ValueError, match="Already connected"):
            await xt_exchange.connect()
        
        await xt_exchange.disconnect()

    async def test_disconnect_not_connected_raises_error(self, xt_exchange):
        """Test that disconnecting when not connected raises error.

        Disconnecting an unconnected exchange should raise ValueError
        for clear error indication.
        """
        with pytest.raises(ValueError, match="Not connected"):
            await xt_exchange.disconnect()


@pytest.mark.contract
@pytest.mark.asyncio
@pytest.mark.skipif(not XT_EXCHANGE_AVAILABLE, reason="XTExchange not yet implemented")
class TestXTExchangeMethodReturnTypes:
    """Test that XTExchange methods return correct types."""

    @pytest.fixture
    def mock_xt_api(self):
        """Mock XT API responses."""
        with respx.mock:
            # Mock ticker endpoint
            respx.get("https://sapi.xt.com/v4/public/ticker/price").mock(
                return_value=Response(200, json={"rc": 0, "result": {"c": "50000.00", "v": "100.5"}})
            )
            # Mock orderbook endpoint
            respx.get("https://sapi.xt.com/v4/public/depth").mock(
                return_value=Response(200, json={
                    "rc": 0,
                    "result": {
                        "bids": [["49000.00", "1.5"], ["48900.00", "2.0"]],
                        "asks": [["50100.00", "1.0"], ["50200.00", "1.5"]]
                    }
                })
            )
            # Mock place order endpoint
            respx.post("https://sapi.xt.com/v4/order").mock(
                return_value=Response(200, json={
                    "rc": 0,
                    "result": {"orderId": "12345", "status": "NEW"}
                })
            )
            # Mock cancel order endpoint
            respx.delete("https://sapi.xt.com/v4/order").mock(
                return_value=Response(200, json={"rc": 0, "result": {"status": "CANCELED"}})
            )
            # Mock get order status endpoint
            respx.get("https://sapi.xt.com/v4/order").mock(
                return_value=Response(200, json={
                    "rc": 0,
                    "result": {
                        "orderId": "12345",
                        "symbol": "btc_usdt",
                        "status": "FILLED",
                        "type": "LIMIT",
                        "side": "BUY",
                        "price": "50000.00",
                        "origQty": "1.0",
                        "time": 1609459200000
                    }
                })
            )
            # Mock trade history endpoint
            respx.get("https://sapi.xt.com/v4/trade").mock(
                return_value=Response(200, json={
                    "rc": 0,
                    "result": [
                        {
                            "id": "1",
                            "orderId": "12345",
                            "side": "BUY",
                            "price": "50000.00",
                            "qty": "1.0",
                            "commission": "0.1",
                            "commissionAsset": "USDT",
                            "time": 1609459200000
                        }
                    ]
                })
            )
            yield

    @pytest.fixture
    def xt_exchange(self, mock_xt_api):
        """Create connected XT exchange instance."""
        return XTExchange(
            name="xt_test",
            api_key="test_key",
            api_secret="test_secret"
        )

    async def test_get_ticker_returns_price(self, xt_exchange, sample_trading_pair):
        """Test get_ticker returns Price model.

        Verifies that get_ticker returns correct type for type safety.
        Note: This will use placeholder/mock data until real API integration.
        """
        from tri_arb.core.models import Price

        await xt_exchange.connect()
        ticker = await xt_exchange.get_ticker(sample_trading_pair)
        assert isinstance(ticker, Price)
        await xt_exchange.disconnect()

    async def test_get_orderbook_returns_orderbook(self, xt_exchange, sample_trading_pair):
        """Test get_orderbook returns OrderBook model.

        Verifies that get_orderbook returns correct type for type safety.
        Note: This will use placeholder/mock data until real API integration.
        """
        from tri_arb.core.models import OrderBook

        await xt_exchange.connect()
        orderbook = await xt_exchange.get_orderbook(sample_trading_pair)
        assert isinstance(orderbook, OrderBook)
        await xt_exchange.disconnect()

    async def test_get_trade_history_returns_list(self, xt_exchange, sample_trading_pair):
        """Test get_trade_history returns list.

        Verifies that get_trade_history returns list type (may be empty).
        """
        await xt_exchange.connect()
        trades = await xt_exchange.get_trade_history(sample_trading_pair)
        assert isinstance(trades, list)
        await xt_exchange.disconnect()

    async def test_place_order_returns_order(self, xt_exchange, sample_trading_pair):
        """Test place_order returns Order model.

        Verifies that place_order returns updated Order with exchange ID.
        """
        from tri_arb.core.models import Order, OrderSide, OrderType
        from decimal import Decimal
        from datetime import datetime

        await xt_exchange.connect()

        order = Order(
            order_id="test_order",
            trading_pair=sample_trading_pair,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1.0"),
            price=Decimal("50000.0"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            exchange="xt",
        )

        placed_order = await xt_exchange.place_order(order)
        assert isinstance(placed_order, Order)
        assert placed_order.order_id is not None
        
        await xt_exchange.disconnect()

    async def test_cancel_order_returns_bool(self, xt_exchange):
        """Test cancel_order returns boolean.

        Verifies that cancel_order returns True/False for success.
        """
        await xt_exchange.connect()
        result = await xt_exchange.cancel_order("test_order_id")
        assert isinstance(result, bool)
        await xt_exchange.disconnect()

    async def test_get_order_status_returns_order(self, xt_exchange):
        """Test get_order_status returns Order model.

        Verifies that get_order_status returns Order with status info.
        """
        from tri_arb.core.models import Order

        await xt_exchange.connect()
        order = await xt_exchange.get_order_status("test_order_id")
        assert isinstance(order, Order)
        await xt_exchange.disconnect()


@pytest.mark.contract
@pytest.mark.skipif(not XT_EXCHANGE_AVAILABLE, reason="XTExchange not yet implemented")
class TestXTExchangeFactoryIntegration:
    """Test XT exchange factory registration contract."""

    def test_factory_can_register_xt(self):
        """Test that XTExchange can be registered with factory.

        Verifies factory pattern compatibility.
        """
        from tri_arb.exchanges.factory import ExchangeFactory

        factory = ExchangeFactory()
        factory.register("xt", XTExchange)

        assert factory.is_registered("xt")

    def test_factory_can_create_xt(self):
        """Test that factory can create XTExchange instances.

        Verifies factory creates correct instance type.
        """
        from tri_arb.exchanges.factory import ExchangeFactory

        factory = ExchangeFactory()
        factory.register("xt", XTExchange)

        xt = factory.create("xt", api_key="key", api_secret="secret")
        assert isinstance(xt, XTExchange)
        assert xt.name == "xt"
        assert xt.api_key == "key"
        assert xt.api_secret == "secret"


@pytest.mark.contract
class TestXTExchangeImportability:
    """Test that XTExchange can be imported (implementation exists).
    
    This test should FAIL initially until XTExchange is implemented.
    """

    def test_xt_exchange_importable(self):
        """Test that XTExchange class can be imported.
        
        This is the first test that must pass - verifies the class exists.
        Expected to FAIL until src/tri_arb/exchanges/xt.py is created.
        """
        try:
            from tri_arb.exchanges.xt import XTExchange
            assert XTExchange is not None
        except ImportError as e:
            pytest.fail(f"XTExchange not yet implemented: {e}")

    def test_xt_exchange_in_exchanges_init(self):
        """Test that XTExchange is exported from exchanges package.
        
        Verifies that XTExchange is added to __all__ in exchanges/__init__.py
        """
        from tri_arb import exchanges
        
        # Check if XTExchange is in __all__ (if __all__ exists)
        if hasattr(exchanges, '__all__'):
            assert 'XTExchange' in exchanges.__all__, \
                "XTExchange should be in exchanges.__all__"
        
        # Check if XTExchange can be imported from exchanges
        assert hasattr(exchanges, 'XTExchange'), \
            "XTExchange should be importable from tri_arb.exchanges"
