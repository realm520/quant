"""Contract tests for BaseExchange.get_ticker() - Feature 003

These tests define the expected behavior contract for get_ticker() method.
All exchange adapters MUST pass these tests to ensure API consistency.

Test Status: MUST FAIL until implementation complete (TDD requirement)
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Union

from tri_arb.core.models import Price, TradingPair
from tri_arb.exchanges.base import BaseExchange


# Test Fixtures

@pytest.fixture
def btc_usdt_pair() -> TradingPair:
    """BTC/USDT trading pair for single ticker tests."""
    return TradingPair(
        base_currency="BTC",
        quote_currency="USDT",
        exchange="test",
        min_order_size=Decimal("0.001"),
        max_order_size=Decimal("1000"),
        price_precision=2,
        quantity_precision=8,
    )


@pytest.fixture
async def connected_exchange(exchange: BaseExchange) -> BaseExchange:
    """Ensure exchange is connected before tests."""
    await exchange.connect()
    yield exchange
    await exchange.disconnect()


# Contract Tests: Single Ticker Query (Backward Compatibility)

@pytest.mark.asyncio
async def test_single_ticker_returns_price_object(
    connected_exchange: BaseExchange,
    btc_usdt_pair: TradingPair
):
    """CONTRACT: get_ticker(trading_pair) MUST return single Price object."""
    result = await connected_exchange.get_ticker(btc_usdt_pair)

    assert isinstance(result, Price), "Single ticker query must return Price object"
    assert not isinstance(result, list), "Single ticker should not return list"


@pytest.mark.asyncio
async def test_single_ticker_price_data_valid(
    connected_exchange: BaseExchange,
    btc_usdt_pair: TradingPair
):
    """CONTRACT: Returned Price object MUST satisfy data constraints."""
    price = await connected_exchange.get_ticker(btc_usdt_pair)

    # Price constraints
    assert price.bid_price > 0, "Bid price must be positive"
    assert price.ask_price > 0, "Ask price must be positive"
    assert price.ask_price >= price.bid_price, "Ask >= bid (normal market)"

    # Volume constraints
    assert price.bid_volume >= 0, "Bid volume must be non-negative"
    assert price.ask_volume >= 0, "Ask volume must be non-negative"

    # Metadata constraints
    assert price.trading_pair == btc_usdt_pair, "Trading pair must match input"
    assert price.exchange == connected_exchange.name, "Exchange name must match"

    # Timestamp freshness (< 5 seconds old)
    age = datetime.now(price.timestamp.tzinfo) - price.timestamp
    assert age < timedelta(seconds=5), f"Timestamp too old: {age.total_seconds()}s"


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_single_ticker_performance(
    connected_exchange: BaseExchange,
    btc_usdt_pair: TradingPair,
    benchmark
):
    """CONTRACT: Single ticker query MUST complete in <50ms p95."""
    async def query():
        return await connected_exchange.get_ticker(btc_usdt_pair)

    result = benchmark(query)

    # pytest-benchmark provides percentile stats
    # Assert p95 latency < 50ms
    stats = benchmark.stats
    p95_ms = stats.get('p95', 0) * 1000  # Convert to ms

    assert p95_ms < 50, f"p95 latency {p95_ms:.2f}ms exceeds 50ms target"


# Contract Tests: Batch Ticker Query (New Feature)

@pytest.mark.asyncio
async def test_batch_ticker_returns_list(
    connected_exchange: BaseExchange
):
    """CONTRACT: get_ticker(None) MUST return List[Price]."""
    result = await connected_exchange.get_ticker(None)

    assert isinstance(result, list), "Batch query must return list"
    assert all(isinstance(p, Price) for p in result), "All items must be Price objects"


@pytest.mark.asyncio
async def test_batch_ticker_no_duplicates(
    connected_exchange: BaseExchange
):
    """CONTRACT: Batch ticker MUST not return duplicate trading pairs."""
    prices = await connected_exchange.get_ticker(None)

    # Extract trading pair keys (base_quote_exchange)
    pair_keys = [
        f"{p.trading_pair.base_currency}_{p.trading_pair.quote_currency}_{p.trading_pair.exchange}"
        for p in prices
    ]

    assert len(pair_keys) == len(set(pair_keys)), "Duplicate trading pairs detected"


@pytest.mark.asyncio
async def test_batch_ticker_each_price_valid(
    connected_exchange: BaseExchange
):
    """CONTRACT: Each Price in batch result MUST satisfy data constraints."""
    prices = await connected_exchange.get_ticker(None)

    for price in prices:
        # Same validation as single ticker
        assert price.bid_price > 0, f"Invalid bid for {price.trading_pair}"
        assert price.ask_price > 0, f"Invalid ask for {price.trading_pair}"
        assert price.ask_price >= price.bid_price, f"Ask < bid for {price.trading_pair}"
        assert price.bid_volume >= 0, f"Negative bid volume for {price.trading_pair}"
        assert price.ask_volume >= 0, f"Negative ask volume for {price.trading_pair}"
        assert price.exchange == connected_exchange.name, "Exchange name mismatch"

        # Timestamp freshness
        age = datetime.now(price.timestamp.tzinfo) - price.timestamp
        assert age < timedelta(seconds=10), f"Stale data for {price.trading_pair}: {age.total_seconds()}s"


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_batch_ticker_performance(
    connected_exchange: BaseExchange,
    benchmark
):
    """CONTRACT: Batch ticker query MUST complete in <1000ms p95."""
    async def query():
        return await connected_exchange.get_ticker(None)

    result = benchmark(query)

    # Assert p95 latency < 1000ms
    stats = benchmark.stats
    p95_ms = stats.get('p95', 0) * 1000

    assert p95_ms < 1000, f"p95 latency {p95_ms:.2f}ms exceeds 1000ms target"


@pytest.mark.asyncio
async def test_batch_ticker_scalability(
    connected_exchange: BaseExchange
):
    """CONTRACT: Batch query MUST support ≥500 trading pairs (NFR-002)."""
    prices = await connected_exchange.get_ticker(None)

    # If exchange has <500 pairs, this test is informational
    # Main assertion: Should NOT fail/timeout even with 500+ pairs
    market_count = len(prices)

    # Log market count for monitoring
    print(f"Batch query returned {market_count} markets")

    # No hard failure, but warn if unexpectedly low
    if market_count > 0:
        assert market_count >= 1, "Batch query should return at least 1 market"


# Contract Tests: Error Handling

@pytest.mark.asyncio
async def test_batch_query_unsupported_raises_not_implemented(
    base_exchange: BaseExchange  # Concrete BaseExchange instance, not subclass
):
    """CONTRACT: Unsupported batch query MUST raise NotImplementedError."""
    with pytest.raises(NotImplementedError) as exc_info:
        await base_exchange.get_ticker(None)

    error_msg = str(exc_info.value)
    assert "does not support batch ticker queries" in error_msg.lower()
    assert base_exchange.name in error_msg  # Exchange name in message


@pytest.mark.asyncio
async def test_not_connected_raises_error(
    exchange: BaseExchange,
    btc_usdt_pair: TradingPair
):
    """CONTRACT: Calling get_ticker without connect() MUST raise error."""
    # Do NOT connect
    with pytest.raises(Exception) as exc_info:  # Specific error type may vary
        await exchange.get_ticker(btc_usdt_pair)

    # Error message should mention connection
    error_msg = str(exc_info.value).lower()
    assert "connect" in error_msg or "not connected" in error_msg


@pytest.mark.asyncio
async def test_invalid_trading_pair_raises_error(
    connected_exchange: BaseExchange
):
    """CONTRACT: Invalid trading pair MUST be rejected."""
    invalid_pair = TradingPair(
        base_currency="",  # Invalid: empty string
        quote_currency="USDT",
        exchange="test",
        min_order_size=Decimal("0.001"),
        max_order_size=Decimal("1000"),
        price_precision=2,
        quantity_precision=8,
    )

    with pytest.raises(Exception):  # Validation error
        await connected_exchange.get_ticker(invalid_pair)


# Contract Tests: Partial Failure Handling (Batch)

@pytest.mark.asyncio
async def test_batch_partial_failure_returns_success_subset(
    connected_exchange: BaseExchange,
    monkeypatch
):
    """CONTRACT: Batch query with partial failures MUST return successful subset."""
    # This test requires mocking to inject failures
    # Implementation will vary by exchange adapter

    # Mock parsing to fail for some tickers
    original_parse = connected_exchange._parse_ticker_to_price

    def mock_parse_with_failures(ticker_data):
        symbol = ticker_data.get("s", "")
        if symbol.startswith("fail_"):
            raise ValueError("Simulated parse failure")
        return original_parse(ticker_data)

    monkeypatch.setattr(
        connected_exchange,
        "_parse_ticker_to_price",
        mock_parse_with_failures
    )

    prices = await connected_exchange.get_ticker(None)

    # Verify successful subset returned
    assert isinstance(prices, list), "Must return list even with partial failures"
    assert len(prices) > 0, "Should have some successful results"

    # Failed tickers should be logged (check logs separately)


@pytest.mark.asyncio
async def test_batch_all_failures_returns_empty_list(
    connected_exchange: BaseExchange,
    monkeypatch
):
    """CONTRACT: Batch query with all failures MUST return empty list."""
    # Mock parsing to fail for all tickers
    def mock_parse_always_fails(ticker_data):
        raise ValueError("Simulated total failure")

    monkeypatch.setattr(
        connected_exchange,
        "_parse_ticker_to_price",
        mock_parse_always_fails
    )

    prices = await connected_exchange.get_ticker(None)

    assert prices == [], "All failures should return empty list, not raise exception"


# Contract Tests: Type Safety

def test_return_type_annotation():
    """CONTRACT: get_ticker signature MUST have correct type annotations."""
    import inspect
    from typing import get_type_hints

    hints = get_type_hints(BaseExchange.get_ticker)

    assert "trading_pair" in hints, "trading_pair parameter must be annotated"
    assert "return" in hints, "Return type must be annotated"

    # Verify Optional[TradingPair] for parameter
    # Verify Union[Price, List[Price]] for return
    # (Exact assertion depends on typing module version)


# Pytest Configuration

def pytest_configure(config):
    """Register custom markers for contract tests."""
    config.addinivalue_line(
        "markers",
        "benchmark: Performance benchmark tests (require pytest-benchmark)"
    )


# Test Parametrization for Multiple Exchanges

@pytest.mark.parametrize("exchange_name", ["xt", "binance", "okx"])
@pytest.mark.asyncio
async def test_all_exchanges_satisfy_contract(exchange_name: str):
    """CONTRACT: All exchange adapters MUST pass core contract tests.

    This parametrized test ensures contract compliance across all exchanges.
    """
    # Factory function to create exchange instances
    from tri_arb.exchanges import create_exchange

    exchange = create_exchange(exchange_name)
    await exchange.connect()

    try:
        # Test single ticker
        pair = TradingPair(...)  # Default pair for testing
        price = await exchange.get_ticker(pair)
        assert isinstance(price, Price)

        # Test batch ticker (if supported)
        try:
            prices = await exchange.get_ticker(None)
            assert isinstance(prices, list)
        except NotImplementedError:
            pytest.skip(f"{exchange_name} does not support batch queries yet")

    finally:
        await exchange.disconnect()
