"""持仓指标定时计算服务.

每5分钟计算一次持仓和交易指标，并存储到数据库供 Grafana 可视化。
"""

import asyncio
import json
from datetime import datetime, timedelta, date
from decimal import Decimal
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from prometheus_client import Gauge
from rich.console import Console
from rich.table import Table

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.xt_perp import XTPerpExchange
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.position_metrics_models import PositionMetrics
from typing import List, Tuple

logger = get_logger(__name__)
# 使用标准输出流，确保表格能在控制台正确显示
console = Console(file=None)  # file=None 表示使用 sys.stdout

# Prometheus metrics for position metrics
position_pre_long_qty = Gauge(
    "position_pre_long_qty",
    "昨日多头持仓量",
    ["account_id", "exchange", "symbol"],
)

position_pre_short_qty = Gauge(
    "position_pre_short_qty",
    "昨日空头持仓量",
    ["account_id", "exchange", "symbol"],
)

position_pre_long_value = Gauge(
    "position_pre_long_value",
    "昨日多头市值",
    ["account_id", "exchange", "symbol"],
)

position_pre_short_value = Gauge(
    "position_pre_short_value",
    "昨日空头市值",
    ["account_id", "exchange", "symbol"],
)

position_long_qty = Gauge(
    "position_long_qty",
    "多头交易量",
    ["account_id", "exchange", "symbol"],
)

position_short_qty = Gauge(
    "position_short_qty",
    "空头交易量",
    ["account_id", "exchange", "symbol"],
)

position_long_value = Gauge(
    "position_long_value",
    "多头市值",
    ["account_id", "exchange", "symbol"],
)

position_short_value = Gauge(
    "position_short_value",
    "空头市值",
    ["account_id", "exchange", "symbol"],
)

position_avg_buy_prz = Gauge(
    "position_avg_buy_prz",
    "买入平均价格",
    ["account_id", "exchange", "symbol"],
)

position_avg_sell_prz = Gauge(
    "position_avg_sell_prz",
    "卖出平均价格",
    ["account_id", "exchange", "symbol"],
)

position_matched_qty = Gauge(
    "position_matched_qty",
    "轧差数量",
    ["account_id", "exchange", "symbol"],
)

position_realized_pnl = Gauge(
    "position_realized_pnl",
    "当日已实现盈亏",
    ["account_id", "exchange", "symbol"],
)

position_left_long_qty = Gauge(
    "position_left_long_qty",
    "多头剩余持仓",
    ["account_id", "exchange", "symbol"],
)

position_left_short_qty = Gauge(
    "position_left_short_qty",
    "空头剩余持仓",
    ["account_id", "exchange", "symbol"],
)

position_left_long_value = Gauge(
    "position_left_long_value",
    "多头剩余市值",
    ["account_id", "exchange", "symbol"],
)

position_left_short_value = Gauge(
    "position_left_short_value",
    "空头剩余市值",
    ["account_id", "exchange", "symbol"],
)

position_close_prz = Gauge(
    "position_close_prz",
    "当日最后一笔成交价",
    ["account_id", "exchange", "symbol"],
)

position_unrealized_pnl = Gauge(
    "position_unrealized_pnl",
    "当日未实现盈亏",
    ["account_id", "exchange", "symbol"],
)

position_daily_pnl = Gauge(
    "position_daily_pnl",
    "单日 PnL",
    ["account_id", "exchange", "symbol"],
)

position_cumulative_pnl = Gauge(
    "position_cumulative_pnl",
    "累计 PnL",
    ["account_id", "exchange", "symbol"],
)


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
        # 启动时立即执行一次计算
        try:
            await self._calculate_and_store_metrics()
        except Exception as e:
            logger.error(f"启动时计算指标失败: {e}", exc_info=True)
        
        # 然后按间隔循环执行
        while self._running:
            try:
                # 等待下一个周期
                await asyncio.sleep(self.interval_seconds)
                
                # 计算并存储指标
                await self._calculate_and_store_metrics()
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"定时计算出错: {e}", exc_info=True)
                # 出错后等待一段时间再继续
                await asyncio.sleep(60)
    
    async def _calculate_and_store_metrics(self):
        """计算并存储指标."""
        try:
            logger.info("开始计算持仓指标...")
            # 读取账号配置
            config_path = Path(self.config_path)
            if not config_path.exists():
                logger.warning(f"配置文件不存在: {self.config_path}")
                return
            
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
            
            accounts = config.get("accounts", {})
            logger.info(f"找到 {len(accounts)} 个账号配置")
            
            # 按交易所分组账号
            accounts_by_exchange: Dict[str, list] = {"binance": [], "xt": []}
            
            for account_id, account_config in accounts.items():
                if not isinstance(account_config, dict):
                    logger.warning(f"账号配置不是字典类型: {account_id} - {type(account_config)}")
                    continue
                
                exchange_name = account_config.get("exchange", "").lower()
                if exchange_name not in ["binance", "xt"]:
                    logger.debug(f"跳过账号 {account_id}: 交易所 {exchange_name} 不在支持列表中")
                    continue
                
                enabled = account_config.get("enabled", True)
                if not enabled:
                    logger.debug(f"账号 {account_id} 未启用，跳过")
                    continue
                
                # 添加 account_id 到配置中（如果还没有）
                account_config_with_id = account_config.copy()
                account_config_with_id["account_id"] = account_id
                accounts_by_exchange[exchange_name].append(account_config_with_id)
            
            # 统计信息
            binance_count = len(accounts_by_exchange["binance"])
            xt_count = len(accounts_by_exchange["xt"])
            logger.info(f"Binance 账号数: {binance_count}, XT 账号数: {xt_count}")
            
            if binance_count == 0 and xt_count == 0:
                logger.warning("没有找到启用的 binance 或 xt 账号，跳过计算")
                return
            
            # 计算今日 UTC 区间
            today = datetime.utcnow().date()
            start_time = datetime(today.year, today.month, today.day)  # 今日 00:00 UTC
            end_time = datetime.utcnow()  # 当前 UTC
            
            # 计算昨日 UTC 区间（用于获取昨收持仓）
            yesterday = today - timedelta(days=1)
            yesterday_start = datetime(yesterday.year, yesterday.month, yesterday.day)  # 昨日 00:00 UTC
            yesterday_end = datetime(today.year, today.month, today.day)  # 昨日 24:00 UTC
            
            # 检查是否换日（如果当前时间已经跨过今天 00:00，需要计算今天零点快照）
            # 这个检查在每次定时任务运行时都会执行，如果发现今天零点快照不存在，会自动重建
            
            async with self.db_manager.session() as session:
                # 遍历所有交易所
                for exchange_name in ["binance", "xt"]:
                    account_list = accounts_by_exchange[exchange_name]
                    if not account_list:
                        continue
                    
                    logger.info(f"处理交易所: {exchange_name}, 账号数: {len(account_list)}")
                    
                    for account_config in account_list:
                        account_id = account_config.get("account_id")
                        if not account_id:
                            logger.warning(f"账号配置缺少 account_id: {account_config}")
                            continue
                        
                        logger.info(f"计算账号指标: {account_id} ({exchange_name})")
                        
                        try:
                            # 创建合约乘数 getter（使用同步方法）
                            contract_multiplier_getter: Optional[Callable[[str], Decimal]] = None
                            if self.contract_multiplier_service:
                                # 使用同步方法，直接调用公开 API（不需要 API key）
                                service = self.contract_multiplier_service
                                exchange = exchange_name
                                
                                # 使用闭包捕获 service 和 exchange
                                def sync_getter(symbol: str) -> Decimal:
                                    """同步获取合约乘数."""
                                    return service.get_multiplier_sync(exchange, symbol)
                                
                                contract_multiplier_getter = sync_getter
                            
                            # 创建计算器
                            calc = PositionCalculator(
                                session,
                                exchange=exchange_name,
                                account_id=account_id,
                                contract_multiplier_getter=contract_multiplier_getter,
                            )
                            
                            # 每次启动/运行都重建所有零点快照（覆盖写入）
                            logger.info(
                                f"重建账号所有零点快照",
                                account_id=account_id,
                                exchange=exchange_name,
                            )
                            await self._rebuild_midnight_snapshots(
                                session=session,
                                calc=calc,
                                account_id=account_id,
                                exchange=exchange_name,
                                symbol=None,  # 所有 symbol
                            )
                            
                            # 获取昨日开始时的初始持仓（从 position_metrics 表读取）
                            initial_positions_yesterday = await self._get_or_calculate_daily_initial_positions(
                                session=session,
                                calc=calc,
                                account_id=account_id,
                                exchange=exchange_name,
                                target_date=yesterday_start.date(),  # 昨天的日期
                            )
                            
                            # 计算昨日数据（用于获取昨收持仓，用于显示）
                            yesterday_metrics = await calc.calculate_yesterday_end_left_qty_value(
                                start_time=yesterday_start,
                                end_time=yesterday_end,
                                initial_positions_dict=initial_positions_yesterday if initial_positions_yesterday else None,
                            )
                            
                            # 检查今天零点快照是否存在，如果不存在则计算并写入
                            today_midnight = datetime.combine(start_time.date(), datetime.min.time()).replace(tzinfo=None)
                            today_snapshot_query = (
                                select(PositionMetrics)
                                .where(PositionMetrics.account_id == account_id)
                                .where(PositionMetrics.exchange == exchange_name)
                                .where(PositionMetrics.timestamp == today_midnight)
                                .limit(1)
                            )
                            today_snapshot_result = await session.execute(today_snapshot_query)
                            today_snapshot = today_snapshot_result.scalar_one_or_none()
                            
                            if not today_snapshot:
                                # 今天零点快照不存在，需要计算并写入
                                # 使用昨天收盘持仓 + 今天成交来计算今天零点快照
                                logger.info(
                                    f"计算并写入今天零点快照",
                                    account_id=account_id,
                                    exchange=exchange_name,
                                )
                                # 这里可以调用 _rebuild_midnight_snapshots 只重建到今天，或者单独计算今天
                                # 为了简化，我们直接调用一次重建（会覆盖所有，但确保今天有数据）
                                await self._rebuild_midnight_snapshots(
                                    session=session,
                                    calc=calc,
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol=None,
                                )
                            
                            # 构建今日初始持仓（从昨日剩余持仓获取）
                            yesterday_left_qty_value_dict = {}
                            for symbol_key, yesterday_m in yesterday_metrics.items():
                                if symbol_key == "TOTAL":
                                    continue
                                yesterday_left_qty_value_dict[symbol_key] = {
                                    # 作为今日初始持仓传入 PositionCalculator
                                    "initial_long_qty": yesterday_m.get("left_long_qty", Decimal("0")),
                                    "initial_short_qty": yesterday_m.get("left_short_qty", Decimal("0")),
                                    "initial_long_value": yesterday_m.get("left_long_value", Decimal("0")),
                                    "initial_short_value": yesterday_m.get("left_short_value", Decimal("0")),
                                }
                            
                            # 计算今日数据（使用昨日剩余持仓作为初始持仓）
                            logger.debug(f"计算今日数据: {start_time} -> {end_time}")
                            today_metrics = await calc.calculate_positions_by_symbol(
                                start_time=start_time,
                                end_time=end_time,
                                initial_positions_dict=yesterday_left_qty_value_dict if yesterday_left_qty_value_dict else None,
                            )
                            
                            symbol_count = len([k for k in today_metrics.keys() if k != "TOTAL"])
                            logger.info(f"账号 {account_id} 找到 {symbol_count} 个交易对")
                            
                            if symbol_count ==  0:
                                logger.warning(f"账号 {account_id} 没有找到交易对数据，跳过")
                                continue
                            
                            # 存储每个交易对的指标
                            for symbol_key, m in today_metrics.items():
                                if symbol_key == "TOTAL":
                                    continue
                                
                                # 获取昨日数据
                                yesterday_m = yesterday_metrics.get(symbol_key, {})
                                
                                # 使用 PositionCalculator 计算的未实现盈亏（基于平均价格和剩余持仓）
                                # 计算逻辑：
                                # - long_qty = sum(buy_vol) + pre_long_qty
                                # - short_qty = sum(sell_vol) + pre_short_qty
                                # - long_value = sum(buy_vol * buy_price) + pre_long_value
                                # - short_value = sum(sell_vol * sell_price) + pre_short_value
                                # - avg_buy_prz = long_value / long_qty
                                # - avg_sell_prz = short_value / short_qty
                                # - matched_qty = min(long_qty, short_qty)
                                # - left_long_qty = long_qty - matched_qty
                                # - left_short_qty = short_qty - matched_qty
                                # - unrealized_pnl = left_long_qty * (close_prz - avg_buy_prz) + left_short_qty * (avg_sell_prz - close_prz)
                                today_unrealized_pnl = m.get("unrealized_pnl", Decimal("0"))
                                
                                # 计算今日新增的已实现盈亏（仅今日新增的轧差对应的已实现盈亏）
                                # 今日总轧差 = 包含初始持仓的轧差
                                total_matched_qty = m.get("matched_qty", Decimal("0"))
                                # 昨日收盘时的轧差（如果昨日有数据）
                                yesterday_matched_qty = yesterday_m.get("matched_qty", Decimal("0"))
                                # 今日新增的轧差数量 = 今日总轧差 - 昨日收盘时的轧差
                                daily_new_matched_qty = total_matched_qty - yesterday_matched_qty
                                
                                # 计算今日新增的已实现盈亏
                                avg_buy_prz = m.get("avg_buy_prz", Decimal("0"))
                                avg_sell_prz = m.get("avg_sell_prz", Decimal("0"))
                                today_realized_pnl = Decimal("0")
                                if daily_new_matched_qty > 0 and avg_sell_prz > 0 and avg_buy_prz > 0:
                                    today_realized_pnl = daily_new_matched_qty * (avg_sell_prz - avg_buy_prz)
                                
                                # 从 position_metrics 表读取今天零点快照的 cumulative_realized_pnl
                                today_midnight = datetime.combine(start_time.date(), datetime.min.time()).replace(tzinfo=None)
                                midnight_snapshot_query = (
                                    select(PositionMetrics.cumulative_realized_pnl)
                                    .where(PositionMetrics.account_id == account_id)
                                    .where(PositionMetrics.exchange == exchange_name)
                                    .where(PositionMetrics.symbol == symbol_key)
                                    .where(PositionMetrics.timestamp == today_midnight)
                                    .limit(1)
                                )
                                midnight_result = await session.execute(midnight_snapshot_query)
                                cumulative_realized_pnl_at_midnight = midnight_result.scalar()
                                
                                if cumulative_realized_pnl_at_midnight is None:
                                    # 如果今天零点快照不存在，使用 0（理论上不应该发生，因为前面已经重建了）
                                    logger.warning(
                                        f"今天零点快照不存在，使用 0 作为累积已实现盈亏",
                                        account_id=account_id,
                                        exchange=exchange_name,
                                        symbol=symbol_key,
                                    )
                                    cumulative_realized_pnl_at_midnight = Decimal("0")
                                
                                # 当前时刻的累积已实现盈亏 = 零点快照的累积已实现 + 今日新增的已实现
                                cumulative_realized_pnl_now = cumulative_realized_pnl_at_midnight + today_realized_pnl
                                
                                # 累计 PnL = 累积已实现盈亏 + 当前未实现盈亏
                                cumulative_pnl = cumulative_realized_pnl_now + today_unrealized_pnl
                                
                                # 在控制台输出详细指标（使用表格格式）
                                logger.info(f"计算完成: {account_id} - {exchange_name} - {symbol_key}")
                                # 创建一个修改后的 today_m，使用正确的今日新增已实现盈亏
                                today_m_corrected = m.copy()
                                today_m_corrected["realized_pnl"] = today_realized_pnl
                                today_m_corrected["daily_pnl"] = today_realized_pnl + today_unrealized_pnl
                                self._log_metrics_table(
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol=symbol_key,
                                    yesterday_m=yesterday_m,
                                    today_m=today_m_corrected,
                                    cumulative_pnl=cumulative_pnl,
                                )
                                
                                # 创建指标记录
                                metrics_record = PositionMetrics(
                                    timestamp=end_time,
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol=symbol_key,
                                    
                                    # 1. 昨收持仓（使用昨日剩余持仓）
                                    pre_long_qty=yesterday_m.get("left_long_qty", Decimal("0")),
                                    pre_short_qty=yesterday_m.get("left_short_qty", Decimal("0")),
                                    pre_long_value=yesterday_m.get("left_long_value", Decimal("0")),
                                    pre_short_value=yesterday_m.get("left_short_value", Decimal("0")),
                                    
                                    # 2. 今日交易
                                    long_qty=m.get("long_qty", Decimal("0")),
                                    short_qty=m.get("short_qty", Decimal("0")),
                                    long_value=m.get("long_value", Decimal("0")),
                                    short_value=m.get("short_value", Decimal("0")),
                                    avg_buy_prz=m.get("avg_buy_prz", Decimal("0")),
                                    avg_sell_prz=m.get("avg_sell_prz", Decimal("0")),
                                    
                                    # 3. 已实现 Pnl
                                    matched_qty=m.get("matched_qty", Decimal("0")),
                                    # 使用今日新增的已实现盈亏（而不是包含初始持仓的已实现盈亏）
                                    daily_realized_pnl=today_realized_pnl,
                                    
                                    # 4. 当日剩余仓位
                                    left_long_qty=m.get("left_long_qty", Decimal("0")),
                                    left_short_qty=m.get("left_short_qty", Decimal("0")),
                                    left_long_value=m.get("left_long_value", Decimal("0")),
                                    left_short_value=m.get("left_short_value", Decimal("0")),
                                    close_prz=m.get("close_prz", Decimal("0")),
                                    unrealized_pnl=today_unrealized_pnl,  # 使用从成交记录计算的累积未实现盈亏
                                    
                                    # 5. Pnl 汇总
                                    # 单日 PnL = 今日新增的已实现盈亏 + 今日未实现盈亏
                                    daily_pnl=today_realized_pnl + today_unrealized_pnl,
                                    cumulative_pnl=cumulative_pnl,
                                    cumulative_realized_pnl=cumulative_realized_pnl_now,
                                )
                                
                                session.add(metrics_record)
                                
                                # 更新 Prometheus metrics
                                labels = {
                                    "account_id": account_id,
                                    "exchange": exchange_name,
                                    "symbol": symbol_key,
                                }
                                
                                position_pre_long_qty.labels(**labels).set(float(yesterday_m.get("left_long_qty", Decimal("0"))))
                                position_pre_short_qty.labels(**labels).set(float(yesterday_m.get("left_short_qty", Decimal("0"))))
                                position_pre_long_value.labels(**labels).set(float(yesterday_m.get("left_long_value", Decimal("0"))))
                                position_pre_short_value.labels(**labels).set(float(yesterday_m.get("left_short_value", Decimal("0"))))
                                
                                position_long_qty.labels(**labels).set(float(m.get("long_qty", Decimal("0"))))
                                position_short_qty.labels(**labels).set(float(m.get("short_qty", Decimal("0"))))
                                position_long_value.labels(**labels).set(float(m.get("long_value", Decimal("0"))))
                                position_short_value.labels(**labels).set(float(m.get("short_value", Decimal("0"))))
                                position_avg_buy_prz.labels(**labels).set(float(m.get("avg_buy_prz", Decimal("0"))))
                                position_avg_sell_prz.labels(**labels).set(float(m.get("avg_sell_prz", Decimal("0"))))
                                
                                position_matched_qty.labels(**labels).set(float(m.get("matched_qty", Decimal("0"))))
                                # 使用今日新增的已实现盈亏（而不是包含初始持仓的已实现盈亏）
                                position_realized_pnl.labels(**labels).set(float(today_realized_pnl))
                                
                                position_left_long_qty.labels(**labels).set(float(m.get("left_long_qty", Decimal("0"))))
                                position_left_short_qty.labels(**labels).set(float(m.get("left_short_qty", Decimal("0"))))
                                position_left_long_value.labels(**labels).set(float(m.get("left_long_value", Decimal("0"))))
                                position_left_short_value.labels(**labels).set(float(m.get("left_short_value", Decimal("0"))))
                                position_close_prz.labels(**labels).set(float(m.get("close_prz", Decimal("0"))))
                                position_unrealized_pnl.labels(**labels).set(float(m.get("unrealized_pnl", Decimal("0"))))
                                
                                # 使用正确的单日 PnL（今日新增已实现 + 今日未实现）
                                position_daily_pnl.labels(**labels).set(float(today_realized_pnl + today_unrealized_pnl))
                                position_cumulative_pnl.labels(**labels).set(float(cumulative_pnl))
                                # 注意：Prometheus 指标里没有 cumulative_realized_pnl，如果需要可以添加
                            
                            await session.commit()
                            
                            logger.info(
                                f"已计算并存储指标（包括 Prometheus metrics）",
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
        today_realized_pnl: Decimal,
        today_unrealized_pnl: Decimal,
        end_time: datetime,
    ) -> Decimal:
        """从成交记录计算累计 PnL（准确，无时间偏差）.
        
        计算逻辑：
        - 历史累计已实现盈亏 = 从成交记录重新计算今天之前所有天的已实现盈亏总和（每天00:00:00-24:00:00）
        - 累计 PnL = 历史累计已实现盈亏 + 今天的已实现盈亏 + 今天的未实现盈亏
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            exchange: 交易所
            symbol: 交易对
            today_realized_pnl: 今天的已实现盈亏
            today_unrealized_pnl: 今天的未实现盈亏
            end_time: 当前时间（用于查询历史数据，排除今天）
        
        Returns:
            累计 PnL
        """
        try:
            # 获取今天的日期（UTC 00:00）
            today_start = datetime(end_time.year, end_time.month, end_time.day)
            
            # 从成交记录重新计算历史每天的已实现盈亏
            # 首先找到最早有成交记录的日期
            from sqlalchemy import func, cast, Date
            
            # 根据交易所选择对应的模型
            if exchange == "xt":
                from tri_arb.storage.xt_websocket_models import XTTradeUpdate
                TradeModel = XTTradeUpdate
                time_column = XTTradeUpdate.update_time
            elif exchange == "binance":
                from tri_arb.storage.models import TradeUpdate
                TradeModel = TradeUpdate
                time_column = TradeUpdate.transaction_time
            else:
                logger.warning(f"不支持的交易所: {exchange}，返回今天的总盈亏")
                return today_realized_pnl + today_unrealized_pnl
            
            # 查询最早有成交记录的日期
            earliest_query = (
                select(func.min(cast(time_column, Date)))
                .where(TradeModel.symbol == symbol)
            )
            if exchange == "binance":
                earliest_query = earliest_query.where(TradeModel.exchange == "binance_perp")
            if account_id:
                earliest_query = earliest_query.where(TradeModel.account_id == account_id)
            
            earliest_result = await session.execute(earliest_query)
            earliest_date = earliest_result.scalar()
            
            if not earliest_date:
                # 如果没有历史成交记录，只返回今天的总盈亏
                return today_realized_pnl + today_unrealized_pnl
            
            # 创建合约乘数 getter
            contract_multiplier_getter: Optional[Callable[[str], Decimal]] = None
            if self.contract_multiplier_service:
                service = self.contract_multiplier_service
                contract_multiplier_getter = lambda s: service.get_multiplier_sync(exchange, s)
            else:
                contract_multiplier_getter = lambda s: Decimal("1")
            
            # 创建计算器
            calc = PositionCalculator(
                session,
                exchange=exchange,
                account_id=account_id,
                contract_multiplier_getter=contract_multiplier_getter,
            )
            
            # 遍历今天之前的所有天，从成交记录计算每天完整一天的已实现盈亏
            historical_cumulative_realized_pnl = Decimal("0")
            current_date = earliest_date
            previous_day_matched_qty = Decimal("0")  # 前一天收盘时的轧差数量
            
            while current_date < today_start.date():
                day_start = datetime(current_date.year, current_date.month, current_date.day)
                day_end = day_start + timedelta(days=1)
                
                # 从成交记录计算这一天的完整数据
                day_metrics = await calc.calculate_positions_by_symbol(
                    start_time=day_start,
                    end_time=day_end,
                    symbol=symbol,
                )
                
                day_data = day_metrics.get(symbol, {})
                # 今日总轧差数量
                total_matched_qty = day_data.get("matched_qty", Decimal("0"))
                # 今日新增的轧差数量 = 今日总轧差 - 昨日收盘时的轧差
                daily_new_matched_qty = total_matched_qty - previous_day_matched_qty
                
                # 计算今日新增的已实现盈亏
                avg_buy_prz = day_data.get("avg_buy_prz", Decimal("0"))
                avg_sell_prz = day_data.get("avg_sell_prz", Decimal("0"))
                day_realized_pnl = Decimal("0")
                if daily_new_matched_qty > 0 and avg_sell_prz > 0 and avg_buy_prz > 0:
                    day_realized_pnl = daily_new_matched_qty * (avg_sell_prz - avg_buy_prz)
                
                # 累加这一天的已实现盈亏（仅今日新增的部分）
                historical_cumulative_realized_pnl += day_realized_pnl
                
                # 更新前一天收盘时的轧差数量（用于下一天的计算）
                previous_day_matched_qty = total_matched_qty
                
                current_date += timedelta(days=1)
            
            # 累计 PnL = 历史累计已实现盈亏 + 今天的已实现盈亏 + 今天的未实现盈亏
            cumulative_pnl = (
                historical_cumulative_realized_pnl 
                + today_realized_pnl 
                + today_unrealized_pnl
            )
            
            return cumulative_pnl
        
        except Exception as e:
            logger.error(
                f"从成交记录计算累计 PnL 失败",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )
            # 如果查询失败，返回今天的总盈亏（至少保证有值）
            return today_realized_pnl + today_unrealized_pnl
    
    async def _get_last_calc_time(
        self,
        session: AsyncSession,
        account_id: str,
        exchange: str,
        symbol: str,
    ) -> Optional[datetime]:
        """获取上次计算的时间点（用于增量查询）.
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            exchange: 交易所
            symbol: 交易对
        
        Returns:
            上次计算的时间点，如果没有则返回 None
        """
        try:
            result = await session.execute(
                select(PositionMetrics.timestamp)
                .where(PositionMetrics.account_id == account_id)
                .where(PositionMetrics.exchange == exchange)
                .where(PositionMetrics.symbol == symbol)
                .order_by(PositionMetrics.timestamp.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return row
        except Exception as e:
            logger.warning(
                f"获取上次计算时间失败",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                error=str(e),
            )
            return None

    async def _rebuild_midnight_snapshots(
        self,
        session: AsyncSession,
        calc: PositionCalculator,
        account_id: str,
        exchange: str,
        symbol: Optional[str] = None,
    ) -> None:
        """从成交表重算所有零点快照并写入/覆盖 position_metrics.
        
        流程：
        1. 查出该账号最早和最后成交日期
        2. 用 PositionCalculator.get_daily_trade_stats 获取日度成交统计
        3. 用 PositionCalculator.calc_daily_realized_series 计算每日和累积已实现盈亏
        4. 对每个 trade_date，构造零点 timestamp = (trade_date + 1天) 00:00，
           然后 INSERT ... ON CONFLICT DO UPDATE 覆盖写入 position_metrics
        
        Args:
            session: 数据库会话
            calc: PositionCalculator 实例
            account_id: 账号ID
            exchange: 交易所
            symbol: 交易对（可选），如果不指定则处理所有交易对
        """
        from sqlalchemy import insert, cast, Date
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        
        try:
            # 1. 查出最早和最后成交日期
            time_column = (
                calc.TradeModel.transaction_time
                if calc.exchange == "binance"
                else calc.TradeModel.update_time
            )
            
            earliest_query = select(func.min(cast(time_column, Date)))
            latest_query = select(func.max(cast(time_column, Date)))
            
            if calc.exchange == "binance":
                earliest_query = earliest_query.where(calc.TradeModel.exchange == "binance_perp")
                latest_query = latest_query.where(calc.TradeModel.exchange == "binance_perp")
            if calc.account_id:
                earliest_query = earliest_query.where(calc.TradeModel.account_id == calc.account_id)
                latest_query = latest_query.where(calc.TradeModel.account_id == calc.account_id)
            if symbol:
                earliest_query = earliest_query.where(calc.TradeModel.symbol == symbol)
                latest_query = latest_query.where(calc.TradeModel.symbol == symbol)
            
            earliest_result = await session.execute(earliest_query)
            latest_result = await session.execute(latest_query)
            earliest_date = earliest_result.scalar()
            latest_date = latest_result.scalar()
            
            if not earliest_date or not latest_date:
                logger.warning(
                    "没有找到成交记录，跳过重建零点快照",
                    account_id=account_id,
                    exchange=exchange,
                    symbol=symbol,
                )
                return
            
            # 2. 获取日度成交统计
            logger.info(
                f"开始重建零点快照: {earliest_date} -> {latest_date}",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
            )
            
            daily_stats = await calc.get_daily_trade_stats(
                start_date=earliest_date,
                end_date=latest_date,
                symbol=symbol,
            )
            
            if not daily_stats:
                logger.warning("日度成交统计为空，跳过重建")
                return
            
            # 3. 计算每日和累积已实现盈亏
            daily_series = calc.calc_daily_realized_series(daily_stats)
            
            if not daily_series:
                logger.warning("日度计算结果为空，跳过重建")
                return
            
            # 4. 对每个 trade_date，构造零点快照并写入/覆盖 position_metrics
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            
            for trade_date, day_data in sorted(daily_series.items()):
                # 零点 timestamp = trade_date 的下一天 00:00（即该日结束时的快照）
                midnight_timestamp = datetime.combine(trade_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)
                
                for sym, metrics in day_data.items():
                    # 获取前一日收盘持仓（作为今日开盘持仓）
                    prev_date = trade_date - timedelta(days=1)
                    prev_day_data = daily_series.get(prev_date, {})
                    prev_metrics = prev_day_data.get(sym, {})
                    
                    # 获取当日最后一笔成交价（用于未实现盈亏）
                    day_end = datetime.combine(trade_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)
                    day_start = datetime.combine(trade_date, datetime.min.time()).replace(tzinfo=None)
                    close_prices = await calc._get_close_prices(day_start, day_end, sym)
                    close_prz = close_prices.get(sym, Decimal("0"))
                    
                    # 计算未实现盈亏（用收盘持仓 + 最后成交价）
                    unrealized_pnl = Decimal("0")
                    if close_prz > 0:
                        close_left_long_qty = metrics.get("close_left_long_qty", Decimal("0"))
                        close_left_short_qty = metrics.get("close_left_short_qty", Decimal("0"))
                        avg_buy_prz = metrics.get("avg_buy_prz", Decimal("0"))
                        avg_sell_prz = metrics.get("avg_sell_prz", Decimal("0"))
                        unrealized_pnl = (
                            close_left_long_qty * (close_prz - avg_buy_prz) +
                            close_left_short_qty * (avg_sell_prz - close_prz)
                        )
                    
                    # 构造要插入/更新的记录
                    daily_realized_pnl = metrics.get("daily_realized_pnl", Decimal("0"))
                    cumulative_realized_pnl = metrics.get("cumulative_realized_pnl", Decimal("0"))
                    daily_pnl = daily_realized_pnl + unrealized_pnl
                    cumulative_pnl = cumulative_realized_pnl + unrealized_pnl
                    
                    # 使用 PostgreSQL 的 ON CONFLICT DO UPDATE 实现覆盖写入
                    stmt = pg_insert(PositionMetrics).values(
                        timestamp=midnight_timestamp,
                        account_id=account_id,
                        exchange=exchange,
                        symbol=sym,
                        pre_long_qty=metrics.get("open_left_long_qty", Decimal("0")),
                        pre_short_qty=metrics.get("open_left_short_qty", Decimal("0")),
                        pre_long_value=metrics.get("open_left_long_value", Decimal("0")),
                        pre_short_value=metrics.get("open_left_short_value", Decimal("0")),
                        long_qty=metrics.get("total_long_qty", Decimal("0")),
                        short_qty=metrics.get("total_short_qty", Decimal("0")),
                        long_value=metrics.get("total_long_value", Decimal("0")),
                        short_value=metrics.get("total_short_value", Decimal("0")),
                        avg_buy_prz=metrics.get("avg_buy_prz", Decimal("0")),
                        avg_sell_prz=metrics.get("avg_sell_prz", Decimal("0")),
                        matched_qty=metrics.get("matched_qty", Decimal("0")),
                        daily_realized_pnl=daily_realized_pnl,
                        left_long_qty=metrics.get("close_left_long_qty", Decimal("0")),
                        left_short_qty=metrics.get("close_left_short_qty", Decimal("0")),
                        left_long_value=metrics.get("close_left_long_value", Decimal("0")),
                        left_short_value=metrics.get("close_left_short_value", Decimal("0")),
                        close_prz=close_prz,
                        unrealized_pnl=unrealized_pnl,
                        daily_pnl=daily_pnl,
                        cumulative_pnl=cumulative_pnl,
                        cumulative_realized_pnl=cumulative_realized_pnl,
                        created_at=datetime.utcnow(),
                    )
                    
                    # ON CONFLICT: 如果 (timestamp, account_id, exchange, symbol) 已存在，则更新所有字段
                    # 使用 index_elements 指定唯一索引的列
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["timestamp", "account_id", "exchange", "symbol"],
                        set_={
                            "pre_long_qty": stmt.excluded.pre_long_qty,
                            "pre_short_qty": stmt.excluded.pre_short_qty,
                            "pre_long_value": stmt.excluded.pre_long_value,
                            "pre_short_value": stmt.excluded.pre_short_value,
                            "long_qty": stmt.excluded.long_qty,
                            "short_qty": stmt.excluded.short_qty,
                            "long_value": stmt.excluded.long_value,
                            "short_value": stmt.excluded.short_value,
                            "avg_buy_prz": stmt.excluded.avg_buy_prz,
                            "avg_sell_prz": stmt.excluded.avg_sell_prz,
                            "matched_qty": stmt.excluded.matched_qty,
                            "daily_realized_pnl": stmt.excluded.daily_realized_pnl,
                            "left_long_qty": stmt.excluded.left_long_qty,
                            "left_short_qty": stmt.excluded.left_short_qty,
                            "left_long_value": stmt.excluded.left_long_value,
                            "left_short_value": stmt.excluded.left_short_value,
                            "close_prz": stmt.excluded.close_prz,
                            "unrealized_pnl": stmt.excluded.unrealized_pnl,
                            "daily_pnl": stmt.excluded.daily_pnl,
                            "cumulative_pnl": stmt.excluded.cumulative_pnl,
                            "cumulative_realized_pnl": stmt.excluded.cumulative_realized_pnl,
                            "created_at": stmt.excluded.created_at,
                        }
                    )
                    
                    await session.execute(stmt)
            
            await session.commit()
            logger.info(
                f"完成重建零点快照",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                date_range=f"{earliest_date} -> {latest_date}",
            )
            
        except Exception as e:
            logger.error(
                f"重建零点快照失败",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                error=str(e),
            )
            await session.rollback()
            raise
    
    async def _get_or_calculate_daily_initial_positions(
        self,
        session: AsyncSession,
        calc: PositionCalculator,
        account_id: str,
        exchange: str,
        target_date: datetime.date,
    ) -> Dict[str, Dict[str, Decimal]]:
        """获取每日零点的初始持仓（从 position_metrics 表读取）.
        
        如果缓存不存在，会调用 _rebuild_midnight_snapshots 重建所有零点快照。
        
        Args:
            session: 数据库会话
            calc: PositionCalculator 实例
            account_id: 账号ID
            exchange: 交易所
            target_date: 目标日期（例如昨天的日期）
        
        Returns:
            字典，格式为 {
                "symbol": {
                    "initial_long_qty": Decimal,
                    "initial_short_qty": Decimal,
                    "initial_long_value": Decimal,
                    "initial_short_value": Decimal,
                }
            }
        """
        # 目标日期的零点时间（UTC，但使用 naive datetime 因为数据库是 TIMESTAMP WITHOUT TIME ZONE）
        target_start_time = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=None)
        
        try:
            # 1. 先检查缓存：查找 PositionMetrics 表中是否有目标日期零点的记录
            cache_query = (
                select(PositionMetrics)
                .where(PositionMetrics.account_id == account_id)
                .where(PositionMetrics.exchange == exchange)
                .where(PositionMetrics.timestamp == target_start_time)
            )
            cache_result = await session.execute(cache_query)
            cache_rows = cache_result.scalars().all()
            
            if cache_rows:
                # 从缓存中读取所有 symbol 的持仓
                cached_positions: Dict[str, Dict[str, Decimal]] = {}
                for row in cache_rows:
                    cached_positions[row.symbol] = {
                        "initial_long_qty": row.left_long_qty or Decimal("0"),
                        "initial_short_qty": row.left_short_qty or Decimal("0"),
                        "initial_long_value": row.left_long_value or Decimal("0"),
                        "initial_short_value": row.left_short_value or Decimal("0"),
                    }
                
                logger.debug(
                    f"从缓存读取 {target_date} 零点的初始持仓",
                    account_id=account_id,
                    exchange=exchange,
                    symbol_count=len(cached_positions),
                )
                return cached_positions
            
            # 2. 缓存不存在，重建所有零点快照
            logger.info(
                f"缓存不存在，重建所有零点快照",
                account_id=account_id,
                exchange=exchange,
                target_date=target_date,
            )
            
            await self._rebuild_midnight_snapshots(
                session=session,
                calc=calc,
                account_id=account_id,
                exchange=exchange,
                symbol=None,  # 重建所有 symbol
            )
            
            # 3. 重建后再次读取
            cache_result = await session.execute(cache_query)
            cache_rows = cache_result.scalars().all()
            
            if cache_rows:
                cached_positions: Dict[str, Dict[str, Decimal]] = {}
                for row in cache_rows:
                    cached_positions[row.symbol] = {
                        "initial_long_qty": row.left_long_qty or Decimal("0"),
                        "initial_short_qty": row.left_short_qty or Decimal("0"),
                        "initial_long_value": row.left_long_value or Decimal("0"),
                        "initial_short_value": row.left_short_value or Decimal("0"),
                    }
                return cached_positions
            
            # 如果重建后还是没有，返回空字典
            logger.warning(
                f"重建零点快照后仍未找到 {target_date} 的数据",
                account_id=account_id,
                exchange=exchange,
            )
            return {}
            
        except Exception as e:
            logger.error(
                f"获取每日初始持仓失败",
                account_id=account_id,
                exchange=exchange,
                target_date=target_date,
                error=str(e),
            )
            return {}
    
    async def _cache_daily_initial_positions(
        self,
        session: AsyncSession,
        account_id: str,
        exchange: str,
        target_date: datetime.date,
        positions: Dict[str, Dict[str, Decimal]],
    ) -> None:
        """缓存每日零点的初始持仓（用于明天使用）.
        
        将计算出的持仓存储到 PositionMetrics 表，timestamp 设置为目标日期零点。
        这样明天计算时就可以直接从缓存读取，而不需要重新计算。
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            exchange: 交易所
            target_date: 目标日期（例如今天的日期）
            positions: 持仓字典，格式为 {
                "symbol": {
                    "left_long_qty": Decimal,
                    "left_short_qty": Decimal,
                    "left_long_value": Decimal,
                    "left_short_value": Decimal,
                }
            }
        """
        from sqlalchemy import insert
        
        try:
            # 目标日期的零点时间（UTC，但使用 naive datetime 因为数据库是 TIMESTAMP WITHOUT TIME ZONE）
            target_start_time = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=None)
            
            # 检查是否已经存在缓存
            check_query = (
                select(PositionMetrics)
                .where(PositionMetrics.account_id == account_id)
                .where(PositionMetrics.exchange == exchange)
                .where(PositionMetrics.timestamp == target_start_time)
                .limit(1)
            )
            check_result = await session.execute(check_query)
            existing = check_result.scalar_one_or_none()
            
            if existing:
                # 缓存已存在，跳过
                logger.debug(
                    f"缓存已存在，跳过存储 {target_date} 零点的初始持仓",
                    account_id=account_id,
                    exchange=exchange,
                )
                return
            
            # 构建缓存记录（使用当时完整的指标，而不是全部填 0）
            cache_records = []
            for symbol, pos_data in positions.items():
                if symbol == "TOTAL":
                    continue
                cache_records.append({
                    "timestamp": target_start_time,
                    "account_id": account_id,
                    "exchange": exchange,
                    "symbol": symbol,
                    # 昨日完整指标在 target_start_time 时刻的快照
                    "pre_long_qty": pos_data.get("pre_long_qty", Decimal("0")),
                    "pre_short_qty": pos_data.get("pre_short_qty", Decimal("0")),
                    "pre_long_value": pos_data.get("pre_long_value", Decimal("0")),
                    "pre_short_value": pos_data.get("pre_short_value", Decimal("0")),
                    "long_qty": pos_data.get("long_qty", Decimal("0")),
                    "short_qty": pos_data.get("short_qty", Decimal("0")),
                    "long_value": pos_data.get("long_value", Decimal("0")),
                    "short_value": pos_data.get("short_value", Decimal("0")),
                    "avg_buy_prz": pos_data.get("avg_buy_prz", Decimal("0")),
                    "avg_sell_prz": pos_data.get("avg_sell_prz", Decimal("0")),
                    "matched_qty": pos_data.get("matched_qty", Decimal("0")),
                    "realized_pnl": pos_data.get("realized_pnl", Decimal("0")),
                    "left_long_qty": pos_data.get("left_long_qty", Decimal("0")),
                    "left_short_qty": pos_data.get("left_short_qty", Decimal("0")),
                    "left_long_value": pos_data.get("left_long_value", Decimal("0")),
                    "left_short_value": pos_data.get("left_short_value", Decimal("0")),
                    "close_prz": pos_data.get("close_prz", Decimal("0")),
                    "unrealized_pnl": pos_data.get("unrealized_pnl", Decimal("0")),
                    "daily_pnl": pos_data.get("daily_pnl", Decimal("0")),
                    "cumulative_pnl": pos_data.get("cumulative_pnl", Decimal("0")),
                })
            
            if cache_records:
                await session.execute(insert(PositionMetrics).values(cache_records))
                await session.commit()
                logger.info(
                    f"已缓存 {target_date} 零点的初始持仓（用于明天使用）",
                    account_id=account_id,
                    exchange=exchange,
                    symbol_count=len(cache_records),
                )
        except Exception as e:
            logger.warning(
                f"缓存每日初始持仓失败",
                account_id=account_id,
                exchange=exchange,
                target_date=target_date,
                error=str(e),
            )
            # 不抛出异常，允许继续执行
    
    async def _get_prior_left_positions_from_trades(
        self,
        calc: PositionCalculator,
        target_start_time: datetime,
    ) -> Dict[str, Dict[str, Decimal]]:
        """从 xt_trade_update 表计算某时间点之前的剩余持仓（用于作为下一天的初始持仓）.
        
        通过计算 target_start_time 之前的所有交易数据，得到每个 symbol 的剩余持仓。
        这样完全基于原始交易数据，不依赖 PositionMetrics 表中的历史计算结果。
        
        Args:
            calc: PositionCalculator 实例（已初始化好 session、account_id、exchange）
            target_start_time: 目标开始时间（例如昨日 00:00）
        
        Returns:
            字典，格式为 {
                "symbol": {
                    "initial_long_qty": Decimal,
                    "initial_short_qty": Decimal,
                    "initial_long_value": Decimal,
                    "initial_short_value": Decimal,
                }
            }
        """
        try:
            # 从数据库中查询最早的一条交易记录的时间
            from sqlalchemy import func
            
            time_column = (
                calc.TradeModel.transaction_time
                if calc.exchange == "binance"
                else calc.TradeModel.update_time
            )
            
            # 查询最早的一条交易记录
            query = select(func.min(time_column))
            if calc.exchange == "binance":
                query = query.where(calc.TradeModel.exchange == "binance_perp")
            if calc.account_id:
                query = query.where(calc.TradeModel.account_id == calc.account_id)
            query = query.where(time_column < target_start_time)
            
            result = await calc.db_session.execute(query)
            earliest_time = result.scalar_one_or_none()
            
            # 如果数据库中没有交易记录，返回空字典（表示没有初始持仓）
            if earliest_time is None:
                return {}
            
            # 计算从最早时间到 target_start_time 的所有交易：
            # - 剩余持仓（left_*）作为下一段计算的初始持仓
            # - realized_pnl 作为“从 earliest_time 到 target_start_time 的整段累积已实现盈亏”
            prior_metrics = await calc.calculate_yesterday_end_left_qty_value(
                start_time=earliest_time,
                end_time=target_start_time,
                initial_positions_dict=None,  # 从最早开始计算，没有初始持仓
            )

            # 转换为返回格式：
            # - initial_* 用于下一段计算的初始持仓（= 此时刻的剩余持仓）
            # - cumulative_realized_pnl = 这一整段区间的 realized_pnl
            prior: Dict[str, Dict[str, Decimal]] = {}
            for symbol, metrics in prior_metrics.items():
                prior[symbol] = {
                    "initial_long_qty": metrics.get("left_long_qty", Decimal("0")),
                    "initial_short_qty": metrics.get("left_short_qty", Decimal("0")),
                    "initial_long_value": metrics.get("left_long_value", Decimal("0")),
                    "initial_short_value": metrics.get("left_short_value", Decimal("0")),
                    "cumulative_realized_pnl": metrics.get("realized_pnl", Decimal("0")),
                }
            
            return prior
        except Exception as e:
            logger.warning(
                f"从交易数据计算历史剩余持仓失败",
                target_start_time=target_start_time,
                error=str(e),
            )
            return {}
    
    async def _get_initial_positions_from_trades(
        self,
        session: AsyncSession,
        account_id: str,
        exchange: str,
        symbol: str,
        before_time: datetime,
        contract_multiplier_getter: Callable[[str], Decimal],
    ) -> Tuple[List[Tuple[Decimal, Decimal]], List[Tuple[Decimal, Decimal]]]:
        """从成交记录获取指定时间点之前的持仓状态（用于增量计算）.
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            exchange: 交易所
            symbol: 交易对
            before_time: 时间点
            contract_multiplier_getter: 获取合约乘数的函数
        
        Returns:
            (long_positions, short_positions) 持仓队列，每个元素是 (数量, 开仓价格)
        """
        # 根据交易所选择对应的模型
        if exchange == "xt":
            from tri_arb.storage.xt_websocket_models import XTTradeUpdate
            TradeModel = XTTradeUpdate
            time_column = XTTradeUpdate.update_time
        elif exchange == "binance":
            from tri_arb.storage.models import TradeUpdate
            TradeModel = TradeUpdate
            time_column = TradeUpdate.transaction_time
        else:
            logger.warning(f"不支持的交易所: {exchange}，返回空持仓")
            return [], []
        
        try:
            # 查询该时间点之前的所有成交记录（优化：只查询需要的字段）
            query = (
                select(TradeModel.side, TradeModel.price, TradeModel.quantity, time_column)
                .where(time_column < before_time)
                .where(TradeModel.symbol == symbol)
                .order_by(time_column.asc())
            )
            
            if exchange == "binance":
                query = query.where(TradeModel.exchange == "binance_perp")
            if account_id:
                query = query.where(TradeModel.account_id == account_id)
            
            result = await session.execute(query)
            rows = result.all()
            
            # 获取合约乘数
            contract_multiplier = contract_multiplier_getter(symbol)
            
            # 使用 FIFO 方式处理持仓
            long_positions: List[Tuple[Decimal, Decimal]] = []
            short_positions: List[Tuple[Decimal, Decimal]] = []
            
            for row in rows:
                side = row.side.upper()
                price = Decimal(str(row.price))
                quantity_contracts = Decimal(str(row.quantity))
                quantity_coins = quantity_contracts * contract_multiplier
                
                if side == "BUY":
                    remaining = quantity_coins
                    while remaining > 0 and short_positions:
                        short_qty, short_price = short_positions[0]
                        if short_qty <= remaining:
                            remaining -= short_qty
                            short_positions.pop(0)
                        else:
                            short_positions[0] = (short_qty - remaining, short_price)
                            remaining = Decimal("0")
                    if remaining > 0:
                        long_positions.append((remaining, price))
                elif side == "SELL":
                    remaining = quantity_coins
                    while remaining > 0 and long_positions:
                        long_qty, long_price = long_positions[0]
                        if long_qty <= remaining:
                            remaining -= long_qty
                            long_positions.pop(0)
                        else:
                            long_positions[0] = (long_qty - remaining, long_price)
                            remaining = Decimal("0")
                    if remaining > 0:
                        short_positions.append((remaining, price))
            
            return long_positions, short_positions
            
        except Exception as e:
            logger.error(
                f"从成交记录获取初始持仓失败",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )
            return [], []
    
    async def _calculate_unrealized_pnl_from_trades(
        self,
        session: AsyncSession,
        account_id: str,
        exchange: str,
        symbol: str,
        current_price: Decimal,
        end_time: datetime,
    ) -> Decimal:
        """从成交记录计算未实现盈亏（优化：支持增量查询）.
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            exchange: 交易所
            symbol: 交易对
            current_price: 当前价格
            end_time: 计算时间点
        
        Returns:
            未实现盈亏
        """
        if current_price <= 0:
            logger.warning(f"当前价格为 0，无法计算未实现盈亏", symbol=symbol)
            return Decimal("0")
        
        try:
            # 获取合约乘数
            contract_multiplier_getter = None
            if self.contract_multiplier_service:
                service = self.contract_multiplier_service
                contract_multiplier_getter = lambda s: service.get_multiplier_sync(exchange, s)
            else:
                contract_multiplier_getter = lambda s: Decimal("1")
            
            # 获取上次计算时间（用于增量查询）
            last_calc_time = await self._get_last_calc_time(session, account_id, exchange, symbol)
            
            # 根据交易所选择对应的模型
            if exchange == "xt":
                from tri_arb.storage.xt_websocket_models import XTTradeUpdate
                TradeModel = XTTradeUpdate
                time_column = XTTradeUpdate.update_time
            elif exchange == "binance":
                from tri_arb.storage.models import TradeUpdate
                TradeModel = TradeUpdate
                time_column = TradeUpdate.transaction_time
            else:
                logger.warning(f"不支持的交易所: {exchange}，返回 0")
                return Decimal("0")
            
            # 获取初始持仓（如果有上次计算时间，只查询该时间之后的成交记录）
            if last_calc_time:
                logger.debug(
                    f"增量计算未实现盈亏",
                    account_id=account_id,
                    exchange=exchange,
                    symbol=symbol,
                    last_calc_time=last_calc_time,
                )
                long_positions, short_positions = await self._get_initial_positions_from_trades(
                    session, account_id, exchange, symbol, last_calc_time, contract_multiplier_getter
                )
                
                # 只查询新成交记录（优化：只查询需要的字段）
                query = (
                    select(TradeModel.side, TradeModel.price, TradeModel.quantity, time_column)
                    .where(time_column >= last_calc_time)
                    .where(time_column <= end_time)
                    .where(TradeModel.symbol == symbol)
                    .order_by(time_column.asc())
                )
            else:
                # 全量计算：查询所有成交记录
                logger.debug(
                    f"全量计算未实现盈亏",
                    account_id=account_id,
                    exchange=exchange,
                    symbol=symbol,
                )
                long_positions, short_positions = [], []
                
                query = (
                    select(TradeModel.side, TradeModel.price, TradeModel.quantity, time_column)
                    .where(time_column <= end_time)
                    .where(TradeModel.symbol == symbol)
                    .order_by(time_column.asc())
                )
            
            if exchange == "binance":
                query = query.where(TradeModel.exchange == "binance_perp")
            if account_id:
                query = query.where(TradeModel.account_id == account_id)
            
            result = await session.execute(query)
            rows = result.all()
            
            # 获取合约乘数
            contract_multiplier = contract_multiplier_getter(symbol)
            
            # 处理新成交记录
            for row in rows:
                side = row.side.upper()
                price = Decimal(str(row.price))
                quantity_contracts = Decimal(str(row.quantity))
                quantity_coins = quantity_contracts * contract_multiplier
                
                if side == "BUY":
                    remaining = quantity_coins
                    while remaining > 0 and short_positions:
                        short_qty, short_price = short_positions[0]
                        if short_qty <= remaining:
                            remaining -= short_qty
                            short_positions.pop(0)
                        else:
                            short_positions[0] = (short_qty - remaining, short_price)
                            remaining = Decimal("0")
                    if remaining > 0:
                        long_positions.append((remaining, price))
                elif side == "SELL":
                    remaining = quantity_coins
                    while remaining > 0 and long_positions:
                        long_qty, long_price = long_positions[0]
                        if long_qty <= remaining:
                            remaining -= long_qty
                            long_positions.pop(0)
                        else:
                            long_positions[0] = (long_qty - remaining, long_price)
                            remaining = Decimal("0")
                    if remaining > 0:
                        short_positions.append((remaining, price))
            
            # 计算未实现盈亏
            long_unrealized = sum(qty * (current_price - price) for qty, price in long_positions)
            short_unrealized = sum(qty * (price - current_price) for qty, price in short_positions)
            total_unrealized = long_unrealized + short_unrealized
            
            logger.debug(
                f"从成交记录计算未实现盈亏完成",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                long_qty=sum(qty for qty, _ in long_positions),
                short_qty=sum(qty for qty, _ in short_positions),
                unrealized_pnl=total_unrealized,
            )
            
            return total_unrealized
            
        except Exception as e:
            logger.error(
                f"从成交记录计算未实现盈亏失败",
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
                error=str(e),
                exc_info=True,
            )
            # 如果计算失败，返回 0（或者可以回退到原来的计算方法）
            return Decimal("0")
    
    def _log_metrics_table(
        self,
        account_id: str,
        exchange: str,
        symbol: str,
        yesterday_m: Dict[str, Any],
        today_m: Dict[str, Any],
        cumulative_pnl: Decimal,
    ) -> None:
        """使用表格格式输出持仓指标到日志.
        
        Args:
            account_id: 账号ID
            exchange: 交易所
            symbol: 交易对
            yesterday_m: 昨日指标数据
            today_m: 今日指标数据
            cumulative_pnl: 累计 PnL
        """
        def _format_decimal(value: Decimal, precision: int = 2) -> str:
            """格式化 Decimal 值."""
            if value is None:
                return "0.00"
            return f"{float(value):,.{precision}f}"
        
        def _format_decimal_no_comma(value: Decimal, precision: int = 2) -> str:
            """格式化 Decimal 值（不使用千分位分隔符，用于计算过程显示）."""
            if value is None:
                return "0.00"
            return f"{float(value):.{precision}f}"
        
        # 获取计算过程中的中间变量
        initial_long_qty = today_m.get("initial_long_qty", Decimal("0"))
        initial_short_qty = today_m.get("initial_short_qty", Decimal("0"))
        buy_volume = today_m.get("buy_volume", Decimal("0"))
        sell_volume = today_m.get("sell_volume", Decimal("0"))
        buy_trade_value = today_m.get("buy_trade_value", Decimal("0"))
        sell_trade_value = today_m.get("sell_trade_value", Decimal("0"))
        initial_long_value = today_m.get("initial_long_value", Decimal("0"))
        initial_short_value = today_m.get("initial_short_value", Decimal("0"))
        long_qty = today_m.get("long_qty", Decimal("0"))
        short_qty = today_m.get("short_qty", Decimal("0"))
        long_value = today_m.get("long_value", Decimal("0"))
        short_value = today_m.get("short_value", Decimal("0"))
        avg_buy_prz = today_m.get("avg_buy_prz", Decimal("0"))
        avg_sell_prz = today_m.get("avg_sell_prz", Decimal("0"))
        matched_qty = today_m.get("matched_qty", Decimal("0"))
        realized_pnl = today_m.get("realized_pnl", Decimal("0"))
        left_long_qty = today_m.get("left_long_qty", Decimal("0"))
        left_short_qty = today_m.get("left_short_qty", Decimal("0"))
        close_prz = today_m.get("close_prz", Decimal("0"))
        unrealized_pnl = today_m.get("unrealized_pnl", Decimal("0"))
        
        table = Table(
            title=f"持仓指标计算结果 [{account_id} - {exchange} - {symbol}]",
            show_header=True,
            header_style="bold cyan",
            box=None,  # 使用简单边框，确保在控制台正确显示
        )
        table.add_column("指标", justify="left", style="cyan")
        table.add_column("数值", justify="right", style="green")
        
        # 1. 昨收持仓
        table.add_row("[bold yellow]--- 1. 昨收持仓 ---[/bold yellow]", "")
        table.add_row("  昨日多头持仓量 (pre_long_qty)", _format_decimal(yesterday_m.get("left_long_qty", Decimal("0")), 2))
        table.add_row("  昨日空头持仓量 (pre_short_qty)", _format_decimal(yesterday_m.get("left_short_qty", Decimal("0")), 2))
        table.add_row("  昨日多头市值 (pre_long_value)", _format_decimal(yesterday_m.get("left_long_value", Decimal("0")), 4))
        table.add_row("  昨日空头市值 (pre_short_value)", _format_decimal(yesterday_m.get("left_short_value", Decimal("0")), 4))
        table.add_row("", "")  # 空行
        
        # 2. 今日交易
        table.add_row("[bold yellow]--- 2. 今日交易 ---[/bold yellow]", "")
        table.add_row(
            f"  多头交易量: long_qty = sum(buy_vol) + pre_long_qty",
            f"{_format_decimal_no_comma(buy_volume, 2)} + {_format_decimal_no_comma(initial_long_qty, 2)} = {_format_decimal_no_comma(long_qty, 2)}"
        )
        table.add_row(
            f"  空头交易量: short_qty = sum(sell_vol) + pre_short_qty",
            f"{_format_decimal_no_comma(sell_volume, 2)} + {_format_decimal_no_comma(initial_short_qty, 2)} = {_format_decimal_no_comma(short_qty, 2)}"
        )
        table.add_row(
            f"  多头市值: long_value = sum(buy_vol * buy_price) + pre_long_value",
            f"{_format_decimal_no_comma(buy_trade_value, 4)} + {_format_decimal_no_comma(initial_long_value, 4)} = {_format_decimal_no_comma(long_value, 4)}"
        )
        table.add_row(
            f"  空头市值: short_value = sum(sell_vol * sell_price) + pre_short_value",
            f"{_format_decimal_no_comma(sell_trade_value, 4)} + {_format_decimal_no_comma(initial_short_value, 4)} = {_format_decimal_no_comma(short_value, 4)}"
        )
        if long_qty > 0:
            table.add_row(
                f"  买入平均价格: avg_buy_prz = long_value / long_qty",
                f"{_format_decimal_no_comma(long_value, 4)} / {_format_decimal_no_comma(long_qty, 2)} = {_format_decimal_no_comma(avg_buy_prz, 8)}"
            )
        else:
            table.add_row("  买入平均价格 (avg_buy_prz)", _format_decimal(avg_buy_prz, 8))
        if short_qty > 0:
            table.add_row(
                f"  卖出平均价格: avg_sell_prz = short_value / short_qty",
                f"{_format_decimal_no_comma(short_value, 4)} / {_format_decimal_no_comma(short_qty, 2)} = {_format_decimal_no_comma(avg_sell_prz, 8)}"
            )
        else:
            table.add_row("  卖出平均价格 (avg_sell_prz)", _format_decimal(avg_sell_prz, 8))
        table.add_row("", "")  # 空行
        
        # 3. 已实现 Pnl
        table.add_row("[bold yellow]--- 3. 已实现 Pnl ---[/bold yellow]", "")
        table.add_row(
            f"  轧差数量: matched_qty = min(long_qty, short_qty)",
            f"min({_format_decimal_no_comma(long_qty, 2)}, {_format_decimal_no_comma(short_qty, 2)}) = {_format_decimal_no_comma(matched_qty, 2)}"
        )
        if matched_qty > 0:
            table.add_row(
                f"  已实现盈亏: realized_pnl = (avg_sell_prz - avg_buy_prz) * matched_qty",
                f"({_format_decimal_no_comma(avg_sell_prz, 8)} - {_format_decimal_no_comma(avg_buy_prz, 8)}) * {_format_decimal_no_comma(matched_qty, 2)} = {_format_decimal_no_comma(realized_pnl, 4)}"
            )
        else:
            table.add_row("  当日已实现盈亏 (realized_pnl)", _format_decimal(realized_pnl, 4))
        table.add_row("", "")  # 空行
        
        # 4. 当日剩余仓位
        table.add_row("[bold yellow]--- 4. 当日剩余仓位 ---[/bold yellow]", "")
        table.add_row(
            f"  日内多头剩余持仓: left_long_qty = long_qty - matched_qty",
            f"{_format_decimal_no_comma(long_qty, 2)} - {_format_decimal_no_comma(matched_qty, 2)} = {_format_decimal_no_comma(left_long_qty, 2)}"
        )
        table.add_row(
            f"  日内空头剩余持仓: left_short_qty = short_qty - matched_qty",
            f"{_format_decimal_no_comma(short_qty, 2)} - {_format_decimal_no_comma(matched_qty, 2)} = {_format_decimal_no_comma(left_short_qty, 2)}"
        )
        table.add_row("  多头剩余市值 (left_long_value)", _format_decimal(today_m.get("left_long_value", Decimal("0")), 4))
        table.add_row("  空头剩余市值 (left_short_value)", _format_decimal(today_m.get("left_short_value", Decimal("0")), 4))
        table.add_row("  当日最后一笔成交价 (close_prz)", _format_decimal(close_prz, 8))
        if close_prz > 0:
            long_unrealized = left_long_qty * (close_prz - avg_buy_prz) if avg_buy_prz > 0 else Decimal("0")
            short_unrealized = left_short_qty * (avg_sell_prz - close_prz) if avg_sell_prz > 0 else Decimal("0")
            if left_long_qty > 0 or left_short_qty > 0:
                table.add_row(
                    f"  日内未实现盈亏: unrealized_pnl = left_long_qty * (close_prz - avg_buy_prz) + left_short_qty * (avg_sell_prz - close_prz)",
                    f"{_format_decimal_no_comma(left_long_qty, 2)} * ({_format_decimal_no_comma(close_prz, 8)} - {_format_decimal_no_comma(avg_buy_prz, 8)}) + {_format_decimal_no_comma(left_short_qty, 2)} * ({_format_decimal_no_comma(avg_sell_prz, 8)} - {_format_decimal_no_comma(close_prz, 8)}) = {_format_decimal_no_comma(unrealized_pnl, 4)}"
                )
            else:
                table.add_row("  累积未实现盈亏 (unrealized_pnl)", _format_decimal(unrealized_pnl, 4))
        else:
            table.add_row("  累积未实现盈亏 (unrealized_pnl)", _format_decimal(unrealized_pnl, 4))
        table.add_row("", "")  # 空行
        
        # 5. Pnl 汇总
        table.add_row("[bold yellow]--- 5. Pnl 汇总 ---[/bold yellow]", "")
        # 单日 PnL = 今日新增的已实现盈亏 + 今日未实现盈亏
        today_realized = today_m.get("realized_pnl", Decimal("0"))
        today_unrealized = today_m.get("unrealized_pnl", Decimal("0"))
        daily_pnl = today_realized + today_unrealized
        table.add_row("  单日已实现盈亏 (realized_pnl)", _format_decimal(today_realized, 4))
        table.add_row("  单日 PnL (今日新增已实现 + 今日未实现)", _format_decimal(daily_pnl, 4))
        table.add_row("  累计盈亏: accum_pnl = 历史已实现盈亏加总 + 当日已实现盈亏 + 当日未实现盈亏", _format_decimal(cumulative_pnl, 4))
        
        # 输出表格到控制台（使用标准输出，确保在控制台可见）
        console.print()  # 空行分隔
        console.print(table)
        console.print()  # 空行分隔

