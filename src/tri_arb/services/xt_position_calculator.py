"""XT 持仓量计算服务.

用于计算昨日持仓量、持仓市值等指标。
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from tri_arb.config.logging import get_logger
from tri_arb.storage.xt_rest_models import XTPerpPosition
from tri_arb.storage.xt_websocket_models import XTPositionUpdate

logger = get_logger(__name__)


class XTPositionCalculator:
    """XT 持仓量计算器.

    用于计算昨日持仓量、持仓市值等指标。
    """

    def __init__(self, db_session: AsyncSession, account_id: Optional[str] = None):
        """初始化持仓量计算器.

        Args:
            db_session: 数据库会话
            account_id: 账号ID（可选），用于多账号场景
        """
        self.db_session = db_session
        self.account_id = account_id

    async def get_yesterday_positions(
        self, target_date: Optional[datetime] = None, hours_back: int = 24
    ) -> Dict[str, Dict[str, Decimal]]:
        """获取昨日持仓快照.

        Args:
            target_date: 目标日期（UTC时间），如果为None则使用当前时间减去hours_back小时
            hours_back: 往前回溯的小时数（默认24小时，即昨日）

        Returns:
            字典，格式为: {
                "symbol": {
                    "LONG": {
                        "quantity": Decimal,
                        "entry_price": Decimal,
                        "notional": Decimal,
                        "query_time": datetime
                    },
                    "SHORT": {
                        "quantity": Decimal,
                        "entry_price": Decimal,
                        "notional": Decimal,
                        "query_time": datetime
                    }
                }
            }
        """
        if target_date is None:
            target_date = datetime.utcnow() - timedelta(hours=hours_back)

        # 查询目标时间点之前最近的持仓快照
        # 使用子查询找到每个symbol+side组合在目标时间之前的最新记录
        subquery = select(
            XTPerpPosition.symbol,
            XTPerpPosition.position_side,
            func.max(XTPerpPosition.query_time).label("max_time"),
        ).where(XTPerpPosition.query_time <= target_date)
        # 如果指定了 account_id，添加过滤条件
        if self.account_id:
            subquery = subquery.where(XTPerpPosition.account_id == self.account_id)
        subquery = subquery.group_by(
            XTPerpPosition.symbol, XTPerpPosition.position_side
        ).subquery()

        # 主查询：获取这些最新记录的完整信息
        query = (
            select(XTPerpPosition)
            .join(
                subquery,
                (XTPerpPosition.symbol == subquery.c.symbol)
                & (XTPerpPosition.position_side == subquery.c.position_side)
                & (XTPerpPosition.query_time == subquery.c.max_time),
            )
            .where(XTPerpPosition.position_amount > 0)  # 只查询有持仓的记录
        )
        # 如果指定了 account_id，添加过滤条件
        if self.account_id:
            query = query.where(XTPerpPosition.account_id == self.account_id)

        result = await self.db_session.execute(query)
        positions = result.scalars().all()

        # 组织数据
        position_dict: Dict[str, Dict[str, Dict[str, any]]] = {}

        for pos in positions:
            symbol = pos.symbol
            side = pos.position_side.upper()  # LONG 或 SHORT

            if symbol not in position_dict:
                position_dict[symbol] = {}

            position_dict[symbol][side] = {
                "quantity": pos.position_amount,
                "entry_price": pos.entry_price or Decimal("0"),
                "notional": pos.notional or Decimal("0"),
                "query_time": pos.query_time,
            }

        logger.info(
            "Retrieved yesterday positions",
            target_date=target_date.isoformat(),
            total_symbols=len(position_dict),
            total_positions=sum(len(sides) for sides in position_dict.values()),
        )

        return position_dict

    async def calculate_pre_position_metrics(
        self,
        target_date: Optional[datetime] = None,
        hours_back: int = 24,
        use_websocket: bool = True,
    ) -> Dict[str, Decimal]:
        """计算昨日持仓指标.

        Args:
            target_date: 目标日期（UTC时间），如果为None则使用当前时间减去hours_back小时
            hours_back: 往前回溯的小时数（默认24小时，即昨日）
            use_websocket: 是否使用 WebSocket 数据（默认 True，推荐）
                          - True: 使用 WebSocket 持仓更新数据（更实时、更准确）
                          - False: 使用 REST API 持仓快照数据

        Returns:
            字典，包含以下指标：
            - pre_long_qty: 昨日多头持仓量（所有symbol的多头持仓量之和）
            - pre_short_qty: 昨日空头持仓量（所有symbol的空头持仓量之和）
            - pre_long_value: 昨日多头持仓市值（所有symbol的多头持仓市值之和）
            - pre_short_value: 昨日空头持仓市值（所有symbol的空头持仓市值之和）
        """
        if use_websocket:
            # 使用 WebSocket 数据（推荐）
            return await self.calculate_pre_position_metrics_from_websocket(
                target_date, hours_back
            )
        else:
            # 使用 REST API 持仓快照数据
            yesterday_positions = await self.get_yesterday_positions(
                target_date, hours_back
            )

        pre_long_qty = Decimal("0")
        pre_short_qty = Decimal("0")
        pre_long_value = Decimal("0")
        pre_short_value = Decimal("0")

        for symbol, sides in yesterday_positions.items():
            # 多头持仓
            if "LONG" in sides:
                long_data = sides["LONG"]
                pre_long_qty += long_data["quantity"]
                # 持仓市值 = 持仓量 × 开仓价格
                # 如果API提供了notional（名义价值），优先使用notional
                if long_data["notional"] > 0:
                    pre_long_value += long_data["notional"]
                else:
                    pre_long_value += long_data["quantity"] * long_data["entry_price"]

            # 空头持仓
            if "SHORT" in sides:
                short_data = sides["SHORT"]
                pre_short_qty += short_data["quantity"]
                # 持仓市值 = 持仓量 × 开仓价格
                # 如果API提供了notional（名义价值），优先使用notional
                if short_data["notional"] > 0:
                    pre_short_value += short_data["notional"]
                else:
                    pre_short_value += (
                        short_data["quantity"] * short_data["entry_price"]
                    )

        metrics = {
            "pre_long_qty": pre_long_qty,
            "pre_short_qty": pre_short_qty,
            "pre_long_value": pre_long_value,
            "pre_short_value": pre_short_value,
        }

        logger.info(
            "Calculated pre-position metrics",
            target_date=target_date.isoformat() if target_date else None,
            **{k: str(v) for k, v in metrics.items()},
        )

        return metrics

    async def calculate_current_position_metrics(
        self, current_positions: list
    ) -> Dict[str, Decimal]:
        """计算当前持仓指标.

        Args:
            current_positions: 当前持仓列表（Position对象列表）

        Returns:
            字典，包含以下指标：
            - long_qty: 当前多头持仓量
            - short_qty: 当前空头持仓量
            - long_value: 当前多头持仓市值
            - short_value: 当前空头持仓市值
        """
        long_qty = Decimal("0")
        short_qty = Decimal("0")
        long_value = Decimal("0")
        short_value = Decimal("0")

        for pos in current_positions:
            if pos.side.upper() == "LONG":
                long_qty += pos.quantity
                # 持仓市值 = 持仓量 × 开仓价格
                long_value += pos.quantity * pos.entry_price
            elif pos.side.upper() == "SHORT":
                short_qty += pos.quantity
                # 持仓市值 = 持仓量 × 开仓价格
                short_value += pos.quantity * pos.entry_price

        metrics = {
            "long_qty": long_qty,
            "short_qty": short_qty,
            "long_value": long_value,
            "short_value": short_value,
        }

        logger.info(
            "Calculated current position metrics",
            **{k: str(v) for k, v in metrics.items()},
        )

        return metrics

    async def calculate_position_change(
        self,
        current_positions: list,
        target_date: Optional[datetime] = None,
        hours_back: int = 24,
    ) -> Dict[str, Decimal]:
        """计算持仓变化.

        Args:
            current_positions: 当前持仓列表
            target_date: 目标日期（用于计算昨日持仓）
            hours_back: 往前回溯的小时数

        Returns:
            字典，包含持仓变化指标：
            - long_qty_change: 多头持仓量变化（当前 - 昨日）
            - short_qty_change: 空头持仓量变化（当前 - 昨日）
            - long_value_change: 多头持仓市值变化（当前 - 昨日）
            - short_value_change: 空头持仓市值变化（当前 - 昨日）
        """
        current_metrics = await self.calculate_current_position_metrics(
            current_positions
        )
        pre_metrics = await self.calculate_pre_position_metrics(target_date, hours_back)

        changes = {
            "long_qty_change": current_metrics["long_qty"]
            - pre_metrics["pre_long_qty"],
            "short_qty_change": current_metrics["short_qty"]
            - pre_metrics["pre_short_qty"],
            "long_value_change": current_metrics["long_value"]
            - pre_metrics["pre_long_value"],
            "short_value_change": current_metrics["short_value"]
            - pre_metrics["pre_short_value"],
        }

        logger.info(
            "Calculated position changes", **{k: str(v) for k, v in changes.items()}
        )

        return changes

    async def get_yesterday_positions_from_websocket(
        self, target_date: Optional[datetime] = None, hours_back: int = 24
    ) -> Dict[str, Dict[str, Decimal]]:
        """从 WebSocket 持仓更新数据获取昨日持仓快照.

        ⭐ 推荐使用此方法，因为 WebSocket 数据更实时、更准确。

        Args:
            target_date: 目标日期（UTC时间），如果为None则使用当前时间减去hours_back小时
            hours_back: 往前回溯的小时数（默认24小时，即昨日）

        Returns:
            字典，格式为: {
                "symbol": {
                    "LONG": {
                        "quantity": Decimal,
                        "entry_price": Decimal,
                        "notional": Decimal,
                        "update_time": datetime
                    },
                    "SHORT": {
                        "quantity": Decimal,
                        "entry_price": Decimal,
                        "notional": Decimal,
                        "update_time": datetime
                    }
                }
            }
        """
        if target_date is None:
            target_date = datetime.utcnow() - timedelta(hours=hours_back)

        # 查询目标时间点之前最近的 WebSocket 持仓更新
        # 使用子查询找到每个symbol+side组合在目标时间之前的最新记录
        subquery = select(
            XTPositionUpdate.symbol,
            XTPositionUpdate.side,
            func.max(XTPositionUpdate.update_time).label("max_time"),
        ).where(XTPositionUpdate.update_time <= target_date)
        # 如果指定了 account_id，添加过滤条件
        if self.account_id:
            subquery = subquery.where(XTPositionUpdate.account_id == self.account_id)
        subquery = subquery.group_by(
            XTPositionUpdate.symbol, XTPositionUpdate.side
        ).subquery()

        # 主查询：获取这些最新记录的完整信息
        query = (
            select(XTPositionUpdate)
            .join(
                subquery,
                (XTPositionUpdate.symbol == subquery.c.symbol)
                & (XTPositionUpdate.side == subquery.c.side)
                & (XTPositionUpdate.update_time == subquery.c.max_time),
            )
            .where(XTPositionUpdate.quantity > 0)  # 只查询有持仓的记录
        )
        # 如果指定了 account_id，添加过滤条件
        if self.account_id:
            query = query.where(XTPositionUpdate.account_id == self.account_id)

        result = await self.db_session.execute(query)
        positions = result.scalars().all()

        # 组织数据
        position_dict: Dict[str, Dict[str, Dict[str, any]]] = {}

        for pos in positions:
            symbol = pos.symbol
            side = pos.side.upper()  # LONG 或 SHORT

            if symbol not in position_dict:
                position_dict[symbol] = {}

            # 计算名义价值（持仓市值）
            entry_price = pos.entry_price or Decimal("0")
            notional = pos.quantity * entry_price if entry_price > 0 else Decimal("0")

            position_dict[symbol][side] = {
                "quantity": pos.quantity,
                "entry_price": entry_price,
                "notional": notional,
                "update_time": pos.update_time,
            }

        logger.info(
            "Retrieved yesterday positions from WebSocket data",
            target_date=target_date.isoformat(),
            total_symbols=len(position_dict),
            total_positions=sum(len(sides) for sides in position_dict.values()),
            data_source="websocket",
        )

        return position_dict

    async def calculate_pre_position_metrics_from_websocket(
        self, target_date: Optional[datetime] = None, hours_back: int = 24
    ) -> Dict[str, Decimal]:
        """从 WebSocket 持仓更新数据计算昨日持仓指标.

        ⭐ 推荐使用此方法，因为 WebSocket 数据更实时、更准确。

        WebSocket 数据的优势：
        1. 实时性更好：每次仓位变化都会立即推送并保存
        2. 数据更准确：反映真实的仓位变化历史
        3. 数据更完整：可以追踪每次仓位变化的详细时间

        Args:
            target_date: 目标日期（UTC时间），如果为None则使用当前时间减去hours_back小时
            hours_back: 往前回溯的小时数（默认24小时，即昨日）

        Returns:
            字典，包含以下指标：
            - pre_long_qty: 昨日多头持仓量（所有symbol的多头持仓量之和）
            - pre_short_qty: 昨日空头持仓量（所有symbol的空头持仓量之和）
            - pre_long_value: 昨日多头持仓市值（所有symbol的多头持仓市值之和）
            - pre_short_value: 昨日空头持仓市值（所有symbol的空头持仓市值之和）
        """
        yesterday_positions = await self.get_yesterday_positions_from_websocket(
            target_date, hours_back
        )

        pre_long_qty = Decimal("0")
        pre_short_qty = Decimal("0")
        pre_long_value = Decimal("0")
        pre_short_value = Decimal("0")

        for symbol, sides in yesterday_positions.items():
            # 多头持仓
            if "LONG" in sides:
                long_data = sides["LONG"]
                pre_long_qty += long_data["quantity"]
                # 持仓市值 = 持仓量 × 开仓价格
                pre_long_value += long_data["notional"]

            # 空头持仓
            if "SHORT" in sides:
                short_data = sides["SHORT"]
                pre_short_qty += short_data["quantity"]
                # 持仓市值 = 持仓量 × 开仓价格
                pre_short_value += short_data["notional"]

        metrics = {
            "pre_long_qty": pre_long_qty,
            "pre_short_qty": pre_short_qty,
            "pre_long_value": pre_long_value,
            "pre_short_value": pre_short_value,
        }

        logger.info(
            "Calculated pre-position metrics from WebSocket data",
            target_date=target_date.isoformat() if target_date else None,
            data_source="websocket",
            **{k: str(v) for k, v in metrics.items()},
        )

        return metrics
