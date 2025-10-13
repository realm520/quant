# CEXTools Quick Start Guide

**Feature**: XT 交易所统一 CLI 工具 | **Version**: 1.0.0

## 简介

CEXTools 是统一的命令行工具，用于管理 XT 交易所的现货（spot）和永续合约（perp）账户。通过 `--exchange-type` 参数可以在两种交易类型之间无缝切换。

---

## 安装

### 前置条件
- Python 3.11+
- XT 交易所账户和 API 凭证

### 安装依赖
```bash
# 使用 uv 安装（推荐）
uv pip install typer rich

# 或使用 pip
pip install typer rich
```

### 验证安装
```bash
cextools --help
```

---

## 配置

### 环境变量

CEXTools 需要配置 API 凭证才能访问 XT 交易所。根据您使用的交易类型，配置相应的环境变量：

#### 现货交易（Spot）
```bash
export XT_API_KEY="your_spot_api_key"
export XT_API_SECRET="your_spot_api_secret"
```

#### 永续合约（Perpetual Futures）
```bash
export XT_PERP_API_KEY="your_perp_api_key"
export XT_PERP_API_SECRET="your_perp_api_secret"
```

#### 同时使用两种类型
```bash
# 现货
export XT_API_KEY="your_spot_api_key"
export XT_API_SECRET="your_spot_api_secret"

# 永续
export XT_PERP_API_KEY="your_perp_api_key"
export XT_PERP_API_SECRET="your_perp_api_secret"
```

### 临时覆盖凭证

如果不想使用环境变量，可以通过命令行参数临时指定：

```bash
cextools account balance \
  --exchange-type spot \
  --api-key "your_key" \
  --api-secret "your_secret"
```

---

## 基础使用

### 1. 账户管理

#### 查询现货账户余额
```bash
cextools account balance --exchange-type spot
```

**输出示例**:
```
┏━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Currency ┃    Available ┃       Frozen ┃        Total ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ USDT     │ 1000.00000000│    0.00000000│ 1000.00000000│
│ BTC      │    0.05000000│    0.00000000│    0.05000000│
└──────────┴──────────────┴──────────────┴──────────────┘
Data fetched at: 2025-10-12 14:30:00 UTC
```

#### 查询永续合约账户余额
```bash
cextools account balance --exchange-type perp
```

#### 查询永续合约持仓
```bash
# 所有持仓
cextools account positions --exchange-type perp

# 筛选特定交易对
cextools account positions --exchange-type perp --symbol BTC/USDT
```

**输出示例**:
```
┏━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Symbol    ┃ Side   ┃ Quantity ┃ Entry Price┃ Current Price┃ PnL      ┃ ROE     ┃Leverage┃
┡━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ BTC/USDT  │ LONG   │     0.10 │  50000.00  │   51000.00   │ +100.00  │ +20.00% │  10x   │
└───────────┴────────┴──────────┴────────────┴──────────────┴──────────┴─────────┴────────┘
```

### 2. 市场行情

#### 查询价格（默认现货）
```bash
# 单个交易对（现货）
cextools market ticker --symbol BTC/USDT

# 单个交易对（永续）
cextools market ticker --exchange-type perp --symbol BTC/USDT

# 所有活跃交易对
cextools market ticker --exchange-type perp
```

#### 查询订单簿深度
```bash
# 默认 10 档
cextools market depth --exchange-type perp --symbol BTC/USDT

# 自定义档数（5-50）
cextools market depth --exchange-type perp --symbol BTC/USDT --limit 20
```

#### 查询资金费率（仅永续）
```bash
cextools market funding --exchange-type perp --symbol BTC/USDT
```

**输出示例**:
```
Funding Rate: BTC/USDT
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Field            ┃ Value                        ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ Current Rate     │ 0.01% (0.0001)               │
│ Next Funding     │ 2025-10-12 16:00:00 UTC      │
│ Time Until       │ 1h 25m                       │
└──────────────────┴──────────────────────────────┘
```

#### 实时监控价格
```bash
# 每 5 秒刷新（默认）
cextools market watch --exchange-type perp --symbol BTC/USDT

# 自定义刷新间隔（1-60 秒）
cextools market watch --exchange-type perp --symbol BTC/USDT --interval 10

# 按 Ctrl+C 停止监控
```

### 3. 订单管理

#### 下市价单（现货）
```bash
cextools order place \
  --exchange-type spot \
  --symbol BTC/USDT \
  --side BUY \
  --quantity 0.01 \
  --order-type MARKET
```

#### 下限价单（永续合约）
```bash
# 开多仓
cextools order place \
  --exchange-type perp \
  --symbol BTC/USDT \
  --side BUY \
  --position-side LONG \
  --quantity 0.01 \
  --order-type LIMIT \
  --price 50000

# 平空仓
cextools order place \
  --exchange-type perp \
  --symbol BTC/USDT \
  --side BUY \
  --position-side SHORT \
  --quantity 0.01 \
  --order-type MARKET
```

**注意**: 永续合约下单必须指定 `--position-side` (LONG 或 SHORT)

#### 查询订单状态
```bash
cextools order status \
  --exchange-type perp \
  --order-id 12345
```

#### 取消订单
```bash
# 取消单个订单
cextools order cancel \
  --exchange-type perp \
  --order-id 12345

# 取消特定交易对的所有订单
cextools order cancel-all \
  --exchange-type perp \
  --symbol BTC/USDT

# 取消所有订单（需要确认）
cextools order cancel-all --exchange-type perp

# 跳过确认（脚本使用）
cextools order cancel-all --exchange-type perp --yes
```

### 4. 杠杆管理（仅永续）

#### 设置杠杆倍数
```bash
cextools leverage set \
  --exchange-type perp \
  --symbol BTC/USDT \
  --leverage 10
```

**杠杆范围**: 1-125x（具体范围取决于交易对和持仓规模）

#### 查询当前杠杆
```bash
cextools leverage info \
  --exchange-type perp \
  --symbol BTC/USDT
```

---

## 高级功能

### 输出格式

CEXTools 支持三种输出格式：table（默认）、json、csv

#### JSON 输出（便于脚本解析）
```bash
cextools account balance --exchange-type spot --output json
```

**输出**:
```json
[
  {
    "currency": "USDT",
    "available": "1000.00000000",
    "frozen": "0.00000000",
    "total": "1000.00000000"
  }
]
```

#### CSV 输出（便于导入表格）
```bash
cextools account balance --exchange-type spot --output csv
```

**输出**:
```csv
currency,available,frozen,total
USDT,1000.00000000,0.00000000,1000.00000000
BTC,0.05000000,0.00000000,0.05000000
```

### 调试模式

启用 `--debug` 参数查看详细日志和 API 请求细节：

```bash
cextools account balance --exchange-type spot --debug
```

**输出示例**:
```
[DEBUG] Exchange factory: Creating XTSpotExchange
[DEBUG] API Request: GET /spot/v1/account/balance
[DEBUG] Request headers: {validate-appkey: XT123..., validate-timestamp: 1728745800000}
[DEBUG] Response: 200 OK
[DEBUG] Response body: {"code": 0, "data": {"USDT": {"available": "1000.00", ...}}}

┏━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Currency ┃    Available ┃       Frozen ┃        Total ┃
...
```

---

## 常见问题

### 1. 提示 API 凭证未配置

**问题**:
```
Error: 现货交易需要配置 XT_API_KEY 和 XT_API_SECRET 环境变量
或使用 --api-key 和 --api-secret 参数
```

**解决方案**:
- 检查环境变量是否正确设置：`echo $XT_API_KEY`
- 确认变量名是否正确（spot 使用 `XT_API_KEY`，perp 使用 `XT_PERP_API_KEY`）
- 重新导出环境变量或使用 `--api-key` 参数

### 2. leverage 命令报错（现货不支持杠杆）

**问题**:
```
Error: leverage 命令仅适用于永续合约（perp），现货交易不支持杠杆
```

**解决方案**:
- 确认使用 `--exchange-type perp` 而不是 `spot`
- leverage 命令仅适用于永续合约

### 3. 永续合约下单缺少 position-side

**问题**:
```
Error: 永续合约下单需要指定 --position-side (LONG 或 SHORT)
```

**解决方案**:
- 添加 `--position-side LONG`（开多或平空）
- 或 `--position-side SHORT`（开空或平多）

### 4. 交易对格式错误

**问题**:
```
Error: 交易对不存在或未上线永续合约
```

**解决方案**:
- 确认交易对格式为 `BASE/QUOTE`（如 `BTC/USDT`，不是 `BTCUSDT` 或 `BTC-USDT`）
- 检查交易对是否在 XT 交易所上线
- 使用 `cextools market ticker --exchange-type perp` 查看所有可用交易对

### 5. 网络请求超时

**问题**:
```
Error: 网络请求超时，请检查网络连接
```

**解决方案**:
- 检查网络连接
- 确认 XT API 服务正常（访问 XT 官网）
- 使用 `--debug` 参数查看详细错误信息

---

## 脚本化使用

### 示例 1: 监控账户余额
```bash
#!/bin/bash
# monitor_balance.sh

while true; do
  echo "=== $(date) ==="
  cextools account balance --exchange-type perp --output json | jq '.[] | select(.currency == "USDT")'
  sleep 60
done
```

### 示例 2: 批量查询多个交易对价格
```bash
#!/bin/bash
# check_prices.sh

SYMBOLS=("BTC/USDT" "ETH/USDT" "SOL/USDT")

for symbol in "${SYMBOLS[@]}"; do
  echo "Price for $symbol:"
  cextools market ticker --exchange-type perp --symbol "$symbol" --output json | jq '.[0].last_price'
done
```

### 示例 3: 自动设置杠杆
```bash
#!/bin/bash
# set_leverage_all.sh

SYMBOLS=("BTC/USDT" "ETH/USDT")
LEVERAGE=10

for symbol in "${SYMBOLS[@]}"; do
  echo "Setting leverage for $symbol to ${LEVERAGE}x..."
  cextools leverage set --exchange-type perp --symbol "$symbol" --leverage $LEVERAGE
done
```

---

## 下一步

1. **阅读完整文档**: 查看 [spec.md](./spec.md) 了解所有功能需求
2. **查看实现计划**: 阅读 [plan.md](./plan.md) 了解技术架构
3. **运行测试**: 查看 [contracts/](./contracts/) 目录的契约测试

---

**Questions?** 查看 [spec.md](./spec.md) 的 Edge Cases 部分或启用 `--debug` 模式获取详细错误信息。
