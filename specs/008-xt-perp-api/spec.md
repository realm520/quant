# Feature Specification: XT永续合约交易所集成

**Feature Branch**: `008-xt-perp-api`
**Created**: 2025-10-11
**Status**: Draft
**Input**: 用户描述: "根据xt_perp_api.py 集成xt 永续合约，代码文件名为 xt_perp.py， 实现 XTPerpExchange类。使用 xt_perp_api.py 中的xt api集成逻辑，最主要是签名方式和api的端点，参数，返回。框架使用我们现有的基础框架"

## Execution Flow (main)
```
1. Parse user description from Input
   → Extract: XT永续合约API集成需求
2. Extract key concepts from description
   → Identify:
     - 基于xt_perp_api.py的API集成逻辑
     - XTPerpExchange类实现
     - 现有BaseExchange框架复用
     - 签名方式、端点、参数适配
3. For each unclear aspect:
   → [已明确] 使用xt_perp_api.py中的签名逻辑
   → [已明确] 实现BaseExchange接口
   → [已明确] 永续合约特定功能
4. Fill User Scenarios & Testing section
   → 明确用户场景：永续合约交易操作
5. Generate Functional Requirements
   → 基于BaseExchange接口 + 永续合约特性
6. Identify Key Entities
   → 永续合约特定实体（仓位、杠杆、资金费率等）
7. Run Review Checklist
   → 业务需求明确，可生成技术规格
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
作为量化交易系统用户，我需要通过统一接口访问XT交易所的永续合约市场，以便进行跨交易所的三角套利和永续合约交易策略。系统应该能够获取永续合约的市场数据（价格、订单簿、资金费率）、管理仓位（开仓、平仓、调整杠杆）、执行各类订单（市价、限价、计划委托、止盈止损）。

### Acceptance Scenarios

#### 场景1：获取永续合约市场数据
1. **Given** 系统已连接到XT永续合约交易所
   **When** 用户查询BTC/USDT永续合约的当前价格
   **Then** 系统返回包含买一价、卖一价、买一量、卖一量的价格信息

2. **Given** 系统已连接到XT永续合约交易所
   **When** 用户查询所有永续合约市场的价格信息
   **Then** 系统返回所有活跃永续合约的价格列表

3. **Given** 系统已连接到XT永续合约交易所
   **When** 用户查询ETH/USDT永续合约的订单簿深度
   **Then** 系统返回包含多档买卖盘的订单簿数据

4. **Given** 系统已连接到XT永续合约交易所
   **When** 用户查询合约的资金费率
   **Then** 系统返回当前资金费率和下次收取时间

#### 场景2：获取合约配置信息
1. **Given** 系统已连接到XT永续合约交易所
   **When** 用户查询BTC/USDT永续合约的配置信息
   **Then** 系统返回合约的精度、最小/最大下单量、杠杆档位、保证金率等完整配置

2. **Given** 系统已连接到XT永续合约交易所
   **When** 用户查询所有永续合约的配置信息
   **Then** 系统返回所有合约的配置列表，用于系统初始化

#### 场景3：执行永续合约订单
1. **Given** 用户账户有足够的USDT保证金
   **When** 用户下达开多BTC/USDT永续合约的市价单（数量10张）
   **Then** 系统成功提交订单并返回订单ID和状态

2. **Given** 用户账户有足够的保证金
   **When** 用户下达限价单（价格50000 USDT，数量5张）
   **Then** 系统成功提交限价单并返回订单详情

3. **Given** 用户已有开仓订单
   **When** 用户查询订单状态
   **Then** 系统返回订单的当前状态（已成交、部分成交、未成交、已取消等）

4. **Given** 用户有未成交的限价单
   **When** 用户取消该订单
   **Then** 系统成功取消订单并返回取消确认

#### 场景4：管理永续合约仓位
1. **Given** 用户已有BTC/USDT多头仓位
   **When** 用户查询当前仓位信息
   **Then** 系统返回仓位的详细信息（持仓数量、开仓均价、未实现盈亏、保证金、杠杆倍数、强平价格）

2. **Given** 用户已有仓位
   **When** 用户调整仓位的杠杆倍数（从10x调整到5x）
   **Then** 系统成功调整杠杆并返回新的保证金要求和强平价格

3. **Given** 用户有持仓
   **When** 用户设置止盈止损委托（止盈价55000，止损价45000）
   **Then** 系统成功设置条件单，当价格触发时自动平仓

#### 场景5：查询账户和历史信息
1. **Given** 系统已连接且用户已认证
   **When** 用户查询永续合约账户余额
   **Then** 系统返回可用余额、冻结保证金、未实现盈亏等账户信息

2. **Given** 用户已进行过永续合约交易
   **When** 用户查询历史成交记录
   **Then** 系统返回成交历史列表（交易ID、价格、数量、手续费、时间）

3. **Given** 用户已支付过资金费用
   **When** 用户查询资金费用历史
   **Then** 系统返回资金费用收支记录

### Edge Cases
- **网络超时**：API请求超时时系统如何处理？是否重试？重试几次？
- **余额不足**：保证金不足以开仓时系统如何提示用户？
- **强平风险**：仓位接近强平价格时系统如何预警？
- **API限流**：触发交易所API频率限制时系统如何应对？
- **仓位模式**：系统是否支持双向持仓模式？还是仅支持单向持仓？
- **API认证失败**：API密钥无效或过期时系统如何处理？
- **市价单滑点**：市价单执行时流动性不足导致较大滑点如何控制？
- **计划委托触发**：计划委托的触发条件和执行逻辑是否与XT交易所一致？

---

## Requirements *(mandatory)*

### Functional Requirements

#### 核心连接和认证
- **FR-001**: 系统MUST能够连接到XT永续合约交易所的REST API
- **FR-002**: 系统MUST支持使用API密钥和密钥进行HMAC-SHA256签名认证
- **FR-003**: 系统MUST在初始化时加载所有永续合约的配置信息并缓存
- **FR-004**: 系统MUST在连接失败时返回明确的错误信息（网络错误、认证失败、服务不可用等）

#### 市场数据查询
- **FR-005**: 系统MUST能够查询单个永续合约的实时价格（买一价、卖一价、买一量、卖一量）
- **FR-006**: 系统MUST能够批量查询所有活跃永续合约的实时价格
- **FR-007**: 系统MUST能够查询永续合约的订单簿深度（支持指定档位数，如5档、20档、200档）
- **FR-008**: 系统MUST能够查询永续合约的最新成交记录
- **FR-009**: 系统MUST能够查询永续合约的当前资金费率和下次资金费率
- **FR-010**: 系统MUST能够查询永续合约的历史资金费率记录
- **FR-011**: 系统MUST能够查询永续合约的标记价格
- **FR-012**: 系统MUST能够查询K线数据（支持多种时间周期：1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w）

#### 合约配置信息
- **FR-013**: 系统MUST能够查询单个永续合约的完整配置（价格精度、数量精度、最小/最大下单量、价格过滤器、数量过滤器）
- **FR-014**: 系统MUST能够批量查询所有永续合约的配置信息
- **FR-015**: 系统MUST能够查询永续合约的杠杆档位列表和对应的保证金率
- **FR-016**: 系统MUST缓存合约配置信息以提高性能，并提供手动刷新缓存的方法

#### 订单管理
- **FR-017**: 系统MUST能够下达市价单（做多/做多、开仓/平仓）
- **FR-018**: 系统MUST能够下达限价单（支持GTC、IOC、FOK等时效类型）
- **FR-019**: 系统MUST能够批量下单（一次提交多个订单）
- **FR-020**: 系统MUST能够取消单个订单
- **FR-021**: 系统MUST能够批量取消订单
- **FR-022**: 系统MUST能够取消某个合约的所有订单
- **FR-023**: 系统MUST能够查询单个订单的详细状态
- **FR-024**: 系统MUST能够查询当前活跃订单列表（支持按合约筛选、分页查询）
- **FR-025**: 系统MUST能够查询历史订单记录（支持按合约、时间范围、订单ID筛选）

#### 计划委托和条件单
- **FR-026**: 系统MUST能够下达计划委托单（触发价、委托类型、委托数量）
- **FR-027**: 系统MUST能够取消单个计划委托
- **FR-028**: 系统MUST能够取消某个合约的所有计划委托
- **FR-029**: 系统MUST能够查询当前计划委托列表
- **FR-030**: 系统MUST能够查询计划委托的历史记录
- **FR-031**: 系统MUST能够设置止盈止损委托（同时设置止盈价和止损价）
- **FR-032**: 系统MUST能够修改已有的止盈止损委托
- **FR-033**: 系统MUST能够取消止盈止损委托

#### 仓位管理
- **FR-034**: 系统MUST能够查询单个合约的当前仓位信息（持仓数量、开仓均价、未实现盈亏、保证金、杠杆、强平价格）
- **FR-035**: 系统MUST能够查询所有合约的仓位列表
- **FR-036**: 系统MUST能够调整仓位的杠杆倍数（支持逐仓和全仓模式）
- **FR-037**: 系统MUST能够一键平仓所有仓位

#### 账户信息
- **FR-038**: 系统MUST能够查询永续合约账户余额（可用余额、已用保证金、未实现盈亏）
- **FR-039**: 系统MUST能够查询账户的成交历史记录
- **FR-040**: 系统MUST能够查询账户的资金费用历史记录

#### 数据模型映射
- **FR-041**: 系统MUST将XT永续合约API返回的订单状态映射到内部OrderStatus枚举（NEW→OPEN, FILLED→FILLED, PARTIALLY_FILLED→PARTIALLY_FILLED, CANCELED→CANCELLED）
- **FR-042**: 系统MUST将XT永续合约API返回的交易方向映射到内部OrderSide枚举（BUY→BUY, SELL→SELL）
- **FR-043**: 系统MUST将XT永续合约API的合约符号格式（如btc_usdt）转换为内部TradingPair对象

#### 错误处理
- **FR-044**: 系统MUST在API请求失败时提供详细的错误信息（包括错误代码、错误描述）
- **FR-045**: 系统MUST对网络超时和临时性错误进行自动重试（最多3次，使用指数退避策略）
- **FR-046**: 系统MUST在认证失败时明确提示用户检查API密钥配置
- **FR-047**: 系统MUST在余额不足时返回明确的错误提示
- **FR-048**: 系统MUST记录所有关键操作的日志，包括订单提交、取消、仓位变更等

#### 性能要求
- **FR-049**: 系统MUST在50ms内完成订单提交（从调用到API请求发出，不含网络传输）
- **FR-050**: 系统MUST支持并发请求，在高频交易场景下保持稳定性
- **FR-051**: 系统MUST使用HTTP连接池复用连接，减少连接建立开销

### Key Entities *(include if feature involves data)*

#### 永续合约仓位 (PerpetualPosition)
- 合约符号（trading_pair）
- 仓位方向（多头/空头：LONG/SHORT）
- 持仓数量（position_quantity）
- 开仓均价（average_entry_price）
- 当前标记价格（mark_price）
- 未实现盈亏（unrealized_pnl）
- 已用保证金（margin）
- 杠杆倍数（leverage）
- 强平价格（liquidation_price）
- 保证金模式（逐仓/全仓：ISOLATED/CROSS）
- 持仓状态（OPEN/CLOSED）

#### 永续合约订单 (PerpetualOrder)
- 订单ID（order_id）
- 合约符号（trading_pair）
- 订单方向（买入/卖出：BUY/SELL）
- 仓位方向（开多/开空/平多/平空：LONG/SHORT）
- 订单类型（市价/限价：MARKET/LIMIT）
- 价格（price，市价单为空）
- 数量（quantity）
- 已成交数量（filled_quantity）
- 订单状态（NEW/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED）
- 时效类型（GTC/IOC/FOK/POST_ONLY）
- 创建时间（created_at）
- 更新时间（updated_at）
- 客户端订单ID（client_order_id，可选）

#### 计划委托 (PlanOrder)
- 委托ID（entrust_id）
- 合约符号（trading_pair）
- 触发价格类型（最新价/标记价：LAST/MARK）
- 触发价格（trigger_price）
- 委托类型（限价/市价：LIMIT/MARKET）
- 委托价格（order_price，市价为空）
- 委托数量（quantity）
- 订单方向（BUY/SELL）
- 仓位方向（LONG/SHORT）
- 委托状态（未触发/已触发/已取消：NOT_TRIGGERED/TRIGGERED/CANCELED）
- 创建时间（created_at）

#### 止盈止损委托 (StopProfit)
- 委托ID（profit_id）
- 合约符号（trading_pair）
- 止盈价格（profit_price，可选）
- 止损价格（stop_price，可选）
- 委托数量（quantity）
- 仓位方向（LONG/SHORT）
- 到期时间（expire_time）
- 委托状态（NOT_TRIGGERED/TRIGGERED/CANCELED）
- 创建时间（created_at）

#### 资金费率 (FundingRate)
- 合约符号（trading_pair）
- 当前资金费率（current_rate）
- 下次资金费率（next_rate）
- 下次收取时间（next_funding_time）
- 时间戳（timestamp）

#### 合约配置 (PerpetualSymbolInfo)
- 合约符号（symbol）
- 基础货币（base_currency）
- 计价货币（quote_currency）
- 价格精度（price_precision）
- 数量精度（quantity_precision）
- 最小下单价格（min_price）
- 最大下单价格（max_price）
- 价格步长（price_step）
- 最小下单量（min_quantity）
- 最大下单量（max_quantity）
- 数量步长（quantity_step）
- 最小名义价值（min_notional）
- 做市商手续费率（maker_fee）
- 吃单手续费率（taker_fee）
- 杠杆档位（leverage_brackets：列表，包含每档的最大持仓量和保证金率）
- 合约状态（ONLINE/OFFLINE/HALT）

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
- [x] Scope is clearly bounded (XT永续合约API集成，不包括现货API)
- [x] Dependencies identified (依赖BaseExchange框架、现有的XT签名逻辑)

---

## Execution Status

- [x] User description parsed
- [x] Key concepts extracted (永续合约交易、仓位管理、计划委托、资金费率)
- [x] Ambiguities marked (边界情况已标记)
- [x] User scenarios defined (5个主要场景，覆盖查询、交易、仓位管理)
- [x] Requirements generated (51个功能需求，覆盖所有核心功能)
- [x] Entities identified (6个核心实体：仓位、订单、计划委托、止盈止损、资金费率、合约配置)
- [x] Review checklist passed (业务需求明确，可进入技术设计阶段)

---

## 附录：与现货交易的主要差异

为了帮助理解永续合约集成的特殊性，以下列出与现货交易的关键差异：

### 核心概念差异
1. **仓位 vs 余额**：永续合约有仓位概念（持仓数量、方向、杠杆），现货仅有资产余额
2. **保证金 vs 全额资金**：永续合约使用保证金交易，现货需全额资金
3. **双向交易**：永续合约可做多做空，现货仅能买入卖出已持有资产
4. **资金费率**：永续合约定期收取资金费用，现货无此概念
5. **强平机制**：永续合约有强制平仓风险，现货无此风险

### API端点差异
- 现货API基础URL：`https://sapi.xt.com`
- 永续合约API基础URL：`https://fapi.xt.com`

### 数据结构差异
- 现货订单无需指定仓位方向（positionSide）
- 永续合约需要区分开仓/平仓、多头/空头
- 永续合约返回数据包含仓位、杠杆、保证金等额外字段

### 风险控制差异
- 永续合约需监控保证金率、强平价格
- 永续合约需管理杠杆倍数
- 永续合约需考虑资金费率对收益的影响
