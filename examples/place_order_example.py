#!/usr/bin/env python3
"""多交易所下单示例

演示如何使用不同交易所的下单功能。

⚠️ 警告：此示例会实际下单！请在测试环境或使用小额资金测试！

使用方法:
    1. 设置环境变量
    2. 修改下单参数（symbol, quantity, price等）
    3. 运行示例
"""

import asyncio
import os
from decimal import Decimal

from tri_arb.exchanges.binance_perp import BinancePerpExchange
from tri_arb.exchanges.okx_perp import OKXPerpExchange


async def example_okx_place_limit_order():
    """示例1: OKX限价下单"""
    print("=" * 60)
    print("示例1: OKX永续合约限价下单")
    print("=" * 60)
    
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    
    if not all([api_key, api_secret, passphrase]):
        print("❌ 错误: 请设置 OKX_API_KEY, OKX_API_SECRET 和 OKX_PASSPHRASE")
        return
    
    exchange = OKXPerpExchange(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase
    )
    
    try:
        await exchange.connect()
        print("✅ 已连接到OKX")
        
        # ⚠️ 实际下单参数 - 请根据实际情况修改！
        result = await exchange.place_order(
            symbol="BTC-USDT-SWAP",      # 产品ID
            side="buy",                   # 买入
            order_type="limit",           # 限价单
            quantity="0.001",             # 数量（请使用小额测试！）
            price="30000",                # 价格（设置一个不会成交的价格用于测试）
            position_side="long",         # 开多仓
        )
        
        print(f"\n✅ 订单已提交！")
        print(f"  订单ID: {result.get('ordId')}")
        print(f"  客户订单ID: {result.get('clOrdId')}")
        print(f"  执行结果: {result.get('sMsg')}")
        
    except Exception as e:
        print(f"❌ 下单失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await exchange.disconnect()


async def example_okx_place_market_order():
    """示例2: OKX市价下单"""
    print("\n" + "=" * 60)
    print("示例2: OKX永续合约市价下单")
    print("=" * 60)
    
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    
    if not all([api_key, api_secret, passphrase]):
        print("❌ 错误: 请设置 OKX API凭证")
        return
    
    exchange = OKXPerpExchange(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase
    )
    
    try:
        await exchange.connect()
        
        # ⚠️ 市价单会立即成交！请谨慎使用！
        print("⚠️  警告：市价单会立即成交！")
        print("建议：在实际使用前，先用限价单测试")
        
        # 取消注释以下代码来实际下单
        # result = await exchange.place_order(
        #     symbol="BTC-USDT-SWAP",
        #     side="buy",
        #     order_type="market",
        #     quantity="0.001",  # 请使用小额测试！
        #     position_side="long",
        # )
        # print(f"✅ 市价单已成交！订单ID: {result.get('ordId')}")
        
        print("（代码已注释，取消注释以实际下单）")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    finally:
        await exchange.disconnect()


async def example_binance_place_limit_order():
    """示例3: Binance限价下单"""
    print("\n" + "=" * 60)
    print("示例3: Binance永续合约限价下单")
    print("=" * 60)
    
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    
    if not api_key or not api_secret:
        print("❌ 错误: 请设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        return
    
    exchange = BinancePerpExchange(
        api_key=api_key,
        api_secret=api_secret
    )
    
    try:
        await exchange.connect()
        print("✅ 已连接到Binance")
        
        # ⚠️ 实际下单参数
        result = await exchange.place_order(
            symbol="BTCUSDT",             # 交易对
            side="BUY",                   # 买入
            order_type="LIMIT",           # 限价单
            quantity="0.001",             # 数量
            price="30000",                # 价格（低于市价，不会立即成交）
            position_side="LONG",         # 开多仓
            time_in_force="GTC",          # 一直有效直到取消
        )
        
        print(f"\n✅ 订单已提交！")
        print(f"  订单ID: {result.get('orderId')}")
        print(f"  交易对: {result.get('symbol')}")
        print(f"  状态: {result.get('status')}")
        print(f"  价格: {result.get('price')}")
        print(f"  数量: {result.get('origQty')}")
        
    except Exception as e:
        print(f"❌ 下单失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await exchange.disconnect()


async def example_comparison():
    """示例4: 对比不同交易所的下单"""
    print("\n" + "=" * 60)
    print("示例4: 多交易所下单对比")
    print("=" * 60)
    
    print("\n📊 下单参数对比：\n")
    
    print("OKX:")
    print("  symbol: 'BTC-USDT-SWAP'")
    print("  side: 'buy' (小写)")
    print("  order_type: 'limit'")
    print("  position_side: 'long'")
    
    print("\nBinance:")
    print("  symbol: 'BTCUSDT'")
    print("  side: 'BUY' (大写)")
    print("  order_type: 'LIMIT'")
    print("  position_side: 'LONG'")
    
    print("\n主要差异：")
    print("  1. Symbol格式: OKX用横杠分隔，Binance直接拼接")
    print("  2. 大小写: OKX小写，Binance大写")
    print("  3. 认证: OKX需要3个参数(+Passphrase)")


async def main():
    """运行示例"""
    print("\n🚀 多交易所下单功能示例\n")
    print("⚠️  警告：此示例会实际下单！")
    print("⚠️  建议：使用小额资金和不会成交的价格进行测试\n")
    
    # 示例1: OKX限价单
    await example_okx_place_limit_order()
    
    # 示例2: OKX市价单（已注释）
    await example_okx_place_market_order()
    
    # 示例3: Binance限价单
    await example_binance_place_limit_order()
    
    # 示例4: 参数对比
    await example_comparison()
    
    print("\n✅ 示例运行完成!")
    print("\n💡 提示:")
    print("  1. 下单前请先确认账户有足够余额")
    print("  2. 建议先用限价单测试（不会立即成交）")
    print("  3. 测试完成后记得撤销测试订单")
    print("  4. 查看挂单: cextools account orders -x okx -e perp")


if __name__ == "__main__":
    asyncio.run(main())

