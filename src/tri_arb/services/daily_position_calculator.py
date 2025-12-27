"""每日持仓量计算服务.

用于计算币安和XT的昨日持仓量和市值：
- 昨日多头持仓量 = 区间内所有买单的成交量 + 之前遗留的未平仓的买单
- 昨日空头持仓量 = 区间内所有卖单的成交量 + 之前遗留的未平仓的卖单
- 昨日多头市值 = 每笔买单市值累加 + 前日遗留的多头市值
- 昨日空头市值 = 每笔卖单市值累加 + 前日遗留的空头市值
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional, List, Callable

from tri_arb.config.logging import get_logger
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.storage.database import DatabaseManager

logger = get_logger(__name__)


class DailyPositionCalculator:
    """每日持仓量计算器.

    用于计算币安和XT的昨日持仓量和市值。
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        contract_multiplier_getter: Optional[Callable[[str, str], Decimal]] = None,
        contract_multiplier_service: Optional[ContractMultiplierService] = None,
    ):
        """初始化每日持仓量计算器.

        Args:
            db_manager: 数据库管理器
            contract_multiplier_getter: 获取合约乘数的函数，接收 (exchange, symbol) 参数，返回合约乘数（Decimal）
                                       如果不提供，默认使用 1
        """
        self.db_manager = db_manager
        # 如果调用方提供了自定义函数，则优先使用；否则使用默认的服务实现
        if contract_multiplier_getter is not None:
            self._contract_multiplier_getter = contract_multiplier_getter
            self._multiplier_service: Optional[ContractMultiplierService] = None
        else:
            # 使用注入的服务或创建默认服务
            self._multiplier_service = (
                contract_multiplier_service or ContractMultiplierService()
            )

            async def _default_getter(exchange: str, symbol: str) -> Decimal:
                return await self._multiplier_service.get_multiplier(exchange, symbol)

            # 这里保存一个异步函数引用，方便在内部调用时封装成同步接口
            self._contract_multiplier_getter = _default_getter  # type: ignore[assignment]

    async def _get_multiplier(self, exchange: str, symbol: str) -> Decimal:
        """内部统一入口：获取合约乘数."""
        getter = self._contract_multiplier_getter
        # 如果是异步函数（默认服务），直接 await
        if callable(getter) and getattr(getter, "__code__", None) and "await" in getter.__code__.co_names:  # type: ignore[attr-defined]
            return await getter(exchange, symbol)  # type: ignore[misc]
        # 否则认为是同步函数
        return getter(exchange, symbol)  # type: ignore[misc]

    async def calculate_daily_positions(
        self,
        target_date: Optional[datetime] = None,
        hours_back: int = 24,
        account_ids: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Dict[str, Decimal]]:
        """计算昨日持仓量和市值.

        Args:
            target_date: 目标日期（UTC时间），如果为None则使用当前时间减去hours_back小时
            hours_back: 往前回溯的小时数（默认24小时，即昨日）
            account_ids: 账号ID字典，格式为 {"binance": ["binance_main_001", ...], "xt": ["xt_main_001", ...]}
                        如果不提供，则统计所有账号

        Returns:
            字典，格式为:
            {
                "binance": {
                    "pre_long_qty": Decimal,
                    "pre_short_qty": Decimal,
                    "pre_long_value": Decimal,
                    "pre_short_value": Decimal,
                    "buy_volume": Decimal,
                    "sell_volume": Decimal,
                    "initial_long_qty": Decimal,
                    "initial_short_qty": Decimal,
                },
                "xt": {
                    ...
                },
                "total": {
                    "pre_long_qty": Decimal,  # binance + xt
                    "pre_short_qty": Decimal,
                    "pre_long_value": Decimal,
                    "pre_short_value": Decimal,
                }
            }
        """
        # 统一使用 UTC+0 的“昨日自然日”时间段：
        # [yesterday 00:00, yesterday 24:00)
        if target_date is None:
            # 以当前 UTC 日期为基准，回退 1 天
            today_utc = datetime.utcnow().date()
            start_time = datetime(
                today_utc.year, today_utc.month, today_utc.day
            ) - timedelta(days=1)
        else:
            # 如果调用方显式传入 target_date，则取其 UTC 日期的 00:00 作为起点
            date_utc = target_date.date()
            start_time = datetime(date_utc.year, date_utc.month, date_utc.day)

        end_time = start_time + timedelta(days=1)

        results = {
            "binance": {
                "pre_long_qty": Decimal("0"),
                "pre_short_qty": Decimal("0"),
                "pre_long_value": Decimal("0"),
                "pre_short_value": Decimal("0"),
                "buy_volume": Decimal("0"),
                "sell_volume": Decimal("0"),
                "initial_long_qty": Decimal("0"),
                "initial_short_qty": Decimal("0"),
            },
            "xt": {
                "pre_long_qty": Decimal("0"),
                "pre_short_qty": Decimal("0"),
                "pre_long_value": Decimal("0"),
                "pre_short_value": Decimal("0"),
                "buy_volume": Decimal("0"),
                "sell_volume": Decimal("0"),
                "initial_long_qty": Decimal("0"),
                "initial_short_qty": Decimal("0"),
            },
        }

        async with self.db_manager.session() as session:
            # 计算 Binance 持仓
            binance_account_ids = (
                account_ids.get("binance", [None]) if account_ids else [None]
            )
            for account_id in binance_account_ids:
                try:
                    calculator = PositionCalculator(
                        session,
                        exchange="binance",
                        account_id=account_id,
                        contract_multiplier_getter=lambda s: Decimal("1"),
                    )

                    metrics = await calculator.calculate_position_from_trades(
                        start_time=start_time, end_time=end_time, symbol=None
                    )

                    # 累加结果
                    for key in results["binance"]:
                        results["binance"][key] += metrics.get(key, Decimal("0"))

                    logger.info(
                        f"Calculated Binance positions for account {account_id}",
                        **{k: str(v) for k, v in metrics.items()},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to calculate Binance positions for account {account_id}: {e}"
                    )

            # 计算 XT 持仓
            xt_account_ids = account_ids.get("xt", [None]) if account_ids else [None]
            for account_id in xt_account_ids:
                try:
                    calculator = PositionCalculator(
                        session,
                        exchange="xt",
                        account_id=account_id,
                        # 对于 XT，从合约乘数服务获取
                        contract_multiplier_getter=lambda s: Decimal("1"),
                    )

                    metrics = await calculator.calculate_position_from_trades(
                        start_time=start_time, end_time=end_time, symbol=None
                    )

                    # 累加结果
                    for key in results["xt"]:
                        results["xt"][key] += metrics.get(key, Decimal("0"))

                    logger.info(
                        f"Calculated XT positions for account {account_id}",
                        **{k: str(v) for k, v in metrics.items()},
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to calculate XT positions for account {account_id}: {e}"
                    )

        # 计算总计
        results["total"] = {
            "pre_long_qty": results["binance"]["pre_long_qty"]
            + results["xt"]["pre_long_qty"],
            "pre_short_qty": results["binance"]["pre_short_qty"]
            + results["xt"]["pre_short_qty"],
            "pre_long_value": results["binance"]["pre_long_value"]
            + results["xt"]["pre_long_value"],
            "pre_short_value": results["binance"]["pre_short_value"]
            + results["xt"]["pre_short_value"],
        }

        logger.info(
            "Calculated daily positions",
            target_date=target_date.isoformat(),
            hours_back=hours_back,
            binance_long_qty=str(results["binance"]["pre_long_qty"]),
            binance_short_qty=str(results["binance"]["pre_short_qty"]),
            xt_long_qty=str(results["xt"]["pre_long_qty"]),
            xt_short_qty=str(results["xt"]["pre_short_qty"]),
            total_long_qty=str(results["total"]["pre_long_qty"]),
            total_short_qty=str(results["total"]["pre_short_qty"]),
        )

        return results

    async def calculate_daily_positions_for_accounts(
        self,
        accounts_config: Dict[str, List[Dict]],
        target_date: Optional[datetime] = None,
        hours_back: int = 24,
    ) -> Dict[str, Dict[str, Decimal]]:
        """根据账号配置计算昨日持仓量和市值.

        Args:
            accounts_config: 账号配置字典，格式为 {"binance": [...], "xt": [...]}
            target_date: 目标日期（UTC时间），如果为None则使用当前时间减去hours_back小时
            hours_back: 往前回溯的小时数（默认24小时，即昨日）

        Returns:
            同 calculate_daily_positions
        """
        # 提取账号ID
        account_ids = {}
        for exchange in ["binance", "xt"]:
            if exchange in accounts_config:
                account_ids[exchange] = [
                    acc.get("account_id")
                    for acc in accounts_config[exchange]
                    if acc.get("account_id")
                ]

        return await self.calculate_daily_positions(
            target_date=target_date,
            hours_back=hours_back,
            account_ids=account_ids if account_ids else None,
        )


async def calculate_yesterday_positions(
    db_manager: Optional[DatabaseManager] = None,
    account_ids: Optional[Dict[str, List[str]]] = None,
    contract_multiplier_getter: Optional[callable] = None,
) -> Dict[str, Dict[str, Decimal]]:
    """计算昨日持仓量和市值的便捷函数.

    Args:
        db_manager: 数据库管理器，如果不提供则创建新的
        account_ids: 账号ID字典，格式为 {"binance": ["binance_main_001", ...], "xt": ["xt_main_001", ...]}
        contract_multiplier_getter: 获取合约乘数的函数

    Returns:
        同 DailyPositionCalculator.calculate_daily_positions
    """
    if db_manager is None:
        db_manager = DatabaseManager()

    calculator = DailyPositionCalculator(
        db_manager=db_manager, contract_multiplier_getter=contract_multiplier_getter
    )

    return await calculator.calculate_daily_positions(account_ids=account_ids)
