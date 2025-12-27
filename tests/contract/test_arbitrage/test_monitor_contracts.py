"""
Contract tests for ArbitrageMonitor API.

These tests verify that ArbitrageMonitor implements the contract
defined in specs/004-xt-get-ticker/contracts/monitor_api.md.

IMPORTANT: These tests MUST FAIL until implementation is complete.
"""

from datetime import datetime
from decimal import Decimal

import pytest

# These imports will fail until implementation exists
from tri_arb.arbitrage import ArbitrageMonitor
from tri_arb.arbitrage.config import MonitorConfig
from tri_arb.models.exchange import Ticker


class MockExchange:
    """Mock exchange for contract testing."""

    def __init__(self, tickers: list[Ticker]):
        self.tickers = tickers

    async def get_ticker(self, symbol=None):
        """Mock get_ticker implementation."""
        if symbol is None:
            return self.tickers
        return [t for t in self.tickers if t.symbol == symbol][0]


class TestArbitrageMonitorContract:
    """Test ArbitrageMonitor API contract compliance."""

    @pytest.fixture
    def test_tickers(self):
        """Create test tickers with profitable path."""
        return [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2700"),
                ask=Decimal("2701"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0"),
            ),
            Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.051"),
                ask=Decimal("0.052"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0"),
            ),
        ]

    @pytest.fixture
    def config(self):
        """Create default monitor configuration."""
        return MonitorConfig(
            min_profit_threshold=0.5,
            fee_rate_per_trade=0.1,
            base_currency_whitelist=["USDT"],
            refresh_interval_seconds=10,
            run_mode="once",
        )

    @pytest.fixture
    def monitor(self, config, test_tickers):
        """Create ArbitrageMonitor instance with mock exchange."""
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(test_tickers)
        return monitor

    @pytest.mark.asyncio
    async def test_scan_once_returns_list(self, monitor):
        """Contract: scan_once() returns list[ArbitrageOpportunity]."""
        opportunities = await monitor.scan_once()
        assert isinstance(opportunities, list)

    @pytest.mark.asyncio
    async def test_scan_once_sorted_by_profit_desc(self, monitor):
        """Contract: scan_once() returns opportunities sorted by profit rate DESC."""
        opportunities = await monitor.scan_once()
        if len(opportunities) > 1:
            for i in range(len(opportunities) - 1):
                assert (
                    opportunities[i].expected_profit_rate
                    >= opportunities[i + 1].expected_profit_rate
                )

    @pytest.mark.asyncio
    async def test_scan_once_filters_by_threshold(self, monitor):
        """Contract: scan_once() only returns opportunities >= min_profit_threshold."""
        opportunities = await monitor.scan_once()
        threshold = monitor.config.min_profit_threshold
        for opp in opportunities:
            assert opp.expected_profit_rate >= threshold

    @pytest.mark.asyncio
    async def test_scan_once_empty_list_when_no_opportunities(self, test_tickers):
        """Contract: scan_once() returns empty list when no opportunities found."""
        config = MonitorConfig(
            min_profit_threshold=99.0,  # Impossibly high threshold
            fee_rate_per_trade=0.1,
            run_mode="once",
        )
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(test_tickers)
        opportunities = await monitor.scan_once()
        assert opportunities == []

    @pytest.mark.asyncio
    async def test_scan_once_performance_under_1_second(self, monitor):
        """Contract: scan_once() completes in < 1 second (NFR-001)."""
        start = datetime.utcnow()
        await monitor.scan_once()
        duration = (datetime.utcnow() - start).total_seconds()
        assert duration < 1.0

    @pytest.mark.asyncio
    async def test_scan_realtime_yields_lists(self, test_tickers):
        """Contract: scan_realtime() yields list[ArbitrageOpportunity]."""
        config = MonitorConfig(
            min_profit_threshold=0.5, refresh_interval_seconds=1, run_mode="realtime"
        )
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(test_tickers)

        count = 0
        async for opportunities in monitor.scan_realtime():
            assert isinstance(opportunities, list)
            count += 1
            if count >= 2:  # Test 2 iterations
                monitor._shutdown_requested = True
                break

    @pytest.mark.asyncio
    async def test_scan_realtime_requires_realtime_mode(self):
        """Contract: scan_realtime() requires config.run_mode == 'realtime'."""
        config = MonitorConfig(run_mode="once")
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")

        with pytest.raises(ValueError, match="realtime"):
            async for _ in monitor.scan_realtime():
                pass


class TestArbitrageMonitorExceptions:
    """Test exception handling contracts."""

    @pytest.mark.asyncio
    async def test_network_error_raised_after_retries(self, mocker):
        """Contract: NetworkError raised after 3 failed retries."""
        from tri_arb.arbitrage.exceptions import NetworkError

        config = MonitorConfig(run_mode="once")
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")

        # Mock network failure
        mocker.patch.object(
            monitor, "_fetch_tickers", side_effect=NetworkError("Network timeout")
        )

        with pytest.raises(NetworkError):
            await monitor.scan_once()

    @pytest.mark.asyncio
    async def test_validation_error_on_invalid_config(self):
        """Contract: ValidationError raised on invalid config."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MonitorConfig(min_profit_threshold=150.0, run_mode="once")  # Invalid: > 100
