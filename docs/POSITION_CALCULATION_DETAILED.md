# 持仓量计算详细说明

## 计算逻辑

### 1. 昨日多头持仓量（pre_long_qty）

```
pre_long_qty = initial_long_qty + buy_volume

其中：
- initial_long_qty: 区间开始时的多头持仓（之前遗留的未平仓的买单）
- buy_volume: 区间内所有 BUY 订单的成交量之和
```

**计算步骤**：
1. 查询区间开始时间之前最后一次持仓更新，获取多头持仓量（initial_long_qty）
2. 查询区间内所有 BUY 订单，累加成交量（buy_volume）
3. 相加得到总多头持仓量

### 2. 昨日空头持仓量（pre_short_qty）

```
pre_short_qty = initial_short_qty + sell_volume

其中：
- initial_short_qty: 区间开始时的空头持仓（之前遗留的未平仓的卖单）
- sell_volume: 区间内所有 SELL 订单的成交量之和
```

**计算步骤**：
1. 查询区间开始时间之前最后一次持仓更新，获取空头持仓量（initial_short_qty）
2. 查询区间内所有 SELL 订单，累加成交量（sell_volume）
3. 相加得到总空头持仓量

### 3. 昨日多头市值（pre_long_value）

```
pre_long_value = initial_long_value + sum(buy_trade_value)

其中：
- initial_long_value: 区间开始时的多头持仓市值
- buy_trade_value: 每笔 BUY 订单的市值 = 成交价格 × 成交数量 × 合约乘数

每笔 BUY 订单的市值计算：
buy_trade_value = price × quantity × contract_multiplier
```

**计算步骤**：
1. 查询区间开始时间之前最后一次持仓更新，计算多头持仓市值：
   ```
   initial_long_value = initial_long_qty × entry_price × contract_multiplier
   ```

2. 遍历区间内所有 BUY 订单，计算每笔市值并累加：
   ```
   for each BUY trade:
       trade_value = trade.price × trade.quantity × contract_multiplier
       sum(buy_trade_value) += trade_value
   ```

3. 相加得到总多头市值：
   ```
   pre_long_value = initial_long_value + sum(buy_trade_value)
   ```

### 4. 昨日空头市值（pre_short_value）

```
pre_short_value = initial_short_value + sum(sell_trade_value)

其中：
- initial_short_value: 区间开始时的空头持仓市值
- sell_trade_value: 每笔 SELL 订单的市值 = 成交价格 × 成交数量 × 合约乘数

每笔 SELL 订单的市值计算：
sell_trade_value = price × quantity × contract_multiplier
```

**计算步骤**：
1. 查询区间开始时间之前最后一次持仓更新，计算空头持仓市值：
   ```
   initial_short_value = initial_short_qty × entry_price × contract_multiplier
   ```

2. 遍历区间内所有 SELL 订单，计算每笔市值并累加：
   ```
   for each SELL trade:
       trade_value = trade.price × trade.quantity × contract_multiplier
       sum(sell_trade_value) += trade_value
   ```

3. 相加得到总空头市值：
   ```
   pre_short_value = initial_short_value + sum(sell_trade_value)
   ```

## 合约乘数（Contract Multiplier）

### 定义

**合约乘数** = 每张期货合约包含的基础资产数量

### 常见值

- **大多数永续合约**：合约乘数 = 1
  - 例如：BTC/USDT 永续合约，1 张合约 = 1 BTC
  - 例如：ETH/USDT 永续合约，1 张合约 = 1 ETH

- **部分合约**：合约乘数 ≠ 1
  - 例如：某些小型币种，1 张合约 = 0.01 BTC
  - 例如：某些反向合约，1 张合约 = 100 USDT

### 获取方式

1. **从交易所 API 获取**：
   - Binance: `/fapi/v1/exchangeInfo` 返回 `contractSize` 字段
   - XT: 从交易对信息中获取 `contractSize` 字段

2. **默认值**：
   - 如果无法获取，默认使用 1（大多数情况）

### 计算示例

假设：
- 合约乘数 = 1（1 张合约 = 1 BTC）
- 成交价格 = 50000 USDT
- 成交数量 = 0.5 BTC

**市值计算**：
```
市值 = 50000 × 0.5 × 1 = 25000 USDT
```

如果合约乘数 = 0.01（1 张合约 = 0.01 BTC）：
```
市值 = 50000 × 0.5 × 0.01 = 250 USDT
```

## 完整计算示例

### 场景设置

- **区间**：2024-01-01 00:00:00 到 2024-01-02 00:00:00（24小时）
- **交易对**：BTC/USDT
- **合约乘数**：1

### 初始持仓（区间开始时）

- 多头持仓：1.0 BTC，开仓均价：45000 USDT
- 空头持仓：0.5 BTC，开仓均价：46000 USDT

### 区间内成交记录

| 时间 | 方向 | 价格 | 数量 | 市值计算 |
|------|------|------|------|----------|
| 10:00 | BUY | 50000 | 0.2 | 50000 × 0.2 × 1 = 10000 |
| 12:00 | BUY | 51000 | 0.3 | 51000 × 0.3 × 1 = 15300 |
| 14:00 | SELL | 52000 | 0.1 | 52000 × 0.1 × 1 = 5200 |
| 16:00 | SELL | 53000 | 0.2 | 53000 × 0.2 × 1 = 10600 |

### 计算结果

**1. 昨日多头持仓量（pre_long_qty）**：
```
initial_long_qty = 1.0 BTC
buy_volume = 0.2 + 0.3 = 0.5 BTC
pre_long_qty = 1.0 + 0.5 = 1.5 BTC
```

**2. 昨日空头持仓量（pre_short_qty）**：
```
initial_short_qty = 0.5 BTC
sell_volume = 0.1 + 0.2 = 0.3 BTC
pre_short_qty = 0.5 + 0.3 = 0.8 BTC
```

**3. 昨日多头市值（pre_long_value）**：
```
initial_long_value = 1.0 × 45000 × 1 = 45000 USDT
buy_trade_value_sum = 10000 + 15300 = 25300 USDT
pre_long_value = 45000 + 25300 = 70300 USDT
```

**4. 昨日空头市值（pre_short_value）**：
```
initial_short_value = 0.5 × 46000 × 1 = 23000 USDT
sell_trade_value_sum = 5200 + 10600 = 15800 USDT
pre_short_value = 23000 + 15800 = 38800 USDT
```

## 数据表查询

### 1. 查询初始持仓

**Binance**：
```sql
SELECT symbol, position_side, position_amount, entry_price, event_time
FROM binance_account_update
WHERE event_time < '2024-01-01 00:00:00'
  AND event_type = 'POSITION_UPDATE'
  AND position_amount != 0
  AND account_id = 'binance_main_001'
ORDER BY event_time DESC
-- 然后按 symbol + position_side 分组，取每组最新的记录
```

**XT**：
```sql
SELECT symbol, side, quantity, entry_price, update_time
FROM xt_position_update
WHERE update_time < '2024-01-01 00:00:00'
  AND quantity > 0
  AND account_id = 'xt_main_001'
ORDER BY update_time DESC
-- 然后按 symbol + side 分组，取每组最新的记录
```

### 2. 查询区间内成交记录

**Binance**：
```sql
SELECT side, price, quantity, transaction_time
FROM binance_trade_update
WHERE transaction_time >= '2024-01-01 00:00:00'
  AND transaction_time < '2024-01-02 00:00:00'
  AND exchange = 'binance_perp'
  AND account_id = 'binance_main_001'
ORDER BY transaction_time
```

**XT**：
```sql
SELECT side, price, quantity, update_time
FROM xt_trade_update
WHERE update_time >= '2024-01-01 00:00:00'
  AND update_time < '2024-01-02 00:00:00'
  AND account_id = 'xt_main_001'
ORDER BY update_time
```

## 注意事项

1. **合约乘数**：
   - 需要从交易所 API 获取每个交易对的合约乘数
   - 如果无法获取，默认使用 1
   - 不同交易对的合约乘数可能不同

2. **时间范围**：
   - 使用 UTC 时间，确保跨时区一致性
   - 区间是左闭右开：[start_time, end_time)

3. **数据完整性**：
   - 确保 WebSocket 连接稳定，避免成交记录丢失
   - 如果成交记录不完整，计算结果会不准确

4. **初始持仓**：
   - 如果区间开始之前没有持仓记录，初始持仓为 0
   - 这是正确的行为：如果之前没有持仓，就从 0 开始计算

5. **市值计算**：
   - 每笔成交的市值 = 成交价格 × 成交数量 × 合约乘数
   - 初始持仓市值 = 初始持仓量 × 开仓均价 × 合约乘数
   - 总市值 = 初始持仓市值 + 区间内所有成交市值之和

