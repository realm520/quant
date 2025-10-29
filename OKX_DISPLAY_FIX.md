# OKX 数据恢复显示优化

**修复时间**: 2025-10-28
**问题**: 数据恢复时没有在控制台显示恢复的订单和成交
**状态**: ✅ 已完成

---

## 🎯 用户需求

1. **控制台显示恢复的订单** - 当数据恢复时，在控制台显示每个恢复的订单
2. **控制台显示恢复的成交** - 当数据恢复时，在控制台显示每个恢复的成交
3. **优化日志输出** - 添加恢复总结表格，清晰展示恢复结果

---

## ✅ 完成的修复

### 修复1: 添加恢复订单显示方法

**文件**: `src/tri_arb/services/okx_user_stream.py`
**位置**: 第 659-716 行

```python
def _display_recovered_order(self, order_data: dict):
    """显示恢复的订单（数据恢复时使用）."""
    if self.display_format == "none":
        return

    table = Table(
        title=f"🔄 [bold cyan]恢复订单[/bold cyan] - {datetime.now().strftime('%H:%M:%S')}",
        box=box.ROUNDED
    )
    # ... 显示订单详情 ...
    console.print(table)
    console.print(f"[green]✅ 订单已恢复到数据库[/green]")
```

**显示内容：**
- 产品ID
- 订单ID
- 状态（带颜色）
- 方向（买/卖，带颜色）
- 类型（限价/市价）
- 委托价格和数量
- 已成交数量
- 平均成交价
- 更新时间

### 修复2: 添加恢复成交显示方法

**文件**: `src/tri_arb/services/okx_user_stream.py`
**位置**: 第 718-766 行

```python
def _display_recovered_trade(self, trade_data: dict):
    """显示恢复的成交（数据恢复时使用）."""
    if self.display_format == "none":
        return

    table = Table(
        title=f"🔄 [bold green]恢复成交[/bold green] - {datetime.now().strftime('%H:%M:%S')}",
        box=box.ROUNDED
    )
    # ... 显示成交详情 ...
    console.print(table)
    console.print(f"[green]✅ 成交已恢复到数据库[/green]")
```

**显示内容：**
- 产品ID
- 成交ID
- 订单ID
- 方向（买/卖，带颜色）
- 成交价格
- 成交数量
- 成交金额
- 手续费
- 成交时间

### 修复3: 调用显示方法

**文件**: `src/tri_arb/services/okx_user_stream.py`
**位置**: 第 1000-1025 行

```python
# 保存订单到数据库（带去重）并显示
for order_data in orders:
    saved = await self._save_order_with_dedup(order_data)
    if saved:
        recovered_orders += 1
        # ✅ 在控制台显示恢复的订单
        self._display_recovered_order(order_data)

# 保存成交到数据库（带去重）并显示
for trade_data in trades:
    saved = await self._save_trade_with_dedup(trade_data)
    if saved:
        recovered_trades += 1
        # ✅ 在控制台显示恢复的成交
        self._display_recovered_trade(trade_data)
```

### 修复4: 添加恢复总结表格

**文件**: `src/tri_arb/services/okx_user_stream.py`
**位置**: 第 1156-1183 行

```python
# ✅ 在控制台显示恢复总结
if self.display_format != "none":
    summary_table = Table(
        title=f"📊 [bold magenta]数据恢复总结[/bold magenta]",
        box=box.DOUBLE
    )
    summary_table.add_column("项目", style="cyan", justify="left")
    summary_table.add_column("数量", style="yellow", justify="right")

    summary_table.add_row("断线时长", f"{gap_seconds} 秒 ({round(gap_seconds / 60, 2)} 分钟)")
    summary_table.add_row("查询交易对", str(len(symbols)))
    summary_table.add_row("━" * 20, "━" * 10)
    summary_table.add_row("查询到的订单", str(total_orders))
    summary_table.add_row("恢复到数据库", f"[green]{recovered_orders}[/green]")
    summary_table.add_row("跳过重复订单", f"[yellow]{duplicate_orders}[/yellow]")
    summary_table.add_row("━" * 20, "━" * 10)
    summary_table.add_row("查询到的成交", str(total_trades))
    summary_table.add_row("恢复到数据库", f"[green]{recovered_trades}[/green]")
    summary_table.add_row("跳过重复成交", f"[yellow]{duplicate_trades}[/yellow]")

    console.print(summary_table)

    if recovered_orders > 0 or recovered_trades > 0:
        console.print(f"\n[bold green]✅ 数据恢复成功！恢复了 {recovered_orders} 个订单和 {recovered_trades} 个成交[/bold green]\n")
    elif total_orders == 0 and total_trades == 0:
        console.print(f"\n[yellow]ℹ️  断线期间没有新的订单或成交[/yellow]\n")
    else:
        console.print(f"\n[yellow]ℹ️  所有数据已存在，无需恢复[/yellow]\n")
```

---

## 📺 预期控制台输出

### 场景1: 恢复了订单和成交

```
🔄 恢复订单 - 14:52:38
╭─────────────────┬─────────────────────╮
│ 字段            │ 值                  │
├─────────────────┼─────────────────────┤
│ 产品            │ ETH-USDT-SWAP       │
│ 订单ID          │ 2990770989367091200 │
│ 状态            │ FILLED              │
│ 方向            │ BUY                 │
│ 类型            │ LIMIT               │
│ 委托价格        │ 3150.0000           │
│ 委托数量        │ 0.50000000          │
│ 已成交          │ 0.50000000          │
│ 平均价          │ 3150.1000           │
│ 更新时间        │ 2025-10-28 14:52:30 │
╰─────────────────┴─────────────────────╯
✅ 订单已恢复到数据库

🔄 恢复成交 - 14:52:38
╭─────────────────┬─────────────────────╮
│ 字段            │ 值                  │
├─────────────────┼─────────────────────┤
│ 产品            │ ETH-USDT-SWAP       │
│ 成交ID          │ 123456789           │
│ 订单ID          │ 2990770989367091200 │
│ 方向            │ BUY                 │
│ 成交价          │ 3150.1000           │
│ 成交量          │ 0.50000000          │
│ 成交额          │ 1575.0500 USDT      │
│ 手续费          │ 0.00050000 ETH      │
│ 成交时间        │ 2025-10-28 14:52:30 │
╰─────────────────┴─────────────────────╯
✅ 成交已恢复到数据库

     📊 数据恢复总结
╔══════════════════════╦════════╗
║ 项目                 ║ 数量   ║
╠══════════════════════╬════════╣
║ 断线时长             ║ 6 秒   ║
║                      ║ (0.1   ║
║                      ║ 分钟)  ║
║ 查询交易对           ║ 1      ║
║ ━━━━━━━━━━━━━━━━━━━━ ║ ━━━━━  ║
║ 查询到的订单         ║ 1      ║
║ 恢复到数据库         ║ 1      ║
║ 跳过重复订单         ║ 0      ║
║ ━━━━━━━━━━━━━━━━━━━━ ║ ━━━━━  ║
║ 查询到的成交         ║ 1      ║
║ 恢复到数据库         ║ 1      ║
║ 跳过重复成交         ║ 0      ║
╚══════════════════════╩════════╝

✅ 数据恢复成功！恢复了 1 个订单和 1 个成交
```

### 场景2: 没有新数据

```
     📊 数据恢复总结
╔══════════════════════╦════════╗
║ 项目                 ║ 数量   ║
╠══════════════════════╬════════╣
║ 断线时长             ║ 6 秒   ║
║ 查询交易对           ║ 1      ║
║ ━━━━━━━━━━━━━━━━━━━━ ║ ━━━━━  ║
║ 查询到的订单         ║ 0      ║
║ 恢复到数据库         ║ 0      ║
║ 跳过重复订单         ║ 0      ║
║ ━━━━━━━━━━━━━━━━━━━━ ║ ━━━━━  ║
║ 查询到的成交         ║ 0      ║
║ 恢复到数据库         ║ 0      ║
║ 跳过重复成交         ║ 0      ║
╚══════════════════════╩════════╝

ℹ️  断线期间没有新的订单或成交
```

### 场景3: 数据已存在（去重）

```
     📊 数据恢复总结
╔══════════════════════╦════════╗
║ 项目                 ║ 数量   ║
╠══════════════════════╬════════╣
║ 断线时长             ║ 6 秒   ║
║ 查询交易对           ║ 1      ║
║ ━━━━━━━━━━━━━━━━━━━━ ║ ━━━━━  ║
║ 查询到的订单         ║ 2      ║
║ 恢复到数据库         ║ 0      ║
║ 跳过重复订单         ║ 2      ║
║ ━━━━━━━━━━━━━━━━━━━━ ║ ━━━━━  ║
║ 查询到的成交         ║ 1      ║
║ 恢复到数据库         ║ 0      ║
║ 跳过重复成交         ║ 1      ║
╚══════════════════════╩════════╝

ℹ️  所有数据已存在，无需恢复
```

---

## 📝 重要说明

### 关于 "Retrieved 0 orders" 的情况

如果你看到日志显示 `Retrieved 0 orders` 但数据库有数据，可能原因：

1. **订单已通过 WebSocket 实时保存**
   - WebSocket 在断线前就推送并保存了订单
   - REST API 查询的时间范围在断线期间
   - 所以查不到订单是正常的

2. **时间范围的理解**
   - REST API 只查询断线期间的数据
   - 如果订单在断线之前就已经产生，REST API 不会重复查询
   - 这是为了避免重复数据

3. **举例说明**
   ```
   14:52:01 - 订单创建（WebSocket推送并保存）✅
   14:52:26 - 订单撤销（WebSocket推送并保存）✅
   14:52:29 - WebSocket断线 ❌
   14:52:36 - WebSocket重连 ✅

   REST API查询范围: 14:52:29 - 14:52:36
   结果: 0 个订单（因为订单在14:52:01和14:52:26，不在查询范围内）
   ```

### 如何验证数据完整性

```sql
-- 查看最近的订单
SELECT ord_id, inst_id, state, u_time
FROM okx_orders
WHERE u_time >= NOW() - INTERVAL '1 hour'
ORDER BY u_time DESC;

-- 查看最近的成交
SELECT trade_id, ord_id, inst_id, fill_px, fill_sz, fill_time
FROM okx_trades
WHERE fill_time >= NOW() - INTERVAL '1 hour'
ORDER BY fill_time DESC;
```

---

## 🎯 修复总结

**添加的功能：**
- ✅ 恢复订单时在控制台显示详细信息
- ✅ 恢复成交时在控制台显示详细信息
- ✅ 添加数据恢复总结表格
- ✅ 智能提示（成功/无数据/已存在）

**修改的文件：**
- `src/tri_arb/services/okx_user_stream.py` (+130行)

**用户体验提升：**
- 清晰看到每个恢复的订单和成交
- 一目了然的恢复总结
- 智能提示帮助理解恢复结果

---

**状态**: ✅ 已完成
**测试建议**: 断网测试，验证控制台输出
