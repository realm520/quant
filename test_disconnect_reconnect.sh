#!/bin/bash
# XT WebSocket 断线重连测试脚本
# 用于手动触发正在运行的服务断线重连

set -e

DISCONNECT_DURATION=${1:-30}  # 默认断线30秒

echo "========================================"
echo "XT WebSocket 断线重连测试"
echo "========================================"
echo ""
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "断线时长: ${DISCONNECT_DURATION} 秒"
echo ""

# 检查服务是否在运行
SERVICE_PID=$(pgrep -f "cextools subscribe multi-account" | head -1)
if [ -z "$SERVICE_PID" ]; then
    echo "❌ 错误：未找到运行中的订阅服务"
    echo "   请先运行: cextools subscribe multi-account --config config/accounts.json"
    exit 1
fi

echo "✓ 找到运行中的服务 (PID: $SERVICE_PID)"
echo ""

# 记录断线前的订单数（可选）
echo "[1/3] 记录断线前的状态..."
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

# 使用 iptables 阻止到 fstream.xt.com 的连接
echo "[2/3] 触发网络断线（${DISCONNECT_DURATION}秒）..."
echo "  断线开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  正在阻止到 fstream.xt.com 的连接..."

# 检查规则是否已存在
if sudo iptables -C OUTPUT -d fstream.xt.com -j DROP 2>/dev/null; then
    echo "  ⚠️  iptables 规则已存在，先删除..."
    sudo iptables -D OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || true
fi

# 添加阻止规则
sudo iptables -A OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || {
    echo "  ❌ 错误：无法添加 iptables 规则（需要 sudo 权限）"
    exit 1
}

echo "  ✓ 已阻止到 fstream.xt.com 的连接"
echo "  等待 ${DISCONNECT_DURATION} 秒..."
sleep ${DISCONNECT_DURATION}

# 恢复网络连接
echo ""
echo "[3/3] 恢复网络连接..."
echo "  断线结束时间: $(date '+%Y-%m-%d %H:%M:%S')"

# 删除阻止规则
sudo iptables -D OUTPUT -d fstream.xt.com -j DROP 2>/dev/null || {
    echo "  ⚠️  清理 iptables 规则失败（可能规则不存在）"
}

echo "  ✓ 已恢复网络连接"
echo ""

# 等待重连和数据回补
echo "等待重连和数据回补（60秒）..."
sleep 60

# 检查回补结果
echo ""
echo "========================================"
echo "测试结果分析"
echo "========================================"
echo ""

AFTER_COUNT=$(export DATABASE_URL="postgresql+asyncpg://postgres@localhost:5432/trading" && export LOG_LEVEL=CRITICAL && source .venv/bin/activate 2>/dev/null && python3 << 'PYTHON_SCRIPT' 2>&1 | grep -E "^[0-9]+$" | tail -1
import asyncio
from datetime import datetime, timedelta
from tri_arb.storage.database import DatabaseManager
from sqlalchemy import text
import json

async def check_backfill():
    db_manager = DatabaseManager()
    now = datetime.utcnow()
    start_time = now - timedelta(hours=1)
    
    total = 0
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
                    total += 1
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

echo "断线回补结果："
echo "  断线时长: ${DISCONNECT_DURATION} 秒"
echo "  断线前订单数: ${BEFORE_COUNT:-N/A} 条"
if [ -n "$AFTER_COUNT" ]; then
    echo "  回补订单统计:"
    echo "    - rest_sync: $REST_SYNC_COUNT 条"
    echo "    - rest_sync_fixed_lookback: $REST_SYNC_FIXED_COUNT 条"
    echo "    - 总计: $TOTAL_REST_SYNC 条"
else
    echo "  回补订单统计: N/A"
fi
echo ""

if [ -n "$AFTER_COUNT" ] && [ "$TOTAL_REST_SYNC" -gt "0" ]; then
    echo "✅ 成功：检测到断线回补功能正常工作"
    echo "   成功回补 $TOTAL_REST_SYNC 条订单"
else
    echo "⚠️  未检测到 REST 回补订单"
    echo "   可能原因："
    echo "     1. 断线期间没有新的订单"
    echo "     2. 所有订单已存在于数据库中（去重）"
    echo "     3. 回补功能未触发"
fi
echo "========================================"
echo ""

echo "提示："
echo "  - 服务仍在运行 (PID: $SERVICE_PID)"
echo "  - 查看服务日志: tail -f logs/tri-arb.log"
echo "  - 停止服务: kill $SERVICE_PID"
echo ""

