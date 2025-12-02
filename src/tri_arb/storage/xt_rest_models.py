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
    注意：与 XTPerpBalance 共享同一个表 xt_account_snapshot，通过 exchange_type 区分。
    """
    
    __tablename__ = "xt_account_snapshot"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange_type = Column(String(10), nullable=False, index=True, default='spot')  # spot/perp
    query_time = Column(DateTime, nullable=False, index=True)  # 查询时间
    query_type = Column(String(20), nullable=False, index=True)  # manual, scheduled
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（用于区分多账号）
    
    # 余额信息
    asset = Column(String(20), nullable=False, index=True)  # 资产类型（如USDT, BTC）
    free = Column(Numeric(30, 10), nullable=False)  # 可用余额
    locked = Column(Numeric(30, 10), nullable=False)  # 冻结余额
    total = Column(Numeric(30, 10), nullable=False)  # 总余额
    
    # 盈亏信息（仅 perp 使用，spot 为 NULL）
    unrealized_pnl = Column(Numeric(30, 10), nullable=True)  # 未实现盈亏
    realized_pnl = Column(Numeric(30, 10), nullable=True)  # 已实现盈亏
    equity = Column(Numeric(30, 10), nullable=True)  # 总权益（余额+未实现盈亏）
    margin = Column(Numeric(30, 10), nullable=True)  # 保证金
    margin_ratio = Column(Numeric(10, 4), nullable=True)  # 保证金率
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON原始数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_account_type_time', 'exchange_type', 'query_time'),
        Index('idx_xt_account_asset_time', 'asset', 'query_time'),
        Index('idx_xt_account_query_type_time', 'query_type', 'query_time'),
        Index('idx_xt_account_account_time', 'account_id', 'query_time'),
    )


class XTPerpBalance(Base):
    """XT合约账户余额记录.
    
    存储XT永续合约账户的余额快照。
    注意：与 XTSpotBalance 共享同一个表 xt_account_snapshot，通过 exchange_type 区分。
    使用 XTSpotBalance 的表定义以避免重复定义错误。
    """
    
    __table__ = XTSpotBalance.__table__


class XTPerpPosition(Base):
    """XT合约账户仓位记录.
    
    存储XT永续合约账户的持仓快照。
    """
    
    __tablename__ = "xt_position_snapshot"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    query_time = Column(DateTime, nullable=False, index=True)  # 查询时间
    query_type = Column(String(20), nullable=False, index=True)  # manual, scheduled
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（用于区分多账号）
    
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
    maintenance_margin = Column(Numeric(30, 10), nullable=True)  # 维持保证金
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON原始数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_position_symbol_time', 'symbol', 'query_time'),
        Index('idx_xt_position_side_time', 'position_side', 'query_time'),
        Index('idx_xt_position_query_type_time', 'query_type', 'query_time'),
        Index('idx_xt_position_account_time', 'account_id', 'query_time'),
    )


class XTRestPositionUpdate(Base):
    """XT永续仓位定时更新记录.
    
    注意：与 XTPerpPosition 共享同一个表 xt_position_snapshot。
    使用 XTPerpPosition 的表定义以避免重复定义错误。
    """

    __table__ = XTPerpPosition.__table__
