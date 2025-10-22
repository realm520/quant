# Gate.io 定时查询功能

本文档介绍如何使用 Gate.io 的定时查询功能，包括余额、持仓和订单的定时监控。

## 功能概述

新增了三个定时查询命令，支持所有交易所（XT、Binance、OKX、Gate.io）：

- `watch-balance`: 定时查询账户余额
- `watch-positions`: 定时查询持仓
- `watch-orders`: 定时查询挂单

## 命令使用

### 1. 定时查询余额

```bash
# 每1分钟查询一次Gate.io永续合约余额
python -m tri_arb.cli.main account watch-balance -x gate -e perp

# 每5分钟查询一次Gate.io现货余额
python -m tri_arb.cli.main account watch-balance -x gate -e spot --interval 5

# JSON格式输出
python -m tri_arb.cli.main account watch-balance -x gate -e perp --output json
```

### 2. 定时查询持仓

```bash
# 每1分钟查询一次Gate.io所有持仓
python -m tri_arb.cli.main account watch-positions -x gate -e perp

# 每2分钟查询Gate.io的ETH持仓
python -m tri_arb.cli.main account watch-positions -x gate -e perp -s ETH/USDT --interval 2

# JSON格式输出
python -m tri_arb.cli.main account watch-positions -x gate -e perp --output json
```

### 3. 定时查询挂单

```bash
# 每1分钟查询一次Gate.io所有挂单
python -m tri_arb.cli.main account watch-orders -x gate -e perp

# 每3分钟查询Gate.io的BTC挂单
python -m tri_arb.cli.main account watch-orders -x gate -e perp -s BTC/USDT --interval 3

# JSON格式输出
python -m tri_arb.cli.main account watch-orders -x gate -e perp --output json
```

## 参数说明

### 通用参数

- `-x, --exchange`: 交易所选择 (xt, binance, okx, gate)
- `-e, --exchange-type`: 交易类型 (spot, perp)
- `-i, --interval`: 查询间隔（分钟），默认1分钟
- `-s, --symbol`: 交易对筛选（可选）
- `-o, --output`: 输出格式 (table, json)
- `--api-key`: API密钥（覆盖环境变量）
- `--api-secret`: API密钥（覆盖环境变量）
- `--debug`: 启用调试模式

### 持仓查询特有功能

- 支持多交易所格式识别（Gate.io、OKX、Binance、XT）
- 自动统计多头/空头持仓数量
- 显示持仓变化趋势

### 订单查询特有功能

- 支持多交易所格式识别
- 自动统计买单/卖单数量
- 显示订单状态变化

## 使用示例

### 监控Gate.io永续合约账户

```bash
# 设置环境变量
export GATE_API_KEY="your_api_key"
export GATE_API_SECRET="your_api_secret"

# 每2分钟查询一次余额
python -m tri_arb.cli.main account watch-balance -x gate -e perp --interval 2

# 每1分钟查询一次持仓
python -m tri_arb.cli.main account watch-positions -x gate -e perp

# 每1分钟查询一次挂单
python -m tri_arb.cli.main account watch-orders -x gate -e perp
```

### 监控特定交易对

```bash
# 只监控ETH/USDT的持仓
python -m tri_arb.cli.main account watch-positions -x gate -e perp -s ETH/USDT

# 只监控BTC/USDT的挂单
python -m tri_arb.cli.main account watch-orders -x gate -e perp -s BTC/USDT
```

## 输出格式

### 表格格式（默认）

- 实时更新的表格显示
- 彩色标识（盈利/亏损）
- 统计信息（持仓数量、订单数量等）

### JSON格式

```bash
python -m tri_arb.cli.main account watch-positions -x gate -e perp --output json
```

## 停止监控

按 `Ctrl+C` 停止所有定时查询。

## 注意事项

1. **API限制**: 注意交易所的API调用频率限制
2. **网络连接**: 确保网络连接稳定
3. **API权限**: 确保API密钥有相应的查询权限
4. **数据准确性**: 定时查询基于REST API，数据可能有延迟

## 故障排除

### 常见错误

1. **API认证失败**: 检查API密钥和密钥是否正确
2. **网络超时**: 检查网络连接
3. **权限不足**: 确保API密钥有查询权限

### 调试模式

使用 `--debug` 参数获取详细错误信息：

```bash
python -m tri_arb.cli.main account watch-balance -x gate -e perp --debug
```

## 与其他功能集成

定时查询功能可以与WebSocket订阅功能结合使用：

- **REST API定时查询**: 用于定期获取账户快照
- **WebSocket实时推送**: 用于实时监控变化

这样可以实现更全面的账户监控方案。
