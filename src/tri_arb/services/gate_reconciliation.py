"""Gate.io 订单和成交数据对账服务."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal
import json

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.gate_perp import GatePerpExchange
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.gate_models import GateOrder, GateTrade
from tri_arb.services.reconciliation import BaseReconciliationService
from tri_arb.utils.json_utils import dumps_with_decimal

logger = get_logger(__name__)


class GateReconciliationService(BaseReconciliationService):
    """Gate.io 对账服务.

    定期从 Gate.io REST API 拉取订单和成交数据，与数据库对比并补全缺失数据。
    """

    def __init__(
        self,
        exchange: GatePerpExchange,
        db_manager: DatabaseManager,
        poll_interval: int = 60,
        lookback_window: int = 600,
    ):
        """初始化 Gate.io 对账服务.

        Args:
            exchange: Gate.io 交易所 adapter
            db_manager: 数据库管理器
            poll_interval: 轮询间隔（秒）
            lookback_window: 回溯窗口（秒）
        """
        super().__init__(exchange, db_manager, poll_interval, lookback_window)
        logger.info(
            "Gate.io order data reconciliation service initialized (auto-discover symbols)"
        )

    @property
    def exchange_name(self) -> str:
        return "gate_perp"

    @staticmethod
    def _order_timestamp(order: dict) -> int:
        for field in ("update_time", "finish_time", "create_time"):
            value = order.get(field)
            if value not in (None, "", "0"):
                try:
                    return int(float(value))
                except (ValueError, TypeError):
                    continue
        return 0

    @staticmethod
    def _trade_timestamp(trade: dict) -> int:
        value = trade.get("create_time")
        if value in (None, "", "0"):
            return 0
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0

    async def _discover_contracts(
        self, session: AsyncSession, since: datetime
    ) -> List[str]:
        contracts: set[str] = set()

        order_stmt = (
            select(GateOrder.contract).where(GateOrder.update_time >= since).distinct()
        )
        order_result = await session.execute(order_stmt)
        contracts.update(row[0] for row in order_result.fetchall() if row[0])

        trade_stmt = (
            select(GateTrade.contract).where(GateTrade.create_time >= since).distinct()
        )
        trade_result = await session.execute(trade_stmt)
        contracts.update(row[0] for row in trade_result.fetchall() if row[0])

        if contracts:
            return sorted(contracts)

        try:
            positions = await self.exchange.get_positions()
            position_contracts = {
                pos.get("contract") for pos in positions if pos.get("contract")
            }
            if position_contracts:
                logger.info(
                    "Discovered Gate.io contracts from REST positions",
                    contracts=sorted(position_contracts),
                )
                contracts.update(position_contracts)
        except Exception as e:
            logger.warning(
                "Failed to fetch Gate.io positions while discovering contracts",
                error=str(e),
                exc_info=True,
            )

        if contracts:
            return sorted(contracts)

        try:
            open_orders = await self.exchange.get_open_orders()
            order_contracts = {
                order.get("contract") for order in open_orders if order.get("contract")
            }
            if order_contracts:
                logger.info(
                    "Discovered Gate.io contracts from open orders",
                    contracts=sorted(order_contracts),
                )
                contracts.update(order_contracts)
        except Exception as e:
            logger.warning(
                "Failed to fetch Gate.io open orders while discovering contracts",
                error=str(e),
                exc_info=True,
            )

        if not contracts:
            logger.debug("No active Gate.io contracts found via DB or REST fallback")
        return sorted(contracts)

    async def _fetch_orders_with_pagination(
        self,
        contract: str,
        start_time_sec: int,
        end_time_sec: int,
        limit: int = 100,
        max_iterations: int = 50,
    ) -> List[dict]:
        order_map: dict[str, dict] = {}
        next_end = end_time_sec

        for _ in range(max_iterations):
            if next_end <= start_time_sec:
                break

            batch = await self.exchange.get_all_orders(
                symbol=contract,
                start_time=start_time_sec,
                end_time=next_end,
                limit=limit,
            )

            if not batch:
                break

            for order in batch:
                order_id = str(order.get("id"))
                timestamp = self._order_timestamp(order)
                if not order_id:
                    continue

                current = order_map.get(order_id)
                if current is None or self._order_timestamp(current) < timestamp:
                    order_map[order_id] = order

            if len(batch) < limit:
                break

            valid_times = [
                self._order_timestamp(order)
                for order in batch
                if self._order_timestamp(order) > 0
            ]
            if not valid_times:
                break

            next_end = min(valid_times) - 1

        return sorted(order_map.values(), key=self._order_timestamp)

    async def _fetch_trades_with_pagination(
        self,
        contract: str,
        start_time_sec: int,
        end_time_sec: int,
        limit: int = 100,
        max_iterations: int = 50,
    ) -> List[dict]:
        trade_map: dict[str, dict] = {}
        next_end = end_time_sec

        for _ in range(max_iterations):
            if next_end <= start_time_sec:
                break

            batch = await self.exchange.get_user_trades(
                symbol=contract,
                start_time=start_time_sec,
                end_time=next_end,
                limit=limit,
            )

            if not batch:
                break

            for trade in batch:
                trade_id = str(trade.get("id"))
                timestamp = self._trade_timestamp(trade)
                if not trade_id:
                    continue

                current = trade_map.get(trade_id)
                if current is None or self._trade_timestamp(current) < timestamp:
                    trade_map[trade_id] = trade

            if len(batch) < limit:
                break

            valid_times = [
                self._trade_timestamp(trade)
                for trade in batch
                if self._trade_timestamp(trade) > 0
            ]
            if not valid_times:
                break

            next_end = min(valid_times) - 1

        return sorted(trade_map.values(), key=self._trade_timestamp)

    async def reconcile_orders(
        self, session: AsyncSession, start_time: datetime, end_time: datetime
    ) -> Dict[str, int]:
        """对账 Gate.io 订单数据.

        Args:
            session: 数据库会话
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息: {'fetched': N, 'inserted': M, 'updated': K}
        """
        stats = {"fetched": 0, "inserted": 0, "updated": 0}

        # Gate.io 使用秒级时间戳
        start_sec = int(start_time.timestamp())
        end_sec = int(end_time.timestamp())

        try:
            contracts = await self._discover_contracts(session, start_time)

            if not contracts:
                logger.debug(
                    "No Gate.io contracts discovered, skipping order reconciliation"
                )
                return stats

            logger.debug(
                "Reconciling Gate.io orders",
                contracts=contracts,
                start_ts=start_sec,
                end_ts=end_sec,
            )

            for contract in contracts:
                try:
                    orders = await self._fetch_orders_with_pagination(
                        contract=contract,
                        start_time_sec=start_sec,
                        end_time_sec=end_sec,
                        limit=100,
                    )
                    stats["fetched"] += len(orders)

                    for order in orders:
                        try:
                            order_record = self._convert_order_to_db_model(order)

                            # 检查订单是否已存在（基于 order_id 和 update_time）
                            existing_stmt = (
                                select(GateOrder.order_id, GateOrder.update_time)
                                .where(
                                    GateOrder.order_id == order_record["order_id"],
                                    GateOrder.update_time
                                    == order_record["update_time"],
                                )
                                .limit(1)
                            )
                            existing_row = await session.execute(existing_stmt)
                            has_existing = existing_row.scalar_one_or_none() is not None

                            stmt = insert(GateOrder).values(**order_record)
                            stmt = stmt.on_conflict_do_update(
                                index_elements=["order_id", "update_time"],
                                set_={
                                    "contract": stmt.excluded.contract,
                                    "size": stmt.excluded.size,
                                    "price": stmt.excluded.price,
                                    "left": stmt.excluded.left,
                                    "filled_total": stmt.excluded.filled_total,
                                    "status": stmt.excluded.status,
                                    "create_time": stmt.excluded.create_time,
                                    "finish_time": stmt.excluded.finish_time,
                                    "reduce_only": stmt.excluded.reduce_only,
                                    "tif": stmt.excluded.tif,
                                    "text": stmt.excluded.text,
                                    "raw_data": stmt.excluded.raw_data,
                                },
                            )
                            result = await session.execute(stmt)

                            if result.rowcount > 0:
                                if has_existing:
                                    stats["updated"] += 1
                                else:
                                    stats["inserted"] += 1
                        except Exception as order_error:
                            logger.warning(
                                "Failed to save individual order",
                                contract=contract,
                                order_id=order.get("id"),
                                error=str(order_error),
                            )
                            continue

                except Exception as e:
                    logger.error(
                        "Failed to reconcile orders for contract",
                        contract=contract,
                        error=str(e),
                        exc_info=True,
                    )
                    continue

        except Exception as e:
            logger.error(
                "Failed to reconcile orders",
                error=str(e),
                exc_info=True,
            )
            raise

        return stats

    async def reconcile_trades(
        self, session: AsyncSession, start_time: datetime, end_time: datetime
    ) -> Dict[str, int]:
        """对账 Gate.io 成交数据（已禁用，仅返回空统计）.

        Args:
            session: 数据库会话
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息: {'fetched': 0, 'inserted': 0, 'skipped': 0}
        """
        # Gate.io 对账服务已优化为仅处理订单数据，不处理成交数据
        logger.debug("Gate.io trade reconciliation skipped (order-only mode)")
        return {"fetched": 0, "inserted": 0, "skipped": 0}

    def _convert_order_to_db_model(self, order: dict) -> dict:
        """将 REST API 订单转换为数据库模型.

        Args:
            order: REST API 返回的订单数据

        Returns:
            数据库模型字典
        """
        # Gate.io REST API 订单字段参考：
        # https://www.gate.io/docs/developers/apiv4/en/#list-futures-orders

        def safe_decimal(value):
            if value is None or value == "":
                return None
            return Decimal(str(value))

        def safe_datetime(value):
            if value is None or value == "":
                return None
            try:
                return datetime.fromtimestamp(float(value))
            except (ValueError, TypeError):
                return None

        return {
            "order_id": str(order["id"]),
            "contract": order["contract"],
            "size": safe_decimal(order.get("size")),
            "price": safe_decimal(order.get("price")),
            "left": safe_decimal(order.get("left")),
            "filled_total": safe_decimal(order.get("filled_total")),
            "status": order.get("status", "unknown"),
            "create_time": safe_datetime(order.get("create_time")),
            "finish_time": safe_datetime(order.get("finish_time")),
            "update_time": safe_datetime(order.get("finish_time"))
            or datetime.utcnow(),  # Gate 没有单独的 update_time
            "reduce_only": order.get("reduce_only", False),
            "tif": order.get("tif"),
            "text": order.get("text"),
            "raw_data": dumps_with_decimal(order),
        }

    def _convert_trade_to_db_model(self, trade: dict) -> dict:
        """将 REST API 成交转换为数据库模型.

        Args:
            trade: REST API 返回的成交数据

        Returns:
            数据库模型字典
        """
        # Gate.io REST API 成交字段参考：
        # https://www.gate.io/docs/developers/apiv4/en/#list-personal-trading-history

        def safe_decimal(value):
            if value is None or value == "":
                return None
            return Decimal(str(value))

        def safe_datetime(value):
            if value is None or value == "":
                return None
            try:
                return datetime.fromtimestamp(float(value))
            except (ValueError, TypeError):
                return None

        return {
            "trade_id": str(trade["id"]),
            "order_id": str(trade["order_id"]),
            "contract": trade["contract"],
            "size": safe_decimal(trade.get("size")),
            "price": safe_decimal(trade.get("price")),
            "role": trade.get("role"),
            "create_time": safe_datetime(trade.get("create_time")) or datetime.utcnow(),
            "raw_data": dumps_with_decimal(trade),
        }

    async def _run_reconciliation(self, lookback_seconds: Optional[int] = None):
        """执行一次订单数据对账（仅处理订单，不处理成交）."""
        end_time = datetime.utcnow()
        lookback = (
            lookback_seconds if lookback_seconds is not None else self.lookback_window
        )
        start_time = end_time - timedelta(seconds=lookback)

        logger.debug(
            "Starting Gate order data reconciliation",
            exchange=self.exchange_name,
            start_time=start_time,
            end_time=end_time,
        )

        async with self.db_manager.session() as session:
            try:
                # 仅对账订单数据
                order_stats = await self.reconcile_orders(session, start_time, end_time)
                logger.info(
                    "Gate order data reconciliation completed",
                    exchange=self.exchange_name,
                    **order_stats,
                )

                await session.commit()

            except Exception as e:
                logger.error(
                    "Gate order data reconciliation failed",
                    exchange=self.exchange_name,
                    error=str(e),
                    exc_info=True,
                )
                await session.rollback()
                raise
