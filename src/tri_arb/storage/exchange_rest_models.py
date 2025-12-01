"""Database models for exchange-specific REST API data.

按交易所区分的 REST API 数据表模型：
- binance_balance_rest, binance_position_rest, binance_order_rest
- xt_balance_rest, xt_position_rest, xt_order_rest
- okx_balance_rest, okx_position_rest, okx_order_rest
- gate_balance_rest, gate_position_rest, gate_order_rest
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, Numeric, String, Text, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


def _create_balance_model(exchange: str) -> type:
    """创建交易所特定的余额表模型.
    
    Args:
        exchange: 交易所名称 (binance, xt, okx, gate)
        
    Returns:
        SQLAlchemy 模型类
    """
    table_name = f"{exchange}_balance_rest"
    
    class ExchangeBalanceRest(Base):
        """REST API余额查询记录 - {exchange}."""
        
        __tablename__ = table_name
        
        id = Column(BigInteger, primary_key=True, autoincrement=True)
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
            Index(f'idx_{exchange}_balance_type_time', 'exchange_type', 'query_time'),
            Index(f'idx_{exchange}_balance_asset_time', 'asset', 'query_time'),
            Index(f'idx_{exchange}_balance_query_type_time', 'query_type', 'query_time'),
            Index(f'idx_{exchange}_balance_account_time', 'account_id', 'query_time'),
        )
    
    ExchangeBalanceRest.__name__ = f"{exchange.capitalize()}BalanceRest"
    return ExchangeBalanceRest


def _create_position_model(exchange: str) -> type:
    """创建交易所特定的持仓表模型.
    
    Args:
        exchange: 交易所名称 (binance, xt, okx, gate)
        
    Returns:
        SQLAlchemy 模型类
    """
    table_name = f"{exchange}_position_rest"
    
    class ExchangePositionRest(Base):
        """REST API持仓查询记录 - {exchange}."""
        
        __tablename__ = table_name
        
        id = Column(BigInteger, primary_key=True, autoincrement=True)
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
            Index(f'idx_{exchange}_position_symbol_time', 'symbol', 'query_time'),
            Index(f'idx_{exchange}_position_side_time', 'position_side', 'query_time'),
            Index(f'idx_{exchange}_position_query_type_time', 'query_type', 'query_time'),
            Index(f'idx_{exchange}_position_account_time', 'account_id', 'query_time'),
        )
    
    ExchangePositionRest.__name__ = f"{exchange.capitalize()}PositionRest"
    return ExchangePositionRest


def _create_order_model(exchange: str) -> type:
    """创建交易所特定的订单表模型.
    
    Args:
        exchange: 交易所名称 (binance, xt, okx, gate)
        
    Returns:
        SQLAlchemy 模型类
    """
    table_name = f"{exchange}_order_rest"
    
    class ExchangeOrderRest(Base):
        """REST API订单查询记录 - {exchange}."""
        
        __tablename__ = table_name
        
        id = Column(BigInteger, primary_key=True, autoincrement=True)
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
            Index(f'idx_{exchange}_order_id_time', 'order_id', 'query_time'),
            Index(f'idx_{exchange}_order_symbol_status_time', 'symbol', 'order_status', 'query_time'),
            Index(f'idx_{exchange}_order_query_type_time', 'query_type', 'query_time'),
            Index(f'idx_{exchange}_order_account_time', 'account_id', 'query_time'),
        )
    
    ExchangeOrderRest.__name__ = f"{exchange.capitalize()}OrderRest"
    return ExchangeOrderRest


# 创建各交易所的表模型
BinanceBalanceRest = _create_balance_model("binance")
BinancePositionRest = _create_position_model("binance")
BinanceOrderRest = _create_order_model("binance")

XTBalanceRest = _create_balance_model("xt")
XTPositionRest = _create_position_model("xt")
XTOrderRest = _create_order_model("xt")

OKXBalanceRest = _create_balance_model("okx")
OKXPositionRest = _create_position_model("okx")
OKXOrderRest = _create_order_model("okx")

GateBalanceRest = _create_balance_model("gate")
GatePositionRest = _create_position_model("gate")
GateOrderRest = _create_order_model("gate")


# 交易所到模型的映射
EXCHANGE_BALANCE_MODELS = {
    "binance": BinanceBalanceRest,
    "xt": XTBalanceRest,
    "okx": OKXBalanceRest,
    "gate": GateBalanceRest,
}

EXCHANGE_POSITION_MODELS = {
    "binance": BinancePositionRest,
    "xt": XTPositionRest,
    "okx": OKXPositionRest,
    "gate": GatePositionRest,
}

EXCHANGE_ORDER_MODELS = {
    "binance": BinanceOrderRest,
    "xt": XTOrderRest,
    "okx": OKXOrderRest,
    "gate": GateOrderRest,
}


def get_balance_model(exchange: str):
    """获取交易所的余额表模型.
    
    Args:
        exchange: 交易所名称
        
    Returns:
        SQLAlchemy 模型类
        
    Raises:
        ValueError: 如果交易所不支持
    """
    model = EXCHANGE_BALANCE_MODELS.get(exchange.lower())
    if not model:
        raise ValueError(f"Unsupported exchange: {exchange}. Supported: {list(EXCHANGE_BALANCE_MODELS.keys())}")
    return model


def get_position_model(exchange: str):
    """获取交易所的持仓表模型.
    
    Args:
        exchange: 交易所名称
        
    Returns:
        SQLAlchemy 模型类
        
    Raises:
        ValueError: 如果交易所不支持
    """
    model = EXCHANGE_POSITION_MODELS.get(exchange.lower())
    if not model:
        raise ValueError(f"Unsupported exchange: {exchange}. Supported: {list(EXCHANGE_POSITION_MODELS.keys())}")
    return model


def get_order_model(exchange: str):
    """获取交易所的订单表模型.
    
    Args:
        exchange: 交易所名称
        
    Returns:
        SQLAlchemy 模型类
        
    Raises:
        ValueError: 如果交易所不支持
    """
    model = EXCHANGE_ORDER_MODELS.get(exchange.lower())
    if not model:
        raise ValueError(f"Unsupported exchange: {exchange}. Supported: {list(EXCHANGE_ORDER_MODELS.keys())}")
    return model

