# Feature Specification: 重命名XTExchange为XTSpotExchange

**Feature Branch**: `007-xtexhcnage-xtspotexchange-xt`
**Created**: 2025-10-11
**Status**: Draft
**Input**: User description: "修改当前XTExhcnage名称，更名为XTSpotExchange，代码文件名也改成xt_spot.py"

## Execution Flow (main)
```
1. 用户描述已解析: 重命名类从XTExchange到XTSpotExchange,文件名改为xt_spot.py
   → 明确: 类名XTExchange → XTSpotExchange, 文件名xt.py → xt_spot.py
2. 提取关键概念:
   → 类名重命名: XTExchange → XTSpotExchange
   → 文件名重命名: xt.py → xt_spot.py
   → 导入语句更新: 所有引用需要更新
   → 测试文件更新: 测试中的类引用需要更新
   → 文档更新: CLAUDE.md等文档需要同步
3. 无需澄清的方面: 需求明确
4. 填写用户场景和测试: 已完成
5. 生成功能需求: 已完成(5条需求)
6. 识别关键实体: 已完成
7. 审查清单检查: 通过
   → 无[NEEDS CLARIFICATION]标记
   → 无实现细节
8. 返回: SUCCESS (规格准备完成,可进入规划阶段)
```

---

## ⚡ Quick Guidelines
- ✅ 关注重命名的完整性和一致性
- ❌ 不涉及具体实现工具和方法
- 👥 为开发者和维护人员提供清晰的变更范围

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
作为开发者,我需要将当前的`XTExchange`类重命名为`XTSpotExchange`,并将文件`xt.py`重命名为`xt_spot.py`,以便:
- 类名更明确地表达这是XT交易所的现货交易适配器
- 文件名与类名保持一致性
- 为未来可能的合约交易(xt_futures.py)等实现预留命名空间
- 提高代码的可读性和可维护性

### Acceptance Scenarios
1. **Given** 存在类`XTExchange`在文件`src/tri_arb/exchanges/xt.py`, **When** 执行重命名, **Then** 类名变为`XTSpotExchange`,文件名变为`xt_spot.py`
2. **Given** 其他模块导入了`XTExchange`, **When** 完成重命名, **Then** 所有导入语句正确指向`from tri_arb.exchanges.xt_spot import XTSpotExchange`
3. **Given** 测试文件实例化和使用`XTExchange`, **When** 完成重命名, **Then** 所有测试使用`XTSpotExchange`且测试通过
4. **Given** 文档中提到`XTExchange`或`xt.py`, **When** 完成重命名, **Then** 所有文档引用都已更新为新名称

### Edge Cases
- 确保字符串字面量中的类名引用(如日志、错误消息)也已更新
- 确保配置文件中如果有类名引用也已同步
- 确保没有遗漏间接导入(通过`__init__.py`等)
- 确保CLAUDE.md中"Common Pitfalls"等章节的示例代码也已更新

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: 系统必须将类`XTExchange`重命名为`XTSpotExchange`,保持所有类方法、属性和行为不变
- **FR-002**: 系统必须将文件`src/tri_arb/exchanges/xt.py`重命名为`src/tri_arb/exchanges/xt_spot.py`
- **FR-003**: 系统必须更新所有源代码文件中对该类的导入语句,从`from tri_arb.exchanges.xt import XTExchange`改为`from tri_arb.exchanges.xt_spot import XTSpotExchange`
- **FR-004**: 系统必须更新所有测试文件中的类引用,包括导入语句、类实例化、类型注解等,确保测试套件通过
- **FR-005**: 系统必须更新项目文档(CLAUDE.md、README等)中所有对类名和文件名的引用,保持文档与代码同步

### Key Entities *(include if feature involves data)*
- **XTExchange类**: 当前的XT交易所适配器类,需要重命名为`XTSpotExchange`
- **源文件**: `src/tri_arb/exchanges/xt.py`,需要重命名为`xt_spot.py`
- **导入语句**: 所有Python模块中引用该类的import语句
- **测试文件**: 单元测试、集成测试、契约测试文件
- **文档文件**: CLAUDE.md、README.md及其他包含代码引用的文档
- **类实例引用**: 代码中创建该类实例的所有位置

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [x] 无实现细节(语言、框架、API)
- [x] 关注用户价值和业务需求(提高代码可维护性)
- [x] 为技术和非技术干系人编写
- [x] 所有必填部分已完成

### Requirement Completeness
- [x] 无[NEEDS CLARIFICATION]标记
- [x] 需求可测试且明确
- [x] 成功标准可衡量(测试通过,无遗漏引用)
- [x] 范围边界清晰(重命名+更新引用)
- [x] 依赖关系和假设已识别

---

## Execution Status
*Updated by main() during processing*

- [x] 用户描述已解析
- [x] 关键概念已提取
- [x] 歧义已标记(无歧义)
- [x] 用户场景已定义
- [x] 需求已生成
- [x] 实体已识别
- [x] 审查清单已通过

---

## Additional Context

### Current State
当前代码库状态:
- 类名: `XTExchange` (在`src/tri_arb/exchanges/xt.py`中定义)
- 该类实现了BaseExchange接口,提供XT交易所REST API v4集成
- 该类被多个模块导入和使用(CLI、arbitrage模块等)
- 存在完整的测试套件(单元测试、集成测试、契约测试)
- CLAUDE.md文档详细记录了该类的使用方法和注意事项

### Naming Rationale
重命名为`XTSpotExchange`的原因:
1. **明确性**: "Spot"明确表明这是现货交易API适配器
2. **扩展性**: 为未来可能的`XTFuturesExchange`(合约交易)预留命名空间
3. **一致性**: 文件名`xt_spot.py`与类名`XTSpotExchange`保持一致
4. **行业惯例**: 交易所通常区分现货(Spot)和合约(Futures/Perpetual)API

### Change Impact Assessment
此重命名将影响:
1. **核心文件**: `src/tri_arb/exchanges/xt.py` → `xt_spot.py`
2. **类定义**: `class XTExchange` → `class XTSpotExchange`
3. **导入语句**: 所有`from tri_arb.exchanges.xt import XTExchange`
4. **类型注解**: 所有使用`XTExchange`作为类型的地方
5. **测试文件**: `tests/unit/test_exchanges/test_xt*.py`等
6. **文档**: CLAUDE.md中的"XT Exchange Integration"章节

### Success Criteria
重命名成功的标准:
- 所有单元测试通过(`pytest tests/unit/test_exchanges/`)
- 所有集成测试通过(`pytest tests/integration/ --run-integration`)
- 类型检查通过(`mypy src/`)
- 代码检查通过(`ruff check .`)
- 格式检查通过(`black --check .`)
- 文档与代码保持一致
- Git历史记录保留(使用`git mv`命令)

### Verification Steps
验证重命名完整性的步骤:
1. 全局搜索`XTExchange`确保无遗漏
2. 全局搜索`from tri_arb.exchanges.xt import`确保导入更新
3. 检查`__init__.py`中的导出列表
4. 运行完整测试套件
5. 检查文档中的代码示例
6. 验证CLI命令仍能正常工作
