"""Binance 订单和成交数据对账服务."""

from datetime import datetime
from typing import Dict, List
from decimal import Decimal
import json

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from rich.console import Console
from rich.table import Table

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.binance_perp import BinancePerpExchange
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.models import OrderUpdate, TradeUpdate
from tri_arb.services.reconciliation import BaseReconciliationService
from tri_arb.utils.json_utils import dumps_with_decimal

logger = get_logger(__name__)
console = Console()


class BinanceReconciliationService(BaseReconciliationService):
    """Binance 对账服务.

    定期从 Binance REST API 拉取订单和成交数据，与数据库对比并补全缺失数据。
    """

    def __init__(
        self,
        exchange: BinancePerpExchange,
        db_manager: DatabaseManager,
        poll_interval: int = 60,
        lookback_window: int = 600,
    ):
        """初始化 Binance 对账服务.

        Args:
            exchange: Binance 交易所 adapter
            db_manager: 数据库管理器
            poll_interval: 轮询间隔（秒）
            lookback_window: 回溯窗口（秒）
        """
        super().__init__(exchange, db_manager, poll_interval, lookback_window)
        logger.info("Binance reconciliation service initialized (auto-discover symbols)")

    @property
    def exchange_name(self) -> str:
        return "binance_perp"

    async def reconcile_orders(self, session: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """对账 Binance 订单数据.

        查询当前所有挂单并与数据库对比，确保数据库状态与实际挂单一致。

        Args:
            session: 数据库会话
            start_time: 开始时间（未使用，保留接口兼容）
            end_time: 结束时间（未使用，保留接口兼容）

        Returns:
            统计信息: {'fetched': N, 'inserted': M, 'updated': K}
        """
        stats = {'fetched': 0, 'inserted': 0, 'updated': 0}

        try:
            # 1. 查询当前所有挂单
            open_orders = await self.exchange.get_open_orders()
            stats['fetched'] = len(open_orders)

            if open_orders:
                table = Table(title="Binance 当前挂单 (前5条)", show_edge=False, box=None)
                table.add_column("订单ID", justify="right")
                table.add_column("交易对", justify="left")
                table.add_column("方向", justify="left")
                table.add_column("状态", justify="left")
                table.add_column("委托价", justify="right")
                table.add_column("成交量", justify="right")

                for order in open_orders[:5]:
                    table.add_row(
                        str(order.get('orderId')),
                        order.get('symbol', ''),
                        order.get('side', ''),
                        order.get('status', ''),
                        str(order.get('price')),
                        str(order.get('executedQty')),
                    )

                console.print(table)

            logger.debug(f"Fetched {len(open_orders)} open orders from API")

            # 2. 获取所有当前挂单的 order_id
            api_order_ids = {order['orderId'] for order in open_orders}

            # 3. 查询数据库中所有未完成的订单
            db_result = await session.execute(
                select(OrderUpdate).where(
                    and_(
                        OrderUpdate.exchange == 'binance_perp',
                        OrderUpdate.order_status.in_(['NEW', 'PARTIALLY_FILLED'])
                    )
                )
            )
            db_open_orders_dict = {order.order_id: order for order in db_result.scalars()}

            logger.debug(f"Found {len(db_open_orders_dict)} open orders in database")

            # 4. 处理 API 中的订单（插入或更新）
            for order in open_orders:
                async with session.begin_nested():
                    try:
                        order_record = self._convert_order_to_db_model(order)

                        stmt = insert(OrderUpdate).values(**order_record)
                        stmt = stmt.on_conflict_do_update(
                            constraint='uq_order_update_event',
                            set_={
                                'order_status': stmt.excluded.order_status,
                                'cumulative_filled_quantity': stmt.excluded.cumulative_filled_quantity,
                                'average_price': stmt.excluded.average_price,
                                'raw_data': stmt.excluded.raw_data,
                            }
                        )
                        result = await session.execute(stmt)

                        if result.rowcount > 0:
                            if order['orderId'] in db_open_orders_dict:
                                stats['updated'] += 1
                            else:
                                stats['inserted'] += 1

                    except Exception as e:
                        logger.error(
                            "Failed to insert/update order",
                            order_id=order.get('orderId'),
                            symbol=order.get('symbol'),
                            error=str(e),
                            exc_info=True,
                        )

            # 5. 处理数据库中有但 API 中没有的订单（可能已完成或取消）
            missing_order_ids = set(db_open_orders_dict.keys()) - api_order_ids

            if missing_order_ids:
                logger.debug(f"Found {len(missing_order_ids)} orders in DB but not in API, querying history")

                # 按交易对分组查询
                symbols_to_query = {}
                for order_id in missing_order_ids:
                    db_order = db_open_orders_dict[order_id]
                    if db_order.symbol not in symbols_to_query:
                        symbols_to_query[db_order.symbol] = []
                    symbols_to_query[db_order.symbol].append(order_id)

                # 查询每个交易对的历史订单
                for symbol, order_ids in symbols_to_query.items():
                    async with session.begin_nested():
                        try:
                            # 查询最近的订单历史
                            historical_orders = await self.exchange.get_all_orders(
                                symbol=symbol,
                                limit=100,
                            )

                            # 查找对应的订单并更新状态
                            for historical_order in historical_orders:
                                if historical_order['orderId'] in order_ids:
                                    order_record = self._convert_order_to_db_model(historical_order)

                                    stmt = insert(OrderUpdate).values(**order_record)
                                    stmt = stmt.on_conflict_do_update(
                                        constraint='uq_order_update_event',
                                        set_={
                                            'order_status': stmt.excluded.order_status,
                                            'cumulative_filled_quantity': stmt.excluded.cumulative_filled_quantity,
                                            'average_price': stmt.excluded.average_price,
                                            'raw_data': stmt.excluded.raw_data,
                                        }
                                    )
                                    await session.execute(stmt)
                                    stats['updated'] += 1

                                    logger.debug(
                                        "Updated completed/cancelled order",
                                        order_id=historical_order['orderId'],
                                        status=historical_order['status'],
                                    )

                        except Exception as e:
                            logger.error(
                                "Failed to query historical orders",
                                symbol=symbol,
                                error=str(e),
                                exc_info=True,
                            )

        except Exception as e:
            logger.error(
                "Failed to reconcile orders",
                error=str(e),
                exc_info=True,
            )
            raise

        return stats

    async def reconcile_trades(self, session: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """对账 Binance 成交数据.

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
            # 从数据库获取最近活跃的交易对
            symbols = await self._get_active_symbols(session, start_time)

            if not symbols:
                logger.debug("No active symbols found, skipping reconciliation")
                return stats

            for symbol in symbols:
                # 使用 savepoint 隔离每个 symbol 的失败
                async with session.begin_nested():
                    try:
                        # 从 REST API 获取成交
                        trades = await self.exchange.get_user_trades(
                            symbol=symbol,
                            start_time=start_ms,
                            end_time=end_ms,
                            limit=1000,
                        )
                        stats['fetched'] += len(trades)

                        if trades:
                            trade_table = Table(title=f"Binance {symbol} 成交对账 (前5条)", show_edge=False, box=None)
                            trade_table.add_column("成交ID", justify="right")
                            trade_table.add_column("方向", justify="left")
                            trade_table.add_column("价格", justify="right")
                            trade_table.add_column("数量", justify="right")
                            trade_table.add_column("时间", justify="left")

                            for trade in trades[:5]:
                                trade_table.add_row(
                                    str(trade.get('id')),
                                    trade.get('side', ''),
                                    str(trade.get('price')),
                                    str(trade.get('qty')),
                                    datetime.fromtimestamp(trade.get('time', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                                )

                            console.print(trade_table)

                        for trade in trades:
                            # 转换为数据库模型
                            trade_record = self._convert_trade_to_db_model(trade)

                            # 使用 PostgreSQL INSERT ... ON CONFLICT DO NOTHING
                            # 成交记录不可变，只需插入
                            stmt = insert(TradeUpdate).values(**trade_record)
                            stmt = stmt.on_conflict_do_nothing(constraint='uq_trade_id')
                            result = await session.execute(stmt)

                            if result.rowcount > 0:
                                stats['inserted'] += 1
                            else:
                                stats['skipped'] += 1

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

    def _convert_order_to_db_model(self, order: dict) -> dict:
        """将 REST API 订单转换为数据库模型.

        Args:
            order: REST API 返回的订单数据

        Returns:
            数据库模型字典
        """
        # Binance REST API 订单字段参考：
        # https://binance-docs.github.io/apidocs/futures/en/#all-orders-user_data
        return {
            'exchange': 'binance_perp',
            'event_type': 'ORDER_TRADE_UPDATE',
            'event_time': datetime.fromtimestamp(order['updateTime'] / 1000),
            'transaction_time': datetime.fromtimestamp(order['updateTime'] / 1000),
            'symbol': order['symbol'],
            'client_order_id': order.get('clientOrderId'),
            'side': order['side'],  # BUY/SELL
            'order_type': order['type'],
            'time_in_force': order.get('timeInForce'),
            'original_quantity': Decimal(str(order['origQty'])),
            'original_price': Decimal(str(order['price'])) if order.get('price') else None,
            'average_price': Decimal(str(order['avgPrice'])) if order.get('avgPrice') and order['avgPrice'] != '0' else None,
            'order_status': order['status'],
            'order_id': int(order['orderId']),
            'last_filled_quantity': None,  # REST API 不提供单次成交量
            'cumulative_filled_quantity': Decimal(str(order['executedQty'])),
            'last_filled_price': None,
            'commission_amount': None,  # REST API 不提供手续费
            'commission_asset': None,
            'position_side': order.get('positionSide'),
            'is_reduce_only': order.get('reduceOnly', False),
            'raw_data': dumps_with_decimal(order),
        }

    def _convert_trade_to_db_model(self, trade: dict) -> dict:
        """将 REST API 成交转换为数据库模型.

        Args:
            trade: REST API 返回的成交数据

        Returns:
            数据库模型字典
        """
        # Binance REST API 成交字段参考：
        # https://binance-docs.github.io/apidocs/futures/en/#account-trade-list-user_data
        return {
            'exchange': 'binance_perp',
            'event_type': 'ORDER_TRADE_UPDATE',
            'event_time': datetime.fromtimestamp(trade['time'] / 1000),
            'transaction_time': datetime.fromtimestamp(trade['time'] / 1000),
            'symbol': trade['symbol'],
            'order_id': int(trade['orderId']),
            'trade_id': int(trade['id']),
            'side': trade['side'],
            'price': Decimal(str(trade['price'])),
            'quantity': Decimal(str(trade['qty'])),
            'quote_quantity': Decimal(str(trade['quoteQty'])),
            'commission': Decimal(str(trade['commission'])),
            'commission_asset': trade['commissionAsset'],
            'is_maker': trade['maker'],
            'position_side': trade.get('positionSide'),
            'raw_data': dumps_with_decimal(trade),
        }

    async def _get_active_symbols(self, session: AsyncSession, since: datetime) -> List[str]:
        """从数据库获取最近活跃的交易对.

        Args:
            session: 数据库会话
            since: 起始时间

        Returns:
            交易对列表
        """
        symbols: set[str] = set()

        # 查询最近有订单活动的交易对
        order_stmt = select(OrderUpdate.symbol).where(
            and_(
                OrderUpdate.exchange == 'binance_perp',
                OrderUpdate.event_time >= since,
            )
        ).distinct()
        order_result = await session.execute(order_stmt)
        symbols.update(row[0] for row in order_result.fetchall() if row[0])

        # 查询最近有成交活动的交易对
        trade_stmt = select(TradeUpdate.symbol).where(
            and_(
                TradeUpdate.exchange == 'binance_perp',
                TradeUpdate.event_time >= since,
            )
        ).distinct()
        trade_result = await session.execute(trade_stmt)
        symbols.update(row[0] for row in trade_result.fetchall() if row[0])
        if symbols:
            return sorted(symbols)

        # 如果数据库没有近期记录， fallback 到 REST 持仓接口获取当前活跃交易对
        try:
            positions = await self.exchange.get_positions()
            position_symbols = {pos.get('symbol') for pos in positions if pos.get('symbol')}
            if position_symbols:
                logger.info(
                    "Discovered Binance symbols from REST positions",
                    symbols=sorted(position_symbols),
                )
                pos_table = Table(title="Binance 持仓发现的交易对", show_edge=False, box=None)
                pos_table.add_column("交易对", justify="left")
                pos_table.add_column("持仓量", justify="right")
                pos_table.add_column("未实现盈亏", justify="right")

                for pos in positions:
                    symbol = pos.get('symbol')
                    if symbol in position_symbols:
                        pos_table.add_row(
                            symbol,
                            str(pos.get('positionAmt')),
                            str(pos.get('unRealizedProfit')),
                        )

                console.print(pos_table)
                return sorted(position_symbols)
        except Exception as e:
            logger.warning(
                "Failed to fetch Binance positions while discovering symbols",
                error=str(e),
                exc_info=True,
            )

        logger.debug("No active Binance symbols found via DB or positions fallback")
        return []
