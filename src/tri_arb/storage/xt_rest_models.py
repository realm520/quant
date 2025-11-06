"""XT交易所REST API数据库模型.

独立的XT交易所表，将现货和合约分开存储。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class XTSpotBalance(Base):
    """XT现货账户余额记录.
    
    存储XT现货账户的余额快照。
    """
    
    __tablename__ = "xt_spot_balances"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    query_time = Column(DateTime, nullable=False, index=True)  # 查询时间
    query_type = Column(String(20), nullable=False, index=True)  # manual, scheduled
    
    # 余额信息
    asset = Column(String(20), nullable=False, index=True)  # 资产类型（如USDT, BTC）
    free = Column(Numeric(30, 10), nullable=False)  # 可用余额
    locked = Column(Numeric(30, 10), nullable=False)  # 冻结余额
    total = Column(Numeric(30, 10), nullable=False)  # 总余额
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON原始数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_spot_balance_asset_time', 'asset', 'query_time'),
        Index('idx_xt_spot_balance_query_type_time', 'query_type', 'query_time'),
    )


class XTPerpBalance(Base):
    """XT合约账户余额记录.
    
    存储XT永续合约账户的余额快照。
    """
    
    __tablename__ = "xt_perp_balances"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    query_time = Column(DateTime, nullable=False, index=True)  # 查询时间
    query_type = Column(String(20), nullable=False, index=True)  # manual, scheduled
    
    # 余额信息
    asset = Column(String(20), nullable=False, index=True)  # 资产类型（如USDT, BTC）
    free = Column(Numeric(30, 10), nullable=False)  # 可用余额
    locked = Column(Numeric(30, 10), nullable=False)  # 冻结余额
    total = Column(Numeric(30, 10), nullable=False)  # 总余额
    
    # 盈亏信息
    unrealized_pnl = Column(Numeric(30, 10), nullable=True)  # 未实现盈亏
    realized_pnl = Column(Numeric(30, 10), nullable=True)  # 已实现盈亏
    equity = Column(Numeric(30, 10), nullable=True)  # 总权益（余额+未实现盈亏）
    margin = Column(Numeric(30, 10), nullable=True)  # 保证金
    margin_ratio = Column(Numeric(10, 4), nullable=True)  # 保证金率
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON原始数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_perp_balance_asset_time', 'asset', 'query_time'),
        Index('idx_xt_perp_balance_query_type_time', 'query_type', 'query_time'),
    )


class XTPerpPosition(Base):
    """XT合约账户仓位记录.
    
    存储XT永续合约账户的持仓快照。
    """
    
    __tablename__ = "xt_perp_positions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    query_time = Column(DateTime, nullable=False, index=True)  # 查询时间
    query_type = Column(String(20), nullable=False, index=True)  # manual, scheduled
    
    # 持仓信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对（如BTC/USDT）
    position_side = Column(String(10), nullable=False)  # LONG/SHORT
    position_amount = Column(Numeric(30, 10), nullable=False)  # 持仓数量
    entry_price = Column(Numeric(30, 10), nullable=True)  # 开仓均价
    mark_price = Column(Numeric(30, 10), nullable=True)  # 标记价格
    unrealized_pnl = Column(Numeric(30, 10), nullable=True)  # 未实现盈亏
    realized_pnl = Column(Numeric(30, 10), nullable=True)  # 已实现盈亏
    percentage = Column(Numeric(10, 4), nullable=True)  # 盈亏百分比
    notional = Column(Numeric(30, 10), nullable=True)  # 名义价值
    isolated = Column(Boolean, default=False)  # 是否逐仓
    leverage = Column(String(10), nullable=True)  # 杠杆倍数
    liquidation_price = Column(Numeric(30, 10), nullable=True)  # 强平价格
    margin = Column(Numeric(30, 10), nullable=True)  # 保证金
    roe = Column(Numeric(10, 4), nullable=True)  # 收益率百分比
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON原始数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_perp_position_symbol_time', 'symbol', 'query_time'),
        Index('idx_xt_perp_position_side_time', 'position_side', 'query_time'),
        Index('idx_xt_perp_position_query_type_time', 'query_type', 'query_time'),
    )

