#!/bin/bash
# load_env.sh - 加载环境变量脚本（支持所有交易所）

# 检查 .env 文件是否存在
if [ ! -f ".env" ]; then
    echo "❌ 错误: .env 文件不存在"
    echo "请确保 .env 文件在当前目录中"
    exit 1
fi

# 加载环境变量
echo "🔄 正在加载环境变量..."
set -a
source .env
set +a

# 验证关键环境变量
echo "✅ 环境变量加载完成"
echo "📊 验证交易所API密钥:"

# Binance
if [ -n "$BINANCE_API_KEY" ]; then
    echo "  ✅ BINANCE_API_KEY: ${BINANCE_API_KEY:0:8}..."
else
    echo "  ❌ BINANCE_API_KEY: 未设置"
fi

if [ -n "$BINANCE_API_SECRET" ]; then
    echo "  ✅ BINANCE_API_SECRET: ${BINANCE_API_SECRET:0:8}..."
else
    echo "  ❌ BINANCE_API_SECRET: 未设置"
fi

# OKX
if [ -n "$OKX_API_KEY" ]; then
    echo "  ✅ OKX_API_KEY: ${OKX_API_KEY:0:8}..."
else
    echo "  ❌ OKX_API_KEY: 未设置"
fi

if [ -n "$OKX_API_SECRET" ]; then
    echo "  ✅ OKX_API_SECRET: ${OKX_API_SECRET:0:8}..."
else
    echo "  ❌ OKX_API_SECRET: 未设置"
fi

if [ -n "$OKX_PASSPHRASE" ]; then
    echo "  ✅ OKX_PASSPHRASE: ${OKX_PASSPHRASE:0:8}..."
else
    echo "  ❌ OKX_PASSPHRASE: 未设置"
fi

# Gate.io
if [ -n "$GATE_API_KEY" ]; then
    echo "  ✅ GATE_API_KEY: ${GATE_API_KEY:0:8}..."
else
    echo "  ❌ GATE_API_KEY: 未设置"
fi

if [ -n "$GATE_API_SECRET" ]; then
    echo "  ✅ GATE_API_SECRET: ${GATE_API_SECRET:0:8}..."
else
    echo "  ❌ GATE_API_SECRET: 未设置"
fi

# XT
if [ -n "$XT_API_KEY" ]; then
    echo "  ✅ XT_API_KEY: ${XT_API_KEY:0:8}..."
else
    echo "  ❌ XT_API_KEY: 未设置"
fi

if [ -n "$XT_API_SECRET" ]; then
    echo "  ✅ XT_API_SECRET: ${XT_API_SECRET:0:8}..."
else
    echo "  ❌ XT_API_SECRET: 未设置"
fi

# 数据库配置
echo ""
echo "🗄️  数据库配置:"
if [ -n "$DATABASE_URL" ]; then
    echo "  ✅ DATABASE_URL: $DATABASE_URL"
else
    echo "  ❌ DATABASE_URL: 未设置"
fi

echo ""
echo "💡 使用方法:"
echo "  source load_env.sh    # 加载环境变量"
echo "  ./load_env.sh         # 或者直接运行脚本"
echo ""
echo "🚀 支持的交易所WebSocket订阅:"
echo "  python -m tri_arb.cli.main subscribe user-stream -x binance  # 币安"
echo "  python -m tri_arb.cli.main subscribe user-stream -x okx       # OKX"
echo "  python -m tri_arb.cli.main subscribe user-stream -x gate     # Gate.io"
echo "  python -m tri_arb.cli.main subscribe user-stream -x xt        # XT"
echo ""
echo "🚀 支持的交易所REST API查询:"
echo "  cextools account balance -x binance  # 币安余额查询"
echo "  cextools account balance -x okx      # OKX余额查询"
echo "  cextools account balance -x gate     # Gate.io余额查询"
echo "  cextools account balance -x xt        # XT余额查询"

