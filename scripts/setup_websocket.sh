#!/bin/bash

# Binance WebSocket订阅功能快速安装脚本

set -e

echo "================================================"
echo "  Binance WebSocket订阅功能 - 快速安装"
echo "================================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查Python虚拟环境
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}警告: 未检测到Python虚拟环境${NC}"
    echo "建议先激活虚拟环境:"
    echo "  source .venv/bin/activate"
    echo ""
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 步骤1：安装Python依赖
echo -e "${GREEN}步骤 1/4: 安装Python依赖${NC}"
if [ -f "requirements-db.txt" ]; then
    echo "正在安装依赖..."
    pip install -r requirements-db.txt
    echo -e "${GREEN}✅ 依赖安装完成${NC}"
else
    echo -e "${RED}❌ 错误: 找不到 requirements-db.txt${NC}"
    exit 1
fi
echo ""

# 步骤2：检查PostgreSQL
echo -e "${GREEN}步骤 2/4: 检查PostgreSQL${NC}"
if command -v docker &> /dev/null; then
    echo "检测到Docker，可以使用Docker运行PostgreSQL"
    read -p "是否使用Docker启动PostgreSQL? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "正在启动PostgreSQL容器..."
        docker run --name postgres-trading \
            -e POSTGRES_PASSWORD=postgres \
            -e POSTGRES_DB=trading \
            -p 5432:5432 \
            -d postgres:16 || echo "容器可能已存在"
        
        echo "等待PostgreSQL启动..."
        sleep 5
        echo -e "${GREEN}✅ PostgreSQL已启动${NC}"
    fi
elif command -v psql &> /dev/null; then
    echo "检测到本地PostgreSQL"
    psql -U postgres -c "SELECT version();" &> /dev/null && echo -e "${GREEN}✅ PostgreSQL已就绪${NC}" || echo -e "${YELLOW}⚠️  PostgreSQL未运行${NC}"
else
    echo -e "${YELLOW}⚠️  未检测到PostgreSQL${NC}"
    echo "请手动安装PostgreSQL或使用Docker"
fi
echo ""

# 步骤3：配置环境变量
echo -e "${GREEN}步骤 3/4: 配置环境变量${NC}"

if [ -z "$BINANCE_API_KEY" ]; then
    echo -e "${YELLOW}未设置 BINANCE_API_KEY${NC}"
    read -p "请输入Binance API Key (或按Enter跳过): " api_key
    if [ ! -z "$api_key" ]; then
        export BINANCE_API_KEY="$api_key"
        echo "export BINANCE_API_KEY=\"$api_key\"" >> .env
    fi
fi

if [ -z "$BINANCE_API_SECRET" ]; then
    echo -e "${YELLOW}未设置 BINANCE_API_SECRET${NC}"
    read -p "请输入Binance API Secret (或按Enter跳过): " api_secret
    if [ ! -z "$api_secret" ]; then
        export BINANCE_API_SECRET="$api_secret"
        echo "export BINANCE_API_SECRET=\"$api_secret\"" >> .env
    fi
fi

if [ -z "$DATABASE_URL" ]; then
    default_db="postgresql+asyncpg://postgres:postgres@localhost:5432/trading"
    read -p "请输入数据库URL (默认: $default_db): " db_url
    db_url=${db_url:-$default_db}
    export DATABASE_URL="$db_url"
    echo "export DATABASE_URL=\"$db_url\"" >> .env
fi

echo -e "${GREEN}✅ 环境变量配置完成${NC}"
echo ""

# 步骤4：初始化数据库
echo -e "${GREEN}步骤 4/4: 初始化数据库${NC}"
read -p "是否初始化数据库表? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "正在创建数据库表..."
    python3 << EOF
import asyncio
from tri_arb.storage.database import DatabaseManager

async def init():
    try:
        db = DatabaseManager()
        await db.create_tables()
        print("✅ 数据库表创建成功")
        await db.close()
    except Exception as e:
        print(f"❌ 创建失败: {e}")

asyncio.run(init())
EOF
fi
echo ""

# 完成
echo "================================================"
echo -e "${GREEN}  ✅ 安装完成!${NC}"
echo "================================================"
echo ""
echo "下一步："
echo "  1. 加载环境变量:"
echo "     source .env"
echo ""
echo "  2. 启动WebSocket订阅:"
echo "     cextools subscribe binance-user-stream"
echo ""
echo "  3. 查询数据（在另一个终端）:"
echo "     psql -U postgres -d trading -c \"SELECT * FROM order_updates LIMIT 5;\""
echo ""
echo "文档："
echo "  - docs/WEBSOCKET_SETUP_GUIDE.md"
echo "  - docs/binance-websocket-subscription.md"
echo ""

