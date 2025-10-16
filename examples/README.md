# Examples / 示例代码

这个目录包含了各种使用示例，展示如何使用项目中的交易所适配器和工具。

## 📁 示例列表

### 币安合约持仓查询 (`binance_positions_example.py`)

演示如何使用 `BinancePerpExchange` 类查询币安永续合约的持仓信息。

**功能示例**：
- ✅ 查询所有持仓
- ✅ 查询特定合约持仓
- ✅ 持仓统计和分析
- ✅ 盈亏排名

**使用方法**：
```bash
# 1. 设置环境变量
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# 2. 运行示例
python examples/binance_positions_example.py
```

**API说明**：
- 使用币安永续合约API v3 (`/fapi/v3/positionRisk`)
- 仅返回有持仓或挂单的交易对
- 支持单向持仓模式和双向持仓模式
- 包含详细的保证金和盈亏信息

## 🔧 准备工作

### 1. 安装依赖

确保已安装项目依赖：
```bash
uv pip install -e ".[dev]"
```

### 2. 配置API凭证

所有示例都需要相应交易所的API凭证。请在运行前设置环境变量：

**币安交易所**：
```bash
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_api_secret"
```

**XT交易所**：
```bash
export XT_API_KEY="your_xt_api_key"
export XT_API_SECRET="your_xt_api_secret"
```

### 3. API权限要求

不同示例需要的API权限：
- 持仓查询：**只读权限**
- 余额查询：**只读权限**
- 下单交易：**交易权限**

> ⚠️ **安全提示**：建议不要启用提币权限，并设置IP白名单。

## 📚 更多资源

- [CEXTools使用指南](../docs/cextools-usage.md)
- [币安API实现状态](../docs/binance-api-implementation.md)
- [项目README](../README.md)

## 💡 贡献

欢迎提交更多示例！如果你有好的使用案例，请：
1. Fork 项目
2. 添加你的示例代码
3. 更新这个 README
4. 提交 Pull Request

## 📝 示例代码规范

编写示例代码时，请遵循以下规范：

1. **注释完整**：包含中文注释和docstring
2. **错误处理**：优雅地处理异常
3. **环境变量**：使用环境变量配置敏感信息
4. **资源清理**：确保正确连接和断开交易所
5. **输出友好**：使用emoji和格式化输出
6. **独立运行**：每个示例都应该能独立运行

## 🚀 快速开始

运行第一个示例：
```bash
# 克隆项目（如果还没有）
git clone https://github.com/realm520/quant.git
cd quant

# 安装依赖
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[dev]"

# 配置API密钥
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"

# 运行示例
python examples/binance_positions_example.py
```

---

**最后更新**：2025-10-16

