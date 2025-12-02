"""持仓量计算服务（基于成交记录）.

用于计算基于成交记录的持仓量：
- 多头持仓量 = 区间内所有买单的成交量 + 之前遗留的未平仓的买单
- 空头持仓量 = 区间内所有卖单的成交量 + 之前遗留的未平仓的卖单
- 多头市值 = 每笔买单市值累加 + 前日遗留的多头市值
- 空头市值 = 每笔卖单市值累加 + 前日遗留的空头市值

市值计算：每笔市值 = 成交价格 × 成交数量 × 合约乘数
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional, Callable

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
    
    def __init__(
        self,
        db_session: AsyncSession,
        exchange: str = "binance",
        account_id: Optional[str] = None,
        contract_multiplier_getter: Optional[Callable[[str], Decimal]] = None
    ):
        """初始化持仓量计算器.
        
        Args:
            db_session: 数据库会话
            exchange: 交易所名称 (binance, xt, okx, gate)
            account_id: 账号ID（可选），用于多账号场景
            contract_multiplier_getter: 获取合约乘数的函数，接收 symbol 参数，返回合约乘数（Decimal）
                                       如果不提供，默认使用 1
        """
        self.db_session = db_session
        self.exchange = exchange.lower()
        self.account_id = account_id
        self.contract_multiplier_getter = contract_multiplier_getter or (lambda s: Decimal("1"))
        
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
    
    def _get_contract_multiplier(self, symbol: str) -> Decimal:
        """获取合约乘数.
        
        Args:
            symbol: 交易对
        
        Returns:
            合约乘数（默认 1）
        """
        try:
            return self.contract_multiplier_getter(symbol)
        except Exception as e:
            logger.warning(f"Failed to get contract multiplier for {symbol}, using default 1: {e}")
            return Decimal("1")
    
    async def calculate_position_from_trades(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None
    ) -> Dict[str, Decimal]:
        """基于成交记录计算持仓量和市值（用于某一时间区间，例如“昨日”或“今日”）.
        
        Args:
            start_time: 区间开始时间（UTC）
            end_time: 区间结束时间（UTC）
            symbol: 交易对（可选），如果不指定则统计所有交易对
        
        Returns:
            字典，包含以下指标：
            - pre_long_qty: 区间结束时的多头持仓量（= initial_long_qty + buy_volume）
            - pre_short_qty: 区间结束时的空头持仓量（= initial_short_qty + sell_volume）
            - pre_long_value: 区间结束时的多头市值
            - pre_short_value: 区间结束时的空头市值
            - buy_volume: 区间内所有 BUY 成交量之和
            - sell_volume: 区间内所有 SELL 成交量之和
            - initial_long_qty: 区间开始时的多头持仓量（之前遗留的未平仓多头）
            - initial_short_qty: 区间开始时的空头持仓量（之前遗留的未平仓空头）
            - buy_trade_value: 区间内所有 BUY 成交市值之和（∑ price * qty * 合约乘数）
            - sell_trade_value: 区间内所有 SELL 成交市值之和
            - long_qty: 多头交易量 = pre_long_qty + buy_volume
            - short_qty: 空头交易量 = pre_short_qty + sell_volume
            - long_value: 多头市值 = pre_long_value + buy_trade_value
            - short_value: 空头市值 = pre_short_value + sell_trade_value
            - avg_buy_prz: 买入平均价格 = long_value / long_qty（如 long_qty 为 0 则为 0）
            - avg_sell_prz: 卖出平均价格 = short_value / short_qty（如 short_qty 为 0 则为 0）
        """
        # 1. 获取区间开始时的持仓（之前遗留的未平仓持仓）
        initial_positions = await self._get_initial_positions(start_time, symbol)
        initial_long_qty = Decimal("0")
        initial_short_qty = Decimal("0")
        initial_long_value = Decimal("0")
        initial_short_value = Decimal("0")
        
        # 计算初始持仓量和市值（使用开仓均价和合约乘数）
        for symbol_key, pos_data in initial_positions.items():
            pos_symbol = symbol_key.split("_")[0]  # 从 "symbol_side" 中提取 symbol
            contract_multiplier = self._get_contract_multiplier(pos_symbol)
            side = pos_data.get("side", "").upper()
            quantity = pos_data.get("quantity", Decimal("0"))
            entry_price = pos_data.get("entry_price", Decimal("0"))
            
            # 市值 = 持仓量 × 开仓均价 × 合约乘数
            position_value = quantity * entry_price * contract_multiplier
            
            if side == "LONG":
                initial_long_qty += quantity
                initial_long_value += position_value
            elif side == "SHORT":
                initial_short_qty += quantity
                initial_short_value += position_value
        
        # 2. 统计区间内所有成交记录
        buy_volume, sell_volume = await self._calculate_trade_volumes(start_time, end_time, symbol)
        
        # 3. 计算总持仓量
        pre_long_qty = initial_long_qty + buy_volume
        pre_short_qty = initial_short_qty + sell_volume
        
        # 4. 计算持仓市值
        # 4.1 计算区间内成交的市值（每笔成交的市值累加）
        buy_trade_value, sell_trade_value = await self._calculate_trade_values(start_time, end_time, symbol)
        
        # 4.2 计算区间结束时的市值（基于初始市值 + 区间内成交市值之和）
        pre_long_value = initial_long_value + buy_trade_value
        pre_short_value = initial_short_value + sell_trade_value

        # 5. 根据你的公式计算“今日”的交易量和市值：
        #   long_qty = sum(buy_vol) + pre_long_qty
        #   short_qty = sum(sell_vol) + pre_short_qty
        #   long_value = sum(buy_vol * buy_price) + pre_long_value
        #   short_value = sum(sell_vol * sell_price) + pre_short_value
        long_qty = pre_long_qty + buy_volume
        short_qty = pre_short_qty + sell_volume
        long_value = pre_long_value + buy_trade_value
        short_value = pre_short_value + sell_trade_value

        # 6. 计算平均价格（不可舍入，直接用 Decimal 相除）
        avg_buy_prz = Decimal("0")
        avg_sell_prz = Decimal("0")
        if long_qty > 0:
            avg_buy_prz = long_value / long_qty
        if short_qty > 0:
            avg_sell_prz = short_value / short_qty
        
        return {
            "pre_long_qty": pre_long_qty,
            "pre_short_qty": pre_short_qty,
            "pre_long_value": pre_long_value,
            "pre_short_value": pre_short_value,
            "buy_volume": buy_volume,
            "sell_volume": sell_volume,
            "initial_long_qty": initial_long_qty,
            "initial_short_qty": initial_short_qty,
            "buy_trade_value": buy_trade_value,
            "sell_trade_value": sell_trade_value,
            "long_qty": long_qty,
            "short_qty": short_qty,
            "long_value": long_value,
            "short_value": short_value,
            "avg_buy_prz": avg_buy_prz,
            "avg_sell_prz": avg_sell_prz,
        }

    async def calculate_positions_by_symbol(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None,
    ) -> Dict[str, Dict[str, Decimal]]:
        """按交易对（symbol）维度计算区间内的持仓与交易指标.

        与 ``calculate_position_from_trades`` 类似，但会返回每个 symbol 的独立统计结果。

        返回结构示例::

            {
                "BTCUSDT": {
                    "pre_long_qty": ...,
                    "pre_short_qty": ...,
                    "pre_long_value": ...,
                    "pre_short_value": ...,
                    "buy_volume": ...,
                    "sell_volume": ...,
                    "buy_trade_value": ...,
                    "sell_trade_value": ...,
                    "long_qty": ...,
                    "short_qty": ...,
                    "long_value": ...,
                    "short_value": ...,
                    "avg_buy_prz": ...,
                    "avg_sell_prz": ...,
                    "initial_long_qty": ...,
                    "initial_short_qty": ...,
                },
                "TOTAL": { ... 所有 symbol 汇总 ... }
            }
        """
        # 1. 获取区间开始时的逐 symbol 持仓
        initial_positions = await self._get_initial_positions(start_time, symbol)

        # 先构建逐 symbol 的初始多空持仓与市值
        by_symbol: Dict[str, Dict[str, Decimal]] = {}
        for symbol_key, pos_data in initial_positions.items():
            pos_symbol = symbol_key.split("_")[0]
            contract_multiplier = self._get_contract_multiplier(pos_symbol)
            side = pos_data.get("side", "").upper()
            quantity = pos_data.get("quantity", Decimal("0"))
            entry_price = pos_data.get("entry_price", Decimal("0"))

            position_value = quantity * entry_price * contract_multiplier

            s = pos_symbol
            if s not in by_symbol:
                by_symbol[s] = {
                    "initial_long_qty": Decimal("0"),
                    "initial_short_qty": Decimal("0"),
                    "initial_long_value": Decimal("0"),
                    "initial_short_value": Decimal("0"),
                    "buy_volume": Decimal("0"),
                    "sell_volume": Decimal("0"),
                    "buy_trade_value": Decimal("0"),
                    "sell_trade_value": Decimal("0"),
                }

            if side == "LONG":
                by_symbol[s]["initial_long_qty"] += quantity
                by_symbol[s]["initial_long_value"] += position_value
            elif side == "SHORT":
                by_symbol[s]["initial_short_qty"] += quantity
                by_symbol[s]["initial_short_value"] += position_value

        # 2. 统计区间内逐 symbol 的成交量与市值
        time_column = (
            self.TradeModel.transaction_time
            if self.exchange == "binance"
            else self.TradeModel.update_time
        )

        query = (
            select(
                self.TradeModel.symbol,
                self.TradeModel.side,
                self.TradeModel.price,
                self.TradeModel.quantity,
            )
            .where(time_column >= start_time)
            .where(time_column < end_time)
        )

        if self.exchange == "binance":
            query = query.where(self.TradeModel.exchange == "binance_perp")
        if self.account_id:
            query = query.where(self.TradeModel.account_id == self.account_id)
        if symbol:
            query = query.where(self.TradeModel.symbol == symbol)

        result = await self.db_session.execute(query)
        rows = result.all()

        for row in rows:
            trade_symbol = row.symbol
            side = row.side.upper()
            price = row.price
            qty = row.quantity

            if trade_symbol not in by_symbol:
                by_symbol[trade_symbol] = {
                    "initial_long_qty": Decimal("0"),
                    "initial_short_qty": Decimal("0"),
                    "initial_long_value": Decimal("0"),
                    "initial_short_value": Decimal("0"),
                    "buy_volume": Decimal("0"),
                    "sell_volume": Decimal("0"),
                    "buy_trade_value": Decimal("0"),
                    "sell_trade_value": Decimal("0"),
                }

            # 成交量
            if side == "BUY":
                by_symbol[trade_symbol]["buy_volume"] += qty
            elif side == "SELL":
                by_symbol[trade_symbol]["sell_volume"] += qty

            # 成交市值（使用合约乘数）
            contract_multiplier = self._get_contract_multiplier(trade_symbol)
            trade_value = price * qty * contract_multiplier
            if side == "BUY":
                by_symbol[trade_symbol]["buy_trade_value"] += trade_value
            elif side == "SELL":
                by_symbol[trade_symbol]["sell_trade_value"] += trade_value

        # 3. 计算每个 symbol 的最终指标
        total: Dict[str, Decimal] = {
            "pre_long_qty": Decimal("0"),
            "pre_short_qty": Decimal("0"),
            "pre_long_value": Decimal("0"),
            "pre_short_value": Decimal("0"),
            "buy_volume": Decimal("0"),
            "sell_volume": Decimal("0"),
            "buy_trade_value": Decimal("0"),
            "sell_trade_value": Decimal("0"),
            "long_qty": Decimal("0"),
            "short_qty": Decimal("0"),
            "long_value": Decimal("0"),
            "short_value": Decimal("0"),
        }

        for s, data in by_symbol.items():
            initial_long_qty = data["initial_long_qty"]
            initial_short_qty = data["initial_short_qty"]
            initial_long_value = data["initial_long_value"]
            initial_short_value = data["initial_short_value"]
            buy_volume = data["buy_volume"]
            sell_volume = data["sell_volume"]
            buy_trade_value = data["buy_trade_value"]
            sell_trade_value = data["sell_trade_value"]

            pre_long_qty = initial_long_qty + buy_volume
            pre_short_qty = initial_short_qty + sell_volume
            pre_long_value = initial_long_value + buy_trade_value
            pre_short_value = initial_short_value + sell_trade_value

            long_qty = pre_long_qty + buy_volume
            short_qty = pre_short_qty + sell_volume
            long_value = pre_long_value + buy_trade_value
            short_value = pre_short_value + sell_trade_value

            avg_buy_prz = Decimal("0")
            avg_sell_prz = Decimal("0")
            if long_qty > 0:
                avg_buy_prz = long_value / long_qty
            if short_qty > 0:
                avg_sell_prz = short_value / short_qty

            data.update(
                {
                    "pre_long_qty": pre_long_qty,
                    "pre_short_qty": pre_short_qty,
                    "pre_long_value": pre_long_value,
                    "pre_short_value": pre_short_value,
                    "long_qty": long_qty,
                    "short_qty": short_qty,
                    "long_value": long_value,
                    "short_value": short_value,
                    "avg_buy_prz": avg_buy_prz,
                    "avg_sell_prz": avg_sell_prz,
                }
            )

            # 累加到 TOTAL
            total["pre_long_qty"] += pre_long_qty
            total["pre_short_qty"] += pre_short_qty
            total["pre_long_value"] += pre_long_value
            total["pre_short_value"] += pre_short_value
            total["buy_volume"] += buy_volume
            total["sell_volume"] += sell_volume
            total["buy_trade_value"] += buy_trade_value
            total["sell_trade_value"] += sell_trade_value
            total["long_qty"] += long_qty
            total["short_qty"] += short_qty
            total["long_value"] += long_value
            total["short_value"] += short_value

        # 计算 TOTAL 的均价
        avg_buy_prz_total = Decimal("0")
        avg_sell_prz_total = Decimal("0")
        if total["long_qty"] > 0:
            avg_buy_prz_total = total["long_value"] / total["long_qty"]
        if total["short_qty"] > 0:
            avg_sell_prz_total = total["short_value"] / total["short_qty"]
        total["avg_buy_prz"] = avg_buy_prz_total
        total["avg_sell_prz"] = avg_sell_prz_total

        by_symbol["TOTAL"] = total
        return by_symbol
    
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
        # 根据交易所选择时间字段
        time_column = self.TradeModel.transaction_time if self.exchange == "binance" else self.TradeModel.update_time
        
        query = (
            select(
                self.TradeModel.side,
                func.sum(self.TradeModel.quantity).label('total_quantity')
            )
            .where(time_column >= start_time)
            .where(time_column < end_time)
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
    
    async def _calculate_trade_values(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None
    ) -> tuple[Decimal, Decimal]:
        """计算区间内所有成交的市值（每笔成交的市值累加）.
        
        每笔成交的市值 = 成交价格 × 成交数量 × 合约乘数
        
        Args:
            start_time: 区间开始时间
            end_time: 区间结束时间
            symbol: 交易对（可选）
        
        Returns:
            (buy_trade_value, sell_trade_value) 元组
        """
        # 查询所有成交记录
        time_column = self.TradeModel.transaction_time if self.exchange == "binance" else self.TradeModel.update_time
        
        query = (
            select(
                self.TradeModel.symbol,
                self.TradeModel.side,
                self.TradeModel.price,
                self.TradeModel.quantity
            )
            .where(time_column >= start_time)
            .where(time_column < end_time)
        )
        
        if self.exchange == "binance":
            query = query.where(self.TradeModel.exchange == 'binance_perp')
        if self.account_id:
            query = query.where(self.TradeModel.account_id == self.account_id)
        if symbol:
            query = query.where(self.TradeModel.symbol == symbol)
        
        result = await self.db_session.execute(query)
        trades = result.all()
        
        buy_trade_value = Decimal("0")
        sell_trade_value = Decimal("0")
        
        for trade in trades:
            trade_symbol = trade.symbol
            side = trade.side.upper()
            price = trade.price
            quantity = trade.quantity
            
            # 获取合约乘数
            contract_multiplier = self._get_contract_multiplier(trade_symbol)
            
            # 计算市值：成交价格 × 成交数量 × 合约乘数
            trade_value = price * quantity * contract_multiplier
            
            if side == "BUY":
                buy_trade_value += trade_value
            elif side == "SELL":
                sell_trade_value += trade_value
        
        return buy_trade_value, sell_trade_value

