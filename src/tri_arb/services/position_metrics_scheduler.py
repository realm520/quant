"""持仓指标定时计算服务.

每5分钟计算一次持仓和交易指标，并存储到数据库供 Grafana 可视化。
"""

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.position_metrics_models import PositionMetrics

logger = get_logger(__name__)


class PositionMetricsScheduler:
    """持仓指标定时计算服务.
    
    每5分钟计算一次持仓和交易指标，并存储到数据库。
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        config_path: str = "config/accounts.json",
        interval_minutes: int = 5,
    ):
        """初始化持仓指标定时计算服务.
        
        Args:
            db_manager: 数据库管理器
            config_path: 账号配置文件路径
            interval_minutes: 计算间隔（分钟），默认5分钟
        """
        self.db_manager = db_manager
        self.config_path = config_path
        self.interval_minutes = interval_minutes
        self.interval_seconds = interval_minutes * 60
        
        # 合约乘数服务
        self.contract_multiplier_service: Optional[ContractMultiplierService] = None
        
        # 运行状态
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        logger.info(
            "持仓指标定时计算服务初始化",
            interval_minutes=interval_minutes,
        )
    
    async def start(self):
        """启动定时计算服务."""
        if self._running:
            logger.warning("定时计算服务已在运行")
            return
        
        # 初始化合约乘数服务
        await self._init_contract_multiplier_service()
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("持仓指标定时计算服务已启动")
    
    async def stop(self):
        """停止定时计算服务."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("持仓指标定时计算服务已停止")
    
    async def _init_contract_multiplier_service(self):
        """初始化合约乘数服务."""
        try:
            # 读取账号配置
            config_path = Path(self.config_path)
            if not config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}，将使用默认合约乘数")
                self.contract_multiplier_service = ContractMultiplierService()
                return
            
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
            
            # 提取 XT API 密钥（用于获取合约乘数）
            xt_accounts = config.get("accounts", {}).get("xt", [])
            xt_api_key = None
            xt_api_secret = None
            
            for account in xt_accounts:
                if account.get("api_key") and account.get("api_secret"):
                    xt_api_key = account.get("api_key")
                    xt_api_secret = account.get("api_secret")
                    break
            
            # 创建 XTPerpExchange 实例（如果需要）
            xt_exchange = None
            if xt_api_key and xt_api_secret:
                try:
                    xt_exchange = XTPerpExchange(
                        api_key=xt_api_key,
                        api_secret=xt_api_secret,
                    )
                    logger.info("XTPerpExchange 已创建，用于获取合约乘数")
                except Exception as e:
                    logger.warning(f"创建 XTPerpExchange 失败: {e}，将使用默认合约乘数")
            
            self.contract_multiplier_service = ContractMultiplierService(
                xt_exchange=xt_exchange,
            )
            logger.info("合约乘数服务已初始化")
        
        except Exception as e:
            logger.error(f"初始化合约乘数服务失败: {e}", exc_info=True)
            self.contract_multiplier_service = ContractMultiplierService()
    
    async def _run_loop(self):
        """运行定时计算循环."""
        while self._running:
            try:
                # 计算并存储指标
                await self._calculate_and_store_metrics()
                
                # 等待下一个周期
                await asyncio.sleep(self.interval_seconds)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"定时计算出错: {e}", exc_info=True)
                # 出错后等待一段时间再继续
                await asyncio.sleep(60)
    
    async def _calculate_and_store_metrics(self):
        """计算并存储指标."""
        try:
            # 读取账号配置
            config_path = Path(self.config_path)
            if not config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}")
                return
            
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
            
            accounts = config.get("accounts", {})
            
            # 计算今日 UTC 区间
            today = datetime.utcnow().date()
            start_time = datetime(today.year, today.month, today.day)  # 今日 00:00 UTC
            end_time = datetime.utcnow()  # 当前 UTC
            
            # 计算昨日 UTC 区间（用于获取昨收持仓）
            yesterday = today - timedelta(days=1)
            yesterday_start = datetime(yesterday.year, yesterday.month, yesterday.day)  # 昨日 00:00 UTC
            yesterday_end = datetime(today.year, today.month, today.day)  # 昨日 24:00 UTC
            
            async with self.db_manager.session() as session:
                # 遍历所有账号
                for exchange_name, account_list in accounts.items():
                    if exchange_name not in ["binance", "xt"]:
                        continue
                    
                    for account_config in account_list:
                        account_id = account_config.get("account_id")
                        if not account_id:
                            continue
                        
                        try:
                            # 创建计算器
                            calc = PositionCalculator(
                                session,
                                exchange=exchange_name,
                                account_id=account_id,
                                contract_multiplier_getter=self.contract_multiplier_service.get_contract_multiplier if self.contract_multiplier_service else None,
                            )
                            
                            # 计算昨日数据（用于获取昨收持仓）
                            yesterday_metrics = await calc.calculate_positions_by_symbol(
                                start_time=yesterday_start,
                                end_time=yesterday_end,
                            )
                            
                            # 计算今日数据
                            today_metrics = await calc.calculate_positions_by_symbol(
                                start_time=start_time,
                                end_time=end_time,
                            )
                            
                            # 存储每个交易对的指标
                            for symbol_key, m in today_metrics.items():
                                if symbol_key == "TOTAL":
                                    continue
                                
                                # 获取昨日数据
                                yesterday_m = yesterday_metrics.get(symbol_key, {})
                                
                                # 从数据库计算累计 PnL（历史已实现盈亏总和 + 当前未实现盈亏）
                                current_unrealized_pnl = m.get("unrealized_pnl", Decimal("0"))
                                cumulative_pnl = await self._calculate_cumulative_pnl_from_db(
                                    session=session,
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol=symbol_key,
                                    current_unrealized_pnl=current_unrealized_pnl,
                                    end_time=end_time,
                                )
                                
                                # 创建指标记录
                                metrics_record = PositionMetrics(
                                    timestamp=end_time,
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol=symbol_key,
                                    
                                    # 1. 昨收持仓（使用昨日的数据）
                                    pre_long_qty=yesterday_m.get("pre_long_qty", Decimal("0")),
                                    pre_short_qty=yesterday_m.get("pre_short_qty", Decimal("0")),
                                    pre_long_value=yesterday_m.get("pre_long_value", Decimal("0")),
                                    pre_short_value=yesterday_m.get("pre_short_value", Decimal("0")),
                                    
                                    # 2. 今日交易
                                    long_qty=m.get("long_qty", Decimal("0")),
                                    short_qty=m.get("short_qty", Decimal("0")),
                                    long_value=m.get("long_value", Decimal("0")),
                                    short_value=m.get("short_value", Decimal("0")),
                                    avg_buy_prz=m.get("avg_buy_prz", Decimal("0")),
                                    avg_sell_prz=m.get("avg_sell_prz", Decimal("0")),
                                    
                                    # 3. 已实现 Pnl
                                    matched_qty=m.get("matched_qty", Decimal("0")),
                                    realized_pnl=m.get("realized_pnl", Decimal("0")),
                                    
                                    # 4. 当日剩余仓位
                                    left_long_qty=m.get("left_long_qty", Decimal("0")),
                                    left_short_qty=m.get("left_short_qty", Decimal("0")),
                                    left_long_value=m.get("left_long_value", Decimal("0")),
                                    left_short_value=m.get("left_short_value", Decimal("0")),
                                    close_prz=m.get("close_prz", Decimal("0")),
                                    unrealized_pnl=m.get("unrealized_pnl", Decimal("0")),
                                    
                                    # 5. Pnl 汇总
                                    daily_pnl=m.get("daily_pnl", Decimal("0")),
                                    cumulative_pnl=cumulative_pnl,
                                )
                                
                                session.add(metrics_record)
                            
                            await session.commit()
                            logger.info(
                                f"已计算并存储指标",
                                account_id=account_id,
                                exchange=exchange_name,
                                symbol_count=len([k for k in today_metrics.keys() if k != "TOTAL"]),
                            )
                        
                        except Exception as e:
                            logger.error(
                                f"计算账号指标失败",
                                account_id=account_id,
                                exchange=exchange_name,
                                error=str(e),
                                exc_info=True,
                            )
                            await session.rollback()
        
        except Exception as e:
            logger.error(f"计算指标失败: {e}", exc_info=True)
    
    async def _calculate_cumulative_pnl_from_db(
        self,
        session: AsyncSession,
        account_id: str,
        exchange: str,
        symbol: str,
        current_unrealized_pnl: Decimal,
        end_time: datetime,
    ) -> Decimal:
        """从数据库计算累计 PnL.
        
        计算逻辑：
        - 累计已实现盈亏 = 数据库中该账号/交易所/交易对的所有已实现盈亏总和
        - 累计 PnL = 累计已实现盈亏 + 当前未实现盈亏
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            exchange: 交易所
            symbol: 交易对
            current_unrealized_pnl: 当前未实现盈亏
            end_time: 当前时间（用于查询历史数据）
        
        Returns:
            累计 PnL
        """
        try:
            # 查询该账号/交易所/交易对的所有历史已实现盈亏总和
            query = (
                select(func.sum(PositionMetrics.realized_pnl))
                .where(PositionMetrics.account_id == account_id)
                .where(PositionMetrics.exchange == exchange)
                .where(PositionMetrics.symbol == symbol)
                .where(PositionMetrics.timestamp < end_time)  # 不包括当前记录
            )
            
            result = await session.execute(query)
            cumulative_realized_pnl = result.scalar() or Decimal("0")
            
            # 累计 PnL = 累计已实现盈亏 + 当前未实现盈亏
            cumulative_pnl = cumulative_realized_pnl + current_unrealized_pnl
            
            return cumulative_pnl
        
        except Exception as e:
            logger.error(
                f"从数据库计算累计 PnL 失败",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )
            # 如果查询失败，返回当前未实现盈亏（至少保证有值）
            return current_unrealized_pnl

