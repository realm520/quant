#!/bin/bash
# 测试 WebSocket 数据流，运行 3 分钟
cd /home/ubuntu/quant
source .venv/bin/activate

echo "=========================================="
echo "开始监听 XT WebSocket 数据流"
echo "运行时长: 3 分钟"
echo "按 Ctrl+C 随时停止"
echo "=========================================="

timeout 180 python -m tri_arb.cli.main subscribe multi-account \
    --config config/accounts_test.json \
    --output table \
    2>&1 | grep -E "(消息类型|ACCT:|POS:|ORDER:|TRADE:|收到.*条消息|账号.*开始订阅|Connected|Subscribed|RAW MESSAGE)" | head -100

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
