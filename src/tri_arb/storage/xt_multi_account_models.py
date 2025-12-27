"""XT 多账号数据库模型.

为每个账号动态生成独立的表，表名格式：{base_table_name}_{account_id}
例如：xt_account_updates_account_001
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
    """为指定账号创建表模型类.

    Args:
        account_id: 账号ID（例如 "account_001"）

    Returns:
        dict: 包含所有表模型类的字典
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

    XTAccountUpdate = _create_model_class(
        "XTAccountUpdate",
        class_suffix,
        f"xt_account_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "update_time": Column(DateTime, nullable=False, index=True),
            "currency": Column(String(20), nullable=False, index=True),
            "available": Column(Numeric(30, 10), nullable=False),
            "frozen": Column(Numeric(30, 10), nullable=False),
            "total": Column(Numeric(30, 10), nullable=False),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_xt_account_{table_suffix}_currency_time",
                "currency",
                "update_time",
            ),
            Index(f"idx_xt_account_{table_suffix}_time", "update_time"),
            {"extend_existing": True},
        ),
        "XT WebSocket账户信息更新记录（账号特定表）。",
    )

    XTSpotUpdate = _create_model_class(
        "XTSpotUpdate",
        class_suffix,
        f"xt_spot_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "update_time": Column(DateTime, nullable=False, index=True),
            "currency": Column(String(20), nullable=False, index=True),
            "available": Column(Numeric(30, 10), nullable=False),
            "frozen": Column(Numeric(30, 10), nullable=False),
            "total": Column(Numeric(30, 10), nullable=False),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_xt_spot_{table_suffix}_currency_time", "currency", "update_time"
            ),
            Index(f"idx_xt_spot_{table_suffix}_time", "update_time"),
            {"extend_existing": True},
        ),
        "XT 现货账户余额快照（账号特定表）。",
    )

    XTPositionUpdate = _create_model_class(
        "XTPositionUpdate",
        class_suffix,
        f"xt_position_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "update_time": Column(DateTime, nullable=False, index=True),
            "symbol": Column(String(20), nullable=False, index=True),
            "side": Column(String(10), nullable=False),
            "quantity": Column(Numeric(30, 10), nullable=False),
            "entry_price": Column(Numeric(30, 10), nullable=True),
            "mark_price": Column(Numeric(30, 10), nullable=True),
            "liquidation_price": Column(Numeric(30, 10), nullable=True),
            "unrealized_pnl": Column(Numeric(30, 10), nullable=True),
            "leverage": Column(Integer, nullable=True),
            "margin": Column(Numeric(30, 10), nullable=True),
            "roe": Column(Numeric(10, 4), nullable=True),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_xt_position_{table_suffix}_symbol_time", "symbol", "update_time"
            ),
            Index(f"idx_xt_position_{table_suffix}_side_time", "side", "update_time"),
            Index(f"idx_xt_position_{table_suffix}_time", "update_time"),
            {"extend_existing": True},
        ),
        "XT WebSocket持仓更新记录（账号特定表）。",
    )

    XTOrderUpdate = _create_model_class(
        "XTOrderUpdate",
        class_suffix,
        f"xt_order_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "update_time": Column(DateTime, nullable=False, index=True),
            "symbol": Column(String(20), nullable=False, index=True),
            "order_id": Column(String(50), nullable=False, index=True),
            "client_order_id": Column(String(50), nullable=True, index=True),
            "side": Column(String(10), nullable=False),
            "order_type": Column(String(30), nullable=False),
            "position_side": Column(String(10), nullable=True),
            "quantity": Column(Numeric(30, 10), nullable=False),
            "price": Column(Numeric(30, 10), nullable=True),
            "filled_quantity": Column(Numeric(30, 10), nullable=False),
            "status": Column(String(20), nullable=False, index=True),
            "time_in_force": Column(String(10), nullable=True),
            "create_time": Column(DateTime, nullable=True),
            "update_time_order": Column(DateTime, nullable=True),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(f"idx_xt_order_{table_suffix}_id_time", "order_id", "update_time"),
            Index(
                f"idx_xt_order_{table_suffix}_symbol_status_time",
                "symbol",
                "status",
                "update_time",
            ),
            Index(f"idx_xt_order_{table_suffix}_time", "update_time"),
            UniqueConstraint(
                "order_id", "update_time", name=f"uq_xt_order_{table_suffix}_id_time"
            ),
            {"extend_existing": True},
        ),
        "XT WebSocket订单更新记录（账号特定表）。",
    )

    XTTradeUpdate = _create_model_class(
        "XTTradeUpdate",
        class_suffix,
        f"xt_trade_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "update_time": Column(DateTime, nullable=False, index=True),
            "symbol": Column(String(20), nullable=False, index=True),
            "order_id": Column(String(50), nullable=False, index=True),
            "trade_id": Column(String(50), nullable=False, unique=True, index=True),
            "side": Column(String(10), nullable=False),
            "price": Column(Numeric(30, 10), nullable=False),
            "quantity": Column(Numeric(30, 10), nullable=False),
            "quote_quantity": Column(Numeric(30, 10), nullable=False),
            "commission": Column(Numeric(30, 10), nullable=True),
            "commission_asset": Column(String(20), nullable=True),
            "is_maker": Column(Boolean, default=False),
            "position_side": Column(String(10), nullable=True),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(f"idx_xt_trade_{table_suffix}_symbol_time", "symbol", "update_time"),
            Index(f"idx_xt_trade_{table_suffix}_order_trade", "order_id", "trade_id"),
            Index(f"idx_xt_trade_{table_suffix}_time", "update_time"),
            {"extend_existing": True},
        ),
        "XT WebSocket成交记录（账号特定表）。",
    )

    XTTransfer = _create_model_class(
        "XTTransfer",
        class_suffix,
        f"xt_transfers_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "transfer_time": Column(DateTime, nullable=False, index=True),
            "currency": Column(String(20), nullable=False, index=True),
            "amount": Column(Numeric(30, 10), nullable=False),
            "transfer_type": Column(String(20), nullable=True, index=True),
            "balance_before": Column(Numeric(30, 10), nullable=True),
            "balance_after": Column(Numeric(30, 10), nullable=False),
            "related_order_id": Column(String(50), nullable=True),
            "related_trade_id": Column(String(50), nullable=True),
            "notes": Column(Text, nullable=True),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_xt_transfer_{table_suffix}_currency_time",
                "currency",
                "transfer_time",
            ),
            Index(f"idx_xt_transfer_{table_suffix}_time", "transfer_time"),
            Index(f"idx_xt_transfer_{table_suffix}_type", "transfer_type"),
            {"extend_existing": True},
        ),
        "XT资金划转记录（账号特定表）。",
    )

    XTSpotBalance = _create_model_class(
        "XTSpotBalance",
        class_suffix,
        f"xt_spot_balances_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "query_time": Column(DateTime, nullable=False, index=True),
            "query_type": Column(String(20), nullable=False, index=True),
            "asset": Column(String(20), nullable=False, index=True),
            "free": Column(Numeric(30, 10), nullable=False),
            "locked": Column(Numeric(30, 10), nullable=False),
            "total": Column(Numeric(30, 10), nullable=False),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_xt_spot_balance_{table_suffix}_asset_time", "asset", "query_time"
            ),
            Index(
                f"idx_xt_spot_balance_{table_suffix}_query_type_time",
                "query_type",
                "query_time",
            ),
            {"extend_existing": True},
        ),
        "XT现货账户余额记录（账号特定表）。",
    )

    XTPerpBalance = _create_model_class(
        "XTPerpBalance",
        class_suffix,
        f"xt_perp_balances_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "query_time": Column(DateTime, nullable=False, index=True),
            "query_type": Column(String(20), nullable=False, index=True),
            "asset": Column(String(20), nullable=False, index=True),
            "free": Column(Numeric(30, 10), nullable=False),
            "locked": Column(Numeric(30, 10), nullable=False),
            "total": Column(Numeric(30, 10), nullable=False),
            "unrealized_pnl": Column(Numeric(30, 10), nullable=True),
            "realized_pnl": Column(Numeric(30, 10), nullable=True),
            "equity": Column(Numeric(30, 10), nullable=True),
            "margin": Column(Numeric(30, 10), nullable=True),
            "margin_ratio": Column(Numeric(10, 4), nullable=True),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_xt_perp_balance_{table_suffix}_asset_time", "asset", "query_time"
            ),
            Index(
                f"idx_xt_perp_balance_{table_suffix}_query_type_time",
                "query_type",
                "query_time",
            ),
            {"extend_existing": True},
        ),
        "XT合约账户余额记录（账号特定表）。",
    )

    XTPerpPosition = _create_model_class(
        "XTPerpPosition",
        class_suffix,
        f"xt_perp_positions_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "query_time": Column(DateTime, nullable=False, index=True),
            "query_type": Column(String(20), nullable=False, index=True),
            "symbol": Column(String(20), nullable=False, index=True),
            "position_side": Column(String(10), nullable=False),
            "position_amount": Column(Numeric(30, 10), nullable=False),
            "entry_price": Column(Numeric(30, 10), nullable=True),
            "mark_price": Column(Numeric(30, 10), nullable=True),
            "unrealized_pnl": Column(Numeric(30, 10), nullable=True),
            "realized_pnl": Column(Numeric(30, 10), nullable=True),
            "percentage": Column(Numeric(10, 4), nullable=True),
            "notional": Column(Numeric(30, 10), nullable=True),
            "isolated": Column(Boolean, default=False),
            "leverage": Column(String(10), nullable=True),
            "liquidation_price": Column(Numeric(30, 10), nullable=True),
            "margin": Column(Numeric(30, 10), nullable=True),
            "roe": Column(Numeric(10, 4), nullable=True),
            "maintenance_margin": Column(Numeric(30, 10), nullable=True),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_xt_perp_position_{table_suffix}_symbol_time",
                "symbol",
                "query_time",
            ),
            Index(
                f"idx_xt_perp_position_{table_suffix}_side_time",
                "position_side",
                "query_time",
            ),
            Index(
                f"idx_xt_perp_position_{table_suffix}_query_type_time",
                "query_type",
                "query_time",
            ),
            {"extend_existing": True},
        ),
        "XT合约账户仓位记录（账号特定表）。",
    )

    XTRestPositionUpdate = _create_model_class(
        "XTRestPositionUpdate",
        class_suffix,
        f"xt_rest_position_updates_{table_suffix}",
        {
            "id": Column(BigInteger, primary_key=True, autoincrement=True),
            "query_time": Column(DateTime, nullable=False, index=True),
            "query_type": Column(String(20), nullable=False, index=True),
            "symbol": Column(String(20), nullable=False, index=True),
            "position_side": Column(String(10), nullable=False),
            "position_amount": Column(Numeric(30, 10), nullable=False),
            "entry_price": Column(Numeric(30, 10), nullable=True),
            "mark_price": Column(Numeric(30, 10), nullable=True),
            "liquidation_price": Column(Numeric(30, 10), nullable=True),
            "unrealized_pnl": Column(Numeric(30, 10), nullable=True),
            "realized_pnl": Column(Numeric(30, 10), nullable=True),
            "margin": Column(Numeric(30, 10), nullable=True),
            "leverage": Column(String(10), nullable=True),
            "roe": Column(Numeric(10, 4), nullable=True),
            "maintenance_margin": Column(Numeric(30, 10), nullable=True),
            "raw_data": Column(Text, nullable=True),
            "created_at": Column(DateTime, default=datetime.utcnow, nullable=False),
        },
        (
            Index(
                f"idx_xt_rest_position_{table_suffix}_symbol_time",
                "symbol",
                "query_time",
            ),
            Index(
                f"idx_xt_rest_position_{table_suffix}_side_time",
                "position_side",
                "query_time",
            ),
            Index(
                f"idx_xt_rest_position_{table_suffix}_query_type_time",
                "query_type",
                "query_time",
            ),
            {"extend_existing": True},
        ),
        "XT永续仓位定时更新记录（账号特定表）。",
    )

    models = {
        "XTAccountUpdate": XTAccountUpdate,
        "XTSpotUpdate": XTSpotUpdate,
        "XTPositionUpdate": XTPositionUpdate,
        "XTOrderUpdate": XTOrderUpdate,
        "XTTradeUpdate": XTTradeUpdate,
        "XTTransfer": XTTransfer,
        "XTSpotBalance": XTSpotBalance,
        "XTPerpBalance": XTPerpBalance,
        "XTPerpPosition": XTPerpPosition,
        "XTRestPositionUpdate": XTRestPositionUpdate,
    }

    # 缓存模型
    _account_models_cache[account_id] = models

    return models
