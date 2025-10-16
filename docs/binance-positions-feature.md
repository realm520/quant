# 币安合约持仓查询功能实现 (V2 API)

## 📋 功能概述

为币安永续合约交易所添加了持仓查询功能，支持查询所有持仓和特定合约持仓。使用 Binance Futures API V2，直接返回杠杆倍数和保证金类型信息。

## ✅ 实现内容

### 1. 核心API实现 (`src/tri_arb/exchanges/binance_perp.py`)

添加了 `get_positions()` 方法：

```python
async def get_positions(self, symbol: str | None = None) -> list[dict[str, Any]]
```

**功能特性**：
- ✅ 支持查询所有持仓（`symbol=None`）
- ✅ 支持查询特定合约持仓（`symbol="BTCUSDT"`）
- ✅ 使用币安API v2 (`/fapi/v2/positionRisk`)
- ✅ 完整的HMAC-SHA256签名认证
- ✅ 直接返回杠杆倍数和保证金类型
- ✅ 所有数值字段使用 Decimal 类型确保精度

**返回字段**：
- `symbol`: 交易对
- `positionSide`: 持仓方向 (BOTH/LONG/SHORT)
- `positionAmt`: 持仓数量
- `entryPrice`: 开仓均价
- `markPrice`: 标记价格
- `unRealizedProfit`: 未实现盈亏
- `liquidationPrice`: 参考强平价格
- `leverage`: 当前杠杆倍数 ⭐
- `marginType`: 保证金类型 (isolated/cross) ⭐
- `notional`: 名义价值
- `maxNotionalValue`: 最大名义价值
- 等等...（详见[API文档](https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2)）

### 2. CLI命令支持

现有的 `cextools account positions` 命令已自动支持币安合约：

```bash
# 查询所有持仓
cextools account positions -x binance -e perp

# 查询特定合约持仓
cextools account positions -x binance -e perp --symbol BTC/USDT

# JSON格式输出
cextools account positions -x binance -e perp -o json

# CSV格式输出
cextools account positions -x binance -e perp -o csv

# 表格格式输出（默认）
cextools account positions -x binance -e perp -o table
```

### 3. 格式化输出增强 (`src/tri_arb/cli/formatters/table.py`)

更新了 `format_positions_table()` 函数，支持两种数据格式：
- ✅ Position对象（XT交易所）
- ✅ 字典格式（币安交易所）

自动适配不同交易所的数据结构，统一显示：
- 交易对
- 持仓方向
- 持仓数量
- 开仓价格
- 当前价格
- 未实现盈亏（带颜色：绿色盈利/红色亏损）
- 收益率（ROE%）
- 杠杆倍数

### 4. CSV导出支持 (`src/tri_arb/cli/commands/account.py`)

更新了CSV导出功能，支持币安持仓数据：
- ✅ 自动检测数据格式
- ✅ 统一输出格式
- ✅ 计算ROE和杠杆

### 5. 文档更新

**更新的文档**：
- ✅ `docs/cextools-usage.md` - 添加币安持仓查询使用示例
- ✅ `docs/binance-api-implementation.md` - 添加持仓API实现说明和数据格式
- ✅ `examples/README.md` - 创建示例代码说明文档

**新增内容**：
- 持仓查询命令使用方法
- API响应数据格式说明
- 字段详细说明
- 测试示例

### 6. 示例代码 (`examples/binance_positions_example.py`)

创建了完整的Python示例代码，包含3个场景：

**示例1：查询所有持仓**
- 连接币安合约交易所
- 查询所有持仓
- 显示详细信息

**示例2：查询特定合约持仓**
- 查询指定交易对
- 计算收益率和杠杆
- 格式化显示

**示例3：持仓统计分析**
- 统计持仓概览
- 多空分类统计
- 盈利/亏损排名

## 🎯 API详细信息

### 接口端点
```
GET /fapi/v2/positionRisk
```

### 请求参数
- `symbol` (可选): 交易对，如 "BTCUSDT"
- `timestamp` (必需): 时间戳
- `signature` (必需): HMAC-SHA256签名

### 请求权重
**5** (每次请求消耗5个权重单位)

### 响应示例

**单向持仓模式**：
```json
[
  {
    "symbol": "BTCUSDT",
    "positionSide": "BOTH",
    "positionAmt": "0.001",
    "entryPrice": "50000.00",
    "breakEvenPrice": "50001.00",
    "markPrice": "51000.00",
    "unRealizedProfit": "1.00",
    "liquidationPrice": "45000.00",
    "leverage": "10",
    "marginType": "cross",
    "isolatedMargin": "0.00",
    "isAutoAddMargin": "false",
    "notional": "51.00",
    "isolatedWallet": "0",
    "maxNotionalValue": "20000000",
    "updateTime": 1625474304765
  }
]
```

**双向持仓模式**：
```json
[
  {
    "symbol": "BTCUSDT",
    "positionSide": "LONG",
    "positionAmt": "0.001",
    "leverage": "4",
    "marginType": "cross",
    ...
  },
  {
    "symbol": "BTCUSDT",
    "positionSide": "SHORT",
    "positionAmt": "-0.001",
    "leverage": "4",
    "marginType": "cross",
    ...
  }
]
```

## 🚀 使用方法

### 1. 配置API凭证

```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
```

### 2. 使用CLI命令

```bash
# 查询所有持仓（表格格式）
cextools account positions -x binance -e perp

# 查询特定合约
cextools account positions -x binance -e perp -s BTC/USDT

# JSON格式输出（包含完整API数据）
cextools account positions -x binance -e perp -o json
```

### 3. 使用Python API

```python
import asyncio
from tri_arb.exchanges.binance_perp import BinancePerpExchange

async def main():
    exchange = BinancePerpExchange(
        api_key="your_key",
        api_secret="your_secret"
    )
    
    await exchange.connect()
    
    # 查询所有持仓
    positions = await exchange.get_positions()
    
    # 查询特定合约
    btc_positions = await exchange.get_positions(symbol="BTCUSDT")
    
    await exchange.disconnect()

asyncio.run(main())
```

### 4. 运行示例代码

```bash
python examples/binance_positions_example.py
```

## 📊 数据格式说明

### positionSide 持仓方向
- `BOTH`: 单向持仓模式（默认）
- `LONG`: 双向持仓模式的多仓
- `SHORT`: 双向持仓模式的空仓

### positionAmt 持仓数量
- 正数：多头持仓
- 负数：空头持仓
- 0：无持仓

### 保证金类型 (marginType)
- `isolated`: 逐仓模式
  - 每个持仓使用独立的保证金
  - 强平只影响该持仓
  - 可以手动增加保证金
- `cross`: 全仓模式
  - 使用账户总余额作为保证金
  - 强平会影响所有持仓
  - 自动使用可用余额

### 杠杆倍数 (leverage)
- V2 API 直接返回当前使用的杠杆倍数
- 无需通过名义价值和保证金计算
- 例如："10" 表示 10倍杠杆

### 名义价值 (notional)
- 持仓的市值：`positionAmt * markPrice`
- 用于计算实际占用的保证金：`notional / leverage`
- 正数表示多仓，负数表示空仓

## 🔍 技术细节

### 1. 数值精度处理

所有金额和价格字段都使用 `Decimal` 类型：
```python
position = {
    "positionAmt": Decimal(pos.get("positionAmt", "0")),
    "entryPrice": Decimal(pos.get("entryPrice", "0")),
    "unRealizedProfit": Decimal(pos.get("unRealizedProfit", "0")),
    "leverage": pos.get("leverage", "1"),  # 字符串类型
    "marginType": pos.get("marginType", "cross"),  # 字符串类型
    # ...
}
```

### 2. ROE 收益率计算

V2 API 使用名义价值和杠杆计算保证金：
```python
# 计算保证金
notional = abs(pos['notional'])
leverage = Decimal(pos['leverage'])
margin = notional / leverage if leverage > 0 else Decimal('0')

# 计算 ROE
unrealized_pnl = pos['unRealizedProfit']
roe = (unrealized_pnl / margin * 100) if margin > 0 else Decimal('0')
```

### 3. 符号格式转换

CLI命令接受标准格式（BTC/USDT），自动转换为币安格式（BTCUSDT）：
```python
# CLI层面处理
symbol = "BTC/USDT"  # 用户输入
symbol = symbol.replace("/", "")  # 转换为 BTCUSDT
```

### 4. 错误处理

完整的错误处理机制：
- API凭证验证
- 网络请求异常
- 数据格式验证
- 日志记录

### 5. 兼容性设计

格式化函数同时支持两种数据结构：
```python
if isinstance(pos, dict):
    # 币安字典格式 (V2 API)
    leverage = pos.get('leverage', '1')
    symbol = pos.get('symbol', '')
else:
    # XT Position对象格式
    leverage = f"{pos.leverage}"
    symbol = pos.symbol
```

## 🎨 输出效果

### 表格格式
```
┏━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ Symbol    ┃ Side ┃ Quantity ┃ Entry Price ┃ Current Price┃ PnL     ┃ ROE    ┃ Leverage┃
┡━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ BTCUSDT   │ LONG │ 0.001000 │ 50000.00    │ 51000.00     │ +1.00   │ +39.22%│ 20x     │
└───────────┴──────┴──────────┴─────────────┴──────────────┴─────────┴────────┴─────────┘
```

### JSON格式
```json
[
  {
    "symbol": "BTCUSDT",
    "positionSide": "LONG",
    "positionAmt": "0.001",
    "entryPrice": "50000.00",
    ...
  }
]
```

### CSV格式
```csv
symbol,side,quantity,entry_price,current_price,pnl,roe,leverage
BTCUSDT,LONG,0.001,50000.00,51000.00,1.00,39.22,20
```

## 🧪 测试

### 功能测试
- ✅ 查询所有持仓
- ✅ 查询特定合约
- ✅ 空持仓处理
- ✅ 单向持仓模式
- ✅ 双向持仓模式
- ✅ 表格/JSON/CSV输出

### 代码质量
- ✅ 无linter错误
- ✅ 类型注解完整
- ✅ Docstring文档
- ✅ 错误处理

## 📝 相关文档

- [币安永续合约持仓API文档 (V2)](https://developers.binance.com/docs/zh-CN/derivatives/usds-margined-futures/trade/rest-api/Position-Information-V2)
- [CEXTools使用指南](cextools-usage.md)
- [币安API实现状态](binance-api-implementation.md)
- [示例代码说明](../examples/README.md)

## 🎉 总结

本次实现完整地添加了币安合约持仓查询功能，使用 V2 API，包括：

1. ✅ 核心API实现（使用 V2 端点）
2. ✅ CLI命令集成
3. ✅ 多格式输出支持（table/json/csv）
4. ✅ 完整文档
5. ✅ 示例代码
6. ✅ 错误处理
7. ✅ 代码质量保证

### V2 API 的优势

相比 V3 API，V2 版本的优势：
- ⭐ **直接返回杠杆倍数** - 无需计算
- ⭐ **直接返回保证金类型** - isolated/cross
- ⭐ **更简洁的字段** - 更易理解和使用
- ⭐ **完全满足持仓查询需求**

用户现在可以通过命令行或Python API轻松查询币安永续合约的持仓信息！

---

**实现日期**：2025-10-16  
**API版本**：Binance Futures API V2  
**状态**：✅ 已完成并测试

