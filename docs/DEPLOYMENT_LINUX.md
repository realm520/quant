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

## 3. 创建数据库
```bash
sudo -u postgres createdb trading || true
# 或使用本机普通用户如已配置
# createdb trading || true

psql -d trading -f scripts/init_database.sql || true
```

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
