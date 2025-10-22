#!/usr/bin/env python3
"""测试Gate.io API连接和认证

用于验证Gate.io API凭证和签名是否正确。
"""

import asyncio
import hashlib
import hmac
import os
import time


async def test_gate_connection():
    """测试Gate.io连接."""
    print("=" * 60)
    print("  Gate.io API连接测试")
    print("=" * 60)
    print()
    
    # 获取API凭证
    api_key = os.getenv("GATE_API_KEY", "")
    api_secret = os.getenv("GATE_API_SECRET", "")
    
    if not api_key or not api_secret:
        print("❌ 错误: 未设置GATE_API_KEY或GATE_API_SECRET")
        print("\n请设置环境变量:")
        print("  export GATE_API_KEY='your_key'")
        print("  export GATE_API_SECRET='your_secret'")
        return
    
    print(f"API Key: {api_key[:10]}...")
    print(f"API Secret: {api_secret[:10]}...")
    print()
    
    # 生成签名（查询余额）
    method = "GET"
    url_path = "/api/v4/futures/usdt/accounts"
    query_string = ""
    body_string = ""
    timestamp = str(int(time.time()))
    
    print("签名信息:")
    print(f"  Method: {method}")
    print(f"  Path: {url_path}")
    print(f"  Query: {query_string}")
    print(f"  Body: {body_string}")
    print(f"  Timestamp: {timestamp}")
    print()
    
    # 计算body hash
    body_hash = hashlib.sha512(body_string.encode()).hexdigest()
    print(f"  Body Hash: {body_hash}")
    
    # 构造签名字符串
    sign_string = f"{method}\n{url_path}\n{query_string}\n{body_hash}\n{timestamp}"
    print(f"  Sign String: {repr(sign_string[:100])}")
    print()
    
    # 生成签名
    signature = hmac.new(
        api_secret.encode('utf-8'),
        sign_string.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()
    
    print(f"  Signature: {signature[:40]}...")
    print()
    
    # 测试API请求
    print("测试API请求...")
    
    import httpx
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "KEY": api_key,
        "Timestamp": timestamp,
        "SIGN": signature,
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.gateio.ws{url_path}",
                headers=headers,
                timeout=10.0
            )
            
            print(f"Response Status: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")
            print(f"Response: {response.text[:500]}")
            print()
            
            if response.status_code == 200:
                print("✅ 连接成功！")
                data = response.json()
                print(f"账户数据: {data}")
            else:
                print(f"❌ 连接失败: {response.status_code}")
                print(f"错误信息: {response.text}")
                
                # 提示可能的问题
                print("\n可能的问题:")
                print("  1. API Key或Secret错误")
                print("  2. 签名格式不对")
                print("  3. API权限不足（需要'读取'权限）")
                print("  4. IP未加入白名单")
                
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_gate_connection())

