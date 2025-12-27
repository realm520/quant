"""XT 订单和成交数据对账服务."""

from datetime import datetime
from typing import Dict, List
from decimal import Decimal
import json

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_websocket_models import XTOrderUpdate, XTTradeUpdate
from tri_arb.services.reconciliation import BaseReconciliationService
from tri_arb.utils.json_utils import dumps_with_decimal

logger = get_logger(__name__)


class XTReconciliationService(BaseReconciliationService):
    """XT 对账服务.

    定期从 XT REST API 拉取订单和成交数据，与数据库对比并补全缺失数据。
    """

    def __init__(
        self,
        exchange: XTPerpExchange,
        db_manager: DatabaseManager,
        poll_interval: int = 60,
        lookback_window: int = 600,
        account_id: Optional[str] = None,
    ):
        """初始化 XT 对账服务.

        Args:
            exchange: XT 交易所 adapter
            db_manager: 数据库管理器
            poll_interval: 轮询间隔（秒）
            lookback_window: 回溯窗口（秒）
            account_id: 账号ID（可选），用于区分多账号数据
        """
        super().__init__(exchange, db_manager, poll_interval, lookback_window)
        self.account_id = account_id
        logger.info(
            "XT reconciliation service initialized (auto-discover symbols)",
            account_id=account_id,
        )

    @property
    def exchange_name(self) -> str:
        return "xt_perp"

    async def reconcile_orders(
        self, session: AsyncSession, start_time: datetime, end_time: datetime
    ) -> Dict[str, int]:
        """对账 XT 订单数据.

        Args:
            session: 数据库会话
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息: {'fetched': N, 'inserted': M, 'updated': K}
        """
        stats = {"fetched": 0, "inserted": 0, "updated": 0}

        # 转换为毫秒时间戳
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        try:
            # 从数据库获取最近活跃的交易对
            symbols = await self._get_active_symbols(session, start_time)

            if not symbols:
                logger.debug("No active symbols found, skipping reconciliation")
                return stats

            logger.debug(
                f"Reconciling orders for {len(symbols)} symbols: {symbols[:5]}..."
            )

            for symbol in symbols:
                # 使用 savepoint 隔离每个 symbol 的失败
                async with session.begin_nested():
                    try:
                        # 从 REST API 获取订单（XT 返回 Order 对象列表）
                        orders = await self.exchange.get_order_history(
                            symbol=symbol,
                            start_time=start_ms,
                            end_time=end_ms,
                            limit=500,
                        )
                        stats["fetched"] += len(orders)

                        for order in orders:
                            # 转换为数据库模型
                            order_record = self._convert_order_to_db_model(order)

                            # 使用 PostgreSQL INSERT ... ON CONFLICT DO UPDATE
                            stmt = insert(XTOrderUpdate).values(**order_record)
                            stmt = stmt.on_conflict_do_update(
                                constraint="uq_xt_order_id_time_account",
                                set_={
                                    "status": stmt.excluded.status,
                                    "filled_quantity": stmt.excluded.filled_quantity,
                                    "raw_data": stmt.excluded.raw_data,
                                },
                            )
                            result = await session.execute(stmt)

                            if result.rowcount > 0:
                                stats["inserted"] += 1

                    except Exception as e:
                        logger.error(
                            "Failed to reconcile orders for symbol",
                            symbol=symbol,
                            error=str(e),
                            exc_info=True,
                        )
                        # savepoint 自动回滚，不影响其他 symbol

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
        """对账 XT 成交数据.

        Args:
            session: 数据库会话
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息: {'fetched': N, 'inserted': M, 'skipped': K}
        """
        stats = {"fetched": 0, "inserted": 0, "skipped": 0}

        # 转换为毫秒时间戳
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        try:
            # 从数据库获取最近活跃的交易对
            symbols = await self._get_active_symbols(session, start_time)

            if not symbols:
                logger.debug("No active symbols found, skipping reconciliation")
                return stats

            for symbol in symbols:
                # 使用 savepoint 隔离每个 symbol 的失败
                async with session.begin_nested():
                    try:
                        # 从 REST API 获取成交（XT 返回字典列表）
                        trades = await self.exchange.get_user_trades(
                            symbol=symbol,
                            start_time=start_ms,
                            end_time=end_ms,
                            limit=500,
                        )
                        stats["fetched"] += len(trades)

                        for trade in trades:
                            # 转换为数据库模型
                            trade_record = self._convert_trade_to_db_model(trade)

                            # 使用 PostgreSQL INSERT ... ON CONFLICT DO NOTHING
                            # 成交记录不可变，只需插入
                            stmt = insert(XTTradeUpdate).values(**trade_record)
                            # XT 的成交表使用 (trade_id, account_id) 唯一约束
                            stmt = stmt.on_conflict_do_nothing(
                                constraint="uq_xt_trade_id_account"
                            )
                            result = await session.execute(stmt)

                            if result.rowcount > 0:
                                stats["inserted"] += 1
                            else:
                                stats["skipped"] += 1

                    except Exception as e:
                        logger.error(
                            "Failed to reconcile trades for symbol",
                            symbol=symbol,
                            error=str(e),
                            exc_info=True,
                        )
                        # savepoint 自动回滚，不影响其他 symbol

        except Exception as e:
            logger.error(
                "Failed to reconcile trades",
                error=str(e),
                exc_info=True,
            )
            raise

        return stats

    def _convert_order_to_db_model(self, order) -> dict:
        """将 Order 对象转换为数据库模型.

        Args:
            order: Order 对象

        Returns:
            数据库模型字典
        """
        # XT 返回的是 Order 对象，需要转换为数据库模型
        symbol = f"{order.trading_pair.base_currency}_{order.trading_pair.quote_currency}".upper()

        return {
            "update_time": order.timestamp or datetime.utcnow(),
            "account_id": self.account_id,  # 添加 account_id 字段
            "symbol": symbol,
            "order_id": order.exchange_order_id,
            "client_order_id": None,  # Order 对象没有 client_order_id
            "side": order.side.value,
            "order_type": order.order_type.value,
            "position_side": order.position_side,
            "quantity": order.quantity,
            "price": order.price,
            "filled_quantity": order.filled_quantity or Decimal("0"),
            "status": order.status.value,
            "time_in_force": None,  # Order 对象没有 time_in_force
            "create_time": order.timestamp,
            "update_time_order": order.timestamp,
            "raw_data": json.dumps(
                {
                    "order_id": order.exchange_order_id,
                    "symbol": symbol,
                    "side": order.side.value,
                    "order_type": order.order_type.value,
                    "quantity": str(order.quantity),
                    "price": str(order.price) if order.price else None,
                    "status": order.status.value,
                    "position_side": order.position_side,
                }
            ),
        }

    def _convert_trade_to_db_model(self, trade: dict) -> dict:
        """将 REST API 成交转换为数据库模型.

        Args:
            trade: REST API 返回的成交数据

        Returns:
            数据库模型字典
        """
        # XT REST API 成交字段参考：trade-list 端点

        def safe_decimal(value):
            if value is None or value == "":
                return Decimal("0")
            return Decimal(str(value))

        def safe_datetime(value):
            if value is None or value == "":
                return datetime.utcnow()
            try:
                return datetime.fromtimestamp(int(value) / 1000)
            except (ValueError, TypeError):
                return datetime.utcnow()

        return {
            "update_time": safe_datetime(trade.get("time")),
            "account_id": self.account_id,  # 添加 account_id 字段
            "symbol": trade.get("symbol", "").upper(),
            "order_id": str(trade.get("orderId", "")),
            "trade_id": str(trade.get("id", "")),
            "side": trade.get("side", "BUY").upper(),
            "price": safe_decimal(trade.get("price")),
            "quantity": safe_decimal(trade.get("qty")),
            "quote_quantity": safe_decimal(trade.get("amount")),
            "commission": safe_decimal(trade.get("fee")),
            "commission_asset": trade.get("feeCurrency"),
            "is_maker": trade.get("isMaker", False),
            "position_side": trade.get("positionSide"),
            "raw_data": dumps_with_decimal(trade),
        }

    async def _get_active_symbols(
        self, session: AsyncSession, since: datetime
    ) -> List[str]:
        """从数据库获取最近活跃的交易对.

        Args:
            session: 数据库会话
            since: 起始时间

        Returns:
            交易对列表
        """
        # 查询最近有订单活动的交易对
        stmt = select(XTOrderUpdate.symbol).where(XTOrderUpdate.update_time >= since)
        # 如果指定了 account_id，添加过滤条件
        if self.account_id:
            stmt = stmt.where(XTOrderUpdate.account_id == self.account_id)
        stmt = stmt.distinct()

        result = await session.execute(stmt)
        symbols = [row[0].lower() for row in result.fetchall()]  # XT 使用小写

        return symbols
