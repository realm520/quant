# 数据库数据转化、Metrics 和可视化指南

本文档详细说明如何将数据库中的交易数据转化为 Prometheus metrics，并通过 Grafana 进行可视化监控。

## 📋 目录

1. [架构概述](#架构概述)
2. [数据源说明](#数据源说明)
3. [数据转化流程](#数据转化流程)
4. [Metrics 定义](#metrics-定义)
5. [Prometheus 配置](#prometheus-配置)
6. [Grafana 可视化](#grafana-可视化)
7. [常用查询示例](#常用查询示例)
8. [告警配置](#告警配置)
9. [故障排查](#故障排查)

---

## 架构概述

```
┌─────────────────┐
│   PostgreSQL    │  ← 存储原始交易数据（WebSocket + REST API）
│   数据库        │
└────────┬────────┘
         │
         │ 数据读取
         ▼
┌─────────────────┐
│   cextools      │  ← 应用服务（订阅、查询、监控）
│   服务进程      │
└────────┬────────┘
         │
         │ 暴露 Metrics
         ▼
┌─────────────────┐
│   Prometheus    │  ← Metrics 收集和存储
│   (端口 9090)   │
└────────┬────────┘
         │
         │ 查询 Metrics
         ▼
┌─────────────────┐
│    Grafana      │  ← 数据可视化
│   (端口 3000)   │
└─────────────────┘
```

### 数据流向

1. **数据采集**：WebSocket 实时推送 + REST API 定时查询
2. **数据存储**：PostgreSQL 数据库（原始数据 + 结构化数据）
3. **Metrics 生成**：应用服务实时计算并暴露 Prometheus metrics
4. **Metrics 收集**：Prometheus 定期抓取 metrics
5. **数据可视化**：Grafana 从 Prometheus 查询并展示

---

## 数据源说明

### 数据库表结构

系统使用 PostgreSQL 存储以下类型的数据：

#### 1. WebSocket 实时数据表

**XT 交易所 WebSocket 数据：**
- `xt_account_updates` - 账户余额更新
- `xt_position_updates` - 持仓更新
- `xt_order_updates` - 订单状态更新
- `xt_trade_updates` - 成交记录
- `xt_order_updates_account_*` - 多账号订单表（按账号分表）

**其他交易所 WebSocket 数据：**
- `account_updates` - 通用账户更新（Binance、OKX、Gate）

#### 2. REST API 快照数据表

- `rest_balances` - 余额快照
- `rest_positions` - 持仓快照
- `rest_orders` - 订单快照
- `scheduled_queries` - 定时查询记录

### 数据表关键字段

#### 余额数据（rest_balances / xt_account_updates）

```sql
- exchange: 交易所名称 (binance, okx, gate, xt)
- exchange_type: 交易类型 (spot, perp)
- account_id: 账号ID（多账号支持）
- asset/currency: 资产类型 (USDT, BTC, ETH等)
- free/available: 可用余额
- locked/frozen: 冻结余额
- total: 总余额
- query_time/update_time: 时间戳
```

#### 持仓数据（rest_positions / xt_position_updates）

```sql
- symbol: 交易对 (BTC_USDT, ETH_USDT等)
- position_side: 持仓方向 (LONG, SHORT)
- position_amount/quantity: 持仓数量
- entry_price: 开仓均价
- mark_price: 标记价格
- unrealized_pnl: 未实现盈亏
- leverage: 杠杆倍数
```

#### 订单数据（rest_orders / xt_order_updates）

```sql
- order_id: 订单ID
- symbol: 交易对
- side: 买卖方向 (BUY, SELL)
- position_side: 持仓方向 (LONG, SHORT)
- order_status/status: 订单状态 (NEW, FILLED, CANCELED等)
- original_quantity/quantity: 原始数量
- executed_quantity/filled_quantity: 已成交数量
- price: 订单价格
- average_price: 平均成交价
```

---

## 数据转化流程

### 1. 实时数据转化（WebSocket）

当 WebSocket 接收到数据更新时，系统会：

1. **保存原始数据**到数据库
2. **更新 Prometheus Metrics**（实时）

```python
# 示例：更新余额 metrics
from tri_arb.metrics.prometheus import update_balance_metrics

# 当收到账户更新时
update_balance_metrics(
    exchange="xt",
    exchange_type="perp",
    account_id="account_001",
    balances={
        "USDT": {
            "available": 10000.0,
            "frozen": 500.0,
            "total": 10500.0
        }
    }
)
```

### 2. 定时查询数据转化（REST API）

当执行定时查询时，系统会：

1. **查询 REST API**获取最新数据
2. **保存快照**到数据库
3. **更新 Prometheus Metrics**

```python
# 示例：保存余额查询结果
from tri_arb.services.rest_data_service import RestDataService

service = RestDataService(db_manager)
await service.save_balance_query(
    exchange="xt",
    exchange_type="perp",
    balances_data={
        "USDT": {
            "available": 10000.0,
            "frozen": 500.0,
            "total": 10500.0
        }
    },
    query_type="scheduled",
    account_id="account_001"
)
```

### 3. Metrics 更新时机

- **WebSocket 更新**：实时更新（延迟 < 1秒）
- **REST API 查询**：按配置间隔更新（默认 1-5 分钟）
- **手动查询**：立即更新

---

## Metrics 定义

### 余额 Metrics

#### `exchange_balance_available`
- **类型**：Gauge（当前值）
- **标签**：`exchange`, `exchange_type`, `account_id`, `asset`
- **说明**：各账户各资产的可用余额
- **单位**：资产数量（如 USDT）

**示例查询：**
```promql
# 查看所有账户的 USDT 可用余额
exchange_balance_available{asset="USDT"}

# 查看特定账户的余额
exchange_balance_available{account_id="account_001", asset="USDT"}
```

#### `exchange_balance_frozen`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `asset`
- **说明**：冻结余额（用于保证金、挂单等）

#### `exchange_balance_total`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `asset`
- **说明**：总余额（可用 + 冻结）

#### `exchange_balance_query_total`
- **类型**：Counter（累计计数）
- **标签**：`exchange`, `exchange_type`, `account_id`, `status`
- **说明**：余额查询次数（success/failure）

**示例查询：**
```promql
# 查询成功率
rate(exchange_balance_query_total{status="success"}[5m])

# 查询失败次数
increase(exchange_balance_query_total{status="failure"}[1h])
```

### 持仓 Metrics

#### `exchange_position_quantity`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `symbol`, `position_side`
- **说明**：持仓数量（正数=多仓，负数=空仓）

#### `exchange_position_entry_price`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `symbol`, `position_side`
- **说明**：开仓均价

#### `exchange_position_mark_price`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `symbol`, `position_side`
- **说明**：标记价格

#### `exchange_position_unrealized_pnl`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `symbol`, `position_side`
- **说明**：未实现盈亏

#### `exchange_position_leverage`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `symbol`, `position_side`
- **说明**：杠杆倍数

**示例查询：**
```promql
# 查看所有持仓的未实现盈亏
exchange_position_unrealized_pnl

# 计算总未实现盈亏
sum(exchange_position_unrealized_pnl) by (account_id)
```

### 订单 Metrics

#### `exchange_order_count`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `symbol`, `side`, `position_side`, `status`
- **说明**：活跃订单数量（按状态分类）

#### `exchange_order_notional`
- **类型**：Gauge
- **标签**：`exchange`, `exchange_type`, `account_id`, `symbol`, `side`, `position_side`
- **说明**：订单名义价值（数量 × 价格）

#### `exchange_order_update_total`
- **类型**：Counter
- **标签**：`exchange`, `exchange_type`, `account_id`, `order_status`, `side`, `position_side`
- **说明**：订单更新次数（按状态分类）

#### `exchange_trade_update_total`
- **类型**：Counter
- **标签**：`exchange`, `exchange_type`, `account_id`, `symbol`, `side`, `position_side`
- **说明**：成交更新次数（按交易对、方向和持仓方向分类）

**示例查询：**
```promql
# 查看活跃订单数
sum(exchange_order_count{status="NEW"}) by (account_id, symbol)

# 查看订单更新频率
rate(exchange_order_update_total[1m])

# 查看成交频率
rate(exchange_trade_update_total[1m])

# 查看特定交易对的成交频率
rate(exchange_trade_update_total{symbol="BTC/USDT"}[1m])
```

### 系统 Metrics

#### `tri_arb_requests_total`
- **类型**：Counter
- **标签**：`method`, `endpoint`, `status`
- **说明**：API 请求总数

#### `tri_arb_requests_duration_seconds`
- **类型**：Histogram
- **标签**：`method`, `endpoint`
- **说明**：API 请求延迟分布

#### `tri_arb_errors_total`
- **类型**：Counter
- **标签**：`type`, `component`
- **说明**：错误总数

---

## Prometheus 配置

### 配置文件位置

`prometheus/prometheus.yml`

### 配置说明

```yaml
global:
  scrape_interval: 15s      # 每15秒抓取一次
  evaluation_interval: 15s   # 每15秒评估一次规则

scrape_configs:
  - job_name: 'cextools-monitor'
    static_configs:
      - targets: 
          - 'localhost:9600'  # watch-balance, watch-account
          - 'localhost:9601'  # subscribe multi-account
        labels:
          service: 'cextools'
          component: 'exchange-monitor'
    scrape_interval: 10s  # 更频繁的抓取以获得实时数据
    metrics_path: '/metrics'
```

### 启动 Prometheus

#### 使用 Docker Compose（推荐）

```bash
cd /home/ubuntu/quant
docker-compose -f docker-compose.monitoring.yml up -d
```

#### 手动启动

```bash
# 下载 Prometheus
wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz
tar xvfz prometheus-*.tar.gz
cd prometheus-*

# 复制配置文件
cp /home/ubuntu/quant/prometheus/prometheus.yml .

# 启动 Prometheus
./prometheus --config.file=prometheus.yml
```

### 验证 Prometheus

1. **访问 Web UI**：http://localhost:9090
2. **检查 Targets**：http://localhost:9090/targets（确认状态为 "UP"）
3. **测试查询**：http://localhost:9090/graph
   ```promql
   exchange_balance_total
   ```

---

## Grafana 可视化

### 启动 Grafana

#### 使用 Docker Compose（推荐）

```bash
cd /home/ubuntu/quant
docker-compose -f docker-compose.monitoring.yml up -d
```

#### 手动安装

```bash
# Ubuntu/Debian
sudo apt-get install -y software-properties-common
sudo add-apt-repository "deb https://packages.grafana.com/oss/deb stable main"
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
sudo apt-get update
sudo apt-get install grafana

# 启动 Grafana
sudo systemctl start grafana-server
sudo systemctl enable grafana-server
```

### 配置数据源

1. 登录 Grafana：http://localhost:3000
   - 默认用户名：`admin`
   - 默认密码：`admin`

2. 进入 **Configuration** > **Data Sources**

3. 点击 **Add data source** > 选择 **Prometheus**

4. 配置：
   - **URL**：`http://prometheus:9090`（Docker 中）或 `http://localhost:9090`
   - **Access**：Server（默认）

5. 点击 **Save & Test**

### 导入仪表板

#### 方法 1：导入预配置仪表板（推荐）

1. 进入 **Dashboards** > **Import**
2. 点击 **Upload JSON file**
3. 选择 `/home/ubuntu/quant/grafana/dashboards/exchange-monitor.json`
4. 选择 Prometheus 数据源
5. 点击 **Import**

#### 方法 2：手动创建面板

##### 面板 1：账户余额总览

- **Panel type**：Stat
- **Query**：
  ```promql
  sum(exchange_balance_total{asset="USDT"}) by (account_id, exchange)
  ```
- **Legend**：`{{account_id}} ({{exchange}})`
- **Unit**：Currency > USD

##### 面板 2：可用余额趋势

- **Panel type**：Time series
- **Query**：
  ```promql
  exchange_balance_available
  ```
- **Legend**：`{{account_id}} - {{asset}} ({{exchange}})`
- **Unit**：Currency > USD

##### 面板 3：持仓未实现盈亏

- **Panel type**：Time series
- **Query**：
  ```promql
  exchange_position_unrealized_pnl
  ```
- **Legend**：`{{account_id}} - {{symbol}} ({{position_side}})`
- **Unit**：Currency > USD

##### 面板 4：订单更新频率

- **Panel type**：Time series
- **Query**：
  ```promql
  rate(exchange_order_update_total[1m])
  ```
- **Legend**：`{{account_id}} - {{symbol}} - {{order_status}}`
- **Unit**：Ops/sec

##### 面板 5：成交频率

- **Panel type**：Time series
- **Query**：
  ```promql
  rate(exchange_trade_update_total[1m])
  ```
- **Legend**：`{{account_id}} - {{symbol}} - {{side}} ({{position_side}})`
- **Unit**：Ops/sec

##### 面板 6：查询成功率

- **Panel type**：Stat
- **Query**：
  ```promql
  sum(rate(exchange_balance_query_total{status="success"}[5m])) by (account_id, exchange)
  ```
- **Unit**：Ops/sec

---

## 常用查询示例

### 余额查询

#### 查看所有账户的 USDT 总余额

```promql
sum(exchange_balance_total{asset="USDT"}) by (account_id, exchange)
```

#### 查看特定账户的余额变化率

```promql
rate(exchange_balance_total{account_id="account_001", asset="USDT"}[5m])
```

#### 查看各交易所的总资产

```promql
sum(exchange_balance_total) by (exchange, asset)
```

#### 查看可用余额占比

```promql
exchange_balance_available{asset="USDT"} / exchange_balance_total{asset="USDT"} * 100
```

### 持仓查询

#### 查看所有持仓的未实现盈亏

```promql
exchange_position_unrealized_pnl
```

#### 计算总未实现盈亏

```promql
sum(exchange_position_unrealized_pnl) by (account_id)
```

#### 查看持仓数量（按交易对）

```promql
sum(abs(exchange_position_quantity)) by (symbol, position_side)
```

#### 查看持仓价值（按币种分组）

```promql
sum(exchange_position_quantity * exchange_position_mark_price) by (symbol, account_id, exchange)
```

#### 查看持仓收益率

```promql
exchange_position_unrealized_pnl / (exchange_position_entry_price * abs(exchange_position_quantity)) * 100
```

### 订单查询

#### 查看活跃订单数

```promql
sum(exchange_order_count{status="NEW"}) by (account_id, symbol)
```

#### 查看订单更新频率

```promql
rate(exchange_order_update_total[1m])
```

#### 查看成交频率

```promql
rate(exchange_trade_update_total[1m])
```

#### 查看特定交易对的成交频率

```promql
rate(exchange_trade_update_total{symbol="BTC/USDT"}[1m])
```

#### 查看订单成交率

```promql
sum(increase(exchange_order_update_total{order_status="FILLED"}[1h])) 
/ 
sum(increase(exchange_order_update_total[1h])) * 100
```

### 系统监控查询

#### 查看查询错误率

```promql
sum(rate(exchange_balance_query_total{status="failure"}[5m])) 
/ 
sum(rate(exchange_balance_query_total[5m])) * 100
```

#### 查看 API 请求延迟

```promql
histogram_quantile(0.95, tri_arb_requests_duration_seconds_bucket)
```

#### 查看错误总数

```promql
sum(increase(tri_arb_errors_total[1h])) by (type, component)
```

---

## 告警配置

### 在 Grafana 中配置告警

#### 示例 1：余额低于阈值告警

1. 进入 **Alerting** > **Alert rules**
2. 点击 **New alert rule**
3. 配置：
   - **Name**：账户余额过低
   - **Query A**：
     ```promql
     exchange_balance_total{account_id="account_001", asset="USDT"}
     ```
   - **Condition**：`WHEN last() OF A IS BELOW 1000`
   - **Duration**：5m
   - **Notification**：配置通知渠道（Email、Webhook等）

#### 示例 2：查询失败率过高告警

1. 创建新规则
2. 配置：
   - **Name**：查询失败率过高
   - **Query A**：
     ```promql
     sum(rate(exchange_balance_query_total{status="failure"}[5m])) by (account_id) 
     / 
     sum(rate(exchange_balance_query_total[5m])) by (account_id) * 100
     ```
   - **Condition**：`WHEN last() OF A IS ABOVE 10`
   - **Duration**：5m

#### 示例 3：未实现盈亏过大告警

1. 创建新规则
2. 配置：
   - **Name**：未实现亏损过大
   - **Query A**：
     ```promql
     sum(exchange_position_unrealized_pnl) by (account_id)
     ```
   - **Condition**：`WHEN last() OF A IS BELOW -1000`
   - **Duration**：5m

### 在 Prometheus 中配置告警规则

创建告警规则文件：`prometheus/alerts.yml`

```yaml
groups:
  - name: trading_alerts
    interval: 30s
    rules:
      - alert: LowBalance
        expr: exchange_balance_total{asset="USDT"} < 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "账户余额过低"
          description: "账户 {{ $labels.account_id }} 的 {{ $labels.asset }} 余额为 {{ $value }}"

      - alert: HighQueryFailureRate
        expr: |
          sum(rate(exchange_balance_query_total{status="failure"}[5m])) by (account_id)
          /
          sum(rate(exchange_balance_query_total[5m])) by (account_id) * 100 > 10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "查询失败率过高"
          description: "账户 {{ $labels.account_id }} 的查询失败率为 {{ $value }}%"
```

在 `prometheus.yml` 中添加：

```yaml
rule_files:
  - "alerts.yml"
```

---

## 故障排查

### Prometheus 无法抓取数据

**症状**：Prometheus targets 显示 "DOWN"

**排查步骤**：

1. **检查 metrics 端点是否可访问**：
   ```bash
   curl http://localhost:9600/metrics | head -20
   ```

2. **检查服务是否运行**：
   ```bash
   ps aux | grep cextools
   ```

3. **检查端口是否被占用**：
   ```bash
   netstat -tlnp | grep 9600
   ```

4. **检查 Prometheus 配置**：
   - 确认 `prometheus.yml` 中的 targets 地址正确
   - 确认端口号匹配

5. **查看 Prometheus 日志**：
   ```bash
   docker logs prometheus
   # 或
   journalctl -u prometheus -f
   ```

### Grafana 显示 "No data"

**症状**：Grafana 面板显示 "No data"

**排查步骤**：

1. **确认数据源连接正常**：
   - 进入 **Configuration** > **Data Sources**
   - 点击 **Test** 按钮

2. **检查时间范围设置**：
   - 确认时间范围包含数据时间
   - 尝试扩大时间范围（如最近 1 小时）

3. **在 Prometheus 中验证查询**：
   - 访问 http://localhost:9090/graph
   - 输入相同的 PromQL 查询
   - 确认是否有数据返回

4. **检查 PromQL 语法**：
   - 确认查询语法正确
   - 检查标签名称是否匹配

### Metrics 更新延迟

**症状**：Grafana 中数据更新不及时

**排查步骤**：

1. **检查 Prometheus scrape_interval**：
   ```yaml
   scrape_interval: 10s  # 更频繁的抓取
   ```

2. **检查应用服务 metrics 更新频率**：
   - WebSocket 数据应该实时更新
   - REST API 查询按配置间隔更新

3. **检查数据库查询性能**：
   ```sql
   -- 检查最近的数据更新时间
   SELECT MAX(update_time) FROM xt_account_updates;
   ```

### 数据不一致

**症状**：数据库中有数据，但 Prometheus metrics 中没有

**排查步骤**：

1. **检查应用服务日志**：
   ```bash
   tail -f logs/tri-arb.log | grep -i metric
   ```

2. **确认 metrics 更新代码被调用**：
   - 检查 WebSocket 处理函数中是否调用了 `update_balance_metrics`
   - 检查 REST API 查询后是否更新了 metrics

3. **手动触发 metrics 更新**：
   ```bash
   # 执行一次余额查询
   cextools account watch-balance -x xt -e perp --config config/accounts.json
   ```

### 内存占用过高

**症状**：Prometheus 或 Grafana 内存占用持续增长

**排查步骤**：

1. **检查 metrics 数量**：
   ```promql
   count({__name__=~".+"})
   ```

2. **检查标签基数**：
   - 过多的标签组合会导致 metrics 数量爆炸
   - 考虑减少不必要的标签

3. **配置数据保留时间**：
   ```yaml
   # prometheus.yml
   global:
     retention: 15d  # 保留15天数据
   ```

---

## 最佳实践

### 1. Metrics 命名规范

- 使用下划线分隔：`exchange_balance_total`
- 使用描述性名称
- 统一前缀：`exchange_*` 用于交易所相关，`tri_arb_*` 用于系统相关

### 2. 标签设计

- 使用有意义的标签：`account_id`, `exchange`, `asset`
- 避免高基数标签（如订单ID、时间戳）
- 保持标签一致性

### 3. 查询优化

- 使用 `rate()` 和 `increase()` 处理 Counter
- 使用 `sum()` 和 `by` 聚合数据
- 避免过于复杂的查询

### 4. 告警设计

- 设置合理的阈值
- 使用 `for` 持续时间避免误报
- 配置清晰的告警消息

### 5. 数据保留

- Prometheus 数据保留：15-30 天
- 长期数据可导出到对象存储
- 使用 Grafana 的长期存储插件

---

## 相关文档

- [Grafana 设置指南](./grafana-setup.md)
- [Grafana 快速入门](../README-GRAFANA.md)
- [多账号架构](./MULTI_ACCOUNT_ARCHITECTURE.md)
- [数据库架构](./architecture.md)

---

## 附录

### A. Metrics 完整列表

#### 余额 Metrics
- `exchange_balance_available`
- `exchange_balance_frozen`
- `exchange_balance_total`
- `exchange_balance_query_total`

#### 持仓 Metrics
- `exchange_position_quantity`
- `exchange_position_entry_price`
- `exchange_position_mark_price`
- `exchange_position_unrealized_pnl`
- `exchange_position_leverage`

#### 订单 Metrics
- `exchange_order_count`
- `exchange_order_notional`
- `exchange_order_update_total`
- `exchange_trade_update_total`

#### 系统 Metrics
- `tri_arb_requests_total`
- `tri_arb_requests_duration_seconds`
- `tri_arb_errors_total`
- `tri_arb_exchange_errors_total`
- `tri_arb_database_queries_total`
- `tri_arb_database_query_duration_seconds`

### B. 数据库表映射

| Metrics | 数据源表 | 更新方式 |
|---------|---------|---------|
| `exchange_balance_*` | `rest_balances`, `xt_account_updates` | WebSocket 实时 + REST 定时 |
| `exchange_position_*` | `rest_positions`, `xt_position_updates` | WebSocket 实时 + REST 定时 |
| `exchange_order_*` | `rest_orders`, `xt_order_updates` | WebSocket 实时 + REST 定时 |

### C. 常用 PromQL 函数

- `rate()` - 计算速率（Counter）
- `increase()` - 计算增量（Counter）
- `sum()` - 求和
- `avg()` - 平均值
- `max()` - 最大值
- `min()` - 最小值
- `by` - 按标签分组
- `without` - 排除标签分组
- `histogram_quantile()` - 计算分位数（Histogram）

---

**文档版本**：1.0  
**最后更新**：2024年  
**维护者**：开发团队

