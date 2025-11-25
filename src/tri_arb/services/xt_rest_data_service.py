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
    
    专门用于保存XT交易所的账户数据到独立的表中：
    - xt_spot_balances: XT现货账户余额
    - xt_perp_balances: XT合约账户余额
    - xt_perp_positions: XT合约账户仓位（REST定时拉取）
    - xt_rest_position_updates: XT合约仓位定时快照（watch-positions 命令）
    
    支持账号特定的表：如果提供 account_id，数据会保存到 {table_name}_{account_id} 表中。
    """
    
    def __init__(self, db_manager: DatabaseManager, account_id: Optional[str] = None):
        """初始化XT REST数据服务.
        
        Args:
            db_manager: 数据库管理器
            account_id: 账号ID（可选），如果提供则使用账号特定的表
        """
        self.db_manager = db_manager
        self.account_id = account_id
        self._account_models = None
        
        # 如果提供了账号ID，加载账号特定的表模型
        if account_id:
            from tri_arb.storage.xt_multi_account_models import create_account_table_models
            self._account_models = create_account_table_models(account_id)
    
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
            # 确保账号特定的表已创建（如果是新账号）
            await self.ensure_account_tables()
            
            # 选择使用账号特定的表模型或默认表模型
            if self._account_models:
                BalanceModel = self._account_models['XTSpotBalance']
            else:
                BalanceModel = XTSpotBalance
            
            async with self.db_manager.session() as session:
                for asset, data in balances_data.items():
                    # 准备原始数据（保存完整的传入数据，包括所有字段）
                    raw_data_dict = {
                        "asset": asset,
                        **{k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()},
                        "query_time": datetime.utcnow().isoformat(),
                        "query_type": query_type,
                    }
                    
                    balance_record = BalanceModel(
                        query_time=datetime.utcnow(),
                        query_type=query_type,
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
            # 确保账号特定的表已创建（如果是新账号）
            await self.ensure_account_tables()
            
            # 选择使用账号特定的表模型或默认表模型
            if self._account_models:
                BalanceModel = self._account_models['XTPerpBalance']
            else:
                BalanceModel = XTPerpBalance
            
            async with self.db_manager.session() as session:
                for asset, data in balances_data.items():
                    # 准备原始数据（保存完整的传入数据，包括所有字段）
                    raw_data_dict = {
                        "asset": asset,
                        **{k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()},
                        "query_time": datetime.utcnow().isoformat(),
                        "query_type": query_type,
                    }
                    
                    balance_record = BalanceModel(
                        query_time=datetime.utcnow(),
                        query_type=query_type,
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
            # 确保账号特定的表已创建（如果是新账号）
            await self.ensure_account_tables()
            
            # 选择使用账号特定的表模型或默认表模型
            if self._account_models:
                PositionModel = self._account_models['XTPerpPosition']
            else:
                PositionModel = XTPerpPosition
            
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
                    
                    position_record = PositionModel(
                        query_time=now,
                        query_type=query_type,
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
            # 确保账号特定的表已创建（如果是新账号）
            await self.ensure_account_tables()
            
            # 选择使用账号特定的表模型或默认表模型
            if self._account_models:
                PositionUpdateModel = self._account_models['XTRestPositionUpdate']
            else:
                PositionUpdateModel = XTRestPositionUpdate
            
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

                    record = PositionUpdateModel(
                        query_time=now,
                        query_type=query_type,
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
    
    async def ensure_account_tables(self):
        """确保账号特定的表已创建."""
        if not self.account_id or not self._account_models:
            return
        
        try:
            async with self.db_manager.async_engine.begin() as conn:
                for model_class in self._account_models.values():
                    await conn.run_sync(
                        lambda sync_conn, m=model_class: m.metadata.create_all(
                            sync_conn, checkfirst=True
                        )
                    )
            logger.info(f"账号 {self.account_id} 的数据库表已就绪")
        except Exception as e:
            logger.error(f"创建账号 {self.account_id} 的表失败: {e}")
            raise

