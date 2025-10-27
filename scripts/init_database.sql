-- 多交易所WebSocket数据存储数据库初始化脚本
-- 支持：Binance、OKX、Gate.io
-- PostgreSQL

-- 创建数据库
CREATE DATABASE IF NOT EXISTS trading;

\c trading;

-- ============================================================
-- Binance 表结构
-- ============================================================

-- 账户更新表
CREATE TABLE IF NOT EXISTS account_updates (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,
    event_type VARCHAR(20) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    transaction_time TIMESTAMP NOT NULL,
    
    -- 余额信息
    asset VARCHAR(20),
    wallet_balance NUMERIC(30, 10),
    cross_wallet_balance NUMERIC(30, 10),
    balance_change NUMERIC(30, 10),
    
    -- 持仓信息
    symbol VARCHAR(20),
    position_side VARCHAR(10),
    position_amount NUMERIC(30, 10),
    entry_price NUMERIC(30, 10),
    unrealized_pnl NUMERIC(30, 10),
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_account_exchange_time ON account_updates(exchange, event_time);
CREATE INDEX IF NOT EXISTS idx_account_symbol_time ON account_updates(symbol, event_time);
CREATE INDEX IF NOT EXISTS idx_account_asset ON account_updates(asset);

-- 订单更新表
CREATE TABLE IF NOT EXISTS order_updates (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,
    event_type VARCHAR(20) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    transaction_time TIMESTAMP NOT NULL,
    
    -- 订单信息
    symbol VARCHAR(20) NOT NULL,
    client_order_id VARCHAR(50),
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(30) NOT NULL,
    time_in_force VARCHAR(10),
    original_quantity NUMERIC(30, 10) NOT NULL,
    original_price NUMERIC(30, 10),
    average_price NUMERIC(30, 10),
    
    -- 执行信息
    order_status VARCHAR(20) NOT NULL,
    order_id BIGINT NOT NULL,
    last_filled_quantity NUMERIC(30, 10),
    cumulative_filled_quantity NUMERIC(30, 10) NOT NULL,
    last_filled_price NUMERIC(30, 10),
    
    -- 手续费
    commission_amount NUMERIC(30, 10),
    commission_asset VARCHAR(20),
    
    -- 持仓方向
    position_side VARCHAR(10),
    is_reduce_only BOOLEAN DEFAULT FALSE,
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_order_id_time ON order_updates(order_id, event_time);
CREATE INDEX IF NOT EXISTS idx_order_symbol_status ON order_updates(symbol, order_status);
CREATE INDEX IF NOT EXISTS idx_order_exchange_symbol_time ON order_updates(exchange, symbol, event_time);
CREATE INDEX IF NOT EXISTS idx_order_client_id ON order_updates(client_order_id);

-- 成交记录表
CREATE TABLE IF NOT EXISTS trade_updates (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,
    event_type VARCHAR(20) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    transaction_time TIMESTAMP NOT NULL,
    
    -- 交易信息
    symbol VARCHAR(20) NOT NULL,
    order_id BIGINT NOT NULL,
    trade_id BIGINT NOT NULL UNIQUE,
    
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
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_trade_symbol_time ON trade_updates(symbol, transaction_time);
CREATE INDEX IF NOT EXISTS idx_trade_order_trade ON trade_updates(order_id, trade_id);
CREATE INDEX IF NOT EXISTS idx_trade_id ON trade_updates(trade_id);

-- ListenKey记录表
CREATE TABLE IF NOT EXISTS listen_keys (
    id SERIAL PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,
    listen_key VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_keepalive TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_listen_key_active ON listen_keys(is_active);

-- 创建视图：最新订单状态
CREATE OR REPLACE VIEW latest_orders AS
SELECT DISTINCT ON (order_id)
    *
FROM order_updates
ORDER BY order_id, event_time DESC;

-- 创建视图：每日成交统计
CREATE OR REPLACE VIEW daily_trade_stats AS
SELECT
    DATE(transaction_time) as trade_date,
    symbol,
    exchange,
    COUNT(*) as trade_count,
    SUM(quantity) as total_quantity,
    SUM(quote_quantity) as total_volume,
    SUM(commission) as total_commission,
    AVG(price) as avg_price
FROM trade_updates
GROUP BY DATE(transaction_time), symbol, exchange
ORDER BY trade_date DESC, total_volume DESC;

COMMENT ON TABLE account_updates IS 'Binance账户和持仓更新记录（通用）';
COMMENT ON TABLE order_updates IS 'Binance订单更新记录（通用）';
COMMENT ON TABLE trade_updates IS 'Binance成交记录（通用）';
COMMENT ON TABLE listen_keys IS 'Binance WebSocket ListenKey记录';

-- ============================================================
-- OKX 表结构
-- ============================================================

-- OKX账户余额表
CREATE TABLE IF NOT EXISTS okx_account_balances (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    
    -- 账户总览
    total_eq NUMERIC(30, 10),          -- 账户总权益(USD)
    iso_eq NUMERIC(30, 10),            -- 逐仓账户权益
    adj_eq NUMERIC(30, 10),            -- 调整后的账户权益
    notional_usd NUMERIC(30, 10),      -- 持仓折合USD
    
    -- 币种详情
    currency VARCHAR(20) NOT NULL,      -- 币种
    available_bal NUMERIC(30, 10),      -- 可用余额
    cash_bal NUMERIC(30, 10),          -- 现金余额
    frozen_bal NUMERIC(30, 10),        -- 冻结余额
    equity NUMERIC(30, 10),            -- 币种权益
    upl NUMERIC(30, 10),               -- 未实现盈亏
    
    -- 元数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_okx_balance_time ON okx_account_balances(update_time);
CREATE INDEX IF NOT EXISTS idx_okx_balance_currency ON okx_account_balances(currency);
CREATE INDEX IF NOT EXISTS idx_okx_balance_currency_time ON okx_account_balances(currency, update_time);

-- OKX持仓表
CREATE TABLE IF NOT EXISTS okx_positions (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    
    -- 产品信息
    inst_id VARCHAR(50) NOT NULL,      -- 产品ID (如BTC-USDT-SWAP)
    inst_type VARCHAR(20),             -- 产品类型 (SWAP/FUTURES/SPOT)
    
    -- 持仓信息
    pos_side VARCHAR(10),              -- 持仓方向 (long/short/net)
    pos NUMERIC(30, 10),               -- 持仓数量
    pos_ccy VARCHAR(20),               -- 持仓币种
    
    -- 价格信息
    avg_px NUMERIC(30, 10),            -- 开仓均价
    mark_px NUMERIC(30, 10),           -- 标记价格
    liq_px NUMERIC(30, 10),            -- 预估强平价
    
    -- 盈亏信息
    upl NUMERIC(30, 10),               -- 未实现盈亏
    upl_ratio NUMERIC(20, 10),         -- 未实现盈亏比例
    
    -- 保证金信息
    margin NUMERIC(30, 10),            -- 保证金
    imr NUMERIC(30, 10),               -- 初始保证金
    mmr NUMERIC(30, 10),               -- 维持保证金
    
    -- 杠杆
    lever NUMERIC(10, 2),              -- 杠杆倍数
    
    -- 元数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_okx_position_time ON okx_positions(update_time);
CREATE INDEX IF NOT EXISTS idx_okx_position_inst ON okx_positions(inst_id);
CREATE INDEX IF NOT EXISTS idx_okx_position_inst_time ON okx_positions(inst_id, update_time);
CREATE INDEX IF NOT EXISTS idx_okx_position_side ON okx_positions(pos_side);

-- OKX订单表
CREATE TABLE IF NOT EXISTS okx_orders (
    id BIGSERIAL PRIMARY KEY,
    
    -- 产品信息
    inst_id VARCHAR(50) NOT NULL,      -- 产品ID
    inst_type VARCHAR(20),             -- 产品类型
    
    -- 订单ID
    ord_id VARCHAR(50) NOT NULL,       -- 订单ID
    cl_ord_id VARCHAR(50),             -- 客户订单ID
    
    -- 订单信息
    ord_type VARCHAR(20) NOT NULL,     -- 订单类型 (limit/market/post_only)
    side VARCHAR(10) NOT NULL,         -- 订单方向 (buy/sell)
    pos_side VARCHAR(10),              -- 持仓方向 (long/short/net)
    
    -- 数量和价格
    sz NUMERIC(30, 10) NOT NULL,       -- 委托数量
    px NUMERIC(30, 10),                -- 委托价格
    avg_px NUMERIC(30, 10),            -- 成交均价
    
    -- 成交信息
    acc_fill_sz NUMERIC(30, 10),       -- 累计成交数量
    fill_sz NUMERIC(30, 10),           -- 最新成交数量
    fill_px NUMERIC(30, 10),           -- 最新成交价格
    
    -- 订单状态
    state VARCHAR(20) NOT NULL,        -- 订单状态 (live/partially_filled/filled/canceled)
    
    -- 手续费
    fee NUMERIC(30, 10),               -- 手续费
    fee_ccy VARCHAR(20),               -- 手续费币种
    rebate NUMERIC(30, 10),            -- 返佣
    rebate_ccy VARCHAR(20),            -- 返佣币种
    
    -- 时间
    c_time TIMESTAMP,                  -- 创建时间
    u_time TIMESTAMP NOT NULL,         -- 更新时间
    fill_time TIMESTAMP,               -- 最新成交时间
    
    -- 其他
    reduce_only BOOLEAN DEFAULT FALSE, -- 是否只减仓
    td_mode VARCHAR(20),               -- 交易模式 (isolated/cross)
    
    -- 元数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_okx_order_ord_id ON okx_orders(ord_id);
CREATE INDEX IF NOT EXISTS idx_okx_order_cl_ord_id ON okx_orders(cl_ord_id);
CREATE INDEX IF NOT EXISTS idx_okx_order_inst ON okx_orders(inst_id);
CREATE INDEX IF NOT EXISTS idx_okx_order_state ON okx_orders(state);
CREATE INDEX IF NOT EXISTS idx_okx_order_inst_state ON okx_orders(inst_id, state);
CREATE INDEX IF NOT EXISTS idx_okx_order_time ON okx_orders(u_time);

-- OKX成交表
CREATE TABLE IF NOT EXISTS okx_trades (
    id BIGSERIAL PRIMARY KEY,
    
    -- 产品信息
    inst_id VARCHAR(50) NOT NULL,      -- 产品ID
    
    -- 订单和成交ID
    ord_id VARCHAR(50) NOT NULL,       -- 订单ID
    trade_id VARCHAR(50),              -- 成交ID
    
    -- 成交信息
    side VARCHAR(10) NOT NULL,         -- 方向
    fill_px NUMERIC(30, 10) NOT NULL,  -- 成交价格
    fill_sz NUMERIC(30, 10) NOT NULL,  -- 成交数量
    
    -- 手续费
    fee NUMERIC(30, 10),               -- 手续费
    fee_ccy VARCHAR(20),               -- 手续费币种
    
    -- 时间
    fill_time TIMESTAMP NOT NULL,      -- 成交时间
    
    -- 元数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_okx_trade_inst ON okx_trades(inst_id);
CREATE INDEX IF NOT EXISTS idx_okx_trade_ord_id ON okx_trades(ord_id);
CREATE INDEX IF NOT EXISTS idx_okx_trade_id ON okx_trades(trade_id);
CREATE INDEX IF NOT EXISTS idx_okx_trade_time ON okx_trades(fill_time);
CREATE INDEX IF NOT EXISTS idx_okx_trade_inst_time ON okx_trades(inst_id, fill_time);

-- ============================================================
-- OKX 视图
-- ============================================================

-- 创建视图：最新OKX持仓
CREATE OR REPLACE VIEW okx_latest_positions AS
SELECT DISTINCT ON (inst_id, pos_side)
    *
FROM okx_positions
WHERE pos > 0
ORDER BY inst_id, pos_side, update_time DESC;

-- 创建视图：最新OKX订单
CREATE OR REPLACE VIEW okx_latest_orders AS
SELECT DISTINCT ON (ord_id)
    *
FROM okx_orders
ORDER BY ord_id, u_time DESC;

-- 创建视图：OKX每日交易统计
CREATE OR REPLACE VIEW okx_daily_trade_stats AS
SELECT
    DATE(fill_time) as trade_date,
    inst_id,
    side,
    COUNT(*) as trade_count,
    SUM(fill_sz) as total_quantity,
    SUM(fill_px * fill_sz) as total_volume,
    AVG(fill_px) as avg_price,
    SUM(fee) as total_fee
FROM okx_trades
GROUP BY DATE(fill_time), inst_id, side
ORDER BY trade_date DESC, total_volume DESC;

-- ============================================================
-- 表注释
-- ============================================================

COMMENT ON TABLE okx_account_balances IS 'OKX账户余额记录';
COMMENT ON TABLE okx_positions IS 'OKX持仓记录';
COMMENT ON TABLE okx_orders IS 'OKX订单记录';
COMMENT ON TABLE okx_trades IS 'OKX成交记录';

-- ============================================================
-- 完成
-- ============================================================

-- ============================================================
-- Gate.io 表结构
-- ============================================================

-- Gate.io账户余额表
CREATE TABLE IF NOT EXISTS gate_account_balances (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    user_id BIGINT,
    currency VARCHAR(20) NOT NULL,
    total NUMERIC(30, 10),
    available NUMERIC(30, 10),
    unrealised_pnl NUMERIC(30, 10),
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gate_balance_time ON gate_account_balances(update_time);
CREATE INDEX IF NOT EXISTS idx_gate_balance_currency ON gate_account_balances(currency);
CREATE INDEX IF NOT EXISTS idx_gate_balance_currency_time ON gate_account_balances(currency, update_time);

-- Gate.io持仓表
CREATE TABLE IF NOT EXISTS gate_positions (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    contract VARCHAR(50) NOT NULL,
    size NUMERIC(30, 10),
    leverage NUMERIC(10, 2),
    margin NUMERIC(30, 10),
    entry_price NUMERIC(30, 10),
    mark_price NUMERIC(30, 10),
    liq_price NUMERIC(30, 10),
    unrealised_pnl NUMERIC(30, 10),
    realised_pnl NUMERIC(30, 10),
    mode VARCHAR(20),
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gate_position_time ON gate_positions(update_time);
CREATE INDEX IF NOT EXISTS idx_gate_position_contract ON gate_positions(contract);
CREATE INDEX IF NOT EXISTS idx_gate_position_contract_time ON gate_positions(contract, update_time);

-- Gate.io订单表
CREATE TABLE IF NOT EXISTS gate_orders (
    id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL UNIQUE,
    contract VARCHAR(50) NOT NULL,
    size NUMERIC(30, 10) NOT NULL,
    price NUMERIC(30, 10),
    left NUMERIC(30, 10),
    filled_total NUMERIC(30, 10),
    status VARCHAR(20) NOT NULL,
    create_time TIMESTAMP,
    finish_time TIMESTAMP,
    update_time TIMESTAMP NOT NULL,
    reduce_only BOOLEAN DEFAULT FALSE,
    tif VARCHAR(20),
    text VARCHAR(100),
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gate_order_id ON gate_orders(order_id);
CREATE INDEX IF NOT EXISTS idx_gate_order_contract ON gate_orders(contract);
CREATE INDEX IF NOT EXISTS idx_gate_order_status ON gate_orders(status);
CREATE INDEX IF NOT EXISTS idx_gate_order_contract_status ON gate_orders(contract, status);
CREATE INDEX IF NOT EXISTS idx_gate_order_time ON gate_orders(update_time);

-- Gate.io成交表
CREATE TABLE IF NOT EXISTS gate_trades (
    id BIGSERIAL PRIMARY KEY,
    trade_id VARCHAR(50) NOT NULL UNIQUE,
    order_id VARCHAR(50) NOT NULL,
    contract VARCHAR(50) NOT NULL,
    size NUMERIC(30, 10) NOT NULL,
    price NUMERIC(30, 10) NOT NULL,
    role VARCHAR(10),
    create_time TIMESTAMP NOT NULL,
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gate_trade_id ON gate_trades(trade_id);
CREATE INDEX IF NOT EXISTS idx_gate_trade_order_id ON gate_trades(order_id);
CREATE INDEX IF NOT EXISTS idx_gate_trade_contract ON gate_trades(contract);
CREATE INDEX IF NOT EXISTS idx_gate_trade_time ON gate_trades(create_time);
CREATE INDEX IF NOT EXISTS idx_gate_trade_contract_time ON gate_trades(contract, create_time);

-- ============================================================
-- Gate.io 视图
-- ============================================================

-- Gate.io最新持仓
CREATE OR REPLACE VIEW gate_latest_positions AS
SELECT DISTINCT ON (contract)
    *
FROM gate_positions
WHERE size != 0
ORDER BY contract, update_time DESC;

-- Gate.io最新订单
CREATE OR REPLACE VIEW gate_latest_orders AS
SELECT DISTINCT ON (order_id)
    *
FROM gate_orders
ORDER BY order_id, update_time DESC;

-- Gate.io每日交易统计
CREATE OR REPLACE VIEW gate_daily_trade_stats AS
SELECT
    DATE(create_time) as trade_date,
    contract,
    COUNT(*) as trade_count,
    SUM(ABS(size)) as total_quantity,
    SUM(price * ABS(size)) as total_volume,
    AVG(price) as avg_price
FROM gate_trades
GROUP BY DATE(create_time), contract
ORDER BY trade_date DESC, total_volume DESC;

-- ============================================================
-- Gate.io 表注释
-- ============================================================

COMMENT ON TABLE gate_account_balances IS 'Gate.io账户余额记录';
COMMENT ON TABLE gate_positions IS 'Gate.io持仓记录';
COMMENT ON TABLE gate_orders IS 'Gate.io订单记录';
COMMENT ON TABLE gate_trades IS 'Gate.io成交记录';

-- ============================================================
-- XT WebSocket 表结构
-- ============================================================

-- XT WebSocket账户更新表
CREATE TABLE IF NOT EXISTS xt_account_updates (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    
    -- 余额信息
    currency VARCHAR(20) NOT NULL,
    available NUMERIC(30, 10) NOT NULL,
    frozen NUMERIC(30, 10) NOT NULL,
    total NUMERIC(30, 10) NOT NULL,
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_xt_account_currency_time ON xt_account_updates(currency, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_account_time ON xt_account_updates(update_time);

-- XT WebSocket持仓更新表
CREATE TABLE IF NOT EXISTS xt_position_updates (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    
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
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_xt_position_symbol_time ON xt_position_updates(symbol, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_position_side_time ON xt_position_updates(side, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_position_time ON xt_position_updates(update_time);

-- XT WebSocket订单更新表
CREATE TABLE IF NOT EXISTS xt_order_updates (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    
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
    create_time TIMESTAMP,
    update_time_order TIMESTAMP,
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_xt_order_id_time ON xt_order_updates(order_id, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_symbol_status_time ON xt_order_updates(symbol, status, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_time ON xt_order_updates(update_time);

-- XT WebSocket成交更新表
CREATE TABLE IF NOT EXISTS xt_trade_updates (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    
    -- 交易信息
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(50) NOT NULL,
    trade_id VARCHAR(50) NOT NULL UNIQUE,
    
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
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_xt_trade_symbol_time ON xt_trade_updates(symbol, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_trade_order_trade ON xt_trade_updates(order_id, trade_id);
CREATE INDEX IF NOT EXISTS idx_xt_trade_time ON xt_trade_updates(update_time);

-- XT WebSocket连接记录表
CREATE TABLE IF NOT EXISTS xt_websocket_connections (
    id SERIAL PRIMARY KEY,
    connection_id VARCHAR(100) NOT NULL UNIQUE,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    
    -- 连接统计
    total_messages INTEGER DEFAULT 0,
    account_updates INTEGER DEFAULT 0,
    position_updates INTEGER DEFAULT 0,
    order_updates INTEGER DEFAULT 0,
    trade_updates INTEGER DEFAULT 0,
    
    -- 重连统计
    reconnect_count INTEGER DEFAULT 0,
    last_reconnect_time TIMESTAMP,
    last_error TEXT,
    
    -- 数据同步统计
    data_sync_count INTEGER DEFAULT 0,
    last_sync_time TIMESTAMP,
    
    -- 原始数据
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_xt_ws_active ON xt_websocket_connections(is_active);
CREATE INDEX IF NOT EXISTS idx_xt_ws_start_time ON xt_websocket_connections(start_time);

-- ============================================================
-- XT WebSocket 视图
-- ============================================================

-- XT最新账户余额
CREATE OR REPLACE VIEW xt_latest_account_balances AS
SELECT DISTINCT ON (currency)
    *
FROM xt_account_updates
ORDER BY currency, update_time DESC;

-- XT最新持仓
CREATE OR REPLACE VIEW xt_latest_positions AS
SELECT DISTINCT ON (symbol, side)
    *
FROM xt_position_updates
WHERE quantity > 0
ORDER BY symbol, side, update_time DESC;

-- XT最新订单
CREATE OR REPLACE VIEW xt_latest_orders AS
SELECT DISTINCT ON (order_id)
    *
FROM xt_order_updates
ORDER BY order_id, update_time DESC;

-- XT WebSocket连接统计
CREATE OR REPLACE VIEW xt_websocket_stats AS
SELECT
    COUNT(*) as total_connections,
    COUNT(CASE WHEN is_active = TRUE THEN 1 END) as active_connections,
    SUM(total_messages) as total_messages,
    SUM(account_updates) as total_account_updates,
    SUM(position_updates) as total_position_updates,
    SUM(order_updates) as total_order_updates,
    SUM(trade_updates) as total_trade_updates,
    SUM(reconnect_count) as total_reconnects,
    SUM(data_sync_count) as total_data_syncs,
    MAX(start_time) as last_connection_start,
    MAX(end_time) as last_connection_end
FROM xt_websocket_connections;

-- ============================================================
-- XT WebSocket 表注释
-- ============================================================

COMMENT ON TABLE xt_account_updates IS 'XT WebSocket账户余额更新记录';
COMMENT ON TABLE xt_position_updates IS 'XT WebSocket持仓更新记录';
COMMENT ON TABLE xt_order_updates IS 'XT WebSocket订单更新记录';
COMMENT ON TABLE xt_trade_updates IS 'XT WebSocket成交更新记录';
COMMENT ON TABLE xt_websocket_connections IS 'XT WebSocket连接记录';

-- ============================================================
-- 完成
-- ============================================================

-- 显示所有表
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

