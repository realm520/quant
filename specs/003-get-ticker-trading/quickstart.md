# Quickstart Guide: Get All Market Tickers

**Feature**: 003-get-ticker-trading | **Audience**: Developers | **Date**: 2025-10-06

## Overview
快速开始指南，演示如何使用扩展的 `get_ticker()` API 进行单个市场查询和批量市场查询。

## Prerequisites
- Python 3.11+ installed
- tri-arb project set up (see main README)
- XT Exchange API credentials (for integration tests)

## Installation
```bash
# Clone repository (if not already done)
git clone <repo-url>
cd tri-arb

# Checkout feature branch
git checkout 003-get-ticker-trading

# Install dependencies with uv
uv pip install -e ".[dev]"
```

## Basic Usage

### 1. Single Ticker Query (Existing Behavior)
```python
import asyncio
from decimal import Decimal
from tri_arb.core.models import TradingPair
from tri_arb.exchanges.xt_spot import XTSpotExchange

async def get_single_ticker():
    """Query price for a specific trading pair."""

    # Create exchange adapter
    exchange = XTSpotExchange(
        api_key="your_api_key",      # Optional for public endpoints
        api_secret="your_api_secret"
    )

    # Define trading pair
    btc_usdt = TradingPair(
        base_currency="BTC",
        quote_currency="USDT",
        exchange="xt",
        min_order_size=Decimal("0.001"),
        max_order_size=Decimal("1000"),
        price_precision=2,
        quantity_precision=8,
    )

    try:
        # Connect to exchange
        await exchange.connect()

        # Get single ticker (existing API)
        price = await exchange.get_ticker(btc_usdt)

        print(f"BTC/USDT Price:")
        print(f"  Bid: {price.bid_price} (volume: {price.bid_volume})")
        print(f"  Ask: {price.ask_price} (volume: {price.ask_volume})")
        print(f"  Timestamp: {price.timestamp}")

    finally:
        await exchange.disconnect()

# Run
asyncio.run(get_single_ticker())
```

**Expected Output**:
```
BTC/USDT Price:
  Bid: 50000.00 (volume: 10.5)
  Ask: 50001.00 (volume: 8.3)
  Timestamp: 2025-10-06 12:00:00+00:00
```

### 2. Batch Ticker Query (New Feature)
```python
import asyncio
from tri_arb.exchanges.xt_spot import XTSpotExchange

async def get_all_tickers():
    """Query prices for ALL active markets on exchange."""

    exchange = XTSpotExchange(
        api_key="your_api_key",
        api_secret="your_api_secret"
    )

    try:
        await exchange.connect()

        # Get ALL market tickers (new API)
        prices = await exchange.get_ticker(None)  # Note: None parameter

        print(f"Retrieved {len(prices)} market tickers:")

        # Display first 5 markets
        for price in prices[:5]:
            pair = price.trading_pair
            print(f"{pair.base_currency}/{pair.quote_currency}: "
                  f"bid={price.bid_price}, ask={price.ask_price}")

        # Find BTC markets
        btc_markets = [p for p in prices if p.trading_pair.base_currency == "BTC"]
        print(f"\nFound {len(btc_markets)} BTC markets")

    finally:
        await exchange.disconnect()

# Run
asyncio.run(get_all_tickers())
```

**Expected Output**:
```
Retrieved 250 market tickers:
BTC/USDT: bid=50000.00, ask=50001.00
ETH/USDT: bid=3000.00, ask=3001.00
SOL/USDT: bid=100.00, ask=100.10
BNB/USDT: bid=300.00, ask=300.50
ADA/USDT: bid=0.50, ask=0.51

Found 15 BTC markets
```

### 3. Performance Measurement
```python
import asyncio
import time
from tri_arb.exchanges.xt_spot import XTSpotExchange

async def measure_batch_performance():
    """Measure batch query performance."""

    exchange = XTSpotExchange()
    await exchange.connect()

    try:
        # Measure batch query time
        start = time.perf_counter()
        prices = await exchange.get_ticker(None)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"Batch Query Performance:")
        print(f"  Markets retrieved: {len(prices)}")
        print(f"  Time taken: {elapsed_ms:.2f}ms")
        print(f"  Target: <1000ms")
        print(f"  Status: {'✅ PASS' if elapsed_ms < 1000 else '❌ FAIL'}")

    finally:
        await exchange.disconnect()

# Run
asyncio.run(measure_batch_performance())
```

**Expected Output**:
```
Batch Query Performance:
  Markets retrieved: 250
  Time taken: 650.23ms
  Target: <1000ms
  Status: ✅ PASS
```

## Advanced Usage

### 4. Partial Failure Handling
```python
import asyncio
from tri_arb.config.logging import get_logger
from tri_arb.exchanges.xt_spot import XTSpotExchange

logger = get_logger(__name__)

async def handle_partial_failures():
    """Demonstrate partial failure handling in batch queries."""

    exchange = XTSpotExchange()
    await exchange.connect()

    try:
        # Batch query (some markets may fail to parse)
        prices = await exchange.get_ticker(None)

        print(f"Successfully retrieved {len(prices)} market tickers")

        # Check logs for any failures
        # Failed markets will be logged with WARNING level

        # Filter by criteria
        high_volume_markets = [
            p for p in prices
            if p.bid_volume > 100 or p.ask_volume > 100
        ]

        print(f"High volume markets (>100): {len(high_volume_markets)}")

    finally:
        await exchange.disconnect()

# Run
asyncio.run(handle_partial_failures())
```

### 5. Type-Safe Usage with Type Narrowing
```python
import asyncio
from typing import Union, List
from tri_arb.core.models import Price, TradingPair
from tri_arb.exchanges.xt_spot import XTSpotExchange

async def type_safe_query(trading_pair: TradingPair | None):
    """Demonstrate type-safe usage with type narrowing."""

    exchange = XTSpotExchange()
    await exchange.connect()

    try:
        result = await exchange.get_ticker(trading_pair)

        # Type narrowing based on parameter
        if isinstance(result, list):
            # Batch query result
            print(f"Batch query: {len(result)} markets")
            for price in result[:3]:
                print(f"  {price.trading_pair.base_currency}/{price.trading_pair.quote_currency}")
        else:
            # Single query result
            print(f"Single query: {result.trading_pair.base_currency}/{result.trading_pair.quote_currency}")
            print(f"  Bid: {result.bid_price}, Ask: {result.ask_price}")

    finally:
        await exchange.disconnect()

# Run examples
asyncio.run(type_safe_query(None))  # Batch query
asyncio.run(type_safe_query(btc_usdt))  # Single query
```

## Running Tests

### Contract Tests
```bash
# Run contract tests for BaseExchange
uv run pytest tests/unit/test_exchanges/test_base_contract.py -v

# Expected: Tests SHOULD FAIL (not implemented yet)
```

### Integration Tests
```bash
# Set XT API credentials
export XT_API_KEY=your_key
export XT_API_SECRET=your_secret

# Run integration tests
uv run pytest tests/integration/test_xt_integration.py::test_batch_ticker -v

# Run with performance benchmarks
uv run pytest tests/integration/test_xt_integration.py --benchmark-only
```

### All Tests
```bash
# Run all tests for feature 003
uv run pytest -m "feature_003" -v
```

## Common Issues & Troubleshooting

### Issue 1: NotImplementedError
```
NotImplementedError: xt exchange does not support batch ticker queries
```

**Cause**: Exchange adapter hasn't implemented batch query support yet.

**Solution**: Use single ticker queries or implement batch support for the exchange.

### Issue 2: Performance Warning
```
WARNING: Batch ticker query exceeded performance target
  elapsed_ms=1200, target_ms=1000, market_count=250
```

**Cause**: Batch query took >1 second (violates NFR-001).

**Solution**: Check network latency, exchange API status, or reduce number of markets.

### Issue 3: Empty Batch Result
```python
prices = await exchange.get_ticker(None)
assert len(prices) == 0  # Unexpected
```

**Possible Causes**:
- Exchange has no active markets (rare)
- All market data failed to parse (check logs)
- Exchange API returned unexpected format

**Debugging**:
```python
# Enable debug logging
import logging
logging.getLogger("tri_arb").setLevel(logging.DEBUG)

# Re-run query
prices = await exchange.get_ticker(None)

# Check logs for:
# - API response format
# - Parse failures
# - Network errors
```

## Performance Benchmarking

### Batch Query Performance Test
```python
import asyncio
import statistics
from tri_arb.exchanges.xt_spot import XTSpotExchange

async def benchmark_batch_query(iterations=10):
    """Run batch query multiple times and analyze performance."""

    exchange = XTSpotExchange()
    await exchange.connect()

    try:
        times_ms = []

        for i in range(iterations):
            start = time.perf_counter()
            prices = await exchange.get_ticker(None)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times_ms.append(elapsed_ms)

            print(f"Iteration {i+1}: {elapsed_ms:.2f}ms ({len(prices)} markets)")

        # Statistics
        print(f"\nPerformance Statistics ({iterations} iterations):")
        print(f"  Mean: {statistics.mean(times_ms):.2f}ms")
        print(f"  Median: {statistics.median(times_ms):.2f}ms")
        print(f"  Min: {min(times_ms):.2f}ms")
        print(f"  Max: {max(times_ms):.2f}ms")
        print(f"  p95: {statistics.quantiles(times_ms, n=20)[18]:.2f}ms")

    finally:
        await exchange.disconnect()

# Run
asyncio.run(benchmark_batch_query(10))
```

## Next Steps
1. Run contract tests to verify API compliance
2. Implement batch ticker support in exchange adapter
3. Run integration tests with real exchange data
4. Benchmark performance and optimize if needed
5. Deploy to production environment

## Related Documentation
- [API Contract](./contracts/base_exchange_get_ticker.md)
- [Data Model](./data-model.md)
- [Research Document](./research.md)
- [Implementation Tasks](./tasks.md) (generated by /tasks command)

---

**Questions?** Check [Feature 003 Specification](./spec.md) for requirements and clarifications.
