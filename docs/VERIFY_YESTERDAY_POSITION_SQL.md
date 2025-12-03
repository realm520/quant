# 验证昨收持仓 SQL 查询文档

用于验证 `pre_long_qty`、`pre_short_qty`、`pre_long_value`、`pre_short_value` 的计算是否正确。

## 数据表说明

- **XT 持仓表**: `xt_position_update`
- **XT 成交表**: `xt_trade_update`
- **账号ID**: `account_008`
- **交易对**: `iota_usdt`
- **统计日期**: 2025-12-02（昨日）
- **initial_long_qty 查询时间点**: 2025-12-02 00:00:00 UTC **之前**
- **buy_volume 查询区间**: 2025-12-02 00:00:00 UTC ~ 2025-12-02 24:00:00 UTC（昨日一整天）

## 计算公式

**昨日持仓量**（以12月2日为例）：
```
pre_long_qty = initial_long_qty + buy_volume
pre_short_qty = initial_short_qty + sell_volume
pre_long_value = initial_long_value + buy_trade_value
pre_short_value = initial_short_value + sell_trade_value
```

其中：
- `initial_long_qty` / `initial_short_qty`: **昨日 00:00 UTC 之前**最后一次持仓记录（例如：12月2日 00:00 之前）
- `buy_volume` / `sell_volume`: **昨日一整天**的成交数量（例如：12月2日 00:00 ~ 12月2日 24:00）
- `initial_long_value` / `initial_short_value`: 昨日 00:00 之前的持仓市值（持仓量 × 开仓均价 × 合约乘数）
- `buy_trade_value` / `sell_trade_value`: 昨日一整天的成交市值（价格 × 数量 × 合约乘数）

**重要**：`initial_long_qty` 的时间点是**昨日 00:00 之前**，`buy_volume` 的时间区间是**昨日 00:00 ~ 昨日 24:00**。

## SQL 查询

### 1. 查询昨日 00:00 之前的持仓（initial_long_qty, initial_short_qty）

```sql
-- 找到每个 symbol + side 在昨日 00:00 之前最后一次持仓记录
-- 例如：12月2日的持仓量，需要找 12月2日 00:00 之前的最后一笔持仓
WITH latest_positions AS (
    SELECT 
        symbol,
        side,
        MAX(update_time) AS max_time
    FROM xt_position_update
    WHERE account_id = 'account_008'
      AND symbol = 'iota_usdt'
      AND update_time < '2025-12-02 00:00:00'::timestamp  -- 昨日 00:00 之前
      AND quantity > 0
    GROUP BY symbol, side
)
SELECT 
    p.symbol,
    p.side,
    p.quantity AS initial_qty,
    p.entry_price,
    p.update_time
FROM xt_position_update p
INNER JOIN latest_positions lp
    ON p.symbol = lp.symbol
    AND p.side = lp.side
    AND p.update_time = lp.max_time
WHERE p.account_id = 'account_008'
  AND p.quantity > 0
ORDER BY p.side;
```

**预期结果示例**:
```
symbol      | side | initial_qty | entry_price | update_time
------------+------+-------------+-------------+-------------------
iota_usdt   | LONG | 15428.0     | 0.104       | 2025-12-02 23:59:xx
iota_usdt   | SHORT| 53.0        | 0.104       | 2025-12-02 23:59:xx
```

### 2. 查询昨日一整天的成交量（buy_volume, sell_volume）

```sql
-- 统计昨日一整天（00:00 ~ 24:00）的所有成交记录的成交量
SELECT 
    side,
    SUM(quantity) AS total_volume
FROM xt_trade_update
WHERE account_id = 'account_008'
  AND symbol = 'iota_usdt'
  AND update_time >= '2025-12-02 00:00:00'::timestamp  -- 昨日 00:00
  AND update_time < '2025-12-03 00:00:00'::timestamp  -- 昨日 24:00（即今日 00:00）
GROUP BY side
ORDER BY side;
```

**预期结果示例**:
```
side | total_volume
-----+-------------
BUY  | 978728.0
SELL | 981019.0
```

### 3. 查询昨日一整天的成交市值（buy_trade_value, sell_trade_value）

```sql
-- 计算昨日一整天成交的市值（价格 × 数量 × 合约乘数）
-- 注意：合约乘数需要根据实际情况设置，大多数情况下为 1
SELECT 
    side,
    SUM(price * quantity * 1) AS total_trade_value  -- 合约乘数 = 1（需要根据实际情况调整）
FROM xt_trade_update
WHERE account_id = 'account_008'
  AND symbol = 'iota_usdt'
  AND update_time >= '2025-12-02 00:00:00'::timestamp  -- 昨日 00:00
  AND update_time < '2025-12-03 00:00:00'::timestamp  -- 昨日 24:00（即今日 00:00）
GROUP BY side
ORDER BY side;
```

**预期结果示例**:
```
side | total_trade_value
-----+------------------
BUY  | 102079.1411
SELL | 102318.8645
```

### 4. 计算昨日 00:00 之前的持仓市值（initial_long_value, initial_short_value）

```sql
-- 计算昨日 00:00 之前的持仓市值（持仓量 × 开仓均价 × 合约乘数）
WITH latest_positions AS (
    SELECT 
        symbol,
        side,
        MAX(update_time) AS max_time
    FROM xt_position_update
    WHERE account_id = 'account_008'
      AND symbol = 'iota_usdt'
      AND update_time < '2025-12-02 00:00:00'::timestamp  -- 昨日 00:00 之前
      AND quantity > 0
    GROUP BY symbol, side
)
SELECT 
    p.side,
    p.quantity AS initial_qty,
    p.entry_price,
    p.quantity * p.entry_price * 1 AS initial_value  -- 合约乘数 = 1（需要根据实际情况调整）
FROM xt_position_update p
INNER JOIN latest_positions lp
    ON p.symbol = lp.symbol
    AND p.side = lp.side
    AND p.update_time = lp.max_time
WHERE p.account_id = 'account_008'
  AND p.quantity > 0
ORDER BY p.side;
```

**预期结果示例**:
```
side  | initial_qty | entry_price | initial_value
------+-------------+-------------+---------------
LONG  | 15428.0     | 0.104       | 1604.512
SHORT | 53.0        | 0.104       | 5.512
```

### 5. 完整验证：计算昨收持仓（pre_long_qty, pre_short_qty, pre_long_value, pre_short_value）

```sql
-- 完整的验证查询：计算昨收持仓的所有指标
WITH 
-- 1. 昨日 00:00 之前的持仓
initial_positions AS (
    WITH latest_positions AS (
        SELECT 
            symbol,
            side,
            MAX(update_time) AS max_time
        FROM xt_position_update
        WHERE account_id = 'account_008'
          AND symbol = 'iota_usdt'
          AND update_time < '2025-12-02 00:00:00'::timestamp  -- 昨日 00:00 之前
          AND quantity > 0
        GROUP BY symbol, side
    )
    SELECT 
        p.side,
        p.quantity AS initial_qty,
        p.entry_price,
        p.quantity * p.entry_price * 1 AS initial_value  -- 合约乘数 = 1
    FROM xt_position_update p
    INNER JOIN latest_positions lp
        ON p.symbol = lp.symbol
        AND p.side = lp.side
        AND p.update_time = lp.max_time
    WHERE p.account_id = 'account_008'
      AND p.quantity > 0
),
-- 2. 昨日一整天的成交统计
trade_stats AS (
    SELECT 
        side,
        SUM(quantity) AS total_volume,
        SUM(price * quantity * 1) AS total_trade_value  -- 合约乘数 = 1
    FROM xt_trade_update
    WHERE account_id = 'account_008'
      AND symbol = 'iota_usdt'
      AND update_time >= '2025-12-02 00:00:00'::timestamp  -- 昨日 00:00
      AND update_time < '2025-12-03 00:00:00'::timestamp  -- 昨日 24:00（即今日 00:00）
    GROUP BY side
)
-- 3. 汇总计算
SELECT 
    COALESCE(SUM(CASE WHEN ip.side = 'LONG' THEN ip.initial_qty ELSE 0 END), 0) AS initial_long_qty,
    COALESCE(SUM(CASE WHEN ip.side = 'SHORT' THEN ip.initial_qty ELSE 0 END), 0) AS initial_short_qty,
    COALESCE(SUM(CASE WHEN ip.side = 'LONG' THEN ip.initial_value ELSE 0 END), 0) AS initial_long_value,
    COALESCE(SUM(CASE WHEN ip.side = 'SHORT' THEN ip.initial_value ELSE 0 END), 0) AS initial_short_value,
    COALESCE(SUM(CASE WHEN ts.side = 'BUY' THEN ts.total_volume ELSE 0 END), 0) AS buy_volume,
    COALESCE(SUM(CASE WHEN ts.side = 'SELL' THEN ts.total_volume ELSE 0 END), 0) AS sell_volume,
    COALESCE(SUM(CASE WHEN ts.side = 'BUY' THEN ts.total_trade_value ELSE 0 END), 0) AS buy_trade_value,
    COALESCE(SUM(CASE WHEN ts.side = 'SELL' THEN ts.total_trade_value ELSE 0 END), 0) AS sell_trade_value,
    -- 计算昨收持仓
    COALESCE(SUM(CASE WHEN ip.side = 'LONG' THEN ip.initial_qty ELSE 0 END), 0) + 
    COALESCE(SUM(CASE WHEN ts.side = 'BUY' THEN ts.total_volume ELSE 0 END), 0) AS pre_long_qty,
    COALESCE(SUM(CASE WHEN ip.side = 'SHORT' THEN ip.initial_qty ELSE 0 END), 0) + 
    COALESCE(SUM(CASE WHEN ts.side = 'SELL' THEN ts.total_volume ELSE 0 END), 0) AS pre_short_qty,
    COALESCE(SUM(CASE WHEN ip.side = 'LONG' THEN ip.initial_value ELSE 0 END), 0) + 
    COALESCE(SUM(CASE WHEN ts.side = 'BUY' THEN ts.total_trade_value ELSE 0 END), 0) AS pre_long_value,
    COALESCE(SUM(CASE WHEN ip.side = 'SHORT' THEN ip.initial_value ELSE 0 END), 0) + 
    COALESCE(SUM(CASE WHEN ts.side = 'SELL' THEN ts.total_trade_value ELSE 0 END), 0) AS pre_short_value
FROM initial_positions ip
FULL OUTER JOIN trade_stats ts ON TRUE;
```

**预期结果**:
```
initial_long_qty | initial_short_qty | initial_long_value | initial_short_value | buy_volume | sell_volume | buy_trade_value | sell_trade_value | pre_long_qty | pre_short_qty | pre_long_value | pre_short_value
-----------------+-------------------+--------------------+---------------------+------------+-------------+-----------------+------------------+--------------+---------------+----------------+-----------------
15428.0          | 53.0              | 1604.512           | 5.512               | 978728.0   | 981019.0    | 102079.1411     | 102318.8645      | 994156.0      | 981072.0      | 103683.6531    | 102324.3712
```

## 验证步骤

1. **执行查询 1**：检查 `initial_long_qty` 和 `initial_short_qty` 是否正确
2. **执行查询 2**：检查 `buy_volume` 和 `sell_volume` 是否正确
3. **执行查询 3**：检查 `buy_trade_value` 和 `sell_trade_value` 是否正确（注意合约乘数）
4. **执行查询 4**：检查 `initial_long_value` 和 `initial_short_value` 是否正确
5. **执行查询 5**：完整验证所有指标，确认 `pre_long_qty`、`pre_short_qty`、`pre_long_value`、`pre_short_value` 的计算结果

## 使用调试脚本验证

也可以使用调试脚本直接验证：

```bash
python scripts/debug_yesterday_position.py --exchange xt --account-id account_008 --symbol iota_usdt
```

这个脚本会：
1. 计算昨日（12月2日）的持仓量
2. 显示 `initial_long_qty`、`buy_volume`、`pre_long_qty` 等所有指标
3. 自动验证公式：`pre_long_qty = initial_long_qty + buy_volume`
4. 如果公式验证失败，会显示差异值

## 注意事项

1. **合约乘数**：SQL 中使用了 `* 1` 作为合约乘数，实际使用时需要根据交易对的合约乘数调整。可以通过以下方式获取：
   ```sql
   -- 从交易对配置中获取合约乘数（如果有相关表）
   -- 或者从 XT API 的 symbol/detail 接口获取 contractSize 字段
   ```

2. **时间精度**：确保时间戳的精度匹配，包括时区（UTC+0）

3. **数据完整性**：确保区间开始时间之前有持仓记录，否则 `initial_*` 值可能为 0

4. **账号ID 和交易对**：根据实际需要修改 `account_id` 和 `symbol` 参数

## 常见问题

### Q: 为什么 `initial_long_qty` 和 `initial_short_qty` 为 0？
A: 可能原因：
- 区间开始时间之前没有持仓记录
- `account_id` 或 `symbol` 不匹配
- 持仓记录的 `quantity` 为 0 或负数

### Q: 为什么 `buy_volume` 和 `sell_volume` 为 0？
A: 可能原因：
- 区间内没有成交记录
- 时间范围不正确
- `account_id` 或 `symbol` 不匹配

### Q: 合约乘数在哪里获取？
A: 合约乘数（contractSize）可以通过：
- XT API: `GET /future/market/v1/public/symbol/detail` 返回的 `contractSize` 字段
- 大多数 USDT 永续合约的合约乘数为 1

