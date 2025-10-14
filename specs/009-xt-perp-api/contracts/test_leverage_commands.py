"""Contract tests for leverage commands.

Status: MUST FAIL until implementation complete (TDD)
"""

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestLeverageSet:
    """Contract tests for 'cextools leverage set' command."""

    def test_leverage_set_only_perp(self):
        """MUST fail: leverage set only works with perp exchange type."""
        pytest.skip("Implementation not started")

    def test_leverage_set_requires_symbol(self):
        """MUST fail: leverage set requires --symbol parameter."""
        pytest.skip("Implementation not started")

    def test_leverage_set_requires_leverage(self):
        """MUST fail: leverage set requires --leverage parameter."""
        pytest.skip("Implementation not started")

    def test_leverage_set_validates_range(self):
        """MUST fail: leverage set rejects values outside 1-125 range."""
        pytest.skip("Implementation not started")

    def test_leverage_set_success(self):
        """MUST pass: leverage set with valid params succeeds."""
        pytest.skip("Implementation not started")

    def test_leverage_set_rejects_spot(self):
        """MUST fail: leverage set with spot exchange-type fails."""
        pytest.skip("Implementation not started")


class TestLeverageInfo:
    """Contract tests for 'cextools leverage info' command."""

    def test_leverage_info_only_perp(self):
        """MUST fail: leverage info only works with perp exchange type."""
        pytest.skip("Implementation not started")

    def test_leverage_info_requires_symbol(self):
        """MUST fail: leverage info requires --symbol parameter."""
        pytest.skip("Implementation not started")

    def test_leverage_info_success(self):
        """MUST pass: leverage info shows current leverage and allowed range."""
        pytest.skip("Implementation not started")

    def test_leverage_info_shows_leverage_brackets(self):
        """MUST pass: leverage info shows leverage brackets based on position size."""
        pytest.skip("Implementation not started")
