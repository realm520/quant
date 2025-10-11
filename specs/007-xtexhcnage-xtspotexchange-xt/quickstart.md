# Quickstart: 验证XTExchange重命名为XTSpotExchange

**Feature**: 007-xtexhcnage-xtspotexchange-xt
**Purpose**: 验证重命名操作的完整性和正确性
**Time**: ~10分钟

## Prerequisites

- Python 3.11+ 环境
- 项目依赖已安装 (`uv sync`)
- Git工作目录干净
- 在feature分支: `007-xtexhcnage-xtspotexchange-xt`

## Verification Steps

### Step 1: 验证文件重命名
```bash
# 检查新文件存在
ls -la src/tri_arb/exchanges/xt_spot.py

# 检查旧文件不存在
ls src/tri_arb/exchanges/xt.py 2>&1 | grep "No such file"

# 验证Git历史保留
git log --follow src/tri_arb/exchanges/xt_spot.py | head -20
```

**Expected**:
- 新文件存在
- 旧文件不存在
- Git log显示完整历史(包括重命名前的提交)

### Step 2: 验证导入更新
```bash
# 搜索旧导入(应该无结果)
grep -r "from tri_arb.exchanges.xt import" src/ tests/ || echo "✅ 无旧导入"

# 搜索新导入(应该有结果)
grep -r "from tri_arb.exchanges.xt_spot import XTSpotExchange" src/ tests/

# 验证__init__.py导出
grep "XTSpotExchange" src/tri_arb/exchanges/__init__.py
```

**Expected**:
- 无旧导入语句
- 所有文件使用新导入
- `__init__.py`正确导出`XTSpotExchange`

### Step 3: 验证类型检查
```bash
# 类型检查核心文件
uv run mypy src/tri_arb/exchanges/xt_spot.py --strict

# 类型检查所有受影响文件
uv run mypy src/tri_arb/exchanges/factory.py --strict
uv run mypy src/tri_arb/arbitrage/adapters.py --strict
```

**Expected**: 零类型错误,所有检查通过

### Step 4: 验证代码检查
```bash
# Ruff检查
uv run ruff check src/tri_arb/exchanges/xt_spot.py

# 格式检查
uv run black --check src/tri_arb/exchanges/xt_spot.py
```

**Expected**: 零违规,零格式问题

### Step 5: 运行契约测试
```bash
# 验证BaseExchange接口遵从性
uv run pytest tests/unit/test_exchanges/test_xt_contract.py -v

# 检查测试输出中的类名
uv run pytest tests/unit/test_exchanges/test_xt_contract.py -v | grep "XTSpotExchange"
```

**Expected**:
- 所有契约测试通过
- 测试输出显示`XTSpotExchange`类名

### Step 6: 运行单元测试
```bash
# 运行所有XT exchange相关单元测试
uv run pytest tests/unit/test_exchanges/ -v -k xt
```

**Expected**: 所有测试通过,无失败,无错误

### Step 7: (可选)运行集成测试
```bash
# 需要设置API credentials
export XT_API_KEY=your_test_key
export XT_API_SECRET=your_test_secret

# 运行集成测试
uv run pytest tests/integration/test_xt_integration.py --run-integration -v
```

**Expected**: 集成测试通过(如果有credentials)

### Step 8: 验证文档更新
```bash
# 检查CLAUDE.md中无旧引用
grep -n "XTExchange" CLAUDE.md | grep -v "XTSpotExchange" || echo "✅ CLAUDE.md已更新"

# 检查specs文档更新
grep -r "xt\.py" specs/002-xt-spot-api/ specs/003-get-ticker-trading/ || echo "✅ Specs已更新"

# 验证新引用存在
grep "XTSpotExchange" CLAUDE.md
grep "xt_spot.py" CLAUDE.md
```

**Expected**:
- 无旧引用残留
- 新引用正确存在

### Step 9: 全局搜索验证
```bash
# 最终安全检查:搜索所有可能遗漏的旧引用
grep -r "class XTExchange" src/ tests/ specs/ || echo "✅ 无旧类定义"
grep -r "\"XTExchange\"" src/ tests/ || echo "✅ 无字符串字面量旧引用"

# 验证exchange标识符保持不变(应该有结果)
grep -r "exchange=\"xt\"" src/tri_arb/exchanges/xt_spot.py
```

**Expected**:
- 无旧类定义残留
- `exchange="xt"`标识符保持不变(这是正确的)

### Step 10: 运行完整测试套件
```bash
# 最终验证:运行所有测试
uv run pytest tests/ -v --tb=short

# 查看测试摘要
uv run pytest tests/ -v --tb=short | tail -20
```

**Expected**:
- 所有测试通过
- 测试摘要显示100%通过率
- 无failures,无errors

## Success Criteria

✅ 所有步骤的Expected结果都已达成

**核心验证点**:
- [x] 文件已重命名,Git历史保留
- [x] 所有导入已更新,无旧引用
- [x] 类型检查通过
- [x] 代码检查通过
- [x] 契约测试通过
- [x] 单元测试通过
- [x] 文档已更新
- [x] 全局搜索无遗漏
- [x] 完整测试套件通过

## Rollback (如果需要)

```bash
# 如果发现问题,回滚重命名
git checkout main -- src/tri_arb/exchanges/xt.py
git rm src/tri_arb/exchanges/xt_spot.py
git checkout main -- src/ tests/ CLAUDE.md specs/

# 重置分支
git reset --hard origin/007-xtexhcnage-xtspotexchange-xt
```

## Next Steps

如果所有验证通过:
1. 提交变更: `git add -A && git commit -m "refactor: rename XTExchange to XTSpotExchange"`
2. 推送分支: `git push origin 007-xtexhcnage-xtspotexchange-xt`
3. 创建Pull Request
4. 等待代码审查
5. 合并到main分支
