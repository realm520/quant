# Architecture Documentation

## System Overview
7-layer async architecture for triangle arbitrage trading with production-ready infrastructure.

## Layers
1. **Core**: Models (Pydantic), business logic, exceptions
2. **Exchanges**: BaseExchange interface, Binance/OKX adapters, factory pattern
3. **Data**: aiosqlite (DB), cachetools (cache), repository pattern
4. **Services**: MarketData, Trading, Monitoring, Risk
5. **Config**: pydantic-settings, structlog logging
6. **CLI**: Typer commands (start, status, config)
7. **Utils**: Prometheus metrics, health checks, async utilities

## Key Patterns
- **Repository Pattern**: Data access abstraction
- **Factory Pattern**: Exchange creation
- **Async/Await**: uvloop + asyncio
- **Type Safety**: mypy strict mode
- **TDD**: Tests before implementation

## Data Flow
Config → Services → Exchanges → Data Layer → Cache/DB

## MVP Scope
Placeholder implementations only - no actual trading.
