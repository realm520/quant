# Prometheus 配置指南

本文档说明如何配置 Prometheus 来抓取持仓指标的 metrics。

## 前置条件

1. **启动持仓指标定时计算服务**：
   ```bash
   uv run scripts/start_position_metrics_scheduler.py --config config/accounts.json --interval 10
   ```
   服务会自动启动 Prometheus metrics server（端口 9600）

2. **确保 Prometheus 已安装并运行**

## 配置 Prometheus

### 1. 更新 Prometheus 配置文件

编辑 `prometheus/prometheus.yml`，添加持仓指标服务的抓取配置：

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # 持仓指标服务
  - job_name: 'position-metrics-scheduler'
    static_configs:
      - targets: ['localhost:9602']
    scrape_interval: 30s  # 每30秒抓取一次（因为服务每5-10分钟计算一次）
    metrics_path: '/metrics'
```

### 2. 重启 Prometheus

```bash
# 如果使用 Docker
docker-compose -f docker-compose.monitoring.yml restart prometheus

# 如果直接运行 Prometheus
# 重启 Prometheus 服务
```

### 3. 验证抓取状态

访问 Prometheus UI：http://localhost:9090

1. 进入 **Status** > **Targets**
2. 确认 `position-metrics-scheduler` 的状态为 **UP**
3. 在 **Graph** 页面测试查询：
   ```promql
   position_daily_pnl
   ```

## 在 Grafana 中配置

### 1. 添加 Prometheus 数据源

1. 进入 Grafana **Configuration** > **Data Sources**
2. 点击 **Add data source**
3. 选择 **Prometheus**
4. 配置：
   - **URL**: `http://localhost:9090`
   - 点击 **Save & Test**

### 2. 导入 Prometheus Dashboard

1. 进入 **Dashboards** > **Import**
2. 上传 `grafana/dashboards/position-metrics-prometheus.json`
3. 选择 Prometheus 数据源
4. 点击 **Import**

## 可用的 Prometheus Metrics

所有 metrics 都包含以下 labels：
- `account_id`: 账号ID
- `exchange`: 交易所（binance, xt）
- `symbol`: 交易对（如 BTCUSDT）

### Metrics 列表

| Metric 名称 | 类型 | 说明 |
|-----------|------|------|
| `position_pre_long_qty` | Gauge | 昨日多头持仓量 |
| `position_pre_short_qty` | Gauge | 昨日空头持仓量 |
| `position_pre_long_value` | Gauge | 昨日多头市值 |
| `position_pre_short_value` | Gauge | 昨日空头市值 |
| `position_long_qty` | Gauge | 多头交易量 |
| `position_short_qty` | Gauge | 空头交易量 |
| `position_long_value` | Gauge | 多头市值 |
| `position_short_value` | Gauge | 空头市值 |
| `position_avg_buy_prz` | Gauge | 买入平均价格 |
| `position_avg_sell_prz` | Gauge | 卖出平均价格 |
| `position_matched_qty` | Gauge | 轧差数量 |
| `position_realized_pnl` | Gauge | 当日已实现盈亏 |
| `position_left_long_qty` | Gauge | 多头剩余持仓 |
| `position_left_short_qty` | Gauge | 空头剩余持仓 |
| `position_left_long_value` | Gauge | 多头剩余市值 |
| `position_left_short_value` | Gauge | 空头剩余市值 |
| `position_close_prz` | Gauge | 当日最后一笔成交价 |
| `position_unrealized_pnl` | Gauge | 当日未实现盈亏 |
| `position_daily_pnl` | Gauge | 单日 PnL |
| `position_cumulative_pnl` | Gauge | 累计 PnL |

## 常用 PromQL 查询示例

### 查看所有账号的单日 PnL

```promql
position_daily_pnl
```

### 查看特定账号的累计 PnL

```promql
position_cumulative_pnl{account_id="account_006ktmm1"}
```

### 查看特定交易对的持仓量

```promql
position_pre_long_qty{exchange="xt", symbol="BTCUSDT"}
```

### 按交易所聚合的累计 PnL

```promql
sum(position_cumulative_pnl) by (exchange)
```

### 按账号聚合的单日 PnL

```promql
sum(position_daily_pnl) by (account_id)
```

### 查看所有账号的总累计 PnL

```promql
sum(position_cumulative_pnl)
```

## 告警配置示例

### 单日 PnL 异常告警

在 Prometheus AlertManager 中配置：

```yaml
groups:
  - name: position_alerts
    rules:
      - alert: HighDailyPnL
        expr: abs(position_daily_pnl) > 10000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "单日 PnL 异常"
          description: "账号 {{ $labels.account_id }} 的交易对 {{ $labels.symbol }} 单日 PnL 为 {{ $value }}"
```

## 故障排查

### Metrics 端点无法访问

1. 检查服务是否运行：
   ```bash
   ps aux | grep start_position_metrics_scheduler
   ```

2. 测试 metrics 端点：
   ```bash
   curl http://localhost:9602/metrics
   ```

3. 查看服务日志：
   ```bash
   tail -f logs/tri-arb.log
   ```

### Prometheus 无法抓取

1. 检查 Prometheus targets：http://localhost:9090/targets
2. 确认 `position-metrics-scheduler` 状态为 **UP**
3. 检查 Prometheus 配置文件的语法：
   ```bash
   promtool check config prometheus/prometheus.yml
   ```

### Grafana 显示 "No data"

1. 确认 Prometheus 数据源连接正常
2. 在 Prometheus UI 中测试查询是否返回数据
3. 检查时间范围设置
4. 确认变量（account_id, exchange, symbol）选择了正确的值

## 数据保留

Prometheus 默认保留 15 天的数据。如果需要长期保留：

1. **使用 Thanos**：长期存储解决方案
2. **使用 VictoriaMetrics**：高性能时序数据库
3. **继续使用 PostgreSQL**：数据永久保存在 `position_metrics` 表中

## 混合方案

可以同时使用 PostgreSQL 和 Prometheus：

- **PostgreSQL**：用于历史数据分析和报表（永久保存）
- **Prometheus**：用于实时监控和告警（15天保留）

两个数据源可以同时工作，互不干扰。

