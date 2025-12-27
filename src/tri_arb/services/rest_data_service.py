"""Generic REST API data service for all exchanges.

Provides unified service for saving REST API query data to database
and managing scheduled query statistics.
"""

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError

from tri_arb.config.logging import get_logger
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.rest_models import ScheduledQuery
from tri_arb.storage.exchange_rest_models import (
    get_balance_model,
    get_position_model,
    get_order_model,
)

logger = get_logger(__name__)


class RestDataService:
    """通用REST API数据服务.

    提供统一的接口来保存REST API查询结果到数据库，
    并管理定时查询的统计信息。
    """

    def __init__(self, db_manager: DatabaseManager):
        """初始化REST数据服务.

        Args:
            db_manager: 数据库管理器
        """
        self.db_manager = db_manager

    async def save_balance_query(
        self,
        exchange: str,
        exchange_type: str,
        balances_data: Dict[str, Any],
        query_type: str = "manual",
        account_id: Optional[str] = None,
    ):
        """保存余额查询结果到数据库.

        Args:
            exchange: 交易所名称 (binance, okx, gate, xt)
            exchange_type: 交易类型 (spot, perp)
            balances_data: 余额数据字典
            query_type: 查询类型 (manual, scheduled)
            account_id: 账号ID（可选，用于区分多账号）
        """
        try:
            # 根据交易所选择对应的表模型
            BalanceModel = get_balance_model(exchange)

            async with self.db_manager.session() as session:
                for asset, data in balances_data.items():
                    balance_record = BalanceModel(
                        exchange_type=exchange_type,
                        query_time=datetime.utcnow(),
                        query_type=query_type,
                        account_id=account_id,
                        asset=asset,
                        free=Decimal(str(data.get("available", 0))),
                        locked=Decimal(str(data.get("frozen", 0))),
                        total=Decimal(str(data.get("total", 0))),
                        raw_data=json.dumps(data, ensure_ascii=False, default=str),
                    )
                    session.add(balance_record)

                await session.commit()
                logger.info(
                    f"Saved {len(balances_data)} balance records for {exchange} {exchange_type}"
                )

        except SQLAlchemyError as e:
            logger.error(f"Failed to save balance query: {e}")
            raise

    async def save_positions_query(
        self,
        exchange: str,
        exchange_type: str,
        positions_data: List[Dict[str, Any]],
        query_type: str = "manual",
        account_id: Optional[str] = None,
    ):
        """保存持仓查询结果到数据库.

        Args:
            exchange: 交易所名称 (binance, okx, gate, xt)
            exchange_type: 交易类型 (spot, perp)
            positions_data: 持仓数据列表
            query_type: 查询类型 (manual, scheduled)
            account_id: 账号ID（可选，用于区分多账号）
        """
        try:
            # 根据交易所选择对应的表模型
            PositionModel = get_position_model(exchange)

            async with self.db_manager.session() as session:
                for pos_data in positions_data:
                    # 尝试标准化不同交易所的字段
                    symbol = (
                        pos_data.get("symbol")
                        or pos_data.get("instId")
                        or pos_data.get("contract")
                    )
                    position_amount = (
                        pos_data.get("positionAmt")
                        or pos_data.get("pos")
                        or pos_data.get("size")
                    )
                    entry_price = (
                        pos_data.get("entryPrice")
                        or pos_data.get("avgPx")
                        or pos_data.get("entry_price")
                    )
                    mark_price = (
                        pos_data.get("markPrice")
                        or pos_data.get("markPx")
                        or pos_data.get("mark_price")
                    )
                    unrealized_pnl = (
                        pos_data.get("unRealizedProfit")
                        or pos_data.get("upl")
                        or pos_data.get("unrealised_pnl")
                    )
                    leverage = (
                        pos_data.get("leverage")
                        or pos_data.get("lever")
                        or pos_data.get("leverage")
                    )

                    # 处理持仓方向
                    position_side = pos_data.get("positionSide") or pos_data.get(
                        "posSide"
                    )
                    if not position_side and isinstance(
                        position_amount, (int, float, str)
                    ):
                        try:
                            amt = Decimal(str(position_amount))
                            if amt > 0:
                                position_side = "LONG"
                            elif amt < 0:
                                position_side = "SHORT"
                            else:
                                position_side = "BOTH"
                        except Exception:
                            position_side = "UNKNOWN"

                    position_record = PositionModel(
                        exchange_type=exchange_type,
                        query_time=datetime.utcnow(),
                        query_type=query_type,
                        account_id=account_id,
                        symbol=str(symbol),
                        position_side=str(position_side),
                        position_amount=Decimal(str(position_amount)),
                        entry_price=Decimal(str(entry_price)) if entry_price else None,
                        mark_price=Decimal(str(mark_price)) if mark_price else None,
                        unrealized_pnl=(
                            Decimal(str(unrealized_pnl)) if unrealized_pnl else None
                        ),
                        percentage=(
                            Decimal(str(pos_data.get("percentage")))
                            if pos_data.get("percentage")
                            else None
                        ),
                        notional=(
                            Decimal(str(pos_data.get("notional")))
                            if pos_data.get("notional")
                            else None
                        ),
                        isolated=pos_data.get("isolated", False),
                        leverage=str(leverage) if leverage else None,
                        raw_data=json.dumps(pos_data, ensure_ascii=False, default=str),
                    )
                    session.add(position_record)

                await session.commit()
                logger.info(
                    f"Saved {len(positions_data)} position records for {exchange} {exchange_type}"
                )

        except SQLAlchemyError as e:
            logger.error(f"Failed to save positions query: {e}")
            raise

    async def save_orders_query(
        self,
        exchange: str,
        exchange_type: str,
        orders_data: List[Dict[str, Any]],
        query_type: str = "manual",
        account_id: Optional[str] = None,
    ):
        """保存订单查询结果到数据库.

        Args:
            exchange: 交易所名称 (binance, okx, gate, xt)
            exchange_type: 交易类型 (spot, perp)
            orders_data: 订单数据列表
            query_type: 查询类型 (manual, scheduled)
            account_id: 账号ID（可选，用于区分多账号）
        """
        try:
            # 根据交易所选择对应的表模型
            OrderModel = get_order_model(exchange)

            async with self.db_manager.session() as session:
                for order_data in orders_data:
                    # 尝试标准化不同交易所的字段
                    symbol = (
                        order_data.get("symbol")
                        or order_data.get("instId")
                        or order_data.get("contract")
                    )
                    order_id = (
                        order_data.get("orderId")
                        or order_data.get("ordId")
                        or order_data.get("id")
                    )
                    client_order_id = order_data.get("clientOrderId") or order_data.get(
                        "clOrdId"
                    )
                    side = order_data.get("side")
                    order_type = (
                        order_data.get("type")
                        or order_data.get("ordType")
                        or order_data.get("tif")
                    )
                    time_in_force = order_data.get("timeInForce")
                    original_quantity = (
                        order_data.get("origQty")
                        or order_data.get("sz")
                        or order_data.get("size")
                    )
                    original_price = order_data.get("price") or order_data.get("px")
                    average_price = order_data.get("avgPrice") or order_data.get(
                        "avgPx"
                    )
                    executed_quantity = (
                        order_data.get("executedQty")
                        or order_data.get("accFillSz")
                        or (
                            Decimal(str(original_quantity))
                            - Decimal(str(order_data.get("left", 0)))
                            if original_quantity
                            else 0
                        )
                    )
                    cumulative_quote_quantity = order_data.get("cummulativeQuoteQty")
                    order_status = order_data.get("status") or order_data.get("state")
                    position_side = order_data.get("positionSide") or order_data.get(
                        "posSide"
                    )
                    is_reduce_only = order_data.get("reduceOnly", False)

                    # 时间字段
                    order_time_ms = (
                        order_data.get("time")
                        or order_data.get("cTime")
                        or order_data.get("create_time")
                    )
                    update_time_ms = (
                        order_data.get("updateTime")
                        or order_data.get("uTime")
                        or order_data.get("finish_time")
                        or order_data.get("update_time")
                    )

                    order_time = (
                        datetime.fromtimestamp(int(order_time_ms) / 1000)
                        if order_time_ms
                        else None
                    )
                    update_time = (
                        datetime.fromtimestamp(int(update_time_ms) / 1000)
                        if update_time_ms
                        else None
                    )

                    order_record = OrderModel(
                        exchange_type=exchange_type,
                        query_time=datetime.utcnow(),
                        query_type=query_type,
                        account_id=account_id,
                        symbol=str(symbol),
                        order_id=str(order_id),
                        client_order_id=(
                            str(client_order_id) if client_order_id else None
                        ),
                        side=str(side),
                        order_type=str(order_type),
                        time_in_force=str(time_in_force) if time_in_force else None,
                        original_quantity=Decimal(str(original_quantity)),
                        original_price=(
                            Decimal(str(original_price)) if original_price else None
                        ),
                        average_price=(
                            Decimal(str(average_price)) if average_price else None
                        ),
                        executed_quantity=Decimal(str(executed_quantity)),
                        cumulative_quote_quantity=(
                            Decimal(str(cumulative_quote_quantity))
                            if cumulative_quote_quantity
                            else None
                        ),
                        order_status=str(order_status),
                        position_side=str(position_side) if position_side else None,
                        is_reduce_only=is_reduce_only,
                        order_time=order_time,
                        update_time=update_time,
                        raw_data=json.dumps(
                            order_data, ensure_ascii=False, default=str
                        ),
                    )
                    session.add(order_record)

                await session.commit()
                logger.info(
                    f"Saved {len(orders_data)} order records for {exchange} {exchange_type}"
                )

        except SQLAlchemyError as e:
            logger.error(f"Failed to save orders query: {e}")
            raise

    async def start_scheduled_query(
        self,
        exchange: str,
        query_type: str,
        exchange_type: str,
        interval_minutes: int,
        account_id: Optional[str] = None,
    ) -> int:
        """记录定时查询的开始.

        Args:
            exchange: 交易所名称
            query_type: 查询类型 (balance, position, order)
            exchange_type: 交易类型 (spot, perp)
            interval_minutes: 查询间隔（分钟）
            account_id: 账号ID（可选，用于区分多账号）

        Returns:
            定时查询记录ID
        """
        try:
            async with self.db_manager.session() as session:
                scheduled_query = ScheduledQuery(
                    exchange=exchange,
                    query_type=query_type,
                    exchange_type=exchange_type,
                    start_time=datetime.utcnow(),
                    interval_minutes=interval_minutes,
                    is_active=True,
                    account_id=account_id,
                )
                session.add(scheduled_query)
                await session.commit()
                logger.info(
                    f"Started scheduled query for {exchange} {query_type} (ID: {scheduled_query.id})"
                )
                return scheduled_query.id

        except SQLAlchemyError as e:
            logger.error(f"Failed to start scheduled query: {e}")
            raise

    async def update_scheduled_query_stats(
        self,
        query_id: int,
        success: bool,
        error_message: Optional[str] = None,
    ):
        """更新定时查询的统计信息.

        Args:
            query_id: 定时查询记录ID
            success: 是否成功
            error_message: 错误信息（如果失败）
        """
        try:
            async with self.db_manager.session() as session:
                scheduled_query = await session.get(ScheduledQuery, query_id)
                if scheduled_query:
                    scheduled_query.total_queries += 1
                    scheduled_query.last_query_time = datetime.utcnow()

                    if success:
                        scheduled_query.successful_queries += 1
                        scheduled_query.last_success_time = datetime.utcnow()
                        scheduled_query.last_error = None
                    else:
                        scheduled_query.failed_queries += 1
                        scheduled_query.last_error = error_message

                    await session.commit()
                    logger.debug(
                        f"Updated scheduled query {query_id} stats. Success: {success}"
                    )
                else:
                    logger.warning(
                        f"Scheduled query with ID {query_id} not found for update."
                    )

        except SQLAlchemyError as e:
            logger.error(f"Failed to update scheduled query stats: {e}")
            raise

    async def end_scheduled_query(self, query_id: int):
        """结束定时查询.

        Args:
            query_id: 定时查询记录ID
        """
        try:
            async with self.db_manager.session() as session:
                scheduled_query = await session.get(ScheduledQuery, query_id)
                if scheduled_query:
                    scheduled_query.end_time = datetime.utcnow()
                    scheduled_query.is_active = False
                    await session.commit()
                    logger.info(f"Ended scheduled query {query_id}.")
                else:
                    logger.warning(
                        f"Scheduled query with ID {query_id} not found for ending."
                    )

        except SQLAlchemyError as e:
            logger.error(f"Failed to end scheduled query: {e}")
            raise
