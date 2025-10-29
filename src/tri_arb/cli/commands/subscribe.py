"""WebSocket订阅命令."""

import asyncio
import os
from typing import Optional

import typer
from rich.console import Console
from dotenv import load_dotenv

from tri_arb.cli.utils.exchange_factory import ExchangeName
from tri_arb.services.binance_user_stream import BinanceUserStreamService
from tri_arb.services.okx_user_stream import OKXUserStreamService
from tri_arb.services.gate_user_stream import GateUserStreamService
from tri_arb.services.xt_user_stream import XTUserStreamService
from tri_arb.storage.database import DatabaseManager

app = typer.Typer(help="WebSocket订阅命令")
console = Console()
load_dotenv()


@app.command("user-stream")
def user_stream(
    exchange: ExchangeName = typer.Option(
        ...,
        "--exchange",
        "-x",
        help="交易所: binance, okx, gate, xt"
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
    passphrase: Optional[str] = typer.Option(
        None,
        "--passphrase",
        help="API Passphrase（OKX需要，覆盖环境变量）"
    ),
    database_url: Optional[str] = typer.Option(
        None,
        "--database-url",
        help="PostgreSQL连接URL（覆盖环境变量）"
    ),
    create_tables: bool = typer.Option(
        False,
        "--create-tables",
        help="自动创建数据库表"
    ),
    output: str = typer.Option(
        "table",
        "--output",
        "-o",
        help="输出格式: table(表格), json(JSON), none(不显示)"
    ),
    channels: Optional[str] = typer.Option(
        None,
        "--channels",
        "-c",
        help="订阅的频道，用逗号分隔。Binance: account,order,trade; OKX: account,position,order; XT: account,position,order,trade。留空=全部订阅（默认订阅永续合约）"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    ),
    enable_data_sync: bool = typer.Option(
        True,
        "--enable-data-sync/--disable-data-sync",
        help="启用/禁用数据同步（默认启用，防止数据丢失）"
    )
):
    """订阅用户数据流.
    
    实时接收账户更新、订单更新和成交信息，并存储到PostgreSQL数据库。
    默认订阅永续合约数据。
    
    示例:
        # Binance永续合约
        cextools subscribe user-stream -x binance
        
        # OKX永续合约
        cextools subscribe user-stream -x okx
        
        # XT永续合约（默认）
        cextools subscribe user-stream -x xt
        
        # 指定输出格式
        cextools subscribe user-stream -x binance --output table
        cextools subscribe user-stream -x okx --output json
        
        # 首次运行，创建数据库表
        cextools subscribe user-stream -x binance --create-tables
    
    环境变量:
        Binance:
            BINANCE_API_KEY: API密钥
            BINANCE_API_SECRET: API密钥
        
        OKX:
            OKX_API_KEY: API密钥
            OKX_API_SECRET: API密钥
            OKX_PASSPHRASE: API Passphrase
        
        Gate.io:
            GATE_API_KEY: API密钥
            GATE_API_SECRET: API密钥
        
        XT:
            XT_API_KEY: API密钥（现货和永续合约共用）
            XT_API_SECRET: API密钥（现货和永续合约共用）
        
        数据库:
            DATABASE_URL: PostgreSQL连接URL
        
    按 Ctrl+C 停止订阅。
    """
    try:
        # 验证交易所
        if exchange not in [ExchangeName.BINANCE, ExchangeName.OKX, ExchangeName.GATE, ExchangeName.XT]:
            console.print(f"[red]错误:[/red] 不支持的交易所: {exchange}")
            console.print("支持的交易所: binance, okx, gate, xt")
            raise typer.Exit(code=1)
        
        # 根据交易所获取API凭证
        if exchange == ExchangeName.BINANCE:
            key = api_key or os.getenv("BINANCE_API_KEY", "")
            secret = api_secret or os.getenv("BINANCE_API_SECRET", "")
            
            if not key or not secret:
                console.print("[red]错误:[/red] 缺少Binance API凭证")
                console.print("请设置环境变量或使用 --api-key 和 --api-secret 参数")
                console.print("\n示例:")
                console.print("  export BINANCE_API_KEY='your_key'")
                console.print("  export BINANCE_API_SECRET='your_secret'")
                raise typer.Exit(code=1)
        
        elif exchange == ExchangeName.OKX:
            key = api_key or os.getenv("OKX_API_KEY", "")
            secret = api_secret or os.getenv("OKX_API_SECRET", "")
            phrase = passphrase or os.getenv("OKX_PASSPHRASE", "")
            
            if not key or not secret or not phrase:
                console.print("[red]错误:[/red] 缺少OKX API凭证")
                console.print("请设置环境变量或使用命令行参数")
                console.print("\n示例:")
                console.print("  export OKX_API_KEY='your_key'")
                console.print("  export OKX_API_SECRET='your_secret'")
                console.print("  export OKX_PASSPHRASE='your_passphrase'")
                raise typer.Exit(code=1)
        
        elif exchange == ExchangeName.GATE:
            key = api_key or os.getenv("GATE_API_KEY", "")
            secret = api_secret or os.getenv("GATE_API_SECRET", "")
            
            if not key or not secret:
                console.print("[red]错误:[/red] 缺少Gate.io API凭证")
                console.print("请设置环境变量或使用命令行参数")
                console.print("\n示例:")
                console.print("  export GATE_API_KEY='your_key'")
                console.print("  export GATE_API_SECRET='your_secret'")
                raise typer.Exit(code=1)
        
        elif exchange == ExchangeName.XT:
            key = api_key or os.getenv("XT_API_KEY", "")
            secret = api_secret or os.getenv("XT_API_SECRET", "")
            
            if not key or not secret:
                console.print("[red]错误:[/red] 缺少XT API凭证")
                console.print("请设置环境变量或使用命令行参数")
                console.print("\n示例:")
                console.print("  export XT_API_KEY='your_key'")
                console.print("  export XT_API_SECRET='your_secret'")
                raise typer.Exit(code=1)
        
        # 获取数据库URL
        db_url = database_url or os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://oliver@localhost:5432/trading"
        )
        
        # 解析订阅频道
        channel_list = None
        if channels:
            channel_list = [ch.strip().lower() for ch in channels.split(",")]
            # 验证频道名称
            if exchange == ExchangeName.BINANCE:
                valid_channels = {"account", "order", "trade"}
                invalid = set(channel_list) - valid_channels
                if invalid:
                    console.print(f"[red]错误:[/red] Binance不支持的频道: {', '.join(invalid)}")
                    console.print(f"支持的频道: {', '.join(valid_channels)}")
                    raise typer.Exit(code=1)
            elif exchange == ExchangeName.OKX:
                valid_channels = {"account", "position", "order"}
                invalid = set(channel_list) - valid_channels
                if invalid:
                    console.print(f"[red]错误:[/red] OKX不支持的频道: {', '.join(invalid)}")
                    console.print(f"支持的频道: {', '.join(valid_channels)}")
                    raise typer.Exit(code=1)
            elif exchange == ExchangeName.GATE:
                valid_channels = {"account", "position", "order"}
                invalid = set(channel_list) - valid_channels
                if invalid:
                    console.print(f"[red]错误:[/red] Gate.io不支持的频道: {', '.join(invalid)}")
                    console.print(f"支持的频道: {', '.join(valid_channels)}")
                    raise typer.Exit(code=1)
            elif exchange == ExchangeName.XT:
                valid_channels = {"account", "position", "order", "trade"}
                invalid = set(channel_list) - valid_channels
                if invalid:
                    console.print(f"[red]错误:[/red] XT不支持的频道: {', '.join(invalid)}")
                    console.print(f"支持的频道: {', '.join(valid_channels)}")
                    raise typer.Exit(code=1)
        
        exchange_name = {
            ExchangeName.BINANCE: "Binance",
            ExchangeName.OKX: "OKX",
            ExchangeName.GATE: "Gate.io",
            ExchangeName.XT: "XT"
        }.get(exchange, "Unknown")
        console.print(f"[cyan]{exchange_name}用户数据流订阅服务[/cyan]")
        console.print(f"[cyan]数据库: {db_url.split('@')[-1] if '@' in db_url else 'localhost'}[/cyan]")
        if channel_list:
            console.print(f"[cyan]订阅频道: {', '.join(channel_list)}[/cyan]")
        else:
            console.print(f"[cyan]订阅频道: 全部[/cyan]")
        console.print(f"[cyan]数据同步: {'启用' if enable_data_sync else '禁用'}[/cyan]")
        console.print(f"[yellow]按 Ctrl+C 停止订阅[/yellow]\n")
        
        async def run_service():
            # 初始化数据库管理器
            db_manager = DatabaseManager(database_url=db_url)
            
            # 创建数据库表（如果指定）
            if create_tables:
                console.print("[cyan]正在创建数据库表...[/cyan]")
                await db_manager.create_tables()
                console.print("[green]✅ 数据库表创建成功[/green]\n")
            
            # 验证输出格式
            if output not in ["table", "json", "none"]:
                console.print(f"[red]错误:[/red] 无效的输出格式: {output}")
                console.print("支持的格式: table, json, none")
                raise typer.Exit(code=1)
            
            # 根据交易所初始化服务
            if exchange == ExchangeName.BINANCE:
                service = BinanceUserStreamService(
                    api_key=key,
                    api_secret=secret,
                    db_manager=db_manager,
                    auto_reconnect=True,
                    display_format=output,
                    enabled_channels=channel_list,
                )
            elif exchange == ExchangeName.OKX:
                service = OKXUserStreamService(
                    api_key=key,
                    api_secret=secret,
                    passphrase=phrase,
                    db_manager=db_manager,
                    auto_reconnect=True,
                    display_format=output,
                    enabled_channels=channel_list,
                )
            elif exchange == ExchangeName.GATE:
                service = GateUserStreamService(
                    api_key=key,
                    api_secret=secret,
                    db_manager=db_manager,
                    auto_reconnect=True,
                    display_format=output,
                    enabled_channels=channel_list,
                )
            else:  # XT
                service = XTUserStreamService(
                    api_key=key,
                    api_secret=secret,
                    db_manager=db_manager,
                    auto_reconnect=True,
                    display_format=output,
                    enabled_channels=channel_list,
                    enable_data_sync=enable_data_sync,
                )
            
            console.print("[green]✅ 服务已启动[/green]")
            console.print("[cyan]正在连接WebSocket...[/cyan]\n")
            
            try:
                await service.start()
            except KeyboardInterrupt:
                console.print("\n[yellow]正在停止服务...[/yellow]")
                await service.stop()
                await db_manager.close()
                console.print("[green]✅ 服务已停止[/green]")
        
        asyncio.run(run_service())
        
    except KeyboardInterrupt:
        console.print("\n[yellow]订阅已停止[/yellow]")
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {e}")
        raise typer.Exit(code=1)


@app.command("binance-user-stream")
def binance_user_stream_legacy(
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API 密钥"),
    api_secret: Optional[str] = typer.Option(None, "--api-secret", help="API 密钥"),
    database_url: Optional[str] = typer.Option(None, "--database-url", help="数据库URL"),
    create_tables: bool = typer.Option(False, "--create-tables", help="创建表"),
    output: str = typer.Option("table", "--output", "-o", help="输出格式"),
    debug: bool = typer.Option(False, "--debug", help="调试模式")
):
    """Binance用户数据流订阅（向后兼容命令）.
    
    推荐使用新命令: cextools subscribe user-stream -x binance
    """
    console.print("[yellow]提示: 此命令已过时，推荐使用:[/yellow]")
    console.print("  cextools subscribe user-stream -x binance\n")
    
    # 调用新命令
    user_stream(
        exchange=ExchangeName.BINANCE,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=None,
        database_url=database_url,
        create_tables=create_tables,
        output=output,
        debug=debug
    )


@app.command("okx-user-stream")
def okx_user_stream_shortcut(
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API 密钥"),
    api_secret: Optional[str] = typer.Option(None, "--api-secret", help="API 密钥"),
    passphrase: Optional[str] = typer.Option(None, "--passphrase", help="API Passphrase"),
    database_url: Optional[str] = typer.Option(None, "--database-url", help="数据库URL"),
    create_tables: bool = typer.Option(False, "--create-tables", help="创建表"),
    output: str = typer.Option("table", "--output", "-o", help="输出格式"),
    debug: bool = typer.Option(False, "--debug", help="调试模式")
):
    """OKX用户数据流订阅（快捷命令）.
    
    等同于: cextools subscribe user-stream -x okx
    """
    user_stream(
        exchange=ExchangeName.OKX,
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        database_url=database_url,
        create_tables=create_tables,
        output=output,
        debug=debug
    )


if __name__ == "__main__":
    app()
