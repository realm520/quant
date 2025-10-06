<!--
Sync Impact Report - Constitution v1.0.0
Generated: 2025-10-05

VERSION CHANGE: Initial → v1.0.0

MODIFIED PRINCIPLES:
- All principles created (initial version)

ADDED SECTIONS:
- Core Principles (I-V)
- Performance & Quality Standards
- Development Workflow
- Governance

REMOVED SECTIONS:
- None (initial creation)

TEMPLATES REQUIRING UPDATES:
✅ plan-template.md - Reviewed, constitution check section compatible
✅ spec-template.md - Reviewed, requirements align with principles
✅ tasks-template.md - Reviewed, TDD workflow compatible

FOLLOW-UP TODOS:
- None - all placeholders filled
-->

# Tri-Arb Constitution
<!-- Cryptocurrency Triangle Arbitrage Trading System -->

## Core Principles

### I. Type Safety & Error Handling (NON-NEGOTIABLE)
**Mandatory type annotations** for all functions, classes, and variables; **Comprehensive exception handling** with specific error types (never bare except); **Input validation** at system boundaries (API, CLI, external data); **Immutable data structures** where possible to prevent state corruption; **Null safety** patterns (Optional types, explicit None checks).

**Rationale**: Trading systems handle financial transactions where type errors or unhandled exceptions can lead to significant monetary loss. Type safety prevents entire classes of runtime errors, while comprehensive error handling ensures graceful degradation under adverse conditions.

### II. Test-Driven Development (NON-NEGOTIABLE)
**TDD strictly enforced**: Write failing tests → User approval → Implementation; **Contract tests mandatory** for all exchange integrations and external APIs; **Integration tests required** for trading workflows and multi-component interactions; **Backtest validation** for all trading strategies with historical data; **Performance tests** with latency targets (<50ms p95) before production deployment.

**Rationale**: In high-frequency trading environments, untested code can execute thousands of trades with bugs, amplifying losses exponentially. TDD ensures correctness before capital is at risk, while backtesting validates strategy profitability.

### III. Performance-First Architecture
**Latency targets**: <50ms p95 for order execution, <10ms for price data processing; **Async-first design** using asyncio for all I/O operations (network, database); **Memory efficiency**: Streaming data processing, no unbounded caches; **Batching strategy**: Aggregate operations where latency permits (logging, metrics); **Hot path optimization**: Profile and optimize critical execution paths monthly.

**Rationale**: Arbitrage opportunities exist in millisecond windows. A 100ms delay can mean the difference between profitable and unprofitable trades. Performance must be designed in from the start, not retrofitted later.

### IV. Observability & Audit Trail
**Structured logging** (JSON format) for all system events with correlation IDs; **Performance metrics** tracked for every critical path (order latency, API response times); **Audit trail** for all trading decisions: inputs, outputs, timestamps, reasoning; **Error context** preservation: full stack traces, system state, external conditions; **Alerting thresholds** for latency, error rates, and anomalous trading patterns.

**Rationale**: Post-incident debugging requires detailed context. Regulatory compliance demands complete audit trails. Performance degradation must be detected before profitability suffers.

### V. Simplicity & Maintainability
**YAGNI principle**: Implement only what's needed for current requirements; **Cyclomatic complexity <10** per function, refactor if exceeded; **Code review mandatory** for all changes with performance and correctness focus; **Documentation**: Docstrings for public APIs, inline comments for complex algorithms; **Dependency discipline**: Minimize third-party libraries, justify each addition.

**Rationale**: Complex systems are harder to debug under time pressure. Trading logic must be understandable by new team members quickly. Technical debt compounds in high-stakes environments.

## Performance & Quality Standards

### Technology Stack
- **Language**: Python 3.11+ (required for performance improvements)
- **Type Checking**: mypy (strict mode) + ruff for linting
- **Async Runtime**: asyncio with uvloop for event loop optimization
- **Testing**: pytest with pytest-asyncio, pytest-benchmark
- **Logging**: structlog for structured JSON logging
- **Monitoring**: Prometheus metrics, Grafana dashboards

### Performance Benchmarks
- **Order Execution**: <50ms p95 from signal to order submission
- **Price Processing**: <10ms p95 for multi-exchange price aggregation
- **Memory**: <500MB steady-state, <1GB peak during high volatility
- **CPU**: <70% average utilization to handle traffic spikes
- **Network**: Connection pooling, retry with exponential backoff

### Quality Gates
- **Test Coverage**: ≥90% for core trading logic, ≥80% overall
- **Type Coverage**: 100% (no Any types without justification)
- **Linting**: Zero ruff violations (errors), warnings allowed with comments
- **Performance**: All benchmarks must pass before merging
- **Documentation**: Public APIs 100% documented, complex algorithms explained

## Development Workflow

### Branching Strategy
- **Feature branches**: `feature/###-description` from main
- **Never commit directly to main**: All changes via pull requests
- **Branch naming**: Include issue number for traceability

### Pull Request Requirements
1. **Tests pass**: All existing + new tests green
2. **Performance benchmarks**: No regressions in critical paths
3. **Type checking**: mypy strict mode passes
4. **Code review**: At least one approval focused on correctness and performance
5. **Changelog**: Update with user-facing changes

### Testing Phases
1. **Contract Tests**: Validate exchange API integration (run first)
2. **Unit Tests**: Test individual components in isolation
3. **Integration Tests**: Multi-component workflows (order → execution → reconciliation)
4. **Backtest**: Strategy validation with ≥6 months historical data
5. **Performance Tests**: Latency and throughput validation under load

### Deployment Process
1. **Staging environment**: Deploy and soak test for 24 hours
2. **Canary deployment**: 10% of capital for 1 hour, monitor closely
3. **Full deployment**: If canary metrics healthy (latency, error rate, P&L)
4. **Rollback plan**: Automated rollback if error rate >1% or latency >2x baseline

## Governance

### Amendment Process
1. **Proposal**: Document rationale, impact analysis, migration plan
2. **Review**: Team review with focus on necessity and risk
3. **Approval**: Unanimous consent for BREAKING changes, majority for additions
4. **Implementation**: Update constitution, templates, and dependent docs
5. **Communication**: Announce changes, update onboarding materials

### Version Control
- **Format**: MAJOR.MINOR.PATCH (semantic versioning)
- **MAJOR**: Backward-incompatible principle removals or redefinitions
- **MINOR**: New principles or materially expanded guidance
- **PATCH**: Clarifications, wording, non-semantic refinements

### Compliance Review
- **Frequency**: Quarterly review of adherence to principles
- **Scope**: Code review samples, incident postmortems, performance metrics
- **Action**: Document violations, create remediation plans, update guidance
- **Enforcement**: Blocking PRs that violate NON-NEGOTIABLE principles

### Agent Guidance
Runtime development guidance for AI coding assistants is maintained in repository root files (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot). These files translate constitutional principles into actionable development patterns and should be kept synchronized with this constitution.

**Version**: 1.0.0 | **Ratified**: 2025-10-05 | **Last Amended**: 2025-10-05
