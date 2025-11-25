#!/usr/bin/env python3
"""Binance WebSocket订阅示例

演示如何订阅Binance用户数据流并存储到PostgreSQL。

使用方法:
    1. 安装依赖: pip install -r requirements-db.txt
    2. 启动PostgreSQL
    3. 设置环境变量
    4. 运行示例: python examples/binance_websocket_example.py
"""

import asyncio
import os

from tri_arb.services.binance_user_stream import BinanceUserStreamService
from tri_arb.storage.database import DatabaseManager


async def example_subscribe_and_store():
    """示例：订阅Binance用户数据流并存储到数据库"""
    
    print("=" * 60)
    print("Binance WebSocket订阅示例")
    print("=" * 60)
    
    # 从环境变量获取凭证
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/trading"
    )
    
    if not api_key or not api_secret:
        print("❌ 错误: 请设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        return
    
    print(f"\n配置信息:")
    print(f"  API Key: {api_key[:8]}...")
    print(f"  数据库: {database_url.split('@')[-1]}\n")
    
    # 初始化数据库管理器
    db_manager = DatabaseManager(database_url=database_url)
    
    # 创建数据库表
    print("正在创建数据库表...")
    await db_manager.create_tables()
    print("✅ 数据库表创建成功\n")
    
    # 初始化订阅服务
    service = BinanceUserStreamService(
        api_key=api_key,
        api_secret=api_secret,
        db_manager=db_manager,
        auto_reconnect=True,
        display_format="table",  # 可选: table, json, none
    )
    
    print("✅ 服务已初始化")
    print("正在连接WebSocket...")
    print("按 Ctrl+C 停止订阅\n")
    
    try:
        # 启动订阅
        await service.start()
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        await service.stop()
        await db_manager.close()
        print("✅ 服务已停止")


async def example_query_data():
    """示例：查询数据库中的数据"""
    
    print("\n" + "=" * 60)
    print("查询数据库示例")
    print("=" * 60)
    
    from tri_arb.storage.models import OrderUpdate, TradeUpdate, AccountUpdate
    from sqlalchemy import select, func
    
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/trading"
    )
    
    db_manager = DatabaseManager(database_url=database_url)
    
    async with db_manager.session() as session:
        # 查询最近的订单更新
        print("\n📊 最近的订单更新:")
        stmt = select(OrderUpdate).order_by(OrderUpdate.event_time.desc()).limit(5)
        result = await session.execute(stmt)
        orders = result.scalars().all()
        
        for order in orders:
            print(f"  {order.symbol} - {order.side} - {order.order_status} - {order.event_time}")
        
        # 查询今日成交次数
        print("\n📈 今日成交统计:")
        from datetime import date
        today = date.today()
        
        stmt = select(
            TradeUpdate.symbol,
            func.count(TradeUpdate.id).label('count'),
            func.sum(TradeUpdate.quantity).label('total_qty'),
            func.sum(TradeUpdate.commission).label('total_fee')
        ).where(
            func.date(TradeUpdate.transaction_time) == today
        ).group_by(TradeUpdate.symbol)
        
        result = await session.execute(stmt)
        stats = result.all()
        
        for stat in stats:
            print(f"  {stat.symbol}: {stat.count}笔, 数量: {stat.total_qty}, 手续费: {stat.total_fee}")
        
        # 查询最近的账户更新
        print("\n💰 最近的账户更新:")
        stmt = select(AccountUpdate).order_by(AccountUpdate.event_time.desc()).limit(5)
        result = await session.execute(stmt)
        updates = result.scalars().all()
        
        for update in updates:
            if update.asset:
                print(f"  {update.asset} - 余额: {update.wallet_balance} - {update.event_time}")
            elif update.symbol:
                print(f"  {update.symbol} - 持仓: {update.position_amount} - {update.event_time}")
    
    await db_manager.close()
    print("\n✅ 查询完成")


async def main():
    """运行示例"""
    
    print("\n🚀 Binance WebSocket订阅功能示例\n")
    print("⚠️  此示例会:")
    print("  1. 连接到Binance WebSocket")
    print("  2. 订阅用户数据流")
    print("  3. 将数据存储到PostgreSQL")
    print()
    
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "query":
        # 仅查询数据
        await example_query_data()
    else:
        # 订阅并存储
        await example_subscribe_and_store()


if __name__ == "__main__":
    asyncio.run(main())

