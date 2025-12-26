# CEX Tools 部署指南（Amazon Linux）

本指南帮助你在 Amazon Linux 2 或 Amazon Linux 2023 上部署并运行 cextools 与 tri-arb。

## 1. 系统要求

- **Amazon Linux 2** 或 **Amazon Linux 2023**
- **Python 3.11+**（推荐使用 uv 或 venv）
- **PostgreSQL 14+**
- **Git**
- **Docker**（可选，用于 Prometheus/Grafana）

## 2. 更新系统

```bash
# Amazon Linux 2
sudo yum update -y

# Amazon Linux 2023
sudo dnf update -y
```

## 3. 安装基础依赖

### Amazon Linux 2023

```bash
# 安装开发工具和编译依赖
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y gcc gcc-c++ make openssl-devel libffi-devel zlib-devel readline-devel

# 安装 PostgreSQL 14+
sudo dnf install -y postgresql15 postgresql15-server postgresql15-devel

# 安装 Git
sudo dnf install -y git

# 安装 Python 3.11（如果系统默认不是 3.11）
sudo dnf install -y python3.11 python3.11-devel python3.11-pip
```

### Amazon Linux 2

```bash
# 安装开发工具和编译依赖
sudo yum groupinstall -y "Development Tools"
sudo yum install -y gcc gcc-c++ make openssl-devel libffi-devel zlib-devel readline-devel

# 启用 Amazon Linux Extras 获取 PostgreSQL
sudo amazon-linux-extras enable postgresql14

# 安装 PostgreSQL 14
sudo yum install -y postgresql postgresql-server postgresql-devel

# 安装 Git
sudo yum install -y git

# 安装 Python 3.11（Amazon Linux 2 可能需要从源码编译或使用 Amazon Linux Extras）
# 检查可用版本
amazon-linux-extras list | grep python

# 如果可用，启用并安装
sudo amazon-linux-extras enable python3.11
sudo yum install -y python3.11 python3.11-devel python3.11-pip

# 如果没有 Python 3.11，可以从源码编译或使用 pyenv
```

### 安装 Python 3.11（如果系统默认版本不够）

如果系统没有 Python 3.11，可以编译安装：

```bash
# 下载 Python 3.11 源码
cd /tmp
wget https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tgz
tar -xzf Python-3.11.9.tgz
cd Python-3.11.9

# 编译安装
./configure --enable-optimizations --with-ssl
make -j$(nproc)
sudo make altinstall

# 验证安装
python3.11 --version
```

或者使用 pyenv（推荐）：

```bash
# 安装 pyenv 依赖
sudo dnf install -y make gcc openssl-devel bzip2-devel libffi-devel zlib-devel readline-devel sqlite-devel xz-devel

# 安装 pyenv
curl https://pyenv.run | bash

# 添加到 PATH
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
source ~/.bashrc

# 安装 Python 3.11
pyenv install 3.11.9
pyenv global 3.11.9
```

## 4. 安装 uv（推荐）

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l

# 验证安装
uv --version
```

## 5. 配置 PostgreSQL

### 初始化数据库（首次安装）

```bash
# Amazon Linux 2023
sudo postgresql-setup --initdb
# 或
sudo /usr/pgsql-15/bin/postgresql-15-setup initdb

# Amazon Linux 2
sudo postgresql-setup initdb
```

### 启动 PostgreSQL

```bash
# Amazon Linux 2023
sudo systemctl enable postgresql-15
sudo systemctl start postgresql-15

# Amazon Linux 2
sudo systemctl enable postgresql
sudo systemctl start postgresql
```

### 创建数据库和用户

```bash
# 切换到 postgres 用户
sudo -u postgres psql

# 在 PostgreSQL 命令行中执行：
CREATE DATABASE trading;
CREATE USER your_username WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE trading TO your_username;
ALTER USER your_username CREATEDB;
\q
```

### 配置 PostgreSQL 允许本地连接（如需要）

```bash
# 编辑 pg_hba.conf
sudo vi /var/lib/pgsql/data/pg_hba.conf

# 确保有以下行（允许本地密码认证）：
# local   all             all                                     peer
# host    all             all             127.0.0.1/32            md5
# host    all             all             ::1/128                 md5

# 重启 PostgreSQL
sudo systemctl restart postgresql  # Amazon Linux 2
sudo systemctl restart postgresql-15  # Amazon Linux 2023
```

## 6. 获取代码和创建虚拟环境

```bash
# 克隆仓库
cd /home/ec2-user  # 或你喜欢的目录
git clone https://github.com/realm520/quant.git
cd quant

# 使用 uv（推荐）
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .
uv pip install -r requirements-db.txt

# 或使用 venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
pip install -r requirements-db.txt
```

## 7. 配置环境变量

创建 `.env` 文件或在 shell 中导出：

```bash
# 创建 .env 文件
cat > .env << 'EOF'
# XT 交易所（现货和永续共用）
XT_API_KEY=your_api_key
XT_API_SECRET=your_api_secret

# OKX 交易所
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_PASSPHRASE=your_okx_passphrase

# Binance 交易所（可选）
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret

# 数据库配置（根据实际配置调整）
DATABASE_URL=postgresql+asyncpg://your_username:your_password@localhost:5432/trading

# Prometheus metrics 端口
PROM_METRICS_PORT=9600
EOF

# 加载环境变量
source .env

# 或手动导出
export XT_API_KEY="your_api_key"
export XT_API_SECRET="your_api_secret"
export DATABASE_URL="postgresql+asyncpg://your_username:your_password@localhost:5432/trading"
export PROM_METRICS_PORT=9600
```

## 8. 创建数据库表

首次运行命令时会自动创建表结构，无需手动初始化。

验证数据库连接：

```bash
psql $DATABASE_URL -c "SELECT version();"
```

## 9. 安装 Docker 和 Docker Compose（用于监控）

```bash
# Amazon Linux 2023
sudo dnf install -y docker docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ec2-user

# Amazon Linux 2
sudo yum install -y docker docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ec2-user

# 重新登录以使 docker 组生效，或运行：
newgrp docker

# 验证 Docker
docker --version
docker compose version
```

## 10. 启动监控服务（Prometheus + Grafana）

```bash
cd /home/ec2-user/quant  # 调整到你的项目目录

# 启动 Prometheus 和 Grafana
docker compose -f docker-compose.monitoring.yml up -d

# 验证服务
docker ps
curl http://localhost:9090/api/v1/status/config  # Prometheus
curl http://localhost:3000/api/health  # Grafana
```

## 11. 启动监控命令

### 方式 1: 单账号监控

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动余额监控（暴露 metrics）
cextools account watch-balance \
  -x xt \
  -e perp \
  --config config/accounts.json \
  --account-id account_002 \
  --port 9600

# 启动账户监控
cextools account watch-account \
  --config config/accounts.json \
  --account-id account_002 \
  --port 9601

# 启动持仓监控
cextools account watch-positions \
  -x xt \
  --config config/accounts.json \
  --account-id account_002 \
  --interval 5
```

### 方式 2: 多账号统一监控（推荐）

```bash
# 启动所有监控任务
cextools account watch-all \
  --config config/accounts.json
```

## 12. 配置为系统服务（可选）

创建 systemd 服务文件：

```bash
sudo nano /etc/systemd/system/cextools-watch-all.service
```

添加以下内容（根据实际情况调整路径和用户）：

```ini
[Unit]
Description=CEX Tools Watch All Services
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/quant
Environment="PATH=/home/ec2-user/quant/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/home/ec2-user/quant/.env
ExecStart=/home/ec2-user/quant/.venv/bin/cextools account watch-all --config /home/ec2-user/quant/config/accounts.json
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

启用并启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable cextools-watch-all
sudo systemctl start cextools-watch-all

# 查看状态
sudo systemctl status cextools-watch-all

# 查看日志
sudo journalctl -u cextools-watch-all -f
```

## 13. 配置防火墙（Amazon Linux 使用 firewalld）

```bash
# 安装 firewalld（如果未安装）
sudo dnf install -y firewalld  # Amazon Linux 2023
sudo yum install -y firewalld  # Amazon Linux 2

# 启动 firewalld
sudo systemctl enable firewalld
sudo systemctl start firewalld

# 开放必要端口
sudo firewall-cmd --permanent --add-port=3000/tcp  # Grafana
sudo firewall-cmd --permanent --add-port=9090/tcp  # Prometheus
sudo firewall-cmd --permanent --add-port=9600/tcp  # Metrics endpoint
sudo firewall-cmd --permanent --add-port=9601/tcp  # Metrics endpoint
sudo firewall-cmd --reload

# 查看规则
sudo firewall-cmd --list-all
```

**注意**：如果是 AWS EC2，还需要在 AWS 控制台配置安全组规则！

## 14. 配置 AWS 安全组（重要！）

1. 登录 AWS 控制台
2. 进入 **EC2** > **Instances**
3. 选择你的实例
4. 点击 **Security** 标签 > **Security groups** > 点击安全组 ID
5. 点击 **Inbound rules** > **Edit inbound rules**
6. 添加规则：
   - **Type**: Custom TCP
   - **Port**: 3000 (Grafana)
   - **Source**: 0.0.0.0/0（或特定 IP）
   - **Description**: Grafana access
7. 同样添加：
   - 端口 9090 (Prometheus，如果需要外部访问)
   - 端口 9600, 9601 (Metrics endpoints，通常只需要内网访问)
8. 点击 **Save rules**

## 15. 验证部署

### 验证 Prometheus

```bash
# 检查 Prometheus targets
curl http://localhost:9090/api/v1/targets | python3 -m json.tool

# 测试查询
curl "http://localhost:9090/api/v1/query?query=exchange_balance_total"
```

### 验证 Grafana

```bash
# 访问 Grafana
curl http://localhost:3000/api/health

# 浏览器访问
# http://your-ec2-public-ip:3000
# 用户名: admin
# 密码: admin
```

### 验证 Metrics 端点

```bash
# 检查 metrics 是否暴露
curl http://localhost:9600/metrics | grep exchange_balance_total
```

## 16. 常见问题

### Python 版本问题

```bash
# 检查 Python 版本
python3.11 --version

# 如果命令不存在，使用完整路径
/usr/local/bin/python3.11 --version
```

### PostgreSQL 连接问题

```bash
# 测试连接
psql $DATABASE_URL -c "SELECT 1;"

# 如果连接失败，检查：
# 1. PostgreSQL 是否运行
sudo systemctl status postgresql

# 2. 数据库是否存在
sudo -u postgres psql -c "\l" | grep trading

# 3. 用户权限
sudo -u postgres psql -c "\du"
```

### 端口被占用

```bash
# 检查端口占用
sudo lsof -i :3000
sudo lsof -i :9090
sudo lsof -i :9600

# 如果被占用，停止相应服务或更改端口
```

### 权限问题

```bash
# 确保用户有项目目录权限
sudo chown -R ec2-user:ec2-user /home/ec2-user/quant

# 确保虚拟环境可执行
chmod +x .venv/bin/*
```

### DNS/网络问题

```bash
# 如果无法下载包，检查网络
ping 8.8.8.8

# 如果使用代理
export http_proxy=http://proxy.example.com:8080
export https_proxy=http://proxy.example.com:8080
```

## 17. 性能优化

### 设置时区

```bash
# 设置时区为 UTC
sudo timedatectl set-timezone UTC
```

### 优化 PostgreSQL

```bash
# 编辑 PostgreSQL 配置
sudo vi /var/lib/pgsql/data/postgresql.conf

# 建议设置：
# shared_buffers = 256MB
# effective_cache_size = 1GB
# maintenance_work_mem = 128MB
# checkpoint_completion_target = 0.9
# wal_buffers = 16MB
# default_statistics_target = 100
# random_page_cost = 1.1
# effective_io_concurrency = 200
# work_mem = 16MB
# min_wal_size = 1GB
# max_wal_size = 4GB

# 重启 PostgreSQL
sudo systemctl restart postgresql  # 或 postgresql-15
```

## 18. 安全建议

1. **更改默认密码**
   - Grafana 默认密码：admin/admin
   - PostgreSQL 用户密码

2. **使用 IAM 角色**
   - 避免在 EC2 上存储 AWS 凭证
   - 使用 IAM 角色访问 AWS 服务

3. **限制访问**
   - 安全组只允许必要的 IP
   - 使用 VPN 或堡垒机访问

4. **定期更新**
   - 保持系统和依赖包最新
   - `sudo dnf update -y`（Amazon Linux 2023）
   - `sudo yum update -y`（Amazon Linux 2）

## 19. 备份和恢复

### 备份数据库

```bash
# 创建备份
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# 或使用压缩
pg_dump $DATABASE_URL | gzip > backup_$(date +%Y%m%d).sql.gz
```

### 恢复数据库

```bash
# 从备份恢复
psql $DATABASE_URL < backup_20241124.sql

# 或从压缩文件恢复
gunzip < backup_20241124.sql.gz | psql $DATABASE_URL
```

## 20. 监控和维护

### 查看服务日志

```bash
# systemd 服务日志
sudo journalctl -u cextools-watch-all -f

# Docker 容器日志
docker logs grafana -f
docker logs prometheus -f

# 应用日志
tail -f /home/ec2-user/quant/logs/tri-arb.log
```

### 磁盘空间监控

```bash
# 查看磁盘使用
df -h

# 查看 PostgreSQL 数据目录大小
du -sh /var/lib/pgsql/data

# 清理 Docker 未使用的资源
docker system prune -a
```

## 快速验证清单

- [ ] PostgreSQL 运行正常
- [ ] 数据库 `trading` 已创建
- [ ] Python 3.11+ 已安装
- [ ] 虚拟环境已创建并激活
- [ ] 依赖已安装
- [ ] 环境变量已配置
- [ ] Docker 已安装（如使用监控）
- [ ] Prometheus 和 Grafana 已启动（如使用监控）
- [ ] 防火墙/安全组已配置
- [ ] Metrics 端点可访问
- [ ] Grafana 可访问
- [ ] 监控命令正常运行

## 下一步

部署完成后，参考以下文档：
- [账户监控使用指南](MULTI_ACCOUNT_USAGE.md)
- [Metrics 和可视化指南](METRICS_AND_VISUALIZATION.md)
- [命令快速参考](COMMANDS_QUICK_REFERENCE.md)

