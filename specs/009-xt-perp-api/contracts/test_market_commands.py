"""Contract tests for market commands.

Status: MUST FAIL until implementation complete (TDD)
"""

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestMarketTicker:
    """Contract tests for 'cextools market ticker' command."""

    def test_market_ticker_defaults_to_spot(self):
        """MUST pass: market ticker defaults to spot when --exchange-type omitted."""
        pytest.skip("Implementation not started")

    def test_market_ticker_perp_with_symbol(self):
        """MUST pass: market ticker works with perp and specific symbol."""
        pytest.skip("Implementation not started")

    def test_market_ticker_all_symbols(self):
        """MUST pass: market ticker without --symbol shows all active pairs."""
        pytest.skip("Implementation not started")

    def test_market_ticker_json_output(self):
        """MUST pass: market ticker supports JSON output."""
        pytest.skip("Implementation not started")


class TestMarketDepth:
    """Contract tests for 'cextools market depth' command."""

    def test_market_depth_requires_symbol(self):
        """MUST fail: market depth requires --symbol parameter."""
        pytest.skip("Implementation not started")

    def test_market_depth_default_limit(self):
        """MUST pass: market depth defaults to 10 levels."""
        pytest.skip("Implementation not started")

    def test_market_depth_custom_limit(self):
        """MUST pass: market depth respects --limit parameter (5-50)."""
        pytest.skip("Implementation not started")

    def test_market_depth_invalid_limit(self):
        """MUST fail: market depth rejects limit outside 5-50 range."""
        pytest.skip("Implementation not started")


class TestMarketFunding:
    """Contract tests for 'cextools market funding' command."""

    def test_market_funding_only_perp(self):
        """MUST fail: market funding only works with perp exchange type."""
        pytest.skip("Implementation not started")

    def test_market_funding_requires_symbol(self):
        """MUST fail: market funding requires --symbol parameter."""
        pytest.skip("Implementation not started")

    def test_market_funding_perp_success(self):
        """MUST pass: market funding with perp and symbol succeeds."""
        pytest.skip("Implementation not started")


class TestMarketWatch:
    """Contract tests for 'cextools market watch' command."""

    def test_market_watch_requires_symbol(self):
        """MUST fail: market watch requires --symbol parameter."""
        pytest.skip("Implementation not started")

    def test_market_watch_default_interval(self):
        """MUST pass: market watch defaults to 5 second interval."""
        pytest.skip("Implementation not started")

    def test_market_watch_custom_interval(self):
        """MUST pass: market watch respects --interval parameter (1-60)."""
        pytest.skip("Implementation not started")

    def test_market_watch_invalid_interval(self):
        """MUST fail: market watch rejects interval outside 1-60 range."""
        pytest.skip("Implementation not started")

    def test_market_watch_ctrl_c_graceful_exit(self):
        """MUST pass: market watch exits gracefully on Ctrl+C."""
        pytest.skip("Implementation not started")
