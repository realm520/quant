"""XT交易所REST API数据服务.

专门用于保存XT交易所的账户数据到独立的表中。
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from tri_arb.config.logging import get_logger
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_rest_models import (
    XTSpotBalance,
    XTPerpBalance,
    XTPerpPosition,
    XTRestPositionUpdate,
)

logger = get_logger(__name__)


class XTRestDataService:
    """XT交易所REST API数据服务.
    
    专门用于保存XT交易所的账户数据到统一的表中：
    - xt_account_snapshot: XT账户余额快照（现货和合约，通过 exchange_type 区分）
    - xt_position_snapshot: XT合约账户仓位快照
    
    所有表都使用 account_id 字段区分不同账号的数据。
    """
    
    def __init__(self, db_manager: DatabaseManager, account_id: Optional[str] = None):
        """初始化XT REST数据服务.
        
        Args:
            db_manager: 数据库管理器
            account_id: 账号ID（可选），用于区分多账号数据
        """
        self.db_manager = db_manager
        self.account_id = account_id
    
    async def save_spot_balance(
        self,
        balances_data: Dict[str, Any],
        query_type: str = "scheduled"
    ):
        """保存XT现货账户余额到数据库.
        
        Args:
            balances_data: 余额数据字典 {currency: {available, frozen, total}}
            query_type: 查询类型 (manual, scheduled)
        """
        try:
            async with self.db_manager.session() as session:
                for asset, data in balances_data.items():
                    # 准备原始数据（保存完整的传入数据，包括所有字段）
                    raw_data_dict = {
                        "asset": asset,
                        **{k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()},
                        "query_time": datetime.utcnow().isoformat(),
                        "query_type": query_type,
                    }
                    
                    balance_record = XTSpotBalance(
                        exchange_type='spot',  # 明确设置为 spot
                        query_time=datetime.utcnow(),
                        query_type=query_type,
                        account_id=self.account_id,
                        asset=asset,
                        free=Decimal(str(data.get("available", 0))),
                        locked=Decimal(str(data.get("frozen", 0))),
                        total=Decimal(str(data.get("total", 0))),
                        raw_data=json.dumps(raw_data_dict, ensure_ascii=False, default=str)
                    )
                    session.add(balance_record)
                
                await session.commit()
                account_info = f" (account: {self.account_id})" if self.account_id else ""
                logger.info(f"Saved {len(balances_data)} XT spot balance records{account_info}")
                
        except SQLAlchemyError as e:
            logger.error(f"Failed to save XT spot balance: {e}")
            raise
    
    async def save_perp_balance(
        self,
        balances_data: Dict[str, Any],
        query_type: str = "scheduled"
    ):
        """保存XT合约账户余额到数据库.
        
        Args:
            balances_data: 余额数据字典 {currency: {available, frozen, total}}
            query_type: 查询类型 (manual, scheduled)
        """
        try:
            async with self.db_manager.session() as session:
                for asset, data in balances_data.items():
                    # 准备原始数据（保存完整的传入数据，包括所有字段）
                    raw_data_dict = {
                        "asset": asset,
                        **{k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()},
                        "query_time": datetime.utcnow().isoformat(),
                        "query_type": query_type,
                    }
                    
                    balance_record = XTPerpBalance(
                        exchange_type='perp',  # 明确设置为 perp
                        query_time=datetime.utcnow(),
                        query_type=query_type,
                        account_id=self.account_id,
                        asset=asset,
                        free=Decimal(str(data.get("available", 0))),
                        locked=Decimal(str(data.get("frozen", 0))),
                        total=Decimal(str(data.get("total", 0))),
                        unrealized_pnl=Decimal(str(data.get("unrealized_pnl", 0))) if data.get("unrealized_pnl") is not None else None,
                        realized_pnl=Decimal(str(data.get("realized_pnl", 0))) if data.get("realized_pnl") is not None else None,
                        equity=Decimal(str(data.get("equity", 0))) if data.get("equity") is not None else None,
                        margin=Decimal(str(data.get("margin", 0))) if data.get("margin") is not None else None,
                        margin_ratio=Decimal(str(data.get("margin_ratio", 0))) if data.get("margin_ratio") is not None else None,
                        raw_data=json.dumps(raw_data_dict, ensure_ascii=False, default=str)
                    )
                    session.add(balance_record)
                
                await session.commit()
                account_info = f" (account: {self.account_id})" if self.account_id else ""
                logger.info(f"Saved {len(balances_data)} XT perp balance records{account_info}")
                
        except SQLAlchemyError as e:
            logger.error(f"Failed to save XT perp balance: {e}")
            raise
    
    async def save_perp_positions(
        self,
        positions_data: List[Dict[str, Any]],
        query_type: str = "scheduled"
    ):
        """保存XT合约账户仓位到数据库.
        
        Args:
            positions_data: 持仓数据列表
            query_type: 查询类型 (manual, scheduled)
        """
        try:
            async with self.db_manager.session() as session:
                now = datetime.utcnow()
                for pos_data in positions_data:
                    symbol = pos_data.get("symbol", "")
                    position_side = pos_data.get("positionSide", "LONG")
                    # XT API uses positionSize, but we also support positionAmt for compatibility
                    position_amount = pos_data.get("positionSize") or pos_data.get("positionAmt", "0")
                    entry_price = pos_data.get("entryPrice")
                    # XT API uses calMarkPrice, but we also support markPrice for compatibility
                    mark_price = pos_data.get("calMarkPrice") or pos_data.get("markPrice")
                    # XT API uses floatingPL, but we also support other field names for compatibility
                    unrealized_pnl = pos_data.get("floatingPL") or pos_data.get("unRealizedProfit") or pos_data.get("unrealizedPnl")
                    # XT API uses realizedProfit
                    realized_pnl = pos_data.get("realizedProfit") or pos_data.get("realizedPnl")
                    leverage = pos_data.get("leverage")
                    # XT API uses breakPrice, but we also support liquidationPrice for compatibility
                    liquidation_price = pos_data.get("breakPrice") or pos_data.get("liquidationPrice")
                    # XT API uses isolatedMargin, but we also support margin for compatibility
                    margin = pos_data.get("isolatedMargin") or pos_data.get("margin")
                    roe = pos_data.get("roe")
                    maint_margin = (
                        pos_data.get("maintMargin")
                        or pos_data.get("maintenanceMargin")
                        or pos_data.get("maintMarginAmount")
                    )
                    
                    # 保存原始数据（完整的API响应）
                    raw_data = json.dumps(pos_data, ensure_ascii=False, default=str)
                    
                    position_record = XTPerpPosition(
                        query_time=now,
                        query_type=query_type,
                        account_id=self.account_id,
                        symbol=str(symbol),
                        position_side=str(position_side),
                        position_amount=Decimal(str(position_amount)) if position_amount else Decimal("0"),
                        entry_price=Decimal(str(entry_price)) if entry_price else None,
                        mark_price=Decimal(str(mark_price)) if mark_price else None,
                        unrealized_pnl=Decimal(str(unrealized_pnl)) if unrealized_pnl else None,
                        realized_pnl=Decimal(str(realized_pnl)) if realized_pnl else None,
                        percentage=Decimal(str(pos_data.get("percentage"))) if pos_data.get("percentage") else None,
                        notional=Decimal(str(pos_data.get("notional"))) if pos_data.get("notional") else None,
                        isolated=pos_data.get("isolated", False),
                        leverage=str(leverage) if leverage else None,
                        liquidation_price=Decimal(str(liquidation_price)) if liquidation_price else None,
                        margin=Decimal(str(margin)) if margin else None,
                        roe=Decimal(str(roe)) if roe else None,
                        maintenance_margin=Decimal(str(maint_margin)) if maint_margin else None,
                        raw_data=raw_data
                    )
                    session.add(position_record)
                
                await session.commit()
                account_info = f" (account: {self.account_id})" if self.account_id else ""
                logger.info(f"Saved {len(positions_data)} XT perp position records{account_info}")
                
        except SQLAlchemyError as e:
            logger.error(f"Failed to save XT perp positions: {e}")
            raise

    async def save_position_updates(
        self,
        positions_data: List[Dict[str, Any]],
        query_type: str = "scheduled",
    ):
        """保存XT永续仓位定时更新记录."""
        try:
            async with self.db_manager.session() as session:
                now = datetime.utcnow()
                for pos_data in positions_data:
                    symbol = pos_data.get("symbol", "")
                    position_side = pos_data.get("positionSide") or pos_data.get("position_side", "LONG")
                    position_amount = pos_data.get("positionSize") or pos_data.get("positionAmt") or pos_data.get("position_amount", "0")
                    entry_price = pos_data.get("entryPrice")
                    mark_price = pos_data.get("calMarkPrice") or pos_data.get("markPrice")
                    liquidation_price = pos_data.get("breakPrice") or pos_data.get("liquidationPrice")
                    unrealized_pnl = pos_data.get("floatingPL") or pos_data.get("unRealizedProfit") or pos_data.get("unrealizedPnl")
                    realized_pnl = pos_data.get("realizedProfit") or pos_data.get("realizedPnl")
                    margin = pos_data.get("isolatedMargin") or pos_data.get("margin")
                    maint_margin = (
                        pos_data.get("maintMargin")
                        or pos_data.get("maintenanceMargin")
                        or pos_data.get("maintMarginAmount")
                    )
                    leverage = pos_data.get("leverage")
                    roe = pos_data.get("roe")

                    record = XTRestPositionUpdate(
                        query_time=now,
                        query_type=query_type,
                        account_id=self.account_id,
                        symbol=str(symbol),
                        position_side=str(position_side),
                        position_amount=Decimal(str(position_amount)) if position_amount is not None else Decimal("0"),
                        entry_price=Decimal(str(entry_price)) if entry_price else None,
                        mark_price=Decimal(str(mark_price)) if mark_price else None,
                        liquidation_price=Decimal(str(liquidation_price)) if liquidation_price else None,
                        unrealized_pnl=Decimal(str(unrealized_pnl)) if unrealized_pnl else None,
                        realized_pnl=Decimal(str(realized_pnl)) if realized_pnl else None,
                        margin=Decimal(str(margin)) if margin else None,
                        leverage=str(leverage) if leverage else None,
                        roe=Decimal(str(roe)) if roe else None,
                        maintenance_margin=Decimal(str(maint_margin)) if maint_margin else None,
                        raw_data=json.dumps(pos_data, ensure_ascii=False, default=str),
                    )
                    session.add(record)

                await session.commit()
                account_info = f" (account: {self.account_id})" if self.account_id else ""
                logger.info(f"Saved {len(positions_data)} XT rest position update records{account_info}")

        except SQLAlchemyError as e:
            logger.error(f"Failed to save XT rest position updates: {e}")
            raise

