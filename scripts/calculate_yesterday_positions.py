#!/usr/bin/env python3
"""计算昨日持仓量统计脚本.

使用 XTPositionCalculator 从数据库的历史持仓快照中查询并计算昨日持仓指标。
"""

import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from tri_arb.services.xt_position_calculator import XTPositionCalculator
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def calculate_yesterday_positions(
    database_url: str,
    account_id: str | None = None,
    hours_back: int = 24,
    use_websocket: bool = True
):
    """计算昨日持仓量统计.
    
    Args:
        database_url: 数据库连接URL
        account_id: 账号ID（可选），用于多账号场景
        hours_back: 往前回溯的小时数（默认24小时，即昨日）
        use_websocket: 是否使用 WebSocket 数据（默认 True，推荐）
    """
    # 创建数据库连接
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 创建持仓量计算器
        calculator = XTPositionCalculator(
            db_session=session,
            account_id=account_id
        )
        
        # 计算昨日持仓指标（默认使用 WebSocket 数据）
        target_date = datetime.utcnow() - timedelta(hours=hours_back)
        metrics = await calculator.calculate_pre_position_metrics(
            target_date=target_date,
            hours_back=hours_back,
            use_websocket=use_websocket
        )
        
        # 显示数据来源
        data_source = "WebSocket" if use_websocket else "REST API"
        
        # 输出结果
        print("=" * 60)
        print("昨日持仓量统计")
        print("=" * 60)
        print(f"目标时间: {target_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"数据来源: {data_source} {'(推荐)' if use_websocket else ''}")
        if account_id:
            print(f"账号ID: {account_id}")
        print()
        print("持仓量:")
        print(f"  昨日多头持仓量 (pre_long_qty):     {metrics['pre_long_qty']:,.10f}")
        print(f"  昨日空头持仓量 (pre_short_qty):    {metrics['pre_short_qty']:,.10f}")
        print()
        print("持仓市值:")
        print(f"  昨日多头市值 (pre_long_value):    {metrics['pre_long_value']:,.2f} USDT")
        print(f"  昨日空头市值 (pre_short_value):    {metrics['pre_short_value']:,.2f} USDT")
        print()
        print("总计:")
        total_qty = metrics['pre_long_qty'] + metrics['pre_short_qty']
        total_value = metrics['pre_long_value'] + metrics['pre_short_value']
        print(f"  总持仓量:                         {total_qty:,.10f}")
        print(f"  总持仓市值:                       {total_value:,.2f} USDT")
        print("=" * 60)
        
        return metrics


async def main():
    """主函数."""
    import argparse
    
    parser = argparse.ArgumentParser(description="计算昨日持仓量统计")
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.getenv("DATABASE_URL"),
        help="数据库连接URL（默认从环境变量DATABASE_URL读取）"
    )
    parser.add_argument(
        "--account-id",
        type=str,
        default=None,
        help="账号ID（可选），用于多账号场景"
    )
    parser.add_argument(
        "--hours-back",
        type=int,
        default=24,
        help="往前回溯的小时数（默认24小时，即昨日）"
    )
    parser.add_argument(
        "--use-websocket",
        action="store_true",
        default=True,
        help="使用 WebSocket 数据（默认，推荐）"
    )
    parser.add_argument(
        "--use-rest-api",
        action="store_true",
        help="使用 REST API 持仓快照数据（备选）"
    )
    
    args = parser.parse_args()
    
    # 确定数据源
    use_websocket = args.use_websocket and not args.use_rest_api
    
    if not args.database_url:
        print("错误: 请提供数据库连接URL（通过 --database-url 参数或 DATABASE_URL 环境变量）")
        return
    
    try:
        metrics = await calculate_yesterday_positions(
            database_url=args.database_url,
            account_id=args.account_id,
            hours_back=args.hours_back,
            use_websocket=use_websocket
        )
        
        # 返回结果（可用于脚本调用）
        return metrics
        
    except Exception as e:
        logger.error(f"计算失败: {e}", exc_info=True)
        print(f"错误: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

