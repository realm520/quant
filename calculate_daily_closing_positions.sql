-- ============================================
-- 从 xt_trade_update 表计算每日开盘持仓（昨日收盘持仓 = 今日开盘持仓）
-- ============================================
-- 注意：此查询假设合约乘数为 1，如果实际不是 1，需要调整 quantity 的计算
-- 此查询会从最早交易日期前一天开始计算，确保每一天都有开盘持仓数据
-- 昨日收盘持仓 = 今日开盘持仓

-- 替换参数：
--   - 'account_008' 为你的 account_id
--   - 'tradoor_usdt' 为你要查询的 symbol（可选，如果查询所有 symbol 则删除 WHERE symbol 条件）
--   - 日期范围根据需要调整

-- 1. 获取日期范围（从最早交易日期前一天开始）
WITH date_range AS (
    SELECT 
        DATE(MIN(update_time)) - INTERVAL '1 day' as start_date,
        DATE(MAX(update_time)) as end_date,
        account_id,
        symbol
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'  -- 只查询 tradoor_usdt
        AND update_time >= '2025-12-01 00:00:00'  -- 调整开始日期
        AND update_time < CURRENT_DATE + INTERVAL '1 day'  -- 结束日期：今天（自动获取最新日期）
    GROUP BY account_id, symbol
),
-- 2. 生成日期序列（从最早交易日期前一天到当前日期）
date_series AS (
    SELECT 
        dr.account_id,
        dr.symbol,
        generate_series(
            dr.start_date::date,
            dr.end_date::date,
            '1 day'::interval
        )::date as trade_date
    FROM date_range dr
),
-- 3. 计算每日的买入总量、卖出总量、买入总市值、卖出总市值
daily_trades AS (
    SELECT 
        DATE(update_time) as trade_date,
        account_id,
        symbol,
        -- 买入总量（币数量，假设合约乘数为 1，实际需要根据 symbol 调整）
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
        -- 卖出总量（币数量）
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume,
        -- 买入总市值 = sum(quantity * price) for BUY
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity * price ELSE 0 END) as buy_trade_value,
        -- 卖出总市值 = sum(quantity * price) for SELL
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity * price ELSE 0 END) as sell_trade_value
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'  -- 只查询 tradoor_usdt
        AND update_time >= '2025-12-01 00:00:00'  -- 调整开始日期
        AND update_time < CURRENT_DATE + INTERVAL '1 day'  -- 结束日期：今天（自动获取最新日期）
    GROUP BY DATE(update_time), account_id, symbol
),
-- 4. 合并日期序列和交易数据（没有交易的日期交易量为0）
daily_data AS (
    SELECT 
        ds.trade_date,
        ds.account_id,
        ds.symbol,
        COALESCE(dt.buy_volume, 0) as buy_volume,
        COALESCE(dt.sell_volume, 0) as sell_volume,
        COALESCE(dt.buy_trade_value, 0) as buy_trade_value,
        COALESCE(dt.sell_trade_value, 0) as sell_trade_value
    FROM date_series ds
    LEFT JOIN daily_trades dt ON 
        ds.trade_date = dt.trade_date 
        AND ds.account_id = dt.account_id 
        AND ds.symbol = dt.symbol
),
-- 5. 计算累计持仓（从最早日期开始累计）
cumulative_positions AS (
    SELECT 
        trade_date,
        account_id,
        symbol,
        buy_volume,
        sell_volume,
        buy_trade_value,
        sell_trade_value,
        -- 累计买入总量（从最早日期到当前日期，包含当天）
        SUM(buy_volume) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_buy_volume,
        -- 累计卖出总量（包含当天）
        SUM(sell_volume) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_sell_volume,
        -- 累计买入总市值（包含当天）
        SUM(buy_trade_value) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_buy_value,
        -- 累计卖出总市值（包含当天）
        SUM(sell_trade_value) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_sell_value
    FROM daily_data
),
-- 6. 计算昨日收盘持仓（用于今日开盘持仓）
prev_day_closing AS (
    SELECT 
        trade_date,
        account_id,
        symbol,
        buy_volume,
        sell_volume,
        buy_trade_value,
        sell_trade_value,
        cumulative_buy_volume,
        cumulative_sell_volume,
        cumulative_buy_value,
        cumulative_sell_value,
        -- 使用 LAG 获取前一天的累计持仓（昨日收盘持仓）
        COALESCE(LAG(cumulative_buy_volume, 1) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date
        ), 0) as prev_cumulative_buy_volume,
        COALESCE(LAG(cumulative_sell_volume, 1) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date
        ), 0) as prev_cumulative_sell_volume,
        COALESCE(LAG(cumulative_buy_value, 1) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date
        ), 0) as prev_cumulative_buy_value,
        COALESCE(LAG(cumulative_sell_value, 1) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date
        ), 0) as prev_cumulative_sell_value
    FROM cumulative_positions
),
-- 7. 计算昨日收盘持仓的剩余持仓（今日开盘持仓）
opening_positions AS (
    SELECT 
        trade_date,
        account_id,
        symbol,
        buy_volume,
        sell_volume,
        buy_trade_value,
        sell_trade_value,
        cumulative_buy_volume,
        cumulative_sell_volume,
        cumulative_buy_value,
        cumulative_sell_value,
        prev_cumulative_buy_volume,
        prev_cumulative_sell_volume,
        prev_cumulative_buy_value,
        prev_cumulative_sell_value,
        -- 昨日收盘时的平均价格
        CASE 
            WHEN prev_cumulative_buy_volume > 0 
            THEN prev_cumulative_buy_value / prev_cumulative_buy_volume 
            ELSE 0 
        END as prev_avg_buy_prz,
        CASE 
            WHEN prev_cumulative_sell_volume > 0 
            THEN prev_cumulative_sell_value / prev_cumulative_sell_volume 
            ELSE 0 
        END as prev_avg_sell_prz,
        -- 昨日收盘时的轧差数量
        LEAST(prev_cumulative_buy_volume, prev_cumulative_sell_volume) as prev_matched_qty,
        -- 今日累计平均价格（用于计算今日已实现盈亏）
        CASE 
            WHEN cumulative_buy_volume > 0 
            THEN cumulative_buy_value / cumulative_buy_volume 
            ELSE 0 
        END as avg_buy_prz,
        CASE 
            WHEN cumulative_sell_volume > 0 
            THEN cumulative_sell_value / cumulative_sell_volume 
            ELSE 0 
        END as avg_sell_prz,
        -- 今日累计轧差数量
        LEAST(cumulative_buy_volume, cumulative_sell_volume) as matched_qty,
        -- 昨日累计轧差数量
        COALESCE(LAG(LEAST(cumulative_buy_volume, cumulative_sell_volume), 1) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date
        ), 0) as prev_matched_qty_calc
    FROM prev_day_closing
),
-- 8. 计算每日已实现盈亏和累积已实现盈亏
pnl_calculation AS (
    SELECT 
        trade_date,
        account_id,
        symbol,
        buy_volume,
        sell_volume,
        buy_trade_value,
        sell_trade_value,
        cumulative_buy_volume,
        cumulative_sell_volume,
        cumulative_buy_value,
        cumulative_sell_value,
        prev_cumulative_buy_volume,
        prev_cumulative_sell_volume,
        prev_cumulative_buy_value,
        prev_cumulative_sell_value,
        prev_avg_buy_prz,
        prev_avg_sell_prz,
        prev_matched_qty,
        avg_buy_prz,
        avg_sell_prz,
        matched_qty,
        prev_matched_qty_calc,
        -- 今日新增轧差数量（今日累计轧差 - 昨日累计轧差）
        matched_qty - prev_matched_qty_calc as daily_matched_qty,
        -- 今日已实现盈亏 = (卖出平均价 - 买入平均价) * 今日新增轧差数量
        -- 使用累计平均价计算，因为轧差是基于累计持仓计算的
        CASE 
            WHEN matched_qty > prev_matched_qty_calc AND avg_sell_prz > 0 AND avg_buy_prz > 0
            THEN (avg_sell_prz - avg_buy_prz) * (matched_qty - prev_matched_qty_calc)
            ELSE 0
        END as daily_realized_pnl
    FROM opening_positions
)
-- 3. 计算每日开盘持仓（昨日收盘持仓 = 今日开盘持仓）
SELECT 
    trade_date,
    account_id,
    symbol,
    -- ===== 今日开盘持仓（等于昨日收盘持仓，不包含当天交易）=====
    prev_cumulative_buy_volume - prev_matched_qty as open_left_long_qty,
    prev_cumulative_sell_volume - prev_matched_qty as open_left_short_qty,
    (prev_cumulative_buy_volume - prev_matched_qty) * 
    CASE WHEN prev_cumulative_buy_volume > 0 THEN prev_avg_buy_prz ELSE 0 END 
    as open_left_long_value,
    (prev_cumulative_sell_volume - prev_matched_qty) * 
    CASE WHEN prev_cumulative_sell_volume > 0 THEN prev_avg_sell_prz ELSE 0 END 
    as open_left_short_value,
    -- ===== 当日交易统计 =====
    buy_volume as daily_buy_volume,
    sell_volume as daily_sell_volume,
    buy_trade_value as daily_buy_value,
    sell_trade_value as daily_sell_value,
    -- ===== 累计持仓（从最早日期到当前日期，包含当天）=====
    cumulative_buy_volume as total_long_qty,
    cumulative_sell_volume as total_short_qty,
    cumulative_buy_value as total_long_value,
    cumulative_sell_value as total_short_value,
    -- ===== 平均价格（包含当天）=====
    CASE 
        WHEN cumulative_buy_volume > 0 
        THEN cumulative_buy_value / cumulative_buy_volume 
        ELSE 0 
    END as avg_buy_prz,
    CASE 
        WHEN cumulative_sell_volume > 0 
        THEN cumulative_sell_value / cumulative_sell_volume 
        ELSE 0 
    END as avg_sell_prz,
    -- ===== 轧差数量（包含当天）=====
    matched_qty,
    -- ===== 今日收盘持仓（包含当天交易）=====
    cumulative_buy_volume - matched_qty as close_left_long_qty,
    cumulative_sell_volume - matched_qty as close_left_short_qty,
    -- ===== 已实现盈亏 =====
    daily_matched_qty,
    daily_realized_pnl,
    -- ===== 累积已实现盈亏（从最早日期开始累计）=====
    SUM(daily_realized_pnl) OVER (
        PARTITION BY account_id, symbol 
        ORDER BY trade_date 
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) as cumulative_realized_pnl
FROM pnl_calculation
ORDER BY trade_date, account_id, symbol;

-- ============================================
-- 调试查询：检查开盘持仓计算逻辑
-- ============================================
-- 这个查询显示每一步的计算过程，帮助验证逻辑是否正确

WITH date_range AS (
    SELECT 
        DATE(MIN(update_time)) - INTERVAL '1 day' as start_date,
        DATE(MAX(update_time)) as end_date,
        account_id,
        symbol
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'
        AND update_time >= '2025-12-01 00:00:00'
        AND update_time < CURRENT_DATE + INTERVAL '1 day'  -- 结束日期：今天（自动获取最新日期）
    GROUP BY account_id, symbol
),
date_series AS (
    SELECT 
        dr.account_id,
        dr.symbol,
        generate_series(
            dr.start_date::date,
            dr.end_date::date,
            '1 day'::interval
        )::date as trade_date
    FROM date_range dr
),
daily_trades AS (
    SELECT 
        DATE(update_time) as trade_date,
        account_id,
        symbol,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity * price ELSE 0 END) as buy_trade_value,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity * price ELSE 0 END) as sell_trade_value
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'
        AND update_time >= '2025-12-01 00:00:00'
        AND update_time < CURRENT_DATE + INTERVAL '1 day'  -- 结束日期：今天（自动获取最新日期）
    GROUP BY DATE(update_time), account_id, symbol
),
daily_data AS (
    SELECT 
        ds.trade_date,
        ds.account_id,
        ds.symbol,
        COALESCE(dt.buy_volume, 0) as buy_volume,
        COALESCE(dt.sell_volume, 0) as sell_volume,
        COALESCE(dt.buy_trade_value, 0) as buy_trade_value,
        COALESCE(dt.sell_trade_value, 0) as sell_trade_value
    FROM date_series ds
    LEFT JOIN daily_trades dt ON 
        ds.trade_date = dt.trade_date 
        AND ds.account_id = dt.account_id 
        AND ds.symbol = dt.symbol
),
cumulative_positions AS (
    SELECT 
        trade_date,
        account_id,
        symbol,
        buy_volume,
        sell_volume,
        SUM(buy_volume) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_buy_volume,
        SUM(sell_volume) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_sell_volume
    FROM daily_data
)
SELECT 
    trade_date,
    account_id,
    symbol,
    buy_volume as daily_buy,
    sell_volume as daily_sell,
    cumulative_buy_volume as cum_buy,
    cumulative_sell_volume as cum_sell,
    -- 前一天累计持仓
    COALESCE(LAG(cumulative_buy_volume, 1) OVER (
        PARTITION BY account_id, symbol 
        ORDER BY trade_date
    ), 0) as prev_cum_buy,
    COALESCE(LAG(cumulative_sell_volume, 1) OVER (
        PARTITION BY account_id, symbol 
        ORDER BY trade_date
    ), 0) as prev_cum_sell,
    -- 开盘持仓
    COALESCE(LAG(cumulative_buy_volume, 1) OVER (
        PARTITION BY account_id, symbol 
        ORDER BY trade_date
    ), 0) - 
    LEAST(
        COALESCE(LAG(cumulative_buy_volume, 1) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date
        ), 0),
        COALESCE(LAG(cumulative_sell_volume, 1) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date
        ), 0)
    ) as open_left_long_qty
FROM cumulative_positions
ORDER BY trade_date;

-- ============================================
-- 简化版本：只查看特定日期的开盘持仓（包含最早交易日期前一天）
-- ============================================
-- 例如：查看今天的开盘持仓（即昨天的收盘持仓）

WITH date_range AS (
    SELECT 
        DATE(MIN(update_time)) - INTERVAL '1 day' as start_date,
        DATE(MAX(update_time)) as end_date,
        account_id,
        symbol
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'  -- 替换为你要查询的 symbol
        AND update_time < CURRENT_DATE + INTERVAL '1 day'  -- 查询到今天为止的所有数据（自动获取最新日期）
    GROUP BY account_id, symbol
),
date_series AS (
    SELECT 
        dr.account_id,
        dr.symbol,
        generate_series(
            dr.start_date::date,
            dr.end_date::date,
            '1 day'::interval
        )::date as trade_date
    FROM date_range dr
),
daily_trades AS (
    SELECT 
        DATE(update_time) as trade_date,
        account_id,
        symbol,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity * price ELSE 0 END) as buy_trade_value,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity * price ELSE 0 END) as sell_trade_value
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'
        AND update_time < CURRENT_DATE + INTERVAL '1 day'  -- 结束日期：今天（自动获取最新日期）
    GROUP BY DATE(update_time), account_id, symbol
),
daily_data AS (
    SELECT 
        ds.trade_date,
        ds.account_id,
        ds.symbol,
        COALESCE(dt.buy_volume, 0) as buy_volume,
        COALESCE(dt.sell_volume, 0) as sell_volume,
        COALESCE(dt.buy_trade_value, 0) as buy_trade_value,
        COALESCE(dt.sell_trade_value, 0) as sell_trade_value
    FROM date_series ds
    LEFT JOIN daily_trades dt ON 
        ds.trade_date = dt.trade_date 
        AND ds.account_id = dt.account_id 
        AND ds.symbol = dt.symbol
),
cumulative_data AS (
    SELECT 
        trade_date,
        account_id,
        symbol,
        buy_volume,
        sell_volume,
        buy_trade_value,
        sell_trade_value,
        SUM(buy_volume) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_buy_volume,
        SUM(sell_volume) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_sell_volume,
        SUM(buy_trade_value) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_buy_value,
        SUM(sell_trade_value) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cumulative_sell_value
    FROM daily_data
)
SELECT 
    trade_date,
    account_id,
    symbol,
    buy_volume as daily_buy_volume,
    sell_volume as daily_sell_volume,
    buy_trade_value as daily_buy_value,
    sell_trade_value as daily_sell_value,
    cumulative_buy_volume as total_long_qty,
    cumulative_sell_volume as total_short_qty,
    cumulative_buy_value as total_long_value,
    cumulative_sell_value as total_short_value,
    CASE WHEN cumulative_buy_volume > 0 THEN cumulative_buy_value / cumulative_buy_volume ELSE 0 END as avg_buy_prz,
    CASE WHEN cumulative_sell_volume > 0 THEN cumulative_sell_value / cumulative_sell_volume ELSE 0 END as avg_sell_prz,
    LEAST(cumulative_buy_volume, cumulative_sell_volume) as matched_qty,
    -- 今日开盘持仓（等于昨日收盘持仓）
    cumulative_buy_volume - LEAST(cumulative_buy_volume, cumulative_sell_volume) as open_left_long_qty,
    cumulative_sell_volume - LEAST(cumulative_buy_volume, cumulative_sell_volume) as open_left_short_qty,
    (cumulative_buy_volume - LEAST(cumulative_buy_volume, cumulative_sell_volume)) * 
    CASE WHEN cumulative_buy_volume > 0 THEN cumulative_buy_value / cumulative_buy_volume ELSE 0 END 
    as open_left_long_value,
    (cumulative_sell_volume - LEAST(cumulative_buy_volume, cumulative_sell_volume)) * 
    CASE WHEN cumulative_sell_volume > 0 THEN cumulative_sell_value / cumulative_sell_volume ELSE 0 END 
    as open_left_short_value
FROM cumulative_data
ORDER BY trade_date;

-- ============================================
-- 对比不同日期的开盘持仓
-- ============================================
-- 例如：对比 12-11 和 12-12 的开盘持仓（即 12-10 和 12-11 的收盘持仓）

WITH date1_positions AS (
    SELECT 
        account_id,
        symbol,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity * price ELSE 0 END) as buy_value,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity * price ELSE 0 END) as sell_value
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'
        AND update_time < CURRENT_DATE  -- 昨天及之前（用于对比查询）
    GROUP BY account_id, symbol
),
date2_positions AS (
    SELECT 
        account_id,
        symbol,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity * price ELSE 0 END) as buy_value,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity * price ELSE 0 END) as sell_value
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'
        AND update_time < CURRENT_DATE + INTERVAL '1 day'  -- 今天及之前（用于对比查询）
    GROUP BY account_id, symbol
)
SELECT 
    COALESCE(d1.account_id, d2.account_id) as account_id,
    COALESCE(d1.symbol, d2.symbol) as symbol,
    -- 12-11 开盘持仓（即 12-10 收盘持仓）
    (d1.buy_volume - LEAST(d1.buy_volume, d1.sell_volume)) as date1_open_left_long_qty,
    (d1.sell_volume - LEAST(d1.buy_volume, d1.sell_volume)) as date1_open_left_short_qty,
    -- 12-12 开盘持仓（即 12-11 收盘持仓）
    (d2.buy_volume - LEAST(d2.buy_volume, d2.sell_volume)) as date2_open_left_long_qty,
    (d2.sell_volume - LEAST(d2.buy_volume, d2.sell_volume)) as date2_open_left_short_qty,
    -- 12-11 当天的交易（用于验证）
    (d1.buy_volume - COALESCE((
        SELECT SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END)
        FROM xt_trade_update
        WHERE account_id = d1.account_id 
        AND symbol = d1.symbol
        AND update_time < CURRENT_DATE - INTERVAL '1 day'  -- 前天及之前（用于对比查询）
    ), 0)) as date1_daily_buy_volume,
    (d1.sell_volume - COALESCE((
        SELECT SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END)
        FROM xt_trade_update
        WHERE account_id = d1.account_id 
        AND symbol = d1.symbol
        AND update_time < CURRENT_DATE - INTERVAL '1 day'  -- 前天及之前（用于对比查询）
    ), 0)) as date1_daily_sell_volume,
    -- 12-12 当天的交易（用于验证）
    (d2.buy_volume - COALESCE(d1.buy_volume, 0)) as date2_daily_buy_volume,
    (d2.sell_volume - COALESCE(d1.sell_volume, 0)) as date2_daily_sell_volume
FROM date1_positions d1
FULL OUTER JOIN date2_positions d2 ON d1.account_id = d2.account_id AND d1.symbol = d2.symbol;
