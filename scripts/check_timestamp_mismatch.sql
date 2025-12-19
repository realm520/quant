-- 查询 update_time 和 raw_data 中 timestamp 不匹配的成交记录
-- 使用 PostgreSQL 的 JSON 函数解析 raw_data 中的 timestamp 字段

WITH parsed_data AS (
    SELECT 
        id,
        update_time,
        account_id,
        symbol,
        order_id,
        trade_id,
        side,
        price,
        quantity,
        raw_data,
        created_at,
        -- 从 raw_data JSON 中提取 timestamp（毫秒级）
        (raw_data::json->>'timestamp')::bigint AS timestamp_ms,
        -- 将 timestamp 转换为 datetime（除以 1000 转为秒，然后转换为 timestamp）
        to_timestamp((raw_data::json->>'timestamp')::bigint / 1000.0) AS timestamp_dt
    FROM xt_trade_update
    WHERE raw_data IS NOT NULL
      AND raw_data::json->>'timestamp' IS NOT NULL
)
SELECT 
    id,
    account_id,
    symbol,
    order_id,
    trade_id,
    side,
    price,
    quantity,
    update_time AS db_update_time,
    timestamp_dt AS raw_timestamp_dt,
    timestamp_ms AS raw_timestamp_ms,
    -- 计算时间差（秒）
    EXTRACT(EPOCH FROM (update_time - timestamp_dt)) AS time_diff_seconds,
    ABS(EXTRACT(EPOCH FROM (update_time - timestamp_dt))) AS abs_time_diff_seconds,
    created_at,
    raw_data
FROM parsed_data
WHERE ABS(EXTRACT(EPOCH FROM (update_time - timestamp_dt))) > 1.0  -- 时间差超过 1 秒
ORDER BY update_time DESC
LIMIT 10;
