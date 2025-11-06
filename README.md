# tri-arb - Multi-Exchange Trading System

**Version 2.0** - 全功能多交易所量化交易系统，支持XT、Binance、OKX、Gate.io。

## 🎉 新功能亮点

### ⚡ WebSocket实时订阅 (NEW!)
- ✅ 实时账户更新推送
- ✅ 实时订单状态推送
- ✅ 实时成交记录推送
- ✅ PostgreSQL数据持久化
- ✅ 自动重连机制

### 🔄 定时监控 (NEW!)
- ✅ 定时查询余额 (`watch-balance`)
- ✅ 定时查询订单 (`watch-orders`)
- ✅ XT账户定时监控 (`watch-account`) - 现货余额、合约余额、合约仓位
- ✅ 可配置时间间隔

### 📊 多交易所支持
- ✅ **XT** - 完整支持
- ✅ **Binance** - 完整支持 + WebSocket
- ✅ **OKX** - 完整支持 + WebSocket
- ✅ **Gate.io** - 完整支持 + WebSocket

## ⚡ 快速开始

### 1. REST API查询（基础功能）

```bash
# 配置API凭证
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
export OKX_API_KEY="..."
export OKX_API_SECRET="..."
export OKX_PASSPHRASE="..."
export XT_API_KEY="..."  # XT现货和永续合约共用
export XT_API_SECRET="..."  # XT现货和永续合约共用

# 查询余额
cextools account balance -x binance -e perp
cextools account balance -x okx -e perp
cextools account balance -x xt -e perp  # XT永续合约
cextools account balance -x xt -e spot  # XT现货

# 查询持仓
cextools account positions -x binance -e perp --symbol BTC/USDT
cextools account positions -x xt -e perp --symbol BTC/USDT

# XT账户定时监控（每10分钟自动获取现货余额、合约余额、合约仓位）
cextools account watch-account

# 定时查询余额（支持所有交易所）
cextools account watch-balance -x xt -e spot --interval 5
cextools account watch-balance -x xt -e perp --interval 5

# 下单
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 50000 --position-side LONG
```

### 2. XT账户定时监控（推荐）

```bash
# 配置XT API密钥（现货和合约共用）
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"

# 启动XT账户定时监控
# 每10分钟自动获取：现货余额、合约余额、合约仓位
# 数据自动保存到PostgreSQL数据库
cextools account watch-account

# 使用命令行参数提供API密钥
cextools account watch-account --api-key YOUR_KEY --api-secret YOUR_SECRET

# 启用调试模式
cextools account watch-account --debug
```

**功能特性**：
- ✅ 自动获取XT现货账户余额
- ✅ 自动获取XT合约账户余额
- ✅ 自动获取XT合约账户仓位
- ✅ 数据自动保存到PostgreSQL（`rest_balances`和`rest_positions`表）
- ✅ 实时表格显示（三个独立表格）
- ✅ 固定10分钟间隔（无需配置）

📚 **详细文档**：查看 [docs/XT_ACCOUNT_SCHEDULER.md](docs/XT_ACCOUNT_SCHEDULER.md)

### 3. WebSocket实时订阅（推荐）

```bash
# 1. 安装依赖
pip install -r requirements-db.txt

# 2. 配置PostgreSQL
bash scripts/configure_postgres_trust.sh

# 3. 启动订阅（首次运行会自动建表）
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
cextools subscribe user-stream -x binance        # Binance永续合约
cextools subscribe user-stream -x okx            # OKX永续合约
cextools subscribe user-stream -x xt              # XT永续合约（默认）
cextools subscribe user-stream -x okx -c order   # OKX只订阅订单
```

📚 **核心文档**：
1. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** ⭐ - 所有命令（5分钟）
2. **[docs/CEXTOOLS_COMPLETE_GUIDE.md](docs/CEXTOOLS_COMPLETE_GUIDE.md)** ⭐ - 完整使用指南（20分钟）
3. **[FEATURES.md](FEATURES.md)** ⭐ - 功能总览
4. **[docs/WEBSOCKET_COMPLETE_GUIDE.md](docs/WEBSOCKET_COMPLETE_GUIDE.md)** - WebSocket指南
5. **[docs/README.md](docs/README.md)** - 文档中心

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

### Arbitrage Monitoring (Feature 004)

Monitor triangular arbitrage opportunities across trading pairs:

```bash
# Single scan (default configuration)
tri-arb monitor

# Custom profit threshold (only show opportunities >= 1%)
tri-arb monitor --min-profit 1.0

# Filter by base currency (e.g., USDT only)
tri-arb monitor --base-currencies USDT

# Realtime monitoring mode (refresh every 10 seconds)
tri-arb monitor --mode realtime --refresh-interval 10

# Debug mode (show all filtered opportunities)
tri-arb monitor --debug
```

**Example Output**:
```
[2025-10-06 10:00:00] 开始扫描市场...
[2025-10-06 10:00:01] 已获取 500 个市场价格

发现 2 条套利机会（按收益率排序）:
┏━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┓
┃ 序号 ┃             路径             ┃ 收益率   ┃ 建议金额 ┃
┡━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━┩
│  1   │ USDT → BTC → ETH → USDT      │  1.25%   │  1000    │
│  2   │ USDT → BNB → ETH → USDT      │  0.80%   │  1000    │
└──────┴──────────────────────────────┴──────────┴──────────┘
```

See [specs/004-xt-get-ticker/quickstart.md](specs/004-xt-get-ticker/quickstart.md) for detailed usage examples.

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
