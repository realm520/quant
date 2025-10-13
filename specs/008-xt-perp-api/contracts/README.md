# API Contracts: XT永续合约API集成

**Feature**: 008-xt-perp-api | **Date**: 2025-10-11 | **Phase**: 1

## Overview

本目录包含XT永续合约API的所有端点合约定义。合约定义用于：
1. 生成合约测试（contract tests）
2. 验证API请求/响应格式
3. 作为实现的参考文档

## Contract Organization

```
contracts/
├── README.md           # 本文件
├── market_data.yaml    # 市场数据相关API（公开端点）
├── trading.yaml        # 交易相关API（需认证）
├── position.yaml       # 仓位管理API（需认证）
├── account.yaml        # 账户信息API（需认证）
└── advanced.yaml       # 高级功能API（计划委托、止盈止损）
```

## API Base URL

**Production**: `https://fapi.xt.com`

## Authentication

所有需认证的API使用HMAC-SHA256签名：

```
Headers:
  validate-algorithms: HmacSHA256
  validate-appkey: <API_KEY>
  validate-timestamp: <TIMESTAMP_MS>
  validate-recvwindow: 5000
  validate-signature: <SIGNATURE>
  Content-Type: application/json

Signature Calculation:
  For application/x-www-form-urlencoded (GET):
    sig_data = "xt-validate-appkey={api_key}&xt-validate-timestamp={timestamp}#{method}#{path}#{query}"
    signature = hmac_sha256(secret_key, sig_data).hexdigest()

  For application/json (POST/DELETE):
    sig_data = "xt-validate-appkey={api_key}&xt-validate-timestamp={timestamp}#{method}#{path}#{body}"
    signature = hmac_sha256(secret_key, sig_data).hexdigest()
```

## Response Format

所有API响应使用统一格式：

```json
{
  "rc": 0,              // Return code: 0=success, non-zero=error
  "mc": "",             // Error code (if rc != 0)
  "ma": [],             // Error messages (if rc != 0)
  "result": {}          // Result data (null if error)
}
```

## Contract Files

### market_data.yaml
公开市场数据端点（无需认证）：
- `GET /future/market/v1/public/q/ticker` - 单个合约ticker
- `GET /future/market/v1/public/q/tickers` - 所有合约ticker
- `GET /future/market/v1/public/q/depth` - 订单簿深度
- `GET /future/market/v1/public/q/funding-rate` - 资金费率
- `GET /future/market/v1/public/q/symbol-mark-price` - 标记价格
- `GET /future/market/v3/public/symbol/list` - 合约列表

### trading.yaml
交易相关端点（需认证）：
- `POST /future/trade/v1/order/create` - 创建订单
- `DELETE /future/trade/v1/order/cancel` - 取消订单
- `GET /future/trade/v1/order/detail` - 订单详情
- `GET /future/trade/v1/order/list` - 活跃订单列表
- `GET /future/trade/v1/order/list-history` - 历史订单
- `GET /future/trade/v1/order/trade-list` - 成交历史

### position.yaml
仓位管理端点（需认证）：
- `GET /future/user/v1/position` - 查询仓位
- `POST /future/user/v1/position/adjust-leverage` - 调整杠杆
- `POST /future/user/v1/position/close-all` - 一键平仓

### account.yaml
账户信息端点（需认证）：
- `GET /future/user/v1/balance/list` - 账户余额
- `GET /future/user/v1/balance/funding-rate-list` - 资金费用历史

### advanced.yaml
高级功能端点（需认证）：
- `POST /future/trade/v1/entrust/create-plan` - 创建计划委托
- `POST /future/trade/v1/entrust/cancel-plan` - 取消计划委托
- `POST /future/trade/v1/entrust/create-profit` - 创建止盈止损
- `POST /future/trade/v1/entrust/cancel-profit-stop` - 取消止盈止损
- `POST /future/trade/v1/entrust/update-profit-stop` - 修改止盈止损

## Contract Test Generation

每个合约文件将生成对应的合约测试文件：

```
tests/unit/test_exchanges/
├── test_xt_perp_market_data_contract.py    # market_data.yaml
├── test_xt_perp_trading_contract.py        # trading.yaml
├── test_xt_perp_position_contract.py       # position.yaml
├── test_xt_perp_account_contract.py        # account.yaml
└── test_xt_perp_advanced_contract.py       # advanced.yaml
```

## Implementation Notes

1. **错误处理**: 所有API可能返回rc!=0，必须检查并处理
2. **Rate Limiting**: XT对API调用有频率限制，需实现重试机制
3. **Timeout**: 建议设置10s超时，connect超时5s
4. **Connection Pooling**: 使用连接池复用连接，提高性能
5. **Timestamp**: 时间戳使用毫秒，与服务器时间差<5秒
6. **Symbol Format**: 合约符号使用小写+下划线格式（如btc_usdt）

## Reference

- 完整API文档: xt_perp_api.py (repository root)
- 现货API合约: specs/002-xt-spot-api/contracts/
- 数据模型定义: specs/008-xt-perp-api/data-model.md

---
**Status**: Contracts Structure Complete ✓ | **Next**: Generate Individual Contract Files
