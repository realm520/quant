# CEXTools 文档中心

## 📚 核心文档

### ⭐ 必读文档

| 文档 | 说明 | 阅读时间 |
|------|------|----------|
| [../QUICK_REFERENCE.md](../QUICK_REFERENCE.md) | 所有命令快速参考 | 5分钟 |
| [CEXTOOLS_COMPLETE_GUIDE.md](CEXTOOLS_COMPLETE_GUIDE.md) | CEXTools完整使用指南 | 20分钟 |
| [WEBSOCKET_COMPLETE_GUIDE.md](WEBSOCKET_COMPLETE_GUIDE.md) | WebSocket订阅完整指南 | 10分钟 |

---

## 🎯 按需求查找

### 我想要...

**快速上手CEXTools**
→ [CEXTOOLS_COMPLETE_GUIDE.md](CEXTOOLS_COMPLETE_GUIDE.md) ⭐

**查看所有命令**
→ [../QUICK_REFERENCE.md](../QUICK_REFERENCE.md) ⭐

**实时监控账户和订单**
→ [WEBSOCKET_COMPLETE_GUIDE.md](WEBSOCKET_COMPLETE_GUIDE.md) ⭐

**配置数据库**
→ [UNIFIED_DATABASE_INIT.md](UNIFIED_DATABASE_INIT.md)

**了解交易对格式**
→ [SYMBOL_FORMAT_GUIDE.md](SYMBOL_FORMAT_GUIDE.md)

---

## 📊 功能概览

### 支持的交易所

| 交易所 | REST API | WebSocket | 下单 | 定时查询 |
|--------|---------|-----------|------|----------|
| XT | ✅ | - | ✅ | ✅ |
| Binance | ✅ | ✅ | ✅ | ✅ |
| OKX | ✅ | ✅ | ✅ | ✅ |
| Gate.io | ✅ | ✅ | ✅ | ✅ |

### 核心功能

| 功能 | 说明 |
|------|------|
| 查询余额 | 支持所有交易所的现货和永续合约 |
| 查询持仓 | 支持所有交易所的永续合约持仓 |
| 查询订单 | 支持所有交易所的挂单查询 |
| 下单交易 | 支持限价、市价、Post-only订单 |
| WebSocket订阅 | 实时账户、持仓、订单推送 |
| 定时查询 | 可配置间隔的定时监控 |
| 数据库存储 | PostgreSQL数据持久化 |

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

**开始使用**：[CEXTOOLS_COMPLETE_GUIDE.md](CEXTOOLS_COMPLETE_GUIDE.md) ⭐
