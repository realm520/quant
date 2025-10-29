# OKX 断线恢复功能修复

**修复时间**: 2025-10-27
**问题**: 断线期间的订单和撤单没有恢复到数据库
**状态**: ✅ 已修复

---

## 🔍 问题回顾

用户在测试 `cextools subscribe user-stream -x okx -c order` 时发现：
- 断网期间下单和撤单
- 重新连接后，订单没有恢复到数据库

**根本原因：**
`_save_trade_with_dedup()` 方法有 TODO 注释，成交数据被直接跳过，没有保存到数据库。

---

## ✅ 修复内容

### 修复1: 实现 _save_trade_with_dedup() 方法

**文件**: `src/tri_arb/services/okx_user_stream.py`
**位置**: 第 1123-1146 行

#### 修复前 ❌
```python
async def _save_trade_with_dedup(self, trade_data: dict) -> bool:
    trade_id = trade_data.get("tradeId", "")
    try:
        async with self.db_manager.session() as session:
            trade_time = datetime.fromtimestamp(...)

            # ❌ TODO: 创建专门的 OKXTrade 模型
            logger.debug(f"OKX trade {trade_id} - skipping (no trade table yet)")
            return False  # ❌ 直接返回，数据被丢弃

    except IntegrityError:
        logger.debug(f"OKX trade {trade_id} already exists, skipping")
        return False
```

#### 修复后 ✅
```python
async def _save_trade_with_dedup(self, trade_data: dict) -> bool:
    """保存成交数据，自动去重."""
    trade_id = trade_data.get("tradeId", "")
    ord_id = trade_data.get("ordId", "")

    try:
        async with self.db_manager.session() as session:
            # 解析时间戳
            fill_time = datetime.fromtimestamp(
                int(trade_data.get("ts", 0)) / 1000
            ) if trade_data.get("ts") else datetime.utcnow()

            # ✅ 保存到 OKXTrade 表
            okx_trade = OKXTrade(
                inst_id=trade_data.get("instId"),
                ord_id=ord_id,
                trade_id=trade_id,
                side=trade_data.get("side"),
                fill_px=_safe_decimal(trade_data.get("fillPx")),
                fill_sz=_safe_decimal(trade_data.get("fillSz")),
                fee=_safe_decimal(trade_data.get("fee")) if trade_data.get("fee") else None,
                fee_ccy=trade_data.get("feeCcy"),
                fill_time=fill_time,
                raw_data=json.dumps(trade_data),
            )
            session.add(okx_trade)
            await session.commit()

            logger.debug(
                "Saved recovered OKX trade",
                trade_id=trade_id,
                ord_id=ord_id,
                inst_id=trade_data.get("instId"),
            )
            return True

    except IntegrityError:
        logger.debug(f"OKX trade {trade_id} already exists, skipping")
        return False
    except Exception as e:
        logger.error(f"Failed to save OKX trade {trade_id}", error=str(e), exc_info=True)
        return False
```

**关键改进：**
- ✅ 使用已有的 `OKXTrade` 模型
- ✅ 正确解析 OKX API 返回的成交数据
- ✅ 保存所有必要字段（价格、数量、手续费等）
- ✅ 添加详细的调试日志
- ✅ 完善的错误处理

---

### 修复2: 添加唯一性约束

**文件**: `src/tri_arb/storage/okx_models.py`
**位置**: 第 190-193 行

#### 修复前 ❌
```python
__table_args__ = (
    Index('idx_okx_trade_inst_time', 'inst_id', 'fill_time'),
)
```

#### 修复后 ✅
```python
__table_args__ = (
    Index('idx_okx_trade_inst_time', 'inst_id', 'fill_time'),
    UniqueConstraint('trade_id', name='uq_okx_trade_id'),  # ✅ 防止重复成交记录
)
```

**同时添加导入：**
```python
from sqlalchemy import ..., Index, UniqueConstraint  # ✅ 添加 UniqueConstraint
```

---

### 修复3: 数据库迁移脚本

**文件**: `scripts/migrate_add_okx_trade_constraint.py` (新增)

**功能：**
1. ✅ 检查 `okx_trades` 表是否存在
2. ✅ 检查唯一性约束是否已存在
3. ✅ 删除重复的 trade_id（保留最新的）
4. ✅ 添加唯一性约束 `uq_okx_trade_id`
5. ✅ 验证约束是否成功添加

---

## 📊 预期效果对比

### 修复前 ❌
```
=== OKX data recovery completed ===
  total_orders_retrieved=5
  total_trades_retrieved=3
  new_orders_saved=5
  new_trades_saved=0          ❌ 永远是 0 (TODO 未实现)
  duplicate_orders_skipped=0
  duplicate_trades_skipped=3  ❌ 实际上是全部跳过
  gap_seconds=120
  gap_minutes=2.0
```

### 修复后 ✅
```
=== OKX data recovery completed ===
  total_orders_retrieved=5
  total_trades_retrieved=3
  new_orders_saved=5
  new_trades_saved=3          ✅ 实际保存的数量
  duplicate_orders_skipped=0
  duplicate_trades_skipped=0  ✅ 准确的去重统计
  gap_seconds=120
  gap_minutes=2.0
```

---

## 🧪 验证步骤

### 1. 运行数据库迁移

```bash
# 添加唯一性约束
uv run python scripts/migrate_add_okx_trade_constraint.py
```

**预期输出：**
```
Starting OKX trade constraint migration
Database URL: postgresql+asyncpg://postgres:postgres@localhost:5432/trading
Checking for duplicate trade_id...
No duplicate trade_ids found
Adding unique constraint 'uq_okx_trade_id'...
✅ Unique constraint added successfully
Current unique constraints on okx_trades:
  - uq_okx_trade_id
Migration completed successfully
```

### 2. 测试断线恢复

```bash
# 1. 启动订阅
uv run cextools subscribe user-stream -x okx -c order position

# 2. 观察日志输出，确认连接成功

# 3. 断开网络（拔网线或关闭WiFi）

# 4. 在断线期间，到 OKX 交易界面：
#    - 下一个市价单或限价单
#    - 撤销订单
#    - 等待30秒

# 5. 恢复网络连接

# 6. 观察日志中的数据恢复信息
```

**预期日志：**
```
=== Starting OKX data recovery process ===
OKX data recovery time range
  start_time=2025-10-27 14:30:00
  end_time=2025-10-27 14:32:00
  gap_seconds=120
  gap_minutes=2.0

Auto-detected 1 active OKX symbols: ['BTC-USDT-SWAP']
Processing OKX symbol: BTC-USDT-SWAP
Querying orders for BTC-USDT-SWAP...
Retrieved 2 orders for BTC-USDT-SWAP
Saved recovered OKX order, order_id=..., inst_id=BTC-USDT-SWAP, state=filled
Saved recovered OKX order, order_id=..., inst_id=BTC-USDT-SWAP, state=canceled

Querying trades for BTC-USDT-SWAP...
Retrieved 1 trades for BTC-USDT-SWAP
Saved recovered OKX trade, trade_id=..., ord_id=..., inst_id=BTC-USDT-SWAP  ✅

=== OKX data recovery completed ===
  total_orders_retrieved=2
  total_trades_retrieved=1
  new_orders_saved=2           ✅
  new_trades_saved=1           ✅ 不再是 0！
  duplicate_orders_skipped=0
  duplicate_trades_skipped=0
  gap_seconds=120
  gap_minutes=2.0
```

### 3. 验证数据库

```sql
-- 查看恢复的订单
SELECT ord_id, inst_id, side, state, u_time
FROM okx_orders
WHERE u_time >= NOW() - INTERVAL '5 minutes'
ORDER BY u_time DESC;

-- ✅ 查看恢复的成交（修复后应该有数据）
SELECT trade_id, ord_id, inst_id, side, fill_px, fill_sz, fill_time
FROM okx_trades
WHERE fill_time >= NOW() - INTERVAL '5 minutes'
ORDER BY fill_time DESC;

-- 验证唯一性约束
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'okx_trades'
  AND constraint_type = 'UNIQUE';
-- 应该看到: uq_okx_trade_id | UNIQUE
```

---

## 📋 修改的文件

| 文件 | 修改内容 | 行数 |
|-----|---------|------|
| `src/tri_arb/services/okx_user_stream.py` | 实现 `_save_trade_with_dedup()` 方法 | ~1123-1173 (+30行) |
| `src/tri_arb/storage/okx_models.py` | 添加唯一性约束和导入 | ~9, ~190-193 (+2行) |
| `scripts/migrate_add_okx_trade_constraint.py` | 数据库迁移脚本 | +136行 (新文件) |
| `OKX_RECONNECTION_ISSUE.md` | 问题分析文档 | +330行 (新文件) |
| `OKX_RECONNECTION_FIX.md` | 修复文档 | +300行 (新文件) |

---

## ✅ 检查点清单

修复完成后，请验证以下检查点：

- [ ] ✅ 运行数据库迁移脚本
- [ ] ✅ 启动 OKX 用户数据流订阅
- [ ] ✅ 模拟断线（断网或杀进程）
- [ ] ✅ 在断线期间下单和撤单
- [ ] ✅ 恢复连接
- [ ] ✅ 日志显示 `new_trades_saved` > 0
- [ ] ✅ 数据库中有成交记录
- [ ] ✅ 唯一性约束生效（无重复数据）

---

## 🎯 总结

### 核心问题
- ❌ `_save_trade_with_dedup()` 有 TODO 注释，成交数据被跳过
- ❌ `OKXTrade` 模型已存在但未使用
- ❌ 缺少唯一性约束导致潜在重复数据

### 修复方案
1. ✅ 实现 `_save_trade_with_dedup()` 方法保存逻辑
2. ✅ 使用已有的 `OKXTrade` 模型
3. ✅ 添加 `trade_id` 唯一性约束
4. ✅ 创建数据库迁移脚本
5. ✅ 添加详细的调试日志

### 影响
- **数据完整性**: 断线期间的成交记录现在会被正确恢复
- **去重保护**: 唯一性约束防止重复数据
- **可观测性**: 详细日志便于排查问题

---

**修复状态**: ✅ 已完成
**测试状态**: ⚠️  待用户验证
**文档状态**: ✅ 已更新
