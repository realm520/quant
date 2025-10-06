# Feature Specification: XT Exchange Spot Market Integration

**Feature ID**: 002  
**Feature Name**: XT Exchange Spot Market Support  
**Status**: Planning  
**Created**: 2025-10-05  
**Last Updated**: 2025-10-05

---

## Overview

### Purpose
Enable the triangle arbitrage trading system to access XT exchange's spot market, allowing traders to monitor prices, manage orders, and execute arbitrage strategies across XT and existing supported exchanges (Binance, OKX).

### Business Value
- **Market Coverage**: Expand arbitrage opportunities by adding XT exchange as a trading venue
- **Liquidity Access**: Tap into XT's unique liquidity pools and trading pairs
- **Strategy Diversification**: Enable cross-exchange arbitrage strategies involving XT
- **Risk Distribution**: Reduce dependency on single exchange by supporting multiple venues

### Scope
**In Scope**:
- XT spot market price retrieval (ticker, orderbook)
- Trading pair information and market data
- Order placement and cancellation
- Order status tracking
- Trade history retrieval
- Account balance queries

**Out of Scope**:
- XT futures/derivatives markets
- XT WebSocket streaming (will use REST API polling initially)
- XT staking or lending features
- Cross-exchange order routing logic (handled by strategy layer)

---

## User Scenarios & Testing

### Scenario 1: Monitor XT Market Prices
**As a** trader  
**I want to** retrieve real-time price data from XT exchange  
**So that** I can identify arbitrage opportunities involving XT

**Given** the system is connected to XT exchange  
**When** I request ticker price for BTC/USDT trading pair  
**Then** I should receive current bid/ask prices with volume information  
**And** the timestamp should be within last 5 seconds  
**And** the data format should match other exchanges (Binance, OKX)

**Testing Checklist**:
- [ ] Successfully retrieve ticker for major pairs (BTC/USDT, ETH/USDT)
- [ ] Handle invalid trading pair gracefully with clear error message
- [ ] Price data includes all required fields (bid, ask, volumes, timestamp)
- [ ] Timestamp is accurate and timezone-aware (UTC)

### Scenario 2: Analyze XT Order Book Depth
**As a** trader  
**I want to** view XT order book with multiple price levels  
**So that** I can assess liquidity and execution feasibility

**Given** the system is connected to XT exchange  
**When** I request order book for ETH/USDT with depth of 20 levels  
**Then** I should receive bids and asks sorted by price  
**And** each level should contain price and quantity  
**And** the data should be fresh (< 5 seconds old)

**Testing Checklist**:
- [ ] Order book contains requested depth (default 20, configurable up to 500)
- [ ] Bids sorted descending by price, asks sorted ascending
- [ ] Price and quantity precision match XT's trading rules
- [ ] Empty order book handled gracefully (no trades for pair)

### Scenario 3: Place Limit Order on XT
**As a** trader  
**I want to** place limit buy/sell orders on XT  
**So that** I can execute arbitrage strategies at target prices

**Given** I have sufficient balance in my XT account  
**And** the trading pair is active  
**When** I place a limit buy order for 0.1 BTC at 50000 USDT  
**Then** the order should be submitted successfully  
**And** I should receive an order ID for tracking  
**And** the order status should be "OPEN" or "FILLED"

**Testing Checklist**:
- [ ] Successful order placement returns valid order ID
- [ ] Order details match submitted parameters (pair, side, quantity, price)
- [ ] Invalid orders rejected with clear error (insufficient balance, invalid price)
- [ ] Order status reflects actual exchange state

### Scenario 4: Cancel Active XT Orders
**As a** trader  
**I want to** cancel my open orders on XT  
**So that** I can adjust my strategy or prevent unwanted execution

**Given** I have an open order on XT  
**When** I request order cancellation using the order ID  
**Then** the order should be cancelled successfully  
**And** the cancellation should be confirmed  
**And** my balance should be updated to reflect released funds

**Testing Checklist**:
- [ ] Successfully cancel open orders
- [ ] Cancelling already filled/cancelled order handled gracefully
- [ ] Invalid order ID returns clear error message
- [ ] Balance updates after cancellation

### Scenario 5: Track XT Order Status
**As a** trader  
**I want to** check the status of my XT orders  
**So that** I can monitor execution and manage risk

**Given** I have placed an order on XT  
**When** I query order status using the order ID  
**Then** I should receive current order state (OPEN, FILLED, CANCELLED)  
**And** filled quantity and remaining quantity should be accurate  
**And** average fill price should be provided if partially/fully filled

**Testing Checklist**:
- [ ] Order status accurately reflects exchange state
- [ ] Filled quantity and remaining quantity sum to total quantity
- [ ] Filled orders include average execution price
- [ ] Order timestamps (created, updated) are accurate

### Scenario 6: Retrieve XT Trade History
**As a** trader  
**I want to** access my historical trades on XT  
**So that** I can analyze performance and reconcile accounting

**Given** I have executed trades on XT  
**When** I request trade history for BTC/USDT pair  
**Then** I should receive list of past trades with details  
**And** each trade should include price, quantity, fee, timestamp  
**And** trades should be sorted by time (most recent first)

**Testing Checklist**:
- [ ] Trade history returns up to requested limit (default 100)
- [ ] Each trade contains all required fields
- [ ] Fee information is accurate and properly formatted
- [ ] Empty history handled gracefully for new pairs

### Scenario 7: Query XT Account Balance
**As a** trader  
**I want to** check my available balance on XT  
**So that** I can plan trades and manage capital allocation

**Given** I have an active XT account  
**When** I request account balance  
**Then** I should receive balances for all assets  
**And** available and locked amounts should be separated  
**And** total balance should equal available + locked

**Testing Checklist**:
- [ ] Balance query returns all non-zero assets
- [ ] Available balance reflects unlocked funds
- [ ] Locked balance reflects funds in open orders
- [ ] Zero balances handled appropriately

### Scenario 8: Handle XT API Authentication Errors
**As a** trader  
**I want to** receive clear feedback when authentication fails  
**So that** I can correct API key configuration

**Given** I have configured invalid XT API credentials  
**When** I attempt any authenticated operation  
**Then** I should receive authentication error  
**And** the error message should indicate credential issue  
**And** no partial data should be returned

**Testing Checklist**:
- [ ] Invalid API key returns authentication error
- [ ] Invalid signature returns authentication error
- [ ] Expired timestamp handled with clear message
- [ ] Missing credentials handled gracefully

---

## Requirements

### Functional Requirements

#### FR-1: Price Data Retrieval
- **FR-1.1**: System must retrieve current ticker price for any XT spot trading pair
- **FR-1.2**: System must retrieve order book with configurable depth (1-500 levels)
- **FR-1.3**: Price data must include bid/ask prices, volumes, and UTC timestamp
- **FR-1.4**: System must handle XT-specific trading pair format (e.g., "btc_usdt")

#### FR-2: Order Management
- **FR-2.1**: System must support limit order placement (buy/sell)
- **FR-2.2**: System must support market order placement (buy/sell)
- **FR-2.3**: System must allow order cancellation by order ID
- **FR-2.4**: System must track order status (OPEN, FILLED, CANCELLED, PARTIAL)
- **FR-2.5**: System must validate order parameters before submission

#### FR-3: Account Operations
- **FR-3.1**: System must retrieve account balance for all assets
- **FR-3.2**: System must distinguish between available and locked balances
- **FR-3.3**: System must support authenticated API operations using API key/secret

#### FR-4: Trade History
- **FR-4.1**: System must retrieve historical trades for specific trading pairs
- **FR-4.2**: System must provide trade details including price, quantity, fee, timestamp
- **FR-4.3**: System must support pagination/limiting of trade history results

#### FR-5: Error Handling
- **FR-5.1**: System must handle XT API errors gracefully with meaningful messages
- **FR-5.2**: System must retry transient network errors with exponential backoff
- **FR-5.3**: System must validate authentication before making API calls
- **FR-5.4**: System must handle rate limiting according to XT's policies

### Non-Functional Requirements

#### NFR-1: Performance
- **NFR-1.1**: Price data retrieval must complete within 2 seconds under normal conditions
- **NFR-1.2**: Order placement must complete within 3 seconds
- **NFR-1.3**: System must handle concurrent requests efficiently (async pattern)

#### NFR-2: Reliability
- **NFR-2.1**: System must maintain >99% uptime for XT connectivity
- **NFR-2.2**: Failed requests must be logged with full context for debugging
- **NFR-2.3**: System must gracefully handle XT exchange downtime

#### NFR-3: Security
- **NFR-3.1**: API credentials must not be logged or exposed in error messages
- **NFR-3.2**: All API requests must use HMAC-SHA256 signature authentication
- **NFR-3.3**: Timestamp validation must prevent replay attacks (5-second window)

#### NFR-4: Maintainability
- **NFR-4.1**: XT adapter must conform to existing BaseExchange interface
- **NFR-4.2**: Code must follow project coding standards (Ruff, Black)
- **NFR-4.3**: All public methods must have docstrings with type hints

#### NFR-5: Testability
- **NFR-5.1**: All adapter methods must be unit testable
- **NFR-5.2**: Integration tests must verify XT API contract compliance
- **NFR-5.3**: Test coverage must be ≥80% for XT adapter code

### Data Requirements

#### Trading Pair Format
- XT uses lowercase with underscore: `btc_usdt`, `eth_usdt`
- Internal system uses: `TradingPair(base_currency="BTC", quote_currency="USDT")`
- Adapter must transform between formats bidirectionally

#### Price Precision
- Must respect XT's price precision rules per trading pair
- Quantity precision must match XT's lot size requirements
- Decimal type must be used to avoid floating-point errors

#### Timestamp Handling
- All timestamps must be UTC timezone-aware
- XT API uses millisecond Unix timestamps
- Internal system uses Python datetime objects

#### Order States Mapping
| XT Status | Internal Status |
|-----------|----------------|
| NEW       | OPEN           |
| FILLED    | FILLED         |
| CANCELED  | CANCELLED      |
| PARTIAL   | PARTIAL        |
| REJECTED  | FAILED         |

---

## Key Entities

### XTExchange Adapter
- **Purpose**: Implement BaseExchange interface for XT exchange operations
- **Attributes**:
  - `name`: Exchange identifier ("xt")
  - `api_key`: XT API key for authentication
  - `api_secret`: XT API secret for signature generation
  - `is_connected`: Connection state flag
- **Behaviors**: All BaseExchange abstract methods (connect, disconnect, get_ticker, etc.)

### XT API Configuration
- **Base URL**: `https://sapi.xt.com`
- **API Version**: v4
- **Authentication**: HMAC-SHA256 with custom header format
- **Rate Limits**: To be determined from XT documentation
- **Required Headers**:
  - `validate-algorithms`: HmacSHA256
  - `validate-appkey`: API key
  - `validate-timestamp`: Millisecond timestamp
  - `validate-signature`: HMAC signature
  - `validate-recvwindow`: 5000 (ms)

### Trading Pair Transformation
- **Input Format**: `TradingPair(base_currency="BTC", quote_currency="USDT")`
- **XT Format**: `"btc_usdt"` (lowercase, underscore separator)
- **Validation**: Ensure trading pair exists on XT before operations

---

## Technical Constraints

### XT API Limitations
- REST API only (no WebSocket in initial version)
- Rate limiting policies must be respected
- Authentication requires precise timestamp synchronization
- Some endpoints may have specific recvWindow requirements

### Project Architecture Constraints
- Must use async/await pattern (no synchronous blocking calls)
- Must conform to BaseExchange interface contract
- Must use project's HTTP client library (aiohttp or httpx)
- Must integrate with existing logging (structlog) and error handling

### Integration Points
- **Exchange Factory**: Must register XT in exchange creation factory
- **Configuration**: Must support XT credentials in settings
- **Testing**: Must pass contract tests for BaseExchange compliance

---

## Dependencies

### External Dependencies
- XT Exchange REST API (v4)
- Python async HTTP client (aiohttp or httpx)
- HMAC-SHA256 cryptographic library (built-in hashlib)

### Internal Dependencies
- `tri_arb.core.models` - TradingPair, Price, OrderBook, Order models
- `tri_arb.exchanges.base` - BaseExchange abstract interface
- `tri_arb.config.settings` - Configuration management
- `tri_arb.config.logging` - Structured logging

### Documentation Dependencies
- XT API documentation for endpoint specifications
- XT trading rules for precision and lot sizes
- XT rate limiting policies

---

## Open Questions

1. **Rate Limiting**: What are XT's exact rate limits per endpoint and IP?
2. **WebSocket Support**: When should we add WebSocket streaming for real-time data?
3. **Trading Pairs**: Which XT trading pairs should be prioritized for initial support?
4. **Testnet**: Does XT provide a testnet/sandbox environment for testing?
5. **Order Types**: Does XT support additional order types beyond LIMIT and MARKET (IOC, FOK)?
6. **Pagination**: How does XT handle pagination for trade history with large result sets?

---

## Review & Acceptance Checklist

### Specification Completeness
- [x] User scenarios cover all major use cases
- [x] Functional requirements are clear and testable
- [x] Non-functional requirements are measurable
- [x] Key entities and data models are identified
- [x] Technical constraints are documented

### Stakeholder Review
- [ ] Development team reviewed and approved
- [ ] Testing approach validated
- [ ] Security considerations addressed
- [ ] Performance targets are realistic

### Ready for Planning
- [ ] All open questions answered or deferred
- [ ] Dependencies identified and available
- [ ] Resource requirements estimated
- [ ] Risk assessment completed

---

## Execution Status

**Current Phase**: Specification  
**Next Phase**: Planning  
**Blocked**: No  
**Blockers**: None

### Notes
- Specification created based on analysis of existing `xt_spot_api.py` implementation
- XT API uses similar pattern to other exchanges but with custom authentication headers
- Initial implementation will focus on REST API; WebSocket can be added later
- Must transform synchronous requests-based code to async pattern
