# 选择性频道订阅指南

## 🎯 功能概述

通过 `--channels` 参数，可以选择性订阅特定的数据流，而不是订阅所有频道。

## 📊 支持的频道

### Binance频道

| 频道名 | 说明 | 包含数据 |
|--------|------|----------|
| `account` | 账户更新 | 余额变化、持仓变化 |
| `order` | 订单更新 | 订单状态、成交进度 |
| `trade` | 成交记录 | 实际成交详情 |

### OKX频道

| 频道名 | 说明 | 包含数据 |
|--------|------|----------|
| `account` | 账户余额 | 币种余额、权益、盈亏 |
| `position` | 持仓 | 持仓量、盈亏、保证金 |
| `order` | 订单 | 订单状态、成交进度 |

## 🚀 使用方法

### 基本语法

```bash
cextools subscribe user-stream -x <exchange> --channels <channel1,channel2,...>
```

### Binance示例

#### 只订阅账户更新
```bash
cextools subscribe user-stream -x binance --channels account
```

#### 只订阅订单更新
```bash
cextools subscribe user-stream -x binance --channels order
```

#### 订阅账户和订单（不含成交）
```bash
cextools subscribe user-stream -x binance --channels account,order
```

#### 订阅所有（默认）
```bash
cextools subscribe user-stream -x binance
# 或显式指定
cextools subscribe user-stream -x binance --channels account,order,trade
```

### OKX示例

#### 只订阅账户余额
```bash
cextools subscribe user-stream -x okx --channels account
```

#### 只订阅持仓更新
```bash
cextools subscribe user-stream -x okx --channels position
```

#### 只订阅订单更新
```bash
cextools subscribe user-stream -x okx --channels order
```

#### 订阅账户和持仓
```bash
cextools subscribe user-stream -x okx --channels account,position
```

#### 订阅持仓和订单
```bash
cextools subscribe user-stream -x okx --channels position,order
```

#### 订阅所有（默认）
```bash
cextools subscribe user-stream -x okx
# 或显式指定
cextools subscribe user-stream -x okx --channels account,position,order
```

## 🎯 使用场景

### 场景1：监控账户风险

只关注账户余额和持仓风险：

```bash
# OKX: 账户 + 持仓
cextools subscribe user-stream -x okx --channels account,position --output table

# Binance: 账户
cextools subscribe user-stream -x binance --channels account --output table
```

### 场景2：监控订单执行

只关注订单状态，不关心账户余额：

```bash
# OKX: 只订阅订单
cextools subscribe user-stream -x okx --channels order --output table

# Binance: 订单 + 成交
cextools subscribe user-stream -x binance --channels order,trade --output table
```

### 场景3：分离监控（多终端）

不同终端监控不同的数据流：

```bash
# 终端1：监控Binance账户
cextools subscribe user-stream -x binance --channels account

# 终端2：监控Binance订单
cextools subscribe user-stream -x binance --channels order

# 终端3：监控OKX持仓
cextools subscribe user-stream -x okx --channels position

# 终端4：监控OKX订单
cextools subscribe user-stream -x okx --channels order
```

### 场景4：减少数据量

只订阅必要的数据，减少数据库存储：

```bash
# 只监控订单，不存储账户快照
cextools subscribe user-stream -x okx --channels order --output table
```

## 💡 实用技巧

### 技巧1：组合不同显示格式

```bash
# 账户用表格，订单用JSON
# 终端1
cextools subscribe user-stream -x okx --channels account --output table

# 终端2
cextools subscribe user-stream -x okx --channels order --output json
```

### 技巧2：后台运行不同频道

```bash
# 账户静默保存
nohup cextools subscribe user-stream -x okx --channels account --output none > account.log 2>&1 &

# 订单实时显示
cextools subscribe user-stream -x okx --channels order --output table
```

### 技巧3：数据库分析特定频道

```sql
-- 如果只订阅了order频道，okx_account_balances表将为空
SELECT COUNT(*) FROM okx_orders;  -- 有数据
SELECT COUNT(*) FROM okx_account_balances;  -- 无数据（未订阅）
```

## 📊 频道对比

### Binance vs OKX

| 特性 | Binance | OKX |
|------|---------|-----|
| 频道数量 | 3个 | 3个 |
| 账户频道 | `account` | `account` |
| 持仓频道 | `account`（混合） | `position`（独立） |
| 订单频道 | `order` | `order` |
| 成交频道 | `trade` | -（包含在order中） |
| 可选订阅 | ✅ | ✅ |

### 频道依赖关系

| 交易所 | 频道 | 依赖 | 说明 |
|--------|------|------|------|
| Binance | account | 无 | 独立频道 |
| Binance | order | 无 | 独立频道 |
| Binance | trade | order | 从order提取 |
| OKX | account | 无 | 独立频道 |
| OKX | position | 无 | 独立频道 |
| OKX | order | 无 | 独立频道 |

## ⚙️ 参数说明

### --channels 参数格式

```bash
--channels <channel1,channel2,...>

# 或简写
-c <channel1,channel2,...>
```

**注意事项**：
- ✅ 多个频道用逗号分隔，不要空格
- ✅ 频道名不区分大小写
- ✅ 留空表示订阅所有频道
- ❌ 不能包含不支持的频道名

### 正确示例

```bash
# ✅ 正确
--channels account
--channels account,order
--channels ACCOUNT,ORDER  # 不区分大小写

# ❌ 错误
--channels account, order  # 有空格
--channels account order   # 没有逗号
--channels unknown         # 不支持的频道
```

## 🔍 验证订阅

### 查看日志

```bash
# 启动订阅
cextools subscribe user-stream -x okx --channels account,order --output table

# 查看日志（应该只看到订阅了2个频道）
tail -f logs/tri-arb.log | grep "Subscribed"

# 输出示例：
# Subscribed to OKX channels channels=['account', 'orders'] count=2
```

### 测试数据接收

```bash
# 只订阅order频道
cextools subscribe user-stream -x okx --channels order

# 下单测试
cextools order place -x okx -e perp -s BTC/USDT --side buy -q 0.001 -p 50000 --position-side LONG

# 应该能看到订单更新
# 不会看到账户余额更新（因为没订阅）
```

## 📋 完整命令示例

### Binance

```bash
# 只监控账户
cextools subscribe user-stream -x binance -c account -o table

# 只监控订单
cextools subscribe user-stream -x binance -c order -o table

# 账户+订单
cextools subscribe user-stream -x binance -c account,order -o table

# 全部
cextools subscribe user-stream -x binance
```

### OKX

```bash
# 只监控账户
cextools subscribe user-stream -x okx -c account -o table

# 只监控持仓
cextools subscribe user-stream -x okx -c position -o table

# 只监控订单
cextools subscribe user-stream -x okx -c order -o table

# 账户+持仓
cextools subscribe user-stream -x okx -c account,position -o table

# 持仓+订单
cextools subscribe user-stream -x okx -c position,order -o table

# 全部
cextools subscribe user-stream -x okx
```

## 💾 数据库影响

### 订阅选择对数据库表的影响

| 订阅频道 | Binance写入的表 | OKX写入的表 |
|---------|----------------|-------------|
| account | `account_updates` | `okx_account_balances` |
| position | `account_updates` | `okx_positions` |
| order | `order_updates` | `okx_orders` |
| trade | `trade_updates` | - |

**示例**：

```bash
# 只订阅OKX的order频道
cextools subscribe user-stream -x okx -c order

# 结果：
# ✅ okx_orders 表有数据
# ❌ okx_account_balances 表无新数据（未订阅account）
# ❌ okx_positions 表无新数据（未订阅position）
```

## 🎯 推荐配置

### 日常交易监控

```bash
# OKX: 持仓 + 订单
cextools subscribe user-stream -x okx -c position,order -o table

# Binance: 账户 + 订单
cextools subscribe user-stream -x binance -c account,order -o table
```

### 风险监控

```bash
# 只监控持仓和账户
cextools subscribe user-stream -x okx -c account,position -o table
```

### 订单执行分析

```bash
# 只监控订单
cextools subscribe user-stream -x okx -c order -o json > orders.log
```

### 后台数据收集

```bash
# OKX全部频道，静默保存
nohup cextools subscribe user-stream -x okx --output none > okx-all.log 2>&1 &

# Binance只保存订单
nohup cextools subscribe user-stream -x binance -c order --output none > binance-orders.log 2>&1 &
```

## 🔧 与其他参数组合

### 完整参数示例

```bash
cextools subscribe user-stream \
  -x okx \                        # 交易所
  --channels position,order \     # 订阅频道
  --output table \                # 显示格式
  --create-tables \               # 首次运行创建表
  --database-url "..." \          # 数据库URL
  --debug                         # 调试模式
```

### 简写形式

```bash
cextools subscribe user-stream -x okx -c position,order -o table
```

## 📚 帮助信息

```bash
# 查看完整帮助
cextools subscribe user-stream --help

# 查看支持的频道
cextools subscribe user-stream -x binance --help
cextools subscribe user-stream -x okx --help
```

## 🎉 总结

### 优势

- ✅ **灵活控制** - 只订阅需要的数据
- ✅ **减少数据量** - 降低存储压力
- ✅ **专注监控** - 不同终端监控不同数据
- ✅ **性能优化** - 减少处理开销

### 频道选择建议

| 需求 | Binance推荐 | OKX推荐 |
|------|------------|---------|
| 全面监控 | 全部 | 全部 |
| 风险管理 | `account` | `account,position` |
| 订单执行 | `order` | `order` |
| 成交分析 | `order,trade` | `order` |
| 最小化存储 | `order` | `order` |

### 快速参考

```bash
# Binance
cextools subscribe user-stream -x binance -c account      # 只账户
cextools subscribe user-stream -x binance -c order        # 只订单
cextools subscribe user-stream -x binance -c account,order # 账户+订单

# OKX
cextools subscribe user-stream -x okx -c account          # 只账户
cextools subscribe user-stream -x okx -c position         # 只持仓
cextools subscribe user-stream -x okx -c order            # 只订单
cextools subscribe user-stream -x okx -c position,order   # 持仓+订单

# 全部
cextools subscribe user-stream -x binance  # 留空=全部
cextools subscribe user-stream -x okx      # 留空=全部
```

---

**享受灵活的频道订阅！** 🚀

