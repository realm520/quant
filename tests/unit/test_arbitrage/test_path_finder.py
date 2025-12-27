"""
Unit tests for path finding algorithm.

Tests edge cases and boundary conditions for triangular path discovery.
"""

from decimal import Decimal

import pytest

from tri_arb.arbitrage.path_finder import find_arbitrage_paths
from tri_arb.models.exchange import Ticker


class TestPathFinderEdgeCases:
    """Test edge cases for path finding algorithm."""

    def test_empty_ticker_list_raises_error(self):
        """Empty ticker list should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            find_arbitrage_paths(tickers=[])

    def test_single_trading_pair_no_paths(self):
        """Single pair cannot form triangular arbitrage."""
        tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            )
        ]

        paths = find_arbitrage_paths(tickers=tickers)
        assert paths == []

    def test_two_currencies_no_closed_loop(self):
        """Two currencies cannot form closed triangular path."""
        tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600"),
                ask=Decimal("2601"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        ]

        paths = find_arbitrage_paths(tickers=tickers)
        assert paths == []

    def test_three_currencies_finds_triangular_path(self):
        """Three currencies should form valid triangular paths."""
        tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600"),
                ask=Decimal("2601"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        ]

        paths = find_arbitrage_paths(tickers=tickers)
        assert len(paths) > 0

        # All paths should be closed loops
        for path in paths:
            assert path.is_closed_loop is True

    def test_whitelist_filters_paths(self):
        """Whitelist should filter paths by starting currency."""
        tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600"),
                ask=Decimal("2601"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        ]

        # Filter to only USDT starting paths
        paths = find_arbitrage_paths(tickers=tickers, base_currencies=["USDT"])

        for path in paths:
            assert path.start_currency == "USDT"

    def test_empty_whitelist_means_all_currencies(self):
        """Empty whitelist should allow all starting currencies (per spec: empty=all)."""
        tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600"),
                ask=Decimal("2601"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        ]

        paths_all = find_arbitrage_paths(tickers=tickers, base_currencies=None)
        paths_empty = find_arbitrage_paths(tickers=tickers, base_currencies=[])

        # Per spec: empty whitelist = all currencies (same as None)
        assert len(paths_empty) == len(paths_all)

        # None whitelist should find all paths
        assert len(paths_all) > 0

    def test_invalid_ticker_symbols_skipped(self):
        """Tickers with invalid symbol format should be skipped."""
        tickers = [
            Ticker(
                symbol="INVALID_SYMBOL",  # No "/" separator
                bid=Decimal("100"),
                ask=Decimal("101"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        ]

        # Should not crash, just skip invalid ticker
        paths = find_arbitrage_paths(tickers=tickers)
        assert isinstance(paths, list)

    def test_multiple_paths_for_same_currencies(self):
        """
        Multiple paths with same trading pairs should be deduplicated.

        Before deduplication: 6 paths (2 per starting currency × 3 currencies)
        After deduplication: 1 path (same trading pair set)

        Example:
        - USDT→BTC→ETH→USDT uses {BTC/USDT, ETH/BTC, ETH/USDT}
        - BTC→ETH→USDT→BTC uses {ETH/BTC, ETH/USDT, BTC/USDT} (same set)
        - ETH→USDT→BTC→ETH uses {ETH/USDT, BTC/USDT, ETH/BTC} (same set)

        All three use the same trading pairs, so only one is kept.
        """
        tickers = [
            # Triangle 1: USDT -> BTC -> ETH -> USDT
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600"),
                ask=Decimal("2601"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.051"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        ]

        paths = find_arbitrage_paths(tickers=tickers)

        # After deduplication, should return only 1 unique path
        # (same trading pair set regardless of starting currency)
        assert len(paths) == 1

        # Verify the path uses the expected trading pairs
        path = paths[0]
        pair_set = set(path.trading_pairs)
        expected_pairs = {"BTC/USDT", "ETH/USDT", "ETH/BTC"}
        assert pair_set == expected_pairs
