-- 创建 XT 测试表，包含延迟监控字段
-- 用于测试消息队列方案的性能

-- 1. 创建 xt_order_update_test 表
CREATE TABLE IF NOT EXISTS xt_order_update_test (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    account_id VARCHAR(64),
    
    -- 订单信息
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(50) NOT NULL,
    client_order_id VARCHAR(50),
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(30) NOT NULL,
    position_side VARCHAR(10),
    quantity NUMERIC(30, 10) NOT NULL,
    price NUMERIC(30, 10),
    filled_quantity NUMERIC(30, 10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    time_in_force VARCHAR(10),
    
    -- 时间信息
    create_time TIMESTAMP WITHOUT TIME ZONE,
    update_time_order TIMESTAMP WITHOUT TIME ZONE,
    
    -- 延迟监控字段
    message_received_at TIMESTAMP WITHOUT TIME ZONE,  -- 消息接收时间
    queue_wait_time_ms NUMERIC(10, 2),  -- 队列等待时间（毫秒）
    processing_duration_ms NUMERIC(10, 2),  -- 处理耗时（毫秒）
    database_write_duration_ms NUMERIC(10, 2),  -- 数据库写入耗时（毫秒）
    timestamp_from_raw TIMESTAMP WITHOUT TIME ZONE,  -- 从 raw_data 解析的 timestamp 时间
    delay_from_timestamp_ms NUMERIC(10, 2),  -- 与 timestamp 的延迟（毫秒）
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_xt_order_test_id_time ON xt_order_update_test(order_id, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_test_symbol_status_time ON xt_order_update_test(symbol, status, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_test_time ON xt_order_update_test(update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_test_account_time ON xt_order_update_test(account_id, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_test_received_at ON xt_order_update_test(message_received_at);
CREATE INDEX IF NOT EXISTS idx_xt_order_test_queue_wait ON xt_order_update_test(queue_wait_time_ms);

-- 2. 创建 xt_position_update_test 表
CREATE TABLE IF NOT EXISTS xt_position_update_test (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    account_id VARCHAR(64),
    
    -- 持仓信息
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity NUMERIC(30, 10) NOT NULL,
    entry_price NUMERIC(30, 10),
    mark_price NUMERIC(30, 10),
    liquidation_price NUMERIC(30, 10),
    unrealized_pnl NUMERIC(30, 10),
    leverage INTEGER,
    margin NUMERIC(30, 10),
    roe NUMERIC(10, 4),
    
    -- 延迟监控字段
    message_received_at TIMESTAMP WITHOUT TIME ZONE,  -- 消息接收时间
    queue_wait_time_ms NUMERIC(10, 2),  -- 队列等待时间（毫秒）
    processing_duration_ms NUMERIC(10, 2),  -- 处理耗时（毫秒）
    database_write_duration_ms NUMERIC(10, 2),  -- 数据库写入耗时（毫秒）
    timestamp_from_raw TIMESTAMP WITHOUT TIME ZONE,  -- 从 raw_data 解析的 timestamp 时间
    delay_from_timestamp_ms NUMERIC(10, 2),  -- 与 timestamp 的延迟（毫秒）
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_xt_position_test_symbol_time ON xt_position_update_test(symbol, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_position_test_side_time ON xt_position_update_test(side, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_position_test_time ON xt_position_update_test(update_time);
CREATE INDEX IF NOT EXISTS idx_xt_position_test_account_time ON xt_position_update_test(account_id, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_position_test_received_at ON xt_position_update_test(message_received_at);
CREATE INDEX IF NOT EXISTS idx_xt_position_test_queue_wait ON xt_position_update_test(queue_wait_time_ms);

-- 3. 创建 xt_trade_update_test 表
CREATE TABLE IF NOT EXISTS xt_trade_update_test (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    account_id VARCHAR(64),
    
    -- 交易信息
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(50) NOT NULL,
    trade_id VARCHAR(50) NOT NULL,
    
    -- 成交详情
    side VARCHAR(10) NOT NULL,
    price NUMERIC(30, 10) NOT NULL,
    quantity NUMERIC(30, 10) NOT NULL,
    quote_quantity NUMERIC(30, 10) NOT NULL,
    
    -- 手续费
    commission NUMERIC(30, 10),
    commission_asset VARCHAR(20),
    
    -- 是否为Maker
    is_maker BOOLEAN DEFAULT FALSE,
    
    -- 持仓方向
    position_side VARCHAR(10),
    
    -- 延迟监控字段
    message_received_at TIMESTAMP WITHOUT TIME ZONE,  -- 消息接收时间
    queue_wait_time_ms NUMERIC(10, 2),  -- 队列等待时间（毫秒）
    processing_duration_ms NUMERIC(10, 2),  -- 处理耗时（毫秒）
    database_write_duration_ms NUMERIC(10, 2),  -- 数据库写入耗时（毫秒）
    timestamp_from_raw TIMESTAMP WITHOUT TIME ZONE,  -- 从 raw_data 解析的 timestamp 时间
    delay_from_timestamp_ms NUMERIC(10, 2),  -- 与 timestamp 的延迟（毫秒）
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_xt_trade_test_symbol_time ON xt_trade_update_test(symbol, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_trade_test_order_trade ON xt_trade_update_test(order_id, trade_id);
CREATE INDEX IF NOT EXISTS idx_xt_trade_test_time ON xt_trade_update_test(update_time);
CREATE INDEX IF NOT EXISTS idx_xt_trade_test_account_time ON xt_trade_update_test(account_id, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_trade_test_received_at ON xt_trade_update_test(message_received_at);
CREATE INDEX IF NOT EXISTS idx_xt_trade_test_queue_wait ON xt_trade_update_test(queue_wait_time_ms);
CREATE INDEX IF NOT EXISTS idx_xt_trade_test_delay ON xt_trade_update_test(delay_from_timestamp_ms);

-- 添加注释说明
COMMENT ON TABLE xt_order_update_test IS 'XT 订单更新测试表，包含延迟监控字段';
COMMENT ON TABLE xt_position_update_test IS 'XT 持仓更新测试表，包含延迟监控字段';
COMMENT ON TABLE xt_trade_update_test IS 'XT 成交更新测试表，包含延迟监控字段';

COMMENT ON COLUMN xt_order_update_test.message_received_at IS '消息接收时间（WebSocket消息到达时间）';
COMMENT ON COLUMN xt_order_update_test.queue_wait_time_ms IS '队列等待时间（毫秒）：从消息接收到开始处理的时间';
COMMENT ON COLUMN xt_order_update_test.processing_duration_ms IS '处理耗时（毫秒）：从开始处理到完成的时间';
COMMENT ON COLUMN xt_order_update_test.database_write_duration_ms IS '数据库写入耗时（毫秒）：session.commit() 的耗时';
COMMENT ON COLUMN xt_order_update_test.timestamp_from_raw IS '从 raw_data 解析的 timestamp 字段转换的时间';
COMMENT ON COLUMN xt_order_update_test.delay_from_timestamp_ms IS '与 timestamp 的延迟（毫秒）：message_received_at - timestamp_from_raw';

COMMENT ON COLUMN xt_position_update_test.message_received_at IS '消息接收时间（WebSocket消息到达时间）';
COMMENT ON COLUMN xt_position_update_test.queue_wait_time_ms IS '队列等待时间（毫秒）：从消息接收到开始处理的时间';
COMMENT ON COLUMN xt_position_update_test.processing_duration_ms IS '处理耗时（毫秒）：从开始处理到完成的时间';
COMMENT ON COLUMN xt_position_update_test.database_write_duration_ms IS '数据库写入耗时（毫秒）：session.commit() 的耗时';
COMMENT ON COLUMN xt_position_update_test.timestamp_from_raw IS '从 raw_data 解析的 timestamp 字段转换的时间';
COMMENT ON COLUMN xt_position_update_test.delay_from_timestamp_ms IS '与 timestamp 的延迟（毫秒）：message_received_at - timestamp_from_raw';

COMMENT ON COLUMN xt_trade_update_test.message_received_at IS '消息接收时间（WebSocket消息到达时间）';
COMMENT ON COLUMN xt_trade_update_test.queue_wait_time_ms IS '队列等待时间（毫秒）：从消息接收到开始处理的时间';
COMMENT ON COLUMN xt_trade_update_test.processing_duration_ms IS '处理耗时（毫秒）：从开始处理到完成的时间';
COMMENT ON COLUMN xt_trade_update_test.database_write_duration_ms IS '数据库写入耗时（毫秒）：session.commit() 的耗时';
COMMENT ON COLUMN xt_trade_update_test.timestamp_from_raw IS '从 raw_data 解析的 timestamp 字段转换的时间';
COMMENT ON COLUMN xt_trade_update_test.delay_from_timestamp_ms IS '与 timestamp 的延迟（毫秒）：message_received_at - timestamp_from_raw';
