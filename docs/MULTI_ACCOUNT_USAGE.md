# XT 多账号订阅使用指南

本文档介绍如何使用多账号订阅功能，同时监控多个 XT 账号的 WebSocket 数据流。

---

## 1. 功能特性

- ✅ **多账号支持**: 从 JSON 配置文件加载多个账号
- ✅ **独立表结构**: 每个账号使用独立的数据库表
- ✅ **账号命名**: 每个账号可以设置友好的名称
- ✅ **灵活配置**: 每个账号可以独立配置订阅频道、告警等
- ✅ **并发订阅**: 同时订阅多个账号的 WebSocket 数据流
- ✅ **仅支持 XT**: 目前仅支持 XT 交易所

---

## 2. 配置文件格式

### 2.1 创建配置文件

复制示例配置文件并修改：

```bash
cp config/accounts.example.json config/accounts.json
```

### 2.2 配置文件结构

```json
{
  "accounts": {
    "account_001": {
      "name": "主账号",
      "exchange": "xt",
      "api_key": "your_xt_api_key_1",
      "api_secret": "your_xt_api_secret_1",
      "enabled": true,
      "channels": ["account", "position", "order"],
      "metrics_config": {
        "perp_balance_volatility": {
          "enabled": true,
          "window_minutes": 1440,
          "warning_threshold": 0.05,
          "critical_threshold": 0.10
        },
        "perp_risk_ratio": {
          "enabled": true,
          "asset": "USDT",
          "warning_threshold": 0.50,
          "critical_threshold": 0.80
        }
      },
      "lark_webhook": "https://open.larksuite.com/open-apis/bot/v2/hook/...",
      "lark_secret": "optional_secret"
    },
    "account_002": {
      "name": "测试账号",
      "exchange": "xt",
      "api_key": "your_xt_api_key_2",
      "api_secret": "your_xt_api_secret_2",
      "enabled": true,
      "channels": ["account", "position"],
      "lark_webhook": null
    }
  },
  "global_settings": {
    "default_interval_minutes": 10,
    "enable_lark_by_default": false,
    "database_url": "${DATABASE_URL}"
  }
}
```

### 2.3 配置字段说明

#### 账号配置 (`accounts.*`)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 账号友好名称 |
| `exchange` | string | 是 | 交易所名称（目前仅支持 "xt"） |
| `api_key` | string | 是 | XT API Key |
| `api_secret` | string | 是 | XT API Secret |
| `enabled` | boolean | 否 | 是否启用（默认 true） |
| `channels` | array | 否 | 订阅频道列表：account, position, order, trade |
| `metrics_config` | object | 否 | 指标配置（告警阈值等） |
| `lark_webhook` | string/null | 否 | Lark 告警 Webhook URL |
| `lark_secret` | string | 否 | Lark 签名密钥（可选） |

#### 全局设置 (`global_settings`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `default_interval_minutes` | number | 默认查询间隔（分钟） |
| `enable_lark_by_default` | boolean | 默认是否启用 Lark 告警 |
| `database_url` | string | 数据库 URL（支持环境变量 `${DATABASE_URL}`） |

---

## 3. 数据库表结构

每个账号会创建独立的表，表名格式：`{base_table_name}_{account_id}`

### 3.1 WebSocket 数据表

- `xt_account_updates_{account_id}` - 账户余额更新
- `xt_spot_updates_{account_id}` - 现货余额快照
- `xt_position_updates_{account_id}` - 持仓更新
- `xt_order_updates_{account_id}` - 订单更新
- `xt_trade_updates_{account_id}` - 成交记录
- `xt_transfers_{account_id}` - 资金划转记录

### 3.2 REST API 数据表

- `xt_spot_balances_{account_id}` - 现货余额记录
- `xt_perp_balances_{account_id}` - 合约余额记录
- `xt_perp_positions_{account_id}` - 合约仓位记录
- `xt_rest_position_updates_{account_id}` - 仓位定时更新

### 3.3 表结构示例

以 `account_001` 为例，会创建以下表：

```sql
-- 账户余额更新表
CREATE TABLE xt_account_updates_account_001 (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    currency VARCHAR(20) NOT NULL,
    available NUMERIC(30, 10) NOT NULL,
    frozen NUMERIC(30, 10) NOT NULL,
    total NUMERIC(30, 10) NOT NULL,
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 其他表类似...
```

---

## 4. 使用方法

### 4.1 基本使用

```bash
# 使用默认配置文件 (config/accounts.json)
cextools subscribe multi-account

# 指定配置文件
cextools subscribe multi-account --config config/my_accounts.json
```

### 4.2 首次运行（创建表）

```bash
# 自动创建所有账号的数据库表
cextools subscribe multi-account --create-tables
```

### 4.3 只启动指定账号

```bash
# 只启动 account_001 和 account_002
cextools subscribe multi-account --accounts account_001,account_002
```

### 4.4 指定数据库

```bash
# 通过命令行参数
cextools subscribe multi-account --database-url postgresql://user:pass@host:5432/db

# 或通过环境变量
export DATABASE_URL=postgresql://user:pass@host:5432/db
cextools subscribe multi-account
```

### 4.5 输出格式

```bash
# 表格格式（默认）
cextools subscribe multi-account --output table

# JSON 格式
cextools subscribe multi-account --output json

# 不显示输出（仅保存到数据库）
cextools subscribe multi-account --output none
```

### 4.6 禁用数据同步

```bash
# 禁用数据同步（不推荐，可能导致数据丢失）
cextools subscribe multi-account --disable-data-sync
```

---

## 5. 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--config` | `-c` | 配置文件路径 | `config/accounts.json` |
| `--accounts` | `-a` | 要启动的账号ID列表（逗号分隔） | 所有启用的账号 |
| `--database-url` | - | 数据库连接URL | 从配置文件或环境变量读取 |
| `--create-tables` | - | 自动创建数据库表 | `false` |
| `--output` | `-o` | 输出格式（table/json/none） | `table` |
| `--enable-data-sync` | - | 启用数据同步 | `true` |
| `--disable-data-sync` | - | 禁用数据同步 | - |
| `--debug` | - | 启用调试模式 | `false` |

---

## 6. 查询数据示例

### 6.1 查询特定账号的账户余额

```sql
-- 查询 account_001 的最新余额
SELECT * FROM xt_account_updates_account_001
ORDER BY update_time DESC
LIMIT 10;
```

### 6.2 查询所有账号的余额（需要联合查询）

```sql
-- 查询所有账号的最新 USDT 余额
SELECT 'account_001' as account_id, currency, total, update_time
FROM xt_account_updates_account_001
WHERE currency = 'USDT'
ORDER BY update_time DESC
LIMIT 1

UNION ALL

SELECT 'account_002' as account_id, currency, total, update_time
FROM xt_account_updates_account_002
WHERE currency = 'USDT'
ORDER BY update_time DESC
LIMIT 1;
```

### 6.3 查询资金划转记录

```sql
-- 查询 account_001 的资金划转
SELECT * FROM xt_transfers_account_001
ORDER BY transfer_time DESC
LIMIT 20;
```

---

## 7. 注意事项

1. **账号ID命名**: 账号ID会用作表名后缀，建议使用字母、数字和下划线，避免特殊字符
2. **表数量**: 每个账号会创建约 10 个表，10 个账号就是 100 个表，请确保数据库支持
3. **并发连接**: 每个账号会建立独立的 WebSocket 连接，请确保网络和系统资源充足
4. **API 限流**: XT API 有频率限制，多账号同时订阅时请注意限流
5. **数据同步**: 建议启用数据同步（默认启用），防止 WebSocket 断线时数据丢失
6. **配置文件安全**: 配置文件包含 API 密钥，请妥善保管，不要提交到版本控制系统

---

## 8. 故障排查

### 8.1 配置文件不存在

```
错误: 配置文件不存在: config/accounts.json
```

**解决**: 创建配置文件或使用 `--config` 指定正确的路径

### 8.2 账号不存在

```
错误: 账号不存在: account_xxx
```

**解决**: 检查配置文件中的账号ID是否正确

### 8.3 数据库连接失败

```
错误: 未指定数据库URL
```

**解决**: 通过 `--database-url`、配置文件或 `DATABASE_URL` 环境变量指定数据库URL

### 8.4 表创建失败

```
错误: relation "xt_account_updates_xxx" already exists
```

**解决**: 表已存在，这是正常的。如果确实需要重建，先手动删除表

---

## 9. 扩展说明

### 9.1 添加新账号

1. 编辑配置文件 `config/accounts.json`
2. 在 `accounts` 中添加新账号配置
3. 运行 `cextools subscribe multi-account --create-tables` 创建表
4. 启动订阅服务

### 9.2 禁用账号

在配置文件中将账号的 `enabled` 字段设置为 `false`，或从配置文件中删除该账号。

### 9.3 修改账号配置

修改配置文件后，需要重启订阅服务才能生效。

---

## 10. 示例场景

### 场景1: 监控 3 个账号

```json
{
  "accounts": {
    "main_account": {
      "name": "主账号",
      "exchange": "xt",
      "api_key": "...",
      "api_secret": "...",
      "enabled": true,
      "channels": ["account", "position", "order"]
    },
    "test_account": {
      "name": "测试账号",
      "exchange": "xt",
      "api_key": "...",
      "api_secret": "...",
      "enabled": true,
      "channels": ["account", "position"]
    },
    "backup_account": {
      "name": "备用账号",
      "exchange": "xt",
      "api_key": "...",
      "api_secret": "...",
      "enabled": false,
      "channels": ["account"]
    }
  }
}
```

启动命令：
```bash
# 启动所有启用的账号（main_account 和 test_account）
cextools subscribe multi-account

# 只启动主账号
cextools subscribe multi-account --accounts main_account
```

---

## 11. 与单账号订阅的区别

| 特性 | 单账号订阅 | 多账号订阅 |
|------|-----------|-----------|
| 配置文件 | 命令行参数 | JSON 配置文件 |
| 数据库表 | 共享表 | 每个账号独立表 |
| 账号数量 | 1 个 | 多个（建议 10-50 个） |
| 账号命名 | 无 | 支持友好名称 |
| 使用场景 | 单个账号监控 | 批量账号监控 |

---

## 12. 后续计划

- [ ] 支持其他交易所（Binance、OKX 等）
- [ ] 账号配置热重载（无需重启）
- [ ] 账号健康检查和自动恢复
- [ ] 账号级别的指标告警配置
- [ ] 账号数据统计和报表

---

如有问题，请参考主文档或提交 Issue。

