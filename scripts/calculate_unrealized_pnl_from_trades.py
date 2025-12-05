#!/usr/bin/env python3
"""从成交记录计算累积未实现盈亏.

从数据库的成交记录中直接计算累积未实现盈亏，不依赖 position_metrics 表。
"""

import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional, List, Tuple

import asyncpg
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer()
console = Console()


async def get_trades(
    conn: asyncpg.Connection,
    account_id: str,
    exchange: str,
    symbol: str,
    start_time: Optional[datetime] = None,
) -> List[Dict]:
    """从数据库获取成交记录.
    
    Args:
        conn: 数据库连接
        account_id: 账号ID
        exchange: 交易所
        symbol: 交易对
        start_time: 开始时间（可选），如果不提供则获取所有记录
    
    Returns:
        成交记录列表，按时间排序
    """
    if exchange == "xt":
        table = "xt_trade_update"
    elif exchange == "binance":
        table = "binance_trade_update"
    else:
        raise ValueError(f"Unsupported exchange: {exchange}")
    
    query = f"""
        SELECT 
            update_time,
            side,
            price,
            quantity,
            quote_quantity
        FROM {table}
        WHERE account_id = $1
          AND symbol = $2
    """
    params = [account_id, symbol]
    
    if start_time:
        query += " AND update_time >= $3"
        params.append(start_time)
    
    query += " ORDER BY update_time ASC"
    
    rows = await conn.fetch(query, *params)
    
    return [
        {
            "update_time": row["update_time"],
            "side": row["side"],
            "price": Decimal(str(row["price"])),
            "quantity": Decimal(str(row["quantity"])),
            "quote_quantity": Decimal(str(row["quote_quantity"])),
        }
        for row in rows
    ]


async def get_current_price(
    conn: asyncpg.Connection,
    account_id: str,
    exchange: str,
    symbol: str,
) -> Decimal:
    """获取当前价格（从 position_metrics 或 xt_position_update）.
    
    Args:
        conn: 数据库连接
        account_id: 账号ID
        exchange: 交易所
        symbol: 交易对
    
    Returns:
        当前价格
    """
    # 先尝试从 position_metrics 获取最新价格
    query = """
        SELECT close_prz
        FROM position_metrics
        WHERE account_id = $1
          AND exchange = $2
          AND symbol = $3
        ORDER BY timestamp DESC
        LIMIT 1
    """
    row = await conn.fetchrow(query, account_id, exchange, symbol)
    if row and row["close_prz"]:
        return Decimal(str(row["close_prz"]))
    
    # 如果 position_metrics 没有，尝试从 xt_position_update 获取最新标记价格
    if exchange == "xt":
        query = """
            SELECT mark_price
            FROM xt_position_update
            WHERE account_id = $1
              AND symbol = $2
            ORDER BY update_time DESC
            LIMIT 1
        """
        row = await conn.fetchrow(query, account_id, symbol)
        if row and row["mark_price"]:
            return Decimal(str(row["mark_price"]))
    
    # 如果都没有，使用最新成交价格
    query = f"""
        SELECT price
        FROM xt_trade_update
        WHERE account_id = $1
          AND symbol = $2
        ORDER BY update_time DESC
        LIMIT 1
    """
    row = await conn.fetchrow(query, account_id, symbol)
    if row:
        return Decimal(str(row["price"]))
    
    raise ValueError(f"无法获取 {symbol} 的当前价格")


async def get_contract_multiplier(
    conn: asyncpg.Connection,
    exchange: str,
    symbol: str,
) -> Decimal:
    """获取合约乘数.
    
    Args:
        conn: 数据库连接
        exchange: 交易所
        symbol: 交易对
    
    Returns:
        合约乘数
    """
    # 使用 ContractMultiplierService 获取合约乘数
    try:
        from tri_arb.services.contract_multiplier_service import ContractMultiplierService
        
        service = ContractMultiplierService()
        # 同步方法获取
        multiplier = service.get_multiplier_sync(exchange, symbol)
        if multiplier:
            return Decimal(str(multiplier))
    except Exception as e:
        console.print(f"[yellow]⚠️  无法从 ContractMultiplierService 获取合约乘数: {e}[/yellow]")
        console.print("[yellow]使用默认值 1[/yellow]")
    
    # 默认返回 1
    return Decimal("1")


def calculate_unrealized_pnl_from_trades(
    trades: List[Dict],
    current_price: Decimal,
    contract_multiplier: Decimal = Decimal("1"),
) -> Tuple[Decimal, Dict]:
    """从成交记录计算累积未实现盈亏.
    
    计算逻辑：
    1. 使用 FIFO 方式处理持仓
    2. 维护两个队列：多头持仓队列和空头持仓队列
    3. BUY：如果有空头，先平空（FIFO），剩余开多
    4. SELL：如果有多头，先平多（FIFO），剩余开空
    5. 最后计算未实现盈亏时，用当前价格减去每个持仓的开仓价格
    
    Args:
        trades: 成交记录列表
        current_price: 当前价格
        contract_multiplier: 合约乘数
    
    Returns:
        (累积未实现盈亏, 详细信息字典)
    """
    # 使用列表存储持仓（FIFO 队列）
    # 每个元素是 (数量, 开仓价格)
    long_positions: List[Tuple[Decimal, Decimal]] = []  # [(数量, 价格), ...]
    short_positions: List[Tuple[Decimal, Decimal]] = []  # [(数量, 价格), ...]
    
    # 遍历所有成交记录
    for trade in trades:
        side = trade["side"].upper()
        price = trade["price"]
        quantity_contracts = trade["quantity"]
        quantity_coins = quantity_contracts * contract_multiplier
        
        if side == "BUY":
            # BUY 可能开多或平空
            remaining = quantity_coins
            
            # 先平空（FIFO）
            while remaining > 0 and short_positions:
                short_qty, short_price = short_positions[0]
                if short_qty <= remaining:
                    # 完全平掉这个空头持仓
                    remaining -= short_qty
                    short_positions.pop(0)
                else:
                    # 部分平掉
                    short_positions[0] = (short_qty - remaining, short_price)
                    remaining = Decimal("0")
            
            # 剩余部分开多
            if remaining > 0:
                long_positions.append((remaining, price))
                
        elif side == "SELL":
            # SELL 可能开空或平多
            remaining = quantity_coins
            
            # 先平多（FIFO）
            while remaining > 0 and long_positions:
                long_qty, long_price = long_positions[0]
                if long_qty <= remaining:
                    # 完全平掉这个多头持仓
                    remaining -= long_qty
                    long_positions.pop(0)
                else:
                    # 部分平掉
                    long_positions[0] = (long_qty - remaining, long_price)
                    remaining = Decimal("0")
            
            # 剩余部分开空
            if remaining > 0:
                short_positions.append((remaining, price))
    
    # 计算当前持仓和加权平均价格
    long_qty = sum(qty for qty, _ in long_positions)
    short_qty = sum(qty for qty, _ in short_positions)
    
    long_value = sum(qty * price for qty, price in long_positions)
    short_value = sum(qty * price for qty, price in short_positions)
    
    avg_long_price = long_value / long_qty if long_qty > 0 else Decimal("0")
    avg_short_price = short_value / short_qty if short_qty > 0 else Decimal("0")
    
    # 计算未实现盈亏（使用当前价格）
    long_unrealized = sum(qty * (current_price - price) for qty, price in long_positions)
    short_unrealized = sum(qty * (price - current_price) for qty, price in short_positions)
    total_unrealized = long_unrealized + short_unrealized
    
    return total_unrealized, {
        "long_qty": long_qty,
        "short_qty": short_qty,
        "avg_long_price": avg_long_price,
        "avg_short_price": avg_short_price,
        "long_unrealized": long_unrealized,
        "short_unrealized": short_unrealized,
        "current_price": current_price,
        "long_positions_count": len(long_positions),
        "short_positions_count": len(short_positions),
    }


async def get_initial_positions_from_trades(
    conn: asyncpg.Connection,
    account_id: str,
    exchange: str,
    symbol: str,
    before_time: datetime,
) -> Dict:
    """获取指定时间点之前的持仓状态（通过处理所有历史成交记录）.
    
    Args:
        conn: 数据库连接
        account_id: 账号ID
        exchange: 交易所
        symbol: 交易对
        before_time: 时间点
    
    Returns:
        持仓状态字典，包含 long_positions, short_positions, long_qty, short_qty, avg_long_price, avg_short_price
    """
    # 获取该时间点之前的所有成交记录
    trades = await get_trades(conn, account_id, exchange, symbol, None)
    trades = [t for t in trades if t["update_time"] < before_time]
    
    if not trades:
        return {
            "long_positions": [],
            "short_positions": [],
            "long_qty": Decimal("0"),
            "short_qty": Decimal("0"),
            "avg_long_price": Decimal("0"),
            "avg_short_price": Decimal("0"),
        }
    
    # 获取合约乘数
    contract_multiplier = await get_contract_multiplier(conn, exchange, symbol)
    
    # 处理所有历史成交记录
    long_positions: List[Tuple[Decimal, Decimal]] = []
    short_positions: List[Tuple[Decimal, Decimal]] = []
    
    for trade in trades:
        side = trade["side"].upper()
        price = trade["price"]
        quantity_contracts = trade["quantity"]
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
    
    long_qty = sum(qty for qty, _ in long_positions)
    short_qty = sum(qty for qty, _ in short_positions)
    long_value = sum(qty * price for qty, price in long_positions)
    short_value = sum(qty * price for qty, price in short_positions)
    avg_long_price = long_value / long_qty if long_qty > 0 else Decimal("0")
    avg_short_price = short_value / short_qty if short_qty > 0 else Decimal("0")
    
    return {
        "long_positions": long_positions,
        "short_positions": short_positions,
        "long_qty": long_qty,
        "short_qty": short_qty,
        "avg_long_price": avg_long_price,
        "avg_short_price": avg_short_price,
    }


async def calculate_unrealized_pnl_by_interval(
    trades: List[Dict],
    interval_minutes: int,
    contract_multiplier: Decimal,
    initial_positions: Optional[Dict] = None,
) -> List[Dict]:
    """按时间间隔计算未实现盈亏.
    
    Args:
        trades: 成交记录列表（按时间排序）
        interval_minutes: 时间间隔（分钟）
        contract_multiplier: 合约乘数
        initial_positions: 初始持仓状态（用于增量计算）
    
    Returns:
        每个时间点的计算结果列表，每个结果包含：
        - time: 时间点
        - current_price: 该时间点之前的最新成交价格
        - long_qty: 多头持仓
        - short_qty: 空头持仓
        - avg_long_price: 多头均价
        - avg_short_price: 空头均价
        - unrealized_pnl: 未实现盈亏
    """
    # 如果没有成交记录，但有初始持仓，仍然需要计算
    if not trades:
        if initial_positions and (initial_positions["long_qty"] > 0 or initial_positions["short_qty"] > 0):
            # 有初始持仓但没有新成交，返回当前持仓状态（需要获取当前价格）
            # 这里返回一个空列表，让调用者处理
            return []
        return []
    
    # 确定时间范围（确保 trades 不为空）
    if not trades or len(trades) == 0:
        return []
    
    start_time = trades[0]["update_time"]
    end_time = trades[-1]["update_time"]
    
    # 生成时间点列表（每 interval_minutes 分钟一个点）
    time_points = []
    current_time = start_time.replace(second=0, microsecond=0)
    interval = timedelta(minutes=interval_minutes)
    
    while current_time <= end_time:
        time_points.append(current_time)
        current_time += interval
    
    # 确保包含最后一个时间点
    if time_points[-1] < end_time:
        time_points.append(end_time.replace(second=0, microsecond=0))
    
    results = []
    
    # 维护持仓状态（从初始持仓开始，如果有的话）
    if initial_positions:
        long_positions: List[Tuple[Decimal, Decimal]] = initial_positions["long_positions"].copy()
        short_positions: List[Tuple[Decimal, Decimal]] = initial_positions["short_positions"].copy()
    else:
        long_positions: List[Tuple[Decimal, Decimal]] = []
        short_positions: List[Tuple[Decimal, Decimal]] = []
    
    trade_index = 0
    
    # 对每个时间点计算
    for time_point in time_points:
        # 处理该时间点之前的所有成交记录
        while trade_index < len(trades) and trades[trade_index]["update_time"] <= time_point:
            trade = trades[trade_index]
            side = trade["side"].upper()
            price = trade["price"]
            quantity_contracts = trade["quantity"]
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
            
            trade_index += 1
        
        # 直接使用该时间点之前的最新成交价格
        if trade_index > 0 and trade_index <= len(trades):
            current_price = trades[trade_index - 1]["price"]
        elif trades and len(trades) > 0:
            # 如果还没有处理成交记录，使用第一条成交的价格
            current_price = trades[0]["price"]
        elif initial_positions and (initial_positions["long_qty"] > 0 or initial_positions["short_qty"] > 0):
            # 如果有初始持仓但没有成交记录，需要从外部获取价格
            # 这里暂时使用 0，会在外部处理
            current_price = Decimal("0")
        else:
            current_price = Decimal("0")
        
        # 计算当前持仓和未实现盈亏
        long_qty = sum(qty for qty, _ in long_positions)
        short_qty = sum(qty for qty, _ in short_positions)
        
        long_value = sum(qty * price for qty, price in long_positions)
        short_value = sum(qty * price for qty, price in short_positions)
        
        avg_long_price = long_value / long_qty if long_qty > 0 else Decimal("0")
        avg_short_price = short_value / short_qty if short_qty > 0 else Decimal("0")
        
        long_unrealized = sum(qty * (current_price - price) for qty, price in long_positions)
        short_unrealized = sum(qty * (price - current_price) for qty, price in short_positions)
        total_unrealized = long_unrealized + short_unrealized
        
        results.append({
            "time": time_point,
            "current_price": current_price,
            "long_qty": long_qty,
            "short_qty": short_qty,
            "avg_long_price": avg_long_price,
            "avg_short_price": avg_short_price,
            "unrealized_pnl": total_unrealized,
        })
    
    return results


@app.command()
def calculate(
    account_id: str = typer.Option(..., help="账号ID"),
    exchange: str = typer.Option("xt", help="交易所"),
    symbol: str = typer.Option(..., help="交易对"),
    start_time: Optional[str] = typer.Option(None, help="开始时间（YYYY-MM-DD HH:MM:SS），如果不提供则从所有历史记录计算"),
    last_calc_time: Optional[str] = typer.Option(None, help="上次计算时间（YYYY-MM-DD HH:MM:SS），用于增量计算，只处理该时间之后的成交记录"),
    interval_minutes: int = typer.Option(5, help="计算间隔（分钟），默认5分钟"),
    database_url: Optional[str] = typer.Option(None, help="数据库连接URL，如果不提供则从环境变量 DATABASE_URL 读取"),
):
    """从成交记录按时间间隔计算未实现盈亏.
    
    如果提供了 last_calc_time，则只处理该时间之后的新成交记录，大大提高计算速度。
    """
    asyncio.run(_calculate(account_id, exchange, symbol, start_time, last_calc_time, interval_minutes, database_url))


async def _calculate(
    account_id: str,
    exchange: str,
    symbol: str,
    start_time: Optional[str],
    last_calc_time: Optional[str],
    interval_minutes: int,
    database_url: Optional[str],
):
    """计算累积未实现盈亏."""
    # 获取数据库连接
    if database_url is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            console.print("[red]错误：需要提供 DATABASE_URL 环境变量或 --database-url 参数[/red]")
            raise typer.Exit(1)
    
    # asyncpg 不支持 postgresql+asyncpg:// 格式，需要转换为 postgresql://
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    elif database_url.startswith("postgres+asyncpg://"):
        database_url = database_url.replace("postgres+asyncpg://", "postgresql://")
    
    # 解析开始时间
    start_datetime = None
    if start_time:
        try:
            start_datetime = datetime.fromisoformat(start_time.replace(" ", "T"))
        except ValueError:
            console.print(f"[red]错误：无效的时间格式 {start_time}[/red]")
            raise typer.Exit(1)
    
    # 解析上次计算时间（用于增量计算）
    last_calc_datetime = None
    if last_calc_time:
        try:
            last_calc_datetime = datetime.fromisoformat(last_calc_time.replace(" ", "T"))
            console.print(f"[cyan]增量计算模式：只处理 {last_calc_datetime} 之后的新成交记录[/cyan]")
        except ValueError:
            console.print(f"[red]错误：无效的时间格式 {last_calc_time}[/red]")
            raise typer.Exit(1)
    
    # 连接数据库
    conn = await asyncpg.connect(database_url)
    
    try:
        # 获取成交记录
        if last_calc_datetime:
            # 增量计算：需要先获取上次计算时的持仓状态
            console.print(f"[cyan]正在获取上次计算时的持仓状态...[/cyan]")
            initial_positions = await get_initial_positions_from_trades(
                conn, account_id, exchange, symbol, last_calc_datetime
            )
            console.print(f"[green]✓ 上次持仓状态: 多头 {initial_positions['long_qty']:.2f} @ {initial_positions['avg_long_price']:.6f}, "
                         f"空头 {initial_positions['short_qty']:.2f} @ {initial_positions['avg_short_price']:.6f}[/green]")
            
            # 只获取新成交记录
            console.print(f"[cyan]正在获取新成交记录（{last_calc_datetime} 之后）...[/cyan]")
            trades = await get_trades(conn, account_id, exchange, symbol, last_calc_datetime)
            console.print(f"[green]✓ 找到 {len(trades)} 条新成交记录[/green]")
        else:
            # 全量计算
            console.print(f"[cyan]正在获取成交记录...[/cyan]")
            trades = await get_trades(conn, account_id, exchange, symbol, start_datetime)
            console.print(f"[green]✓ 找到 {len(trades)} 条成交记录[/green]")
            initial_positions = None
        
        if not trades and not initial_positions:
            console.print("[yellow]⚠️  没有找到成交记录[/yellow]")
            return
        
        # 获取合约乘数
        contract_multiplier = await get_contract_multiplier(conn, exchange, symbol)
        console.print(f"[cyan]合约乘数: {contract_multiplier}[/cyan]")
        
        # 按时间间隔计算未实现盈亏
        console.print(f"[cyan]正在按 {interval_minutes} 分钟间隔计算未实现盈亏...[/cyan]")
        results = await calculate_unrealized_pnl_by_interval(
            trades, interval_minutes, contract_multiplier, initial_positions
        )
        
        # 如果没有新成交记录，但有初始持仓，计算当前持仓的未实现盈亏
        if not results and initial_positions and (initial_positions["long_qty"] > 0 or initial_positions["short_qty"] > 0):
            console.print("[cyan]没有新成交记录，计算当前持仓的未实现盈亏...[/cyan]")
            # 获取当前价格
            current_price = await get_current_price(conn, account_id, exchange, symbol)
            console.print(f"[green]✓ 当前价格: {current_price}[/green]")
            
            # 计算未实现盈亏
            long_positions = initial_positions["long_positions"]
            short_positions = initial_positions["short_positions"]
            long_unrealized = sum(qty * (current_price - price) for qty, price in long_positions)
            short_unrealized = sum(qty * (price - current_price) for qty, price in short_positions)
            total_unrealized = long_unrealized + short_unrealized
            
            # 创建结果
            results = [{
                "time": datetime.now().replace(second=0, microsecond=0),
                "current_price": current_price,
                "long_qty": initial_positions["long_qty"],
                "short_qty": initial_positions["short_qty"],
                "avg_long_price": initial_positions["avg_long_price"],
                "avg_short_price": initial_positions["avg_short_price"],
                "unrealized_pnl": total_unrealized,
            }]
        
        if not results:
            console.print("[yellow]⚠️  没有计算结果[/yellow]")
            return
        
        # 显示结果表格
        table = Table(title=f"未实现盈亏时间序列 [{account_id} - {exchange} - {symbol}] (间隔: {interval_minutes}分钟)")
        table.add_column("时间", style="cyan")
        table.add_column("当前价格", style="blue", justify="right")
        table.add_column("多头持仓", style="green", justify="right")
        table.add_column("空头持仓", style="red", justify="right")
        table.add_column("多头均价", style="dim", justify="right")
        table.add_column("空头均价", style="dim", justify="right")
        table.add_column("未实现盈亏", style="yellow", justify="right")
        
        for result in results:
            table.add_row(
                result["time"].strftime("%Y-%m-%d %H:%M:%S"),
                f"{result['current_price']:.6f}",
                f"{result['long_qty']:.2f}",
                f"{result['short_qty']:.2f}",
                f"{result['avg_long_price']:.6f}" if result['avg_long_price'] > 0 else "-",
                f"{result['avg_short_price']:.6f}" if result['avg_short_price'] > 0 else "-",
                f"{result['unrealized_pnl']:.4f}",
            )
        
        console.print(table)
        
        # 显示统计信息
        if results:
            latest = results[-1]
            console.print(f"\n[bold]最新状态:[/bold]")
            console.print(f"  时间: {latest['time'].strftime('%Y-%m-%d %H:%M:%S')}")
            console.print(f"  当前价格: {latest['current_price']:.6f}")
            console.print(f"  多头持仓: {latest['long_qty']:.2f} @ {latest['avg_long_price']:.6f}")
            console.print(f"  空头持仓: {latest['short_qty']:.2f} @ {latest['avg_short_price']:.6f}")
            console.print(f"  未实现盈亏: {latest['unrealized_pnl']:.4f}")
            
            console.print(f"\n[dim]计算时间点数量: {len(results)}[/dim]")
            if trades:
                console.print(f"[dim]成交记录时间范围: {trades[0]['update_time']} 到 {trades[-1]['update_time']}[/dim]")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    app()

