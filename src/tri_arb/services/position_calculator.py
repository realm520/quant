"""持仓量计算服务（基于成交记录）.

用于计算基于成交记录的持仓量：
- 多头持仓量 = 区间内所有买单的成交量 + 之前遗留的未平仓的买单
- 空头持仓量 = 区间内所有卖单的成交量 + 之前遗留的未平仓的卖单
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


class PositionCalculator:
    """持仓量计算器（基于成交记录）.
    
    计算逻辑：
    - 多头持仓量 = 区间开始时多头持仓 + 区间内所有 BUY 订单的成交量
    - 空头持仓量 = 区间开始时空头持仓 + 区间内所有 SELL 订单的成交量
    """
    
    def __init__(self, db_session: AsyncSession, exchange: str = "binance", account_id: Optional[str] = None):
        """初始化持仓量计算器.
        
        Args:
            db_session: 数据库会话
            exchange: 交易所名称 (binance, xt, okx, gate)
            account_id: 账号ID（可选），用于多账号场景
        """
        self.db_session = db_session
        self.exchange = exchange.lower()
        self.account_id = account_id
        
        # 根据交易所选择对应的模型
        if self.exchange == "binance":
            from tri_arb.storage.models import TradeUpdate, AccountUpdate
            self.TradeModel = TradeUpdate
            self.PositionModel = AccountUpdate
            self.trade_table = "binance_trade_update"
            self.position_table = "binance_account_update"
        elif self.exchange == "xt":
            from tri_arb.storage.xt_websocket_models import XTTradeUpdate, XTPositionUpdate
            self.TradeModel = XTTradeUpdate
            self.PositionModel = XTPositionUpdate
            self.trade_table = "xt_trade_update"
            self.position_table = "xt_position_update"
        else:
            raise ValueError(f"Unsupported exchange: {exchange}")
    
    async def calculate_position_from_trades(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None
    ) -> Dict[str, Decimal]:
        """基于成交记录计算持仓量.
        
        Args:
            start_time: 区间开始时间（UTC）
            end_time: 区间结束时间（UTC）
            symbol: 交易对（可选），如果不指定则统计所有交易对
        
        Returns:
            字典，包含以下指标：
            - pre_long_qty: 多头持仓量（区间开始时多头持仓 + 区间内所有 BUY 订单的成交量）
            - pre_short_qty: 空头持仓量（区间开始时空头持仓 + 区间内所有 SELL 订单的成交量）
            - pre_long_value: 多头持仓市值
            - pre_short_value: 空头持仓市值
            - buy_volume: 区间内所有 BUY 订单的成交量
            - sell_volume: 区间内所有 SELL 订单的成交量
            - initial_long_qty: 区间开始时的多头持仓
            - initial_short_qty: 区间开始时的空头持仓
        """
        # 1. 获取区间开始时的持仓（之前遗留的未平仓持仓）
        initial_positions = await self._get_initial_positions(start_time, symbol)
        initial_long_qty = Decimal("0")
        initial_short_qty = Decimal("0")
        initial_long_value = Decimal("0")
        initial_short_value = Decimal("0")
        
        for symbol_key, pos_data in initial_positions.items():
            if pos_data.get("side", "").upper() == "LONG":
                initial_long_qty += pos_data.get("quantity", Decimal("0"))
                initial_long_value += pos_data.get("notional", Decimal("0"))
            elif pos_data.get("side", "").upper() == "SHORT":
                initial_short_qty += pos_data.get("quantity", Decimal("0"))
                initial_short_value += pos_data.get("notional", Decimal("0"))
        
        # 2. 统计区间内所有成交记录
        buy_volume, sell_volume = await self._calculate_trade_volumes(start_time, end_time, symbol)
        
        # 3. 计算总持仓量
        pre_long_qty = initial_long_qty + buy_volume
        pre_short_qty = initial_short_qty + sell_volume
        
        # 4. 计算持仓市值（使用平均价格）
        # 这里简化处理，使用区间内成交的平均价格
        avg_buy_price, avg_sell_price = await self._calculate_avg_prices(start_time, end_time, symbol)
        
        pre_long_value = initial_long_value + (buy_volume * avg_buy_price if avg_buy_price > 0 else Decimal("0"))
        pre_short_value = initial_short_value + (sell_volume * avg_sell_price if avg_sell_price > 0 else Decimal("0"))
        
        return {
            "pre_long_qty": pre_long_qty,
            "pre_short_qty": pre_short_qty,
            "pre_long_value": pre_long_value,
            "pre_short_value": pre_short_value,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "initial_long_qty": initial_long_qty,
            "initial_short_qty": initial_short_qty,
        }
    
    async def _get_initial_positions(
        self,
        start_time: datetime,
        symbol: Optional[str] = None
    ) -> Dict[str, Dict[str, any]]:
        """获取区间开始时的持仓（之前遗留的未平仓持仓）.
        
        Args:
            start_time: 区间开始时间
            symbol: 交易对（可选）
        
        Returns:
            字典，格式为: {
                "symbol_side": {
                    "quantity": Decimal,
                    "entry_price": Decimal,
                    "notional": Decimal,
                    "side": "LONG" or "SHORT"
                }
            }
        """
        if self.exchange == "binance":
            # 使用 AccountUpdate 表，找到 start_time 之前最后一次持仓更新
            subquery = (
                select(
                    self.PositionModel.symbol,
                    self.PositionModel.position_side,
                    func.max(self.PositionModel.event_time).label('max_time')
                )
                .where(self.PositionModel.event_time < start_time)
                .where(self.PositionModel.event_type == 'POSITION_UPDATE')
                .where(self.PositionModel.exchange == 'binance_perp')
                .where(self.PositionModel.position_amount != 0)
            )
            if self.account_id:
                subquery = subquery.where(self.PositionModel.account_id == self.account_id)
            if symbol:
                subquery = subquery.where(self.PositionModel.symbol == symbol)
            
            subquery = subquery.group_by(
                self.PositionModel.symbol,
                self.PositionModel.position_side
            ).subquery()
            
            query = (
                select(self.PositionModel)
                .join(
                    subquery,
                    (self.PositionModel.symbol == subquery.c.symbol) &
                    (self.PositionModel.position_side == subquery.c.position_side) &
                    (self.PositionModel.event_time == subquery.c.max_time)
                )
                .where(self.PositionModel.event_type == 'POSITION_UPDATE')
                .where(self.PositionModel.exchange == 'binance_perp')
            )
        elif self.exchange == "xt":
            # 使用 XTPositionUpdate 表
            subquery = (
                select(
                    self.PositionModel.symbol,
                    self.PositionModel.side,
                    func.max(self.PositionModel.update_time).label('max_time')
                )
                .where(self.PositionModel.update_time < start_time)
                .where(self.PositionModel.quantity > 0)
            )
            if self.account_id:
                subquery = subquery.where(self.PositionModel.account_id == self.account_id)
            if symbol:
                subquery = subquery.where(self.PositionModel.symbol == symbol)
            
            subquery = subquery.group_by(
                self.PositionModel.symbol,
                self.PositionModel.side
            ).subquery()
            
            query = (
                select(self.PositionModel)
                .join(
                    subquery,
                    (self.PositionModel.symbol == subquery.c.symbol) &
                    (self.PositionModel.side == subquery.c.side) &
                    (self.PositionModel.update_time == subquery.c.max_time)
                )
                .where(self.PositionModel.quantity > 0)
            )
        else:
            return {}
        
        if self.account_id:
            query = query.where(self.PositionModel.account_id == self.account_id)
        
        result = await self.db_session.execute(query)
        positions = result.scalars().all()
        
        position_dict = {}
        for pos in positions:
            if self.exchange == "binance":
                symbol_key = pos.symbol
                side = pos.position_side.upper()
                quantity = abs(pos.position_amount)
                entry_price = pos.entry_price or Decimal("0")
            else:  # xt
                symbol_key = pos.symbol
                side = pos.side.upper()
                quantity = pos.quantity
                entry_price = pos.entry_price or Decimal("0")
            
            key = f"{symbol_key}_{side}"
            notional = quantity * entry_price if entry_price > 0 else Decimal("0")
            
            position_dict[key] = {
                "quantity": quantity,
                "entry_price": entry_price,
                "notional": notional,
                "side": side,
            }
        
        return position_dict
    
    async def _calculate_trade_volumes(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None
    ) -> tuple[Decimal, Decimal]:
        """统计区间内所有成交记录的成交量.
        
        Args:
            start_time: 区间开始时间
            end_time: 区间结束时间
            symbol: 交易对（可选）
        
        Returns:
            (buy_volume, sell_volume) 元组
        """
        query = (
            select(
                self.TradeModel.side,
                func.sum(self.TradeModel.quantity).label('total_quantity')
            )
            .where(self.TradeModel.transaction_time >= start_time)
            .where(self.TradeModel.transaction_time < end_time)
        )
        
        if self.exchange == "binance":
            query = query.where(self.TradeModel.exchange == 'binance_perp')
        if self.account_id:
            query = query.where(self.TradeModel.account_id == self.account_id)
        if symbol:
            query = query.where(self.TradeModel.symbol == symbol)
        
        query = query.group_by(self.TradeModel.side)
        
        result = await self.db_session.execute(query)
        rows = result.all()
        
        buy_volume = Decimal("0")
        sell_volume = Decimal("0")
        
        for side, total_quantity in rows:
            if side.upper() == "BUY":
                buy_volume += total_quantity or Decimal("0")
            elif side.upper() == "SELL":
                sell_volume += total_quantity or Decimal("0")
        
        return buy_volume, sell_volume
    
    async def _calculate_avg_prices(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None
    ) -> tuple[Decimal, Decimal]:
        """计算区间内成交的平均价格.
        
        Args:
            start_time: 区间开始时间
            end_time: 区间结束时间
            symbol: 交易对（可选）
        
        Returns:
            (avg_buy_price, avg_sell_price) 元组
        """
        # 计算加权平均价格：sum(price * quantity) / sum(quantity)
        query = (
            select(
                self.TradeModel.side,
                func.sum(self.TradeModel.price * self.TradeModel.quantity).label('total_value'),
                func.sum(self.TradeModel.quantity).label('total_quantity')
            )
            .where(self.TradeModel.transaction_time >= start_time)
            .where(self.TradeModel.transaction_time < end_time)
        )
        
        if self.exchange == "binance":
            query = query.where(self.TradeModel.exchange == 'binance_perp')
        if self.account_id:
            query = query.where(self.TradeModel.account_id == self.account_id)
        if symbol:
            query = query.where(self.TradeModel.symbol == symbol)
        
        query = query.group_by(self.TradeModel.side)
        
        result = await self.db_session.execute(query)
        rows = result.all()
        
        avg_buy_price = Decimal("0")
        avg_sell_price = Decimal("0")
        
        for side, total_value, total_quantity in rows:
            if total_quantity and total_quantity > 0:
                avg_price = total_value / total_quantity
                if side.upper() == "BUY":
                    avg_buy_price = avg_price
                elif side.upper() == "SELL":
                    avg_sell_price = avg_price
        
        return avg_buy_price, avg_sell_price

