# CEX Tools 使用指南

## 安装方式

### 方式 1: 本地开发安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/realm520/quant.git
cd quant

# 使用 UV 安装
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e .

# 运行 cextools
cextools --help
```

### 方式 2: 从 GitHub 直接安装

```bash
# 使用 UV
uv pip install git+https://github.com/realm520/quant.git

# 运行 cextools
cextools --help
```

### 方式 3: uvx 临时运行（需要本地构建）

```bash
# 先克隆并构建
git clone https://github.com/realm520/quant.git
cd quant
uv build

# 使用 uvx 运行
uvx --from . cextools --help
```

## 命令示例

### 查看帮助
```bash
cextools --help
cextools market --help
```

### 获取实时价格
```bash
# 默认使用 XT 交易所
cextools market ticker BTC/USDT
cextools market ticker ETH/USDT

# 指定交易所
cextools --exchange xt market ticker BTC/USDT
```

### 获取订单簿深度
```bash
# 默认 20 档深度
cextools market orderbook BTC/USDT

# 指定深度
cextools market orderbook BTC/USDT --depth 50
```

### 启用详细日志
```bash
cextools --verbose market ticker BTC/USDT
```

## 环境变量配置

### XT 交易所（公开 API 无需配置）

公开 API（市场数据）无需配置凭证：
- `market ticker`
- `market orderbook`

私有 API（交易、账户）需要配置：
```bash
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
```

### 其他交易所（未来支持）

```bash
# Binance
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# OKX
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_api_secret"
```

## 功能特性

### 当前支持
- ✅ XT Exchange 市场数据查询
- ✅ 实时价格（ticker）
- ✅ 订单簿深度（orderbook）
- ✅ Rich 终端彩色输出
- ✅ 自动加载环境变量凭证

### 规划中
- ⏳ Binance Exchange 支持
- ⏳ OKX Exchange 支持
- ⏳ 账户查询命令
- ⏳ 交易命令

## 故障排查

### 命令找不到

**错误**: `cextools: command not found`

**解决**:
```bash
# 确认安装成功
pip list | grep tri-arb

# 检查虚拟环境
which python
which cextools

# 重新安装
uv pip install -e .
```

### API 错误

**错误**: `HTTP 404 Not Found`

**原因**: XT API 端点可能变更

**解决**: 检查 [XT API 文档](https://doc.xt.com)

### 符号格式错误

**错误**: `Trading pair not found: btc_usdt`

**解决**: 使用正确的格式 `BTC/USDT`（大写，斜杠分隔）

```bash
# ✅ 正确
cextools market ticker BTC/USDT

# ❌ 错误
cextools market ticker btc_usdt
cextools market ticker BTCUSDT
```

## 与 tri-arb 的关系

- **tri-arb**: 三角套利监控和自动执行系统
- **cextools**: 通用交易所 API 查询工具

两者**共用同一套交易所接口**，但服务不同用途：
- tri-arb 用于套利策略
- cextools 用于快速查询和调试

可以同时安装使用：
```bash
# 套利监控
tri-arb monitor

# 快速查价格
cextools market ticker BTC/USDT
```
