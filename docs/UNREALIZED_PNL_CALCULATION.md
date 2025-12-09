# 未实现盈亏（Unrealized PnL）计算文档

本文档详细说明系统中未实现盈亏的计算方法，并提供 SQL 验证查询。

## 目录

1. [计算方法概述](#计算方法概述)
2. [方法一：基于持仓和平均价格](#方法一基于持仓和平均价格)
3. [方法二：基于成交记录（FIFO）](#方法二基于成交记录fifo)
4. [SQL 验证查询](#sql-验证查询)

---

## 计算方法概述

系统中未实现盈亏有两种计算方式，适用于不同场景：

| 方法 | 适用场景 | 数据来源 | 代码位置 |
|------|---------|---------|---------|
| **方法一：基于持仓和平均价格** | 持仓指标计算（position_metrics） | 成交记录 + 持仓快照 | `position_calculator.py` |
| **方法二：基于成交记录（FIFO）** | 增量计算、实时更新 | 成交记录（FIFO 队列） | `position_metrics_scheduler.py` |

---

## 方法一：基于持仓和平均价格

### 计算公式

```python
unrealized_pnl = left_long_qty * (close_prz - avg_buy_prz) + 
                 left_short_qty * (avg_sell_prz - close_prz)
```

### 变量说明

- `left_long_qty`: 剩余多头持仓量（已轧差后的剩余）
- `left_short_qty`: 剩余空头持仓量（已轧差后的剩余）
- `avg_buy_prz`: 买入平均价格 = `long_value / long_qty`
- `avg_sell_prz`: 卖出平均价格 = `short_value / short_qty`
- `close_prz`: 当日最后一笔成交价格

### 计算步骤

1. **计算剩余持仓**：
   ```python
   matched_qty = min(long_qty, short_qty)
   left_long_qty = long_qty - matched_qty
   left_short_qty = short_qty - matched_qty
   ```

2. **计算平均价格**：
   ```python
   avg_buy_prz = long_value / long_qty  # 当 long_qty > 0
   avg_sell_prz = short_value / short_qty  # 当 short_qty > 0
   ```
   其中：
   - `long_value = initial_long_value + buy_trade_value`
   - `short_value = initial_short_value + sell_trade_value`
   - `long_qty = initial_long_qty + buy_volume`
   - `short_qty = initial_short_qty + sell_volume`

3. **获取最后一笔成交价**：
   ```python
   close_prz = 当日最后一笔成交的价格
   ```

4. **计算未实现盈亏**：
   ```python
   多头未实现盈亏 = left_long_qty * (close_prz - avg_buy_prz)
   空头未实现盈亏 = left_short_qty * (avg_sell_prz - close_prz)
   总未实现盈亏 = 多头未实现盈亏 + 空头未实现盈亏
   ```

### 代码位置

- `src/tri_arb/services/position_calculator.py` (第 204-210 行)
- `src/tri_arb/services/position_calculator.py` (第 433-438 行，按 symbol 计算)

### 代码实现

```204:210:src/tri_arb/services/position_calculator.py
        # 10. 计算未实现盈亏
        unrealized_pnl = Decimal("0")
        if close_prz > 0:
            unrealized_pnl = (
                left_long_qty * (close_prz - avg_buy_prz) +
                left_short_qty * (avg_sell_prz - close_prz)
            )
```

---

## 方法二：基于成交记录（FIFO）

### 计算公式

使用 FIFO（先进先出）方法，逐笔处理成交记录：

```python
long_unrealized = sum(qty * (current_price - entry_price) for qty, entry_price in long_positions)
short_unrealized = sum(qty * (entry_price - current_price) for qty, entry_price in short_positions)
total_unrealized = long_unrealized + short_unrealized
```

### 计算逻辑

1. **初始化持仓队列**：
   - `long_positions`: 多头持仓队列 `[(数量, 开仓价格), ...]`
   - `short_positions`: 空头持仓队列 `[(数量, 开仓价格), ...]`

2. **处理成交记录**（按时间顺序）：
   - **买单（BUY）**：
     - 先与空头持仓队列轧差（FIFO）
     - 剩余部分加入多头持仓队列
   - **卖单（SELL）**：
     - 先与多头持仓队列轧差（FIFO）
     - 剩余部分加入空头持仓队列

3. **计算未实现盈亏**：
   - 对剩余的多头持仓：`数量 × (当前价格 - 开仓价格)`
   - 对剩余的空头持仓：`数量 × (开仓价格 - 当前价格)`

### 代码位置

- `src/tri_arb/services/position_metrics_scheduler.py` (第 777-936 行)

### 代码实现

```910:912:src/tri_arb/services/position_metrics_scheduler.py
            # 计算未实现盈亏
            long_unrealized = sum(qty * (current_price - price) for qty, price in long_positions)
            short_unrealized = sum(qty * (price - current_price) for qty, price in short_positions)
            total_unrealized = long_unrealized + short_unrealized
```

### 处理成交记录的代码

```884:907:src/tri_arb/services/position_metrics_scheduler.py
                if side == "BUY":
                    remaining = quantity_coins
                    while remaining > 0 and short_positions:
                        short_qty, short_price = short_positions[0]
                        if short_qty <= remaining:
                            remaining -= short_qty
                            short_positions.pop(0)
                        else:
                            short_positions[0] = (short_qty - remaining, short_price)
                            remaining = Decimal("0")
                    if remaining > 0:
                        long_positions.append((remaining, price))
                elif side == "SELL":
                    remaining = quantity_coins
                    while remaining > 0 and long_positions:
                        long_qty, long_price = long_positions[0]
                        if long_qty <= remaining:
                            remaining -= long_qty
                            long_positions.pop(0)
                        else:
                            long_positions[0] = (long_qty - remaining, long_price)
                            remaining = Decimal("0")
                    if remaining > 0:
                        short_positions.append((remaining, price))
```

### 示例

假设有以下成交记录（按时间顺序）：

| 时间 | 方向 | 价格 | 数量 |
|------|------|------|------|
| 10:00 | BUY | 100 | 10 |
| 10:30 | SELL | 105 | 5 |
| 11:00 | BUY | 110 | 8 |
| 11:30 | SELL | 108 | 12 |

当前价格 = 115

**处理过程**：

1. 10:00 BUY 100 × 10 → 多头队列：`[(10, 100)]`
2. 10:30 SELL 105 × 5 → 与多头轧差 5，剩余多头：`[(5, 100)]`，已实现盈亏：`5 × (105 - 100) = 25`
3. 11:00 BUY 110 × 8 → 多头队列：`[(5, 100), (8, 110)]`
4. 11:30 SELL 108 × 12 → 先与 `(5, 100)` 轧差 5，再与 `(8, 110)` 轧差 7，剩余空头：`[(1, 108)]`，已实现盈亏：`5 × (108 - 100) + 7 × (108 - 110) = 40 - 14 = 26`

**最终持仓**：
- 多头：`[(1, 110)]`（从 `(8, 110)` 剩余 1）
- 空头：`[(1, 108)]`

**未实现盈亏**：
- 多头：`1 × (115 - 110) = 5`
- 空头：`1 × (108 - 115) = -7`
- 总计：`5 + (-7) = -2`

---

## SQL 验证查询

### 验证方法一：基于持仓和平均价格

#### 1. 查询剩余持仓和平均价格

**XT 交易所**：

```sql
-- 查询指定账号和交易对的剩余持仓
WITH position_metrics AS (
    SELECT 
        account_id,
        symbol,
        timestamp,
        left_long_qty,
        left_short_qty,
        avg_buy_prz,
        avg_sell_prz,
        close_prz,
        unrealized_pnl
    FROM position_metrics
    WHERE account_id = 'account_006ktmm1'
      AND exchange = 'xt'
      AND symbol = 'trump_usdt'
      AND timestamp >= CURRENT_DATE - INTERVAL '1 day'
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT 
    account_id,
    symbol,
    timestamp,
    left_long_qty,
    left_short_qty,
    avg_buy_prz,
    avg_sell_prz,
    close_prz,
    unrealized_pnl AS stored_unrealized_pnl,
    -- 手动计算未实现盈亏
    (left_long_qty * (close_prz - avg_buy_prz) + 
     left_short_qty * (avg_sell_prz - close_prz)) AS calculated_unrealized_pnl,
    -- 验证差异
    unrealized_pnl - (left_long_qty * (close_prz - avg_buy_prz) + 
                      left_short_qty * (avg_sell_prz - close_prz)) AS difference
FROM position_metrics;
```

**Binance 交易所**：

```sql
-- Binance 交易所的验证查询（类似，但表名不同）
WITH position_metrics AS (
    SELECT 
        account_id,
        symbol,
        timestamp,
        left_long_qty,
        left_short_qty,
        avg_buy_prz,
        avg_sell_prz,
        close_prz,
        unrealized_pnl
    FROM position_metrics
    WHERE account_id = 'your_account_id'
      AND exchange = 'binance'
      AND symbol = 'BTCUSDT'
      AND timestamp >= CURRENT_DATE - INTERVAL '1 day'
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT 
    account_id,
    symbol,
    timestamp,
    left_long_qty,
    left_short_qty,
    avg_buy_prz,
    avg_sell_prz,
    close_prz,
    unrealized_pnl AS stored_unrealized_pnl,
    (left_long_qty * (close_prz - avg_buy_prz) + 
     left_short_qty * (avg_sell_prz - close_prz)) AS calculated_unrealized_pnl,
    unrealized_pnl - (left_long_qty * (close_prz - avg_buy_prz) + 
                      left_short_qty * (avg_sell_prz - close_prz)) AS difference
FROM position_metrics;
```

#### 2. 验证平均价格计算

```sql
-- 验证买入平均价格（XT 交易所）
WITH buy_trades AS (
    SELECT 
        account_id,
        symbol,
        SUM(quantity) AS total_buy_qty,
        SUM(price * quantity) AS total_buy_value,
        SUM(price * quantity) / NULLIF(SUM(quantity), 0) AS calculated_avg_buy_prz
    FROM xt_trade_update
    WHERE account_id = 'account_006ktmm1'
      AND symbol = 'trump_usdt'
      AND side = 'BUY'
      AND update_time >= CURRENT_DATE
    GROUP BY account_id, symbol
)
SELECT 
    account_id,
    symbol,
    total_buy_qty,
    total_buy_value,
    calculated_avg_buy_prz,
    -- 与 position_metrics 中的 avg_buy_prz 对比
    (SELECT avg_buy_prz 
     FROM position_metrics 
     WHERE account_id = bt.account_id 
       AND symbol = bt.symbol 
       AND exchange = 'xt'
       AND timestamp >= CURRENT_DATE 
     ORDER BY timestamp DESC LIMIT 1) AS stored_avg_buy_prz,
    -- 差异
    calculated_avg_buy_prz - (SELECT avg_buy_prz 
                              FROM position_metrics 
                              WHERE account_id = bt.account_id 
                                AND symbol = bt.symbol 
                                AND exchange = 'xt'
                                AND timestamp >= CURRENT_DATE 
                              ORDER BY timestamp DESC LIMIT 1) AS difference
FROM buy_trades bt;
```

#### 3. 验证最后一笔成交价

```sql
-- 查询最后一笔成交价（XT 交易所）
SELECT 
    account_id,
    symbol,
    price AS close_prz,
    update_time
FROM xt_trade_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= CURRENT_DATE
ORDER BY update_time DESC
LIMIT 1;
```

```sql
-- 查询最后一笔成交价（Binance 交易所）
SELECT 
    account_id,
    symbol,
    price AS close_prz,
    transaction_time
FROM binance_trade_update
WHERE account_id = 'your_account_id'
  AND symbol = 'BTCUSDT'
  AND exchange = 'binance_perp'
  AND transaction_time >= CURRENT_DATE
ORDER BY transaction_time DESC
LIMIT 1;
```

#### 4. 验证剩余持仓计算

```sql
-- 验证剩余持仓（XT 交易所）
WITH trade_stats AS (
    SELECT 
        account_id,
        symbol,
        -- 买入总量
        SUM(CASE WHEN side = 'BUY' THEN quantity ELSE 0 END) AS buy_volume,
        -- 卖出总量
        SUM(CASE WHEN side = 'SELL' THEN quantity ELSE 0 END) AS sell_volume
    FROM xt_trade_update
    WHERE account_id = 'account_006ktmm1'
      AND symbol = 'trump_usdt'
      AND update_time >= CURRENT_DATE
    GROUP BY account_id, symbol
),
initial_positions AS (
    -- 获取区间开始时的持仓（需要根据实际情况调整）
    SELECT 
        account_id,
        symbol,
        SUM(CASE WHEN side = 'LONG' THEN quantity ELSE 0 END) AS initial_long_qty,
        SUM(CASE WHEN side = 'SHORT' THEN quantity ELSE 0 END) AS initial_short_qty
    FROM xt_position_update
    WHERE account_id = 'account_006ktmm1'
      AND symbol = 'trump_usdt'
      AND update_time < CURRENT_DATE
      AND update_time >= CURRENT_DATE - INTERVAL '1 day'
    GROUP BY account_id, symbol
)
SELECT 
    ts.account_id,
    ts.symbol,
    COALESCE(ip.initial_long_qty, 0) AS initial_long_qty,
    COALESCE(ip.initial_short_qty, 0) AS initial_short_qty,
    ts.buy_volume,
    ts.sell_volume,
    COALESCE(ip.initial_long_qty, 0) + ts.buy_volume AS long_qty,
    COALESCE(ip.initial_short_qty, 0) + ts.sell_volume AS short_qty,
    LEAST(COALESCE(ip.initial_long_qty, 0) + ts.buy_volume, 
          COALESCE(ip.initial_short_qty, 0) + ts.sell_volume) AS matched_qty,
    (COALESCE(ip.initial_long_qty, 0) + ts.buy_volume) - 
    LEAST(COALESCE(ip.initial_long_qty, 0) + ts.buy_volume, 
          COALESCE(ip.initial_short_qty, 0) + ts.sell_volume) AS calculated_left_long_qty,
    (COALESCE(ip.initial_short_qty, 0) + ts.sell_volume) - 
    LEAST(COALESCE(ip.initial_long_qty, 0) + ts.buy_volume, 
          COALESCE(ip.initial_short_qty, 0) + ts.sell_volume) AS calculated_left_short_qty,
    -- 与 position_metrics 中的值对比
    (SELECT left_long_qty 
     FROM position_metrics 
     WHERE account_id = ts.account_id 
       AND symbol = ts.symbol 
       AND exchange = 'xt'
       AND timestamp >= CURRENT_DATE 
     ORDER BY timestamp DESC LIMIT 1) AS stored_left_long_qty,
    (SELECT left_short_qty 
     FROM position_metrics 
     WHERE account_id = ts.account_id 
       AND symbol = ts.symbol 
       AND exchange = 'xt'
       AND timestamp >= CURRENT_DATE 
     ORDER BY timestamp DESC LIMIT 1) AS stored_left_short_qty
FROM trade_stats ts
LEFT JOIN initial_positions ip ON ts.account_id = ip.account_id AND ts.symbol = ip.symbol;
```

---

### 验证方法二：基于成交记录（FIFO）

#### 1. 查询所有成交记录（按时间排序）

```sql
-- 查询指定时间范围内的所有成交记录（XT 交易所）
SELECT 
    update_time,
    side,
    price,
    quantity,
    -- 计算合约乘数（大多数 USDT 永续合约为 1）
    quantity * 1 AS quantity_coins
FROM xt_trade_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= '2025-01-01 00:00:00'
  AND update_time <= '2025-01-01 23:59:59'
ORDER BY update_time ASC;
```

```sql
-- 查询指定时间范围内的所有成交记录（Binance 交易所）
SELECT 
    transaction_time,
    side,
    price,
    quantity,
    quantity * 1 AS quantity_coins
FROM binance_trade_update
WHERE account_id = 'your_account_id'
  AND symbol = 'BTCUSDT'
  AND exchange = 'binance_perp'
  AND transaction_time >= '2025-01-01 00:00:00'
  AND transaction_time <= '2025-01-01 23:59:59'
ORDER BY transaction_time ASC;
```

#### 2. 验证 FIFO 计算的中间结果

由于 FIFO 计算需要按顺序处理，SQL 难以直接实现完整的 FIFO 逻辑，但可以验证基础数据：

```sql
-- 统计成交记录总数和方向分布
SELECT 
    account_id,
    symbol,
    COUNT(*) AS total_trades,
    SUM(CASE WHEN side = 'BUY' THEN 1 ELSE 0 END) AS buy_count,
    SUM(CASE WHEN side = 'SELL' THEN 1 ELSE 0 END) AS sell_count,
    SUM(CASE WHEN side = 'BUY' THEN quantity ELSE 0 END) AS total_buy_qty,
    SUM(CASE WHEN side = 'SELL' THEN quantity ELSE 0 END) AS total_sell_qty,
    MIN(update_time) AS first_trade_time,
    MAX(update_time) AS last_trade_time
FROM xt_trade_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= CURRENT_DATE
GROUP BY account_id, symbol;
```

#### 3. 对比 position_metrics 中的未实现盈亏

```sql
-- 对比 position_metrics 中的未实现盈亏（方法二的结果）
SELECT 
    account_id,
    exchange,
    symbol,
    timestamp,
    unrealized_pnl,
    left_long_qty,
    left_short_qty,
    close_prz
FROM position_metrics
WHERE account_id = 'account_006ktmm1'
  AND exchange = 'xt'
  AND symbol = 'trump_usdt'
  AND timestamp >= CURRENT_DATE
ORDER BY timestamp DESC
LIMIT 10;
```

---

## 完整验证流程

### 步骤 1：验证基础数据

```sql
-- 1. 验证成交记录完整性（XT 交易所）
SELECT 
    COUNT(*) AS trade_count,
    MIN(update_time) AS first_trade,
    MAX(update_time) AS last_trade,
    SUM(CASE WHEN side = 'BUY' THEN quantity ELSE 0 END) AS total_buy_qty,
    SUM(CASE WHEN side = 'SELL' THEN quantity ELSE 0 END) AS total_sell_qty
FROM xt_trade_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= CURRENT_DATE;
```

```sql
-- 2. 验证持仓记录（XT 交易所）
SELECT 
    COUNT(*) AS position_count,
    SUM(CASE WHEN side = 'LONG' THEN quantity ELSE 0 END) AS total_long_qty,
    SUM(CASE WHEN side = 'SHORT' THEN quantity ELSE 0 END) AS total_short_qty
FROM xt_position_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= CURRENT_DATE - INTERVAL '1 hour';
```

### 步骤 2：验证平均价格

```sql
-- 验证买入平均价格（XT 交易所）
WITH buy_stats AS (
    SELECT 
        SUM(quantity) AS total_qty,
        SUM(price * quantity) AS total_value,
        SUM(price * quantity) / NULLIF(SUM(quantity), 0) AS avg_price
    FROM xt_trade_update
    WHERE account_id = 'account_006ktmm1'
      AND symbol = 'trump_usdt'
      AND side = 'BUY'
      AND update_time >= CURRENT_DATE
)
SELECT 
    total_qty,
    total_value,
    avg_price AS calculated_avg_buy_prz,
    (SELECT avg_buy_prz 
     FROM position_metrics 
     WHERE account_id = 'account_006ktmm1'
       AND symbol = 'trump_usdt'
       AND exchange = 'xt'
       AND timestamp >= CURRENT_DATE
     ORDER BY timestamp DESC LIMIT 1) AS stored_avg_buy_prz,
    avg_price - (SELECT avg_buy_prz 
                 FROM position_metrics 
                 WHERE account_id = 'account_006ktmm1'
                   AND symbol = 'trump_usdt'
                   AND exchange = 'xt'
                   AND timestamp >= CURRENT_DATE
                 ORDER BY timestamp DESC LIMIT 1) AS difference
FROM buy_stats;
```

### 步骤 3：验证未实现盈亏

```sql
-- 综合验证：对比方法一的计算结果
WITH metrics_data AS (
    SELECT 
        timestamp,
        left_long_qty,
        left_short_qty,
        avg_buy_prz,
        avg_sell_prz,
        close_prz,
        unrealized_pnl AS stored_unrealized_pnl
    FROM position_metrics
    WHERE account_id = 'account_006ktmm1'
      AND exchange = 'xt'
      AND symbol = 'trump_usdt'
      AND timestamp >= CURRENT_DATE
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT 
    md.timestamp,
    md.left_long_qty,
    md.left_short_qty,
    md.avg_buy_prz,
    md.avg_sell_prz,
    md.close_prz,
    md.stored_unrealized_pnl,
    -- 方法一计算
    (md.left_long_qty * (md.close_prz - md.avg_buy_prz) + 
     md.left_short_qty * (md.avg_sell_prz - md.close_prz)) AS calculated_unrealized_pnl,
    -- 差异
    md.stored_unrealized_pnl - (md.left_long_qty * (md.close_prz - md.avg_buy_prz) + 
                                 md.left_short_qty * (md.avg_sell_prz - md.close_prz)) AS difference
FROM metrics_data md;
```

---

## 注意事项

1. **合约乘数**：
   - 大多数 USDT 永续合约的合约乘数为 1
   - 可通过 XT API 的 `symbol/detail` 接口获取 `contractSize` 字段
   - 计算时需要将合约张数转换为币数量：`币数量 = 合约张数 × 合约乘数`

2. **时间精度**：
   - 所有时间字段使用 UTC 时间
   - 计算时注意时区转换

3. **精度问题**：
   - 所有计算使用 `Decimal` 类型，避免浮点数精度问题
   - SQL 查询时使用 `NUMERIC` 类型进行计算

4. **数据完整性**：
   - 确保成交记录完整（无遗漏）
   - 确保持仓记录及时更新

5. **账号和交易对**：
   - 所有计算都按 `account_id` 和 `symbol` 分别进行
   - 不进行跨账号或跨交易对的汇总

6. **方法选择**：
   - **方法一**：用于批量计算和指标统计，基于平均价格，计算简单
   - **方法二**：用于增量计算和实时更新，基于 FIFO 队列，精度更高

---

## 相关文件

- `src/tri_arb/services/position_calculator.py`: 方法一实现
- `src/tri_arb/services/position_metrics_scheduler.py`: 方法二实现
- `docs/POSITION_CALCULATION_FORMULA.md`: 持仓计算完整公式文档

本文档详细说明系统中未实现盈亏的计算方法，并提供 SQL 验证查询。

## 目录

1. [计算方法概述](#计算方法概述)
2. [方法一：基于持仓和平均价格](#方法一基于持仓和平均价格)
3. [方法二：基于成交记录（FIFO）](#方法二基于成交记录fifo)
4. [SQL 验证查询](#sql-验证查询)

---

## 计算方法概述

系统中未实现盈亏有两种计算方式，适用于不同场景：

| 方法 | 适用场景 | 数据来源 | 代码位置 |
|------|---------|---------|---------|
| **方法一：基于持仓和平均价格** | 持仓指标计算（position_metrics） | 成交记录 + 持仓快照 | `position_calculator.py` |
| **方法二：基于成交记录（FIFO）** | 增量计算、实时更新 | 成交记录（FIFO 队列） | `position_metrics_scheduler.py` |

---

## 方法一：基于持仓和平均价格

### 计算公式

```python
unrealized_pnl = left_long_qty * (close_prz - avg_buy_prz) + 
                 left_short_qty * (avg_sell_prz - close_prz)
```

### 变量说明

- `left_long_qty`: 剩余多头持仓量（已轧差后的剩余）
- `left_short_qty`: 剩余空头持仓量（已轧差后的剩余）
- `avg_buy_prz`: 买入平均价格 = `long_value / long_qty`
- `avg_sell_prz`: 卖出平均价格 = `short_value / short_qty`
- `close_prz`: 当日最后一笔成交价格

### 计算步骤

1. **计算剩余持仓**：
   ```python
   matched_qty = min(long_qty, short_qty)
   left_long_qty = long_qty - matched_qty
   left_short_qty = short_qty - matched_qty
   ```

2. **计算平均价格**：
   ```python
   avg_buy_prz = long_value / long_qty  # 当 long_qty > 0
   avg_sell_prz = short_value / short_qty  # 当 short_qty > 0
   ```
   其中：
   - `long_value = initial_long_value + buy_trade_value`
   - `short_value = initial_short_value + sell_trade_value`
   - `long_qty = initial_long_qty + buy_volume`
   - `short_qty = initial_short_qty + sell_volume`

3. **获取最后一笔成交价**：
   ```python
   close_prz = 当日最后一笔成交的价格
   ```

4. **计算未实现盈亏**：
   ```python
   多头未实现盈亏 = left_long_qty * (close_prz - avg_buy_prz)
   空头未实现盈亏 = left_short_qty * (avg_sell_prz - close_prz)
   总未实现盈亏 = 多头未实现盈亏 + 空头未实现盈亏
   ```

### 代码位置

- `src/tri_arb/services/position_calculator.py` (第 204-210 行)
- `src/tri_arb/services/position_calculator.py` (第 433-438 行，按 symbol 计算)

### 代码实现

```204:210:src/tri_arb/services/position_calculator.py
        # 10. 计算未实现盈亏
        unrealized_pnl = Decimal("0")
        if close_prz > 0:
            unrealized_pnl = (
                left_long_qty * (close_prz - avg_buy_prz) +
                left_short_qty * (avg_sell_prz - close_prz)
            )
```

---

## 方法二：基于成交记录（FIFO）

### 计算公式

使用 FIFO（先进先出）方法，逐笔处理成交记录：

```python
long_unrealized = sum(qty * (current_price - entry_price) for qty, entry_price in long_positions)
short_unrealized = sum(qty * (entry_price - current_price) for qty, entry_price in short_positions)
total_unrealized = long_unrealized + short_unrealized
```

### 计算逻辑

1. **初始化持仓队列**：
   - `long_positions`: 多头持仓队列 `[(数量, 开仓价格), ...]`
   - `short_positions`: 空头持仓队列 `[(数量, 开仓价格), ...]`

2. **处理成交记录**（按时间顺序）：
   - **买单（BUY）**：
     - 先与空头持仓队列轧差（FIFO）
     - 剩余部分加入多头持仓队列
   - **卖单（SELL）**：
     - 先与多头持仓队列轧差（FIFO）
     - 剩余部分加入空头持仓队列

3. **计算未实现盈亏**：
   - 对剩余的多头持仓：`数量 × (当前价格 - 开仓价格)`
   - 对剩余的空头持仓：`数量 × (开仓价格 - 当前价格)`

### 代码位置

- `src/tri_arb/services/position_metrics_scheduler.py` (第 777-936 行)

### 代码实现

```910:912:src/tri_arb/services/position_metrics_scheduler.py
            # 计算未实现盈亏
            long_unrealized = sum(qty * (current_price - price) for qty, price in long_positions)
            short_unrealized = sum(qty * (price - current_price) for qty, price in short_positions)
            total_unrealized = long_unrealized + short_unrealized
```

### 处理成交记录的代码

```884:907:src/tri_arb/services/position_metrics_scheduler.py
                if side == "BUY":
                    remaining = quantity_coins
                    while remaining > 0 and short_positions:
                        short_qty, short_price = short_positions[0]
                        if short_qty <= remaining:
                            remaining -= short_qty
                            short_positions.pop(0)
                        else:
                            short_positions[0] = (short_qty - remaining, short_price)
                            remaining = Decimal("0")
                    if remaining > 0:
                        long_positions.append((remaining, price))
                elif side == "SELL":
                    remaining = quantity_coins
                    while remaining > 0 and long_positions:
                        long_qty, long_price = long_positions[0]
                        if long_qty <= remaining:
                            remaining -= long_qty
                            long_positions.pop(0)
                        else:
                            long_positions[0] = (long_qty - remaining, long_price)
                            remaining = Decimal("0")
                    if remaining > 0:
                        short_positions.append((remaining, price))
```

### 示例

假设有以下成交记录（按时间顺序）：

| 时间 | 方向 | 价格 | 数量 |
|------|------|------|------|
| 10:00 | BUY | 100 | 10 |
| 10:30 | SELL | 105 | 5 |
| 11:00 | BUY | 110 | 8 |
| 11:30 | SELL | 108 | 12 |

当前价格 = 115

**处理过程**：

1. 10:00 BUY 100 × 10 → 多头队列：`[(10, 100)]`
2. 10:30 SELL 105 × 5 → 与多头轧差 5，剩余多头：`[(5, 100)]`，已实现盈亏：`5 × (105 - 100) = 25`
3. 11:00 BUY 110 × 8 → 多头队列：`[(5, 100), (8, 110)]`
4. 11:30 SELL 108 × 12 → 先与 `(5, 100)` 轧差 5，再与 `(8, 110)` 轧差 7，剩余空头：`[(1, 108)]`，已实现盈亏：`5 × (108 - 100) + 7 × (108 - 110) = 40 - 14 = 26`

**最终持仓**：
- 多头：`[(1, 110)]`（从 `(8, 110)` 剩余 1）
- 空头：`[(1, 108)]`

**未实现盈亏**：
- 多头：`1 × (115 - 110) = 5`
- 空头：`1 × (108 - 115) = -7`
- 总计：`5 + (-7) = -2`

---

## SQL 验证查询

### 验证方法一：基于持仓和平均价格

#### 1. 查询剩余持仓和平均价格

**XT 交易所**：

```sql
-- 查询指定账号和交易对的剩余持仓
WITH position_metrics AS (
    SELECT 
        account_id,
        symbol,
        timestamp,
        left_long_qty,
        left_short_qty,
        avg_buy_prz,
        avg_sell_prz,
        close_prz,
        unrealized_pnl
    FROM position_metrics
    WHERE account_id = 'account_006ktmm1'
      AND exchange = 'xt'
      AND symbol = 'trump_usdt'
      AND timestamp >= CURRENT_DATE - INTERVAL '1 day'
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT 
    account_id,
    symbol,
    timestamp,
    left_long_qty,
    left_short_qty,
    avg_buy_prz,
    avg_sell_prz,
    close_prz,
    unrealized_pnl AS stored_unrealized_pnl,
    -- 手动计算未实现盈亏
    (left_long_qty * (close_prz - avg_buy_prz) + 
     left_short_qty * (avg_sell_prz - close_prz)) AS calculated_unrealized_pnl,
    -- 验证差异
    unrealized_pnl - (left_long_qty * (close_prz - avg_buy_prz) + 
                      left_short_qty * (avg_sell_prz - close_prz)) AS difference
FROM position_metrics;
```

**Binance 交易所**：

```sql
-- Binance 交易所的验证查询（类似，但表名不同）
WITH position_metrics AS (
    SELECT 
        account_id,
        symbol,
        timestamp,
        left_long_qty,
        left_short_qty,
        avg_buy_prz,
        avg_sell_prz,
        close_prz,
        unrealized_pnl
    FROM position_metrics
    WHERE account_id = 'your_account_id'
      AND exchange = 'binance'
      AND symbol = 'BTCUSDT'
      AND timestamp >= CURRENT_DATE - INTERVAL '1 day'
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT 
    account_id,
    symbol,
    timestamp,
    left_long_qty,
    left_short_qty,
    avg_buy_prz,
    avg_sell_prz,
    close_prz,
    unrealized_pnl AS stored_unrealized_pnl,
    (left_long_qty * (close_prz - avg_buy_prz) + 
     left_short_qty * (avg_sell_prz - close_prz)) AS calculated_unrealized_pnl,
    unrealized_pnl - (left_long_qty * (close_prz - avg_buy_prz) + 
                      left_short_qty * (avg_sell_prz - close_prz)) AS difference
FROM position_metrics;
```

#### 2. 验证平均价格计算

```sql
-- 验证买入平均价格（XT 交易所）
WITH buy_trades AS (
    SELECT 
        account_id,
        symbol,
        SUM(quantity) AS total_buy_qty,
        SUM(price * quantity) AS total_buy_value,
        SUM(price * quantity) / NULLIF(SUM(quantity), 0) AS calculated_avg_buy_prz
    FROM xt_trade_update
    WHERE account_id = 'account_006ktmm1'
      AND symbol = 'trump_usdt'
      AND side = 'BUY'
      AND update_time >= CURRENT_DATE
    GROUP BY account_id, symbol
)
SELECT 
    account_id,
    symbol,
    total_buy_qty,
    total_buy_value,
    calculated_avg_buy_prz,
    -- 与 position_metrics 中的 avg_buy_prz 对比
    (SELECT avg_buy_prz 
     FROM position_metrics 
     WHERE account_id = bt.account_id 
       AND symbol = bt.symbol 
       AND exchange = 'xt'
       AND timestamp >= CURRENT_DATE 
     ORDER BY timestamp DESC LIMIT 1) AS stored_avg_buy_prz,
    -- 差异
    calculated_avg_buy_prz - (SELECT avg_buy_prz 
                              FROM position_metrics 
                              WHERE account_id = bt.account_id 
                                AND symbol = bt.symbol 
                                AND exchange = 'xt'
                                AND timestamp >= CURRENT_DATE 
                              ORDER BY timestamp DESC LIMIT 1) AS difference
FROM buy_trades bt;
```

#### 3. 验证最后一笔成交价

```sql
-- 查询最后一笔成交价（XT 交易所）
SELECT 
    account_id,
    symbol,
    price AS close_prz,
    update_time
FROM xt_trade_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= CURRENT_DATE
ORDER BY update_time DESC
LIMIT 1;
```

```sql
-- 查询最后一笔成交价（Binance 交易所）
SELECT 
    account_id,
    symbol,
    price AS close_prz,
    transaction_time
FROM binance_trade_update
WHERE account_id = 'your_account_id'
  AND symbol = 'BTCUSDT'
  AND exchange = 'binance_perp'
  AND transaction_time >= CURRENT_DATE
ORDER BY transaction_time DESC
LIMIT 1;
```

#### 4. 验证剩余持仓计算

```sql
-- 验证剩余持仓（XT 交易所）
WITH trade_stats AS (
    SELECT 
        account_id,
        symbol,
        -- 买入总量
        SUM(CASE WHEN side = 'BUY' THEN quantity ELSE 0 END) AS buy_volume,
        -- 卖出总量
        SUM(CASE WHEN side = 'SELL' THEN quantity ELSE 0 END) AS sell_volume
    FROM xt_trade_update
    WHERE account_id = 'account_006ktmm1'
      AND symbol = 'trump_usdt'
      AND update_time >= CURRENT_DATE
    GROUP BY account_id, symbol
),
initial_positions AS (
    -- 获取区间开始时的持仓（需要根据实际情况调整）
    SELECT 
        account_id,
        symbol,
        SUM(CASE WHEN side = 'LONG' THEN quantity ELSE 0 END) AS initial_long_qty,
        SUM(CASE WHEN side = 'SHORT' THEN quantity ELSE 0 END) AS initial_short_qty
    FROM xt_position_update
    WHERE account_id = 'account_006ktmm1'
      AND symbol = 'trump_usdt'
      AND update_time < CURRENT_DATE
      AND update_time >= CURRENT_DATE - INTERVAL '1 day'
    GROUP BY account_id, symbol
)
SELECT 
    ts.account_id,
    ts.symbol,
    COALESCE(ip.initial_long_qty, 0) AS initial_long_qty,
    COALESCE(ip.initial_short_qty, 0) AS initial_short_qty,
    ts.buy_volume,
    ts.sell_volume,
    COALESCE(ip.initial_long_qty, 0) + ts.buy_volume AS long_qty,
    COALESCE(ip.initial_short_qty, 0) + ts.sell_volume AS short_qty,
    LEAST(COALESCE(ip.initial_long_qty, 0) + ts.buy_volume, 
          COALESCE(ip.initial_short_qty, 0) + ts.sell_volume) AS matched_qty,
    (COALESCE(ip.initial_long_qty, 0) + ts.buy_volume) - 
    LEAST(COALESCE(ip.initial_long_qty, 0) + ts.buy_volume, 
          COALESCE(ip.initial_short_qty, 0) + ts.sell_volume) AS calculated_left_long_qty,
    (COALESCE(ip.initial_short_qty, 0) + ts.sell_volume) - 
    LEAST(COALESCE(ip.initial_long_qty, 0) + ts.buy_volume, 
          COALESCE(ip.initial_short_qty, 0) + ts.sell_volume) AS calculated_left_short_qty,
    -- 与 position_metrics 中的值对比
    (SELECT left_long_qty 
     FROM position_metrics 
     WHERE account_id = ts.account_id 
       AND symbol = ts.symbol 
       AND exchange = 'xt'
       AND timestamp >= CURRENT_DATE 
     ORDER BY timestamp DESC LIMIT 1) AS stored_left_long_qty,
    (SELECT left_short_qty 
     FROM position_metrics 
     WHERE account_id = ts.account_id 
       AND symbol = ts.symbol 
       AND exchange = 'xt'
       AND timestamp >= CURRENT_DATE 
     ORDER BY timestamp DESC LIMIT 1) AS stored_left_short_qty
FROM trade_stats ts
LEFT JOIN initial_positions ip ON ts.account_id = ip.account_id AND ts.symbol = ip.symbol;
```

---

### 验证方法二：基于成交记录（FIFO）

#### 1. 查询所有成交记录（按时间排序）

```sql
-- 查询指定时间范围内的所有成交记录（XT 交易所）
SELECT 
    update_time,
    side,
    price,
    quantity,
    -- 计算合约乘数（大多数 USDT 永续合约为 1）
    quantity * 1 AS quantity_coins
FROM xt_trade_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= '2025-01-01 00:00:00'
  AND update_time <= '2025-01-01 23:59:59'
ORDER BY update_time ASC;
```

```sql
-- 查询指定时间范围内的所有成交记录（Binance 交易所）
SELECT 
    transaction_time,
    side,
    price,
    quantity,
    quantity * 1 AS quantity_coins
FROM binance_trade_update
WHERE account_id = 'your_account_id'
  AND symbol = 'BTCUSDT'
  AND exchange = 'binance_perp'
  AND transaction_time >= '2025-01-01 00:00:00'
  AND transaction_time <= '2025-01-01 23:59:59'
ORDER BY transaction_time ASC;
```

#### 2. 验证 FIFO 计算的中间结果

由于 FIFO 计算需要按顺序处理，SQL 难以直接实现完整的 FIFO 逻辑，但可以验证基础数据：

```sql
-- 统计成交记录总数和方向分布
SELECT 
    account_id,
    symbol,
    COUNT(*) AS total_trades,
    SUM(CASE WHEN side = 'BUY' THEN 1 ELSE 0 END) AS buy_count,
    SUM(CASE WHEN side = 'SELL' THEN 1 ELSE 0 END) AS sell_count,
    SUM(CASE WHEN side = 'BUY' THEN quantity ELSE 0 END) AS total_buy_qty,
    SUM(CASE WHEN side = 'SELL' THEN quantity ELSE 0 END) AS total_sell_qty,
    MIN(update_time) AS first_trade_time,
    MAX(update_time) AS last_trade_time
FROM xt_trade_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= CURRENT_DATE
GROUP BY account_id, symbol;
```

#### 3. 对比 position_metrics 中的未实现盈亏

```sql
-- 对比 position_metrics 中的未实现盈亏（方法二的结果）
SELECT 
    account_id,
    exchange,
    symbol,
    timestamp,
    unrealized_pnl,
    left_long_qty,
    left_short_qty,
    close_prz
FROM position_metrics
WHERE account_id = 'account_006ktmm1'
  AND exchange = 'xt'
  AND symbol = 'trump_usdt'
  AND timestamp >= CURRENT_DATE
ORDER BY timestamp DESC
LIMIT 10;
```

---

## 完整验证流程

### 步骤 1：验证基础数据

```sql
-- 1. 验证成交记录完整性（XT 交易所）
SELECT 
    COUNT(*) AS trade_count,
    MIN(update_time) AS first_trade,
    MAX(update_time) AS last_trade,
    SUM(CASE WHEN side = 'BUY' THEN quantity ELSE 0 END) AS total_buy_qty,
    SUM(CASE WHEN side = 'SELL' THEN quantity ELSE 0 END) AS total_sell_qty
FROM xt_trade_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= CURRENT_DATE;
```

```sql
-- 2. 验证持仓记录（XT 交易所）
SELECT 
    COUNT(*) AS position_count,
    SUM(CASE WHEN side = 'LONG' THEN quantity ELSE 0 END) AS total_long_qty,
    SUM(CASE WHEN side = 'SHORT' THEN quantity ELSE 0 END) AS total_short_qty
FROM xt_position_update
WHERE account_id = 'account_006ktmm1'
  AND symbol = 'trump_usdt'
  AND update_time >= CURRENT_DATE - INTERVAL '1 hour';
```

### 步骤 2：验证平均价格

```sql
-- 验证买入平均价格（XT 交易所）
WITH buy_stats AS (
    SELECT 
        SUM(quantity) AS total_qty,
        SUM(price * quantity) AS total_value,
        SUM(price * quantity) / NULLIF(SUM(quantity), 0) AS avg_price
    FROM xt_trade_update
    WHERE account_id = 'account_006ktmm1'
      AND symbol = 'trump_usdt'
      AND side = 'BUY'
      AND update_time >= CURRENT_DATE
)
SELECT 
    total_qty,
    total_value,
    avg_price AS calculated_avg_buy_prz,
    (SELECT avg_buy_prz 
     FROM position_metrics 
     WHERE account_id = 'account_006ktmm1'
       AND symbol = 'trump_usdt'
       AND exchange = 'xt'
       AND timestamp >= CURRENT_DATE
     ORDER BY timestamp DESC LIMIT 1) AS stored_avg_buy_prz,
    avg_price - (SELECT avg_buy_prz 
                 FROM position_metrics 
                 WHERE account_id = 'account_006ktmm1'
                   AND symbol = 'trump_usdt'
                   AND exchange = 'xt'
                   AND timestamp >= CURRENT_DATE
                 ORDER BY timestamp DESC LIMIT 1) AS difference
FROM buy_stats;
```

### 步骤 3：验证未实现盈亏

```sql
-- 综合验证：对比方法一的计算结果
WITH metrics_data AS (
    SELECT 
        timestamp,
        left_long_qty,
        left_short_qty,
        avg_buy_prz,
        avg_sell_prz,
        close_prz,
        unrealized_pnl AS stored_unrealized_pnl
    FROM position_metrics
    WHERE account_id = 'account_006ktmm1'
      AND exchange = 'xt'
      AND symbol = 'trump_usdt'
      AND timestamp >= CURRENT_DATE
    ORDER BY timestamp DESC
    LIMIT 1
)
SELECT 
    md.timestamp,
    md.left_long_qty,
    md.left_short_qty,
    md.avg_buy_prz,
    md.avg_sell_prz,
    md.close_prz,
    md.stored_unrealized_pnl,
    -- 方法一计算
    (md.left_long_qty * (md.close_prz - md.avg_buy_prz) + 
     md.left_short_qty * (md.avg_sell_prz - md.close_prz)) AS calculated_unrealized_pnl,
    -- 差异
    md.stored_unrealized_pnl - (md.left_long_qty * (md.close_prz - md.avg_buy_prz) + 
                                 md.left_short_qty * (md.avg_sell_prz - md.close_prz)) AS difference
FROM metrics_data md;
```

---

## 注意事项

1. **合约乘数**：
   - 大多数 USDT 永续合约的合约乘数为 1
   - 可通过 XT API 的 `symbol/detail` 接口获取 `contractSize` 字段
   - 计算时需要将合约张数转换为币数量：`币数量 = 合约张数 × 合约乘数`

2. **时间精度**：
   - 所有时间字段使用 UTC 时间
   - 计算时注意时区转换

3. **精度问题**：
   - 所有计算使用 `Decimal` 类型，避免浮点数精度问题
   - SQL 查询时使用 `NUMERIC` 类型进行计算

4. **数据完整性**：
   - 确保成交记录完整（无遗漏）
   - 确保持仓记录及时更新

5. **账号和交易对**：
   - 所有计算都按 `account_id` 和 `symbol` 分别进行
   - 不进行跨账号或跨交易对的汇总

6. **方法选择**：
   - **方法一**：用于批量计算和指标统计，基于平均价格，计算简单
   - **方法二**：用于增量计算和实时更新，基于 FIFO 队列，精度更高

---

## 相关文件

- `src/tri_arb/services/position_calculator.py`: 方法一实现
- `src/tri_arb/services/position_metrics_scheduler.py`: 方法二实现
- `docs/POSITION_CALCULATION_FORMULA.md`: 持仓计算完整公式文档
