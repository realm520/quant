"""
Contract tests for Feature 003 get_ticker() integration.

These tests verify that ArbitrageMonitor correctly integrates with
the existing XTSpotExchange.get_ticker() method from Feature 003.

IMPORTANT: These tests MUST FAIL until implementation is complete.
"""

from decimal import Decimal

import pytest

# These imports will fail until implementation exists
from tri_arb.arbitrage import ArbitrageMonitor
from tri_arb.arbitrage.config import MonitorConfig
from tri_arb.exchanges.xt_spot import XTSpotExchange
from tri_arb.models.exchange import Ticker


class TestGetTickerIntegration:
    """Test integration with Feature 003 get_ticker() API."""

    @pytest.fixture
    async def exchange(self):
        """Create XTSpotExchange instance."""
        exchange = XTSpotExchange(
            api_key="test_key",
            api_secret="test_secret"
        )
        await exchange.connect()
        yield exchange
        await exchange.disconnect()

    @pytest.mark.asyncio
    async def test_monitor_uses_get_ticker(self, exchange, mocker):
        """Contract: ArbitrageMonitor uses XTSpotExchange.get_ticker() to fetch prices."""
        config = MonitorConfig(run_mode="once")
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        
        # Mock get_ticker to return test data
        mock_tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.0"),
                ask=Decimal("50001.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            )
        ]
        spy = mocker.patch.object(exchange, "get_ticker", return_value=mock_tickers)
        
        # Inject exchange into monitor for testing
        monitor._exchange = exchange
        await monitor.scan_once()
        
        # Verify get_ticker was called with symbol=None (all pairs)
        spy.assert_called_once_with(symbol=None)

    @pytest.mark.asyncio
    async def test_monitor_handles_ticker_list_response(self, exchange, mocker):
        """Contract: ArbitrageMonitor correctly processes list[Ticker] response."""
        config = MonitorConfig(run_mode="once")
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        
        # Mock multiple tickers
        mock_tickers = [
            Ticker(
                symbol=f"COIN{i}/USDT",
                bid=Decimal(f"{1000 + i}.0"),
                ask=Decimal(f"{1000 + i + 1}.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            )
            for i in range(10)
        ]
        mocker.patch.object(exchange, "get_ticker", return_value=mock_tickers)
        
        monitor._exchange = exchange
        opportunities = await monitor.scan_once()
        
        # Should process all tickers without error
        assert isinstance(opportunities, list)

    @pytest.mark.asyncio
    async def test_monitor_filters_invalid_prices(self, exchange, mocker):
        """Contract: ArbitrageMonitor filters out invalid prices (bid > ask)."""
        config = MonitorConfig(run_mode="once")
        monitor = ArbitrageMonitor(config=config, exchange_name="xt")
        
        # Mix of valid and invalid tickers
        mock_tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.0"),
                ask=Decimal("50001.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600.0"),  # Invalid: bid > ask
                ask=Decimal("2599.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            ),
        ]
        mocker.patch.object(exchange, "get_ticker", return_value=mock_tickers)
        
        monitor._exchange = exchange
        
        # Should filter invalid prices and log warning
        opportunities = await monitor.scan_once()
        
        # No crash, just filtered
        assert isinstance(opportunities, list)


class TestTickerDataUsage:
    """Test how ArbitrageMonitor uses Ticker data fields."""

    @pytest.mark.asyncio
    async def test_uses_bid_for_sell_prices(self):
        """Contract: Monitor uses Ticker.bid for selling actions."""
        from tri_arb.arbitrage.calculator import calculate_profit_rate
        from tri_arb.models.arbitrage import TradingPath
        
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )
        
        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.0"),
                ask=Decimal("50001.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.0501"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600.0"),
                ask=Decimal("2601.0"),
                bid_volume=Decimal("100.0"),
                ask_volume=Decimal("100.0")
            ),
        }
        
        profit_rate, price_details = await calculate_profit_rate(
            path=path,
            tickers=tickers,
            fee_rate=Decimal("0.001")
        )
        
        # Verify sell uses bid price
        sell_step = [d for d in price_details if d["type"] == "sell"][0]
        assert sell_step["price"] == Decimal("2600.0")  # bid, not ask

    @pytest.mark.asyncio
    async def test_uses_ask_for_buy_prices(self):
        """Contract: Monitor uses Ticker.ask for buying actions."""
        from tri_arb.arbitrage.calculator import calculate_profit_rate
        from tri_arb.models.arbitrage import TradingPath
        
        path = TradingPath(
            start_currency="USDT",
            trading_pairs=("BTC/USDT", "ETH/BTC", "ETH/USDT")
        )
        
        tickers = {
            "BTC/USDT": Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000.0"),
                ask=Decimal("50001.0"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0")
            ),
            "ETH/BTC": Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.05"),
                ask=Decimal("0.0501"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0")
            ),
            "ETH/USDT": Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2600.0"),
                ask=Decimal("2601.0"),
                bid_volume=Decimal("100.0"),
                ask_volume=Decimal("100.0")
            ),
        }
        
        profit_rate, price_details = await calculate_profit_rate(
            path=path,
            tickers=tickers,
            fee_rate=Decimal("0.001")
        )
        
        # Verify buy uses ask price
        buy_steps = [d for d in price_details if d["type"] == "buy"]
        assert buy_steps[0]["price"] == Decimal("50001.0")  # ask, not bid
        assert buy_steps[1]["price"] == Decimal("0.0501")   # ask, not bid
