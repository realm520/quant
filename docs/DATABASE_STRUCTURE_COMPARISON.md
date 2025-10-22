##数据库表结构对比：Binance vs OKX

## 🎯 为什么需要独立的表结构？

### 数据结构差异

| 特性 | Binance | OKX |
|------|---------|-----|
| **产品标识** | BTCUSDT | BTC-USDT-SWAP |
| **持仓方向** | LONG/SHORT/BOTH | long/short/net |
| **订单方向** | BUY/SELL (大写) | buy/sell (小写) |
| **订单状态** | NEW/FILLED/CANCELED | live/filled/canceled |
| **推送模式** | 增量（仅变化时） | 快照（定期推送） |
| **时间格式** | 毫秒时间戳 | 毫秒时间戳 |
| **保证金信息** | 简化 | 详细（初始/维持保证金） |

### OKX独有字段

- `inst_type` - 产品类型(SWAP/FUTURES/SPOT)
- `pos_ccy` - 持仓币种
- `mark_px` - 标记价格
- `liq_px` - 预估强平价
- `imr` / `mmr` - 初始/维持保证金
- `rebate` - 返佣信息
- `td_mode` - 交易模式

### Binance独有字段

- `position_side` - 持仓方向(LONG/SHORT/BOTH)
- `time_in_force` - 订单有效期(GTC/IOC/FOK)
- `reduce_only` - 是否仅减仓

## 📊 表结构对比

### 1. 账户/余额表

#### Binance: `account_updates`
```sql
- event_type: ACCOUNT_UPDATE
- asset: USDT
- wallet_balance: 钱包余额
- cross_wallet_balance: 全仓余额
- balance_change: 余额变化
```

#### OKX: `okx_account_balances`
```sql
- total_eq: 账户总权益(USD)
- currency: 币种
- available_bal: 可用余额
- cash_bal: 现金余额
- frozen_bal: 冻结余额
- equity: 币种权益
- upl: 未实现盈亏
```

**主要差异**：
- ✅ OKX提供更详细的账户权益信息
- ✅ OKX区分现金余额和冻结余额
- ✅ Binance提供余额变化量

### 2. 持仓表

#### Binance: `account_updates` (混合表)
```sql
- symbol: BTCUSDT
- position_side: LONG/SHORT
- position_amount: 持仓量
- entry_price: 开仓均价
- unrealized_pnl: 未实现盈亏
```

#### OKX: `okx_positions` (独立表)
```sql
- inst_id: BTC-USDT-SWAP
- pos_side: long/short/net
- pos: 持仓量
- avg_px: 开仓均价
- mark_px: 标记价格
- liq_px: 预估强平价
- upl: 未实现盈亏
- upl_ratio: 盈亏比例
- margin: 保证金
- imr/mmr: 初始/维持保证金
- lever: 杠杆倍数
```

**主要差异**：
- ✅ OKX有独立的持仓表
- ✅ OKX提供详细的保证金信息
- ✅ OKX包含强平价格
- ✅ OKX提供标记价格

### 3. 订单表

#### Binance: `order_updates`
```sql
- order_id: 123456789
- symbol: BTCUSDT
- side: BUY/SELL
- order_type: LIMIT/MARKET
- original_price: 委托价
- average_price: 成交均价
- order_status: NEW/FILLED
- position_side: LONG/SHORT
```

#### OKX: `okx_orders`
```sql
- ord_id: "123456789"
- inst_id: BTC-USDT-SWAP
- side: buy/sell
- ord_type: limit/market/post_only
- px: 委托价
- avg_px: 成交均价
- state: live/filled
- pos_side: long/short/net
- td_mode: isolated/cross
- rebate: 返佣
```

**主要差异**：
- ✅ OKX支持post_only订单类型
- ✅ OKX有返佣信息
- ✅ OKX明确区分交易模式(全仓/逐仓)
- ✅ Binance有time_in_force字段

### 4. 成交表

#### Binance: `trade_updates`
```sql
- trade_id: 成交ID
- order_id: 关联订单
- symbol: BTCUSDT
- price: 成交价
- quantity: 成交量
- commission: 手续费
- is_maker: 是否maker
```

#### OKX: `okx_trades`
```sql
- trade_id: 成交ID
- ord_id: 关联订单
- inst_id: BTC-USDT-SWAP
- fill_px: 成交价
- fill_sz: 成交量
- fee: 手续费
- fill_time: 成交时间
```

## 🗂️ 数据库设计方案

### 方案A：共享表（当前方案）

**优点**：
- ✅ 方便跨交易所对比
- ✅ 统一的查询接口
- ✅ 减少表数量

**缺点**：
- ❌ 字段不匹配，很多NULL值
- ❌ 难以利用交易所特有字段
- ❌ 查询效率降低

### 方案B：独立表（推荐方案）⭐

**优点**：
- ✅ 完整保存各交易所特有字段
- ✅ 表结构清晰，易于维护
- ✅ 查询效率高
- ✅ 索引优化更精确

**缺点**：
- ⚠️ 跨交易所查询需要UNION
- ⚠️ 需要维护两套表结构

## 📋 表名对照

| 功能 | Binance表名 | OKX表名 |
|------|------------|---------|
| 账户余额 | `account_updates` | `okx_account_balances` |
| 持仓 | `account_updates` | `okx_positions` |
| 订单 | `order_updates` | `okx_orders` |
| 成交 | `trade_updates` | `okx_trades` |

## 🔍 查询示例对比

### 查询最新持仓

**Binance:**
```sql
SELECT * FROM account_updates 
WHERE exchange = 'binance_perp' 
  AND event_type = 'POSITION_UPDATE'
ORDER BY event_time DESC 
LIMIT 10;
```

**OKX:**
```sql
SELECT * FROM okx_positions 
ORDER BY update_time DESC 
LIMIT 10;

-- 或使用视图
SELECT * FROM okx_latest_positions;
```

### 查询今日成交

**Binance:**
```sql
SELECT * FROM trade_updates
WHERE exchange = 'binance_perp'
  AND DATE(transaction_time) = CURRENT_DATE;
```

**OKX:**
```sql
SELECT * FROM okx_trades
WHERE DATE(fill_time) = CURRENT_DATE;

-- 或使用统计视图
SELECT * FROM okx_daily_trade_stats 
WHERE trade_date = CURRENT_DATE;
```

### 跨交易所对比查询

```sql
-- 需要UNION
SELECT 
    'Binance' as exchange,
    symbol as product,
    order_status as status,
    event_time as time
FROM order_updates
WHERE exchange = 'binance_perp'
  AND DATE(event_time) = CURRENT_DATE

UNION ALL

SELECT 
    'OKX' as exchange,
    inst_id as product,
    state as status,
    u_time as time
FROM okx_orders
WHERE DATE(u_time) = CURRENT_DATE

ORDER BY time DESC;
```

## 🎯 迁移指南

### 步骤1：创建OKX独立表

```bash
# 运行OKX表初始化脚本
psql -U postgres -d trading -f scripts/init_okx_tables.sql
```

### 步骤2：验证表结构

```sql
-- 查看所有表
\dt

-- 应该看到：
-- okx_account_balances
-- okx_positions
-- okx_orders
-- okx_trades
```

### 步骤3：测试OKX订阅

```bash
# 使用新表结构
cextools subscribe user-stream -x okx --output table
```

### 步骤4：（可选）迁移旧数据

如果之前有OKX数据存在共享表中：

```sql
-- 迁移订单数据示例
INSERT INTO okx_orders (inst_id, ord_id, ...)
SELECT symbol, order_id, ...
FROM order_updates
WHERE exchange = 'okx_perp';
```

## 📊 推送频率差异

### Binance
- **模式**：增量推送
- **频率**：仅在数据变化时
- **特点**：实时性好，数据量小

### OKX
- **模式**：快照推送
- **频率**：每5秒推送一次（即使无变化）
- **特点**：确保数据完整，但有重复

**解决方案**：
```python
# 在代码中过滤重复数据
skip_duplicate_updates = True  # 默认启用
```

## 🎉 总结

### 推荐方案

✅ **使用独立的表结构**

**理由**：
1. OKX和Binance数据结构差异较大
2. 各自的特有字段很重要
3. 独立表查询效率更高
4. 便于后续扩展更多交易所

### 数据管理

- **Binance**: 使用 `account_updates`, `order_updates`, `trade_updates`
- **OKX**: 使用 `okx_account_balances`, `okx_positions`, `okx_orders`, `okx_trades`
- **跨交易所查询**: 使用UNION或创建统一视图

---

**最后更新**：2024-10-21

