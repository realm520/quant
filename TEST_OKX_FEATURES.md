# OKX功能测试指南

## ✅ 已实现的功能

OKX永续合约交易所已实现以下功能：

1. ✅ **查询余额** - `get_balance()`
2. ✅ **查询仓位** - `get_positions(symbol=None)`
3. ✅ **查询挂单** - `get_open_orders(symbol=None)`

## 🚀 快速测试

### 前提条件

```bash
# 1. 激活虚拟环境
source .venv/bin/activate

# 2. 设置OKX API凭证（如果还没设置）
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_api_secret"
export OKX_PASSPHRASE="your_passphrase"

# 3. 验证环境变量
env | grep OKX
```

### 测试1：查询余额

```bash
# 表格格式
cextools account balance -x okx -e perp

# JSON格式
cextools account balance -x okx -e perp -o json

# 调试模式
cextools account balance -x okx -e perp --debug
```

**预期输出**：
```
Account Balance
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Currency ┃ Available      ┃ Frozen       ┃ Total        ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ USDT     │ 9500.30000000  │ 500.20000000 │ 10000.50000000│
└──────────┴────────────────┴──────────────┴──────────────┘
```

### 测试2：查询仓位

```bash
# 查询所有仓位
cextools account positions -x okx -e perp

# 查询特定合约仓位（注意OKX格式）
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP

# JSON格式
cextools account positions -x okx -e perp -o json

# CSV格式
cextools account positions -x okx -e perp -o csv
```

**预期输出**：
```
Positions
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃ Exchange┃ Symbol         ┃ Side ┃ Quantity ┃ Entry Price┃ Current Price┃ Liquidation Price┃ PnL    ┃ ROE    ┃ Leverage ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ okx_perp│ BTC-USDT-SWAP  │ Long │ 0.100000 │ 50000.00   │ 51000.00     │ 45000.00         │ +100.00│ +2.00% │ 10x      │
└─────────┴────────────────┴──────┴──────────┴────────────┴──────────────┴──────────────────┴────────┴────────┴──────────┘
```

### 测试3：查询挂单

```bash
# 查询所有挂单
cextools account orders -x okx -e perp

# 查询特定合约挂单
cextools account orders -x okx -e perp --symbol ETH-USDT-SWAP

# JSON格式
cextools account orders -x okx -e perp -o json

# CSV格式
cextools account orders -x okx -e perp -o csv
```

**预期输出**：
```
Open Orders
┏━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Exchange┃ Symbol         ┃ Order ID ┃ Side ┃ Type  ┃ Price    ┃ Quantity ┃ Filled      ┃ Status ┃ Time              ┃
┡━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ okx_perp│ BTC-USDT-SWAP  │ 12345678 │ BUY  │ limit │ 50000.00 │ 0.001000 │ 0.00 (0.0%) │ live   │ 2025-10-17 10:30:00│
└─────────┴────────────────┴──────────┴──────┴───────┴──────────┴──────────┴─────────────┴────────┴───────────────────┘
```

## 🐛 如果遇到401错误

### 原因：环境变量未设置

从您的终端输出看，环境变量可能未设置。请按以下步骤操作：

```bash
# 1. 设置环境变量（请替换为您的真实凭证）
export OKX_API_KEY="your_api_key_here"
export OKX_API_SECRET="your_api_secret_here"
export OKX_PASSPHRASE="your_passphrase_here"

# 2. 验证设置成功
env | grep OKX
# 应该看到3行输出

# 3. 运行测试脚本
python scripts/test_okx_connection.py

# 4. 如果测试通过，开始使用
cextools account balance -x okx -e perp
```

### 获取OKX API凭证

如果您还没有OKX API：

1. 登录 https://www.okx.com
2. 进入 **个人中心** → **API管理**
3. 点击 **创建V5 API Key**
4. 设置权限：
   - ✅ 读取
   - ⏸️ 交易（可选）
   - ❌ 提币（不要勾选）
5. **设置Passphrase**（重要！自己设置一个密码）
6. 记录三个凭证：API Key、Secret Key、Passphrase

详细步骤请参考：`docs/okx-setup-guide.md`

## 📊 完整功能验证

### 使用Python API测试

创建 `test_okx_all.py`：

```python
import asyncio
import os
from tri_arb.exchanges.okx_perp import OKXPerpExchange

async def test_all_features():
    """测试所有OKX功能"""
    
    exchange = OKXPerpExchange(
        api_key=os.getenv("OKX_API_KEY"),
        api_secret=os.getenv("OKX_API_SECRET"),
        passphrase=os.getenv("OKX_PASSPHRASE")
    )
    
    await exchange.connect()
    print("✅ 已连接到OKX")
    
    try:
        # 测试1：查询余额
        print("\n测试1: 查询余额...")
        balances = await exchange.get_balance()
        print(f"✅ 找到 {len(balances)} 种资产")
        
        # 测试2：查询仓位
        print("\n测试2: 查询仓位...")
        positions = await exchange.get_positions()
        print(f"✅ 找到 {len(positions)} 个仓位")
        
        # 测试3：查询挂单
        print("\n测试3: 查询挂单...")
        orders = await exchange.get_open_orders()
        print(f"✅ 找到 {len(orders)} 个挂单")
        
        print("\n🎉 所有功能测试通过！")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await exchange.disconnect()
        print("\n👋 已断开连接")

asyncio.run(test_all_features())
```

运行：
```bash
source .venv/bin/activate
python test_okx_all.py
```

## 📋 功能清单

| 功能 | 方法 | CLI命令 | 状态 |
|------|------|---------|------|
| 查询余额 | `get_balance()` | `cextools account balance -x okx -e perp` | ✅ |
| 查询仓位 | `get_positions(symbol)` | `cextools account positions -x okx -e perp` | ✅ |
| 查询挂单 | `get_open_orders(symbol)` | `cextools account orders -x okx -e perp` | ✅ |

## 📚 相关文档

- [OKX实现文档](docs/okx-implementation.md)
- [OKX快速开始](docs/okx-quickstart.md)
- [OKX配置指南](docs/okx-setup-guide.md)
- [OKX问题排查](docs/okx-troubleshooting.md)
- [调试日志指南](docs/debug-logging.md)

## 🎊 总结

OKX的查询功能已经**完整实现并可用**！

如果遇到401错误，最常见的原因是：
1. ❌ 环境变量未设置 → 运行上面的 export 命令
2. ❌ Passphrase错误 → 使用创建API时设置的密码（不是登录密码）
3. ❌ API权限不足 → 确保开启了"读取"权限

运行测试脚本进行诊断：
```bash
python scripts/test_okx_connection.py
```

---

**状态**：✅ 功能完整，已可使用  
**测试日期**：2025-10-17

