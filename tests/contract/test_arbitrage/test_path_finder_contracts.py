"""
Contract tests for find_arbitrage_paths() function.

These tests verify the path finding algorithm contract defined in
specs/004-xt-get-ticker/contracts/monitor_api.md.

IMPORTANT: These tests MUST FAIL until implementation is complete.
"""

from decimal import Decimal

import pytest

# These imports will fail until implementation exists
from tri_arb.arbitrage.path_finder import find_arbitrage_paths
from tri_arb.models.arbitrage import TradingPath
from tri_arb.models.exchange import Ticker


class TestFindArbitragePathsContract:
    """Test find_arbitrage_paths() API contract."""

    @pytest.fixture
    def valid_tickers(self):
        """Create valid ticker data for testing."""
        return [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.0"),
                ask=Decimal("50001.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600.0"),
                ask=Decimal("2601.0"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0"),
            ),
            Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.0501"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0"),
            ),
        ]

    def test_returns_list_of_trading_paths(self, valid_tickers):
        """Contract: find_arbitrage_paths() returns list[TradingPath]."""
        paths = find_arbitrage_paths(tickers=valid_tickers)
        assert isinstance(paths, list)
        for path in paths:
            assert isinstance(path, TradingPath)

    def test_all_paths_are_closed_loops(self, valid_tickers):
        """Contract: All returned paths have is_closed_loop == True."""
        paths = find_arbitrage_paths(tickers=valid_tickers)
        for path in paths:
            assert path.is_closed_loop is True

    def test_all_paths_have_3_pairs(self, valid_tickers):
        """Contract: All paths have exactly 3 trading pairs."""
        paths = find_arbitrage_paths(tickers=valid_tickers)
        for path in paths:
            assert len(path.trading_pairs) == 3

    def test_filters_by_base_currency_whitelist(self, valid_tickers):
        """Contract: Respects base_currency_whitelist filter."""
        paths = find_arbitrage_paths(tickers=valid_tickers, base_currencies=["USDT"])
        for path in paths:
            assert path.start_currency == "USDT"

    def test_empty_list_when_whitelist_excludes_all(self, valid_tickers):
        """Contract: Returns empty list when whitelist excludes all currencies."""
        paths = find_arbitrage_paths(
            tickers=valid_tickers, base_currencies=["XRP"]  # Not in tickers
        )
        assert paths == []

    def test_raises_value_error_on_empty_tickers(self):
        """Contract: Raises ValueError when tickers is empty."""
        with pytest.raises(ValueError, match="empty"):
            find_arbitrage_paths(tickers=[])

    def test_performance_500_pairs_under_100ms(self):
        """Contract: Processes 500 pairs in < 100ms (NFR-002)."""
        import time

        # Generate 500 ticker pairs
        tickers = []
        for i in range(500):
            tickers.append(
                Ticker(
                    symbol=f"COIN{i}/USDT",
                    bid=Decimal(f"{1000 + i}.0"),
                    ask=Decimal(f"{1000 + i + 1}.0"),
                    bid_volume=Decimal("1.0"),
                    ask_volume=Decimal("1.0"),
                )
            )

        start = time.perf_counter()
        find_arbitrage_paths(tickers=tickers)
        duration = time.perf_counter() - start

        assert duration < 0.1  # < 100ms


class TestPathFindingAlgorithm:
    """Test DFS algorithm characteristics."""

    def test_dfs_depth_limited_to_3(self):
        """Contract: DFS depth is limited to 3 steps."""
        # Create a chain of 5 pairs: A->B->C->D->E
        tickers = [
            Ticker(
                symbol="B/A",
                bid=Decimal("2.0"),
                ask=Decimal("2.1"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="C/B",
                bid=Decimal("3.0"),
                ask=Decimal("3.1"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="D/C",
                bid=Decimal("4.0"),
                ask=Decimal("4.1"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="E/D",
                bid=Decimal("5.0"),
                ask=Decimal("5.1"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="A/E",  # Close the loop after 5 steps
                bid=Decimal("1.0"),
                ask=Decimal("1.1"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        ]

        paths = find_arbitrage_paths(tickers=tickers)

        # Should not find 5-step path (depth limit = 3)
        assert all(len(p.trading_pairs) == 3 for p in paths)

    def test_finds_triangular_arbitrage(self):
        """Contract: Finds standard triangular arbitrage (3 currencies)."""
        tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.0"),
                ask=Decimal("50001.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.0501"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600.0"),
                ask=Decimal("2601.0"),
                bid_volume=Decimal("100.0"),
                ask_volume=Decimal("100.0"),
            ),
        ]

        paths = find_arbitrage_paths(tickers=tickers)

        # Should find USDT -> BTC -> ETH -> USDT
        assert len(paths) > 0

        # Check one path is the expected triangle
        found_triangle = any(
            set(p.trading_pairs) == {"BTC/USDT", "ETH/BTC", "ETH/USDT"} for p in paths
        )
        assert found_triangle
