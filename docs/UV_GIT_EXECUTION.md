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

### 常用子命令与完整示例

> 下述所有示例均可将 `--from` 源替换为 Tag 或 Commit 形式；执行前请先正确导出环境变量。

#### 市场数据（market）
```bash
# 实时价格（默认永续）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools market ticker -s BTC/USDT

# 现货价格
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools market ticker -e spot -s ETH/USDT

# 订单簿深度（指定深度）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools market depth -s BTC/USDT --limit 50

# K 线数据
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools market klines -e spot -s BTC/USDT --interval 1h --limit 48
```

#### 账户（account）
```bash
# 余额
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools account balance -e perp

# 持仓（永续）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools account positions -e perp

# 当前挂单（永续）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools account orders -e perp

# 定时查询余额（watch-balance）
# 每 1 分钟（默认）查询一次永续余额
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools account watch-balance -e perp

# 指定交易所/间隔/输出格式（示例：OKX 永续，每 5 分钟，JSON 输出）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools account watch-balance -x okx -e perp --interval 5 --output json
```

#### 订单（order）
```bash
# 下单（永续限价示例，注意风险）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools order place -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side long

# 撤单（示例：撤销所有现货某交易对的订单）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools order cancel-all -e spot --symbol BTC/USDT
```

#### 杠杆（leverage，仅永续）
```bash
# 设置杠杆
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools leverage set -e perp -s BTC/USDT --leverage 10

# 查看杠杆设置
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools leverage list -e perp
```

#### 输出格式
```bash
# JSON 输出
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools account balance -e spot -o json

# CSV 输出（重定向到文件）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver \
  cextools market depth -s BTC/USDT -o csv > depth.csv
```

#### 多交易所切换
```bash
# XT（默认）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver cextools market ticker -s BTC/USDT

# Binance（部分功能已实现，以占位为主）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver cextools market ticker -x binance -e spot -s BTC/USDT

# OKX（部分功能）
uvx --from git+https://github.com/realm520/quant.git@feat/oliver cextools account balance -x okx -e perp
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

> 说明：
> - 订阅确认后（Subscription confirmed），进行划转/下单即可收到推送；
> - 连接断开后会自动重连，并执行固定 1 小时的断线回补（订单/成交），账户/持仓则同步最新状态；
> - 如果仅需某一频道（如仅订单），可只传 `-c order`。

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

## 调试与最佳实践
- 使用 `--debug` 查看更详细日志（例如：`cextools account balance -e perp --debug`）。
- 建议将密钥放入 `.env` 并用 `source load_env.sh` 统一加载，避免泄露；不要将密钥提交到仓库。
- 服务器/本机时间保持与 NTP 同步，减少签名/时间漂移相关报错。
- 生产环境建议启用日志轮转与数据库备份，定期维护索引。

## 何时选择 uvx / 本地安装
- 临时使用/快速验证：优先使用 `uvx --from git+...`，无需安装即可运行。
- 长期使用/稳定环境：使用 `uv venv` + `uv pip install git+...` 安装到虚拟环境。
