# 多账号订阅使用指南

多账号 WebSocket 订阅服务，同时监控多个 XT 账号的实时数据流（账户、持仓、订单、成交）。

## 配置文件

默认路径：`config/accounts.json`

```json
{
  "global_settings": {
    "database_url": "postgresql+asyncpg://user:pass@localhost:5432/trading",
    "s3": {
      "bucket": "market-history-test",
      "prefix": "user-stream",
      "local_dir": "/tmp/xt-ws-data",
      "aws_access_key": "YOUR_AWS_ACCESS_KEY",
      "aws_secret_key": "YOUR_AWS_SECRET_KEY"
    }
  },
  "accounts": {
    "account_001": {
      "name": "主账号",
      "exchange": "xt",
      "api_key": "YOUR_XT_API_KEY",
      "api_secret": "YOUR_XT_API_SECRET",
      "enabled": true,
      "channels": ["account", "position", "order", "trade"]
    }
  }
}
```

### 账号字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 账号友好名称 |
| `exchange` | string | 是 | 交易所（目前仅 `xt`） |
| `api_key` | string | 是 | API Key |
| `api_secret` | string | 是 | API Secret |
| `enabled` | bool | 否 | 是否启用（默认 true） |
| `channels` | array | 否 | 订阅频道：account, position, order, trade |

### 全局设置

| 字段 | 说明 |
|------|------|
| `database_url` | PostgreSQL 连接 URL |
| `s3.bucket` | S3 存储桶名称 |
| `s3.prefix` | S3 对象前缀 |
| `s3.aws_access_key` | AWS Access Key（可选，默认用 IAM Role） |
| `s3.aws_secret_key` | AWS Secret Key（可选） |

## 使用方法

```bash
# 启动所有启用的账号
cextools subscribe multi-account

# 指定配置文件
cextools subscribe multi-account --config config/accounts.json

# 只启动指定账号
cextools subscribe multi-account --accounts account_001,account_002

# 首次运行（自动创建表）
cextools subscribe multi-account --create-tables

# 指定数据库
cextools subscribe multi-account --database-url postgresql://user:pass@host:5432/db
```

### 命令行参数

| 参数 | 简写 | 说明 | 默认值 |
|------|------|------|--------|
| `--config` | `-c` | 配置文件路径 | `config/accounts.json` |
| `--accounts` | `-a` | 要启动的账号 ID（逗号分隔） | 所有启用的 |
| `--database-url` | - | 数据库连接 URL | 配置文件或环境变量 |
| `--create-tables` | - | 自动创建表 | false |
| `--output` | `-o` | 输出格式（table/json/none） | table |
| `--debug` | - | 调试模式 | false |

## 数据存储

### 数据库表（每个账号独立表）

- `xt_account_updates_{account_id}` — 账户余额
- `xt_position_updates_{account_id}` — 持仓
- `xt_order_updates_{account_id}` — 订单
- `xt_trade_updates_{account_id}` — 成交
- `xt_transfers_{account_id}` — 资金划转

### S3 归档

启用 S3 后，数据同步写入本地 JSONL 文件，每小时 gzip 压缩上传：

```
s3://{bucket}/{prefix}/{account_id}/{data_type}/date=YYYY-MM-DD/hour=HH.jsonl.gz
```

## 运行架构

1. 为每个账号创建独立 WebSocket 连接
2. 消息按类型路由到对应处理函数
3. 数据通过异步队列批量写入数据库
4. 同时写入本地 JSONL 文件，定时上传 S3
5. 断线自动重连 + REST API 数据回补

## 注意事项

- 账号 ID 命名只用字母、数字、下划线
- 每个账号约 5 张表，10 个账号 = 50 张表
- 配置文件包含 API 密钥，不要提交到 Git
