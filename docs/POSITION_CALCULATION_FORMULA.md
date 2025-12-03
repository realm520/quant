# 持仓与交易统计计算逻辑文档

本文档详细说明所有持仓和交易指标的计算公式，用于验证代码实现的正确性。

## 1. 昨收持仓

**定义**：昨日结束时的持仓量和市值（即昨日 00:00 之前的持仓 + 昨日一整天的成交）

### 计算公式

```
pre_long_qty = initial_long_qty + buy_volume
pre_short_qty = initial_short_qty + sell_volume
pre_long_value = initial_long_value + buy_trade_value
pre_short_value = initial_short_value + sell_trade_value
```

其中：
- `initial_long_qty` / `initial_short_qty`: **昨日 00:00 之前**最后一次持仓记录的数量
- `buy_volume` / `sell_volume`: **昨日 00:00 ~ 昨日 24:00** 的成交数量
- `initial_long_value` / `initial_short_value`: 昨日 00:00 之前的持仓市值 = `持仓量 × 开仓均价 × 合约乘数`
- `buy_trade_value` / `sell_trade_value`: 昨日一整天的成交市值 = `∑(成交价格 × 成交数量 × 合约乘数)`

### 数据来源

- **初始持仓**：从 `xt_position_update` 或 `binance_account_update` 表中查询 `update_time < 昨日00:00` 的最后一条记录
- **成交记录**：从 `xt_trade_update` 或 `binance_trade_update` 表中查询 `update_time >= 昨日00:00 AND update_time < 昨日24:00` 的所有记录

---

## 2. 今日交易

**定义**：今日的交易量和市值（昨收持仓 + 今日成交）

### 计算公式

```
long_qty = sum(buy_vol) + pre_long_qty
short_qty = sum(sell_vol) + pre_short_qty
long_value = sum(buy_vol * buy_price * 合约乘数) + pre_long_value
short_value = sum(sell_vol * sell_price * 合约乘数) + pre_short_value
```

**注意**：这里的 `sum(buy_vol)` 是**今日 00:00 ~ 当前时间**的买单成交量。

### 平均价格（不可舍入）

```
avg_buy_prz = long_value / long_qty  (当 long_qty > 0 时)
avg_sell_prz = short_value / short_qty  (当 short_qty > 0 时)
```

**重要**：使用 `Decimal` 类型进行除法运算，不进行四舍五入，保持精确精度。

### 数据来源

- **昨收持仓**：使用第1步计算的结果
- **今日成交**：从成交表中查询 `update_time >= 今日00:00 AND update_time < 当前时间` 的所有记录

---

## 3. 已实现 Pnl 计算

### 计算公式

```
matched_qty = min(long_qty, short_qty)
realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)
```

**说明**：
- `matched_qty`：可以轧差的数量（多头和空头中较小的那个）
- `realized_pnl`：已实现盈亏 = 轧差数量 × (卖出均价 - 买入均价)

---

## 4. 当日剩余仓位

**定义**：当日未轧差的持仓，将作为下一日的"昨日持仓"

### 计算公式

```
left_long_qty = long_qty - matched_qty
left_short_qty = short_qty - matched_qty
left_long_value = left_long_qty * avg_buy_prz
left_short_value = left_short_qty * avg_sell_prz
```

### 当日最后一笔成交价

```
close_prz = 当日最后一笔成交的价格
```

从成交表中查询 `update_time >= 今日00:00 AND update_time < 当前时间` 的最大 `update_time` 对应的 `price`。

### 当日未实现盈亏

```
unrealized_pnl = left_long_qty * (close_prz - avg_buy_prz) + left_short_qty * (avg_sell_prz - close_prz)
```

**说明**：
- 多头未实现盈亏 = 剩余多头持仓 × (当前价格 - 买入均价)
- 空头未实现盈亏 = 剩余空头持仓 × (卖出均价 - 当前价格)

---

## 5. Pnl 汇总

### 单日 PnL

```
daily_pnl = realized_pnl + unrealized_pnl
```

### 多日 PnL

```
多日pnl = sum(所有已实现盈亏) + 最后一期的未实现盈亏
```

**计算逻辑**：
- 对每一天，计算当天的 `realized_pnl` 和 `unrealized_pnl`
- 累计所有已实现盈亏：`cumulative_realized_pnl = sum(所有天的 realized_pnl)`
- 累计 PnL = `cumulative_realized_pnl + 最后一期的 unrealized_pnl`

---

## 完整计算流程示例

### 场景：计算 12月3日 的持仓和交易统计

#### 步骤 1：获取昨收持仓（12月2日结束时的持仓）

```
initial_long_qty = 12月2日 00:00 之前的最后一笔多头持仓 = 15428
initial_short_qty = 12月2日 00:00 之前的最后一笔空头持仓 = 53
buy_volume = 12月2日 00:00 ~ 12月2日 24:00 的买单成交量 = 978728
sell_volume = 12月2日 00:00 ~ 12月2日 24:00 的卖单成交量 = 981019

pre_long_qty = 15428 + 978728 = 994156
pre_short_qty = 53 + 981019 = 981072
```

#### 步骤 2：计算今日交易（12月3日 00:00 ~ 当前时间）

```
今日 buy_volume = 12月3日 00:00 ~ 当前时间的买单成交量
今日 sell_volume = 12月3日 00:00 ~ 当前时间的卖单成交量

long_qty = pre_long_qty + 今日 buy_volume
short_qty = pre_short_qty + 今日 sell_volume
long_value = pre_long_value + 今日 buy_trade_value
short_value = pre_short_value + 今日 sell_trade_value

avg_buy_prz = long_value / long_qty
avg_sell_prz = short_value / short_qty
```

#### 步骤 3：计算已实现 Pnl

```
matched_qty = min(long_qty, short_qty)
realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)
```

#### 步骤 4：计算当日剩余仓位

```
left_long_qty = long_qty - matched_qty
left_short_qty = short_qty - matched_qty
left_long_value = left_long_qty * avg_buy_prz
left_short_value = left_short_qty * avg_sell_prz

close_prz = 12月3日最后一笔成交的价格
unrealized_pnl = left_long_qty * (close_prz - avg_buy_prz) + left_short_qty * (avg_sell_prz - close_prz)
```

#### 步骤 5：计算单日 PnL

```
daily_pnl = realized_pnl + unrealized_pnl
```

---

## 数据表结构

### XT 交易所

- **持仓表**: `xt_position_update`
  - `symbol`: 交易对（如 `iota_usdt`）
  - `side`: 方向（`LONG` / `SHORT`）
  - `quantity`: 持仓数量
  - `entry_price`: 开仓均价
  - `update_time`: 更新时间
  - `account_id`: 账号ID

- **成交表**: `xt_trade_update`
  - `symbol`: 交易对
  - `side`: 方向（`BUY` / `SELL`）
  - `price`: 成交价格
  - `quantity`: 成交数量
  - `update_time`: 成交时间
  - `account_id`: 账号ID

### Binance 交易所

- **持仓表**: `binance_account_update`
  - `symbol`: 交易对（如 `BTCUSDT`）
  - `position_side`: 方向（`LONG` / `SHORT`）
  - `position_amount`: 持仓数量
  - `entry_price`: 开仓均价
  - `event_time`: 事件时间
  - `account_id`: 账号ID

- **成交表**: `binance_trade_update`
  - `symbol`: 交易对
  - `side`: 方向（`BUY` / `SELL`）
  - `price`: 成交价格
  - `quantity`: 成交数量
  - `transaction_time`: 成交时间
  - `account_id`: 账号ID

---

## 验证方法

### 1. 验证昨收持仓

使用 SQL 查询验证 `pre_long_qty` 和 `pre_short_qty`：
- 查询昨日 00:00 之前的最后持仓
- 查询昨日一整天的成交
- 相加验证结果

详见：`docs/VERIFY_YESTERDAY_POSITION_SQL.md`

### 2. 验证今日交易

使用 SQL 查询验证 `long_qty` 和 `short_qty`：
- 查询昨收持仓（使用步骤1的结果）
- 查询今日 00:00 ~ 当前时间的成交
- 相加验证结果

### 3. 验证已实现 Pnl

手动计算：
```
matched_qty = min(long_qty, short_qty)
realized_pnl = matched_qty * (avg_sell_prz - avg_buy_prz)
```

### 4. 验证未实现 Pnl

手动计算：
```
unrealized_pnl = left_long_qty * (close_prz - avg_buy_prz) + left_short_qty * (avg_sell_prz - close_prz)
```

---

## 注意事项

1. **时间区间**：
   - 昨收持仓：使用"昨日 00:00 ~ 昨日 24:00"的区间
   - 今日交易：使用"今日 00:00 ~ 当前时间"的区间

2. **合约乘数**：
   - 大多数 USDT 永续合约的合约乘数为 1
   - 可通过 XT API 的 `symbol/detail` 接口获取 `contractSize` 字段
   - Binance 的 USDT 永续合约通常为 1

3. **精度**：
   - 所有计算使用 `Decimal` 类型，避免浮点数精度问题
   - 平均价格不进行四舍五入，保持精确精度

4. **账号和币种**：
   - 所有计算都按 `account_id` 和 `symbol` 分别进行
   - 不进行跨账号或跨币种的汇总

