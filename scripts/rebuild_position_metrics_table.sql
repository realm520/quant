-- ============================================
-- 重建 position_metrics 表（按新的列名）
-- ============================================

-- 1. 备份旧表（如果存在）
DROP TABLE IF EXISTS position_metrics_backup;
CREATE TABLE position_metrics_backup AS SELECT * FROM position_metrics;

-- 2. 删除旧表
DROP TABLE IF EXISTS position_metrics CASCADE;

-- 3. 创建新表（按你的列名）
CREATE TABLE position_metrics (
    id BIGSERIAL PRIMARY KEY,
    
    -- 时间戳
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    
    -- 账号和交易所信息
    account_id VARCHAR(64) NOT NULL,
    exchange VARCHAR(20) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    
    -- 1. 开盘持仓（昨收持仓）
    open_left_long_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    open_left_short_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    open_left_long_value NUMERIC(30, 10) NOT NULL DEFAULT 0,
    open_left_short_value NUMERIC(30, 10) NOT NULL DEFAULT 0,
    
    -- 2. 当日成交量（当日买入/卖出量）
    daily_sum_buy_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    daily_sum_sell_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    daily_sum_buy_value NUMERIC(30, 10) NOT NULL DEFAULT 0,
    daily_sum_sell_value NUMERIC(30, 10) NOT NULL DEFAULT 0,
    
    -- 3. 总持仓（初始持仓 + 当日成交量）
    long_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    short_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    long_value NUMERIC(30, 10) NOT NULL DEFAULT 0,
    short_value NUMERIC(30, 10) NOT NULL DEFAULT 0,
    
    -- 4. 平均价格
    avg_buy_prz NUMERIC(30, 10) NOT NULL DEFAULT 0,
    avg_sell_prz NUMERIC(30, 10) NOT NULL DEFAULT 0,
    
    -- 5. 轧差和已实现盈亏
    matched_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    daily_realized_pnl NUMERIC(30, 10) NOT NULL DEFAULT 0,
    cumulative_realized_pnl NUMERIC(30, 10) NOT NULL DEFAULT 0,
    
    -- 6. 收盘持仓（当日剩余仓位）
    left_long_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    left_short_qty NUMERIC(30, 10) NOT NULL DEFAULT 0,
    left_long_value NUMERIC(30, 10) NOT NULL DEFAULT 0,
    left_short_value NUMERIC(30, 10) NOT NULL DEFAULT 0,
    
    -- 7. 收盘价和未实现盈亏
    close_prz NUMERIC(30, 10) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(30, 10) NOT NULL DEFAULT 0,
    
    -- 8. PnL 汇总
    daily_pnl NUMERIC(30, 10) NOT NULL DEFAULT 0,
    cumulative_pnl NUMERIC(30, 10) NOT NULL DEFAULT 0,
    
    -- 元数据
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. 创建索引
CREATE INDEX idx_position_metrics_timestamp ON position_metrics(timestamp);
CREATE INDEX idx_position_metrics_account_exchange ON position_metrics(account_id, exchange);
CREATE INDEX idx_position_metrics_symbol ON position_metrics(symbol);
CREATE INDEX idx_position_metrics_account_symbol_time ON position_metrics(account_id, symbol, timestamp);
CREATE INDEX idx_position_metrics_exchange_symbol_time ON position_metrics(exchange, symbol, timestamp);

-- 5. 创建唯一约束（用于 ON CONFLICT DO UPDATE）
CREATE UNIQUE INDEX idx_position_metrics_unique 
ON position_metrics(timestamp, account_id, exchange, symbol);

-- 6. 验证表结构
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'position_metrics'
ORDER BY ordinal_position;
