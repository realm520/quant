# OKX WebSocket连接故障排查指南

## 🚨 常见错误

### 错误1：Invalid timestamp (错误代码: 60004)

**错误信息**：
```
OKX WebSocket login failed: Invalid timestamp
code: 60004
```

**原因**：
1. 系统时间与OKX服务器时间差异过大（>30秒）
2. 时间戳格式不正确
3. 时区设置错误

**解决方法**：

#### 步骤1：检查时间同步

```bash
# 使用我们的工具检查
python scripts/check_okx_time.py

# 应该看到：
# ✅ 时间同步良好 (差异 < 5秒)
```

#### 步骤2：同步系统时间

**Linux/WSL：**
```bash
# 方法1：使用ntpdate
sudo apt install ntpdate
sudo ntpdate pool.ntp.org

# 方法2：使用systemd-timesyncd
sudo timedatectl set-ntp true
sudo systemctl restart systemd-timesyncd

# 验证
timedatectl status
```

**macOS：**
```bash
# 系统偏好设置 → 日期与时间 → 启用"自动设置日期和时间"

# 或命令行
sudo sntp -sS time.apple.com
```

**Windows：**
```
设置 → 时间和语言 → 自动设置时间 (开启)
```

#### 步骤3：再次测试

```bash
# 再次运行时间检测
python scripts/check_okx_time.py

# 启动WebSocket订阅
cextools subscribe user-stream -x okx --output table --debug
```

### 错误2：Invalid sign (错误代码: 50113)

**错误信息**：
```
OKX WebSocket login failed: Invalid sign
code: 50113
```

**原因**：
1. API Key或Secret错误
2. Passphrase错误
3. 签名计算错误

**解决方法**：

#### 步骤1：检查API凭证

```bash
# 查看环境变量
echo "API Key: $OKX_API_KEY"
echo "Passphrase: $OKX_PASSPHRASE"

# API Secret不要直接打印（安全考虑）
echo "API Secret length: ${#OKX_API_SECRET}"
```

#### 步骤2：验证API权限

登录OKX网站，检查API权限：
- ✅ **读取** (Read) - 必需
- ❌ **交易** (Trade) - 订阅不需要，但建议启用
- ❌ **提币** (Withdraw) - 不需要

#### 步骤3：测试API连接

```bash
# 使用测试脚本
python scripts/test_okx_connection.py
```

### 错误3：Websocket connection failed

**错误信息**：
```
Failed to connect to wss://ws.okx.com:8443/ws/v5/private
```

**原因**：
1. 网络连接问题
2. 防火墙阻止
3. 代理设置

**解决方法**：

```bash
# 测试OKX API连接
curl https://www.okx.com/api/v5/public/time

# 测试WebSocket连接（使用websocat工具）
# sudo apt install websocat
websocat wss://ws.okx.com:8443/ws/v5/public

# 检查防火墙
sudo ufw status
```

## 🔍 调试步骤

### 启用详细日志

```bash
# 启用调试模式
cextools subscribe user-stream -x okx --output json --debug

# 查看日志文件
tail -f logs/tri-arb.log
```

### 查看完整错误信息

调试模式会显示：
- 发送的时间戳
- API Key（部分）
- 签名消息构成
- 服务器响应

### 手动测试认证

创建测试脚本 `test_okx_auth.py`：

```python
import time
import base64
import hmac
import hashlib
from datetime import datetime

# 配置
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
PASSPHRASE = "your_passphrase"

# 生成时间戳
timestamp = datetime.utcfromtimestamp(time.time()).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
print(f"Timestamp: {timestamp}")

# 生成签名
method = 'GET'
request_path = '/users/self/verify'
message = timestamp + method + request_path
print(f"Message: {message}")

# 计算签名
mac = hmac.new(
    API_SECRET.encode('utf-8'),
    message.encode('utf-8'),
    hashlib.sha256
)
signature = base64.b64encode(mac.digest()).decode('utf-8')
print(f"Signature: {signature}")

# 构造登录消息
login_msg = {
    "op": "login",
    "args": [{
        "apiKey": API_KEY,
        "passphrase": PASSPHRASE,
        "timestamp": timestamp,
        "sign": signature
    }]
}
print(f"\nLogin message:")
import json
print(json.dumps(login_msg, indent=2))
```

## 📋 检查清单

使用前请确认：

- [ ] 系统时间已同步（运行 `python scripts/check_okx_time.py`）
- [ ] 时间差 < 5秒
- [ ] OKX_API_KEY 已设置
- [ ] OKX_API_SECRET 已设置
- [ ] OKX_PASSPHRASE 已设置
- [ ] API权限包含"读取"
- [ ] PostgreSQL已启动
- [ ] DATABASE_URL已配置
- [ ] 数据库表已创建（首次运行使用 `--create-tables`）
- [ ] 网络可以访问 ws.okx.com

## 🛠️ 快速诊断脚本

创建 `diagnose_okx.sh`：

```bash
#!/bin/bash

echo "OKX WebSocket 诊断工具"
echo "====================="
echo

# 检查时间
echo "1. 检查时间同步..."
python scripts/check_okx_time.py | grep "时间差"

# 检查环境变量
echo
echo "2. 检查环境变量..."
[ -z "$OKX_API_KEY" ] && echo "❌ OKX_API_KEY 未设置" || echo "✅ OKX_API_KEY 已设置"
[ -z "$OKX_API_SECRET" ] && echo "❌ OKX_API_SECRET 未设置" || echo "✅ OKX_API_SECRET 已设置"
[ -z "$OKX_PASSPHRASE" ] && echo "❌ OKX_PASSPHRASE 未设置" || echo "✅ OKX_PASSPHRASE 已设置"
[ -z "$DATABASE_URL" ] && echo "❌ DATABASE_URL 未设置" || echo "✅ DATABASE_URL 已设置"

# 检查网络
echo
echo "3. 检查网络连接..."
curl -s -o /dev/null -w "%{http_code}" https://www.okx.com/api/v5/public/time | \
  grep -q "200" && echo "✅ 可以访问OKX API" || echo "❌ 无法访问OKX API"

# 检查数据库
echo
echo "4. 检查数据库..."
psql -U postgres -d trading -c "SELECT 1" > /dev/null 2>&1 && \
  echo "✅ 数据库连接正常" || echo "❌ 数据库连接失败"

echo
echo "诊断完成"
```

## 💡 最佳实践

### 1. 使用NTP自动同步

**Linux：**
```bash
# 安装并启用chrony（推荐）
sudo apt install chrony
sudo systemctl enable chrony
sudo systemctl start chrony

# 查看同步状态
chronyc tracking
```

### 2. 使用环境变量文件

```bash
# 创建 .env.okx
cat > .env.okx << 'EOF'
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_PASSPHRASE="your_passphrase"
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
EOF

# 加载
source .env.okx

# 启动订阅
cextools subscribe user-stream -x okx
```

### 3. 监控日志

```bash
# 实时查看日志
tail -f logs/tri-arb.log | grep -i "okx"

# 只看错误
tail -f logs/tri-arb.log | grep -i "error"
```

## 📞 获取帮助

如果问题仍未解决：

1. **查看日志**：`logs/tri-arb.log`
2. **启用调试**：`--debug` 参数
3. **检查文档**：
   - [OKX WebSocket指南](OKX_WEBSOCKET_GUIDE.md)
   - [OKX API实现](okx-implementation.md)
4. **测试工具**：
   - `python scripts/check_okx_time.py` - 检查时间
   - `python scripts/test_okx_connection.py` - 测试API

## 🎯 成功示例

正确配置后的输出：

```
OKX用户数据流订阅服务
数据库: localhost:5432/trading
按 Ctrl+C 停止订阅

✅ 数据库表创建成功

✅ 服务已启动
正在连接WebSocket...

2025-10-21T06:58:40.123456Z [info] Connecting to OKX WebSocket
2025-10-21T06:58:40.234567Z [info] OKX WebSocket connected
2025-10-21T06:58:40.345678Z [info] OKX WebSocket login successful
2025-10-21T06:58:40.456789Z [info] Subscribed to OKX channels

╭─────────── 💰 OKX账户余额 - 06:58:41 ───────────╮
│ 币种 │ 可用余额   │ 冻结余额 │   权益    │
│ USDT │ 9500.0000 │ 500.0000│ 10000.0000│
╰────────────────────────────────────────────────────╯
```

---

**最后更新**：2025-10-21

