"""CEXTools - Unified CLI tool for XT Exchange (Spot & Perpetual Futures).

统一的 XT 交易所 CLI 工具，支持现货和永续合约交易。

使用示例:
    # 查询现货余额
    cextools account balance --exchange-type spot

    # 查询永续合约持仓
    cextools account positions -e perp

    # 查看实时价格
    cextools market ticker --symbol BTC/USDT

    # 提交限价买单（现货）
    cextools order place -s BTC/USDT --side buy -q 0.001 -e spot -p 50000

    # 设置杠杆（永续合约）
    cextools leverage set -s BTC/USDT -l 10 -e perp
"""

import typer
from rich.console import Console

from tri_arb.cli.commands import account, market, order, leverage

# 主应用
app = typer.Typer(
    name="cextools",
    help="XT 交易所统一 CLI 工具 - 支持现货和永续合约交易",
    add_completion=False,
    no_args_is_help=True,
)

# 注册命令组
app.add_typer(account.app, name="account", help="账户管理")
app.add_typer(market.app, name="market", help="市场行情")
app.add_typer(order.app, name="order", help="订单管理")
app.add_typer(leverage.app, name="leverage", help="杠杆管理（仅永续合约）")

# 添加subscribe命令组（WebSocket订阅）
try:
    from tri_arb.cli.commands import subscribe

    app.add_typer(subscribe.app, name="subscribe", help="WebSocket订阅（Binance）")
except ImportError as e:
    import sys

    print(f"Warning: subscribe command not available: {e}", file=sys.stderr)
except Exception as e:
    import sys

    print(f"Error loading subscribe command: {e}", file=sys.stderr)

# 添加trading-monitor命令组（交易指标监控）
try:
    from tri_arb.cli.commands import position_metrics

    app.add_typer(position_metrics.app, name="trading-monitor", help="交易指标监控服务")
except ImportError as e:
    import sys

    print(f"Warning: trading-monitor command not available: {e}", file=sys.stderr)
except Exception as e:
    import sys

    print(f"Error loading trading-monitor command: {e}", file=sys.stderr)

console = Console()


@app.command()
def version():
    """显示版本信息."""
    console.print("[cyan]CEXTools v1.0.0[/cyan]")
    console.print("XT 交易所统一 CLI 工具")
    console.print("\n[bold]支持的交易类型:[/bold]")
    console.print("  • spot (现货)")
    console.print("  • perp (永续合约)")
    console.print("\n[bold]命令组:[/bold]")
    console.print("  • account - 账户管理")
    console.print("  • market  - 市场行情")
    console.print("  • order   - 订单管理")
    console.print("  • leverage - 杠杆管理")


def main():
    """CLI 入口点."""
    app()


if __name__ == "__main__":
    main()
