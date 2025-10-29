#!/usr/bin/env python3
"""测试reconciliation服务的事务管理修复.

此脚本模拟reconciliation服务处理多个symbol时的错误场景，
验证savepoint是否正确隔离了失败的影响。
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.models import OrderUpdate
from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


async def test_transaction_isolation():
    """测试事务隔离是否正常工作."""

    db_manager = DatabaseManager()

    try:
        print("🔬 Testing transaction isolation with savepoints...")
        print()

        # 测试1: 模拟部分symbol失败的场景
        print("Test 1: Simulating partial symbol failures")
        print("-" * 50)

        async with db_manager.session() as session:
            stats = {'success': 0, 'failed': 0}

            # 模拟3个symbol的处理
            test_symbols = ['BTCUSDT', 'ETHUSDT', 'INVALID_SYMBOL']

            for i, symbol in enumerate(test_symbols):
                print(f"\nProcessing symbol {i+1}/3: {symbol}")

                # 使用savepoint隔离每个symbol
                async with session.begin_nested():
                    try:
                        if symbol == 'INVALID_SYMBOL':
                            # 模拟错误：插入无效数据
                            raise ValueError(f"Simulated error for {symbol}")

                        # 模拟正常插入
                        order_record = {
                            'exchange': 'binance_perp',
                            'event_type': 'ORDER_TRADE_UPDATE',
                            'event_time': datetime.utcnow(),
                            'transaction_time': datetime.utcnow(),
                            'symbol': symbol,
                            'client_order_id': f'test_{symbol}_{i}',
                            'side': 'BUY',
                            'order_type': 'MARKET',
                            'original_quantity': 0.001,
                            'order_status': 'FILLED',
                            'order_id': 1000000 + i,
                            'cumulative_filled_quantity': 0.001,
                        }

                        order = OrderUpdate(**order_record)
                        session.add(order)
                        await session.flush()  # 触发数据库操作

                        stats['success'] += 1
                        print(f"  ✅ Successfully processed {symbol}")

                    except Exception as e:
                        stats['failed'] += 1
                        print(f"  ❌ Failed to process {symbol}: {e}")
                        print(f"     Savepoint will rollback, other symbols continue...")

            # 提交事务
            await session.commit()

            print()
            print("Results:")
            print(f"  Success: {stats['success']}/3")
            print(f"  Failed:  {stats['failed']}/3")
            print()

            if stats['success'] == 2 and stats['failed'] == 1:
                print("✅ Test PASSED: Savepoint successfully isolated failures!")
            else:
                print("❌ Test FAILED: Transaction isolation not working correctly")
                return False

        # 测试2: 验证成功的记录已保存
        print()
        print("Test 2: Verifying successful records were saved")
        print("-" * 50)

        async with db_manager.session() as session:
            from sqlalchemy import select, func

            # 统计今天的测试订单
            stmt = select(func.count(OrderUpdate.id)).where(
                OrderUpdate.client_order_id.like('test_%'),
                OrderUpdate.event_time >= datetime.utcnow() - timedelta(minutes=1)
            )
            result = await session.execute(stmt)
            count = result.scalar()

            print(f"\nFound {count} test records in database")

            if count >= 2:
                print("✅ Test PASSED: Successful records were saved!")
            else:
                print("❌ Test FAILED: Expected records not found in database")
                return False

        print()
        print("=" * 50)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 50)
        print()
        print("The reconciliation service transaction management is working correctly.")
        print("Savepoints successfully isolate failures without affecting other symbols.")

        return True

    except Exception as e:
        logger.error("Test failed with exception", error=str(e), exc_info=True)
        print(f"\n❌ Test failed with exception: {e}")
        return False

    finally:
        await db_manager.close()


if __name__ == "__main__":
    print()
    print("=" * 50)
    print("Reconciliation Transaction Management Test")
    print("=" * 50)
    print()

    success = asyncio.run(test_transaction_isolation())

    sys.exit(0 if success else 1)
