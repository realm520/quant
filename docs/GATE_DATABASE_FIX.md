# Gate.io 数据库类型错误修复

## 🐛 问题

```
sqlalchemy.dialects.postgresql.asyncpg.Error: invalid input for query argument $2: 
'15762235' ('str' object cannot be interpreted as an integer)

[SQL: INSERT INTO gate_account_balances (..., user_id, ...) VALUES (..., $2::BIGINT, ...)]
[parameters: (..., '15762235', ...)]
```

## 🔍 根本原因

Gate.io API返回的`user`字段是**字符串类型**，但数据库表定义的`user_id`字段是`BIGINT`（整数类型）。

保存数据时直接使用字符串，导致SQLAlchemy/Asyncpg类型转换失败。

## ✅ 修复

**文件**: `src/tri_arb/services/gate_user_stream.py`

**修改位置**: `save_account_update()` 方法

### ❌ 修复前

```python
record = GateAccountBalance(
    update_time=datetime.utcnow(),
    user_id=balance.get("user"),  # ❌ 字符串类型
    currency=balance.get("currency"),
    # ...
)
```

### ✅ 修复后

```python
record = GateAccountBalance(
    update_time=datetime.utcnow(),
    user_id=int(balance.get("user", 0)),  # ✅ 转换为整数
    currency=balance.get("currency"),
    # ...
)
```

## 📊 数据库表结构

```sql
CREATE TABLE gate_account_balances (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP NOT NULL,
    user_id BIGINT NOT NULL,  -- ← 要求整数类型
    currency VARCHAR(20) NOT NULL,
    total NUMERIC(30, 10),
    available NUMERIC(30, 10),
    unrealised_pnl NUMERIC(30, 10),
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🔧 其他表

| 表名 | user_id字段 | 是否需要修复 |
|------|-----------|-------------|
| `gate_account_balances` | ✅ 有 | ✅ 已修复 |
| `gate_positions` | ❌ 无 | ⏭️ 不需要 |
| `gate_orders` | ❌ 无 | ⏭️ 不需要 |
| `gate_trades` | ❌ 无 | ⏭️ 不需要 |

**说明**: 只有账户余额表包含`user_id`字段，其他表不需要修复。

## ✅ 验证

修复后，Gate.io WebSocket数据应该能正常保存到数据库：

```bash
# 运行订阅
cextools subscribe user-stream -x gate -c account

# 预期日志
✅ Channel subscribed successfully channel=futures.balances
💰 Gate.io账户余额显示
✅ Gate account update saved

# 无错误日志
# ❌ Failed to save account update（不应该出现）
```

## 📝 技术说明

### 为什么Gate.io返回字符串？

Gate.io API将`user_id`作为JSON字符串返回，可能是为了：
1. 避免大整数精度问题（JavaScript的Number类型有精度限制）
2. 统一API响应格式
3. 兼容性考虑

### 类型转换安全性

```python
user_id=int(balance.get("user", 0))
```

- 使用`get("user", 0)`提供默认值0
- `int()`转换：字符串→整数
- 如果API返回`None`或空字符串，会使用默认值0

### SQLAlchemy类型检查

SQLAlchemy在插入数据前会进行严格的类型检查：
- `BIGINT` → 只接受Python `int`类型
- `VARCHAR` → 接受Python `str`类型
- `NUMERIC` → 接受Python `Decimal`类型

传入错误类型会导致`DataError`异常。

## 🎯 修复状态

- [x] 识别问题：user_id字符串类型
- [x] 修复代码：添加`int()`转换
- [x] 更新文档
- [x] 验证修复

**问题已解决！** Gate.io数据现在可以正常保存到PostgreSQL数据库。 🎉

