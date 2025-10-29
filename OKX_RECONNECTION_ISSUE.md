# OKX 断线恢复问题分析

**报告时间**: 2025-10-27
**问题**: 断线期间的订单和撤单没有恢复到数据库

---

## 🔍 问题发现

用户测试命令：
```bash
cextools subscribe user-stream -x okx -c order
```

**测试步骤：**
1. 启动 WebSocket 订阅
2. 断开网络
3. 在断线期间下单和撤单
4. 恢复网络连接

**预期结果：**
- 断线期间的订单应该通过 REST API 恢复到数据库

**实际结果：**
- ❌ 订单没有恢复到数据库

---

## 🐛 根本原因

通过代码审查，发现了**关键问题**：

### 问题1: 成交数据没有被保存 ⚠️ **严重**

**位置**: `src/tri_arb/services/okx_user_stream.py:1123-1146`

```python
async def _save_trade_with_dedup(self, trade_data: dict) -> bool:
    """保存成交数据，自动去重."""
    trade_id = trade_data.get("tradeId", "")

    try:
        async with self.db_manager.session() as session:
            trade_time = datetime.fromtimestamp(int(trade_data.get("ts", 0)) / 1000)

            # ❌ 关键问题：成交数据根本没有被保存！
            # OKX 没有专门的 Trade 表，我们存储到 Order 表中（或者可以扩展模型）
            # 暂时跳过，因为 OKX 的 fills API 返回的数据格式与订单不同
            # TODO: 创建专门的 OKXTrade 模型
            logger.debug(f"OKX trade {trade_id} - skipping (no trade table yet)")
            return False  # ❌ 直接返回 False，数据被丢弃

    except IntegrityError:
        logger.debug(f"OKX trade {trade_id} already exists, skipping")
        return False
```

**问题描述：**
- `_save_trade_with_dedup()` 方法有 TODO 注释
- 成交数据被直接跳过，没有保存到数据库
- 返回 `False`，导致统计也不准确

**影响：**
- 断线恢复时，查询到的成交数据全部被丢弃
- `recovered_trades` 永远是 0
- 成交历史记录缺失

### 问题2: OKXTrade 模型已存在但未使用

**证据：**
```python
# okx_user_stream.py:26 - 已导入
from tri_arb.storage.okx_models import OKXAccountBalance, OKXPosition, OKXOrder, OKXTrade

# okx_models.py:157 - 模型已定义
class OKXTrade(Base):
    __tablename__ = "okx_trades"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    inst_id = Column(String(50), nullable=False, index=True)
    ord_id = Column(String(50), nullable=False, index=True)
    trade_id = Column(String(50), nullable=True, index=True)
    side = Column(String(10), nullable=False)
    fill_px = Column(Numeric(30, 10), nullable=False)  # 成交价格
    fill_sz = Column(Numeric(30, 10), nullable=False)  # 成交数量
    fee = Column(Numeric(30, 10), nullable=True)
    fee_ccy = Column(String(20), nullable=True)
    fill_time = Column(DateTime, nullable=False, index=True)
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

**结论：**
- `OKXTrade` 模型完整定义，可以直接使用
- 只需要实现保存逻辑

---

## 📊 数据恢复流程分析

### 当前流程

```
用户断线
    ↓
重新连接
    ↓
检测到断线记录 ✅
    ↓
触发 query_missing_data() ✅
    ↓
查询订单: exchange.get_all_orders() ✅
    ↓
保存订单: _save_order_with_dedup() ✅
    ↓
查询成交: exchange.get_user_trades() ✅
    ↓
保存成交: _save_trade_with_dedup() ❌ 直接跳过！
    ↓
日志显示: new_trades_saved=0 ❌
```

### OKX API 端点

#### 1. 查询历史订单
```python
# okx_perp.py:730
path="/api/v5/trade/orders-history-archive"
```

#### 2. 查询成交历史
```python
# okx_perp.py:796
path="/api/v5/trade/fills-history"
```

**返回数据格式示例：**
```json
{
  "code": "0",
  "msg": "",
  "data": [
    {
      "instType": "SWAP",
      "instId": "BTC-USDT-SWAP",
      "tradeId": "123456",
      "ordId": "654321",
      "clOrdId": "",
      "billId": "111",
      "tag": "",
      "fillPx": "50000.5",
      "fillSz": "0.01",
      "side": "buy",
      "posSide": "long",
      "execType": "T",
      "feeCcy": "USDT",
      "fee": "-0.025",
      "ts": "1698765432000"
    }
  ]
}
```

---

## 🔧 修复方案

### 修复1: 实现 _save_trade_with_dedup() 方法

**需要修改**: `src/tri_arb/services/okx_user_stream.py:1123-1146`

```python
async def _save_trade_with_dedup(self, trade_data: dict) -> bool:
    """保存成交数据，自动去重.

    Args:
        trade_data: OKX API返回的成交数据

    Returns:
        bool: True 表示新数据已保存，False 表示数据已存在（去重）
    """
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
                fill_px=trade_data.get("fillPx"),
                fill_sz=trade_data.get("fillSz"),
            )
            return True

    except IntegrityError:
        logger.debug(f"OKX trade {trade_id} already exists, skipping")
        return False
    except Exception as e:
        logger.error(f"Failed to save OKX trade {trade_id}", error=str(e), exc_info=True)
        return False
```

### 修复2: 添加唯一性约束（如果没有）

**检查**: `src/tri_arb/storage/okx_models.py:190-192`

可能需要添加：
```python
__table_args__ = (
    Index('idx_okx_trade_inst_time', 'inst_id', 'fill_time'),
    UniqueConstraint('trade_id', name='uq_okx_trade_id'),  # ✅ 添加唯一约束
)
```

---

## ✅ 预期修复后的效果

### 修复前 ❌
```
=== OKX data recovery completed ===
  total_orders_retrieved=5
  total_trades_retrieved=3
  new_orders_saved=5
  new_trades_saved=0          ❌ 永远是 0
  duplicate_orders_skipped=0
  duplicate_trades_skipped=3  ❌ 实际上是全部跳过
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
```

---

## 🧪 验证步骤

### 1. 修复代码后

```bash
# 重启服务
uv run cextools subscribe user-stream -x okx -c order position
```

### 2. 模拟断线测试

```bash
# 1. 启动订阅（观察日志）
# 2. 断开网络（拔网线或关闭WiFi）
# 3. 在断线期间，到OKX交易界面下单和撤单
# 4. 等待30秒
# 5. 恢复网络连接
# 6. 观察日志中的数据恢复信息
```

### 3. 查询数据库验证

```sql
-- 查看恢复的订单
SELECT * FROM okx_orders
WHERE u_time >= NOW() - INTERVAL '5 minutes'
ORDER BY u_time DESC;

-- 查看恢复的成交 ✅ 修复后应该有数据
SELECT * FROM okx_trades
WHERE fill_time >= NOW() - INTERVAL '5 minutes'
ORDER BY fill_time DESC;

-- 查看连接状态
SELECT * FROM connection_status
WHERE exchange = 'okx_perp';
```

---

## 🎯 总结

### 核心问题
- ❌ `_save_trade_with_dedup()` 方法有 TODO，成交数据被直接跳过
- ❌ `OKXTrade` 模型已存在但未使用
- ❌ 导致断线期间的成交记录全部丢失

### 修复方案
1. ✅ 实现 `_save_trade_with_dedup()` 方法保存逻辑
2. ✅ 使用已有的 `OKXTrade` 模型
3. ✅ 添加适当的错误处理和日志
4. ✅ 确保唯一性约束防止重复

### 影响范围
- **文件**: `src/tri_arb/services/okx_user_stream.py`
- **方法**: `_save_trade_with_dedup()`
- **行数**: ~1123-1146
- **修改量**: ~40行代码

---

**状态**: 🔴 待修复
**优先级**: 🔥 高（影响数据完整性）
**预计工作量**: ~30分钟
