"""Account management commands."""

import asyncio
import datetime
import logging
from decimal import Decimal
from typing import Optional

import typer
from rich.console import Console

from tri_arb.cli.utils.exchange_factory import ExchangeType, ExchangeName, create_exchange
from tri_arb.cli.formatters.table import format_balance_table, format_positions_table, format_open_orders_table
from tri_arb.cli.formatters.json import print_json
from tri_arb.cli.formatters.csv import print_csv
from tri_arb.cli.utils.validators import validate_symbol
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.models import BinanceAccountBalance
from tri_arb.storage.okx_models import OKXAccountBalance
from tri_arb.storage.gate_models import GateAccountBalance
import json

app = typer.Typer(help="账户管理命令")
console = Console()
logger = logging.getLogger(__name__)

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
            format_balance_table(balances,exchange_instance)

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
            # 标准化symbol格式用于匹配（移除斜杠、横杠、下划线并转大写）
            normalized_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
            
            filtered_positions = []
            for pos in positions_list:
                if isinstance(pos, dict):
                    # OKX格式 (instId: "BTC-USDT-SWAP")
                    if 'instId' in pos:
                        pos_symbol = pos.get("instId", "").replace("-", "").replace("SWAP", "").upper()
                    # Binance格式 (symbol: "BTCUSDT")
                    else:
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
                    # Check if it's OKX format or Binance format
                    if 'instId' in pos:
                        # OKX format
                        symbol = pos.get("instId", "")
                        side = pos.get("posSide", "").capitalize()
                        quantity = abs(pos.get("pos", Decimal('0')))
                        entry_price = pos.get("avgPx", Decimal('0'))
                        current_price = pos.get("markPx", Decimal('0'))
                        unrealized_pnl = pos.get("upl", Decimal('0'))
                        roe = pos.get("uplRatio", Decimal('0')) * 100
                        leverage = pos.get("lever", "1")
                    else:
                        # Binance dict format (V2 API)
                        symbol = pos.get("symbol", "")
                        side = "Long" if pos.get("positionAmt", Decimal('0')) > 0 else "Short"
                        quantity = abs(pos.get("positionAmt", Decimal('0')))
                        entry_price = pos.get("entryPrice", Decimal('0'))
                        current_price = pos.get("markPrice", Decimal('0'))
                        unrealized_pnl = pos.get("unRealizedProfit", Decimal('0'))
                        leverage = pos.get("leverage", "1")
                        
                        # Calculate ROE: use notional/leverage to get margin
                        notional = abs(pos.get("notional", Decimal('0')))
                        leverage_num = Decimal(leverage) if leverage else Decimal('1')
                        margin = notional / leverage_num if leverage_num > 0 and notional > 0 else Decimal('0')
                        roe = (unrealized_pnl / margin * 100) if margin > 0 else Decimal('0')
                    
                    csv_data.append({
                        "symbol": symbol,
                        "side": side,
                        "quantity": str(quantity),
                        "entry_price": str(entry_price),
                        "current_price": str(current_price),
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


@app.command("orders")
def orders(
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
    """查询当前挂单（仅永续合约）.
    
    示例:
        cextools account orders -e perp
        cextools account orders -e perp --symbol BTC/USDT
        cextools account orders -e perp -o json
        cextools account orders -e perp --exchange binance
    """
    try:
        # 验证 exchange_type
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] orders 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        # 验证 symbol 格式（如果提供）
        if symbol:
            symbol = validate_symbol(symbol)

        # 创建 exchange 实例
        exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange)

        # 异步获取挂单
        async def get_orders():
            await exchange_instance.connect()
            try:
                # 始终获取所有挂单，然后在本地筛选
                orders_data = await exchange_instance.get_open_orders(None)
                return orders_data
            finally:
                await exchange_instance.disconnect()

        orders_list = asyncio.run(get_orders())

        # 如果指定了symbol，在本地筛选
        if symbol:
            # 标准化symbol格式用于匹配（移除斜杠、横杠、下划线并转大写）
            normalized_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
            filtered_orders = []
            for order in orders_list:
                # Gate.io格式 (contract: "BTC_USDT")
                if 'contract' in order and 'instId' not in order:
                    order_symbol = order.get("contract", "").replace("_", "").upper()
                    
                # OKX格式 (instId: "BTC-USDT-SWAP")
                elif 'instId' in order:
                    order_symbol = order.get("instId", "").replace("-", "").replace("SWAP", "").upper()
                    
                # Binance格式 (symbol: "BTCUSDT")
                else:
                    order_symbol = order.get("symbol", "").upper()

                if order_symbol == normalized_symbol:
                    filtered_orders.append(order)
            
            orders_list = filtered_orders

        if not orders_list:
            if symbol:
                console.print(f"[yellow]未发现 {symbol} 的挂单[/yellow]")
            else:
                console.print("[yellow]未发现挂单[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(orders_list)
        elif output == "csv":
            # 转换为字典列表供 CSV 使用，支持Gate.io、OKX和Binance格式
            csv_data = []
            for order in orders_list:
                if 'contract' in order and 'instId' not in order:
                    # Gate.io format
                    size = order.get("size", 0)
                    left = order.get("left", 0)
                    filled = size - left if isinstance(size, (int, float)) and isinstance(left, (int, float)) else 0
                    csv_data.append({
                        "order_id": str(order.get("id", "")),
                        "symbol": order.get("contract", ""),
                        "side": order.get("side", ""),
                        "type": order.get("tif", ""),
                        "price": str(order.get("price", 0)),
                        "quantity": str(size),
                        "filled": str(filled),
                        "status": order.get("status", ""),
                        "time": str(order.get("create_time", 0))
                    })
                elif 'instId' in order:
                    # OKX format
                    csv_data.append({
                        "order_id": order.get("ordId", ""),
                        "symbol": order.get("instId", ""),
                        "side": order.get("side", ""),
                        "type": order.get("ordType", ""),
                        "price": str(order.get("px", 0)),
                        "quantity": str(order.get("sz", 0)),
                        "filled": str(order.get("accFillSz", 0)),
                        "status": order.get("state", ""),
                        "time": str(order.get("cTime", 0))
                    })
                else:
                    # Binance format
                    csv_data.append({
                        "order_id": str(order.get("orderId", "")),
                        "symbol": order.get("symbol", ""),
                        "side": order.get("side", ""),
                        "type": order.get("type", ""),
                        "price": str(order.get("price", 0)),
                        "quantity": str(order.get("origQty", 0)),
                        "filled": str(order.get("executedQty", 0)),
                        "status": order.get("status", ""),
                        "time": str(order.get("time", 0))
                    })
            print_csv(csv_data)
        else:  # table (default)
            format_open_orders_table(orders_list, exchange_instance)

    except ValueError as e:
        console.print(f"[red]参数错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("watch-balance")
def watch_balance(
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
        help="交易所 (xt, binance, okx, gate)，默认 xt"
    ),
    interval: int = typer.Option(
        1,
        "--interval",
        "-i",
        help="查询间隔（分钟），默认1分钟"
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
        help="输出格式 (table, json)"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    )
):
    """定时查询账户余额.
    
    每隔指定分钟查询一次余额，持续监控账户变化。
    按 Ctrl+C 停止监控。
    
    示例:
        # 每1分钟查询一次余额
        cextools account watch-balance -e perp
        
        # 每5分钟查询一次Binance余额
        cextools account watch-balance -x binance -e perp --interval 5
        
        # 每10分钟查询一次OKX余额
        cextools account watch-balance -x okx -e perp -i 10
    """
    try:
        # 验证间隔时间
        if interval < 1:
            raise ValueError("查询间隔必须至少为1分钟")
        
        # 创建 exchange 实例
        exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange)
        
        console.print(f"[cyan]开始监控 {exchange.value.upper()} {exchange_type.value.upper()} 账户余额[/cyan]")
        console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
        console.print(f"[yellow]按 Ctrl+C 停止监控[/yellow]\n")
        
        # 定时查询函数
        async def watch_loop():
            iteration = 0
            try:
                await exchange_instance.connect()
                
                while True:
                    iteration += 1
                    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    console.print(f"\n{'='*60}")
                    console.print(f"[bold]第 {iteration} 次查询 - {current_time}[/bold]")
                    console.print(f"{'='*60}\n")
                    
                    try:
                        # 查询余额
                        balance_data = await exchange_instance.get_balance()
                        
                        if not balance_data:
                            console.print("[yellow]账户余额为空或所有币种余额为0[/yellow]")
                        else:
                            # 根据输出格式显示
                            if output == "json":
                                print_json(balance_data)
                            else:  # table (default)
                                format_balance_table(balance_data,exchange_instance)

                            # 保存到数据库（Binance/OKX/Gate 每个交易所一张表）
                            try:
                                db_manager = DatabaseManager()
                                now = datetime.datetime.utcnow()
                                # 标准化余额数据: {currency: {available, frozen, total, raw}}
                                for currency, data in balance_data.items():
                                    available = Decimal(str(data.get("available", 0)))
                                    frozen = Decimal(str(data.get("frozen", 0)))
                                    total = Decimal(str(data.get("total", 0)))
                                    raw_json = json.dumps(data)

                                    async with db_manager.session() as session:
                                        if exchange == ExchangeName.BINANCE:
                                            record = BinanceAccountBalance(
                                                update_time=now,
                                                asset=currency.upper(),
                                                free=available,
                                                locked=frozen,
                                                total=total,
                                                raw_data=raw_json,
                                            )
                                        elif exchange == ExchangeName.OKX:
                                            record = OKXAccountBalance(
                                                update_time=now,
                                                currency=currency.upper(),
                                                available_bal=available,
                                                frozen_bal=frozen,
                                                equity=total,
                                                raw_data=raw_json,
                                            )
                                        elif exchange == ExchangeName.GATE:
                                            record = GateAccountBalance(
                                                update_time=now,
                                                currency=currency.upper(),
                                                available=available,
                                                total=total,
                                                raw_data=raw_json,
                                            )
                                        else:
                                            record = None

                                        if record is not None:
                                            session.add(record)
                                # 提交由 session ctx 管理
                            except Exception as save_exc:
                                logger.warning(f"保存余额到数据库失败: {save_exc}")
                        
                        # 显示下次查询时间
                        next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval)
                        console.print(f"\n[dim]下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
                        
                    except Exception as e:
                        console.print(f"[red]查询失败:[/red] {e}")
                        if debug:
                            console.print_exception()
                    
                    # 等待指定分钟数（转换为秒）
                    console.print(f"[dim]等待 {interval} 分钟...[/dim]")
                    await asyncio.sleep(interval * 60)
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]监控已停止[/yellow]")
            finally:
                await exchange_instance.disconnect()
        
        # 运行监控循环
        asyncio.run(watch_loop())
        
    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
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


@app.command("watch-positions")
def watch_positions(
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
        help="交易所 (xt, binance, okx, gate)，默认 xt"
    ),
    symbol: Optional[str] = typer.Option(
        None,
        "--symbol",
        "-s",
        help="交易对（例如 BTC/USDT），不指定则显示所有"
    ),
    interval: int = typer.Option(
        1,
        "--interval",
        "-i",
        help="查询间隔（分钟），默认1分钟"
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
        help="输出格式 (table, json)"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    )
):
    """定时查询持仓（仅永续合约）.
    
    每隔指定分钟查询一次持仓，持续监控持仓变化。
    按 Ctrl+C 停止监控。
    
    示例:
        # 每1分钟查询一次所有持仓
        cextools account watch-positions -e perp
        
        # 每2分钟查询Binance的BTC持仓
        cextools account watch-positions -x binance -e perp -s BTC/USDT --interval 2
        
        # 每5分钟查询Gate.io的所有持仓
        cextools account watch-positions -x gate -e perp -i 5
    """
    try:
        # 验证 exchange_type
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] watch-positions 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        # 验证间隔时间
        if interval < 1:
            raise ValueError("查询间隔必须至少为1分钟")

        # 验证 symbol 格式（如果提供）
        if symbol:
            symbol = validate_symbol(symbol)

        # 创建 exchange 实例
        exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange)

        symbol_text = f"的 {symbol} " if symbol else ""
        console.print(f"[cyan]开始监控 {exchange.value.upper()} 永续合约{symbol_text}持仓[/cyan]")
        console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
        console.print(f"[yellow]按 Ctrl+C 停止监控[/yellow]\n")

        # 定时查询函数
        async def watch_loop():
            iteration = 0
            try:
                await exchange_instance.connect()
                
                while True:
                    iteration += 1
                    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    console.print(f"\n{'='*60}")
                    console.print(f"[bold]第 {iteration} 次查询 - {current_time}[/bold]")
                    console.print(f"{'='*60}\n")
                    
                    try:
                        # 始终获取所有持仓，然后在本地筛选
                        positions_data = await exchange_instance.get_positions(None)
                        
                        # 如果指定了symbol，在本地筛选
                        if symbol:
                            # 标准化symbol格式用于匹配（移除斜杠、横杠、下划线并转大写）
                            normalized_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
                            
                            filtered_positions = []
                            for pos in positions_data:
                                if isinstance(pos, dict):
                                    # Gate.io格式 (contract: "BTC_USDT")
                                    if 'contract' in pos and 'instId' not in pos:
                                        pos_symbol = pos.get("contract", "").replace("_", "").upper()
                                    # OKX格式 (instId: "BTC-USDT-SWAP")
                                    elif 'instId' in pos:
                                        pos_symbol = pos.get("instId", "").replace("-", "").replace("SWAP", "").upper()
                                    # Binance格式 (symbol: "BTCUSDT")
                                    else:
                                        pos_symbol = pos.get("symbol", "").upper()
                                else:
                                    # XT格式，可能是 "btc_usdt" 或 "BTC/USDT"
                                    pos_symbol = pos.symbol.replace("/", "").replace("_", "").upper()
                                
                                if pos_symbol == normalized_symbol:
                                    filtered_positions.append(pos)
                            
                            positions_data = filtered_positions
                        
                        # 显示结果
                        if not positions_data:
                            if symbol:
                                console.print(f"[yellow]未发现 {symbol} 的持仓[/yellow]")
                            else:
                                console.print("[yellow]未发现持仓[/yellow]")
                        else:
                            # 根据输出格式显示
                            if output == "json":
                                print_json(positions_data)
                            else:  # table (default)
                                format_positions_table(positions_data, exchange_instance)
                        
                        # 显示统计信息
                        if positions_data:
                            total_positions = len(positions_data)
                            long_positions = 0
                            short_positions = 0
                            
                            for pos in positions_data:
                                if isinstance(pos, dict):
                                    # Gate.io格式
                                    if 'contract' in pos and 'instId' not in pos:
                                        size = pos.get("size", 0)
                                        if size > 0:
                                            long_positions += 1
                                        elif size < 0:
                                            short_positions += 1
                                    # OKX格式
                                    elif 'instId' in pos:
                                        pos_side = pos.get("posSide", "")
                                        if pos_side == "long":
                                            long_positions += 1
                                        elif pos_side == "short":
                                            short_positions += 1
                                    # Binance格式
                                    else:
                                        pos_amt = pos.get("positionAmt", 0)
                                        if pos_amt > 0:
                                            long_positions += 1
                                        elif pos_amt < 0:
                                            short_positions += 1
                                else:
                                    # XT格式
                                    if hasattr(pos, 'side'):
                                        if pos.side.lower() == 'long':
                                            long_positions += 1
                                        elif pos.side.lower() == 'short':
                                            short_positions += 1
                            
                            console.print(f"\n[dim]统计: 共 {total_positions} 个持仓 (多头: {long_positions}, 空头: {short_positions})[/dim]")
                        
                        # 显示下次查询时间
                        next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval)
                        console.print(f"[dim]下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
                        
                    except Exception as e:
                        console.print(f"[red]查询失败:[/red] {e}")
                        if debug:
                            console.print_exception()
                    
                    # 等待指定分钟数（转换为秒）
                    console.print(f"[dim]等待 {interval} 分钟...[/dim]")
                    await asyncio.sleep(interval * 60)
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]监控已停止[/yellow]")
            finally:
                await exchange_instance.disconnect()
        
        # 运行监控循环
        asyncio.run(watch_loop())
        
    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
    except ValueError as e:
        console.print(f"[red]参数错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("watch-orders")
def watch_orders(
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
        help="交易所 (xt, binance, okx, gate)，默认 xt"
    ),
    symbol: Optional[str] = typer.Option(
        None,
        "--symbol",
        "-s",
        help="交易对（例如 BTC/USDT），不指定则显示所有"
    ),
    interval: int = typer.Option(
        1,
        "--interval",
        "-i",
        help="查询间隔（分钟），默认1分钟"
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
        help="输出格式 (table, json)"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    )
):
    """定时查询挂单（仅永续合约）.
    
    每隔指定分钟查询一次挂单，持续监控订单状态变化。
    按 Ctrl+C 停止监控。
    
    示例:
        # 每1分钟查询一次所有挂单
        cextools account watch-orders -e perp
        
        # 每2分钟查询Binance的BTC挂单
        cextools account watch-orders -x binance -e perp -s BTC/USDT --interval 2
        
        # 每5分钟查询Gate.io的所有挂单
        cextools account watch-orders -x gate -e perp -i 5
    """
    try:
        # 验证 exchange_type
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] watch-orders 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        # 验证间隔时间
        if interval < 1:
            raise ValueError("查询间隔必须至少为1分钟")

        # 验证 symbol 格式（如果提供）
        if symbol:
            symbol = validate_symbol(symbol)

        # 创建 exchange 实例
        exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange)

        symbol_text = f"的 {symbol} " if symbol else ""
        console.print(f"[cyan]开始监控 {exchange.value.upper()} 永续合约{symbol_text}挂单[/cyan]")
        console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
        console.print(f"[yellow]按 Ctrl+C 停止监控[/yellow]\n")

        # 定时查询函数
        async def watch_loop():
            iteration = 0
            try:
                await exchange_instance.connect()
                
                while True:
                    iteration += 1
                    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    console.print(f"\n{'='*60}")
                    console.print(f"[bold]第 {iteration} 次查询 - {current_time}[/bold]")
                    console.print(f"{'='*60}\n")
                    
                    try:
                        # 始终获取所有挂单，然后在本地筛选
                        orders_data = await exchange_instance.get_open_orders(None)
                        
                        # 如果指定了symbol，在本地筛选
                        if symbol:
                            # 标准化symbol格式用于匹配（移除斜杠、横杠、下划线并转大写）
                            normalized_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
                            
                            filtered_orders = []
                            for order in orders_data:
                                # OKX格式 (instId: "BTC-USDT-SWAP")
                                if 'instId' in order:
                                    order_symbol = order.get("instId", "").replace("-", "").replace("SWAP", "").upper()
                                # Binance格式 (symbol: "BTCUSDT")
                                else:
                                    order_symbol = order.get("symbol", "").upper()
                                
                                if order_symbol == normalized_symbol:
                                    filtered_orders.append(order)
                            
                            orders_data = filtered_orders
                        
                        # 显示结果
                        if not orders_data:
                            if symbol:
                                console.print(f"[yellow]未发现 {symbol} 的挂单[/yellow]")
                            else:
                                console.print("[yellow]未发现挂单[/yellow]")
                        else:
                            # 根据输出格式显示
                            if output == "json":
                                print_json(orders_data)
                            else:  # table (default)
                                format_open_orders_table(orders_data, exchange_instance)
                        
                        # 显示统计信息
                        if orders_data:
                            total_orders = len(orders_data)
                            buy_orders = sum(1 for o in orders_data if o.get('side', '').upper() == 'BUY' or o.get('side', '').lower() == 'buy')
                            sell_orders = total_orders - buy_orders
                            console.print(f"\n[dim]统计: 共 {total_orders} 个挂单 (买单: {buy_orders}, 卖单: {sell_orders})[/dim]")
                        
                        # 显示下次查询时间
                        next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval)
                        console.print(f"[dim]下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
                        
                    except Exception as e:
                        console.print(f"[red]查询失败:[/red] {e}")
                        if debug:
                            console.print_exception()
                    
                    # 等待指定分钟数（转换为秒）
                    console.print(f"[dim]等待 {interval} 分钟...[/dim]")
                    await asyncio.sleep(interval * 60)
                    
            except KeyboardInterrupt:
                console.print("\n[yellow]监控已停止[/yellow]")
            finally:
                await exchange_instance.disconnect()
        
        # 运行监控循环
        asyncio.run(watch_loop())
        
    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
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

