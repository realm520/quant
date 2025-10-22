#!/bin/bash

# PostgreSQL Docker快速启动脚本

set -e

echo "================================================"
echo "  PostgreSQL Docker 快速启动"
echo "================================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 错误: Docker未安装"
    echo "请先安装Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# 容器名称
CONTAINER_NAME="postgres-trading"

# 检查容器是否已存在
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "检测到已存在的容器..."
    
    # 检查容器是否在运行
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo -e "${GREEN}✅ PostgreSQL容器已在运行${NC}"
        echo ""
        echo "连接信息:"
        echo "  Host: localhost"
        echo "  Port: 5432"
        echo "  Database: trading"
        echo "  User: postgres"
        echo "  Password: postgres"
        echo ""
        echo "DATABASE_URL:"
        echo "  postgresql+asyncpg://postgres:postgres@localhost:5432/trading"
        echo ""
        echo "如需重启容器，运行:"
        echo "  docker restart ${CONTAINER_NAME}"
        exit 0
    else
        echo "容器存在但未运行，正在启动..."
        docker start ${CONTAINER_NAME}
        echo -e "${GREEN}✅ 容器已启动${NC}"
    fi
else
    echo "创建新的PostgreSQL容器..."
    docker run --name ${CONTAINER_NAME} \
        -e POSTGRES_PASSWORD=postgres \
        -e POSTGRES_DB=trading \
        -e POSTGRES_USER=postgres \
        -p 5432:5432 \
        -d postgres:16
    
    echo -e "${GREEN}✅ 容器创建成功${NC}"
    echo "等待PostgreSQL启动..."
    sleep 5
fi

# 验证连接
echo ""
echo "验证数据库连接..."
if docker exec ${CONTAINER_NAME} psql -U postgres -d trading -c "SELECT version();" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 数据库连接成功${NC}"
else
    echo -e "${YELLOW}⚠️  数据库可能还在启动中，请稍等几秒后重试${NC}"
fi

echo ""
echo "================================================"
echo -e "${GREEN}  PostgreSQL已准备就绪！${NC}"
echo "================================================"
echo ""
echo "📋 连接信息:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: trading"
echo "  User: postgres"
echo "  Password: postgres"
echo ""
echo "🔗 DATABASE_URL:"
echo "  export DATABASE_URL=\"postgresql+asyncpg://postgres:postgres@localhost:5432/trading\""
echo ""
echo "💡 下一步:"
echo "  1. 设置环境变量:"
echo "     export DATABASE_URL=\"postgresql+asyncpg://postgres:postgres@localhost:5432/trading\""
echo ""
echo "  2. 启动WebSocket订阅:"
echo "     cextools subscribe binance-user-stream --create-tables"
echo ""
echo "  3. 连接数据库查询:"
echo "     docker exec -it ${CONTAINER_NAME} psql -U postgres -d trading"
echo ""
echo "🛑 停止容器:"
echo "     docker stop ${CONTAINER_NAME}"
echo ""
echo "🗑️  删除容器:"
echo "     docker stop ${CONTAINER_NAME} && docker rm ${CONTAINER_NAME}"
echo ""

