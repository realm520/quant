-- 查询指定时间范围的买入数据（买入量和买入市值）
-- 支持 XT 和 Binance 两个交易所

-- 方式1: 查询 XT 交易所从 2025-12-16 00:00:00 到 2025-12-16 08:51:31 的买入数据
SELECT 
    symbol,
    account_id,
    COUNT(*) as buy_trade_count,  -- 买入成交笔数
    SUM(quantity) as total_buy_quantity,  -- 买入总量
    SUM(quote_quantity) as total_buy_value,  -- 买入总市值（使用 quote_quantity）
    SUM(quantity * price) as total_buy_value_calc,  -- 买入总市值（通过 quantity * price 计算，用于验证）
    AVG(price) as avg_buy_price,  -- 平均买入价格
    MIN(price) as min_buy_price,  -- 最低买入价格
    MAX(price) as max_buy_price,  -- 最高买入价格
    MIN(update_time) as first_trade_time,  -- 第一笔成交时间
    MAX(update_time) as last_trade_time    -- 最后一笔成交时间
FROM xt_trade_update
WHERE 
    update_time >= '2025-12-16 00:00:00'
    AND update_time <= '2025-12-16 08:51:31'
    AND side = 'BUY'
    -- 可选：按交易对筛选
    AND symbol = 'tradoor_usdt'
    -- 可选：按账号筛选
    -- AND account_id = 'your_account_id'
GROUP BY symbol, account_id
ORDER BY symbol, account_id;


-- 方式2: 查询 Binance 交易所从 2025-12-16 00:00:00 到 2025-12-16 08:51:31 的买入数据
SELECT 
    symbol,
    account_id,
    COUNT(*) as buy_trade_count,
    SUM(quantity) as total_buy_quantity,
    SUM(quote_quantity) as total_buy_value,
    SUM(quantity * price) as total_buy_value_calc,
    AVG(price) as avg_buy_price,
    MIN(price) as min_buy_price,
    MAX(price) as max_buy_price,
    MIN(transaction_time) as first_trade_time,
    MAX(transaction_time) as last_trade_time
FROM binance_trade_update
WHERE 
    transaction_time >= '2025-12-16 00:00:00'
    AND transaction_time <= '2025-12-16 08:51:31'
    AND side = 'BUY'
    -- 可选：按交易对筛选
    -- AND symbol = 'BTCUSDT'
    -- 可选：按账号筛选
    -- AND account_id = 'your_account_id'
GROUP BY symbol, account_id
ORDER BY symbol, account_id;


-- 方式3: 联合查询 XT 和 Binance（如果需要同时查看两个交易所）
SELECT 
    'xt' as exchange,
    symbol,
    account_id,
    COUNT(*) as buy_trade_count,
    SUM(quantity) as total_buy_quantity,
    SUM(quote_quantity) as total_buy_value,
    AVG(price) as avg_buy_price,
    MIN(update_time) as first_trade_time,
    MAX(update_time) as last_trade_time
FROM xt_trade_update
WHERE 
    update_time >= '2025-12-16 00:00:00'
    AND update_time <= '2025-12-16 08:51:31'
    AND side = 'BUY'
GROUP BY symbol, account_id

UNION ALL

SELECT 
    'binance' as exchange,
    symbol,
    account_id,
    COUNT(*) as buy_trade_count,
    SUM(quantity) as total_buy_quantity,
    SUM(quote_quantity) as total_buy_value,
    AVG(price) as avg_buy_price,
    MIN(transaction_time) as first_trade_time,
    MAX(transaction_time) as last_trade_time
FROM binance_trade_update
WHERE 
    transaction_time >= '2025-12-16 00:00:00'
    AND transaction_time <= '2025-12-16 08:51:31'
    AND side = 'BUY'
GROUP BY symbol, account_id

ORDER BY exchange, symbol, account_id;


-- 方式4: 查询 tradoor_usdt 从 2025-12-16 00:00:00 到 2025-12-16 08:51:31 的详细买入记录（逐笔）
SELECT 
    update_time,
    symbol,
    account_id,
    side,
    price,
    quantity,
    quote_quantity,
    order_id,
    trade_id
FROM xt_trade_update
WHERE 
    update_time >= '2025-12-16 00:00:00'
    AND update_time <= '2025-12-16 08:51:31'
    AND side = 'BUY'
    AND symbol = 'tradoor_usdt'
    -- 可选：按账号筛选
    -- AND account_id = 'your_account_id'
ORDER BY update_time ASC;
