# Quickstart Guide

**Feature**: Python Triangle Arbitrage Scaffold
**Date**: 2025-10-05
**Target Audience**: Developers setting up the project for the first time

## Prerequisites

Before starting, ensure you have:

- **Python 3.11+** installed
- **uv** package manager installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Git** for version control
- **Make** (optional, for convenience commands)
- **Linux/macOS** operating system (Windows via WSL2)

## Quick Setup (5 minutes)

### 1. Clone and Navigate
```bash
git clone <repository-url> tri-arb
cd tri-arb
```

### 2. Install Dependencies
```bash
# Using uv (recommended)
uv sync

# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows
```

### 3. Verify Installation
```bash
# Check that tri-arb CLI is available
tri-arb --help

# Expected output:
# Usage: tri-arb [OPTIONS] COMMAND [ARGS]...
#
# Cryptocurrency triangle arbitrage trading system scaffold
#
# Commands:
#   start         Start the arbitrage monitoring system
#   status        Check system status
#   config        Manage configuration
#   health-check  Check system health
```

### 4. Run Health Check
```bash
tri-arb health-check

# Expected output:
# ✓ Configuration: OK
# ✓ Database: OK (SQLite connected)
# ✓ Cache: OK (in-memory cache ready)
# ✓ Logging: OK (structlog configured)
# ✓ Metrics: OK (Prometheus endpoint ready)
# System Status: HEALTHY
```

### 5. Test Configuration
```bash
# View current configuration
tri-arb config show

# Validate configuration
tri-arb config validate

# Expected output:
# Configuration file: config/config.yaml
# Status: VALID
# All required fields present
# Type validation: PASSED
```

## Basic Usage

### Start the System
```bash
# Start with default configuration
tri-arb start

# Expected output:
# [2025-10-05 10:00:00] INFO     Starting tri-arb v0.1.0
# [2025-10-05 10:00:00] INFO     Configuration loaded from config/config.yaml
# [2025-10-05 10:00:00] INFO     Database initialized: tri_arb.db
# [2025-10-05 10:00:00] INFO     Cache initialized (TTL: 60s, max_size: 1000)
# [2025-10-05 10:00:00] INFO     Metrics server started on port 9090
# [2025-10-05 10:00:00] INFO     System ready (placeholder mode - no trading logic)
# [2025-10-05 10:00:00] INFO     Press Ctrl+C to stop
```

### Check Status
```bash
# In another terminal
tri-arb status

# Expected output:
# System Status: RUNNING
# Uptime: 00:05:23
# Active Connections: 0 (placeholder)
# Opportunities Detected: 0 (placeholder)
# Orders Executed: 0 (placeholder)
# Memory Usage: 45 MB
# CPU Usage: 0.5%
```

### View Metrics
```bash
# Metrics available at http://localhost:9090/metrics
curl http://localhost:9090/metrics

# Expected output (Prometheus format):
# # HELP tri_arb_requests_total Total number of requests
# # TYPE tri_arb_requests_total counter
# tri_arb_requests_total 0
#
# # HELP tri_arb_opportunities_detected Total opportunities detected
# # TYPE tri_arb_opportunities_detected counter
# tri_arb_opportunities_detected 0
```

## Development Workflow

### Running Tests
```bash
# Run all tests
make test
# or
pytest

# Run with coverage
make test-cov
# or
pytest --cov=src/tri_arb --cov-report=html

# Run specific test file
pytest tests/unit/test_core/test_models.py

# Run performance benchmarks
pytest tests/ -k benchmark
```

### Code Quality Checks
```bash
# Type checking with mypy
make lint
# or
mypy src/

# Code formatting and linting with ruff
ruff check src/
ruff format src/

# Run all quality checks
make check
# or
make lint && make format && make test
```

### Building the Project
```bash
# Build binary with PyInstaller
make build
# or
./scripts/build.sh

# Output: dist/tri-arb (single-file executable)

# Test the binary
./dist/tri-arb --help
./dist/tri-arb health-check
```

## Configuration

### Environment Variables
Create a `.env` file from the example:
```bash
cp config/.env.example .env
```

Edit `.env` with your settings:
```bash
# Application
APP_NAME=tri-arb
LOG_LEVEL=INFO

# Database
DB_PATH=tri_arb.db
DB_POOL_SIZE=5

# Cache
CACHE_TTL=60
CACHE_MAX_SIZE=1000

# Performance
MAX_CONCURRENT_REQUESTS=10
REQUEST_TIMEOUT=30

# Monitoring
METRICS_PORT=9090
HEALTH_CHECK_INTERVAL=30
```

### YAML Configuration
Edit `config/config.yaml` for more advanced settings:
```yaml
app:
  name: tri-arb
  log_level: INFO

database:
  path: tri_arb.db
  pool_size: 5

cache:
  ttl: 60  # seconds
  max_size: 1000

exchanges:
  - name: binance
    enabled: false  # Placeholder only
  - name: okx
    enabled: false  # Placeholder only

monitoring:
  metrics_port: 9090
  health_check_interval: 30
```

## Testing the Scaffold

### Manual Testing Checklist

- [ ] Installation completes without errors
- [ ] Virtual environment activates successfully
- [ ] `tri-arb --help` displays command help
- [ ] `tri-arb health-check` returns HEALTHY status
- [ ] `tri-arb config show` displays configuration
- [ ] `tri-arb config validate` passes validation
- [ ] `tri-arb start` starts without errors
- [ ] `tri-arb status` shows system as RUNNING
- [ ] Metrics endpoint responds at http://localhost:9090/metrics
- [ ] All tests pass (`pytest`)
- [ ] Type checking passes (`mypy src/`)
- [ ] Linting passes (`ruff check src/`)
- [ ] Binary builds successfully (`make build`)
- [ ] Binary executable runs (`./dist/tri-arb --help`)

### Expected Behavior (MVP Scaffold)

The MVP scaffold is **infrastructure only**. It should:

✅ **Work**:
- Install and configure correctly
- Start and stop cleanly
- Respond to CLI commands
- Pass all tests
- Generate metrics
- Log structured messages
- Build to binary

❌ **Not Work (Placeholder)**:
- Actual exchange connections
- Real arbitrage calculations
- Order execution
- Risk management
- Trading logic

All trading-related functionality returns placeholder responses or logs "placeholder mode" messages.

## Troubleshooting

### Issue: `command not found: tri-arb`
**Solution**: Activate virtual environment
```bash
source .venv/bin/activate
```

### Issue: `ModuleNotFoundError: No module named 'tri_arb'`
**Solution**: Install in editable mode
```bash
uv pip install -e .
```

### Issue: `Database file is locked`
**Solution**: Stop all running instances
```bash
pkill -f tri-arb
rm tri_arb.db  # Remove lock file
tri-arb start
```

### Issue: `Port 9090 already in use`
**Solution**: Change metrics port
```bash
export METRICS_PORT=9091
tri-arb start
```

### Issue: Tests fail with `ImportError`
**Solution**: Install dev dependencies
```bash
uv pip install -e ".[dev]"
```

## Next Steps

After completing the quickstart:

1. **Read Architecture Documentation**: `docs/architecture.md`
2. **Review Development Guide**: `docs/development.md`
3. **Explore Test Examples**: `tests/unit/`, `tests/integration/`
4. **Check Data Models**: `src/tri_arb/core/models.py`
5. **Understand Module Organization**: `src/tri_arb/` directory structure

## Getting Help

- **Documentation**: See `docs/` directory
- **Examples**: See `tests/` for usage examples
- **Issues**: Open an issue on GitHub
- **Code**: Review inline comments and docstrings

## Deployment (Optional)

For production deployment, see:
- `scripts/deploy.sh` - Deployment automation
- `scripts/systemd/tri-arb.service` - systemd service configuration
- `docs/deployment.md` - Detailed deployment guide

Quick deployment test:
```bash
# Build binary
make build

# Test systemd service (requires sudo)
sudo cp scripts/systemd/tri-arb.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start tri-arb
sudo systemctl status tri-arb
```

## Summary

You've successfully:
- ✅ Installed the tri-arb scaffold
- ✅ Verified all components work
- ✅ Run basic commands
- ✅ Checked system health
- ✅ Reviewed configuration
- ✅ Run tests and quality checks
- ✅ Built the binary

The scaffold is ready for development. All placeholder components can now be replaced with actual trading logic in future iterations.
