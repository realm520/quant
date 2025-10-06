"""
Unit tests for core data models.

Tests validation rules for all trading models including:
- TradingPair: Currency validation, order size constraints
- Price: Bid/ask validation, computed properties
- OrderBook: Sorting validation
- Order: State machine, type validation
- Trade: Execution data validation
- ArbitrageOpportunity: Triangle validation
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tri_arb.core.models import (
    ArbitrageOpportunity,
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    OrderType,
    Price,
    Trade,
    TradingPair,
)


# ============================================================================
# TradingPair Model Tests
# ============================================================================

@pytest.fixture
def valid_trading_pair_data():
    """Valid TradingPair data for successful creation."""
    return {
        "base_currency": "BTC",
        "quote_currency": "USDT",
        "exchange": "binance",
        "min_order_size": Decimal("0.001"),
        "max_order_size": Decimal("100.0"),
        "price_precision": 2,
        "quantity_precision": 8,
    }


class TestTradingPairCreation:
    """Test successful TradingPair creation."""

    def test_create_with_valid_data(self, valid_trading_pair_data):
        """Should create TradingPair with all valid fields."""
        pair = TradingPair(**valid_trading_pair_data)

        assert pair.base_currency == "BTC"
        assert pair.quote_currency == "USDT"
        assert pair.exchange == "binance"
        assert pair.min_order_size == Decimal("0.001")
        assert pair.max_order_size == Decimal("100.0")
        assert pair.price_precision == 2
        assert pair.quantity_precision == 8


class TestCurrencyValidation:
    """Test currency code validation and uppercase conversion."""

    def test_uppercase_conversion_base_currency(self, valid_trading_pair_data):
        """Should convert base_currency to uppercase."""
        valid_trading_pair_data["base_currency"] = "btc"
        pair = TradingPair(**valid_trading_pair_data)

        assert pair.base_currency == "BTC"

    def test_base_currency_too_short(self, valid_trading_pair_data):
        """Should raise ValidationError for base_currency < 1 char (empty string)."""
        valid_trading_pair_data["base_currency"] = ""

        with pytest.raises(ValidationError) as exc_info:
            TradingPair(**valid_trading_pair_data)

        assert "base_currency" in str(exc_info.value)


class TestOrderSizeValidation:
    """Test order size validation rules."""

    def test_min_order_size_zero(self, valid_trading_pair_data):
        """Should raise ValidationError for min_order_size = 0."""
        valid_trading_pair_data["min_order_size"] = Decimal("0")

        with pytest.raises(ValidationError) as exc_info:
            TradingPair(**valid_trading_pair_data)

        assert "min_order_size" in str(exc_info.value)

    def test_max_less_than_min(self, valid_trading_pair_data):
        """Should raise ValidationError when max_order_size < min_order_size."""
        valid_trading_pair_data["min_order_size"] = Decimal("10.0")
        valid_trading_pair_data["max_order_size"] = Decimal("5.0")

        with pytest.raises(ValidationError) as exc_info:
            TradingPair(**valid_trading_pair_data)

        assert "max_order_size" in str(exc_info.value)


# ============================================================================
# Price Model Tests
# ============================================================================

class TestPriceCreation:
    """Test Price model creation and validation."""

    def test_price_creation_valid(self, valid_trading_pair_data):
        """Test valid Price creation."""
        trading_pair = TradingPair(**valid_trading_pair_data)
        timestamp = datetime.utcnow()

        price = Price(
            trading_pair=trading_pair,
            bid_price=Decimal("50000.00"),
            ask_price=Decimal("50010.00"),
            bid_volume=Decimal("1.5"),
            ask_volume=Decimal("2.0"),
            timestamp=timestamp,
            exchange="binance"
        )

        assert price.trading_pair == trading_pair
        assert price.bid_price == Decimal("50000.00")
        assert price.ask_price == Decimal("50010.00")

    def test_ask_greater_than_bid_validation(self, valid_trading_pair_data):
        """Test ask_price must be > bid_price."""
        trading_pair = TradingPair(**valid_trading_pair_data)

        with pytest.raises(ValidationError) as exc_info:
            Price(
                trading_pair=trading_pair,
                bid_price=Decimal("50000.00"),
                ask_price=Decimal("50000.00"),
                bid_volume=Decimal("1.5"),
                ask_volume=Decimal("2.0"),
                timestamp=datetime.utcnow(),
                exchange="binance"
            )

        assert "ask_price" in str(exc_info.value)


class TestPriceComputedProperties:
    """Test Price computed properties."""

    def test_mid_price_computed_property(self, valid_trading_pair_data):
        """Test mid_price = (bid_price + ask_price) / 2."""
        trading_pair = TradingPair(**valid_trading_pair_data)

        price = Price(
            trading_pair=trading_pair,
            bid_price=Decimal("50000.00"),
            ask_price=Decimal("50010.00"),
            bid_volume=Decimal("1.5"),
            ask_volume=Decimal("2.0"),
            timestamp=datetime.utcnow(),
            exchange="binance"
        )

        assert price.mid_price == Decimal("50005.00")

    def test_is_stale_property_fresh_data(self, valid_trading_pair_data):
        """Test is_stale property - fresh data (< 5 minutes)."""
        trading_pair = TradingPair(**valid_trading_pair_data)
        recent_timestamp = datetime.utcnow() - timedelta(minutes=3)

        price = Price(
            trading_pair=trading_pair,
            bid_price=Decimal("50000.00"),
            ask_price=Decimal("50010.00"),
            bid_volume=Decimal("1.5"),
            ask_volume=Decimal("2.0"),
            timestamp=recent_timestamp,
            exchange="binance"
        )

        assert price.is_stale is False

    def test_is_stale_property_stale_data(self, valid_trading_pair_data):
        """Test is_stale property - stale data (> 5 minutes)."""
        trading_pair = TradingPair(**valid_trading_pair_data)
        old_timestamp = datetime.utcnow() - timedelta(minutes=6)

        price = Price(
            trading_pair=trading_pair,
            bid_price=Decimal("50000.00"),
            ask_price=Decimal("50010.00"),
            bid_volume=Decimal("1.5"),
            ask_volume=Decimal("2.0"),
            timestamp=old_timestamp,
            exchange="binance"
        )

        assert price.is_stale is True


# ============================================================================
# OrderBook Model Tests
# ============================================================================

class TestOrderBookSorting:
    """Test OrderBook sorting validation."""

    def test_bids_descending_order(self, valid_trading_pair_data):
        """Test bids must be sorted descending by price."""
        trading_pair = TradingPair(**valid_trading_pair_data)

        orderbook = OrderBook(
            trading_pair=trading_pair,
            bids=[(Decimal("100"), Decimal("1.0")), (Decimal("99"), Decimal("2.0"))],
            asks=[(Decimal("101"), Decimal("1.0")), (Decimal("102"), Decimal("2.0"))],
            timestamp=datetime.utcnow(),
            exchange="binance"
        )

        assert orderbook.bids[0][0] > orderbook.bids[1][0]

    def test_asks_ascending_order(self, valid_trading_pair_data):
        """Test asks must be sorted ascending by price."""
        trading_pair = TradingPair(**valid_trading_pair_data)

        orderbook = OrderBook(
            trading_pair=trading_pair,
            bids=[(Decimal("100"), Decimal("1.0")), (Decimal("99"), Decimal("2.0"))],
            asks=[(Decimal("101"), Decimal("1.0")), (Decimal("102"), Decimal("2.0"))],
            timestamp=datetime.utcnow(),
            exchange="binance"
        )

        assert orderbook.asks[0][0] < orderbook.asks[1][0]

    def test_bids_wrong_order_validation(self, valid_trading_pair_data):
        """Test bids in wrong order raises ValidationError."""
        trading_pair = TradingPair(**valid_trading_pair_data)

        with pytest.raises(ValidationError) as exc_info:
            OrderBook(
                trading_pair=trading_pair,
                bids=[(Decimal("99"), Decimal("1.0")), (Decimal("100"), Decimal("2.0"))],
                asks=[(Decimal("101"), Decimal("1.0"))],
                timestamp=datetime.utcnow(),
                exchange="binance"
            )

        assert "bids" in str(exc_info.value).lower()


# ============================================================================
# Order Model Tests
# ============================================================================

@pytest.fixture
def sample_trading_pair(valid_trading_pair_data):
    """Create a sample trading pair for testing."""
    return TradingPair(**valid_trading_pair_data)


@pytest.fixture
def valid_limit_order_data(sample_trading_pair):
    """Valid limit order data."""
    return {
        "order_id": "order_123",
        "trading_pair": sample_trading_pair,
        "side": OrderSide.BUY,
        "order_type": OrderType.LIMIT,
        "price": Decimal("50000.00"),
        "quantity": Decimal("0.1"),
        "status": OrderStatus.PENDING,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "exchange": "binance",
    }


class TestOrderCreation:
    """Test Order creation."""

    def test_order_creation_with_valid_limit_order(self, valid_limit_order_data):
        """Test creating a valid limit order."""
        order = Order(**valid_limit_order_data)
        assert order.order_id == "order_123"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.LIMIT
        assert order.price == Decimal("50000.00")
        assert order.quantity == Decimal("0.1")


class TestOrderPriceValidation:
    """Test Order price validation."""

    def test_limit_order_requires_price(self, valid_limit_order_data):
        """Test that limit orders must have a price."""
        valid_limit_order_data["price"] = None
        with pytest.raises(ValidationError) as exc_info:
            Order(**valid_limit_order_data)

        assert "price" in str(exc_info.value).lower()


# ============================================================================
# Trade Model Tests
# ============================================================================

@pytest.fixture
def valid_trade_data(sample_trading_pair):
    """Valid trade data."""
    return {
        "trade_id": "trade_789",
        "order_id": "order_123",
        "trading_pair": sample_trading_pair,
        "side": OrderSide.BUY,
        "price": Decimal("50000.00"),
        "quantity": Decimal("0.1"),
        "fee": Decimal("5.00"),
        "fee_currency": "USDT",
        "timestamp": datetime.utcnow(),
        "exchange": "binance",
    }


class TestTradeCreation:
    """Test Trade creation."""

    def test_trade_creation_with_valid_data(self, valid_trade_data):
        """Test creating a valid trade."""
        trade = Trade(**valid_trade_data)
        assert trade.trade_id == "trade_789"
        assert trade.order_id == "order_123"
        assert trade.price == Decimal("50000.00")
        assert trade.quantity == Decimal("0.1")
        assert trade.fee == Decimal("5.00")


class TestTradePriceValidation:
    """Test Trade price validation."""

    def test_trade_price_must_be_positive(self, valid_trade_data):
        """Test that trade price must be > 0."""
        valid_trade_data["price"] = Decimal("0")
        with pytest.raises(ValidationError):
            Trade(**valid_trade_data)


# ============================================================================
# ArbitrageOpportunity Model Tests
# ============================================================================

class TestArbitrageOpportunityCreation:
    """Test ArbitrageOpportunity creation."""

    def test_arbitrage_opportunity_creation(self, sample_trading_pair):
        """Test creating an arbitrage opportunity."""
        # Create 3 trading pairs for the triangle
        pair1 = sample_trading_pair
        pair2 = TradingPair(
            base_currency="ETH",
            quote_currency="USDT",
            exchange="binance",
            min_order_size=Decimal("0.01"),
            max_order_size=Decimal("100.0"),
            price_precision=2,
            quantity_precision=8,
        )
        pair3 = TradingPair(
            base_currency="BTC",
            quote_currency="ETH",
            exchange="binance",
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("100.0"),
            price_precision=6,
            quantity_precision=8,
        )

        # Create 3 prices
        price1 = Price(
            trading_pair=pair1,
            bid_price=Decimal("50000.00"),
            ask_price=Decimal("50010.00"),
            bid_volume=Decimal("1.0"),
            ask_volume=Decimal("1.0"),
            timestamp=datetime.utcnow(),
            exchange="binance"
        )
        price2 = Price(
            trading_pair=pair2,
            bid_price=Decimal("3000.00"),
            ask_price=Decimal("3005.00"),
            bid_volume=Decimal("10.0"),
            ask_volume=Decimal("10.0"),
            timestamp=datetime.utcnow(),
            exchange="binance"
        )
        price3 = Price(
            trading_pair=pair3,
            bid_price=Decimal("16.5"),
            ask_price=Decimal("16.6"),
            bid_volume=Decimal("1.0"),
            ask_volume=Decimal("1.0"),
            timestamp=datetime.utcnow(),
            exchange="binance"
        )

        opportunity = ArbitrageOpportunity(
            opportunity_id="opp_001",
            path=[pair1, pair2, pair3],
            prices=[price1, price2, price3],
            estimated_profit=Decimal("0.5"),
            estimated_profit_amount=Decimal("250.00"),
            required_capital=Decimal("10000.00"),
            slippage_tolerance=Decimal("0.003"),
            detected_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=30),
            exchange="binance",
            is_viable=True
        )

        assert opportunity.opportunity_id == "opp_001"
        assert len(opportunity.path) == 3
        assert len(opportunity.prices) == 3


class TestArbitrageTriangleValidation:
    """Test arbitrage triangle path validation."""

    def test_path_must_have_three_pairs(self, sample_trading_pair):
        """Test that path must contain exactly 3 trading pairs."""
        pair1 = sample_trading_pair
        price1 = Price(
            trading_pair=pair1,
            bid_price=Decimal("50000.00"),
            ask_price=Decimal("50010.00"),
            bid_volume=Decimal("1.0"),
            ask_volume=Decimal("1.0"),
            timestamp=datetime.utcnow(),
            exchange="binance"
        )

        # Try with only 2 pairs
        with pytest.raises(ValidationError) as exc_info:
            ArbitrageOpportunity(
                opportunity_id="opp_001",
                path=[pair1, pair1],
                prices=[price1, price1, price1],
                estimated_profit=Decimal("0.5"),
                estimated_profit_amount=Decimal("250.00"),
                required_capital=Decimal("10000.00"),
                slippage_tolerance=Decimal("0.003"),
                detected_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(seconds=30),
                exchange="binance"
            )

        assert "path" in str(exc_info.value).lower()
