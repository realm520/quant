# CEXTools macOS 部署使用指南

本指南将帮助您在 macOS 系统上成功部署和使用 CEXTools，这是一个支持多交易所的量化交易工具。

## 📋 目录

- [系统要求](#系统要求)
- [安装方法](#安装方法)
- [环境配置](#环境配置)
- [快速开始](#快速开始)
- [常用命令](#常用命令)
- [高级功能](#高级功能)
- [故障排查](#故障排查)
- [最佳实践](#最佳实践)

## 🖥️ 系统要求

### macOS 版本要求
- **macOS 10.15 (Catalina)** 或更高版本
- **推荐**: macOS 12.0 (Monterey) 或更高版本

### 硬件要求
- **内存**: 至少 4GB RAM（推荐 8GB+）
- **存储**: 至少 2GB 可用磁盘空间
- **网络**: 稳定的互联网连接

### 软件依赖
- **Python 3.11+** (必需)
- **Git** (用于克隆代码)
- **Homebrew** (推荐，用于安装依赖)

## 🚀 安装方法

### 方法 1: 本地开发安装（推荐）

这是最完整的安装方式，适合日常使用和开发：

```bash
# 1. 安装 Homebrew（如果尚未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安装 Python 3.11 和 Git
brew install python@3.11 git

# 3. 安装 UV（现代 Python 包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc  # 或 ~/.bash_profile

# 4. 克隆项目
git clone https://github.com/realm520/quant.git
cd quant

# 5. 创建虚拟环境并安装依赖
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# 6. 验证安装
cextools --help
```

### 方法 2: 使用 Makefile（自动化安装）

项目提供了 Makefile 来简化安装过程：

```bash
# 克隆项目
git clone https://github.com/realm520/quant.git
cd quant

# 一键安装
make setup

# 激活虚拟环境
source .venv/bin/activate

# 验证安装
cextools --help
```

### 方法 3: uvx 远程运行（无需安装）

适合临时使用或测试，无需本地安装：

```bash
# 安装 UV（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc

# 直接运行（首次运行会下载和缓存）
uvx --from git+https://github.com/realm520/quant.git@main cextools --help

# 查看 BTC 价格
uvx --from git+https://github.com/realm520/quant.git@main cextools market ticker BTC/USDT
```

### 方法 4: 从 GitHub 直接安装

```bash
# 安装 UV
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc

# 直接安装
uv pip install git+https://github.com/realm520/quant.git

# 运行
cextools --help
```

## ⚙️ 环境配置

### 1. API 凭证配置

CEXTools 支持多个交易所，需要配置相应的 API 凭证：

#### Binance 交易所
```bash
# 添加到 ~/.zshrc 或 ~/.bash_profile
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"

# 重新加载配置
source ~/.zshrc
```

#### OKX 交易所
```bash
# OKX 需要三个参数
export OKX_API_KEY="your_okx_api_key"
export OKX_API_SECRET="your_okx_api_secret"
export OKX_PASSPHRASE="your_okx_passphrase"

# 重新加载配置
source ~/.zshrc
```

#### XT 交易所
```bash
export XT_API_KEY="your_xt_api_key"
export XT_API_SECRET="your_xt_api_secret"

# 重新加载配置
source ~/.zshrc
```

### 2. 创建配置文件

```bash
# 复制配置示例
cp config/config.example.yaml config/config.yaml

# 编辑配置文件（可选）
nano config/config.yaml
```

### 3. 数据库配置（WebSocket 功能需要）

如果需要使用 WebSocket 订阅功能，需要配置 PostgreSQL：

#### 使用 Homebrew 安装 PostgreSQL
```bash
# 安装 PostgreSQL
brew install postgresql@15

# 启动服务
brew services start postgresql@15

# 创建数据库
createdb trading

# 设置环境变量
export DATABASE_URL="postgresql+asyncpg://$(whoami)@localhost:5432/trading"
```

#### 使用 Docker（推荐）
```bash
# 启动 PostgreSQL 容器
docker run --name postgres-trading \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=trading \
  -p 5432:5432 \
  -d postgres:15

# 设置环境变量
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/trading"
```

## 🎯 快速开始

### 1. 验证安装

```bash
# 检查版本
cextools version

# 查看帮助
cextools --help

# 查看子命令帮助
cextools market --help
cextools account --help
```

### 2. 测试连接

```bash
# 测试 Binance 连接（需要 API 凭证）
cextools account balance -x binance -e perp

# 测试 OKX 连接（需要 API 凭证）
cextools account balance -x okx -e perp

# 测试公开 API（无需凭证）
cextools market ticker -x binance -s BTC/USDT
```

### 3. 基本使用

```bash
# 查看 BTC 价格
cextools market ticker BTC/USDT

# 查看订单簿
cextools market orderbook BTC/USDT --depth 20

# 查看账户余额
cextools account balance -x binance -e perp
```

## 📝 常用命令

### 市场数据查询

```bash
# 实时价格查询
cextools market ticker BTC/USDT
cextools market ticker ETH/USDT

# 订单簿深度
cextools market orderbook BTC/USDT --depth 50
cextools market orderbook ETH/USDT --depth 100

# K线数据
cextools market klines BTC/USDT --interval 1h --limit 24

# 实时监控
cextools market watch BTC/USDT --interval 5
```

### 账户管理

```bash
# 查询余额
cextools account balance -x binance -e perp
cextools account balance -x okx -e perp

# 查询持仓
cextools account positions -x binance -e perp
cextools account positions -x okx -e perp

# 查询挂单
cextools account orders -x binance -e perp
cextools account orders -x okx -e perp

# 定时查询余额
cextools account watch-balance -x binance -e perp -i 5
```

### 订单管理

```bash
# 下单（限价单）
cextools order place -x binance -e perp -s BTC/USDT \
  --side buy -q 0.001 -p 50000 --position-side LONG

# 下单（市价单）
cextools order place -x binance -e perp -s BTC/USDT \
  --side buy -q 0.001 --type market --position-side LONG

# 查询订单
cextools order list -x binance -e perp -s BTC/USDT

# 撤销订单
cextools order cancel -x binance -e perp -s BTC/USDT --order-id 123456
```

### 输出格式

```bash
# 表格格式（默认）
cextools account balance -x binance -e perp

# JSON 格式
cextools account balance -x binance -e perp --output json

# CSV 格式
cextools account balance -x binance -e perp --output csv > balance.csv
```

## 🔧 高级功能

### WebSocket 订阅

```bash
# 订阅用户数据流
cextools subscribe user-stream -x binance
cextools subscribe user-stream -x okx

# 选择性订阅
cextools subscribe user-stream -x binance -c account,order
cextools subscribe user-stream -x okx -c position,order
```

### 定时监控

```bash
# 定时查询余额
cextools account watch-balance -x binance -e perp -i 5

# 定时查询持仓
cextools account watch-positions -x okx -e perp -i 2

# 定时查询挂单
cextools account watch-orders -x binance -e perp -i 1
```

### 脚本集成

创建 Shell 脚本来自动化任务：

```bash
#!/bin/bash
# price_monitor.sh

# 设置 API 凭证
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# 监控 BTC 价格
while true; do
    echo "$(date): $(cextools market ticker BTC/USDT | grep 'Mid Price' | awk '{print $4}')"
    sleep 60
done
```

## 🛠️ 故障排查

### 常见问题

#### 1. Python 版本问题

```bash
# 检查 Python 版本
python3 --version

# 如果版本低于 3.11，使用 Homebrew 安装
brew install python@3.11

# 创建符号链接
brew link python@3.11
```

#### 2. 权限问题

```bash
# 如果遇到权限错误，使用 sudo
sudo chown -R $(whoami) /usr/local/bin

# 或者使用用户目录安装
uv pip install --user git+https://github.com/realm520/quant.git
```

#### 3. 网络连接问题

```bash
# 测试网络连接
ping api.binance.com
ping www.okx.com

# 如果在中国大陆，可能需要配置代理
export https_proxy=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
```

#### 4. API 认证失败

```bash
# 检查环境变量
echo $BINANCE_API_KEY
echo $BINANCE_API_SECRET

# 重新加载配置
source ~/.zshrc

# 测试连接
cextools account balance -x binance -e perp --debug
```

#### 5. 数据库连接问题

```bash
# 检查 PostgreSQL 状态
brew services list | grep postgresql

# 启动服务
brew services start postgresql@15

# 测试连接
psql -d trading -c "SELECT 1;"
```

### 调试模式

```bash
# 启用详细日志
cextools account balance -x binance -e perp --debug

# 查看日志文件
tail -f logs/tri-arb.log
```

## 🎯 最佳实践

### 1. 安全配置

```bash
# 创建专用的 API 密钥，只开启必要权限
# - ✅ 读取权限
# - ✅ 交易权限（如果需要下单）
# - ❌ 提币权限（不要开启）

# 设置 IP 白名单（如果可能）
# 定期轮换 API 密钥
```

### 2. 性能优化

```bash
# 使用虚拟环境
source .venv/bin/activate

# 定期更新依赖
uv pip install --upgrade -e ".[dev]"

# 清理缓存
uv cache clean
```

### 3. 监控和日志

```bash
# 后台运行监控脚本
nohup cextools account watch-balance -x binance -e perp -i 5 > balance.log 2>&1 &

# 查看进程
ps aux | grep cextools

# 停止进程
pkill -f "watch-balance"
```

### 4. 自动化部署

创建启动脚本：

```bash
#!/bin/bash
# start_monitoring.sh

# 激活虚拟环境
source /path/to/quant/.venv/bin/activate

# 启动多个监控任务
nohup cextools account watch-balance -x binance -e perp -i 5 > binance_balance.log 2>&1 &
nohup cextools account watch-balance -x okx -e perp -i 5 > okx_balance.log 2>&1 &
nohup cextools subscribe user-stream -x binance > binance_ws.log 2>&1 &

echo "监控任务已启动"
```

### 5. 数据备份

```bash
# 备份配置文件
cp ~/.zshrc ~/.zshrc.backup

# 备份数据库（如果使用）
pg_dump trading > backup_$(date +%Y%m%d).sql
```

## 📚 参考资源

### 官方文档
- [项目仓库](https://github.com/realm520/quant)
- [Binance API 文档](https://developers.binance.com/docs)
- [OKX API 文档](https://www.okx.com/docs-v5/zh/)
- [XT API 文档](https://doc.xt.com)

### 项目文档
- [CEXTools 使用指南](cextools-usage.md)
- [CEXTools 完整指南](CEXTOOLS_COMPLETE_GUIDE.md)
- [快速参考](QUICK_REFERENCE.md)
- [功能总览](FEATURES.md)

### macOS 相关
- [Homebrew 官网](https://brew.sh/)
- [UV 文档](https://docs.astral.sh/uv/)
- [Python 官方文档](https://docs.python.org/3/)

## 🆘 获取帮助

如果遇到问题，可以：

1. **查看日志**: `tail -f logs/tri-arb.log`
2. **启用调试**: 在命令后添加 `--debug`
3. **检查配置**: 确认环境变量和 API 凭证
4. **查看文档**: 参考项目中的其他文档
5. **提交 Issue**: 在 GitHub 上报告问题

---

**CEXTools** - 专业的多交易所量化交易工具  
**版本**: 2.0  
**支持平台**: macOS 10.15+  
**支持交易所**: XT, Binance, OKX, Gate.io  
**功能**: REST API, WebSocket订阅, 定时查询, 数据库存储

> ⚠️ **风险提示**: 本工具仅供学习和研究使用。进行实盘交易前请充分测试，并注意风险控制。数字货币交易存在高风险，可能导致资金损失。
