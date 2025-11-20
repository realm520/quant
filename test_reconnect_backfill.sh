#!/bin/bash
# 测试 XT WebSocket 断线回补功能
# 1. 检查账号是否有挂单撤单活动
# 2. 模拟断线
# 3. 验证是否回补到订单

set -e

LOG_FILE="/tmp/xt_reconnect_test_$(date +%Y%m%d_%H%M%S).log"
PID_FILE="/tmp/xt_subscribe.pid"
DISCONNECT_DURATION=30  # 断线时间（秒）

echo "========================================"
echo "XT WebSocket 断线回补功能测试"
echo "========================================"
echo ""
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "断线时长: ${DISCONNECT_DURATION} 秒"
echo "日志文件: $LOG_FILE"
echo ""

# 清理旧的进程
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "[清理] 停止旧的订阅服务进程 (PID: $OLD_PID)..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 2
    fi
    rm -f "$PID_FILE"
fi

# 启动订阅服务
echo "[1/6] 启动订阅服务..."
cd /home/ubuntu/quant
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
export PROM_METRICS_PORT=9601

source .venv/bin/activate

nohup /home/ubuntu/quant/.venv/bin/cextools subscribe multi-account --config config/accounts.json > "$LOG_FILE" 2>&1 &
SUBSCRIBE_PID=$!
echo "$SUBSCRIBE_PID" > "$PID_FILE"

echo "  服务已启动 (PID: $SUBSCRIBE_PID)"
echo ""

# 等待连接建立
echo "[2/6] 等待 WebSocket 连接建立（30秒）..."
sleep 30

# 检查进程状态
if ! ps -p "$SUBSCRIBE_PID" > /dev/null 2>&1; then
    echo "  ❌ 错误：进程意外退出"
    echo "  日志内容："
    tail -50 "$LOG_FILE"
    exit 1
fi

# 检查连接状态
CONNECTION_COUNT=$(timeout 5 grep -c "Connected to XT WebSocket" "$LOG_FILE" 2>/dev/null || echo "0")
if [ "$CONNECTION_COUNT" -eq "0" ]; then
    echo "  ⚠️  警告：未检测到连接建立日志"
else
    echo "  ✓ 检测到连接建立"
fi

# 记录初始订单数（最近1分钟的订单）
echo "[3/6] 记录初始订单数（检查账号活跃度）..."
INITIAL_TIME=$(date +%s)
INITIAL_ORDER_COUNT=$(export LOG_LEVEL=CRITICAL && source .venv/bin/activate && python3 test_reconnect_backfill.py count_recent 1 2>&1 | grep -E "^[0-9]+$" | tail -1)
echo "  初始订单数（最近1分钟）: $INITIAL_ORDER_COUNT"
echo ""

# 监控订单活动（30秒）
echo "[4/6] 监控订单活动（30秒）..."
MONITOR_START=$(date +%s)
sleep 30
MONITOR_END=$(date +%s)

# 统计监控期间的订单数
MONITOR_ORDER_COUNT=$(export LOG_LEVEL=CRITICAL && source .venv/bin/activate && python3 test_reconnect_backfill.py count_recent 1 2>&1 | grep -E "^[0-9]+$" | tail -1)

MONITOR_DELTA=$((MONITOR_ORDER_COUNT - INITIAL_ORDER_COUNT))
echo "  监控期间新增订单数: $MONITOR_DELTA"

if [ "$MONITOR_DELTA" -gt "10" ]; then
    echo "  ✓ 账号活跃度高，有频繁的挂单撤单活动"
elif [ "$MONITOR_DELTA" -gt "0" ]; then
    echo "  ⚠️  账号有一定活动，但不太频繁"
else
    echo "  ⚠️  账号活动较少，可能影响测试效果"
fi
echo ""

# 记录断线前的订单数
DISCONNECT_START=$(date +%s)
echo "[5/6] 模拟网络断线（${DISCONNECT_DURATION}秒）..."
echo "  断线开始时间: $(date '+%Y-%m-%d %H:%M:%S')"

# 记录断线前的订单数（用于对比）
BEFORE_DISCONNECT_COUNT=$(export LOG_LEVEL=CRITICAL && source .venv/bin/activate && python3 test_reconnect_backfill.py count_window 1 2>&1 | grep -E "^[0-9]+$" | tail -1)

echo "  断线前订单数（最近1小时）: $BEFORE_DISCONNECT_COUNT"

# 使用 iptables 阻止到 XT WebSocket 的连接
sudo iptables -A OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || echo "  ⚠️  iptables 规则可能已存在"

# 等待断线
echo "  断线中..."
sleep ${DISCONNECT_DURATION}

# 恢复网络连接
echo "[6/6] 恢复网络连接..."
echo "  断线结束时间: $(date '+%Y-%m-%d %H:%M:%S')"
sudo iptables -D OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || echo "  ⚠️  清理 iptables 规则失败"

echo ""
echo "等待重连和数据回补（60秒）..."
sleep 60

DISCONNECT_END=$(date +%s)
DISCONNECT_DURATION_ACTUAL=$((DISCONNECT_END - DISCONNECT_START))

# 记录断线后的订单数
AFTER_RECONNECT_COUNT=$(export LOG_LEVEL=CRITICAL && source .venv/bin/activate && python3 test_reconnect_backfill.py count_window 1 2>&1 | grep -E "^[0-9]+$" | tail -1)

NEW_ORDERS=$((AFTER_RECONNECT_COUNT - BEFORE_DISCONNECT_COUNT))

echo ""
echo "========================================"
echo "测试结果分析"
echo "========================================"
echo ""
echo "账号活跃度："
echo "  监控期间新增订单: $MONITOR_DELTA 条"
echo ""
echo "断线回补结果："
echo "  断线时长: ${DISCONNECT_DURATION_ACTUAL} 秒"
echo "  断线前订单数: $BEFORE_DISCONNECT_COUNT 条"
echo "  断线后订单数: $AFTER_RECONNECT_COUNT 条"
echo "  新增订单数: $NEW_ORDERS 条"
echo ""
echo "回补订单统计："
REST_SYNC_COUNT_FULL=$(export LOG_LEVEL=CRITICAL && source .venv/bin/activate && python3 test_reconnect_backfill.py count_rest_sync 1 2>&1 | grep -E "^[0-9]+,[0-9]+$" | tail -1)

REST_SYNC_COUNT=$(echo "$REST_SYNC_COUNT_FULL" | cut -d',' -f1)
REST_SYNC_FIXED_COUNT=$(echo "$REST_SYNC_COUNT_FULL" | cut -d',' -f2)
TOTAL_REST_SYNC=$((REST_SYNC_COUNT + REST_SYNC_FIXED_COUNT))

echo "  REST 回补订单总数: $TOTAL_REST_SYNC 条"
echo "    - rest_sync: $REST_SYNC_COUNT 条"
echo "    - rest_sync_fixed_lookback: $REST_SYNC_FIXED_COUNT 条"
echo ""

# 检查回补日志
echo "回补日志检查："
SYNC_LOG_COUNT=$(timeout 5 grep -c "Synced order data from REST API" "$LOG_FILE" 2>/dev/null || echo "0")
SYNC_START_LOG=$(timeout 5 grep -c "Syncing orders for fixed lookback period" "$LOG_FILE" 2>/dev/null || echo "0")

echo "  回补开始次数: $SYNC_START_LOG"
echo "  回补完成次数: $SYNC_LOG_COUNT"
echo ""

# 结论
echo "========================================"
if [ "$TOTAL_REST_SYNC" -gt "0" ]; then
    echo "✓ 测试通过：检测到断线回补功能正常工作"
    echo "  成功回补 $TOTAL_REST_SYNC 条订单"
else
    echo "⚠️  测试结果：未检测到回补订单"
    echo "  可能原因："
    echo "    1. 断线期间没有新的订单"
    echo "    2. 回补功能未触发"
    echo "    3. 需要更长的等待时间"
fi
echo "========================================"
echo ""
echo "提示："
echo "  查看完整日志: tail -f $LOG_FILE"
echo "  停止服务: kill $SUBSCRIBE_PID"
echo ""

