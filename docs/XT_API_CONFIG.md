# XT交易所API配置说明

## 🔑 API密钥配置

### 重要说明

**XT交易所的现货交易和永续合约交易使用相同的API密钥对**，无需分别配置不同的密钥。

### 环境变量配置

```bash
# XT API配置（现货和永续合约共用）
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
```

### API密钥获取

1. 登录XT交易所官网
2. 进入API管理页面
3. 创建新的API密钥
4. 设置适当的权限（现货交易、永续合约交易等）
5. 保存API Key和Secret

### 权限设置建议

对于WebSocket订阅和数据同步功能，建议设置以下权限：

- ✅ **现货交易** - 用于现货市场数据
- ✅ **永续合约交易** - 用于合约市场数据
- ✅ **读取权限** - 查询账户余额、持仓、订单等
- ❌ **提现权限** - 出于安全考虑，不建议开启

### 安全注意事项

1. **密钥保护**
   - 不要在代码中硬编码API密钥
   - 使用环境变量存储敏感信息
   - 定期轮换API密钥

2. **权限最小化**
   - 只开启必要的权限
   - 避免开启提现等高风险权限
   - 设置IP白名单（如果支持）

3. **网络安全**
   - 使用HTTPS/WSS连接
   - 监控API调用频率
   - 设置合理的API限制

## 🔧 配置示例

### 开发环境

```bash
# .env文件
XT_API_KEY=your_development_api_key
XT_API_SECRET=your_development_api_secret
DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/trading_dev
```

### 生产环境

```bash
# 生产环境配置
XT_API_KEY=your_production_api_key
XT_API_SECRET=your_production_api_secret
DATABASE_URL=postgresql+asyncpg://user:password@prod-db:5432/trading_prod
```

## 📊 使用场景

### WebSocket订阅

```bash
# 默认订阅永续合约数据流
python -m tri_arb.cli.main subscribe user-stream -x xt
```

**注意**: WebSocket订阅默认订阅永续合约数据，这是交易系统的主要用途。

### REST API查询

```bash
# 现货交易
python -m tri_arb.cli.main account balance -x xt -t spot

# 永续合约交易
python -m tri_arb.cli.main account balance -x xt -t perp
```

### 数据同步

WebSocket服务会自动使用相同的API密钥进行数据同步：

```python
# 自动使用相同的API密钥进行数据同步
service = XTUserStreamService(
    api_key=os.getenv("XT_API_KEY"),      # 现货和合约共用
    api_secret=os.getenv("XT_API_SECRET"), # 现货和合约共用
    enable_data_sync=True,  # 默认启用数据同步
)
```

## 🔍 故障排除

### 常见问题

1. **API密钥无效**
   ```
   错误: Invalid API key
   解决: 检查API密钥是否正确，是否已激活
   ```

2. **权限不足**
   ```
   错误: Insufficient permissions
   解决: 检查API密钥权限设置，确保开启了必要的权限
   ```

3. **IP限制**
   ```
   错误: IP not allowed
   解决: 检查IP白名单设置，或联系客服添加IP
   ```

### 调试步骤

1. **验证API密钥**
   ```bash
   # 测试API连接
   python test_xt_websocket.py rest
   ```

2. **检查权限**
   ```bash
   # 测试不同功能
   python -m tri_arb.cli.main account balance -x xt -t spot
   python -m tri_arb.cli.main account balance -x xt -t perp
   ```

3. **查看日志**
   ```bash
   # 启用调试模式
   python -m tri_arb.cli.main subscribe user-stream -x xt --debug
   ```

## 📚 相关文档

- [XT WebSocket订阅功能使用指南](XT_WEBSOCKET_GUIDE.md)
- [CEXTools完整使用指南](CEXTOOLS_COMPLETE_GUIDE.md)
- [XT API官方文档](https://doc.xt.com/)

---

**注意**: 请确保在生产环境中正确配置安全设置，定期轮换API密钥，并监控API使用情况。
