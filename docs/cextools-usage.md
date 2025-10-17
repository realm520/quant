# CEX Tools 使用指南

CEX Tools 是一个统一的 XT 交易所 CLI 工具，支持现货和永续合约交易，提供市场行情、账户管理、订单管理和杠杆设置等功能。

## 安装方式

### 方式 1: 本地开发安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/realm520/quant.git
cd quant

# 使用 UV 安装
uv venv --python 3.11
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"              

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

## 核心功能特性

### 支持的交易所
- **xt** - XT 交易所（默认，完整实现）
  - 现货交易 (spot) - ✅ 完整实现
  - 永续合约交易 (perp) - ✅ 完整实现
- **binance** - 币安交易所（部分实现）
  - 现货交易 (spot) - ✅ 余额/行情已实现，订单功能待实现
  - 永续合约 (perp) - ✅ 余额/行情/持仓/挂单已实现，下单功能待实现
- **okx** - OKX交易所（部分实现）
  - 永续合约 (perp) - ✅ 余额/持仓/挂单已实现，下单功能待实现
  - 现货交易 (spot) - ⏳ 待实现

### 支持的交易类型
- **spot** - 现货交易
- **perp** - 永续合约交易

### 主要命令组
- **account** - 账户管理（余额查询、持仓查看）
- **market** - 市场行情（实时价格、订单簿、K线数据）
- **order** - 订单管理（下单、撤单、订单查询）
- **leverage** - 杠杆管理（仅永续合约）

### 输出格式支持
- **table** - 格式化表格显示（默认）
- **json** - JSON 格式输出
- **csv** - CSV 格式输出

## 基础命令

### 查看帮助和版本
```bash
# 查看主帮助
cextools --help

# 查看版本信息
cextools version

# 查看子命令帮助
cextools market --help
cextools account --help
cextools order --help
cextools leverage --help
```

## 市场行情命令 (market)

### 实时价格查询
```bash
# 查询 XT 交易所所有永续合约价格（默认）
cextools market ticker

# 查询 XT 交易所特定永续合约价格
cextools market ticker --symbol BTC/USDT

# 查询现货价格需要显式指定
cextools market ticker --exchange-type spot --symbol BTC/USDT

# 查询币安交易所永续合约价格（占位符）
cextools market ticker --exchange binance --symbol BTC/USDT
cextools market ticker -x binance -s ETH/USDT

# 查询币安现货价格（占位符）
cextools market ticker -x binance -e spot -s ETH/USDT

# 查询 XT 现货价格
cextools market ticker --exchange-type spot --symbol ETH/USDT

# JSON 格式输出（默认合约）
cextools market ticker -s BTC/USDT --output json
```

### 订单簿深度
```bash
# 永续合约订单簿（默认）
cextools market depth --symbol BTC/USDT

# 指定深度
cextools market depth -s ETH/USDT --limit 50

# 现货订单簿
cextools market depth --exchange-type spot --symbol BTC/USDT

# CSV 格式输出
cextools market depth -s BTC/USDT --output csv
```

### K线数据
```bash
# 获取 1 小时 K线数据
cextools market klines -e spot -s BTC/USDT --interval 1h

# 获取指定数量的 K线数据
cextools market klines -e spot -s BTC/USDT --interval 1d --limit 30

# JSON 格式输出K线数据
cextools market klines -e spot -s BTC/USDT --interval 4h -o json
```

### 实时行情监控
```bash
# 实时监控单个永续合约价格（默认）
cextools market watch --symbol BTC/USDT

# 监控现货价格
cextools market watch --symbol ETH/USDT --exchange-type spot --interval 5
```

## 账户管理命令 (account)

### 余额查询
```bash
# 查询 XT 现货账户余额
cextools account balance --exchange-type spot

# 查询币安现货账户余额（占位符）
cextools account balance --exchange binance --exchange-type spot
cextools account balance -x binance -e spot

# 查询 XT 永续合约账户余额
cextools account balance --exchange-type perp

# 查询币安永续合约账户余额（占位符）
cextools account balance -x binance -e perp

# JSON 格式输出余额
cextools account balance -e spot --output json
```

### 定时查询余额（新功能！）

```bash
# 每1分钟查询一次余额（默认）
cextools account watch-balance -e perp

# 每5分钟查询一次Binance余额
cextools account watch-balance -x binance -e perp --interval 5

# 每10分钟查询一次OKX余额
cextools account watch-balance -x okx -e perp -i 10

# JSON格式输出（便于记录）
cextools account watch-balance -x okx -e perp -i 5 -o json

# 按 Ctrl+C 停止监控
```

### 持仓查询（永续合约）
```bash
# 查询所有永续合约持仓（XT交易所）
cextools account positions --exchange-type perp

# 查询特定合约持仓
cextools account positions -e perp --symbol BTC/USDT

# CSV 格式输出持仓信息
cextools account positions -e perp --output csv

# 查询币安合约的所有持仓
cextools account positions -e perp --exchange binance

# 查询币安合约的特定持仓
cextools account positions -e perp -x binance --symbol BTC/USDT

# JSON 格式输出币安持仓（包含完整的API返回数据）
cextools account positions -e perp -x binance -o json
```

### 挂单查询（永续合约）
```bash
# 查询所有挂单（XT交易所）
cextools account orders --exchange-type perp

# 查询特定合约的挂单
cextools account orders -e perp --symbol BTC/USDT

# CSV 格式输出挂单信息
cextools account orders -e perp --output csv

# 查询币安合约的所有挂单
cextools account orders -e perp --exchange binance

# 查询币安合约的特定挂单
cextools account orders -e perp -x binance --symbol BTC/USDT

# JSON 格式输出币安挂单（包含完整的API返回数据）
cextools account orders -e perp -x binance -o json
```

### 定时查询挂单（新功能！）

```bash
# 每1分钟查询一次所有挂单
cextools account watch-orders -e perp

# 每2分钟查询Binance的BTC挂单
cextools account watch-orders -x binance -e perp -s BTC/USDT --interval 2

# 每5分钟查询OKX的所有挂单
cextools account watch-orders -x okx -e perp -i 5

# JSON格式输出（便于记录）
cextools account watch-orders -x okx -e perp -i 3 -o json

# 按 Ctrl+C 停止监控
```

### 交易历史
```bash
# 查询交易历史（最近50条）
cextools account history --exchange-type spot --symbol BTC/USDT

# 查询指定数量的交易历史
cextools account history -e spot -s BTC/USDT --limit 100
```

## 订单管理命令 (order)

### 下单操作
```bash
# 现货限价买单
cextools order place -e spot -s BTC/USDT --side buy --quantity 0.001 --price 50000

# 现货市价卖单
cextools order place -e spot -s BTC/USDT --side sell --quantity 0.001 --type market

# 永续合约限价开多仓
cextools order place -e perp -s BTC/USDT --side buy -q 0.01 -p 50000 --position-side long

# 永续合约限价开空仓
cextools order place -e perp -s ETH/USDT --side sell -q 0.1 -p 3000 --position-side short
```

### 订单查询
```bash
# 查询当前挂单
cextools order list --exchange-type spot

# 查询特定交易对的挂单
cextools order list -e spot --symbol BTC/USDT

# 查询订单详情
cextools order get --exchange-type spot --order-id 12345

# 查询历史订单
cextools order history -e spot -s BTC/USDT --limit 50
```

### 撤单操作
```bash
# 撤销单个订单
cextools order cancel --exchange-type spot --order-id 12345

# 撤销特定交易对的所有订单
cextools order cancel-all -e spot --symbol BTC/USDT

# 撤销所有挂单
cextools order cancel-all -e spot
```

## 杠杆管理命令 (leverage)

> 注意：杠杆管理仅适用于永续合约 (`--exchange-type perp`)

### 设置杠杆
```bash
# 设置 BTC/USDT 永续合约杠杆为 10 倍
cextools leverage set --symbol BTC/USDT --leverage 10 --exchange-type perp

# 设置多个合约的杠杆
cextools leverage set -s ETH/USDT -l 20 -e perp
```

### 查询杠杆设置
```bash
# 查询所有合约的杠杆设置
cextools leverage list --exchange-type perp

# 查询特定合约的杠杆设置
cextools leverage get -s BTC/USDT -e perp
```

## 多交易所支持

### 使用 --exchange 参数

所有命令都支持 `--exchange` (或 `-x`) 参数来指定交易所：

```bash
# 默认使用 XT 交易所
cextools market ticker -e spot -s BTC/USDT

# 使用币安交易所（占位符）
cextools market ticker -x binance -e spot -s BTC/USDT

# 查询不同交易所的余额
cextools account balance -x xt -e spot
cextools account balance -x binance -e spot
```

### 支持的交易所列表

| 交易所 | 标识符 | 现货 | 永续合约 | 状态 |
|--------|--------|------|----------|------|
| XT | `xt` | ✅ | ✅ | 完整实现 |
| Binance | `binance` | ⚡ | ⚡ | 部分实现 |
| OKX | `okx` | ⏳ | ⚡ | 部分实现 |

**说明**：
- ✅ **完整实现**：所有功能可正常使用，连接真实 API
- ⚡ **部分实现**：余额/持仓/挂单已实现，订单功能待完善
- ⏳ **待实现**：功能尚未实现

### 币安交易所说明

币安交易所**已实现真实API调用**，可以查询实时数据：

**已实现功能** ✅：
- 账户余额查询（现货和永续合约）
- 实时价格查询
- 订单簿深度查询
- 持仓查询（永续合约）- 支持查询所有持仓和特定合约持仓
- 挂单查询（永续合约）- 支持查询所有挂单和特定合约挂单
- 下单功能（永续合约）- 支持限价单、市价单等多种订单类型
- HMAC-SHA256 签名认证

**待实现功能** 🔄：
- 撤单功能
- 历史订单查询
- 交易历史查询
- WebSocket 实时订阅

**使用示例**：
```bash
# 查询币安现货余额（真实API）
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
cextools account balance -x binance -e spot

# 查询币安永续合约余额（真实API）
cextools account balance -x binance -e perp

# 查询币安永续合约持仓（真实API）
cextools account positions -x binance -e perp

# 查询特定合约持仓
cextools account positions -x binance -e perp --symbol BTC/USDT

# 查询币安永续合约挂单（真实API）
cextools account orders -x binance -e perp

# 查询特定合约挂单
cextools account orders -x binance -e perp --symbol BTC/USDT

# 下单（永续合约限价单）
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

# 下单（永续合约市价单，⚠️会立即成交）
cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 --type market --position-side LONG

# 查询实时价格（公开API，无需密钥）
cextools market ticker -x binance -s BTC/USDT
```

### OKX交易所说明

OKX交易所**已实现真实API调用**，可以查询实时数据：

**已实现功能** ✅：
- 账户余额查询（永续合约）
- 持仓查询（永续合约）- 支持查询所有持仓和特定合约持仓
- 挂单查询（永续合约）- 支持查询所有挂单和特定合约挂单
- 下单功能（永续合约）- 支持限价单、市价单、Post-only等订单类型
- HMAC-SHA256 签名认证

**待实现功能** 🔄：
- 现货交易功能
- 撤单功能
- 行情查询
- WebSocket 实时订阅

**使用示例**：
```bash
# 配置OKX API凭证（注意：OKX需要3个参数）
export OKX_API_KEY="your_okx_api_key"
export OKX_API_SECRET="your_okx_api_secret"
export OKX_PASSPHRASE="your_okx_passphrase"

# 查询OKX永续合约余额
cextools account balance -x okx -e perp

# 查询OKX永续合约持仓
cextools account positions -x okx -e perp

# 查询特定合约持仓（注意OKX格式：BTC-USDT-SWAP）
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP

# 查询OKX永续合约挂单
cextools account orders -x okx -e perp

# 下单（永续合约限价单）
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

# 下单（Post-only订单，只做Maker）
cextools order place -x okx -e perp -s ETH/USDT --side buy -q 0.01 -p 2000 --type post_only --position-side LONG

# JSON格式输出
cextools account positions -x okx -e perp -o json
```

**注意事项**：
- OKX 需要3个API凭证：API Key、Secret Key 和 Passphrase
- OKX 产品ID格式为：`BTC-USDT-SWAP`（币安格式是 `BTCUSDT`）
- OKX 持仓方向为：`long`/`short`/`net`（币安格式是 `LONG`/`SHORT`/`BOTH`）
- CLI命令会自动转换symbol格式（`BTC/USDT` → `BTC-USDT-SWAP`）

## 环境变量配置

### XT 交易所 API 凭证

对于公开 API（市场数据），无需配置凭证：
- `market ticker`
- `market orderbook` 
- `market klines`

对于私有 API（账户、交易、杠杆），需要配置：
```bash
# XT 现货和永续合约共用同一个 API key
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
```

**说明**：同一个 API key 可以同时用于现货和永续合约交易。

### 币安交易所 API 凭证

币安现货和永续合约共用同一个 API key：

```bash
# 币安现货和永续合约共用
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
```

**说明**：
- 同一个 API key 可以同时用于币安的现货和永续合约交易
- 币安交易所已实现真实API调用

### OKX交易所 API 凭证

OKX现货和永续合约共用同一个 API key，但需要额外的 passphrase：

```bash
# OKX 现货和永续合约共用（注意：需要3个参数）
export OKX_API_KEY="your_okx_api_key"
export OKX_API_SECRET="your_okx_api_secret"
export OKX_PASSPHRASE="your_okx_passphrase"
```

**说明**：
- OKX API 需要3个凭证：API Key、Secret Key 和 Passphrase
- Passphrase 是创建 API 时自己设置的密码
- 同一个 API key 可以同时用于 OKX 的现货和永续合约交易

### API 凭证获取

1. 登录 [XT 交易所](https://www.xt.com)
2. 进入 API 管理页面
3. 创建新的 API Key
4. 设置适当的权限：
   - **现货交易**：需要 "Spot Trading" 权限
   - **永续合约**：需要 "Futures Trading" 权限
   - **账户查询**：需要 "Read" 权限

### 环境变量设置
```bash
# Linux/macOS
export XT_API_KEY="your_api_key_here"
export XT_API_SECRET="your_api_secret_here"

# Windows PowerShell
$env:XT_API_KEY="your_api_key_here"
$env:XT_API_SECRET="your_api_secret_here"

# Windows CMD
set XT_API_KEY=your_api_key_here
set XT_API_SECRET=your_api_secret_here
```

## 高级使用

### 批量操作
```bash
# 批量查询多个交易对价格
cextools market ticker -e spot -s "BTC/USDT,ETH/USDT,BNB/USDT" -o json

# 批量撤销订单
cextools order cancel-all -e spot --symbol BTC/USDT
```

### 自定义输出格式
```bash
# 表格格式（默认，美观显示）
cextools account balance -e spot

# JSON 格式（便于脚本处理）
cextools account balance -e spot -o json | jq '.USDT.available'

# CSV 格式（便于导入 Excel）
cextools account balance -e spot -o csv > balance.csv
```

### 调试和错误诊断
```bash
# 启用调试模式查看详细错误信息
cextools account balance -e spot --debug

# 查看 API 调用日志
cextools market ticker -e spot -s BTC/USDT --debug
```

## 功能特性

### 当前支持 ✅
- **多交易所支持**：XT (完整)、Binance (占位符)
  - 统一的命令接口跨所有交易所
  - 使用 `--exchange` 参数轻松切换
  - 工厂模式支持动态注册新交易所
- **多交易类型**：现货 (spot) 和永续合约 (perp)
- **完整市场数据**：实时价格、订单簿、K线数据、实时监控
- **账户管理**：余额查询、持仓查看、交易历史
- **订单管理**：下单、撤单、订单查询、历史订单
- **杠杆管理**：永续合约杠杆设置和查询
- **多种输出格式**：Table、JSON、CSV
- **Rich 终端**：彩色输出和格式化表格
- **自动凭证加载**：从环境变量自动加载 API 凭证
- **错误处理**：详细的错误信息和调试支持
- **参数验证**：交易对格式、限制参数等验证

### 架构特点 🏗️
- **异步架构**：基于 asyncio 的高性能 I/O
- **类型安全**：100% 类型注解，mypy 严格模式
- **模块化设计**：清晰的命令组织和代码结构
- **工厂模式**：可扩展的交易所适配器架构
- **统一接口**：BaseExchange 抽象层统一所有交易所
- **可扩展性**：轻松添加新交易所支持
- **生产就绪**：完整的日志记录和错误处理

## 故障排查

### 安装和环境问题

#### 命令找不到
**错误**: `cextools: command not found`

**解决方案**:
```bash
# 1. 确认安装成功
pip list | grep tri-arb

# 2. 检查虚拟环境是否激活
which python
which cextools

# 3. 重新安装
uv pip install -e ".[dev]"

# 4. 确认 Python 版本（需要 3.11+）
python --version
```

#### 依赖冲突
**错误**: 包依赖冲突或版本不兼容

**解决方案**:
```bash
# 清理并重新创建虚拟环境
rm -rf .venv
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### API 相关错误

#### 认证失败
**错误**: `401 Unauthorized` 或 `403 Forbidden`

**原因和解决**:
```bash
# 1. 检查环境变量是否正确设置
echo $XT_API_KEY
echo $XT_API_SECRET

# 2. 确认 API Key 权限设置正确
# 3. 检查 API Key 是否已激活
# 4. 确认没有IP白名单限制
```

#### API 端点错误
**错误**: `HTTP 404 Not Found` 或连接超时

**解决方案**:
```bash
# 1. 检查网络连接
ping api.xt.com

# 2. 启用调试模式查看详细信息
cextools market ticker -e spot -s BTC/USDT --debug

# 3. 参考最新 API 文档
# https://doc.xt.com
```

### 参数和格式错误

#### 交易对格式错误
**错误**: `Trading pair not found` 或 `Invalid symbol format`

**解决方案**:
```bash
# ✅ 正确格式
cextools market ticker -e spot -s BTC/USDT
cextools market ticker -e spot -s ETH/USDT

# ❌ 错误格式
# cextools market ticker -e spot -s btc_usdt     # 小写+下划线
# cextools market ticker -e spot -s BTCUSDT      # 无分隔符
# cextools market ticker -e spot -s BTC-USDT     # 错误分隔符
```

#### 参数范围错误
**错误**: 数量、价格或深度参数超出允许范围

**解决方案**:
```bash
# 检查参数限制
cextools market orderbook --help

# 常见限制
# - depth: 1-100
# - limit: 1-1000  
# - quantity: 根据交易对最小交易量
```

### 性能和连接问题

#### 请求频率限制
**错误**: `429 Too Many Requests`

**解决方案**:
```bash
# 1. 减少请求频率
# 2. 添加请求间隔
# 3. 查看 API 文档的频率限制说明
```

#### 网络连接问题
**错误**: 连接超时或网络错误

**解决方案**:
```bash
# 1. 检查网络连接
curl -I https://sapi.xt.com

# 2. 检查防火墙设置
# 3. 尝试使用代理（如需要）
# 4. 启用调试模式查看详细网络日志
cextools account balance -e spot --debug
```

## 与 tri-arb 的关系

本项目包含两个主要的 CLI 工具，它们共享相同的底层交易所接口和架构：

### tri-arb - 三角套利系统 🔺
专门用于三角套利策略的监控和执行：

```bash
# 监控套利机会
tri-arb monitor

# 设置最小盈利阈值
tri-arb monitor --min-profit 0.5

# 实时监控模式
tri-arb monitor --mode realtime --refresh-interval 10

# 指定基础货币
tri-arb monitor --base-currencies USDT,BUSD
```

**主要功能**:
- 三角套利机会检测
- 实时盈利计算
- 自动交易执行（规划中）
- 风险管理和监控

### cextools - 通用交易工具 🛠️
通用的交易所 API 查询和管理工具：

```bash
# 市场数据查询
cextools market ticker -e spot -s BTC/USDT

# 账户管理
cextools account balance -e spot

# 订单操作
cextools order place -e spot -s BTC/USDT --side buy -q 0.001 -p 50000
```

**主要功能**:
- 市场数据查询（价格、订单簿、K线）
- 账户管理（余额、持仓、历史）
- 订单管理（下单、撤单、查询）
- 杠杆管理（永续合约）

### 共享特性 🤝

两个工具**共用同一套底层架构**：
- **统一交换所接口** (`BaseExchange`)
- **相同的数据模型** (`TradingPair`, `OrderBook`, `Ticker`)
- **一致的配置管理** (环境变量、设置)
- **相同的日志系统** (structlog)
- **共享的错误处理** 

### 使用场景对比

| 场景 | tri-arb | cextools |
|------|---------|----------|
| 快速查价格 | ❌ | ✅ |
| 账户余额查询 | ❌ | ✅ |
| 手动下单交易 | ❌ | ✅ |
| 套利机会监控 | ✅ | ❌ |
| 策略自动执行 | ✅ | ❌ |
| 数据分析调试 | ❌ | ✅ |
| 批量操作 | ❌ | ✅ |

### 协同使用示例

```bash
# 1. 使用 cextools 检查 XT 账户状态
cextools account balance -e spot -o json

# 2. 使用 cextools 检查币安账户状态（占位符）
cextools account balance -x binance -e spot -o json

# 3. 使用 cextools 查看市场深度
cextools market orderbook -e spot -s BTC/USDT --depth 50

# 4. 比较不同交易所的价格
cextools market ticker -x xt -e spot -s BTC/USDT -o json
cextools market ticker -x binance -e spot -s BTC/USDT -o json

# 5. 使用 tri-arb 监控套利机会
tri-arb monitor --min-profit 0.3

# 6. 使用 cextools 执行具体交易
cextools order place -e spot -s BTC/USDT --side buy -q 0.001 -p 50000
```

### 多交易所对比查询

利用 `--exchange` 参数可以轻松对比不同交易所的数据：

```bash
# 对比 XT 和币安的价格（币安为占位符数据）
echo "XT 交易所:"
cextools market ticker -x xt -e spot -s BTC/USDT

echo "\n币安交易所 (占位符):"
cextools market ticker -x binance -e spot -s BTC/USDT

# 使用 JSON 格式进行数据分析
cextools market ticker -x xt -e spot -s BTC/USDT -o json > xt_btc.json
cextools market ticker -x binance -e spot -s BTC/USDT -o json > binance_btc.json
```

### 开发和调试

在开发和调试过程中，两个工具可以互补使用：
- 使用 `cextools` 验证 API 连接和数据格式
- 使用 `tri-arb` 测试套利策略逻辑
- 两者都支持 `--debug` 模式查看详细日志

```bash
# 调试 API 连接
cextools market ticker -e spot -s BTC/USDT --debug

# 调试套利逻辑
tri-arb monitor --debug --min-profit 0.1
```

## 更多资源

- **项目仓库**: https://github.com/realm520/quant
- **XT API 文档**: https://doc.xt.com
- **问题反馈**: GitHub Issues
- **架构文档**: `docs/architecture.md`
- **开发指南**: `README.md`

---

**注意**: 本工具仅供学习和研究使用。进行实盘交易前请充分测试，并注意风险控制。
