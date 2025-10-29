"""OKX 订单和成交数据对账服务."""

from datetime import datetime
from typing import Dict, List, Optional
from decimal import Decimal
import json

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.okx_perp import OKXPerpExchange
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.okx_models import OKXOrder, OKXTrade
from tri_arb.services.reconciliation import BaseReconciliationService
from tri_arb.utils.json_utils import dumps_with_decimal

logger = get_logger(__name__)


class OKXReconciliationService(BaseReconciliationService):
    """OKX 对账服务.

    定期从 OKX REST API 拉取订单和成交数据，与数据库对比并补全缺失数据。
    """

    def __init__(
        self,
        exchange: OKXPerpExchange,
        db_manager: DatabaseManager,
        poll_interval: int = 60,
        lookback_window: int = 600,
    ):
        """初始化 OKX 对账服务.

        Args:
            exchange: OKX 交易所 adapter
            db_manager: 数据库管理器
            poll_interval: 轮询间隔（秒）
            lookback_window: 回溯窗口（秒）
        """
        super().__init__(exchange, db_manager, poll_interval, lookback_window)
        logger.info("OKX reconciliation service initialized (auto-discover symbols)")

    @property
    def exchange_name(self) -> str:
        return "okx_perp"

    @staticmethod
    def _order_timestamp(order: dict) -> int:
        for field in ("uTime", "cTime"):
            value = order.get(field)
            if value:
                return int(value)
        return 0

    @staticmethod
    def _trade_timestamp(trade: dict) -> int:
        value = trade.get("ts")
        return int(value) if value else 0

    async def _fetch_orders_with_pagination(
        self,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 100,
        max_iterations: int = 50,
    ) -> List[dict]:
        order_map: dict[tuple[str, str | None], dict] = {}
        next_end = end_time_ms

        for _ in range(max_iterations):
            if next_end <= start_time_ms:
                break

            batch = await self.exchange.get_all_orders(
                symbol=symbol,
                start_time=start_time_ms,
                end_time=next_end,
                limit=limit,
            )

            if not batch:
                break

            for order in batch:
                key = (order.get("ordId"), order.get("instId"))
                timestamp = self._order_timestamp(order)

                existing = order_map.get(key)
                if existing is None or self._order_timestamp(existing) < timestamp:
                    order_map[key] = order

            if len(batch) < limit:
                break

            valid_times = [self._order_timestamp(order) for order in batch if self._order_timestamp(order) > 0]
            if not valid_times:
                break

            next_end = min(valid_times) - 1

        orders = sorted(order_map.values(), key=self._order_timestamp)
        return orders

    async def _fetch_trades_with_pagination(
        self,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 100,
        max_iterations: int = 50,
    ) -> List[dict]:
        trades: dict[str, dict] = {}
        next_end = end_time_ms

        for _ in range(max_iterations):
            if next_end <= start_time_ms:
                break

            batch = await self.exchange.get_user_trades(
                symbol=symbol,
                start_time=start_time_ms,
                end_time=next_end,
                limit=limit,
            )

            if not batch:
                break

            for trade in batch:
                trade_id = trade.get("tradeId")
                timestamp = self._trade_timestamp(trade)
                if trade_id is None:
                    continue

                existing = trades.get(trade_id)
                if existing is None or self._trade_timestamp(existing) < timestamp:
                    trades[trade_id] = trade

            if len(batch) < limit:
                break

            valid_times = [self._trade_timestamp(trade) for trade in batch if self._trade_timestamp(trade) > 0]
            if not valid_times:
                break

            next_end = min(valid_times) - 1

        return sorted(trades.values(), key=self._trade_timestamp)

    async def reconcile_orders(self, session: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """对账 OKX 订单数据.

        Args:
            session: 数据库会话
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息: {'fetched': N, 'inserted': M, 'updated': K}
        """
        stats = {'fetched': 0, 'inserted': 0, 'updated': 0}

        # 转换为毫秒时间戳
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        try:
            orders = await self._fetch_orders_with_pagination(
                symbol=None,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
                limit=100,
            )
            stats['fetched'] = len(orders)

            for order in orders:
                order_record = self._convert_order_to_db_model(order)

                existing_stmt = select(OKXOrder.id).where(
                    and_(
                        OKXOrder.ord_id == order_record['ord_id'],
                        OKXOrder.u_time == order_record['u_time'],
                    )
                ).limit(1)
                existing_row = await session.execute(existing_stmt)
                has_same_event = existing_row.scalar_one_or_none() is not None

                stmt = insert(OKXOrder).values(**order_record)
                stmt = stmt.on_conflict_do_update(
                    constraint='uq_okx_order_id_time',
                    set_={
                        'state': stmt.excluded.state,
                        'acc_fill_sz': stmt.excluded.acc_fill_sz,
                        'avg_px': stmt.excluded.avg_px,
                        'fill_sz': stmt.excluded.fill_sz,
                        'fill_px': stmt.excluded.fill_px,
                        'fill_time': stmt.excluded.fill_time,
                        'raw_data': stmt.excluded.raw_data,
                    }
                )
                result = await session.execute(stmt)

                if result.rowcount > 0:
                    if has_same_event:
                        stats['updated'] += 1
                    else:
                        stats['inserted'] += 1

        except Exception as e:
            logger.error(
                "Failed to reconcile orders",
                error=str(e),
                exc_info=True,
            )
            raise

        return stats

    async def reconcile_trades(self, session: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """对账 OKX 成交数据.

        Args:
            session: 数据库会话
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息: {'fetched': N, 'inserted': M, 'skipped': K}
        """
        stats = {'fetched': 0, 'inserted': 0, 'skipped': 0}

        # 转换为毫秒时间戳
        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        try:
            trades = await self._fetch_trades_with_pagination(
                symbol=None,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
                limit=100,
            )
            stats['fetched'] = len(trades)

            for trade in trades:
                trade_record = self._convert_trade_to_db_model(trade)

                stmt = insert(OKXTrade).values(**trade_record)
                stmt = stmt.on_conflict_do_nothing(constraint='uq_okx_trade_id')
                result = await session.execute(stmt)

                if result.rowcount > 0:
                    stats['inserted'] += 1
                else:
                    stats['skipped'] += 1

        except Exception as e:
            logger.error(
                "Failed to reconcile trades",
                error=str(e),
                exc_info=True,
            )
            raise

        return stats

    def _convert_order_to_db_model(self, order: dict) -> dict:
        """将 REST API 订单转换为数据库模型.

        Args:
            order: REST API 返回的订单数据

        Returns:
            数据库模型字典
        """
        # OKX REST API 订单字段参考：
        # https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-order-history-last-7-days

        def safe_decimal(value, default="0"):
            if value is None or value == '':
                return None
            return Decimal(str(value))

        def safe_datetime(value):
            if value is None or value == '':
                return None
            return datetime.fromtimestamp(int(value) / 1000)

        return {
            'inst_id': order['instId'],
            'inst_type': order.get('instType'),
            'ord_id': order['ordId'],
            'cl_ord_id': order.get('clOrdId'),
            'ord_type': order['ordType'],
            'side': order['side'],
            'pos_side': order.get('posSide'),
            'sz': safe_decimal(order['sz']),
            'px': safe_decimal(order.get('px')),
            'avg_px': safe_decimal(order.get('avgPx')),
            'acc_fill_sz': safe_decimal(order.get('accFillSz')),
            'fill_sz': safe_decimal(order.get('fillSz')),
            'fill_px': safe_decimal(order.get('fillPx')),
            'state': order['state'],
            'fee': safe_decimal(order.get('fee')),
            'fee_ccy': order.get('feeCcy'),
            'rebate': safe_decimal(order.get('rebate')),
            'rebate_ccy': order.get('rebateCcy'),
            'c_time': safe_datetime(order.get('cTime')),
            'u_time': safe_datetime(order['uTime']),
            'fill_time': safe_datetime(order.get('fillTime')),
            'reduce_only': order.get('reduceOnly') == 'true',
            'td_mode': order.get('tdMode'),
            'raw_data': dumps_with_decimal(order),
        }

    def _convert_trade_to_db_model(self, trade: dict) -> dict:
        """将 REST API 成交转换为数据库模型.

        Args:
            trade: REST API 返回的成交数据

        Returns:
            数据库模型字典
        """
        # OKX REST API 成交字段参考：
        # https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-transaction-details-last-3-months

        def safe_decimal(value, default="0"):
            if value is None or value == '':
                return None
            return Decimal(str(value))

        def safe_datetime(value):
            if value is None or value == '':
                return None
            return datetime.fromtimestamp(int(value) / 1000)

        return {
            'inst_id': trade['instId'],
            'ord_id': trade['ordId'],
            'trade_id': trade['tradeId'],
            'side': trade['side'],
            'fill_px': safe_decimal(trade['fillPx']),
            'fill_sz': safe_decimal(trade['fillSz']),
            'fee': safe_decimal(trade.get('fee')),
            'fee_ccy': trade.get('feeCcy'),
            'fill_time': safe_datetime(trade['ts']),
            'raw_data': dumps_with_decimal(trade),
        }
