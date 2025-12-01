"""Binance 多账号数据库模型.

为每个账号动态生成独立的 WebSocket 表，表名格式：{base_table_name}_{account_id}。

与 XT 的 `xt_multi_account_models.py` 设计类似，用于按账号拆分：
- 账户/持仓更新（WebSocket ACCOUNT_UPDATE）
- 订单更新（WebSocket ORDER_TRADE_UPDATE）
- 成交记录（WebSocket 成交）

注意：
- 这里只处理 WebSocket 实时数据表，不影响通用的 REST 表（rest_*）。
- 旧的无后缀表（如 binance_order_updates）仍然保留以兼容历史数据；
  新账号可以切换到带后缀的新表。
"""

from datetime import datetime
from decimal import Decimal

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
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# 缓存已创建的表模型，避免重复定义
_account_models_cache: dict[str, dict] = {}


def _create_model_class(
    base_name: str,
    class_suffix: str,
    table_name: str,
    columns: dict,
    table_args,
    doc: str,
):
    """动态创建带唯一类名的 SQLAlchemy 模型."""
    attrs: dict = {
        "__tablename__": table_name,
        "__doc__": doc,
        "__table_args__": table_args,
    }
    attrs.update(columns)
    class_name = f"{base_name}{class_suffix}"
    return type(class_name, (Base,), attrs)


def create_account_table_models(account_id: str):
    """为指定 Binance 账号创建表模型类.

    Args:
        account_id: 账号ID（例如 "binance_main_001"）

    Returns:
        dict: 包含所有表模型类的字典，键包括：
              - AccountUpdate
              - OrderUpdate
              - TradeUpdate
    """
    # 检查缓存
    if account_id in _account_models_cache:
        return _account_models_cache[account_id]

    # 表名后缀（清理特殊字符，确保表名合法）
    table_suffix = account_id.replace("-", "_").replace(".", "_").lower()
    # 类名后缀（用于确保类名唯一）
    class_suffix = (
        account_id.replace("-", "_").replace(".", "_").title().replace("_", "")
    )

    # 账户/持仓更新（对应原来的 AccountUpdate 表，但按账号拆分）
    BinanceAccountUpdate = _create_model_class(
        "BinanceAccountUpdate",
        class_suffix,
        f"binance_account_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "exchange": Column(String(20), nullable=False, index=True),
            "event_type": Column(String(20), nullable=False),
            "event_time": Column(DateTime, nullable=False, index=True),
            "transaction_time": Column(DateTime, nullable=False),
            # 余额信息
            "asset": Column(String(20), nullable=True, index=True),
            "wallet_balance": Column(Numeric(30, 10), nullable=True),
            "cross_wallet_balance": Column(Numeric(30, 10), nullable=True),
            "balance_change": Column(Numeric(30, 10), nullable=True),
            # 持仓信息
            "symbol": Column(String(20), nullable=True, index=True),
            "position_side": Column(String(10), nullable=True),
            "position_amount": Column(Numeric(30, 10), nullable=True),
            "entry_price": Column(Numeric(30, 10), nullable=True),
            "unrealized_pnl": Column(Numeric(30, 10), nullable=True),
            # 原始数据
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_binance_account_{table_suffix}_event_time",
                "exchange",
                "event_time",
            ),
            Index(
                f"idx_binance_account_{table_suffix}_symbol_time",
                "symbol",
                "event_time",
            ),
            {"extend_existing": True},
        ),
        "Binance 账户/持仓更新记录（WebSocket，多账号表）。",
    )

    # 订单更新（对应原来的 binance_order_updates 表，但按账号拆分）
    BinanceOrderUpdate = _create_model_class(
        "BinanceOrderUpdate",
        class_suffix,
        f"binance_order_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "exchange": Column(String(20), nullable=False, index=True),
            "event_type": Column(String(20), nullable=False),
            "event_time": Column(DateTime, nullable=False, index=True),
            "transaction_time": Column(DateTime, nullable=False),
            # 订单信息
            "symbol": Column(String(20), nullable=False, index=True),
            "client_order_id": Column(String(50), nullable=True, index=True),
            "side": Column(String(10), nullable=False),
            "order_type": Column(String(30), nullable=False),
            "time_in_force": Column(String(10), nullable=True),
            "original_quantity": Column(Numeric(30, 10), nullable=False),
            "original_price": Column(Numeric(30, 10), nullable=True),
            "average_price": Column(Numeric(30, 10), nullable=True),
            # 执行信息
            "order_status": Column(String(20), nullable=False, index=True),
            "order_id": Column(BigInteger, nullable=False, index=True),
            "last_filled_quantity": Column(Numeric(30, 10), nullable=True),
            "cumulative_filled_quantity": Column(Numeric(30, 10), nullable=False),
            "last_filled_price": Column(Numeric(30, 10), nullable=True),
            # 手续费
            "commission_amount": Column(Numeric(30, 10), nullable=True),
            "commission_asset": Column(String(20), nullable=True),
            # 持仓方向
            "position_side": Column(String(10), nullable=True),
            # 是否仅减仓
            "is_reduce_only": Column(Boolean, default=False),
            # 原始数据
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_binance_order_{table_suffix}_order_time",
                "order_id",
                "event_time",
            ),
            Index(
                f"idx_binance_order_{table_suffix}_symbol_status",
                "symbol",
                "order_status",
            ),
            Index(
                f"idx_binance_order_{table_suffix}_exchange_symbol_time",
                "exchange",
                "symbol",
                "event_time",
            ),
            UniqueConstraint(
                "exchange",
                "order_id",
                "event_time",
                name=f"uq_binance_order_{table_suffix}_event",
            ),
            {"extend_existing": True},
        ),
        "Binance 订单更新记录（WebSocket，多账号表）。",
    )

    # 成交记录（对应原来的 binance_trade_updates 表，但按账号拆分）
    BinanceTradeUpdate = _create_model_class(
        "BinanceTradeUpdate",
        class_suffix,
        f"binance_trade_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "exchange": Column(String(20), nullable=False, index=True),
            "event_type": Column(String(20), nullable=False),
            "event_time": Column(DateTime, nullable=False, index=True),
            "transaction_time": Column(DateTime, nullable=False),
            # 交易信息
            "symbol": Column(String(20), nullable=False, index=True),
            "order_id": Column(BigInteger, nullable=False, index=True),
            "trade_id": Column(BigInteger, nullable=False, index=True),
            # 成交详情
            "side": Column(String(10), nullable=False),
            "price": Column(Numeric(30, 10), nullable=False),
            "quantity": Column(Numeric(30, 10), nullable=False),
            "quote_quantity": Column(Numeric(30, 10), nullable=False),
            # 手续费
            "commission": Column(Numeric(30, 10), nullable=True),
            "commission_asset": Column(String(20), nullable=True),
            # 是否为Maker
            "is_maker": Column(Boolean, default=False),
            # 持仓方向
            "position_side": Column(String(10), nullable=True),
            # 原始数据
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_binance_trade_{table_suffix}_symbol_time",
                "symbol",
                "transaction_time",
            ),
            Index(
                f"idx_binance_trade_{table_suffix}_order_trade",
                "order_id",
                "trade_id",
            ),
            UniqueConstraint(
                "exchange",
                "trade_id",
                name=f"uq_binance_trade_{table_suffix}_id",
            ),
            {"extend_existing": True},
        ),
        "Binance 成交记录（WebSocket，多账号表）。",
    )

    models = {
        "AccountUpdate": BinanceAccountUpdate,
        "OrderUpdate": BinanceOrderUpdate,
        "TradeUpdate": BinanceTradeUpdate,
    }

    _account_models_cache[account_id] = models
    return models


