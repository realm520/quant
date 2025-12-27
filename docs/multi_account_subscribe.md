# 多账号订阅服务使用文档

## 命令概述

`uv run cextools subscribe multi-account --config config/accounts_test.json` 是一个多交易所、多账号的 WebSocket 订阅服务，用于实时接收并存储账户更新、订单更新、持仓更新和成交信息。

## 执行步骤详解

### 1. 命令解析与初始化

**步骤 1.1: 解析命令行参数**
- 读取配置文件路径：`--config config/accounts_test.json`
- 解析其他可选参数：
  - `--accounts`: 指定要启动的账号ID列表（逗号分隔）
  - `--database-url`: 数据库连接URL（覆盖配置文件和环境变量）
  - `--create-tables`: 是否自动创建数据库表
  - `--output`: 输出格式（table/json/none）
  - `--enable-data-sync/--disable-data-sync`: 启用/禁用数据同步（默认启用）
  - `--debug`: 启用调试模式

**步骤 1.2: 加载配置文件**
- 读取 JSON 配置文件（`config/accounts_test.json`）
- 解析 `global_settings` 部分（包含数据库URL等全局配置）
- 解析 `accounts` 部分（包含各个账号的配置信息）

**步骤 1.3: 验证配置**
- 检查数据库URL是否存在（优先级：命令行参数 > 配置文件 > 环境变量）
- 验证账号配置的有效性
- 过滤出启用的账号（`enabled: true`）

### 2. 数据库初始化

**步骤 2.1: 创建数据库连接**
- 使用解析得到的数据库URL创建 `DatabaseManager` 实例
- 连接 PostgreSQL 数据库

**步骤 2.2: 创建数据库表**
- 检查并创建基础数据库表（如果不存在）
- 支持的交易所表：
  - Binance: `binance_account_update`, `binance_order_update`, `binance_trade_update`, `binance_position_update`
  - OKX: `okx_account_update`, `okx_order_update`, `okx_trade_update`, `okx_position_update`
  - Gate.io: `gate_account_update`, `gate_order_update`, `gate_trade_update`, `gate_position_update`
  - XT: `xt_account_update`, `xt_order_update`, `xt_trade_update`, `xt_position_update`, `xt_websocket_connection`

### 3. 启动 Prometheus Metrics 服务器

**步骤 3.1: 初始化 Metrics 服务器**
- 启动 Prometheus metrics 服务器（端口 9601）
- 用于监控订阅服务的运行状态和性能指标

### 4. 为每个账号启动订阅服务

**步骤 4.1: 遍历启用的账号**
- 对于配置文件中每个 `enabled: true` 的账号：
  - 读取账号信息：
    - `account_id`: 账号ID（如 `account_008`）
    - `name`: 账号名称（如 `账号8`）
    - `exchange`: 交易所类型（`xt`, `binance`, `okx`, `gate`）
    - `api_key`: API 密钥
    - `api_secret`: API 密钥
    - `channels`: 订阅的频道列表（如 `["order", "trade", "position"]`）

**步骤 4.2: 创建交易所服务实例**
- 根据 `exchange` 字段创建对应的用户流服务：
  - **XT**: `XTUserStreamService`
  - **Binance**: `BinanceUserStreamService`
  - **OKX**: `OKXUserStreamService`
  - **Gate.io**: `GateUserStreamService`

**步骤 4.3: 初始化服务**
- 为每个服务实例设置：
  - API 凭证（`api_key`, `api_secret`）
  - 数据库管理器
  - 账号ID和账号名称
  - 启用的频道列表
  - 数据同步开关（`enable_data_sync`）
  - 自动重连配置

**步骤 4.4: 启动服务（异步任务）**
- 为每个账号创建独立的异步任务
- 任务之间延迟 0.3 秒启动，避免同时连接过多

### 5. XT 账号服务启动流程（以 XT 为例）

**步骤 5.1: 初始化 REST 客户端**
- 创建 `XTPerpExchange` 实例用于数据同步
- 连接到 XT 交易所 REST API

**步骤 5.2: 启动批量写入任务**
- 根据启用的频道启动对应的批量写入任务：
  - **Trade 频道**: 启动 `_trade_writer_task`
    - 从 `_trade_queue` 队列读取成交数据
    - 批量保存到 `xt_trade_update` 表
  - **Order 频道**: 启动 `_order_writer_task`
    - 从 `_order_queue` 队列读取订单数据
    - 批量保存到 `xt_order_update` 表
  - **Position 频道**: 启动 `_position_writer_task`
    - 从 `_position_queue` 队列读取持仓数据
    - 批量保存到 `xt_position_update` 表

**步骤 5.3: 建立 WebSocket 连接**
- 连接到 XT WebSocket 服务器：`wss://fstream.xt.com/ws/user`
- 使用 API 密钥进行身份验证
- 订阅指定的频道（order, trade, position）

**步骤 5.4: 启动消息处理循环**
- 持续接收 WebSocket 消息
- 根据消息类型路由到对应的处理函数：
  - `account` 消息 → `_handle_account_update()`
  - `position` 消息 → `_handle_position_update()`
  - `order` 消息 → `_handle_order_update()`
  - `trade` 消息 → `_handle_trade_update()`

**步骤 5.5: 数据入队处理**
- 将接收到的数据放入对应的异步队列：
  - 账户更新：立即保存（低频率）
  - 订单更新：放入 `_order_queue` 队列
  - 持仓更新：放入 `_position_queue` 队列
  - 成交更新：放入 `_trade_queue` 队列

**步骤 5.6: 批量写入数据库**
- 批量写入任务定期从队列中取出数据：
  - 达到批量大小（默认 50 条）或超时（默认 0.5 秒）时触发
  - 使用 `ON CONFLICT DO UPDATE` 处理重复数据
  - 更新 Prometheus metrics

### 6. 断线重连与数据同步

**步骤 6.1: 检测连接断开**
- 监听 WebSocket 连接状态
- 记录断开时间（`disconnect_time`）

**步骤 6.2: 自动重连**
- 如果启用自动重连（`auto_reconnect=True`）：
  - 等待重连延迟（默认 5 秒）
  - 重新建立 WebSocket 连接
  - 记录重连时间（`reconnect_time`）

**步骤 6.3: 数据同步（如果启用）**
- 如果 `enable_data_sync=True`：
  - 计算断线时间范围（`disconnect_time` 到 `reconnect_time`）
  - 通过 REST API 同步缺失的数据：
    - 同步账户余额（`_sync_account_data()`）
    - 同步持仓数据（`_sync_position_data()`）
    - 同步订单数据（`_sync_order_data_fixed_lookback()`）

### 7. 运行与监控

**步骤 7.1: 保持运行**
- 所有账号的订阅服务在后台并发运行
- 主程序等待所有任务完成（或直到收到停止信号）

**步骤 7.2: 日志输出**
- 输出服务启动信息
- 记录连接状态、订阅状态
- 记录数据同步状态
- 输出批量写入统计信息

**步骤 7.3: Metrics 更新**
- 实时更新 Prometheus metrics：
  - 订单数量、状态分布
  - 成交数量、金额统计
  - 连接状态、重连次数

### 8. 停止服务

**步骤 8.1: 接收停止信号**
- 用户按 `Ctrl+C` 发送中断信号
- 或程序异常退出

**步骤 8.2: 清理资源**
- 取消所有异步任务
- 刷新队列中剩余的数据
- 关闭 WebSocket 连接
- 关闭数据库连接
- 记录连接结束时间

## 配置文件格式

```json
{
  "global_settings": {
    "database_url": "postgresql+asyncpg://postgres@localhost:5432/trading"
  },
  "accounts": {
    "account_008": {
      "name": "账号8",
      "exchange": "xt",
      "api_key": "your_api_key",
      "api_secret": "your_api_secret",
      "enabled": true,
      "channels": ["order", "trade", "position"],
      "watch_tasks": {
        "balance": {
          "enabled": true,
          "exchange_type": "perp",
          "interval": 5
        }
      }
    }
  }
}
```

## 数据存储

### XT 交易所数据表

- **xt_account_update**: 账户余额更新
  - 字段：`account_id`, `currency`, `available`, `frozen`, `total`, `update_time`
  
- **xt_order_update**: 订单更新
  - 字段：`order_id`, `account_id`, `symbol`, `status`, `quantity`, `filled_quantity`, `price`, `update_time`
  - 唯一约束：`(order_id, update_time, account_id)`
  
- **xt_trade_update**: 成交更新
  - 字段：`trade_id`, `order_id`, `account_id`, `symbol`, `price`, `quantity`, `commission`, `update_time`
  
- **xt_position_update**: 持仓更新
  - 字段：`account_id`, `symbol`, `side`, `quantity`, `entry_price`, `mark_price`, `unrealized_pnl`, `update_time`
  
- **xt_websocket_connection**: WebSocket 连接记录
  - 字段：`connection_id`, `start_time`, `end_time`, `is_active`

## 性能特性

1. **批量写入**: 使用异步队列批量写入数据库，提高性能
2. **并发处理**: 多个账号并发运行，互不干扰
3. **自动重连**: 断线后自动重连，保证数据连续性
4. **数据同步**: 重连后自动同步断线期间的数据，防止数据丢失
5. **去重处理**: 使用数据库唯一约束和 `ON CONFLICT` 处理重复数据

## 注意事项

1. **数据库连接**: 确保 PostgreSQL 数据库已启动并可访问
2. **API 凭证**: 确保配置文件中的 API 密钥有效且有相应权限
3. **网络连接**: 确保可以访问交易所的 WebSocket 和 REST API
4. **资源占用**: 多个账号并发运行会占用较多系统资源
5. **数据量**: 高频交易会产生大量数据，注意数据库存储空间

## 停止服务

按 `Ctrl+C` 停止所有订阅服务，程序会优雅地关闭所有连接并保存剩余数据。

