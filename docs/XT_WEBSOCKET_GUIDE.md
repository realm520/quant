# XT WebSocket订阅功能使用指南

## 📋 概述

XT WebSocket订阅功能提供了实时接收XT交易所用户数据流的能力，包括：

- **账户余额更新** - 实时监控账户资金变化
- **持仓更新** - 跟踪持仓状态和盈亏变化  
- **订单更新** - 监控订单状态变化
- **成交记录** - 实时接收成交信息
- **数据同步** - 自动补充断线期间的缺失数据（默认启用）
- **永续合约** - 默认订阅永续合约数据（主要交易类型）

## 🚀 快速开始

### 1. 环境配置

设置XT API凭证：

```bash
# XT交易所的现货和永续合约使用同一个API密钥
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
```

**重要说明**: XT交易所的现货交易和永续合约交易使用相同的API密钥对，无需分别配置。

### 2. 启动订阅服务

```bash
# 订阅永续合约数据流（默认）
python -m tri_arb.cli.main subscribe user-stream -x xt

# 只订阅账户和持仓
python -m tri_arb.cli.main subscribe user-stream -x xt --channels account,position

# 禁用数据同步（不推荐）
python -m tri_arb.cli.main subscribe user-stream -x xt --disable-data-sync

# 首次运行，自动创建数据库表
python -m tri_arb.cli.main subscribe user-stream -x xt --create-tables
```

**重要说明**: 
- 默认订阅永续合约数据（主要交易类型）
- XT交易所的现货和永续合约使用相同的API密钥对
- 数据同步功能默认启用，防止断线期间数据丢失

### 3. 停止服务

按 `Ctrl+C` 停止订阅服务。

## 📊 支持的频道

| 频道 | 描述 | 数据内容 |
|------|------|----------|
| `account` | 账户余额 | 可用余额、冻结余额、总余额 |
| `position` | 持仓信息 | 持仓数量、开仓价、标记价、未实现盈亏 |
| `order` | 订单状态 | 订单ID、状态、数量、价格、成交情况 |
| `trade` | 成交记录 | 成交ID、价格、数量、手续费 |

## 🔧 高级配置

### 输出格式

- `table` - 表格格式（默认）
- `json` - JSON格式
- `none` - 不显示，仅保存到数据库

### 数据库配置

```bash
# 使用自定义数据库URL
python -m tri_arb.cli.main subscribe user-stream -x xt --database-url "postgresql+asyncpg://user:pass@host:port/db"
```

### 调试模式

```bash
# 启用详细日志
python -m tri_arb.cli.main subscribe user-stream -x xt --debug
```

## 🗄️ 数据库表结构

### XT WebSocket数据表

- `xt_account_updates` - 账户余额更新记录
- `xt_position_updates` - 持仓更新记录  
- `xt_order_updates` - 订单更新记录
- `xt_trade_updates` - 成交更新记录
- `xt_websocket_connections` - WebSocket连接记录

### 视图

- `xt_latest_account_balances` - 最新账户余额
- `xt_latest_positions` - 最新持仓
- `xt_latest_orders` - 最新订单
- `xt_websocket_stats` - WebSocket连接统计

## 🔄 数据同步机制（默认启用）

### 自动数据同步

- **默认启用**: 数据同步功能默认开启，防止数据丢失
- **同步间隔**: 每5分钟自动同步一次
- **重连同步**: 每次重连后立即进行数据同步
- **同步内容**: 账户余额、持仓信息

### 同步触发条件

1. **定期同步**: 每5分钟自动触发
2. **重连同步**: WebSocket重连成功后立即同步
3. **手动同步**: 可通过API手动触发

### 禁用数据同步

```bash
# 禁用数据同步（不推荐，可能导致数据丢失）
python -m tri_arb.cli.main subscribe user-stream -x xt --disable-data-sync
```

**注意**: 禁用数据同步可能导致断线期间的数据丢失，建议保持默认启用状态。

## 📈 监控和统计

### 连接统计

```sql
-- 查看WebSocket连接统计
SELECT * FROM xt_websocket_stats;

-- 查看最新账户余额
SELECT * FROM xt_latest_account_balances;

-- 查看最新持仓
SELECT * FROM xt_latest_positions;
```

### 性能监控

```sql
-- 查看消息处理统计
SELECT 
    total_connections,
    active_connections,
    total_messages,
    account_updates,
    position_updates,
    order_updates,
    trade_updates,
    total_reconnects,
    total_data_syncs
FROM xt_websocket_stats;
```

## 🛠️ 故障排除

### 常见问题

1. **连接失败**
   ```
   错误: WebSocket连接失败
   解决: 检查网络连接和API凭证
   ```

2. **认证失败**
   ```
   错误: 认证失败
   解决: 验证API Key和Secret是否正确
   ```

3. **数据库连接失败**
   ```
   错误: 数据库连接失败
   解决: 检查PostgreSQL服务状态和连接URL
   ```

### 调试步骤

1. **启用调试模式**
   ```bash
   python -m tri_arb.cli.main subscribe user-stream -x xt --debug
   ```

2. **检查日志**
   ```bash
   # 查看详细错误信息
   tail -f logs/xt_websocket.log
   ```

3. **测试REST API**
   ```bash
   python test_xt_websocket.py rest
   ```

## 🔒 安全注意事项

1. **API凭证保护**
   - 不要在代码中硬编码API凭证
   - 使用环境变量存储敏感信息
   - 定期轮换API密钥

2. **网络安全**
   - 使用HTTPS/WSS连接
   - 限制API权限范围
   - 监控异常访问

3. **数据安全**
   - 定期备份数据库
   - 加密敏感数据
   - 访问控制

## 📚 示例代码

### Python API使用

```python
import asyncio
from tri_arb.services.xt_user_stream import XTUserStreamService
from tri_arb.storage.database import DatabaseManager

async def main():
    # 初始化数据库管理器
    db_manager = DatabaseManager()
    
    # 创建WebSocket服务
    service = XTUserStreamService(
        api_key="your_api_key",
        api_secret="your_api_secret",
        db_manager=db_manager,
        auto_reconnect=True,
        display_format="table",
        enabled_channels={"account", "position", "order", "trade"},
    )
    
    # 启动服务
    await service.start()

# 运行服务
asyncio.run(main())
```

### 数据库查询示例

```sql
-- 查询最近的账户更新
SELECT 
    currency,
    available,
    frozen,
    total,
    update_time
FROM xt_account_updates
WHERE update_time > NOW() - INTERVAL '1 hour'
ORDER BY update_time DESC;

-- 查询活跃持仓
SELECT 
    symbol,
    side,
    quantity,
    entry_price,
    mark_price,
    unrealized_pnl,
    leverage
FROM xt_latest_positions
WHERE quantity > 0;

-- 查询最近的订单
SELECT 
    symbol,
    order_id,
    side,
    order_type,
    quantity,
    price,
    status,
    create_time
FROM xt_latest_orders
WHERE create_time > NOW() - INTERVAL '1 day'
ORDER BY create_time DESC;
```

## 🆘 技术支持

如果遇到问题，请：

1. 查看日志文件
2. 检查网络连接
3. 验证API凭证
4. 联系技术支持

---

**注意**: 此功能需要有效的XT API凭证和PostgreSQL数据库。请确保在生产环境中正确配置安全设置。
