"""Database models for storing XT WebSocket data.

SQLAlchemy models for PostgreSQL storage of XT WebSocket account updates, orders, and trades.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, Index, UniqueConstraint, Float
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class XTAccountUpdate(Base):
    """XT WebSocket账户信息更新记录.
    
    存储XT WebSocket推送的账户余额变化。
    """
    
    __tablename__ = "xt_account_update"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（用于区分多账号）
    
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
        Index('idx_xt_account_account_time', 'account_id', 'update_time'),
    )


class XTSpotUpdate(Base):
    """XT 现货账户余额快照.
    
    在处理合约账户余额变化时，记录对应时间点的现货账户余额。
    """
    
    __tablename__ = "xt_spot_update"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 记录时间
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（用于区分多账号）
    
    currency = Column(String(20), nullable=False, index=True)  # 币种
    available = Column(Numeric(30, 10), nullable=False)  # 可用余额
    frozen = Column(Numeric(30, 10), nullable=False)  # 冻结余额
    total = Column(Numeric(30, 10), nullable=False)  # 总余额
    
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_spot_currency_time', 'currency', 'update_time'),
        Index('idx_xt_spot_time', 'update_time'),
        Index('idx_xt_spot_account_time', 'account_id', 'update_time'),
    )


class XTPositionUpdate(Base):
    """XT WebSocket持仓更新记录.
    
    存储XT WebSocket推送的持仓变化。
    """
    
    __tablename__ = "xt_position_update"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（用于区分多账号）
    
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
        Index('idx_xt_position_account_time', 'account_id', 'update_time'),
    )


class XTOrderUpdate(Base):
    """XT WebSocket订单更新记录.
    
    存储XT WebSocket推送的订单状态变化。
    """
    
    __tablename__ = "xt_order_update"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（用于区分多账号）
    
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
        Index('idx_xt_order_account_time', 'account_id', 'update_time'),
        # 唯一约束：防止重复订单记录（对账服务依赖此约束）
        UniqueConstraint('order_id', 'update_time', 'account_id', name='uq_xt_order_id_time_account'),
    )


class XTTradeUpdate(Base):
    """XT WebSocket成交记录.
    
    存储XT WebSocket推送的实时成交信息。
    """
    
    __tablename__ = "xt_trade_update"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    update_time = Column(DateTime, nullable=False, index=True)  # 更新时间
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（用于区分多账号）
    
    # 交易信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    order_id = Column(String(50), nullable=False, index=True)  # 订单ID
    trade_id = Column(String(50), nullable=False, index=True)  # 成交ID
    
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
        Index('idx_xt_trade_account_time', 'account_id', 'update_time'),
        # 唯一约束：防止重复成交记录（需要包含 account_id）
        UniqueConstraint('trade_id', 'account_id', name='uq_xt_trade_id_account'),
    )


class XTTransfer(Base):
    """XT资金划转记录.
    
    通过分析账户余额变化识别资金划转（充值、提现、账户间划转等）。
    """
    
    __tablename__ = "xt_transfer_update"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    transfer_time = Column(DateTime, nullable=False, index=True)  # 划转时间
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID（用于区分多账号）
    
    # 划转信息
    currency = Column(String(20), nullable=False, index=True)  # 币种
    amount = Column(Numeric(30, 10), nullable=False)  # 划转金额（正数=转入，负数=转出）
    transfer_type = Column(String(20), nullable=True, index=True)  # 划转类型：DEPOSIT(充值), WITHDRAW(提现), TRANSFER(账户间划转), UNKNOWN(未知)
    
    # 余额变化
    balance_before = Column(Numeric(30, 10), nullable=True)  # 划转前余额
    balance_after = Column(Numeric(30, 10), nullable=False)  # 划转后余额
    
    # 关联信息
    related_order_id = Column(String(50), nullable=True)  # 关联订单ID（如果有）
    related_trade_id = Column(String(50), nullable=True)  # 关联成交ID（如果有）
    
    # 备注
    notes = Column(Text, nullable=True)  # 备注信息
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_transfer_currency_time', 'currency', 'transfer_time'),
        Index('idx_xt_transfer_time', 'transfer_time'),
        Index('idx_xt_transfer_type', 'transfer_type'),
        Index('idx_xt_transfer_account_time', 'account_id', 'transfer_time'),
    )


class XTOrderHistory(Base):
    """XT 历史订单记录（通过 REST API 定时获取）.
    
    存储通过 REST API 定时获取的历史订单，用于补充 WebSocket 可能遗漏的订单。
    与 XTOrderUpdate 的区别：
    - XTOrderUpdate: WebSocket 实时推送的订单更新
    - XTOrderHistory: REST API 定时获取的历史订单快照
    """
    
    __tablename__ = "xt_order_history"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    order_id = Column(String(50), nullable=False, index=True)  # 订单ID
    account_id = Column(String(64), nullable=True, index=True)  # 账号ID
    
    # 订单信息
    symbol = Column(String(20), nullable=False, index=True)  # 交易对
    client_order_id = Column(String(50), nullable=True)  # 客户订单ID
    side = Column(String(10), nullable=False)  # BUY/SELL
    order_type = Column(String(30), nullable=False)  # 订单类型
    position_side = Column(String(10), nullable=True)  # 持仓方向
    
    # 数量信息
    quantity = Column(Numeric(30, 10), nullable=False)  # 订单数量
    price = Column(Numeric(30, 10), nullable=True)  # 订单价格
    filled_quantity = Column(Numeric(30, 10), nullable=False)  # 已成交数量
    avg_price = Column(Numeric(30, 10), nullable=True)  # 成交均价
    
    # 状态信息
    status = Column(String(20), nullable=False, index=True)  # 订单状态
    time_in_force = Column(String(10), nullable=True)  # 有效方式
    
    # 时间信息
    created_time = Column(DateTime, nullable=False, index=True)  # 创建时间（来自API的createdTime）
    updated_time = Column(DateTime, nullable=True)  # 更新时间（来自API的updatedTime）
    sync_time = Column(DateTime, nullable=False, index=True)  # 同步时间（REST API获取的时间）
    
    # 其他信息
    margin_frozen = Column(Numeric(30, 10), nullable=True)  # 占用保证金
    close_position = Column(Boolean, nullable=True)  # 是否全部平仓
    close_profit = Column(Numeric(30, 10), nullable=True)  # 平仓盈亏
    force_close = Column(Boolean, nullable=True)  # 是否为强平订单
    
    # 原始数据
    raw_data = Column(Text, nullable=True)  # 完整JSON数据
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index('idx_xt_order_history_id_time', 'order_id', 'created_time'),
        Index('idx_xt_order_history_symbol_status', 'symbol', 'status'),
        Index('idx_xt_order_history_sync_time', 'sync_time'),
        Index('idx_xt_order_history_account_time', 'account_id', 'sync_time'),
        # 唯一约束：同一个订单在同一时间只能有一条记录
        UniqueConstraint('order_id', 'created_time', 'account_id', name='uq_xt_order_history_id_time_account'),
    )


class XTWebSocketConnection(Base):
    """XT WebSocket连接记录.
    
    存储XT WebSocket连接状态和重连信息。
    """
    
    __tablename__ = "xt_connection"
    
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
