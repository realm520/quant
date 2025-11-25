# 订单订阅与多空显示

## 功能概述

现在你可以订阅订单更新，并在控制台和 Grafana 中实时查看订单的多空方向。

## 使用方法

### 1. 订阅订单更新

#### XT 交易所
```bash
# 订阅单个账号的订单
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/trading
export PROM_METRICS_PORT=9600
source .venv/bin/activate

cextools subscribe user-stream -x xt \
  --channels order \
  --account-id account_002
```

#### Binance 交易所
```bash
cextools subscribe user-stream -x binance \
  --channels order
```

#### OKX 交易所
```bash
cextools subscribe user-stream -x okx \
  --channels order \
  --passphrase YOUR_PASSPHRASE
```

#### Gate.io 交易所
```bash
cextools subscribe user-stream -x gate \
  --channels order
```

### 2. 多账号订阅（XT）

```bash
cextools subscribe multi-account \
  --config config/accounts.json \
  --accounts account_002,account_003
```

## 订单显示格式

订单更新会在控制台以表格形式显示，包含以下信息：

- **订单ID**: 订单唯一标识
- **交易对**: 例如 BTC/USDT
- **方向**: BUY（买入，绿色）或 SELL（卖出，红色）
- **多空**: LONG（多，亮绿色）或 SHORT（空，亮红色）
- **类型**: 订单类型（LIMIT, MARKET 等）
- **数量**: 订单数量
- **价格**: 订单价格
- **状态**: 订单状态（NEW, FILLED, CANCELED 等）

### 示例输出

```
XT订单更新
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ 订单ID     ┃ 交易对       ┃ 方向   ┃ 多空   ┃ 类型   ┃ 数量       ┃ 价格       ┃ 状态       ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ 123456789  │ BTC/USDT     │ BUY    │ LONG   │ LIMIT  │ 0.00100000 │ 30000.00   │ NEW        │
│ 123456790  │ ETH/USDT     │ SELL   │ SHORT  │ LIMIT  │ 0.01000000 │ 2000.00    │ PARTIALLY  │
└────────────┴──────────────┴────────┴────────┴────────┴────────────┴────────────┴────────────┘
```

## Prometheus Metrics

订单数据会自动导出为 Prometheus metrics，可在 Grafana 中可视化：

### 可用指标

1. **exchange_order_count**: 活跃订单数量
   - Labels: `exchange`, `exchange_type`, `account_id`, `symbol`, `side`, `position_side`, `status`
   - 示例: `exchange_order_count{exchange="xt",exchange_type="perp",account_id="account_002",symbol="BTC/USDT",side="BUY",position_side="LONG",status="NEW"}`

2. **exchange_order_notional**: 订单名义价值
   - Labels: `exchange`, `exchange_type`, `account_id`, `symbol`, `side`, `position_side`
   - 示例: `exchange_order_notional{exchange="xt",exchange_type="perp",account_id="account_002",symbol="BTC/USDT",side="BUY",position_side="LONG"}`

3. **exchange_order_update_total**: 订单更新总数
   - Labels: `exchange`, `exchange_type`, `account_id`, `order_status`, `side`, `position_side`
   - 示例: `exchange_order_update_total{exchange="xt",exchange_type="perp",account_id="account_002",order_status="FILLED",side="BUY",position_side="LONG"}`

### 在 Grafana 中查询

#### 查看所有活跃的多单
```promql
sum(exchange_order_count{position_side="LONG",status=~"NEW|LIVE|PARTIALLY_FILLED"}) by (account_id, symbol, exchange)
```

#### 查看所有活跃的空单
```promql
sum(exchange_order_count{position_side="SHORT",status=~"NEW|LIVE|PARTIALLY_FILLED"}) by (account_id, symbol, exchange)
```

#### 查看多空订单数量对比
```promql
sum(exchange_order_count{status=~"NEW|LIVE|PARTIALLY_FILLED"}) by (position_side, account_id)
```

#### 查看订单名义价值
```promql
sum(exchange_order_notional) by (account_id, symbol, position_side)
```

#### 查看持仓价值（按币种分组）
```promql
sum(exchange_position_quantity * exchange_position_mark_price) by (symbol, account_id, exchange)
```

## 在 Grafana 仪表板中添加订单面板

### 面板 1: 活跃订单数量（按多空分组）

- **Panel type**: Stat
- **Query**:
  ```promql
  sum(exchange_order_count{status=~"NEW|LIVE|PARTIALLY_FILLED|OPEN"}) by (position_side, account_id, exchange)
  ```
- **Legend**: `{{position_side}} - {{account_id}} ({{exchange}})`
- **Unit**: Short

### 面板 2: 订单更新趋势

- **Panel type**: Time series
- **Query**:
  ```promql
  rate(exchange_order_update_total[1m])
  ```
- **Legend**: `{{account_id}} - {{order_status}} - {{position_side}}`
- **Unit**: Ops/sec

### 面板 3: 多空订单名义价值对比

- **Panel type**: Time series
- **Query**:
  ```promql
  sum(exchange_order_notional) by (position_side, account_id, symbol)
  ```
- **Legend**: `{{position_side}} - {{account_id}} - {{symbol}}`
- **Unit**: Currency > USD

### 面板 4: 订单状态分布（饼图）

- **Panel type**: Pie chart
- **Query**:
  ```promql
  sum(exchange_order_update_total) by (order_status)
  ```

## 注意事项

1. **多空方向说明**:
   - **LONG（多）**: 看涨方向，买入开多或卖出平多
   - **SHORT（空）**: 看跌方向，卖出开空或买入平空
   - **NET**: 净持仓模式（部分交易所支持）

2. **订单状态**:
   - **NEW/LIVE/OPEN**: 新订单，等待成交
   - **PARTIALLY_FILLED**: 部分成交
   - **FILLED**: 完全成交
   - **CANCELED**: 已取消
   - **REJECTED**: 已拒绝

3. **Metrics 端口**:
   - 默认端口: `9500`
   - 可通过环境变量 `PROM_METRICS_PORT` 自定义
   - 确保端口未被占用

4. **数据同步**:
   - 订单数据会自动保存到数据库
   - XT 多账号模式使用账号特定的表
   - 其他交易所使用通用表

## 故障排查

### 订单不显示多空方向

- 检查订单数据是否包含 `positionSide` 或 `ps` 字段
- 某些交易所可能使用不同的字段名
- 查看日志确认订单数据结构

### Metrics 未更新

- 确认 metrics 服务器已启动（检查端口是否监听）
- 验证 Prometheus 能抓取到 metrics: `curl http://localhost:9600/metrics | grep exchange_order`
- 检查订单订阅是否正常运行

### 订单显示格式问题

- 使用 `--output json` 查看原始订单数据
- 使用 `--debug` 查看详细日志

