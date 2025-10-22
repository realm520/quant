#!/bin/bash

# 选择性频道订阅示例脚本

echo "================================================"
echo "  WebSocket选择性频道订阅示例"
echo "================================================"
echo ""

# 检查环境变量
if [ -z "$BINANCE_API_KEY" ] || [ -z "$OKX_API_KEY" ]; then
    echo "⚠️  请先设置环境变量:"
    echo "  export BINANCE_API_KEY='...'"
    echo "  export BINANCE_API_SECRET='...'"
    echo "  export OKX_API_KEY='...'"
    echo "  export OKX_API_SECRET='...'"
    echo "  export OKX_PASSPHRASE='...'"
    echo "  export DATABASE_URL='postgresql+asyncpg://postgres@localhost:5432/trading'"
    echo ""
    exit 1
fi

echo "选择示例:"
echo "  1. Binance - 只订阅账户"
echo "  2. Binance - 只订阅订单"
echo "  3. Binance - 账户+订单"
echo "  4. OKX - 只订阅账户"
echo "  5. OKX - 只订阅持仓"
echo "  6. OKX - 只订阅订单"
echo "  7. OKX - 账户+持仓"
echo "  8. OKX - 持仓+订单"
echo "  9. OKX - 全部"
echo ""

read -p "请选择 (1-9): " choice

case $choice in
    1)
        echo "启动: Binance - 只订阅账户"
        cextools subscribe user-stream -x binance -c account -o table
        ;;
    2)
        echo "启动: Binance - 只订阅订单"
        cextools subscribe user-stream -x binance -c order -o table
        ;;
    3)
        echo "启动: Binance - 账户+订单"
        cextools subscribe user-stream -x binance -c account,order -o table
        ;;
    4)
        echo "启动: OKX - 只订阅账户"
        cextools subscribe user-stream -x okx -c account -o table
        ;;
    5)
        echo "启动: OKX - 只订阅持仓"
        cextools subscribe user-stream -x okx -c position -o table
        ;;
    6)
        echo "启动: OKX - 只订阅订单"
        cextools subscribe user-stream -x okx -c order -o table
        ;;
    7)
        echo "启动: OKX - 账户+持仓"
        cextools subscribe user-stream -x okx -c account,position -o table
        ;;
    8)
        echo "启动: OKX - 持仓+订单"
        cextools subscribe user-stream -x okx -c position,order -o table
        ;;
    9)
        echo "启动: OKX - 全部频道"
        cextools subscribe user-stream -x okx -o table
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac

