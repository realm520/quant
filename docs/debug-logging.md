# 调试日志输出指南

## 🔍 如何查看调试信息

### 方法1：使用 --debug 参数（最简单）

```bash
cextools account balance -x okx -e perp --debug
```

这会显示：
- ✅ 完整的错误堆栈
- ✅ 异常详情
- ✅ 所有logger输出

**输出示例**：
```
2025-10-17T06:47:03.298711Z [info] Connected to OKX Perpetual Futures exchange
2025-10-17T06:47:03.350000Z [debug] OKX authentication timestamp=2025-10-17T06:47:03.349Z
2025-10-17T06:47:04.100000Z [error] OKX API error status_code=401
Traceback (most recent call last):
  ...
```

### 方法2：查看日志文件

项目默认会将日志写入文件：

```bash
# 查看所有日志
tail -f logs/tri-arb.log

# 查看错误日志
tail -f logs/tri-arb-errors.log

# 实时监控（在另一个终端运行）
tail -f logs/tri-arb.log &
cextools account balance -x okx -e perp
```

### 方法3：查看OKX API响应详情

现在OKX实现已经添加了详细的日志记录，运行命令后会自动记录：

```bash
# 运行命令
cextools account balance -x okx -e perp

# 查看日志（会显示响应状态码和内容）
grep "OKX API" logs/tri-arb.log | tail -20
```

### 方法4：使用 Python 脚本直接打印

创建测试脚本 `test_okx_debug.py`：

```python
import asyncio
import os
from tri_arb.exchanges.okx_perp import OKXPerpExchange

async def test():
    exchange = OKXPerpExchange(
        api_key=os.getenv("OKX_API_KEY"),
        api_secret=os.getenv("OKX_API_SECRET"),
        passphrase=os.getenv("OKX_PASSPHRASE")
    )
    
    await exchange.connect()
    
    try:
        balances = await exchange.get_balance()
        print("✅ 成功！余额数据：")
        print(balances)
    except Exception as e:
        print(f"❌ 错误：{e}")
        import traceback
        traceback.print_exc()
    
    await exchange.disconnect()

asyncio.run(test())
```

运行：
```bash
source .venv/bin/activate
python test_okx_debug.py
```

## 🔍 查看OKX具体错误信息

### 当前实现已自动记录以下信息：

1. **请求信息**：
   - 时间戳
   - 请求路径
   - 签名消息
   - API Key前缀

2. **响应信息**：
   - 状态码
   - URL
   - 响应内容长度

3. **错误详情**（401时）：
   - 状态码
   - 响应body（前500字符）
   - 请求headers（隐藏签名）

### 查看日志示例

```bash
# 运行命令
cextools account balance -x okx -e perp

# 查看完整日志
cat logs/tri-arb.log

# 查看最近的OKX相关日志
grep -A 5 "OKX" logs/tri-arb.log | tail -30
```

## 🐛 OKX 401错误调试

如果遇到401错误，日志会显示：

```
[info] OKX authentication timestamp=2025-10-17T06:47:03.349Z request_path=/api/v5/account/balance method=GET
[info] OKX API response status_code=401 url=https://www.okx.com/api/v5/account/balance
[error] OKX API error status_code=401 response_body={"code":"50113","msg":"Invalid sign"}
```

从日志中可以看出：
- 时间戳格式
- 请求路径
- OKX返回的具体错误码和消息

### OKX常见错误码

| 错误码 | 含义 | 解决方法 |
|-------|------|---------|
| 50113 | Invalid sign | 签名错误，检查Secret Key |
| 50111 | Invalid OK-ACCESS-KEY | API Key错误 |
| 50112 | Invalid OK-ACCESS-PASSPHRASE | Passphrase错误 |
| 50114 | Invalid OK-ACCESS-TIMESTAMP | 时间戳格式错误 |

## 💡 调试技巧

### 1. 启用httpx日志

如果需要查看HTTP请求详情：

```python
import logging
import httpx

# 启用httpx调试日志
logging.basicConfig(level=logging.DEBUG)
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.DEBUG)
```

### 2. 手动测试签名

使用测试脚本查看签名生成过程：

```bash
python scripts/test_okx_connection.py
```

会显示：
```
签名信息:
  Timestamp: 2025-10-17T06:47:03.349Z
  Method: GET
  Request Path: /api/v5/account/balance
  Message: 2025-10-17T06:47:03.349ZGET/api/v5/account/balance
  Signature: xY7Km5Nq...
```

### 3. 对比正确的签名

创建 `verify_signature.py`：

```python
import hmac
import hashlib
import base64
from datetime import datetime

# 你的凭证
api_secret = "your_secret"

# 固定的测试数据
timestamp = "2025-10-17T06:47:03.349Z"
method = "GET"
request_path = "/api/v5/account/balance"
body = ""

# 生成签名
message = timestamp + method + request_path + body
print(f"签名消息: {message}")

mac = hmac.new(
    api_secret.encode('utf-8'),
    message.encode('utf-8'),
    hashlib.sha256
)
signature = base64.b64encode(mac.digest()).decode()
print(f"签名结果: {signature}")
```

## 📋 调试检查清单

遇到401错误时，按顺序检查：

- [ ] 环境变量已设置：`env | grep OKX`
- [ ] Passphrase是创建API时设置的密码（不是登录密码）
- [ ] API状态为"已启用"
- [ ] API权限包含"读取"
- [ ] IP在白名单内（如果设置了IP限制）
- [ ] Secret Key正确（创建API时只显示一次）
- [ ] 查看日志文件：`cat logs/tri-arb.log`
- [ ] 运行测试脚本：`python scripts/test_okx_connection.py`

## 🚀 推荐的调试流程

```bash
# 1. 运行测试脚本（会显示详细的签名信息）
source .venv/bin/activate
python scripts/test_okx_connection.py

# 2. 如果测试脚本失败，查看环境变量
env | grep OKX

# 3. 使用debug模式运行CLI
cextools account balance -x okx -e perp --debug

# 4. 查看日志文件
cat logs/tri-arb.log | grep -A 5 "OKX API error"

# 5. 如果是Passphrase问题，重新创建API
# （最常见的解决方案）
```

## 📚 相关文档

- [OKX配置指南](okx-setup-guide.md) - 详细的配置步骤
- [OKX问题排查](okx-troubleshooting.md) - 常见问题解决
- [OKX快速开始](okx-quickstart.md) - 快速上手

---

**最后更新**：2025-10-17
