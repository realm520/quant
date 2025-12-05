# 验证 tradoor_usdt 持仓指标 SQL 查询文档

用于验证 `account_008` 账号的 `tradoor_usdt` 交易对的持仓指标计算是否正确。

## 1. 查看最新的持仓指标记录

```sql
-- 查看最新的持仓指标记录（每5分钟一条）
SELECT 
    timestamp,
    account_id,
    exchange,
    symbol,
    -- 昨收持仓
    pre_long_qty,
    pre_short_qty,
    pre_long_value,
    pre_short_value,
    -- 今日交易
    long_qty,
    short_qty,
    long_value,
    short_value,
    avg_buy_prz,
    avg_sell_prz,
    -- 已实现 Pnl
    matched_qty,
    realized_pnl,
    -- 当日剩余仓位
    left_long_qty,
    left_short_qty,
    left_long_value,
    left_short_value,
    close_prz,
    unrealized_pnl,
    -- Pnl 汇总
    daily_pnl,
    cumulative_pnl
FROM position_metrics
WHERE account_id = 'account_008'
  AND exchange = 'xt'
  AND symbol = 'tradoor_usdt'
ORDER BY timestamp DESC
LIMIT 10;
```

## 2. 查看今日的初始持仓（从 WebSocket 持仓更新表）

```sql
-- 查看今日 UTC 00:00 之前的最后一条持仓记录（作为初始持仓）
WITH today_start AS (
    SELECT DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')::timestamp AS ts
),
last_position_before_today AS (
    SELECT 
        symbol,
        side,
        MAX(update_time) AS max_time
    FROM xt_position_update
    WHERE account_id = 'account_008'
      AND symbol = 'tradoor_usdt'
      AND update_time < (SELECT ts FROM today_start)
      AND quantity > 0
    GROUP BY symbol, side
)
SELECT 
    p.symbol,
    p.side,
    p.quantity AS quantity_contracts,  -- 合约张数
    p.entry_price,
    p.update_time,
    -- 需要乘以合约乘数才能得到币数量
    -- 合约乘数需要从 XT API 获取，这里先显示合约张数
    p.quantity * p.entry_price AS notional_contracts  -- 合约张数 × 价格
FROM xt_position_update p
JOIN last_position_before_today l
    ON p.symbol = l.symbol
    AND p.side = l.side
    AND p.update_time = l.max_time
WHERE p.account_id = 'account_008'
  AND p.quantity > 0
ORDER BY p.side;
```

## 3. 查看今日的交易记录（成交量）

```sql
-- 查看今日（UTC 00:00 到现在）的所有交易记录
WITH today_start AS (
    SELECT DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')::timestamp AS ts
)
SELECT 
    side,
    COUNT(*) AS trade_count,
    SUM(quantity) AS total_quantity_contracts,  -- 合约张数总和
    SUM(price * quantity) AS total_notional_contracts,  -- 合约张数 × 价格总和
    AVG(price) AS avg_price,
    MIN(update_time) AS first_trade_time,
    MAX(update_time) AS last_trade_time
FROM xt_trade_update
WHERE account_id = 'account_008'
  AND symbol = 'tradoor_usdt'
  AND update_time >= (SELECT ts FROM today_start)
GROUP BY side
ORDER BY side;
```

## 4. 验证今日交易量计算（需要合约乘数）

```sql
-- 注意：这个查询需要知道合约乘数
-- tradoor_usdt 的合约乘数需要从 XT API 获取（通常是 1 或其他值）
-- 这里假设合约乘数为 1，实际使用时需要替换

WITH today_start AS (
    SELECT DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')::timestamp AS ts
),
contract_multiplier AS (
    SELECT 1.0 AS multiplier  -- TODO: 替换为实际的合约乘数
)
SELECT 
    side,
    SUM(quantity) AS buy_volume_contracts,  -- 合约张数
    SUM(quantity) * (SELECT multiplier FROM contract_multiplier) AS buy_volume_coins,  -- 币数量
    SUM(price * quantity * (SELECT multiplier FROM contract_multiplier)) AS buy_trade_value  -- 市值
FROM xt_trade_update
WHERE account_id = 'account_008'
  AND symbol = 'tradoor_usdt'
  AND update_time >= (SELECT ts FROM today_start)
  AND side = 'BUY'
GROUP BY side

UNION ALL

SELECT 
    side,
    SUM(quantity) AS sell_volume_contracts,  -- 合约张数
    SUM(quantity) * (SELECT multiplier FROM contract_multiplier) AS sell_volume_coins,  -- 币数量
    SUM(price * quantity * (SELECT multiplier FROM contract_multiplier)) AS sell_trade_value  -- 市值
FROM xt_trade_update
WHERE account_id = 'account_008'
  AND symbol = 'tradoor_usdt'
  AND update_time >= (SELECT ts FROM today_start)
  AND side = 'SELL'
GROUP BY side;
```

## 5. 查看历史累计已实现盈亏

```sql
-- 查看今天之前的所有已实现盈亏记录（按天分组，取每天最后一条）
WITH today_start AS (
    SELECT DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')::timestamp AS ts
),
daily_max_timestamp AS (
    SELECT 
        DATE(timestamp) AS date,
        MAX(timestamp) AS max_timestamp
    FROM position_metrics
    WHERE account_id = 'account_008'
      AND exchange = 'xt'
      AND symbol = 'tradoor_usdt'
      AND timestamp < (SELECT ts FROM today_start)
    GROUP BY DATE(timestamp)
)
SELECT 
    DATE(p.timestamp) AS date,
    p.timestamp,
    p.realized_pnl AS daily_realized_pnl,  -- 该天完整一天的已实现盈亏
    SUM(p.realized_pnl) OVER (ORDER BY p.timestamp) AS cumulative_realized_pnl  -- 累计已实现盈亏
FROM position_metrics p
JOIN daily_max_timestamp d
    ON DATE(p.timestamp) = d.date
    AND p.timestamp = d.max_timestamp
WHERE p.account_id = 'account_008'
  AND p.exchange = 'xt'
  AND p.symbol = 'tradoor_usdt'
ORDER BY p.timestamp;
```

## 6. 验证累计 PnL 计算

```sql
-- 验证累计 PnL = 历史累计已实现盈亏 + 今天的已实现盈亏 + 今天的未实现盈亏
WITH today_start AS (
    SELECT DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')::timestamp AS ts
),
historical_realized_pnl AS (
    -- 历史累计已实现盈亏（今天之前的所有天，每天取最后一条）
    SELECT COALESCE(SUM(daily_realized_pnl), 0) AS total
    FROM (
        SELECT DISTINCT ON (DATE(timestamp))
            realized_pnl AS daily_realized_pnl
        FROM position_metrics
        WHERE account_id = 'account_008'
          AND exchange = 'xt'
          AND symbol = 'tradoor_usdt'
          AND timestamp < (SELECT ts FROM today_start)
        ORDER BY DATE(timestamp), timestamp DESC
    ) AS daily_max
),
today_metrics AS (
    -- 今天的指标（最新一条）
    SELECT 
        realized_pnl,
        unrealized_pnl
    FROM position_metrics
    WHERE account_id = 'account_008'
      AND exchange = 'xt'
      AND symbol = 'tradoor_usdt'
      AND timestamp >= (SELECT ts FROM today_start)
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT 
    h.total AS historical_cumulative_realized_pnl,
    t.realized_pnl AS today_realized_pnl,
    t.unrealized_pnl AS today_unrealized_pnl,
    h.total + t.realized_pnl + t.unrealized_pnl AS calculated_cumulative_pnl,
    (SELECT cumulative_pnl FROM today_metrics ORDER BY timestamp DESC LIMIT 1) AS stored_cumulative_pnl,
    (h.total + t.realized_pnl + t.unrealized_pnl) - 
    (SELECT cumulative_pnl FROM today_metrics ORDER BY timestamp DESC LIMIT 1) AS difference
FROM historical_realized_pnl h
CROSS JOIN today_metrics t;
```

## 7. 查看合约乘数（需要从 XT API 获取）

```sql
-- 注意：合约乘数存储在代码中，不在数据库
-- 可以通过以下方式获取：
-- 1. 查看 XT API 响应：https://fapi.xt.com/future/market/v1/public/symbol/detail?symbol=tradoor_usdt
-- 2. 查看 contractSize 字段
-- 3. 或者查看代码中的 ContractMultiplierService

-- 这里提供一个查询，用于验证计算时使用的合约乘数是否正确
-- 假设合约乘数为 1，如果计算结果不对，可能需要检查合约乘数

-- 验证：如果合约乘数 = 1，那么币数量 = 合约张数
-- 如果合约乘数 ≠ 1，需要乘以合约乘数
```

## 8. 完整验证流程

```sql
-- 综合验证：对比计算值和存储值
WITH today_start AS (
    SELECT DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')::timestamp AS ts
),
latest_metrics AS (
    SELECT *
    FROM position_metrics
    WHERE account_id = 'account_008'
      AND exchange = 'xt'
      AND symbol = 'tradoor_usdt'
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT 
    '存储的指标' AS source,
    pre_long_qty,
    pre_short_qty,
    long_qty,
    short_qty,
    realized_pnl,
    unrealized_pnl,
    daily_pnl,
    cumulative_pnl
FROM latest_metrics

UNION ALL

-- 这里可以添加计算值进行对比
SELECT 
    '计算值（需要手动计算）' AS source,
    0 AS pre_long_qty,  -- TODO: 从初始持仓计算
    0 AS pre_short_qty,  -- TODO: 从初始持仓计算
    0 AS long_qty,  -- TODO: 从交易记录计算
    0 AS short_qty,  -- TODO: 从交易记录计算
    0 AS realized_pnl,  -- TODO: 从交易记录计算
    0 AS unrealized_pnl,  -- TODO: 从持仓和价格计算
    0 AS daily_pnl,  -- TODO: realized + unrealized
    0 AS cumulative_pnl;  -- TODO: 历史累计 + 今日
```

## 使用说明

1. **合约乘数**：需要从 XT API 获取 `tradoor_usdt` 的 `contractSize`，或查看代码中的 `ContractMultiplierService`
2. **时间范围**：所有查询使用 UTC 时间，确保时区正确
3. **验证步骤**：
   - 先查看最新的 `position_metrics` 记录
   - 验证初始持仓是否正确（从 `xt_position_update` 表）
   - 验证今日交易量是否正确（从 `xt_trade_update` 表）
   - 验证累计 PnL 计算是否正确

## 常见问题

1. **合约乘数在哪里？**
   - 代码中：`src/tri_arb/services/contract_multiplier_service.py`
   - XT API：`https://fapi.xt.com/future/market/v1/public/symbol/detail?symbol=tradoor_usdt`

2. **为什么需要合约乘数？**
   - XT 返回的 `quantity` 是合约张数
   - 需要乘以合约乘数才能得到币数量
   - 币数量用于计算市值和盈亏

3. **如何验证计算是否正确？**
   - 对比 SQL 查询结果和 `position_metrics` 表中的存储值
   - 检查是否有重复计算或遗漏

