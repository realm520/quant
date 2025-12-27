"""Contract test for BaseExchange interface.

Verifies that all exchange adapters correctly implement the BaseExchange
interface and adhere to the contract requirements.
"""

import inspect

import pytest

from tri_arb.exchanges.base import BaseExchange
from tri_arb.exchanges.binance import BinanceExchange
from tri_arb.exchanges.okx import OKXExchange


@pytest.mark.contract
class TestBaseExchangeContract:
    """Test that all exchanges implement BaseExchange contract."""

    @pytest.fixture
    def exchange_implementations(self):
        """Get all exchange implementations to test.

        Returns:
            List of exchange classes to verify
        """
        return [BinanceExchange, OKXExchange]

    def test_exchange_inherits_base(self, exchange_implementations):
        """Verify all exchanges inherit from BaseExchange.

        All exchange implementations must inherit from BaseExchange
        to ensure consistent interface.
        """
        for exchange_class in exchange_implementations:
            assert issubclass(
                exchange_class, BaseExchange
            ), f"{exchange_class.__name__} must inherit from BaseExchange"

    def test_exchange_implements_required_methods(self, exchange_implementations):
        """Verify all exchanges implement required abstract methods.

        All exchange implementations must implement all abstract methods
        defined in BaseExchange.
        """
        # Get abstract methods from BaseExchange
        abstract_methods = {
            name
            for name, method in inspect.getmembers(BaseExchange, inspect.isfunction)
            if getattr(method, "__isabstractmethod__", False)
        }

        for exchange_class in exchange_implementations:
            # Get implemented methods
            implemented_methods = {
                name
                for name, method in inspect.getmembers(exchange_class, inspect.ismethod)
            }

            # Verify all abstract methods are implemented
            missing_methods = abstract_methods - implemented_methods
            assert (
                not missing_methods
            ), f"{exchange_class.__name__} missing methods: {missing_methods}"

    def test_exchange_method_signatures(self, exchange_implementations):
        """Verify method signatures match BaseExchange.

        All exchange implementations must have method signatures that
        match the base class interface.
        """
        # Define expected method signatures
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

        for exchange_class in exchange_implementations:
            for method_name, expected_params in expected_signatures.items():
                # Get method signature
                method = getattr(exchange_class, method_name, None)
                assert (
                    method is not None
                ), f"{exchange_class.__name__} missing method: {method_name}"

                # Get method parameters
                sig = inspect.signature(method)
                params = [p.name for p in sig.parameters.values() if p.name != "self"]

                # Verify parameters match (at least the required ones)
                for expected_param in expected_params:
                    assert (
                        expected_param in params
                    ), f"{exchange_class.__name__}.{method_name} missing parameter: {expected_param}"


@pytest.mark.contract
@pytest.mark.asyncio
class TestBinanceExchangeContract:
    """Test Binance exchange implementation contract."""

    @pytest.fixture
    def binance_exchange(self):
        """Create Binance exchange instance for testing.

        Returns:
            BinanceExchange instance
        """
        return BinanceExchange(
            name="binance_test", api_key="test_key", api_secret="test_secret"
        )

    async def test_connect_disconnect(self, binance_exchange):
        """Test connect and disconnect methods.

        Verifies that connect/disconnect work without errors.
        Note: This is a placeholder test for MVP scaffold.
        """
        # Test connect
        await binance_exchange.connect()
        assert binance_exchange.is_connected

        # Test disconnect
        await binance_exchange.disconnect()
        assert not binance_exchange.is_connected

    async def test_exchange_initialization(self, binance_exchange):
        """Test exchange initialization.

        Verifies that exchange initializes with correct attributes.
        """
        assert binance_exchange.name == "binance_test"
        assert binance_exchange.api_key == "test_key"
        assert binance_exchange.api_secret == "test_secret"

    async def test_method_return_types(self, binance_exchange, sample_trading_pair):
        """Test that methods return correct types.

        Verifies that exchange methods return expected types.
        Note: This is a placeholder test for MVP scaffold.
        """
        from tri_arb.core.models import Order, OrderBook, OrderSide, Price

        # Connect first
        await binance_exchange.connect()

        # Test get_ticker returns Price
        ticker = await binance_exchange.get_ticker(sample_trading_pair)
        assert isinstance(ticker, Price)

        # Test get_orderbook returns OrderBook
        orderbook = await binance_exchange.get_orderbook(sample_trading_pair)
        assert isinstance(orderbook, OrderBook)

        # Test get_trade_history returns list
        trades = await binance_exchange.get_trade_history(sample_trading_pair)
        assert isinstance(trades, list)

        # Test place_order returns Order
        from decimal import Decimal

        order = Order(
            id="test_order",
            trading_pair=sample_trading_pair,
            side=OrderSide.BUY,
            quantity=Decimal("1.0"),
            price=Decimal("50000.0"),
        )
        placed_order = await binance_exchange.place_order(order)
        assert isinstance(placed_order, Order)

        # Test cancel_order returns bool
        result = await binance_exchange.cancel_order("test_order_id")
        assert isinstance(result, bool)

        # Test get_order_status returns Order
        order_status = await binance_exchange.get_order_status("test_order_id")
        assert isinstance(order_status, Order)


@pytest.mark.contract
@pytest.mark.asyncio
class TestOKXExchangeContract:
    """Test OKX exchange implementation contract."""

    @pytest.fixture
    def okx_exchange(self):
        """Create OKX exchange instance for testing.

        Returns:
            OKXExchange instance
        """
        return OKXExchange(
            name="okx_test",
            api_key="test_key",
            api_secret="test_secret",
            passphrase="test_passphrase",
        )

    async def test_connect_disconnect(self, okx_exchange):
        """Test connect and disconnect methods.

        Verifies that connect/disconnect work without errors.
        Note: This is a placeholder test for MVP scaffold.
        """
        # Test connect
        await okx_exchange.connect()
        assert okx_exchange.is_connected

        # Test disconnect
        await okx_exchange.disconnect()
        assert not okx_exchange.is_connected

    async def test_exchange_initialization(self, okx_exchange):
        """Test exchange initialization.

        Verifies that exchange initializes with correct attributes.
        """
        assert okx_exchange.name == "okx_test"
        assert okx_exchange.api_key == "test_key"
        assert okx_exchange.api_secret == "test_secret"
        assert okx_exchange.passphrase == "test_passphrase"

    async def test_method_return_types(self, okx_exchange, sample_trading_pair):
        """Test that methods return correct types.

        Verifies that exchange methods return expected types.
        Note: This is a placeholder test for MVP scaffold.
        """
        from tri_arb.core.models import Order, OrderBook, OrderSide, Price

        # Connect first
        await okx_exchange.connect()

        # Test get_ticker returns Price
        ticker = await okx_exchange.get_ticker(sample_trading_pair)
        assert isinstance(ticker, Price)

        # Test get_orderbook returns OrderBook
        orderbook = await okx_exchange.get_orderbook(sample_trading_pair)
        assert isinstance(orderbook, OrderBook)

        # Test get_trade_history returns list
        trades = await okx_exchange.get_trade_history(sample_trading_pair)
        assert isinstance(trades, list)


@pytest.mark.contract
class TestExchangeFactory:
    """Test exchange factory contract."""

    def test_factory_registration(self):
        """Test that exchanges can be registered with factory.

        Verifies that factory registration system works correctly.
        """
        from tri_arb.exchanges.factory import ExchangeFactory

        factory = ExchangeFactory()

        # Register exchanges
        factory.register("binance", BinanceExchange)
        factory.register("okx", OKXExchange)

        # Verify registration
        assert factory.is_registered("binance")
        assert factory.is_registered("okx")
        assert not factory.is_registered("unknown")

    def test_factory_creation(self):
        """Test that factory can create exchange instances.

        Verifies that factory creates correct exchange instances.
        """
        from tri_arb.exchanges.factory import ExchangeFactory

        factory = ExchangeFactory()

        # Register and create Binance
        factory.register("binance", BinanceExchange)
        binance = factory.create("binance", api_key="key", api_secret="secret")
        assert isinstance(binance, BinanceExchange)
        assert binance.name == "binance"

        # Register and create OKX
        factory.register("okx", OKXExchange)
        okx = factory.create(
            "okx", api_key="key", api_secret="secret", passphrase="pass"
        )
        assert isinstance(okx, OKXExchange)
        assert okx.name == "okx"
