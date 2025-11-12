# 第一阶段：安装依赖
FROM python:3.11-slim AS builder

WORKDIR /app

RUN set -eux; \
    codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"; \
    rm -f /etc/apt/sources.list.d/*; \
    printf '%s\n' \
        "deb http://mirrors.aliyun.com/debian ${codename} main contrib non-free non-free-firmware" \
        "deb http://mirrors.aliyun.com/debian ${codename}-updates main contrib non-free non-free-firmware" \
        "deb http://mirrors.aliyun.com/debian ${codename}-backports main contrib non-free non-free-firmware" \
        "deb http://mirrors.aliyun.com/debian-security ${codename}-security main contrib non-free non-free-firmware" \
        > /etc/apt/sources.list; \
    apt-get update -o Acquire::Retries=3 && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml poetry.lock* uv.lock* ./
COPY src ./src
COPY config ./config
COPY README.md .

RUN uv sync --python 3.11

# 第二阶段：运行镜像
FROM python:3.11-slim

WORKDIR /app

RUN set -eux; \
    codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"; \
    rm -f /etc/apt/sources.list.d/*; \
    printf '%s\n' \
        "deb http://mirrors.aliyun.com/debian ${codename} main contrib non-free non-free-firmware" \
        "deb http://mirrors.aliyun.com/debian ${codename}-updates main contrib non-free non-free-firmware" \
        "deb http://mirrors.aliyun.com/debian ${codename}-backports main contrib non-free non-free-firmware" \
        "deb http://mirrors.aliyun.com/debian-security ${codename}-security main contrib non-free non-free-firmware" \
        > /etc/apt/sources.list; \
    apt-get update -o Acquire::Retries=3 && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.cache/uv /root/.cache/uv
COPY --from=builder /app /app

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:/root/.cache/uv/bin:${PATH}"

ENTRYPOINT ["cextools"]
CMD ["--help"]