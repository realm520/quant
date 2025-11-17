# 多交易所支持文档

## 概述

`cextools` 现在支持在同一个配置文件中配置多个不同交易所的账号，并可以同时监控它们。支持的交易所包括：

- **XT** (`xt`) - 完整支持，包括 `watch-balance / watch-account / watch-positions` 以及账号特定表
- **Binance** (`binance`) - 支持 `watch-balance` 与 `watch-account`，现货/合约余额及合约仓位会写入 `rest_balances` / `rest_positions`
- **OKX** (`okx`) - 支持 `watch-balance`（仅余额监控）
- **Gate.io** (`gate`) - 支持 `watch-balance`（仅余额监控）

## 配置文件格式

在 `accounts.json` 配置文件中，每个账号可以指定不同的交易所：

```json
{
  "global_settings": {
    "database_url": "postgresql+asyncpg://postgres@localhost:5432/trading"
  },
  "accounts": {
    "account_001": {
      "name": "XT主账号",
      "exchange": "xt",
      "api_key": "your_xt_api_key",
      "api_secret": "your_xt_api_secret",
      "enabled": true,
      "channels": ["account", "position"]
    },
    "account_002": {
      "name": "Binance账号",
      "exchange": "binance",
      "api_key": "your_binance_api_key",
      "api_secret": "your_binance_api_secret",
      "enabled": true,
      "channels": ["account", "position"]
    },
    "account_003": {
      "name": "OKX账号",
      "exchange": "okx",
      "api_key": "your_okx_api_key",
      "api_secret": "your_okx_api_secret",
      "passphrase": "your_okx_passphrase",
      "enabled": true,
      "channels": ["account", "position"]
    },
    "account_004": {
      "name": "Gate账号",
      "exchange": "gate",
      "api_key": "your_gate_api_key",
      "api_secret": "your_gate_api_secret",
      "enabled": true,
      "channels": ["account", "position"]
    }
  }
}
```

## 使用方法

### 监控所有启用的账号（多交易所）

```bash
# 监控所有账号的永续合约余额
cextools account watch-balance -x xt -e perp --config config/accounts.json --all-accounts

# 监控所有账号的现货余额
cextools account watch-balance -x xt -e spot --config config/accounts.json --all-accounts
```

**注意**：`-x` 参数在多账号模式下会被忽略，系统会根据每个账号配置中的 `exchange` 字段自动选择对应的交易所。

### 监控特定账号

```bash
# 监控特定账号（可以是不同交易所）
cextools account watch-balance -x xt -e perp --config config/accounts.json --account-id account_001
```

## 功能特性

### XT 交易所

- ✅ 完整支持账号特定表（每个账号有独立的数据库表）
- ✅ 支持余额监控和保存到数据库
- ✅ 支持仓位监控（`watch-positions`）
- ✅ 支持账户监控（`watch-account`）
- ✅ 支持 WebSocket 数据流订阅

### 其他交易所（Binance, OKX, Gate）

- ✅ 支持余额监控和显示
- ✅ 支持日志记录（暂不保存到数据库）
- ⚠️ 暂不支持账号特定表（使用默认表结构）
- ⚠️ 暂不支持仓位监控和账户监控（仅支持余额监控）

## 实现原理

1. **路由机制**：`_run_watch_balance_async` 函数根据账号配置中的 `exchange` 字段，自动路由到对应的交易所处理函数。

2. **XT 专用实现**：XT 交易所使用 `_run_xt_watch_balance_async`，支持账号特定表和完整的数据保存功能。

3. **通用实现**：其他交易所使用 `_run_generic_watch_balance_async`，提供基础的余额监控和显示功能。

4. **并发执行**：所有账号的监控任务通过 `asyncio.gather` 并发执行，互不干扰。

## 数据库存储

- **XT 交易所**
  - 使用账号特定表（如 `xt_account_updates_{account_id}`）
  - 支持余额、仓位、订单等多种数据类型的入库
- **其他交易所（Binance / OKX / Gate 等）**
  - 使用通用的 `rest_balances` / `rest_positions` 表
  - 每条记录包含 `exchange`、`exchange_type`、`account_id` 等字段，可区分不同交易所和账号
  - 目前 Binance `watch-account` 会写入现货/合约余额以及合约仓位，其它交易所可参考 `rest_models.py` 与 `rest_data_service.py` 扩展仓位、订单等数据保存能力

## 注意事项

1. **API 凭证**：确保每个账号的 `api_key` 和 `api_secret` 正确配置
2. **OKX Passphrase**：OKX 交易所需要额外的 `passphrase` 字段，请在配置文件中添加
3. **交易所限制**：某些交易所可能对 API 调用频率有限制，建议合理设置查询间隔
4. **数据库连接**：所有账号共享同一个数据库连接（通过 `global_settings.database_url` 配置）
5. **错误处理**：如果某个账号的监控失败，不会影响其他账号的监控

## 示例

### 混合交易所配置

```json
{
  "global_settings": {
    "database_url": "postgresql+asyncpg://postgres@localhost:5432/trading"
  },
  "accounts": {
    "xt_main": {
      "name": "XT主账号",
      "exchange": "xt",
      "api_key": "...",
      "api_secret": "...",
      "enabled": true
    },
    "binance_main": {
      "name": "Binance主账号",
      "exchange": "binance",
      "api_key": "...",
      "api_secret": "...",
      "enabled": true
    },
    "okx_test": {
      "name": "OKX测试账号",
      "exchange": "okx",
      "api_key": "...",
      "api_secret": "...",
      "enabled": false
    }
  }
}
```

运行后，系统会：
- 启动 XT 主账号的监控（使用 XT 专用实现）
- 启动 Binance 主账号的监控（使用通用实现）
- 跳过 OKX 测试账号（`enabled: false`）

### 常用命令

- XT 多账号监控：`cextools account watch-account --config config/accounts.json --all-accounts`
- Binance 单账号监控：`cextools account watch-account -x binance --api-key YOUR_KEY --api-secret YOUR_SECRET`
- Binance 使用配置文件：`cextools account watch-account --config config/accounts.json --account-id binance_main`

## 未来计划

- [ ] 为其他交易所添加数据库存储支持
- [ ] 为其他交易所添加账号特定表支持
- [ ] 为其他交易所添加仓位监控支持
- [ ] 为其他交易所添加账户监控支持

