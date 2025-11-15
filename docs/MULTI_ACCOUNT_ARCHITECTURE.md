# 多账号监控系统架构设计

本文档描述如何设计一个能够同时监控上万个账号的系统架构。

---

## 1. 核心挑战

- **并发连接数**: 上万个账号需要大量 WebSocket 连接和 REST API 请求
- **数据库性能**: 海量数据写入和查询
- **API 限流**: 交易所 API 有频率限制
- **资源消耗**: CPU、内存、网络带宽
- **故障隔离**: 单个账号故障不应影响其他账号
- **可扩展性**: 需要支持水平扩展

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     负载均衡层 (Nginx/HAProxy)                │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐   ┌────────▼────────┐   ┌─────▼──────┐
│ Worker Node 1│   │  Worker Node 2  │   │Worker Node N│
│              │   │                 │   │            │
│ ┌──────────┐ │   │ ┌────────────┐ │   │ ┌────────┐ │
│ │Account   │ │   │ │Account     │ │   │ │Account │ │
│ │Manager   │ │   │ │Manager     │ │   │ │Manager │ │
│ └──────────┘ │   │ └────────────┘ │   │ └────────┘ │
│              │   │                 │   │            │
│ ┌──────────┐ │   │ ┌────────────┐ │   │ ┌────────┐ │
│ │WebSocket │ │   │ │WebSocket   │ │   │ │WebSocket│ │
│ │Pool      │ │   │ │Pool        │ │   │ │Pool    │ │
│ └──────────┘ │   │ └────────────┘ │   │ └────────┘ │
└───────┬──────┘   └────────┬────────┘   └─────┬──────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐   ┌────────▼────────┐   ┌─────▼──────┐
│  PostgreSQL  │   │   Redis Cache   │   │  Message   │
│  (Sharded)   │   │   (Pub/Sub)     │   │  Queue     │
└──────────────┘   └─────────────────┘   └────────────┘
```

### 2.2 核心组件

#### 2.2.1 账号管理器 (Account Manager)

**职责**:
- 账号配置管理（API Key、Secret、监控配置）
- 账号状态管理（活跃、暂停、错误）
- 账号分配和负载均衡

**设计要点**:
```python
class AccountManager:
    def __init__(self):
        self.accounts = {}  # account_id -> AccountConfig
        self.worker_nodes = []  # 工作节点列表
        self.account_assignments = {}  # account_id -> worker_node_id
    
    def assign_account(self, account_id: str) -> str:
        """将账号分配给负载最低的工作节点"""
        # 负载均衡算法：轮询、最少连接、加权轮询
        pass
    
    def get_account_config(self, account_id: str) -> AccountConfig:
        """获取账号配置"""
        pass
```

#### 2.2.2 工作节点 (Worker Node)

**职责**:
- 管理分配给它的账号集合（例如每个节点 100-500 个账号）
- 维护 WebSocket 连接池
- 执行 REST API 轮询任务
- 处理数据写入和告警

**设计要点**:
```python
class WorkerNode:
    def __init__(self, node_id: str, max_accounts: int = 500):
        self.node_id = node_id
        self.max_accounts = max_accounts
        self.accounts = {}  # account_id -> AccountMonitor
        self.ws_pool = WebSocketConnectionPool(max_connections=100)
        self.rest_client_pool = RESTClientPool(max_clients=50)
        self.task_queue = asyncio.Queue()
    
    async def add_account(self, account_id: str, config: AccountConfig):
        """添加账号到本节点"""
        monitor = AccountMonitor(account_id, config, self)
        self.accounts[account_id] = monitor
        await monitor.start()
    
    async def remove_account(self, account_id: str):
        """从本节点移除账号"""
        if account_id in self.accounts:
            await self.accounts[account_id].stop()
            del self.accounts[account_id]
```

---

## 3. 数据库设计

### 3.1 分表策略

**按账号 ID 分表**:
```sql
-- 示例：xt_perp_balances_0000 到 xt_perp_balances_0099
-- 使用 account_id 的哈希值决定表名
CREATE TABLE xt_perp_balances_0000 (
    id BIGSERIAL PRIMARY KEY,
    account_id VARCHAR(50) NOT NULL,  -- 新增字段
    query_time TIMESTAMP NOT NULL,
    -- ... 其他字段
    INDEX idx_account_time (account_id, query_time)
);
```

**分表函数**:
```python
def get_table_suffix(account_id: str, total_shards: int = 100) -> str:
    """根据账号ID计算分表后缀"""
    hash_value = hash(account_id) % total_shards
    return f"{hash_value:04d}"

def get_table_name(base_name: str, account_id: str) -> str:
    """获取完整表名"""
    suffix = get_table_suffix(account_id)
    return f"{base_name}_{suffix}"
```

### 3.2 账号配置表

```sql
CREATE TABLE account_configs (
    account_id VARCHAR(50) PRIMARY KEY,
    exchange VARCHAR(20) NOT NULL,  -- xt, binance, etc.
    api_key VARCHAR(200) NOT NULL,
    api_secret_encrypted TEXT NOT NULL,  -- 加密存储
    enabled BOOLEAN DEFAULT TRUE,
    worker_node_id VARCHAR(50),  -- 当前分配的工作节点
    config_json JSONB,  -- 监控配置（指标阈值、告警设置等）
    last_heartbeat TIMESTAMP,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_account_enabled ON account_configs(enabled, worker_node_id);
CREATE INDEX idx_account_heartbeat ON account_configs(last_heartbeat);
```

### 3.3 时序数据优化

**使用 PostgreSQL 分区表**:
```sql
-- 按月分区
CREATE TABLE xt_perp_balances_0000 (
    -- 字段定义
) PARTITION BY RANGE (query_time);

CREATE TABLE xt_perp_balances_0000_2025_11 
PARTITION OF xt_perp_balances_0000
FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
```

**或使用 TimescaleDB**（时序数据库扩展）:
```sql
-- 转换为超表
SELECT create_hypertable('xt_perp_balances_0000', 'query_time');
```

---

## 4. 并发和连接管理

### 4.1 WebSocket 连接池

```python
class WebSocketConnectionPool:
    def __init__(self, max_connections: int = 100):
        self.max_connections = max_connections
        self.connections: dict[str, WebSocketConnection] = {}
        self.connection_queue = asyncio.Queue()
    
    async def get_connection(self, account_id: str) -> WebSocketConnection:
        """获取或创建 WebSocket 连接"""
        if account_id in self.connections:
            return self.connections[account_id]
        
        if len(self.connections) >= self.max_connections:
            # 连接池满，等待或复用
            await self._wait_for_slot()
        
        conn = await self._create_connection(account_id)
        self.connections[account_id] = conn
        return conn
    
    async def _wait_for_slot(self):
        """等待连接池有空位"""
        # 可以关闭最久未使用的连接
        pass
```

### 4.2 REST API 限流管理

```python
class RateLimiter:
    def __init__(self, max_requests_per_second: int = 10):
        self.max_rps = max_requests_per_second
        self.tokens = asyncio.Semaphore(max_requests_per_second)
        self.refill_task = None
    
    async def acquire(self):
        """获取请求令牌"""
        await self.tokens.acquire()
    
    async def _refill_tokens(self):
        """定期补充令牌"""
        while True:
            await asyncio.sleep(1)
            # 补充令牌到 max_rps
            for _ in range(self.max_rps):
                try:
                    self.tokens.release()
                except:
                    break

# 全局限流器（按交易所）
rate_limiters = {
    'xt': RateLimiter(max_requests_per_second=20),
    'binance': RateLimiter(max_requests_per_second=10),
}
```

### 4.3 任务调度

```python
class TaskScheduler:
    def __init__(self, worker_node: WorkerNode):
        self.worker_node = worker_node
        self.task_intervals = {
            'balance': 600,  # 10分钟
            'position': 300,  # 5分钟
            'metrics': 60,   # 1分钟
        }
        self.running_tasks = {}
    
    async def schedule_account_tasks(self, account_id: str):
        """为账号调度所有任务"""
        for task_type, interval in self.task_intervals.items():
            task = asyncio.create_task(
                self._periodic_task(account_id, task_type, interval)
            )
            self.running_tasks[f"{account_id}:{task_type}"] = task
    
    async def _periodic_task(self, account_id: str, task_type: str, interval: int):
        """周期性执行任务"""
        while True:
            try:
                await self._execute_task(account_id, task_type)
            except Exception as e:
                logger.error(f"Task failed: {account_id}:{task_type}", exc_info=e)
                # 错误处理：重试、告警、暂停账号
            await asyncio.sleep(interval)
```

---

## 5. 消息队列和异步处理

### 5.1 使用 Redis Pub/Sub 或 RabbitMQ

**账号状态变更通知**:
```python
# 发布者（控制节点）
async def notify_account_update(account_id: str, action: str):
    await redis.publish('account_updates', json.dumps({
        'account_id': account_id,
        'action': action,  # add, remove, update
        'timestamp': time.time()
    }))

# 订阅者（工作节点）
async def listen_account_updates():
    pubsub = redis.pubsub()
    await pubsub.subscribe('account_updates')
    async for message in pubsub.listen():
        data = json.loads(message['data'])
        if data['action'] == 'add':
            await worker_node.add_account(data['account_id'])
```

### 5.2 告警队列

```python
# 告警消息队列（避免阻塞主流程）
class AlertQueue:
    def __init__(self):
        self.queue = asyncio.Queue(maxsize=10000)
        self.workers = []
    
    async def put_alert(self, account_id: str, alert_data: dict):
        """添加告警到队列"""
        await self.queue.put({
            'account_id': account_id,
            'alert_data': alert_data,
            'timestamp': time.time()
        })
    
    async def process_alerts(self):
        """处理告警（多个 worker 并发）"""
        while True:
            alert = await self.queue.get()
            try:
                await self._send_alert(alert)
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")
            finally:
                self.queue.task_done()
```

---

## 6. 配置管理

### 6.1 账号配置存储

**使用数据库 + 缓存**:
```python
class AccountConfigManager:
    def __init__(self):
        self.cache = {}  # 内存缓存
        self.cache_ttl = 300  # 5分钟
    
    async def get_config(self, account_id: str) -> AccountConfig:
        """获取账号配置（带缓存）"""
        if account_id in self.cache:
            config, cached_time = self.cache[account_id]
            if time.time() - cached_time < self.cache_ttl:
                return config
        
        # 从数据库加载
        config = await db.get_account_config(account_id)
        self.cache[account_id] = (config, time.time())
        return config
```

### 6.2 监控指标配置

```yaml
# 每个账号可以有独立的指标配置
accounts:
  account_001:
    metrics:
      perp_balance_volatility:
        warning_threshold: 0.05
        critical_threshold: 0.10
      perp_risk_ratio:
        warning_threshold: 0.50
        critical_threshold: 0.80
    lark_webhook: "https://..."
  account_002:
    # 不同的配置
```

---

## 7. 扩展性设计

### 7.1 水平扩展

**添加新工作节点**:
1. 启动新的 Worker Node
2. 向负载均衡器注册
3. 从控制节点接收账号分配
4. 自动开始监控分配的账号

**动态重新分配**:
```python
async def rebalance_accounts():
    """重新平衡账号分配"""
    all_accounts = await db.get_all_enabled_accounts()
    active_nodes = await get_active_worker_nodes()
    
    # 计算每个节点应该管理的账号数
    accounts_per_node = len(all_accounts) // len(active_nodes)
    
    # 重新分配
    for i, account in enumerate(all_accounts):
        node_id = active_nodes[i % len(active_nodes)]
        await assign_account_to_node(account.id, node_id)
```

### 7.2 垂直扩展

- **增加连接池大小**: 每个节点管理更多账号
- **优化数据库**: 使用更强大的数据库服务器
- **增加缓存**: 使用 Redis 集群

---

## 8. 监控和告警

### 8.1 系统监控

```python
class SystemMonitor:
    async def collect_metrics(self):
        """收集系统指标"""
        return {
            'total_accounts': len(self.accounts),
            'active_connections': len(self.ws_pool.connections),
            'queue_size': self.task_queue.qsize(),
            'error_rate': self.error_count / self.total_requests,
            'cpu_usage': psutil.cpu_percent(),
            'memory_usage': psutil.virtual_memory().percent,
        }
```

### 8.2 账号健康检查

```python
async def health_check_account(account_id: str):
    """检查账号健康状态"""
    try:
        # 测试 API 连接
        await test_api_connection(account_id)
        # 检查数据更新是否及时
        last_update = await get_last_update_time(account_id)
        if time.time() - last_update > 300:  # 5分钟无更新
            await mark_account_unhealthy(account_id)
    except Exception as e:
        await mark_account_error(account_id, str(e))
```

---

## 9. 故障处理

### 9.1 故障隔离

```python
class AccountMonitor:
    async def start(self):
        """启动监控（带故障隔离）"""
        try:
            await self._connect()
            await self._start_tasks()
        except Exception as e:
            # 记录错误，但不影响其他账号
            await self._handle_error(e)
            # 可以暂停该账号，等待人工处理
            await self.pause()
    
    async def _handle_error(self, error: Exception):
        """处理错误"""
        self.error_count += 1
        if self.error_count > 5:
            # 错误过多，暂停账号
            await self.pause()
            await notify_admin(self.account_id, error)
```

### 9.2 自动恢复

```python
async def auto_recover_account(account_id: str):
    """自动恢复账号"""
    # 等待一段时间后重试
    await asyncio.sleep(60)
    try:
        await restart_account_monitor(account_id)
    except Exception as e:
        # 重试失败，标记为需要人工处理
        await mark_for_manual_review(account_id)
```

---

## 10. 性能优化建议

### 10.1 数据库优化

1. **批量写入**: 使用 `COPY` 或批量 `INSERT`
2. **连接池**: 使用连接池管理数据库连接
3. **读写分离**: 查询使用只读副本
4. **索引优化**: 根据查询模式创建合适的索引

### 10.2 缓存策略

```python
# 使用 Redis 缓存账号配置、最近余额等
cache_keys = {
    'account_config': f"account:{account_id}:config",
    'last_balance': f"account:{account_id}:balance",
    'metrics': f"account:{account_id}:metrics",
}
```

### 10.3 异步处理

- 所有 I/O 操作使用异步（`async/await`）
- 使用 `asyncio.gather()` 并发执行多个任务
- 避免阻塞操作

---

## 11. 部署建议

### 11.1 Docker Compose 示例

```yaml
version: '3.8'
services:
  worker-1:
    image: cextools:latest
    environment:
      - WORKER_NODE_ID=worker-1
      - MAX_ACCOUNTS=500
      - DATABASE_URL=...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
  
  worker-2:
    image: cextools:latest
    environment:
      - WORKER_NODE_ID=worker-2
      - MAX_ACCOUNTS=500
    # ...
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  postgres:
    image: postgres:16
    environment:
      - POSTGRES_DB=trading
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

### 11.2 Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cextools-worker
spec:
  replicas: 10  # 10个工作节点
  template:
    spec:
      containers:
      - name: worker
        image: cextools:latest
        env:
        - name: WORKER_NODE_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
```

---

## 12. 容量规划

### 12.1 资源估算

假设每个账号：
- WebSocket 连接: 1 个
- REST API 请求: 每 10 分钟 3 次（余额、仓位、指标）
- 数据写入: 每 10 分钟约 5 条记录
- 内存占用: 约 10MB

**1 万个账号**:
- WebSocket 连接: 10,000 个（需要连接池管理）
- REST API QPS: 约 50 次/秒（10,000 * 3 / 600）
- 数据写入: 约 5,000 条/10分钟
- 内存: 约 100GB（需要分布式）

### 12.2 节点数量建议

- **每个节点管理**: 200-500 个账号
- **1 万个账号需要**: 20-50 个工作节点
- **数据库**: 使用分库分表，可能需要多个数据库实例

---

## 13. 实施步骤

1. **Phase 1**: 单节点支持多账号（100-500 个）
2. **Phase 2**: 添加账号配置管理和数据库分表
3. **Phase 3**: 实现工作节点集群和负载均衡
4. **Phase 4**: 优化性能和扩展性
5. **Phase 5**: 添加监控、告警和自动恢复

---

## 14. 总结

设计要点：
- ✅ **分表分库**: 按账号 ID 分表，支持水平扩展
- ✅ **工作节点集群**: 分布式处理，负载均衡
- ✅ **连接池管理**: 复用 WebSocket 和 REST 连接
- ✅ **异步处理**: 所有 I/O 操作异步化
- ✅ **故障隔离**: 单个账号故障不影响其他账号
- ✅ **消息队列**: 解耦组件，提高可靠性
- ✅ **缓存策略**: 减少数据库压力
- ✅ **监控告警**: 及时发现和处理问题

通过以上设计，可以支持同时监控上万个账号，并具备良好的扩展性和可靠性。

