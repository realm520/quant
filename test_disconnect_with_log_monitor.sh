#!/bin/bash
# 改进的断线回补测试脚本，实时监控日志

set -e

DISCONNECT_DURATION=${1:-120}  # 默认断线2分钟（足够让 ping/pong 超时）

echo "========================================"
echo "XT WebSocket 断线回补功能测试（改进版）"
echo "========================================"
echo ""
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "断线时长: ${DISCONNECT_DURATION} 秒"
echo ""

# 检查服务是否在运行
SERVICE_PID=$(pgrep -f "cextools subscribe multi-account" | head -1)
if [ -z "$SERVICE_PID" ]; then
    echo "❌ 错误：未找到运行中的订阅服务"
    exit 1
fi

echo "✓ 找到运行中的服务 (PID: $SERVICE_PID)"
echo ""

# 清空日志（确保日志干净）
> logs/tri-arb.log
echo "✓ 日志文件已清空"
echo ""

# 记录断线前的时间
DISCONNECT_START=$(date '+%Y-%m-%d %H:%M:%S')
DISCONNECT_START_TS=$(date +%s)

echo "[1/4] 记录断线前的状态..."
BEFORE_COUNT=$(export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading" && export LOG_LEVEL=CRITICAL && source .venv/bin/activate 2>/dev/null && python3 << 'PYTHON_SCRIPT' 2>&1 | grep -E "^[0-9]+$" | tail -1
import asyncio
from datetime import datetime, timedelta
from tri_arb.storage.database import DatabaseManager
from sqlalchemy import text

async def count_recent_orders():
    db_manager = DatabaseManager()
    now = datetime.utcnow()
    start_time = now - timedelta(hours=1)
    
    total = 0
    async with db_manager.session() as session:
        result = await session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'xt_order_updates_account%'
        """))
        tables = [row[0] for row in result.fetchall()]
        
        for table in tables:
            try:
                result = await session.execute(text(f'''
                    SELECT COUNT(*) as cnt
                    FROM {table}
                    WHERE create_time >= :start_time
                '''), {'start_time': start_time})
                row = result.fetchone()
                if row:
                    total += row[0]
            except:
                pass
    
    print(total)

asyncio.run(count_recent_orders())
PYTHON_SCRIPT
)
echo "  断线前订单数（最近1小时）: ${BEFORE_COUNT:-N/A}"
echo ""

# 开始监控日志（后台进程）
LOG_MONITOR_PID=
(
    while true; do
        if [ -f logs/tri-arb.log ]; then
            tail -n 0 -f logs/tri-arb.log 2>/dev/null | grep -iE "disconnect|reconnect|closed|syncing|missing|recorded|error|warning" | while read line; do
                echo "[日志] $(date '+%H:%M:%S') $line"
            done
        fi
        sleep 1
    done
) &
LOG_MONITOR_PID=$!
echo "✓ 日志监控已启动 (PID: $LOG_MONITOR_PID)"
echo ""

# 使用 iptables 阻止到 fstream.xt.com 的连接
echo "[2/4] 触发网络断线（${DISCONNECT_DURATION}秒）..."
echo "  断线开始时间: $DISCONNECT_START"
echo "  正在阻止到 fstream.xt.com 的连接..."

# 检查规则是否已存在
if sudo iptables -C OUTPUT -d fstream.xt.com -j DROP 2>/dev/null; then
    echo "  ⚠️  iptables 规则已存在，先删除..."
    sudo iptables -D OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || true
fi

# 添加阻止规则
sudo iptables -I OUTPUT 1 -d fstream.xt.com -j DROP 2>/dev/null || {
    echo "  ❌ 错误：无法添加 iptables 规则（需要 sudo 权限）"
    kill $LOG_MONITOR_PID 2>/dev/null || true
    exit 1
}

echo "  ✓ 已阻止到 fstream.xt.com 的连接"
echo "  等待 ${DISCONNECT_DURATION} 秒（让 ping/pong 超时）..."

# 实时显示日志
for i in $(seq 1 ${DISCONNECT_DURATION}); do
    sleep 1
    if [ $((i % 10)) -eq 0 ]; then
        echo "  断线中... ${i}/${DISCONNECT_DURATION} 秒"
    fi
done

# 恢复网络连接
echo ""
echo "[3/4] 恢复网络连接..."
DISCONNECT_END=$(date '+%Y-%m-%d %H:%M:%S')
DISCONNECT_END_TS=$(date +%s)
DISCONNECT_DURATION_ACTUAL=$((DISCONNECT_END_TS - DISCONNECT_START_TS))

# 删除阻止规则
sudo iptables -D OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || {
    echo "  ⚠️  清理 iptables 规则失败（可能规则不存在）"
}

echo "  ✓ 已恢复网络连接"
echo "  断线结束时间: $DISCONNECT_END"
echo "  实际断线时长: ${DISCONNECT_DURATION_ACTUAL} 秒"
echo ""

# 等待重连和数据回补
echo "[4/4] 等待重连和数据回补（120秒）..."
for i in $(seq 1 120); do
    sleep 1
    if [ $((i % 20)) -eq 0 ]; then
        echo "  等待中... ${i}/120 秒"
    fi
done

# 停止日志监控
kill $LOG_MONITOR_PID 2>/dev/null || true

echo ""
echo "========================================"
echo "测试结果分析"
echo "========================================"
echo ""

# 检查日志中的关键信息
echo "检查日志中的断线和回补记录..."
echo ""

if [ -f logs/tri-arb.log ]; then
    echo "日志文件大小: $(wc -l < logs/tri-arb.log) 行"
    echo ""
    
    echo "断线相关日志:"
    grep -iE "disconnect|connection.*closed|websocket.*closed|recorded.*disconnect" logs/tri-arb.log | tail -10 || echo "  （未找到）"
    echo ""
    
    echo "重连相关日志:"
    grep -iE "reconnect|connected|starting missing" logs/tri-arb.log | tail -10 || echo "  （未找到）"
    echo ""
    
    echo "回补相关日志:"
    grep -iE "syncing.*order|synced.*order|missing.*data" logs/tri-arb.log | tail -10 || echo "  （未找到）"
    echo ""
fi

# 检查回补结果
AFTER_COUNT=$(export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading" && export LOG_LEVEL=CRITICAL && source .venv/bin/activate 2>/dev/null && python3 << 'PYTHON_SCRIPT' 2>&1 | grep -E "^[0-9]+,[0-9]+$" | tail -1
import asyncio
from datetime import datetime, timedelta
from tri_arb.storage.database import DatabaseManager
from sqlalchemy import text
import json

async def check_backfill():
    db_manager = DatabaseManager()
    now = datetime.utcnow()
    start_time = now - timedelta(minutes=5)
    
    rest_sync_count = 0
    rest_sync_fixed_count = 0
    
    async with db_manager.session() as session:
        result = await session.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'xt_order_updates_account%'
        """))
        tables = [row[0] for row in result.fetchall()]
        
        for table in tables:
            try:
                result = await session.execute(text(f'''
                    SELECT raw_data
                    FROM {table}
                    WHERE create_time >= :start_time
                '''), {'start_time': start_time})
                rows = result.fetchall()
                
                for row in rows:
                    raw_data = row[0]
                    if raw_data:
                        try:
                            data = json.loads(raw_data)
                            source = data.get('source', '')
                            if 'rest_sync_fixed_lookback' in source:
                                rest_sync_fixed_count += 1
                            elif 'rest_sync' in source:
                                rest_sync_count += 1
                        except:
                            pass
            except:
                pass
    
    print(f"{rest_sync_count},{rest_sync_fixed_count}")

asyncio.run(check_backfill())
PYTHON_SCRIPT
)

REST_SYNC_COUNT=$(echo "$AFTER_COUNT" | cut -d',' -f1)
REST_SYNC_FIXED_COUNT=$(echo "$AFTER_COUNT" | cut -d',' -f2)
TOTAL_REST_SYNC=$((REST_SYNC_COUNT + REST_SYNC_FIXED_COUNT))

echo "回补订单统计:"
echo "  REST 回补 (rest_sync): $REST_SYNC_COUNT 条"
echo "  REST 回补 (rest_sync_fixed_lookback): $REST_SYNC_FIXED_COUNT 条"
echo "  总计: $TOTAL_REST_SYNC 条"
echo ""

# 结论
echo "========================================"
if [ -n "$AFTER_COUNT" ] && [ "$TOTAL_REST_SYNC" -gt "0" ]; then
    echo "✅ 测试通过：检测到断线回补功能正常工作"
    echo "   成功回补 $TOTAL_REST_SYNC 条订单"
else
    echo "⚠️  测试结果：未检测到回补订单"
    echo "   请检查日志文件查看详细信息"
fi
echo "========================================"
echo ""

echo "提示："
echo "  - 服务仍在运行 (PID: $SERVICE_PID)"
echo "  - 查看完整日志: tail -f logs/tri-arb.log"
echo "  - 停止服务: kill $SERVICE_PID"
echo ""
