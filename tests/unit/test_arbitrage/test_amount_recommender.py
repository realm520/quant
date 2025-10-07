"""
Unit tests for amount recommender.

Tests smart amount calculation based on liquidity, profit, and risk.
"""

from decimal import Decimal

import pytest

from tri_arb.arbitrage.amount_recommender import (
    _calculate_min_liquidity_in_base,
    calculate_recommended_amount,
)
from tri_arb.models.arbitrage import TradingPath
from tri_arb.models.exchange import Ticker


class TestCalculateRecommendedAmount:
    """Test calculate_recommended_amount function."""

    def test_basic_calculation_with_sufficient_liquidity(self):
        """Test basic calculation with good liquidity."""
        # Setup: Path with decent liquidity
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("10"),  # 500k USDT liquidity
                ask_volume=Decimal("10")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("100"),
                ask_volume=Decimal("100")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("50"),  # 125k USDT liquidity
                ask_volume=Decimal("50")
            )
        }

        # Execute: 2% profit rate
        result = calculate_recommended_amount(
            path=path,
            tickers=tickers,
            profit_rate=Decimal("0.02"),  # 2%
            max_amount=Decimal("10000"),
            min_amount=Decimal("100"),
            liquidity_usage_rate=Decimal("0.3")
        )

        # Verify:
        # - Min liquidity: min(500k, ~5k, 125k) = ~5k
        # - 30% usage: ~1.5k
        # - Profit boost (2%): ~1.5x multiplier
        # - Result should be between min and max
        assert result >= Decimal("100")
        assert result <= Decimal("10000")
        assert result > Decimal("1000")  # Should be boosted above base

    def test_low_liquidity_limits_amount(self):
        """Test that low liquidity properly limits recommended amount."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")  # Must have 3 pairs
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("0.01"),  # Only 500 USDT liquidity
                ask_volume=Decimal("0.01")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("0.01"),
                ask_volume=Decimal("0.01")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("0.01"),
                ask_volume=Decimal("0.01")
            )
        }

        result = calculate_recommended_amount(
            path=path,
            tickers=tickers,
            profit_rate=Decimal("0.01"),
            max_amount=Decimal("10000"),
            min_amount=Decimal("100"),
            liquidity_usage_rate=Decimal("0.3")
        )

        # With only 500 USDT liquidity, 30% = 150
        # Should return min_amount due to low liquidity
        assert result == Decimal("100")

    def test_high_profit_increases_amount(self):
        """Test that higher profit rates lead to larger recommended amounts."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("100"),  # 5M USDT liquidity
                ask_volume=Decimal("100")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("100"),
                ask_volume=Decimal("100")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("100"),
                ask_volume=Decimal("100")
            )
        }

        # Calculate with low profit
        amount_low_profit = calculate_recommended_amount(
            path=path,
            tickers=tickers,
            profit_rate=Decimal("0.005"),  # 0.5%
            max_amount=Decimal("10000"),
            min_amount=Decimal("100"),
            liquidity_usage_rate=Decimal("0.3")
        )

        # Calculate with high profit
        amount_high_profit = calculate_recommended_amount(
            path=path,
            tickers=tickers,
            profit_rate=Decimal("0.05"),  # 5%
            max_amount=Decimal("10000"),
            min_amount=Decimal("100"),
            liquidity_usage_rate=Decimal("0.3")
        )

        # High profit should recommend larger amount
        assert amount_high_profit > amount_low_profit

    def test_respects_max_amount_limit(self):
        """Test that max_amount is never exceeded."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1000"),  # 50M USDT liquidity (huge)
                ask_volume=Decimal("1000")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("1000"),
                ask_volume=Decimal("1000")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("1000"),
                ask_volume=Decimal("1000")
            )
        }

        result = calculate_recommended_amount(
            path=path,
            tickers=tickers,
            profit_rate=Decimal("0.1"),  # 10% (huge profit)
            max_amount=Decimal("5000"),  # Strict limit
            min_amount=Decimal("100"),
            liquidity_usage_rate=Decimal("0.3")
        )

        # Should be capped at max_amount
        assert result == Decimal("5000")

    def test_respects_min_amount_limit(self):
        """Test that min_amount is enforced."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("0.0001"),  # Tiny liquidity
                ask_volume=Decimal("0.0001")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("0.0001"),
                ask_volume=Decimal("0.0001")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("0.0001"),
                ask_volume=Decimal("0.0001")
            )
        }

        result = calculate_recommended_amount(
            path=path,
            tickers=tickers,
            profit_rate=Decimal("0.001"),
            max_amount=Decimal("10000"),
            min_amount=Decimal("500"),  # High minimum
            liquidity_usage_rate=Decimal("0.3")
        )

        # Should return min_amount
        assert result == Decimal("500")

    def test_missing_ticker_returns_min_amount(self):
        """Test graceful handling when ticker is missing."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("10"),
                ask_volume=Decimal("10")
            )
            # Missing ETH/BTC ticker
        }

        result = calculate_recommended_amount(
            path=path,
            tickers=tickers,
            profit_rate=Decimal("0.02"),
            max_amount=Decimal("10000"),
            min_amount=Decimal("100"),
            liquidity_usage_rate=Decimal("0.3")
        )

        # Should return min_amount when data is incomplete
        assert result == Decimal("100")

    def test_multi_hop_path_uses_minimum_liquidity(self):
        """Test that multi-hop paths use the bottleneck liquidity."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("100"),  # Large: 5M USDT
                ask_volume=Decimal("100")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("10"),  # Bottleneck: ~25k USDT
                ask_volume=Decimal("10")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("100"),  # Large: 250k USDT
                ask_volume=Decimal("100")
            )
        }

        result = calculate_recommended_amount(
            path=path,
            tickers=tickers,
            profit_rate=Decimal("0.01"),
            max_amount=Decimal("50000"),
            min_amount=Decimal("100"),
            liquidity_usage_rate=Decimal("0.3")
        )

        # Should be limited by ETH/BTC bottleneck (~25k * 0.3 = ~7.5k)
        # But with profit boost, might be higher
        assert result < Decimal("20000")  # Well below non-bottleneck liquidity


class TestCalculateMinLiquidityInBase:
    """Test _calculate_min_liquidity_in_base helper function."""

    def test_single_pair_buy_direction(self):
        """Test liquidity calculation for buying base with quote."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")  # Buy BTC with USDT
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("10"),
                ask_volume=Decimal("5")  # We're buying, so use ask_volume
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("10"),
                ask_volume=Decimal("10")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("10"),
                ask_volume=Decimal("10")
            )
        }

        result = _calculate_min_liquidity_in_base(path=path, tickers=tickers)

        # Buying 5 BTC at 50001 = 250005 USDT
        assert result == Decimal("5") * Decimal("50001")

    def test_single_pair_sell_direction(self):
        """Test liquidity calculation for selling base for quote."""
        path = TradingPath(
            start_currency="BTC",
            trading_pairs=("BTC/USDT", "BTC/ETH", "ETH/USDT")  # Must have 3 pairs
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("10"),  # We're selling, so use bid_volume
                ask_volume=Decimal("5")
            ),
            "BTC/ETH": Ticker(
                symbol="BTC/ETH",
                bid=Decimal("20"),
                ask=Decimal("20.1"),
                bid_volume=Decimal("10"),
                ask_volume=Decimal("10")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("10"),
                ask_volume=Decimal("10")
            )
        }

        result = _calculate_min_liquidity_in_base(path=path, tickers=tickers)

        # Selling 10 BTC at 50000 = 500000 USDT (if base is BTC, convert to USDT)
        assert result == Decimal("10") * Decimal("50000")

    def test_missing_ticker_returns_zero(self):
        """Test that missing ticker returns zero liquidity."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("10"),
                ask_volume=Decimal("10")
            )
            # Missing ETH/BTC and ETH/USDT
        }

        result = _calculate_min_liquidity_in_base(path=path, tickers=tickers)

        assert result == Decimal("0")

    def test_multi_pair_returns_minimum(self):
        """Test that multi-pair path returns minimum liquidity."""
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )

        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("100"),
                ask_volume=Decimal("100")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("10"),  # Bottleneck
                ask_volume=Decimal("10")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2500"),
                ask=Decimal("2501"),
                bid_volume=Decimal("100"),
                ask_volume=Decimal("100")
            )
        }

        result = _calculate_min_liquidity_in_base(path=path, tickers=tickers)

        # Should be limited by smallest liquidity across path
        # ETH/BTC: 10 * 0.051 * 50000 ≈ 25500 (rough estimate)
        assert result > Decimal("0")
        assert result < Decimal("100000")  # Less than other pairs
