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
    liquidity_usage: float = typer.Option(
        1.0,
        "--liquidity-usage",
        help="流动性使用率（0.0-1.0，例如 0.3 表示 30%，1.0 表示 100%）",
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
                liquidity_usage=liquidity_usage,
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
    liquidity_usage: float,
    debug: bool,
) -> None:
    """Async monitor execution.

    Args:
        min_profit: Minimum profit threshold percentage
        base_currencies: Comma-separated base currency whitelist
        mode: Run mode (once or realtime)
        refresh_interval: Refresh interval in seconds (realtime mode)
        liquidity_usage: Liquidity usage rate (0.0-1.0)
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

                # Get tickers for liquidity display
                tickers_list = await monitor._exchange.get_ticker(symbol=None)
                tickers_dict = {t.symbol: t for t in tickers_list}

                _display_opportunities(opportunities, min_profit, tickers_dict, liquidity_usage)

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

                    # Get tickers for liquidity display
                    tickers_list = await monitor._exchange.get_ticker(symbol=None)
                    tickers_dict = {t.symbol: t for t in tickers_list}

                    console.print(f"\n[bold cyan]═══ 扫描 {iteration} ═══[/bold cyan]")
                    _display_opportunities(opportunities, min_profit, tickers_dict, liquidity_usage)

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


def _calculate_max_safe_amount(
    opportunity,
    tickers: dict,
    liquidity_usage_rate: Decimal,
    fee_rate: Decimal = Decimal("0.001")
) -> tuple[Decimal, int]:
    """Calculate maximum safe amount based on liquidity constraints.

    Args:
        opportunity: ArbitrageOpportunity object
        tickers: Dictionary mapping symbol to Ticker
        liquidity_usage_rate: Maximum liquidity usage rate (0.0-1.0)
        fee_rate: Fee rate per trade (default 0.1%)

    Returns:
        Tuple of (max_safe_amount, bottleneck_step_index)
    """
    # Step 1: Calculate available liquidity for each step
    available_amounts = []

    for i, price_info in enumerate(opportunity.prices):
        trade_type = price_info["type"]
        pair = price_info["pair"]

        ticker = tickers.get(pair)
        if not ticker:
            # No ticker data, assume zero liquidity
            available_amounts.append((Decimal("0"), i))
            continue

        # Get available liquidity for this step
        if trade_type == "buy":
            # Buying base with quote → limited by ask_volume
            max_tradeable = ticker.ask_volume * liquidity_usage_rate
        else:  # sell
            # Selling base for quote → limited by bid_volume
            max_tradeable = ticker.bid_volume * liquidity_usage_rate

        available_amounts.append((max_tradeable, i))

    if not available_amounts:
        return Decimal("0"), 0

    # Step 2: Find bottleneck (minimum available amount in the path currency)
    # We need to convert all amounts to a common base for comparison
    # Simplest approach: find the step with minimum liquidity and work backwards

    # For now, use simpler heuristic: reverse calculate from each step
    # and find the minimum starting amount
    min_start_amount = Decimal("999999999")
    bottleneck_idx = 0

    for step_idx in range(len(opportunity.prices)):
        # Calculate what starting amount would result in 30% usage at this step
        start_amount = _reverse_calculate_start_amount(
            opportunity, tickers, step_idx, liquidity_usage_rate, fee_rate
        )
        if start_amount < min_start_amount:
            min_start_amount = start_amount
            bottleneck_idx = step_idx

    return min_start_amount, bottleneck_idx


def _reverse_calculate_start_amount(
    opportunity,
    tickers: dict,
    target_step_idx: int,
    liquidity_usage_rate: Decimal,
    fee_rate: Decimal
) -> Decimal:
    """Reverse calculate starting amount for a given bottleneck step.

    Args:
        opportunity: ArbitrageOpportunity object
        tickers: Dictionary mapping symbol to Ticker
        target_step_idx: Index of the bottleneck step
        liquidity_usage_rate: Target usage rate at bottleneck
        fee_rate: Fee rate per trade

    Returns:
        Starting amount in base currency
    """
    # Get the maximum tradeable amount at the bottleneck step
    target_price_info = opportunity.prices[target_step_idx]
    target_pair = target_price_info["pair"]
    target_type = target_price_info["type"]

    ticker = tickers.get(target_pair)
    if not ticker:
        return Decimal("999999999")  # No limit if no ticker data

    # Maximum amount we can trade at this step
    if target_type == "buy":
        max_at_target = ticker.ask_volume * liquidity_usage_rate
    else:
        max_at_target = ticker.bid_volume * liquidity_usage_rate

    # Now reverse calculate from target step back to start
    current_amount = max_at_target

    # Work backwards from target step to step 0
    for i in range(target_step_idx, -1, -1):
        price_info = opportunity.prices[i]
        trade_type = price_info["type"]
        price = price_info["price"]

        if trade_type == "buy":
            # We're reversing a buy: amount_after = (amount_before / price) * (1 - fee)
            # So: amount_before = amount_after * price / (1 - fee)
            current_amount = current_amount * price / (Decimal("1") - fee_rate)
        else:  # sell
            # We're reversing a sell: amount_after = (amount_before * price) * (1 - fee)
            # So: amount_before = amount_after / (price * (1 - fee))
            current_amount = current_amount / (price * (Decimal("1") - fee_rate))

    return current_amount


def _calculate_step_details(
    opportunity,
    tickers: dict,
    initial_amount: Decimal,
    fee_rate: Decimal = Decimal("0.001")
) -> list[dict]:
    """Calculate detailed step-by-step trading information.
    
    Args:
        opportunity: ArbitrageOpportunity object
        tickers: Dictionary mapping symbol to Ticker (for liquidity data)
        initial_amount: Initial investment amount
        fee_rate: Fee rate per trade (default 0.1%)
    
    Returns:
        List of dicts with step details (type, pair, price, amount_before, amount_after, fee, liquidity, usage_rate)
    """
    steps = []
    current_amount = initial_amount
    current_currency = opportunity.path.start_currency

    for i, price_info in enumerate(opportunity.prices):
        trade_type = price_info["type"]
        pair = price_info["pair"]
        price = price_info["price"]
        base, quote = pair.split("/")

        # Get ticker for liquidity data
        ticker = tickers.get(pair)

        # Record amount before trade
        amount_before = current_amount
        currency_before = current_currency

        # Calculate amount after trade and get liquidity
        if trade_type == "buy":
            # Buying base with quote currency
            # amount_before (quote) / price = base_amount
            amount_after = (current_amount / price) * (Decimal("1") - fee_rate)
            current_currency = base

            # Liquidity: how much base we can buy (ask_volume)
            available_liquidity = ticker.ask_volume if ticker else Decimal("0")
            liquidity_currency = base
        else:  # sell
            # Selling base for quote currency
            # amount_before (base) * price = quote_amount
            amount_after = (current_amount * price) * (Decimal("1") - fee_rate)
            current_currency = quote

            # Liquidity: how much base we can sell (bid_volume)
            available_liquidity = ticker.bid_volume if ticker else Decimal("0")
            liquidity_currency = base

        current_amount = amount_after

        # Calculate fee in the resulting currency
        fee_amount = amount_before * fee_rate if trade_type == "sell" else (amount_before / price) * fee_rate

        # Calculate liquidity usage rate
        # For buy: compare amount_after (base we get) with ask_volume
        # For sell: compare amount_before (base we sell) with bid_volume
        trade_amount = amount_after if trade_type == "buy" else amount_before

        if available_liquidity > 0:
            usage_rate = (trade_amount / available_liquidity) * Decimal("100")
        else:
            usage_rate = Decimal("0")

        steps.append({
            "step": i + 1,
            "type": trade_type,
            "pair": pair,
            "price": price,
            "amount_before": amount_before,
            "currency_before": currency_before,
            "amount_after": amount_after,
            "currency_after": current_currency,
            "fee": fee_amount,
            "fee_currency": current_currency,
            "available_liquidity": available_liquidity,
            "liquidity_currency": liquidity_currency,
            "usage_rate": usage_rate
        })

    return steps


def _display_opportunities(
    opportunities: list,
    min_profit: float,
    tickers: dict | None = None,
    liquidity_usage: float = 1.0,
) -> None:
    """Display arbitrage opportunities in a formatted table.

    Args:
        opportunities: List of ArbitrageOpportunity objects
        min_profit: Minimum profit threshold (for display context)
        tickers: Optional dictionary mapping symbol to Ticker (for liquidity display)
        liquidity_usage: Liquidity usage rate (0.0-1.0)
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
    table.add_column("最大安全金额", justify="right", style="yellow")

    # Pre-calculate safe amounts for main table
    safe_amounts_map = {}
    liquidity_usage_rate = Decimal(str(liquidity_usage))
    if tickers:
        for i, opp in enumerate(opportunities, 1):
            max_safe, _ = _calculate_max_safe_amount(opp, tickers, liquidity_usage_rate)
            safe_amounts_map[i] = max_safe

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

        # Use safe amount if available, otherwise use recommended
        display_amount = safe_amounts_map.get(i, opp.recommended_amount)

        # Add row to table
        table.add_row(
            str(i),
            path_str,
            f"{opp.expected_profit_rate:.2f}%",
            f"{display_amount:.2f}",
        )

    console.print(table)
    
    # Display detailed breakdown for each opportunity
    console.print()  # Empty line for spacing
    
    for i, opp in enumerate(opportunities, 1):
        # Calculate maximum safe amount based on liquidity constraints
        if tickers:
            max_safe_amount, _ = _calculate_max_safe_amount(opp, tickers, liquidity_usage_rate)
        else:
            max_safe_amount = opp.recommended_amount

        # Calculate step details using safe amount
        steps = _calculate_step_details(opp, tickers or {}, max_safe_amount)

        # Create detail table for this opportunity
        detail_table = Table(
            title=f"#{i} 交易路径详情",
            show_header=True,
            header_style="bold cyan",
            expand=False
        )
        detail_table.add_column("步骤", justify="center", style="cyan", no_wrap=True)
        detail_table.add_column("操作", justify="center", no_wrap=True)
        detail_table.add_column("交易对", justify="left", style="magenta", no_wrap=True)
        detail_table.add_column("价格", justify="right", style="yellow")
        detail_table.add_column("交易前", justify="right", style="white")
        detail_table.add_column("交易后", justify="right", style="white")
        detail_table.add_column("手续费", justify="right", style="dim")
        detail_table.add_column("可用流动性", justify="right", style="cyan")
        detail_table.add_column("使用率", justify="right", style="green")
        
        for step in steps:
            # Format type with emoji
            type_display = "🔴买入" if step["type"] == "buy" else "🔵卖出"

            # Format amounts with appropriate precision
            if step["amount_before"] < Decimal("1"):
                amount_before_str = f"{step['amount_before']:.6f} {step['currency_before']}"
            else:
                amount_before_str = f"{step['amount_before']:.2f} {step['currency_before']}"

            if step["amount_after"] < Decimal("1"):
                amount_after_str = f"{step['amount_after']:.6f} {step['currency_after']}"
            else:
                amount_after_str = f"{step['amount_after']:.2f} {step['currency_after']}"

            fee_str = f"{step['fee']:.6f}" if step["fee"] < Decimal("1") else f"{step['fee']:.2f}"

            # Format liquidity
            liquidity = step.get("available_liquidity", Decimal("0"))
            if liquidity < Decimal("1"):
                liquidity_str = f"{liquidity:.6f} {step.get('liquidity_currency', '')}"
            else:
                liquidity_str = f"{liquidity:.2f} {step.get('liquidity_currency', '')}"

            # Format usage rate with warning markers
            usage_rate = step.get("usage_rate", Decimal("0"))
            if usage_rate >= Decimal("50"):
                usage_str = f"[red bold]🚨 {usage_rate:.1f}%[/red bold]"
            elif usage_rate >= Decimal("30"):
                usage_str = f"[yellow]⚠️  {usage_rate:.1f}%[/yellow]"
            else:
                usage_str = f"{usage_rate:.1f}%"

            detail_table.add_row(
                f"{step['step']}",
                type_display,
                step["pair"],
                f"{step['price']:.6f}" if step["price"] < Decimal("10") else f"{step['price']:.2f}",
                amount_before_str,
                amount_after_str,
                fee_str,
                liquidity_str,
                usage_str
            )
        
        # Add summary row
        initial_amount = max_safe_amount
        final_amount = steps[-1]["amount_after"]
        profit_amount = final_amount - initial_amount
        profit_rate = opp.expected_profit_rate

        summary = (
            f"[bold green]💰 投入: {initial_amount:.2f} {opp.path.start_currency}[/bold green] → "
            f"[bold green]获得: {final_amount:.2f} {opp.path.start_currency}[/bold green] → "
            f"[bold yellow]利润: {profit_amount:+.2f} {opp.path.start_currency} ({profit_rate:+.2f}%)[/bold yellow]"
        )

        console.print(detail_table)
        console.print(summary)

        # Show liquidity constraint message if applicable
        if tickers and max_safe_amount < opp.recommended_amount:
            constraint_msg = (
                f"[yellow]ℹ️  流动性约束：理论建议 {opp.recommended_amount:.2f} {opp.path.start_currency}，"
                f"实际可用 {max_safe_amount:.2f} {opp.path.start_currency}[/yellow]"
            )
            console.print(constraint_msg)

        # Add liquidity analysis summary
        if tickers:
            # Find bottleneck step (highest usage rate)
            bottleneck_step = max(steps, key=lambda s: s.get("usage_rate", Decimal("0")))

            liquidity_summary_lines = []
            liquidity_summary_lines.append("[bold cyan]📊 流动性分析:[/bold cyan]")

            for step in steps:
                usage = step.get("usage_rate", Decimal("0"))
                liquidity = step.get("available_liquidity", Decimal("0"))
                liquidity_curr = step.get("liquidity_currency", "")

                if liquidity < Decimal("1"):
                    liq_str = f"{liquidity:.6f} {liquidity_curr}"
                else:
                    liq_str = f"{liquidity:.2f} {liquidity_curr}"

                # Mark high usage with warnings
                if usage >= Decimal("50"):
                    marker = "🚨"
                    style = "red"
                elif usage >= Decimal("30"):
                    marker = "⚠️ "
                    style = "yellow"
                else:
                    marker = "✓"
                    style = "green"

                liquidity_summary_lines.append(
                    f"   [{style}]{marker} 第{step['step']}步 {step['pair']}: "
                    f"使用 {usage:.1f}% (可用: {liq_str})[/{style}]"
                )

            # Add bottleneck warning if usage > 30%
            max_usage = bottleneck_step.get("usage_rate", Decimal("0"))
            if max_usage >= Decimal("30"):
                liquidity_summary_lines.append(
                    f"[yellow bold]⚠️  瓶颈: 第{bottleneck_step['step']}步 "
                    f"({bottleneck_step['pair']}) - 流动性使用率 {max_usage:.1f}%[/yellow bold]"
                )

            console.print("\n".join(liquidity_summary_lines))

        console.print()  # Empty line between opportunities
