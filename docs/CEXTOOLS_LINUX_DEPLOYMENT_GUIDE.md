# CEXTools Linux 服务器部署与运行指南

适用于全新 Linux 服务器（如 Ubuntu 22.04+/24.04+）的一站式部署文档，覆盖依赖安装、数据库初始化、运行验证与生产化运维（systemd）。

## 1. 前置条件

- 已有一台可联网的 Linux 服务器（x86_64）
- 用户具备 `sudo` 权限
- 推荐使用 Python 3.11+

### 1.1 系统依赖

```bash
sudo apt update
sudo apt install -y build-essential curl git python3 python3-venv python3-pip \
  libpq-dev postgresql postgresql-contrib
```

### 1.2 安装 uv（推荐的包管理工具）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# 重新登录或加载环境后可用 `uv --version` 验证
```

## 2. 获取代码并创建虚拟环境

如果你已经在服务器上放置了代码，请跳到 3 节。以下为从 Git 获取的示例：

```bash
cd /opt
sudo git clone https://github.com/realm520/quant.git
sudo chown -R $USER:$USER /opt/quant
cd /opt/quant

# 使用 uv 创建并激活虚拟环境
uv venv --python 3.11
source .venv/bin/activate

# 安装开发版（包含 CLI 与依赖）
uv pip install -e ".[dev]"
```

> 已存在工作目录的场景：当前仓库路径为 `/home/ubuntu/quant`，则进入该目录并按上面从 `uv venv` 开始执行即可。

## 3. 数据库初始化（WebSocket/数据持久化必需）

如果仅使用公开 REST 查询且不落库，可跳过数据库步骤。若需账户/订单/成交等实时落库，请按下述步骤：

### 3.1 启动与信任配置（开发/单机环境）

```bash
# 确保 PostgreSQL 已安装（1.1 已安装）

# 配置本地免密（开发/单机环境）
sudo bash /home/ubuntu/quant/scripts/configure_postgres_trust.sh

# 创建数据库
sudo -u postgres createdb trading || true

# 初始化表结构
psql -U postgres -d trading -f /home/ubuntu/quant/scripts/init_database.sql

# 设置连接串（当前会话）
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
```

> 生产环境请使用强口令账号、限制网络访问、不要使用 trust 模式。可自建专用用户与 `pg_hba.conf` 访问控制。

## 4. 配置交易所凭证

根据需要配置所用交易所的 API Key。以下示例直接导出到当前会话，生产建议写入服务用户环境文件或 systemd 环境：

```bash
# Binance
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# OKX
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_api_secret"
export OKX_PASSPHRASE="your_passphrase"

# Gate.io（如使用）
export GATE_API_KEY="your_api_key"
export GATE_API_SECRET="your_api_secret"

# XT（如使用）
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
```

如使用 YAML 配置，可参考 `/home/ubuntu/quant/config/config.example.yaml`，复制并调整：

```bash
cp /home/ubuntu/quant/config/config.example.yaml /home/ubuntu/quant/config/config.yaml
```

## 5. 安装依赖并验证 CLI

```bash
cd /home/ubuntu/quant
source .venv/bin/activate  # 若尚未激活

# 安装数据库/订阅相关依赖（开启 subscribe 与落库所必需）
uv pip install -r requirements-db.txt

# 验证 CLI 可用
cextools --help
cextools version || cextools --version
```

若提示找不到命令，使用 `which cextools` 检查 PATH，并确认当前虚拟环境已激活。

> 提示：若执行订阅时报错 `No module named 'sqlalchemy'` 或命令显示 `No such command 'subscribe'`，说明未安装数据库/订阅依赖。请在已激活的虚拟环境内执行：
>
> ```bash
> uv pip install -r /home/ubuntu/quant/requirements-db.txt
> ```
> 
> 然后再次运行：
> 
> ```bash
> cextools --help    # 确认已出现 subscribe 子命令
> ```

## 6. 快速功能验证

### 6.1 REST 基本验证

```bash
# 余额（示例：Binance 永续）
cextools account balance -x binance -e perp

# 行情（公开接口，无需密钥）
cextools market ticker -x xt -e spot -s BTC/USDT
```

### 6.2 WebSocket + 落库验证（推荐）

```bash
# 确保已设置 DATABASE_URL（见 3.1）
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"

# 首次运行请创建数据表
cextools subscribe user-stream -x binance --create-tables --output table

# 后台运行示例
nohup cextools subscribe user-stream -x okx --output none > okx_ws.log 2>&1 &

# 验证数据库中是否有数据或连接状态
psql -U postgres -d trading -c "SELECT * FROM connection_status ORDER BY updated_at DESC LIMIT 5;"
```

更多命令与说明，参考：
- `/home/ubuntu/quant/docs/CEXTOOLS_COMPLETE_GUIDE.md`
- `/home/ubuntu/quant/docs/cextools-usage.md`

## 7. 生产化部署（systemd 可选）

项目包含一键部署脚本与 systemd 服务单元，适合将可执行文件安装至系统路径并以服务方式运行。

### 7.1 构建与部署

```bash
cd /home/ubuntu/quant
sudo bash scripts/deploy.sh
```

该脚本会：
- 构建二进制到 `dist/tri-arb`
- 安装到 `/opt/tri-arb`（含 `bin/config/data/logs`）
- 创建系统用户 `tri-arb`
- 安装并注册 systemd 服务 `tri-arb.service`
- 创建可执行软链 `/usr/local/bin/tri-arb`

> 注意：`deploy.sh` 针对可执行 `tri-arb`。若需以 `cextools` 的命令形态运行，可直接使用虚拟环境内的 `cextools`，或在 systemd 中执行 venv 下的命令（见 7.2 自定义）。

### 7.2 启动与日志

```bash
# 开机自启
sudo systemctl enable tri-arb

# 启动/状态/日志
sudo systemctl start tri-arb
sudo systemctl status tri-arb
sudo journalctl -u tri-arb -f
```

如需为 `cextools` 专门创建服务，可参考 `scripts/systemd/tri-arb.service` 自定义一个 `cextools.service`：

```ini
[Service]
Environment=DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/trading
Environment=BINANCE_API_KEY=...
Environment=BINANCE_API_SECRET=...
ExecStart=/home/ubuntu/quant/.venv/bin/cextools subscribe user-stream -x binance --output none
WorkingDirectory=/home/ubuntu/quant
User=ubuntu
Restart=always
```

将文件放置到 `/etc/systemd/system/cextools.service` 后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable cextools
sudo systemctl start cextools
```

## 8. 常见排错

- API 认证失败（401/60032 等）：确认环境变量是否正确、是否有读/交易权限，不要开启提币权限。
- 数据库连接失败：确认 `DATABASE_URL` 正确、PostgreSQL 服务已启动、`psql -U postgres -d trading -c "SELECT 1;"` 可用。
- 报错 `relation "connection_status" does not exist`：说明还未创建表。执行任一方式：
  - 方式A：`cextools subscribe user-stream -x binance --create-tables`
  - 方式B：`uv run python /home/ubuntu/quant/scripts/migrate_add_connection_status.py`
- 命令找不到：确认虚拟环境是否激活（`source .venv/bin/activate`），或使用绝对路径执行 `/home/ubuntu/quant/.venv/bin/cextools`。
- 权限问题：systemd 下需要为服务用户配置环境变量与数据目录权限。

## 9. 安全最佳实践

- 使用最小权限 API Key，仅开启读取/交易权限，禁用提币。
- 生产环境为数据库设置强口令与访问白名单，不使用 trust 模式。
- 将密钥放入受限的环境文件或系统密钥管理（而非明文脚本）。
- 定期轮换 API Key，限制可用 IP（若交易所支持）。

## 10. 参考文档

- `/home/ubuntu/quant/docs/CEXTOOLS_COMPLETE_GUIDE.md`
- `/home/ubuntu/quant/docs/CEXTOOLS_API_CONFIGURATION_GUIDE.md`
- `/home/ubuntu/quant/docs/WEBSOCKET_COMPLETE_GUIDE.md`
- `/home/ubuntu/quant/docs/cextools-usage.md`
- `/home/ubuntu/quant/README.md`

---

完成以上步骤后，你即可在新服务器上稳定运行 CEXTools，并可按需扩展为 systemd 持续运行与监控。祝部署顺利！


