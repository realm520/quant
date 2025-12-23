#!/usr/bin/env python3
"""
测试脚本：检查 XT API 返回的 symbol 格式，以及合约乘数查找逻辑
"""

import httpx
import json
from decimal import Decimal

def test_xt_api_symbol_format():
    """测试 XT API 返回的 symbol 格式"""
    print("=" * 80)
    print("测试 XT API 返回的 symbol 格式")
    print("=" * 80)
    
    try:
        client = httpx.Client(
            base_url="https://fapi.xt.com",
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        
        response = client.get("/future/market/v3/public/symbol/list")
        response.raise_for_status()
        data = response.json()
        
        if data.get("returnCode") != 0:
            print(f"API 返回错误: {data.get('msgInfo')}")
            return
        
        symbols = data.get("result", [])
        print(f"\n总共返回 {len(symbols)} 个交易对\n")
        
        # 查找我们关心的交易对
        target_symbols = ["mon_usdt", "rave_usdt", "iota_usdt", "tradoor_usdt", "fhe_usdt"]
        
        print("查找目标交易对:")
        print("-" * 80)
        
        found_symbols = {}
        for symbol_config in symbols:
            if not isinstance(symbol_config, dict):
                continue
            
            original_symbol = symbol_config.get("symbol", "")
            symbol_lower = original_symbol.lower()
            
            # 检查是否匹配目标交易对（考虑各种格式）
            for target in target_symbols:
                target_variants = [
                    target,
                    target.replace("_", "/"),
                    target.replace("_", "-"),
                    target.upper(),
                    target.upper().replace("_", "/"),
                    target.upper().replace("_", "-"),
                ]
                
                if symbol_lower in [v.lower() for v in target_variants]:
                    if target not in found_symbols:
                        found_symbols[target] = {
                            "original": original_symbol,
                            "lower": symbol_lower,
                            "contract_size": symbol_config.get("contractSize"),
                        }
        
        # 显示找到的交易对
        for target, info in found_symbols.items():
            print(f"\n目标: {target}")
            print(f"  API 返回的原始格式: {info['original']}")
            print(f"  小写格式: {info['lower']}")
            print(f"  合约乘数: {info['contract_size']}")
            
            # 测试查找逻辑
            normalized = info['lower'].replace("/", "_").replace("-", "_")
            print(f"  归一化后（查找用）: {normalized}")
            print(f"  存储时（只转小写）: {info['lower']}")
            print(f"  匹配: {'✓' if normalized == info['lower'] else '✗ 不匹配！'}")
        
        # 显示未找到的交易对
        not_found = set(target_symbols) - set(found_symbols.keys())
        if not_found:
            print(f"\n未找到的交易对: {', '.join(not_found)}")
        
        # 显示前10个交易对的格式示例
        print("\n" + "=" * 80)
        print("前10个交易对的格式示例:")
        print("-" * 80)
        for i, symbol_config in enumerate(symbols[:10]):
            if isinstance(symbol_config, dict):
                original = symbol_config.get("symbol", "")
                print(f"{i+1}. 原始: {original}, 小写: {original.lower()}, 归一化: {original.lower().replace('/', '_').replace('-', '_')}")
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_xt_api_symbol_format()
