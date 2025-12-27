"""Order management commands."""

import asyncio
from typing import Optional
from decimal import Decimal

import typer
from rich.console import Console

from tri_arb.cli.utils.exchange_factory import (
    ExchangeType,
    ExchangeName,
    create_exchange,
)
from tri_arb.cli.formatters.table import format_order_summary
from tri_arb.cli.formatters.json import print_json
from tri_arb.cli.formatters.csv import print_csv
from tri_arb.cli.utils.validators import (
    validate_symbol,
    validate_price,
    validate_quantity,
)

app = typer.Typer(help="订单管理命令")
console = Console()


@app.command("place")
def place(
    symbol: str = typer.Option(..., "--symbol", "-s", help="交易对（例如 BTC/USDT）"),
    side: str = typer.Option(..., "--side", help="订单方向 (buy 或 sell)"),
    quantity: float = typer.Option(..., "--quantity", "-q", help="订单数量"),
    exchange_type: ExchangeType = typer.Option(
        ..., "--exchange-type", "-e", help="交易类型 (spot 或 perp)"
    ),
    order_type: str = typer.Option(
        "limit", "--type", "-t", help="订单类型 (limit 或 market，默认 limit)"
    ),
    price: Optional[float] = typer.Option(
        None, "--price", "-p", help="限价单价格（market 订单不需要）"
    ),
    position_side: Optional[str] = typer.Option(
        None, "--position-side", help="持仓方向（仅 perp，LONG 或 SHORT）"
    ),
    exchange: ExchangeName = typer.Option(
        ExchangeName.XT, "--exchange", "-x", help="交易所 (xt, binance, okx)，默认 xt"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="API 密钥（覆盖环境变量）"
    ),
    api_secret: Optional[str] = typer.Option(
        None, "--api-secret", help="API 密钥（覆盖环境变量）"
    ),
    output: str = typer.Option(
        "table", "--output", "-o", help="输出格式 (table, json, csv)"
    ),
    debug: bool = typer.Option(False, "--debug", help="启用调试模式"),
):
    """提交订单.

    示例:
        # Binance 永续合约限价开多单
        cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 -p 30000 --position-side LONG

        # OKX 永续合约限价开空单
        cextools order place -x okx -e perp -s BTC/USDT --side sell -q 0.001 -p 70000 --position-side SHORT

        # Binance 市价单（会立即成交！）
        cextools order place -x binance -e perp -s BTC/USDT --side buy -q 0.001 --type market --position-side LONG

        # OKX Post-only订单（只做Maker）
        cextools order place -x okx -e perp -s ETH/USDT --side buy -q 0.01 -p 2000 --type post_only --position-side LONG
    """
    try:
        # 验证参数
        symbol = validate_symbol(symbol)
        side = side.upper()
        if side not in ["BUY", "SELL"]:
            raise ValueError(f"订单方向必须是 BUY 或 SELL，收到: {side}")

        order_type = order_type.upper()
        if order_type not in ["LIMIT", "MARKET"]:
            raise ValueError(f"订单类型必须是 LIMIT 或 MARKET，收到: {order_type}")

        quantity = validate_quantity(quantity)

        # 限价单必须提供价格
        if order_type == "LIMIT" and price is None:
            raise ValueError("限价单 (LIMIT) 必须提供 --price 参数")

        if price is not None:
            price = validate_price(price)

        # 永续合约必须提供持仓方向
        if exchange_type == ExchangeType.PERP:
            if position_side is None:
                raise ValueError(
                    "永续合约订单必须提供 --position-side 参数 (LONG 或 SHORT)"
                )
            position_side = position_side.upper()
            if position_side not in ["LONG", "SHORT"]:
                raise ValueError(f"持仓方向必须是 LONG 或 SHORT，收到: {position_side}")

        # 创建 exchange 实例
        exchange_instance = create_exchange(
            exchange_type, api_key, api_secret, exchange
        )

        # 异步提交订单
        async def submit_order():
            await exchange_instance.connect()
            try:
                # 根据交易所类型调整参数
                if exchange == ExchangeName.OKX:
                    # OKX格式转换
                    okx_symbol = (
                        symbol.replace("/", "-") + "-SWAP"
                        if exchange_type == ExchangeType.PERP
                        else symbol.replace("/", "-")
                    )
                    order_result = await exchange_instance.place_order(
                        symbol=okx_symbol,
                        side=side.lower(),  # OKX使用小写
                        order_type=order_type.lower(),
                        quantity=str(quantity),
                        price=str(price) if price else None,
                        position_side=position_side.lower() if position_side else None,
                    )
                elif exchange == ExchangeName.BINANCE:
                    # Binance格式转换
                    binance_symbol = symbol.replace("/", "")
                    order_result = await exchange_instance.place_order(
                        symbol=binance_symbol,
                        side=side.upper(),  # Binance使用大写
                        order_type=order_type.upper(),
                        quantity=str(quantity),
                        price=str(price) if price else None,
                        position_side=position_side.upper() if position_side else None,
                    )
                else:
                    # XT 使用原有方法（Order对象）
                    # 这里保持原有逻辑
                    raise NotImplementedError(f"XT下单功能暂未适配新接口")

                return order_result
            finally:
                await exchange_instance.disconnect()

        order_info = asyncio.run(submit_order())

        if not order_info:
            console.print("[red]订单提交失败[/red]")
            raise typer.Exit(code=1)

        console.print("[green]订单提交成功![/green]\n")

        # 根据输出格式显示
        if output == "json":
            print_json(order_info)
        elif output == "csv":
            # 适配不同交易所的返回格式
            if exchange == ExchangeName.OKX:
                csv_data = [
                    {
                        "order_id": order_info.get("ordId", ""),
                        "client_order_id": order_info.get("clOrdId", ""),
                        "result_code": order_info.get("sCode", ""),
                        "result_msg": order_info.get("sMsg", ""),
                    }
                ]
            elif exchange == ExchangeName.BINANCE:
                csv_data = [
                    {
                        "order_id": str(order_info.get("orderId", "")),
                        "symbol": order_info.get("symbol", ""),
                        "side": order_info.get("side", ""),
                        "type": order_info.get("type", ""),
                        "quantity": str(order_info.get("origQty", 0)),
                        "price": str(order_info.get("price", 0)),
                        "status": order_info.get("status", ""),
                    }
                ]
            else:
                csv_data = [
                    {
                        "order_id": order_info.get("order_id", ""),
                        "symbol": order_info.get("symbol", ""),
                        "side": order_info.get("side", ""),
                        "type": order_info.get("type", ""),
                        "quantity": str(order_info.get("quantity", 0)),
                        "price": str(order_info.get("price", 0)),
                        "status": order_info.get("status", ""),
                    }
                ]
            print_csv(csv_data)
        else:  # table (default)
            # 格式化显示订单信息
            if exchange == ExchangeName.OKX:
                console.print("订单详情:")
                console.print(f"  订单ID: [cyan]{order_info.get('ordId', '')}[/cyan]")
                console.print(f"  客户订单ID: {order_info.get('clOrdId', 'N/A')}")
                console.print(
                    f"  执行结果: {order_info.get('sMsg', 'Success') if order_info.get('sCode') == '0' else order_info.get('sMsg', 'Failed')}"
                )
            elif exchange == ExchangeName.BINANCE:
                console.print("订单详情:")
                console.print(f"  订单ID: [cyan]{order_info.get('orderId', '')}[/cyan]")
                console.print(f"  交易对: {order_info.get('symbol', '')}")
                console.print(f"  方向: {order_info.get('side', '')}")
                console.print(f"  类型: {order_info.get('type', '')}")
                console.print(f"  价格: {order_info.get('price', 'MARKET')}")
                console.print(f"  数量: {order_info.get('origQty', '')}")
                console.print(
                    f"  状态: [yellow]{order_info.get('status', '')}[/yellow]"
                )
            else:
                format_order_summary(order_info)

    except ValueError as e:
        console.print(f"[red]参数错误:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("status")
def status(
    order_id: str = typer.Option(..., "--order-id", help="订单 ID"),
    exchange_type: ExchangeType = typer.Option(
        ..., "--exchange-type", "-e", help="交易类型 (spot 或 perp)"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="API 密钥（覆盖环境变量）"
    ),
    api_secret: Optional[str] = typer.Option(
        None, "--api-secret", help="API 密钥（覆盖环境变量）"
    ),
    output: str = typer.Option(
        "table", "--output", "-o", help="输出格式 (table, json, csv)"
    ),
    debug: bool = typer.Option(False, "--debug", help="启用调试模式"),
):
    """查询订单状态.

    示例:
        cextools order status --order-id 12345678 -e spot
        cextools order status --order-id 87654321 -e perp -o json
    """
    try:
        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步查询订单
        async def get_order_status():
            await exchange.connect()
            try:
                order_data = await exchange.get_order(order_id)
                return order_data
            finally:
                await exchange.disconnect()

        order_info = asyncio.run(get_order_status())

        if not order_info:
            console.print(f"[yellow]未找到订单 {order_id}[/yellow]")
            return

        # 根据输出格式显示
        if output == "json":
            print_json(order_info)
        elif output == "csv":
            csv_data = [
                {
                    "order_id": order_info.get("order_id", ""),
                    "symbol": order_info.get("symbol", ""),
                    "side": order_info.get("side", ""),
                    "type": order_info.get("type", ""),
                    "quantity": str(order_info.get("quantity", 0)),
                    "filled_quantity": str(order_info.get("filled_quantity", 0)),
                    "price": str(order_info.get("price", 0)),
                    "status": order_info.get("status", ""),
                }
            ]
            print_csv(csv_data)
        else:  # table (default)
            format_order_summary(order_info)

    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("cancel")
def cancel(
    order_id: str = typer.Option(..., "--order-id", help="订单 ID"),
    exchange_type: ExchangeType = typer.Option(
        ..., "--exchange-type", "-e", help="交易类型 (spot 或 perp)"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="API 密钥（覆盖环境变量）"
    ),
    api_secret: Optional[str] = typer.Option(
        None, "--api-secret", help="API 密钥（覆盖环境变量）"
    ),
    debug: bool = typer.Option(False, "--debug", help="启用调试模式"),
):
    """取消单个订单.

    示例:
        cextools order cancel --order-id 12345678 -e spot
        cextools order cancel --order-id 87654321 -e perp
    """
    try:
        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步取消订单
        async def cancel_order():
            await exchange.connect()
            try:
                result = await exchange.cancel_order(order_id)
                return result
            finally:
                await exchange.disconnect()

        result = asyncio.run(cancel_order())

        if result:
            console.print(f"[green]订单 {order_id} 已成功取消[/green]")
        else:
            console.print(
                f"[yellow]订单 {order_id} 取消失败（可能已完成或不存在）[/yellow]"
            )

    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("cancel-all")
def cancel_all(
    symbol: Optional[str] = typer.Option(
        None, "--symbol", "-s", help="交易对（例如 BTC/USDT），不指定则取消所有"
    ),
    exchange_type: ExchangeType = typer.Option(
        ..., "--exchange-type", "-e", help="交易类型 (spot 或 perp)"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key", help="API 密钥（覆盖环境变量）"
    ),
    api_secret: Optional[str] = typer.Option(
        None, "--api-secret", help="API 密钥（覆盖环境变量）"
    ),
    confirm: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示"),
    debug: bool = typer.Option(False, "--debug", help="启用调试模式"),
):
    """批量取消订单.

    示例:
        cextools order cancel-all -e spot
        cextools order cancel-all -s BTC/USDT -e perp --yes
    """
    try:
        # 验证 symbol 格式（如果提供）
        if symbol:
            symbol = validate_symbol(symbol)

        # 确认提示
        if not confirm:
            target = f"交易对 {symbol}" if symbol else "所有交易对"
            prompt = f"确认要取消 {target} 的所有挂单吗？"
            if not typer.confirm(prompt):
                console.print("[yellow]已取消操作[/yellow]")
                return

        # 创建 exchange 实例
        exchange = create_exchange(exchange_type, api_key, api_secret)

        # 异步批量取消
        async def cancel_all_orders():
            await exchange.connect()
            try:
                if symbol:
                    result = await exchange.cancel_all_orders(symbol)
                else:
                    result = await exchange.cancel_all_orders()
                return result
            finally:
                await exchange.disconnect()

        result = asyncio.run(cancel_all_orders())

        if result:
            cancelled_count = result.get("cancelled_count", 0)
            console.print(f"[green]成功取消 {cancelled_count} 个订单[/green]")
        else:
            console.print("[yellow]没有可取消的订单[/yellow]")

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
