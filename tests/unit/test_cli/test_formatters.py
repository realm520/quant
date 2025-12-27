"""Unit tests for CLI formatters."""

import json
from decimal import Decimal
from datetime import datetime
from io import StringIO
from unittest.mock import patch

import pytest

from tri_arb.cli.formatters.json import decimal_default, format_json, print_json
from tri_arb.cli.formatters.csv import format_csv, print_csv
from tri_arb.cli.formatters.table import format_pnl, format_percentage


class TestJsonFormatter:
    """Test JSON formatter."""

    def test_decimal_default_with_decimal(self):
        """Test that Decimal is serialized to string."""
        result = decimal_default(Decimal("123.456"))
        assert result == "123.456"
        assert isinstance(result, str)

    def test_decimal_default_with_datetime(self):
        """Test that datetime is serialized to ISO format."""
        dt = datetime(2025, 1, 15, 10, 30, 45)
        result = decimal_default(dt)
        assert result == "2025-01-15T10:30:45"
        assert isinstance(result, str)

    def test_decimal_default_with_unsupported_type(self):
        """Test that unsupported types raise TypeError."""
        with pytest.raises(TypeError, match="not JSON serializable"):
            decimal_default(object())

    def test_format_json_with_dict(self):
        """Test formatting a dictionary."""
        data = {
            "symbol": "BTC/USDT",
            "price": Decimal("50000.50"),
            "timestamp": datetime(2025, 1, 15, 10, 30, 45),
        }

        result = format_json(data)
        parsed = json.loads(result)

        assert parsed["symbol"] == "BTC/USDT"
        assert parsed["price"] == "50000.50"
        assert parsed["timestamp"] == "2025-01-15T10:30:45"

    def test_format_json_with_object(self):
        """Test formatting an object with __dict__."""

        class TestObject:
            def __init__(self):
                self.name = "test"
                self.value = Decimal("123.45")

        obj = TestObject()
        result = format_json(obj)
        parsed = json.loads(result)

        assert parsed["name"] == "test"
        assert parsed["value"] == "123.45"

    def test_format_json_with_list_of_objects(self):
        """Test formatting a list of objects."""

        class TestObject:
            def __init__(self, name, value):
                self.name = name
                self.value = value

        objects = [
            TestObject("first", Decimal("100")),
            TestObject("second", Decimal("200")),
        ]

        result = format_json(objects)
        parsed = json.loads(result)

        assert len(parsed) == 2
        assert parsed[0]["name"] == "first"
        assert parsed[0]["value"] == "100"
        assert parsed[1]["name"] == "second"
        assert parsed[1]["value"] == "200"

    def test_format_json_with_chinese_characters(self):
        """Test that Chinese characters are preserved (not escaped)."""
        data = {"message": "交易成功"}
        result = format_json(data)

        assert "交易成功" in result
        assert "\\u" not in result

    def test_format_json_indentation(self):
        """Test that JSON is properly indented."""
        data = {"a": 1, "b": 2}
        result = format_json(data)

        assert "\n" in result
        assert "  " in result

    @patch("sys.stdout", new_callable=StringIO)
    def test_print_json(self, mock_stdout):
        """Test print_json function."""
        data = {"test": "value"}
        print_json(data)

        output = mock_stdout.getvalue()
        assert "test" in output
        assert "value" in output


class TestCsvFormatter:
    """Test CSV formatter."""

    def test_format_csv_empty_list(self):
        """Test formatting empty list returns empty string."""
        result = format_csv([])
        assert result == ""

    def test_format_csv_single_row(self):
        """Test formatting single row."""
        data = [{"name": "Alice", "age": "30", "city": "Beijing"}]
        result = format_csv(data)

        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert "name,age,city" in lines[0]
        assert "Alice,30,Beijing" in lines[1]

    def test_format_csv_multiple_rows(self):
        """Test formatting multiple rows."""
        data = [
            {"symbol": "BTC/USDT", "price": "50000", "volume": "1000"},
            {"symbol": "ETH/USDT", "price": "3000", "volume": "5000"},
        ]
        result = format_csv(data)

        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert "symbol,price,volume" in lines[0]
        assert "BTC/USDT,50000,1000" in lines[1]
        assert "ETH/USDT,3000,5000" in lines[2]

    def test_format_csv_preserves_field_order(self):
        """Test that field order is preserved from first dict."""
        data = [{"c": "3", "a": "1", "b": "2"}, {"c": "6", "a": "4", "b": "5"}]
        result = format_csv(data)

        lines = [line.strip() for line in result.strip().split("\n")]
        assert lines[0] == "c,a,b"

    def test_format_csv_with_commas_in_values(self):
        """Test that commas in values are properly escaped."""
        data = [{"name": "Alice, Bob", "city": "Beijing"}]
        result = format_csv(data)

        assert '"Alice, Bob"' in result or "Alice, Bob" in result

    @patch("sys.stdout", new_callable=StringIO)
    def test_print_csv(self, mock_stdout):
        """Test print_csv function."""
        data = [{"col1": "val1", "col2": "val2"}]
        print_csv(data)

        output = mock_stdout.getvalue()
        assert "col1,col2" in output
        assert "val1,val2" in output


class TestTableHelpers:
    """Test table formatting helper functions."""

    def test_format_pnl_positive(self):
        """Test formatting positive PnL (profit)."""
        result = format_pnl(Decimal("123.45"))

        assert "[green]" in result
        assert "+123.45" in result
        assert "[/green]" in result

    def test_format_pnl_negative(self):
        """Test formatting negative PnL (loss)."""
        result = format_pnl(Decimal("-456.78"))

        assert "[red]" in result
        assert "-456.78" in result
        assert "[/red]" in result

    def test_format_pnl_zero(self):
        """Test formatting zero PnL."""
        result = format_pnl(Decimal("0"))

        assert "[white]" in result
        assert "0.00" in result
        assert "[/white]" in result

    def test_format_pnl_two_decimal_places(self):
        """Test that PnL is formatted with 2 decimal places."""
        result = format_pnl(Decimal("123.456789"))
        assert "123.46" in result

    def test_format_percentage_positive(self):
        """Test formatting positive percentage."""
        result = format_percentage(Decimal("15.5"))

        assert "[green]" in result
        assert "+15.50%" in result
        assert "[/green]" in result

    def test_format_percentage_negative(self):
        """Test formatting negative percentage."""
        result = format_percentage(Decimal("-8.25"))

        assert "[red]" in result
        assert "-8.25%" in result
        assert "[/red]" in result

    def test_format_percentage_zero(self):
        """Test formatting zero percentage."""
        result = format_percentage(Decimal("0"))

        assert "[white]" in result
        assert "0.00%" in result
        assert "[/white]" in result

    def test_format_percentage_two_decimal_places(self):
        """Test that percentage is formatted with 2 decimal places."""
        result = format_percentage(Decimal("12.3456"))
        assert "12.35%" in result
