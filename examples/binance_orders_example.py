#!/usr/bin/env python3
"""币安合约挂单查询示例

演示如何使用 BinancePerpExchange 查询挂单信息。

使用方法:
    1. 设置环境变量：
       export BINANCE_API_KEY="your_api_key"
       export BINANCE_API_SECRET="your_api_secret"
    
    2. 运行示例：
       python examples/binance_orders_example.py
"""

import asyncio
import os
from datetime import datetime
from decimal import Decimal

from tri_arb.exchanges.binance_perp import BinancePerpExchange


async def example_get_all_orders():
    """示例1: 查询所有挂单"""
    print("=" * 60)
    print("示例1: 查询所有挂单")
    print("=" * 60)
    
    # 从环境变量获取API凭证
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    
    if not api_key or not api_secret:
        print("❌ 错误: 请设置 BINANCE_API_KEY 和 BINANCE_API_SECRET 环境变量")
        return
    
    # 创建交易所实例
    exchange = BinancePerpExchange(
        api_key=api_key,
        api_secret=api_secret
    )
    
    try:
        # 连接交易所
        await exchange.connect()
        print("✅ 已连接到币安永续合约交易所")
        
        # 查询所有挂单
        orders = await exchange.get_open_orders()
        
        if not orders:
            print("📭 当前没有挂单")
        else:
            print(f"📊 共找到 {len(orders)} 个挂单:\n")
            
            for i, order in enumerate(orders, 1):
                order_time = datetime.fromtimestamp(order['time'] / 1000)
                
                print(f"挂单 #{i}:")
                print(f"  订单ID: {order['orderId']}")
                print(f"  交易对: {order['symbol']}")
                print(f"  方向: {order['side']}")
                print(f"  持仓方向: {order['positionSide']}")
                print(f"  订单类型: {order['type']}")
                print(f"  价格: {order['price']}")
                print(f"  数量: {order['origQty']}")
                print(f"  已成交: {order['executedQty']}")
                print(f"  状态: {order['status']}")
                print(f"  时间: {order_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                if order['type'] in ['STOP', 'STOP_MARKET', 'TAKE_PROFIT', 'TAKE_PROFIT_MARKET']:
                    print(f"  触发价: {order['stopPrice']}")
                
                print()
    
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    finally:
        # 断开连接
        await exchange.disconnect()
        print("👋 已断开连接")


async def example_get_specific_symbol_orders():
    """示例2: 查询特定交易对的挂单"""
    print("\n" + "=" * 60)
    print("示例2: 查询特定交易对的挂单 (BTCUSDT)")
    print("=" * 60)
    
    # 从环境变量获取API凭证
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    
    if not api_key or not api_secret:
        print("❌ 错误: 请设置 BINANCE_API_KEY 和 BINANCE_API_SECRET 环境变量")
        return
    
    # 创建交易所实例
    exchange = BinancePerpExchange(
        api_key=api_key,
        api_secret=api_secret
    )
    
    try:
        # 连接交易所
        await exchange.connect()
        
        # 查询特定交易对的挂单（注意：币安格式不带斜杠）
        symbol = "BTCUSDT"
        orders = await exchange.get_open_orders(symbol=symbol)
        
        if not orders:
            print(f"📭 {symbol} 没有挂单")
        else:
            print(f"📊 {symbol} 挂单信息:\n")
            
            for order in orders:
                # 计算成交百分比
                orig_qty = order['origQty']
                executed_qty = order['executedQty']
                filled_pct = (executed_qty / orig_qty * 100) if orig_qty > 0 else Decimal('0')
                
                print(f"  订单ID: {order['orderId']}")
                print(f"  方向: {order['side']}")
                print(f"  类型: {order['type']}")
                print(f"  价格: {order['price']}")
                print(f"  数量: {orig_qty}")
                print(f"  已成交: {executed_qty} ({filled_pct:.2f}%)")
                print(f"  状态: {order['status']}")
                print()
    
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    finally:
        # 断开连接
        await exchange.disconnect()


async def example_analyze_orders():
    """示例3: 分析挂单统计"""
    print("\n" + "=" * 60)
    print("示例3: 挂单统计分析")
    print("=" * 60)
    
    # 从环境变量获取API凭证
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    
    if not api_key or not api_secret:
        print("❌ 错误: 请设置 BINANCE_API_KEY 和 BINANCE_API_SECRET 环境变量")
        return
    
    # 创建交易所实例
    exchange = BinancePerpExchange(
        api_key=api_key,
        api_secret=api_secret
    )
    
    try:
        # 连接交易所
        await exchange.connect()
        
        # 查询所有挂单
        orders = await exchange.get_open_orders()
        
        if not orders:
            print("📭 当前没有挂单")
            return
        
        # 统计数据
        total_orders = len(orders)
        buy_orders = [o for o in orders if o['side'] == 'BUY']
        sell_orders = [o for o in orders if o['side'] == 'SELL']
        
        # 按订单类型分组
        order_types = {}
        for order in orders:
            order_type = order['type']
            order_types[order_type] = order_types.get(order_type, 0) + 1
        
        # 按交易对分组
        symbols = {}
        for order in orders:
            symbol = order['symbol']
            symbols[symbol] = symbols.get(symbol, 0) + 1
        
        # 显示统计
        print(f"📊 挂单概览:")
        print(f"  总挂单数: {total_orders}")
        print(f"  买单: {len(buy_orders)}")
        print(f"  卖单: {len(sell_orders)}")
        
        print("\n📈 订单类型分布:")
        for order_type, count in sorted(order_types.items(), key=lambda x: x[1], reverse=True):
            print(f"  {order_type}: {count}")
        
        print("\n💱 交易对分布:")
        for symbol, count in sorted(symbols.items(), key=lambda x: x[1], reverse=True):
            print(f"  {symbol}: {count}")
        
        # 计算总价值
        total_value = Decimal('0')
        for order in orders:
            price = order['price']
            qty = order['origQty']
            if price > 0:  # 排除市价单
                total_value += price * qty
        
        print(f"\n💰 挂单总价值: {total_value:.2f} USDT")
        
        # 显示最近的5个订单
        print("\n🕐 最近的5个订单:")
        recent_orders = sorted(orders, key=lambda x: x['time'], reverse=True)[:5]
        for order in recent_orders:
            order_time = datetime.fromtimestamp(order['time'] / 1000)
            print(f"  {order['symbol']} - {order['side']} {order['type']} @ {order['price']} - {order_time.strftime('%H:%M:%S')}")
    
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    finally:
        # 断开连接
        await exchange.disconnect()


async def main():
    """运行所有示例"""
    print("\n🚀 币安合约挂单查询示例\n")
    
    # 运行示例1: 查询所有挂单
    await example_get_all_orders()
    
    # 运行示例2: 查询特定交易对的挂单
    await example_get_specific_symbol_orders()
    
    # 运行示例3: 挂单统计分析
    await example_analyze_orders()
    
    print("\n✅ 所有示例运行完成!")


if __name__ == "__main__":
    asyncio.run(main())

