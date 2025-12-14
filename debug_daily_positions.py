#!/usr/bin/env python3
"""每日持仓调试脚本.

每5分钟运行一次，计算并输出每日开盘持仓、交易统计、累积已实现盈亏等数据。
只查询 tradoor_usdt，输出到控制台，不写入数据库。
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from tri_arb.config.logging import get_logger
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.storage.database import DatabaseManager

logger = get_logger(__name__)
console = Console()


async def calculate_daily_positions(
    db_manager: DatabaseManager,
    account_id: str = "account_008",
    exchange: str = "xt",
    symbol: str = "tradoor_usdt",
):
    """计算每日持仓数据."""
    async with db_manager.session() as session:
        # 初始化合约乘数服务
        contract_multiplier_service = ContractMultiplierService()
        
        def sync_getter(symbol: str) -> Decimal:
            """同步获取合约乘数."""
            return contract_multiplier_service.get_multiplier_sync(exchange, symbol)
        
        contract_multiplier_getter = sync_getter
        
        # 创建计算器
        calc = PositionCalculator(
            session,
            exchange=exchange,
            account_id=account_id,
            contract_multiplier_getter=contract_multiplier_getter,
        )
        
        # 获取最早交易时间
        from sqlalchemy import select, func
        from tri_arb.storage.xt_websocket_models import XTTradeUpdate
        
        earliest_query = (
            select(func.min(XTTradeUpdate.update_time))
            .where(XTTradeUpdate.account_id == account_id)
            .where(XTTradeUpdate.symbol == symbol)
        )
        result = await session.execute(earliest_query)
        earliest_time = result.scalar_one_or_none()
        
        if earliest_time is None:
            console.print(f"[yellow]未找到 {symbol} 的交易数据[/yellow]")
            return
        
        # 计算日期范围（从最早交易日期前一天到今天）
        earliest_date = earliest_time.date()
        start_date = earliest_date - timedelta(days=1)  # 前一天
        end_date = datetime.now(timezone.utc).date()  # 今天
        
        console.print(f"\n[bold cyan]计算日期范围: {start_date} 到 {end_date}[/bold cyan]")
        console.print(f"[cyan]最早交易时间: {earliest_time}[/cyan]\n")
        
        # 存储每日数据
        daily_data = []
        
        # 遍历每一天
        current_date = start_date
        prev_left_long_qty = Decimal("0")
        prev_left_short_qty = Decimal("0")
        prev_left_long_value = Decimal("0")
        prev_left_short_value = Decimal("0")
        cumulative_realized_pnl = Decimal("0")
        
        while current_date <= end_date:
            day_start = datetime.combine(current_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            
            # 计算当天的交易数据（使用前一天收盘持仓作为初始持仓）
            initial_positions = {
                symbol: {
                    "initial_long_qty": prev_left_long_qty,
                    "initial_short_qty": prev_left_short_qty,
                    "initial_long_value": prev_left_long_value,
                    "initial_short_value": prev_left_short_value,
                }
            } if prev_left_long_qty > 0 or prev_left_short_qty > 0 else None
            
            daily_metrics = await calc.calculate_positions_by_symbol(
                start_time=day_start,
                end_time=day_end,
                initial_positions_dict=initial_positions,
            )
            
            if symbol not in daily_metrics:
                # 如果当天没有交易，开盘持仓等于前一天收盘持仓
                day_data = {
                    "date": current_date,
                    "open_left_long_qty": prev_left_long_qty,
                    "open_left_short_qty": prev_left_short_qty,
                    "open_left_long_value": prev_left_long_value,
                    "open_left_short_value": prev_left_short_value,
                    "daily_buy_volume": Decimal("0"),
                    "daily_sell_volume": Decimal("0"),
                    "daily_buy_value": Decimal("0"),
                    "daily_sell_value": Decimal("0"),
                    "matched_qty": Decimal("0"),
                    "daily_realized_pnl": Decimal("0"),
                    "cumulative_realized_pnl": cumulative_realized_pnl,
                    "close_left_long_qty": prev_left_long_qty,
                    "close_left_short_qty": prev_left_short_qty,
                }
            else:
                daily_m = daily_metrics[symbol]
                daily_buy_volume = daily_m.get("buy_volume", Decimal("0"))
                daily_sell_volume = daily_m.get("sell_volume", Decimal("0"))
                daily_buy_value = daily_m.get("buy_trade_value", Decimal("0"))
                daily_sell_value = daily_m.get("sell_trade_value", Decimal("0"))
                matched_qty = daily_m.get("matched_qty", Decimal("0"))
                realized_pnl = daily_m.get("realized_pnl", Decimal("0"))
                left_long_qty = daily_m.get("left_long_qty", Decimal("0"))
                left_short_qty = daily_m.get("left_short_qty", Decimal("0"))
                left_long_value = daily_m.get("left_long_value", Decimal("0"))
                left_short_value = daily_m.get("left_short_value", Decimal("0"))
                
                # 累计已实现盈亏
                cumulative_realized_pnl += realized_pnl
                
                day_data = {
                    "date": current_date,
                    "open_left_long_qty": prev_left_long_qty,
                    "open_left_short_qty": prev_left_short_qty,
                    "open_left_long_value": prev_left_long_value,
                    "open_left_short_value": prev_left_short_value,
                    "daily_buy_volume": daily_buy_volume,
                    "daily_sell_volume": daily_sell_volume,
                    "daily_buy_value": daily_buy_value,
                    "daily_sell_value": daily_sell_value,
                    "matched_qty": matched_qty,
                    "daily_realized_pnl": realized_pnl,
                    "cumulative_realized_pnl": cumulative_realized_pnl,
                    "close_left_long_qty": left_long_qty,
                    "close_left_short_qty": left_short_qty,
                }
                
                # 更新前一天收盘持仓
                prev_left_long_qty = left_long_qty
                prev_left_short_qty = left_short_qty
                prev_left_long_value = left_long_value
                prev_left_short_value = left_short_value
            
            daily_data.append(day_data)
            current_date += timedelta(days=1)
        
        # 输出结果表格
        table = Table(
            title=f"[bold green]每日持仓数据 - {account_id} / {exchange} / {symbol}[/bold green]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
        )
        
        table.add_column("日期", style="cyan", width=12)
        table.add_column("开盘多头", justify="right", style="yellow", width=12)
        table.add_column("开盘空头", justify="right", style="yellow", width=12)
        table.add_column("当日买入", justify="right", style="blue", width=12)
        table.add_column("当日卖出", justify="right", style="blue", width=12)
        table.add_column("轧差数量", justify="right", style="green", width=12)
        table.add_column("当日已实现", justify="right", style="green", width=12)
        table.add_column("累积已实现", justify="right", style="bold green", width=14)
        table.add_column("收盘多头", justify="right", style="red", width=12)
        table.add_column("收盘空头", justify="right", style="red", width=12)
        
        for data in daily_data:
            table.add_row(
                str(data["date"]),
                f"{data['open_left_long_qty']:,.0f}",
                f"{data['open_left_short_qty']:,.0f}",
                f"{data['daily_buy_volume']:,.0f}",
                f"{data['daily_sell_volume']:,.0f}",
                f"{data['matched_qty']:,.0f}",
                f"{data['daily_realized_pnl']:,.2f}",
                f"{data['cumulative_realized_pnl']:,.2f}",
                f"{data.get('close_left_long_qty', Decimal('0')):,.0f}",
                f"{data.get('close_left_short_qty', Decimal('0')):,.0f}",
            )
        
        console.print(table)
        
        # 输出最新数据摘要
        if daily_data:
            latest = daily_data[-1]
            summary = Panel(
                f"""[bold]最新数据摘要 ({latest['date']})[/bold]

[cyan]开盘持仓:[/cyan] 多头 {latest['open_left_long_qty']:,.0f} | 空头 {latest['open_left_short_qty']:,.0f}
[blue]当日交易:[/blue] 买入 {latest['daily_buy_volume']:,.0f} | 卖出 {latest['daily_sell_volume']:,.0f}
[green]已实现盈亏:[/green] 当日 {latest['daily_realized_pnl']:,.2f} | 累积 {latest['cumulative_realized_pnl']:,.2f}
[red]收盘持仓:[/red] 多头 {latest.get('close_left_long_qty', Decimal('0')):,.0f} | 空头 {latest.get('close_left_short_qty', Decimal('0')):,.0f}""",
                title="[bold yellow]数据摘要[/bold yellow]",
                border_style="yellow",
            )
            console.print(summary)


async def main(config_path: Path = None):
    """主函数.
    
    Args:
        config_path: 配置文件路径，如果为None则使用默认路径
    """
    # 从配置文件读取数据库连接信息
    if config_path is None:
        config_path = project_root / "config" / "accounts.json"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        console.print(f"[red]配置文件不存在: {config_path}[/red]")
        return
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    database_url = config.get("global_settings", {}).get("database_url")
    if not database_url:
        console.print("[red]未找到 database_url 配置[/red]")
        return
    
    # 初始化数据库管理器
    db_manager = DatabaseManager(database_url)
    
    console.print("[bold green]开始计算每日持仓数据...[/bold green]")
    console.print(f"[cyan]时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}[/cyan]\n")
    
    try:
        await calculate_daily_positions(
            db_manager=db_manager,
            account_id="account_008",
            exchange="xt",
            symbol="tradoor_usdt",
        )
    except Exception as e:
        console.print(f"[red]计算失败: {e}[/red]")
        logger.exception("计算失败")
    finally:
        await db_manager.close()


async def run_periodically(config_path: Path = None):
    """每5分钟运行一次.
    
    Args:
        config_path: 配置文件路径
    """
    while True:
        try:
            await main(config_path)
        except Exception as e:
            console.print(f"[red]运行出错: {e}[/red]")
            logger.exception("运行出错")
        
        # 等待5分钟
        console.print(f"\n[dim]等待5分钟后再次运行... (下次运行时间: {(datetime.now(timezone.utc) + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S UTC')})[/dim]\n")
        await asyncio.sleep(300)  # 5分钟 = 300秒


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="每日持仓调试脚本 - 每5分钟运行一次，计算并输出每日持仓数据"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="配置文件路径（默认: config/accounts.json）",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只运行一次，不循环运行",
    )
    
    args = parser.parse_args()
    
    # 解析配置文件路径
    config_path = None
    if args.config:
        config_path = Path(args.config).expanduser().resolve()
        if not config_path.exists():
            console.print(f"[red]指定的配置文件不存在: {config_path}[/red]")
            sys.exit(1)
    else:
        # 使用默认路径
        config_path = project_root / "config" / "accounts.json"
    
    if args.once:
        # 只运行一次
        asyncio.run(main(config_path))
    else:
        # 每5分钟运行一次
        console.print("[bold yellow]按 Ctrl+C 停止运行[/bold yellow]")
        console.print(f"[dim]使用配置文件: {config_path}[/dim]")
        console.print("[dim]提示: 使用 --once 参数可以只运行一次[/dim]")
        console.print("[dim]提示: 使用 --config 参数可以指定配置文件路径[/dim]\n")
        try:
            asyncio.run(run_periodically(config_path))
        except KeyboardInterrupt:
            console.print("\n[yellow]已停止运行[/yellow]")
