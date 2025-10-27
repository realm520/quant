"""Database models for storing XT WebSocket data.

SQLAlchemy models for PostgreSQL storage of XT WebSocket account updates, orders, and trades.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class XTAccountUpdate(Base):
    """XT WebSocket账户信息更新记录.
    
    存储XT WebSocket推送的账户余额变化。
    """
    
    __tablename__ = "xt_account_updates"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    
    # 余额信息
    currency = Column(String(20), nullable=False, index=True)  # 币种
    available = Column(Numeric(30, 10), nullable=False)  # 可用余额
    frozen = Column(Numeric(30, 10), nullable=False)  # 冻结余额
    total = Column(Numeric(30, 10), nullable=False)  # 总余额
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_account_currency_time', 'currency', 'update_time'),
        Index('idx_xt_account_time', 'update_time'),
    )


class XTPositionUpdate(Base):
    """XT WebSocket持仓更新记录.
    
    存储XT WebSocket推送的持仓变化。
    """
    
    __tablename__ = "xt_position_updates"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    
    # 持仓信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    side = Column(String(10), nullable=False)  # LONG/SHORT
    quantity = Column(Numeric(30, 10), nullable=False)  # 持仓数量
    entry_price = Column(Numeric(30, 10), nullable=True)  # 开仓均价
    mark_price = Column(Numeric(30, 10), nullable=True)  # 标记价格
    liquidation_price = Column(Numeric(30, 10), nullable=True)  # 强平价格
    unrealized_pnl = Column(Numeric(30, 10), nullable=True)  # 未实现盈亏
    leverage = Column(Integer, nullable=True)  # 杠杆倍数
    margin = Column(Numeric(30, 10), nullable=True)  # 保证金
    roe = Column(Numeric(10, 4), nullable=True)  # 收益率
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_position_symbol_time', 'symbol', 'update_time'),
        Index('idx_xt_position_side_time', 'side', 'update_time'),
        Index('idx_xt_position_time', 'update_time'),
    )


class XTOrderUpdate(Base):
    """XT WebSocket订单更新记录.
    
    存储XT WebSocket推送的订单状态变化。
    """
    
    __tablename__ = "xt_order_updates"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    
    # 订单信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    order_id = Column(String(50), nullable=False, index=True)  # 订单ID
    client_order_id = Column(String(50), nullable=True, index=True)  # 客户订单ID
    side = Column(String(10), nullable=False)  # BUY/SELL
    order_type = Column(String(30), nullable=False)  # 订单类型
    position_side = Column(String(10), nullable=True)  # 持仓方向
    quantity = Column(Numeric(30, 10), nullable=False)  # 订单数量
    price = Column(Numeric(30, 10), nullable=True)  # 订单价格
    filled_quantity = Column(Numeric(30, 10), nullable=False)  # 已成交数量
    status = Column(String(20), nullable=False, index=True)  # 订单状态
    time_in_force = Column(String(10), nullable=True)  # 有效方式
    
    # 时间信息
    create_time = Column(DateTime, nullable=True)  # 创建时间
    update_time_order = Column(DateTime, nullable=True)  # 订单更新时间
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_order_id_time', 'order_id', 'update_time'),
        Index('idx_xt_order_symbol_status_time', 'symbol', 'status', 'update_time'),
        Index('idx_xt_order_time', 'update_time'),
    )


class XTTradeUpdate(Base):
    """XT WebSocket成交记录.
    
    存储XT WebSocket推送的实时成交信息。
    """
    
    __tablename__ = "xt_trade_updates"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    
    # 交易信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    order_id = Column(String(50), nullable=False, index=True)  # 订单ID
    trade_id = Column(String(50), nullable=False, unique=True, index=True)  # 成交ID
    
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
    position_side = Column(String(10), nullable=True)  # LONG/SHORT
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_trade_symbol_time', 'symbol', 'update_time'),
        Index('idx_xt_trade_order_trade', 'order_id', 'trade_id'),
        Index('idx_xt_trade_time', 'update_time'),
    )


class XTWebSocketConnection(Base):
    """XT WebSocket连接记录.
    
    存储XT WebSocket连接状态和重连信息。
    """
    
    __tablename__ = "xt_websocket_connections"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(String(100), nullable=False, unique=True)  # 连接ID
    start_time = Column(DateTime, nullable=False)  # 开始时间
    end_time = Column(DateTime, nullable=True)  # 结束时间
    is_active = Column(Boolean, default=True, index=True)  # 是否活跃
    
    # 连接统计
    total_messages = Column(Integer, default=0)  # 总消息数
    account_updates = Column(Integer, default=0)  # 账户更新数
    position_updates = Column(Integer, default=0)  # 持仓更新数
    order_updates = Column(Integer, default=0)  # 订单更新数
    trade_updates = Column(Integer, default=0)  # 成交更新数
    
    # 重连统计
    reconnect_count = Column(Integer, default=0)  # 重连次数
    last_reconnect_time = Column(DateTime, nullable=True)  # 最后重连时间
    last_error = Column(Text, nullable=True)  # 最后错误信息
    
    # 数据同步统计
    data_sync_count = Column(Integer, default=0)  # 数据同步次数
    last_sync_time = Column(DateTime, nullable=True)  # 最后同步时间
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 配置信息
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_ws_active', 'is_active'),
        Index('idx_xt_ws_start_time', 'start_time'),
    )
