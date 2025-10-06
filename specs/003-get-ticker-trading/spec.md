# Feature Specification: Get All Market Tickers

**Feature Branch**: `003-get-ticker-trading`
**Created**: 2025-10-06
**Status**: Ready for Planning
**Input**: User description: "修改get_ticker的实现，如果传入空trading_pair，返回所有市场的ticker"

## Execution Flow (main)
```
1. Parse user description from Input
   → Feature clear: extend get_ticker to support fetching all market tickers
2. Extract key concepts from description
   → Actor: trading system
   → Action: retrieve ticker data
   → Data: market prices (bid/ask/volume)
   → Constraint: optional parameter behavior (None = all markets)
3. Clarifications received from user:
   ✅ Market scope: All active trading markets (open for trading)
   ✅ Performance target: <1 second response time
   ✅ Fallback strategy: Return error if batch API not supported
   ✅ Caching: No caching required
   ✅ Data integrity: Return partial results on partial failures
4. User Scenarios & Testing section completed
5. Functional Requirements generated (all testable)
6. Key Entities identified (Price, TradingPair)
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
交易系统需要获取市场价格信息，以便进行三角套利机会扫描。当扫描单个交易对时，系统传入具体的交易对参数；当进行全市场扫描时，系统希望一次性获取所有市场的ticker数据，而不是逐个调用API，以提高效率并降低API调用次数。

### Acceptance Scenarios
1. **Given** 用户想查询BTC/USDT的当前价格, **When** 调用get_ticker并传入BTC/USDT交易对, **Then** 系统返回该交易对的买卖价格、成交量等信息
2. **Given** 用户想扫描所有市场寻找套利机会, **When** 调用get_ticker并传入None（或不传入参数）, **Then** 系统返回所有可用市场的ticker信息列表
3. **Given** 用户想获取特定交易所的所有市场价格, **When** 调用get_ticker时不传入trading_pair参数, **Then** 系统返回该交易所支持的所有交易对的ticker数据
4. **Given** 某个市场暂时无交易或数据不可用, **When** 请求所有市场ticker时, **Then** 系统应能优雅处理该市场，不影响其他市场数据的返回

### Edge Cases
- **Given** 交易所没有任何活跃市场, **When** 请求所有市场ticker, **Then** 系统返回空列表
- **Given** 请求所有市场但某些市场数据获取失败, **When** 批量查询执行, **Then** 系统返回成功获取的数据并记录失败的市场
- **Given** 交易所不支持批量ticker查询API, **When** 传入None参数请求所有市场, **Then** 系统返回明确的错误信息
- **Given** 批量查询响应时间超过1秒, **When** 性能监控检测到超时, **Then** 系统记录性能警告日志

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: 系统MUST支持通过传入具体TradingPair参数获取单个市场的ticker数据
- **FR-002**: 系统MUST支持通过传入None或不传参数获取所有开放交易市场的ticker数据
- **FR-003**: 系统MUST在获取所有市场ticker时，返回一个包含所有活跃市场Price数据的集合
- **FR-004**: 系统MUST确保单个市场查询和批量查询的返回数据格式一致（都包含bid_price, ask_price, bid_volume, ask_volume, timestamp等字段）
- **FR-005**: 系统MUST在API文档中明确说明trading_pair参数为可选参数，并解释不同参数值的行为差异
- **FR-006**: 系统MUST保持向后兼容性，现有传入TradingPair的调用不应受到影响
- **FR-007**: 系统MUST在交易所不支持批量ticker查询API时，抛出NotImplementedError异常，提示该交易所不支持批量查询
- **FR-008**: 系统MUST在批量查询部分失败时，返回成功获取的数据，并在日志中记录失败的市场信息
- **FR-009**: 系统MUST在批量查询失败时提供清晰的错误信息，说明失败原因和影响范围
- **FR-010**: 系统MUST在返回数据中包含每个ticker的时间戳，以便用户判断数据新鲜度
- **FR-011**: 系统MUST确保批量查询不使用缓存，每次都从交易所获取最新数据
- **FR-012**: 系统MUST在批量查询中，当部分市场数据获取失败时，返回成功部分并记录失败的市场列表

### Key Entities *(include if feature involves data)*
- **Price**: 表示某个交易对的价格信息，包含bid_price（买价）、ask_price（卖价）、bid_volume（买量）、ask_volume（卖量）、timestamp（时间戳）、exchange（交易所标识）等属性
- **TradingPair**: 表示交易对，包含base_currency（基础货币）、quote_currency（报价货币）、exchange（所属交易所）等属性；在批量查询场景下，每个返回的Price对象都应关联到其对应的TradingPair

### Non-Functional Requirements
- **NFR-001**: 批量ticker查询的响应时间MUST在1秒内完成（包括网络请求和数据解析）
- **NFR-002**: 系统MUST能够处理交易所返回的大量市场数据（至少支持500个交易对）而不出现内存溢出
- **NFR-003**: API调用MUST有适当的错误重试机制，避免因临时网络问题导致整体查询失败
- **NFR-004**: 返回的数据结构MUST便于后续处理和过滤（例如按交易量、价差等条件筛选）
- **NFR-005**: 系统MUST在批量查询响应时间超过1秒时记录性能警告日志
- **NFR-006**: 系统MUST确保批量查询不会因为单个市场的失败而影响整体性能（超时设置合理）

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

## Clarification Decisions (用户澄清的决策)

1. **市场范围**: ✅ 返回所有开放交易的市场（active trading markets）

2. **性能目标**: ✅ 批量查询的响应时间目标为1秒内完成

3. **降级策略**: ✅ 当交易所不支持批量ticker查询API时，直接返回错误（NotImplementedError）

4. **缓存策略**: ✅ 不需要缓存，每次都从交易所获取最新数据

5. **数据完整性**: ✅ 当批量查询中某些市场数据获取失败时，返回成功获取的部分，并记录失败的市场

---

## Business Value (业务价值)

- **提升效率**: 减少API调用次数，从N次（N=市场数量）降低到1次，显著提升全市场扫描速度
- **降低成本**: 减少API调用可能降低交易所API使用费用（如果按调用次数计费）
- **改善用户体验**: 更快的市场数据获取意味着更及时的套利机会发现
- **系统可扩展性**: 为未来支持多交易所同时扫描打下基础
