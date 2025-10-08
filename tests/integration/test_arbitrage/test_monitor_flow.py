"""
Integration tests for complete arbitrage monitoring flow.

Tests end-to-end scenarios from quickstart.md with mocked exchange.
"""

from decimal import Decimal

import pytest

from tri_arb.arbitrage import ArbitrageMonitor
from tri_arb.arbitrage.config import MonitorConfig
from tri_arb.models.exchange import Ticker


class MockExchange:
    """Mock exchange for testing."""
    
    def __init__(self, tickers: list[Ticker]):
        self.tickers = tickers
    
    async def get_ticker(self, symbol=None):
        """Mock get_ticker implementation."""
        if symbol is None:
            return self.tickers
        return [t for t in self.tickers if t.symbol == symbol][0]


@pytest.fixture
def valid_tickers():
    """Create 500 valid tickers for testing."""
    tickers = []
    
    # Add triangular arbitrage opportunity: USDT -> BTC -> ETH -> USDT
    # To be profitable: (1/50001) * (1/0.051) * 2700 * 0.999^3 > 1
    # = 1.059 > 1, profit ~5.9%
    tickers.extend([
        Ticker(
            symbol="BTC/USDT",
            bid=Decimal("50000"),
            ask=Decimal("50001"),
            bid_volume=Decimal("1.0"),
            ask_volume=Decimal("1.0")
        ),
        Ticker(
            symbol="ETH/USDT",
            bid=Decimal("2700"),  # Higher to make arbitrage profitable
            ask=Decimal("2701"),
            bid_volume=Decimal("10.0"),
            ask_volume=Decimal("10.0")
        ),
        Ticker(
            symbol="ETH/BTC",
            bid=Decimal("0.051"),  # Profitable arbitrage
            ask=Decimal("0.052"),
            bid_volume=Decimal("10.0"),
            ask_volume=Decimal("10.0")
        ),
    ])
    
    # Add 497 more random pairs to reach 500
    for i in range(497):
        tickers.append(
            Ticker(
                symbol=f"COIN{i}/USDT",
                bid=Decimal(f"{1000 + i}"),
                ask=Decimal(f"{1000 + i + 1}"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            )
        )
    
    return tickers


class TestMonitorFlowIntegration:
    """Test complete monitoring flow scenarios."""
    
    @pytest.mark.asyncio
    async def test_scenario_1_single_scan_default_config(self, valid_tickers):
        """Scenario 1: Single scan with default configuration."""
        config = MonitorConfig()
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(valid_tickers)
        
        opportunities = await monitor.scan_once()
        
        # Should find at least the BTC-ETH-USDT triangle
        assert len(opportunities) > 0
        
        # Verify sorted by profit rate descending
        for i in range(len(opportunities) - 1):
            assert opportunities[i].expected_profit_rate >= opportunities[i + 1].expected_profit_rate
        
        # Verify all above threshold
        for opp in opportunities:
            assert opp.expected_profit_rate >= config.min_profit_threshold
    
    @pytest.mark.asyncio
    async def test_scenario_2_custom_profit_threshold(self, valid_tickers):
        """Scenario 2: Custom profit threshold (1%)."""
        config = MonitorConfig(min_profit_threshold=1.0)
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(valid_tickers)
        
        opportunities = await monitor.scan_once()
        
        # All opportunities must be >= 1%
        for opp in opportunities:
            assert opp.expected_profit_rate >= Decimal("1.0")
    
    @pytest.mark.asyncio
    async def test_scenario_3_base_currency_whitelist(self, valid_tickers):
        """Scenario 3: Base currency whitelist (USDT only)."""
        config = MonitorConfig(base_currency_whitelist=["USDT"])
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(valid_tickers)
        
        opportunities = await monitor.scan_once()
        
        # All paths must start with USDT
        for opp in opportunities:
            assert opp.path.start_currency == "USDT"
    
    @pytest.mark.asyncio
    async def test_scenario_4_realtime_monitoring(self, valid_tickers):
        """Scenario 4: Realtime monitoring (stop after 2 iterations)."""
        config = MonitorConfig(
            run_mode="realtime",
            refresh_interval_seconds=1
        )
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(valid_tickers)
        
        iterations = 0
        async for opportunities in monitor.scan_realtime():
            assert isinstance(opportunities, list)
            iterations += 1
            if iterations >= 2:
                monitor._shutdown_requested = True
                break
        
        assert iterations == 2
    
    @pytest.mark.asyncio
    async def test_scenario_8_1_no_opportunities(self, valid_tickers):
        """Scenario 8.1: No opportunities with impossibly high threshold."""
        config = MonitorConfig(min_profit_threshold=50.0)
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(valid_tickers)
        
        opportunities = await monitor.scan_once()
        
        # Should return empty list, not error
        assert opportunities == []
    
    @pytest.mark.asyncio
    async def test_scenario_8_2_invalid_price_data(self):
        """Scenario 8.2: Handle invalid price data (bid > ask)."""
        invalid_tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50001"),  # Invalid: bid > ask
                ask=Decimal("50000"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600"),
                ask=Decimal("2601"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            ),
        ]
        
        config = MonitorConfig()
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        monitor._exchange = MockExchange(invalid_tickers)
        
        # Should not crash, just filter invalid prices
        opportunities = await monitor.scan_once()
        
        # Should work with valid tickers only
        assert isinstance(opportunities, list)
