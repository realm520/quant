-- 查询 rave 在 12月22日 23:00 到 12月23日 01:00 的 PositionMetrics 数据

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
    symbol = 'rave'
    AND timestamp >= '2025-12-22 23:00:00'
    AND timestamp <= '2025-12-23 01:00:00'
    -- 可选：按账号筛选
    -- AND account_id = 'your_account_id'
    -- 可选：按交易所筛选
    -- AND exchange = 'xt'
ORDER BY timestamp ASC, account_id, exchange;
