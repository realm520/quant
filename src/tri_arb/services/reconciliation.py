"""订单和成交数据对账服务.

定期从 REST API 获取订单和成交历史，与数据库中的 WebSocket 数据对账，
确保数据完整性。使用 order_id + timestamp 作为唯一键，自动补全缺失数据。
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tri_arb.config.logging import get_logger
from tri_arb.storage.database import DatabaseManager

logger = get_logger(__name__)


class BaseReconciliationService(ABC):
    """对账服务基类.

    定期从 REST API 拉取订单和成交数据，与数据库对比并补全缺失数据。
    """

    def __init__(
        self,
        exchange_adapter: Any,
        db_manager: DatabaseManager,
        poll_interval: int = 60,  # 轮询间隔（秒）
        lookback_window: int = 600,  # 回溯窗口（秒，默认10分钟）
    ):
        """初始化对账服务.

        Args:
            exchange_adapter: 交易所 adapter（如 BinancePerpExchange）
            db_manager: 数据库管理器
            poll_interval: 轮询间隔（秒）
            lookback_window: 回溯窗口（秒）
        """
        self.exchange = exchange_adapter
        self.db_manager = db_manager
        self.poll_interval = poll_interval
        self.lookback_window = lookback_window
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(
            "Reconciliation service initialized",
            exchange=self.exchange_name,
            poll_interval=poll_interval,
            lookback_window=lookback_window,
        )

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """交易所名称（如 'binance_perp'）."""
        pass

    @abstractmethod
    async def reconcile_orders(self, session: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """对账订单数据.

        Args:
            session: 数据库会话
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息: {'fetched': N, 'inserted': M, 'updated': K}
        """
        pass

    @abstractmethod
    async def reconcile_trades(self, session: AsyncSession, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """对账成交数据.

        Args:
            session: 数据库会话
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            统计信息: {'fetched': N, 'inserted': M, 'skipped': K}
        """
        pass

    async def start(self):
        """启动对账服务."""
        if self._running:
            logger.warning("Reconciliation service already running", exchange=self.exchange_name)
            return

        self._running = True
        self._task = asyncio.create_task(self._reconciliation_loop())
        logger.info("Reconciliation service started", exchange=self.exchange_name)

    async def stop(self):
        """停止对账服务."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Reconciliation service stopped", exchange=self.exchange_name)

    async def _reconciliation_loop(self):
        """对账循环任务."""
        logger.info("Reconciliation loop started", exchange=self.exchange_name)

        while self._running:
            try:
                await self._run_reconciliation()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                logger.info("Reconciliation loop cancelled", exchange=self.exchange_name)
                break
            except Exception as e:
                logger.error(
                    "Error in reconciliation loop",
                    exchange=self.exchange_name,
                    error=str(e),
                    exc_info=True,
                )
                # 出错后等待一段时间再重试
                await asyncio.sleep(self.poll_interval)

    async def reconcile_once(self, lookback_seconds: Optional[int] = None):
        """执行一次对账（公共方法，供外部调用）.

        Args:
            lookback_seconds: 回溯窗口（秒），如果为 None 则使用实例的 lookback_window
        """
        await self._run_reconciliation(lookback_seconds)

    async def _run_reconciliation(self, lookback_seconds: Optional[int] = None):
        """执行一次对账."""
        end_time = datetime.utcnow()
        lookback = lookback_seconds if lookback_seconds is not None else self.lookback_window
        start_time = end_time - timedelta(seconds=lookback)

        logger.debug(
            "Starting reconciliation",
            exchange=self.exchange_name,
            start_time=start_time,
            end_time=end_time,
        )

        async with self.db_manager.session() as session:
            try:
                # 对账订单
                order_stats = await self.reconcile_orders(session, start_time, end_time)
                logger.info(
                    "Order reconciliation completed",
                    exchange=self.exchange_name,
                    **order_stats,
                )

                # 对账成交
                trade_stats = await self.reconcile_trades(session, start_time, end_time)
                logger.info(
                    "Trade reconciliation completed",
                    exchange=self.exchange_name,
                    **trade_stats,
                )

                await session.commit()

            except Exception as e:
                logger.error(
                    "Reconciliation failed",
                    exchange=self.exchange_name,
                    error=str(e),
                    exc_info=True,
                )
                await session.rollback()
                raise
