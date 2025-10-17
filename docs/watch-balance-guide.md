# 定时查询余额功能指南

## 📋 功能概述

`watch-balance` 命令可以定时查询账户余额，实时监控账户资金变化。

## 🚀 基本使用

### 语法

```bash
cextools account watch-balance -x <exchange> -e <type> [--interval MINUTES]
```

### 参数说明

| 参数 | 简写 | 说明 | 默认值 | 必需 |
|------|------|------|--------|------|
| `--exchange-type` | `-e` | 交易类型 | - | ✅ |
| `--exchange` | `-x` | 交易所 | `xt` | - |
| `--interval` | `-i` | 查询间隔（分钟） | `1` | - |
| `--output` | `-o` | 输出格式 | `table` | - |
| `--debug` | - | 调试模式 | `false` | - |

## 📖 使用示例

### 基础用法

```bash
# 每1分钟查询一次XT永续合约余额（默认）
cextools account watch-balance -e perp

# 每5分钟查询一次Binance余额
cextools account watch-balance -x binance -e perp --interval 5

# 每10分钟查询一次OKX余额
cextools account watch-balance -x okx -e perp -i 10

# 每30分钟查询一次，JSON格式输出
cextools account watch-balance -x binance -e perp -i 30 -o json
```

### 多交易所监控

可以在不同终端同时监控多个交易所：

```bash
# 终端1：监控Binance
cextools account watch-balance -x binance -e perp -i 5

# 终端2：监控OKX
cextools account watch-balance -x okx -e perp -i 5

# 终端3：监控XT
cextools account watch-balance -x xt -e perp -i 5
```

## 🎨 输出效果

### 表格格式（默认）

```
============================================================
第 1 次查询 - 2025-10-17 15:30:00
============================================================

Account Balance
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Currency ┃ Available      ┃ Frozen       ┃ Total        ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ USDT     │ 9500.30000000  │ 500.20000000 │ 10000.50000000│
│ BTC      │ 0.15000000     │ 0.05000000   │ 0.20000000   │
└──────────┴────────────────┴──────────────┴──────────────┘
Data fetched at: 2025-10-17 15:30:00 UTC

下次查询: 2025-10-17 15:35:00
等待 5 分钟...
```

### JSON格式

```bash
cextools account watch-balance -x okx -e perp -i 5 -o json
```

输出：
```json
{
  "USDT": {
    "available": "9500.30000000",
    "frozen": "500.20000000",
    "total": "10000.50000000"
  },
  "BTC": {
    "available": "0.15000000",
    "frozen": "0.05000000",
    "total": "0.20000000"
  }
}
```

## 🛑 停止监控

按 `Ctrl+C` 优雅停止：

```
^C
监控已停止
```

程序会自动：
- 断开交易所连接
- 清理资源
- 显示停止消息

## 💡 使用场景

### 1. 资金监控

实时监控账户资金变化：

```bash
# 每5分钟检查一次余额
cextools account watch-balance -x okx -e perp -i 5
```

**适用于**：
- 监控交易盈亏
- 检测异常资金变动
- 跟踪充值到账

### 2. 套利监控

监控多个交易所的资金：

```bash
# 终端1：Binance
cextools account watch-balance -x binance -e perp -i 1

# 终端2：OKX
cextools account watch-balance -x okx -e perp -i 1

# 终端3：XT
cextools account watch-balance -x xt -e perp -i 1
```

### 3. 风险管理

定期检查账户余额，及时发现问题：

```bash
# 每30分钟检查一次
cextools account watch-balance -x okx -e perp -i 30
```

### 4. 数据记录

将输出重定向到文件进行记录：

```bash
# 记录到文件
cextools account watch-balance -x okx -e perp -i 10 -o json >> balance_history.jsonl

# 每次查询追加一行JSON到文件
```

## 🔍 技术细节

### 实现原理

```python
while True:
    # 1. 查询余额
    balance_data = await exchange.get_balance()
    
    # 2. 显示数据
    format_balance_table(balance_data)
    
    # 3. 等待指定时间
    await asyncio.sleep(interval * 60)  # 分钟转秒
```

### 优雅退出

捕获 `KeyboardInterrupt` 确保资源释放：

```python
try:
    while True:
        # 查询循环
        ...
except KeyboardInterrupt:
    console.print("\n监控已停止")
finally:
    await exchange.disconnect()
```

## 📊 性能考虑

### API限流

注意各交易所的API限流：

| 交易所 | 查询余额限制 | 建议最小间隔 |
|--------|-------------|-------------|
| Binance | 1200/分钟 | 1分钟 |
| OKX | - | 1分钟 |
| XT | - | 1分钟 |

**建议**：
- 不要设置太短的间隔（< 1分钟）
- 避免同时监控太多交易所
- 合理设置查询间隔

### 资源使用

- 内存：每次查询约 1-2MB
- 网络：每次查询 1-2KB
- CPU：几乎可忽略

## 🐛 常见问题

### 1. 间隔太短被限流

**问题**：设置间隔太短，触发API限流

**解决**：
```bash
# ❌ 可能被限流
cextools account watch-balance -e perp -i 0.5

# ✅ 推荐：至少1分钟
cextools account watch-balance -e perp -i 1
```

### 2. 连接超时

**问题**：长时间运行可能出现连接超时

**解决**：
- 程序会自动重连
- 或重启监控

### 3. API凭证过期

**问题**：监控过程中API凭证过期

**解决**：
- 检查API是否有效期
- 重新配置凭证
- 重启监控

## 🎯 高级用法

### 1. 后台运行

```bash
# 使用nohup后台运行
nohup cextools account watch-balance -x okx -e perp -i 10 -o json >> balance.log 2>&1 &

# 查看进程
ps aux | grep watch-balance

# 停止
kill <PID>
```

### 2. 结合cron定时任务

如果不需要持续监控，可以用cron：

```bash
# 编辑crontab
crontab -e

# 每小时查询一次
0 * * * * cd /home/w_zy/crypto/xt/quant && source .venv/bin/activate && cextools account balance -x okx -e perp -o json >> /tmp/balance_$(date +\%Y\%m\%d).json
```

### 3. 告警通知

结合脚本实现余额告警：

```python
import asyncio
from tri_arb.exchanges.okx_perp import OKXPerpExchange

async def watch_with_alert():
    exchange = OKXPerpExchange(...)
    await exchange.connect()
    
    while True:
        balances = await exchange.get_balance()
        usdt_balance = balances.get('USDT', {}).get('total', Decimal('0'))
        
        # 如果余额低于阈值，发送告警
        if usdt_balance < Decimal('1000'):
            print(f"⚠️  警告：USDT余额过低！当前: {usdt_balance}")
            # 这里可以添加邮件、webhook等通知
        
        await asyncio.sleep(300)  # 5分钟
    
    await exchange.disconnect()
```

## 📚 相关命令

### 单次查询

```bash
# 查询一次即可
cextools account balance -x okx -e perp
```

### 查询持仓

```bash
# 监控持仓变化（待实现）
# cextools account watch-positions -x okx -e perp -i 5
```

## ✅ 使用建议

1. **合理设置间隔**
   - 快速监控：1-5分钟
   - 常规监控：10-30分钟
   - 长期监控：60分钟

2. **选择输出格式**
   - 实时查看：`table`（默认）
   - 数据记录：`json`

3. **后台运行**
   - 使用 `nohup` 或 `screen`
   - 输出重定向到文件

4. **优雅退出**
   - 使用 `Ctrl+C`
   - 不要强制kill进程

## 📚 相关文档

- [CEXTools使用指南](cextools-usage.md)
- [OKX实现文档](okx-implementation.md)
- [Binance实现文档](binance-api-implementation.md)

---

**功能状态**：✅ 已完成并可用  
**最后更新**：2025-10-17

