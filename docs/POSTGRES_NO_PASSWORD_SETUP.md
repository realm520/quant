# PostgreSQL 无密码连接配置指南

## 🎯 目标

配置本地PostgreSQL使用trust认证，允许无密码连接（仅用于开发环境）。

## ⚡ 一键配置（推荐）

```bash
cd /home/w_zy/crypto/xt/quant
bash scripts/configure_postgres_trust.sh
```

脚本会自动：
1. ✅ 备份原始pg_hba.conf
2. ✅ 配置trust认证
3. ✅ 重新加载PostgreSQL
4. ✅ 创建trading数据库
5. ✅ 测试无密码连接

## 📋 手动配置步骤

如果自动脚本失败，可以手动配置：

### 步骤1：找到pg_hba.conf

```bash
# 查询配置文件位置
sudo -u postgres psql -c "SHOW hba_file;"

# 常见位置
# Ubuntu: /etc/postgresql/14/main/pg_hba.conf
# 其他: /var/lib/postgresql/data/pg_hba.conf
```

### 步骤2：备份原始配置

```bash
sudo cp /etc/postgresql/14/main/pg_hba.conf /etc/postgresql/14/main/pg_hba.conf.backup
```

### 步骤3：编辑pg_hba.conf

```bash
sudo nano /etc/postgresql/14/main/pg_hba.conf
```

修改为以下内容（或将所有`md5`/`peer`改为`trust`）：

```conf
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# "local" is for Unix domain socket connections only
local   all             all                                     trust

# IPv4 local connections:
host    all             all             127.0.0.1/32            trust
host    all             all             localhost               trust

# IPv6 local connections:
host    all             all             ::1/128                 trust
```

### 步骤4：重新加载PostgreSQL

```bash
sudo systemctl reload postgresql

# 或
sudo -u postgres pg_ctl reload
```

### 步骤5：创建数据库

```bash
# 方法1：使用createdb
createdb -U postgres trading

# 方法2：使用SQL
psql -U postgres -c "CREATE DATABASE trading;"
```

### 步骤6：测试连接

```bash
# 无密码连接
psql -U postgres -h localhost -d trading

# 应该能直接连接，不需要密码
```

## 🚀 使用WebSocket订阅

配置完成后：

```bash
cd /home/w_zy/crypto/xt/quant
source .venv/bin/activate

# 设置数据库URL（无密码）
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"

# 设置Binance API凭证
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"

# 启动订阅（首次运行）
cextools subscribe binance-user-stream --create-tables

# 后续运行
cextools subscribe binance-user-stream
```

## 🔍 验证配置

### 测试1：命令行连接

```bash
# 应该不需要密码直接连接
psql -U postgres -h localhost -d trading

# 在psql中
\dt  # 查看表
SELECT version();  # 查看版本
\q   # 退出
```

### 测试2：Python连接

```python
import asyncio
from tri_arb.storage.database import DatabaseManager

async def test():
    db = DatabaseManager()  # 使用默认无密码URL
    await db.create_tables()
    print("✅ 连接成功！")
    await db.close()

asyncio.run(test())
```

### 测试3：psycopg2连接

```python
import psycopg2

# 无密码连接
conn = psycopg2.connect(
    dbname="trading",
    user="postgres",
    host="localhost",
    port=5432
    # 注意：没有password参数
)
print("✅ 连接成功！")
conn.close()
```

## 📊 DATABASE_URL 格式

### 有密码（原来的格式）

```bash
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/trading"
#                                             ^^^^^^^^^ 密码
```

### 无密码（新格式）

```bash
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
#                                         ^^^^^^ 没有:password部分
```

## 🔄 切换回密码认证

如果需要恢复密码认证：

```bash
# 1. 恢复备份
sudo cp /etc/postgresql/14/main/pg_hba.conf.backup /etc/postgresql/14/main/pg_hba.conf

# 2. 重新加载
sudo systemctl reload postgresql

# 3. 设置密码
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'your_password';"

# 4. 更新DATABASE_URL
export DATABASE_URL="postgresql+asyncpg://postgres:your_password@localhost:5432/trading"
```

## ⚠️ 安全提示

### trust认证的影响

- ✅ **优点**：开发方便，不需要记密码
- ❌ **缺点**：任何本地用户都可以无密码访问数据库

### 使用场景

- ✅ **开发环境**：本地开发机器
- ✅ **测试环境**：隔离的测试服务器
- ❌ **生产环境**：绝对不要在生产环境使用trust认证

### 最佳实践

1. **开发环境**：使用trust认证（方便）
2. **测试环境**：使用密码认证（安全）
3. **生产环境**：使用密码认证 + SSL + IP限制（最安全）

## 🛠️ 故障排查

### 问题1：配置后仍需要密码

**原因**：配置未生效

**解决**：
```bash
# 确认pg_hba.conf已修改
sudo cat /etc/postgresql/14/main/pg_hba.conf | grep trust

# 强制重启PostgreSQL
sudo systemctl restart postgresql

# 等待几秒后测试
psql -U postgres -h localhost -d trading
```

### 问题2：找不到pg_hba.conf

**解决**：
```bash
# 方法1：查询PostgreSQL
sudo -u postgres psql -c "SHOW hba_file;"

# 方法2：查找文件
sudo find / -name pg_hba.conf 2>/dev/null

# 方法3：检查常见位置
ls -la /etc/postgresql/*/main/pg_hba.conf
ls -la /var/lib/postgresql/data/pg_hba.conf
```

### 问题3：权限被拒绝

**错误**：`permission denied for database`

**解决**：
```bash
# 赋予权限
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE trading TO postgres;"
```

### 问题4：数据库不存在

**错误**：`database "trading" does not exist`

**解决**：
```bash
# 创建数据库
psql -U postgres -c "CREATE DATABASE trading;"

# 或使用createdb
createdb -U postgres trading
```

## 📝 配置文件示例

### 完整的pg_hba.conf（trust认证）

```conf
# PostgreSQL Client Authentication Configuration File
# ===================================================
#
# This file controls: which hosts are allowed to connect, how clients
# are authenticated, which PostgreSQL user names they can use, which
# databases they can access.
#
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# "local" is for Unix domain socket connections only
local   all             all                                     trust

# IPv4 local connections:
host    all             all             127.0.0.1/32            trust
host    all             all             localhost               trust

# IPv6 local connections:
host    all             all             ::1/128                 trust

# Allow replication connections from localhost
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust
```

### 混合认证（本地trust，远程密码）

如果需要本地无密码，远程需要密码：

```conf
# 本地连接 - 无密码
local   all             all                                     trust
host    all             all             127.0.0.1/32            trust
host    all             all             ::1/128                 trust

# 远程连接 - 需要密码
host    all             all             0.0.0.0/0               md5
```

## 🎉 快速开始流程

```bash
# 1. 配置PostgreSQL
cd /home/w_zy/crypto/xt/quant
bash scripts/configure_postgres_trust.sh

# 2. 启动WebSocket订阅
source .venv/bin/activate
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
cextools subscribe binance-user-stream --create-tables

# 3. 查询数据（另一个终端）
psql -U postgres -d trading -c "SELECT * FROM order_updates ORDER BY event_time DESC LIMIT 5;"
```

---

**配置完成！** 现在您可以无密码连接PostgreSQL了。🎊

