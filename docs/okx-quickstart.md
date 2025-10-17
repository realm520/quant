# OKX 快速开始指南

## 🚀 快速上手

### 第一步：获取API凭证

1. 登录 [OKX交易所](https://www.okx.com)
2. 进入 **个人中心** → **API管理**
3. 点击 **创建API**
4. 设置API权限：
   - ✅ **读取** - 查询余额、持仓、订单
   - ⏸️ **交易** - 仅在需要下单时开启
   - ❌ **提币** - 不要开启
5. 设置 **Passphrase**（重要！这是你自己设置的密码）
6. 记录三个凭证：
   - API Key
   - Secret Key
   - Passphrase

### 第二步：配置环境变量

```bash
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_api_secret"
export OKX_PASSPHRASE="your_passphrase"
```

> ⚠️ **重要**：OKX 需要3个凭证，其中 Passphrase 是你创建API时自己设置的密码，不是登录密码！

### 第三步：测试连接

#### 方法1：使用测试脚本（推荐）

```bash
# 运行OKX连接测试脚本
python scripts/test_okx_connection.py

# 如果所有测试通过，说明配置正确！
```

测试脚本会检查：
- ✅ 环境变量是否正确设置
- ✅ API凭证是否有效
- ✅ 签名机制是否正确
- ✅ 网络连接是否正常

#### 方法2：直接测试命令

```bash
# 查询账户余额
cextools account balance -x okx -e perp

# 如果出现余额数据，说明连接成功！
```

#### 遇到问题？

如果测试失败，请参考：
- [OKX问题排查指南](okx-troubleshooting.md)
- 运行调试模式：`cextools account balance -x okx -e perp --debug`

## 📖 常用命令

### 查询余额
```bash
# 表格格式
cextools account balance -x okx -e perp

# JSON格式
cextools account balance -x okx -e perp -o json
```

### 查询持仓
```bash
# 查询所有持仓
cextools account positions -x okx -e perp

# 查询特定合约（注意格式：BTC-USDT-SWAP）
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP

# JSON格式
cextools account positions -x okx -e perp -o json
```

### 查询挂单
```bash
# 查询所有挂单
cextools account orders -x okx -e perp

# 查询特定合约
cextools account orders -x okx -e perp --symbol ETH-USDT-SWAP

# CSV格式导出
cextools account orders -x okx -e perp -o csv
```

## 🆚 OKX vs Binance 对比

### Symbol格式差异
| 交易所 | 永续合约格式 | 示例 |
|--------|-------------|------|
| OKX | `BASE-QUOTE-SWAP` | `BTC-USDT-SWAP` |
| Binance | `BASEQUOTE` | `BTCUSDT` |
| XT | `base_quote` | `btc_usdt` |

### 持仓方向差异
| 交易所 | 持仓方向 |
|--------|---------|
| OKX | `long`, `short`, `net` |
| Binance | `LONG`, `SHORT`, `BOTH` |
| XT | `LONG`, `SHORT` |

### API认证差异
| 交易所 | 认证参数 |
|--------|---------|
| OKX | 3个：Key + Secret + Passphrase |
| Binance | 2个：Key + Secret |
| XT | 2个：Key + Secret |

## 🐛 常见问题

### 1. 签名错误

**错误信息**：
```
OKX API error: Invalid Sign
```

**解决方法**：
- 检查 API Key、Secret Key、Passphrase 是否正确
- 确保没有多余的空格或换行
- 检查环境变量是否正确设置：
  ```bash
  echo $OKX_API_KEY
  echo $OKX_API_SECRET
  echo $OKX_PASSPHRASE
  ```

### 2. Passphrase错误

**错误信息**：
```
OKX API error: Invalid Passphrase
```

**解决方法**：
- Passphrase是创建API时**你自己设置**的密码
- 不是OKX账户的登录密码
- 如果忘记，需要重新创建API

### 3. IP限制

**错误信息**：
```
OKX API error: IP access denied
```

**解决方法**：
- 在OKX后台添加当前IP到白名单
- 或删除IP限制（生产环境不推荐）

### 4. Symbol格式错误

**错误信息**：
```
未发现 BTCUSDT 的持仓
```

**解决方法**：
```bash
# ❌ 错误（使用了Binance格式）
cextools account positions -x okx -e perp --symbol BTCUSDT

# ✅ 正确（OKX格式）
cextools account positions -x okx -e perp --symbol BTC-USDT-SWAP
```

## 🎯 进阶技巧

### 1. 多交易所对比

同时查询不同交易所的持仓：
```bash
# Binance
cextools account positions -x binance -e perp -o json > binance_positions.json

# OKX
cextools account positions -x okx -e perp -o json > okx_positions.json

# XT
cextools account positions -x xt -e perp -o json > xt_positions.json
```

### 2. 定时监控脚本

创建监控脚本：
```bash
#!/bin/bash
while true; do
    echo "========== $(date) =========="
    cextools account positions -x okx -e perp
    sleep 60
done
```

### 3. 导出到Excel

使用CSV格式导出，可以直接在Excel中打开：
```bash
cextools account positions -x okx -e perp -o csv > positions.csv
```

## 📚 参考资料

- [OKX API官方文档](https://www.okx.com/docs-v5/zh/)
- [OKX实现文档](okx-implementation.md)
- [CEXTools使用指南](cextools-usage.md)
- [示例代码](../examples/okx_example.py)

## ✅ 测试清单

在生产使用前，建议完成以下测试：

- [ ] 测试余额查询
- [ ] 测试持仓查询
- [ ] 测试挂单查询
- [ ] 测试不同输出格式（table/json/csv）
- [ ] 测试错误处理（错误的凭证、网络异常等）
- [ ] 确认API权限设置正确
- [ ] 设置IP白名单（可选但推荐）

## 🎉 开始使用

完成上述配置后，你就可以开始使用OKX交易所功能了！

```bash
# 一条命令查看所有信息
python examples/okx_example.py
```

祝交易顺利！ 🚀

---

**最后更新**：2025-10-16

