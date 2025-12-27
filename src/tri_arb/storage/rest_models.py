"""Database models for storing REST API data from all exchanges.

SQLAlchemy models for PostgreSQL storage of REST API queries and scheduled queries.
Compatible with existing WebSocket data models.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class RestBalance(Base):
    """REST API余额查询记录.

    存储通过REST API查询的账户余额快照，支持所有交易所。
    """

    __tablename__ = "rest_balances"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)  # binance, okx, gate, xt
    exchange_type = Column(String(10), nullable=False, index=True)  # spot, perp
    query_time = Column(DateTime, nullable=False, index=True)  # 查询时间
    query_type = Column(String(20), nullable=False, index=True)  # manual, scheduled
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（可选）

    # 余额信息
    asset = Column(String(20), nullable=False, index=True)  # 资产类型（如USDT）
    free = Column(Numeric(30, 10), nullable=False)  # 可用余额
    locked = Column(Numeric(30, 10), nullable=False)  # 冻结余额
    total = Column(Numeric(30, 10), nullable=False)  # 总余额

    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "idx_rest_balance_exchange_type_time",
            "exchange",
            "exchange_type",
            "query_time",
        ),
        Index("idx_rest_balance_asset_time", "asset", "query_time"),
        Index("idx_rest_balance_query_type_time", "query_type", "query_time"),
        Index("idx_rest_balance_account_time", "account_id", "query_time"),
    )


class RestPosition(Base):
    """REST API持仓查询记录.

    存储通过REST API查询的持仓快照，支持所有交易所。
    """

    __tablename__ = "rest_positions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)  # binance, okx, gate, xt
    exchange_type = Column(String(10), nullable=False, index=True)  # spot, perp
    query_time = Column(DateTime, nullable=False, index=True)  # 查询时间
    query_type = Column(String(20), nullable=False, index=True)  # manual, scheduled
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（可选）

    # 持仓信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    position_side = Column(String(10), nullable=False)  # LONG/SHORT
    position_amount = Column(Numeric(30, 10), nullable=False)  # 持仓数量
    entry_price = Column(Numeric(30, 10), nullable=True)  # 开仓均价
    mark_price = Column(Numeric(30, 10), nullable=True)  # 标记价格
    unrealized_pnl = Column(Numeric(30, 10), nullable=True)  # 未实现盈亏
    percentage = Column(Numeric(10, 4), nullable=True)  # 盈亏百分比
    notional = Column(Numeric(30, 10), nullable=True)  # 名义价值
    isolated = Column(Boolean, default=False)  # 是否逐仓
    leverage = Column(String(10), nullable=True)  # 杠杆倍数

    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_rest_position_symbol_time", "symbol", "query_time"),
        Index("idx_rest_position_side_time", "position_side", "query_time"),
        Index("idx_rest_position_query_type_time", "query_type", "query_time"),
        Index("idx_rest_position_account_time", "account_id", "query_time"),
    )


class RestOrder(Base):
    """REST API订单查询记录.

    存储通过REST API查询的订单快照，支持所有交易所。
    """

    __tablename__ = "rest_orders"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)  # binance, okx, gate, xt
    exchange_type = Column(String(10), nullable=False, index=True)  # spot, perp
    query_time = Column(DateTime, nullable=False, index=True)  # 查询时间
    query_type = Column(String(20), nullable=False, index=True)  # manual, scheduled
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（可选）

    # 订单信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    order_id = Column(String(50), nullable=False, index=True)  # 订单ID
    client_order_id = Column(String(50), nullable=True)  # 客户订单ID
    side = Column(String(10), nullable=False)  # BUY/SELL
    order_type = Column(String(30), nullable=False)  # 订单类型
    time_in_force = Column(String(10), nullable=True)  # 有效方式
    original_quantity = Column(Numeric(30, 10), nullable=False)  # 原始数量
    original_price = Column(Numeric(30, 10), nullable=True)  # 原始价格
    average_price = Column(Numeric(30, 10), nullable=True)  # 平均价格
    executed_quantity = Column(Numeric(30, 10), nullable=False)  # 已成交数量
    cumulative_quote_quantity = Column(Numeric(30, 10), nullable=True)  # 累计成交金额
    order_status = Column(String(20), nullable=False, index=True)  # 订单状态
    position_side = Column(String(10), nullable=True)  # 持仓方向
    is_reduce_only = Column(Boolean, default=False)  # 是否只减仓

    # 时间信息
    order_time = Column(DateTime, nullable=True)  # 订单时间
    update_time = Column(DateTime, nullable=True)  # 更新时间

    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_rest_order_id_time", "order_id", "query_time"),
        Index(
            "idx_rest_order_symbol_status_time", "symbol", "order_status", "query_time"
        ),
        Index("idx_rest_order_query_type_time", "query_type", "query_time"),
        Index("idx_rest_order_account_time", "account_id", "query_time"),
    )


class ScheduledQuery(Base):
    """定时查询记录.

    存储定时查询的元数据和统计信息。
    """

    __tablename__ = "scheduled_queries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    exchange = Column(String(20), nullable=False, index=True)  # binance, okx, gate, xt
    query_type = Column(String(20), nullable=False)  # balance, position, order
    exchange_type = Column(String(10), nullable=False)  # spot, perp
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（可选）
    start_time = Column(DateTime, nullable=False)  # 开始时间
    end_time = Column(DateTime, nullable=True)  # 结束时间
    interval_minutes = Column(Integer, nullable=False)  # 查询间隔（分钟）

    # 统计信息
    total_queries = Column(Integer, default=0)  # 总查询次数
    successful_queries = Column(Integer, default=0)  # 成功查询次数
    failed_queries = Column(Integer, default=0)  # 失败查询次数
    is_active = Column(Boolean, default=True, index=True)  # 是否活跃

    # 最后状态
    last_query_time = Column(DateTime, nullable=True)  # 最后查询时间
    last_success_time = Column(DateTime, nullable=True)  # 最后成功时间
    last_error = Column(Text, nullable=True)  # 最后错误信息

    # 原始数据
    raw_data = Column(Text, nullable=True)  # 配置信息
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "idx_scheduled_exchange_query_type_active",
            "exchange",
            "query_type",
            "is_active",
        ),
        Index(
            "idx_scheduled_exchange_type_active",
            "exchange",
            "exchange_type",
            "is_active",
        ),
    )
