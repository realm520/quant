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
    table_name = f"{exchange}_account_snapshot"
    class_name = f"{exchange.capitalize()}BalanceRest"
    
    # 使用 type() 动态创建类，避免类名冲突警告
    attrs = {
        "__tablename__": table_name,
        "__doc__": f"REST API余额查询记录 - {exchange}.",
        "id": Column(BigInteger, primary_key=True, autoincrement=True),
        "exchange_type": Column(String(10), nullable=False, index=True),
        "query_time": Column(DateTime, nullable=False, index=True),
        "query_type": Column(String(20), nullable=False, index=True),
        "account_id": Column(String(64), nullable=True, index=True),
        "asset": Column(String(20), nullable=False, index=True),
        "free": Column(Numeric(30, 10), nullable=False),
        "locked": Column(Numeric(30, 10), nullable=False),
        "total": Column(Numeric(30, 10), nullable=False),
        "raw_data": Column(Text, nullable=True),
        "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        "__table_args__": (
            Index(f'idx_{exchange}_balance_type_time', 'exchange_type', 'query_time'),
            Index(f'idx_{exchange}_balance_asset_time', 'asset', 'query_time'),
            Index(f'idx_{exchange}_balance_query_type_time', 'query_type', 'query_time'),
            Index(f'idx_{exchange}_balance_account_time', 'account_id', 'query_time'),
        ),
    }
    
    model_class = type(class_name, (Base,), attrs)
    return model_class


def _create_position_model(exchange: str) -> type:
    """创建交易所特定的持仓表模型.
    
    Args:
        exchange: 交易所名称 (binance, xt, okx, gate)
        
    Returns:
        SQLAlchemy 模型类
    """
    table_name = f"{exchange}_position_snapshot"
    class_name = f"{exchange.capitalize()}PositionRest"
    
    attrs = {
        "__tablename__": table_name,
        "__doc__": f"REST API持仓查询记录 - {exchange}.",
        "id": Column(BigInteger, primary_key=True, autoincrement=True),
        "exchange_type": Column(String(10), nullable=False, index=True),
        "query_time": Column(DateTime, nullable=False, index=True),
        "query_type": Column(String(20), nullable=False, index=True),
        "account_id": Column(String(64), nullable=True, index=True),
        "symbol": Column(String(20), nullable=False, index=True),
        "position_side": Column(String(10), nullable=False),
        "position_amount": Column(Numeric(30, 10), nullable=False),
        "entry_price": Column(Numeric(30, 10), nullable=True),
        "mark_price": Column(Numeric(30, 10), nullable=True),
        "unrealized_pnl": Column(Numeric(30, 10), nullable=True),
        "percentage": Column(Numeric(10, 4), nullable=True),
        "notional": Column(Numeric(30, 10), nullable=True),
        "isolated": Column(Boolean, default=False),
        "leverage": Column(String(10), nullable=True),
        "raw_data": Column(Text, nullable=True),
        "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        "__table_args__": (
            Index(f'idx_{exchange}_position_symbol_time', 'symbol', 'query_time'),
            Index(f'idx_{exchange}_position_side_time', 'position_side', 'query_time'),
            Index(f'idx_{exchange}_position_query_type_time', 'query_type', 'query_time'),
            Index(f'idx_{exchange}_position_account_time', 'account_id', 'query_time'),
        ),
    }
    
    model_class = type(class_name, (Base,), attrs)
    return model_class


def _create_order_model(exchange: str) -> type:
    """创建交易所特定的订单表模型.
    
    Args:
        exchange: 交易所名称 (binance, xt, okx, gate)
        
    Returns:
        SQLAlchemy 模型类
    """
    table_name = f"{exchange}_order_snapshot"
    class_name = f"{exchange.capitalize()}OrderRest"
    
    attrs = {
        "__tablename__": table_name,
        "__doc__": f"REST API订单查询记录 - {exchange}.",
        "id": Column(BigInteger, primary_key=True, autoincrement=True),
        "exchange_type": Column(String(10), nullable=False, index=True),
        "query_time": Column(DateTime, nullable=False, index=True),
        "query_type": Column(String(20), nullable=False, index=True),
        "account_id": Column(String(64), nullable=True, index=True),
        "symbol": Column(String(20), nullable=False, index=True),
        "order_id": Column(String(50), nullable=False, index=True),
        "client_order_id": Column(String(50), nullable=True),
        "side": Column(String(10), nullable=False),
        "order_type": Column(String(30), nullable=False),
        "time_in_force": Column(String(10), nullable=True),
        "original_quantity": Column(Numeric(30, 10), nullable=False),
        "original_price": Column(Numeric(30, 10), nullable=True),
        "average_price": Column(Numeric(30, 10), nullable=True),
        "executed_quantity": Column(Numeric(30, 10), nullable=False),
        "cumulative_quote_quantity": Column(Numeric(30, 10), nullable=True),
        "order_status": Column(String(20), nullable=False, index=True),
        "position_side": Column(String(10), nullable=True),
        "is_reduce_only": Column(Boolean, default=False),
        "order_time": Column(DateTime, nullable=True),
        "update_time": Column(DateTime, nullable=True),
        "raw_data": Column(Text, nullable=True),
        "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        "__table_args__": (
            Index(f'idx_{exchange}_order_id_time', 'order_id', 'query_time'),
            Index(f'idx_{exchange}_order_symbol_status_time', 'symbol', 'order_status', 'query_time'),
            Index(f'idx_{exchange}_order_query_type_time', 'query_type', 'query_time'),
            Index(f'idx_{exchange}_order_account_time', 'account_id', 'query_time'),
        ),
    }
    
    model_class = type(class_name, (Base,), attrs)
    return model_class


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

