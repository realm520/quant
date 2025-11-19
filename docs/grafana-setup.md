# Grafana 可视化设置指南

## 前置条件

1. 确保 `cextools account watch-balance` 正在运行并暴露 metrics（端口 9600）
2. 安装 Docker 和 Docker Compose

## 快速启动（使用 Docker Compose）

### 1. 启动 Prometheus 和 Grafana

```bash
cd /home/ubuntu/quant
docker-compose -f docker-compose.monitoring.yml up -d
```

### 2. 验证服务运行

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
  - 用户名: `admin`
  - 密码: `admin`

### 3. 在 Prometheus 中验证数据

访问 http://localhost:9090/targets，确认 `cextools-monitor` target 状态为 "UP"。

在 http://localhost:9090/graph 中测试查询：
```promql
exchange_balance_total
```

## 手动安装（不使用 Docker）

### 1. 安装 Prometheus

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

### 2. 安装 Grafana

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

## 在 Grafana 中配置数据源

1. 登录 Grafana (http://localhost:3000)
2. 进入 **Configuration** > **Data Sources**
3. 点击 **Add data source**
4. 选择 **Prometheus**
5. 设置 URL: `http://localhost:9090`
6. 点击 **Save & Test**

## 创建仪表板

### 方法 1: 导入预配置仪表板

1. 进入 **Dashboards** > **Import**
2. 上传 `/home/ubuntu/quant/grafana/dashboards/exchange-monitor.json`
3. 选择 Prometheus 数据源
4. 点击 **Import**

### 方法 2: 手动创建面板

#### 面板 1: 账户余额总览

- **Panel type**: Stat
- **Query**: 
  ```promql
  sum(exchange_balance_total) by (account_id, exchange)
  ```
- **Legend**: `{{account_id}} ({{exchange}})`
- **Unit**: Currency > USD

#### 面板 2: 可用余额趋势

- **Panel type**: Time series
- **Query**:
  ```promql
  exchange_balance_available
  ```
- **Legend**: `{{account_id}} - {{asset}} ({{exchange}})`
- **Unit**: Currency > USD

#### 面板 3: 冻结余额

- **Panel type**: Time series
- **Query**:
  ```promql
  exchange_balance_frozen
  ```
- **Legend**: `{{account_id}} - {{asset}} ({{exchange}})`
- **Unit**: Currency > USD

#### 面板 4: 总余额

- **Panel type**: Time series
- **Query**:
  ```promql
  exchange_balance_total
  ```
- **Legend**: `{{account_id}} - {{asset}} ({{exchange}})`
- **Unit**: Currency > USD

#### 面板 5: 查询成功率

- **Panel type**: Stat
- **Query**:
  ```promql
  sum(rate(exchange_balance_query_total{status="success"}[5m])) by (account_id, exchange)
  ```
- **Unit**: Ops/sec

#### 面板 6: 查询失败次数

- **Panel type**: Stat
- **Query**:
  ```promql
  sum(increase(exchange_balance_query_total{status="failure"}[1h])) by (account_id, exchange)
  ```

## 常用 PromQL 查询示例

### 查看所有账户的 USDT 总余额
```promql
sum(exchange_balance_total{asset="USDT"}) by (account_id, exchange)
```

### 查看特定账户的余额变化率
```promql
rate(exchange_balance_total{account_id="account_002"}[5m])
```

### 查看各交易所的总资产
```promql
sum(exchange_balance_total) by (exchange, asset)
```

### 查看查询错误率
```promql
sum(rate(exchange_balance_query_total{status="failure"}[5m])) / sum(rate(exchange_balance_query_total[5m]))
```

### 查看最近一次查询时间
```promql
exchange_last_query_timestamp
```

## 告警设置

### 示例：余额低于阈值告警

1. 进入 **Alerting** > **Alert rules**
2. 创建新规则：
   - **Name**: 账户余额过低
   - **Query**: 
     ```promql
     exchange_balance_total{account_id="account_002", asset="USDT"} < 1000
     ```
   - **Condition**: `WHEN last() OF A IS BELOW 1000`
   - **Duration**: 5m

### 示例：查询失败告警

1. 创建新规则：
   - **Name**: 查询失败率过高
   - **Query**:
     ```promql
     sum(rate(exchange_balance_query_total{status="failure"}[5m])) by (account_id) > 0.1
     ```

## 故障排查

### Prometheus 无法抓取数据

1. 检查 Prometheus targets: http://localhost:9090/targets
2. 确认 `cextools` 进程正在运行
3. 测试 metrics 端点: `curl http://localhost:9600/metrics`

### Grafana 显示 "No data"

1. 确认数据源连接正常
2. 检查时间范围设置
3. 在 Prometheus 中验证查询是否返回数据

### 更新仪表板

修改 `/home/ubuntu/quant/grafana/dashboards/exchange-monitor.json` 后，在 Grafana 中重新导入。

