"""XT 账号表适配器.

将账号特定的表模型适配到 XTUserStreamService 中。
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class XTAccountTableAdapter:
    """账号表适配器，用于将数据保存到账号特定的表中."""

    def __init__(self, account_id: str, account_models: Dict[str, Any]):
        """初始化适配器.

        Args:
            account_id: 账号ID
            account_models: 账号特定的表模型字典
        """
        self.account_id = account_id
        self.models = account_models

    async def save_account_update(
        self,
        session: AsyncSession,
        update_data: Dict[str, Any],
    ):
        """保存账户更新到账号特定的表."""
        if "XTAccountUpdate" not in self.models:
            logger.warning(f"账号 {self.account_id} 缺少 XTAccountUpdate 模型")
            return

        model = self.models["XTAccountUpdate"]
        # 创建记录并保存
        record = model(**update_data)
        session.add(record)
        await session.commit()

    async def save_position_update(
        self,
        session: AsyncSession,
        update_data: Dict[str, Any],
    ):
        """保存持仓更新到账号特定的表."""
        if "XTPositionUpdate" not in self.models:
            logger.warning(f"账号 {self.account_id} 缺少 XTPositionUpdate 模型")
            return

        model = self.models["XTPositionUpdate"]
        record = model(**update_data)
        session.add(record)
        await session.commit()

    async def save_order_update(
        self,
        session: AsyncSession,
        update_data: Dict[str, Any],
    ):
        """保存订单更新到账号特定的表."""
        if "XTOrderUpdate" not in self.models:
            logger.warning(f"账号 {self.account_id} 缺少 XTOrderUpdate 模型")
            return

        model = self.models["XTOrderUpdate"]
        record = model(**update_data)
        session.add(record)
        await session.commit()

    async def save_trade_update(
        self,
        session: AsyncSession,
        update_data: Dict[str, Any],
    ):
        """保存成交更新到账号特定的表."""
        if "XTTradeUpdate" not in self.models:
            logger.warning(f"账号 {self.account_id} 缺少 XTTradeUpdate 模型")
            return

        model = self.models["XTTradeUpdate"]
        record = model(**update_data)
        session.add(record)
        await session.commit()

    async def save_transfer(
        self,
        session: AsyncSession,
        transfer_data: Dict[str, Any],
    ):
        """保存划转记录到账号特定的表."""
        if "XTTransfer" not in self.models:
            logger.warning(f"账号 {self.account_id} 缺少 XTTransfer 模型")
            return

        model = self.models["XTTransfer"]
        record = model(**transfer_data)
        session.add(record)
        await session.commit()

    async def save_spot_update(
        self,
        session: AsyncSession,
        update_data: Dict[str, Any],
    ):
        """保存现货更新到账号特定的表."""
        if "XTSpotUpdate" not in self.models:
            logger.warning(f"账号 {self.account_id} 缺少 XTSpotUpdate 模型")
            return

        model = self.models["XTSpotUpdate"]
        record = model(**update_data)
        session.add(record)
        await session.commit()
