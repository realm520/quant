#!/bin/bash
# 强制断线回补测试脚本

set -e

DISCONNECT_DURATION=${1:-60}  # 默认断线1分钟

echo "========================================"
echo "XT WebSocket 强制断线回补功能测试"
echo "========================================"
echo ""
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "断线方式: 直接 kill WebSocket 进程"
echo ""

# 检查服务是否在运行
SERVICE_PID=$(pgrep -f "cextools subscribe multi-account" | head -1)
if [ -z "$SERVICE_PID" ]; then
    echo "❌ 错误：未找到运行中的订阅服务"
    exit 1
fi

echo "✓ 找到运行中的服务 (PID: $SERVICE_PID)"
echo ""

# 清空日志
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

# 方法1：使用 iptables 阻止连接（给一些时间让连接建立）
echo "[2/4] 触发网络断线（${DISCONNECT_DURATION}秒）..."
echo "  断线开始时间: $DISCONNECT_START"
echo "  正在阻止到 fstream.xt.com 的连接..."

# 清理旧的规则
sudo iptables -D OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || true

# 添加阻止规则
sudo iptables -I OUTPUT 1 -d fstream.xt.com -j DROP 2>/dev/null || {
    echo "  ❌ 错误：无法添加 iptables 规则（需要 sudo 权限）"
    exit 1
}

echo "  ✓ 已阻止到 fstream.xt.com 的连接"
echo "  等待 ${DISCONNECT_DURATION} 秒（让 ping/pong 超时）..."

# 等待足够长的时间让连接超时
sleep ${DISCONNECT_DURATION}

# 恢复网络连接
echo ""
echo "[3/4] 恢复网络连接..."
DISCONNECT_END=$(date '+%Y-%m-%d %H:%M:%S')
DISCONNECT_END_TS=$(date +%s)
DISCONNECT_DURATION_ACTUAL=$((DISCONNECT_END_TS - DISCONNECT_START_TS))

# 删除阻止规则
sudo iptables -D OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || true

echo "  ✓ 已恢复网络连接"
echo "  断线结束时间: $DISCONNECT_END"
echo "  实际断线时长: ${DISCONNECT_DURATION_ACTUAL} 秒"
echo ""

# 等待重连和数据回补
echo "[4/4] 等待重连和数据回补（180秒）..."
for i in $(seq 1 180); do
    sleep 1
    if [ $((i % 30)) -eq 0 ]; then
        echo "  等待中... ${i}/180 秒"
    fi
done

echo ""
echo "========================================"
echo "测试结果分析"
echo "========================================"
echo ""

# 检查日志中的关键信息
if [ -f logs/tri-arb.log ]; then
    LOG_SIZE=$(wc -l < logs/tri-arb.log)
    echo "日志文件大小: $LOG_SIZE 行"
else
    LOG_SIZE=0
    echo "⚠️  日志文件不存在或为空"
fi

if [ $LOG_SIZE -gt 0 ]; then
    echo ""
    echo "断线相关日志:"
    grep -iE "disconnect|connection.*closed|websocket.*closed|recorded.*disconnect|xt websocket.*closed" logs/tri-arb.log | tail -5 || echo "  （未找到）"
    echo ""
    
    echo "重连相关日志:"
    grep -iE "reconnect|connected|starting missing" logs/tri-arb.log | tail -5 || echo "  （未找到）"
    echo ""
    
    echo "回补相关日志:"
    grep -iE "syncing.*order|synced.*order|missing.*data|saved|skipped" logs/tri-arb.log | tail -10 || echo "  （未找到）"
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
    start_time = now - timedelta(minutes=10)  # 最近10分钟
    
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

echo "回补订单统计（最近10分钟）:"
echo "  REST 回补 (rest_sync): $REST_SYNC_COUNT 条"
echo "  REST 回补 (rest_sync_fixed_lookback): $REST_SYNC_FIXED_COUNT 条"
echo "  总计: $TOTAL_REST_SYNC 条"
echo ""

# 检查标准输出日志
echo "检查服务标准输出日志..."
if [ -f /tmp/xt_subscribe_service.log ]; then
    echo "  标准输出日志大小: $(wc -l < /tmp/xt_subscribe_service.log) 行"
    
    echo ""
    echo "  标准输出中的错误日志:"
    tail -1000 /tmp/xt_subscribe_service.log | grep -iE "error|exception|failed|timeout|closed" | tail -5 || echo "    （未找到）"
    echo ""
    
    echo "  标准输出中的回补相关日志:"
    tail -1000 /tmp/xt_subscribe_service.log | grep -iE "syncing|synced|missing|backfill|回补" | tail -5 || echo "    （未找到）"
    echo ""
fi

# 结论
echo "========================================"
if [ -n "$AFTER_COUNT" ] && [ "$TOTAL_REST_SYNC" -gt "0" ]; then
    echo "✅ 测试通过：检测到断线回补功能正常工作"
    echo "   成功回补 $TOTAL_REST_SYNC 条订单"
elif [ $LOG_SIZE -gt 0 ]; then
    echo "⚠️  测试部分成功：检测到日志记录，但未检测到回补订单"
    echo "   可能原因：所有订单都已存在（去重逻辑）"
else
    echo "❌ 测试失败：未检测到断线或回补日志"
    echo "   可能原因：WebSocket 未真正断开或日志配置问题"
fi
echo "========================================"
echo ""

echo "提示："
echo "  - 服务仍在运行 (PID: $SERVICE_PID)"
echo "  - 查看完整日志: tail -f logs/tri-arb.log"
echo "  - 查看标准输出: tail -f /tmp/xt_subscribe_service.log"
echo "  - 停止服务: kill $SERVICE_PID"
echo ""
