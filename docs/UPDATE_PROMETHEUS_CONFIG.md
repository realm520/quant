# 更新运行中的 Prometheus 配置

## 当前配置位置

根据 pm2 信息，当前运行的 Prometheus 使用的配置文件是：
```
/opt/prometheus/prometheus.yml
```

## 修改步骤

### 1. 编辑配置文件

```bash
sudo vim /opt/prometheus/prometheus.yml
# 或
sudo nano /opt/prometheus/prometheus.yml
```

### 2. 添加持仓指标服务配置

在 `scrape_configs` 部分添加以下配置：

```yaml
  # 持仓指标定时计算服务（每5-10分钟计算一次持仓和交易指标）
  - job_name: 'position-metrics-scheduler'
    static_configs:
      - targets: ['127.0.0.1:9602']  # position metrics scheduler
        labels:
          service: 'position-metrics'
          component: 'scheduler'
    scrape_interval: 30s  # 每30秒抓取一次（因为服务每5-10分钟计算一次）
    metrics_path: '/metrics'
```

### 3. 完整的配置文件示例

修改后的完整配置应该是：

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  # 订阅服务自动启动的 metrics（实时 WebSocket 数据：订单、成交、账户更新）
  - job_name: 'cextools-subscribe'
    static_configs:
      - targets: ['127.0.0.1:9601']

  # 监控服务自动启动的 metrics（定时 REST API 数据：余额、仓位快照）
  - job_name: 'cextools-watch'
    static_configs:
      - targets: ['127.0.0.1:9500']

  # 可选：独立 exporter（数据库历史快照数据）
  - job_name: 'cextools-exporter'
    static_configs:
      - targets: ['127.0.0.1:9100']

  # 持仓指标定时计算服务（每5-10分钟计算一次持仓和交易指标）
  - job_name: 'position-metrics-scheduler'
    static_configs:
      - targets: ['127.0.0.1:9602']  # position metrics scheduler
        labels:
          service: 'position-metrics'
          component: 'scheduler'
    scrape_interval: 30s  # 每30秒抓取一次（因为服务每5-10分钟计算一次）
    metrics_path: '/metrics'
```

### 4. 验证配置文件语法

```bash
# 如果安装了 promtool
/opt/prometheus/promtool check config /opt/prometheus/prometheus.yml
```

### 5. 重新加载配置

有两种方式：

#### 方式 1：通过 HTTP API 重新加载（推荐，无需重启）

```bash
curl -X POST http://localhost:9090/-/reload
```

#### 方式 2：重启 Prometheus 服务

```bash
pm2 restart prometheus
```

### 6. 验证配置是否生效

1. 访问 Prometheus UI：http://localhost:9090
2. 进入 **Status** > **Configuration**，查看配置是否已更新
3. 进入 **Status** > **Targets**，确认 `position-metrics-scheduler` 状态为 **UP**
4. 在 **Graph** 页面测试查询：
   ```promql
   position_daily_pnl
   ```

## 注意事项

1. **权限**：可能需要 sudo 权限来编辑 `/opt/prometheus/prometheus.yml`
2. **YAML 语法**：注意缩进，使用空格不要用 Tab
3. **备份**：修改前建议备份原文件：
   ```bash
   sudo cp /opt/prometheus/prometheus.yml /opt/prometheus/prometheus.yml.backup
   ```
4. **端口确认**：确保 `127.0.0.1:9602` 端口上的服务正在运行：
   ```bash
   curl http://127.0.0.1:9602/metrics
   ```

## 快速修改命令

如果你想快速添加配置，可以使用以下命令：

```bash
# 备份原配置
sudo cp /opt/prometheus/prometheus.yml /opt/prometheus/prometheus.yml.backup

# 添加新配置（追加到文件末尾）
sudo tee -a /opt/prometheus/prometheus.yml > /dev/null << 'EOF'

  # 持仓指标定时计算服务（每5-10分钟计算一次持仓和交易指标）
  - job_name: 'position-metrics-scheduler'
    static_configs:
      - targets: ['127.0.0.1:9602']  # position metrics scheduler
        labels:
          service: 'position-metrics'
          component: 'scheduler'
    scrape_interval: 30s  # 每30秒抓取一次（因为服务每5-10分钟计算一次）
    metrics_path: '/metrics'
EOF

# 重新加载配置
curl -X POST http://localhost:9090/-/reload
```

## 验证服务是否运行

在修改 Prometheus 配置之前，确保持仓指标服务正在运行：

```bash
# 检查服务是否运行
ps aux | grep start_position_metrics_scheduler

# 测试 metrics 端点
curl http://127.0.0.1:9602/metrics
```

如果 metrics 端点返回数据，说明服务正常运行，可以配置 Prometheus 抓取。

