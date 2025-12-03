#!/usr/bin/env python3
"""检查持仓指标数据是否已写入数据库."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.position_metrics_models import PositionMetrics

console = Console()


async def main():
    """检查数据库中的持仓指标数据."""
    db_manager = DatabaseManager()
    
    try:
        async with db_manager.session() as session:
            # 查询最新的记录
            query = (
                select(PositionMetrics)
                .order_by(desc(PositionMetrics.timestamp))
                .limit(20)
            )
            
            result = await session.execute(query)
            records = result.scalars().all()
            
            if not records:
                console.print("[yellow]⚠ 数据库中还没有持仓指标数据[/yellow]")
                console.print("\n可能的原因：")
                console.print("1. 定时任务服务还未运行")
                console.print("2. 定时任务服务刚启动，还未完成第一次计算")
                console.print("3. 计算过程中出现错误（请查看日志）")
                console.print("\n建议：")
                console.print("- 确认服务正在运行：ps aux | grep start_position_metrics_scheduler")
                console.print("- 查看服务日志：tail -f logs/tri-arb.log")
                return
            
            # 显示统计信息
            count_query = select(func.count(PositionMetrics.id))
            count_result = await session.execute(count_query)
            total_count = count_result.scalar()
            
            # 按账号和交易所分组统计
            stats_query = (
                select(
                    PositionMetrics.account_id,
                    PositionMetrics.exchange,
                    func.count(PositionMetrics.id).label("count"),
                    func.max(PositionMetrics.timestamp).label("latest_time")
                )
                .group_by(PositionMetrics.account_id, PositionMetrics.exchange)
            )
            stats_result = await session.execute(stats_query)
            stats = stats_result.all()
            
            console.print(f"[green]✓ 数据库中有 {total_count} 条持仓指标记录[/green]\n")
            
            # 显示统计表
            table = Table(title="数据统计（按账号和交易所）")
            table.add_column("账号", justify="left")
            table.add_column("交易所", justify="left")
            table.add_column("记录数", justify="right")
            table.add_column("最新时间", justify="left")
            
            for stat in stats:
                table.add_row(
                    stat.account_id,
                    stat.exchange,
                    str(stat.count),
                    stat.latest_time.strftime("%Y-%m-%d %H:%M:%S UTC") if stat.latest_time else "N/A"
                )
            
            console.print(table)
            console.print()
            
            # 显示最新记录
            table2 = Table(title="最新记录（最近20条）")
            table2.add_column("时间", justify="left")
            table2.add_column("账号", justify="left")
            table2.add_column("交易所", justify="left")
            table2.add_column("交易对", justify="left")
            table2.add_column("单日 PnL", justify="right")
            table2.add_column("累计 PnL", justify="right")
            
            for record in records:
                table2.add_row(
                    record.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    record.account_id,
                    record.exchange,
                    record.symbol,
                    f"{float(record.daily_pnl):,.2f}",
                    f"{float(record.cumulative_pnl):,.2f}"
                )
            
            console.print(table2)
            
    except Exception as e:
        console.print(f"[red]✗ 查询失败: {e}[/red]")
        import traceback
        traceback.print_exc()
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())

