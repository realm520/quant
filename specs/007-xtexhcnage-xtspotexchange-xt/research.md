# Research: 重命名XTExchange为XTSpotExchange

**Feature**: 007-xtexhcnage-xtspotexchange-xt
**Date**: 2025-10-11
**Status**: Complete

## Research Goals

确定最佳的类和文件重命名策略,确保:
1. 保留Git历史记录
2. 系统性更新所有引用
3. 不引入功能性变更
4. 验证重命名完整性

## Decision 1: 文件重命名方法

**Chosen**: 使用`git mv`命令保留文件历史

**Rationale**:
- Git会追踪文件重命名,保留完整的提交历史
- 避免在blame和log中丢失历史信息
- 符合最佳实践,不会在代码审查中产生困惑

**Alternatives Considered**:
- ❌ 简单的`mv`命令: 会在Git中显示为删除+新增,丢失历史
- ❌ 手动删除和创建: 完全丢失历史,不可接受

**Command**: `git mv src/tri_arb/exchanges/xt.py src/tri_arb/exchanges/xt_spot.py`

## Decision 2: 引用查找策略

**Chosen**: 多层次搜索策略

**Search Patterns**:
1. **Python导入语句**: `from tri_arb.exchanges.xt import`
2. **类名引用**: `XTExchange` (全词匹配)
3. **类型注解**: `: XTExchange` 和 `-> XTExchange`
4. **字符串字面量**: `"XTExchange"` 和 `'XTExchange'`
5. **文档引用**: 在.md文件中搜索`XTExchange`和`xt.py`

**Rationale**:
- 逐层搜索确保不遗漏任何引用
- 区分不同类型的引用,采用相应的替换策略
- 文档引用需要手动审查上下文

**Tools**:
- `grep -r "XTExchange" --include="*.py"` (代码)
- `grep -r "xt.py" --include="*.md"` (文档)
- IDE的全局搜索和替换功能

## Decision 3: 测试验证策略

**Chosen**: 分阶段验证方法

**Validation Steps**:
1. **类型检查**: `mypy src/tri_arb/exchanges/xt_spot.py --strict`
2. **代码检查**: `ruff check src/tri_arb/exchanges/xt_spot.py`
3. **单元测试**: `pytest tests/unit/test_exchanges/test_xt_contract.py -v`
4. **集成测试**: `pytest tests/integration/test_xt_integration.py --run-integration -v`
5. **完整测试套件**: `pytest tests/ -v`
6. **全局搜索验证**: 确认无遗留的旧引用

**Rationale**:
- 渐进式验证,快速发现问题
- 类型检查和代码检查在测试前运行,减少不必要的测试执行
- 集成测试需要API credentials,单独标记
- 最终全局搜索作为最后的安全网

**Success Criteria**:
- 所有测试通过(零失败)
- 类型检查零错误
- 代码检查零违规
- 全局搜索无遗留旧引用

## Decision 4: 保持不变的元素

**Chosen**: 最小化变更原则

**不修改的元素**:
1. **exchange标识符**: `exchange="xt"` 保持不变(用于日志和数据持久化)
2. **API端点**: BASE_URL和API路径不变
3. **类方法**: 所有方法名、参数、返回值保持不变
4. **类属性**: 所有属性名和类型保持不变
5. **业务逻辑**: 所有算法和计算逻辑保持不变
6. **配置常量**: BASE_URL, API_VERSION, RECV_WINDOW等保持不变

**Rationale**:
- `exchange="xt"`是外部可见的标识符,改变会影响日志分析和监控
- 最小化变更降低引入bug的风险
- 纯命名重构,不触及功能性代码

**Special Attention**:
- 字符串字面量`"xt"`在exchange字段中保持不变
- 只有类名`XTExchange` → `XTSpotExchange`需要修改
- 文件名`xt.py` → `xt_spot.py`需要修改

## Decision 5: 文档更新范围

**Chosen**: 系统性文档更新

**需要更新的文档**:
1. **CLAUDE.md**:
   - "XT Exchange Integration"章节
   - 代码示例中的类名和导入语句
   - Quick Commands中的文件路径

2. **specs/002-xt-spot-api/**:
   - quickstart.md中的示例代码
   - tasks.md中的文件路径引用

3. **specs/003-get-ticker-trading/**:
   - quickstart.md中的示例代码

**Rationale**:
- 文档与代码同步是最佳实践
- 过时的文档会误导开发者
- 示例代码必须可执行

**Update Strategy**:
- 使用编辑器的搜索替换功能
- 手动审查每个变更以确保上下文正确
- 特别注意代码块中的导入语句

## Research Summary

重命名操作的技术路径已明确:
1. 使用git mv保留历史
2. 多层次搜索策略确保完整性
3. 分阶段测试验证
4. 最小化变更原则(只改命名)
5. 系统性文档更新

无NEEDS CLARIFICATION项,所有技术决策已确定,可以进入Phase 1设计阶段。

## Risk Assessment

**Low Risk**:
- 纯重构操作,无业务逻辑变更
- 有完整的测试套件验证
- Git历史保留,可随时回滚

**Mitigation**:
- 在feature分支进行,不影响main分支
- 分步骤执行,每步验证
- 保持测试通过才合并

**Estimated Time**: 1-2小时(包括验证和文档更新)
