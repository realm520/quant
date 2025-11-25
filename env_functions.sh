# 环境变量加载函数（支持所有交易所）
load_env() {
    if [ -f ".env" ]; then
        echo "🔄 加载 .env 文件..."
        set -a
        source .env
        set +a
        echo "✅ 环境变量加载完成"
        
        # 显示所有交易所的API密钥
        echo "📊 交易所API密钥:"
        
        # Binance
        [ -n "$BINANCE_API_KEY" ] && echo "  ✅ BINANCE_API_KEY: ${BINANCE_API_KEY:0:8}..."
        [ -n "$BINANCE_API_SECRET" ] && echo "  ✅ BINANCE_API_SECRET: ${BINANCE_API_SECRET:0:8}..."
        
        # OKX
        [ -n "$OKX_API_KEY" ] && echo "  ✅ OKX_API_KEY: ${OKX_API_KEY:0:8}..."
        [ -n "$OKX_API_SECRET" ] && echo "  ✅ OKX_API_SECRET: ${OKX_API_SECRET:0:8}..."
        [ -n "$OKX_PASSPHRASE" ] && echo "  ✅ OKX_PASSPHRASE: ${OKX_PASSPHRASE:0:8}..."
        
        # Gate.io
        [ -n "$GATE_API_KEY" ] && echo "  ✅ GATE_API_KEY: ${GATE_API_KEY:0:8}..."
        [ -n "$GATE_API_SECRET" ] && echo "  ✅ GATE_API_SECRET: ${GATE_API_SECRET:0:8}..."
        
        # XT
        [ -n "$XT_API_KEY" ] && echo "  ✅ XT_API_KEY: ${XT_API_KEY:0:8}..."
        [ -n "$XT_API_SECRET" ] && echo "  ✅ XT_API_SECRET: ${XT_API_SECRET:0:8}..."
        
        # 数据库配置
        echo "🗄️  数据库配置:"
        [ -n "$DATABASE_URL" ] && echo "  ✅ DATABASE_URL: $DATABASE_URL"
        
        echo ""
        echo "🚀 现在可以使用所有交易所功能:"
        echo "  cextools account balance -x binance  # 币安余额查询"
        echo "  cextools account balance -x okx      # OKX余额查询"
        echo "  cextools account balance -x gate     # Gate.io余额查询"
        echo "  cextools account balance -x xt        # XT余额查询"
    else
        echo "❌ .env 文件不存在"
    fi
}

# 别名
alias env_load='load_env'

