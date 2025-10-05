# API Contracts

**Feature**: Python Triangle Arbitrage Scaffold
**Date**: 2025-10-05
**Status**: Not Applicable for MVP

## Overview

This directory would normally contain API contract definitions (OpenAPI/Swagger specs, GraphQL schemas, gRPC proto files, etc.) for external-facing APIs.

## MVP Scope

The MVP scaffold is a **CLI application only** with no Web API component. Therefore, there are no HTTP/REST/GraphQL contracts to define.

## Interface Contracts (CLI)

While there are no HTTP APIs, the CLI commands serve as the external interface. The CLI contract is defined through Typer's type hints and command structure.

### CLI Command Interface

**Available Commands**:

```bash
# Start the trading system
tri-arb start [OPTIONS]

# Check system status
tri-arb status [OPTIONS]

# Manage configuration
tri-arb config show
tri-arb config validate
tri-arb config set <key> <value>

# Health check
tri-arb health-check
```

**Command Specifications**:

#### `tri-arb start`
- **Purpose**: Start the arbitrage monitoring system
- **Options**:
  - `--exchanges`: Comma-separated list of exchanges (default: all configured)
  - `--log-level`: Log level (debug, info, warning, error)
  - `--config`: Path to configuration file
- **Output**: System startup status, running processes
- **Exit Codes**: 0 (success), 1 (error)

#### `tri-arb status`
- **Purpose**: Display system runtime status
- **Options**:
  - `--format`: Output format (text, json)
- **Output**: System health, active connections, metrics summary
- **Exit Codes**: 0 (healthy), 1 (unhealthy)

#### `tri-arb config`
- **Subcommands**:
  - `show`: Display current configuration
  - `validate`: Validate configuration file
  - `set <key> <value>`: Update configuration value
- **Output**: Configuration data or validation results
- **Exit Codes**: 0 (success), 1 (validation error)

#### `tri-arb health-check`
- **Purpose**: Check system health and dependencies
- **Output**: Health check results (database, cache, exchanges)
- **Exit Codes**: 0 (healthy), 1 (unhealthy)

## Exchange Integration Contracts

The system integrates with external exchange APIs. These contracts are defined by the `BaseExchange` abstract class in `src/tri_arb/exchanges/base.py`.

### BaseExchange Interface

```python
from abc import ABC, abstractmethod
from typing import List
from tri_arb.core.models import TradingPair, Price, OrderBook, Order, Trade

class BaseExchange(ABC):
    """Abstract base class defining exchange integration contract"""

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Price:
        """Get current ticker price for a trading pair"""
        pass

    @abstractmethod
    async def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBook:
        """Get order book depth for a trading pair"""
        pass

    @abstractmethod
    async def place_order(self, order: Order) -> Order:
        """Place a trading order on the exchange"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Order:
        """Get status of an order"""
        pass

    @abstractmethod
    async def get_trade_history(self, symbol: str, limit: int = 100) -> List[Trade]:
        """Get recent trade history for a symbol"""
        pass

    @abstractmethod
    async def subscribe_ticker(self, symbol: str, callback: callable) -> None:
        """Subscribe to real-time ticker updates via WebSocket"""
        pass

    @abstractmethod
    async def subscribe_orderbook(self, symbol: str, callback: callable) -> None:
        """Subscribe to real-time order book updates via WebSocket"""
        pass
```

## Contract Testing

For the MVP scaffold, contract tests will validate:

1. **CLI Interface Contracts**:
   - Command parsing and validation
   - Option handling
   - Exit codes
   - Output formats

2. **Exchange Interface Contracts**:
   - `BaseExchange` interface compliance
   - Method signatures
   - Return type validation
   - Exception handling

Test files will be located in `tests/contract/`:
- `test_cli_interface.py` - CLI command contract tests
- `test_exchange_interface.py` - Exchange interface contract tests

## Future Extensions

When Web API functionality is added in future iterations, this directory will contain:

- **OpenAPI/Swagger specifications** for REST APIs
- **GraphQL schemas** for GraphQL endpoints
- **gRPC proto files** for gRPC services
- **AsyncAPI specs** for WebSocket/event streams

Example future structure:
```
contracts/
├── openapi/
│   ├── v1.yaml              # REST API v1 spec
│   └── v2.yaml              # REST API v2 spec
├── graphql/
│   └── schema.graphql       # GraphQL schema
├── grpc/
│   └── trading.proto        # gRPC service definitions
└── asyncapi/
    └── websocket.yaml       # WebSocket event specs
```

## References

- CLI implementation: `src/tri_arb/cli/`
- Exchange interfaces: `src/tri_arb/exchanges/base.py`
- Contract tests: `tests/contract/`
- Type definitions: `src/tri_arb/core/models.py`
