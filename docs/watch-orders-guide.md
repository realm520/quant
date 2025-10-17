# 定时查询订单功能指南

## 📋 功能概述

`watch-orders` 命令可以定时查询挂单状态，实时监控订单变化，包括成交情况、订单数量等。

## 🚀 基本使用

### 语法

```bash
cextools account watch-orders -x <exchange> -e perp [--symbol SYMBOL] [--interval MINUTES]
```

### 参数说明

| 参数 | 简写 | 说明 | 默认值 | 必需 |
|------|------|------|--------|------|
| `--exchange-type` | `-e` | 交易类型（仅支持perp） | - | ✅ |
| `--exchange` | `-x` | 交易所 | `xt` | - |
| `--symbol` | `-s` | 交易对 | 全部 | - |
| `--interval` | `-i` | 查询间隔（分钟） | `1` | - |
| `--output` | `-o` | 输出格式 | `table` | - |
| `--debug` | - | 调试模式 | `false` | - |

## 📖 使用示例

### 基础用法

```bash
# 每1分钟查询一次所有挂单
cextools account watch-orders -e perp

# 每2分钟查询Binance的所有挂单
cextools account watch-orders -x binance -e perp --interval 2

# 每5分钟查询OKX的所有挂单
cextools account watch-orders -x okx -e perp -i 5
```

### 监控特定交易对

```bash
# 每1分钟查询BTC/USDT的挂单
cextools account watch-orders -x binance -e perp -s BTC/USDT

# 每2分钟查询ETH/USDT的挂单
cextools account watch-orders -x okx -e perp -s ETH/USDT -i 2

# JSON格式输出
cextools account watch-orders -x okx -e perp -s BTC/USDT -i 3 -o json
```

### 多交易所同时监控

在不同终端同时运行：

```bash
# 终端1：监控Binance所有挂单
cextools account watch-orders -x binance -e perp -i 1

# 终端2：监控OKX的BTC挂单
cextools account watch-orders -x okx -e perp -s BTC/USDT -i 1

# 终端3：监控OKX的ETH挂单
cextools account watch-orders -x okx -e perp -s ETH/USDT -i 2
```

## 🎨 输出效果

### 表格格式（默认）

```
============================================================
第 1 次查询 - 2025-10-17 16:30:00
============================================================

Open Orders
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┓
┃ Exchange ┃ Symbol         ┃ Order ID ┃ Side ┃ Type  ┃ Price    ┃ Quantity ┃ Filled      ┃ Status ┃ Time              ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━┩
│ okx_perp │ BTC-USDT-SWAP  │ 12345678 │ BUY  │ limit │ 30000.00 │ 0.001000 │ 0.00 (0.0%) │ live   │ 2025-10-17 10:00:00│
│ okx_perp │ ETH-USDT-SWAP  │ 87654321 │ SELL │ limit │ 5000.00  │ 0.010000 │ 0.00 (0.0%) │ live   │ 2025-10-17 10:05:00│
└──────────┴────────────────┴──────────┴──────┴───────┴──────────┴──────────┴─────────────┴────────┴───────────────────┘
Data fetched at: 2025-10-17 16:30:00 UTC

统计: 共 2 个挂单 (买单: 1, 卖单: 1)
下次查询: 2025-10-17 16:31:00
等待 1 分钟...
```

### JSON格式

```bash
cextools account watch-orders -x okx -e perp -i 2 -o json
```

每次查询输出JSON数据，便于程序处理。

## 💡 使用场景

### 1. 监控订单成交

实时查看订单是否成交：

```bash
# 每1分钟检查BTC订单
cextools account watch-orders -x binance -e perp -s BTC/USDT -i 1
```

**作用**：
- 及时发现订单成交
- 监控部分成交情况
- 检查订单状态变化

### 2. 多订单策略监控

监控所有挂单：

```bash
# 每2分钟查询所有挂单
cextools account watch-orders -x okx -e perp -i 2
```

**作用**：
- 监控多个交易对的订单
- 查看订单分布
- 及时发现订单异常

### 3. 套利订单监控

同时监控多个交易所的订单：

```bash
# 终端1：Binance
cextools account watch-orders -x binance -e perp -s BTC/USDT -i 1

# 终端2：OKX
cextools account watch-orders -x okx -e perp -s BTC/USDT -i 1
```

**作用**：
- 对比不同交易所的挂单状态
- 监控套利订单执行
- 及时发现价差机会

### 4. 数据记录

记录订单历史数据：

```bash
# 每5分钟记录一次，输出到文件
cextools account watch-orders -x okx -e perp -i 5 -o json >> orders_history.jsonl
```

## 🔍 输出信息解读

### 订单状态

| 状态 | Binance | OKX | 含义 |
|------|---------|-----|------|
| 新建 | NEW | live | 订单已挂单，等待成交 |
| 部分成交 | PARTIALLY_FILLED | partially_filled | 部分数量已成交 |
| 完全成交 | FILLED | filled | 全部成交，订单完成 |
| 已取消 | CANCELED | canceled | 订单已撤销 |

### 成交信息

- **Filled列**：显示已成交数量和百分比
  - `0.000000 (0.0%)` - 未成交
  - `0.000500 (50.0%)` - 部分成交50%
  - `0.001000 (100.0%)` - 完全成交

### 统计信息

每次查询后显示：
- 总挂单数
- 买单数量
- 卖单数量

## ⚠️ 注意事项

### 1. API限流

不要设置太短的间隔：

```bash
# ⚠️  可能触发限流
cextools account watch-orders -e perp -i 0.5

# ✅ 推荐：至少1分钟
cextools account watch-orders -e perp -i 1
```

### 2. 资源消耗

- 长时间运行会占用一个终端窗口
- 网络连接持续占用
- 建议使用后台运行（见下文）

### 3. 仅限永续合约

当前只支持永续合约：

```bash
# ❌ 不支持
cextools account watch-orders -e spot

# ✅ 支持
cextools account watch-orders -e perp
```

## 🎯 高级用法

### 1. 后台运行

使用`nohup`后台运行：

```bash
# 后台运行，输出到文件
nohup cextools account watch-orders -x okx -e perp -i 5 -o json > orders_monitor.log 2>&1 &

# 查看输出
tail -f orders_monitor.log

# 查看进程
ps aux | grep watch-orders

# 停止监控
kill <PID>
```

### 2. 使用screen或tmux

```bash
# 创建screen会话
screen -S okx-orders

# 运行监控
cextools account watch-orders -x okx -e perp -i 2

# 按 Ctrl+A, D 分离会话
# 恢复会话：screen -r okx-orders
```

### 3. 结合脚本处理

创建 `monitor_orders.sh`：

```bash
#!/bin/bash

echo "开始监控订单..."

# 监控订单，如果发现成交则通知
cextools account watch-orders -x okx -e perp -i 1 -o json | while read line; do
    echo "$line" >> orders.log
    
    # 检查是否有订单成交
    if echo "$line" | grep -q '"state":"filled"'; then
        echo "🎉 订单已成交！"
        # 这里可以添加通知逻辑
    fi
done
```

### 4. 多symbol监控

监控多个交易对（使用脚本）：

```bash
#!/bin/bash

symbols=("BTC/USDT" "ETH/USDT" "SOL/USDT")

for symbol in "${symbols[@]}"; do
    echo "监控 $symbol"
    cextools account watch-orders -x okx -e perp -s "$symbol" -i 5 &
done

wait
```

## 📊 性能优化

### 1. 合理设置间隔

根据需求设置合适的间隔：

| 场景 | 推荐间隔 |
|------|---------|
| 快速监控（高频交易） | 1-2分钟 |
| 常规监控 | 5-10分钟 |
| 长期监控 | 30-60分钟 |

### 2. 选择性监控

```bash
# ✅ 推荐：只监控特定交易对
cextools account watch-orders -x okx -e perp -s BTC/USDT -i 2

# ⚠️  谨慎：监控所有交易对（数据量大）
cextools account watch-orders -x okx -e perp -i 2
```

### 3. 输出格式选择

```bash
# 实时查看：table格式（美观）
cextools account watch-orders -x okx -e perp -i 5

# 数据记录：json格式（便于处理）
cextools account watch-orders -x okx -e perp -i 5 -o json >> data.jsonl
```

## 🆚 与单次查询的区别

| 特性 | 单次查询 (`orders`) | 定时查询 (`watch-orders`) |
|------|-------------------|------------------------|
| 查询次数 | 1次 | 持续查询 |
| 适用场景 | 快速查看 | 持续监控 |
| 资源占用 | 低 | 中等 |
| 停止方式 | 自动结束 | Ctrl+C |

## 🔄 与watch-balance配合使用

同时监控余额和订单：

```bash
# 终端1：监控余额（每5分钟）
cextools account watch-balance -x okx -e perp -i 5

# 终端2：监控订单（每1分钟）
cextools account watch-orders -x okx -e perp -i 1
```

## 📚 相关命令

### 单次查询

```bash
# 查询一次即可
cextools account orders -x okx -e perp
```

### 定时查询余额

```bash
# 监控余额变化
cextools account watch-balance -x okx -e perp -i 5
```

### 查询持仓

```bash
# 查询持仓
cextools account positions -x okx -e perp
```

## 🐛 常见问题

### 1. 为什么没有订单显示？

**原因**：当前没有挂单

**确认**：
```bash
# 下单后再监控
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

# 然后监控
cextools account watch-orders -x okx -e perp -s BTC/USDT
```

### 2. 如何停止监控？

**方法**：按 `Ctrl+C`

```
^C
监控已停止
```

### 3. 间隔可以小于1分钟吗？

**不建议**：
- 可能触发API限流
- 增加服务器负担
- 通常1分钟已足够

## 💡 实用技巧

### 1. 订单成交监控

```bash
# 每1分钟检查订单是否成交
cextools account watch-orders -x okx -e perp -s BTC/USDT -i 1
```

观察 **Filled** 列的百分比变化。

### 2. 记录订单历史

```bash
# 每5分钟记录一次订单状态
cextools account watch-orders -x okx -e perp -i 5 -o json >> orders_$(date +%Y%m%d).jsonl
```

### 3. 告警脚本

创建 `alert_on_fill.sh`：

```bash
#!/bin/bash

cextools account watch-orders -x okx -e perp -i 1 -o json | while read line; do
    # 检查是否有订单成交
    if echo "$line" | grep -q '"state":"filled"'; then
        echo "🎉 订单已成交！"
        echo "$line" | jq '.'
        # 可以添加邮件、Telegram等通知
    fi
done
```

### 4. 对比不同交易所

```python
# Python脚本同时监控两个交易所
import asyncio
from tri_arb.exchanges.binance_perp import BinancePerpExchange
from tri_arb.exchanges.okx_perp import OKXPerpExchange

async def monitor_both():
    binance = BinancePerpExchange(...)
    okx = OKXPerpExchange(...)
    
    await binance.connect()
    await okx.connect()
    
    while True:
        binance_orders = await binance.get_open_orders()
        okx_orders = await okx.get_open_orders()
        
        print(f"Binance: {len(binance_orders)} 个订单")
        print(f"OKX: {len(okx_orders)} 个订单")
        
        await asyncio.sleep(60)
    
    await binance.disconnect()
    await okx.disconnect()
```

## 🎯 监控策略

### 策略1：快速响应

```bash
# 高频监控（适合短线交易）
cextools account watch-orders -x binance -e perp -s BTC/USDT -i 1
```

### 策略2：定期检查

```bash
# 定期检查（适合挂单后等待）
cextools account watch-orders -x okx -e perp -i 10
```

### 策略3：长期监控

```bash
# 长期监控（后台运行）
nohup cextools account watch-orders -x okx -e perp -i 30 -o json >> orders.log 2>&1 &
```

## 📋 监控检查清单

开始监控前确认：

- [ ] API凭证已正确设置
- [ ] 确实有挂单存在
- [ ] 查询间隔合理（>= 1分钟）
- [ ] 选择了合适的输出格式
- [ ] 了解如何停止（Ctrl+C）

## 🆚 功能对比

| 命令 | 功能 | 持续性 | 适用场景 |
|------|------|--------|---------|
| `orders` | 查询一次 | 单次 | 快速查看 |
| `watch-orders` | 定时查询 | 持续 | 持续监控 |

## 📚 相关文档

- [定时查询余额指南](watch-balance-guide.md)
- [CEXTools使用指南](cextools-usage.md)
- [下单功能指南](place-order-guide.md)

## 🎊 总结

`watch-orders` 命令提供了强大的订单监控功能：

- ✅ 支持所有交易所（XT、Binance、OKX）
- ✅ 可配置查询间隔
- ✅ 支持特定交易对筛选
- ✅ 实时统计信息
- ✅ 多种输出格式
- ✅ 优雅的Ctrl+C退出

**开始监控**：

```bash
# 监控OKX的所有挂单（每2分钟）
cextools account watch-orders -x okx -e perp -i 2
```

按 `Ctrl+C` 停止监控！

---

**功能状态**：✅ 已完成并可用  
**最后更新**：2025-10-17

