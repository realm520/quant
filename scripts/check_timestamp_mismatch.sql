-- 查询 xt_trade_update 表中时间错乱的记录
-- 对比 raw_data.timestamp 和 update_time 字段

-- 方法1: 统计时间差超过 1 秒的记录数量
WITH parsed_data AS (
    SELECT 
        id,
        trade_id,
        order_id,
        symbol,
        account_id,
        update_time,
        raw_data,
        -- 从 raw_data JSON 中提取 timestamp（毫秒）
        (raw_data::json->>'timestamp')::bigint AS raw_timestamp_ms,
        -- 将 timestamp 除以 1000 转换为 datetime
        to_timestamp((raw_data::json->>'timestamp')::bigint / 1000.0) AS timestamp_dt
    FROM xt_trade_update
    WHERE raw_data IS NOT NULL
      AND raw_data::json->>'timestamp' IS NOT NULL
)
SELECT 
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE ABS(EXTRACT(EPOCH FROM (update_time - timestamp_dt))) > 1) AS mismatched_count,
    COUNT(*) FILTER (WHERE ABS(EXTRACT(EPOCH FROM (update_time - timestamp_dt))) <= 1) AS matched_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE ABS(EXTRACT(EPOCH FROM (update_time - timestamp_dt))) > 1) / COUNT(*), 2) AS mismatch_percentage
FROM parsed_data;


-- 方法2: 详细列出时间差超过 1 秒的记录（前 100 条）
WITH parsed_data AS (
    SELECT 
        id,
        trade_id,
        order_id,
        symbol,
        account_id,
        update_time,
        raw_data,
        (raw_data::json->>'timestamp')::bigint AS raw_timestamp_ms,
        to_timestamp((raw_data::json->>'timestamp')::bigint / 1000.0) AS timestamp_dt,
        ABS(EXTRACT(EPOCH FROM (update_time - to_timestamp((raw_data::json->>'timestamp')::bigint / 1000.0)))) AS time_diff_seconds
    FROM xt_trade_update
    WHERE raw_data IS NOT NULL
      AND raw_data::json->>'timestamp' IS NOT NULL
)
SELECT 
    id,
    trade_id,
    order_id,
    symbol,
    account_id,
    raw_timestamp_ms,
    timestamp_dt AS timestamp_from_raw_data,
    update_time AS update_time_in_db,
    ROUND(time_diff_seconds, 2) AS time_diff_seconds,
    ROUND(time_diff_seconds / 86400.0, 2) AS time_diff_days
FROM parsed_data
WHERE time_diff_seconds > 1
ORDER BY time_diff_seconds DESC
LIMIT 100;


-- 方法3: 按时间差范围统计
WITH parsed_data AS (
    SELECT 
        id,
        ABS(EXTRACT(EPOCH FROM (update_time - to_timestamp((raw_data::json->>'timestamp')::bigint / 1000.0)))) AS time_diff_seconds
    FROM xt_trade_update
    WHERE raw_data IS NOT NULL
      AND raw_data::json->>'timestamp' IS NOT NULL
)
SELECT 
    CASE 
        WHEN time_diff_seconds <= 1 THEN '0-1秒'
        WHEN time_diff_seconds <= 60 THEN '1秒-1分钟'
        WHEN time_diff_seconds <= 3600 THEN '1分钟-1小时'
        WHEN time_diff_seconds <= 86400 THEN '1小时-1天'
        WHEN time_diff_seconds <= 604800 THEN '1天-1周'
        ELSE '超过1周'
    END AS time_diff_range,
    COUNT(*) AS record_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percentage
FROM parsed_data
GROUP BY 
    CASE 
        WHEN time_diff_seconds <= 1 THEN '0-1秒'
        WHEN time_diff_seconds <= 60 THEN '1秒-1分钟'
        WHEN time_diff_seconds <= 3600 THEN '1分钟-1小时'
        WHEN time_diff_seconds <= 86400 THEN '1小时-1天'
        WHEN time_diff_seconds <= 604800 THEN '1天-1周'
        ELSE '超过1周'
    END
ORDER BY 
    CASE 
        WHEN time_diff_seconds <= 1 THEN 1
        WHEN time_diff_seconds <= 60 THEN 2
        WHEN time_diff_seconds <= 3600 THEN 3
        WHEN time_diff_seconds <= 86400 THEN 4
        WHEN time_diff_seconds <= 604800 THEN 5
        ELSE 6
    END;


-- 方法4: 按账户和交易对统计时间错乱情况
WITH parsed_data AS (
    SELECT 
        account_id,
        symbol,
        ABS(EXTRACT(EPOCH FROM (update_time - to_timestamp((raw_data::json->>'timestamp')::bigint / 1000.0)))) AS time_diff_seconds
    FROM xt_trade_update
    WHERE raw_data IS NOT NULL
      AND raw_data::json->>'timestamp' IS NOT NULL
)
SELECT 
    account_id,
    symbol,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE time_diff_seconds > 1) AS mismatched_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE time_diff_seconds > 1) / COUNT(*), 2) AS mismatch_percentage,
    ROUND(AVG(time_diff_seconds), 2) AS avg_time_diff_seconds,
    ROUND(MAX(time_diff_seconds), 2) AS max_time_diff_seconds
FROM parsed_data
GROUP BY account_id, symbol
HAVING COUNT(*) FILTER (WHERE time_diff_seconds > 1) > 0
ORDER BY mismatched_count DESC;
