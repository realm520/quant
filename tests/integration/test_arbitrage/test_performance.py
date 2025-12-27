"""
Performance benchmark tests for arbitrage monitoring.

Tests NFR-001, NFR-002, NFR-003 performance requirements.
"""

import asyncio
import tracemalloc
from decimal import Decimal

import pytest

from tri_arb.arbitrage import ArbitrageMonitor
from tri_arb.arbitrage.config import MonitorConfig
from tri_arb.models.exchange import Ticker


class MockExchange:
    """Mock exchange for performance testing."""

    def __init__(self, tickers: list[Ticker]):
        self.tickers = tickers

    async def get_ticker(self, symbol=None):
        """Mock get_ticker implementation."""
        if symbol is None:
            return self.tickers
        return [t for t in self.tickers if t.symbol == symbol][0]


def generate_test_tickers(count: int) -> list[Ticker]:
    """Generate test ticker data."""
    tickers = []

    # Add some triangular opportunities
    triangles = [
        ("BTC", "ETH", "USDT"),
        ("BNB", "BTC", "USDT"),
        ("SOL", "ETH", "USDT"),
    ]

    for base, mid, quote in triangles:
        tickers.extend(
            [
                Ticker(
                    symbol=f"{base}/{quote}",
                    bid=Decimal("100"),
                    ask=Decimal("101"),
                    bid_volume=Decimal("1.0"),
                    ask_volume=Decimal("1.0"),
                ),
                Ticker(
                    symbol=f"{mid}/{quote}",
                    bid=Decimal("50"),
                    ask=Decimal("51"),
                    bid_volume=Decimal("1.0"),
                    ask_volume=Decimal("1.0"),
                ),
                Ticker(
                    symbol=f"{mid}/{base}",
                    bid=Decimal("0.5"),
                    ask=Decimal("0.51"),
                    bid_volume=Decimal("1.0"),
                    ask_volume=Decimal("1.0"),
                ),
            ]
        )

    # Fill remaining with random pairs
    remaining = count - len(tickers)
    for i in range(remaining):
        tickers.append(
            Ticker(
                symbol=f"COIN{i}/USDT",
                bid=Decimal(f"{1000 + i}"),
                ask=Decimal(f"{1000 + i + 1}"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            )
        )

    return tickers[:count]


class TestPerformanceRequirements:
    """Test performance requirements (NFR-001, 002, 003)."""

    def test_nfr_001_scan_time_under_1_second(self, benchmark):
        """NFR-001: Full market scan completes in < 1 second."""
        tickers = generate_test_tickers(500)
        config = MonitorConfig()
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(tickers)

        # Benchmark async function using new event loop
        def scan():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(monitor.scan_once())
            finally:
                loop.close()

        # Run benchmark
        benchmark.pedantic(scan, rounds=10, iterations=1)

        # Verify performance
        assert benchmark.stats["mean"] < 1.0  # < 1 second

    @pytest.mark.asyncio
    async def test_nfr_002_handles_500_plus_pairs(self):
        """NFR-002: System handles ≥ 500 trading pairs."""
        tickers = generate_test_tickers(550)  # Test with 550 pairs
        config = MonitorConfig()
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(tickers)

        opportunities = await monitor.scan_once()

        # Should complete without error
        assert isinstance(opportunities, list)

    @pytest.mark.asyncio
    async def test_nfr_003_memory_under_100mb(self):
        """NFR-003: Memory usage stays < 100MB during operation."""
        tickers = generate_test_tickers(500)
        config = MonitorConfig(run_mode="realtime", refresh_interval_seconds=1)
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(tickers)

        # Start memory tracking
        tracemalloc.start()

        # Run 5 scan iterations
        iterations = 0
        memory_samples = []

        async for _opportunities in monitor.scan_realtime():
            current, peak = tracemalloc.get_traced_memory()
            memory_samples.append(peak / 1024 / 1024)  # Convert to MB

            iterations += 1
            if iterations >= 5:
                monitor._shutdown_requested = True
                break

        tracemalloc.stop()

        # Check peak memory
        max_memory_mb = max(memory_samples)
        assert (
            max_memory_mb < 100.0
        ), f"Peak memory {max_memory_mb:.2f} MB exceeds 100 MB"

    @pytest.mark.asyncio
    async def test_path_finding_performance(self, benchmark):
        """Test path finding algorithm performance."""
        from tri_arb.arbitrage.path_finder import find_arbitrage_paths

        tickers = generate_test_tickers(500)

        # Benchmark path finding only
        benchmark.pedantic(
            lambda: find_arbitrage_paths(tickers=tickers), rounds=10, iterations=1
        )

        # Should complete in < 100ms
        assert benchmark.stats["mean"] < 0.1

    def test_profit_calculation_performance(self, benchmark):
        """Test profit calculation performance."""
        from tri_arb.arbitrage.calculator import calculate_profit_rate
        from tri_arb.models.arbitrage import TradingPath

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
                bid=Decimal("0.05"),
                ask=Decimal("0.0501"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600"),
                ask=Decimal("2601"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
        }

        # Benchmark calculation using new event loop
        def calc():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    calculate_profit_rate(
                        path=path, tickers=tickers, fee_rate=Decimal("0.001")
                    )
                )
            finally:
                loop.close()

        benchmark.pedantic(calc, rounds=100, iterations=1)

        # Should complete in < 10ms
        assert benchmark.stats["mean"] < 0.01
