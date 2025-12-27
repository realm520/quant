#!/usr/bin/env python3
"""检查 XT 交易对的合约乘数配置"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import httpx
from decimal import Decimal

# 要检查的交易对
symbols_to_check = ["mon_usdt", "rave_usdt", "iota_usdt", "tradoor_usdt", "fhe_usdt"]


def check_xt_contract_multipliers():
    """检查 XT 交易对的合约乘数配置"""
    try:
        # 初始化同步 HTTP 客户端
        client = httpx.Client(
            base_url="https://fapi.xt.com",
            timeout=httpx.Timeout(10.0, connect=5.0),
        )

        # 调用批量获取 API
        print("正在从 XT API 获取交易对配置...")
        response = client.get("/future/market/v3/public/symbol/list")
        response.raise_for_status()
        data = response.json()

        # 检查返回码
        if data.get("returnCode") != 0:
            error_msg = data.get("msgInfo", "Unknown error")
            print(f"❌ XT API 返回错误: {error_msg}")
            return

        # 解析所有交易对的配置
        symbols = data.get("result", [])

        if not isinstance(symbols, list):
            print(f"❌ XT API 返回的 result 不是列表类型")
            return

        print(f"✅ 成功获取 {len(symbols)} 个交易对的配置\n")

        # 构建交易对配置字典
        symbol_configs = {}
        for symbol_config in symbols:
            if not isinstance(symbol_config, dict):
                continue

            symbol = symbol_config.get("symbol", "").lower()
            contract_size = symbol_config.get("contractSize")

            if symbol and contract_size is not None:
                try:
                    multiplier = Decimal(str(contract_size))
                    if multiplier > 0:
                        symbol_configs[symbol] = multiplier
                except (ValueError, TypeError):
                    pass

        # 检查目标交易对
        print("检查目标交易对的合约乘数：")
        print("-" * 60)
        for symbol in symbols_to_check:
            normalized = symbol.lower().replace("/", "_").replace("-", "_")
            if normalized in symbol_configs:
                multiplier = symbol_configs[normalized]
                print(f"✅ {symbol:20s} -> {multiplier}")
            else:
                print(f"❌ {symbol:20s} -> 未找到（使用默认值 1）")

        print("\n" + "-" * 60)
        print(f"总共找到 {len(symbol_configs)} 个交易对的配置")

        # 显示一些示例
        print("\n示例交易对配置（前10个）：")
        count = 0
        for symbol, multiplier in symbol_configs.items():
            if count >= 10:
                break
            print(f"  {symbol:20s} -> {multiplier}")
            count += 1

    except httpx.HTTPError as e:
        print(f"❌ HTTP 错误: {e}")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    check_xt_contract_multipliers()
