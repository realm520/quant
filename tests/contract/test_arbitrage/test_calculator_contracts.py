"""
Contract tests for calculate_profit_rate() function.

These tests verify the profit calculation contract defined in
specs/004-xt-get-ticker/contracts/monitor_api.md.

IMPORTANT: These tests MUST FAIL until implementation is complete.
"""

from decimal import Decimal

import pytest

# These imports will fail until implementation exists
from tri_arb.arbitrage.calculator import calculate_profit_rate
from tri_arb.models.arbitrage import TradingPath
from tri_arb.models.exchange import Ticker


class TestCalculateProfitRateContract:
    """Test calculate_profit_rate() API contract."""

    @pytest.fixture
    def simple_path(self):
        """Create a simple triangular path."""
        return TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

    @pytest.fixture
    def tickers_dict(self):
        """Create ticker dictionary for testing."""
        return {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.0"),
                ask=Decimal("50001.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.0501"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600.0"),
                ask=Decimal("2601.0"),
                bid_volume=Decimal("100.0"),
                ask_volume=Decimal("100.0"),
            ),
        }

    @pytest.mark.asyncio
    async def test_returns_tuple_of_decimal_and_list(self, simple_path, tickers_dict):
        """Contract: Returns tuple[Decimal, list[dict]]."""
        result = await calculate_profit_rate(
            path=simple_path, tickers=tickers_dict, fee_rate=Decimal("0.001")
        )

        assert isinstance(result, tuple)
        assert len(result) == 2

        profit_rate, price_details = result
        assert isinstance(profit_rate, Decimal)
        assert isinstance(price_details, list)
        assert len(price_details) == 3

    @pytest.mark.asyncio
    async def test_price_details_structure(self, simple_path, tickers_dict):
        """Contract: price_details has correct structure."""
        _, price_details = await calculate_profit_rate(
            path=simple_path, tickers=tickers_dict, fee_rate=Decimal("0.001")
        )

        required_keys = {"type", "pair", "price"}
        for detail in price_details:
            assert isinstance(detail, dict)
            assert required_keys.issubset(detail.keys())
            assert detail["type"] in ["buy", "sell"]

    @pytest.mark.asyncio
    async def test_deducts_fees_correctly(self, simple_path, tickers_dict):
        """Contract: Deducts fees from each trade (1 - fee_rate)³."""
        fee_rate = Decimal("0.001")  # 0.1%

        profit_rate_with_fee, _ = await calculate_profit_rate(
            path=simple_path, tickers=tickers_dict, fee_rate=fee_rate
        )

        profit_rate_no_fee, _ = await calculate_profit_rate(
            path=simple_path, tickers=tickers_dict, fee_rate=Decimal("0.0")
        )

        # With fees should be lower
        assert profit_rate_with_fee < profit_rate_no_fee

    @pytest.mark.asyncio
    async def test_uses_decimal_for_precision(self, simple_path, tickers_dict):
        """Contract: Uses Decimal type for precision."""
        profit_rate, price_details = await calculate_profit_rate(
            path=simple_path, tickers=tickers_dict, fee_rate=Decimal("0.001")
        )

        assert isinstance(profit_rate, Decimal)
        for detail in price_details:
            # Price should be Decimal from Ticker
            assert isinstance(detail["price"], Decimal)

    @pytest.mark.asyncio
    async def test_raises_key_error_on_missing_ticker(self, simple_path):
        """Contract: Raises KeyError when ticker missing."""
        incomplete_tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.0"),
                ask=Decimal("50001.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            # Missing ETH/BTC and ETH/USDT
        }

        with pytest.raises(KeyError):
            await calculate_profit_rate(
                path=simple_path, tickers=incomplete_tickers, fee_rate=Decimal("0.001")
            )

    @pytest.mark.asyncio
    async def test_validates_fee_rate_range(self, simple_path, tickers_dict):
        """Contract: fee_rate must be in [0.0, 0.1] range."""
        # Valid fee rates should work
        await calculate_profit_rate(
            path=simple_path, tickers=tickers_dict, fee_rate=Decimal("0.0")
        )

        await calculate_profit_rate(
            path=simple_path, tickers=tickers_dict, fee_rate=Decimal("0.1")
        )

        # Invalid fee rate should fail
        with pytest.raises(ValueError, match="fee_rate"):
            await calculate_profit_rate(
                path=simple_path,
                tickers=tickers_dict,
                fee_rate=Decimal("0.15"),  # > 10%
            )

    @pytest.mark.asyncio
    async def test_performance_under_10ms(self, simple_path, tickers_dict):
        """Contract: Single calculation completes in < 10ms."""
        import time

        start = time.perf_counter()
        await calculate_profit_rate(
            path=simple_path, tickers=tickers_dict, fee_rate=Decimal("0.001")
        )
        duration = time.perf_counter() - start

        assert duration < 0.01  # < 10ms


class TestProfitCalculationFormula:
    """Test profit calculation formula correctness."""

    @pytest.mark.asyncio
    async def test_formula_matches_specification(self):
        """Contract: Implements formula from FR-004, FR-005."""
        # USDT -> BTC -> ETH -> USDT with simple prices
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("100"),
                ask=Decimal("100"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.5"),
                ask=Decimal("0.5"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("60"),
                ask=Decimal("60"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        fee_rate = Decimal("0.001")  # 0.1%

        profit_rate, _ = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=fee_rate
        )

        # Manual calculation:
        # Start: 100 USDT
        # Buy BTC/USDT @ 100: 100/100 = 1 BTC, after fee: 1 * 0.999 = 0.999 BTC
        # Buy ETH/BTC @ 0.5: 0.999/0.5 = 1.998 ETH, after fee: 1.998 * 0.999 = 1.996 ETH
        # Sell ETH/USDT @ 60: 1.996 * 60 = 119.76 USDT, after fee: 119.76 * 0.999 = 119.64 USDT
        # Profit rate: (119.64 - 100) / 100 * 100 = 19.64%

        expected = Decimal("19.64")
        assert abs(profit_rate - expected) < Decimal(
            "0.1"
        )  # Allow small rounding difference

    @pytest.mark.asyncio
    async def test_negative_profit_rate_possible(self):
        """Contract: Can return negative profit rate."""
        # Create unfavorable prices
        path = TradingPath(
            start_currency="USDT", trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("51000"),  # Large spread
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.06"),  # Large spread
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2600"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        profit_rate, _ = await calculate_profit_rate(
            path=path, tickers=tickers, fee_rate=Decimal("0.001")
        )

        # Should be negative due to spreads and fees
        assert profit_rate < Decimal("0")
