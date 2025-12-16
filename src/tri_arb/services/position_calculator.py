"""持仓量计算服务（基于成交记录）.

用于计算基于成交记录的持仓量（不叠加遗留持仓）：
- 多头持仓量 = 区间内所有买单的成交量
- 空头持仓量 = 区间内所有卖单的成交量
- 多头市值 = 区间内买单市值累加
- 空头市值 = 区间内卖单市值累加

市值计算：每笔市值 = 成交价格 × 成交数量 × 合约乘数
"""

from datetime import datetime, timedelta, date
from decimal import Decimal
from typing import Dict, Optional, Callable, Any

from sqlalchemy import select, func, case
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
    async def calculate_yesterday_end_left_qty_value(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None,
        initial_positions_dict: Optional[Dict[str, Dict[str, Decimal]]] = None,
    ) -> Dict[str, Dict[str, Decimal]]:
        """计算昨日结束时的剩余持仓量和市值（按 symbol 分组）.
        
        根据注释：如果不是第一天计算，那么昨收持仓需要使用昨天的昨收持仓和昨天的成交进行计算。
        即：初始持仓（昨天的昨收持仓）+ 昨天交易 → 昨天结束时的剩余持仓
        
        Args:
            start_time: 区间开始时间（UTC）
            end_time: 区间结束时间（UTC）
            symbol: 交易对（可选），如果不指定则统计所有交易对
            initial_positions_dict: 初始持仓字典，格式为 {
                "symbol": {
                    "initial_long_qty": Decimal,
                    "initial_short_qty": Decimal,
                    "initial_long_value": Decimal,
                    "initial_short_value": Decimal,
                }
            }。如果提供，将使用此数据作为初始持仓；否则初始持仓为 0（表示第一天计算）。
        
        Returns:
            字典，格式为 {
                "symbol": {
                    "left_long_qty": Decimal,
                    "left_short_qty": Decimal,
                    "left_long_value": Decimal,
                    "left_short_value": Decimal,
                }
            }
        """
        # 1. 初始化按 symbol 分组的数据结构
        by_symbol: Dict[str, Dict[str, Decimal]] = {}
        
        # 如果有初始持仓，先初始化（表示不是第一天计算）
        if initial_positions_dict is not None:
            for s, pos_data in initial_positions_dict.items():
                by_symbol[s] = {
                    "initial_long_qty": pos_data.get("initial_long_qty", Decimal("0")),
                    "initial_short_qty": pos_data.get("initial_short_qty", Decimal("0")),
                    "initial_long_value": pos_data.get("initial_long_value", Decimal("0")),
                    "initial_short_value": pos_data.get("initial_short_value", Decimal("0")),
                    "buy_volume": Decimal("0"),
                    "sell_volume": Decimal("0"),
                    "buy_trade_value": Decimal("0"),
                    "sell_trade_value": Decimal("0"),
                }
        
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
            qty_contracts = row.quantity  # 合约张数

            if trade_symbol not in by_symbol:
                # 如果没有初始持仓，表示这是第一天计算，初始持仓为 0
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

            # 获取合约乘数并转换为币的数量
            contract_multiplier = self._get_contract_multiplier(trade_symbol)
            qty_coins = qty_contracts * contract_multiplier  # 币数量

            # 成交量（币数量）
            if side == "BUY":
                by_symbol[trade_symbol]["buy_volume"] += qty_coins
            elif side == "SELL":
                by_symbol[trade_symbol]["sell_volume"] += qty_coins

            # 成交市值 = 币数量 × 价格
            trade_value = qty_coins * price
            if side == "BUY":
                by_symbol[trade_symbol]["buy_trade_value"] += trade_value
            elif side == "SELL":
                by_symbol[trade_symbol]["sell_trade_value"] += trade_value

        # 3. 计算每个 symbol 的剩余持仓和市值
        result_dict: Dict[str, Dict[str, Decimal]] = {}
        
        for s, data in by_symbol.items():
            initial_long_qty = data["initial_long_qty"]
            initial_short_qty = data["initial_short_qty"]
            initial_long_value = data["initial_long_value"]
            initial_short_value = data["initial_short_value"]
            buy_volume = data["buy_volume"]
            sell_volume = data["sell_volume"]
            buy_trade_value = data["buy_trade_value"]
            sell_trade_value = data["sell_trade_value"]

            # 如果没有任何交易且没有初始持仓，表示第一天且无交易，返回 0
            if buy_volume == 0 and sell_volume == 0 and initial_long_qty == 0 and initial_short_qty == 0:
                result_dict[s] = {
                    "left_long_qty": Decimal("0"),
                    "left_short_qty": Decimal("0"),
                    "left_long_value": Decimal("0"),
                    "left_short_value": Decimal("0"),
                }
                continue

            # 计算总持仓量和市值：初始持仓 + 今日交易
            long_qty = initial_long_qty + buy_volume
            short_qty = initial_short_qty + sell_volume
            long_value = initial_long_value + buy_trade_value
            short_value = initial_short_value + sell_trade_value

            # 计算平均价格
            avg_buy_prz = Decimal("0")
            avg_sell_prz = Decimal("0")
            if long_qty > 0:
                avg_buy_prz = long_value / long_qty
            if short_qty > 0:
                avg_sell_prz = short_value / short_qty

            # 计算轧差数量和剩余持仓
            matched_qty = min(long_qty, short_qty)
            left_long_qty = long_qty - matched_qty
            left_short_qty = short_qty - matched_qty
            
            # 计算剩余市值
            left_long_value = left_long_qty * avg_buy_prz if avg_buy_prz > 0 else Decimal("0")
            left_short_value = left_short_qty * avg_sell_prz if avg_sell_prz > 0 else Decimal("0")

            result_dict[s] = {
                "left_long_qty": left_long_qty,
                "left_short_qty": left_short_qty,
                "left_long_value": left_long_value,
                "left_short_value": left_short_value,
            }

        return result_dict

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
            - matched_qty: 轧差数量 = min(long_qty, short_qty)
            - realized_pnl: 当日已实现盈亏 = matched_qty * (avg_sell_prz - avg_buy_prz)
        """
        # 1. 初始持仓：按需求仅依赖成交，忽略切日前持仓推送，默认 0
        initial_long_qty = Decimal("0")
        initial_short_qty = Decimal("0")
        initial_long_value = Decimal("0")
        initial_short_value = Decimal("0")
        
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

        # 5. 根据你的公式计算"今日"的交易量和市值：
        #   用户公式：long_qty = sum(buy_vol) + pre_long_qty
        #   其中 sum(buy_vol) 是"今日"成交，pre_long_qty 是"昨收持仓"
        #   当前实现：pre_long_qty = initial_long_qty + buy_volume（区间结束时的持仓）
        #   如果区间是"今日"：initial_long_qty 是昨收持仓，buy_volume 是今日成交
        #   所以：long_qty = buy_volume + initial_long_qty = pre_long_qty
        long_qty = pre_long_qty  # = initial_long_qty + buy_volume
        short_qty = pre_short_qty  # = initial_short_qty + sell_volume
        long_value = pre_long_value  # = initial_long_value + buy_trade_value
        short_value = pre_short_value  # = initial_short_value + sell_trade_value

        # 6. 计算平均价格（不可舍入，直接用 Decimal 相除）
        avg_buy_prz = Decimal("0")
        avg_sell_prz = Decimal("0")
        if long_qty > 0:
            avg_buy_prz = long_value / long_qty
        if short_qty > 0:
            avg_sell_prz = short_value / short_qty
        
        # 7. 计算轧差数量和当日已实现盈亏
        matched_qty = min(long_qty, short_qty)
        realized_pnl = Decimal("0")
        if matched_qty > 0:
            realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)
        
        # 8. 计算剩余持仓和市值
        left_long_qty = long_qty - matched_qty
        left_short_qty = short_qty - matched_qty
        left_long_value = left_long_qty * avg_buy_prz if avg_buy_prz > 0 else Decimal("0")
        left_short_value = left_short_qty * avg_sell_prz if avg_sell_prz > 0 else Decimal("0")
        
        # 9. 获取最后一笔成交价（close_prz）
        close_prices = await self._get_close_prices(start_time, end_time, symbol)
        # 如果指定了 symbol，取该 symbol 的 close_prz；否则取所有 symbol 中最大的 close_prz
        if symbol:
            close_prz = close_prices.get(symbol, Decimal("0"))
        else:
            close_prz = max(close_prices.values()) if close_prices else Decimal("0")
        
        # 10. 计算未实现盈亏
        unrealized_pnl = Decimal("0")
        if close_prz > 0:
            unrealized_pnl = (
                left_long_qty * (close_prz - avg_buy_prz) +
                left_short_qty * (avg_sell_prz - close_prz)
            )
        
        # 11. 计算单日 PnL
        daily_pnl = realized_pnl + unrealized_pnl
        
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
            "matched_qty": matched_qty,
            "realized_pnl": realized_pnl,
            "left_long_qty": left_long_qty,
            "left_short_qty": left_short_qty,
            "left_long_value": left_long_value,
            "left_short_value": left_short_value,
            "close_prz": close_prz,
            "unrealized_pnl": unrealized_pnl,
            "daily_pnl": daily_pnl,
        }

    async def calculate_positions_by_symbol(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None,
        initial_positions_dict: Optional[Dict[str, Dict[str, Decimal]]] = None,
    ) -> Dict[str, Dict[str, Decimal]]:
        """按交易对（symbol）维度计算区间内的持仓与交易指标.

        与 ``calculate_position_from_trades`` 类似，但会返回每个 symbol 的独立统计结果。

        Args:
            start_time: 区间开始时间
            end_time: 区间结束时间
            symbol: 交易对（可选）
            initial_positions_dict: 初始持仓字典，格式为 {
                "symbol": {
                    "initial_long_qty": Decimal,
                    "initial_short_qty": Decimal,
                    "initial_long_value": Decimal,
                    "initial_short_value": Decimal,
                }
            }。如果提供，将使用此数据作为初始持仓；否则从持仓表查询。

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
                "ETHUSDT": { ... },
                ...
            }
        """
        # 1. 获取区间开始时的逐 symbol 持仓
        by_symbol: Dict[str, Dict[str, Decimal]] = {}
        
        if initial_positions_dict is not None:
            # 使用提供的初始持仓（从昨日剩余持仓获取）
            for s, pos_data in initial_positions_dict.items():
                by_symbol[s] = {
                    "initial_long_qty": pos_data.get("initial_long_qty", Decimal("0")),
                    "initial_short_qty": pos_data.get("initial_short_qty", Decimal("0")),
                    "initial_long_value": pos_data.get("initial_long_value", Decimal("0")),
                    "initial_short_value": pos_data.get("initial_short_value", Decimal("0")),
                    "buy_volume": Decimal("0"),
                    "sell_volume": Decimal("0"),
                    "buy_trade_value": Decimal("0"),
                    "sell_trade_value": Decimal("0"),
                }

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
            qty_contracts = row.quantity  # 合约张数

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

            # 获取合约乘数并转换为币的数量
            contract_multiplier = self._get_contract_multiplier(trade_symbol)
            qty_coins = qty_contracts * contract_multiplier  # 币数量

            # 成交量（币数量）
            if side == "BUY":
                by_symbol[trade_symbol]["buy_volume"] += qty_coins
            elif side == "SELL":
                by_symbol[trade_symbol]["sell_volume"] += qty_coins

            # 成交市值 = 币数量 × 价格
            trade_value = qty_coins * price
            if side == "BUY":
                by_symbol[trade_symbol]["buy_trade_value"] += trade_value
            elif side == "SELL":
                by_symbol[trade_symbol]["sell_trade_value"] += trade_value

        # 2.5 获取每个 symbol 的最后一笔成交价（close_prz）
        close_prices = await self._get_close_prices(start_time, end_time, symbol)

        # 3. 计算每个 symbol 的最终指标
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

            # 根据用户公式：long_qty = sum(buy_vol) + pre_long_qty
            # 其中 pre_long_qty 是"昨收持仓"（= initial_long_qty），sum(buy_vol) 是"今日"成交（= buy_volume）
            # 所以：long_qty = buy_volume + initial_long_qty = pre_long_qty
            long_qty = pre_long_qty  # = initial_long_qty + buy_volume
            short_qty = pre_short_qty  # = initial_short_qty + sell_volume
            long_value = pre_long_value  # = initial_long_value + buy_trade_value
            short_value = pre_short_value  # = initial_short_value + sell_trade_value

            avg_buy_prz = Decimal("0")
            avg_sell_prz = Decimal("0")
            if long_qty > 0:
                avg_buy_prz = long_value / long_qty
            if short_qty > 0:
                avg_sell_prz = short_value / short_qty

            matched_qty = min(long_qty, short_qty)
            realized_pnl = Decimal("0")
            if matched_qty > 0:
                realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)

            # 计算剩余持仓和市值
            left_long_qty = long_qty - matched_qty
            left_short_qty = short_qty - matched_qty
            left_long_value = left_long_qty * avg_buy_prz if avg_buy_prz > 0 else Decimal("0")
            left_short_value = left_short_qty * avg_sell_prz if avg_sell_prz > 0 else Decimal("0")

            # 获取最后一笔成交价（close_prz）
            close_prz = close_prices.get(s, Decimal("0"))

            # 计算未实现盈亏
            unrealized_pnl = Decimal("0")
            if close_prz > 0:
                unrealized_pnl = (
                    left_long_qty * (close_prz - avg_buy_prz) +
                    left_short_qty * (avg_sell_prz - close_prz)
                )

            # 计算单日 PnL
            daily_pnl = realized_pnl + unrealized_pnl

            # 更新返回结果，包含所有计算过程中的中间变量值（便于调试和验证）
            data.update(
                {
                    # 1. 初始持仓（昨日剩余持仓或区间开始时的持仓）
                    "initial_long_qty": initial_long_qty,
                    "initial_short_qty": initial_short_qty,
                    "initial_long_value": initial_long_value,
                    "initial_short_value": initial_short_value,
                    
                    # 2. 今日交易统计（区间内的成交记录）
                    "buy_volume": buy_volume,
                    "sell_volume": sell_volume,
                    "buy_trade_value": buy_trade_value,
                    "sell_trade_value": sell_trade_value,
                    
                    # 3. 总持仓量和市值（初始持仓 + 今日交易）
                    "pre_long_qty": pre_long_qty,  # = initial_long_qty + buy_volume
                    "pre_short_qty": pre_short_qty,  # = initial_short_qty + sell_volume
                    "pre_long_value": pre_long_value,  # = initial_long_value + buy_trade_value
                    "pre_short_value": pre_short_value,  # = initial_short_value + sell_trade_value
                    
                    # 4. 多头和空头交易量及市值（与 pre_* 相同，保持命名一致性）
                    "long_qty": long_qty,  # = pre_long_qty = initial_long_qty + buy_volume
                    "short_qty": short_qty,  # = pre_short_qty = initial_short_qty + sell_volume
                    "long_value": long_value,  # = pre_long_value = initial_long_value + buy_trade_value
                    "short_value": short_value,  # = pre_short_value = initial_short_value + sell_trade_value
                    
                    # 5. 平均价格
                    "avg_buy_prz": avg_buy_prz,  # = long_value / long_qty
                    "avg_sell_prz": avg_sell_prz,  # = short_value / short_qty
                    
                    # 6. 已实现盈亏
                    "matched_qty": matched_qty,  # = min(long_qty, short_qty)
                    "realized_pnl": realized_pnl,  # = matched_qty * (avg_sell_prz - avg_buy_prz)
                    
                    # 7. 剩余持仓和市值
                    "left_long_qty": left_long_qty,  # = long_qty - matched_qty
                    "left_short_qty": left_short_qty,  # = short_qty - matched_qty
                    "left_long_value": left_long_value,  # = left_long_qty * avg_buy_prz
                    "left_short_value": left_short_value,  # = left_short_qty * avg_sell_prz
                    
                    # 8. 未实现盈亏
                    "close_prz": close_prz,  # 当日最后一笔成交价
                    "unrealized_pnl": unrealized_pnl,  # = left_long_qty * (close_prz - avg_buy_prz) + left_short_qty * (avg_sell_prz - close_prz)
                    
                    # 9. 单日 PnL
                    "daily_pnl": daily_pnl,  # = realized_pnl + unrealized_pnl
                }
            )

        return by_symbol
    
    async def calculate_cumulative_pnl(
        self,
        start_date: datetime,
        end_date: datetime,
        symbol: Optional[str] = None
    ) -> Dict[str, Dict[str, Decimal]]:
        """计算累计 PnL（按币种分别计算）.
        
        计算逻辑：
        - 累计已实现盈亏 = 从 start_date 到 end_date 的所有已实现盈亏累加（按币种）
        - 当前未实现盈亏 = end_date 时刻的未实现盈亏（按币种）
        - 累计 PnL = 累计已实现盈亏 + 当前未实现盈亏
        
        Args:
            start_date: 起始日期（UTC，例如：30 天前）
            end_date: 结束日期（UTC，例如：当前时间）
            symbol: 交易对（可选），如果不指定则统计所有交易对
        
        Returns:
            字典，格式为:
            {
                "BTCUSDT": {
                    "cumulative_realized_pnl": Decimal,
                    "current_unrealized_pnl": Decimal,
                    "cumulative_pnl": Decimal,
                },
                "ETHUSDT": {...},
                "TOTAL": {...}  # 所有币种汇总
            }
        """
        # 按币种分别计算累计 PnL
        by_symbol: Dict[str, Dict[str, Decimal]] = {}
        
        # 遍历每一天，按币种累加已实现盈亏
        current_date = start_date.date()
        end_date_only = end_date.date()
        
        while current_date <= end_date_only:
            day_start = datetime(current_date.year, current_date.month, current_date.day)
            day_end = day_start + timedelta(days=1)
            
            # 如果当天还没结束，使用当前时间作为结束时间
            if current_date == end_date_only:
                day_end = end_date
            
            # 计算当天的指标（按币种）
            day_metrics_by_symbol = await self.calculate_positions_by_symbol(
                start_time=day_start,
                end_time=day_end,
                symbol=symbol
            )
            
            # 累加每个币种的已实现盈亏
            for s, metrics in day_metrics_by_symbol.items():
                if s == "TOTAL":
                    continue  # TOTAL 最后单独计算
                
                if s not in by_symbol:
                    by_symbol[s] = {
                        "cumulative_realized_pnl": Decimal("0"),
                        "current_unrealized_pnl": Decimal("0"),
                        "cumulative_pnl": Decimal("0"),
                    }
                
                day_realized_pnl = metrics.get("realized_pnl", Decimal("0"))
                by_symbol[s]["cumulative_realized_pnl"] += day_realized_pnl
            
            current_date += timedelta(days=1)
        
        # 计算当前时刻（end_date）的未实现盈亏（按币种）
        current_metrics_by_symbol = await self.calculate_positions_by_symbol(
            start_time=datetime(end_date_only.year, end_date_only.month, end_date_only.day),
            end_time=end_date,
            symbol=symbol
        )
        
        # 更新每个币种的当前未实现盈亏和累计 PnL
        for s, metrics in current_metrics_by_symbol.items():
            if s == "TOTAL":
                continue
            
            if s not in by_symbol:
                by_symbol[s] = {
                    "cumulative_realized_pnl": Decimal("0"),
                    "current_unrealized_pnl": Decimal("0"),
                    "cumulative_pnl": Decimal("0"),
                }
            
            current_unrealized_pnl = metrics.get("unrealized_pnl", Decimal("0"))
            by_symbol[s]["current_unrealized_pnl"] = current_unrealized_pnl
            by_symbol[s]["cumulative_pnl"] = (
                by_symbol[s]["cumulative_realized_pnl"] + current_unrealized_pnl
            )
        
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
        # 按你的要求：仅依赖成交数据，忽略切日前最后一笔持仓推送，初始持仓为空
        return {}
    
    async def _calculate_trade_volumes(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None
    ) -> tuple[Decimal, Decimal]:
        """统计区间内所有成交记录的成交量（币数量）.
        
        Args:
            start_time: 区间开始时间
            end_time: 区间结束时间
            symbol: 交易对（可选）
        
        Returns:
            (buy_volume, sell_volume) 元组，单位为币数量
        """
        # 根据交易所选择时间字段
        time_column = self.TradeModel.transaction_time if self.exchange == "binance" else self.TradeModel.update_time
        
        # 需要按 symbol 分组，因为不同 symbol 的合约乘数可能不同
        query = (
            select(
                self.TradeModel.symbol,
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
        
        query = query.group_by(self.TradeModel.symbol, self.TradeModel.side)
        
        result = await self.db_session.execute(query)
        rows = result.all()
        
        buy_volume = Decimal("0")
        sell_volume = Decimal("0")
        
        for trade_symbol, side, total_quantity_contracts in rows:
            # 获取合约乘数并转换为币的数量
            contract_multiplier = self._get_contract_multiplier(trade_symbol)
            total_quantity_coins = (total_quantity_contracts or Decimal("0")) * contract_multiplier
            
            if side.upper() == "BUY":
                buy_volume += total_quantity_coins
            elif side.upper() == "SELL":
                sell_volume += total_quantity_coins
        
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
    
    async def _get_close_prices(
        self,
        start_time: datetime,
        end_time: datetime,
        symbol: Optional[str] = None
    ) -> Dict[str, Decimal]:
        """获取每个 symbol 的最后一笔成交价（close_prz）.
        
        Args:
            start_time: 区间开始时间
            end_time: 区间结束时间
            symbol: 交易对（可选）
        
        Returns:
            字典，格式为 {symbol: close_price}
        """
        time_column = (
            self.TradeModel.transaction_time
            if self.exchange == "binance"
            else self.TradeModel.update_time
        )
        
        # 子查询：找到每个 symbol 的最后一笔成交时间
        subquery = (
            select(
                self.TradeModel.symbol,
                func.max(time_column).label('max_time')
            )
            .where(time_column >= start_time)
            .where(time_column < end_time)
        )
        
        if self.exchange == "binance":
            subquery = subquery.where(self.TradeModel.exchange == 'binance_perp')
        if self.account_id:
            subquery = subquery.where(self.TradeModel.account_id == self.account_id)
        if symbol:
            subquery = subquery.where(self.TradeModel.symbol == symbol)
        
        subquery = subquery.group_by(self.TradeModel.symbol).subquery()
        
        # 主查询：获取最后一笔成交的价格
        # 使用窗口函数或者更简单的方法：对每个 symbol，找到最大时间对应的第一条记录
        from sqlalchemy import distinct
        
        # 使用子查询 + JOIN 的方式，但需要处理同一时间多笔成交的情况
        # 简化：直接查询所有记录，在 Python 中处理
        query_all = (
            select(
                self.TradeModel.symbol,
                self.TradeModel.price,
                time_column
            )
            .where(time_column >= start_time)
            .where(time_column < end_time)
        )
        
        if self.exchange == "binance":
            query_all = query_all.where(self.TradeModel.exchange == 'binance_perp')
        if self.account_id:
            query_all = query_all.where(self.TradeModel.account_id == self.account_id)
        if symbol:
            query_all = query_all.where(self.TradeModel.symbol == symbol)
        
        query_all = query_all.order_by(self.TradeModel.symbol, time_column.desc())
        
        result = await self.db_session.execute(query_all)
        rows = result.all()
        
        # 在 Python 中处理：对每个 symbol，取第一条（即时间最大的）
        close_prices = {}
        seen_symbols = set()
        for row in rows:
            if row.symbol not in seen_symbols:
                close_prices[row.symbol] = row.price
                seen_symbols.add(row.symbol)
        
        return close_prices

    async def get_daily_trade_stats(
        self,
        start_date: date,
        end_date: date,
        symbol: Optional[str] = None,
    ) -> Dict[date, Dict[str, Decimal]]:
        """按日汇总成交数据（等价于 SQL 的 daily_trades CTE）.
        
        Args:
            start_date: 起始日期（包含）
            end_date: 结束日期（包含）
            symbol: 交易对（可选），如果不指定则统计所有交易对
        
        Returns:
            {
                trade_date: {
                    "buy_volume": Decimal,
                    "sell_volume": Decimal,
                    "buy_trade_value": Decimal,
                    "sell_trade_value": Decimal,
                },
                ...
            }
        """
        from sqlalchemy import cast, Date
        
        time_column = (
            self.TradeModel.transaction_time
            if self.exchange == "binance"
            else self.TradeModel.update_time
        )
        
        # 构建查询：按日期分组，统计买卖量和“基础市值”（未乘合约乘数）
        query = (
            select(
                cast(time_column, Date).label("trade_date"),
                self.TradeModel.symbol,
                func.sum(
                    case(
                        (self.TradeModel.side.in_(["BUY", "buy"]), self.TradeModel.quantity),
                        else_=0,
                    )
                ).label("buy_volume"),
                func.sum(
                    case(
                        (self.TradeModel.side.in_(["SELL", "sell"]), self.TradeModel.quantity),
                        else_=0,
                    )
                ).label("sell_volume"),
                func.sum(
                    case(
                        (
                            self.TradeModel.side.in_(["BUY", "buy"]),
                            self.TradeModel.quantity * self.TradeModel.price,
                        ),
                        else_=0,
                    )
                ).label("buy_trade_value_base"),
                func.sum(
                    case(
                        (
                            self.TradeModel.side.in_(["SELL", "sell"]),
                            self.TradeModel.quantity * self.TradeModel.price,
                        ),
                        else_=0,
                    )
                ).label("sell_trade_value_base"),
            )
            .where(time_column >= datetime.combine(start_date, datetime.min.time()))
            .where(time_column < datetime.combine(end_date, datetime.min.time()) + timedelta(days=1))
            .group_by(cast(time_column, Date), self.TradeModel.symbol)
        )
        
        if self.exchange == "binance":
            query = query.where(self.TradeModel.exchange == "binance_perp")
        if self.account_id:
            query = query.where(self.TradeModel.account_id == self.account_id)
        if symbol:
            query = query.where(self.TradeModel.symbol == symbol)
        
        result = await self.db_session.execute(query)
        rows = result.all()
        
        # 按日期和 symbol 组织数据，并在 Python 侧应用合约乘数
        daily_stats: Dict[date, Dict[str, Dict[str, Decimal]]] = {}
        for row in rows:
            trade_date = row.trade_date
            sym = row.symbol
            # 获取该 symbol 的合约乘数（这里是普通的 Python 调用，不会再传入列对象）
            multiplier = self._get_contract_multiplier(sym)

            buy_value_base = row.buy_trade_value_base or Decimal("0")
            sell_value_base = row.sell_trade_value_base or Decimal("0")

            if trade_date not in daily_stats:
                daily_stats[trade_date] = {}
            daily_stats[trade_date][sym] = {
                "buy_volume": row.buy_volume or Decimal("0"),
                "sell_volume": row.sell_volume or Decimal("0"),
                # 最终的买入/卖出市值 = 基础市值 * 合约乘数
                "buy_trade_value": buy_value_base * multiplier,
                "sell_trade_value": sell_value_base * multiplier,
            }
        
        # 如果指定了 symbol，只返回该 symbol 的数据；否则返回所有 symbol
        if symbol:
            return {
                d: {symbol: stats.get(symbol, {
                    "buy_volume": Decimal("0"),
                    "sell_volume": Decimal("0"),
                    "buy_trade_value": Decimal("0"),
                    "sell_trade_value": Decimal("0"),
                })}
                for d, stats in daily_stats.items()
            }
        else:
            return daily_stats

    def calc_daily_realized_series(
        self,
        daily_stats: Dict[date, Dict[str, Dict[str, Decimal]]],
    ) -> Dict[date, Dict[str, Dict[str, Decimal]]]:
        """按日度逻辑计算每日和累积已实现盈亏（等价于你 SQL 的完整逻辑）.
        
        输入: 从最早日期开始的 daily_stats，格式为 {
            trade_date: {
                symbol: {
                    "buy_volume", "sell_volume", "buy_trade_value", "sell_trade_value"
                }
            }
        }
        
        输出: 每个 trade_date 的完整指标，格式为 {
            trade_date: {
                symbol: {
                    "open_left_long_qty", "open_left_short_qty",
                    "open_left_long_value", "open_left_short_value",
                    "daily_buy_volume", "daily_sell_volume",
                    "daily_buy_value", "daily_sell_value",
                    "total_long_qty", "total_short_qty",
                    "total_long_value", "total_short_value",
                    "avg_buy_prz", "avg_sell_prz",
                    "matched_qty", "daily_matched_qty",
                    "daily_realized_pnl",
                    "cumulative_realized_pnl",
                    "close_left_long_qty", "close_left_short_qty",
                    "close_left_long_value", "close_left_short_value",
                }
            }
        }
        """
        if not daily_stats:
            return {}
        
        # 按日期排序
        sorted_dates = sorted(daily_stats.keys())
        if not sorted_dates:
            return {}
        
        # 收集所有 symbol
        all_symbols = set()
        for day_stats in daily_stats.values():
            all_symbols.update(day_stats.keys())
        
        result: Dict[date, Dict[str, Dict[str, Decimal]]] = {}
        
        # 为每个 symbol 维护累计值
        cumulative_by_symbol: Dict[str, Dict[str, Decimal]] = {
            sym: {
                "cumulative_buy_volume": Decimal("0"),
                "cumulative_sell_volume": Decimal("0"),
                "cumulative_buy_value": Decimal("0"),
                "cumulative_sell_value": Decimal("0"),
                "cumulative_realized_pnl": Decimal("0"),
                "prev_matched_qty": Decimal("0"),
            }
            for sym in all_symbols
        }
        
        # 逐日计算
        for trade_date in sorted_dates:
            day_data = daily_stats.get(trade_date, {})
            result[trade_date] = {}
            
            for symbol in all_symbols:
                sym_stats = day_data.get(symbol, {
                    "buy_volume": Decimal("0"),
                    "sell_volume": Decimal("0"),
                    "buy_trade_value": Decimal("0"),
                    "sell_trade_value": Decimal("0"),
                })
                
                cum = cumulative_by_symbol[symbol]
                
                # 更新累计值
                cum["cumulative_buy_volume"] += sym_stats["buy_volume"]
                cum["cumulative_sell_volume"] += sym_stats["sell_volume"]
                cum["cumulative_buy_value"] += sym_stats["buy_trade_value"]
                cum["cumulative_sell_value"] += sym_stats["sell_trade_value"]
                
                # 前一日累计值（用于计算开盘持仓）
                prev_cum_buy_vol = cum["cumulative_buy_volume"] - sym_stats["buy_volume"]
                prev_cum_sell_vol = cum["cumulative_sell_volume"] - sym_stats["sell_volume"]
                prev_cum_buy_val = cum["cumulative_buy_value"] - sym_stats["buy_trade_value"]
                prev_cum_sell_val = cum["cumulative_sell_value"] - sym_stats["sell_trade_value"]
                
                # 前一日平均价和轧差
                prev_avg_buy_prz = (
                    prev_cum_buy_val / prev_cum_buy_vol
                    if prev_cum_buy_vol > 0 else Decimal("0")
                )
                prev_avg_sell_prz = (
                    prev_cum_sell_val / prev_cum_sell_vol
                    if prev_cum_sell_vol > 0 else Decimal("0")
                )
                prev_matched_qty = min(prev_cum_buy_vol, prev_cum_sell_vol)
                
                # 今日开盘持仓（= 昨日收盘持仓）
                open_left_long_qty = prev_cum_buy_vol - prev_matched_qty
                open_left_short_qty = prev_cum_sell_vol - prev_matched_qty
                open_left_long_value = open_left_long_qty * prev_avg_buy_prz if prev_avg_buy_prz > 0 else Decimal("0")
                open_left_short_value = open_left_short_qty * prev_avg_sell_prz if prev_avg_sell_prz > 0 else Decimal("0")
                
                # 当日成交量和市值
                daily_buy_volume = sym_stats["buy_volume"]
                daily_sell_volume = sym_stats["sell_volume"]
                daily_buy_value = sym_stats["buy_trade_value"]
                daily_sell_value = sym_stats["sell_trade_value"]
                
                # 总持仓量 = 初始持仓 + 当日成交量
                total_long_qty = open_left_long_qty + daily_buy_volume
                total_short_qty = open_left_short_qty + daily_sell_volume
                
                # 总持仓市值 = 初始市值 + 当日成交市值
                total_long_value = open_left_long_value + daily_buy_value
                total_short_value = open_left_short_value + daily_sell_value
                
                # 平均买价 = 总多头市值 / 总多头持仓量
                avg_buy_prz = (
                    total_long_value / total_long_qty
                    if total_long_qty > 0 else Decimal("0")
                )
                # 平均卖价 = 当日卖市值 / 当日卖量（不是累计平均）
                avg_sell_prz = (
                    daily_sell_value / daily_sell_volume
                    if daily_sell_volume > 0 else Decimal("0")
                )
                
                # 轧差数量 = min(总多头持仓, 总空头持仓)
                matched_qty = min(total_long_qty, total_short_qty)
                
                # 昨日累计轧差（用于记录）
                prev_matched_qty_calc = cum["prev_matched_qty"]
                
                # 今日新增轧差（用于记录，但计算已实现盈亏时用总轧差）
                daily_matched_qty = matched_qty - prev_matched_qty_calc
                
                # 今日已实现盈亏 = (平均卖价 - 平均买价) * 总轧差数量
                # 按照你的计算方式：用当天的 matched_qty（总轧差）来计算
                daily_realized_pnl = Decimal("0")
                if matched_qty > 0 and avg_sell_prz > 0 and avg_buy_prz > 0:
                    daily_realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)
                
                # 更新累积已实现盈亏
                cum["cumulative_realized_pnl"] += daily_realized_pnl
                cum["prev_matched_qty"] = matched_qty
                
                # 今日收盘持仓
                left_long_qty = total_long_qty - matched_qty
                left_short_qty = total_short_qty - matched_qty
                left_long_value = left_long_qty * avg_buy_prz if avg_buy_prz > 0 else Decimal("0")
                left_short_value = left_short_qty * avg_sell_prz if avg_sell_prz > 0 else Decimal("0")
                
                result[trade_date][symbol] = {
                    "open_left_long_qty": open_left_long_qty,
                    "open_left_short_qty": open_left_short_qty,
                    "open_left_long_value": open_left_long_value,
                    "open_left_short_value": open_left_short_value,
                    "daily_buy_volume": sym_stats["buy_volume"],
                    "daily_sell_volume": sym_stats["sell_volume"],
                    "daily_buy_value": sym_stats["buy_trade_value"],
                    "daily_sell_value": sym_stats["sell_trade_value"],
                    "total_long_qty": total_long_qty,
                    "total_short_qty": total_short_qty,
                    "total_long_value": total_long_value,
                    "total_short_value": total_short_value,
                    "avg_buy_prz": avg_buy_prz,
                    "avg_sell_prz": avg_sell_prz,
                    "matched_qty": matched_qty,
                    "daily_matched_qty": daily_matched_qty,
                    "daily_realized_pnl": daily_realized_pnl,
                    "cumulative_realized_pnl": cum["cumulative_realized_pnl"],
                    "close_left_long_qty": left_long_qty,  # 返回时 key 保持 close_left_* 用于兼容，但值来自 left_*
                    "close_left_short_qty": left_short_qty,
                    "close_left_long_value": left_long_value,
                    "close_left_short_value": left_short_value,
                }
        
        return result

