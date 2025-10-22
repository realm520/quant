# 定时查询功能总结

## 🎯 功能概述

为 Gate.io 和其他交易所添加了完整的定时查询功能，包括：

- ✅ **定时查询余额** (`watch-balance`)
- ✅ **定时查询持仓** (`watch-positions`) - **新增**
- ✅ **定时查询挂单** (`watch-orders`)

## 📋 新增命令

### 1. watch-positions 命令

```bash
# 基本用法
python -m tri_arb.cli.main account watch-positions -x gate -e perp

# 指定交易对
python -m tri_arb.cli.main account watch-positions -x gate -e perp -s ETH/USDT

# 自定义间隔（每2分钟）
python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 2

# JSON输出
python -m tri_arb.cli.main account watch-positions -x gate -e perp --output json
```

### 2. 支持的交易所

所有定时查询命令现在都支持：
- ✅ XT
- ✅ Binance  
- ✅ OKX
- ✅ Gate.io

### 3. 多格式支持

- **表格格式**（默认）：实时更新的彩色表格
- **JSON格式**：结构化数据输出
- **CSV格式**：用于数据导出（仅单次查询）

## 🔧 技术实现

### 1. 代码结构

```
src/tri_arb/cli/commands/account.py
├── watch-balance      # 定时查询余额
├── watch-positions    # 定时查询持仓 (新增)
└── watch-orders       # 定时查询挂单
```

### 2. 核心功能

- **异步执行**：使用 `asyncio` 实现非阻塞定时查询
- **多交易所支持**：统一的接口支持所有交易所
- **智能筛选**：支持按交易对筛选
- **统计信息**：显示持仓/订单数量统计
- **错误处理**：完善的异常处理和重试机制

### 3. 数据格式兼容

自动识别不同交易所的数据格式：

```python
# Gate.io格式
if 'contract' in pos and 'instId' not in pos:
    pos_symbol = pos.get("contract", "").replace("_", "").upper()

# OKX格式  
elif 'instId' in pos:
    pos_symbol = pos.get("instId", "").replace("-", "").replace("SWAP", "").upper()

# Binance格式
else:
    pos_symbol = pos.get("symbol", "").upper()
```

## 📊 使用示例

### 1. Gate.io 完整监控

```bash
# 终端1：监控余额（每5分钟）
python -m tri_arb.cli.main account watch-balance -x gate -e perp -i 5

# 终端2：监控持仓（每2分钟）
python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 2

# 终端3：监控订单（每1分钟）
python -m tri_arb.cli.main account watch-orders -x gate -e perp -i 1

# 终端4：WebSocket实时订阅
python -m tri_arb.cli.main subscribe user-stream -x gate -c account,position,order
```

### 2. 多交易所对比

```bash
# 同时监控多个交易所的持仓
python -m tri_arb.cli.main account watch-positions -x binance -e perp -i 1 &
python -m tri_arb.cli.main account watch-positions -x okx -e perp -i 1 &
python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 1 &
```

### 3. 特定交易对监控

```bash
# 只监控ETH/USDT的持仓
python -m tri_arb.cli.main account watch-positions -x gate -e perp -s ETH/USDT -i 1

# 只监控BTC/USDT的订单
python -m tri_arb.cli.main account watch-orders -x gate -e perp -s BTC/USDT -i 1
```

## 🎨 输出特性

### 1. 表格显示

- **彩色标识**：盈利/亏损用不同颜色显示
- **实时更新**：每次查询显示时间戳
- **统计信息**：显示持仓/订单总数
- **方向统计**：多头/空头、买单/卖单数量

### 2. JSON输出

```bash
python -m tri_arb.cli.main account watch-positions -x gate -e perp --output json
```

### 3. 进度显示

```
============================================================
第 1 次查询 - 2025-10-22 16:35:00
============================================================

📊 Gate.io持仓更新 - 16:35:00
╭──────────┬──────┬────────┬───────────┬──────┬────────────────┬────────────┬──────────╮
│ 合约     │ 方向 │ 持仓量 │  开仓均价 │ 模式 │      杠杆      │ 已实现盈亏 │ 最后平仓 │
├──────────┼──────┼────────┼───────────┼──────┼────────────────┼────────────┼──────────┤
│ ETH_USDT │  多  │      1 │ 3859.5097 │ 单向 │ 全仓11x        │    -0.1838 │  -0.1048 │
╰──────────┴──────┴────────┴───────────┴──────┴────────────────┴────────────┴──────────╯

统计: 共 1 个持仓 (多头: 1, 空头: 0)
下次查询: 2025-10-22 16:37:00
等待 2 分钟...
```

## 🔄 与现有功能集成

### 1. WebSocket + 定时查询

```bash
# 实时数据 + 定期快照
python -m tri_arb.cli.main subscribe user-stream -x gate -c account,position,order &
python -m tri_arb.cli.main account watch-balance -x gate -e perp -i 5 &
```

### 2. 数据库存储

定时查询的数据可以结合WebSocket数据进行分析：

```sql
-- 对比实时数据和定期快照
SELECT 
    'websocket' as source,
    update_time,
    contract,
    size
FROM gate_positions 
WHERE update_time >= NOW() - INTERVAL '1 hour'

UNION ALL

SELECT 
    'rest_api' as source,
    NOW() as update_time,
    'ETH_USDT' as contract,
    1.0 as size;
```

## 📈 性能优化

### 1. 智能间隔

- **余额查询**：建议5-10分钟（变化较慢）
- **持仓查询**：建议1-3分钟（可能频繁变化）
- **订单查询**：建议1-2分钟（状态变化快）

### 2. 资源管理

- **连接复用**：同一交易所复用连接
- **内存优化**：及时释放查询结果
- **错误恢复**：网络异常时自动重连

## 🚀 部署建议

### 1. 生产环境

```bash
# 使用nohup后台运行
nohup python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 2 > gate-positions.log 2>&1 &

# 使用systemd服务
sudo systemctl enable gate-positions-monitor
sudo systemctl start gate-positions-monitor
```

### 2. 监控脚本

```bash
#!/bin/bash
# monitor-gate.sh

# 检查进程是否运行
if ! pgrep -f "watch-positions.*gate" > /dev/null; then
    echo "Gate.io持仓监控已停止，正在重启..."
    nohup python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 2 > gate-positions.log 2>&1 &
fi
```

## 📚 文档更新

### 1. 新增文档

- ✅ `docs/GATE_TIMED_QUERIES.md` - Gate.io定时查询指南
- ✅ `TIMED_QUERIES_SUMMARY.md` - 功能总结（本文档）

### 2. 更新文档

- ✅ `QUICK_REFERENCE.md` - 添加新命令示例
- ✅ 所有交易所示例都包含定时查询功能

## 🎯 下一步计划

### 1. 功能增强

- [ ] 添加邮件/短信通知功能
- [ ] 支持配置文件批量监控
- [ ] 添加数据导出功能
- [ ] 支持自定义筛选条件

### 2. 性能优化

- [ ] 并发查询多个交易所
- [ ] 智能间隔调整
- [ ] 数据缓存机制

### 3. 监控集成

- [ ] Prometheus指标导出
- [ ] Grafana仪表板
- [ ] 告警规则配置

---

## ✅ 完成状态

**功能状态**：✅ 完全实现  
**测试状态**：✅ 已验证  
**文档状态**：✅ 完整更新  
**部署状态**：✅ 生产就绪  

**新增命令**：
- `watch-positions` - 定时查询持仓
- 支持所有交易所（XT、Binance、OKX、Gate.io）
- 完整的参数和输出格式支持

**使用方式**：
```bash
python -m tri_arb.cli.main account watch-positions -x gate -e perp -i 2
```

定时查询功能现已完全集成到CEXTools中，为Gate.io和其他交易所提供了全面的账户监控能力！
