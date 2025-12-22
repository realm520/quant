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
                            
                            # 检查今天零点快照是否存在，如果不存在则计算并写入
                            # 注意：今天零点快照的 timestamp = 今天 00:00:00，表示昨天结束时的状态
                            # 例如：如果今天是12月23日，查询 timestamp = 2025-12-23 00:00:00 的快照
                            # 这个快照表示12月22日结束时的状态，作为12月23日的初始持仓
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
                                # 今天零点快照不存在，需要创建
                                # 这个快照表示昨天结束时的状态（例如：如果今天是12月23日，创建12月22日结束时的快照）
                                # 如果昨天没有交易，初始持仓为0
                                logger.info(
                                    f"计算并写入今天零点快照（昨天结束时的状态）",
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    today_date=today,
                                )
                                # 先尝试重建所有快照（会创建到昨天结束时的快照）
                                await self._rebuild_midnight_snapshots(
                                    session=session,
                                    calc=calc,
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol=None,
                                )
                                # 重新查询今日零点快照
                                today_snapshot_result = await session.execute(today_snapshot_query)
                                today_snapshot = today_snapshot_result.scalar_one_or_none()
                                
                                # 如果仍然不存在（例如：昨天没有交易，第一笔交易发生在今天），创建初始持仓为0的快照
                                if not today_snapshot:
                                    logger.info(
                                        f"创建初始持仓为0的今天零点快照（昨天没有交易）",
                                        account_id=account_id,
                                        exchange=exchange_name,
                                        today_date=today,
                                    )
                                    await self._create_empty_midnight_snapshot(
                                        session=session,
                                        account_id=account_id,
                                        exchange=exchange_name,
                                        midnight_timestamp=today_midnight,
                                    )
                                    # 重新查询
                                    today_snapshot_result = await session.execute(today_snapshot_query)
                                    today_snapshot = today_snapshot_result.scalar_one_or_none()
                            
                            # 从今日零点快照读取初始持仓（作为今日计算的起点）
                            today_initial_positions_dict = {}
                            if today_snapshot:
                                # 如果只有一个 symbol 的快照，直接读取
                                # 但通常会有多个 symbol，需要查询所有 symbol 的快照
                                all_today_snapshots_query = (
                                    select(PositionMetrics)
                                    .where(PositionMetrics.account_id == account_id)
                                    .where(PositionMetrics.exchange == exchange_name)
                                    .where(PositionMetrics.timestamp == today_midnight)
                                )
                                all_snapshots_result = await session.execute(all_today_snapshots_query)
                                all_snapshots = all_snapshots_result.scalars().all()
                                
                                for snapshot in all_snapshots:
                                    today_initial_positions_dict[snapshot.symbol] = {
                                        # 从今日零点快照读取收盘持仓，作为今日的初始持仓
                                        "initial_long_qty": snapshot.left_long_qty or Decimal("0"),
                                        "initial_short_qty": snapshot.left_short_qty or Decimal("0"),
                                        "initial_long_value": snapshot.left_long_value or Decimal("0"),
                                        "initial_short_value": snapshot.left_short_value or Decimal("0"),
                                    }
                                
                                logger.debug(
                                    f"从今日零点快照读取初始持仓",
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol_count=len(today_initial_positions_dict),
                                )
                            else:
                                logger.warning(
                                    f"今日零点快照不存在，使用空初始持仓",
                                    account_id=account_id,
                                    exchange=exchange_name,
                                )
                            
                            # 计算今日数据（使用与零点快照相同的逻辑）
                            logger.debug(f"计算今日数据: {start_time} -> {end_time}")
                            
                            # 1. 获取今日的成交统计（使用与零点快照相同的方法，但只查询到当前时间）
                            today_date = start_time.date()
                            today_daily_stats = await calc.get_daily_trade_stats(
                                start_date=today_date,
                                end_date=today_date,
                                symbol=None,  # 所有 symbol
                                end_time=end_time,  # 只查询到当前时间，而不是到 24:00
                            )
                            
                            # 2. 如果今日有成交数据，使用 calc_daily_realized_series 的逻辑计算
                            # 但需要从今日零点快照的状态初始化
                            if today_daily_stats and today_date in today_daily_stats:
                                # 获取今日零点快照的所有 symbol 数据，用于初始化累计值
                                all_today_snapshots_query = (
                                    select(PositionMetrics)
                                    .where(PositionMetrics.account_id == account_id)
                                    .where(PositionMetrics.exchange == exchange_name)
                                    .where(PositionMetrics.timestamp == today_midnight)
                                )
                                all_snapshots_result = await session.execute(all_today_snapshots_query)
                                all_snapshots = all_snapshots_result.scalars().all()
                                
                                # 构建初始累计值（从今日零点快照读取）
                                initial_cumulative = {}
                                for snapshot in all_snapshots:
                                    # 从零点快照反推累计值
                                    # 零点快照的 matched_qty 就是昨日收盘时的轧差
                                    # 零点快照的 left_* 就是昨日收盘持仓
                                    midnight_matched_qty = snapshot.matched_qty or Decimal("0")
                                    midnight_left_long_qty = snapshot.left_long_qty or Decimal("0")
                                    midnight_left_short_qty = snapshot.left_short_qty or Decimal("0")
                                    
                                    # 反推累计买入量和卖出量
                                    # left_long_qty = cumulative_buy_vol - matched_qty
                                    # left_short_qty = cumulative_sell_vol - matched_qty
                                    cumulative_buy_vol = midnight_left_long_qty + midnight_matched_qty
                                    cumulative_sell_vol = midnight_left_short_qty + midnight_matched_qty
                                    
                                    # 从零点快照读取累计市值和平均价格
                                    midnight_long_value = snapshot.long_value or Decimal("0")
                                    midnight_short_value = snapshot.short_value or Decimal("0")
                                    midnight_avg_buy_prz = snapshot.avg_buy_prz or Decimal("0")
                                    midnight_avg_sell_prz = snapshot.avg_sell_prz or Decimal("0")
                                    
                                    initial_cumulative[snapshot.symbol] = {
                                        "cumulative_buy_volume": cumulative_buy_vol,
                                        "cumulative_sell_volume": cumulative_sell_vol,
                                        "cumulative_buy_value": midnight_long_value,
                                        "cumulative_sell_value": midnight_short_value,
                                        "cumulative_realized_pnl": snapshot.cumulative_realized_pnl or Decimal("0"),
                                        "prev_matched_qty": midnight_matched_qty,
                                        "prev_avg_buy_prz": midnight_avg_buy_prz,
                                        "prev_avg_sell_prz": midnight_avg_sell_prz,
                                    }
                                
                                # 使用 calc_daily_realized_series 的逻辑，但从初始累计值开始
                                today_series_result = calc._calc_daily_realized_series_with_initial(
                                    daily_stats={today_date: today_daily_stats.get(today_date, {})},
                                    initial_cumulative=initial_cumulative,
                                )
                                
                                # 转换为与 calculate_positions_by_symbol 相同的格式
                                today_metrics = {}
                                if today_date in today_series_result:
                                    for symbol, metrics in today_series_result[today_date].items():
                                        # 获取收盘价
                                        close_prices = await calc._get_close_prices(start_time, end_time, symbol)
                                        close_prz = close_prices.get(symbol, Decimal("0"))
                                        
                                        # 计算未实现盈亏
                                        left_long_qty = metrics.get("close_left_long_qty", Decimal("0"))
                                        left_short_qty = metrics.get("close_left_short_qty", Decimal("0"))
                                        avg_buy_prz = metrics.get("avg_buy_prz", Decimal("0"))
                                        avg_sell_prz = metrics.get("avg_sell_prz", Decimal("0"))
                                        unrealized_pnl = Decimal("0")
                                        if close_prz > 0:
                                            unrealized_pnl = (
                                                left_long_qty * (close_prz - avg_buy_prz) +
                                                left_short_qty * (avg_sell_prz - close_prz)
                                            )
                                        
                                        today_metrics[symbol] = {
                                            "buy_volume": metrics.get("daily_buy_volume", Decimal("0")),
                                            "sell_volume": metrics.get("daily_sell_volume", Decimal("0")),
                                            "buy_trade_value": metrics.get("daily_buy_value", Decimal("0")),
                                            "sell_trade_value": metrics.get("daily_sell_value", Decimal("0")),
                                            "long_qty": metrics.get("total_long_qty", Decimal("0")),
                                            "short_qty": metrics.get("total_short_qty", Decimal("0")),
                                            "long_value": metrics.get("total_long_value", Decimal("0")),
                                            "short_value": metrics.get("total_short_value", Decimal("0")),
                                            "avg_buy_prz": avg_buy_prz,
                                            "avg_sell_prz": avg_sell_prz,
                                            "matched_qty": metrics.get("matched_qty", Decimal("0")),
                                            "left_long_qty": left_long_qty,
                                            "left_short_qty": left_short_qty,
                                            "left_long_value": metrics.get("close_left_long_value", Decimal("0")),
                                            "left_short_value": metrics.get("close_left_short_value", Decimal("0")),
                                            "close_prz": close_prz,
                                            "unrealized_pnl": unrealized_pnl,
                                            "daily_realized_pnl": metrics.get("daily_realized_pnl", Decimal("0")),
                                            "cumulative_realized_pnl": metrics.get("cumulative_realized_pnl", Decimal("0")),
                                        }
                            else:
                                # 如果今日没有成交数据，使用空结果
                                today_metrics = {}
                            
                            symbol_count = len([k for k in today_metrics.keys() if k != "TOTAL"])
                            logger.info(f"账号 {account_id} 找到 {symbol_count} 个交易对")
                            
                            if symbol_count ==  0:
                                logger.warning(f"账号 {account_id} 没有找到交易对数据，跳过")
                                continue
                            
                            # 存储每个交易对的指标
                            for symbol_key, m in today_metrics.items():
                                if symbol_key == "TOTAL":
                                    continue
                                
                                # 从今日零点快照读取昨日收盘时的数据（作为计算基准和显示）
                                today_midnight = datetime.combine(start_time.date(), datetime.min.time()).replace(tzinfo=None)
                                midnight_snapshot_query = (
                                    select(PositionMetrics)
                                    .where(PositionMetrics.account_id == account_id)
                                    .where(PositionMetrics.exchange == exchange_name)
                                    .where(PositionMetrics.symbol == symbol_key)
                                    .where(PositionMetrics.timestamp == today_midnight)
                                    .limit(1)
                                )
                                midnight_result = await session.execute(midnight_snapshot_query)
                                midnight_snapshot = midnight_result.scalar_one_or_none()
                                
                                # 从今日零点快照读取昨日收盘时的轧差和累计已实现盈亏
                                midnight_matched_qty = Decimal("0")
                                cumulative_realized_pnl_at_midnight = Decimal("0")
                                if midnight_snapshot:
                                    midnight_matched_qty = midnight_snapshot.matched_qty or Decimal("0")
                                    cumulative_realized_pnl_at_midnight = midnight_snapshot.cumulative_realized_pnl or Decimal("0")
                                else:
                                    logger.warning(
                                        f"今日零点快照不存在，使用 0 作为基准值",
                                        account_id=account_id,
                                        exchange=exchange_name,
                                        symbol=symbol_key,
                                    )
                                
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
                                today_realized_pnl = m.get("daily_realized_pnl", Decimal("0"))
                                # 当前时刻的累积已实现盈亏 = 零点快照的累积已实现 + 今日新增的已实现
                                cumulative_realized_pnl_now = cumulative_realized_pnl_at_midnight + today_realized_pnl
                                
                                # 累计 PnL = 累积已实现盈亏 + 当前未实现盈亏
                                cumulative_pnl = cumulative_realized_pnl_now + today_unrealized_pnl
                                
                                # 在控制台输出详细指标（使用表格格式）
                                logger.info(f"计算完成: {account_id} - {exchange_name} - {symbol_key}")
                                # 创建一个修改后的 today_m，使用正确的今日新增已实现盈亏和开盘初始仓位
                                today_m_corrected = m.copy()
                                today_m_corrected["realized_pnl"] = today_realized_pnl
                                today_m_corrected["daily_pnl"] = today_realized_pnl + today_unrealized_pnl
                                today_m_corrected["cumulative_realized_pnl"] = cumulative_realized_pnl_now  # 累计已实现盈亏
                                if midnight_snapshot:
                                    # 今日的初始仓位 = 今日零点快照的收盘仓位（昨日收盘）
                                    today_m_corrected["initial_long_qty"] = midnight_snapshot.left_long_qty or Decimal("0")
                                    today_m_corrected["initial_short_qty"] = midnight_snapshot.left_short_qty or Decimal("0")
                                    today_m_corrected["initial_long_value"] = midnight_snapshot.left_long_value or Decimal("0")
                                    today_m_corrected["initial_short_value"] = midnight_snapshot.left_short_value or Decimal("0")
                                
                                # 从今日零点快照构建昨日数据显示（用于日志）
                                yesterday_m_for_display = {}
                                if midnight_snapshot:
                                    yesterday_m_for_display = {
                                        "left_long_qty": midnight_snapshot.left_long_qty or Decimal("0"),
                                        "left_short_qty": midnight_snapshot.left_short_qty or Decimal("0"),
                                        "left_long_value": midnight_snapshot.left_long_value or Decimal("0"),
                                        "left_short_value": midnight_snapshot.left_short_value or Decimal("0"),
                                        "avg_buy_prz": midnight_snapshot.avg_buy_prz or Decimal("0"),  # 昨日平均买价
                                        "avg_sell_prz": midnight_snapshot.avg_sell_prz or Decimal("0"),  # 昨日平均卖价
                                        "cumulative_realized_pnl": cumulative_realized_pnl_at_midnight,  # 昨日累计已实现盈亏
                                    }
                                
                                
                                
                                # 创建指标记录
                                # 开盘持仓从今日零点快照读取（今日零点快照的 left_* 就是昨日收盘持仓，即今日开盘持仓）
                                open_left_long_qty_from_snapshot = midnight_snapshot.left_long_qty if midnight_snapshot else Decimal("0")
                                open_left_short_qty_from_snapshot = midnight_snapshot.left_short_qty if midnight_snapshot else Decimal("0")
                                open_left_long_value_from_snapshot = midnight_snapshot.left_long_value if midnight_snapshot else Decimal("0")
                                open_left_short_value_from_snapshot = midnight_snapshot.left_short_value if midnight_snapshot else Decimal("0")
                                
                                metrics_record = PositionMetrics(
                                    timestamp=end_time,
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol=symbol_key,
                                    
                                    # 1. 开盘持仓（从今日零点快照读取，即昨日收盘持仓）
                                    open_left_long_qty=open_left_long_qty_from_snapshot,
                                    open_left_short_qty=open_left_short_qty_from_snapshot,
                                    open_left_long_value=open_left_long_value_from_snapshot,
                                    open_left_short_value=open_left_short_value_from_snapshot,
                                    
                                    # 2. 当日成交量
                                    daily_sum_buy_qty=m.get("buy_volume", Decimal("0")),
                                    daily_sum_sell_qty=m.get("sell_volume", Decimal("0")),
                                    daily_sum_buy_value=m.get("buy_trade_value", Decimal("0")),
                                    daily_sum_sell_value=m.get("sell_trade_value", Decimal("0")),
                                    # 3. 总持仓（初始持仓 + 当日成交量）
                                    long_qty=m.get("long_qty", Decimal("0")),
                                    short_qty=m.get("short_qty", Decimal("0")),
                                    long_value=m.get("long_value", Decimal("0")),
                                    short_value=m.get("short_value", Decimal("0")),
                                    avg_buy_prz=m.get("avg_buy_prz", Decimal("0")),
                                    avg_sell_prz=m.get("avg_sell_prz", Decimal("0")),
                                    
                                    # 4. 轧差和已实现盈亏
                                    matched_qty=m.get("matched_qty", Decimal("0")),
                                    daily_realized_pnl=today_realized_pnl,
                                    cumulative_realized_pnl=cumulative_realized_pnl_now,
                                    
                                    # 5. 收盘持仓（当日剩余仓位）
                                    left_long_qty=m.get("left_long_qty", Decimal("0")),
                                    left_short_qty=m.get("left_short_qty", Decimal("0")),
                                    left_long_value=m.get("left_long_value", Decimal("0")),
                                    left_short_value=m.get("left_short_value", Decimal("0")),
                                    close_prz=m.get("close_prz", Decimal("0")),
                                    unrealized_pnl=today_unrealized_pnl,
                                    
                                    # 6. PnL 汇总
                                    daily_pnl=today_realized_pnl + today_unrealized_pnl,
                                    cumulative_pnl=cumulative_pnl,
                                )

                                self._log_metrics_table(
                                    account_id=account_id,
                                    exchange=exchange_name,
                                    symbol=symbol_key,
                                    yesterday_m=yesterday_m_for_display,
                                    today_m=today_m_corrected,
                                    cumulative_pnl=cumulative_pnl,
                                )
                                session.add(metrics_record)
                                
                                # 更新 Prometheus metrics
                                labels = {
                                    "account_id": account_id,
                                    "exchange": exchange_name,
                                    "symbol": symbol_key,
                                }
                                
                                # 从今日零点快照读取昨日收盘持仓（用于 Prometheus metrics）
                                position_pre_long_qty.labels(**labels).set(float(open_left_long_qty_from_snapshot))
                                position_pre_short_qty.labels(**labels).set(float(open_left_short_qty_from_snapshot))
                                position_pre_long_value.labels(**labels).set(float(open_left_long_value_from_snapshot))
                                position_pre_short_value.labels(**labels).set(float(open_left_short_value_from_snapshot))
                                
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
            # 重要：只创建到 latest_date 结束时的快照，不创建未来日期的快照
            # 例如：如果 latest_date = 12月22日，创建 12月22日结束时的快照（12月23日 00:00）
            # 如果 latest_date = 12月23日（今天），不创建 12月23日结束时的快照（12月24日 00:00），因为12月23日还没有结束
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            
            # 计算今天日期（UTC）
            today_utc = datetime.utcnow().date()
            
            for trade_date, day_data in sorted(daily_series.items()):
                # 如果 trade_date 是今天，跳过创建今天的快照（因为今天还没有结束）
                # 今天的快照应该在换日时创建
                if trade_date == today_utc:
                    logger.debug(
                        f"跳过今天的快照创建（将在换日时创建）: trade_date={trade_date}, today={today_utc}",
                        account_id=account_id,
                        exchange=exchange,
                        symbol=symbol,
                    )
                    continue
                
                # 零点 timestamp = trade_date 的下一天 00:00（即该日结束时的快照）
                midnight_timestamp = datetime.combine(trade_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)
                
                for sym, metrics in day_data.items():
                    # 获取前一日收盘持仓（作为今日开盘持仓）
                    prev_date = trade_date - timedelta(days=1)
                    prev_day_data = daily_series.get(prev_date, {})
                    prev_metrics = prev_day_data.get(sym, {})
                    
                    # 如果前一日没有数据，初始持仓为0（例如：第一笔交易发生在今天）
                    if not prev_metrics:
                        logger.debug(
                            f"前一日没有数据，使用空初始持仓: trade_date={trade_date}, symbol={sym}",
                            account_id=account_id,
                            exchange=exchange,
                        )
                    
                    # 获取当日最后一笔成交价（用于未实现盈亏）
                    day_end = datetime.combine(trade_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=None)
                    day_start = datetime.combine(trade_date, datetime.min.time()).replace(tzinfo=None)
                    close_prices = await calc._get_close_prices(day_start, day_end, sym)
                    close_prz = close_prices.get(sym, Decimal("0"))
                    
                    # 计算未实现盈亏（用收盘持仓 + 最后成交价）
                    unrealized_pnl = Decimal("0")
                    if close_prz > 0:
                        left_long_qty = metrics.get("close_left_long_qty", Decimal("0"))
                        left_short_qty = metrics.get("close_left_short_qty", Decimal("0"))
                        avg_buy_prz = metrics.get("avg_buy_prz", Decimal("0"))
                        avg_sell_prz = metrics.get("avg_sell_prz", Decimal("0"))
                        unrealized_pnl = (
                            left_long_qty * (close_prz - avg_buy_prz) +
                            left_short_qty * (avg_sell_prz - close_prz)
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
                        # 1. 开盘持仓（昨收持仓）
                        open_left_long_qty=metrics.get("open_left_long_qty", Decimal("0")),
                        open_left_short_qty=metrics.get("open_left_short_qty", Decimal("0")),
                        open_left_long_value=metrics.get("open_left_long_value", Decimal("0")),
                        open_left_short_value=metrics.get("open_left_short_value", Decimal("0")),
                        # 2. 当日成交量
                        daily_sum_buy_qty=metrics.get("daily_buy_volume", Decimal("0")),
                        daily_sum_sell_qty=metrics.get("daily_sell_volume", Decimal("0")),
                        daily_sum_buy_value=metrics.get("daily_buy_value", Decimal("0")),
                        daily_sum_sell_value=metrics.get("daily_sell_value", Decimal("0")),
                        # 3. 总持仓（初始持仓 + 当日成交量）
                        long_qty=metrics.get("total_long_qty", Decimal("0")),
                        short_qty=metrics.get("total_short_qty", Decimal("0")),
                        long_value=metrics.get("total_long_value", Decimal("0")),
                        short_value=metrics.get("total_short_value", Decimal("0")),
                        # 4. 平均价格
                        avg_buy_prz=metrics.get("avg_buy_prz", Decimal("0")),
                        avg_sell_prz=metrics.get("avg_sell_prz", Decimal("0")),
                        # 5. 轧差和已实现盈亏
                        matched_qty=metrics.get("matched_qty", Decimal("0")),
                        daily_realized_pnl=daily_realized_pnl,
                        cumulative_realized_pnl=cumulative_realized_pnl,
                        # 6. 收盘持仓
                        left_long_qty=metrics.get("close_left_long_qty", Decimal("0")),  # 从 calc_daily_realized_series 返回的 close_left_* key 获取
                        left_short_qty=metrics.get("close_left_short_qty", Decimal("0")),
                        left_long_value=metrics.get("close_left_long_value", Decimal("0")),
                        left_short_value=metrics.get("close_left_short_value", Decimal("0")),
                        # 7. 收盘价和未实现盈亏
                        close_prz=close_prz,
                        unrealized_pnl=unrealized_pnl,
                        # 8. PnL 汇总
                        daily_pnl=daily_pnl,
                        cumulative_pnl=cumulative_pnl,
                        created_at=datetime.utcnow(),
                    )
                    
                    # ON CONFLICT: 如果 (timestamp, account_id, exchange, symbol) 已存在，则更新所有字段
                    # 使用 index_elements 指定唯一索引的列
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["timestamp", "account_id", "exchange", "symbol"],
                        set_={
                            "open_left_long_qty": stmt.excluded.open_left_long_qty,
                            "open_left_short_qty": stmt.excluded.open_left_short_qty,
                            "open_left_long_value": stmt.excluded.open_left_long_value,
                            "open_left_short_value": stmt.excluded.open_left_short_value,
                            "daily_sum_buy_qty": stmt.excluded.daily_sum_buy_qty,
                            "daily_sum_sell_qty": stmt.excluded.daily_sum_sell_qty,
                            "daily_sum_buy_value": stmt.excluded.daily_sum_buy_value,
                            "daily_sum_sell_value": stmt.excluded.daily_sum_sell_value,
                            "long_qty": stmt.excluded.long_qty,
                            "short_qty": stmt.excluded.short_qty,
                            "long_value": stmt.excluded.long_value,
                            "short_value": stmt.excluded.short_value,
                            "avg_buy_prz": stmt.excluded.avg_buy_prz,
                            "avg_sell_prz": stmt.excluded.avg_sell_prz,
                            "matched_qty": stmt.excluded.matched_qty,
                            "daily_realized_pnl": stmt.excluded.daily_realized_pnl,
                            "cumulative_realized_pnl": stmt.excluded.cumulative_realized_pnl,
                            "left_long_qty": stmt.excluded.left_long_qty,
                            "left_short_qty": stmt.excluded.left_short_qty,
                            "left_long_value": stmt.excluded.left_long_value,
                            "left_short_value": stmt.excluded.left_short_value,
                            "close_prz": stmt.excluded.close_prz,
                            "unrealized_pnl": stmt.excluded.unrealized_pnl,
                            "daily_pnl": stmt.excluded.daily_pnl,
                            "cumulative_pnl": stmt.excluded.cumulative_pnl,
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
    
    async def _create_empty_midnight_snapshot(
        self,
        session: AsyncSession,
        account_id: str,
        exchange: str,
        midnight_timestamp: datetime,
    ) -> None:
        """创建初始持仓为0的零点快照（用于昨天没有交易的情况）.
        
        例如：如果今天是12月23日，昨天（12月22日）没有交易，但今天有交易，
        为今天有交易的所有 symbol 创建初始持仓为0的快照（timestamp = 12月23日 00:00:00）。
        
        Args:
            session: 数据库会话
            account_id: 账号ID
            exchange: 交易所
            midnight_timestamp: 零点时间戳（例如：2025-12-23 00:00:00）
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy import cast, Date, func
        
        try:
            # 查询今天有交易的所有 symbol（快照表示昨天结束时的状态，所以查询今天的交易）
            today_date = midnight_timestamp.date()  # 快照的日期（例如：12月23日）
            if exchange == "binance":
                from tri_arb.storage.models import TradeUpdate
                TradeModel = TradeUpdate
                time_column = TradeModel.transaction_time
            else:
                from tri_arb.storage.xt_websocket_models import XTTradeUpdate
                TradeModel = XTTradeUpdate
                time_column = TradeModel.update_time
            
            symbols_query = (
                select(TradeModel.symbol.distinct())
                .where(cast(time_column, Date) == today_date)
            )
            
            if exchange == "binance":
                symbols_query = symbols_query.where(TradeModel.exchange == "binance_perp")
            if account_id:
                symbols_query = symbols_query.where(TradeModel.account_id == account_id)
            
            symbols_result = await session.execute(symbols_query)
            symbols = [row[0] for row in symbols_result.all()]
            
            if not symbols:
                logger.debug(
                    f"今天没有交易，不需要创建空快照",
                    account_id=account_id,
                    exchange=exchange,
                    midnight_timestamp=midnight_timestamp,
                )
                return
            
            # 为每个 symbol 创建初始持仓为0的快照
            for sym in symbols:
                stmt = pg_insert(PositionMetrics).values(
                    timestamp=midnight_timestamp,
                    account_id=account_id,
                    exchange=exchange,
                    symbol=sym,
                    # 所有字段都初始化为0
                    open_left_long_qty=Decimal("0"),
                    open_left_short_qty=Decimal("0"),
                    open_left_long_value=Decimal("0"),
                    open_left_short_value=Decimal("0"),
                    daily_sum_buy_qty=Decimal("0"),
                    daily_sum_sell_qty=Decimal("0"),
                    daily_sum_buy_value=Decimal("0"),
                    daily_sum_sell_value=Decimal("0"),
                    long_qty=Decimal("0"),
                    short_qty=Decimal("0"),
                    long_value=Decimal("0"),
                    short_value=Decimal("0"),
                    avg_buy_prz=Decimal("0"),
                    avg_sell_prz=Decimal("0"),
                    matched_qty=Decimal("0"),
                    daily_realized_pnl=Decimal("0"),
                    cumulative_realized_pnl=Decimal("0"),
                    left_long_qty=Decimal("0"),
                    left_short_qty=Decimal("0"),
                    left_long_value=Decimal("0"),
                    left_short_value=Decimal("0"),
                    close_prz=Decimal("0"),
                    unrealized_pnl=Decimal("0"),
                    daily_pnl=Decimal("0"),
                    cumulative_pnl=Decimal("0"),
                    created_at=datetime.utcnow(),
                )
                
                stmt = stmt.on_conflict_do_update(
                    index_elements=["timestamp", "account_id", "exchange", "symbol"],
                    set_={
                        "open_left_long_qty": stmt.excluded.open_left_long_qty,
                        "open_left_short_qty": stmt.excluded.open_left_short_qty,
                        "open_left_long_value": stmt.excluded.open_left_long_value,
                        "open_left_short_value": stmt.excluded.open_left_short_value,
                        "created_at": stmt.excluded.created_at,
                    }
                )
                
                await session.execute(stmt)
            
            await session.commit()
            logger.info(
                f"创建初始持仓为0的零点快照",
                account_id=account_id,
                exchange=exchange,
                midnight_timestamp=midnight_timestamp,
                symbol_count=len(symbols),
            )
            
        except Exception as e:
            logger.error(
                f"创建空快照失败",
                account_id=account_id,
                exchange=exchange,
                midnight_timestamp=midnight_timestamp,
                error=str(e),
            )
            await session.rollback()
            raise
    
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
        
        # 获取计算过程中的中间变量（部分字段在不同计算路径下可能不存在，这里做兼容处理）
        initial_long_qty = today_m.get("initial_long_qty", Decimal("0"))
        initial_short_qty = today_m.get("initial_short_qty", Decimal("0"))
        initial_long_value = today_m.get("initial_long_value", Decimal("0"))
        initial_short_value = today_m.get("initial_short_value", Decimal("0"))
        buy_volume = today_m.get("buy_volume", Decimal("0"))
        sell_volume = today_m.get("sell_volume", Decimal("0"))
        buy_trade_value = today_m.get("buy_trade_value", Decimal("0"))
        sell_trade_value = today_m.get("sell_trade_value", Decimal("0"))
        long_qty = today_m.get("long_qty", Decimal("0"))
        short_qty = today_m.get("short_qty", Decimal("0"))
        long_value = today_m.get("long_value", Decimal("0"))
        short_value = today_m.get("short_value", Decimal("0"))

        avg_buy_prz = today_m.get("avg_buy_prz", Decimal("0"))
        avg_sell_prz = today_m.get("avg_sell_prz", Decimal("0"))
        matched_qty = today_m.get("matched_qty", Decimal("0"))
        daily_realized_pnl = today_m.get("daily_realized_pnl", Decimal("0"))
        realized_pnl = today_m.get("realized_pnl", Decimal("0"))
        left_long_qty = today_m.get("left_long_qty", Decimal("0"))
        left_short_qty = today_m.get("left_short_qty", Decimal("0"))
        close_prz = today_m.get("close_prz", Decimal("0"))
        unrealized_pnl = today_m.get("unrealized_pnl", Decimal("0"))
        daily_pnl = today_m.get("daily_pnl", daily_realized_pnl + unrealized_pnl)

        # 昨日数据（来自零点快照）
        yesterday_left_long_qty = yesterday_m.get("left_long_qty", Decimal("0"))
        yesterday_left_short_qty = yesterday_m.get("left_short_qty", Decimal("0"))
        yesterday_left_long_value = yesterday_m.get("left_long_value", Decimal("0"))
        yesterday_left_short_value = yesterday_m.get("left_short_value", Decimal("0"))
        yesterday_avg_buy_prz = yesterday_m.get("avg_buy_prz", Decimal("0"))
        yesterday_avg_sell_prz = yesterday_m.get("avg_sell_prz", Decimal("0"))
        yesterday_cumulative_realized_pnl = yesterday_m.get("cumulative_realized_pnl", Decimal("0"))

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
        table.add_row("  昨日多头持仓量 (pre_long_qty)", _format_decimal(yesterday_left_long_qty, 2))
        table.add_row("  昨日空头持仓量 (pre_short_qty)", _format_decimal(yesterday_left_short_qty, 2))
        table.add_row("  昨日多头市值 (pre_long_value)", _format_decimal(yesterday_left_long_value, 4))
        table.add_row("  昨日空头市值 (pre_short_value)", _format_decimal(yesterday_left_short_value, 4))
        if yesterday_avg_buy_prz > 0:
            table.add_row("  昨日平均买价 (昨日avg_buy_prz)", _format_decimal(yesterday_avg_buy_prz, 8))
        if yesterday_avg_sell_prz > 0:
            table.add_row("  昨日平均卖价 (昨日avg_sell_prz)", _format_decimal(yesterday_avg_sell_prz, 8))
        table.add_row("", "")

        # 2. 今日交易
        table.add_row("[bold yellow]--- 2. 今日交易 ---[/bold yellow]", "")
        table.add_row(
            "  买入成交量 (sum(buy_vol))",
            _format_decimal(buy_volume, 2),
        )
        table.add_row(
            "  卖出成交量 (sum(sell_vol))",
            _format_decimal(sell_volume, 2),
        )
        table.add_row(
            "  初始多头持仓量 (initial_long_qty)",
            _format_decimal(initial_long_qty, 2),
        )
        table.add_row(
            "  初始空头持仓量 (initial_short_qty)",
            _format_decimal(initial_short_qty, 2),
        )
        table.add_row(
            "  多头总持仓量 long_qty = initial_long_qty + buy_volume",
            f"{_format_decimal_no_comma(initial_long_qty, 2)} + {_format_decimal_no_comma(buy_volume, 2)} = {_format_decimal_no_comma(long_qty, 2)}",
        )
        table.add_row(
            "  空头总持仓量 short_qty = initial_short_qty + sell_volume",
            f"{_format_decimal_no_comma(initial_short_qty, 2)} + {_format_decimal_no_comma(sell_volume, 2)} = {_format_decimal_no_comma(short_qty, 2)}",
        )
        table.add_row(
            "  买入成交市值 (sum(buy_vol * buy_price))",
            _format_decimal(buy_trade_value, 4),
        )
        table.add_row(
            "  卖出成交市值 (sum(sell_vol * sell_price))",
            _format_decimal(sell_trade_value, 4),
        )
        table.add_row(
            "  多头总市值 long_value",
            _format_decimal(long_value, 4),
        )
        table.add_row(
            "  空头总市值 short_value",
            _format_decimal(short_value, 4),
        )
        table.add_row(
            "  买入平均价格 avg_buy_prz = long_value / long_qty",
            _format_decimal(avg_buy_prz, 8),
        )
        table.add_row(
            "  卖出平均价格 avg_sell_prz = short_value / short_qty",
            _format_decimal(avg_sell_prz, 8),
        )
        table.add_row("", "")

        # 3. 已实现 PnL
        table.add_row("[bold yellow]--- 3. 已实现 PnL ---[/bold yellow]", "")
        table.add_row(
            "  轧差数量 matched_qty = min(long_qty, short_qty)",
            _format_decimal(matched_qty, 2),
        )
        table.add_row(
            "  当日已实现盈亏 (daily_realized_pnl)",
            _format_decimal(daily_realized_pnl, 4),
        )
        if matched_qty > 0 and avg_buy_prz > 0 and avg_sell_prz > 0:
            table.add_row(
                "  公式: daily_realized_pnl = (avg_sell_prz - avg_buy_prz) * matched_qty",
                f"({_format_decimal_no_comma(avg_sell_prz, 8)} - {_format_decimal_no_comma(avg_buy_prz, 8)}) * {_format_decimal_no_comma(matched_qty, 2)} = {_format_decimal_no_comma(daily_realized_pnl, 4)}",
            )
        table.add_row("", "")

        # 4. 当日剩余仓位
        table.add_row("[bold yellow]--- 4. 当日剩余仓位 ---[/bold yellow]", "")
        table.add_row(
            "  日内多头剩余持仓 left_long_qty = long_qty - matched_qty",
            f"{_format_decimal_no_comma(long_qty, 2)} - {_format_decimal_no_comma(matched_qty, 2)} = {_format_decimal_no_comma(left_long_qty, 2)}",
        )
        table.add_row(
            "  日内空头剩余持仓 left_short_qty = short_qty - matched_qty",
            f"{_format_decimal_no_comma(short_qty, 2)} - {_format_decimal_no_comma(matched_qty, 2)} = {_format_decimal_no_comma(left_short_qty, 2)}",
        )
        table.add_row(
            "  多头剩余市值 (left_long_value)",
            _format_decimal(today_m.get("left_long_value", Decimal("0")), 4),
        )
        table.add_row(
            "  空头剩余市值 (left_short_value)",
            _format_decimal(today_m.get("left_short_value", Decimal("0")), 4),
        )
        table.add_row(
            "  当日最后一笔成交价 (close_prz)",
            _format_decimal(close_prz, 8),
        )
        table.add_row(
            "  日内未实现盈亏 (unrealized_pnl)",
            _format_decimal(unrealized_pnl, 4),
        )
        table.add_row("", "")

        # 5. PnL 汇总
        table.add_row("[bold yellow]--- 5. PnL 汇总 ---[/bold yellow]", "")
        table.add_row(
            "  单日已实现盈亏 (realized_pnl)",
            _format_decimal(realized_pnl, 4),
        )
        table.add_row(
            "  单日 PnL = 当日已实现 + 当日未实现 (daily_pnl)",
            _format_decimal(daily_pnl, 4),
        )
        table.add_row(
            "  累计 PnL (cumulative_pnl)",
            _format_decimal(cumulative_pnl, 4),
        )

        # 输出表格到控制台（使用标准输出，确保在控制台可见）
        console.print()  # 空行分隔
        console.print(table)
        console.print()  # 空行分隔

