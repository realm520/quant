# Grafana 持仓指标可视化配置指南

本文档说明如何在 Grafana 中配置数据源和面板，展示每5分钟计算的持仓和交易指标。

## 快速开始（推荐）

### 导入预配置仪表板

1. 进入 Grafana **Dashboards** > **Import**
2. 点击 **Upload JSON file**
3. 选择 `grafana/dashboards/position-metrics.json` 文件
4. 在 **PostgreSQL** 下拉菜单中选择你的 PostgreSQL 数据源
5. 点击 **Import**

导入后，你将看到包含以下面板的完整仪表板：
- **1. 昨收持仓 - 多头/空头持仓量**
- **2. 昨收持仓 - 多头/空头市值**
- **3. 今日交易 - 多头/空头交易量**
- **4. 买入/卖出平均价格 & 当前价格**
- **5. 已实现/未实现盈亏**
- **6. 单日/累计 PnL**
- **7. 剩余持仓量**
- **8. 单日 PnL 统计**（Stat 面板）
- **9. 累计 PnL 统计**（Stat 面板）

仪表板还包含三个变量（在顶部）：
- **账号**：可以选择一个或多个账号
- **交易所**：可以选择 binance 或 xt
- **交易对**：根据选择的账号和交易所动态过滤

---

## 详细配置说明

## 前置条件

1. **启动持仓指标定时计算服务**：
   ```bash
   python scripts/start_position_metrics_scheduler.py
   ```
   或使用 systemd 服务（见下文）

2. **确保 PostgreSQL 数据源已配置**：
   - Grafana 需要连接到 PostgreSQL 数据库
   - 数据存储在 `position_metrics` 表中

## 配置 Grafana 数据源

### 1. 添加 PostgreSQL 数据源

1. 登录 Grafana (http://localhost:3000)
2. 进入 **Configuration** > **Data Sources**
3. 点击 **Add data source**
4. 选择 **PostgreSQL**
5. 配置连接信息：
   - **Host**: `localhost:5432`（或你的数据库地址）
   - **Database**: `trading`（或你的数据库名）
   - **User**: 数据库用户名
   - **Password**: 数据库密码
   - **SSL Mode**: `disable`（或根据实际情况配置）
6. 点击 **Save & Test**

## 创建仪表板

### 面板 1: 昨收持仓 - 多头持仓量

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    pre_long_qty as value,
    account_id || ' - ' || symbol as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{account_id}} - {{symbol}}`
- **Unit**: Number
- **Y-axis label**: 昨日多头持仓量

### 面板 2: 昨收持仓 - 空头持仓量

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    pre_short_qty as value,
    account_id || ' - ' || symbol as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{account_id}} - {{symbol}}`
- **Unit**: Number
- **Y-axis label**: 昨日空头持仓量

### 面板 3: 今日交易 - 多头/空头交易量

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    long_qty as value,
    account_id || ' - ' || symbol || ' (多头)' as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  UNION ALL
  SELECT
    timestamp as time,
    short_qty as value,
    account_id || ' - ' || symbol || ' (空头)' as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{metric}}`
- **Unit**: Number
- **Y-axis label**: 交易量

### 面板 4: 买入/卖出平均价格

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    avg_buy_prz as value,
    account_id || ' - ' || symbol || ' (买入均价)' as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  UNION ALL
  SELECT
    timestamp as time,
    avg_sell_prz as value,
    account_id || ' - ' || symbol || ' (卖出均价)' as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{metric}}`
- **Unit**: Currency > USD
- **Y-axis label**: 平均价格

### 面板 5: 已实现盈亏 (Realized PnL)

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    realized_pnl as value,
    account_id || ' - ' || symbol as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{account_id}} - {{symbol}}`
- **Unit**: Currency > USD
- **Y-axis label**: 已实现盈亏

### 面板 6: 未实现盈亏 (Unrealized PnL)

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    unrealized_pnl as value,
    account_id || ' - ' || symbol as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{account_id}} - {{symbol}}`
- **Unit**: Currency > USD
- **Y-axis label**: 未实现盈亏

### 面板 7: 单日 PnL

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    daily_pnl as value,
    account_id || ' - ' || symbol as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{account_id}} - {{symbol}}`
- **Unit**: Currency > USD
- **Y-axis label**: 单日 PnL

### 面板 8: 累计 PnL

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    cumulative_pnl as value,
    account_id || ' - ' || symbol as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{account_id}} - {{symbol}}`
- **Unit**: Currency > USD
- **Y-axis label**: 累计 PnL

### 面板 9: 剩余持仓量

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    left_long_qty as value,
    account_id || ' - ' || symbol || ' (多头剩余)' as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  UNION ALL
  SELECT
    timestamp as time,
    left_short_qty as value,
    account_id || ' - ' || symbol || ' (空头剩余)' as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{metric}}`
- **Unit**: Number
- **Y-axis label**: 剩余持仓量

### 面板 10: 当前价格 (Close Price)

- **Panel type**: Time series
- **Query**:
  ```sql
  SELECT
    timestamp as time,
    close_prz as value,
    account_id || ' - ' || symbol as metric
  FROM position_metrics
  WHERE $__timeFilter(timestamp)
    AND account_id = '$account_id'
    AND exchange = '$exchange'
    AND symbol = '$symbol'
  ORDER BY timestamp
  ```
- **Legend**: `{{account_id}} - {{symbol}}`
- **Unit**: Currency > USD
- **Y-axis label**: 当前价格

## 变量配置

为了便于切换账号、交易所和交易对，建议在仪表板中配置以下变量：

### 变量 1: account_id

- **Type**: Query
- **Name**: account_id
- **Query**:
  ```sql
  SELECT DISTINCT account_id FROM position_metrics ORDER BY account_id
  ```
- **Multi-value**: 可选
- **Include All**: 可选

### 变量 2: exchange

- **Type**: Query
- **Name**: exchange
- **Query**:
  ```sql
  SELECT DISTINCT exchange FROM position_metrics ORDER BY exchange
  ```
- **Multi-value**: 可选
- **Include All**: 可选

### 变量 3: symbol

- **Type**: Query
- **Name**: symbol
- **Query**:
  ```sql
  SELECT DISTINCT symbol FROM position_metrics 
  WHERE account_id = '$account_id' AND exchange = '$exchange'
  ORDER BY symbol
  ```
- **Multi-value**: 可选
- **Include All**: 可选

## 聚合查询示例

### 所有账号的总 PnL

```sql
SELECT
  timestamp as time,
  SUM(daily_pnl) as value,
  '总单日 PnL' as metric
FROM position_metrics
WHERE $__timeFilter(timestamp)
GROUP BY timestamp
ORDER BY timestamp
```

### 按交易所聚合的 PnL

```sql
SELECT
  timestamp as time,
  SUM(daily_pnl) as value,
  exchange as metric
FROM position_metrics
WHERE $__timeFilter(timestamp)
GROUP BY timestamp, exchange
ORDER BY timestamp, exchange
```

### 按交易对聚合的持仓量

```sql
SELECT
  timestamp as time,
  SUM(pre_long_qty) as value,
  symbol || ' (多头)' as metric
FROM position_metrics
WHERE $__timeFilter(timestamp)
  AND account_id = '$account_id'
  AND exchange = '$exchange'
GROUP BY timestamp, symbol
ORDER BY timestamp, symbol
```

## 告警配置

### 示例：PnL 异常告警

1. 进入 **Alerting** > **Alert rules**
2. 创建新规则：
   - **Name**: 单日 PnL 异常
   - **Query**:
     ```sql
     SELECT
       timestamp as time,
       daily_pnl as value,
       account_id || ' - ' || symbol as metric
     FROM position_metrics
     WHERE timestamp > NOW() - INTERVAL '10 minutes'
       AND ABS(daily_pnl) > 10000
     ```
   - **Condition**: `WHEN last() OF A IS ABOVE 10000`
   - **Duration**: 5m

## 使用 Systemd 服务（可选）

创建 systemd 服务文件 `/etc/systemd/system/position-metrics-scheduler.service`：

```ini
[Unit]
Description=Position Metrics Scheduler
After=network.target postgresql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/quant
Environment="PATH=/path/to/venv/bin"
ExecStart=/path/to/venv/bin/python /path/to/quant/scripts/start_position_metrics_scheduler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable position-metrics-scheduler
sudo systemctl start position-metrics-scheduler
```

查看日志：

```bash
sudo journalctl -u position-metrics-scheduler -f
```

## 故障排查

### 数据没有更新

1. 检查定时任务服务是否运行：
   ```bash
   ps aux | grep start_position_metrics_scheduler
   ```

2. 检查数据库连接：
   ```bash
   psql -h localhost -U your_user -d trading -c "SELECT COUNT(*) FROM position_metrics;"
   ```

3. 查看服务日志：
   ```bash
   tail -f logs/tri-arb.log
   ```

### Grafana 显示 "No data"

1. 确认数据源连接正常
2. 检查时间范围设置（确保包含数据的时间范围）
3. 在数据库中直接查询验证：
   ```sql
   SELECT * FROM position_metrics 
   ORDER BY timestamp DESC 
   LIMIT 10;
   ```

### 查询性能优化

如果数据量很大，可以考虑：

1. **添加分区表**：按时间分区 `position_metrics` 表
2. **创建物化视图**：为常用查询创建物化视图
3. **索引优化**：确保 `timestamp`, `account_id`, `exchange`, `symbol` 上有索引（已创建）

## 数据保留策略

建议定期清理旧数据，例如只保留最近30天的数据：

```sql
DELETE FROM position_metrics 
WHERE timestamp < NOW() - INTERVAL '30 days';
```

可以创建一个定时任务（cron）来执行清理：

```bash
# 每天凌晨2点清理30天前的数据
0 2 * * * psql -h localhost -U your_user -d trading -c "DELETE FROM position_metrics WHERE timestamp < NOW() - INTERVAL '30 days';"
```

