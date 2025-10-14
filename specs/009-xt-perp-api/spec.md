# Feature Specification: XT 交易所统一 CLI 工具 (CEXTools)

**Feature Branch**: `009-xt-perp-api`
**Created**: 2025-10-11
**Updated**: 2025-10-11
**Status**: Draft
**Input**: User description: "基于当前xt perp api实现cli命令进行perp账户和行情的相关操作，功能和xt spot类似。合并到cextools命令下，用option指定spot和perp"

## Execution Flow (main)
```
1. Parse user description from Input ✓
   → Feature: XT 交易所统一 CLI 工具，支持现货和永续合约
2. Extract key concepts from description ✓
   → Actor: 交易员/系统管理员
   → Action: 查询账户余额、查询持仓、查询市场行情、设置杠杆、下单管理
   → Data: 账户余额、持仓信息、市场价格、资金费率、订单信息
   → Constraint: 统一命令行界面 (cextools)、通过 --exchange-type 区分 spot/perp
3. Clarifications needed:
   → [RESOLVED] CLI 命令结构: 统一 cextools 命令 + --exchange-type 选项 (spot|perp)
   → [RESOLVED] 命令组织: 主命令结构 (cextools account, cextools market, cextools order)
   → [RESOLVED] 输出格式: Rich 表格 + 彩色输出
   → [RESOLVED] 交互模式: 单次查询为主，可选实时监控模式
   → [RESOLVED] 错误处理: 显示友好错误消息，提供调试模式
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
交易员需要通过统一的命令行工具 `cextools` 快速查询 XT 交易所的账户信息、持仓状态和市场行情，支持现货（spot）和永续合约（perp）两种交易类型。用户通过 `--exchange-type` 选项指定要操作的交易类型，系统会自动路由到相应的 API 进行查询。用户可以查看账户余额、当前持仓、实时价格、资金费率（仅 perp）、订单状态等关键信息，也可以进行基础的交易操作，如设置杠杆（仅 perp）、下单、取消订单等。所有操作都通过清晰的表格和彩色输出展示，方便用户快速理解和决策。

### Acceptance Scenarios

#### 账户管理场景
1. **Given** 用户已配置 XT API 凭证，**When** 用户执行 `cextools --exchange-type perp account balance` 命令，**Then** 系统显示永续合约账户所有币种的可用余额和冻结余额，以表格形式展示

2. **Given** 用户已配置 XT API 凭证，**When** 用户执行 `cextools --exchange-type perp account positions` 命令，**Then** 系统显示所有当前永续合约持仓，包括交易对、方向（多/空）、数量、未实现盈亏、收益率等信息

3. **Given** 用户持有 BTC/USDT 永续合约多头仓位，**When** 用户执行 `cextools --exchange-type perp account positions --symbol BTC/USDT`，**Then** 系统只显示 BTC/USDT 的持仓信息

4. **Given** 用户当前没有任何永续合约持仓，**When** 用户执行 `cextools --exchange-type perp account positions`，**Then** 系统显示 "当前无持仓" 消息

5. **Given** 用户想查询现货账户余额，**When** 用户执行 `cextools --exchange-type spot account balance` 命令，**Then** 系统显示现货账户所有币种的可用余额和冻结余额

6. **Given** 用户省略 --exchange-type 参数，**When** 用户执行 `cextools account balance`，**Then** 系统提示 "请使用 --exchange-type 指定交易类型 (spot 或 perp)"

#### 市场行情场景
7. **Given** 用户想查看 BTC/USDT 永续合约价格，**When** 用户执行 `cextools --exchange-type perp market ticker --symbol BTC/USDT`，**Then** 系统显示当前的买一价、卖一价、最新价、24h 涨跌幅等信息

8. **Given** 用户想查看所有活跃永续合约，**When** 用户执行 `cextools --exchange-type perp market ticker`，**Then** 系统显示所有活跃永续合约的价格信息列表

9. **Given** 用户想查看现货 ETH/USDT 的订单簿深度，**When** 用户执行 `cextools --exchange-type spot market depth --symbol ETH/USDT --limit 10`，**Then** 系统显示前 10 档的买单和卖单价格及数量

10. **Given** 用户想查看 BTC/USDT 永续合约的资金费率，**When** 用户执行 `cextools --exchange-type perp market funding --symbol BTC/USDT`，**Then** 系统显示当前资金费率和下次结算时间

11. **Given** 用户想实时监控永续合约 BTC/USDT 价格变化，**When** 用户执行 `cextools --exchange-type perp market watch --symbol BTC/USDT --interval 5`，**Then** 系统每 5 秒刷新并显示最新价格，直到用户按 Ctrl+C 退出

12. **Given** 用户在 market 子命令中省略 --exchange-type，**When** 用户执行 `cextools market ticker --symbol BTC/USDT`，**Then** 系统默认查询现货市场（spot）的价格

#### 订单管理场景
13. **Given** 用户想开 BTC/USDT 永续合约多头仓位，**When** 用户执行 `cextools --exchange-type perp order place --symbol BTC/USDT --side BUY --position-side LONG --quantity 0.01 --order-type MARKET`，**Then** 系统提交市价单并显示订单 ID 和状态

14. **Given** 用户想以限价在现货市场买入 BTC，**When** 用户执行 `cextools --exchange-type spot order place --symbol BTC/USDT --side BUY --quantity 0.01 --order-type LIMIT --price 50000`，**Then** 系统提交限价单并显示订单详情

15. **Given** 用户想查看永续合约订单状态，**When** 用户执行 `cextools --exchange-type perp order status --order-id 123456`，**Then** 系统显示订单的详细状态（已提交/部分成交/完全成交/已取消）

16. **Given** 用户想取消现货订单，**When** 用户执行 `cextools --exchange-type spot order cancel --order-id 123456`，**Then** 系统取消订单并显示操作结果

17. **Given** 用户想取消永续合约 BTC/USDT 的所有挂单，**When** 用户执行 `cextools --exchange-type perp order cancel-all --symbol BTC/USDT`，**Then** 系统批量取消该交易对的所有永续合约订单并显示取消数量

#### 杠杆管理场景（仅永续合约）
18. **Given** 用户想设置 BTC/USDT 永续合约的杠杆倍数，**When** 用户执行 `cextools --exchange-type perp leverage set --symbol BTC/USDT --leverage 10`，**Then** 系统设置杠杆为 10 倍并显示操作结果

19. **Given** 用户想查看 BTC/USDT 永续合约的当前杠杆设置，**When** 用户执行 `cextools --exchange-type perp leverage info --symbol BTC/USDT`，**Then** 系统显示当前杠杆倍数和可用的杠杆范围

20. **Given** 用户尝试在现货交易中使用 leverage 命令，**When** 用户执行 `cextools --exchange-type spot leverage set --symbol BTC/USDT --leverage 10`，**Then** 系统显示错误 "leverage 命令仅适用于永续合约（perp），现货交易不支持杠杆"

21. **Given** 用户尝试设置超过允许范围的杠杆，**When** 用户执行 `cextools --exchange-type perp leverage set --symbol BTC/USDT --leverage 150`，**Then** 系统拒绝操作并显示允许的杠杆范围（1-125x）

### Edge Cases

- **Given** 用户未配置 API 凭证，**When** 用户执行任何需要认证的命令，**Then** 系统显示错误消息 "请先配置 XT API 凭证环境变量：XT_API_KEY 和 XT_API_SECRET（现货）或 XT_PERP_API_KEY 和 XT_PERP_API_SECRET（永续）"

- **Given** API 请求超时（网络问题），**When** 用户执行任何命令，**Then** 系统显示友好的错误消息 "网络请求超时，请检查网络连接"，并在调试模式下显示详细错误

- **Given** 用户输入不存在的交易对，**When** 用户执行 `cextools --exchange-type perp market ticker --symbol INVALID/PAIR`，**Then** 系统显示 "交易对不存在或未上线永续合约" 错误

- **Given** 用户在永续合约账户余额不足，**When** 用户尝试开仓，**Then** 系统显示 "账户余额不足，可用保证金: XXX USDT，所需保证金: YYY USDT"

- **Given** 命令行参数格式错误，**When** 用户执行命令，**Then** 系统显示参数使用帮助，并标明错误的参数

- **Given** 用户在实时监控模式下按 Ctrl+C，**When** 系统收到中断信号，**Then** 系统优雅退出，显示 "监控已停止" 消息

- **Given** 用户使用无效的 --exchange-type 值，**When** 用户执行 `cextools --exchange-type invalid account balance`，**Then** 系统显示错误 "无效的交易类型，请使用 'spot' 或 'perp'"

- **Given** 用户在永续合约操作中遗漏 --position-side，**When** 用户执行 `cextools --exchange-type perp order place --symbol BTC/USDT --side BUY --quantity 0.01`，**Then** 系统提示 "永续合约下单需要指定 --position-side (LONG 或 SHORT)"

- **Given** 用户尝试查询现货市场的资金费率，**When** 用户执行 `cextools --exchange-type spot market funding --symbol BTC/USDT`，**Then** 系统显示 "资金费率仅适用于永续合约，现货市场没有资金费率"

## Requirements *(mandatory)*

### Functional Requirements

#### CLI 命令结构
- **FR-001**: 系统MUST提供统一的 `cextools` 主命令，下设子命令组：`account`（账户）、`market`（市场）、`order`（订单）、`leverage`（杠杆）
- **FR-002**: 系统MUST支持全局参数 `--exchange-type`，接受值为 `spot`（现货）或 `perp`（永续合约）
- **FR-003**: 对于 account 和 order 子命令，`--exchange-type` MUST为必选参数
- **FR-004**: 对于 market 子命令，`--exchange-type` 为可选参数，默认值为 `spot`
- **FR-005**: 对于 leverage 子命令，系统MUST验证 `--exchange-type` 为 `perp`，否则拒绝执行并显示错误
- **FR-006**: 所有子命令MUST支持 `--help` 参数，显示命令用法和参数说明
- **FR-007**: 系统MUST支持 `--debug` 全局参数，启用详细日志输出（包括 API 请求详情）
- **FR-008**: 系统MUST支持 `--output` 参数，指定输出格式（table/json/csv），默认为 table
- **FR-009**: 当用户省略必选的 `--exchange-type` 参数时，系统MUST显示友好的错误提示

#### 账户管理命令
- **FR-010**: 系统MUST提供 `cextools account balance` 命令，根据 `--exchange-type` 参数路由到现货或永续合约账户
- **FR-011**: 余额显示MUST包含：币种、可用余额、冻结余额、总余额
- **FR-012**: 系统MUST提供 `cextools account positions` 命令，显示当前持仓（仅永续合约支持）
- **FR-013**: 当用户对现货账户使用 positions 命令时，系统MUST显示 "现货账户不支持持仓查询，请使用 --exchange-type perp"
- **FR-014**: 永续合约持仓显示MUST包含：交易对、方向（LONG/SHORT）、数量、开仓均价、当前价格、未实现盈亏、收益率（ROE）、杠杆倍数
- **FR-015**: `cextools account positions` 命令MUST支持 `--symbol` 参数，筛选特定交易对的持仓

#### 市场行情命令
- **FR-010**: 系统MUST提供 `cextools market ticker` 命令，查询实时价格
- **FR-011**: ticker 显示MUST包含：交易对、买一价、卖一价、最新价、24h 涨跌幅、24h 成交量
- **FR-012**: `cextools market ticker` 命令MUST支持 `--symbol` 参数，查询特定交易对；不指定时显示所有活跃合约
- **FR-013**: 系统MUST提供 `cextools market depth` 命令，查询订单簿深度
- **FR-014**: depth 显示MUST包含：买单列表（价格、数量）、卖单列表（价格、数量）
- **FR-015**: `cextools market depth` 命令MUST支持 `--limit` 参数，指定显示档数（默认 10 档，范围 5-50）
- **FR-016**: 系统MUST提供 `cextools market funding` 命令，查询资金费率
- **FR-017**: funding 显示MUST包含：交易对、当前资金费率（百分比）、下次结算时间
- **FR-018**: 系统MUST提供 `cextools market watch` 命令，实时监控价格变化
- **FR-019**: watch 命令MUST支持 `--interval` 参数，指定刷新间隔（秒，默认 5 秒，范围 1-60）
- **FR-020**: watch 命令MUST支持 Ctrl+C 优雅退出，显示停止消息

#### 订单管理命令
- **FR-021**: 系统MUST提供 `cextools order place` 命令，提交订单
- **FR-022**: place 命令MUST支持参数：`--symbol`（交易对）、`--side`（BUY/SELL）、`--position-side`（LONG/SHORT）、`--quantity`（数量）、`--order-type`（MARKET/LIMIT）
- **FR-023**: place 命令在 LIMIT 订单时MUST要求 `--price` 参数
- **FR-024**: place 命令MUST在提交前显示订单摘要，要求用户确认（除非使用 `--yes` 参数跳过确认）
- **FR-025**: 订单提交后MUST显示：订单 ID、交易对、方向、类型、数量、价格（限价单）、状态
- **FR-026**: 系统MUST提供 `cextools order status` 命令，查询订单状态
- **FR-027**: status 命令MUST支持 `--order-id` 参数，指定订单 ID
- **FR-028**: status 显示MUST包含：订单 ID、交易对、方向、类型、数量、价格、已成交数量、状态、创建时间
- **FR-029**: 系统MUST提供 `cextools order cancel` 命令，取消单个订单
- **FR-030**: cancel 命令MUST支持 `--order-id` 参数，指定要取消的订单 ID
- **FR-031**: 系统MUST提供 `cextools order cancel-all` 命令，批量取消订单
- **FR-032**: cancel-all 命令MUST支持 `--symbol` 参数，指定交易对；不指定时取消所有订单
- **FR-033**: cancel-all 命令MUST在执行前显示将要取消的订单数量，要求用户确认（除非使用 `--yes` 参数）

#### 杠杆管理命令
- **FR-034**: 系统MUST提供 `cextools leverage set` 命令，设置杠杆倍数
- **FR-035**: set 命令MUST支持参数：`--symbol`（交易对）、`--leverage`（杠杆倍数，范围 1-125）
- **FR-036**: set 命令MUST在设置前验证杠杆范围，超出范围时拒绝操作并显示允许的范围
- **FR-037**: 系统MUST提供 `cextools leverage info` 命令，查询当前杠杆设置
- **FR-038**: info 命令MUST显示：交易对、当前杠杆倍数、允许的杠杆范围（基于持仓名义价值的杠杆梯度）

#### 输出格式和展示
- **FR-039**: 系统MUST使用表格组件展示结构化数据（余额、持仓、订单等）
- **FR-040**: 系统MUST使用颜色区分不同类型的信息：绿色（盈利/成功）、红色（亏损/错误）、黄色（警告/待确认）、白色/灰色（一般信息）
- **FR-041**: 数值显示MUST保持适当精度：价格（8 位小数）、数量（8 位小数）、百分比（2 位小数）
- **FR-042**: 系统MUST在表格底部显示时间戳（数据获取时间）

#### 配置和认证
- **FR-043**: 系统MUST根据 `--exchange-type` 参数选择相应的 API 凭证：
  - `spot`: 使用 `XT_API_KEY` 和 `XT_API_SECRET`
  - `perp`: 使用 `XT_PERP_API_KEY` 和 `XT_PERP_API_SECRET`
- **FR-044**: 系统MUST在启动时验证对应交易类型的 API 凭证是否配置，未配置时显示配置指引
- **FR-045**: 系统MUST支持通过 `--api-key` 和 `--api-secret` 命令行参数临时覆盖环境变量
- **FR-046**: 系统MUST在调试模式下隐藏敏感信息（API 密钥只显示前 4 位和后 4 位）
- **FR-047**: 系统MUST在 `--help` 输出中清晰说明不同交易类型所需的环境变量

#### 错误处理
- **FR-048**: 系统MUST在 API 请求失败时显示友好的错误消息（非技术术语）
- **FR-049**: 系统MUST在调试模式下显示完整的错误堆栈和 API 响应详情
- **FR-050**: 系统MUST为常见错误提供解决建议（如余额不足 → "请充值或降低开仓数量"）
- **FR-051**: 系统MUST在网络错误时自动重试（最多 3 次），显示重试进度
- **FR-052**: 系统MUST在用户使用不匹配的命令和交易类型时显示清晰的错误提示（如对 spot 使用 leverage 命令）

### Key Entities

- **CEXTools CLI Command (统一 CLI 命令)**: 表示一个完整的命令行命令
  - 主命令：cextools
  - 交易类型选项：--exchange-type (spot|perp)
  - 命令组（account/market/order/leverage）
  - 子命令（balance/positions/ticker/place 等）
  - 参数列表（symbol, quantity, price 等）
  - 全局选项（debug, output, help）

- **Account Balance Display (账户余额展示)**: 表示账户余额的展示数据
  - 币种列表
  - 可用余额和冻结余额
  - 数据获取时间戳

- **Position Display (持仓展示)**: 表示持仓信息的展示数据
  - 交易对和持仓方向
  - 数量、开仓价格、当前价格
  - 未实现盈亏和收益率
  - 杠杆倍数

- **Market Ticker Display (市场行情展示)**: 表示市场价格的展示数据
  - 交易对
  - 买一价/卖一价/最新价
  - 24h 涨跌幅和成交量

- **Order Summary (订单摘要)**: 表示订单信息的展示数据
  - 订单基本信息（ID、交易对、方向）
  - 订单参数（类型、数量、价格）
  - 订单状态和成交情况

### Non-Functional Requirements

- **NFR-001**: 命令MUST在 2 秒内返回结果（不包括网络延迟）
- **NFR-002**: 系统MUST支持至少 50 个并发 API 请求而不出现性能问题
- **NFR-003**: 表格输出MUST自动适应终端宽度，避免换行导致的可读性问题
- **NFR-004**: 系统MUST在资源受限环境（512MB 内存）下正常运行
- **NFR-005**: 命令行帮助文档MUST清晰易懂，包含使用示例
- **NFR-006**: 系统MUST兼容主流操作系统（Linux, macOS, Windows）
- **NFR-007**: 实时监控模式MUST保持内存使用稳定（不超过 50MB）

---

## Review & Acceptance Checklist

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
- 依赖 Feature 008 的 `XTPerpExchange` 实现（永续合约 API 方法必须可用）
- 依赖 `XTSpotExchange` 实现（现货 API 方法必须可用）
- 依赖 XT 交易所现货和永续合约 API 的稳定性和可用性

### Assumptions
- 假设用户已经有 XT 交易所账户和对应的 API 凭证（现货和/或永续合约）
- 假设用户理解现货和永续合约的区别
- 假设用户理解永续合约的基本概念（多空、杠杆、资金费率等）
- 假设用户运行命令的终端支持 Unicode 和 ANSI 颜色
- 假设网络延迟合理（< 500ms），API 可用性 > 99%
- 假设用户不会频繁切换 --exchange-type 导致混淆

### Out of Scope (不在范围内)
- 交互式 TUI（Text User Interface）模式
- 历史数据查询和分析（K 线、成交历史等）
- 高级订单类型（条件单、跟踪止损等）
- 批量下单功能
- 多账户管理
- 配置文件管理
- 通知和告警功能
- 自动化交易脚本支持
- 图形化展示

---

## Business Value (业务价值)

- **统一用户体验**: 通过单一 `cextools` 命令管理现货和永续合约，降低认知负担
- **提升操作效率**: 命令行操作比 Web 界面快 3-5 倍，支持快速切换交易类型
- **降低学习成本**: 统一的命令结构，用户学习一次即可操作两种交易类型
- **增强可脚本化**: 支持 JSON 输出，方便集成到自动化脚本和监控系统
- **降低操作风险**: 重要操作提供确认机制，交易类型明确标识避免混淆
- **提升调试能力**: 调试模式显示完整的 API 交互，支持按交易类型过滤日志
- **支持远程操作**: 命令行接口方便通过 SSH 远程管理多种交易账户
- **灵活的扩展性**: 清晰的 --exchange-type 模式为未来添加更多交易类型（如期权、杠杆代币）打下基础
- **减少重复开发**: 统一框架避免为不同交易类型重复开发相似功能
