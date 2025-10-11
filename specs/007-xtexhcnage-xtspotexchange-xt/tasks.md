# Tasks: 重命名XTExchange为XTSpotExchange

**Feature Branch**: `007-xtexhcnage-xtspotexchange-xt`
**Input**: Design documents from `/specs/007-xtexhcnage-xtspotexchange-xt/`
**Prerequisites**: plan.md, research.md, data-model.md, quickstart.md

## Execution Summary

这是一个纯重构任务,将`XTExchange`类重命名为`XTSpotExchange`,文件从`xt.py`重命名为`xt_spot.py`。任务分为三个阶段:准备、执行、验证。

**关键约束**: 不改变任何功能性代码逻辑,仅修改命名。

## Format: `[ID] [P?] Description`
- **[P]**: 可并行执行(不同文件,无依赖)
- 包含精确的文件路径

---

## Phase 3.1: 准备阶段

### T001: 验证Git状态和分支
**File**: N/A (Git操作)
**Command**:
```bash
git status
git branch --show-current
```
**Success Criteria**:
- 工作目录干净
- 在分支`007-xtexhcnage-xtspotexchange-xt`上
- 无未提交的更改

**Why**: 确保从干净的状态开始,避免混淆变更

---

### T002: 创建安全备份点
**File**: N/A (Git操作)
**Command**:
```bash
git add -A
git stash
git tag backup-before-rename-$(date +%Y%m%d-%H%M%S)
git stash pop
```
**Success Criteria**:
- Tag创建成功
- 可以通过tag回滚

**Why**: 创建回滚点,如果出错可以快速恢复

---

## Phase 3.2: 文件和类重命名

### T003: Git mv 重命名文件
**File**: `src/tri_arb/exchanges/xt.py` → `src/tri_arb/exchanges/xt_spot.py`
**Command**:
```bash
git mv src/tri_arb/exchanges/xt.py src/tri_arb/exchanges/xt_spot.py
```
**Success Criteria**:
- 新文件存在: `src/tri_arb/exchanges/xt_spot.py`
- 旧文件不存在
- Git显示为rename操作,不是delete+add

**Why**: 使用git mv保留文件历史

---

### T004: 重命名类定义
**File**: `src/tri_arb/exchanges/xt_spot.py`
**Change**:
```python
# 旧:
class XTExchange(BaseExchange):

# 新:
class XTSpotExchange(BaseExchange):
```
**Success Criteria**:
- 类名已更改为`XTSpotExchange`
- Docstring中的类名也已更新
- 所有方法签名和实现保持不变

**Why**: 核心重命名操作

---

## Phase 3.3: 更新导入语句

### T005 [P]: 更新exchanges/__init__.py导出
**File**: `src/tri_arb/exchanges/__init__.py`
**Change**:
```python
# 旧:
from tri_arb.exchanges.xt import XTExchange

# 新:
from tri_arb.exchanges.xt_spot import XTSpotExchange
```
**Success Criteria**:
- 导入语句已更新
- 如果有`__all__`列表,也已更新

**Why**: 保持包级导出正确

---

### T006 [P]: 更新exchanges/factory.py导入
**File**: `src/tri_arb/exchanges/factory.py`
**Change**:
```python
# 旧:
from tri_arb.exchanges.xt import XTExchange

# 新:
from tri_arb.exchanges.xt_spot import XTSpotExchange
```
**Success Criteria**:
- 导入语句已更新
- 工厂函数中的类引用已更新

**Why**: 工厂模式需要正确的类引用

---

### T007 [P]: 更新arbitrage/adapters.py导入
**File**: `src/tri_arb/arbitrage/adapters.py`
**Change**:
```python
# 旧:
from tri_arb.exchanges.xt import XTExchange

# 新:
from tri_arb.exchanges.xt_spot import XTSpotExchange
```
**Success Criteria**:
- 导入语句已更新
- 类型注解已更新

**Why**: Arbitrage适配器使用Exchange类

---

### T008 [P]: 更新unit/test_exchanges/test_xt_contract.py
**File**: `tests/unit/test_exchanges/test_xt_contract.py`
**Change**:
```python
# 旧:
from tri_arb.exchanges.xt import XTExchange

# 新:
from tri_arb.exchanges.xt_spot import XTSpotExchange
```
**Success Criteria**:
- 导入语句已更新
- 所有测试用例中的类引用已更新
- 测试描述/docstring中的类名已更新

**Why**: 契约测试验证接口遵从性

---

### T009 [P]: 更新integration/test_xt_integration.py
**File**: `tests/integration/test_xt_integration.py`
**Change**:
```python
# 旧:
from tri_arb.exchanges.xt import XTExchange

# 新:
from tri_arb.exchanges.xt_spot import XTSpotExchange
```
**Success Criteria**:
- 导入语句已更新
- 所有测试用例中的实例化已更新

**Why**: 集成测试验证实际API交互

---

### T010 [P]: 更新contract/test_arbitrage/test_ticker_integration.py
**File**: `tests/contract/test_arbitrage/test_ticker_integration.py`
**Change**:
```python
# 旧:
from tri_arb.exchanges.xt import XTExchange

# 新:
from tri_arb.exchanges.xt_spot import XTSpotExchange
```
**Success Criteria**:
- 导入语句已更新

**Why**: 跨模块契约测试

---

## Phase 3.4: 更新类型注解

### T011: 搜索并更新所有类型注解
**Files**: 所有Python文件中的类型注解
**Search Pattern**:
```bash
grep -r ": XTExchange" src/ tests/ --include="*.py"
grep -r "-> XTExchange" src/ tests/ --include="*.py"
```
**Change**: 将所有类型注解中的`XTExchange`改为`XTSpotExchange`
**Success Criteria**:
- 搜索无遗漏的旧类型注解

**Why**: 保持类型安全

---

## Phase 3.5: 更新文档

### T012 [P]: 更新CLAUDE.md中的XT Exchange章节
**File**: `CLAUDE.md`
**Changes**:
- 将"XT Exchange Integration"章节中的`XTExchange`改为`XTSpotExchange`
- 更新示例代码中的导入语句
- 更新文件路径引用`xt.py` → `xt_spot.py`
- Quick Commands中的路径更新

**Success Criteria**:
- 全局搜索`XTExchange`在CLAUDE.md中无旧引用(除了git历史说明)
- 所有代码示例可执行

**Why**: 保持文档与代码同步

---

### T013 [P]: 更新specs/002-xt-spot-api/quickstart.md
**File**: `specs/002-xt-spot-api/quickstart.md`
**Changes**:
- 更新示例代码中的导入语句
- 更新类实例化代码

**Success Criteria**:
- 示例代码使用新类名

**Why**: Quickstart必须可执行

---

### T014 [P]: 更新specs/002-xt-spot-api/tasks.md
**File**: `specs/002-xt-spot-api/tasks.md`
**Changes**:
- 更新文件路径引用

**Success Criteria**:
- 文件路径正确

**Why**: 任务文档准确性

---

### T015 [P]: 更新specs/003-get-ticker-trading/quickstart.md
**File**: `specs/003-get-ticker-trading/quickstart.md`
**Changes**:
- 更新示例代码

**Success Criteria**:
- 示例代码使用新类名

**Why**: 跨特性文档一致性

---

## Phase 3.6: 验证阶段 ⚠️ CRITICAL

### T016: 类型检查验证
**Command**:
```bash
uv run mypy src/tri_arb/exchanges/xt_spot.py --strict
uv run mypy src/tri_arb/exchanges/factory.py --strict
uv run mypy src/tri_arb/arbitrage/adapters.py --strict
```
**Success Criteria**:
- 零类型错误
- 无`Any`类型警告

**Why**: 验证类型安全未被破坏

---

### T017: 代码检查验证
**Command**:
```bash
uv run ruff check src/tri_arb/exchanges/xt_spot.py
uv run ruff check src/
```
**Success Criteria**:
- 零ruff违规
- 无导入错误

**Why**: 代码质量保证

---

### T018: 契约测试验证
**Command**:
```bash
uv run pytest tests/unit/test_exchanges/test_xt_contract.py -v
```
**Success Criteria**:
- 所有测试通过
- 测试输出显示`XTSpotExchange`类名

**Why**: 验证BaseExchange接口遵从性未改变

---

### T019: 单元测试验证
**Command**:
```bash
uv run pytest tests/unit/test_exchanges/ -v -k xt
```
**Success Criteria**:
- 所有XT相关测试通过
- 无failures, 无errors

**Why**: 验证核心功能未被破坏

---

### T020: 全局搜索验证无遗漏
**Command**:
```bash
# 搜索旧类定义(应该无结果)
grep -r "class XTExchange" src/ tests/ || echo "✅ 无旧类定义"

# 搜索旧导入(应该无结果)
grep -r "from tri_arb.exchanges.xt import" src/ tests/ || echo "✅ 无旧导入"

# 验证exchange标识符保持不变(应该有结果)
grep -r 'exchange="xt"' src/tri_arb/exchanges/xt_spot.py
```
**Success Criteria**:
- 无旧类定义残留
- 无旧导入语句
- `exchange="xt"`标识符正确保留

**Why**: 最终安全检查,确保无遗漏

---

### T021: 运行完整测试套件
**Command**:
```bash
uv run pytest tests/ -v --tb=short
```
**Success Criteria**:
- 所有测试通过
- 100%通过率
- 无failures, 无errors

**Why**: 最终验证,确认无功能性破坏

---

## Phase 3.7: 提交和清理

### T022: Git提交变更
**Command**:
```bash
git add -A
git commit -m "refactor: rename XTExchange to XTSpotExchange

- Rename src/tri_arb/exchanges/xt.py to xt_spot.py
- Update class name from XTExchange to XTSpotExchange
- Update all imports and references
- Update documentation (CLAUDE.md, specs/)
- All tests passing

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
"
```
**Success Criteria**:
- Commit成功
- 提交消息清晰

**Why**: 保存变更,准备PR

---

## Dependencies

```
T001 (Git验证)
  ↓
T002 (备份)
  ↓
T003 (git mv文件)
  ↓
T004 (类定义) → T005-T015 (并行更新导入和文档)
  ↓
T011 (类型注解)
  ↓
T016-T021 (串行验证)
  ↓
T022 (提交)
```

**阶段依赖**:
- Phase 3.3 (T005-T010) 可并行执行 [P]
- Phase 3.5 (T012-T015) 可并行执行 [P]
- Phase 3.6 (T016-T021) 必须串行执行
- 必须完成所有验证才能提交

## Parallel Execution Example

**Stage 1: 并行更新导入语句 (T005-T010)**
```bash
# 可以同时在6个不同文件中工作
# T005: __init__.py
# T006: factory.py
# T007: adapters.py
# T008: test_xt_contract.py
# T009: test_xt_integration.py
# T010: test_ticker_integration.py
```

**Stage 2: 并行更新文档 (T012-T015)**
```bash
# 4个不同的文档文件
# T012: CLAUDE.md
# T013: specs/002-xt-spot-api/quickstart.md
# T014: specs/002-xt-spot-api/tasks.md
# T015: specs/003-get-ticker-trading/quickstart.md
```

## Rollback Plan

如果T016-T021任何验证失败:
```bash
# 回滚到备份点
git reset --hard backup-before-rename-TIMESTAMP

# 或者回滚到上一次提交
git reset --hard HEAD~1

# 重新开始从T003
```

## Success Criteria Summary

✅ **完成标准**:
- [ ] 文件已重命名,Git历史保留
- [ ] 类名已更新
- [ ] 所有导入语句已更新
- [ ] 所有类型注解已更新
- [ ] 所有文档已更新
- [ ] 类型检查通过 (T016)
- [ ] 代码检查通过 (T017)
- [ ] 契约测试通过 (T018)
- [ ] 单元测试通过 (T019)
- [ ] 全局搜索无遗漏 (T020)
- [ ] 完整测试套件通过 (T021)
- [ ] 变更已提交 (T022)

## Estimated Time

**Total**: 1-2小时

- Phase 3.1 (准备): 5分钟
- Phase 3.2 (重命名): 5分钟
- Phase 3.3 (导入更新): 15分钟
- Phase 3.4 (类型注解): 10分钟
- Phase 3.5 (文档更新): 20分钟
- Phase 3.6 (验证): 25分钟
- Phase 3.7 (提交): 5分钟

## Notes

- **[P]** 标记的任务可以并行执行(不同文件,无依赖)
- 所有验证任务(T016-T021)必须串行执行
- 如果任何验证失败,立即停止并调查
- 不要跳过验证步骤
- exchange="xt"标识符不应该改变
- 所有方法签名和业务逻辑保持完全不变
