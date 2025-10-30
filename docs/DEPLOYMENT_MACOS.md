# CEX Tools 部署指南（macOS）

本指南帮助你在 macOS 上快速部署并运行 cextools 与 tri-arb。

## 1. 系统要求
- macOS 12+（Apple Silicon 与 Intel 均可）
- Python 3.11（推荐使用 uv 进行环境管理）
- PostgreSQL 14+（用于保存 WebSocket 账户/订单/持仓数据）

## 2. 安装基础依赖
```bash
# 安装 Homebrew（如已安装可跳过）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 PostgreSQL
brew install postgresql@14
brew services start postgresql@14

# 确认 createdb/psql 可用
which createdb
which psql
```

如提示找不到 createdb/psql，请将 brew 路径加入 PATH（以下为 Apple Silicon 默认路径）：
```bash
echo 'export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

## 3. 创建数据库
```bash
createdb trading || true
```
说明：表结构会在首次运行命令时自动创建，无需执行初始化 SQL。

## 4. 获取代码与创建虚拟环境
```bash
git clone https://github.com/realm520/quant.git
cd quant

# 使用 uv 创建并激活虚拟环境
uv venv --python 3.11
source .venv/bin/activate

# 安装项目依赖
uv pip install -e .
uv pip install -r requirements-db.txt
```

## 5. 配置环境变量
将密钥放入 `.env`，或在 shell 中临时导出：
```bash
# XT（现货/永续共用）
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"

# OKX（需要 3 个）
export OKX_API_KEY="your_okx_api_key"
export OKX_API_SECRET="your_okx_api_secret"
export OKX_PASSPHRASE="your_okx_passphrase"

# Binance（可选）
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"

# 数据库（按本机用户名替换 oliver）
export DATABASE_URL="postgresql+asyncpg://oliver@localhost:5432/trading"

# 也可：
source load_env.sh   # 从 .env 读取
```

## 6. 快速启动 WebSocket 订阅
```bash
# 账户（余额）
python -m tri_arb.cli.main subscribe user-stream -x xt -c account

# 持仓
python -m tri_arb.cli.main subscribe user-stream -x xt -c position

# 订单
python -m tri_arb.cli.main subscribe user-stream -x xt -c order
```
看到 “Subscription confirmed” 后，进行划转/下单，即会有推送并入库。

## 7. 常见问题
- createdb: command not found：使用 brew 安装 PostgreSQL 并加入 PATH。
- role "postgres" does not exist：将 `DATABASE_URL` 中用户名改为本机 macOS 用户名（如 `oliver`）。
- XT listen key 403 时间漂移：偶发，由服务自动重试，稍后会成功获取。
- JSON 序列化 Decimal：项目已内置 DecimalEncoder，无需额外处理。

## 8. 日志与验证
```bash
# 查看日志
tail -f logs/tri-arb.log

# 简单验证最近入库记录（示例）
psql -d trading -c "SELECT * FROM xt_account_updates ORDER BY update_time DESC LIMIT 5;"
```

## 9. 注意事项
- 请确保 API Key 权限包含：读取、交易（如需）、期货权限（永续）。
- 不建议在系统 Python 环境中安装（PEP 668），请使用虚拟环境或 uv。
- 生产环境建议将日志轮转/持久化并定期维护数据库索引。
