#!/usr/bin/env python3
"""OKX合约完整功能示例

演示如何使用 OKXPerpExchange 查询余额、持仓和挂单。

使用方法:
    1. 设置环境变量：
       export OKX_API_KEY="your_api_key"
       export OKX_API_SECRET="your_api_secret"
       export OKX_PASSPHRASE="your_passphrase"

    2. 运行示例：
       python examples/okx_example.py
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal

from tri_arb.exchanges.okx_perp import OKXPerpExchange


async def example_get_balance():
    """示例1: 查询账户余额"""
    print("=" * 60)
    print("示例1: 查询账户余额")
    print("=" * 60)

    # 从环境变量获取API凭证
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")

    if not api_key or not api_secret or not passphrase:
        print("❌ 错误: 请设置 OKX_API_KEY, OKX_API_SECRET 和 OKX_PASSPHRASE 环境变量")
        return

    # 创建交易所实例
    exchange = OKXPerpExchange(
        api_key=api_key, api_secret=api_secret, passphrase=passphrase
    )

    try:
        # 连接交易所
        await exchange.connect()
        print("✅ 已连接到OKX永续合约交易所")

        # 查询账户余额
        balances = await exchange.get_balance()

        if not balances:
            print("📭 账户余额为空")
        else:
            print(f"📊 账户余额 ({len(balances)} 种资产):\n")

            for currency, balance in balances.items():
                print(f"{currency}:")
                print(f"  可用: {balance['available']}")
                print(f"  冻结: {balance['frozen']}")
                print(f"  总计: {balance['total']}")
                print()

    except Exception as e:
        print(f"❌ 错误: {e}")

    finally:
        # 断开连接
        await exchange.disconnect()
        print("👋 已断开连接")


async def example_get_positions():
    """示例2: 查询持仓"""
    print("\n" + "=" * 60)
    print("示例2: 查询所有持仓")
    print("=" * 60)

    # 从环境变量获取API凭证
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")

    if not api_key or not api_secret or not passphrase:
        print("❌ 错误: 请设置 OKX_API_KEY, OKX_API_SECRET 和 OKX_PASSPHRASE 环境变量")
        return

    # 创建交易所实例
    exchange = OKXPerpExchange(
        api_key=api_key, api_secret=api_secret, passphrase=passphrase
    )

    try:
        # 连接交易所
        await exchange.connect()

        # 查询所有持仓
        positions = await exchange.get_positions()

        if not positions:
            print("📭 当前没有持仓")
        else:
            print(f"📊 共找到 {len(positions)} 个持仓:\n")

            for i, pos in enumerate(positions, 1):
                print(f"持仓 #{i}:")
                print(f"  产品ID: {pos['instId']}")
                print(f"  持仓方向: {pos['posSide']}")
                print(f"  持仓数量: {pos['pos']}")
                print(f"  开仓均价: {pos['avgPx']}")
                print(f"  标记价格: {pos['markPx']}")
                print(f"  未实现盈亏: {pos['upl']}")
                print(f"  未实现盈亏率: {pos['uplRatio'] * 100:.2f}%")
                print(f"  杠杆倍数: {pos['lever']}x")
                print(f"  预估强平价: {pos['liqPx']}")
                print(f"  保证金模式: {pos['mgnMode']}")
                print(f"  保证金余额: {pos['margin']}")
                print()

    except Exception as e:
        print(f"❌ 错误: {e}")

    finally:
        # 断开连接
        await exchange.disconnect()


async def example_get_orders():
    """示例3: 查询挂单"""
    print("\n" + "=" * 60)
    print("示例3: 查询所有挂单")
    print("=" * 60)

    # 从环境变量获取API凭证
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")

    if not api_key or not api_secret or not passphrase:
        print("❌ 错误: 请设置 OKX_API_KEY, OKX_API_SECRET 和 OKX_PASSPHRASE 环境变量")
        return

    # 创建交易所实例
    exchange = OKXPerpExchange(
        api_key=api_key, api_secret=api_secret, passphrase=passphrase
    )

    try:
        # 连接交易所
        await exchange.connect()

        # 查询所有挂单
        orders = await exchange.get_open_orders()

        if not orders:
            print("📭 当前没有挂单")
        else:
            print(f"📊 共找到 {len(orders)} 个挂单:\n")

            for i, order in enumerate(orders, 1):
                order_time = datetime.fromtimestamp(int(order["cTime"]) / 1000)

                print(f"挂单 #{i}:")
                print(f"  订单ID: {order['ordId']}")
                print(f"  产品ID: {order['instId']}")
                print(f"  方向: {order['side']}")
                print(f"  持仓方向: {order['posSide']}")
                print(f"  订单类型: {order['ordType']}")
                print(f"  价格: {order['px']}")
                print(f"  数量: {order['sz']}")
                print(f"  已成交: {order['accFillSz']}")
                print(f"  状态: {order['state']}")
                print(f"  杠杆: {order['lever']}x")
                print(f"  创建时间: {order_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print()

    except Exception as e:
        print(f"❌ 错误: {e}")

    finally:
        # 断开连接
        await exchange.disconnect()


async def example_comprehensive_analysis():
    """示例4: 综合分析"""
    print("\n" + "=" * 60)
    print("示例4: 账户综合分析")
    print("=" * 60)

    # 从环境变量获取API凭证
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")

    if not api_key or not api_secret or not passphrase:
        print("❌ 错误: 请设置 OKX_API_KEY, OKX_API_SECRET 和 OKX_PASSPHRASE 环境变量")
        return

    # 创建交易所实例
    exchange = OKXPerpExchange(
        api_key=api_key, api_secret=api_secret, passphrase=passphrase
    )

    try:
        # 连接交易所
        await exchange.connect()

        # 查询余额、持仓和挂单
        balances = await exchange.get_balance()
        positions = await exchange.get_positions()
        orders = await exchange.get_open_orders()

        print("📊 账户概览:")
        print(f"  资产种类: {len(balances)}")
        print(f"  持仓数量: {len(positions)}")
        print(f"  挂单数量: {len(orders)}")

        # 计算总未实现盈亏
        if positions:
            total_upl = sum(pos["upl"] for pos in positions)
            print(f"\n💰 总未实现盈亏: {total_upl:.4f} USDT")

            # 按盈亏排序
            profitable = sorted(positions, key=lambda x: x["upl"], reverse=True)

            print("\n📈 盈利前3:")
            for pos in profitable[:3]:
                if pos["upl"] > 0:
                    print(
                        f"  {pos['instId']}: +{pos['upl']:.4f} ({pos['uplRatio'] * 100:.2f}%)"
                    )

            print("\n📉 亏损前3:")
            losing = sorted(positions, key=lambda x: x["upl"])
            for pos in losing[:3]:
                if pos["upl"] < 0:
                    print(
                        f"  {pos['instId']}: {pos['upl']:.4f} ({pos['uplRatio'] * 100:.2f}%)"
                    )

        # 按交易对分组挂单
        if orders:
            symbols = {}
            for order in orders:
                symbol = order["instId"]
                symbols[symbol] = symbols.get(symbol, 0) + 1

            print("\n📋 挂单分布:")
            for symbol, count in sorted(
                symbols.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"  {symbol}: {count}个订单")

    except Exception as e:
        print(f"❌ 错误: {e}")

    finally:
        # 断开连接
        await exchange.disconnect()


async def main():
    """运行所有示例"""
    print("\n🚀 OKX合约完整功能示例\n")

    # 运行示例1: 查询余额
    await example_get_balance()

    # 运行示例2: 查询持仓
    await example_get_positions()

    # 运行示例3: 查询挂单
    await example_get_orders()

    # 运行示例4: 综合分析
    await example_comprehensive_analysis()

    print("\n✅ 所有示例运行完成!")


if __name__ == "__main__":
    asyncio.run(main())
