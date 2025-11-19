# Grafana 可视化快速入门

## 🚀 快速开始（3 步）

### 1. 确保 metrics 服务正在运行

```bash
# 在一个终端中运行监控命令
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/trading
export PROM_METRICS_PORT=9600
source .venv/bin/activate
cextools account watch-balance -x xt -e perp --config config/accounts.json --all-accounts
```

验证 metrics 是否可访问：
```bash
curl http://127.0.0.1:9600/metrics | head -20
```

### 2. 启动 Prometheus 和 Grafana

```bash
# 使用便捷脚本
./scripts/start-monitoring.sh

# 或手动启动
docker-compose -f docker-compose.monitoring.yml up -d
```

### 3. 访问 Grafana 并导入仪表板

1. 打开浏览器访问: http://localhost:3000
2. 登录（默认用户名/密码: `admin` / `admin`）
3. 配置数据源:
   - 进入 **Configuration** > **Data Sources**
   - 点击 **Add data source** > 选择 **Prometheus**
   - URL 设置为: `http://prometheus:9090`（如果在 Docker 中）或 `http://localhost:9090`
   - 点击 **Save & Test**
4. 导入仪表板:
   - 进入 **Dashboards** > **Import**
   - 点击 **Upload JSON file**
   - 选择 `grafana/dashboards/exchange-monitor.json`
   - 选择 Prometheus 数据源
   - 点击 **Import**

## 📊 仪表板功能

导入的仪表板包含以下面板：

1. **可用余额趋势** - 实时显示各账户的可用余额变化
2. **总余额趋势** - 显示各账户的总余额（可用+冻结）
3. **账户余额总览** - 统计卡片显示各账户当前余额
4. **冻结余额趋势** - 显示冻结资金的变化
5. **查询成功率** - 监控查询 API 的成功率
6. **查询失败次数** - 显示查询失败的次数

## 🔍 常用查询示例

在 Grafana 的 Explore 页面或面板编辑器中可以使用以下 PromQL 查询：

### 查看所有账户的 USDT 总余额
```promql
sum(exchange_balance_total{asset="USDT"}) by (account_id, exchange)
```

### 查看特定账户的余额
```promql
exchange_balance_total{account_id="account_002", asset="USDT"}
```

### 查看各交易所的总资产
```promql
sum(exchange_balance_total) by (exchange, asset)
```

### 查看查询错误率
```promql
sum(rate(exchange_balance_query_total{status="failure"}[5m])) / sum(rate(exchange_balance_query_total[5m]))
```

## 🛑 停止服务

```bash
docker-compose -f docker-compose.monitoring.yml down
```

## 📝 更多信息

详细配置说明请参考: `docs/grafana-setup.md`

