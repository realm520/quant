# Docker 启动指南

本文档说明如何使用 Docker 打包并运行 `cextools`，便于在不同服务器或平台快速部署。

---

## 1. 环境要求

- 已安装 Docker（Docker Desktop 或社区版均可）。
- （可选）如需推送镜像，准备好 Docker Hub 或其他镜像仓库账号。

---

## 2. 准备项目

确保代码目录中已经包含：

- `Dockerfile`
- `.dockerignore`
- 项目源码与依赖文件（例如 `pyproject.toml`、`uv.lock` 等）

推荐的 `.dockerignore` 示例：

```
.git
__pycache__/
*.pyc
*.pyo
*.pyd
*.log
.venv/
venv/
.env
dist/
build/
```

---

## 3. 构建镜像

在项目根目录执行：

```bash
docker build -t cextools:latest .
```
docker build --platform linux/amd64 -t docker.io/wzy2317/cextools:latest .
docker push docker.io/wzy2317/cextools:latest  推送

构建成功后，可用以下命令确认镜像存在：

```bash
docker images | grep cextools
```

---

## 4. 运行容器

### 4.1 基础测试

确认镜像内的 CLI 正常：

```bash
docker run --rm cextools:latest --help
```

### 4.2 实际命令示例

以 `watch-account` 为例（请根据实际情况替换环境变量）：

```bash
docker run --rm \
  -e DATABASE_URL="postgresql+asyncpg://postgres:password@db-host:5432/trading" \
  -e XT_API_KEY="your_xt_key" \
  -e XT_API_SECRET="your_xt_secret" \
  -e LARK_WEBHOOK_URL="https://open.feishu.cn/..." \
  -v /path/to/config:/app/config \
  cextools:latest \
  account watch-account -x xt --metrics-config /app/config/metric.yaml --enable-lark --interval 5
```
```bash
docker run --rm --network host \
  -e DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading" \
  -e XT_API_KEY="48e87084-4cb8-4134-958d-1ff294ee3796" \
  -e XT_API_SECRET="e98ebc0389dd9ca6d404a10cb472a306e3ce3229" \
  -e LARK_WEBHOOK_URL="https://open.larksuite.com/open-apis/bot/v2/hook/e4788562-3474-4386-b04e-6cf183f7e149" \
  -v /home/ubuntu/metric.yaml:/app/config/metric.yaml \
  docker.io/wzy2317/cextools:latest \
  account watch-account -x xt --metrics-config /app/config/metric.yaml --enable-lark --interval 5
```

#### 4.2.1 常用命令速查

- **基础监控（无 Lark 告警）**

  ```bash
  docker run --rm \
    -e DATABASE_URL="postgresql+asyncpg://postgres@45.125.23.194:5432/trading" \
    -e XT_API_KEY="48e87084-4cb8-4134-958d-1ff294ee3796" \
    -e XT_API_SECRET="e98ebc0389dd9ca6d404a10cb472a306e3ce3229" \
    docker.io/wzy2317/cextools:latest \
    account watch-account -x xt --interval 10
  ```

- **监控仓位并发送 Lark 告警**

  ```bash
  docker run --rm \
    -e DATABASE_URL="postgresql+asyncpg://postgres@45.125.23.194:5432/trading" \
    -e XT_API_KEY="48e87084-4cb8-4134-958d-1ff294ee3796" \
    -e XT_API_SECRET="e98ebc0389dd9ca6d404a10cb472a306e3ce3229" \
    -e LARK_WEBHOOK_URL="https://open.larksuite.com/open-apis/bot/v2/hook/e4788562-3474-4386-b04e-6cf183f7e149" \
    docker.io/wzy2317/cextools:latest \
    account watch-positions -x xt --interval 3 --enable-lark
  ```

- **一次性获取账户余额**

  ```bash
  docker run --rm \
    -e DATABASE_URL="postgresql+asyncpg://postgres@45.125.23.194:5432/trading" \
    -e XT_API_KEY="48e87084-4cb8-4134-958d-1ff294ee3796" \
    -e XT_API_SECRET="e98ebc0389dd9ca6d404a10cb472a306e3ce3229" \
    docker.io/wzy2317/cextools:latest \
    account balance -x xt -e perp
  ```

- **运行数据库迁移脚本**

  ```bash
  docker run --rm \
    -e DATABASE_URL="postgresql+asyncpg://postgres@45.125.23.194:5432/trading" \
    docker.io/wzy2317/cextools:latest \
    python scripts/migrate_recreate_xt_rest_tables.py
  ```

> **提示**
> - 如果容器运行在与数据库不同的主机上，请将 `DATABASE_URL` 中的 `localhost` 替换为数据库服务器的实际 IP（例如 `postgres@45.125.23.194:5432`），并确认 PostgreSQL 允许外部访问：
>   - 修改 `/etc/postgresql/16/main/postgresql.conf` 中的 `listen_addresses = '*'`。
>   - 在 `pg_hba.conf` 中添加允许访问的网段规则，例如 `host trading postgres 0.0.0.0/0 md5`。
>   - 防火墙/安全组开放 `5432` 端口。
> - 如果容器与数据库在同一台 Linux 主机上，可使用 `--network host`，命令中的 `localhost` 即可生效。

说明：

- `-e` 用于传递运行时需要的环境变量。
- `-v` 将主机上的配置文件目录挂载到容器内部（可选）。
- `--interval` 可根据需要调整，缺省为 10 分钟。
- 若需后台运行，加上 `-d` 并指定容器名称：

  ```bash
  docker run -d --name cextools-watch-account ...（其余参数）...
  ```

### 4.3 使用 Docker Compose（可选）

创建 `docker-compose.yaml`（示例）：

```yaml
services:
  watch-account:
    image: cextools:latest
    environment:
      DATABASE_URL: ${DATABASE_URL}
      XT_API_KEY: ${XT_API_KEY}
      XT_API_SECRET: ${XT_API_SECRET}
      LARK_WEBHOOK_URL: ${LARK_WEBHOOK_URL:-}
      LARK_WEBHOOK_SECRET: ${LARK_WEBHOOK_SECRET:-}
    volumes:
      - ./config:/app/config
    command: >
      account watch-account
      -x xt
      --metrics-config /app/config/metric.yaml
      --enable-lark
      --interval ${INTERVAL_MINUTES:-10}
```

然后执行：

```bash
docker compose up
```

受支持的环境变量可放在 `.env` 文件或直接在命令行指定。

---

## 5. 分发镜像

### 5.1 推送到镜像仓库

```bash
docker tag cextools:latest your-registry/cextools:latest
docker push your-registry/cextools:latest
```

其他用户可以直接 `docker pull` 该镜像使用。

### 5.2 导出镜像文件

如果无镜像仓库，可导出为 tar 包：

```bash
docker save -o cextools.tar cextools:latest
```

对方收到后导入：

```bash
docker load -i cextools.tar
```

---

## 6. 清理与维护

- 停止容器：`docker stop <container_name_or_id>`
- 删除容器：`docker rm <container_name_or_id>`
- 删除镜像：`docker rmi cextools:latest`（确认没有容器在使用）
- 更新镜像时重新执行 `docker build`，记得更新版本号或标签。

---

## 7. 常见问题

1. **拉取基础镜像失败**  
   检查网络、代理或配置镜像加速（例如 Docker Desktop 的 `registry-mirrors`）。

2. **容器内找不到 `cextools` 命令**  
   确保 Dockerfile 中设置了正确的 PATH，例如：
   ```
   ENV PATH="/app/.venv/bin:/root/.cache/uv/bin:${PATH}"
   ```

3. **数据库或配置差异**  
   使用环境变量和挂载目录让不同用户在运行时自行配置，而不是写死在镜像中。

---

通过以上步骤，即可使用 Docker 快速打包和部署 `cextools`，同时方便地在不同平台复用。欢迎结合自身需求进一步扩展（例如加入健康检查、日志卷、CI/CD 流水线等）。***

