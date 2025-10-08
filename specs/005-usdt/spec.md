# Feature Specification: 三角套利自动执行系统

**Feature Branch**: `005-usdt`
**Created**: 2025-10-07
**Status**: Draft
**Input**: User description: "集成下单逻辑，在发现套利机会后，执行下单，因为账户只配置了usdt，需要顺序下单，完成一个机会后再进行下一个机会的套利，暂时不需要并行。使用市价单执行，第一次成交金额不能小于10USDT，暂不考虑滑点，使用一个会话id追踪一次套利，完成后计算盈亏。"

## Execution Flow (main)
```
1. Parse user description from Input ✓
   → Feature: 三角套利自动执行（市价单、顺序执行、会话追踪、盈亏计算）
2. Extract key concepts from description ✓
   → Actor: 交易系统
   → Action: 发现机会、执行下单、等待成交、计算盈亏
   → Data: 套利机会、订单、成交记录、盈亏数据
   → Constraint: 仅USDT账户、顺序执行、市价单、最小10 USDT、串行处理
3. Clarifications needed:
   → [RESOLVED] 订单类型: 市价单
   → [RESOLVED] 最小金额: 10 USDT
   → [RESOLVED] 滑点处理: 暂不考虑
   → [RESOLVED] 会话追踪: 使用UUID作为会话ID
   → [RESOLVED] 执行模式: 串行（完成一个机会再处理下一个）
4. User Scenarios & Testing section completed ✓
5. Functional Requirements generated ✓
6. Key Entities identified ✓
7. Review Checklist
   ✅ All clarifications resolved
8. Return: SUCCESS (spec ready for planning)
```

---

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
交易系统发现三角套利机会后，自动使用市价单执行三笔顺序交易完成套利闭环。系统仅使用USDT账户资金，第一笔交易金额不低于10 USDT。系统为每次套利生成唯一会话ID进行全流程追踪，按路径顺序执行三笔交易，每笔订单完全成交后才执行下一笔。所有交易完成后，系统计算实际盈亏并输出结果。系统每次只处理一个套利机会，完成后再处理下一个。

### Acceptance Scenarios

1. **Given** 系统发现套利机会 USDT→BTC→ETH→USDT 且推荐金额为15 USDT，**When** 执行套利，**Then** 系统生成会话ID，按顺序提交三笔市价单（买BTC、卖BTC买ETH、卖ETH得USDT），记录每笔成交信息，最终计算并显示盈亏

2. **Given** 系统发现套利机会但推荐金额为8 USDT，**When** 评估是否执行，**Then** 系统跳过该机会并记录原因（金额低于10 USDT最小限制）

3. **Given** 三笔订单全部成交，**When** 计算盈亏，**Then** 系统显示：初始投入15 USDT、最终获得15.12 USDT、净利润0.12 USDT、实际收益率0.80%

4. **Given** 第一笔订单提交后立即成交（市价单特性），**When** 系统检查状态，**Then** 系统记录实际成交量和价格，根据实际成交量计算第二笔订单数量

5. **Given** 第二笔订单因余额不足被交易所拒绝，**When** 系统检测到拒绝，**Then** 停止执行，标记状态为失败，记录错误原因，保留第一笔交易的BTC头寸

6. **Given** 某笔订单超时未成交（罕见情况），**When** 超过30秒仍未成交，**Then** 系统尝试取消订单，标记执行失败

7. **Given** 系统发现3条套利机会，**When** 执行套利，**Then** 系统串行处理：完成第一条机会的全部3笔交易→计算盈亏→再开始第二条机会

### Edge Cases

- **Given** 所有发现的套利机会推荐金额都<10 USDT，**When** 评估执行，**Then** 全部跳过并提示"所有机会金额不足"
- **Given** 第一笔订单成交后，市场价格剧烈波动，**When** 提交第二笔订单，**Then** 系统仍按计划执行（暂不考虑滑点保护），记录实际成交价格
- **Given** 网络请求失败导致无法查询订单状态，**When** 系统检测到网络错误，**Then** 自动重试最多3次，失败后标记执行为失败状态
- **Given** 交易所API返回错误代码（如维护中），**When** 提交订单，**Then** 捕获错误，停止执行，记录错误信息
- **Given** 用户在执行过程中按Ctrl+C中断，**When** 系统收到信号，**Then** 完成当前正在等待的订单（不强制中断），然后停止处理后续机会

## Requirements *(mandatory)*

### Functional Requirements

#### 执行控制
- **FR-001**: 系统MUST使用市价单（MARKET）执行所有交易
- **FR-002**: 系统MUST在第一笔交易金额<10 USDT时拒绝执行该机会
- **FR-003**: 系统MUST按照套利路径顺序执行三笔交易（不可打乱顺序）
- **FR-004**: 系统MUST在前一笔订单完全成交后才提交下一笔订单
- **FR-005**: 系统MUST串行处理套利机会（完成一个机会的全部交易后再处理下一个）

#### 会话追踪
- **FR-006**: 系统MUST为每次套利生成唯一会话ID（UUID v4格式）
- **FR-007**: 系统MUST使用会话ID关联该次套利的所有订单和记录
- **FR-008**: 系统MUST在日志和输出中始终显示会话ID，便于追踪和调试

#### 订单管理
- **FR-009**: 系统MUST为每笔订单设置超时时间（默认30秒）
- **FR-010**: 系统MUST定期轮询订单状态（间隔0.5秒）直到成交或超时
- **FR-011**: 系统MUST在订单超时后尝试取消未成交部分
- **FR-012**: 系统MUST根据上一笔订单的实际成交量计算下一笔订单数量
- **FR-013**: 系统MUST记录每笔订单的关键信息：订单ID、交易对、方向、实际成交量、实际成交价格

#### 盈亏计算
- **FR-014**: 系统MUST在第三笔订单成交后立即计算盈亏
- **FR-015**: 系统MUST计算以下指标：
  - 初始投入金额（USDT）
  - 最终获得金额（USDT）
  - 净利润（最终-初始）
  - 实际收益率（净利润/初始投入 * 100%）
- **FR-016**: 系统MUST在控制台输出盈亏计算结果，包含上述所有指标
- **FR-017**: 系统MUST将盈亏数据持久化到执行记录中

#### 记录和日志
- **FR-018**: 系统MUST持久化每次套利的完整执行记录（会话ID、机会信息、三笔订单详情、盈亏数据）
- **FR-019**: 系统MUST在控制台实时输出执行进度（"提交订单1/3..."、"等待成交..."、"订单已成交"）
- **FR-020**: 系统MUST记录结构化日志，包含会话ID、步骤号、订单ID、关键时间戳
- **FR-021**: 系统MUST在执行完成后输出汇总信息（耗时、成交价格、盈亏明细）

#### 错误处理
- **FR-022**: 系统MUST在账户余额不足时拒绝执行并输出清晰错误提示
- **FR-023**: 系统MUST在订单被交易所拒绝时停止执行，记录拒绝原因（如余额不足、交易对无效）
- **FR-024**: 系统MUST在网络错误时自动重试（最多3次），全部失败后标记执行失败
- **FR-025**: 系统MUST在任一环节失败时标记执行状态为失败，保留已成交的头寸信息
- **FR-026**: 系统MUST提供清晰的错误信息，说明失败发生在哪一步、失败原因是什么

#### 用户控制
- **FR-027**: 系统MUST支持命令行参数 `--execute` 启用自动执行模式（默认关闭）
- **FR-028**: 系统MUST支持命令行参数 `--dry-run` 启用模拟模式（不真实下单，仅输出执行计划）
- **FR-029**: 系统MUST在 `--dry-run` 模式下显示将要执行的订单详情（交易对、方向、数量）但不提交订单
- **FR-030**: 系统MUST允许用户通过Ctrl+C优雅停止执行（完成当前订单等待，不处理新机会）

### Key Entities

- **ArbitrageExecution (套利执行记录)**: 表示一次完整的三角套利执行过程
  - session_id: 唯一会话ID（UUID v4格式）
  - opportunity: 关联的套利机会对象
  - status: 执行状态（pending/in_progress/completed/failed/partial）
  - steps: 三笔交易步骤详情列表（ExecutionStep对象）
  - initial_amount: 初始投入金额（USDT，Decimal类型）
  - final_amount: 最终获得金额（USDT，Decimal类型）
  - net_profit: 净利润（USDT，Decimal类型）
  - actual_profit_rate: 实际收益率（百分比，Decimal类型）
  - started_at: 开始执行时间戳
  - completed_at: 完成执行时间戳
  - error_message: 错误信息（失败时记录）

- **ExecutionStep (交易执行步骤)**: 表示三笔交易中的单笔交易详情
  - step_number: 步骤序号（1、2或3）
  - order: 关联的订单对象（Order）
  - exchange_order_id: 交易所返回的订单ID
  - status: 步骤状态（pending/submitted/filled/failed）
  - submitted_at: 订单提交时间戳
  - filled_at: 订单成交时间戳
  - filled_quantity: 实际成交数量（Decimal）
  - filled_price: 实际成交价格（Decimal）
  - fee: 交易手续费（Decimal）
  - fee_currency: 手续费币种（如BTC、ETH、USDT）

- **ExecutionConfig (执行配置)**: 表示套利执行的配置参数
  - min_initial_amount: 最小初始金额（默认10 USDT）
  - order_timeout_seconds: 单笔订单超时时间（默认30秒）
  - poll_interval_seconds: 订单状态轮询间隔（默认0.5秒）
  - max_retries: 网络错误最大重试次数（默认3次）

### Non-Functional Requirements

- **NFR-001**: 系统MUST在单次套利执行时间<2分钟（3笔订单 × 30秒超时 + 处理时间）
- **NFR-002**: 系统MUST能够稳定处理连续多个套利机会（串行执行，无内存泄漏）
- **NFR-003**: 系统MUST保持执行记录数据的完整性（部分失败也要保存已完成的步骤）
- **NFR-004**: 系统MUST提供清晰易读的控制台输出，便于用户实时监控执行进度
- **NFR-005**: 系统MUST记录详细的结构化日志，包含所有关键决策点和时间戳，便于事后分析

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

### Requirement Completeness
- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

---

## Execution Status
*Updated by main() during processing*

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked and resolved
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] Review checklist passed

---

## Dependencies and Assumptions

### Dependencies
- 依赖 Feature 004 的套利机会监测系统（ArbitrageMonitor）
- 依赖 Feature 002 的 XT Exchange 交易接口（place_order, get_order_status, cancel_order）
- 依赖账户有足够的USDT余额用于第一笔交易

### Assumptions
- 假设市价单能够在1秒内成交（交易所流动性充足）
- 假设交易所API稳定可靠，订单状态查询准确
- 假设用户账户仅配置USDT，无其他币种余额
- 假设网络延迟可接受（API请求<100ms响应时间）
- 假设交易对的最小下单量限制低于10 USDT等值
- 假设暂不考虑滑点影响（市价单可能以不利价格成交）

### Out of Scope (不在范围内)
- 限价单执行逻辑（仅支持市价单）
- 滑点保护和检测机制
- 并行多机会套利执行
- 复杂的部分成交处理策略
- 风险管理和止损机制
- 账户余额实时追踪（依赖交易所查询）
- 手续费实时计算（依赖交易所trade history接口）
- 执行结果持久化到数据库（仅内存记录，后续Feature实现）
- Web界面或API接口（仅CLI命令行）

---

## Business Value (业务价值)

- **自动化交易**: 从被动观察到主动执行，完全自动化套利流程
- **提升效率**: 发现机会后立即执行，避免人工干预延迟导致机会消失
- **风险可控**: 使用会话ID全流程追踪，便于审计和问题追溯
- **透明可信**: 实时输出执行进度和盈亏计算，交易过程完全透明
- **可扩展性**: 为后续支持并行执行、风险管理、持久化存储打下基础

---

## Risk Mitigation (风险缓解)

### 识别的风险
1. **市场风险**: 执行过程中价格剧烈波动导致实际收益低于预期
2. **流动性风险**: 市价单可能因流动性不足遇到严重滑点
3. **执行风险**: 三笔订单顺序执行期间机会可能消失
4. **技术风险**: 网络故障、API错误可能导致执行失败
5. **资金风险**: 部分失败可能导致资金卡在中间币种

### 缓解措施
1. **最小金额限制**: 10 USDT最小金额避免过小金额交易
2. **超时机制**: 30秒超时避免订单长时间挂单
3. **错误处理**: 完善的异常捕获和错误日志记录
4. **优雅降级**: 失败时保留已成交头寸信息，便于人工处理
5. **模拟模式**: `--dry-run` 模式允许无风险测试执行逻辑

---

## Success Metrics (成功指标)

- **功能完整性**: 能够完成从发现机会到三笔交易成交的全流程（100%路径覆盖）
- **执行成功率**: 在正常市场条件下，套利执行成功率 > 90%
- **时间效率**: 单次套利执行时间 < 60秒（不含等待时间）
- **数据准确性**: 盈亏计算误差 < 0.01%
- **可追溯性**: 每次执行都有完整的会话ID和日志记录
