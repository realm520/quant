-- ============================================
-- 验证12-10开盘持仓应该是0的查询
-- ============================================

-- 这个查询专门验证12-10的开盘持仓计算

WITH daily_trades AS (
    SELECT 
        DATE(update_time) as trade_date,
        account_id,
        symbol,
        SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
        SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume
    FROM xt_trade_update
    WHERE 
        account_id = 'account_008'
        AND symbol = 'tradoor_usdt'
        AND update_time < '2025-12-11 00:00:00'  -- 12-10及之前
    GROUP BY DATE(update_time), account_id, symbol
),
-- 生成日期序列（包含12-9和12-10）
date_series AS (
    SELECT '2025-12-09'::date as trade_date, 'account_008' as account_id, 'tradoor_usdt' as symbol
    UNION ALL
    SELECT '2025-12-10'::date as trade_date, 'account_008' as account_id, 'tradoor_usdt' as symbol
),
-- 合并数据
daily_data AS (
    SELECT 
        ds.trade_date,
        ds.account_id,
        ds.symbol,
        COALESCE(dt.buy_volume, 0) as buy_volume,
        COALESCE(dt.sell_volume, 0) as sell_volume
    FROM date_series ds
    LEFT JOIN daily_trades dt ON 
        ds.trade_date = dt.trade_date 
        AND ds.account_id = dt.account_id 
        AND ds.symbol = dt.symbol
),
-- 计算累计持仓
cumulative AS (
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
        ) as cum_buy,
        SUM(sell_volume) OVER (
            PARTITION BY account_id, symbol 
            ORDER BY trade_date 
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) as cum_sell
    FROM daily_data
)
SELECT 
    trade_date,
    buy_volume as daily_buy,
    sell_volume as daily_sell,
    cum_buy as cumulative_buy,
    cum_sell as cumulative_sell,
    -- 前一天累计持仓
    COALESCE(LAG(cum_buy, 1) OVER (ORDER BY trade_date), 0) as prev_cum_buy,
    COALESCE(LAG(cum_sell, 1) OVER (ORDER BY trade_date), 0) as prev_cum_sell,
    -- 开盘持仓 = 前一天收盘持仓 = 前一天累计持仓 - 前一天轧差
    COALESCE(LAG(cum_buy, 1) OVER (ORDER BY trade_date), 0) - 
    LEAST(
        COALESCE(LAG(cum_buy, 1) OVER (ORDER BY trade_date), 0),
        COALESCE(LAG(cum_sell, 1) OVER (ORDER BY trade_date), 0)
    ) as open_left_long_qty,
    COALESCE(LAG(cum_sell, 1) OVER (ORDER BY trade_date), 0) - 
    LEAST(
        COALESCE(LAG(cum_buy, 1) OVER (ORDER BY trade_date), 0),
        COALESCE(LAG(cum_sell, 1) OVER (ORDER BY trade_date), 0)
    ) as open_left_short_qty
FROM cumulative
ORDER BY trade_date;
