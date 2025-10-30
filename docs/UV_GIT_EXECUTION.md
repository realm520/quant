# 使用 uv + Git 路径直接执行（无需本地安装）

本文档演示如何通过 uv/uvx 直接从 Git 仓库运行 cextools/tri-arb，而不需要本地克隆与安装。

## 前置条件
- 已安装 uv（推荐）
```bash
# 安装 uv（Linux/macOS）
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l

# 验证
uv --version
uvx --version
```
- 已准备好必要的环境变量（API Key、数据库连接等）。

## 快速开始：直接运行 CLI
你可以指定分支、Tag 或 Commit，按需选择其一：
- 分支：`@feat/oliver`
- Tag：`@v1.0.0`
- Commit：`@<commit-sha>`

### 1) 运行 cextools（无需安装）
```bash
# 查看帮助
uvx --from git+https://github.com/realm520/quant.git@feat/oliver cextools --help

# 账户余额（XT 永续）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools account balance -x xt -e perp

# 市场价格（现货）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools market ticker -e spot -s BTC/USDT
```

### 2) 运行 tri-arb WebSocket 订阅
```bash
# XT 账户（余额）订阅
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  python -m tri_arb.cli.main subscribe user-stream -x xt -c account

# XT 持仓订阅
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  python -m tri_arb.cli.main subscribe user-stream -x xt -c position

# XT 订单订阅
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  python -m tri_arb.cli.main subscribe user-stream -x xt -c order
```

## 环境变量与数据库
在执行前，请在当前 shell 导出密钥与数据库连接（或使用你的加载脚本）：
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

# 数据库（按实际用户/主机修改）
export DATABASE_URL="postgresql+asyncpg://oliver@localhost:5432/trading"

# 若仓库根目录已有 .env，可：
# source load_env.sh
```

确保数据库已创建并初始化（首次使用）：
```bash
createdb trading || true
psql -d trading -f scripts/init_database.sql || true
```

## 选择版本与缓存
- 推荐为生产/验证指定**稳定 Tag 或 Commit**，例如：
```bash
uvx --from git+https://github.com/realm520/quant.git@v1.0.0 cextools --help
uvx --from git+https://github.com/realm520/quant.git@<commit-sha> cextools --help
```
- uv 会缓存构建结果；如需强制刷新，可添加 `--no-cache`：
```bash
uvx --no-cache --from git+https://github.com/realm520/quant.git@feat/oliver cextools --help
```

## 常见问题
- externally-managed-environment：使用 uv/uvx 时不会触发系统 Python 的 PEP 668 限制。
- 认证失败（401/403）：检查环境变量是否已导出，API Key 权限是否正确；OKX 需 3 个参数。
- XT 获取 listen key 出现 403：为接口时间漂移所致，程序会自动重试，一般稍后成功。
- 数据入库失败：确认 `DATABASE_URL` 用户名/主机/端口正确，数据库存在且执行了初始化 SQL。

## 何时选择 uvx / 本地安装
- 临时使用/快速验证：优先使用 `uvx --from git+...`，无需安装即可运行。
- 长期使用/稳定环境：使用 `uv venv` + `uv pip install git+...` 安装到虚拟环境。
