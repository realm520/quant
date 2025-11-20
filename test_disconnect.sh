#!/bin/bash
# 简化版 XT WebSocket 断线回补测试脚本
# 使用 iptables 模拟网络断线

set -e

echo "========================================"
echo "XT WebSocket 断线回补测试"
echo "========================================"
echo ""

# 配置
DISCONNECT_DURATION=${1:-30}  # 断线时长（秒），默认30秒
XT_WS_HOST="fstream.xt.com"

echo "测试配置:"
echo "  断线时长: ${DISCONNECT_DURATION} 秒"
echo "  WebSocket: ${XT_WS_HOST}"
echo ""

# 检查是否已有订阅服务运行
SUBSCRIBE_PIDS=$(pgrep -f "cextools subscribe multi-account" || true)
if [ -z "$SUBSCRIBE_PIDS" ]; then
    echo "❌ 错误：未检测到运行中的订阅服务"
    echo ""
    echo "请先启动订阅服务："
    echo "  cd /home/ubuntu/quant"
    echo "  source .venv/bin/activate"
    echo "  cextools subscribe multi-account --config config/accounts.json"
    echo ""
    exit 1
fi

echo "✓ 检测到订阅服务运行中 (PID: $SUBSCRIBE_PIDS)"
echo ""

# 步骤1: 模拟断线
echo "[1/3] 模拟网络断线..."
echo "  使用 iptables 阻止到 ${XT_WS_HOST} 的连接"

# 添加iptables规则（需要sudo权限）
if ! sudo iptables -C OUTPUT -d ${XT_WS_HOST} -j DROP 2>/dev/null; then
    sudo iptables -A OUTPUT -d ${XT_WS_HOST} -j DROP
    echo "  ✓ iptables规则已添加"
else
    echo "  ⚠️  iptables规则已存在"
fi

echo "  断线开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 步骤2: 等待断线期间
echo "[2/3] 等待 ${DISCONNECT_DURATION} 秒（断线期间）..."
for i in $(seq $DISCONNECT_DURATION -1 1); do
    printf "\r  剩余时间: %02d 秒" $i
    sleep 1
done
printf "\n"
echo ""

# 步骤3: 恢复连接
echo "[3/3] 恢复网络连接..."
sudo iptables -D OUTPUT -d ${XT_WS_HOST} -j DROP 2>/dev/null || echo "  ⚠️  未找到iptables规则"
echo "  ✓ 网络连接已恢复"
echo "  恢复时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

echo "========================================"
echo "测试完成"
echo "========================================"
echo ""
echo "接下来的步骤:"
echo "  1. 等待 60-120 秒，让服务完成重连和数据回补"
echo "  2. 检查订阅服务的日志，查找以下关键信息："
echo "     - 'Recorded disconnect time' （断线时间记录）"
echo "     - 'Starting missing data sync' （开始数据同步）"
echo "     - 'Syncing orders for fixed lookback period' （回补订单）"
echo "     - 'Synced order data from REST API' （REST API回补完成）"
echo "  3. 查询数据库验证回补的订单："
echo "     - 查找 raw_data 包含 'rest_sync_fixed_lookback' 的订单记录"
echo ""

# 提供查询命令示例
cat << 'EOF'
查询数据库示例（PostgreSQL）:

# 查看最近1小时通过REST API回补的订单
SELECT
    update_time,
    symbol,
    order_id,
    side,
    status,
    raw_data::json->>'source' as source
FROM xt_order_updates
WHERE
    update_time > NOW() - INTERVAL '1 hour'
    AND raw_data::text LIKE '%rest_sync%'
ORDER BY update_time DESC
LIMIT 20;

EOF

echo "按 Ctrl+C 可以停止订阅服务（PID: $SUBSCRIBE_PIDS）"
echo ""
