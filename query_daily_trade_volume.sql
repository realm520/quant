-- ============================================
-- 查询指定日期的总交易量
-- ============================================
-- 查询 2025-12-10 的总交易量（买入和卖出）

SELECT 
    DATE(update_time) as trade_date,
    account_id,
    symbol,
    -- 买入总量
    SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
    -- 卖出总量
    SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume,
    -- 总交易量（买入 + 卖出）
    SUM(quantity) as total_volume,
    -- 买入总市值
    SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity * price ELSE 0 END) as buy_value,
    -- 卖出总市值
    SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity * price ELSE 0 END) as sell_value,
    -- 总交易市值
    SUM(quantity * price) as total_value,
    -- 交易笔数
    COUNT(*) as trade_count
FROM xt_trade_update
WHERE 
    account_id = 'account_008'
    AND symbol = 'tradoor_usdt'
    AND DATE(update_time) = '2025-12-10'  -- 查询 12-10 的数据
GROUP BY DATE(update_time), account_id, symbol;

-- ============================================
-- 如果需要查看更详细的分时数据（按小时统计）
-- ============================================

SELECT 
    DATE(update_time) as trade_date,
    EXTRACT(HOUR FROM update_time) as hour,
    account_id,
    symbol,
    SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
    SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume,
    SUM(quantity) as total_volume,
    COUNT(*) as trade_count
FROM xt_trade_update
WHERE 
    account_id = 'account_008'
    AND symbol = 'tradoor_usdt'
    AND DATE(update_time) = '2025-12-10'
GROUP BY DATE(update_time), EXTRACT(HOUR FROM update_time), account_id, symbol
ORDER BY hour;

-- ============================================
-- 如果需要查看每分钟的交易量（前10分钟示例）
-- ============================================

SELECT 
    DATE_TRUNC('minute', update_time) as trade_minute,
    account_id,
    symbol,
    SUM(CASE WHEN UPPER(side) = 'BUY' THEN quantity ELSE 0 END) as buy_volume,
    SUM(CASE WHEN UPPER(side) = 'SELL' THEN quantity ELSE 0 END) as sell_volume,
    SUM(quantity) as total_volume,
    COUNT(*) as trade_count
FROM xt_trade_update
WHERE 
    account_id = 'account_008'
    AND symbol = 'tradoor_usdt'
    AND DATE(update_time) = '2025-12-10'
GROUP BY DATE_TRUNC('minute', update_time), account_id, symbol
ORDER BY trade_minute
LIMIT 10;
