"""Gate.io专用数据库模型.

Gate.io的数据结构，使用独立的表结构。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class GateAccountBalance(Base):
    """Gate.io账户余额记录."""
    
    __tablename__ = "gate_account_balances"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)
    
    # 账户信息
    user_id = Column(BigInteger, nullable=True)
    currency = Column(String(20), nullable=False, index=True)
    total = Column(Numeric(30, 10), nullable=True)
    available = Column(Numeric(30, 10), nullable=True)
    unrealised_pnl = Column(Numeric(30, 10), nullable=True)
    
    # 元数据
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_gate_balance_currency_time', 'currency', 'update_time'),
    )


class GatePosition(Base):
    """Gate.io持仓记录."""
    
    __tablename__ = "gate_positions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)
    
    # 合约信息
    contract = Column(String(50), nullable=False, index=True)
    
    # 持仓信息
    size = Column(Numeric(30, 10), nullable=True)
    leverage = Column(Numeric(10, 2), nullable=True)
    margin = Column(Numeric(30, 10), nullable=True)
    entry_price = Column(Numeric(30, 10), nullable=True)
    mark_price = Column(Numeric(30, 10), nullable=True)
    liq_price = Column(Numeric(30, 10), nullable=True)
    
    # 盈亏
    unrealised_pnl = Column(Numeric(30, 10), nullable=True)
    realised_pnl = Column(Numeric(30, 10), nullable=True)
    
    # 模式
    mode = Column(String(20), nullable=True)  # single/dual
    
    # 元数据
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_gate_position_contract_time', 'contract', 'update_time'),
    )


class GateOrder(Base):
    """Gate.io订单记录."""
    
    __tablename__ = "gate_orders"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 订单ID
    order_id = Column(String(50), nullable=False, index=True, unique=True)
    
    # 合约信息
    contract = Column(String(50), nullable=False, index=True)
    
    # 订单信息
    size = Column(Numeric(30, 10), nullable=False)  # 正数=买，负数=卖
    price = Column(Numeric(30, 10), nullable=True)
    left = Column(Numeric(30, 10), nullable=True)  # 未成交数量
    filled_total = Column(Numeric(30, 10), nullable=True)  # 成交金额
    
    # 订单状态
    status = Column(String(20), nullable=False, index=True)
    
    # 时间
    create_time = Column(DateTime, nullable=True)
    finish_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=False, index=True)
    
    # 其他
    reduce_only = Column(Boolean, default=False)
    tif = Column(String(20), nullable=True)  # gtc/ioc/poc
    text = Column(String(100), nullable=True)  # 用户备注
    
    # 元数据
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_gate_order_contract_status', 'contract', 'status'),
        Index('idx_gate_order_time', 'update_time'),
        # 唯一约束：防止重复订单记录（对账服务依赖此约束）
        # Gate 使用 order_id + update_time 作为唯一键
        UniqueConstraint('order_id', 'update_time', name='uq_gate_order_id_time'),
    )


class GateTrade(Base):
    """Gate.io成交记录."""
    
    __tablename__ = "gate_trades"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 交易ID
    trade_id = Column(String(50), nullable=False, unique=True, index=True)
    order_id = Column(String(50), nullable=False, index=True)
    
    # 合约信息
    contract = Column(String(50), nullable=False, index=True)
    
    # 成交信息
    size = Column(Numeric(30, 10), nullable=False)
    price = Column(Numeric(30, 10), nullable=False)
    role = Column(String(10), nullable=True)  # taker/maker
    
    # 时间
    create_time = Column(DateTime, nullable=False, index=True)
    
    # 元数据
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_gate_trade_contract_time', 'contract', 'create_time'),
    )

