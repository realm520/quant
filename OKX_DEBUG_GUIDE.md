# OKX 断线恢复调试指南

**创建时间**: 2025-10-28
**问题**: 断网期间的订单和撤单没有恢复到数据库

---

## 🔍 问题排查

### 现象
用户测试 `cextools subscribe user-stream -x okx -c order` 时：
1. 断开网络
2. 在 OKX 交易界面下单和撤单
3. 恢复网络
4. **订单没有恢复到数据库**

### 已完成的修复
✅ 修改 API 端点：从 `orders-history-archive` 改为 `orders-history`
✅ 实现成交数据保存方法
✅ 添加唯一性约束
✅ 添加控制台显示功能

---

## 📝 测试步骤

### 1. 启动订阅（带详细日志）

```bash
# 启动 OKX 用户数据流订阅
cextools subscribe user-stream -x okx -c order --debug
```

**预期输出：**
```
OKX用户数据流订阅服务
数据库: localhost:5432/trading
订阅频道: order
数据同步: 启用
按 Ctrl+C 停止订阅

✅ 服务已启动
正在连接WebSocket...
```

### 2. 等待连接成功

**预期日志：**
```
OKX WebSocket connected
OKX WebSocket login successful
Subscribed to OKX channels
```

### 3. 断开网络

- Mac: 关闭 WiFi 或拔网线
- Linux: `sudo ifconfig eth0 down`

**预期日志：**
```
Connection lost
last_connected_at=...
disconnect_time=...
```

### 4. 在断网期间下单

打开 OKX 交易界面（Web或App）：
1. **下一个限价单**（比如 BTC-USDT-SWAP，少量）
2. **等待2-3秒**
3. **撤销这个订单**
4. **等待30秒以上**

### 5. 恢复网络连接

- Mac: 打开 WiFi
- Linux: `sudo ifconfig eth0 up`

### 6. 观察恢复日志

**关键日志检查点：**

#### ✅ 检查点1: API 端点选择
```
Using orders-history endpoint for recent orders
symbol=BTC-USDT-SWAP
start_time=1730094000000
end_time=1730094120000
params={'instType': 'SWAP', 'instId': 'BTC-USDT-SWAP', 'begin': '1730094000000', 'end': '1730094120000', 'limit': '100'}
```

**验证：**
- [ ] 使用的是 `orders-history`（不是 archive）
- [ ] `instType` 是 `SWAP`（合约）
- [ ] `begin` < `end`（时间范围正确）
- [ ] `begin` 和 `end` 覆盖了断网期间

#### ✅ 检查点2: API 响应
```
OKX API response for orders
code=0
msg=
endpoint=/api/v5/trade/orders-history
data_count=2
```

**验证：**
- [ ] `code=0`（成功）
- [ ] `data_count > 0`（查到订单）

#### ✅ 检查点3: 订单保存
```
Retrieved 2 orders for BTC-USDT-SWAP

🔄 恢复订单 - 14:52:38
╭─────────────────┬─────────────────────╮
│ 产品            │ BTC-USDT-SWAP       │
│ 订单ID          │ 2990770989367091200 │
│ 状态            │ CANCELED            │
│ 方向            │ BUY                 │
╰─────────────────┴─────────────────────╯
✅ 订单已恢复到数据库
```

**验证：**
- [ ] 看到 "Retrieved X orders"（X > 0）
- [ ] 看到订单详情表格
- [ ] 看到 "✅ 订单已恢复到数据库"

#### ✅ 检查点4: 恢复总结
```
     📊 数据恢复总结
╔══════════════════════╦════════╗
║ 项目                 ║ 数量   ║
╠══════════════════════╬════════╣
║ 断线时长             ║ 120 秒 ║
║ 查询交易对           ║ 1      ║
║ ━━━━━━━━━━━━━━━━━━━━ ║ ━━━━━  ║
║ 查询到的订单         ║ 2      ║
║ 恢复到数据库         ║ 2      ║
║ 跳过重复订单         ║ 0      ║
╚══════════════════════╩════════╝

✅ 数据恢复成功！恢复了 2 个订单和 0 个成交
```

**验证：**
- [ ] 查询到的订单 > 0
- [ ] 恢复到数据库 > 0

---

## 🔧 如果仍然查不到订单

### 场景1: API返回code≠0

**日志示例：**
```
OKX API error: code=50004, msg=Invalid parameter
```

**排查：**
1. 检查 `params` 中的参数格式
2. 确认 `instId` 符合 OKX 格式（如 `BTC-USDT-SWAP`）
3. 确认时间范围不超过90天

### 场景2: 返回0个订单

**日志示例：**
```
OKX API response for orders
code=0
msg=
data_count=0
```

**可能原因：**

#### A. 订单在断网前就已完成
```
14:52:01 - 订单创建（WebSocket推送并保存）✅
14:52:26 - 订单撤销（WebSocket推送并保存）✅
14:52:29 - WebSocket断线 ❌
14:52:36 - WebSocket重连 ✅

REST API查询范围: 14:52:29 - 14:52:36
结果: 0 个订单（因为订单在断线之前）
```

**解决办法：** 确保在**断网之后**才下单

#### B. 交易对不匹配
- WebSocket 订阅的是 `BTC-USDT-SWAP`
- 但你下单的是 `ETH-USDT-SWAP`

**解决办法：** 确保在相同的交易对下单

#### C. instType 不匹配
- 代码查询的是 `SWAP`（永续合约）
- 但你下单的是现货

**解决办法：** 确保使用永续合约交易（你已确认只用合约）

### 场景3: 查到订单但没保存

**日志示例：**
```
Retrieved 2 orders for BTC-USDT-SWAP
（没有后续的表格显示）
```

**排查：**
```sql
-- 检查数据库中是否有订单
SELECT ord_id, inst_id, state, u_time
FROM okx_orders
ORDER BY u_time DESC
LIMIT 10;
```

**可能原因：**
- 数据库连接问题
- 保存过程抛异常但被捕获
- 去重逻辑误判

---

## 🗃️ 数据库验证

### 查看最近的订单
```sql
SELECT
    ord_id,
    inst_id,
    side,
    state,
    px,
    sz,
    u_time
FROM okx_orders
WHERE u_time >= NOW() - INTERVAL '1 hour'
ORDER BY u_time DESC;
```

### 查看最近的成交
```sql
SELECT
    trade_id,
    ord_id,
    inst_id,
    side,
    fill_px,
    fill_sz,
    fill_time
FROM okx_trades
WHERE fill_time >= NOW() - INTERVAL '1 hour'
ORDER BY fill_time DESC;
```

### 检查连接状态
```sql
SELECT
    exchange,
    is_connected,
    last_connected_at,
    last_disconnected_at,
    last_data_gap_seconds,
    total_reconnect_count
FROM connection_status
WHERE exchange = 'okx_perp';
```

---

## 📊 测试用例

### 用例1: 单笔限价单（最简单）
1. 断网
2. 下一个限价单（BTC-USDT-SWAP，0.001 BTC）
3. 等待60秒
4. 恢复网络
5. **预期**: 查到1个订单，状态为 `live` 或 `canceled`

### 用例2: 下单后立即撤单
1. 断网
2. 下一个限价单
3. 立即撤销这个订单
4. 等待60秒
5. 恢复网络
6. **预期**: 查到1个订单，状态为 `canceled`

### 用例3: 市价单成交
1. 断网
2. 下一个市价单（会立即成交）
3. 等待60秒
4. 恢复网络
5. **预期**: 查到1个订单（状态 `filled`）+ 1个成交

---

## 🐛 已知问题

### 问题1: 时间范围计算
- `start_time`: 从 `last_disconnected_at` 开始
- `end_time`: 到 `now()` 结束
- **注意**: 如果断线时间太短（<1秒），可能查不到数据

### 问题2: OKX API 限流
- OKX限制: 每2秒最多10个请求
- 如果有多个交易对，可能触发限流

### 问题3: 订单状态过滤
- OKX API 默认返回所有状态的订单
- 不需要额外的状态过滤参数

---

## 📝 收集调试信息

如果问题仍然存在，请收集以下信息：

1. **完整日志**（包含时间戳）
   ```bash
   cextools subscribe user-stream -x okx -c order --debug 2>&1 | tee okx_debug.log
   ```

2. **关键信息：**
   - 断网时间（精确到秒）
   - 下单时间（精确到秒）
   - 恢复网络时间（精确到秒）
   - 订单ID（从 OKX 交易界面复制）
   - 交易对名称（如 BTC-USDT-SWAP）

3. **API 响应：**
   - `code` 和 `msg`
   - `data_count`
   - `params` 中的时间范围

4. **数据库查询结果：**
   ```sql
   SELECT * FROM connection_status WHERE exchange = 'okx_perp';
   SELECT * FROM okx_orders ORDER BY u_time DESC LIMIT 5;
   ```

---

**状态**: 🔍 等待用户测试反馈
**优先级**: 🔥 高（核心功能）
