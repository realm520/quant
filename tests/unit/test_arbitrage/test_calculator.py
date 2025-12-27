"""
Unit tests for profit rate calculator.

Tests precision, edge cases, and boundary conditions.
"""

from decimal import Decimal

import pytest

from tri_arb.arbitrage.calculator import calculate_profit_rate
from tri_arb.models.arbitrage import TradingPath
from tri_arb.models.exchange import Ticker


class TestCalculatorPrecision:
    """Test calculation precision and accuracy."""

    @pytest.mark.asyncio
    async def test_decimal_vs_float_precision(self):
        """Decimal should provide better precision than float."""
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.123456789"),
                ask=Decimal("50001.123456789"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.052123456789"),
                ask=Decimal("0.052223456789"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2700.123456789"),
                ask=Decimal("2701.123456789"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        profit_rate, _ = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=Decimal("0.001")
        )

        # Should be Decimal type
        assert isinstance(profit_rate, Decimal)

        # Should maintain high precision (> 8 decimal places)
        assert len(str(profit_rate).split(".")[-1]) >= 8


class TestCalculatorEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_zero_fee_rate(self):
        """Zero fee rate should give higher profit than with fees."""
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.051"),
                ask=Decimal("0.052"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2700"),
                ask=Decimal("2701"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        profit_no_fee, _ = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=Decimal("0.0")
        )

        profit_with_fee, _ = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=Decimal("0.001")
        )

        assert profit_no_fee > profit_with_fee

    @pytest.mark.asyncio
    async def test_high_fee_rate_reduces_profit(self):
        """High fee rate should significantly reduce profit."""
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.051"),
                ask=Decimal("0.052"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2700"),
                ask=Decimal("2701"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        profit_low_fee, _ = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=Decimal("0.001")  # 0.1%
        )

        profit_high_fee, _ = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=Decimal("0.05")  # 5%
        )

        # High fee should significantly reduce profit
        assert profit_high_fee < profit_low_fee
        assert profit_low_fee - profit_high_fee > Decimal("10")  # > 10% difference

    @pytest.mark.asyncio
    async def test_fee_rate_boundary_max(self):
        """Maximum fee rate (10%) should be accepted."""
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.051"),
                ask=Decimal("0.052"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2700"),
                ask=Decimal("2701"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        # Should not raise error
        profit, _ = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=Decimal("0.1")  # 10%
        )

        assert isinstance(profit, Decimal)

    @pytest.mark.asyncio
    async def test_invalid_fee_rate_too_high(self):
        """Fee rate > 10% should raise ValueError."""
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.051"),
                ask=Decimal("0.052"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2700"),
                ask=Decimal("2701"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        with pytest.raises(ValueError, match="fee_rate"):
            await calculate_profit_rate(
                path=path, tickers=tickers, fee_rate=Decimal("0.15")  # 15% > 10%
            )

    @pytest.mark.asyncio
    async def test_missing_ticker_raises_key_error(self):
        """Missing ticker in path should raise KeyError."""
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        incomplete_tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            )
            # Missing ETH/BTC and ETH/USDT
        }

        with pytest.raises(KeyError):
            await calculate_profit_rate(
                path=path, tickers=incomplete_tickers, fee_rate=Decimal("0.001")
            )

    @pytest.mark.asyncio
    async def test_price_details_structure(self):
        """Price details should have correct structure and count."""
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.051"),
                ask=Decimal("0.052"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2700"),
                ask=Decimal("2701"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        _, price_details = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=Decimal("0.001")
        )

        # Should have exactly 3 price entries
        assert len(price_details) == 3

        # Each should have required keys
        for detail in price_details:
            assert "type" in detail
            assert "pair" in detail
            assert "price" in detail
            assert detail["type"] in ["buy", "sell"]
            assert isinstance(detail["price"], Decimal)
