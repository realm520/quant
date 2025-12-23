#!/usr/bin/env python3
"""
补充指定时间段的 position_metrics 数据
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tri_arb.storage.database import DatabaseManager
from tri_arb.services.position_calculator import PositionCalculator
from tri_arb.services.contract_multiplier_service import ContractMultiplierService
from tri_arb.storage.position_metrics_models import PositionMetrics
from scripts.rebuild_position_metrics import _calculate_metrics_for_time


async def supplement_time_range(
    account_id: str,
    exchange: str,
    start_time: datetime,
    end_time: datetime,
    symbol: str | None = None,
    database_url: str | None = None,
):
    """补充指定时间段的 position_metrics 数据。
    
    Args:
        account_id: 账号ID
        exchange: 交易所名称
        start_time: 开始时间（包含）
        end_time: 结束时间（包含）
        symbol: 交易对（可选），None 表示所有交易对
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
    
    async with db_manager.session() as session:
        try:
            # 创建合约乘数服务
            contract_multiplier_service = ContractMultiplierService()
            
            # 创建合约乘数 getter
            def sync_getter(symbol: str) -> Decimal:
                """同步获取合约乘数."""
                try:
                    return contract_multiplier_service.get_multiplier_sync(exchange, symbol)
                except Exception:
                    return Decimal("1")
            
            # 创建 PositionCalculator
            calc = PositionCalculator(
                session,
                exchange=exchange,
                account_id=account_id,
                contract_multiplier_getter=sync_getter,
            )
            
            # 查询数据库中已有的时间点
            print(f"正在查询数据库中已有的时间点...")
            existing_times_query = select(
                PositionMetrics.timestamp,
                PositionMetrics.symbol
            ).where(
                PositionMetrics.account_id == account_id
            ).where(
                PositionMetrics.exchange == exchange
            ).where(
                PositionMetrics.timestamp >= start_time
            ).where(
                PositionMetrics.timestamp <= end_time
            )
            if symbol:
                existing_times_query = existing_times_query.where(PositionMetrics.symbol == symbol)
            
            existing_times_result = await session.execute(existing_times_query)
            existing_times_set = {(row[0], row[1]) for row in existing_times_result.all()}
            print(f"时间范围内已有 {len(existing_times_set)} 条记录")
            
            # 从开始时间到结束时间，每隔5分钟计算一次
            current_time = start_time
            # 如果不是整点，调整到下一个5分钟间隔
            if current_time.minute % 5 != 0:
                current_time = current_time.replace(minute=(current_time.minute // 5 + 1) * 5, second=0, microsecond=0)
            
            interval = timedelta(minutes=5)
            calculated_count = 0
            skipped_count = 0
            
            print(f"开始补充数据: {start_time} -> {end_time}")
            print(f"起始时间点: {current_time}")
            
            while current_time <= end_time:
                # 跳过零点（如果需要保留零点，可以注释掉这行）
                # if current_time.hour == 0 and current_time.minute == 0:
                #     current_time += interval
                #     continue
                
                try:
                    # 如果指定了 symbol，检查该时间点是否已存在
                    if symbol:
                        if (current_time, symbol) in existing_times_set:
                            skipped_count += 1
                            current_time += interval
                            continue
                    
                    # 计算该时间点的数据
                    await _calculate_metrics_for_time(
                        session=session,
                        calc=calc,
                        account_id=account_id,
                        exchange=exchange,
                        symbol=symbol,
                        target_time=current_time,
                    )
                    calculated_count += 1
                    
                    # 每50个时间点提交一次
                    if calculated_count % 50 == 0:
                        await session.commit()
                        print(f"已计算 {calculated_count} 个时间点，跳过 {skipped_count} 个已存在的时间点...")
                except Exception as e:
                    print(f"计算时间点 {current_time} 的数据时出错: {e}")
                    import traceback
                    traceback.print_exc()
                    await session.rollback()
                
                current_time += interval
            
            await session.commit()
            print(f"\n✅ 补充完成！")
            print(f"✅ 已计算 {calculated_count} 个时间点")
            print(f"✅ 跳过 {skipped_count} 个已存在的时间点")
            
        except Exception as e:
            print(f"错误：{e}")
            await session.rollback()
            raise


async def main():
    parser = argparse.ArgumentParser(description="补充指定时间段的 position_metrics 数据")
    parser.add_argument("--account-id", required=True, help="账号ID")
    parser.add_argument("--exchange", required=True, help="交易所名称（如 xt, binance）")
    parser.add_argument("--symbol", default=None, help="交易对（可选），不指定则处理所有交易对")
    parser.add_argument("--start-time", required=True, help="开始时间 (格式: YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--end-time", required=True, help="结束时间 (格式: YYYY-MM-DD HH:MM:SS)")
    parser.add_argument(
        "--database-url",
        default=None,
        help="数据库连接URL（可选），如果不提供则从环境变量 DATABASE_URL 读取",
    )
    
    args = parser.parse_args()
    
    # 解析时间
    try:
        start_time = datetime.strptime(args.start_time, "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(args.end_time, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        print("错误：时间格式不正确，请使用 YYYY-MM-DD HH:MM:SS 格式")
        return
    
    await supplement_time_range(
        account_id=args.account_id,
        exchange=args.exchange,
        start_time=start_time,
        end_time=end_time,
        symbol=args.symbol,
        database_url=args.database_url,
    )


if __name__ == "__main__":
    asyncio.run(main())
