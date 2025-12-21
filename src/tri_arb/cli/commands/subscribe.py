"""WebSocket订阅命令."""

import asyncio
import os
from typing import Optional

import typer
from rich.console import Console
from dotenv import load_dotenv

from tri_arb.cli.utils.exchange_factory import ExchangeName
from tri_arb.config.account_manager import AccountManager
from tri_arb.services.binance_user_stream import BinanceUserStreamService
from tri_arb.services.okx_user_stream import OKXUserStreamService
from tri_arb.services.gate_user_stream import GateUserStreamService
from tri_arb.services.xt_user_stream import XTUserStreamService
from tri_arb.services.xt_multi_account_stream import XTMultiAccountStreamService
from tri_arb.storage.database import DatabaseManager
from tri_arb.metrics.prometheus import ensure_metrics_server

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
    ),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="账号ID（可选，仅支持XT），如果提供则使用账号特定的表。例如: account_001"
    ),
):
    """订阅用户数据流.
    
    实时接收账户更新、订单更新和成交信息，并存储到PostgreSQL数据库。
    默认订阅永续合约数据。
    
    如果提供账号ID（仅支持XT），数据会保存到账号特定的表中。
    表会在首次运行时自动创建，不会重复创建。
    
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
            # 启动 Prometheus metrics 服务器
            # 订阅服务使用端口 9601，避免与 watch-balance 冲突
            ensure_metrics_server(9601)
            
            # 初始化数据库管理器
            db_manager = DatabaseManager(database_url=db_url)
            
            # 始终确保基础表存在（使用 checkfirst，不会重复创建）
            try:
                console.print("[cyan]正在检查/创建基础数据库表...[/cyan]")
                await db_manager.create_tables()
                console.print("[green]✅ 基础数据库表已就绪[/green]\n")
            except Exception as init_exc:
                # 如果建表失败，不中断后续逻辑，但给出警告
                console.print(f"[yellow]警告:[/yellow] 基础数据库表初始化失败: {init_exc}")
            
            # 统一表已通过 create_tables() 创建，不再需要按账号分表
            
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
                if account_id:
                    service.account_id = account_id
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
                # 如果提供了账号ID，附加到服务实例
                service = XTUserStreamService(
                    api_key=key,
                    api_secret=secret,
                    db_manager=db_manager,
                    auto_reconnect=True,
                    display_format=output,
                    enabled_channels=channel_list,
                    enable_data_sync=enable_data_sync,
                )
                if account_id:
                    service.account_id = account_id
                    # 不再需要按账号分表，统一使用 account_id 字段
            
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


@app.command("multi-account")
def multi_account(
    config_path: str = typer.Option(
        "config/accounts.json",
        "--config",
        "-c",
        help="账号配置文件路径（JSON格式）"
    ),
    account_ids: Optional[str] = typer.Option(
        None,
        "--accounts",
        "-a",
        help="要启动的账号ID列表，用逗号分隔。留空则启动所有启用的账号"
    ),
    database_url: Optional[str] = typer.Option(
        None,
        "--database-url",
        help="PostgreSQL连接URL（覆盖环境变量和配置文件）"
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
    enable_data_sync: bool = typer.Option(
        True,
        "--enable-data-sync/--disable-data-sync",
        help="启用/禁用数据同步（默认启用）"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    ),
):
    """多交易所多账号订阅服务.

    - 支持 XT / Binance / OKX / Gate.io 等交易所账号混合运行
    - 账号信息、频道、API 凭证从 JSON 配置文件读取
    - XT 账号自动使用账号特定的表结构
    """
    import logging
    if debug:
        logging.basicConfig(level=logging.DEBUG)

    # 加载账号配置
    try:
        account_manager = AccountManager(config_path)
    except FileNotFoundError:
        console.print(f"[red]错误:[/red] 配置文件不存在: {config_path}")
        console.print("请创建配置文件，参考: config/accounts.example.json")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]错误:[/red] 加载配置文件失败: {exc}")
        raise typer.Exit(code=1)

    # 获取数据库URL，优先级: 参数 > 配置 > 环境变量
    db_url = database_url or account_manager.global_settings.get("database_url") or os.getenv("DATABASE_URL")
    if not db_url:
        console.print("[red]错误:[/red] 未指定数据库URL")
        console.print("请通过 --database-url 参数、配置文件 global_settings 或 DATABASE_URL 环境变量指定")
        raise typer.Exit(code=1)

    # 解析账号ID列表
    requested_ids = None
    if account_ids:
        requested_ids = [acc_id.strip() for acc_id in account_ids.split(",") if acc_id.strip()]
        if not requested_ids:
            console.print("[red]错误:[/red] --accounts 参数为空")
            raise typer.Exit(code=1)

    # 过滤启用账号
    enabled_accounts = account_manager.get_enabled_accounts()
    if requested_ids is not None:
        enabled_accounts = [acc for acc in enabled_accounts if acc.account_id in requested_ids]
        missing = set(requested_ids) - {acc.account_id for acc in enabled_accounts}
        if missing:
            console.print(f"[yellow]警告:[/yellow] 下列账号未启用或不存在: {', '.join(sorted(missing))}")
    if not enabled_accounts:
        console.print("[red]错误:[/red] 没有可用的启用账号")
        raise typer.Exit(code=1)

    total_accounts = len(account_manager.get_all_accounts())
    console.print(f"[cyan]多交易所多账号订阅服务[/cyan]")
    console.print(f"[cyan]配置文件: {config_path}[/cyan]")
    console.print(f"[cyan]数据库: {db_url.split('@')[-1] if '@' in db_url else db_url}[/cyan]")
    console.print(f"[cyan]启用账号: {len(enabled_accounts)} / {total_accounts}[/cyan]")
    for acc in enabled_accounts:
        exchange_name = acc.exchange.upper()
        channels_desc = ", ".join(acc.channels) if acc.channels else "全部"
        console.print(f"  - {acc.account_id}: {acc.name} [{exchange_name}] 频道: {channels_desc}")
    console.print(f"[cyan]输出格式: {output}[/cyan]")
    console.print(f"[cyan]数据同步: {'启用' if enable_data_sync else '禁用'}[/cyan]")
    console.print("[yellow]按 Ctrl+C 停止订阅[/yellow]\n")

    async def prepare_tables_if_needed():
        """为多账号订阅准备数据库表。
        
        - 始终确保基础表存在（使用 checkfirst，无论是否传入 --create-tables）
        - 为 XT 账号预创建多账号表（XT 服务内部仍有 ensure_account_tables 兜底）
        """
        console.print("[cyan]正在检查/创建基础数据库表（多账号）...[/cyan]")
        db_manager = DatabaseManager(database_url=db_url)
        try:
            # 1. 创建/检查通用表（Binance、OKX、Gate、REST 等）
            await db_manager.create_tables()
            
            # 统一表已通过 create_tables() 创建，不再需要按账号分表
            console.print("[green]✅ 多账号基础数据库表已就绪[/green]\n")
        except Exception as init_exc:
            console.print(f"[red]错误:[/red] 多账号基础数据库表初始化失败: {init_exc}")
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Failed to create database tables for multi-account", exc_info=True, extra={"error": str(init_exc)})
            if debug:
                console.print_exception()
            # 表创建失败时，抛出异常阻止程序继续运行
            raise typer.Exit(code=1)
        finally:
            await db_manager.close()

    async def run_account_stream(acc_config):
        try:
            acc_exchange = ExchangeName(acc_config.exchange.lower())
        except ValueError:
            console.print(f"[yellow]警告:[/yellow] 账号 {acc_config.account_id} 的交易所 {acc_config.exchange} 暂不支持，跳过")
            return

        key = acc_config.api_key
        secret = acc_config.api_secret
        passphrase = getattr(acc_config, "passphrase", None)
        if not key or not secret:
            console.print(f"[yellow]警告:[/yellow] 账号 {acc_config.account_id} 缺少 API 凭证，跳过")
            return

        db_manager = DatabaseManager(database_url=db_url)
        enabled_channels = [ch.strip().lower() for ch in acc_config.channels] if acc_config.channels else None

        if output not in ["table", "json", "none"]:
            raise ValueError("输出格式仅支持 table/json/none")

        if acc_exchange == ExchangeName.BINANCE:
            service = BinanceUserStreamService(
                api_key=key,
                api_secret=secret,
                db_manager=db_manager,
                auto_reconnect=True,
                display_format=output,
                enabled_channels=enabled_channels,
            )
            service.account_id = acc_config.account_id
            service.account_name = acc_config.name
        elif acc_exchange == ExchangeName.OKX:
            if not passphrase:
                console.print(f"[yellow]警告:[/yellow] 账号 {acc_config.account_id} 缺少 OKX passphrase，跳过")
                await db_manager.close()
                return
            service = OKXUserStreamService(
                api_key=key,
                api_secret=secret,
                passphrase=passphrase,
                db_manager=db_manager,
                auto_reconnect=True,
                display_format=output,
                enabled_channels=enabled_channels,
            )
        elif acc_exchange == ExchangeName.GATE:
            service = GateUserStreamService(
                api_key=key,
                api_secret=secret,
                db_manager=db_manager,
                auto_reconnect=True,
                display_format=output,
                enabled_channels=enabled_channels,
            )
        else:  # XT
            service = XTUserStreamService(
                api_key=key,
                api_secret=secret,
                db_manager=db_manager,
                auto_reconnect=True,
                display_format=output,
                enabled_channels=enabled_channels,
                enable_data_sync=enable_data_sync,
            )
            service.account_id = acc_config.account_id
            service.account_name = acc_config.name
            # 不再需要按账号分表，统一使用 account_id 字段

        console.print(f"[cyan]账号 {acc_config.account_id} ({acc_config.name}) 开始订阅 - {acc_exchange.value.upper()}[/cyan]")

        try:
            await service.start()
        except asyncio.CancelledError:
            await service.stop()
            raise
        except Exception as exc:
            console.print(f"[red]账号 {acc_config.account_id} 订阅异常:[/red] {exc}")
            logger = logging.getLogger(__name__)
            logger.error("account %s stream error", acc_config.account_id, exc_info=debug)
            if debug:
                console.print_exception()
        finally:
            try:
                await service.stop()
            except Exception:
                pass
            await db_manager.close()

    async def run_multi_account_service():
        # 启动 Prometheus metrics 服务器
        # 订阅服务使用端口 9601，避免与 watch-balance 冲突
        ensure_metrics_server(9601)
        
        await prepare_tables_if_needed()
        tasks = []
        for acc in enabled_accounts:
            task = asyncio.create_task(run_account_stream(acc))
            tasks.append(task)
            await asyncio.sleep(0.3)

        if not tasks:
            console.print("[red]错误:[/red] 没有可运行的账号订阅任务")
            return

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    try:
        asyncio.run(run_multi_account_service())
    except KeyboardInterrupt:
        console.print("\n[yellow]订阅已停止[/yellow]")
    except Exception as exc:
        if debug:
            console.print_exception()
        else:
            console.print(f"[red]错误:[/red] {exc}")
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
