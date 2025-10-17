# OKX 连接问题排查指南

## 🐛 常见错误及解决方案

### 1. 401 Unauthorized - 签名错误

**错误信息**：
```
HTTP/1.1 401 Unauthorized
Client error '401 Unauthorized' for url 'https://www.okx.com/api/v5/account/balance'
```

**可能原因**：

#### A. Passphrase 错误
OKX的Passphrase是创建API时**你自己设置**的密码：

```bash
# ✅ 正确：使用创建API时设置的密码
export OKX_PASSPHRASE="MyCustomPassword123"

# ❌ 错误：使用账户登录密码
export OKX_PASSPHRASE="my_account_password"
```

**检查方法**：
```bash
echo $OKX_PASSPHRASE
# 应该显示你创建API时设置的passphrase
```

#### B. Secret Key 错误
```bash
# 检查Secret Key是否正确
echo $OKX_API_SECRET
# 应该是一个长字符串，通常包含字母和数字
```

#### C. API Key 错误
```bash
# 检查API Key
echo $OKX_API_KEY
# 应该是UUID格式，类似：12345678-1234-1234-1234-123456789abc
```

#### D. 环境变量未设置
```bash
# 检查所有环境变量
env | grep OKX

# 应该看到3行输出：
# OKX_API_KEY=...
# OKX_API_SECRET=...
# OKX_PASSPHRASE=...
```

### 2. 模拟盘 vs 实盘

OKX有模拟盘和实盘两个环境：

**实盘（默认）**：
- URL: `https://www.okx.com`
- 使用真实API凭证

**模拟盘**：
- URL: `https://www.okx.com`
- 需要在请求头添加：`x-simulated-trading: 1`
- 使用模拟盘API凭证

**解决方法**：
确保使用的API凭证与环境匹配：
- 实盘API凭证只能用于实盘
- 模拟盘API凭证只能用于模拟盘

### 3. IP 限制

**错误信息**：
```
IP access denied
```

**解决方法**：
1. 登录 OKX
2. 进入 API 管理
3. 添加当前 IP 到白名单，或删除 IP 限制

**获取当前IP**：
```bash
curl ifconfig.me
# 或
curl ipinfo.io/ip
```

### 4. API 权限不足

**错误信息**：
```
Permission denied
```

**解决方法**：
检查API权限设置：
- ✅ **读取**：必需（查询余额、持仓、订单）
- ⏸️ **交易**：可选（下单、撤单时需要）
- ❌ **提币**：不要开启

## 🔍 调试步骤

### 步骤1：验证环境变量

创建测试脚本 `test_okx_env.sh`：
```bash
#!/bin/bash
echo "=== OKX 环境变量检查 ==="
echo "API Key: ${OKX_API_KEY:0:8}..."
echo "Secret: ${OKX_API_SECRET:0:8}..."
echo "Passphrase: ${OKX_PASSPHRASE:0:3}***"
echo ""

if [ -z "$OKX_API_KEY" ]; then
    echo "❌ OKX_API_KEY 未设置"
else
    echo "✅ OKX_API_KEY 已设置"
fi

if [ -z "$OKX_API_SECRET" ]; then
    echo "❌ OKX_API_SECRET 未设置"
else
    echo "✅ OKX_API_SECRET 已设置"
fi

if [ -z "$OKX_PASSPHRASE" ]; then
    echo "❌ OKX_PASSPHRASE 未设置"
else
    echo "✅ OKX_PASSPHRASE 已设置"
fi
```

运行：
```bash
chmod +x test_okx_env.sh
./test_okx_env.sh
```

### 步骤2：启用调试模式

```bash
cextools account balance -x okx -e perp --debug
```

这会显示详细的请求信息，包括：
- 时间戳
- 请求路径
- 签名消息
- API Key前缀

### 步骤3：检查API凭证

登录OKX后台，确认：
1. API Key 状态为"启用"
2. API 权限包含"读取"
3. IP限制（如果有）包含当前IP
4. API未过期

### 步骤4：重新创建API

如果以上都确认无误，可能是API凭证损坏，建议：
1. 删除旧的API Key
2. 创建新的API Key
3. 重新设置 Passphrase（记住这个密码！）
4. 更新环境变量

## 📋 签名机制详解

OKX的签名机制：

### 签名消息格式
```
timestamp + method + request_path + body
```

**示例**：
```
2023-10-17T03:26:44.569Z + GET + /api/v5/account/balance + (空)
```

### 签名步骤
1. 拼接消息：`timestamp + method + request_path + body`
2. HMAC-SHA256加密（使用Secret Key）
3. Base64编码

### 请求头
```
OK-ACCESS-KEY: your_api_key
OK-ACCESS-SIGN: generated_signature
OK-ACCESS-TIMESTAMP: 2023-10-17T03:26:44.569Z
OK-ACCESS-PASSPHRASE: your_passphrase（明文）
Content-Type: application/json
```

## 🧪 手动测试签名

使用Python手动生成签名进行测试：

```python
import hmac
import hashlib
import base64
from datetime import datetime

# 你的API凭证
api_key = "your_api_key"
api_secret = "your_api_secret"
passphrase = "your_passphrase"

# 生成时间戳
timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
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

# 构造请求头
print("\n请求头:")
print(f"OK-ACCESS-KEY: {api_key}")
print(f"OK-ACCESS-SIGN: {signature}")
print(f"OK-ACCESS-TIMESTAMP: {timestamp}")
print(f"OK-ACCESS-PASSPHRASE: {passphrase}")
```

## 💡 常见陷阱

### 1. Passphrase 不是账户密码
```bash
# ❌ 错误
export OKX_PASSPHRASE="my_login_password"

# ✅ 正确
export OKX_PASSPHRASE="MyAPIPassword123"  # 创建API时自己设置的
```

### 2. 环境变量有空格或换行
```bash
# ❌ 错误（有额外空格）
export OKX_API_KEY=" abc123 "

# ✅ 正确
export OKX_API_KEY="abc123"
```

### 3. 时间戳格式
OKX要求ISO 8601格式：
```
2023-10-17T03:26:44.569Z
```

不是Unix时间戳：
```
1697512004569  # ❌ 错误
```

### 4. 请求路径必须包含查询参数
如果有查询参数，request_path 必须包含：
```python
# ✅ 正确
request_path = "/api/v5/account/positions?instType=SWAP"

# ❌ 错误
request_path = "/api/v5/account/positions"
```

## 🔧 快速修复

### 完全重置

如果一直无法解决，可以尝试完全重置：

```bash
# 1. 清除所有环境变量
unset OKX_API_KEY
unset OKX_API_SECRET
unset OKX_PASSPHRASE

# 2. 登录OKX，删除旧API，创建新API

# 3. 重新设置环境变量
export OKX_API_KEY="新的API_KEY"
export OKX_API_SECRET="新的API_SECRET"
export OKX_PASSPHRASE="新的PASSPHRASE"

# 4. 验证设置
env | grep OKX

# 5. 测试连接
cextools account balance -x okx -e perp --debug
```

## 📚 参考资料

- [OKX API认证文档](https://www.okx.com/docs-v5/zh/#overview-rest-authentication)
- [OKX账户API](https://www.okx.com/docs-v5/zh/#trading-account-rest-api)
- [OKX错误码](https://www.okx.com/docs-v5/zh/#error-code)

## 🆘 还是无法解决？

如果按照以上步骤仍无法解决，请检查：

1. **网络连接**：
   ```bash
   curl -I https://www.okx.com
   # 应该返回 200 OK
   ```

2. **OKX服务状态**：
   访问 [OKX状态页面](https://www.okx.com/status) 检查服务是否正常

3. **API版本**：
   确认使用的是 API v5（本实现使用v5）

4. **时区问题**：
   ```bash
   # 同步系统时间
   sudo ntpdate -s time.nist.gov
   ```

5. **查看完整错误**：
   ```bash
   cextools account balance -x okx -e perp --debug 2>&1 | tee okx_error.log
   ```
   然后查看 `okx_error.log` 文件

---

**提示**：最常见的问题是 Passphrase 设置错误。请确保使用的是创建API时自己设置的密码，而不是OKX账户的登录密码！

**最后更新**：2025-10-16

