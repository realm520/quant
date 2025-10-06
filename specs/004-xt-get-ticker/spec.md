# Feature Specification: 三角套利机会监测系统

**Feature Branch**: `004-xt-get-ticker`
**Created**: 2025-10-06
**Status**: Draft
**Input**: User description: "集成xt的get_ticker接口，获取所有市场的买卖一价格并计算是否有三角套利机会，只需要观察并打印机会，不用执行。可以添加盈利配置，满足条件的才打印"

## Execution Flow (main)
```
1. Parse user description from Input ✓
   → Feature: 三角套利机会监测和筛选
2. Extract key concepts from description ✓
   → Actor: 交易系统/交易员
   → Action: 获取价格、计算套利机会、筛选和打印
   → Data: 市场价格 (bid/ask)、套利机会、盈利配置
   → Constraint: 只观察不执行、满足盈利条件才打印
3. Clarifications needed:
   → [RESOLVED] 盈利阈值: 默认 0.5% (可配置)
   → [RESOLVED] 刷新频率: 实时监控或单次查询 (支持两种模式)
   → [RESOLVED] 输出格式: 控制台彩色输出 + 结构化日志
   → [RESOLVED] 交易对筛选: 支持基础货币白名单 (如只监控 USDT 相关)
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
交易系统需要实时监控加密货币市场的三角套利机会。系统获取所有市场的买一价和卖一价，计算可能存在的三角套利路径（如 USDT → BTC → ETH → USDT），并评估每条路径的预期收益率。只有当收益率超过设定阈值（扣除手续费后）时，系统才将该机会打印到控制台供交易员决策。系统不会自动执行交易，仅提供信息供人工判断。

### Acceptance Scenarios

1. **Given** 用户配置了最低盈利阈值为 0.5%，**When** 系统检测到一条三角套利路径（BTC/USDT → ETH/BTC → ETH/USDT）的预期收益率为 0.8%，**Then** 系统打印该机会的详细信息（路径、收益率、各环节价格）

2. **Given** 用户配置了最低盈利阈值为 0.5%，**When** 系统检测到一条路径的预期收益率为 0.3%（低于阈值），**Then** 系统不打印该机会，但在调试日志中记录

3. **Given** 用户启动单次查询模式，**When** 系统完成一次全市场扫描，**Then** 系统打印所有符合条件的机会后退出

4. **Given** 用户启动实时监控模式，**When** 系统每隔 N 秒刷新市场价格，**Then** 系统持续打印新发现的套利机会

5. **Given** 用户配置了基础货币白名单（USDT, BTC），**When** 系统扫描市场，**Then** 只计算包含这些基础货币的三角套利路径

6. **Given** 某个市场的价格数据无效（买价 > 卖价），**When** 系统遇到该市场，**Then** 跳过该市场并记录警告日志

7. **Given** 系统检测到多条套利机会，**When** 打印机会列表，**Then** 按预期收益率从高到低排序

### Edge Cases

- **Given** 所有市场都被扫描完毕但没有任何套利机会，**When** 系统完成扫描，**Then** 打印 "未发现套利机会" 消息
- **Given** 某个交易对的买一价格等于卖一价格（零价差），**When** 计算涉及该交易对的路径，**Then** 路径收益率为负（因为手续费），不满足打印条件
- **Given** 网络请求失败导致部分市场价格缺失，**When** 系统扫描市场，**Then** 使用可用的市场数据继续计算，并记录缺失市场
- **Given** 用户配置的盈利阈值为负数或非数值，**When** 系统启动，**Then** 拒绝启动并提示配置错误
- **Given** 三角套利路径涉及 3 个以上的交易环节，**When** 系统计算路径，**Then** 仅支持 3 环节路径（A→B→C→A），忽略更复杂的路径

## Requirements *(mandatory)*

### Functional Requirements

#### 数据获取
- **FR-001**: 系统MUST能够获取 XT 交易所所有活跃市场的实时买一价和卖一价
- **FR-002**: 系统MUST在价格数据无效时（如买价 > 卖价、价格为 0 或负数）跳过该市场并记录警告

#### 套利路径计算
- **FR-003**: 系统MUST识别并计算所有可能的三角套利路径（格式: A→B→C→A，如 USDT→BTC→ETH→USDT）
- **FR-004**: 系统MUST使用买一价和卖一价计算路径的预期收益率（考虑每个环节的价格和数量限制）
- **FR-005**: 系统MUST在计算收益率时扣除每个交易环节的手续费（默认 0.1% 每环节，可配置）
- **FR-006**: 系统MUST支持用户配置基础货币白名单，只计算包含白名单货币的路径（如只计算涉及 USDT 的路径）

#### 机会筛选
- **FR-007**: 系统MUST支持用户配置最低盈利阈值（默认 0.5%，可配置）
- **FR-008**: 系统MUST只打印预期收益率超过阈值的套利机会
- **FR-009**: 系统MUST将不满足阈值的机会记录到调试日志，不打印到控制台

#### 结果展示
- **FR-010**: 系统MUST将符合条件的套利机会打印到控制台，包含以下信息：
  - 套利路径（如 USDT → BTC → ETH → USDT）
  - 预期收益率（百分比）
  - 各环节的价格（买价/卖价）
  - 建议的初始投资金额（基于最小可交易量计算）
  - 发现时间戳
- **FR-011**: 系统MUST按预期收益率从高到低排序打印机会列表
- **FR-012**: 系统MUST使用彩色输出区分不同类型的信息（绿色=高收益，黄色=中等收益，白色=一般信息）

#### 运行模式
- **FR-013**: 系统MUST支持单次查询模式：扫描一次市场，打印机会后退出
- **FR-014**: 系统MUST支持实时监控模式：持续刷新市场价格，发现新机会时立即打印
- **FR-015**: 系统MUST在实时监控模式下，允许用户配置刷新间隔（默认 10 秒，可配置）
- **FR-016**: 系统MUST提供优雅退出机制（Ctrl+C 或 SIGTERM 信号），保存最后一次扫描结果

#### 配置管理
- **FR-017**: 系统MUST支持通过命令行参数或配置文件设置以下参数：
  - 最低盈利阈值（百分比）
  - 交易手续费率（每环节百分比）
  - 基础货币白名单（逗号分隔列表）
  - 刷新间隔（秒）
  - 运行模式（单次/实时）
- **FR-018**: 系统MUST在启动时验证配置参数的有效性，无效时拒绝启动并提示错误

#### 日志和调试
- **FR-019**: 系统MUST记录所有扫描活动到结构化日志（包括扫描时间、市场数量、发现的机会数量）
- **FR-020**: 系统MUST在调试模式下，记录所有计算的路径及其收益率（包括不满足阈值的）

### Key Entities

- **ArbitrageOpportunity (套利机会)**: 表示一条三角套利路径及其相关信息
  - 套利路径（3 个交易对的有序列表）
  - 预期收益率（百分比，扣除手续费后）
  - 各环节价格（买价/卖价）
  - 建议初始投资金额
  - 发现时间戳
  - 状态（新发现/已打印/已失效）

- **TradingPath (交易路径)**: 表示一条完整的三角套利路径
  - 起始货币（如 USDT）
  - 第一步交易对（如 BTC/USDT）
  - 第二步交易对（如 ETH/BTC）
  - 第三步交易对（如 ETH/USDT）
  - 路径是否形成闭环（回到起始货币）

- **MarketPrice (市场价格)**: 表示某个交易对的实时价格
  - 交易对标识（如 BTC/USDT）
  - 买一价（bid price）
  - 卖一价（ask price）
  - 买一量（bid volume）
  - 卖一量（ask volume）
  - 时间戳
  - 数据来源（XT 交易所）

- **MonitorConfig (监控配置)**: 表示系统的运行配置
  - 最低盈利阈值（默认 0.5%）
  - 交易手续费率（默认 0.1% 每环节）
  - 基础货币白名单（默认为空，表示监控所有货币）
  - 刷新间隔（默认 10 秒）
  - 运行模式（单次/实时）
  - 输出格式（控制台/日志文件/两者）

### Non-Functional Requirements

- **NFR-001**: 系统MUST在 1 秒内完成一次全市场扫描（包括获取价格和计算所有路径）
- **NFR-002**: 系统MUST能够处理至少 500 个交易对的市场数据而不出现性能问题
- **NFR-003**: 系统MUST在实时监控模式下，保持内存使用稳定（不超过 100MB）
- **NFR-004**: 系统MUST提供清晰易读的控制台输出，方便交易员快速识别机会
- **NFR-005**: 系统MUST在网络请求失败时自动重试（最多 3 次），避免因临时故障中断监控

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
- 依赖 Feature 003 的 `get_ticker()` 批量查询功能（获取所有市场价格）
- 依赖 XT 交易所 API 的稳定性和可用性

### Assumptions
- 假设 XT 交易所支持的交易对足够多，能够形成有意义的三角套利路径
- 假设市场价格数据的延迟足够低（< 1 秒），使得套利机会仍然有效
- 假设用户理解三角套利的基本概念，不需要额外的教育性说明
- 假设系统运行在稳定的网络环境，API 调用失败率 < 5%

### Out of Scope (不在范围内)
- 自动执行交易（系统只观察和打印机会）
- 账户余额管理和仓位跟踪
- 历史套利机会数据存储和分析
- 多交易所套利机会监测（仅支持 XT 交易所）
- 复杂套利路径（超过 3 个交易环节）
- 风险管理和止损策略
- 用户认证和权限管理

---

## Business Value (业务价值)

- **提升发现效率**: 自动化扫描市场，比人工监控快 100 倍以上
- **降低机会成本**: 实时发现套利机会，减少因延迟导致的利润损失
- **优化决策质量**: 提供详细的收益率计算和路径信息，辅助交易员做出更准确的决策
- **降低操作风险**: 只提供信息不执行交易，避免自动化交易的潜在风险
- **可扩展性**: 为未来支持多交易所、更复杂路径和自动执行打下基础
