# CLI 命令参考

## 安装

```bash
git clone https://github.com/realm520/quant.git
cd quant
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"
```

## WebSocket 订阅

### 单账号订阅

```bash
# 所有频道
cextools subscribe user-stream -x xt --account-id account_001

# 指定频道
cextools subscribe user-stream -x xt --account-id account_001 -c account,position,order,trade

# JSON 输出
cextools subscribe user-stream -x xt --account-id account_001 --output json
```

### 多账号订阅

```bash
# 默认配置文件
cextools subscribe multi-account

# 指定配置 + 创建表
cextools subscribe multi-account --config config/accounts.json --create-tables

# 只启动指定账号
cextools subscribe multi-account --accounts account_001,account_002
```

## 账户查询

```bash
# 余额（永续）
cextools account balance -x xt -e perp

# 余额（现货）
cextools account balance -x xt -e spot

# 持仓
cextools account positions -x xt -e perp

# 当前挂单
cextools account orders -x xt -e perp
```

## 定时监控

```bash
# 定时查余额（每 5 分钟）
cextools account watch-balance -x xt -e perp --account-id account_001 --interval 5

# 定时查持仓（每 1 分钟）
cextools account watch-positions -x xt -e perp --account-id account_001 --interval 1

# 从配置文件监控所有账号
cextools account watch-account --config config/accounts.json --all-accounts
```

## 市场数据

```bash
# 实时价格
cextools market ticker -s BTC/USDT

# 订单簿
cextools market depth -s BTC/USDT --limit 50

# K 线
cextools market klines -e spot -s BTC/USDT --interval 1h --limit 48
```

## 订单操作

```bash
# 下单（永续限价）
cextools order place -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side long

# 撤单
cextools order cancel-all -e spot --symbol BTC/USDT
```

## 杠杆设置

```bash
# 设置杠杆
cextools leverage set -e perp -s BTC/USDT --leverage 10

# 查看杠杆
cextools leverage list -e perp
```

## 数据清理

```bash
# 立即清理
uv run cleanup-old-data cleanup

# 模拟运行
uv run cleanup-old-data cleanup --dry-run

# 定时清理（每天凌晨 2 点）
uv run cleanup-old-data cleanup --schedule
```

## 环境变量

```bash
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/trading"
```

## 通用参数

| 参数 | 简写 | 说明 |
|------|------|------|
| `--account-id` | `-a` | 账号 ID |
| `--interval` | `-i` | 查询间隔（分钟） |
| `--channels` | `-c` | 订阅频道（逗号分隔） |
| `--output` | `-o` | 输出格式（table/json/none） |
| `--debug` | - | 调试模式 |
