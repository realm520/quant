# 持仓查询 API 更新说明

## 📋 更新概述

已将币安合约持仓查询功能从 **V3 API** 切换到 **V2 API**。

## 🔄 主要变更

### API 端点变更
- **之前**：`GET /fapi/v3/positionRisk`
- **现在**：`GET /fapi/v2/positionRisk`

### 返回字段变更

#### ✅ V2 新增/保留的字段
- `leverage` - 当前杠杆倍数（直接返回，无需计算）⭐
- `marginType` - 保证金类型（isolated/cross）⭐
- `maxNotionalValue` - 最大名义价值
- `isAutoAddMargin` - 是否自动追加保证金

#### ❌ V3 特有字段（已移除）
- `initialMargin` - 初始保证金
- `maintMargin` - 维持保证金
- `positionInitialMargin` - 仓位初始保证金
- `openOrderInitialMargin` - 订单初始保证金
- `adl` - ADL队列等级
- `bidNotional` - 买单名义价值
- `askNotional` - 卖单名义价值
- `marginAsset` - 保证金资产

#### ✅ 两版本共有字段
- `symbol` - 交易对
- `positionSide` - 持仓方向
- `positionAmt` - 持仓数量
- `entryPrice` - 开仓均价
- `breakEvenPrice` - 盈亏平衡价
- `markPrice` - 标记价格
- `unRealizedProfit` - 未实现盈亏
- `liquidationPrice` - 强平价格
- `isolatedMargin` - 逐仓保证金
- `notional` - 名义价值
- `isolatedWallet` - 逐仓钱包余额
- `updateTime` - 更新时间

## ✨ V2 API 的优势

### 1. **直接返回杠杆倍数**
```python
# V2 - 直接使用
leverage = pos['leverage']  # "10"

# V3 - 需要计算
notional = abs(pos['notional'])
initial_margin = pos['initialMargin']
leverage = int(notional / initial_margin)
```

### 2. **直接返回保证金类型**
```python
# V2 - 直接使用
margin_type = pos['marginType']  # "cross" 或 "isolated"

# V3 - 不提供
```

### 3. **更简洁的字段结构**
- V2 返回 16 个核心字段
- V3 返回 20 个字段（包含更多细节，但对持仓查询非必需）

### 4. **完全满足持仓查询需求**
V2 API 提供的信息已经完全满足：
- ✅ 查看当前持仓
- ✅ 计算盈亏
- ✅ 了解杠杆和保证金类型
- ✅ 监控强平风险

## 🔧 代码变更

### 1. API 调用
```python
# 修改前
path="/fapi/v3/positionRisk"

# 修改后
path="/fapi/v2/positionRisk"
```

### 2. 字段映射
```python
# 修改前
position = {
    ...
    "marginAsset": pos.get("marginAsset", ""),
    "initialMargin": Decimal(pos.get("initialMargin", "0")),
    "maintMargin": Decimal(pos.get("maintMargin", "0")),
    "adl": pos.get("adl", 0),
    ...
}

# 修改后
position = {
    ...
    "leverage": pos.get("leverage", "1"),
    "marginType": pos.get("marginType", "cross"),
    "maxNotionalValue": Decimal(pos.get("maxNotionalValue", "0")),
    "isAutoAddMargin": pos.get("isAutoAddMargin", "false"),
    ...
}
```

### 3. ROE 计算
```python
# 修改前（V3）
initial_margin = pos['initialMargin']
roe = (unrealized_pnl / initial_margin * 100) if initial_margin > 0 else Decimal('0')

# 修改后（V2）
notional = abs(pos['notional'])
leverage = Decimal(pos['leverage'])
margin = notional / leverage if leverage > 0 else Decimal('0')
roe = (unrealized_pnl / margin * 100) if margin > 0 else Decimal('0')
```

## 📊 影响范围

### 修改的文件
1. ✅ `src/tri_arb/exchanges/binance_perp.py` - API 端点和字段映射
2. ✅ `src/tri_arb/cli/formatters/table.py` - 表格格式化（ROE 计算）
3. ✅ `src/tri_arb/cli/commands/account.py` - CSV 导出（ROE 计算）
4. ✅ `examples/binance_positions_example.py` - 示例代码更新
5. ✅ `docs/binance-api-implementation.md` - API 文档更新
6. ✅ `docs/binance-positions-feature.md` - 功能文档更新

### 不受影响的功能
- ✅ CLI 命令使用方式（完全兼容）
- ✅ 输出格式（table/json/csv）
- ✅ 用户体验（无变化）

## 🧪 测试

### 功能测试
- ✅ 查询所有持仓
- ✅ 查询特定合约
- ✅ 表格输出
- ✅ JSON 输出
- ✅ CSV 输出
- ✅ ROE 计算正确性

### 代码质量
- ✅ 无 linter 错误
- ✅ 类型注解完整
- ✅ 文档更新完整

## 📚 相关文档

- [币安 V2 API 文档](https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2)
- [币安 V3 API 文档](https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V3)
- [功能实现文档](binance-positions-feature.md)

## 💡 建议

### 为什么选择 V2？

1. **简洁性**：V2 返回的字段更少但足够用
2. **直接性**：杠杆和保证金类型直接返回，无需计算
3. **实用性**：完全满足持仓查询的实际需求
4. **易用性**：更容易理解和使用

### 什么时候需要 V3？

如果需要以下信息，可以考虑 V3：
- ADL 队列等级（自动减仓优先级）
- 更详细的保证金细节（初始/维持/持仓/订单保证金分离）
- 买卖单名义价值

对于大多数持仓查询场景，V2 API 已经足够！

---

**更新日期**：2025-10-16  
**版本**：V2 API  
**状态**：✅ 已完成并测试

