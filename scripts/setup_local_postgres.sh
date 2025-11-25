#!/bin/bash

# 本地PostgreSQL快速配置脚本

echo "================================================"
echo "  本地PostgreSQL配置"
echo "================================================"
echo ""

# 检查PostgreSQL是否已安装
if command -v psql &> /dev/null; then
    echo "✅ 检测到PostgreSQL"
    psql --version
    echo ""
    
    # 尝试创建数据库
    echo "正在创建数据库 'trading'..."
    
    # 方法1: 直接尝试（可能需要密码）
    createdb trading 2>/dev/null && echo "✅ 数据库创建成功" || {
        echo "⚠️  创建失败，尝试使用sudo..."
        sudo -u postgres createdb trading 2>/dev/null && echo "✅ 数据库创建成功" || echo "数据库可能已存在"
    }
    
    echo ""
    echo "📋 请手动测试连接并找出正确的密码:"
    echo ""
    echo "测试1: 尝试无密码连接"
    echo "  psql -U $USER -d trading"
    echo ""
    echo "测试2: 尝试postgres用户"
    echo "  sudo -u postgres psql -d trading"
    echo ""
    echo "如果成功连接，设置DATABASE_URL:"
    echo ""
    echo "无密码:"
    echo "  export DATABASE_URL=\"postgresql+asyncpg://$USER@localhost:5432/trading\""
    echo ""
    echo "有密码:"
    echo "  export DATABASE_URL=\"postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/trading\""
    echo ""
else
    echo "❌ 未检测到PostgreSQL"
    echo ""
    echo "安装PostgreSQL:"
    echo ""
    echo "Ubuntu/Debian:"
    echo "  sudo apt update"
    echo "  sudo apt install postgresql postgresql-contrib"
    echo ""
    echo "或使用Docker（推荐）:"
    echo "  sudo docker run --name postgres-trading \\"
    echo "    -e POSTGRES_PASSWORD=postgres \\"
    echo "    -e POSTGRES_DB=trading \\"
    echo "    -p 5432:5432 \\"
    echo "    -d postgres:16"
    echo ""
fi

