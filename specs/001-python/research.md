# Research & Technical Decisions

**Feature**: Python Triangle Arbitrage Scaffold
**Date**: 2025-10-05
**Status**: Complete

## Summary

This document captures all technical decisions and research findings for the MVP scaffold implementation. All unknowns have been resolved based on the project requirements (cryptocurrency triangle arbitrage trading system) and constitutional principles (type safety, performance-first, observability).

## Technology Decisions

### 1. Package Management: uv

**Decision**: Use uv as the primary package and virtual environment manager

**Rationale**:
- Modern, fast Python package manager (100x faster than pip)
- Built-in virtual environment management
- Compatible with pyproject.toml standard
- Lock file support for reproducible builds
- Better dependency resolution than pip

**Alternatives Considered**:
- **pip + venv**: Traditional but slower, no lock file, manual venv management
- **poetry**: Feature-rich but slower than uv, additional complexity
- **pip-tools**: Good but requires more manual setup

**Implementation Notes**:
- Configure via pyproject.toml (PEP 621 compliant)
- Use `uv sync` for dependency installation
- Generate uv.lock for reproducible environments

### 2. Async Runtime: asyncio + uvloop

**Decision**: Use asyncio with uvloop optimization

**Rationale**:
- Constitutional requirement: async-first design for all I/O
- uvloop provides 2-4x performance improvement over standard asyncio
- Native Python 3.11+ async features (TaskGroup, ExceptionGroup)
- Minimal configuration required

**Alternatives Considered**:
- **asyncio only**: Slower event loop, doesn't meet performance targets
- **trio**: Different async paradigm, smaller ecosystem
- **gevent**: Monkey-patching approach, harder to debug

**Implementation Notes**:
- Install uvloop and set as default event loop policy in `__main__.py`
- Use async/await throughout codebase for I/O operations
- Leverage Python 3.11+ async context managers

### 3. HTTP Client: httpx

**Decision**: Use httpx for async HTTP communication with exchanges

**Rationale**:
- Native async/await support
- HTTP/2 support for multiplexing requests
- Connection pooling built-in
- Timeout and retry handling
- Similar API to requests (easy migration path)

**Alternatives Considered**:
- **aiohttp**: Popular but less ergonomic API, HTTP/1.1 only
- **requests**: Synchronous, doesn't fit async-first architecture

**Implementation Notes**:
- Configure connection pools per exchange
- Implement retry with exponential backoff
- Set appropriate timeouts (<50ms for critical paths)

### 4. WebSocket Client: websockets

**Decision**: Use websockets library for real-time price feeds

**Rationale**:
- Simple, focused WebSocket client
- Async/await native
- Low overhead, good performance
- Widely used and well-maintained

**Alternatives Considered**:
- **aiohttp WebSocket**: Tied to aiohttp, more heavyweight
- **python-socketio**: Socket.IO protocol, not needed for standard WebSocket

**Implementation Notes**:
- Implement reconnection logic with exponential backoff
- Handle ping/pong for connection health monitoring
- Buffer messages for backpressure handling

### 5. Database: SQLite + aiosqlite

**Decision**: Use SQLite with async wrapper aiosqlite

**Rationale**:
- Lightweight, serverless database (no separate process)
- Sufficient for single-machine deployment
- ACID guarantees for transaction safety
- aiosqlite provides async interface
- Easy to deploy and maintain

**Alternatives Considered**:
- **PostgreSQL**: Overkill for MVP, requires separate service
- **File-based storage**: No ACID guarantees, harder to query
- **Redis**: In-memory only, persistence limitations

**Implementation Notes**:
- Use connection pooling for concurrent access
- Implement repository pattern for data access abstraction
- Enable WAL mode for better concurrent read performance

### 6. Caching: cachetools

**Decision**: Use cachetools for in-memory caching

**Rationale**:
- Pure Python, no external dependencies
- Multiple cache strategies (LRU, TTL, LFU)
- Thread-safe implementations
- Lightweight and fast

**Alternatives Considered**:
- **Redis**: Requires separate service, overkill for MVP
- **functools.lru_cache**: Limited features, no TTL support
- **diskcache**: Disk-based, slower than memory

**Implementation Notes**:
- Use TTLCache for price data (short TTL ~60s)
- Use LRUCache for exchange metadata (longer-lived)
- Wrap in async-safe access patterns

### 7. Data Validation: pydantic

**Decision**: Use pydantic v2 for data modeling and validation

**Rationale**:
- Runtime type validation with Python type hints
- Excellent performance (Rust core in v2)
- JSON serialization/deserialization built-in
- Integration with pydantic-settings for configuration
- Comprehensive documentation and ecosystem

**Alternatives Considered**:
- **dataclasses + dacite**: Less validation features
- **marshmallow**: Older, slower, less type-safe
- **attrs**: Good but less validation features

**Implementation Notes**:
- Use for all data models (TradingPair, Order, etc.)
- Enable strict mode for type checking
- Use Field validators for complex validation logic

### 8. Configuration: pydantic-settings

**Decision**: Use pydantic-settings for configuration management

**Rationale**:
- Type-safe configuration with validation
- Environment variable support (.env files)
- Multiple source support (env, yaml, json)
- Seamless integration with pydantic models

**Alternatives Considered**:
- **python-dotenv + dataclasses**: Manual validation, less type safety
- **dynaconf**: More features but added complexity
- **configparser**: Basic, no type safety

**Implementation Notes**:
- Define Settings class with BaseSettings
- Support .env files for local development
- Environment-specific configuration (dev, test, prod)

### 9. CLI Framework: typer

**Decision**: Use typer for CLI application

**Rationale**:
- Type hints for automatic help generation
- Built on click (mature, stable)
- Excellent developer experience
- Automatic command documentation
- Parameter validation via type hints

**Alternatives Considered**:
- **click**: More verbose, no type hints
- **argparse**: Standard library but basic features
- **fire**: Magic-based, less explicit

**Implementation Notes**:
- Command groups for organization (start, status, config)
- Rich integration for beautiful terminal output
- Progress bars for long-running operations

### 10. Logging: structlog

**Decision**: Use structlog for structured logging

**Rationale**:
- Constitutional requirement: structured JSON logging
- Correlation ID support for request tracing
- Context binding for rich log data
- Multiple output formats (JSON, console)
- Performance-oriented design

**Alternatives Considered**:
- **logging + json formatter**: Manual structure, less ergonomic
- **loguru**: Nice API but less structured output control
- **python-json-logger**: Basic, less features

**Implementation Notes**:
- JSON format for production, human-readable for dev
- Bind correlation IDs to all log messages
- Configure log levels per module
- Integrate with async context for request tracking

### 11. Metrics: prometheus-client

**Decision**: Use prometheus-client for metrics collection

**Rationale**:
- Industry standard for metrics
- Constitutional requirement: performance metrics tracking
- Pull-based model (no external dependencies)
- Rich metric types (Counter, Gauge, Histogram)
- Integration with Grafana for dashboards

**Alternatives Considered**:
- **statsd**: Push-based, requires separate service
- **Custom metrics**: Reinventing the wheel
- **OpenTelemetry**: Overkill for MVP, complex setup

**Implementation Notes**:
- Expose metrics endpoint for Prometheus scraping
- Track key metrics (request latency, error rates, cache hits)
- Use Histogram for latency measurements
- Label metrics by exchange, symbol, operation

### 12. Testing: pytest Ecosystem

**Decision**: Use pytest with pytest-asyncio, pytest-benchmark, pytest-mock

**Rationale**:
- Constitutional requirement: comprehensive testing
- pytest-asyncio for async test support
- pytest-benchmark for performance validation
- pytest-mock for mocking dependencies
- Rich plugin ecosystem

**Alternatives Considered**:
- **unittest**: Standard library but less features
- **nose2**: Less active development
- **standalone async testing**: More manual setup

**Implementation Notes**:
- Organize tests by layer (unit, integration, contract)
- Use fixtures for common setup (database, cache, mocks)
- Performance benchmarks for critical paths
- Coverage reporting with pytest-cov

### 13. Code Quality: mypy + ruff

**Decision**: Use mypy strict mode for type checking, ruff for linting/formatting

**Rationale**:
- Constitutional requirement: 100% type coverage
- mypy strict mode catches type errors
- ruff combines linting + formatting (fast, Rust-based)
- Zero configuration for most Python projects

**Alternatives Considered**:
- **pyright**: Fast but less configurable
- **flake8 + black + isort**: Multiple tools, slower
- **pylint**: Slower, more opinionated

**Implementation Notes**:
- mypy.ini with strict = true
- ruff.toml for custom rules
- Pre-commit hooks for automatic checking
- CI integration for enforcement

### 14. Binary Packaging: PyInstaller

**Decision**: Use PyInstaller for single-file executable generation

**Rationale**:
- User requirement: binary packaging for deployment
- Cross-platform support (Linux, macOS, Windows)
- Single-file output option
- Hidden imports detection
- Mature, widely used

**Alternatives Considered**:
- **Nuitka**: Better performance but slower compilation
- **cx_Freeze**: Less features, more manual configuration
- **shiv**: PEZ format, requires Python runtime

**Implementation Notes**:
- One-file mode for easy distribution
- Specify hidden imports for dynamic imports
- Build script (scripts/build.sh) for automation
- Test binary on target platform

### 15. Service Management: systemd

**Decision**: Use systemd for service management on Linux servers

**Rationale**:
- User requirement: systemd deployment
- Standard on modern Linux distributions
- Process monitoring and auto-restart built-in
- Resource limits and isolation
- Logging integration with journald

**Alternatives Considered**:
- **supervisord**: Additional dependency, less integrated
- **Docker**: More complex, not requested
- **PM2**: Node.js-based, not ideal for Python

**Implementation Notes**:
- Service file in scripts/systemd/tri-arb.service
- Restart policy: on-failure with exponential backoff
- Resource limits: memory, CPU
- Environment variable support

## Implementation Priorities

### MVP Phase 1 (Scaffold)
1. Project structure and packaging (pyproject.toml, uv setup)
2. Configuration management (pydantic-settings)
3. Logging infrastructure (structlog)
4. CLI framework (typer)
5. Testing setup (pytest with plugins)
6. Code quality tools (mypy, ruff)

### MVP Phase 2 (Core Modules)
1. Core data models with validation (pydantic)
2. Exception hierarchy
3. Database setup (aiosqlite)
4. Cache wrapper (cachetools)
5. Exchange base interface (ABC)
6. Service layer placeholders

### MVP Phase 3 (Deployment)
1. Build scripts (PyInstaller)
2. Deployment scripts (systemd)
3. Health check endpoint
4. Metrics collection setup
5. Documentation (README, quickstart, architecture)

## Risk Mitigation

### Performance Risks
- **Risk**: Scaffold overhead impacts performance targets
- **Mitigation**: Async-first design, minimal dependencies, performance benchmarks in tests

### Complexity Risks
- **Risk**: Over-engineering for MVP
- **Mitigation**: Clear MVP scope, placeholder implementations, iterative approach

### Dependency Risks
- **Risk**: Dependency conflicts or vulnerabilities
- **Mitigation**: Lock file (uv.lock), minimal dependencies (15 core), regular updates

## Open Questions (None)

All technical unknowns have been resolved. Ready to proceed to Phase 1 (Design & Contracts).
