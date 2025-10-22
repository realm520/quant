# CEXTools 文档中心

## 📚 文档导航

### ⭐ 快速开始（必读）

| 文档 | 说明 | 阅读时间 |
|------|------|----------|
| [../QUICK_REFERENCE.md](../QUICK_REFERENCE.md) | 所有命令快速参考 | 5分钟 |
| [cextools-usage.md](cextools-usage.md) | CEXTools完整使用指南 | 15分钟 |
| [WEBSOCKET_COMPLETE_GUIDE.md](WEBSOCKET_COMPLETE_GUIDE.md) | WebSocket订阅完整指南 | 10分钟 |
| [GATE.md](GATE.md) | Gate.io 合并指南（快速开始/配置/REST/WS/定时/排错） | 8分钟 |

---

### 📊 功能指南

#### 账户管理
- [watch-balance-guide.md](watch-balance-guide.md) - 定时查询余额
- [Binance持仓查询](binance-positions-feature.md)
- [Binance订单查询](binance-orders-feature.md)

#### 订单交易
- [place-order-guide.md](place-order-guide.md) - 下单功能

#### WebSocket订阅
- [WEBSOCKET_COMPLETE_GUIDE.md](WEBSOCKET_COMPLETE_GUIDE.md) ⭐ 完整指南
- [SELECTIVE_SUBSCRIPTION_GUIDE.md](SELECTIVE_SUBSCRIPTION_GUIDE.md) - 选择性订阅

---

### 🔧 配置指南

#### 交易所配置
- [okx-quickstart.md](okx-quickstart.md) - OKX快速开始
- [okx-setup-guide.md](okx-setup-guide.md) - OKX详细配置
- [GATE.md](GATE.md) - Gate.io 合并指南

#### 数据库配置
- [POSTGRES_NO_PASSWORD_SETUP.md](POSTGRES_NO_PASSWORD_SETUP.md) - PostgreSQL无密码配置
- [UNIFIED_DATABASE_INIT.md](UNIFIED_DATABASE_INIT.md) - 数据库初始化

#### 其他
- [SYMBOL_FORMAT_GUIDE.md](SYMBOL_FORMAT_GUIDE.md) - 交易对格式说明

---

### 🐛 问题排查

- [OKX_WEBSOCKET_TROUBLESHOOTING.md](OKX_WEBSOCKET_TROUBLESHOOTING.md) - OKX WebSocket故障排查
- [okx-troubleshooting.md](okx-troubleshooting.md) - OKX API故障排查
- [debug-logging.md](debug-logging.md) - 调试日志
- Gate.io：请优先阅读 [GATE.md](GATE.md) 中的“常见问题排查（精简）”与引用链接

---

### 📖 技术文档

#### API实现
- [binance-api-implementation.md](binance-api-implementation.md) - Binance API实现
- [okx-implementation.md](okx-implementation.md) - OKX API实现

#### 架构设计
- [DATABASE_STRUCTURE_COMPARISON.md](DATABASE_STRUCTURE_COMPARISON.md) - 数据库结构对比
- [multi-exchange-summary.md](multi-exchange-summary.md) - 多交易所对比
- [architecture.md](architecture.md) - 系统架构

---

### 📦 示例代码

| 示例 | 说明 |
|------|------|
| `examples/binance_positions_example.py` | Binance持仓查询 |
| `examples/binance_orders_example.py` | Binance订单查询 |
| `examples/binance_websocket_example.py` | Binance WebSocket订阅 |
| `examples/okx_example.py` | OKX功能示例 |
| `examples/place_order_example.py` | 下单示例 |
| `examples/selective_subscription_example.sh` | 选择性订阅示例 |

---

## 🎯 按需求查找

### 我想要...

**查询余额/持仓/订单**
→ [cextools-usage.md](cextools-usage.md)

**下单交易**
→ [place-order-guide.md](place-order-guide.md)

**实时监控账户和订单**
→ [WEBSOCKET_COMPLETE_GUIDE.md](WEBSOCKET_COMPLETE_GUIDE.md) ⭐

**配置OKX**
→ [okx-quickstart.md](okx-quickstart.md)

**配置Gate.io**
→ [GATE.md](GATE.md)

**配置数据库**
→ [POSTGRES_NO_PASSWORD_SETUP.md](POSTGRES_NO_PASSWORD_SETUP.md)

**解决OKX连接问题**
→ [OKX_WEBSOCKET_TROUBLESHOOTING.md](OKX_WEBSOCKET_TROUBLESHOOTING.md)

**只订阅特定数据流**
→ [SELECTIVE_SUBSCRIPTION_GUIDE.md](SELECTIVE_SUBSCRIPTION_GUIDE.md)

**查询数据库**
→ [UNIFIED_DATABASE_INIT.md](UNIFIED_DATABASE_INIT.md)

---

## 📊 功能概览

### 支持的交易所

| 交易所 | REST API | WebSocket | 下单 |
|--------|---------|-----------|------|
| XT | ✅ | - | ✅ |
| Binance | ✅ | ✅ | ✅ |
| OKX | ✅ | ✅ | ✅ |
| Gate.io | ✅ | ✅ | ✅ |

### 核心功能

| 功能 | XT | Binance | OKX | Gate.io |
|------|-----|---------|-----|--------|
| 查询余额 | ✅ | ✅ | ✅ | ✅ |
| 查询持仓 | ✅ | ✅ | ✅ | ✅ |
| 查询订单 | ✅ | ✅ | ✅ | ✅ |
| 下单 | ✅ | ✅ | ✅ | ✅ |
| WebSocket订阅 | - | ✅ | ✅ | ✅ |
| 定时查询 | ✅ | ✅ | ✅ | ✅ |

---

## 🔗 相关链接

### 官方文档
- [Binance API文档](https://developers.binance.com/docs/derivatives/usds-margined-futures)
- [OKX API文档](https://www.okx.com/docs-v5/zh/)
- [Gate.io API文档](https://www.gate.io/docs/developers/apiv4/zh_CN/)

### 工具库
- [httpx](https://www.python-httpx.org/) - HTTP客户端
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM框架
- [websockets](https://websockets.readthedocs.io/) - WebSocket客户端
- [Rich](https://rich.readthedocs.io/) - 终端美化

---

**开始使用**：[../QUICK_REFERENCE.md](../QUICK_REFERENCE.md) ⭐

