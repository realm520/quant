# API Key 共享说明

## 重要更新 ✅

现货和永续合约**共用同一个 API key**，无需分别配置。

## 环境变量配置

### XT 交易所
```bash
# 一个 API key 同时用于现货和永续合约
export XT_API_KEY="your_xt_api_key"
export XT_API_SECRET="your_xt_api_secret"
```

### 币安交易所
```bash
# 一个 API key 同时用于现货和永续合约
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
```

## 工作原理

虽然现货和永续合约使用同一个 API key，但系统会根据交易类型自动选择正确的 API 端点：

### XT 交易所
- **现货** → `https://sapi.xt.com` (现货 API)
- **永续合约** → `https://fapi.xt.com` (合约 API)

### 币安交易所
- **现货** → `https://api.binance.com` (现货 API)
- **永续合约** → `https://fapi.binance.com` (合约 API)

## 使用示例

```bash
# 设置一次环境变量
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"

# 可以同时访问现货和永续合约
cextools account balance -x xt -e spot    # 查询现货余额
cextools account balance -x xt -e perp    # 查询永续合约余额
cextools market ticker -x xt -e spot -s BTC/USDT   # 现货价格
cextools market ticker -x xt -e perp -s BTC/USDT   # 合约价格
```

## 代码实现

在 `src/tri_arb/cli/utils/exchange_factory.py` 中：

```python
def _get_env_prefix(exchange_name: ExchangeName, exchange_type: ExchangeType) -> str:
    """获取环境变量前缀.
    
    Note:
        现货和永续合约使用相同的 API key，只需要根据交易所名称区分环境变量。
    """
    # 现货和永续合约共用同一个 API key
    return exchange_name.value.upper()
```

这个简化的实现：
- XT 交易所：统一使用 `XT` 前缀
- 币安交易所：统一使用 `BINANCE` 前缀

## 优势

✅ **简化配置** - 只需配置一组 API 凭证  
✅ **统一管理** - 一个 API key 管理所有交易类型  
✅ **符合实际** - 与交易所的实际实现一致  
✅ **易于理解** - 更直观的配置方式  

## 与之前的区别

### 之前（错误）❌
```bash
export XT_API_KEY="spot_key"
export XT_API_SECRET="spot_secret"
export XT_PERP_API_KEY="perp_key"        # 不需要
export XT_PERP_API_SECRET="perp_secret"  # 不需要
```

### 现在（正确）✅
```bash
export XT_API_KEY="your_key"
export XT_API_SECRET="your_secret"
# 现货和永续合约都用这一组
```

## 常见问题

### Q: 现货和永续合约真的用同一个 API key 吗？
A: 是的，大多数交易所的现货和永续合约共用同一个 API key，只是访问不同的 API 端点。

### Q: 如何区分现货和永续合约？
A: 通过 `--exchange-type` (或 `-e`) 参数：
- `-e spot` = 现货
- `-e perp` = 永续合约

### Q: 安全吗？
A: API key 的权限在交易所后台统一管理，可以设置不同的权限级别（只读、交易等）。

### Q: 如果我想用不同的 API key 怎么办？
A: 可以通过 `--api-key` 和 `--api-secret` 参数临时覆盖环境变量：
```bash
cextools account balance -e spot --api-key "key1" --api-secret "secret1"
cextools account balance -e perp --api-key "key2" --api-secret "secret2"
```

## 参考文档

- [CEXTools 使用指南](cextools-usage.md)
- [币安现货和永续合约支持](binance-spot-perp-support.md)
- [多交易所示例](multi-exchange-examples.md)

