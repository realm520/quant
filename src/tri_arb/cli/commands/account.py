"""Account management commands."""

import asyncio
from decimal import Decimal
from typing import Optional

import typer
from rich.console import Console

from tri_arb.cli.utils.exchange_factory import ExchangeType, ExchangeName, create_exchange
from tri_arb.cli.formatters.table import format_balance_table, format_positions_table
from tri_arb.cli.formatters.json import print_json
from tri_arb.cli.formatters.csv import print_csv
from tri_arb.cli.utils.validators import validate_symbol

app = typer.Typer(help="账户管理命令")
console = Console()


@app.command("balance")
def balance(
    exchange_type: ExchangeType = typer.Option(
        ...,
        "--exchange-type",
        "-e",
        help="交易类型 (spot 或 perp)"
    ),
    exchange: ExchangeName = typer.Option(
        ExchangeName.XT,
        "--exchange",
        "-x",
        help="交易所 (xt 或 binance)，默认 xt"
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API 密钥（覆盖环境变量）"
    ),
    api_secret: Optional[str] = typer.Option(
        None,
        "--api-secret",
        help="API 密钥（覆盖环境变量）"
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="输出格式 (table, json, csv)"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    )
):
    """查询账户余额.
    
    示例:
        cextools account balance --exchange-type spot
        cextools account balance -e perp --output json
        cextools account balance -e spot --exchange binance
    """
    try:
        # 创建 exchange 实例
        exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange)

        # 异步获取余额
        async def get_balance():
            await exchange_instance.connect()
            try:
                balance_data = await exchange_instance.get_balance()
                return balance_data
            finally:
                await exchange_instance.disconnect()

        balances = asyncio.run(get_balance())

        # 检查是否有余额数据
        if not balances:
            console.print("[yellow]账户余额为空或所有币种余额为0[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(balances)
        elif output == "csv":
            # 转换为列表格式供 CSV 使用
            balance_list = [
                {
                    "currency": currency,
                    "available": str(data.get("available", 0)),
                    "frozen": str(data.get("frozen", 0)),
                    "total": str(data.get("total", 0))
                }
                for currency, data in balances.items()
            ]
            print_csv(balance_list)
        else:  # table (default)
            format_balance_table(balances)

    except ValueError as e:
        error_msg = str(e) if str(e) else "配置错误，请检查交易所和API凭证"
        console.print(f"[red]配置错误:[/red] {error_msg}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            error_msg = str(e) if str(e) else f"未知错误: {type(e).__name__}"
            console.print(f"[red]错误:[/red] {error_msg}")
        raise typer.Exit(code=1)


@app.command("positions")
def positions(
    exchange_type: ExchangeType = typer.Option(
        ...,
        "--exchange-type",
        "-e",
        help="交易类型（必须为 perp）"
    ),
    exchange: ExchangeName = typer.Option(
        ExchangeName.XT,
        "--exchange",
        "-x",
        help="交易所 (xt 或 binance)，默认 xt"
    ),
    symbol: Optional[str] = typer.Option(
        None,
        "--symbol",
        "-s",
        help="交易对（例如 BTC/USDT），不指定则显示所有"
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API 密钥（覆盖环境变量）"
    ),
    api_secret: Optional[str] = typer.Option(
        None,
        "--api-secret",
        help="API 密钥（覆盖环境变量）"
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="输出格式 (table, json, csv)"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    )
):
    """查询持仓列表（仅永续合约）.
    
    示例:
        cextools account positions -e perp
        cextools account positions -e perp --symbol BTC/USDT
        cextools account positions -e perp -o json
        cextools account positions -e perp --exchange binance
    """
    try:
        # 验证 exchange_type
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] positions 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        # 验证 symbol 格式（如果提供）
        if symbol:
            symbol = validate_symbol(symbol)

        # 创建 exchange 实例
        exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange)

        # 异步获取持仓
        async def get_positions():
            await exchange_instance.connect()
            try:
                # 始终获取所有持仓，然后在本地筛选
                # 这样可以避免不同交易所的symbol格式转换问题
                positions_data = await exchange_instance.get_positions(None)
                return positions_data
            finally:
                await exchange_instance.disconnect()

        positions_list = asyncio.run(get_positions())

        # 如果指定了symbol，在本地筛选
        if symbol:
            # 标准化symbol格式用于匹配（移除斜杠和转大写）
            normalized_symbol = symbol.replace("/", "").replace("_", "").upper()
            
            filtered_positions = []
            for pos in positions_list:
                if isinstance(pos, dict):
                    # 币安格式
                    pos_symbol = pos.get("symbol", "").upper()
                else:
                    # XT格式，可能是 "btc_usdt" 或 "BTC/USDT"
                    pos_symbol = pos.symbol.replace("/", "").replace("_", "").upper()
                
                if pos_symbol == normalized_symbol:
                    filtered_positions.append(pos)
            
            positions_list = filtered_positions

        if not positions_list:
            if symbol:
                console.print(f"[yellow]未发现 {symbol} 的持仓[/yellow]")
            else:
                console.print("[yellow]未发现持仓[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(positions_list)
        elif output == "csv":
            # 转换为字典列表供 CSV 使用，支持两种格式
            csv_data = []
            for pos in positions_list:
                if isinstance(pos, dict):
                    # Binance dict format (V2 API)
                    unrealized_pnl = pos.get("unRealizedProfit", Decimal('0'))
                    leverage = pos.get("leverage", "1")
                    
                    # Calculate ROE: use notional/leverage to get margin
                    notional = abs(pos.get("notional", Decimal('0')))
                    leverage_num = Decimal(leverage) if leverage else Decimal('1')
                    margin = notional / leverage_num if leverage_num > 0 and notional > 0 else Decimal('0')
                    roe = (unrealized_pnl / margin * 100) if margin > 0 else Decimal('0')
                
                    csv_data.append({
                        "symbol": pos.get("symbol", ""),
                        "side": "Long" if pos.get("positionAmt") > 0 else "Short",
                        "quantity": str(abs(pos.get("positionAmt", 0))),
                        "entry_price": str(pos.get("entryPrice", 0)),
                        "current_price": str(pos.get("markPrice", 0)),
                        "pnl": str(unrealized_pnl),
                        "roe": str(roe),
                        "leverage": str(leverage)
                        })
                else:
                    # Position object format (XT)
                    roe = (pos.unrealized_pnl / pos.margin * 100) if hasattr(pos, 'margin') and pos.margin > 0 else Decimal('0')
                    csv_data.append({
                        "symbol": pos.symbol if hasattr(pos, 'symbol') else "",
                        "side": pos.side if hasattr(pos, 'side') else "",
                        "quantity": str(pos.quantity if hasattr(pos, 'quantity') else 0),
                        "entry_price": str(pos.entry_price if hasattr(pos, 'entry_price') else 0),
                        "current_price": str(pos.mark_price if hasattr(pos, 'mark_price') else 0),
                        "pnl": str(pos.unrealized_pnl if hasattr(pos, 'unrealized_pnl') else 0),
                        "roe": str(roe),
                        "leverage": str(pos.leverage if hasattr(pos, 'leverage') else 0)
                    })
            print_csv(csv_data)
        else:  # table (default)
            format_positions_table(positions_list,exchange_instance)

    except ValueError as e:
        console.print(f"[red]参数错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
