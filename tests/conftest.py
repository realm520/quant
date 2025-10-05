"""Pytest configuration and fixtures.

Provides common fixtures for testing including database,
cache, exchange mocks, and async support.
"""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest

from tri_arb.config.settings import settings
from tri_arb.core.models import TradingPair
from tri_arb.data.cache import CacheManager
from tri_arb.data.database import DatabaseManager


# Async support


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests.

    Yields:
        Event loop instance
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Database fixtures


@pytest.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Create test database instance.

    Args:
        tmp_path: Pytest temporary directory

    Yields:
        DatabaseManager instance with temporary database
    """
    # Create test database path
    db_path = tmp_path / "test.db"

    # Create database manager
    db = DatabaseManager(db_path=str(db_path), pool_size=2)
    await db.initialize()

    yield db

    # Cleanup
    await db.close()
    if db_path.exists():
        db_path.unlink()


# Cache fixtures


@pytest.fixture
async def test_cache() -> AsyncGenerator[CacheManager, None]:
    """Create test cache instance.

    Yields:
        CacheManager instance with test configuration
    """
    cache = CacheManager(ttl=60, max_size=100)

    yield cache

    # Cleanup
    await cache.clear_all()


# Mock exchange fixtures


@pytest.fixture
def mock_binance_exchange():
    """Create mock Binance exchange.

    Returns:
        Mock Binance exchange instance
    """
    from tri_arb.exchanges.binance import BinanceExchange

    exchange = BinanceExchange(
        name="binance_test",
        api_key="test_key",
        api_secret="test_secret",
    )
    return exchange


@pytest.fixture
def mock_okx_exchange():
    """Create mock OKX exchange.

    Returns:
        Mock OKX exchange instance
    """
    from tri_arb.exchanges.okx import OKXExchange

    exchange = OKXExchange(
        name="okx_test",
        api_key="test_key",
        api_secret="test_secret",
        passphrase="test_passphrase",
    )
    return exchange


# Model fixtures


@pytest.fixture
def valid_trading_pair_data() -> dict:
    """Create valid trading pair data.

    Returns:
        Dictionary with valid TradingPair data
    """
    return {
        "base_currency": "BTC",
        "quote_currency": "USDT",
        "exchange": "binance",
        "min_order_size": Decimal("0.001"),
        "max_order_size": Decimal("1000"),
        "price_precision": 2,
        "quantity_precision": 8,
    }


@pytest.fixture
def sample_trading_pair(valid_trading_pair_data: dict) -> TradingPair:
    """Create sample TradingPair instance.

    Args:
        valid_trading_pair_data: Valid trading pair data

    Returns:
        TradingPair instance
    """
    return TradingPair(**valid_trading_pair_data)


# Service fixtures


@pytest.fixture
async def market_data_service():
    """Create market data service instance.

    Returns:
        MarketDataService instance
    """
    from tri_arb.services.market_data import MarketDataService

    service = MarketDataService(exchanges=[])
    return service


@pytest.fixture
async def trading_service():
    """Create trading service instance.

    Returns:
        TradingService instance
    """
    from tri_arb.services.trading import TradingService

    service = TradingService(exchanges={})
    return service


@pytest.fixture
async def monitoring_service():
    """Create monitoring service instance.

    Returns:
        MonitoringService instance
    """
    from tri_arb.services.monitoring import MonitoringService

    service = MonitoringService()
    return service


@pytest.fixture
async def risk_service():
    """Create risk management service instance.

    Returns:
        RiskManagementService instance
    """
    from tri_arb.services.risk import RiskManagementService

    service = RiskManagementService()
    return service


# Configuration fixtures


@pytest.fixture
def test_settings():
    """Create test settings override.

    Returns:
        Test settings instance
    """
    # Store original values
    original_env = settings.environment
    original_db_path = settings.db_path

    # Override for testing
    settings.environment = "test"
    settings.db_path = ":memory:"

    yield settings

    # Restore original values
    settings.environment = original_env
    settings.db_path = original_db_path


# Utility fixtures


@pytest.fixture
def anyio_backend():
    """Configure anyio backend for async tests.

    Returns:
        Backend name
    """
    return "asyncio"


# Marks


def pytest_configure(config):
    """Configure custom pytest marks.

    Args:
        config: Pytest configuration
    """
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "contract: Contract tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
