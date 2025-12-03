"""持仓指标时序数据模型.

用于存储每5分钟计算的持仓和交易指标，供 Grafana 可视化。
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Column, DateTime, Numeric, String, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class PositionMetrics(Base):
    """持仓指标时序数据表.
    
    存储每5分钟计算的持仓和交易指标，包括：
    - 昨收持仓（pre_long_qty, pre_short_qty, pre_long_value, pre_short_value）
    - 今日交易（long_qty, short_qty, long_value, short_value, avg_buy_prz, avg_sell_prz）
    - 已实现 Pnl（matched_qty, realized_pnl）
    - 当日剩余仓位（left_long_qty, left_short_qty, left_long_value, left_short_value, close_prz, unrealized_pnl）
    - Pnl 汇总（daily_pnl, cumulative_pnl）
    """
    
    __tablename__ = "position_metrics"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 时间戳
    timestamp = Column(DateTime, nullable=False, index=True)  # 计算时间戳（UTC）
    
    # 账号和交易所信息
    account_id = Column(String(64), nullable=False, index=True)  # 账号ID
    exchange = Column(String(20), nullable=False, index=True)  # 交易所（binance, xt）
    symbol = Column(String(20), nullable=False, index=True)  # 交易对（如 BTCUSDT）
    
    # 1. 昨收持仓
    pre_long_qty = Column(Numeric(30, 10), nullable=False)  # 昨日多头持仓量
    pre_short_qty = Column(Numeric(30, 10), nullable=False)  # 昨日空头持仓量
    pre_long_value = Column(Numeric(30, 10), nullable=False)  # 昨日多头市值
    pre_short_value = Column(Numeric(30, 10), nullable=False)  # 昨日空头市值
    
    # 2. 今日交易
    long_qty = Column(Numeric(30, 10), nullable=False)  # 多头交易量
    short_qty = Column(Numeric(30, 10), nullable=False)  # 空头交易量
    long_value = Column(Numeric(30, 10), nullable=False)  # 多头市值
    short_value = Column(Numeric(30, 10), nullable=False)  # 空头市值
    avg_buy_prz = Column(Numeric(30, 10), nullable=False)  # 买入平均价格
    avg_sell_prz = Column(Numeric(30, 10), nullable=False)  # 卖出平均价格
    
    # 3. 已实现 Pnl
    matched_qty = Column(Numeric(30, 10), nullable=False)  # 轧差数量
    realized_pnl = Column(Numeric(30, 10), nullable=False)  # 当日已实现盈亏
    
    # 4. 当日剩余仓位
    left_long_qty = Column(Numeric(30, 10), nullable=False)  # 多头剩余持仓
    left_short_qty = Column(Numeric(30, 10), nullable=False)  # 空头剩余持仓
    left_long_value = Column(Numeric(30, 10), nullable=False)  # 多头剩余市值
    left_short_value = Column(Numeric(30, 10), nullable=False)  # 空头剩余市值
    close_prz = Column(Numeric(30, 10), nullable=False)  # 当日最后一笔成交价
    unrealized_pnl = Column(Numeric(30, 10), nullable=False)  # 当日未实现盈亏
    
    # 5. Pnl 汇总
    daily_pnl = Column(Numeric(30, 10), nullable=False)  # 单日 PnL
    cumulative_pnl = Column(Numeric(30, 10), nullable=False)  # 多日 PnL
    
    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_position_metrics_timestamp', 'timestamp'),
        Index('idx_position_metrics_account_exchange', 'account_id', 'exchange'),
        Index('idx_position_metrics_symbol', 'symbol'),
        Index('idx_position_metrics_account_symbol_time', 'account_id', 'symbol', 'timestamp'),
        Index('idx_position_metrics_exchange_symbol_time', 'exchange', 'symbol', 'timestamp'),
    )

