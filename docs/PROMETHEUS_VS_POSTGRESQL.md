# Prometheus vs PostgreSQL 数据源对比

## 为什么当前使用 PostgreSQL？

### 当前架构

1. **数据存储**：持仓指标直接存储在 PostgreSQL 的 `position_metrics` 表中
2. **计算方式**：每 5 分钟计算一次，直接写入数据库
3. **查询方式**：Grafana 通过 PostgreSQL 数据源直接查询数据库

### 使用 PostgreSQL 的优势

✅ **简单直接**：
- 数据已经存储在 PostgreSQL 中，无需额外导出步骤
- 可以直接用 SQL 查询，灵活且强大
- 不需要额外的服务或中间层

✅ **数据持久化**：
- 数据永久保存在数据库中
- 可以查询任意历史时间点的数据
- 支持复杂的数据分析和报表

✅ **SQL 灵活性**：
- 可以使用复杂的 SQL 查询和聚合
- 支持 JOIN、子查询等高级功能
- 可以创建物化视图优化查询性能

## 使用 Prometheus 的方案

### Prometheus 的优势

✅ **时序数据优化**：
- Prometheus 专门为时序数据设计
- 高效的压缩和存储
- 内置的查询语言 PromQL

✅ **统一监控**：
- 可以与其他系统指标统一管理
- 使用相同的监控基础设施
- 统一的告警规则

✅ **实时性**：
- 数据实时更新（通过 pull 方式）
- 适合实时监控场景

### 如何实现 Prometheus 方案

如果要使用 Prometheus，需要：

1. **创建 Metrics 导出服务**：
   - 从 `position_metrics` 表读取最新数据
   - 导出为 Prometheus metrics
   - 暴露 HTTP 端点供 Prometheus 抓取

2. **配置 Prometheus**：
   - 添加抓取目标
   - 配置抓取间隔

3. **更新 Grafana Dashboard**：
   - 使用 PromQL 查询
   - 替换 SQL 查询为 PromQL

## 两种方案对比

| 特性 | PostgreSQL | Prometheus |
|------|-----------|------------|
| **数据存储** | 永久存储 | 默认保留 15 天（可配置） |
| **查询语言** | SQL | PromQL |
| **查询灵活性** | 非常灵活 | 适合时序查询 |
| **实时性** | 取决于计算频率（5分钟） | 实时（取决于抓取间隔） |
| **数据持久化** | ✅ 永久保存 | ⚠️ 需要配置长期存储 |
| **复杂度** | 简单（直接查询） | 需要额外服务 |
| **适用场景** | 历史数据分析、报表 | 实时监控、告警 |

## 推荐方案

### 当前推荐：PostgreSQL

**原因**：
1. 数据已经存储在 PostgreSQL 中
2. 实现简单，无需额外服务
3. 适合历史数据分析和报表需求
4. SQL 查询更灵活，适合复杂分析

### 如果使用 Prometheus

**适用场景**：
1. 需要与其他系统指标统一管理
2. 需要实时告警（Prometheus AlertManager）
3. 需要长期保留数据（需要配置 Thanos 或 VictoriaMetrics）

## 混合方案（推荐）

可以同时使用两种方案：

1. **PostgreSQL**：用于历史数据分析和报表
2. **Prometheus**：用于实时监控和告警

实现方式：
- 在 `PositionMetricsScheduler` 中，除了写入 PostgreSQL，同时更新 Prometheus metrics
- Grafana 中创建两个 dashboard：
  - 一个使用 PostgreSQL（历史分析）
  - 一个使用 Prometheus（实时监控）

