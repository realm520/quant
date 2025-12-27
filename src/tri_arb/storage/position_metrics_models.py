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
    - 开盘持仓（open_left_long_qty, open_left_short_qty, open_left_long_value, open_left_short_value）
    - 当日成交量（daily_buy_volume, daily_sell_volume, daily_buy_value, daily_sell_value）
    - 总持仓（total_long_qty, total_short_qty, total_long_value, total_short_value）
    - 平均价格（avg_buy_prz, avg_sell_prz）
    - 轧差和已实现盈亏（matched_qty, daily_realized_pnl, cumulative_realized_pnl）
    - 收盘持仓（close_left_long_qty, close_left_short_qty, close_left_long_value, close_left_short_value）
    - 收盘价和未实现盈亏（close_prz, unrealized_pnl）
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

    # 1. 开盘持仓（昨收持仓）
    open_left_long_qty = Column(Numeric(30, 10), nullable=False)  # 开盘多头持仓量
    open_left_short_qty = Column(Numeric(30, 10), nullable=False)  # 开盘空头持仓量
    open_left_long_value = Column(Numeric(30, 10), nullable=False)  # 开盘多头市值
    open_left_short_value = Column(Numeric(30, 10), nullable=False)  # 开盘空头市值

    # 2. 当日成交量（当日买入/卖出量）
    daily_sum_buy_qty = Column(Numeric(30, 10), nullable=False)  # 当日买入量
    daily_sum_sell_qty = Column(Numeric(30, 10), nullable=False)  # 当日卖出量
    daily_sum_buy_value = Column(Numeric(30, 10), nullable=False)  # 当日买入市值
    daily_sum_sell_value = Column(Numeric(30, 10), nullable=False)  # 当日卖出市值

    # 3. 总持仓（初始持仓 + 当日成交量）
    long_qty = Column(Numeric(30, 10), nullable=False)  # 总多头持仓量
    short_qty = Column(Numeric(30, 10), nullable=False)  # 总空头持仓量
    long_value = Column(Numeric(30, 10), nullable=False)  # 总多头市值
    short_value = Column(Numeric(30, 10), nullable=False)  # 总空头市值

    # 4. 平均价格
    avg_buy_prz = Column(Numeric(30, 10), nullable=False)  # 买入平均价格
    avg_sell_prz = Column(Numeric(30, 10), nullable=False)  # 卖出平均价格

    # 5. 轧差和已实现盈亏
    matched_qty = Column(Numeric(30, 10), nullable=False)  # 轧差数量
    daily_realized_pnl = Column(Numeric(30, 10), nullable=False)  # 当日已实现盈亏
    cumulative_realized_pnl = Column(
        Numeric(30, 10), nullable=False
    )  # 累积已实现盈亏（从最早成交到当前时刻）

    # 6. 收盘持仓（当日剩余仓位）
    left_long_qty = Column(Numeric(30, 10), nullable=False)  # 收盘多头持仓
    left_short_qty = Column(Numeric(30, 10), nullable=False)  # 收盘空头持仓
    left_long_value = Column(Numeric(30, 10), nullable=False)  # 收盘多头市值
    left_short_value = Column(Numeric(30, 10), nullable=False)  # 收盘空头市值

    # 7. 收盘价和未实现盈亏
    close_prz = Column(Numeric(30, 10), nullable=False)  # 当日最后一笔成交价
    unrealized_pnl = Column(Numeric(30, 10), nullable=False)  # 当日未实现盈亏

    # 8. PnL 汇总
    daily_pnl = Column(Numeric(30, 10), nullable=False)  # 单日 PnL
    cumulative_pnl = Column(Numeric(30, 10), nullable=False)  # 多日 PnL

    # 元数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_position_metrics_timestamp", "timestamp"),
        Index("idx_position_metrics_account_exchange", "account_id", "exchange"),
        Index("idx_position_metrics_symbol", "symbol"),
        Index(
            "idx_position_metrics_account_symbol_time",
            "account_id",
            "symbol",
            "timestamp",
        ),
        Index(
            "idx_position_metrics_exchange_symbol_time",
            "exchange",
            "symbol",
            "timestamp",
        ),
        # 唯一约束：用于 ON CONFLICT DO UPDATE
        Index(
            "idx_position_metrics_unique",
            "timestamp",
            "account_id",
            "exchange",
            "symbol",
            unique=True,
        ),
    )
