# XT 多账号订阅实现说明

本文档说明多账号订阅功能的实现细节和后续改进方向。

---

## 1. 已实现功能

### 1.1 账号配置管理

- ✅ **配置文件格式**: JSON 格式，支持多个账号配置
- ✅ **账号管理器**: `AccountManager` 类，负责加载和管理账号配置
- ✅ **账号命名**: 每个账号可以设置友好的名称
- ✅ **灵活配置**: 每个账号可以独立配置订阅频道、告警等

### 1.2 数据库表结构

- ✅ **动态表模型**: `create_account_table_models()` 函数，为每个账号生成独立的表模型
- ✅ **表命名规则**: `{base_table_name}_{account_id}`，例如 `xt_account_updates_account_001`
- ✅ **完整表结构**: 包含所有 WebSocket 和 REST API 相关的表

### 1.3 CLI 命令

- ✅ **多账号订阅命令**: `cextools subscribe multi-account`
- ✅ **配置文件支持**: 通过 `--config` 指定配置文件
- ✅ **账号选择**: 通过 `--accounts` 选择要启动的账号
- ✅ **表自动创建**: 通过 `--create-tables` 自动创建账号表

### 1.4 多账号服务

- ✅ **XTMultiAccountStreamService**: 多账号订阅服务类
- ✅ **并发订阅**: 同时订阅多个账号的 WebSocket 数据流
- ✅ **独立服务实例**: 每个账号使用独立的 `XTUserStreamService` 实例

---

## 2. 待完善功能

### 2.1 账号特定表的数据保存

**当前状态**: `XTUserStreamService` 仍然使用硬编码的表模型（`xt_account_updates` 等），数据会保存到共享表中，而不是账号特定的表。

**需要修改**:
1. 修改 `XTUserStreamService` 的保存方法，使其支持动态表模型
2. 或者创建一个适配器，在保存数据时使用账号特定的表模型

**建议方案**:
```python
# 在 XTUserStreamService 中添加 account_models 属性
class XTUserStreamService:
    def __init__(self, ..., account_models: Optional[Dict] = None):
        self.account_models = account_models or self._get_default_models()
    
    async def _save_account_update(self, data):
        # 使用 self.account_models['XTAccountUpdate'] 而不是硬编码的 XTAccountUpdate
        model = self.account_models['XTAccountUpdate']
        record = model(**data)
        # ...
```

### 2.2 REST API 数据保存

**当前状态**: `watch-account` 和 `watch-positions` 命令仍然使用共享表。

**需要修改**:
1. 修改 `XTRestDataService` 以支持账号特定的表
2. 在 `watch-account` 命令中添加账号参数
3. 从配置文件读取账号信息

---

## 3. 文件结构

### 3.1 新增文件

```
src/tri_arb/
├── config/
│   └── account_manager.py          # 账号配置管理器
├── services/
│   ├── xt_multi_account_stream.py   # 多账号订阅服务
│   └── xt_account_table_adapter.py # 账号表适配器（待完善）
└── storage/
    └── xt_multi_account_models.py   # 动态表模型生成器

config/
└── accounts.example.json            # 配置文件示例

docs/
├── MULTI_ACCOUNT_USAGE.md           # 使用指南
└── MULTI_ACCOUNT_IMPLEMENTATION.md  # 实现说明（本文档）
```

### 3.2 修改的文件

- `src/tri_arb/cli/commands/subscribe.py`: 添加 `multi-account` 命令

---

## 4. 使用流程

### 4.1 首次使用

1. **创建配置文件**:
   ```bash
   cp config/accounts.example.json config/accounts.json
   # 编辑 config/accounts.json，填入账号信息
   ```

2. **创建数据库表**:
   ```bash
   cextools subscribe multi-account --create-tables
   ```

3. **启动订阅服务**:
   ```bash
   cextools subscribe multi-account
   ```

### 4.2 添加新账号

1. 编辑 `config/accounts.json`，添加新账号配置
2. 运行 `cextools subscribe multi-account --create-tables` 创建新账号的表
3. 重启订阅服务

---

## 5. 数据库表命名规则

### 5.1 账号ID处理

账号ID会经过以下处理：
- 转换为小写
- 将 `-` 替换为 `_`
- 将 `.` 替换为 `_`

例如：
- `account_001` → `account_001`
- `account-001` → `account_001`
- `account.001` → `account_001`

### 5.2 表名示例

对于账号 `account_001`，会创建以下表：

- `xt_account_updates_account_001`
- `xt_spot_updates_account_001`
- `xt_position_updates_account_001`
- `xt_order_updates_account_001`
- `xt_trade_updates_account_001`
- `xt_transfers_account_001`
- `xt_spot_balances_account_001`
- `xt_perp_balances_account_001`
- `xt_perp_positions_account_001`
- `xt_rest_position_updates_account_001`

---

## 6. 后续改进计划

### 6.1 短期（高优先级）

1. **修改 XTUserStreamService 以支持账号特定表**
   - 添加 `account_models` 参数
   - 修改所有保存方法使用动态表模型
   - 测试数据是否正确保存到账号特定的表

2. **修改 REST API 数据保存**
   - 修改 `XTRestDataService` 支持账号特定表
   - 修改 `watch-account` 和 `watch-positions` 命令支持多账号

3. **账号配置验证**
   - 验证 API 凭证是否有效
   - 验证账号是否可访问

### 6.2 中期

1. **账号健康检查**
   - 监控每个账号的连接状态
   - 自动重连失败的账号
   - 告警账号异常

2. **账号配置热重载**
   - 支持在不重启服务的情况下添加/删除账号
   - 监听配置文件变化

3. **账号数据统计**
   - 每个账号的数据量统计
   - 账号级别的指标计算

### 6.3 长期

1. **支持其他交易所**
   - Binance 多账号
   - OKX 多账号
   - Gate.io 多账号

2. **账号管理界面**
   - Web 界面管理账号配置
   - 查看账号状态和数据

3. **账号级别的告警配置**
   - 每个账号独立的告警规则
   - 告警历史记录

---

## 7. 注意事项

### 7.1 账号ID命名

- 使用字母、数字和下划线
- 避免特殊字符（`-`, `.`, 空格等）
- 建议使用有意义的命名，如 `main_account`, `test_account`

### 7.2 表数量

- 每个账号创建约 10 个表
- 10 个账号 = 100 个表
- 50 个账号 = 500 个表
- 确保数据库支持足够的表数量

### 7.3 并发连接

- 每个账号建立独立的 WebSocket 连接
- 10 个账号 = 10 个 WebSocket 连接
- 确保网络和系统资源充足

### 7.4 API 限流

- XT API 有频率限制
- 多账号同时订阅时注意限流
- 建议错开账号的连接时间

---

## 8. 测试建议

### 8.1 单元测试

- 测试 `AccountManager` 加载配置
- 测试 `create_account_table_models` 生成表模型
- 测试表名生成规则

### 8.2 集成测试

- 测试多账号同时订阅
- 测试数据保存到正确的表
- 测试账号添加/删除

### 8.3 性能测试

- 测试 10 个账号同时订阅的性能
- 测试数据库写入性能
- 测试内存和 CPU 使用

---

## 9. 故障排查

### 9.1 表创建失败

**错误**: `relation "xt_account_updates_xxx" already exists`

**原因**: 表已存在

**解决**: 这是正常的，表已存在时不会重复创建

### 9.2 账号连接失败

**错误**: WebSocket 连接失败

**原因**: API 凭证错误或网络问题

**解决**: 
1. 检查 API 凭证是否正确
2. 检查网络连接
3. 查看日志获取详细错误信息

### 9.3 数据未保存到账号表

**原因**: `XTUserStreamService` 仍使用共享表

**解决**: 需要修改 `XTUserStreamService` 以支持账号特定表（见 2.1）

---

## 10. 总结

当前实现提供了多账号订阅的基础框架，包括：

- ✅ 账号配置管理
- ✅ 动态表模型生成
- ✅ CLI 命令
- ✅ 多账号服务框架

**待完善**:
- ⚠️ 账号特定表的数据保存（需要修改 `XTUserStreamService`）
- ⚠️ REST API 数据保存（需要修改 `XTRestDataService`）

建议先完成账号特定表的数据保存功能，确保数据正确保存到每个账号的独立表中。

