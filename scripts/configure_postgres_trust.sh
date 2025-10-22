#!/bin/bash

# 配置PostgreSQL使用trust认证（无密码连接）

set -e

echo "================================================"
echo "  配置PostgreSQL无密码连接"
echo "================================================"
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查PostgreSQL是否运行
if ! pg_isready -h localhost -p 5432 > /dev/null 2>&1; then
    echo -e "${RED}❌ PostgreSQL未运行${NC}"
    echo "启动PostgreSQL:"
    echo "  sudo systemctl start postgresql"
    exit 1
fi

echo -e "${GREEN}✅ PostgreSQL运行中${NC}"
echo ""

# 获取pg_hba.conf位置
echo "查找pg_hba.conf位置..."
PG_HBA_CONF=$(sudo -u postgres psql -t -P format=unaligned -c 'SHOW hba_file;' 2>/dev/null || echo "")

if [ -z "$PG_HBA_CONF" ]; then
    # 尝试常见位置
    PG_HBA_CONF="/etc/postgresql/14/main/pg_hba.conf"
    if [ ! -f "$PG_HBA_CONF" ]; then
        PG_HBA_CONF="/var/lib/postgresql/data/pg_hba.conf"
    fi
fi

echo "pg_hba.conf位置: $PG_HBA_CONF"
echo ""

# 备份原始配置
if [ -f "$PG_HBA_CONF" ]; then
    BACKUP_FILE="${PG_HBA_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "备份原始配置到: $BACKUP_FILE"
    sudo cp "$PG_HBA_CONF" "$BACKUP_FILE"
    echo -e "${GREEN}✅ 备份完成${NC}"
    echo ""
fi

# 创建新的pg_hba.conf配置
echo "配置trust认证..."
cat << 'EOF' | sudo tee "${PG_HBA_CONF}.new" > /dev/null
# PostgreSQL Client Authentication Configuration File
# ===================================================
#
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# "local" is for Unix domain socket connections only
local   all             all                                     trust

# IPv4 local connections:
host    all             all             127.0.0.1/32            trust
host    all             all             localhost               trust

# IPv6 local connections:
host    all             all             ::1/128                 trust
EOF

# 应用新配置
sudo mv "${PG_HBA_CONF}.new" "$PG_HBA_CONF"
echo -e "${GREEN}✅ 配置已更新${NC}"
echo ""

# 重新加载PostgreSQL配置
echo "重新加载PostgreSQL配置..."
sudo systemctl reload postgresql || sudo -u postgres pg_ctl reload -D /var/lib/postgresql/14/main

echo -e "${GREEN}✅ PostgreSQL配置已重新加载${NC}"
echo ""

# 创建trading数据库（如果不存在）
echo "创建trading数据库..."
sudo -u postgres psql -c "CREATE DATABASE trading;" 2>/dev/null && echo -e "${GREEN}✅ 数据库创建成功${NC}" || echo -e "${YELLOW}ℹ️  数据库可能已存在${NC}"
echo ""

# 测试连接
echo "测试无密码连接..."
if psql -U postgres -h localhost -d trading -c "SELECT version();" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ 无密码连接成功！${NC}"
    echo ""
    echo "================================================"
    echo -e "${GREEN}  配置完成！${NC}"
    echo "================================================"
    echo ""
    echo "📋 连接信息:"
    echo "  Host: localhost"
    echo "  Port: 5432"
    echo "  Database: trading"
    echo "  User: postgres"
    echo "  Password: (无密码)"
    echo ""
    echo "🔗 DATABASE_URL (无密码):"
    echo "  export DATABASE_URL=\"postgresql+asyncpg://postgres@localhost:5432/trading\""
    echo ""
    echo "💡 下一步:"
    echo "  1. 设置环境变量:"
    echo "     export DATABASE_URL=\"postgresql+asyncpg://postgres@localhost:5432/trading\""
    echo ""
    echo "  2. 启动WebSocket订阅:"
    echo "     cextools subscribe binance-user-stream --create-tables"
    echo ""
    echo "  3. 直接连接数据库:"
    echo "     psql -U postgres -h localhost -d trading"
    echo ""
else
    echo -e "${RED}❌ 连接测试失败${NC}"
    echo "可能需要等待几秒让配置生效，然后手动测试:"
    echo "  psql -U postgres -h localhost -d trading"
    echo ""
    echo "如果还是失败，恢复备份:"
    echo "  sudo cp $BACKUP_FILE $PG_HBA_CONF"
    echo "  sudo systemctl reload postgresql"
    exit 1
fi

echo "⚠️  安全提示:"
echo "  trust认证允许任何本地用户无密码连接数据库"
echo "  仅适用于开发环境，生产环境请使用密码认证"
echo ""
echo "恢复密码认证:"
echo "  sudo cp $BACKUP_FILE $PG_HBA_CONF"
echo "  sudo systemctl reload postgresql"
echo ""

