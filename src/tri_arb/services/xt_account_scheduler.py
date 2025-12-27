"""XT交易所账户定时任务服务.

定期获取XT交易所的现货账户、合约账户的资金和仓位数据，
并存储到PostgreSQL数据库中。
"""

import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.xt_spot import XTSpotExchange
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.models.perpetual import Position
from tri_arb.services.rest_data_service import RestDataService
from tri_arb.storage.database import DatabaseManager

logger = get_logger(__name__)


class XTAccountScheduler:
    """XT交易所账户定时任务服务.

    每10分钟获取一次账户余额和仓位数据，并存储到数据库。

    Attributes:
        api_key: XT API密钥（现货和合约共用）
        api_secret: XT API密钥（现货和合约共用）
        interval_minutes: 查询间隔（分钟），默认10分钟
        db_manager: 数据库管理器
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        db_manager: DatabaseManager,
        interval_minutes: int = 10,
    ):
        """初始化XT账户定时任务服务.

        Args:
            api_key: XT API密钥（现货和合约共用）
            api_secret: XT API密钥（现货和合约共用）
            db_manager: 数据库管理器
            interval_minutes: 查询间隔（分钟），默认10分钟
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.db_manager = db_manager
        self.interval_minutes = interval_minutes
        self.interval_seconds = interval_minutes * 60

        # 交易所实例
        self.spot_exchange: Optional[XTSpotExchange] = None
        self.perp_exchange: Optional[XTPerpExchange] = None

        # REST数据服务
        self.rest_service = RestDataService(db_manager)

        # 定时查询记录ID
        self.spot_balance_query_id: Optional[int] = None
        self.perp_balance_query_id: Optional[int] = None
        self.perp_position_query_id: Optional[int] = None

        # 运行状态
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(
            "XT账户定时任务服务初始化",
            interval_minutes=interval_minutes,
        )

    async def start(self):
        """启动定时任务服务."""
        if self._running:
            logger.warning("定时任务服务已在运行")
            return

        self._running = True

        # 初始化交易所连接
        try:
            # 初始化现货交易所（使用同一套API密钥）
            self.spot_exchange = XTSpotExchange(
                name="xt",
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            await self.spot_exchange.connect()
            logger.info("XT现货交易所连接成功")

            # 初始化合约交易所（使用同一套API密钥）
            self.perp_exchange = XTPerpExchange(
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            await self.perp_exchange.connect()
            logger.info("XT合约交易所连接成功")

        except Exception as e:
            logger.error("初始化交易所连接失败", error=str(e), exc_info=True)
            self._running = False
            raise

        # 创建定时查询记录
        try:
            self.spot_balance_query_id = await self.rest_service.start_scheduled_query(
                exchange="xt",
                query_type="balance",
                exchange_type="spot",
                interval_minutes=self.interval_minutes,
            )

            self.perp_balance_query_id = await self.rest_service.start_scheduled_query(
                exchange="xt",
                query_type="balance",
                exchange_type="perp",
                interval_minutes=self.interval_minutes,
            )

            self.perp_position_query_id = await self.rest_service.start_scheduled_query(
                exchange="xt",
                query_type="position",
                exchange_type="perp",
                interval_minutes=self.interval_minutes,
            )

            logger.info(
                "定时查询记录已创建",
                spot_balance_id=self.spot_balance_query_id,
                perp_balance_id=self.perp_balance_query_id,
                perp_position_id=self.perp_position_query_id,
            )
        except Exception as e:
            logger.error("创建定时查询记录失败", error=str(e), exc_info=True)
            # 继续执行，不影响定时任务启动

        # 启动定时任务循环
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("XT账户定时任务服务已启动")

    async def stop(self):
        """停止定时任务服务."""
        if not self._running:
            logger.warning("定时任务服务未运行")
            return

        self._running = False

        # 取消任务
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # 结束定时查询记录
        try:
            if self.spot_balance_query_id:
                await self.rest_service.end_scheduled_query(self.spot_balance_query_id)
            if self.perp_balance_query_id:
                await self.rest_service.end_scheduled_query(self.perp_balance_query_id)
            if self.perp_position_query_id:
                await self.rest_service.end_scheduled_query(self.perp_position_query_id)
        except Exception as e:
            logger.error("结束定时查询记录失败", error=str(e))

        # 断开交易所连接
        try:
            if self.spot_exchange:
                await self.spot_exchange.disconnect()
            if self.perp_exchange:
                await self.perp_exchange.disconnect()
        except Exception as e:
            logger.error("断开交易所连接失败", error=str(e))

        logger.info("XT账户定时任务服务已停止")

    async def _scheduler_loop(self):
        """定时任务循环."""
        logger.info("定时任务循环开始", interval_seconds=self.interval_seconds)

        while self._running:
            try:
                # 执行一次查询
                await self._fetch_all_accounts()

                # 等待下次执行
                if self._running:
                    logger.info(
                        "等待下次执行",
                        interval_seconds=self.interval_seconds,
                    )
                    await asyncio.sleep(self.interval_seconds)

            except asyncio.CancelledError:
                logger.info("定时任务循环被取消")
                break
            except Exception as e:
                logger.error(
                    "定时任务循环出错",
                    error=str(e),
                    exc_info=True,
                )
                # 出错后等待一段时间再重试
                if self._running:
                    await asyncio.sleep(self.interval_seconds)

        logger.info("定时任务循环结束")

    async def _fetch_all_accounts(self):
        """获取所有账户数据."""
        logger.info("开始获取XT账户数据")

        # 1. 获取现货账户余额
        try:
            await self._fetch_spot_balance()
        except Exception as e:
            logger.error("获取现货账户余额失败", error=str(e), exc_info=True)
            if self.spot_balance_query_id:
                await self.rest_service.update_scheduled_query_stats(
                    self.spot_balance_query_id,
                    success=False,
                    error_message=str(e),
                )

        # 2. 获取合约账户余额
        try:
            await self._fetch_perp_balance()
        except Exception as e:
            logger.error("获取合约账户余额失败", error=str(e), exc_info=True)
            if self.perp_balance_query_id:
                await self.rest_service.update_scheduled_query_stats(
                    self.perp_balance_query_id,
                    success=False,
                    error_message=str(e),
                )

        # 3. 获取合约账户仓位
        try:
            await self._fetch_perp_positions()
        except Exception as e:
            logger.error("获取合约账户仓位失败", error=str(e), exc_info=True)
            if self.perp_position_query_id:
                await self.rest_service.update_scheduled_query_stats(
                    self.perp_position_query_id,
                    success=False,
                    error_message=str(e),
                )

        logger.info("完成获取XT账户数据")

    async def _fetch_spot_balance(self):
        """获取现货账户余额."""
        if not self.spot_exchange:
            raise RuntimeError("现货交易所未初始化")

        logger.info("获取XT现货账户余额")

        # 调用API获取余额
        balances = await self.spot_exchange.get_balance()

        # 保存到数据库
        await self.rest_service.save_balance_query(
            exchange="xt",
            exchange_type="spot",
            balances_data=balances,
            query_type="scheduled",
        )

        # 更新统计信息
        if self.spot_balance_query_id:
            await self.rest_service.update_scheduled_query_stats(
                self.spot_balance_query_id,
                success=True,
            )

        logger.info(
            "XT现货账户余额已保存",
            currency_count=len(balances),
        )

    async def _fetch_perp_balance(self):
        """获取合约账户余额."""
        if not self.perp_exchange:
            raise RuntimeError("合约交易所未初始化")

        logger.info("获取XT合约账户余额")

        # 调用API获取余额
        balances = await self.perp_exchange.get_balance()

        # 转换为标准格式
        balances_data: dict[str, dict[str, Any]] = {}
        for currency, balance_info in balances.items():
            balances_data[currency] = {
                "available": str(balance_info.get("available", 0)),
                "frozen": str(balance_info.get("frozen", 0)),
                "total": str(balance_info.get("total", 0)),
            }

        # 保存到数据库
        await self.rest_service.save_balance_query(
            exchange="xt",
            exchange_type="perp",
            balances_data=balances_data,
            query_type="scheduled",
        )

        # 更新统计信息
        if self.perp_balance_query_id:
            await self.rest_service.update_scheduled_query_stats(
                self.perp_balance_query_id,
                success=True,
            )

        logger.info(
            "XT合约账户余额已保存",
            currency_count=len(balances_data),
        )

    async def _fetch_perp_positions(self):
        """获取合约账户仓位."""
        if not self.perp_exchange:
            raise RuntimeError("合约交易所未初始化")

        logger.info("获取XT合约账户仓位")

        # 调用API获取仓位
        positions = await self.perp_exchange.get_positions(symbol=None)

        # 转换为字典格式
        positions_data: list[dict[str, Any]] = []
        for pos in positions:
            if isinstance(pos, Position):
                # 转换为字典格式，兼容RestDataService
                pos_dict = {
                    "symbol": pos.symbol,
                    "positionSide": pos.side,
                    "positionAmt": str(pos.quantity),
                    "entryPrice": str(pos.entry_price),
                    "markPrice": str(pos.mark_price),
                    "unRealizedProfit": str(pos.unrealized_pnl),
                    "leverage": str(pos.leverage),
                    "margin": str(pos.margin),
                    "roe": str(pos.roe),
                    "liquidationPrice": str(pos.liquidation_price),
                }
                positions_data.append(pos_dict)
            else:
                # 如果已经是字典格式，直接使用
                positions_data.append(pos)

        # 保存到数据库
        await self.rest_service.save_positions_query(
            exchange="xt",
            exchange_type="perp",
            positions_data=positions_data,
            query_type="scheduled",
        )

        # 更新统计信息
        if self.perp_position_query_id:
            await self.rest_service.update_scheduled_query_stats(
                self.perp_position_query_id,
                success=True,
            )

        logger.info(
            "XT合约账户仓位已保存",
            position_count=len(positions_data),
        )
