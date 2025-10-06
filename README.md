# tri-arb - Triangle Arbitrage Trading System

**MVP Scaffold v0.1.0** - Python-based triangle arbitrage trading system with async architecture and production-ready infrastructure.

> ⚠️ **PLACEHOLDER MODE**: This is an MVP scaffold implementation. All trading logic returns placeholder data. No actual trading occurs.

## 📋 Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing](#testing)
- [Deployment](#deployment)
- [Development](#development)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

## ✨ Features

### Core Capabilities
- **Triangle Arbitrage Detection**: Placeholder algorithms for detecting arbitrage opportunities across trading pairs
- **Multi-Exchange Support**: Binance and OKX exchange adapters (placeholder implementations)
- **Async Architecture**: Built on uvloop + asyncio for high-performance I/O
- **Type Safety**: 100% type-annotated code with mypy strict mode
- **Production Ready**: Logging, metrics, health checks, and monitoring

### Technical Stack
- **Python 3.11+** with strict type checking
- **uv** for fast package management and dependency resolution
- **Pydantic v2** for data validation with Rust-based performance
- **Typer** for beautiful CLI with automatic help generation
- **structlog** for structured JSON logging
- **Prometheus** for metrics collection and monitoring
- **aiosqlite** for async SQLite database access
- **pytest** with async support for comprehensive testing

## 🏗️ Architecture

**7-Layer Architecture**:
1. **Core Layer**: Data models, business logic, exceptions
2. **Exchange Layer**: Exchange adapters and factory pattern
3. **Data Layer**: Database, cache, repository pattern
4. **Service Layer**: Business services and orchestration
5. **Config Layer**: Settings, logging, configuration management
6. **CLI Layer**: Typer-based command-line interface
7. **Utils Layer**: Metrics, health checks, async utilities

See [docs/architecture.md](docs/architecture.md) for detailed architecture documentation.

## 📦 Installation

### Prerequisites
- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Install uv
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Setup Project
```bash
# Clone repository
git clone https://github.com/yourusername/tri-arb.git
cd tri-arb

# Complete setup (environment + dependencies + dev tools)
make setup

# Or manual setup
uv venv --python 3.11
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate   # On Windows
uv pip install -e ".[dev]"
```

## 🚀 Quick Start

### Basic Commands
```bash
# Show version
tri-arb --version

# Show help
tri-arb --help

# Start system (placeholder mode)
tri-arb start

# Check system status
tri-arb status

# Show configuration
tri-arb config show

# Validate configuration
tri-arb config validate
```

### Configuration
```bash
# Copy example configuration
cp .env.example .env
cp config/config.example.yaml config/config.yaml

# Edit configuration
nano config/config.yaml

# Set configuration value
tri-arb config set log_level DEBUG --persist
```

## ⚙️ Configuration

### Environment Variables
Create `.env` file:
```bash
# Application
APP_NAME=tri-arb
ENVIRONMENT=development
LOG_LEVEL=INFO

# Database
DB_PATH=tri_arb.db
DB_POOL_SIZE=10
DB_TIMEOUT=5.0

# Cache
CACHE_TTL=60
CACHE_MAX_SIZE=10000

# Performance
MAX_WORKERS=10
RATE_LIMIT=100

# Monitoring
METRICS_ENABLED=true
METRICS_PORT=9090
```

### YAML Configuration
Edit `config/config.yaml`:
```yaml
app:
  name: tri-arb
  environment: development
  log_level: INFO

database:
  path: tri_arb.db
  pool_size: 10
  timeout: 5.0

cache:
  ttl: 60
  max_size: 10000

exchanges:
  binance:
    enabled: true
    api_key: ""
    api_secret: ""
  okx:
    enabled: true
    api_key: ""
    api_secret: ""
    passphrase: ""

monitoring:
  metrics_enabled: true
  metrics_port: 9090
```

## 📖 Usage

### Starting the System
```bash
# Start in placeholder mode (default)
tri-arb start

# Start with specific mode
tri-arb start --mode backtest

# Start in dry-run mode
tri-arb start --dry-run

# Start with custom config
tri-arb start --config /path/to/config.yaml
```

### Monitoring
```bash
# Check system status
tri-arb status

# Detailed status
tri-arb status --detailed

# Status as JSON
tri-arb status --json
```

### Configuration Management
```bash
# Show all configuration
tri-arb config show

# Show specific key
tri-arb config show log_level

# Set configuration value
tri-arb config set cache_ttl 120

# Validate configuration file
tri-arb config validate

# Validate custom config
tri-arb config validate --file custom-config.yaml
```

## 🧪 Testing

### Run Tests
```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test
make test-specific TEST=test_models

# Run unit tests only
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run contract tests
pytest tests/contract/

# Run with markers
pytest -m unit        # Only unit tests
pytest -m integration # Only integration tests
pytest -m contract    # Only contract tests
```

### Code Quality
```bash
# Run all checks
make check

# Linting
make lint

# Formatting
make format

# Type checking
mypy src/

# Pre-commit checks (format + lint + test)
make pre-commit
```

## 🚢 Deployment

### Build Executable
```bash
# Build standalone executable
bash scripts/build.sh

# Executable will be in dist/tri-arb
./dist/tri-arb --version
```

### System Deployment
```bash
# Deploy to system (requires root)
sudo bash scripts/deploy.sh

# This will:
# 1. Build the application
# 2. Install to /opt/tri-arb
# 3. Create system user
# 4. Set up systemd service
# 5. Create symbolic link in /usr/local/bin
```

### Systemd Service
```bash
# Enable service
sudo systemctl enable tri-arb

# Start service
sudo systemctl start tri-arb

# Check status
sudo systemctl status tri-arb

# View logs
sudo journalctl -u tri-arb -f

# Stop service
sudo systemctl stop tri-arb

# Restart service
sudo systemctl restart tri-arb
```

## 👨‍💻 Development

### Development Setup
```bash
# Install dev dependencies
make install-dev

# Run in development mode
python -m tri_arb start --verbose
```

### Development Workflow
1. **Write tests first** (TDD approach)
2. **Implement features** following type hints
3. **Run quality checks** with `make check`
4. **Run tests** with coverage
5. **Commit changes** with descriptive messages

See [docs/development.md](docs/development.md) for detailed development guide.

## 📁 Project Structure

```
tri-arb/
├── src/tri_arb/           # Source code
│   ├── core/              # Core business logic
│   ├── exchanges/         # Exchange adapters
│   ├── data/              # Data layer (DB, cache)
│   ├── services/          # Business services
│   ├── config/            # Configuration
│   ├── cli/               # CLI commands
│   └── utils/             # Utilities
├── tests/                 # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── contract/          # Contract tests
├── config/                # Configuration files
├── scripts/               # Build and deployment scripts
├── docs/                  # Documentation
├── Makefile               # Development tasks
└── pyproject.toml         # Project metadata
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following the style guide
4. Run tests and quality checks (`make check`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

**This is an MVP scaffold for educational and development purposes.**

- All trading logic is placeholder implementation
- No actual trading occurs in this version
- Not suitable for production trading without significant enhancements
- Use at your own risk

## 🔗 Links

- **Documentation**: [docs/](docs/)
- **Architecture**: [docs/architecture.md](docs/architecture.md)
- **Development Guide**: [docs/development.md](docs/development.md)
- **Issues**: https://github.com/yourusername/tri-arb/issues

## 📞 Support

For questions and support:
- Open an issue on GitHub
- Contact: your-email@example.com

---

**Built with ❤️ using Python, uv, and modern async architecture**
