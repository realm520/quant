#!/usr/bin/env python3
"""币安合约持仓查询示例

演示如何使用 BinancePerpExchange 查询持仓信息。

使用方法：
    1. 设置环境变量：
       export BINANCE_API_KEY="your_api_key"
       export BINANCE_API_SECRET="your_api_secret"
    
    2. 运行示例：
       python examples/binance_positions_example.py
"""

import asyncio
import os
from decimal import Decimal

from tri_arb.exchanges.binance_perp import BinancePerpExchange


async def example_get_all_positions():
    """示例1: 查询所有持仓"""
    print("=" * 60)
    print("示例1: 查询所有持仓")
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
        
        # 查询所有持仓
        positions = await exchange.get_positions()
        
        if not positions:
            print("📭 当前没有持仓")
        else:
            print(f"📊 共找到 {len(positions)} 个持仓:\n")
            
            for i, pos in enumerate(positions, 1):
                print(f"持仓 #{i}:")
                print(f"  交易对: {pos['symbol']}")
                print(f"  方向: {pos['positionSide']}")
                print(f"  数量: {pos['positionAmt']}")
                print(f"  开仓均价: {pos['entryPrice']}")
                print(f"  标记价格: {pos['markPrice']}")
                print(f"  盈亏平衡价: {pos['breakEvenPrice']}")
                print(f"  未实现盈亏: {pos['unRealizedProfit']} USDT")
                print(f"  强平价格: {pos['liquidationPrice']}")
                print(f"  杠杆倍数: {pos['leverage']}x")
                print(f"  保证金类型: {pos['marginType']}")
                print(f"  逐仓保证金: {pos['isolatedMargin']}")
                print(f"  名义价值: {pos['notional']}")
                print(f"  最大名义价值: {pos['maxNotionalValue']}")
                print(f"  更新时间: {pos['updateTime']}")
                print()
    
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    finally:
        # 断开连接
        await exchange.disconnect()
        print("👋 已断开连接")


async def example_get_specific_position():
    """示例2: 查询特定合约持仓"""
    print("\n" + "=" * 60)
    print("示例2: 查询特定合约持仓 (BTCUSDT)")
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
        
        # 查询特定合约持仓（注意：币安格式不带斜杠）
        symbol = "BTCUSDT"
        positions = await exchange.get_positions(symbol=symbol)
        
        if not positions:
            print(f"📭 {symbol} 没有持仓或挂单")
        else:
            print(f"📊 {symbol} 持仓信息:\n")
            
            for pos in positions:
                # V2 API 直接提供杠杆
                leverage = pos['leverage']
                unrealized_pnl = pos['unRealizedProfit']
                notional = abs(pos['notional'])
                
                # 计算收益率：保证金 = 名义价值 / 杠杆
                leverage_num = Decimal(leverage) if leverage else Decimal('1')
                margin = notional / leverage_num if leverage_num > 0 and notional > 0 else Decimal('0')
                roe = (unrealized_pnl / margin * 100) if margin > 0 else Decimal('0')
                
                print(f"  交易对: {pos['symbol']}")
                print(f"  持仓方向: {pos['positionSide']}")
                print(f"  持仓数量: {abs(pos['positionAmt'])}")
                print(f"  开仓均价: {pos['entryPrice']}")
                print(f"  当前标记价: {pos['markPrice']}")
                print(f"  未实现盈亏: {unrealized_pnl} USDT")
                print(f"  收益率(ROE): {roe:.2f}%")
                print(f"  杠杆: {leverage}x")
                print(f"  保证金类型: {pos['marginType']}")
                print(f"  名义价值: {notional} USDT")
                print()
    
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    finally:
        # 断开连接
        await exchange.disconnect()


async def example_compare_positions():
    """示例3: 对比显示持仓统计"""
    print("\n" + "=" * 60)
    print("示例3: 持仓统计")
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
        
        # 查询所有持仓
        positions = await exchange.get_positions()
        
        if not positions:
            print("📭 当前没有持仓")
            return
        
        # 统计数据
        total_unrealized_pnl = Decimal('0')
        total_margin = Decimal('0')
        long_positions = []
        short_positions = []
        
        for pos in positions:
            unrealized_pnl = pos['unRealizedProfit']
            notional = abs(pos['notional'])
            leverage = Decimal(pos['leverage']) if pos['leverage'] else Decimal('1')
            
            # 计算保证金：名义价值 / 杠杆
            margin = notional / leverage if leverage > 0 and notional > 0 else Decimal('0')
            
            total_unrealized_pnl += unrealized_pnl
            total_margin += margin
            
            # 按方向分类
            position_side = pos['positionSide']
            if position_side == "LONG" or (position_side == "BOTH" and pos['positionAmt'] > 0):
                long_positions.append(pos)
            elif position_side == "SHORT" or (position_side == "BOTH" and pos['positionAmt'] < 0):
                short_positions.append(pos)
        
        # 显示统计
        print(f"📊 持仓概览:")
        print(f"  总持仓数: {len(positions)}")
        print(f"  多头持仓: {len(long_positions)}")
        print(f"  空头持仓: {len(short_positions)}")
        print(f"  总未实现盈亏: {total_unrealized_pnl:.4f} USDT")
        print(f"  总保证金: {total_margin:.4f} USDT")
        
        if total_margin > 0:
            total_roe = (total_unrealized_pnl / total_margin * 100)
            print(f"  总收益率(ROE): {total_roe:.2f}%")
        
        # 显示盈利/亏损前三
        print("\n💰 盈利前3:")
        profitable = sorted(positions, key=lambda x: x['unRealizedProfit'], reverse=True)[:3]
        for pos in profitable:
            if pos['unRealizedProfit'] > 0:
                print(f"  {pos['symbol']}: +{pos['unRealizedProfit']:.4f} USDT")
        
        print("\n📉 亏损前3:")
        losing = sorted(positions, key=lambda x: x['unRealizedProfit'])[:3]
        for pos in losing:
            if pos['unRealizedProfit'] < 0:
                print(f"  {pos['symbol']}: {pos['unRealizedProfit']:.4f} USDT")
    
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    finally:
        # 断开连接
        await exchange.disconnect()


async def main():
    """运行所有示例"""
    print("\n🚀 币安合约持仓查询示例\n")
    
    # 运行示例1: 查询所有持仓
    await example_get_all_positions()
    
    # 运行示例2: 查询特定合约持仓
    await example_get_specific_position()
    
    # 运行示例3: 持仓统计
    await example_compare_positions()
    
    print("\n✅ 所有示例运行完成!")


if __name__ == "__main__":
    asyncio.run(main())

