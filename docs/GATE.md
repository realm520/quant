# Gate.io 使用指南（合并版）

本指南整合了 Gate.io 的快速开始、API 配置、REST 查询、WebSocket 订阅、定时查询与常见问题排查，便于快速上手与生产使用。

## 快速开始

环境变量（推荐放入 shell profile）

```bash
export GATE_API_KEY="your_api_key"
export GATE_API_SECRET="your_api_secret"
```

安装依赖并查看命令

```bash
pip install -r requirements.txt
python -m tri_arb.cli.main --help
```

## 账户相关（REST）

- 查询余额（perp）：
```bash
python -m tri_arb.cli.main account balance -x gate -e perp
```
- 查询持仓（perp）：
```bash
python -m tri_arb.cli.main account positions -x gate -e perp
```
- 查询挂单（perp）：
```bash
python -m tri_arb.cli.main account orders -x gate -e perp
```
- 仅筛选某合约（示例 ETH/USDT）：
```bash
python -m tri_arb.cli.main account positions -x gate -e perp -s ETH/USDT
python -m tri_arb.cli.main account orders    -x gate -e perp -s ETH/USDT
```

输出格式：`-o json` 支持 JSON 输出；部分单次查询命令支持 `--output csv`。

## 定时查询（REST）

- 定时查询余额（每 2 分钟）：
```bash
python -m tri_arb.cli.main account watch-balance   -x gate -e perp -i 2
```
- 定时查询持仓（每 2 分钟）：
```bash
python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 2
```
- 定时查询挂单（每 1 分钟）：
```bash
python -m tri_arb.cli.main account watch-orders    -x gate -e perp -i 1
```
- 仅监控某合约：在以上命令追加 `-s BTC/USDT`。

建议间隔：余额 5-10 分钟，持仓 1-3 分钟，挂单 1-2 分钟。

## WebSocket 订阅（私有）

统一命令（选择频道：account/position/order，可多选用逗号分隔）

```bash
python -m tri_arb.cli.main subscribe user-stream -x gate -c account,position,order -o table
```

要点：
- 频道 payload 规范已内置：
  - `futures.balances` 使用 `payload=["USDT"]`
  - `futures.positions` 与 `futures.orders` 使用 `payload=[user_id, "!all"]`
- `user_id` 将在启动时通过 REST 自动获取（`/api/v4/futures/usdt/accounts`）。
- 为避免快照类推送导致重复入库，已实现变更检测逻辑。

## 终端展示

- 余额：使用实际字段 `balance`、`change`、`type` 显示。
- 持仓：无 `mark_price/unrealised_pnl`，展示 `mode/leverage/leverage_max/cross_leverage_limit/entry_price/realised_pnl/last_close_pnl/liq_price`；
  - 杠杆在全仓模式显示为：`全仓{cross_leverage_limit}x`（如 `全仓11x`）。
  - 强平价使用 `liq_price` 字段显示。
- 订单：优先显示 `fill_price`（成交价），无则显示限价或“市价”；附带 `tif/fee/role`。

## 数据库存储

已包含 Gate 专用数据表与视图，执行统一初始化脚本：

```bash
psql -U postgres -d trading -f scripts/init_database.sql
```

表：`gate_account_balances`、`gate_positions`、`gate_orders`、`gate_trades`

## 常见问题排查（精简）

- REST 401 Signature mismatch：
  - 签名需包含完整路径 `/api/v4/...`，且 `base_url` 不应重复 `/api/v4`。
- WebSocket 订阅错误：
  - `request payload does not follow json schema`：确保带 `payload`
  - `unknown contract usdt`：`balances` 使用大写 `USDT`
  - `need 1 or 2 param` / `need market param`：`positions/orders` 需 `[user_id, "!all"]`
- 账户未显示：
  - Gate 余额推送字段为 `balance/change/type`，与其他交易所不同。
- 入库类型错误：
  - `user_id` 为 BIGINT，注意 `str -> int` 转换。

更多细节：
- 订阅排错详解：`docs/GATE_WEBSOCKET_TROUBLESHOOTING.md`
- 字段映射与显示修正：`docs/GATE_FIELD_MAPPING.md`、`docs/GATE_ORDER_DISPLAY_FIX.md`、`docs/GATE_POSITION_DISPLAY_FIX.md`
- 修复汇总：`GATE_FIX_SUMMARY.md`

## 一键运行示例

```bash
# 后台监控（建议用 nohup 或 screen/tmux）
nohup python -m tri_arb.cli.main account watch-balance   -x gate -e perp -i 5 > gate-balance.log 2>&1 &
nohup python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 2 > gate-positions.log 2>&1 &
nohup python -m tri_arb.cli.main account watch-orders    -x gate -e perp -i 1 > gate-orders.log 2>&1 &

# WebSocket 实时订阅
nohup python -m tri_arb.cli.main subscribe user-stream -x gate -c account,position,order -o table > gate-ws.log 2>&1 &
```

## 参考

- 官方文档：https://www.gate.io/docs/developers/apiv4/zh_CN/
- 使用指南（快速参考）：`QUICK_REFERENCE.md`
