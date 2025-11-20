#!/bin/bash
# 通过 kill 并重启服务来触发回补测试

set -e

echo "========================================"
echo "XT WebSocket 重启回补功能测试"
echo "========================================"
echo ""
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "测试方式: 记录断线时间 -> kill 进程 -> 重启服务 -> 检查回补"
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

# 找到并 kill 服务进程
echo "[2/4] 停止服务（模拟断线）..."
SERVICE_PID=$(pgrep -f "cextools subscribe multi-account" | head -1)
if [ -n "$SERVICE_PID" ]; then
    echo "  找到服务进程 (PID: $SERVICE_PID)"
    echo "  正在停止服务..."
    kill $SERVICE_PID
    sleep 5
    echo "  ✓ 服务已停止"
else
    echo "  ⚠️  未找到运行中的服务"
fi

# 等待一段时间（模拟断线期间）
DISCONNECT_DURATION=30
echo ""
echo "  模拟断线期间（${DISCONNECT_DURATION}秒）..."
sleep ${DISCONNECT_DURATION}

DISCONNECT_END=$(date '+%Y-%m-%d %H:%M:%S')
DISCONNECT_END_TS=$(date +%s)
DISCONNECT_DURATION_ACTUAL=$((DISCONNECT_END_TS - DISCONNECT_START_TS))

echo "  断线结束时间: $DISCONNECT_END"
echo "  实际断线时长: ${DISCONNECT_DURATION_ACTUAL} 秒"
echo ""

# 重启服务
echo "[3/4] 重启服务（触发回补）..."
export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading"
export PROM_METRICS_PORT=9601
source .venv/bin/activate
nohup /home/ubuntu/quant/.venv/bin/cextools subscribe multi-account --config config/accounts.json > /tmp/xt_subscribe_service.log 2>&1 &

sleep 15
NEW_PID=$(pgrep -f "cextools subscribe multi-account" | head -1)
if [ -n "$NEW_PID" ]; then
    echo "  ✓ 服务已重启 (新 PID: $NEW_PID)"
else
    echo "  ❌ 服务启动失败"
    exit 1
fi

# 等待重连和数据回补
echo ""
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

# 检查日志
if [ -f logs/tri-arb.log ]; then
    LOG_SIZE=$(wc -l < logs/tri-arb.log)
    echo "日志文件大小: $LOG_SIZE 行"
    
    if [ $LOG_SIZE -gt 0 ]; then
        echo ""
        echo "回补相关日志:"
        grep -iE "syncing|synced|missing|backfill|回补|rest_sync" logs/tri-arb.log | tail -10 || echo "  （未找到）"
        echo ""
    fi
else
    LOG_SIZE=0
    echo "⚠️  日志文件不存在"
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
    start_time = now - timedelta(minutes=10)
    
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
    echo "   日志文件大小: $LOG_SIZE 行"
fi
echo "========================================"
echo ""
