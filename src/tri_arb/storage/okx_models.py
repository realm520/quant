"""OKX专用数据库模型.

OKX的数据结构与Binance不同，使用独立的表结构。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class OKXAccountBalance(Base):
    """OKX账户余额记录.
    
    存储OKX WebSocket推送的账户余额数据。
    """
    
    __tablename__ = "okx_account_balances"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    
    # OKX账户字段
    total_eq = Column(Numeric(30, 10), nullable=True)  # 账户总权益(USD)
    iso_eq = Column(Numeric(30, 10), nullable=True)  # 逐仓账户权益
    adj_eq = Column(Numeric(30, 10), nullable=True)  # 调整后的账户权益
    notional_usd = Column(Numeric(30, 10), nullable=True)  # 持仓折合USD
    
    # 币种详情
    currency = Column(String(20), nullable=False, index=True)  # 币种
    available_bal = Column(Numeric(30, 10), nullable=True)  # 可用余额
    cash_bal = Column(Numeric(30, 10), nullable=True)  # 现金余额
    frozen_bal = Column(Numeric(30, 10), nullable=True)  # 冻结余额
    equity = Column(Numeric(30, 10), nullable=True)  # 币种权益
    upl = Column(Numeric(30, 10), nullable=True)  # 未实现盈亏
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_okx_balance_currency_time', 'currency', 'update_time'),
    )


class OKXPosition(Base):
    """OKX持仓记录.
    
    存储OKX WebSocket推送的持仓数据。
    """
    
    __tablename__ = "okx_positions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    
    # 产品信息
    inst_id = Column(String(50), nullable=False, index=True)  # 产品ID (如BTC-USDT-SWAP)
    inst_type = Column(String(20), nullable=True)  # 产品类型 (SWAP/FUTURES/SPOT)
    
    # 持仓信息
    pos_side = Column(String(10), nullable=True)  # 持仓方向 (long/short/net)
    pos = Column(Numeric(30, 10), nullable=True)  # 持仓数量
    pos_ccy = Column(String(20), nullable=True)  # 持仓币种
    
    # 价格信息
    avg_px = Column(Numeric(30, 10), nullable=True)  # 开仓均价
    mark_px = Column(Numeric(30, 10), nullable=True)  # 标记价格
    liq_px = Column(Numeric(30, 10), nullable=True)  # 预估强平价
    
    # 盈亏信息
    upl = Column(Numeric(30, 10), nullable=True)  # 未实现盈亏
    upl_ratio = Column(Numeric(20, 10), nullable=True)  # 未实现盈亏比例
    
    # 保证金信息
    margin = Column(Numeric(30, 10), nullable=True)  # 保证金
    imr = Column(Numeric(30, 10), nullable=True)  # 初始保证金
    mmr = Column(Numeric(30, 10), nullable=True)  # 维持保证金
    
    # 杠杆
    lever = Column(Numeric(10, 2), nullable=True)  # 杠杆倍数
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_okx_position_inst_time', 'inst_id', 'update_time'),
        Index('idx_okx_position_side', 'pos_side'),
    )


class OKXOrder(Base):
    """OKX订单记录.
    
    存储OKX WebSocket推送的订单数据。
    """
    
    __tablename__ = "okx_orders"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 产品信息
    inst_id = Column(String(50), nullable=False, index=True)  # 产品ID
    inst_type = Column(String(20), nullable=True)  # 产品类型
    
    # 订单ID
    ord_id = Column(String(50), nullable=False, index=True)  # 订单ID
    cl_ord_id = Column(String(50), nullable=True, index=True)  # 客户订单ID
    
    # 订单信息
    ord_type = Column(String(20), nullable=False)  # 订单类型 (limit/market/post_only)
    side = Column(String(10), nullable=False)  # 订单方向 (buy/sell)
    pos_side = Column(String(10), nullable=True)  # 持仓方向 (long/short/net)
    
    # 数量和价格
    sz = Column(Numeric(30, 10), nullable=False)  # 委托数量
    px = Column(Numeric(30, 10), nullable=True)  # 委托价格
    avg_px = Column(Numeric(30, 10), nullable=True)  # 成交均价
    
    # 成交信息
    acc_fill_sz = Column(Numeric(30, 10), nullable=True)  # 累计成交数量
    fill_sz = Column(Numeric(30, 10), nullable=True)  # 最新成交数量
    fill_px = Column(Numeric(30, 10), nullable=True)  # 最新成交价格
    
    # 订单状态
    state = Column(String(20), nullable=False, index=True)  # 订单状态 (live/partially_filled/filled/canceled)
    
    # 手续费
    fee = Column(Numeric(30, 10), nullable=True)  # 手续费
    fee_ccy = Column(String(20), nullable=True)  # 手续费币种
    rebate = Column(Numeric(30, 10), nullable=True)  # 返佣
    rebate_ccy = Column(String(20), nullable=True)  # 返佣币种
    
    # 时间
    c_time = Column(DateTime, nullable=True)  # 创建时间
    u_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    fill_time = Column(DateTime, nullable=True)  # 最新成交时间
    
    # 其他
    reduce_only = Column(Boolean, default=False)  # 是否只减仓
    td_mode = Column(String(20), nullable=True)  # 交易模式 (isolated/cross)
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_okx_order_inst_state', 'inst_id', 'state'),
        Index('idx_okx_order_time', 'u_time'),
        UniqueConstraint('ord_id', 'u_time', name='uq_okx_order_id_time'),  # 防止重复订单更新
    )


class OKXTrade(Base):
    """OKX成交记录.
    
    从订单更新中提取的成交信息。
    """
    
    __tablename__ = "okx_trades"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 产品信息
    inst_id = Column(String(50), nullable=False, index=True)  # 产品ID
    
    # 订单和成交ID
    ord_id = Column(String(50), nullable=False, index=True)  # 订单ID
    trade_id = Column(String(50), nullable=True, index=True)  # 成交ID
    
    # 成交信息
    side = Column(String(10), nullable=False)  # 方向
    fill_px = Column(Numeric(30, 10), nullable=False)  # 成交价格
    fill_sz = Column(Numeric(30, 10), nullable=False)  # 成交数量
    
    # 手续费
    fee = Column(Numeric(30, 10), nullable=True)  # 手续费
    fee_ccy = Column(String(20), nullable=True)  # 手续费币种
    
    # 时间
    fill_time = Column(DateTime, nullable=False, index=True)  # 成交时间
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_okx_trade_inst_time', 'inst_id', 'fill_time'),
        UniqueConstraint('trade_id', name='uq_okx_trade_id'),  # 防止重复成交记录
    )

