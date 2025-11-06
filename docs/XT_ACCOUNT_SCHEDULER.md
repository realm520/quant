# XT账户定时任务服务

XT账户定时任务服务用于定期获取XT交易所的账户余额和仓位数据，并自动存储到PostgreSQL数据库中。

## 功能特性

- ✅ **现货账户余额**：定期获取XT现货账户的所有资产余额
- ✅ **合约账户余额**：定期获取XT永续合约账户的所有资产余额
- ✅ **合约账户仓位**：定期获取XT永续合约账户的所有持仓信息
- ✅ **自动存储**：数据自动存储到PostgreSQL数据库
- ✅ **定时执行**：固定每10分钟执行一次（无需配置）
- ✅ **实时表格显示**：三个独立的表格实时显示数据
  - XT 现货账户余额表格
  - XT 合约账户余额表格
  - XT 合约账户仓位表格
- ✅ **统计记录**：记录查询成功/失败次数和最后错误信息

## 数据库表结构

XT账户数据存储在独立的专用表中，表名均以 `xt` 开头：

### xt_spot_balances（XT现货账户余额表）
存储XT现货账户余额快照：
- `id`: 主键ID
- `query_time`: 查询时间
- `query_type`: 查询类型（scheduled, manual）
- `asset`: 资产类型（如USDT, BTC）
- `free`: 可用余额
- `locked`: 冻结余额
- `total`: 总余额
- `raw_data`: 原始JSON数据（包含完整的API响应）
- `created_at`: 创建时间

### xt_perp_balances（XT合约账户余额表）
存储XT永续合约账户余额快照：
- `id`: 主键ID
- `query_time`: 查询时间
- `query_type`: 查询类型（scheduled, manual）
- `asset`: 资产类型（如USDT, BTC）
- `free`: 可用余额
- `locked`: 冻结余额
- `total`: 总余额
- `raw_data`: 原始JSON数据（包含完整的API响应）
- `created_at`: 创建时间

### xt_perp_positions（XT合约账户仓位表）
存储XT永续合约账户持仓快照：
- `id`: 主键ID
- `query_time`: 查询时间
- `query_type`: 查询类型（scheduled, manual）
- `symbol`: 交易对（如BTC/USDT）
- `position_side`: 持仓方向（LONG/SHORT）
- `position_amount`: 持仓数量
- `entry_price`: 开仓均价
- `mark_price`: 标记价格
- `unrealized_pnl`: 未实现盈亏
- `percentage`: 盈亏百分比
- `notional`: 名义价值
- `isolated`: 是否逐仓
- `leverage`: 杠杆倍数
- `liquidation_price`: 强平价格
- `margin`: 保证金
- `roe`: 收益率百分比
- `raw_data`: 原始JSON数据（包含完整的API响应）
- `created_at`: 创建时间

**注意**：
- 所有表都包含 `raw_data` 列，用于保存完整的原始API响应数据
- 表名均以 `xt` 开头，便于区分和管理
- 现货和合约数据分别存储在不同的表中

## 环境变量配置

在运行服务之前，需要设置以下环境变量：

```bash
# XT API密钥（现货和合约共用同一套密钥）
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"

# 数据库连接URL（可选，默认使用本地数据库）
export DATABASE_URL="postgresql+asyncpg://user:password@localhost:5432/trading"
```

**注意**：
- XT交易所的现货和合约使用同一套API密钥，无需分别配置
- 查询间隔固定为10分钟，无需配置

## 使用方法

### 方法1：使用CLI命令（推荐）

```bash
# 设置环境变量（XT API现货和合约共用）
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"

# 启动XT账户定时监控（默认使用XT交易所）
cextools account watch-account

# 显式指定XT交易所
cextools account watch-account -x xt

# 使用命令行参数提供API密钥
cextools account watch-account -x xt --api-key YOUR_KEY --api-secret YOUR_SECRET

# 启用调试模式
cextools account watch-account -x xt --debug
```

**参数说明**：
- `-x, --exchange`: 指定交易所（目前仅支持 `xt`，默认值为 `xt`）
  - 如果指定其他交易所（如 `binance`, `okx`, `gate`），会显示"暂时不支持"的错误提示
- `--api-key`: API密钥（覆盖环境变量 `XT_API_KEY`）
- `--api-secret`: API密钥（覆盖环境变量 `XT_API_SECRET`）
- `--debug`: 启用调试模式，显示详细错误信息

**功能说明**：
- 启动后立即执行一次查询并显示三个表格
- 每10分钟自动查询并显示
- 数据自动保存到PostgreSQL数据库
- 按 `Ctrl+C` 停止监控

**显示效果**：
```
启动XT账户定时任务服务
查询间隔: 10分钟（固定）
监控内容:
  • 现货账户余额
  • 合约账户余额
  • 合约账户仓位

✓ 数据库表已就绪
✓ 交易所连接成功

============================================================
第 1 次查询 - 2025-01-XX XX:XX:XX
============================================================

[显示 XT 现货账户余额表格]
[显示 XT 合约账户余额表格]
[显示 XT 合约账户仓位表格]

下次查询: 2025-01-XX XX:XX:XX
等待 10 分钟...
```

**注意**：每次查询后会自动显示三个独立的表格，PnL和ROE使用颜色区分盈亏状态。

## 日志

服务会输出详细的日志信息，包括：
- 每次查询的开始和结束时间
- 成功/失败状态
- 错误信息（如果有）
- 数据统计信息

日志会输出到标准输出，可以通过重定向保存到文件：

```bash
# 默认使用XT交易所
cextools account watch-account > xt_scheduler.log 2>&1

# 显式指定XT交易所
cextools account watch-account -x xt > xt_scheduler.log 2>&1
```

### 方法2：直接运行Python脚本（高级用法）

如果需要直接运行Python脚本（例如在后台服务中），可以使用：

```bash
# 设置环境变量
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"

# 运行服务
python -m tri_arb.services.xt_account_scheduler_main
```

**注意**：此方法不会显示表格，只会在后台静默保存数据到数据库。

## 首次运行

首次运行前，确保：

1. **PostgreSQL数据库已启动**
   ```bash
   # 使用Docker启动（如果使用Docker）
   ./scripts/start_postgres.sh
   
   # 或使用本地PostgreSQL
   # 确保PostgreSQL服务正在运行
   ```

2. **数据库表已创建**
   服务启动时会自动创建所需的数据库表（如果不存在）。

3. **API密钥已配置**
   确保环境变量中设置了正确的XT API密钥。

## 查看数据

### 查询余额数据

```sql
-- 查询最新的XT现货账户余额
SELECT * FROM xt_spot_balances 
ORDER BY query_time DESC 
LIMIT 20;

-- 查询最新的XT合约账户余额
SELECT * FROM xt_perp_balances 
ORDER BY query_time DESC 
LIMIT 20;

-- 查询特定资产的历史余额（现货）
SELECT query_time, asset, free, locked, total 
FROM xt_spot_balances 
WHERE asset = 'USDT' 
ORDER BY query_time DESC;

-- 查询特定资产的历史余额（合约）
SELECT query_time, asset, free, locked, total 
FROM xt_perp_balances 
WHERE asset = 'USDT' 
ORDER BY query_time DESC;

-- 查看原始数据（现货）
SELECT asset, query_time, raw_data 
FROM xt_spot_balances 
WHERE asset = 'BTC' 
ORDER BY query_time DESC 
LIMIT 1;
```

### 查询仓位数据

```sql
-- 查询最新的所有仓位
SELECT * FROM xt_perp_positions 
ORDER BY query_time DESC;

-- 查询特定交易对的仓位历史
SELECT query_time, symbol, position_side, position_amount, 
       entry_price, mark_price, unrealized_pnl, leverage, roe
FROM xt_perp_positions 
WHERE symbol = 'BTC/USDT' 
ORDER BY query_time DESC;

-- 查询有持仓的交易对
SELECT DISTINCT symbol, MAX(query_time) as last_query_time
FROM xt_perp_positions 
WHERE position_amount != 0
GROUP BY symbol
ORDER BY last_query_time DESC;

-- 查看原始数据（仓位）
SELECT symbol, query_time, raw_data 
FROM xt_perp_positions 
WHERE symbol = 'BTC/USDT' 
ORDER BY query_time DESC 
LIMIT 1;
```

## 停止服务

使用 `Ctrl+C` 来优雅地停止监控：

```bash
# 在运行 watch-account 命令的终端中按 Ctrl+C
# 服务会优雅地关闭所有连接并保存数据
```

## 表格显示说明

### XT 现货账户余额表格
显示字段：
- **Currency**: 资产类型（如USDT, BTC）
- **Available**: 可用余额
- **Frozen**: 冻结余额
- **Total**: 总余额

### XT 合约账户余额表格
显示字段：
- **Currency**: 资产类型（如USDT, BTC）
- **Available**: 可用余额
- **Frozen**: 冻结余额
- **Total**: 总余额

### XT 合约账户仓位表格
显示字段：
- **Symbol**: 交易对（如BTC/USDT）
- **Side**: 持仓方向（LONG/SHORT）
- **Quantity**: 持仓数量
- **Entry Price**: 开仓均价
- **Current Price**: 当前标记价格
- **Liquidation Price**: 强平价格
- **PnL**: 未实现盈亏（绿色表示盈利，红色表示亏损）
- **ROE**: 收益率百分比（绿色表示盈利，红色表示亏损）
- **Leverage**: 杠杆倍数

## 日志

服务会输出详细的日志信息，包括：
- 每次查询的开始和结束时间
- 成功/失败状态
- 错误信息（如果有）
- 数据统计信息

日志会输出到标准输出，可以通过重定向保存到文件：

```bash
# 默认使用XT交易所
cextools account watch-account > xt_scheduler.log 2>&1

# 显式指定XT交易所
cextools account watch-account -x xt > xt_scheduler.log 2>&1
```

## 关于杠杆账户

目前XT交易所的API主要支持：
- **现货账户**（spot）：现货交易账户
- **永续合约账户**（perp）：永续合约交易账户（带杠杆）

如果XT交易所后续支持独立的杠杆账户（margin trading），可以通过以下方式扩展：

1. 在 `xt_account_scheduler.py` 中添加 `_fetch_margin_balance()` 方法
2. 在 `_fetch_all_accounts()` 中调用该方法
3. 使用 `exchange_type='margin'` 保存数据

## 故障排除

### 问题：无法连接到数据库

**解决方法**：
1. 检查PostgreSQL服务是否运行
2. 检查 `DATABASE_URL` 环境变量是否正确
3. 检查数据库用户权限

### 问题：API调用失败

**解决方法**：
1. 检查API密钥是否正确
2. 检查网络连接
3. 查看日志中的详细错误信息

### 问题：数据未保存

**解决方法**：
1. 检查数据库表是否已创建
2. 查看日志中的错误信息
3. 检查数据库连接是否正常

## 注意事项

1. **交易所支持**：目前仅支持XT交易所，其他交易所（binance、okx、gate）会显示"暂时不支持"的错误提示
2. **API限流**：XT交易所可能有API调用频率限制，查询间隔固定为10分钟以避免触发限流
3. **数据存储**：定期查询会产生大量数据，建议定期清理旧数据或使用数据归档策略
4. **API密钥安全**：不要将API密钥提交到版本控制系统
5. **网络稳定性**：确保服务器网络连接稳定，避免因网络问题导致数据丢失
6. **表格显示**：表格会在每次查询后自动刷新，PnL和ROE使用颜色区分盈亏状态
7. **数据保存**：即使查询失败，已成功获取的数据仍会保存到数据库
8. **原始数据**：所有表都包含 `raw_data` 列，保存完整的API响应JSON数据，便于后续分析和调试

## 扩展功能

可以在此基础上扩展的功能：
- 添加数据导出功能（CSV、JSON格式）
- 添加数据可视化功能
- 添加告警功能（余额变化、仓位变化）
- 添加数据备份功能
- 支持多个交易所同时监控

