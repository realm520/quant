"""Database models for storing trading data.

SQLAlchemy models for PostgreSQL storage of account updates, orders, and trades.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class AccountUpdate(Base):
    """账户信息更新记录.
    
    存储Binance WebSocket推送的账户余额和持仓变化。
    """
    
    __tablename__ = "account_updates"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)  # binance_perp
    event_type = Column(String(20), nullable=False)  # ACCOUNT_UPDATE
    event_time = Column(DateTime, nullable=False, index=True)  # 事件时间
    transaction_time = Column(DateTime, nullable=False)  # 交易时间
    
    # 余额信息
    asset = Column(String(20), nullable=True, index=True)  # 资产类型（如USDT）
    wallet_balance = Column(Numeric(30, 10), nullable=True)  # 钱包余额
    cross_wallet_balance = Column(Numeric(30, 10), nullable=True)  # 全仓余额
    balance_change = Column(Numeric(30, 10), nullable=True)  # 余额变化
    
    # 持仓信息
    symbol = Column(String(20), nullable=True, index=True)  # 交易对
    position_side = Column(String(10), nullable=True)  # 持仓方向
    position_amount = Column(Numeric(30, 10), nullable=True)  # 持仓数量
    entry_price = Column(Numeric(30, 10), nullable=True)  # 开仓均价
    unrealized_pnl = Column(Numeric(30, 10), nullable=True)  # 未实现盈亏
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_exchange_event_time', 'exchange', 'event_time'),
        Index('idx_symbol_event_time', 'symbol', 'event_time'),
    )


class OrderUpdate(Base):
    """订单更新记录.
    
    存储Binance WebSocket推送的订单状态变化。
    """
    
    __tablename__ = "order_updates"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)  # binance_perp
    event_type = Column(String(20), nullable=False)  # ORDER_TRADE_UPDATE
    event_time = Column(DateTime, nullable=False, index=True)  # 事件时间
    transaction_time = Column(DateTime, nullable=False)  # 交易时间
    
    # 订单信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    client_order_id = Column(String(50), nullable=True, index=True)  # 客户订单ID
    side = Column(String(10), nullable=False)  # BUY/SELL
    order_type = Column(String(30), nullable=False)  # 订单类型
    time_in_force = Column(String(10), nullable=True)  # 有效方式
    original_quantity = Column(Numeric(30, 10), nullable=False)  # 原始数量
    original_price = Column(Numeric(30, 10), nullable=True)  # 原始价格
    average_price = Column(Numeric(30, 10), nullable=True)  # 平均成交价
    
    # 执行信息
    order_status = Column(String(20), nullable=False, index=True)  # 订单状态
    order_id = Column(BigInteger, nullable=False, index=True)  # 订单ID
    last_filled_quantity = Column(Numeric(30, 10), nullable=True)  # 最后成交数量
    cumulative_filled_quantity = Column(Numeric(30, 10), nullable=False)  # 累计成交数量
    last_filled_price = Column(Numeric(30, 10), nullable=True)  # 最后成交价格
    
    # 手续费
    commission_amount = Column(Numeric(30, 10), nullable=True)  # 手续费数量
    commission_asset = Column(String(20), nullable=True)  # 手续费资产
    
    # 持仓方向
    position_side = Column(String(10), nullable=True)  # LONG/SHORT/BOTH
    
    # 是否仅减仓
    is_reduce_only = Column(Boolean, default=False)  # 是否仅减仓
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_order_id_event_time', 'order_id', 'event_time'),
        Index('idx_symbol_status', 'symbol', 'order_status'),
        Index('idx_exchange_symbol_time', 'exchange', 'symbol', 'event_time'),
    )


class TradeUpdate(Base):
    """成交记录.
    
    存储Binance WebSocket推送的实时成交信息。
    """
    
    __tablename__ = "trade_updates"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)  # binance_perp
    event_type = Column(String(20), nullable=False)  # ORDER_TRADE_UPDATE
    event_time = Column(DateTime, nullable=False, index=True)  # 事件时间
    transaction_time = Column(DateTime, nullable=False)  # 交易时间
    
    # 交易信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    order_id = Column(BigInteger, nullable=False, index=True)  # 订单ID
    trade_id = Column(BigInteger, nullable=False, unique=True, index=True)  # 成交ID
    
    # 成交详情
    side = Column(String(10), nullable=False)  # BUY/SELL
    price = Column(Numeric(30, 10), nullable=False)  # 成交价格
    quantity = Column(Numeric(30, 10), nullable=False)  # 成交数量
    quote_quantity = Column(Numeric(30, 10), nullable=False)  # 成交金额
    
    # 手续费
    commission = Column(Numeric(30, 10), nullable=True)  # 手续费
    commission_asset = Column(String(20), nullable=True)  # 手续费资产
    
    # 是否为Maker
    is_maker = Column(Boolean, default=False)  # 是否为挂单方
    
    # 持仓方向
    position_side = Column(String(10), nullable=True)  # LONG/SHORT/BOTH
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_symbol_trade_time', 'symbol', 'transaction_time'),
        Index('idx_order_trade', 'order_id', 'trade_id'),
    )


class ListenKeyRecord(Base):
    """ListenKey记录.
    
    存储Binance用户数据流的ListenKey，用于WebSocket连接。
    """
    
    __tablename__ = "listen_keys"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)
    listen_key = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)  # 过期时间（60分钟后）
    is_active = Column(Boolean, default=True, index=True)
    last_keepalive = Column(DateTime, nullable=True)  # 最后一次keepalive时间

