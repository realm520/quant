# OKX API 配置指南

## 📋 配置步骤

### 第一步：在OKX创建API

1. **登录OKX**
   - 访问 https://www.okx.com
   - 登录您的账户

2. **进入API管理**
   - 点击右上角头像
   - 选择 **API管理** 或 **API**
   - 点击 **创建V5 API Key**

3. **设置API权限**
   - ✅ **读取** - 必须勾选
   - ⏸️ **交易** - 可选（需要下单时才勾选）
   - ❌ **提币** - 不要勾选

4. **设置Passphrase**
   - 输入一个自定义密码（例如：`MyOKX2025Pass`）
   - **重要**：这个密码要记住！后面会用到
   - 这不是您的OKX登录密码，是API专用密码

5. **IP白名单（可选）**
   - 如果不设置，任何IP都可以使用（不安全）
   - 建议添加您的服务器IP
   - 获取IP：`curl ifconfig.me`

6. **记录凭证**
   创建成功后，您会看到：
   - **API Key**: 类似 `12345678-1234-1234-1234-123456789abc`
   - **Secret Key**: 一串长字符串
   - **Passphrase**: 刚才设置的密码

   ⚠️ **Secret Key 只显示一次，请立即保存！**

### 第二步：设置环境变量

#### 临时设置（当前终端会话有效）

```bash
export OKX_API_KEY="12345678-1234-1234-1234-123456789abc"
export OKX_API_SECRET="your_secret_key_here"
export OKX_PASSPHRASE="MyOKX2025Pass"
```

#### 永久设置（推荐）

**方法1：添加到 ~/.bashrc**

```bash
# 编辑 .bashrc
nano ~/.bashrc

# 在文件末尾添加：
export OKX_API_KEY="12345678-1234-1234-1234-123456789abc"
export OKX_API_SECRET="your_secret_key_here"
export OKX_PASSPHRASE="MyOKX2025Pass"

# 保存后重新加载
source ~/.bashrc
```

**方法2：使用 .env 文件**

```bash
# 创建 .env 文件
cat > /home/w_zy/crypto/xt/quant/.env << 'EOF'
# OKX API 凭证
OKX_API_KEY=12345678-1234-1234-1234-123456789abc
OKX_API_SECRET=your_secret_key_here
OKX_PASSPHRASE=MyOKX2025Pass
EOF

# 加载环境变量
source /home/w_zy/crypto/xt/quant/.env
```

⚠️ **重要**：不要将 .env 文件提交到git！

### 第三步：验证配置

```bash
# 检查环境变量是否设置成功
env | grep OKX

# 应该看到3行输出：
# OKX_API_KEY=...
# OKX_API_SECRET=...
# OKX_PASSPHRASE=...
```

### 第四步：测试连接

```bash
# 运行测试脚本
cd /home/w_zy/crypto/xt/quant
source .venv/bin/activate
python scripts/test_okx_connection.py
```

如果看到：
```
✅ 所有测试通过！
```

说明配置成功！

## 🔍 常见配置错误

### 1. Passphrase设置错误

```bash
# ❌ 错误：使用了账户密码
export OKX_PASSPHRASE="my_login_password"

# ✅ 正确：使用创建API时设置的密码
export OKX_PASSPHRASE="MyOKX2025Pass"
```

### 2. 环境变量名称错误

```bash
# ❌ 错误
export OKX_KEY="..."
export OKX_SECRET="..."

# ✅ 正确
export OKX_API_KEY="..."
export OKX_API_SECRET="..."
export OKX_PASSPHRASE="..."
```

### 3. 值包含多余空格

```bash
# ❌ 错误
export OKX_API_KEY=" abc123 "

# ✅ 正确
export OKX_API_KEY="abc123"
```

### 4. 引号使用错误

```bash
# ✅ 正确（推荐双引号）
export OKX_API_KEY="abc123"

# ✅ 也可以（单引号）
export OKX_API_KEY='abc123'

# ❌ 错误（没有引号，且有特殊字符）
export OKX_API_KEY=abc-123-def
```

## 📝 快速配置模板

复制并修改以下内容：

```bash
#!/bin/bash
# OKX API 配置脚本

# 替换为您的实际凭证
export OKX_API_KEY="在此粘贴您的API_KEY"
export OKX_API_SECRET="在此粘贴您的SECRET_KEY"  
export OKX_PASSPHRASE="在此粘贴您创建API时设置的密码"

echo "OKX API 凭证已设置"
echo "API Key: ${OKX_API_KEY:0:8}..."
echo "Secret: ${OKX_API_SECRET:0:8}..."
echo "Passphrase: ${OKX_PASSPHRASE:0:3}***"
```

保存为 `okx_config.sh`，然后：

```bash
# 修改文件内容
nano okx_config.sh

# 加载配置
source okx_config.sh

# 测试连接
python scripts/test_okx_connection.py
```

## 🎯 完整配置示例

### 示例1：使用真实凭证

假设您的OKX API凭证是：
- API Key: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- Secret Key: `1A2B3C4D5E6F7G8H9I0J`
- Passphrase: `MySecurePass2025`

配置命令：
```bash
export OKX_API_KEY="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
export OKX_API_SECRET="1A2B3C4D5E6F7G8H9I0J"
export OKX_PASSPHRASE="MySecurePass2025"
```

### 示例2：一键配置脚本

创建 `setup_okx.sh`：
```bash
#!/bin/bash

echo "请输入OKX API凭证："
read -p "API Key: " api_key
read -p "Secret Key: " api_secret
read -p "Passphrase: " passphrase

export OKX_API_KEY="$api_key"
export OKX_API_SECRET="$api_secret"
export OKX_PASSPHRASE="$passphrase"

echo ""
echo "✅ 环境变量已设置"
echo ""
echo "开始测试连接..."
python scripts/test_okx_connection.py
```

## 🆘 仍然遇到401错误？

如果设置了环境变量后仍然401，请检查：

### 1. Passphrase是否正确

```bash
# 显示当前设置
echo "当前Passphrase: $OKX_PASSPHRASE"

# 这应该是您创建API时自己设置的密码
# 不是账户登录密码！
```

### 2. 是否在正确的环境

OKX有两个环境：
- **实盘**：真实交易，用实盘API凭证
- **模拟盘**：模拟交易，用模拟盘API凭证

确保API凭证与环境匹配！

### 3. API是否已启用

登录OKX，检查：
- API状态为"已启用"
- API未过期
- API权限包含"读取"

### 4. 重新创建API

如果实在不确定，建议：
1. 删除旧的API Key
2. 重新创建API Key
3. 设置新的Passphrase（并记住它！）
4. 重新配置环境变量
5. 运行测试脚本

## ✅ 成功标志

当配置正确时，运行测试脚本会看到：

```
============================================================
OKX API 连接测试
============================================================

1. 检查环境变量...
✅ OKX_API_KEY: a1b2c3d4...7890
✅ OKX_API_SECRET: 1A2B3C4D...***
✅ OKX_PASSPHRASE: My***

2. 创建交易所实例...
✅ 实例创建成功

3. 连接交易所...
✅ 连接成功

4. 测试余额查询...
✅ 余额查询成功！
   找到 3 种资产
   资产列表: USDT, BTC, ETH

5. 断开连接
✅ 已断开

============================================================
✅ 所有测试通过！
============================================================
```

## 📚 相关文档

- [OKX快速开始](okx-quickstart.md)
- [OKX问题排查](okx-troubleshooting.md)
- [OKX实现文档](okx-implementation.md)

---

**提示**：90%的401错误都是因为Passphrase设置错误。请确保使用创建API时自己设置的密码！

**最后更新**：2025-10-17

