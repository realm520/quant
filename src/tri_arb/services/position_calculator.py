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
from typing import Dict, Optional, Callable, Any

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
            - matched_qty: 轧差数量 = min(long_qty, short_qty)
            - realized_pnl: 当日已实现盈亏 = matched_qty * (avg_sell_prz - avg_buy_prz)
        """
        # 1. 获取区间开始时的持仓（之前遗留的未平仓持仓）
        initial_positions = await self._get_initial_positions(start_time, symbol)
        initial_long_qty = Decimal("0")
        initial_short_qty = Decimal("0")
        initial_long_value = Decimal("0")
        initial_short_value = Decimal("0")
        
        # 计算初始持仓量和市值（使用开仓均价）
        # 注意：_get_initial_positions 返回的 quantity 已经是币数量（对于 XT 已转换）
        for symbol_key, pos_data in initial_positions.items():
            # symbol_key 格式是 "symbol_LONG" 或 "symbol_SHORT"
            # 需要去掉最后一部分（side）来获取完整的 symbol
            side = pos_data.get("side", "").upper()
            # 去掉末尾的 "_LONG" 或 "_SHORT" 来获取完整的 symbol
            if symbol_key.endswith(f"_{side}"):
                pos_symbol = symbol_key[:-len(f"_{side}")]
            else:
                # 兼容处理：如果格式不对，尝试 split
                pos_symbol = symbol_key.rsplit("_", 1)[0] if "_" in symbol_key else symbol_key
            quantity_coins = pos_data.get("quantity", Decimal("0"))  # 已经是币数量
            entry_price = pos_data.get("entry_price", Decimal("0"))
            
            # 市值 = 币数量 × 开仓均价
            position_value = quantity_coins * entry_price
            
            if side == "LONG":
                initial_long_qty += quantity_coins  # 币数量
                initial_long_value += position_value
            elif side == "SHORT":
                initial_short_qty += quantity_coins  # 币数量
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
        else:
            # 从持仓表查询初始持仓（兼容旧逻辑）
            initial_positions = await self._get_initial_positions(start_time, symbol)
            
            # 先构建逐 symbol 的初始多空持仓与市值
            # 注意：_get_initial_positions 返回的 quantity 已经是币数量（对于 XT 已转换）
            for symbol_key, pos_data in initial_positions.items():
                # symbol_key 格式是 "symbol_LONG" 或 "symbol_SHORT"
                # 需要去掉最后一部分（side）来获取完整的 symbol
                side = pos_data.get("side", "").upper()
                # 去掉末尾的 "_LONG" 或 "_SHORT" 来获取完整的 symbol
                if symbol_key.endswith(f"_{side}"):
                    pos_symbol = symbol_key[:-len(f"_{side}")]
                else:
                    # 兼容处理：如果格式不对，尝试 split
                    pos_symbol = symbol_key.rsplit("_", 1)[0] if "_" in symbol_key else symbol_key
                
                quantity_coins = pos_data.get("quantity", Decimal("0"))  # 已经是币数量
                entry_price = pos_data.get("entry_price", Decimal("0"))

                # 市值 = 币数量 × 价格
                position_value = quantity_coins * entry_price

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
                    by_symbol[s]["initial_long_qty"] += quantity_coins  # 币数量
                    by_symbol[s]["initial_long_value"] += position_value
                elif side == "SHORT":
                    by_symbol[s]["initial_short_qty"] += quantity_coins  # 币数量
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

            # 输出详细计算过程日志
            logger.info(
                f"[{s}] 开始计算持仓指标",
                start_time=start_time,
                end_time=end_time,
            )
            logger.info(
                f"[{s}] 1. 初始持仓（昨收持仓）",
                initial_long_qty=float(initial_long_qty),
                initial_short_qty=float(initial_short_qty),
                initial_long_value=float(initial_long_value),
                initial_short_value=float(initial_short_value),
            )
            logger.info(
                f"[{s}] 2. 今日交易统计",
                buy_volume=float(buy_volume),
                sell_volume=float(sell_volume),
                buy_trade_value=float(buy_trade_value),
                sell_trade_value=float(sell_trade_value),
            )

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

            logger.info(
                f"[{s}] 3. 计算总持仓量和市值",
                long_qty=f"{float(initial_long_qty)} + {float(buy_volume)} = {float(long_qty)}",
                short_qty=f"{float(initial_short_qty)} + {float(sell_volume)} = {float(short_qty)}",
                long_value=f"{float(initial_long_value)} + {float(buy_trade_value)} = {float(long_value)}",
                short_value=f"{float(initial_short_value)} + {float(sell_trade_value)} = {float(short_value)}",
            )

            avg_buy_prz = Decimal("0")
            avg_sell_prz = Decimal("0")
            if long_qty > 0:
                avg_buy_prz = long_value / long_qty
            if short_qty > 0:
                avg_sell_prz = short_value / short_qty

            logger.info(
                f"[{s}] 4. 计算平均价格",
                avg_buy_prz=f"{float(long_value)} / {float(long_qty)} = {float(avg_buy_prz)}",
                avg_sell_prz=f"{float(short_value)} / {float(short_qty)} = {float(avg_sell_prz)}",
            )

            matched_qty = min(long_qty, short_qty)
            realized_pnl = Decimal("0")
            if matched_qty > 0:
                realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)

            logger.info(
                f"[{s}] 5. 计算已实现盈亏",
                matched_qty=f"min({float(long_qty)}, {float(short_qty)}) = {float(matched_qty)}",
                realized_pnl=f"{float(matched_qty)} * ({float(avg_sell_prz)} - {float(avg_buy_prz)}) = {float(realized_pnl)}",
            )

            # 计算剩余持仓和市值
            left_long_qty = long_qty - matched_qty
            left_short_qty = short_qty - matched_qty
            left_long_value = left_long_qty * avg_buy_prz if avg_buy_prz > 0 else Decimal("0")
            left_short_value = left_short_qty * avg_sell_prz if avg_sell_prz > 0 else Decimal("0")

            logger.info(
                f"[{s}] 6. 计算剩余持仓",
                left_long_qty=f"{float(long_qty)} - {float(matched_qty)} = {float(left_long_qty)}",
                left_short_qty=f"{float(short_qty)} - {float(matched_qty)} = {float(left_short_qty)}",
                left_long_value=f"{float(left_long_qty)} * {float(avg_buy_prz)} = {float(left_long_value)}",
                left_short_value=f"{float(left_short_qty)} * {float(avg_sell_prz)} = {float(left_short_value)}",
            )

            # 获取最后一笔成交价（close_prz）
            close_prz = close_prices.get(s, Decimal("0"))

            # 计算未实现盈亏
            unrealized_pnl = Decimal("0")
            if close_prz > 0:
                long_unrealized = left_long_qty * (close_prz - avg_buy_prz)
                short_unrealized = left_short_qty * (avg_sell_prz - close_prz)
                unrealized_pnl = long_unrealized + short_unrealized
                
                logger.info(
                    f"[{s}] 7. 计算未实现盈亏",
                    close_prz=float(close_prz),
                    long_unrealized=f"{float(left_long_qty)} * ({float(close_prz)} - {float(avg_buy_prz)}) = {float(long_unrealized)}",
                    short_unrealized=f"{float(left_short_qty)} * ({float(avg_sell_prz)} - {float(close_prz)}) = {float(short_unrealized)}",
                    unrealized_pnl=f"{float(long_unrealized)} + {float(short_unrealized)} = {float(unrealized_pnl)}",
                )
            else:
                logger.warning(f"[{s}] 7. 计算未实现盈亏: close_prz 为 0，无法计算未实现盈亏")

            # 计算单日 PnL
            daily_pnl = realized_pnl + unrealized_pnl
            
            logger.info(
                f"[{s}] 8. 计算单日 PnL",
                daily_pnl=f"{float(realized_pnl)} + {float(unrealized_pnl)} = {float(daily_pnl)}",
            )

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
                quantity = abs(pos.position_amount)  # Binance 的 position_amount 已经是币数量
                entry_price = pos.entry_price or Decimal("0")
                # Binance 不需要合约乘数转换
                notional = quantity * entry_price if entry_price > 0 else Decimal("0")
            else:  # xt
                symbol_key = pos.symbol
                side = pos.side.upper()
                quantity_contracts = pos.quantity  # XT 的 quantity 是合约张数
                entry_price = pos.entry_price or Decimal("0")
                # 转换为币数量（合约张数 × 合约乘数）
                contract_multiplier = self._get_contract_multiplier(symbol_key)
                quantity = quantity_contracts * contract_multiplier  # 币数量
                # 市值 = 币数量 × 价格
                notional = quantity * entry_price if entry_price > 0 else Decimal("0")
            
            key = f"{symbol_key}_{side}"
            
            position_dict[key] = {
                "quantity": quantity,  # 现在统一为币数量
                "entry_price": entry_price,
                "notional": notional,  # 市值（币数量 × 价格）
                "side": side,
            }
        
        return position_dict
    
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

