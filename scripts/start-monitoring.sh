#!/bin/bash
# 启动监控服务的便捷脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🚀 启动监控服务..."

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi

# 检查 metrics 端点是否可访问
if ! curl -s http://127.0.0.1:9600/metrics > /dev/null 2>&1; then
    echo "⚠️  警告: http://127.0.0.1:9600/metrics 不可访问"
    echo "   请确保 cextools account watch-balance 正在运行"
    echo "   例如: export PROM_METRICS_PORT=9600 && cextools account watch-balance ..."
    read -p "   是否继续启动 Prometheus 和 Grafana? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 启动 Prometheus 和 Grafana
cd "$PROJECT_ROOT"
docker-compose -f docker-compose.monitoring.yml up -d

echo ""
echo "✅ 监控服务已启动！"
echo ""
echo "📊 访问地址:"
echo "   - Prometheus: http://localhost:9090"
echo "   - Grafana:    http://localhost:3000"
echo "   - Metrics:    http://localhost:9600/metrics"
echo ""
echo "🔑 Grafana 默认登录:"
echo "   用户名: admin"
echo "   密码:   admin"
echo ""
echo "📝 下一步:"
echo "   1. 在 Grafana 中配置 Prometheus 数据源 (http://localhost:9090)"
echo "   2. 导入仪表板: Dashboards > Import > 上传 grafana/dashboards/exchange-monitor.json"
echo ""
echo "🛑 停止服务: docker-compose -f docker-compose.monitoring.yml down"

