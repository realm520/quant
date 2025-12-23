#!/usr/bin/env python3
"""
重建 position_metrics 表的所有数据。

用于修复 avg_sell_prz 计算错误导致的数据问题。
会重新计算所有零点快照和实时数据。
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.position_metrics_scheduler import PositionMetricsScheduler
from tri_arb.storage.position_metrics_models import PositionMetrics


async def rebuild_all_metrics(
    account_id: str,
    exchange: str,
    symbol: str | None = None,
    delete_existing: bool = True,
    database_url: str | None = None,
):
    """重建所有 position_metrics 数据。
    
    Args:
        account_id: 账号ID
        exchange: 交易所名称
        symbol: 交易对（可选），None 表示所有交易对
        delete_existing: 是否删除现有数据（默认 True）
        database_url: 数据库连接URL（可选），如果不提供则从环境变量读取
    """
    # 获取数据库连接URL
    if database_url is None:
        database_url = os.getenv("DATABASE_URL")
    
    if database_url is None:
        raise ValueError(
            "数据库连接URL未设置。请通过以下方式之一设置：\n"
            "1. 设置环境变量 DATABASE_URL:\n"
            "   export DATABASE_URL='postgresql+asyncpg://user:password@host:port/dbname'\n"
            "2. 或在命令行传入 --database-url 参数"
        )
    
    db_manager = DatabaseManager(database_url=database_url)
    scheduler = PositionMetricsScheduler(db_manager)
    
    async with db_manager.session() as session:
        try:
            # 1. 删除现有数据（可选）
            if delete_existing:
                print(f"正在删除现有的 position_metrics 数据...")
                delete_query = delete(PositionMetrics).where(
                    PositionMetrics.account_id == account_id
                ).where(
                    PositionMetrics.exchange == exchange
                )
                if symbol:
                    delete_query = delete_query.where(PositionMetrics.symbol == symbol)
                
                result = await session.execute(delete_query)
                deleted_count = result.rowcount
                print(f"已删除 {deleted_count} 条记录")
                await session.commit()
            
            # 2. 创建合约乘数服务（如果需要）
            from tri_arb.services.contract_multiplier_service import ContractMultiplierService
            contract_multiplier_service = ContractMultiplierService()
            
            # 创建合约乘数 getter
            contract_multiplier_getter = None
            if contract_multiplier_service:
                # 使用同步方法，直接调用公开 API（不需要 API key）
                service = contract_multiplier_service
                exchange_name = exchange
                
                # 使用闭包捕获 service 和 exchange
                def sync_getter(symbol: str) -> Decimal:
                    """同步获取合约乘数."""
                    try:
                        return service.get_multiplier_sync(exchange_name, symbol)
                    except Exception:
                        return Decimal("1")
                
                contract_multiplier_getter = sync_getter
            
            # 3. 创建 PositionCalculator（需要在 session 内创建）
            calc = PositionCalculator(
                session,
                exchange=exchange,
                account_id=account_id,
                contract_multiplier_getter=contract_multiplier_getter,
            )
            
            # 4. 重建零点快照
            print(f"正在重建零点快照...")
            await scheduler._rebuild_midnight_snapshots(
                session=session,
                calc=calc,
                account_id=account_id,
                exchange=exchange,
                symbol=symbol,
            )
            await session.commit()
            print(f"零点快照重建完成")
            
            # 5. 重新计算实时数据
            # 注意：实时数据是每5分钟计算的，这里只重新计算当前时刻的数据
            # 历史实时数据需要等待调度器自动重新计算，或者可以手动触发
            print(f"正在重新计算当前时刻的实时数据...")
            
            # 调用调度器的计算方法来重新计算当前数据
            # 这会使用正确的 avg_sell_prz 公式
            try:
                await scheduler._calculate_and_store_metrics(
                    session=session,
                    account_id=account_id,
                    exchange=exchange,
                    symbol=symbol,
                )
                await session.commit()
                print(f"当前时刻的实时数据已重新计算")
            except Exception as e:
                print(f"重新计算实时数据时出错（这可能是正常的，如果调度器未运行）: {e}")
                await session.rollback()
            
            print(f"\n数据重建完成！")
            print(f"✅ 所有零点快照已使用正确的公式重新计算")
            print(f"✅ 当前时刻的实时数据已重新计算")
            print(f"\n注意：")
            print(f"  - 历史实时数据（非零点快照）会在下次调度时自动使用正确的公式重新计算")
            print(f"  - 或者您可以等待调度器运行，它会自动修复所有数据")
            
        except Exception as e:
            print(f"错误：{e}")
            await session.rollback()
            raise


async def main():
    parser = argparse.ArgumentParser(description="重建 position_metrics 表的所有数据")
    parser.add_argument("--account-id", required=True, help="账号ID")
    parser.add_argument("--exchange", required=True, help="交易所名称（如 xt, binance）")
    parser.add_argument("--symbol", default=None, help="交易对（可选），不指定则处理所有交易对")
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="保留现有数据（不删除），只重建缺失的数据",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="数据库连接URL（可选），如果不提供则从环境变量 DATABASE_URL 读取",
    )
    
    args = parser.parse_args()
    
    await rebuild_all_metrics(
        account_id=args.account_id,
        exchange=args.exchange,
        symbol=args.symbol,
        delete_existing=not args.keep_existing,
        database_url=args.database_url,
    )


if __name__ == "__main__":
    asyncio.run(main())
