"""Monitor command for triangular arbitrage opportunity detection.

Implements the 'tri-arb monitor' command for scanning and monitoring
arbitrage opportunities across trading pairs.

Based on specs/004-xt-get-ticker/quickstart.md scenarios.
"""

import asyncio
import os
from decimal import Decimal

import httpx
import typer
import uvloop
from rich.console import Console
from rich.table import Table

from tri_arb.arbitrage import ArbitrageMonitor
from tri_arb.arbitrage.config import MonitorConfig
from tri_arb.arbitrage.exceptions import ArbitrageError, ConfigError, NetworkError
from tri_arb.cli.app import app
from tri_arb.config.logging import get_logger
from tri_arb.models.exchange import Ticker


logger = get_logger(__name__)
console = Console()


class MockExchange:
    """Mock exchange for testing without real API credentials.

    Provides sample ticker data with a profitable arbitrage opportunity.
    """

    def __init__(self):
        """Initialize mock exchange with sample tickers."""
        self.tickers = [
            Ticker(
                symbol="BTC/USDT",
                bid=Decimal("50000"),
                ask=Decimal("50001"),
                bid_volume=Decimal("1.0"),
                ask_volume=Decimal("1.0"),
            ),
            Ticker(
                symbol="ETH/USDT",
                bid=Decimal("2700"),  # Profitable arbitrage setup
                ask=Decimal("2701"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0"),
            ),
            Ticker(
                symbol="ETH/BTC",
                bid=Decimal("0.051"),
                ask=Decimal("0.052"),
                bid_volume=Decimal("10.0"),
                ask_volume=Decimal("10.0"),
            ),
        ]

    async def get_ticker(self, symbol: str | None = None) -> list[Ticker]:
        """Mock get_ticker implementation."""
        if symbol is None:
            return self.tickers
        return [t for t in self.tickers if t.symbol == symbol]


@app.command()
def monitor(
    min_profit: float = typer.Option(
        0.5,
        "--min-profit",
        help="最低盈利阈值（百分比，例如 1.0 表示 1%）",
    ),
    base_currencies: str | None = typer.Option(
        None,
        "--base-currencies",
        help="基础货币白名单（逗号分隔，例如: USDT,BTC）",
    ),
    mode: str = typer.Option(
        "once",
        "--mode",
        help="运行模式: once（单次扫描）或 realtime（实时监控）",
    ),
    refresh_interval: int = typer.Option(
        10,
        "--refresh-interval",
        help="刷新间隔（秒，仅实时模式）",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式（显示详细日志）",
    ),
) -> None:
    """监控三角套利机会。

    扫描市场数据，发现并显示盈利的三角套利路径。

    Examples:

        # 单次扫描（默认）
        tri-arb monitor

        # 只显示收益率 >= 1% 的机会
        tri-arb monitor --min-profit 1.0

        # 只监控 USDT 相关路径
        tri-arb monitor --base-currencies USDT

        # 实时监控，每 5 秒刷新
        tri-arb monitor --mode realtime --refresh-interval 5
    """
    # Install uvloop for better async performance
    uvloop.install()
    logger.info("uvloop event loop policy installed")

    try:
        # Run async monitor
        asyncio.run(
            _async_monitor(
                min_profit=min_profit,
                base_currencies=base_currencies,
                mode=mode,
                refresh_interval=refresh_interval,
                debug=debug,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]✓ 监控已停止[/yellow]")
        logger.info("Monitor stopped by user (Ctrl+C)")
    except ConfigError as e:
        console.print(f"[red]✗ 配置错误: {e}[/red]")
        logger.error("Configuration error", error=str(e))
        raise typer.Exit(code=1) from e
    except httpx.HTTPStatusError as e:
        # HTTP error from XT API
        if e.response.status_code == 429:
            console.print("[red]✗ XT API 限流，请稍后重试[/red]")
        elif e.response.status_code == 401:
            console.print("[red]✗ XT API 密钥无效，请检查 XT_API_KEY 和 XT_API_SECRET[/red]")
        elif e.response.status_code == 403:
            console.print("[red]✗ XT API 访问被拒绝，请检查 API 权限[/red]")
        else:
            console.print(f"[red]✗ XT API 错误 (HTTP {e.response.status_code})[/red]")
        logger.error("XT API HTTP error", status_code=e.response.status_code, error=str(e))
        raise typer.Exit(code=2) from e
    except httpx.TimeoutException as e:
        console.print("[red]✗ XT API 请求超时，请检查网络连接[/red]")
        logger.error("XT API timeout", error=str(e))
        raise typer.Exit(code=2) from e
    except httpx.ConnectError as e:
        console.print("[red]✗ 无法连接到 XT API，请检查网络连接[/red]")
        logger.error("XT API connection error", error=str(e))
        raise typer.Exit(code=2) from e
    except ArbitrageError as e:
        console.print(f"[red]✗ 错误: {e}[/red]")
        logger.error("Arbitrage error", error=str(e))
        raise typer.Exit(code=1) from e


async def _async_monitor(
    min_profit: float,
    base_currencies: str | None,
    mode: str,
    refresh_interval: int,
    debug: bool,
) -> None:
    """Async monitor execution.

    Args:
        min_profit: Minimum profit threshold percentage
        base_currencies: Comma-separated base currency whitelist
        mode: Run mode (once or realtime)
        refresh_interval: Refresh interval in seconds (realtime mode)
        debug: Enable debug mode
    """
    # Parse base currencies
    base_list = []
    if base_currencies:
        base_list = [c.strip().upper() for c in base_currencies.split(",")]
        logger.info("Base currency whitelist", currencies=base_list)

    # Create monitor configuration
    try:
        config = MonitorConfig(
            min_profit_threshold=min_profit,
            base_currency_whitelist=base_list,
            run_mode=mode,
            refresh_interval_seconds=refresh_interval,
        )
        logger.info("Monitor configuration created", config=config)
    except Exception as e:
        raise ConfigError(f"Invalid configuration: {e}") from e

    # Create arbitrage monitor
    monitor = ArbitrageMonitor(config=config, exchange_name="xt")

    # Connect to exchange
    # Check for real API credentials
    api_key = os.getenv("XT_API_KEY")
    api_secret = os.getenv("XT_API_SECRET")

    exchange_adapter = None  # Track for cleanup

    if api_key and api_secret:
        # Use real XT Exchange
        from tri_arb.arbitrage.adapters import XTExchangeAdapter

        console.print("[cyan]ℹ Connecting to XT Exchange...[/cyan]")
        try:
            exchange_adapter = XTExchangeAdapter(api_key=api_key, api_secret=api_secret)
            await exchange_adapter.connect()
            monitor._exchange = exchange_adapter
            console.print("[green]✓ Connected to XT Exchange[/green]")
        except Exception as e:
            console.print(f"[red]✗ Failed to connect to XT Exchange: {e}[/red]")
            logger.error("XT Exchange connection failed", error=str(e))
            raise
    else:
        console.print("[cyan]ℹ Using MockExchange (set XT_API_KEY and XT_API_SECRET for real data)[/cyan]")
        monitor._exchange = MockExchange()

    # Execute scan based on mode
    try:
        if mode == "once":
            console.print("[bold]开始扫描市场...[/bold]")
            logger.info("Starting single scan")

            try:
                opportunities = await monitor.scan_once()
                logger.info("Scan completed", opportunities_found=len(opportunities))

                _display_opportunities(opportunities, min_profit)

            except NetworkError as e:
                raise ArbitrageError(f"Network error: {e}") from e

        elif mode == "realtime":
            console.print(
                f"[bold]开始实时监控（每 {refresh_interval} 秒刷新）...[/bold]"
            )
            console.print("[dim]按 Ctrl+C 停止[/dim]\n")
            logger.info("Starting realtime monitoring", refresh_interval=refresh_interval)

            try:
                iteration = 0
                async for opportunities in monitor.scan_realtime():
                    iteration += 1
                    logger.info("Scan iteration completed", iteration=iteration, opportunities_found=len(opportunities))

                    console.print(f"\n[bold cyan]═══ 扫描 {iteration} ═══[/bold cyan]")
                    _display_opportunities(opportunities, min_profit)

                    if not monitor._shutdown_requested:
                        console.print(
                            f"[dim]下次刷新: {refresh_interval} 秒后...[/dim]"
                        )

            except NetworkError as e:
                raise ArbitrageError(f"Network error: {e}") from e

        else:
            raise ConfigError(f"Invalid run mode: {mode}. Must be 'once' or 'realtime'")

    finally:
        # Ensure exchange is disconnected
        if exchange_adapter is not None:
            try:
                await exchange_adapter.disconnect()
                logger.info("Exchange adapter disconnected")
            except Exception as e:
                logger.warning("Failed to disconnect exchange adapter", error=str(e))


def _display_opportunities(opportunities: list, min_profit: float) -> None:
    """Display arbitrage opportunities in a formatted table.

    Args:
        opportunities: List of ArbitrageOpportunity objects
        min_profit: Minimum profit threshold (for display context)
    """
    if not opportunities:
        console.print(
            f"[yellow]未发现套利机会（阈值: {min_profit}%）[/yellow]"
        )
        return

    # Create Rich table
    table = Table(title=f"发现 {len(opportunities)} 条套利机会（按收益率排序）")
    table.add_column("序号", justify="right", style="cyan", no_wrap=True)
    table.add_column("路径", style="magenta")
    table.add_column("收益率", justify="right", style="green")
    table.add_column("建议金额", justify="right", style="yellow")

    for i, opp in enumerate(opportunities, 1):
        # Format path: USDT → BTC → ETH → USDT
        path_parts = []
        current = opp.path.start_currency
        path_parts.append(current)

        for pair in opp.path.trading_pairs:
            base, quote = pair.split("/")
            # Determine next currency
            current = quote if current == base else base
            path_parts.append(current)

        path_str = " → ".join(path_parts)

        # Add row to table
        table.add_row(
            str(i),
            path_str,
            f"{opp.expected_profit_rate:.2f}%",
            str(opp.recommended_amount),
        )

    console.print(table)
