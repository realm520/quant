"""Unit tests for CLI parameter validators."""

import pytest

from tri_arb.cli.utils.validators import (
    validate_symbol,
    validate_leverage,
    validate_interval,
    validate_limit,
    validate_price,
    validate_quantity,
)


class TestValidateSymbol:
    """Test symbol validation."""

    def test_valid_symbol_btc_usdt(self):
        """Test valid BTC/USDT symbol."""
        result = validate_symbol("BTC/USDT")
        assert result == "BTC/USDT"

    def test_valid_symbol_eth_btc(self):
        """Test valid ETH/BTC symbol."""
        result = validate_symbol("ETH/BTC")
        assert result == "ETH/BTC"

    def test_symbol_lowercase_converted_to_uppercase(self):
        """Test that lowercase symbol is converted to uppercase."""
        result = validate_symbol("btc/usdt")
        assert result == "BTC/USDT"

    def test_symbol_mixed_case_converted_to_uppercase(self):
        """Test that mixed case symbol is converted to uppercase."""
        result = validate_symbol("Btc/UsDt")
        assert result == "BTC/USDT"

    def test_symbol_with_spaces_trimmed(self):
        """Test that spaces are trimmed."""
        result = validate_symbol("  BTC/USDT  ")
        assert result == "BTC/USDT"

    def test_symbol_with_numbers(self):
        """Test symbols with numbers (e.g., USDT)."""
        result = validate_symbol("BTC/USDT")
        assert result == "BTC/USDT"

    def test_invalid_symbol_no_slash(self):
        """Test that symbol without slash is invalid."""
        with pytest.raises(ValueError, match="交易对格式无效"):
            validate_symbol("BTCUSDT")

    def test_invalid_symbol_multiple_slashes(self):
        """Test that symbol with multiple slashes is invalid."""
        with pytest.raises(ValueError, match="交易对格式无效"):
            validate_symbol("BTC/USDT/EUR")

    def test_invalid_symbol_empty_base(self):
        """Test that symbol with empty base is invalid."""
        with pytest.raises(ValueError, match="交易对格式无效"):
            validate_symbol("/USDT")

    def test_invalid_symbol_empty_quote(self):
        """Test that symbol with empty quote is invalid."""
        with pytest.raises(ValueError, match="交易对格式无效"):
            validate_symbol("BTC/")

    def test_invalid_symbol_too_short(self):
        """Test that symbol with too short parts is invalid."""
        with pytest.raises(ValueError, match="交易对格式无效"):
            validate_symbol("B/U")

    def test_invalid_symbol_too_long(self):
        """Test that symbol with too long parts is invalid."""
        with pytest.raises(ValueError, match="交易对格式无效"):
            validate_symbol("VERYLONGTOKEN/ANOTHERVERYLONGTOKEN")


class TestValidateLeverage:
    """Test leverage validation."""

    def test_valid_leverage_1(self):
        """Test minimum leverage of 1."""
        result = validate_leverage(1)
        assert result == 1

    def test_valid_leverage_10(self):
        """Test common leverage of 10."""
        result = validate_leverage(10)
        assert result == 10

    def test_valid_leverage_125(self):
        """Test maximum leverage of 125."""
        result = validate_leverage(125)
        assert result == 125

    def test_leverage_below_minimum(self):
        """Test that leverage below 1 is invalid."""
        with pytest.raises(ValueError, match="杠杆倍数超出范围"):
            validate_leverage(0)

    def test_leverage_above_maximum(self):
        """Test that leverage above 125 is invalid."""
        with pytest.raises(ValueError, match="杠杆倍数超出范围"):
            validate_leverage(126)

    def test_leverage_negative(self):
        """Test that negative leverage is invalid."""
        with pytest.raises(ValueError, match="杠杆倍数超出范围"):
            validate_leverage(-5)

    def test_leverage_not_integer(self):
        """Test that non-integer leverage is invalid."""
        with pytest.raises(ValueError, match="杠杆倍数必须是整数"):
            validate_leverage(10.5)

    def test_leverage_string_type(self):
        """Test that string type is invalid."""
        with pytest.raises(ValueError, match="杠杆倍数必须是整数"):
            validate_leverage("10")


class TestValidateInterval:
    """Test interval validation."""

    def test_valid_interval_1(self):
        """Test minimum interval of 1 second."""
        result = validate_interval(1)
        assert result == 1

    def test_valid_interval_5(self):
        """Test common interval of 5 seconds."""
        result = validate_interval(5)
        assert result == 5

    def test_valid_interval_60(self):
        """Test maximum interval of 60 seconds."""
        result = validate_interval(60)
        assert result == 60

    def test_interval_below_minimum(self):
        """Test that interval below 1 is invalid."""
        with pytest.raises(ValueError, match="刷新间隔超出范围"):
            validate_interval(0)

    def test_interval_above_maximum(self):
        """Test that interval above 60 is invalid."""
        with pytest.raises(ValueError, match="刷新间隔超出范围"):
            validate_interval(61)

    def test_interval_negative(self):
        """Test that negative interval is invalid."""
        with pytest.raises(ValueError, match="刷新间隔超出范围"):
            validate_interval(-1)

    def test_interval_not_integer(self):
        """Test that non-integer interval is invalid."""
        with pytest.raises(ValueError, match="刷新间隔必须是整数"):
            validate_interval(5.5)


class TestValidateLimit:
    """Test limit validation."""

    def test_valid_limit_5(self):
        """Test minimum limit of 5."""
        result = validate_limit(5)
        assert result == 5

    def test_valid_limit_10(self):
        """Test common limit of 10."""
        result = validate_limit(10)
        assert result == 10

    def test_valid_limit_50(self):
        """Test maximum limit of 50."""
        result = validate_limit(50)
        assert result == 50

    def test_limit_below_minimum(self):
        """Test that limit below 5 is invalid."""
        with pytest.raises(ValueError, match="档数超出范围"):
            validate_limit(4)

    def test_limit_above_maximum(self):
        """Test that limit above 50 is invalid."""
        with pytest.raises(ValueError, match="档数超出范围"):
            validate_limit(51)

    def test_limit_custom_range(self):
        """Test custom min/max range."""
        result = validate_limit(15, min_limit=10, max_limit=20)
        assert result == 15

    def test_limit_custom_range_below_min(self):
        """Test custom range validation - below min."""
        with pytest.raises(ValueError, match="档数超出范围"):
            validate_limit(5, min_limit=10, max_limit=20)

    def test_limit_custom_range_above_max(self):
        """Test custom range validation - above max."""
        with pytest.raises(ValueError, match="档数超出范围"):
            validate_limit(25, min_limit=10, max_limit=20)

    def test_limit_not_integer(self):
        """Test that non-integer limit is invalid."""
        with pytest.raises(ValueError, match="档数必须是整数"):
            validate_limit(10.5)


class TestValidatePrice:
    """Test price validation."""

    def test_valid_price_integer(self):
        """Test valid integer price."""
        result = validate_price(50000)
        assert result == 50000.0
        assert isinstance(result, float)

    def test_valid_price_float(self):
        """Test valid float price."""
        result = validate_price(50000.50)
        assert result == 50000.50
        assert isinstance(result, float)

    def test_price_none_allowed(self):
        """Test that None price is allowed (for market orders)."""
        result = validate_price(None)
        assert result is None

    def test_price_zero_invalid(self):
        """Test that zero price is invalid."""
        with pytest.raises(ValueError, match="价格必须大于 0"):
            validate_price(0)

    def test_price_negative_invalid(self):
        """Test that negative price is invalid."""
        with pytest.raises(ValueError, match="价格必须大于 0"):
            validate_price(-100)

    def test_price_string_invalid(self):
        """Test that string price is invalid."""
        with pytest.raises(ValueError, match="价格必须是数字"):
            validate_price("50000")


class TestValidateQuantity:
    """Test quantity validation."""

    def test_valid_quantity_integer(self):
        """Test valid integer quantity."""
        result = validate_quantity(10)
        assert result == 10.0
        assert isinstance(result, float)

    def test_valid_quantity_float(self):
        """Test valid float quantity."""
        result = validate_quantity(0.001)
        assert result == 0.001
        assert isinstance(result, float)

    def test_quantity_zero_invalid(self):
        """Test that zero quantity is invalid."""
        with pytest.raises(ValueError, match="数量必须大于 0"):
            validate_quantity(0)

    def test_quantity_negative_invalid(self):
        """Test that negative quantity is invalid."""
        with pytest.raises(ValueError, match="数量必须大于 0"):
            validate_quantity(-1)

    def test_quantity_string_invalid(self):
        """Test that string quantity is invalid."""
        with pytest.raises(ValueError, match="数量必须是数字"):
            validate_quantity("10")

    def test_quantity_very_small(self):
        """Test very small quantity (e.g., 0.00001 BTC)."""
        result = validate_quantity(0.00001)
        assert result == 0.00001
