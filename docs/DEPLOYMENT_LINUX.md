# CEX Tools 部署指南（Linux）

本指南帮助你在常见 Linux 发行版（Ubuntu/Debian/CentOS 等）上部署并运行 cextools 与 tri-arb。

## 1. 系统要求
- Ubuntu 20.04+/Debian 11+/CentOS 8+/Rocky/AlmaLinux
- Python 3.11（推荐使用 uv 或 venv）
- PostgreSQL 14+

## 2. 安装基础依赖
```bash
# Debian/Ubuntu
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-distutils postgresql postgresql-client

# 可选：安装 uv（推荐）
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l
```

PEP 668 外部托管环境提示（externally-managed-environment）：
- 避免系统 Python 直接 pip 安装，使用 `python -m venv` 或 `uv venv`。

### 2.1 Amazon Linux 2023.9.20251110 专用步骤
> 该版本基于 Fedora/DNF 生态，默认提供 Python 3.11 与 PostgreSQL 15。以下命令需在 root 或具备 sudo 权限的账户运行。

```bash
# 更新基础系统
sudo dnf update -y

# 安装 Python/编译链/数据库客户端
sudo dnf install -y python3.11 python3.11-devel python3.11-pip \
    gcc gcc-c++ make openssl-devel git \
    postgresql15 postgresql15-server postgresql15-devel

# 初始化并启动 PostgreSQL（若尚未配置）
sudo /usr/pgsql-15/bin/postgresql-15-setup initdb || true
sudo systemctl enable --now postgresql-15

# Amazon Linux 2023 默认未自带 uv，可选安装
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l

# 使用 uvx 直接运行（可选）
uvx --from git+https://github.com/realm520/quant.git cextools --help
```

常见问题排查：
- `python` 指向 3.9：使用 `python3.11` 或通过 `alternatives` 切换。
- PostgreSQL 无法连接：确认 `pg_hba.conf` 允许本地用户、端口 5432 未被防火墙阻拦。
- SELinux 拒绝访问：可暂时 `sudo setenforce 0` 验证，生产建议写入策略。
- `uvx` 缓存旧版本：执行 `uv cache purge --all` 后重新运行。

## 3. 创建数据库
```bash
sudo -u postgres createdb trading || true
# 或使用本机普通用户如已配置
# createdb trading || true
```

说明：表结构会在首次运行命令时自动创建，无需执行初始化 SQL。

## 4. 获取代码与创建虚拟环境
```bash
git clone https://github.com/realm520/quant.git
cd quant

# 使用 uv（推荐）
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .
uv pip install -r requirements-db.txt

# 或使用 venv
# python3.11 -m venv .venv
# source .venv/bin/activate
# pip install -e .
# pip install -r requirements-db.txt
```

## 5. 配置环境变量
```bash
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"

export OKX_API_KEY="your_okx_api_key"
export OKX_API_SECRET="your_okx_api_secret"
export OKX_PASSPHRASE="your_okx_passphrase"

export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"

# 根据数据库实际用户/主机调整
export DATABASE_URL="postgresql+asyncpg://$USER@localhost:5432/trading"

# 或从 .env 读取
source load_env.sh
```

## 6. 常用部署命令（全账号批量运行）

以下示例默认在仓库根目录执行，且依赖已安装（本地虚拟环境或 `uv run` 环境）。如果是远程执行、仅需一次性运行，可把 `python -m ...` 换成 `uvx --from git+https://github.com/realm520/quant.git ...`。

```bash
# 统一订阅所有启用账号（自动识别交易所）
python -m tri_arb.cli.main subscribe multi-account --config config/accounts.json

# 定时账户全量巡检（余额/权益等）
python -m tri_arb.cli.main account watch-account --config config/accounts.json --all-accounts

# 定时余额巡检（合约/现货自动按配置路由）
python -m tri_arb.cli.main account watch-balance --config config/accounts.json --all-accounts -e perp

# 定时持仓巡检（多交易所混合）
python -m tri_arb.cli.main account watch-positions --config config/accounts.json --all-accounts

# 需要以系统服务方式运行，可在 systemd 或 tmux 中引用上述命令

# 直接从 Git 拉取运行（不进入仓库）
uvx --from git+https://github.com/realm520/quant.git@feat/xt_dev cextools subscribe multi-account --config config/accounts.json
uvx --from git+https://github.com/realm520/quant.git cextools account watch-account --config config/accounts.json --all-accounts
```

## 7. Prometheus + Grafana 监控

### 7.1 Metrics 服务器（自动启动）

**重要**：以下命令运行时会**自动启动** Prometheus metrics 服务器，无需单独运行 exporter：

- **订阅服务**（`subscribe multi-account` 或 `subscribe user-stream`）：自动启动 metrics 服务器在端口 **9601**
- **监控服务**（`watch-all`、`watch-account`、`watch-balance`、`watch-positions`）：自动启动 metrics 服务器在端口 **9500**（默认）

Metrics 端点：
- 订阅服务：`http://<host>:9601/metrics`（实时 WebSocket 数据：订单、成交、账户更新）
- 监控服务：`http://<host>:9500/metrics`（定时 REST API 数据：余额、仓位快照）

如果需要基于数据库快照的独立 exporter（从数据库读取历史数据），可单独运行：

```bash
# 独立 exporter（从数据库读取，端口 9100）
python -m tri_arb.cli.main metrics exporter --config config/accounts.json --listen 0.0.0.0 --port 9100
```

### 7.2 安装并启动 Prometheus

```bash
sudo useradd --no-create-home --shell /sbin/nologin prometheus || true
cd /opt
sudo curl -LO https://github.com/prometheus/prometheus/releases/download/v2.53.0/prometheus-2.53.0.linux-amd64.tar.gz
sudo tar -xzf prometheus-2.53.0.linux-amd64.tar.gz
sudo mv prometheus-2.53.0.linux-amd64 prometheus
sudo chown -R prometheus:prometheus /opt/prometheus
sudo tee /opt/prometheus/prometheus.yml <<'EOF'
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
EOF
sudo tee /etc/systemd/system/prometheus.service <<'EOF'
[Unit]
Description=Prometheus
After=network-online.target
[Service]
User=prometheus
Group=prometheus
ExecStart=/opt/prometheus/prometheus --config.file=/opt/prometheus/prometheus.yml --storage.tsdb.path=/opt/prometheus/data
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now prometheus
```

访问 `http://<服务器IP>:9090/targets`，确认所有 job（`cextools-subscribe`、`cextools-watch`、`cextools-exporter`）状态为 `UP`。

### 7.3 安装并配置 Grafana

```bash
sudo tee /etc/yum.repos.d/grafana.repo <<'EOF'
[grafana]
name=Grafana
baseurl=https://rpm.grafana.com
repo_gpgcheck=1
enabled=1
gpgcheck=1
gpgkey=https://rpm.grafana.com/gpg.key
EOF
sudo dnf install -y grafana
sudo systemctl enable --now grafana-server
```

### 7.4 访问 Grafana 面板

1. **打开浏览器**，访问 `http://<服务器IP>:3000`
   - 如果是在本地服务器，访问 `http://localhost:3000`
   - 如果是远程服务器，访问 `http://<服务器公网IP>:3000`（确保防火墙开放 3000 端口）

2. **首次登录**：
   - 用户名：`admin`
   - 密码：`admin`
   - 首次登录会要求修改密码

3. **配置 Prometheus 数据源**：
   - 点击左侧菜单 **Connections**（或 **Configuration → Data sources**）
   - 点击 **Add data source**
   - 选择 **Prometheus**
   - URL 填写：`http://127.0.0.1:9090`（如果 Grafana 和 Prometheus 在同一台服务器）
   - 点击 **Save & Test**，确认显示 "Data source is working"

4. **查看指标**：
   - **方式一**：点击左侧菜单 **Explore**，在查询框输入指标名称，例如：
     - `exchange_balance_total`（总余额）
     - `exchange_position_quantity`（持仓数量）
     - `exchange_order_count`（活跃订单数）
   - **方式二**：导入或创建 Dashboard（面板），可视化展示多个指标

### 7.5 验证数据流

在终端运行监控命令后，可以通过以下方式验证数据是否正常：

```bash
# 检查 metrics 端点是否可访问（订阅服务，端口 9601）
# 查看所有指标（包括自定义的交易指标）
curl http://localhost:9601/metrics

# 只查看自定义的交易指标（过滤掉 Python 默认指标）
curl http://localhost:9601/metrics | grep -E "^exchange_|^cex_"

# 检查 metrics 端点是否可访问（监控服务，端口 9500）
curl http://localhost:9500/metrics | grep -E "^exchange_|^cex_"

# 检查 Prometheus 是否成功抓取
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

**说明**：
- 如果看到 `python_gc_*`、`process_*` 等指标，说明 metrics 服务器正常运行
- 如果看到 `exchange_balance_total`、`exchange_order_count`、`exchange_position_quantity` 等指标，说明有交易数据在更新
- 如果没有自定义指标，可能是：
  1. 订阅服务刚启动，还没有接收到数据（等待几秒后重试）
  2. 账号没有活跃订单或持仓（这是正常的，指标会在有数据时出现）


## 6. 快速启动 WebSocket 订阅
```bash
python -m tri_arb.cli.main subscribe user-stream -x xt -c account
python -m tri_arb.cli.main subscribe user-stream -x xt -c position
python -m tri_arb.cli.main subscribe user-stream -x xt -c order
```

## 7. 作为服务运行（可选）
示例 systemd 单元：`scripts/systemd/tri-arb.service`
```bash
sudo cp scripts/systemd/tri-arb.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tri-arb
journalctl -u tri-arb -f
```
请根据你的部署目录与环境变量路径调整单元文件。

## 8. 常见问题
- externally-managed-environment：使用虚拟环境或 uv，避免系统 Python pip 安装。
- 连接数据库失败：确认 `DATABASE_URL` 用户/主机/端口正确，数据库存在且可访问。
- XT listen key 403：偶发时间漂移，程序会自动重试。

## 9. 日志与验证
```bash
# 查看日志
tail -f logs/tri-arb.log

# 验证最近入库
psql -d trading -c "SELECT * FROM xt_account_updates ORDER BY update_time DESC LIMIT 5;"
```

## 10. 注意事项
- API Key 请开启所需权限：读取、交易（如需）、期货权限（永续）。
- 服务器时间建议与 NTP 同步，减少签名与时间相关错误。
- 生产环境建议开启日志轮转与数据库备份。
