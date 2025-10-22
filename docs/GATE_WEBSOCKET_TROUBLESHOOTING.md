# Gate.io WebSocket 订阅故障排查指南

## ✅ 已修复的问题

### 1. **Payload格式错误** ✅
**错误1**: `request payload does not follow json schema`（缺少payload）
**错误2**: `unknown contract usdt`（payload格式错误）
**原因**: Gate.io不同频道需要不同的payload格式
**修复**: 
- 余额频道：`payload: ["USDT"]`（大写结算货币）
- 持仓/订单：`payload: []`（空数组=所有合约）

### 2. **缺少显示方法** ✅
**问题**: WebSocket订阅后没有显示持仓和订单数据
**修复**: 添加了 `display_position_update()` 和 `display_order_update()` 方法

### 3. **重复数据存储** ✅  
**问题**: Gate.io使用快照推送，每次推送都会存库
**修复**: 添加了 `_has_account_changed()` 和 `_has_position_changed()` 方法

### 4. **增强日志** ✅
**问题**: 无法诊断连接问题
**修复**: 添加了详细的订阅状态日志

---

## 🔍 诊断步骤

### 步骤 1: 检查API凭证

```bash
# 查看环境变量
echo $GATE_API_KEY
echo $GATE_API_SECRET

# 如果未设置，从.env加载
cat .env | grep GATE_
```

### 步骤 2: 运行连接测试

```bash
cd /home/w_zy/crypto/xt/quant
source .venv/bin/activate

# 手动设置凭证（如果需要）
export GATE_API_KEY="your_key"
export GATE_API_SECRET="your_secret"

# 运行测试脚本
python scripts/test_gate_websocket.py
```

### 步骤 3: 测试实际订阅

```bash
# 订阅持仓（需要有持仓才会推送数据）
cextools subscribe user-stream -x gate -c position

# 订阅订单（需要有挂单才会推送数据）
cextools subscribe user-stream -x gate -c order

# 订阅账户余额（通常会立即推送）
cextools subscribe user-stream -x gate -c account

# 订阅所有频道
cextools subscribe user-stream -x gate
```

---

## ⚠️ 常见问题

### 问题 1: 订阅成功但没有数据推送

**原因**: Gate.io的WebSocket是**事件驱动**的，只有在数据发生变化时才推送

**解决方案**:
- **持仓频道**: 需要有实际持仓才会推送数据
- **订单频道**: 需要有挂单或订单状态变化
- **账户频道**: 余额变化时推送

**测试方法**:
1. 在Gate.io网页端或App创建一个测试订单
2. 修改或取消订单
3. 观察终端是否收到推送

### 问题 2: API权限不足

**错误信息**: `Authentication failed` 或 `Permission denied`

**解决方案**:
1. 登录Gate.io账户
2. 进入API管理页面
3. 确保API密钥有以下权限:
   - ✅ **Futures - Read** (必须)
   - ✅ **Futures - Trade** (可选，用于下单)
4. 重新创建API密钥并更新`.env`文件

### 问题 3: 连接建立但立即断开

**原因**: 签名错误或时间戳问题

**解决方案**:
```bash
# 检查系统时间
date

# 同步系统时间（如果需要）
sudo ntpdate pool.ntp.org

# 或使用timesyncd
sudo systemctl restart systemd-timesyncd
```

### 问题 4: 没有任何日志输出

**原因**: 日志级别设置过高

**解决方案**:
```bash
# 设置DEBUG日志级别
export LOG_LEVEL=DEBUG

# 重新运行
cextools subscribe user-stream -x gate -c position
```

---

## 📊 预期行为

### 成功订阅的输出示例

```
2024-10-22T15:22:17.716501Z [info] CLI app initialized
Gate.io用户数据流订阅服务
数据库: localhost:5432/trading
订阅频道: position
按 Ctrl+C 停止订阅

2024-10-22T15:22:17.998234Z [info] Database manager initialized
2024-10-22T15:22:17.998775Z [info] GateUserStreamService initialized
✅ 服务已启动
正在连接WebSocket...

2024-10-22T15:22:17.999719Z [info] Connecting to Gate WebSocket
2024-10-22T15:22:19.250393Z [info] Gate WebSocket connected
2024-10-22T15:22:19.351267Z [info] All Gate channels subscribed
2024-10-22T15:22:19.451018Z [info] ✅ Channel subscribed successfully

# 当有持仓变化时：
┏━━━━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━┓
┃ 合约     ┃ 方向 ┃ 持仓量 ┃ 开仓均价 ┃ 标记价格 ┃ 强平价 ┃ 未实现盈亏   ┃ 收益率 ┃ 保证金 ┃ 杠杆 ┃
┡━━━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━┩
│ BTC_USDT │ 多   │ 100    │ 67000.00 │ 67500.00 │ 60000  │ +500.0000    │ +0.75% │ 670.00 │ 10x  │
└──────────┴──────┴────────┴──────────┴──────────┴────────┴──────────────┴────────┴────────┴──────┘
```

### 没有数据时的正常行为

如果订阅成功但**没有看到表格**：
- ✅ **这是正常的！** Gate.io只在数据变化时推送
- 保持连接打开，在网页端操作后观察

---

## 🧪 手动触发数据推送

### 方法 1: 创建测试订单

```bash
# 1. 确保订阅正在运行
# 终端 1
cextools subscribe user-stream -x gate -c order

# 2. 在另一个终端创建订单
# 终端 2
# （使用Gate.io网页端或App创建订单更简单）
```

### 方法 2: 模拟持仓变化

1. 在Gate.io永续合约页面开仓
2. 观察终端立即收到持仓推送
3. 平仓时也会收到更新

### 方法 3: 查看历史数据

即使现在没有推送，历史数据已保存在数据库：

```bash
# 查看数据库中的Gate.io数据
psql -U postgres -d trading -c "SELECT * FROM gate_positions LIMIT 10;"
psql -U postgres -d trading -c "SELECT * FROM gate_orders LIMIT 10;"
```

---

## 🔧 高级调试

### 启用详细日志

编辑 `src/tri_arb/config/logging.py`，添加：

```python
# 设置websockets库的日志级别
logging.getLogger('websockets').setLevel(logging.DEBUG)
```

### 查看原始WebSocket消息

在 `gate_user_stream.py` 的 `handle_message` 方法中：

```python
async def handle_message(self, message: str):
    print(f"RAW MESSAGE: {message}")  # 添加这行
    try:
        data = json.loads(message)
        # ...
```

---

## 📚 参考文档

- [Gate.io WebSocket API文档](https://www.gate.io/docs/developers/futures/ws/zh_CN/)
- [Gate.io 永续合约频道](https://www.gate.io/docs/developers/futures/ws/zh_CN/#%E5%B8%90%E6%88%B7%E4%BD%99%E9%A2%9D%E9%80%9A%E7%9F%A5)

---

## ✅ 确认检查清单

在报告问题前，请确认：

- [ ] API密钥已正确设置
- [ ] API密钥有Futures读取权限
- [ ] 系统时间准确（误差<5秒）
- [ ] 数据库连接正常
- [ ] WebSocket显示"连接成功"
- [ ] WebSocket显示"✅ Channel subscribed successfully"
- [ ] 已在Gate.io创建测试持仓/订单
- [ ] 等待至少30秒观察数据推送

---

**如果所有检查都通过但仍无数据，这可能是正常的！** Gate.io在没有变化时不会推送数据。尝试在网页端操作账户来触发推送。

