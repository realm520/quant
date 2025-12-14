#!/usr/bin/env python3
"""基于成交记录的"今日"持仓与交易统计调试脚本（UTC+0）。

统计区间：当日 UTC 00:00 ~ 当前时间（左闭右开 [00:00, now)）。

输出内容（按币种分别显示）：
1. 昨收持仓：pre_long_qty, pre_short_qty, pre_long_value, pre_short_value
2. 今日交易：long_qty, short_qty, long_value, short_value, avg_buy_prz, avg_sell_prz
3. 已实现 Pnl：matched_qty, realized_pnl
4. 当日剩余仓位：left_long_qty, left_short_qty, left_long_value, left_short_value, close_prz, unrealized_pnl
5. Pnl 汇总：daily_pnl, cumulative_pnl
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService

# 硬编码数据库地址（从 accounts.json 中获取）
DATABASE_URL = "postgresql+asyncpg://oliver:oliver%230987654321@quant-infra-pg-cluster.cluster-cjhorql2nmcs.ap-southeast-1.rds.amazonaws.com:5432/trading"

console = Console()


def _format_dec(value: Decimal, prec: int = 8) -> str:
    if value is None:
        return "0"
    # 不四舍五入，只做字符串格式化
    q = value.quantize(Decimal("1e-%d" % prec))
    return format(q, "f")


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="调试单账号今日持仓与交易统计（UTC+0 当日 00:00~当前），支持按币种拆分。"
    )
    parser.add_argument(
        "--account-id",
        type=str,
        required=True,
        help="账号ID，如 account_008 或 binance_main_001（将用于数据库中的 account_id 过滤）",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        choices=["binance", "xt"],
        required=True,
        help="交易所标识（binance 或 xt）",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="可选：指定单个交易对（如 tradoor_usdt），否则统计该账号下所有交易对并逐币种展示",
    )

    args = parser.parse_args()

    # 使用硬编码的数据库地址
    db_manager = DatabaseManager(database_url=DATABASE_URL)

    # 计算今日 UTC 区间（转换为 naive datetime，因为数据库字段是 TIMESTAMP WITHOUT TIME ZONE）
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    start_time = datetime(today.year, today.month, today.day).replace(tzinfo=None)  # 今日 00:00 UTC（naive）
    end_time = now_utc.replace(tzinfo=None)  # 当前 UTC（naive）

    # 计算昨日 UTC 区间（用于显示"昨收持仓"）
    yesterday = today - timedelta(days=1)
    yesterday_start = datetime(yesterday.year, yesterday.month, yesterday.day).replace(tzinfo=None)  # 昨日 00:00 UTC（naive）
    yesterday_end = datetime(today.year, today.month, today.day).replace(tzinfo=None)  # 昨日 24:00 UTC（即今日 00:00，naive）
    
    # 计算前日 UTC 区间（用于显示"前日收盘持仓"）
    day_before_yesterday = yesterday - timedelta(days=1)
    day_before_yesterday_start = datetime(day_before_yesterday.year, day_before_yesterday.month, day_before_yesterday.day).replace(tzinfo=None)  # 前日 00:00 UTC（naive）
    day_before_yesterday_end = datetime(yesterday.year, yesterday.month, yesterday.day).replace(tzinfo=None)  # 前日 24:00 UTC（即昨日 00:00，naive）

    console.print(
        f"[cyan]统计区间 (UTC+0): {start_time.isoformat()} -> {end_time.isoformat()}[/cyan]"
    )
    console.print(f"[cyan]账号: {args.account_id}, 交易所: {args.exchange}[/cyan]")
    
    # 计算多日 PnL 的起始日期（从月初开始，或从30天前开始）
    month_start = datetime(today.year, today.month, 1).replace(tzinfo=None)  # 本月1日（naive）
    # 如果本月1日早于今日，则从本月1日开始；否则从30天前开始
    if month_start < start_time:
        cumulative_start = month_start
    else:
        cumulative_start = start_time - timedelta(days=30)
    
    cumulative_start_date = cumulative_start.date()
    console.print(f"[dim]多日 PnL 计算起始日期: {cumulative_start_date}[/dim]\n")
    
    async with db_manager.session() as session:
        # 初始化合约乘数服务
        contract_multiplier_service = ContractMultiplierService()
        
        def sync_getter(symbol: str) -> Decimal:
            """同步获取合约乘数."""
            return contract_multiplier_service.get_multiplier_sync(args.exchange, symbol)
        
        contract_multiplier_getter = sync_getter
        
        calc = PositionCalculator(
            session,
            exchange=args.exchange,
            account_id=args.account_id,
            contract_multiplier_getter=contract_multiplier_getter,
        )
        
        # 获取最早交易时间（用于从交易数据重新计算昨日收盘持仓）
        from sqlalchemy import select, func
        from tri_arb.storage.xt_websocket_models import XTTradeUpdate
        
        if args.exchange == "xt":
            TradeModel = XTTradeUpdate
            time_column = XTTradeUpdate.update_time
        else:
            from tri_arb.storage.models import TradeUpdate
            TradeModel = TradeUpdate
            time_column = TradeUpdate.transaction_time
        
        earliest_query = select(func.min(time_column)).where(
            TradeModel.account_id == args.account_id
        )
        if args.symbol:
            earliest_query = earliest_query.where(TradeModel.symbol == args.symbol)
        if args.exchange == "binance":
            earliest_query = earliest_query.where(TradeModel.exchange == "binance_perp")
        
        result = await session.execute(earliest_query)
        earliest_time = result.scalar_one_or_none()
        
        if earliest_time is None:
            console.print(f"[yellow]未找到交易数据[/yellow]")
            await db_manager.close()
            return
        
        # 确保 earliest_time 是 naive datetime
        if earliest_time.tzinfo is not None:
            earliest_time = earliest_time.replace(tzinfo=None)
        
        console.print(f"[dim]从交易数据重新计算（最早交易时间: {earliest_time}）[/dim]\n")
        
        # 步骤1：计算从最早时间到前日结束的所有交易，得到前日收盘持仓
        console.print(f"[dim]步骤1: 计算前日收盘持仓（从最早交易时间 {earliest_time} 到前日结束 {day_before_yesterday_end}）[/dim]")
        day_before_yesterday_full_metrics = await calc.calculate_positions_by_symbol(
            start_time=earliest_time,
            end_time=day_before_yesterday_end,
            symbol=args.symbol,
            initial_positions_dict=None,  # 从最早开始计算，完全基于交易数据
        )
        
        # 从前日完整数据中提取收盘持仓（left_* 字段），作为昨日的初始持仓
        day_before_yesterday_closing = {}
        for symbol_key, full_data in day_before_yesterday_full_metrics.items():
            if symbol_key == "TOTAL":
                continue
            day_before_yesterday_closing[symbol_key] = {
                "left_long_qty": full_data.get("left_long_qty", Decimal("0")),
                "left_short_qty": full_data.get("left_short_qty", Decimal("0")),
                "left_long_value": full_data.get("left_long_value", Decimal("0")),
                "left_short_value": full_data.get("left_short_value", Decimal("0")),
            }
        
        # 步骤2：计算从最早时间到昨日结束的所有交易，得到昨日收盘持仓
        console.print(f"[dim]步骤2: 计算昨日收盘持仓（从最早交易时间 {earliest_time} 到昨日结束 {yesterday_end}）[/dim]")
        yesterday_full_metrics = await calc.calculate_positions_by_symbol(
            start_time=earliest_time,
            end_time=yesterday_end,
            symbol=args.symbol,
            initial_positions_dict=None,  # 从最早开始计算，完全基于交易数据
        )
        
        # 从昨日完整数据中提取收盘持仓（left_* 字段），作为今日的初始持仓
        initial_positions_dict = {}
        yesterday_closing = {}
        for symbol_key, full_data in yesterday_full_metrics.items():
            if symbol_key == "TOTAL":
                continue
            # 昨日收盘持仓 = 昨日结束时的剩余持仓
            yesterday_closing[symbol_key] = {
                "left_long_qty": full_data.get("left_long_qty", Decimal("0")),
                "left_short_qty": full_data.get("left_short_qty", Decimal("0")),
                "left_long_value": full_data.get("left_long_value", Decimal("0")),
                "left_short_value": full_data.get("left_short_value", Decimal("0")),
            }
            # 作为今日初始持仓
            initial_positions_dict[symbol_key] = {
                "initial_long_qty": yesterday_closing[symbol_key]["left_long_qty"],
                "initial_short_qty": yesterday_closing[symbol_key]["left_short_qty"],
                "initial_long_value": yesterday_closing[symbol_key]["left_long_value"],
                "initial_short_value": yesterday_closing[symbol_key]["left_short_value"],
            }
        
        # 步骤3：计算前日完整数据（用于显示"前日收盘持仓"）
        console.print(f"[dim]步骤3: 计算前日完整数据（{day_before_yesterday_start} -> {day_before_yesterday_end}）[/dim]")
        day_before_yesterday_metrics_by_symbol = await calc.calculate_positions_by_symbol(
            start_time=day_before_yesterday_start,
            end_time=day_before_yesterday_end,
            symbol=args.symbol,
            initial_positions_dict={
                symbol_key: {
                    "initial_long_qty": data["left_long_qty"],
                    "initial_short_qty": data["left_short_qty"],
                    "initial_long_value": data["left_long_value"],
                    "initial_short_value": data["left_short_value"],
                }
                for symbol_key, data in day_before_yesterday_closing.items()
            } if day_before_yesterday_closing else None,
        )
        
        # 步骤4：计算昨日完整数据（用于显示"昨收持仓"的 pre_long_qty 等）
        console.print(f"[dim]步骤4: 计算昨日完整数据（{yesterday_start} -> {yesterday_end}）[/dim]")
        yesterday_metrics_by_symbol = await calc.calculate_positions_by_symbol(
            start_time=yesterday_start,
            end_time=yesterday_end,
            symbol=args.symbol,
            initial_positions_dict=initial_positions_dict if initial_positions_dict else None,
        )
        
        # 步骤5：计算今日指标（使用昨日收盘持仓作为初始持仓，加上今日交易数据）
        console.print(f"[dim]步骤5: 计算今日持仓（{start_time} -> {end_time}）[/dim]")
        metrics_by_symbol = await calc.calculate_positions_by_symbol(
            start_time=start_time,
            end_time=end_time,
            symbol=args.symbol,
            initial_positions_dict=initial_positions_dict if initial_positions_dict else None,
        )
        
        # 步骤6：计算昨日收盘时的 matched_qty（用于计算今日新增的已实现盈亏）
        # 昨日收盘时的 matched_qty = min(昨日收盘时的 long_qty, 昨日收盘时的 short_qty)
        yesterday_matched_qty = {}
        for symbol_key, yesterday_data in yesterday_metrics_by_symbol.items():
            if symbol_key == "TOTAL":
                continue
            yesterday_long_qty = yesterday_data.get("long_qty", Decimal("0"))
            yesterday_short_qty = yesterday_data.get("short_qty", Decimal("0"))
            yesterday_matched_qty[symbol_key] = min(yesterday_long_qty, yesterday_short_qty)
        
        # 步骤6：计算多日 PnL（从交易数据计算）
        console.print(f"[dim]步骤6: 计算多日 PnL（{cumulative_start} -> {end_time}）[/dim]\n")
        cumulative_metrics = await calc.calculate_cumulative_pnl(
            start_date=cumulative_start,
            end_date=end_time,
            symbol=args.symbol,
        )

    # 逐币种输出（不包含 TOTAL）
    for symbol_key, m in metrics_by_symbol.items():
        if symbol_key == "TOTAL":
            continue
        
        # 获取前日、昨日数据
        day_before_yesterday_m = day_before_yesterday_metrics_by_symbol.get(symbol_key, {})
        yesterday_m = yesterday_metrics_by_symbol.get(symbol_key, {})
        day_before_yesterday_closing_data = day_before_yesterday_closing.get(symbol_key, {})
        yesterday_closing_data = yesterday_closing.get(symbol_key, {})
        
        # ========== 前日收盘数据 ==========
        title1 = f"前日收盘数据（{symbol_key}，{day_before_yesterday_end.strftime('%Y-%m-%d %H:%M:%S')} UTC）"
        table1 = Table(title=title1, show_header=True, header_style="bold magenta")
        table1.add_column("指标", justify="left")
        table1.add_column("数值", justify="right")
        
        # 前日交易数据
        table1.add_row("[bold cyan]--- 前日交易数据 ---[/bold cyan]", "")
        table1.add_row("前日多头交易量 (long_qty)", _format_dec(day_before_yesterday_m.get("long_qty", Decimal("0"))))
        table1.add_row("前日空头交易量 (short_qty)", _format_dec(day_before_yesterday_m.get("short_qty", Decimal("0"))))
        table1.add_row("前日多头市值 (long_value)", _format_dec(day_before_yesterday_m.get("long_value", Decimal("0")), 4))
        table1.add_row("前日空头市值 (short_value)", _format_dec(day_before_yesterday_m.get("short_value", Decimal("0")), 4))
        table1.add_row("前日买入平均价格 (avg_buy_prz)", _format_dec(day_before_yesterday_m.get("avg_buy_prz", Decimal("0")), 8))
        table1.add_row("前日卖出平均价格 (avg_sell_prz)", _format_dec(day_before_yesterday_m.get("avg_sell_prz", Decimal("0")), 8))
        table1.add_row("前日轧差数量 (matched_qty)", _format_dec(day_before_yesterday_m.get("matched_qty", Decimal("0"))))
        table1.add_row("前日已实现盈亏 (realized_pnl)", _format_dec(day_before_yesterday_m.get("realized_pnl", Decimal("0")), 4))
        table1.add_row("", "")  # 空行分隔
        
        # 前日收盘持仓
        table1.add_row("[bold cyan]--- 前日收盘持仓 ---[/bold cyan]", "")
        table1.add_row("前日收盘多头持仓 (left_long_qty)", _format_dec(day_before_yesterday_closing_data.get("left_long_qty", Decimal("0"))))
        table1.add_row("前日收盘空头持仓 (left_short_qty)", _format_dec(day_before_yesterday_closing_data.get("left_short_qty", Decimal("0"))))
        table1.add_row("前日收盘多头市值 (left_long_value)", _format_dec(day_before_yesterday_closing_data.get("left_long_value", Decimal("0")), 4))
        table1.add_row("前日收盘空头市值 (left_short_value)", _format_dec(day_before_yesterday_closing_data.get("left_short_value", Decimal("0")), 4))
        table1.add_row("前日最后一笔成交价 (close_prz)", _format_dec(day_before_yesterday_m.get("close_prz", Decimal("0")), 8))
        table1.add_row("前日未实现盈亏 (unrealized_pnl)", _format_dec(day_before_yesterday_m.get("unrealized_pnl", Decimal("0")), 4))
        table1.add_row("前日单日 PnL (daily_pnl)", _format_dec(day_before_yesterday_m.get("daily_pnl", Decimal("0")), 4))
        
        console.print()
        console.print(table1)
        
        # ========== 昨日收盘数据 ==========
        title2 = f"昨日收盘数据（{symbol_key}，{yesterday_end.strftime('%Y-%m-%d %H:%M:%S')} UTC）"
        table2 = Table(title=title2, show_header=True, header_style="bold magenta")
        table2.add_column("指标", justify="left")
        table2.add_column("数值", justify="right")
        
        # 昨日交易数据
        table2.add_row("[bold cyan]--- 昨日交易数据 ---[/bold cyan]", "")
        table2.add_row("昨日初始多头持仓 (pre_long_qty)", _format_dec(yesterday_m.get("pre_long_qty", Decimal("0"))))
        table2.add_row("昨日初始空头持仓 (pre_short_qty)", _format_dec(yesterday_m.get("pre_short_qty", Decimal("0"))))
        table2.add_row("昨日初始多头市值 (pre_long_value)", _format_dec(yesterday_m.get("pre_long_value", Decimal("0")), 4))
        table2.add_row("昨日初始空头市值 (pre_short_value)", _format_dec(yesterday_m.get("pre_short_value", Decimal("0")), 4))
        table2.add_row("昨日多头交易量 (long_qty)", _format_dec(yesterday_m.get("long_qty", Decimal("0"))))
        table2.add_row("昨日空头交易量 (short_qty)", _format_dec(yesterday_m.get("short_qty", Decimal("0"))))
        table2.add_row("昨日多头市值 (long_value)", _format_dec(yesterday_m.get("long_value", Decimal("0")), 4))
        table2.add_row("昨日空头市值 (short_value)", _format_dec(yesterday_m.get("short_value", Decimal("0")), 4))
        table2.add_row("昨日买入平均价格 (avg_buy_prz)", _format_dec(yesterday_m.get("avg_buy_prz", Decimal("0")), 8))
        table2.add_row("昨日卖出平均价格 (avg_sell_prz)", _format_dec(yesterday_m.get("avg_sell_prz", Decimal("0")), 8))
        table2.add_row("昨日轧差数量 (matched_qty)", _format_dec(yesterday_m.get("matched_qty", Decimal("0"))))
        table2.add_row("昨日已实现盈亏 (realized_pnl)", _format_dec(yesterday_m.get("realized_pnl", Decimal("0")), 4))
        table2.add_row("", "")  # 空行分隔
        
        # 昨日收盘持仓
        table2.add_row("[bold cyan]--- 昨日收盘持仓 ---[/bold cyan]", "")
        table2.add_row("昨日收盘多头持仓 (left_long_qty)", _format_dec(yesterday_closing_data.get("left_long_qty", Decimal("0"))))
        table2.add_row("昨日收盘空头持仓 (left_short_qty)", _format_dec(yesterday_closing_data.get("left_short_qty", Decimal("0"))))
        table2.add_row("昨日收盘多头市值 (left_long_value)", _format_dec(yesterday_closing_data.get("left_long_value", Decimal("0")), 4))
        table2.add_row("昨日收盘空头市值 (left_short_value)", _format_dec(yesterday_closing_data.get("left_short_value", Decimal("0")), 4))
        table2.add_row("昨日最后一笔成交价 (close_prz)", _format_dec(yesterday_m.get("close_prz", Decimal("0")), 8))
        table2.add_row("昨日未实现盈亏 (unrealized_pnl)", _format_dec(yesterday_m.get("unrealized_pnl", Decimal("0")), 4))
        table2.add_row("昨日单日 PnL (daily_pnl)", _format_dec(yesterday_m.get("daily_pnl", Decimal("0")), 4))
        
        console.print()
        console.print(table2)
        
        # ========== 今日数据 ==========
        title = f"今日持仓与交易统计（{symbol_key}，基于成交记录）"
        table = Table(title=title, show_header=True, header_style="bold magenta")
        table.add_column("指标", justify="left")
        table.add_column("数值", justify="right")

        # 2. 今日交易
        table.add_row("[bold cyan]--- 2. 今日交易 ---[/bold cyan]", "")
        table.add_row("多头交易量 (long_qty)", _format_dec(m.get("long_qty", Decimal("0"))))
        table.add_row("空头交易量 (short_qty)", _format_dec(m.get("short_qty", Decimal("0"))))
        table.add_row("多头市值 (long_value)", _format_dec(m.get("long_value", Decimal("0")), 4))
        table.add_row("空头市值 (short_value)", _format_dec(m.get("short_value", Decimal("0")), 4))
        table.add_row("买入平均价格 (avg_buy_prz)", _format_dec(m.get("avg_buy_prz", Decimal("0")), 8))
        table.add_row("卖出平均价格 (avg_sell_prz)", _format_dec(m.get("avg_sell_prz", Decimal("0")), 8))
        table.add_row("", "")  # 空行分隔

        # 3. 已实现 Pnl 计算
        table.add_row("[bold cyan]--- 3. 已实现 Pnl 计算 ---[/bold cyan]", "")
        total_matched_qty = m.get("matched_qty", Decimal("0"))
        yesterday_matched = yesterday_matched_qty.get(symbol_key, Decimal("0"))
        # 今日新增的轧差数量 = 今日总轧差 - 昨日收盘时的轧差
        daily_new_matched_qty = total_matched_qty - yesterday_matched
        
        table.add_row("昨日收盘轧差数量", _format_dec(yesterday_matched, 4))
        table.add_row("今日总轧差数量 (matched_qty)", _format_dec(total_matched_qty, 4))
        table.add_row("今日新增轧差数量", _format_dec(daily_new_matched_qty, 4))
        
        # 计算今日新增的已实现盈亏
        avg_buy_prz = m.get("avg_buy_prz", Decimal("0"))
        avg_sell_prz = m.get("avg_sell_prz", Decimal("0"))
        daily_realized_pnl = Decimal("0")
        if daily_new_matched_qty > 0 and avg_sell_prz > 0 and avg_buy_prz > 0:
            daily_realized_pnl = daily_new_matched_qty * (avg_sell_prz - avg_buy_prz)
        
        table.add_row("当日已实现盈亏 (今日新增轧差 * (卖出均价 - 买入均价))", _format_dec(daily_realized_pnl, 4))
        table.add_row("[dim]（原计算值，可能包含昨日持仓）[/dim]", _format_dec(m.get("realized_pnl", Decimal("0")), 4))
        table.add_row("", "")  # 空行分隔

        # 4. 当日剩余仓位
        table.add_row("[bold cyan]--- 4. 当日剩余仓位 ---[/bold cyan]", "")
        table.add_row("多头剩余持仓 (left_long_qty)", _format_dec(m.get("left_long_qty", Decimal("0"))))
        table.add_row("空头剩余持仓 (left_short_qty)", _format_dec(m.get("left_short_qty", Decimal("0"))))
        table.add_row("多头剩余市值 (left_long_value)", _format_dec(m.get("left_long_value", Decimal("0")), 4))
        table.add_row("空头剩余市值 (left_short_value)", _format_dec(m.get("left_short_value", Decimal("0")), 4))
        table.add_row("当日最后一笔成交价 (close_prz)", _format_dec(m.get("close_prz", Decimal("0")), 8))
        table.add_row("当日未实现盈亏 (unrealized_pnl)", _format_dec(m.get("unrealized_pnl", Decimal("0")), 4))
        table.add_row("", "")  # 空行分隔

        # 5. Pnl 汇总
        table.add_row("[bold cyan]--- 5. Pnl 汇总 ---[/bold cyan]", "")
        # 单日 PnL = 今日新增的已实现盈亏 + 今日未实现盈亏
        today_unrealized_pnl = m.get("unrealized_pnl", Decimal("0"))
        daily_pnl = daily_realized_pnl + today_unrealized_pnl
        table.add_row("单日 pnl (今日新增已实现 + 今日未实现)", _format_dec(daily_pnl, 4))
        table.add_row("[dim]（原计算值，可能包含昨日持仓）[/dim]", _format_dec(m.get("daily_pnl", Decimal("0")), 4))
        
        # 多日 pnl = sum(realized_pnl) + 最后一期 unrealized_pnl
        cumulative_pnl = Decimal("0")
        cumulative_realized_pnl = Decimal("0")
        current_unrealized_pnl = Decimal("0")
        if symbol_key in cumulative_metrics:
            cum_data = cumulative_metrics[symbol_key]
            cumulative_pnl = cum_data.get("cumulative_pnl", Decimal("0"))
            cumulative_realized_pnl = cum_data.get("cumulative_realized_pnl", Decimal("0"))
            current_unrealized_pnl = cum_data.get("current_unrealized_pnl", Decimal("0"))
        
        table.add_row("", "")  # 空行
        table.add_row(f"[bold yellow]多日 PnL 详情（从 {cumulative_start_date} 开始）[/bold yellow]", "")
        table.add_row("累计已实现盈亏 (cumulative_realized_pnl)", _format_dec(cumulative_realized_pnl, 4))
        table.add_row("当前未实现盈亏 (current_unrealized_pnl)", _format_dec(current_unrealized_pnl, 4))
        table.add_row("多日 pnl (累计已实现 + 当前未实现)", _format_dec(cumulative_pnl, 4))
        
        # 验证：今日的已实现盈亏应该包含在多日累计中
        today_realized = m.get("realized_pnl", Decimal("0"))
        table.add_row("", "")  # 空行
        table.add_row("[dim]验证：今日已实现盈亏[/dim]", _format_dec(today_realized, 4))
        table.add_row("[dim]（应包含在多日累计已实现中）[/dim]", "")

        console.print()
        console.print(table)

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
