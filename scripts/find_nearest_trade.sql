-- 查找 xt_trade_update 表中与指定时间戳最接近的记录
-- 时间戳: 1765967624859 (2025-12-17 10:33:44.859)

-- 方法1: 查找最接近的记录（按时间差绝对值排序）
SELECT 
    id,
    trade_id,
    order_id,
    symbol,
    account_id,
    side,
    price,
    quantity,
    update_time,
    -- 计算时间差（毫秒）
    ABS(EXTRACT(EPOCH FROM (update_time - to_timestamp(1765967624859 / 1000.0))) * 1000) AS time_diff_ms,
    -- 显示可读时间
    to_char(update_time, 'YYYY-MM-DD HH24:MI:SS.MS') AS readable_time
FROM xt_trade_update
ORDER BY ABS(EXTRACT(EPOCH FROM (update_time - to_timestamp(1765967624859 / 1000.0))))
LIMIT 10;


-- 方法2: 查找指定时间窗口内的所有记录（前后各5秒）
SELECT 
    id,
    trade_id,
    order_id,
    symbol,
    account_id,
    side,
    price,
    quantity,
    update_time,
    ABS(EXTRACT(EPOCH FROM (update_time - to_timestamp(1765967624859 / 1000.0))) * 1000) AS time_diff_ms,
    to_char(update_time, 'YYYY-MM-DD HH24:MI:SS.MS') AS readable_time
FROM xt_trade_update
WHERE update_time >= to_timestamp(1765967624859 / 1000.0) - interval '5 seconds'
  AND update_time <= to_timestamp(1765967624859 / 1000.0) + interval '5 seconds'
ORDER BY update_time;


-- 方法3: 查找完全相同的记录（精确匹配到毫秒）
SELECT 
    id,
    trade_id,
    order_id,
    symbol,
    account_id,
    side,
    price,
    quantity,
    update_time,
    to_char(update_time, 'YYYY-MM-DD HH24:MI:SS.MS') AS readable_time
FROM xt_trade_update
WHERE update_time = to_timestamp(1765967624859 / 1000.0);


-- 方法4: 如果 update_time 存储的是毫秒时间戳（bigint），而不是 timestamp 类型
-- 注意：这个查询假设 update_time 是 timestamp 类型，如果是 bigint 存储毫秒，需要调整
-- SELECT 
--     id,
--     trade_id,
--     order_id,
--     symbol,
--     account_id,
--     side,
--     price,
--     quantity,
--     update_time,
--     ABS(update_time - 1765967624859) AS time_diff_ms
-- FROM xt_trade_update
-- ORDER BY ABS(update_time - 1765967624859)
-- LIMIT 10;

