#!/usr/bin/env python3
"""OKX API 连接测试脚本

用于测试OKX API凭证是否正确配置。
"""

import asyncio
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tri_arb.exchanges.okx_perp import OKXPerpExchange


async def test_connection():
    """测试OKX API连接"""
    
    print("=" * 60)
    print("OKX API 连接测试")
    print("=" * 60)
    
    # 读取环境变量
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    
    print("\n1. 检查环境变量...")
    
    if not api_key:
        print("❌ OKX_API_KEY 未设置")
        print("   请运行: export OKX_API_KEY='your_api_key'")
        return False
    else:
        print(f"✅ OKX_API_KEY: {api_key[:8]}...{api_key[-4:]}")
    
    if not api_secret:
        print("❌ OKX_API_SECRET 未设置")
        print("   请运行: export OKX_API_SECRET='your_api_secret'")
        return False
    else:
        print(f"✅ OKX_API_SECRET: {api_secret[:8]}...***")
    
    if not passphrase:
        print("❌ OKX_PASSPHRASE 未设置")
        print("   请运行: export OKX_PASSPHRASE='your_passphrase'")
        return False
    else:
        print(f"✅ OKX_PASSPHRASE: {passphrase[:2]}***")
    
    print("\n2. 创建交易所实例...")
    exchange = OKXPerpExchange(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase
    )
    print("✅ 实例创建成功")
    
    print("\n3. 连接交易所...")
    try:
        await exchange.connect()
        print("✅ 连接成功")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
    
    print("\n4. 测试余额查询...")
    try:
        balances = await exchange.get_balance()
        print(f"✅ 余额查询成功！")
        print(f"   找到 {len(balances)} 种资产")
        if balances:
            print("   资产列表:", ", ".join(list(balances.keys())[:5]))
        return True
    except Exception as e:
        print(f"❌ 余额查询失败: {e}")
        print("\n可能的原因：")
        print("  1. Passphrase 错误（最常见）")
        print("     -> 确认使用的是创建API时设置的密码")
        print("  2. API Key 或 Secret 错误")
        print("     -> 在OKX后台重新确认")
        print("  3. IP限制")
        print("     -> 添加当前IP到白名单")
        print("  4. API权限不足")
        print("     -> 确保开启了'读取'权限")
        return False
    finally:
        await exchange.disconnect()
        print("\n5. 断开连接")
        print("✅ 已断开")


async def test_detailed():
    """详细测试，显示签名信息"""
    
    print("\n" + "=" * 60)
    print("详细签名测试")
    print("=" * 60)
    
    api_key = os.getenv("OKX_API_KEY", "")
    api_secret = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    
    if not all([api_key, api_secret, passphrase]):
        print("❌ 环境变量未完全设置")
        return
    
    from datetime import datetime
    import hmac
    import hashlib
    import base64
    
    # 生成时间戳
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    method = "GET"
    request_path = "/api/v5/account/balance"
    body = ""
    
    # 生成签名
    message = timestamp + method + request_path + body
    mac = hmac.new(
        api_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    )
    signature = base64.b64encode(mac.digest()).decode()
    
    print("\n签名信息:")
    print(f"  Timestamp: {timestamp}")
    print(f"  Method: {method}")
    print(f"  Request Path: {request_path}")
    print(f"  Body: (empty)")
    print(f"  Message: {message}")
    print(f"  Signature: {signature[:20]}...")
    
    print("\n请求头:")
    print(f"  OK-ACCESS-KEY: {api_key[:8]}...{api_key[-4:]}")
    print(f"  OK-ACCESS-SIGN: {signature[:20]}...")
    print(f"  OK-ACCESS-TIMESTAMP: {timestamp}")
    print(f"  OK-ACCESS-PASSPHRASE: {passphrase[:2]}***")
    
    print("\n注意事项:")
    print("  1. Passphrase 是明文发送，不需要加密")
    print("  2. Timestamp 必须是 ISO 8601 格式")
    print("  3. 签名消息不包含任何空格")
    print("  4. Secret Key 用于 HMAC-SHA256")


async def main():
    """运行所有测试"""
    
    # 基础连接测试
    success = await test_connection()
    
    if not success:
        # 如果失败，显示详细签名信息
        await test_detailed()
        print("\n" + "=" * 60)
        print("❌ 测试失败")
        print("=" * 60)
        print("\n请按照上述提示检查配置，或参考文档:")
        print("  docs/okx-troubleshooting.md")
        print("  docs/okx-quickstart.md")
        sys.exit(1)
    else:
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print("\n你的OKX API配置正确，可以开始使用了！")
        print("\n常用命令:")
        print("  cextools account balance -x okx -e perp")
        print("  cextools account positions -x okx -e perp")
        print("  cextools account orders -x okx -e perp")


if __name__ == "__main__":
    asyncio.run(main())

