# 默认交易类型变更：现在默认为永续合约

## 🎯 重要变更

系统默认交易类型已从 **现货 (spot)** 改为 **永续合约 (perp)**。

## 📊 影响的命令

以下市场行情命令的默认交易类型已变更：

| 命令 | 之前默认 | 现在默认 | 说明 |
|------|----------|----------|------|
| `market ticker` | spot | **perp** | 实时价格查询 |
| `market depth` | spot | **perp** | 订单簿深度 |  
| `market watch` | spot | **perp** | 实时监控 |

## 🚀 新的使用方式

### 永续合约（默认，无需指定 -e 参数）

```bash
# 永续合约价格（默认）
cextools market ticker -s BTC/USDT

# 永续合约订单簿（默认）  
cextools market depth -s BTC/USDT

# 永续合约实时监控（默认）
cextools market watch -s BTC/USDT
```

### 现货（需要显式指定 -e spot）

```bash
# 现货价格（需要指定）
cextools market ticker -e spot -s BTC/USDT

# 现货订单簿（需要指定）
cextools market depth -e spot -s BTC/USDT

# 现货实时监控（需要指定）
cextools market watch -e spot -s BTC/USDT
```

## 💡 为什么做这个变更？

1. **符合用户习惯** - 大多数量化交易更关注永续合约
2. **简化常用操作** - 减少永续合约查询时的参数输入
3. **与行业惯例一致** - 大部分交易工具默认关注合约市场

## ⚠️ 注意事项

### 现有脚本需要更新

如果你有现有的脚本使用这些命令查询现货数据，需要添加 `-e spot` 参数：

```bash
# 之前（现在会查询合约数据）
cextools market ticker -s BTC/USDT

# 现在（如果要查询现货）
cextools market ticker -e spot -s BTC/USDT
```

### 账户命令不受影响

账户相关命令仍然要求明确指定交易类型：

```bash
# 仍然需要明确指定
cextools account balance -e spot    # 现货余额
cextools account balance -e perp    # 合约余额  
cextools account positions -e perp  # 合约持仓
```

## 📝 迁移指南

### 检查现有脚本

搜索你的脚本中是否有以下模式：

```bash
# 需要检查的命令
grep -r "market ticker" your_scripts/
grep -r "market depth" your_scripts/ 
grep -r "market watch" your_scripts/
```

### 更新脚本

如果这些命令用于查询现货数据，添加 `-e spot` 参数：

```bash
# 之前
cextools market ticker -s BTC/USDT

# 之后（如果要查询现货）
cextools market ticker -e spot -s BTC/USDT
```

## 🔄 回退方案

如果需要临时回到旧的行为，可以使用别名：

```bash
# 创建现货查询的别名
alias spot-ticker="cextools market ticker -e spot"
alias spot-depth="cextools market depth -e spot"
alias spot-watch="cextools market watch -e spot"

# 使用
spot-ticker -s BTC/USDT
spot-depth -s BTC/USDT  
spot-watch -s BTC/USDT
```

## 🎉 优势

✅ **减少输入** - 永续合约查询更简洁  
✅ **符合预期** - 与用户使用习惯一致  
✅ **向后兼容** - 仍支持显式指定交易类型  
✅ **逻辑清晰** - 默认行为更符合量化交易场景  

## 🏷️ 版本信息

- **变更版本**: v0.2.0
- **生效时间**: 立即
- **影响范围**: 市场行情命令的默认行为
- **兼容性**: 向后兼容，但默认行为改变

## 📚 相关文档

- [CEXTools 使用指南](cextools-usage.md) - 已更新示例
- [多交易所示例](multi-exchange-examples.md)
- [API Key 共享说明](api-key-sharing.md)

---

**提示**: 如果你主要使用现货交易，建议在你的环境中设置别名来简化操作。
