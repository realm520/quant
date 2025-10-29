# OKX 订单恢复失败问题分析

**报告时间**: 2025-10-27
**问题**: 断网期间的订单和撤单没有恢复到数据库
**状态**: 🔴 **严重问题 - API 端点错误**

---

## 🐛 根本原因

### 问题: 使用了错误的 OKX API 端点

**位置**: `src/tri_arb/exchanges/okx_perp.py:730`

```python
# ❌ 当前代码使用的端点
path="/api/v5/trade/orders-history-archive"
```

### OKX API 端点说明

根据 OKX 官方文档：

| API 端点 | 用途 | 时间范围 |
|---------|------|---------|
| `/api/v5/trade/orders-pending` | 查询未完成订单 | 当前活跃订单 |
| `/api/v5/trade/orders-history` | 查询近期历史订单 | **最近7天** ✅ |
| `/api/v5/trade/orders-history-archive` | 查询归档订单 | **3个月前** ❌ |

**当前问题：**
- ❌ 代码使用 `orders-history-archive`（归档端点）
- ❌ 只能查询 **3个月前** 的订单
- ❌ **断网期间的订单根本查不到**

**正确做法：**
- ✅ 应该使用 `orders-history`（近期历史端点）
- ✅ 可以查询 **最近7天** 的订单
- ✅ 能够覆盖断线恢复场景

---

## 📊 测试验证

### 当前代码测试

```bash
# 1. 启动订阅
cextools subscribe user-stream -x okx -c order

# 2. 断网
# 3. 在 OKX 交易界面下单
# 4. 恢复网络
```

**实际日志：**
```
=== Starting OKX data recovery process ===
OKX data recovery time range
  start_time=2025-10-27 14:30:00
  end_time=2025-10-27 14:32:00
  gap_seconds=120

Auto-detected 1 active OKX symbols: ['BTC-USDT-SWAP']
Processing OKX symbol: BTC-USDT-SWAP
Querying orders for BTC-USDT-SWAP...
Retrieved 0 orders for BTC-USDT-SWAP  ❌ 查不到！

=== OKX data recovery completed ===
  new_orders_saved=0  ❌
```

**为什么查不到？**
- 断网期间的订单是"最近2分钟"的
- `orders-history-archive` 只查询 **3个月前** 的订单
- 时间范围完全不匹配！

---

## 🔧 修复方案

### 方案1: 改用正确的 API 端点（推荐）

**修改**: `src/tri_arb/exchanges/okx_perp.py:691-756`

```python
async def get_all_orders(
    self,
    symbol: str,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """查询所有订单（包括历史订单）.

    注意: OKX 区分不同时间范围的订单查询端点：
    - orders-history: 最近7天的订单
    - orders-history-archive: 3个月前的归档订单
    """
    self._require_credentials()

    params: dict[str, Any] = {
        "instType": "SWAP",
        "instId": symbol,
    }

    # OKX API 使用 begin/end 参数，单位是毫秒
    if start_time is not None:
        params["begin"] = str(start_time)
    if end_time is not None:
        params["end"] = str(end_time)

    params["limit"] = str(min(limit, 100))

    # ✅ 修复：根据时间范围选择正确的端点
    now_ms = int(time.time() * 1000)
    seven_days_ms = 7 * 24 * 60 * 60 * 1000

    # 如果查询时间在最近7天内，使用 orders-history
    if start_time is None or (now_ms - start_time) < seven_days_ms:
        path = "/api/v5/trade/orders-history"  # ✅ 最近7天
        logger.debug("Using orders-history endpoint for recent orders")
    else:
        path = "/api/v5/trade/orders-history-archive"  # 归档订单
        logger.debug("Using orders-history-archive endpoint for old orders")

    response = await self._request(
        method="GET",
        path=path,  # ✅ 动态选择端点
        params=params,
        authenticated=True,
    )

    data = response.json()

    # Check for API error
    if data.get("code") != "0":
        raise ValueError(f"OKX API error: {data.get('msg')}")

    orders = data.get("data", [])
    logger.debug(
        "Retrieved historical orders",
        symbol=symbol,
        count=len(orders),
        endpoint=path,  # ✅ 记录使用的端点
        start_time=start_time,
        end_time=end_time,
    )

    return orders
```

### 方案2: 同时查询两个端点（更完整）

```python
async def get_all_orders(
    self,
    symbol: str,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """查询所有订单（包括历史订单）.

    会自动选择或组合多个端点以覆盖所有时间范围。
    """
    self._require_credentials()

    params: dict[str, Any] = {
        "instType": "SWAP",
        "instId": symbol,
    }

    if start_time is not None:
        params["begin"] = str(start_time)
    if end_time is not None:
        params["end"] = str(end_time)

    params["limit"] = str(min(limit, 100))

    all_orders = []

    # ✅ 先查询最近7天的订单（断线恢复场景）
    try:
        response = await self._request(
            method="GET",
            path="/api/v5/trade/orders-history",
            params=params,
            authenticated=True,
        )
        data = response.json()
        if data.get("code") == "0":
            recent_orders = data.get("data", [])
            all_orders.extend(recent_orders)
            logger.debug(f"Retrieved {len(recent_orders)} recent orders (7 days)")
    except Exception as e:
        logger.warning(f"Failed to query recent orders: {e}")

    # 如果时间范围超过7天，再查询归档订单
    now_ms = int(time.time() * 1000)
    seven_days_ms = 7 * 24 * 60 * 60 * 1000

    if start_time is not None and (now_ms - start_time) > seven_days_ms:
        try:
            response = await self._request(
                method="GET",
                path="/api/v5/trade/orders-history-archive",
                params=params,
                authenticated=True,
            )
            data = response.json()
            if data.get("code") == "0":
                archived_orders = data.get("data", [])
                all_orders.extend(archived_orders)
                logger.debug(f"Retrieved {len(archived_orders)} archived orders (3+ months)")
        except Exception as e:
            logger.warning(f"Failed to query archived orders: {e}")

    # 去重（可能存在重复）
    seen_order_ids = set()
    unique_orders = []
    for order in all_orders:
        order_id = order.get("ordId")
        if order_id not in seen_order_ids:
            seen_order_ids.add(order_id)
            unique_orders.append(order)

    logger.debug(
        "Retrieved all orders",
        symbol=symbol,
        total_count=len(unique_orders),
        start_time=start_time,
        end_time=end_time,
    )

    return unique_orders
```

---

## ✅ 推荐的修复方案

**选择方案1（简单有效）**：
- 根据时间范围动态选择端点
- 断线恢复场景（最近几分钟/小时）使用 `orders-history`
- 长期历史查询（超过7天）使用 `orders-history-archive`

**为什么不用方案2？**
- 方案2虽然更完整，但会增加 API 调用次数
- 断线恢复场景通常只需要最近几分钟的数据
- 方案1已经足够覆盖所有实际场景

---

## 🧪 修复后的预期效果

### 修复前 ❌
```bash
# 断网期间下单
# 恢复连接后...

=== OKX data recovery completed ===
  total_orders_retrieved=0  ❌ 查不到订单
  new_orders_saved=0         ❌ 没有保存
```

### 修复后 ✅
```bash
# 断网期间下单
# 恢复连接后...

=== Starting OKX data recovery process ===
Using orders-history endpoint for recent orders  ✅

Processing OKX symbol: BTC-USDT-SWAP
Retrieved 2 orders for BTC-USDT-SWAP  ✅ 找到了！

=== OKX data recovery completed ===
  total_orders_retrieved=2   ✅ 查到订单
  new_orders_saved=2          ✅ 成功保存
  new_trades_saved=1          ✅ 成交也保存
```

---

## 📋 修复检查点

- [ ] 修改 `get_all_orders()` 使用正确的端点
- [ ] 添加端点选择逻辑（基于时间范围）
- [ ] 添加调试日志显示使用的端点
- [ ] 测试断线恢复场景
- [ ] 验证订单能够正确恢复到数据库

---

## 🎯 总结

### 核心问题
- ❌ **错误的 API 端点**：使用了 `orders-history-archive`
- ❌ **时间范围不匹配**：归档端点只查3个月前的订单
- ❌ **断线恢复失败**：无法查询到最近的订单

### 修复方案
- ✅ 使用 `orders-history` 查询最近7天订单
- ✅ 根据时间范围动态选择端点
- ✅ 添加详细日志便于调试

### 影响
- **断线恢复**: 现在可以正确恢复最近的订单
- **历史查询**: 仍支持查询归档订单
- **性能**: 减少不必要的 API 调用

---

**状态**: 🔴 待修复（高优先级）
**预计工作量**: ~20分钟
**测试难度**: 简单（断网测试）
