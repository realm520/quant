
# Implementation Plan: 重命名XTExchange为XTSpotExchange

**Branch**: `007-xtexhcnage-xtspotexchange-xt` | **Date**: 2025-10-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-xtexhcnage-xtspotexchange-xt/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from file system structure or context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code, or `AGENTS.md` for all other agents).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
将`XTExchange`类重命名为`XTSpotExchange`,文件从`src/tri_arb/exchanges/xt.py`重命名为`xt_spot.py`。这是一个纯重构操作,不改变任何功能性代码逻辑,仅更新命名和所有引用点。技术方法:使用git mv保留历史,系统性搜索和替换所有引用(导入、类型注解、字符串字面量、文档),确保测试套件通过验证重命名的完整性。

**用户约束**: 确保不要改动任何功能性代码(仅修改命名,保持所有逻辑不变)

## Technical Context
**Language/Version**: Python 3.11+ (已确定,项目要求)
**Primary Dependencies**: httpx (async HTTP), pydantic (validation), structlog (logging), pytest (testing)
**Storage**: N/A (无存储变更)
**Testing**: pytest + pytest-asyncio (单元测试、集成测试、契约测试)
**Target Platform**: Linux/macOS (交易系统服务器)
**Project Type**: single (单体项目,src/tests结构)
**Performance Goals**: 无性能目标变更(纯重命名操作)
**Constraints**: 不改变任何功能性代码逻辑,保持所有测试通过
**Scale/Scope**: 影响范围约10个文件(源码、测试、文档)

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Initial Check (Pre-Research)

**I. Type Safety & Error Handling**: ✅ PASS
- 重命名操作不涉及类型变更
- 现有类型注解保持不变
- 不改变异常处理逻辑

**II. Test-Driven Development**: ✅ PASS
- 所有现有测试必须在重命名后通过(验证无功能性变更)
- 不需要新测试(纯重构操作)
- 使用现有测试套件验证完整性

**III. Performance-First Architecture**: ✅ PASS
- 不涉及性能变更(纯命名操作)
- 无新代码路径,无性能影响

**IV. Observability & Audit Trail**: ✅ PASS
- 日志消息中的字符串引用需要更新(exchange="xt"保持不变)
- 类名在日志中的引用更新为XTSpotExchange
- 审计追踪不受影响

**V. Simplicity & Maintainability**: ✅ PASS
- 提高可维护性(更清晰的命名)
- 不增加复杂度(纯重命名)
- 遵循YAGNI原则(为未来XTFuturesExchange预留命名空间)

**Overall**: ✅ PASS - 无宪法违规,纯重构操作符合所有原则

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
src/tri_arb/
├── exchanges/
│   ├── __init__.py           # 需要更新导出
│   ├── xt.py → xt_spot.py    # 核心重命名操作
│   ├── factory.py            # 需要更新导入
│   └── base.py               # 不需要修改
├── arbitrage/
│   └── adapters.py           # 需要更新导入
└── cli/
    └── commands/             # 可能需要更新引用

tests/
├── unit/
│   └── test_exchanges/
│       └── test_xt_contract.py    # 需要更新导入和引用
├── integration/
│   └── test_xt_integration.py     # 需要更新导入和引用
└── contract/
    └── test_arbitrage/
        └── test_ticker_integration.py  # 需要更新导入

文档:
├── CLAUDE.md                 # 需要更新文档引用
└── specs/
    ├── 002-xt-spot-api/
    │   ├── quickstart.md     # 需要更新示例代码
    │   └── tasks.md          # 需要更新引用
    └── 003-get-ticker-trading/
        └── quickstart.md     # 需要更新示例代码
```

**Structure Decision**: 单体项目结构(Option 1)。重命名影响的文件分布在src/tri_arb/exchanges/、tests/多个子目录、以及项目文档中。使用git mv保留文件历史,系统性更新所有导入和引用。

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh claude`
     **IMPORTANT**: Execute it exactly as specified above. Do not add or remove any arguments.
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- 基于research.md中的决策生成任务
- 重命名操作分为三个主要阶段:
  1. **准备阶段**: Git操作和备份
  2. **重命名阶段**: 文件、类名、导入语句更新
  3. **验证阶段**: 测试和文档验证

**Specific Tasks**:
1. Git branch verification and backup
2. 文件重命名 (git mv)
3. 类定义重命名
4. 更新src/中的所有导入语句 [P]
5. 更新tests/中的所有导入语句 [P]
6. 更新__init__.py导出
7. 更新类型注解
8. 更新字符串字面量(如果有)
9. 更新CLAUDE.md文档引用
10. 更新specs/文档引用 [P]
11. 运行类型检查验证
12. 运行代码检查验证
13. 运行契约测试
14. 运行单元测试
15. 运行集成测试(可选)
16. 全局搜索验证无遗漏
17. 运行完整测试套件

**Ordering Strategy**:
- 顺序执行: Git操作 → 重命名 → 更新 → 验证
- [P]标记表示可并行执行的独立任务(如多个文档更新)
- 验证任务必须在所有更新完成后执行

**Estimated Output**: 15-20个有序任务,分为准备、执行、验证三个阶段

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [x] Phase 3: Tasks generated (/tasks command) - 22 tasks across 7 phases
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (N/A - no deviations)

**Generated Artifacts**:
- [x] research.md - 重命名策略和技术决策
- [x] data-model.md - 确认无数据模型变更
- [x] contracts/README.md - 确认无契约变更
- [x] quickstart.md - 10步验证流程
- [x] CLAUDE.md - Agent context已更新

---
*Based on Constitution v1.0.0 - See `.specify/memory/constitution.md`*
