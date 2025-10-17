# 调试输出快速参考

## 🔍 查看调试信息的4种方法

### 1️⃣ 使用 --debug 参数（最简单）✨

```bash
cextools account balance -x okx -e perp --debug
```

**会显示**：
- ✅ 完整的错误堆栈
- ✅ 所有logger输出
- ✅ 异常详情

---

### 2️⃣ 查看日志文件

```bash
# 实时查看所有日志
tail -f logs/tri-arb.log

# 查看错误日志
tail -f logs/tri-arb-errors.log

# 查看最近的OKX日志
grep "OKX" logs/tri-arb.log | tail -20
```

---

### 3️⃣ 运行测试脚本

```bash
source .venv/bin/activate
python scripts/test_okx_connection.py
```

**会显示**：
- 环境变量检查
- 签名生成过程
- API测试结果
- 详细错误诊断

---

### 4️⃣ 使用 Python 脚本直接打印

创建 `test_debug.py`：

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
        print("正在查询余额...")
        balances = await exchange.get_balance()
        print(f"✅ 成功！找到 {len(balances)} 种资产")
        for currency, data in balances.items():
            print(f"  {currency}: {data['total']}")
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
python test_debug.py
```

---

## 🎯 针对OKX 401错误

### 快速诊断

```bash
# 1. 检查环境变量
env | grep OKX

# 应该看到3行输出：
# OKX_API_KEY=...
# OKX_API_SECRET=...
# OKX_PASSPHRASE=...

# 2. 运行测试脚本
python scripts/test_okx_connection.py

# 3. 查看错误日志
cat logs/tri-arb.log | grep -A 5 "OKX API error"
```

### 最常见原因

**90% 的401错误都是因为 Passphrase 设置错误！**

```bash
# ❌ 错误：使用了账户登录密码
export OKX_PASSPHRASE="my_login_password"

# ✅ 正确：使用创建API时自己设置的密码
export OKX_PASSPHRASE="MyOKXAPIPassword2025"
```

**Passphrase** 是创建API时你自己输入的一个密码，**不是**OKX账户的登录密码！

---

## 📖 完整文档

详细信息请查看：
- [调试日志完整指南](docs/debug-logging.md)
- [OKX配置指南](docs/okx-setup-guide.md)
- [OKX问题排查](docs/okx-troubleshooting.md)

---

**快速链接**：在终端输入任一命令查看相应文档
```bash
cat docs/debug-logging.md       # 调试指南
cat docs/okx-setup-guide.md     # 配置指南
cat docs/okx-troubleshooting.md # 问题排查
```

