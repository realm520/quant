#!/bin/bash
# Amazon Linux 快速部署脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 检测 Amazon Linux 版本
detect_amazon_linux() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        if [[ "$ID" == "amzn" ]]; then
            if [[ "$VERSION_ID" == "2023" ]]; then
                echo "2023"
            else
                echo "2"
            fi
        else
            echo "unknown"
        fi
    else
        echo "unknown"
    fi
}

AMAZON_LINUX_VERSION=$(detect_amazon_linux)

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CEX Tools Amazon Linux 部署脚本${NC}"
echo -e "${GREEN}检测到: Amazon Linux ${AMAZON_LINUX_VERSION}${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 检查是否为 root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}警告: 不建议以 root 用户运行此脚本${NC}"
    echo -e "${YELLOW}建议使用普通用户（如 ec2-user）运行，仅在需要时使用 sudo${NC}"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 步骤 1: 更新系统
echo -e "${BLUE}[1/10] 更新系统...${NC}"
if [ "$AMAZON_LINUX_VERSION" == "2023" ]; then
    sudo dnf update -y
else
    sudo yum update -y
fi
echo -e "${GREEN}✅ 系统更新完成${NC}"
echo ""

# 步骤 2: 安装基础依赖
echo -e "${BLUE}[2/10] 安装基础依赖...${NC}"
if [ "$AMAZON_LINUX_VERSION" == "2023" ]; then
    sudo dnf groupinstall -y "Development Tools"
    sudo dnf install -y gcc gcc-c++ make openssl-devel libffi-devel zlib-devel readline-devel git
else
    sudo yum groupinstall -y "Development Tools"
    sudo yum install -y gcc gcc-c++ make openssl-devel libffi-devel zlib-devel readline-devel git
fi
echo -e "${GREEN}✅ 基础依赖安装完成${NC}"
echo ""

# 步骤 3: 安装 PostgreSQL
echo -e "${BLUE}[3/10] 安装 PostgreSQL...${NC}"
if [ "$AMAZON_LINUX_VERSION" == "2023" ]; then
    sudo dnf install -y postgresql15 postgresql15-server postgresql15-devel
    sudo postgresql-setup --initdb || sudo /usr/pgsql-15/bin/postgresql-15-setup initdb
    sudo systemctl enable postgresql-15
    sudo systemctl start postgresql-15
else
    sudo amazon-linux-extras enable postgresql14
    sudo yum install -y postgresql postgresql-server postgresql-devel
    sudo postgresql-setup initdb
    sudo systemctl enable postgresql
    sudo systemctl start postgresql
fi
echo -e "${GREEN}✅ PostgreSQL 安装并启动完成${NC}"
echo ""

# 步骤 4: 安装 Python 3.11
echo -e "${BLUE}[4/10] 安装 Python 3.11...${NC}"
if command -v python3.11 &> /dev/null; then
    echo -e "${YELLOW}Python 3.11 已安装${NC}"
    python3.11 --version
else
    echo -e "${YELLOW}Python 3.11 未找到，尝试安装...${NC}"
    if [ "$AMAZON_LINUX_VERSION" == "2023" ]; then
        sudo dnf install -y python3.11 python3.11-devel python3.11-pip || {
            echo -e "${YELLOW}无法通过包管理器安装，请手动编译安装${NC}"
            echo "参考: https://docs.python.org/3.11/using/unix.html#building-python"
        }
    else
        # Amazon Linux 2 可能需要从源码编译
        echo -e "${YELLOW}Amazon Linux 2 需要手动安装 Python 3.11${NC}"
        echo "请参考部署文档中的安装步骤"
    fi
fi
echo ""

# 步骤 5: 安装 uv
echo -e "${BLUE}[5/10] 安装 uv 包管理器...${NC}"
if command -v uv &> /dev/null; then
    echo -e "${YELLOW}uv 已安装${NC}"
    uv --version
else
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
    echo -e "${GREEN}✅ uv 安装完成${NC}"
fi
echo ""

# 步骤 6: 安装 Docker（可选）
echo -e "${BLUE}[6/10] 安装 Docker（用于监控）...${NC}"
read -p "是否安装 Docker? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v docker &> /dev/null; then
        echo -e "${YELLOW}Docker 已安装${NC}"
    else
        if [ "$AMAZON_LINUX_VERSION" == "2023" ]; then
            sudo dnf install -y docker docker-compose-plugin
        else
            sudo yum install -y docker docker-compose-plugin
        fi
        sudo systemctl enable docker
        sudo systemctl start docker
        sudo usermod -aG docker $USER
        echo -e "${GREEN}✅ Docker 安装完成${NC}"
        echo -e "${YELLOW}注意: 需要重新登录才能使 docker 组生效${NC}"
    fi
fi
echo ""

# 步骤 7: 配置数据库
echo -e "${BLUE}[7/10] 配置数据库...${NC}"
read -p "是否创建数据库和用户? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "数据库用户名 (默认: ec2-user): " DB_USER
    DB_USER=${DB_USER:-ec2-user}
    read -sp "数据库密码 (留空则不设置密码): " DB_PASS
    echo
    
    sudo -u postgres psql << EOF
CREATE DATABASE trading;
CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS:-null}';
GRANT ALL PRIVILEGES ON DATABASE trading TO ${DB_USER};
ALTER USER ${DB_USER} CREATEDB;
\q
EOF
    
    echo -e "${GREEN}✅ 数据库配置完成${NC}"
    echo -e "${YELLOW}数据库连接字符串:${NC}"
    if [ -z "$DB_PASS" ]; then
        echo "postgresql+asyncpg://${DB_USER}@localhost:5432/trading"
    else
        echo "postgresql+asyncpg://${DB_USER}:${DB_PASS}@localhost:5432/trading"
    fi
fi
echo ""

# 步骤 8: 获取代码
echo -e "${BLUE}[8/10] 获取项目代码...${NC}"
if [ -d "quant" ]; then
    echo -e "${YELLOW}项目目录已存在，跳过克隆${NC}"
    cd quant
else
    read -p "项目代码路径 (默认: ~/quant): " PROJECT_DIR
    PROJECT_DIR=${PROJECT_DIR:-~/quant}
    
    if [ ! -d "$PROJECT_DIR" ]; then
        git clone https://github.com/realm520/quant.git "$PROJECT_DIR"
    fi
    cd "$PROJECT_DIR"
fi
echo -e "${GREEN}✅ 代码已就绪${NC}"
echo ""

# 步骤 9: 创建虚拟环境并安装依赖
echo -e "${BLUE}[9/10] 创建虚拟环境并安装依赖...${NC}"
if [ -d ".venv" ]; then
    echo -e "${YELLOW}虚拟环境已存在${NC}"
else
    if command -v uv &> /dev/null; then
        uv venv --python 3.11
        source .venv/bin/activate
        uv pip install -e .
        uv pip install -r requirements-db.txt
    else
        python3.11 -m venv .venv
        source .venv/bin/activate
        pip install --upgrade pip
        pip install -e .
        pip install -r requirements-db.txt
    fi
    echo -e "${GREEN}✅ 依赖安装完成${NC}"
fi
echo ""

# 步骤 10: 配置防火墙
echo -e "${BLUE}[10/10] 配置防火墙...${NC}"
if systemctl is-active --quiet firewalld; then
    read -p "是否配置防火墙规则? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo firewall-cmd --permanent --add-port=3000/tcp  # Grafana
        sudo firewall-cmd --permanent --add-port=9090/tcp  # Prometheus
        sudo firewall-cmd --permanent --add-port=9600/tcp  # Metrics
        sudo firewall-cmd --permanent --add-port=9601/tcp  # Metrics
        sudo firewall-cmd --reload
        echo -e "${GREEN}✅ 防火墙规则已添加${NC}"
    fi
else
    echo -e "${YELLOW}firewalld 未运行，跳过防火墙配置${NC}"
fi
echo ""

# 完成
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}下一步操作:${NC}"
echo ""
echo -e "1. 配置环境变量:"
echo -e "   ${BLUE}nano .env${NC}"
echo -e "   或:"
echo -e "   ${BLUE}export XT_API_KEY='your_key'${NC}"
echo -e "   ${BLUE}export XT_API_SECRET='your_secret'${NC}"
echo -e "   ${BLUE}export DATABASE_URL='postgresql+asyncpg://user:pass@localhost:5432/trading'${NC}"
echo ""
echo -e "2. 启动监控服务（如果安装了 Docker）:"
echo -e "   ${BLUE}docker compose -f docker-compose.monitoring.yml up -d${NC}"
echo ""
echo -e "3. 启动监控命令:"
echo -e "   ${BLUE}source .venv/bin/activate${NC}"
echo -e "   ${BLUE}cextools account watch-all --config config/accounts.json${NC}"
echo ""
echo -e "4. 访问 Grafana:"
echo -e "   ${BLUE}http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'your-server-ip'):3000${NC}"
echo ""
echo -e "${YELLOW}重要提醒:${NC}"
echo -e "- 记得在 AWS 控制台配置安全组规则"
echo -e "- 更改 Grafana 默认密码 (admin/admin)"
echo -e "- 查看详细文档: docs/DEPLOYMENT_AMAZON_LINUX.md"
echo ""

