-- 查询零点（00:00:00）的持仓指标数据
-- 可以根据需要修改日期范围、账号、交易所、交易对等筛选条件

-- 方式1: 查询最近7天的零点数据
SELECT 
    timestamp,
    account_id,
    exchange,
    symbol,
    -- 开盘持仓
    open_left_long_qty,
    open_left_short_qty,
    open_left_long_value,
    open_left_short_value,
    -- 当日成交量
    daily_sum_buy_qty,
    daily_sum_sell_qty,
    daily_sum_buy_value,
    daily_sum_sell_value,
    -- 总持仓
    long_qty,
    short_qty,
    long_value,
    short_value,
    -- 平均价格
    avg_buy_prz,
    avg_sell_prz,
    -- 轧差和已实现盈亏
    matched_qty,
    daily_realized_pnl,
    cumulative_realized_pnl,
    -- 收盘持仓
    left_long_qty,
    left_short_qty,
    left_long_value,
    left_short_value,
    -- 收盘价和未实现盈亏
    close_prz,
    unrealized_pnl,
    -- PnL 汇总
    daily_pnl,
    cumulative_pnl,
    created_at
FROM position_metrics
WHERE 
    -- 筛选零点数据：时间部分为 00:00:00
    EXTRACT(HOUR FROM timestamp) = 0 
    AND EXTRACT(MINUTE FROM timestamp) = 0 
    AND EXTRACT(SECOND FROM timestamp) = 0
    -- 最近7天的数据
    AND timestamp >= CURRENT_DATE - INTERVAL '7 days'
    -- 可选：按账号筛选
    -- AND account_id = 'your_account_id'
    -- 可选：按交易所筛选
    -- AND exchange = 'binance'
    -- 可选：按交易对筛选
    -- AND symbol = 'BTCUSDT'
ORDER BY timestamp DESC, account_id, exchange, symbol;


-- 方式2: 查询指定日期的零点数据
SELECT 
    timestamp,
    account_id,
    exchange,
    symbol,
    open_left_long_qty,
    open_left_short_qty,
    daily_sum_buy_qty,
    daily_sum_sell_qty,
    avg_buy_prz,
    avg_sell_prz,
    matched_qty,
    daily_realized_pnl,
    cumulative_realized_pnl,
    left_long_qty,
    left_short_qty,
    close_prz,
    unrealized_pnl,
    daily_pnl,
    cumulative_pnl
FROM position_metrics
WHERE 
    DATE(timestamp) = '2025-12-11'  -- 修改为需要的日期
    AND EXTRACT(HOUR FROM timestamp) = 0 
    AND EXTRACT(MINUTE FROM timestamp) = 0 
    AND EXTRACT(SECOND FROM timestamp) = 0
ORDER BY account_id, exchange, symbol;


-- 方式3: 使用 DATE_TRUNC 查询每天的零点数据（更简洁）
SELECT 
    DATE_TRUNC('day', timestamp) as date,
    account_id,
    exchange,
    symbol,
    timestamp,
    open_left_long_qty,
    open_left_short_qty,
    daily_sum_buy_qty,
    daily_sum_sell_qty,
    avg_buy_prz,
    avg_sell_prz,
    daily_realized_pnl,
    cumulative_realized_pnl,
    left_long_qty,
    left_short_qty,
    close_prz,
    unrealized_pnl,
    daily_pnl,
    cumulative_pnl
FROM position_metrics
WHERE 
    timestamp::time = '00:00:00'  -- 直接比较时间部分
    AND symbol = 'tradoor_usdt'  -- 只查询 tradoor_usdt
    AND timestamp >= CURRENT_DATE - INTERVAL '30 days'  -- 最近30天
ORDER BY timestamp DESC, account_id, exchange, symbol;


-- 方式4: 查询所有零点数据，按日期汇总统计
SELECT 
    DATE(timestamp) as date,
    account_id,
    exchange,
    COUNT(DISTINCT symbol) as symbol_count,
    SUM(daily_realized_pnl) as total_daily_realized_pnl,
    SUM(unrealized_pnl) as total_unrealized_pnl,
    SUM(daily_pnl) as total_daily_pnl,
    MAX(cumulative_pnl) as max_cumulative_pnl
FROM position_metrics
WHERE 
    timestamp::time = '00:00:00'
    AND timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(timestamp), account_id, exchange
ORDER BY date DESC, account_id, exchange;
