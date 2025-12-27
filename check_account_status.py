#!/usr/bin/env python3
"""
检查 XT 账户当前状态：余额、持仓、挂单
"""

import asyncio
import sys
sys.path.insert(0, "/home/ubuntu/quant/src")

from tri_arb.exchanges.xt_perp import XTPerpExchange

# XT API 配置
API_KEY = "28a898c2-afe2-4823-b2ca-306433959365"
API_SECRET = "5280f1ab4483a0a7c8ee4f63139ca3ed6e042921"


async def check_account():
    """检查账户状态"""
    print("=" * 80)
    print("检查 XT 账户状态")
    print("=" * 80)

    exchange = XTPerpExchange(API_KEY, API_SECRET)
    await exchange.connect()

    try:
        # 1. 检查余额
        print("\n【1. 账户余额】")
        print("-" * 80)
        balances = await exchange.get_balance()
        if balances:
            for currency, balance_info in balances.items():
                total = balance_info.get("total", 0)
                available = balance_info.get("available", 0)
                if float(total) > 0:
                    print(f"  {currency}:")
                    print(f"    总余额: {total}")
                    print(f"    可用余额: {available}")
                    print(f"    冻结: {float(total) - float(available)}")
        else:
            print("  ⚠️  没有余额或余额为空")

        # 2. 检查持仓
        print("\n【2. 当前持仓】")
        print("-" * 80)
        positions = await exchange.get_positions()
        if positions:
            has_positions = False
            for pos in positions:
                qty = float(pos.quantity) if hasattr(pos, 'quantity') else 0
                if qty != 0:
                    has_positions = True
                    print(f"  {pos.symbol if hasattr(pos, 'symbol') else 'Unknown'}:")
                    print(f"    方向: {pos.side if hasattr(pos, 'side') else 'Unknown'}")
                    print(f"    数量: {pos.quantity if hasattr(pos, 'quantity') else 0}")
                    print(f"    入场价: {pos.entry_price if hasattr(pos, 'entry_price') else 0}")
                    print(f"    未实现盈亏: {pos.unrealized_pnl if hasattr(pos, 'unrealized_pnl') else 0}")
            if not has_positions:
                print("  ⚠️  当前没有持仓")
        else:
            print("  ⚠️  当前没有持仓")

        # 3. 检查挂单
        print("\n【3. 当前挂单】")
        print("-" * 80)
        try:
            # 尝试获取所有交易对的挂单
            open_orders = await exchange.get_open_orders()
            if open_orders:
                print(f"  共有 {len(open_orders)} 个挂单:")
                for order in open_orders[:5]:  # 只显示前5个
                    print(f"    订单ID: {order.get('orderId')}")
                    print(f"    交易对: {order.get('symbol')}")
                    print(f"    方向: {order.get('orderSide')}")
                    print(f"    价格: {order.get('price')}")
                    print(f"    数量: {order.get('origQty')}")
                    print(f"    状态: {order.get('state')}")
                    print()
            else:
                print("  ⚠️  当前没有挂单")
        except Exception as e:
            print(f"  ⚠️  获取挂单失败: {e}")

        # 总结
        print("\n" + "=" * 80)
        print("【结论】")
        print("=" * 80)
        has_balance = bool(balances and any(float(b.get("total", 0)) > 0 for b in balances.values()))
        has_position = bool(positions and any(float(getattr(p, 'quantity', 0)) != 0 for p in positions))

        if not has_balance:
            print("❌ 账户余额为空")
        else:
            print("✅ 账户有余额")

        if not has_position:
            print("❌ 账户没有持仓")
        else:
            print("✅ 账户有持仓")

        print("\n💡 提示:")
        if not has_balance and not has_position:
            print("  WebSocket 订阅已成功，但账户为空，不会收到数据推送。")
            print("  WebSocket 推送是事件驱动的，只有当发生以下事件时才会推送：")
            print("    - 账户余额变动（充值、提现、交易手续费等）")
            print("    - 订单状态变化（下单、成交、取消等）")
            print("    - 持仓变动（开仓、平仓、爆仓等）")
            print("    - 成交发生")
            print("\n  建议：下一个测试单（最小数量）来验证 WebSocket 数据推送功能。")
        else:
            print("  账户有活动，应该能收到 WebSocket 推送。")
            print("  如果长时间没有新的交易活动，也不会收到新的推送。")

    finally:
        await exchange.disconnect()

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(check_account())
