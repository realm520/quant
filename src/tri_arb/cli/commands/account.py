"""Account management commands."""

import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Optional

import httpx
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
from tri_arb.storage.xt_websocket_models import XTAccountUpdate
from tri_arb.services.rest_data_service import RestDataService
from sqlalchemy import select, func

from tri_arb.storage.xt_rest_models import XTPerpBalance, XTPerpPosition
from tri_arb.config.metrics_loader import (
    MetricsConfig,
    MetricDefinition,
    load_metrics_config,
)
from tri_arb.metrics.prometheus import (
    ensure_metrics_server,
    update_balance_metrics,
    record_balance_query_status,
    update_position_metrics,
    update_active_orders_metrics,
)


async def _run_xt_watch_positions_async(
    interval: int,
    api_key: str,
    api_secret: str,
    symbol: Optional[str],
    debug: bool,
    lark_webhook: Optional[str] = None,
    lark_secret: Optional[str] = None,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """异步版本的 XT 仓位监控（用于多账号并发）."""
    from rich.table import Table
    from tri_arb.exchanges.xt_perp import XTPerpExchange
    from tri_arb.services.xt_rest_data_service import XTRestDataService

    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的仓位监控")
    console.print(f"[cyan]启动账号 {account_label} 的仓位监控[/cyan]")

    metrics_account = account_id or (account_name or "default")
    exchange_label = ExchangeName.XT.value
    exchange_type_label = ExchangeType.PERP.value
    ensure_metrics_server()

    db_manager = DatabaseManager(database_url=database_url)
    perp_exchange = XTPerpExchange(api_key=api_key, api_secret=api_secret)
    xt_rest_service = XTRestDataService(db_manager, account_id=account_id)

    normalized_target = None
    if symbol:
        normalized_target = symbol.replace("/", "").replace("_", "").replace("-", "").upper()

    async def fetch_positions(iteration_num: int):
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"\n[cyan][账号 {account_label}] 第 {iteration_num} 次查询 - {current_time}[/cyan]")

        try:
            positions = await perp_exchange.get_positions(symbol=None)
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取仓位失败:[/red] {exc}")
            logger.error("账号 %s watch-positions fetch error: %s", account_label, exc)
            if debug:
                console.print_exception()
            return

        if not positions:
            console.print(f"[yellow][账号 {account_label}] 当前无持仓[/yellow]")
            return

        position_table = Table(
            title=f"XT 合约账户仓位 - {account_label}",
            show_header=True,
            header_style="bold magenta",
        )
        position_table.add_column("Symbol", style="cyan")
        position_table.add_column("Side", style="white")
        position_table.add_column("Quantity", justify="right")
        position_table.add_column("Entry Price", justify="right")
        position_table.add_column("Mark Price", justify="right")
        position_table.add_column("Liquidation Price", justify="right")
        position_table.add_column("Unrealized PnL", justify="right")
        position_table.add_column("Realized PnL", justify="right")
        position_table.add_column("ROE", justify="right")
        position_table.add_column("Leverage", justify="right")

        positions_payload: list[dict[str, Any]] = []
        rows_added = 0

        for pos in positions:
            try:
                if hasattr(pos, "symbol"):
                    pos_symbol = pos.symbol
                    side = getattr(pos, "side", getattr(pos, "position_side", ""))
                    quantity = getattr(pos, "quantity", Decimal("0"))
                    entry_price = getattr(pos, "entry_price", Decimal("0"))
                    mark_price = getattr(pos, "mark_price", Decimal("0"))
                    unrealized_pnl = getattr(pos, "unrealized_pnl", Decimal("0"))
                    realized_pnl = getattr(pos, "realized_pnl", Decimal("0"))
                    margin = getattr(pos, "margin", Decimal("0"))
                    leverage = getattr(pos, "leverage", "")
                    liquidation_price = getattr(pos, "liquidation_price", Decimal("0"))
                else:
                    pos_symbol = pos.get("symbol", "")
                    side = pos.get("positionSide") or pos.get("side", "")
                    quantity = Decimal(str(pos.get("positionSize") or pos.get("positionAmt") or "0"))
                    entry_price = Decimal(str(pos.get("entryPrice") or "0"))
                    mark_price = Decimal(str(pos.get("calMarkPrice") or pos.get("markPrice") or "0"))
                    unrealized_pnl = Decimal(str(pos.get("floatingPL") or pos.get("unRealizedProfit") or pos.get("unrealizedPnl") or "0"))
                    realized_pnl = Decimal(str(pos.get("realizedProfit") or pos.get("realizedPnl") or "0"))
                    margin = Decimal(str(pos.get("isolatedMargin") or pos.get("margin") or "0"))
                    leverage = pos.get("leverage", "")
                    liquidation_price = Decimal(str(pos.get("breakPrice") or pos.get("liquidationPrice") or "0"))

                normalized_symbol = pos_symbol.replace("/", "").replace("_", "").replace("-", "").upper()
                if normalized_target and normalized_symbol != normalized_target:
                    continue

                roe = Decimal("0")
                if margin and margin != Decimal("0"):
                    roe = (unrealized_pnl / margin) * Decimal("100")

                unrealized_style = "green" if unrealized_pnl >= 0 else "red"
                realized_style = "green" if realized_pnl >= 0 else "red"
                roe_style = "green" if roe >= 0 else "red"

                position_table.add_row(
                    pos_symbol,
                    side,
                    f"{quantity:.8f}",
                    f"{entry_price:.8f}",
                    f"{mark_price:.8f}",
                    f"{liquidation_price:.8f}",
                    f"[{unrealized_style}]{unrealized_pnl:.8f}[/{unrealized_style}]",
                    f"[{realized_style}]{realized_pnl:.8f}[/{realized_style}]",
                    f"[{roe_style}]{roe:.2f}%[/{roe_style}]",
                    f"{leverage}x" if leverage else "-",
                )

                positions_payload.append(
                    {
                        "symbol": pos_symbol,
                        "positionSide": side,
                        "positionSize": str(quantity),
                        "entryPrice": str(entry_price),
                        "calMarkPrice": str(mark_price),
                        "floatingPL": str(unrealized_pnl),
                        "realizedProfit": str(realized_pnl),
                        "isolatedMargin": str(margin),
                        "leverage": leverage,
                        "roe": str(roe),
                        "breakPrice": str(liquidation_price),
                    }
                )
                rows_added += 1
            except Exception as inner_exc:
                logger.warning(f"账号 {account_label} 解析仓位记录失败", error=str(inner_exc))
                if debug:
                    console.print_exception()

        if rows_added == 0:
            if symbol:
                console.print(f"[yellow][账号 {account_label}] 未发现 {symbol} 的持仓[/yellow]")
            else:
                console.print(f"[yellow][账号 {account_label}] 当前无持仓[/yellow]")
            return

        console.print(position_table)
        console.print(f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]")

        await xt_rest_service.save_position_updates(
            positions_data=positions_payload,
            query_type="scheduled",
        )
        console.print(f"[green]✓[/green] [账号 {account_label}] 仓位数据 (perp) 已保存到 [cyan]xt_position_snapshot[/cyan]\n")

        update_position_metrics(
            exchange_label,
            exchange_type_label,
            metrics_account,
            positions_payload,
        )

        if lark_webhook:
            await _send_lark_alert(
                webhook_url=lark_webhook,
                secret=lark_secret,
                positions=positions_payload,
                timestamp=current_time,
                interval=interval,
                debug=debug,
            )

    async def _ensure_xt_rest_tables():
        # 不再需要按账号分表，统一使用 account_id 字段区分
        # 统一表已通过 create_tables() 创建
        pass

    iteration = 0
    try:
        console.print(f"[dim][账号 {account_label}] 正在初始化数据库表...[/dim]")
        await _ensure_xt_rest_tables()
        console.print(f"[green]✓[/green] [账号 {account_label}] 数据库表已就绪")
        
        console.print(f"[dim][账号 {account_label}] 正在连接交易所...[/dim]")
        await perp_exchange.connect()
        console.print(f"[green]✓[/green] [账号 {account_label}] 交易所连接成功\n")

        iteration = 1
        await fetch_positions(iteration)

        while True:
            await asyncio.sleep(interval * 60)
            iteration += 1
            await fetch_positions(iteration)

    except KeyboardInterrupt:
        console.print(f"\n[yellow][账号 {account_label}] 监控已停止[/yellow]")
        logger.info(f"账号 {account_label} 的监控已停止")
    except Exception as e:
        console.print(f"[red][账号 {account_label}] 监控异常:[/red] {e}")
        logger.error("账号 %s 的监控异常: %s", account_label, e, exc_info=True)
        if debug:
            console.print_exception()
    finally:
        try:
            await perp_exchange.disconnect()
        except Exception:
            pass


def _run_xt_watch_positions(
    interval: int,
    api_key: str,
    api_secret: str,
    symbol: Optional[str],
    debug: bool,
    lark_webhook: Optional[str] = None,
    lark_secret: Optional[str] = None,
    account_id: Optional[str] = None,
) -> None:
    """运行XT永续仓位定时监控并写入数据库."""
    from rich.table import Table
    from tri_arb.exchanges.xt_perp import XTPerpExchange
    from tri_arb.services.xt_rest_data_service import XTRestDataService

    console.print("[cyan]启动XT仓位定时监控服务[/cyan]")
    console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
    if symbol:
        console.print(f"[cyan]仅监控交易对: {symbol}[/cyan]")
    if account_id:
        console.print(f"[cyan]账号ID: {account_id}[/cyan]")
    console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")

    metrics_account = account_id or "default"
    exchange_label = ExchangeName.XT.value
    exchange_type_label = ExchangeType.PERP.value
    ensure_metrics_server()

    db_manager = DatabaseManager()
    perp_exchange = XTPerpExchange(api_key=api_key, api_secret=api_secret)
    xt_rest_service = XTRestDataService(db_manager, account_id=account_id)

    normalized_target = None
    if symbol:
        normalized_target = symbol.replace("/", "").replace("_", "").replace("-", "").upper()

    async def fetch_positions(iteration_num: int):
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"\n{'='*60}")
        console.print(f"[bold]第 {iteration_num} 次查询 - {current_time}[/bold]")
        console.print(f"{'='*60}\n")

        try:
            positions = await perp_exchange.get_positions(symbol=None)
        except Exception as exc:
            console.print(f"[red]获取仓位失败:[/red] {exc}")
            logger.error("watch-positions fetch error: %s", exc)
            if debug:
                console.print_exception()
            return

        if not positions:
            console.print("[yellow]当前无持仓[/yellow]")
            return

        position_table = Table(
            title="XT 合约账户仓位",
            show_header=True,
            header_style="bold magenta",
        )
        position_table.add_column("Symbol", style="cyan")
        position_table.add_column("Side", style="white")
        position_table.add_column("Quantity", justify="right")
        position_table.add_column("Entry Price", justify="right")
        position_table.add_column("Mark Price", justify="right")
        position_table.add_column("Liquidation Price", justify="right")
        position_table.add_column("Unrealized PnL", justify="right")
        position_table.add_column("Realized PnL", justify="right")
        position_table.add_column("ROE", justify="right")
        position_table.add_column("Leverage", justify="right")

        positions_payload: list[dict[str, Any]] = []
        rows_added = 0

        for pos in positions:
            try:
                if hasattr(pos, "symbol"):
                    pos_symbol = pos.symbol
                    side = getattr(pos, "side", getattr(pos, "position_side", ""))
                    quantity = getattr(pos, "quantity", Decimal("0"))
                    entry_price = getattr(pos, "entry_price", Decimal("0"))
                    mark_price = getattr(pos, "mark_price", Decimal("0"))
                    unrealized_pnl = getattr(pos, "unrealized_pnl", Decimal("0"))
                    realized_pnl = getattr(pos, "realized_pnl", Decimal("0"))
                    margin = getattr(pos, "margin", Decimal("0"))
                    leverage = getattr(pos, "leverage", "")
                    liquidation_price = getattr(pos, "liquidation_price", Decimal("0"))
                else:
                    pos_symbol = pos.get("symbol", "")
                    side = pos.get("positionSide") or pos.get("side", "")
                    quantity = Decimal(str(pos.get("positionSize") or pos.get("positionAmt") or "0"))
                    entry_price = Decimal(str(pos.get("entryPrice") or "0"))
                    mark_price = Decimal(str(pos.get("calMarkPrice") or pos.get("markPrice") or "0"))
                    unrealized_pnl = Decimal(str(pos.get("floatingPL") or pos.get("unRealizedProfit") or pos.get("unrealizedPnl") or "0"))
                    realized_pnl = Decimal(str(pos.get("realizedProfit") or pos.get("realizedPnl") or "0"))
                    margin = Decimal(str(pos.get("isolatedMargin") or pos.get("margin") or "0"))
                    leverage = pos.get("leverage", "")
                    liquidation_price = Decimal(str(pos.get("breakPrice") or pos.get("liquidationPrice") or "0"))

                normalized_symbol = pos_symbol.replace("/", "").replace("_", "").replace("-", "").upper()
                if normalized_target and normalized_symbol != normalized_target:
                    continue

                roe = Decimal("0")
                if margin and margin != Decimal("0"):
                    roe = (unrealized_pnl / margin) * Decimal("100")

                unrealized_style = "green" if unrealized_pnl >= 0 else "red"
                realized_style = "green" if realized_pnl >= 0 else "red"
                roe_style = "green" if roe >= 0 else "red"

                position_table.add_row(
                    pos_symbol,
                    side,
                    f"{quantity:.8f}",
                    f"{entry_price:.8f}",
                    f"{mark_price:.8f}",
                    f"{liquidation_price:.8f}",
                    f"[{unrealized_style}]{unrealized_pnl:.8f}[/{unrealized_style}]",
                    f"[{realized_style}]{realized_pnl:.8f}[/{realized_style}]",
                    f"[{roe_style}]{roe:.2f}%[/{roe_style}]",
                    f"{leverage}x" if leverage else "-",
                )

                positions_payload.append(
                    {
                        "symbol": pos_symbol,
                        "positionSide": side,
                        "positionSize": str(quantity),
                        "entryPrice": str(entry_price),
                        "calMarkPrice": str(mark_price),
                        "floatingPL": str(unrealized_pnl),
                        "realizedProfit": str(realized_pnl),
                        "isolatedMargin": str(margin),
                        "leverage": leverage,
                        "roe": str(roe),
                        "breakPrice": str(liquidation_price),
                    }
                )
                rows_added += 1
            except Exception as inner_exc:
                logger.warning("Failed to parse position record", error=str(inner_exc))
                if debug:
                    console.print_exception()

        if rows_added == 0:
            if symbol:
                console.print(f"[yellow]未发现 {symbol} 的持仓[/yellow]")
            else:
                console.print("[yellow]当前无持仓[/yellow]")
            return

        console.print(position_table)
        console.print(f"[dim]数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]")

        await xt_rest_service.save_position_updates(
            positions_data=positions_payload,
            query_type="scheduled",
        )
        # 使用 account_id 或默认值（此函数没有 account_label 变量）
        acc_label = account_id or "默认账号"
        console.print(f"[green]✓[/green] [账号 {acc_label}] 仓位数据 (perp) 已保存到 [cyan]xt_position_snapshot[/cyan]\n")

        update_position_metrics(
            exchange_label,
            exchange_type_label,
            metrics_account,
            positions_payload,
        )

        if lark_webhook:
            await _send_lark_alert(
                webhook_url=lark_webhook,
                secret=lark_secret,
                positions=positions_payload,
                timestamp=current_time,
                interval=interval,
                debug=debug,
            )

    async def _ensure_xt_rest_tables():
        # 不再需要按账号分表，统一使用 account_id 字段区分
        # 统一表已通过 create_tables() 创建
        pass

    async def run_scheduler():
        iteration = 0
        try:
            await _ensure_xt_rest_tables()
            if account_id:
                console.print(f"[green]✓[/green] 账号 {account_id} 的数据库表已就绪\n")
            else:
                console.print("[green]✓[/green] XT REST 数据表已就绪\n")

            await perp_exchange.connect()
            console.print("[green]✓[/green] 交易所连接成功\n")

            iteration = 1
            await fetch_positions(iteration)

            while True:
                await asyncio.sleep(interval * 60)
                iteration += 1
                await fetch_positions(iteration)

        except KeyboardInterrupt:
            console.print("\n[yellow]监控已停止[/yellow]")
        finally:
            try:
                await perp_exchange.disconnect()
            except Exception:
                pass
            await db_manager.close()

    asyncio.run(run_scheduler())


def _sign_payload(base: dict[str, Any], secret: str, use_milliseconds: bool) -> dict[str, Any]:
    """为 Lark 请求生成签名。"""
    multiplier = 1000 if use_milliseconds else 1
    lark_timestamp = str(int(time.time() * multiplier))
    string_to_sign = f"{lark_timestamp}\n{secret}"
    sign = base64.b64encode(
        hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    ).decode("utf-8")
    signed = {**base}
    signed["timestamp"] = lark_timestamp
    signed["sign"] = sign
    return signed


async def _send_lark_text(
    webhook_url: str,
    secret: Optional[str],
    text: str,
    debug: bool = False,
    success_message: Optional[str] = None,
) -> bool:
    """向 Lark 发送文本消息。"""
    if not webhook_url:
        return False

    base_body: dict[str, Any] = {
        "msg_type": "text",
        "content": {"text": text},
    }

    payload_attempts: list[dict[str, Any]] = []
    if secret:
        payload_attempts.append(_sign_payload(base_body, secret, use_milliseconds=False))
        payload_attempts.append(_sign_payload(base_body, secret, use_milliseconds=True))
    else:
        payload_attempts.append(base_body)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for attempt_idx, payload in enumerate(payload_attempts):
                response = await client.post(webhook_url, json=payload)
                response.raise_for_status()
                data = response.json()

                if data.get("code", 0) == 0:
                    if success_message:
                        console.print(success_message)
                    return True

                should_retry = (
                    secret is not None
                    and data.get("code") == 19021
                    and attempt_idx == 0
                )
                logger.warning(
                    "Lark 返回非零 code",
                    extra={
                        "lark_code": data.get("code"),
                        "lark_message": data.get("msg"),
                        "attempt": attempt_idx + 1,
                        "retry": should_retry,
                    },
                )
                console.print(f"[red]Lark 返回非零 code:[/red] {data.get('code')}")
                console.print(f"[red]Lark 返回消息:[/red] {data.get('msg')}")

                if should_retry:
                    console.print("[yellow]Lark 签名校验失败，尝试使用毫秒时间戳重试...[/yellow]")
                    continue

                return False
    except Exception as exc:
        logger.error(f"发送 Lark 告警失败: {exc}")
        if debug:
            console.print_exception()
    return False


async def _send_lark_alert(
    webhook_url: str,
    secret: Optional[str],
    positions: list[dict[str, Any]],
    timestamp: str,
    interval: int,
    debug: bool = False,
) -> None:
    """向 Lark 群发送仓位告警。"""
    if not positions:
        return

    try:
        selected = positions[:5]
        lines: list[str] = []

        for pos in selected:
            try:
                symbol = pos.get("symbol", "")
                side = pos.get("positionSide", "")
                mark_price = Decimal(pos.get("calMarkPrice") or pos.get("markPrice") or "0")
                liquidation_price = Decimal(pos.get("breakPrice") or pos.get("liquidationPrice") or "0")
                unrealized = Decimal(pos.get("floatingPL") or pos.get("unRealizedProfit") or "0")
                margin = Decimal(pos.get("isolatedMargin") or pos.get("margin") or "0")
                roe = Decimal(pos.get("roe") or "0")

                if liquidation_price and liquidation_price != Decimal("0"):
                    distance_pct = ((mark_price - liquidation_price) / liquidation_price) * Decimal("100")
                else:
                    distance_pct = Decimal("0")

                lines.append(
                    f"{symbol} [{side}] 标记价 {mark_price:.4f} | 爆仓价 {liquidation_price:.4f} | "
                    f"距爆仓 {distance_pct:.2f}% | ROE {roe:.2f}% | 未实现PnL {unrealized:.4f} | 保证金 {margin:.4f}"
                )
            except Exception as parse_exc:
                logger.debug(
                    "格式化 Lark 告警行失败",
                    extra={"error": str(parse_exc), "position": pos},
                )

        if not lines:
            return

        message = "[XT 仓位监控]\n时间: {ts}\n间隔: {interval} 分钟\n{details}".format(
            ts=timestamp,
            interval=interval,
            details="\n".join(lines),
        )
        await _send_lark_text(
            webhook_url=webhook_url,
            secret=secret,
            text=message,
            debug=debug,
            success_message="[green]✓[/green] Lark 告警发送成功\n",
        )
    except Exception as exc:
        logger.error(f"发送 Lark 告警失败: {exc}")
        if debug:
            console.print_exception()


async def _evaluate_metrics(
    metrics_config: Optional[MetricsConfig],
    db_manager: DatabaseManager,
    enable_lark: bool,
    default_webhook: Optional[str],
    default_secret: Optional[str],
    debug: bool,
) -> None:
    """Evaluate configured metrics and optionally send alerts."""
    if not metrics_config or not metrics_config.exchanges:
        return

    exchange_config = metrics_config.get_exchange("xt")
    if not exchange_config or not exchange_config.metrics:
        return

    for metric in exchange_config.metrics:
        if metric.type == "balance_volatility":
            result = await _evaluate_balance_volatility(metric, db_manager)
            if not result:
                continue

            severity = result["severity"]
            volatility = result["volatility"]
            window_minutes = result["window_minutes"]
            sample_count = result["sample_count"]
            warning_threshold = result["warning_threshold"]
            critical_threshold = result["critical_threshold"]

            logger.info(
                "余额波动率指标评估完成",
                extra={
                    "metric": metric.name,
                    "type": metric.type,
                    "severity": severity,
                    "volatility": str(volatility),
                    "samples": sample_count,
                    "window_minutes": window_minutes,
                },
            )

            # if severity == "NORMAL":
            #     continue

            message_lines = [
                "[XT 指标监控]",
                f"指标: {metric.name}",
                f"类型: 合约余额波动率",
                f"窗口: {window_minutes} 分钟 (样本 {sample_count} 条)",
                f"波动率: {float(volatility * Decimal('100')):.2f}%",
                f"预警阈值: {float(warning_threshold * Decimal('100')):.2f}%",
                f"致命阈值: {float(critical_threshold * Decimal('100')):.2f}%",
                f"当前级别: {severity}",
            ]

            message = "\n".join(message_lines)

            if enable_lark:
                webhook = metric.lark_webhook or default_webhook
                secret = metric.lark_secret or default_secret
                if webhook:
                    success = await _send_lark_text(
                        webhook_url=webhook,
                        secret=secret,
                        text=message,
                        debug=debug,
                        success_message="[green]✓[/green] Lark 指标告警已发送\n",
                    )
                    if not success:
                        logger.warning(
                            "指标告警发送失败",
                            extra={"metric": metric.name, "severity": severity},
                        )
                else:
                    logger.warning(
                        "指标达到阈值但未配置 Lark Webhook",
                        extra={"metric": metric.name, "severity": severity},
                    )
            else:
                logger.warning(
                    "指标达到阈值但 Lark 告警未启用",
                    extra={"metric": metric.name, "severity": severity},
                )
        elif metric.type in ("risk_ratio", "perp_risk_ratio"):
            result = await _evaluate_risk_ratio(metric, db_manager)
            if not result:
                continue

            severity = result["severity"]
            risk_ratio = result["risk_ratio"]
            available_margin = result["available_margin"]
            occupied_margin = result["occupied_margin"]
            floating_loss = result["floating_loss"]
            warning_threshold = result["warning_threshold"]
            critical_threshold = result["critical_threshold"]
            position_count = result["position_count"]

            logger.info(
                "风险率指标评估完成",
                extra={
                    "metric": metric.name,
                    "risk_ratio": str(risk_ratio),
                    "severity": severity,
                    "available_margin": str(available_margin),
                    "occupied_margin": str(occupied_margin),
                    "floating_loss": str(floating_loss),
                    "positions": position_count,
                },
            )

            message_lines = [
                "[XT 指标监控]",
                f"指标: {metric.name}",
                f"类型: 仓位风险率",
                f"最新仓位数: {position_count}",
                f"可用保证金: {available_margin:.4f}",
                f"占用保证金: {occupied_margin:.4f}",
                f"浮亏调整: {floating_loss:.4f}",
                f"风险率: {risk_ratio:.4f}",
                f"预警阈值: {warning_threshold:.4f}",
                f"致命阈值: {critical_threshold:.4f}",
                f"当前级别: {severity}",
            ]
            message = "\n".join(message_lines)

            if enable_lark:
                webhook = metric.lark_webhook or default_webhook
                secret = metric.lark_secret or default_secret
                if webhook:
                    success = await _send_lark_text(
                        webhook_url=webhook,
                        secret=secret,
                        text=message,
                        debug=debug,
                        success_message="[green]✓[/green] Lark 风险率通知已发送\n",
                    )
                    if not success:
                        logger.warning(
                            "风险率告警发送失败",
                            extra={"metric": metric.name, "severity": severity},
                        )
                else:
                    logger.warning(
                        "风险率达到阈值但未配置 Lark Webhook",
                        extra={"metric": metric.name, "severity": severity},
                    )
            else:
                logger.warning(
                    "风险率已评估但 Lark 告警未启用",
                    extra={"metric": metric.name, "severity": severity},
                )


async def _evaluate_balance_volatility(
    metric: MetricDefinition,
    db_manager: DatabaseManager,
) -> Optional[dict[str, Any]]:
    """Calculate intraday balance volatility for XT perpetual account."""
    window_minutes = max(metric.window_minutes, 0)
    if window_minutes <= 0:
        logger.debug(
            "指标窗口配置无效，跳过评估",
            extra={"metric": metric.name, "window_minutes": metric.window_minutes},
        )
        return None

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(minutes=window_minutes)

    async with db_manager.session() as session:
        stmt = (
            select(XTPerpBalance.total, XTPerpBalance.query_time)
            .where(XTPerpBalance.query_time >= start_time)
            .order_by(XTPerpBalance.query_time.asc())
        )
        result = await session.execute(stmt)
        rows = result.all()

    totals: list[Decimal] = []
    for total, _query_time in rows:
        if total is not None:
            totals.append(Decimal(total))

    sample_count = len(totals)
    if sample_count < 2:
        logger.debug(
            "样本数量不足，跳过指标评估",
            extra={"metric": metric.name, "sample_count": sample_count},
        )
        return None

    max_total = max(totals)
    min_total = min(totals)
    avg_total = sum(totals) / sample_count if sample_count else Decimal("0")

    if avg_total == 0:
        volatility = Decimal("0")
    else:
        volatility = (max_total - min_total) / avg_total

    warning_threshold = Decimal(str(metric.warning_threshold))
    critical_threshold = Decimal(str(metric.critical_threshold))

    severity = "NORMAL"
    if critical_threshold > 0 and volatility >= critical_threshold:
        severity = "CRITICAL"
    elif warning_threshold > 0 and volatility >= warning_threshold:
        severity = "WARNING"

    return {
        "severity": severity,
        "volatility": volatility,
        "window_minutes": window_minutes,
        "sample_count": sample_count,
        "warning_threshold": warning_threshold,
        "critical_threshold": critical_threshold,
    }


async def _evaluate_risk_ratio(
    metric: MetricDefinition,
    db_manager: DatabaseManager,
) -> Optional[dict[str, Any]]:
    """计算 XT 合约仓位风险率."""
    asset = str(metric.parameters.get("asset", "USDT")).upper()

    async with db_manager.session() as session:
        balance_stmt = (
            select(XTPerpBalance.free, XTPerpBalance.margin, XTPerpBalance.query_time)
            .where(XTPerpBalance.asset == asset)
            .order_by(XTPerpBalance.query_time.desc())
            .limit(1)
        )
        balance_result = await session.execute(balance_stmt)
        balance_row = balance_result.first()

        if not balance_row or balance_row[0] is None:
            logger.debug(
                "未找到合约余额记录，跳过风险率评估",
                extra={"metric": metric.name, "asset": asset},
            )
            return None

        available_margin = Decimal(str(balance_row[0]))
        margin_total = Decimal(str(balance_row[1])) if balance_row[1] is not None else Decimal("0")
        if available_margin <= 0:
            logger.warning(
                "可用保证金为0，无法计算风险率",
                extra={"metric": metric.name, "asset": asset},
            )
            return None

        latest_time_result = await session.execute(
            select(func.max(XTPerpPosition.query_time))
        )
        latest_query_time = latest_time_result.scalar()

        if latest_query_time is None:
            logger.debug(
                "未找到仓位记录，跳过风险率评估",
                extra={"metric": metric.name},
            )
            return None

        position_stmt = (
            select(
                XTPerpPosition.unrealized_pnl,
                XTPerpPosition.raw_data,
                XTPerpPosition.margin,
            )
            .where(XTPerpPosition.query_time == latest_query_time)
        )
        position_result = await session.execute(position_stmt)
        position_rows = position_result.all()

    if not position_rows:
        logger.debug(
            "仓位列表为空，风险率为0",
            extra={"metric": metric.name},
        )
        return None

    floating_loss = Decimal("0")
    position_count = 0
    position_margin_sum = Decimal("0")

    for (
        unrealized_val,
        raw_data,
        margin_val,
    ) in position_rows:
        unrealized = Decimal(str(unrealized_val)) if unrealized_val is not None else None
        margin = Decimal(str(margin_val)) if margin_val is not None else None

        if unrealized is None and raw_data:
            try:
                raw = json.loads(raw_data)
                unrealized_fallback = (
                    raw.get("floatingPL")
                    or raw.get("unRealizedProfit")
                    or raw.get("unrealizedPnl")
                )
                if unrealized_fallback is not None:
                    unrealized = Decimal(str(unrealized_fallback))
            except json.JSONDecodeError:
                logger.debug(
                    "解析仓位 raw_data 失败",
                    extra={"metric": metric.name},
                )

        if margin is None and raw_data:
            try:
                raw = json.loads(raw_data)
                margin_fallback = raw.get("isolatedMargin") or raw.get("margin")
                if margin_fallback is not None:
                    margin = Decimal(str(margin_fallback))
            except json.JSONDecodeError:
                pass

        if unrealized is None:
            unrealized = Decimal("0")
        if margin is None:
            margin = Decimal("0")

        floating_loss += max(Decimal("0"), -unrealized)
        position_margin_sum += max(Decimal("0"), margin)
        position_count += 1

    if margin_total <= 0:
        margin_total = position_margin_sum

    numerator = margin_total + floating_loss
    risk_ratio = numerator / available_margin if available_margin > 0 else Decimal("0")

    warning_threshold = Decimal(str(metric.warning_threshold))
    critical_threshold = Decimal(str(metric.critical_threshold))

    severity = "NORMAL"
    if critical_threshold > 0 and risk_ratio >= critical_threshold:
        severity = "CRITICAL"
    elif warning_threshold > 0 and risk_ratio >= warning_threshold:
        severity = "WARNING"

    return {
        "severity": severity,
        "risk_ratio": risk_ratio,
        "available_margin": available_margin,
        "occupied_margin": margin_total,
        "floating_loss": floating_loss,
        "warning_threshold": warning_threshold,
        "critical_threshold": critical_threshold,
        "position_count": position_count,
    }


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
    passphrase: Optional[str] = typer.Option(
        None,
        "--passphrase",
        help="OKX 交易所需要的 passphrase（覆盖环境变量）"
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
    ),
    lark_webhook: Optional[str] = typer.Option(
        None,
        "--lark-webhook",
        help="Lark群机器人Webhook URL，用于推送仓位告警"
    ),
    lark_secret: Optional[str] = typer.Option(
        None,
        "--lark-secret",
        help="Lark机器人签名密钥（若启用安全校验需提供）"
    ),
    enable_lark: bool = typer.Option(
        False,
        "--enable-lark",
        help="是否启用 Lark 告警推送（默认 False）"
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
        exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange, passphrase=passphrase)

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
    ),
    alert_webhook: Optional[str] = typer.Option(
        None,
        "--lark-webhook",
        help="Lark群机器人Webhook URL，用于推送仓位告警"
    ),
    alert_secret: Optional[str] = typer.Option(
        None,
        "--lark-secret",
        help="Lark机器人签名密钥（若启用安全校验需提供）"
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
        5,
        "--interval",
        "-i",
        help="查询间隔（分钟），默认5分钟"
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
        help="OKX 交易所需要的 passphrase（覆盖环境变量）"
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
    ),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="账号ID（可选），如果提供则优先使用配置文件里的账号信息"
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="账号配置文件路径（JSON格式）。如果提供，将从配置文件读取账号信息（API密钥等）"
    ),
    accounts: Optional[str] = typer.Option(
        None,
        "--accounts",
        help="多个账号ID（逗号分隔），例如: account_001,account_002。需要配合 --config 使用，只监控 enabled: true 的账号"
    ),
    all_accounts: bool = typer.Option(
        False,
        "--all-accounts",
        help="从配置文件读取所有启用的账号（enabled: true）并同时监控。需要配合 --config 使用"
    ),
):
    """定时查询账户余额（支持 XT / Binance / OKX / Gate，多账号自动路由）。"""
    try:
        if interval < 1:
            raise ValueError("查询间隔必须至少为1分钟")

        account_manager = None
        selected_account_config = None
        database_url: Optional[str] = None

        def ensure_account_manager():
            nonlocal account_manager
            if account_manager is None:
                from tri_arb.config.account_manager import AccountManager
                account_manager = AccountManager(config_path)

        def resolve_credentials(target_exchange: ExchangeName, key: Optional[str], secret: Optional[str], passphrase_value: Optional[str]) -> tuple[str, str, Optional[str]]:
            env_prefix = target_exchange.value.upper()
            final_key = key or os.getenv(f"{env_prefix}_API_KEY", "")
            final_secret = secret or os.getenv(f"{env_prefix}_API_SECRET", "")
            final_passphrase = passphrase_value
            if target_exchange == ExchangeName.OKX:
                final_passphrase = passphrase_value or os.getenv(f"{env_prefix}_PASSPHRASE", "")
            return final_key, final_secret, final_passphrase

        # 处理多账号模式
        if accounts or all_accounts:
            if not config_path:
                console.print("[red]错误:[/red] 多账号模式需要配合 --config 使用")
                raise typer.Exit(code=1)

            ensure_account_manager()
            requested_ids: list[str]
            if accounts:
                requested_ids = [acc_id.strip() for acc_id in accounts.split(",") if acc_id.strip()]
            else:
                requested_ids = [acc.account_id for acc in account_manager.get_enabled_accounts()]

            if not requested_ids:
                console.print("[red]错误:[/red] 没有可用的账号")
                raise typer.Exit(code=1)

            account_configs = []
            for acc_id in requested_ids:
                acc_config = account_manager.get_account(acc_id)
                if not acc_config:
                    console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号: {acc_id}，跳过")
                    continue
                if not acc_config.enabled:
                    console.print(f"[yellow]警告:[/yellow] 账号 {acc_id} 未启用（enabled: false），跳过")
                    continue
                account_configs.append(acc_config)

            if not account_configs:
                console.print("[red]错误:[/red] 没有可用的启用账号")
                raise typer.Exit(code=1)

            database_url = account_manager.global_settings.get("database_url")
            total_accounts = len(account_manager.get_all_accounts())
            console.print(f"[cyan]多账号监控模式（{len(account_configs)} 个账号，配置总数 {total_accounts}）[/cyan]")
            for acc in account_configs:
                console.print(f"  - {acc.account_id}: {acc.name} ({acc.exchange})")
            console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
            console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")

            async def run_multi_account_watch():
                tasks = []
                for acc in account_configs:
                    try:
                        acc_exchange = ExchangeName(acc.exchange.lower())
                    except ValueError:
                        console.print(f"[yellow]警告:[/yellow] 账号 {acc.account_id} 使用未支持的交易所 {acc.exchange}，跳过")
                        continue

                    task = asyncio.create_task(
                        _run_watch_balance_async(
                            exchange=acc_exchange.value,
                            interval=interval,
                            api_key=acc.api_key,
                            api_secret=acc.api_secret,
                            exchange_type=exchange_type,
                            output=output,
                            debug=debug,
                            account_id=acc.account_id,
                            account_name=acc.name,
                            database_url=database_url,
                            passphrase=getattr(acc, "passphrase", None),
                        )
                    )
                    tasks.append(task)
                    await asyncio.sleep(0.5)

                if not tasks:
                    console.print("[red]错误:[/red] 选择的账号交易所暂未支持 watch-balance 功能")
                    return

                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                except KeyboardInterrupt:
                    console.print("\n[yellow]监控已停止[/yellow]")
                except Exception as exc:
                    console.print(f"[red]多账号监控异常:[/red] {exc}")
                    logger.error("多账号 watch-balance 异常: %s", exc)
                    if debug:
                        console.print_exception()

            asyncio.run(run_multi_account_watch())
            return

        # 单账号：尝试从配置文件读取账号信息
        if config_path and account_id:
            try:
                ensure_account_manager()
                account_config = account_manager.get_account(account_id)
                if account_config:
                    selected_account_config = account_config
                    if not account_config.enabled:
                        console.print(f"[yellow]警告:[/yellow] 账号 {account_id} 未启用（enabled: false）")
                    try:
                        exchange = ExchangeName(account_config.exchange.lower())
                    except ValueError:
                        console.print(f"[red]错误:[/red] 账号 {account_id} 使用未支持的交易所 {account_config.exchange}")
                        raise typer.Exit(code=1)
                    if not api_key:
                        api_key = account_config.api_key
                    if not api_secret:
                        api_secret = account_config.api_secret
                    if not passphrase and account_config.passphrase:
                        passphrase = account_config.passphrase
                    database_url = account_manager.global_settings.get("database_url")
                    console.print(f"[cyan]从配置文件加载账号: {account_id} ({account_config.name})[/cyan]")
                else:
                    console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号 {account_id}，使用命令行参数或环境变量")
            except Exception as exc:
                console.print(f"[yellow]警告:[/yellow] 读取配置文件失败: {exc}，使用命令行参数或环境变量")

        final_api_key, final_api_secret, final_passphrase = resolve_credentials(exchange, api_key, api_secret, passphrase)
        if not final_api_key or not final_api_secret:
            console.print(f"[red]错误:[/red] 缺少 {exchange.value.upper()} API 密钥配置")
            console.print("\n请设置环境变量或使用命令行参数:")
            console.print(f"  环境变量: export {exchange.value.upper()}_API_KEY=your_key && export {exchange.value.upper()}_API_SECRET=your_secret")
            console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
            console.print("  配置文件: --config config/accounts.json --account-id <account_id>")
            raise typer.Exit(code=1)

        account_label = selected_account_config.name if selected_account_config else None
        account_ref = selected_account_config.account_id if selected_account_config else account_id

        asyncio.run(
            _run_watch_balance_async(
                exchange=exchange.value,
                interval=interval,
                api_key=final_api_key,
                api_secret=final_api_secret,
                exchange_type=exchange_type,
                output=output,
                debug=debug,
                account_id=account_ref,
                account_name=account_label,
                database_url=database_url,
                passphrase=final_passphrase,
            )
        )

    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
    except ValueError as exc:
        error_msg = str(exc) if str(exc) else "配置错误，请检查交易所和API凭证"
        console.print(f"[red]配置错误:[/red] {error_msg}")
        raise typer.Exit(code=1)
    except Exception as exc:
        if debug:
            console.print_exception()
        else:
            error_msg = str(exc) if str(exc) else f"未知错误: {type(exc).__name__}"
            console.print(f"[red]错误:[/red] {error_msg}")
        raise typer.Exit(code=1)

async def _run_xt_watch_balance_async(
    interval: int,
    api_key: str,
    api_secret: str,
    exchange_type: ExchangeType,
    output: str,
    debug: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """异步版本的 XT 余额监控（用于多账号并发）."""
    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的余额监控")

    exchange_instance = create_exchange(exchange_type, api_key, api_secret, ExchangeName.XT)
    db_manager = DatabaseManager(database_url=database_url)
    metrics_account = account_id or (account_name or "default")
    exchange_label = ExchangeName.XT.value
    exchange_type_label = exchange_type.value
    ensure_metrics_server()
    metrics_account = account_id or (account_name or "default")
    exchange_label = ExchangeName.XT.value
    exchange_type_label = exchange_type.value
    ensure_metrics_server()

    async def watch_loop():
        iteration = 0
        metrics_account = account_id or (account_name or "default")
        exchange_label = ExchangeName.XT.value
        exchange_type_label = exchange_type.value
        ensure_metrics_server()
        try:
            await exchange_instance.connect()
            # 确保所需表存在（统一表，不再需要按账号分表）
            try:
                await db_manager.create_tables()
                logger.info(f"账号 {account_label} 的数据库表已就绪")
            except Exception as init_exc:
                logger.warning(f"账号 {account_label} 初始化数据库表失败: {init_exc}")

            while True:
                iteration += 1
                current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                console.print(f"\n[cyan][账号 {account_label}] 第 {iteration} 次查询 - {current_time}[/cyan]")

                try:
                    balance_data = await exchange_instance.get_balance()
                    record_balance_query_status(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        success=True,
                    )
                    update_balance_metrics(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        balance_data,
                    )
                    if not balance_data:
                        console.print(f"[yellow][账号 {account_label}] 账户余额为空或所有币种余额为0[/yellow]")
                    else:
                        # 根据输出格式显示
                        if output == "json":
                            print_json(balance_data)
                        else:  # table (default)
                            format_balance_table(balance_data, exchange_instance)

                        # 保存到数据库
                        try:
                            now = datetime.datetime.utcnow()
                            for currency, data in balance_data.items():
                                available = Decimal(str(data.get("available", 0)))
                                frozen = Decimal(str(data.get("frozen", 0)))
                                total = Decimal(str(data.get("total", 0)))
                                raw_json = json.dumps(data, default=str)

                                async with db_manager.session() as session:
                                    record = XTAccountUpdate(
                                        update_time=now,
                                        account_id=account_id,  # 使用统一表 + account_id
                                        currency=currency.upper(),
                                        available=available,
                                        frozen=frozen,
                                        total=total,
                                        raw_data=raw_json,
                                    )
                                    session.add(record)
                                    # 提交由 session 上下文管理器自动处理
                                    logger.info(f"账号 {account_label} 余额已保存到数据库: {currency.upper()}")
                                    console.print(f"[green]✓[/green] [账号 {account_label}] 余额数据 ({exchange_type.value}) 已保存到 [cyan]xt_account_update[/cyan]: {currency.upper()}")
                        except Exception as save_exc:
                            logger.warning(f"账号 {account_label} 保存余额到数据库失败: {save_exc}")
                            console.print(f"[red]✗[/red] [账号 {account_label}] 保存余额失败: {save_exc}")

                        next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval)
                        console.print(f"[dim][账号 {account_label}] 下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")

                except Exception as e:
                    record_balance_query_status(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        success=False,
                    )
                    console.print(f"[red][账号 {account_label}] 查询失败:[/red] {e}")
                    if debug:
                        console.print_exception()

                console.print(f"[dim][账号 {account_label}] 等待 {interval} 分钟...[/dim]")
                await asyncio.sleep(interval * 60)

        except KeyboardInterrupt:
            logger.info(f"账号 {account_label} 的监控已停止")
        finally:
            await exchange_instance.disconnect()

    await watch_loop()


async def _run_watch_balance_async(
    exchange: str,
    interval: int,
    api_key: str,
    api_secret: str,
    exchange_type: ExchangeType,
    output: str,
    debug: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
    passphrase: Optional[str] = None,
) -> None:
    """通用的多交易所余额监控函数（用于多账号并发）.
    
    Args:
        exchange: 交易所名称 (xt, binance, okx, gate)
        interval: 查询间隔（分钟）
        api_key: API密钥
        api_secret: API密钥
        exchange_type: 交易类型 (spot, perp)
        output: 输出格式 (table, json)
        debug: 是否启用调试模式
        account_id: 账号ID（可选）
        account_name: 账号名称（可选）
        database_url: 数据库连接URL（可选）
    """
    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的余额监控 (交易所: {exchange})")
    
    # 根据交易所名称创建对应的ExchangeName枚举
    exchange_name_map = {
        "xt": ExchangeName.XT,
        "binance": ExchangeName.BINANCE,
        "okx": ExchangeName.OKX,
        "gate": ExchangeName.GATE,
    }
    
    exchange_name = exchange_name_map.get(exchange.lower())
    if not exchange_name:
        raise ValueError(f"不支持的交易所: {exchange}，支持的交易所: {', '.join(exchange_name_map.keys())}")
    
    # 对于XT交易所，使用专门的实现（支持账号特定表）
    if exchange.lower() == "xt":
        await _run_xt_watch_balance_async(
            interval=interval,
            api_key=api_key,
            api_secret=api_secret,
            exchange_type=exchange_type,
            output=output,
            debug=debug,
            account_id=account_id,
            account_name=account_name,
            database_url=database_url,
        )
        return
    
    # 对于其他交易所，使用通用实现
    await _run_generic_watch_balance_async(
        exchange_name=exchange_name,
        interval=interval,
        api_key=api_key,
        api_secret=api_secret,
        exchange_type=exchange_type,
        output=output,
        debug=debug,
        account_id=account_id,
        account_name=account_name,
        database_url=database_url,
        passphrase=passphrase,
    )


async def _run_generic_watch_balance_async(
    exchange_name: ExchangeName,
    interval: int,
    api_key: str,
    api_secret: str,
    exchange_type: ExchangeType,
    output: str,
    debug: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
    passphrase: Optional[str] = None,
) -> None:
    """通用的多交易所余额监控函数（用于非XT交易所）.
    
    Args:
        exchange_name: 交易所名称枚举
        interval: 查询间隔（分钟）
        api_key: API密钥
        api_secret: API密钥
        exchange_type: 交易类型 (spot, perp)
        output: 输出格式 (table, json)
        debug: 是否启用调试模式
        account_id: 账号ID（可选）
        account_name: 账号名称（可选）
        database_url: 数据库连接URL（可选）
    """
    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的余额监控 ({exchange_name.value})")
    
    exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange_name, passphrase=passphrase)
    db_manager = DatabaseManager(database_url=database_url)
    rest_data_service = RestDataService(db_manager)
    metrics_account = account_id or (account_name or "default")
    exchange_label = exchange_name.value
    exchange_type_label = exchange_type.value
    ensure_metrics_server()
    
    async def watch_loop():
        iteration = 0
        try:
            await exchange_instance.connect()
            # 确保所需表存在（使用默认表，不支持账号特定表）
            try:
                await db_manager.create_tables()
            except Exception as init_exc:
                logger.warning(f"账号 {account_label} 初始化数据库表失败: {init_exc}")
            
            while True:
                iteration += 1
                current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                console.print(f"\n[cyan][账号 {account_label}] 第 {iteration} 次查询 - {current_time}[/cyan]")
                
                try:
                    balance_data = await exchange_instance.get_balance()
                    record_balance_query_status(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        success=True,
                    )
                    update_balance_metrics(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        balance_data,
                    )
                    
                    if not balance_data:
                        console.print(f"[yellow][账号 {account_label}] 账户余额为空或所有币种余额为0[/yellow]")
                    else:
                        # 根据输出格式显示
                        if output == "json":
                            print_json(balance_data)
                        else:  # table (default)
                            format_balance_table(balance_data, exchange_instance)
                        
                        # 保存到数据库（使用 exchange-specific REST 表，如 binance_balance_rest）
                        try:
                            await rest_data_service.save_balance_query(
                                exchange=exchange_name.value,
                                exchange_type=exchange_type.value,
                                balances_data=balance_data,
                                query_type="scheduled",
                                account_id=account_id,
                            )
                            console.print(
                                f"[green]✓[/green] [账号 {account_label}] 余额数据 ({exchange_type.value}) 已保存到 [cyan]{exchange_name.value}_account_snapshot[/cyan]"
                            )
                        except Exception as save_exc:
                            logger.warning(
                                f"账号 {account_label} 保存余额失败: {save_exc}",
                                extra={"exchange": exchange_name.value, "account_id": account_id},
                            )
                            console.print(f"[red]✗[/red] [账号 {account_label}] 保存余额失败: {save_exc}")
                        
                        next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval)
                        console.print(f"[dim][账号 {account_label}] 下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
                
                except Exception as e:
                    console.print(f"[red][账号 {account_label}] 查询失败:[/red] {e}")
                    logger.error("账号 %s watch-balance query error: %s", account_label, e)
                    if debug:
                        console.print_exception()
                
                console.print(f"[dim][账号 {account_label}] 等待 {interval} 分钟...[/dim]")
                await asyncio.sleep(interval * 60)
        
        except KeyboardInterrupt:
            console.print(f"\n[yellow][账号 {account_label}] 监控已停止[/yellow]")
            raise
        except Exception as e:
            console.print(f"[red][账号 {account_label}] 监控异常:[/red] {e}")
            logger.error("账号 %s watch-balance error: %s", account_label, e)
            if debug:
                console.print_exception()
            raise
        finally:
            try:
                await exchange_instance.disconnect()
            except Exception:
                pass
    
    await watch_loop()


async def _run_binance_watch_account_async(
    interval_minutes: int,
    api_key: str,
    api_secret: str,
    debug: bool,
    enable_lark: bool,
    lark_webhook: Optional[str],
    lark_secret: Optional[str],
    metrics_config: Optional[str],
    enable_metrics: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """Binance 账户监控实现（spot + perp + positions）."""
    from rich.table import Table
    from tri_arb.exchanges.binance_spot import BinanceSpotExchange
    from tri_arb.exchanges.binance_perp import BinancePerpExchange

    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的 Binance 账户监控")

    if enable_lark:
        console.print("[yellow]提示:[/yellow] Binance 模式暂不支持 Lark 告警，选项已忽略。")
    if enable_metrics:
        console.print("[yellow]提示:[/yellow] Binance 模式暂不支持指标评估，选项已忽略。")

    db_manager = DatabaseManager(database_url=database_url)
    rest_data_service = RestDataService(db_manager)
    metrics_account = account_id or (account_name or "default")
    exchange_label = "binance"
    exchange_type_label = "perp"  # Binance watch-account 主要监控 perp
    ensure_metrics_server()
    spot_exchange = BinanceSpotExchange(api_key=api_key, api_secret=api_secret)
    perp_exchange = BinancePerpExchange(api_key=api_key, api_secret=api_secret)

    async def fetch_and_display(iteration_num: int):
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"\n[cyan][账号 {account_label}] 第 {iteration_num} 次查询 - {current_time}[/cyan]")

        # Spot balances
        try:
            spot_balances = await spot_exchange.get_balance()
            if spot_balances:
                spot_table = Table(
                    title=f"Binance 现货账户余额 - {account_label}",
                    show_header=True,
                    header_style="bold magenta",
                )
                spot_table.add_column("Currency", style="cyan", width=12)
                spot_table.add_column("Available", justify="right", style="green")
                spot_table.add_column("Frozen", justify="right", style="yellow")
                spot_table.add_column("Total", justify="right", style="white")

                for currency, data in spot_balances.items():
                    available = Decimal(str(data.get("available", 0)))
                    frozen = Decimal(str(data.get("frozen", 0)))
                    total = Decimal(str(data.get("total", available + frozen)))
                    spot_table.add_row(
                        currency,
                        f"{available:.8f}",
                        f"{frozen:.8f}",
                        f"{total:.8f}",
                    )

                console.print(spot_table)
                console.print(
                    f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n"
                )

                await rest_data_service.save_balance_query(
                    exchange="binance",
                    exchange_type="spot",
                    balances_data=spot_balances,
                    query_type="scheduled",
                    account_id=account_id,
                )
                console.print(f"[green]✓[/green] [账号 {account_label}] 余额数据 (spot) 已保存到 [cyan]binance_account_snapshot[/cyan]")
                # 更新 Prometheus 指标
                update_balance_metrics(
                    "binance",
                    "spot",
                    metrics_account,
                    spot_balances,
                )
            else:
                console.print(f"[yellow][账号 {account_label}] Binance 现货账户余额为空[/yellow]")
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取现货余额失败:[/red] {exc}")
            if debug:
                console.print_exception()

        # Perp balances
        try:
            perp_balances = await perp_exchange.get_balance()
            if perp_balances:
                perp_table = Table(
                    title=f"Binance 合约账户余额 - {account_label}",
                    show_header=True,
                    header_style="bold magenta",
                )
                perp_table.add_column("Currency", style="cyan", width=12)
                perp_table.add_column("Available", justify="right", style="green")
                perp_table.add_column("Frozen", justify="right", style="yellow")
                perp_table.add_column("Total", justify="right", style="white")
                perp_table.add_column("Unrealized PnL", justify="right")

                for currency, data in perp_balances.items():
                    available = Decimal(str(data.get("available", 0)))
                    frozen = Decimal(str(data.get("frozen", 0)))
                    total = Decimal(str(data.get("total", 0)))
                    unrealized = Decimal(str(data.get("unrealized_pnl", 0)))
                    perp_table.add_row(
                        currency,
                        f"{available:.8f}",
                        f"{frozen:.8f}",
                        f"{total:.8f}",
                        f"{unrealized:.8f}",
                    )

                console.print(perp_table)
                console.print(
                    f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n"
                )

                await rest_data_service.save_balance_query(
                    exchange="binance",
                    exchange_type="perp",
                    balances_data=perp_balances,
                    query_type="scheduled",
                    account_id=account_id,
                )
                console.print(f"[green]✓[/green] [账号 {account_label}] 余额数据 (perp) 已保存到 [cyan]binance_account_snapshot[/cyan]")
                # 更新 Prometheus 指标
                update_balance_metrics(
                    "binance",
                    "perp",
                    metrics_account,
                    perp_balances,
                )
            else:
                console.print(f"[yellow][账号 {account_label}] Binance 合约账户余额为空[/yellow]")
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取合约余额失败:[/red] {exc}")
            if debug:
                console.print_exception()

        # Positions
        try:
            positions = await perp_exchange.get_positions()
            if positions:
                position_table = Table(
                    title=f"Binance 合约仓位 - {account_label}",
                    show_header=True,
                    header_style="bold magenta",
                )
                position_table.add_column("Symbol", style="cyan")
                position_table.add_column("Side", style="yellow")
                position_table.add_column("Quantity", justify="right")
                position_table.add_column("Entry", justify="right")
                position_table.add_column("Mark", justify="right")
                position_table.add_column("Unrealized PnL", justify="right")
                position_table.add_column("Leverage", justify="right")

                formatted_positions: list[dict[str, Any]] = []
                for pos in positions:
                    qty = Decimal(str(pos.get("positionAmt", "0")))
                    entry = Decimal(str(pos.get("entryPrice", "0")))
                    mark = Decimal(str(pos.get("markPrice", "0")))
                    unrealized = Decimal(str(pos.get("unRealizedProfit", "0")))
                    side = pos.get("positionSide", "BOTH") or "BOTH"
                    leverage = pos.get("leverage", "1")

                    position_table.add_row(
                        pos.get("symbol", ""),
                        side,
                        f"{qty:.8f}",
                        f"{entry:.4f}",
                        f"{mark:.4f}",
                        f"{unrealized:.4f}",
                        str(leverage),
                    )
                    formatted_positions.append(pos)

                console.print(position_table)
                console.print(
                    f"[dim][账号 {account_label}] 仓位获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n"
                )

                await rest_data_service.save_positions_query(
                    exchange="binance",
                    exchange_type="perp",
                    positions_data=formatted_positions,
                    query_type="scheduled",
                    account_id=account_id,
                )
                console.print(f"[green]✓[/green] [账号 {account_label}] 仓位数据 (perp) 已保存到 [cyan]binance_position_snapshot[/cyan]")
                # 更新 Prometheus 指标
                update_position_metrics(
                    "binance",
                    "perp",
                    metrics_account,
                    formatted_positions,
                )
            else:
                console.print(f"[yellow][账号 {account_label}] Binance 当前无持仓[/yellow]")
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取合约仓位失败:[/red] {exc}")
            if debug:
                console.print_exception()

        # 查询活跃订单并更新 metrics（当前挂单数量）
        try:
            active_orders = await perp_exchange.get_open_orders(None)
            # 更新 Prometheus metrics
            ensure_metrics_server()
            try:
                update_active_orders_metrics(
                    exchange="binance",
                    exchange_type="perp",
                    account_id=metrics_account,
                    orders=active_orders if active_orders else [],
                )
            except Exception as metric_error:
                logger.error(f"Failed to update active orders metrics: {metric_error}", exc_info=True)
        except Exception as exc:
            logger.debug(f"获取活跃订单失败: {exc}")

        next_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)
        console.print(f"[dim]下次查询: {next_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
        console.print(f"[dim]等待 {interval_minutes} 分钟...[/dim]\n")

    async def watch_loop():
        iteration = 0
        try:
            await spot_exchange.connect()
            await perp_exchange.connect()
            while True:
                iteration += 1
                await fetch_and_display(iteration)
                await asyncio.sleep(interval_minutes * 60)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            console.print(f"\n[yellow][账号 {account_label}] 监控已停止[/yellow]")
            raise
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 监控异常:[/red] {exc}")
            logger.error("Binance watch-account loop error: %s", exc)
            if debug:
                console.print_exception()
            raise
        finally:
            try:
                await spot_exchange.disconnect()
            except Exception:
                pass
            try:
                await perp_exchange.disconnect()
            except Exception:
                pass

    await watch_loop()


@app.command("watch-account")
def watch_account(
    exchange: ExchangeName = typer.Option(
        ExchangeName.XT,
        "--exchange",
        "-x",
        help="交易所 (xt, binance, okx, gate)，默认 xt"
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
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    ),
    enable_lark: bool = typer.Option(
        False,
        "--enable-lark",
        help="启用 Lark 告警推送（需配置 webhook）"
    ),
    interval_minutes: int = typer.Option(
        10,
        "--interval",
        "-i",
        help="查询间隔（分钟），默认 10 分钟"
    ),
    lark_webhook: Optional[str] = typer.Option(
        None,
        "--lark-webhook",
        help="Lark 群机器人 Webhook，未提供时可使用环境变量 LARK_WEBHOOK_URL"
    ),
    lark_secret: Optional[str] = typer.Option(
        None,
        "--lark-secret",
        help="Lark 机器人签名密钥（可选；未提供则不做签名）"
    ),
    metrics_config: Optional[str] = typer.Option(
        None,
        "--metrics-config",
        help="指标配置文件路径（YAML）。未提供时可使用环境变量 METRICS_CONFIG_PATH"
    ),
    enable_metrics: bool = typer.Option(
        True,
        "--enable-metrics/--disable-metrics",
        help="是否启用指标评估（默认启用）"
    ),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="账号ID（可选），如果提供则优先使用配置文件里的账号信息"
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="账号配置文件路径（JSON格式）。如果提供，将从配置文件读取账号信息（API密钥、Lark配置、指标配置等）"
    ),
    accounts: Optional[str] = typer.Option(
        None,
        "--accounts",
        help="多个账号ID（逗号分隔），例如: account_001,account_002。需要配合 --config 使用，只监控 enabled: true 的账号"
    ),
    all_accounts: bool = typer.Option(
        False,
        "--all-accounts",
        help="从配置文件读取所有启用的账号（enabled: true）并同时监控。需要配合 --config 使用"
    ),
):
    """定时获取账户数据（现货/合约余额 + 仓位，支持 XT 与 Binance 多账号）。"""
    try:
        if interval_minutes <= 0:
            console.print("[red]错误:[/red] 查询间隔必须大于 0 分钟")
            raise typer.Exit(code=1)

        account_manager = None
        selected_account_config = None
        database_url: Optional[str] = None

        def ensure_account_manager():
            nonlocal account_manager
            if account_manager is None:
                from tri_arb.config.account_manager import AccountManager
                account_manager = AccountManager(config_path)

        def resolve_credentials(target_exchange: ExchangeName, key: Optional[str], secret: Optional[str]) -> tuple[str, str]:
            env_prefix = target_exchange.value.upper()
            final_key = key or os.getenv(f"{env_prefix}_API_KEY", "")
            final_secret = secret or os.getenv(f"{env_prefix}_API_SECRET", "")
            return final_key, final_secret

        # 多账号模式
        if accounts or all_accounts:
            if not config_path:
                console.print("[red]错误:[/red] 多账号模式需要配合 --config 使用")
                raise typer.Exit(code=1)

            ensure_account_manager()
            requested_ids = [acc_id.strip() for acc_id in (accounts.split(",") if accounts else []) if acc_id.strip()]
            if all_accounts:
                requested_ids = [acc.account_id for acc in account_manager.get_enabled_accounts()]

            if not requested_ids:
                console.print("[red]错误:[/red] 没有可用的账号")
                raise typer.Exit(code=1)

            account_configs = []
            for acc_id in requested_ids:
                acc_config = account_manager.get_account(acc_id)
                if not acc_config:
                    console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号: {acc_id}，跳过")
                    continue
                if not acc_config.enabled:
                    console.print(f"[yellow]警告:[/yellow] 账号 {acc_id} 未启用（enabled: false），跳过")
                    continue
                account_configs.append(acc_config)

            if not account_configs:
                console.print("[red]错误:[/red] 没有可用的启用账号")
                raise typer.Exit(code=1)

            database_url = account_manager.global_settings.get("database_url")
            total_accounts = len(account_manager.get_all_accounts())
            console.print(f"[cyan]多账号监控模式（{len(account_configs)} 个账号，配置总数 {total_accounts}）[/cyan]")
            for acc in account_configs:
                console.print(f"  - {acc.account_id}: {acc.name} ({acc.exchange})")
            console.print(f"[cyan]查询间隔: {interval_minutes} 分钟[/cyan]")
            console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")

            async def run_multi_account_watch():
                tasks = []
                for acc in account_configs:
                    try:
                        acc_exchange = ExchangeName(acc.exchange.lower())
                    except ValueError:
                        console.print(f"[yellow]警告:[/yellow] 账号 {acc.account_id} 使用未支持的交易所 {acc.exchange}，跳过")
                        continue

                    if acc_exchange == ExchangeName.XT:
                        task = asyncio.create_task(
                            _run_xt_watch_account_async(
                                interval_minutes=interval_minutes,
                                api_key=acc.api_key,
                                api_secret=acc.api_secret,
                                debug=debug,
                                enable_lark=enable_lark,
                                lark_webhook=acc.lark_webhook if enable_lark else None,
                                lark_secret=acc.lark_secret if enable_lark else None,
                                metrics_config=metrics_config,
                                enable_metrics=enable_metrics,
                                account_id=acc.account_id,
                                account_name=acc.name,
                                database_url=database_url,
                            )
                        )
                    elif acc_exchange == ExchangeName.BINANCE:
                        task = asyncio.create_task(
                            _run_binance_watch_account_async(
                                interval_minutes=interval_minutes,
                                api_key=acc.api_key,
                                api_secret=acc.api_secret,
                                debug=debug,
                                enable_lark=enable_lark,
                                lark_webhook=acc.lark_webhook if enable_lark else None,
                                lark_secret=acc.lark_secret if enable_lark else None,
                                metrics_config=metrics_config,
                                enable_metrics=enable_metrics,
                                account_id=acc.account_id,
                                account_name=acc.name,
                                database_url=database_url,
                            )
                        )
                    else:
                        console.print(f"[yellow]警告:[/yellow] 账号 {acc.account_id} 的交易所 {acc_exchange.value} 暂不支持 watch-account，跳过")
                        continue

                    tasks.append(task)
                    await asyncio.sleep(0.5)

                if not tasks:
                    console.print("[red]错误:[/red] 选择的账号交易所暂未支持 watch-account 功能")
                    return

                try:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for idx, result in enumerate(results):
                        if isinstance(result, Exception):
                            console.print(f"[red]账号 {account_configs[idx].account_id} 监控任务异常:[/red] {result}")
                            logger.error("账号 %s watch-account 任务异常: %s", account_configs[idx].account_id, result)
                            if debug:
                                console.print_exception()
                except KeyboardInterrupt:
                    console.print("\n[yellow]监控已停止[/yellow]")
                except Exception as exc:
                    console.print(f"[red]多账号监控异常:[/red] {exc}")
                    logger.error("多账号 watch-account 异常: %s", exc)
                    if debug:
                        console.print_exception()

            asyncio.run(run_multi_account_watch())
            return

        # 单账号：尝试从配置文件读取账号信息
        if config_path and account_id:
            try:
                ensure_account_manager()
                account_config = account_manager.get_account(account_id)
                if account_config:
                    selected_account_config = account_config
                    if not account_config.enabled:
                        console.print(f"[yellow]警告:[/yellow] 账号 {account_id} 未启用（enabled: false）")
                    try:
                        exchange = ExchangeName(account_config.exchange.lower())
                    except ValueError:
                        console.print(f"[red]错误:[/red] 账号 {account_id} 使用未支持的交易所 {account_config.exchange}")
                        raise typer.Exit(code=1)
                    if not api_key:
                        api_key = account_config.api_key
                    if not api_secret:
                        api_secret = account_config.api_secret
                    if enable_lark and not lark_webhook:
                        lark_webhook = account_config.lark_webhook
                    if enable_lark and not lark_secret:
                        lark_secret = account_config.lark_secret
                    database_url = account_manager.global_settings.get("database_url")
                    console.print(f"[cyan]从配置文件加载账号: {account_id} ({account_config.name})[/cyan]")
                else:
                    console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号 {account_id}，使用命令行参数或环境变量")
            except Exception as exc:
                console.print(f"[yellow]警告:[/yellow] 读取配置文件失败: {exc}，使用命令行参数或环境变量")

        final_api_key, final_api_secret = resolve_credentials(exchange, api_key, api_secret)
        if not final_api_key or not final_api_secret:
            console.print(f"[red]错误:[/red] 缺少 {exchange.value.upper()} API 密钥配置")
            console.print("\n请设置环境变量或使用命令行参数:")
            console.print(f"  环境变量: export {exchange.value.upper()}_API_KEY=your_key && export {exchange.value.upper()}_API_SECRET=your_secret")
            console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
            console.print("  配置文件: --config config/accounts.json --account-id <account_id>")
            raise typer.Exit(code=1)

        account_label = selected_account_config.name if selected_account_config else None
        account_ref = selected_account_config.account_id if selected_account_config else account_id

        if exchange == ExchangeName.XT:
            asyncio.run(
                _run_xt_watch_account_async(
                    interval_minutes=interval_minutes,
                    api_key=final_api_key,
                    api_secret=final_api_secret,
                    debug=debug,
                    enable_lark=enable_lark,
                    lark_webhook=lark_webhook,
                    lark_secret=lark_secret,
                    metrics_config=metrics_config,
                    enable_metrics=enable_metrics,
                    account_id=account_ref,
                    account_name=account_label,
                    database_url=database_url,
                )
            )
            return

        if exchange == ExchangeName.BINANCE:
            asyncio.run(
                _run_binance_watch_account_async(
                    interval_minutes=interval_minutes,
                    api_key=final_api_key,
                    api_secret=final_api_secret,
                    debug=debug,
                    enable_lark=enable_lark,
                    lark_webhook=lark_webhook,
                    lark_secret=lark_secret,
                    metrics_config=metrics_config,
                    enable_metrics=enable_metrics,
                    account_id=account_ref,
                    account_name=account_label,
                    database_url=database_url,
                )
            )
            return

        console.print(f"[red]错误:[/red] 交易所 '{exchange.value}' 暂不支持 watch-account 功能")
        raise typer.Exit(code=1)

    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
    except ValueError as exc:
        error_msg = str(exc) if str(exc) else "配置错误，请检查API密钥"
        console.print(f"[red]配置错误:[/red] {error_msg}")
        raise typer.Exit(code=1)
    except Exception as exc:
        if debug:
            console.print_exception()
        else:
            error_msg = str(exc) if str(exc) else f"未知错误: {type(exc).__name__}"
            console.print(f"[red]错误:[/red] {error_msg}")
        raise typer.Exit(code=1)

async def _run_xt_watch_account_async(
    interval_minutes: int,
    api_key: str,
    api_secret: str,
    debug: bool,
    enable_lark: bool,
    lark_webhook: Optional[str],
    lark_secret: Optional[str],
    metrics_config: Optional[str],
    enable_metrics: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """异步版本的 XT 账户监控（用于多账号并发）."""
    from rich.table import Table
    from tri_arb.exchanges.xt_spot import XTSpotExchange
    from tri_arb.exchanges.xt_perp import XTPerpExchange
    from tri_arb.services.xt_rest_data_service import XTRestDataService

    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的账户监控")

    metrics_account = account_id or (account_name or "default")
    exchange_label = ExchangeName.XT.value
    ensure_metrics_server()

    db_manager = DatabaseManager(database_url=database_url)
    spot_exchange = XTSpotExchange(
        name="xt",
        api_key=api_key,
        api_secret=api_secret,
    )
    perp_exchange = XTPerpExchange(
        api_key=api_key,
        api_secret=api_secret,
    )
    xt_rest_service = XTRestDataService(db_manager, account_id=account_id)

    webhook_url: Optional[str] = lark_webhook
    webhook_secret: Optional[str] = lark_secret
    if enable_lark and not webhook_url:
        webhook_url = os.getenv("LARK_WEBHOOK_URL")
    if enable_lark and not webhook_secret:
        webhook_secret = os.getenv("LARK_WEBHOOK_SECRET")

    metrics_definition: Optional[MetricsConfig] = None
    if enable_metrics:
        metrics_path = metrics_config or os.getenv("METRICS_CONFIG_PATH")
        metrics_definition = load_metrics_config(metrics_path)
        if not metrics_definition.exchanges:
            logger.info(f"账号 {account_label} 指标配置为空，跳过指标评估")
            metrics_definition = None

    async def fetch_and_display(iteration_num: int):
        """获取数据并显示表格."""
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        console.print(f"\n[cyan][账号 {account_label}] 第 {iteration_num} 次查询 - {current_time}[/cyan]")

        try:
            # 1. 获取并显示现货账户余额
            try:
                spot_balances = await spot_exchange.get_balance()
                record_balance_query_status(
                    exchange_label,
                    "spot",
                    metrics_account,
                    success=True,
                )
                if spot_balances:
                    spot_table = Table(
                        title=f"XT 现货账户余额 - {account_label}",
                        show_header=True,
                        header_style="bold magenta"
                    )
                    spot_table.add_column("Currency", style="cyan", width=12)
                    spot_table.add_column("Available", justify="right", style="green")
                    spot_table.add_column("Frozen", justify="right", style="yellow")
                    spot_table.add_column("Total", justify="right", style="white")
                    
                    for currency, data in spot_balances.items():
                        available = data.get('available', Decimal('0'))
                        frozen = data.get('frozen', Decimal('0'))
                        total = data.get('total', available + frozen)
                        
                        spot_table.add_row(
                            currency,
                            f"{available:.8f}",
                            f"{frozen:.8f}",
                            f"{total:.8f}",
                        )
                    
                    console.print(spot_table)
                    console.print(f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                    
                    await xt_rest_service.save_spot_balance(
                        balances_data=spot_balances,
                        query_type="scheduled",
                    )
                    # 更新 Prometheus 指标
                    update_balance_metrics(
                        exchange_label,
                        "spot",
                        metrics_account,
                        spot_balances,
                    )
                else:
                    console.print(f"[yellow][账号 {account_label}] XT 现货账户余额为空[/yellow]\n")
            except Exception as e:
                record_balance_query_status(
                    exchange_label,
                    "spot",
                    metrics_account,
                    success=False,
                )
                console.print(f"[red][账号 {account_label}] 获取现货余额失败:[/red] {e}\n")
                if debug:
                    console.print_exception()

            # 2. 获取并显示合约账户余额
            try:
                perp_balances = await perp_exchange.get_balance()
                record_balance_query_status(
                    exchange_label,
                    "perp",
                    metrics_account,
                    success=True,
                )
                if perp_balances:
                    balances_data: dict[str, dict[str, Any]] = {}
                    for currency, balance_info in perp_balances.items():
                        # 包含所有字段，特别是保证金占用率计算所需的字段
                        balances_data[currency] = {
                            "available": balance_info.get("available", Decimal("0")),
                            "frozen": balance_info.get("frozen", Decimal("0")),
                            "total": balance_info.get("total", Decimal("0")),
                            "unrealized_pnl": balance_info.get("unrealized_pnl", Decimal("0")),
                            "realized_pnl": balance_info.get("realized_pnl", Decimal("0")),
                            "equity": balance_info.get("equity", Decimal("0")),
                            "margin": balance_info.get("margin", Decimal("0")),
                            "margin_ratio": balance_info.get("margin_ratio", Decimal("0")),
                            # 保证金占用率计算所需字段
                            "openOrderMarginFrozen": balance_info.get("openOrderMarginFrozen", balance_info.get("frozen", Decimal("0"))),
                            "isolatedMargin": balance_info.get("isolatedMargin", Decimal("0")),
                            "crossedMargin": balance_info.get("crossedMargin", Decimal("0")),
                            "totalAmount": balance_info.get("totalAmount", Decimal("0")),
                            "walletBalance": balance_info.get("walletBalance", Decimal("0")),
                            "marginBalance": balance_info.get("marginBalance", Decimal("0")),
                        }

                    perp_table = Table(
                        title=f"XT 合约账户余额 - {account_label}",
                        show_header=True,
                        header_style="bold magenta"
                    )
                    perp_table.add_column("Currency", style="cyan", width=12)
                    perp_table.add_column("Available", justify="right", style="green")
                    perp_table.add_column("Frozen", justify="right", style="yellow")
                    perp_table.add_column("Total", justify="right", style="white")
                    perp_table.add_column("Unrealized PnL", justify="right")
                    perp_table.add_column("Realized PnL", justify="right")
                    perp_table.add_column("Equity", justify="right")
                    perp_table.add_column("Margin", justify="right")

                    for currency, data in balances_data.items():
                        available = data.get("available", Decimal("0"))
                        frozen = data.get("frozen", Decimal("0"))
                        total = data.get("total", Decimal("0"))
                        unrealized_pnl = data.get("unrealized_pnl", Decimal("0"))
                        realized_pnl = data.get("realized_pnl", Decimal("0"))
                        equity = data.get("equity", Decimal("0"))
                        margin = data.get("margin", Decimal("0"))

                        unrealized_style = "green" if unrealized_pnl >= 0 else "red"
                        realized_style = "green" if realized_pnl >= 0 else "red"

                        perp_table.add_row(
                            currency,
                            f"{available:.8f}",
                            f"{frozen:.8f}",
                            f"{total:.8f}",
                            f"[{unrealized_style}]{unrealized_pnl:.8f}[/{unrealized_style}]",
                            f"[{realized_style}]{realized_pnl:.8f}[/{realized_style}]",
                            f"{equity:.8f}",
                            f"{margin:.8f}",
                        )

                    console.print(perp_table)
                    console.print(f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                    
                    await xt_rest_service.save_perp_balance(
                        balances_data=balances_data,
                        query_type="scheduled",
                    )
                    # 更新 Prometheus 指标
                    update_balance_metrics(
                        exchange_label,
                        "perp",
                        metrics_account,
                        balances_data,
                    )
                else:
                    console.print(f"[yellow][账号 {account_label}] XT 合约账户余额为空[/yellow]\n")
            except Exception as e:
                record_balance_query_status(
                    exchange_label,
                    "perp",
                    metrics_account,
                    success=False,
                )
                console.print(f"[red][账号 {account_label}] 获取合约余额失败:[/red] {e}\n")
                if debug:
                    console.print_exception()

            # 3. 获取并显示合约账户仓位
            try:
                positions = await perp_exchange.get_positions(symbol=None)
                if positions:
                    position_table = Table(
                        title=f"XT 合约账户仓位 - {account_label}",
                        show_header=True,
                        header_style="bold magenta"
                    )
                    position_table.add_column("Symbol", style="cyan")
                    position_table.add_column("Side", style="white")
                    position_table.add_column("Quantity", justify="right")
                    position_table.add_column("Entry Price", justify="right")
                    position_table.add_column("Mark Price", justify="right")
                    position_table.add_column("Liquidation Price", justify="right")
                    position_table.add_column("Unrealized PnL", justify="right")
                    position_table.add_column("Realized PnL", justify="right")
                    position_table.add_column("Maintenance Margin", justify="right")
                    position_table.add_column("Leverage", justify="right")

                    positions_data: list[dict[str, Any]] = []
                    for pos in positions:
                        if hasattr(pos, "symbol"):
                            pos_symbol = pos.symbol
                            side = getattr(pos, "side", getattr(pos, "position_side", ""))
                            quantity = getattr(pos, "quantity", Decimal("0"))
                            entry_price = getattr(pos, "entry_price", Decimal("0"))
                            mark_price = getattr(pos, "mark_price", Decimal("0"))
                            unrealized_pnl = getattr(pos, "unrealized_pnl", Decimal("0"))
                            realized_pnl = getattr(pos, "realized_pnl", Decimal("0"))
                            liquidation_price = getattr(pos, "liquidation_price", Decimal("0"))
                            leverage = getattr(pos, "leverage", "")
                            maintenance_margin = getattr(pos, "maintenance_margin", Decimal("0"))
                        else:
                            pos_symbol = pos.get("symbol", "")
                            side = pos.get("positionSide") or pos.get("side", "")
                            quantity = Decimal(str(pos.get("positionSize") or pos.get("positionAmt") or "0"))
                            entry_price = Decimal(str(pos.get("entryPrice") or "0"))
                            mark_price = Decimal(str(pos.get("calMarkPrice") or pos.get("markPrice") or "0"))
                            unrealized_pnl = Decimal(str(pos.get("floatingPL") or pos.get("unRealizedProfit") or pos.get("unrealizedPnl") or "0"))
                            realized_pnl = Decimal(str(pos.get("realizedProfit") or pos.get("realizedPnl") or "0"))
                            liquidation_price = Decimal(str(pos.get("breakPrice") or pos.get("liquidationPrice") or "0"))
                            leverage = pos.get("leverage", "")
                            maintenance_margin = Decimal(str(pos.get("maintMargin") or "0"))

                        if quantity == Decimal("0"):
                            continue

                        unrealized_style = "green" if unrealized_pnl >= 0 else "red"
                        realized_style = "green" if realized_pnl >= 0 else "red"

                        position_table.add_row(
                            pos_symbol,
                            side,
                            f"{quantity:.8f}",
                            f"{entry_price:.8f}",
                            f"{mark_price:.8f}",
                            f"{liquidation_price:.8f}",
                            f"[{unrealized_style}]{unrealized_pnl:.8f}[/{unrealized_style}]",
                            f"[{realized_style}]{realized_pnl:.8f}[/{realized_style}]",
                            f"{maintenance_margin:.8f}",
                            f"{leverage}x" if leverage else "-",
                        )

                        pos_dict = {
                            "symbol": pos_symbol,
                            "positionSide": side,
                            "positionSize": str(quantity),
                            "entryPrice": str(entry_price),
                            "calMarkPrice": str(mark_price),
                            "floatingPL": str(unrealized_pnl),
                            "realizedProfit": str(realized_pnl),
                            "breakPrice": str(liquidation_price),
                            "isolatedMargin": str(getattr(pos, "margin", Decimal("0")) if hasattr(pos, "margin") else pos.get("isolatedMargin", "0")),
                            "maintMargin": str(maintenance_margin),
                            "leverage": leverage,
                        }
                        positions_data.append(pos_dict)

                    if positions_data:
                        console.print(position_table)
                        console.print(f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                        
                        await xt_rest_service.save_perp_positions(
                            positions_data=positions_data,
                            query_type="scheduled",
                        )
                        # 更新 Prometheus 指标
                        update_position_metrics(
                            exchange_label,
                            "perp",
                            metrics_account,
                            positions_data,
                        )
                    else:
                        console.print(f"[yellow][账号 {account_label}] XT 当前无持仓[/yellow]\n")
                else:
                    console.print(f"[yellow][账号 {account_label}] XT 当前无持仓[/yellow]\n")
            except Exception as e:
                console.print(f"[red][账号 {account_label}] 获取仓位失败:[/red] {e}\n")
                if debug:
                    console.print_exception()

            # 查询活跃订单并更新 metrics（当前挂单数量）
            try:
                active_orders = await perp_exchange.get_open_orders(None)
                # 更新 Prometheus metrics
                ensure_metrics_server()
                try:
                    update_active_orders_metrics(
                        exchange=exchange_label if 'exchange_label' in locals() else "binance",
                        exchange_type="perp",
                        account_id=metrics_account,
                        orders=active_orders if active_orders else [],
                    )
                except Exception as metric_error:
                    logger.error(f"Failed to update active orders metrics: {metric_error}", exc_info=True)
            except Exception as e:
                logger.debug(f"获取活跃订单失败: {e}")

            # 4. 评估指标（如果启用）
            if metrics_definition:
                await _evaluate_metrics(
                    metrics_config=metrics_definition,
                    db_manager=db_manager,
                    enable_lark=enable_lark,
                    default_webhook=webhook_url,
                    default_secret=webhook_secret,
                    debug=debug,
                )

            # 显示下次查询时间
            next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)
            console.print(f"[dim][账号 {account_label}] 下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            console.print(f"[dim][账号 {account_label}] 等待 {interval_minutes} 分钟...[/dim]\n")

        except Exception as e:
            console.print(f"[red][账号 {account_label}] 查询过程出错:[/red] {e}")
            if debug:
                console.print_exception()

    iteration = 0
    try:
        # 创建数据库表
        if account_id:
            await xt_rest_service.ensure_account_tables()
            logger.info(f"账号 {account_label} 的数据库表已就绪")
        else:
            await db_manager.create_tables()

        # 连接交易所
        await spot_exchange.connect()
        await perp_exchange.connect()
        logger.info(f"账号 {account_label} 交易所连接成功")

        # 立即执行一次查询
        iteration = 1
        await fetch_and_display(iteration)

        # 定时查询循环
        while True:
            await asyncio.sleep(interval_minutes * 60)
            iteration += 1
            await fetch_and_display(iteration)

    except KeyboardInterrupt:
        logger.info(f"账号 {account_label} 的监控已停止")
    except Exception as e:
        logger.error("账号 %s 的监控异常: %s", account_label, e, exc_info=True)
        if debug:
            console.print_exception()
    finally:
        await spot_exchange.disconnect()
        await perp_exchange.disconnect()
        await db_manager.close()


async def _run_binance_watch_positions_async(
    interval: int,
    api_key: str,
    api_secret: str,
    symbol: Optional[str],
    debug: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """异步版本的 Binance 仓位监控."""
    from rich.table import Table
    from tri_arb.exchanges.binance_perp import BinancePerpExchange

    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info("启动账号 %s 的 Binance 仓位监控", account_label)
    console.print(f"[cyan]启动账号 {account_label} 的 Binance 仓位监控[/cyan]")

    metrics_account = account_id or (account_name or "default")
    exchange_label = ExchangeName.BINANCE.value
    exchange_type_label = ExchangeType.PERP.value
    ensure_metrics_server()

    metrics_account = account_id or (account_name or "default")
    exchange_label = ExchangeName.BINANCE.value
    exchange_type_label = ExchangeType.PERP.value
    ensure_metrics_server()

    db_manager = DatabaseManager(database_url=database_url)
    rest_data_service = RestDataService(db_manager)
    perp_exchange = BinancePerpExchange(api_key=api_key, api_secret=api_secret)

    normalized_symbol: Optional[str] = None
    if symbol:
        normalized_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()

    async def fetch_positions(iteration_num: int):
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"\n[cyan][账号 {account_label}] 第 {iteration_num} 次查询 - {current_time}[/cyan]")

        try:
            positions = await perp_exchange.get_positions(symbol=normalized_symbol)
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取仓位失败:[/red] {exc}")
            logger.error("账号 %s Binance 持仓查询失败: %s", account_label, exc)
            if debug:
                console.print_exception()
            return

        if not positions:
            console.print(f"[yellow][账号 {account_label}] 当前无持仓[/yellow]")
            return

        position_table = Table(
            title=f"Binance 合约仓位 - {account_label}",
            show_header=True,
            header_style="bold magenta",
        )
        position_table.add_column("Symbol", style="cyan")
        position_table.add_column("Side", style="yellow")
        position_table.add_column("Quantity", justify="right")
        position_table.add_column("Entry", justify="right")
        position_table.add_column("Mark", justify="right")
        position_table.add_column("Unrealized PnL", justify="right")
        position_table.add_column("Leverage", justify="right")

        for pos in positions:
            qty = Decimal(str(pos.get("positionAmt", "0")))
            entry_price = Decimal(str(pos.get("entryPrice", "0")))
            mark_price = Decimal(str(pos.get("markPrice", "0")))
            unrealized = Decimal(str(pos.get("unRealizedProfit", "0")))
            leverage = pos.get("leverage", "1")
            side = pos.get("positionSide") or ("LONG" if qty > 0 else "SHORT" if qty < 0 else "FLAT")

            position_table.add_row(
                pos.get("symbol", ""),
                side,
                f"{qty:.8f}",
                f"{entry_price:.4f}",
                f"{mark_price:.4f}",
                f"{unrealized:.4f}",
                str(leverage),
            )

        console.print(position_table)
        console.print(
            f"[dim][账号 {account_label}] 仓位获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n"
        )

        try:
            await rest_data_service.save_positions_query(
                exchange="binance",
                exchange_type="perp",
                positions_data=positions,
                query_type="scheduled",
                account_id=account_id,
            )
            console.print(f"[green]✓[/green] [账号 {account_label}] 仓位数据 (perp) 已保存到 [cyan]binance_position_snapshot[/cyan]")
        except Exception as save_exc:
            console.print(f"[red][账号 {account_label}] 保存仓位失败:[/red] {save_exc}")
            logger.error("账号 %s Binance 仓位保存失败: %s", account_label, save_exc)
            if debug:
                console.print_exception()

        update_position_metrics(
            exchange_label,
            exchange_type_label,
            metrics_account,
            positions,
        )

    async def watch_loop():
        iteration = 0
        try:
            # 确保数据库表存在
            try:
                console.print(f"[cyan]正在检查/创建数据库表（账号 {account_label}）...[/cyan]")
                await db_manager.create_tables()
                console.print(f"[green]✅ 数据库表已就绪[/green]\n")
            except Exception as init_exc:
                console.print(f"[yellow]警告:[/yellow] 数据库表初始化失败: {init_exc}")
            
            await perp_exchange.connect()
            while True:
                iteration += 1
                await fetch_positions(iteration)
                await asyncio.sleep(interval * 60)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            console.print(f"\n[yellow][账号 {account_label}] 监控已停止[/yellow]")
            raise
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 监控异常:[/red] {exc}")
            logger.error("账号 %s Binance 监控异常: %s", account_label, exc)
            if debug:
                console.print_exception()
            raise
        finally:
            try:
                await perp_exchange.disconnect()
            except Exception:
                pass
            try:
                await db_manager.close()
            except Exception:
                pass

    await watch_loop()


@app.command("watch-positions")
def watch_positions(
    exchange_type: ExchangeType = typer.Option(
        ExchangeType.PERP,
        "--exchange-type",
        "-e",
        help="交易类型（仅支持 perp，默认 perp）"
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
    ),
    lark_webhook: Optional[str] = typer.Option(
        None,
        "--lark-webhook",
        help="Lark群机器人Webhook URL，用于推送仓位告警"
    ),
    lark_secret: Optional[str] = typer.Option(
        None,
        "--lark-secret",
        help="Lark机器人签名密钥（若启用安全校验需提供）"
    ),
    enable_lark: bool = typer.Option(
        False,
        "--enable-lark/--disable-lark",
        help="启用/禁用 Lark 告警推送（默认禁用）"
    ),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="账号ID（可选），如果提供且支持该交易所，则使用账号特定设置"
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="账号配置文件路径（JSON格式）。如果提供，将从配置文件读取账号信息（API密钥、Lark配置等）"
    ),
    accounts: Optional[str] = typer.Option(
        None,
        "--accounts",
        help="多个账号ID（逗号分隔），需要配合 --config 使用"
    ),
    all_accounts: bool = typer.Option(
        False,
        "--all-accounts",
        help="从配置文件读取所有启用的账号并同时监控。需要配合 --config 使用"
    ),
):
    """定时查询永续合约仓位（XT + Binance）。

    - 单账号模式支持通过命令行或配置文件提供 API 凭证。
    - 多账号模式会根据配置文件中账号的 `exchange` 字段自动路由到对应实现。
    - Binance 仓位数据会保存到 `binance_position_snapshot` 表；XT 使用 `xt_position_snapshot` 表。
    """
    try:
        if exchange_type != ExchangeType.PERP:
            console.print("[red]错误:[/red] watch-positions 命令仅支持永续合约 (perp)")
            raise typer.Exit(code=1)

        if interval < 1:
            raise ValueError("查询间隔必须至少为1分钟")

        if symbol:
            symbol = validate_symbol(symbol)

        account_manager = None
        selected_account_config = None
        database_url: Optional[str] = None

        def resolve_credentials(target_exchange: ExchangeName, key: Optional[str], secret: Optional[str]) -> tuple[str, str]:
            env_prefix = target_exchange.value.upper()
            final_key = key or os.getenv(f"{env_prefix}_API_KEY", "")
            final_secret = secret or os.getenv(f"{env_prefix}_API_SECRET", "")
            return final_key, final_secret

        def ensure_account_manager():
            nonlocal account_manager
            if account_manager is None:
                from tri_arb.config.account_manager import AccountManager
                account_manager = AccountManager(config_path)

        # 处理多账号模式
        if accounts or all_accounts:
            if not config_path:
                console.print("[red]错误:[/red] 多账号模式需要配合 --config 使用")
                raise typer.Exit(code=1)

            ensure_account_manager()
            requested_ids: list[str]
            if accounts:
                requested_ids = [acc_id.strip() for acc_id in accounts.split(",") if acc_id.strip()]
            else:
                requested_ids = [acc.account_id for acc in account_manager.get_enabled_accounts()]

            if not requested_ids:
                console.print("[red]错误:[/red] 没有可用的账号")
                raise typer.Exit(code=1)

            account_configs = []
            for acc_id in requested_ids:
                acc_config = account_manager.get_account(acc_id)
                if not acc_config:
                    console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号: {acc_id}，跳过")
                    continue
                if not acc_config.enabled:
                    console.print(f"[yellow]警告:[/yellow] 账号 {acc_id} 未启用（enabled: false），跳过")
                    continue
                account_configs.append(acc_config)

            if not account_configs:
                console.print("[red]错误:[/red] 没有可用的启用账号")
                raise typer.Exit(code=1)

            database_url = account_manager.global_settings.get("database_url")
            total_accounts = len(account_manager.get_all_accounts())
            console.print(f"[cyan]多账号监控模式（{len(account_configs)} 个账号，配置总数 {total_accounts}）[/cyan]")
            for acc in account_configs:
                console.print(f"  - {acc.account_id}: {acc.name} ({acc.exchange})")
            console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
            console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")

            async def run_multi_account_watch():
                tasks = []
                for acc in account_configs:
                    try:
                        acc_exchange = ExchangeName(acc.exchange.lower())
                        console.print(f"[dim]调试: 账号 {acc.account_id} 交易所识别为: {acc_exchange.value}[/dim]")
                    except ValueError:
                        console.print(f"[yellow]警告:[/yellow] 账号 {acc.account_id} 使用未支持的交易所 {acc.exchange}，跳过")
                        continue

                    if acc_exchange == ExchangeName.XT:
                        console.print(f"[dim]调试: 账号 {acc.account_id} 路由到 XT 实现[/dim]")
                        task = asyncio.create_task(
                            _run_xt_watch_positions_async(
                                interval=interval,
                                api_key=acc.api_key,
                                api_secret=acc.api_secret,
                                symbol=symbol,
                                debug=debug,
                                lark_webhook=acc.lark_webhook if enable_lark else None,
                                lark_secret=acc.lark_secret if enable_lark else None,
                                account_id=acc.account_id,
                                account_name=acc.name,
                                database_url=database_url,
                            )
                        )
                    elif acc_exchange == ExchangeName.BINANCE:
                        console.print(f"[dim]调试: 账号 {acc.account_id} 路由到 Binance 实现[/dim]")
                        task = asyncio.create_task(
                            _run_binance_watch_positions_async(
                                interval=interval,
                                api_key=acc.api_key,
                                api_secret=acc.api_secret,
                                symbol=symbol,
                                debug=debug,
                                account_id=acc.account_id,
                                account_name=acc.name,
                                database_url=database_url,
                            )
                        )
                    else:
                        console.print(f"[yellow]警告:[/yellow] 账号 {acc.account_id} 的交易所 {acc_exchange.value} 暂不支持 watch-positions，跳过")
                        continue

                    tasks.append(task)
                    await asyncio.sleep(0.5)

                if not tasks:
                    console.print("[red]错误:[/red] 选择的账号交易所暂未支持 watch-positions 功能")
                    return

                try:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for idx, result in enumerate(results):
                        if isinstance(result, Exception):
                            console.print(f"[red]账号 {account_configs[idx].account_id} 监控任务异常:[/red] {result}")
                            logger.error("账号 %s watch-positions 任务异常: %s", account_configs[idx].account_id, result)
                            if debug:
                                console.print_exception()
                except KeyboardInterrupt:
                    console.print("\n[yellow]监控已停止[/yellow]")
                except Exception as exc:
                    console.print(f"[red]多账号监控异常:[/red] {exc}")
                    logger.error("多账号 watch-positions 异常: %s", exc)
                    if debug:
                        console.print_exception()

            asyncio.run(run_multi_account_watch())
            return

        # 单账号：尝试从配置文件读取账号信息
        if config_path and account_id:
            try:
                ensure_account_manager()
                account_config = account_manager.get_account(account_id)
                if account_config:
                    selected_account_config = account_config
                    if not account_config.enabled:
                        console.print(f"[yellow]警告:[/yellow] 账号 {account_id} 未启用（enabled: false）")
                    try:
                        exchange = ExchangeName(account_config.exchange.lower())
                    except ValueError:
                        console.print(f"[red]错误:[/red] 账号 {account_id} 使用未支持的交易所 {account_config.exchange}")
                        raise typer.Exit(code=1)
                    if not api_key:
                        api_key = account_config.api_key
                    if not api_secret:
                        api_secret = account_config.api_secret
                    if enable_lark and not lark_webhook:
                        lark_webhook = account_config.lark_webhook
                    if enable_lark and not lark_secret:
                        lark_secret = account_config.lark_secret
                    database_url = account_manager.global_settings.get("database_url")
                    console.print(f"[cyan]从配置文件加载账号: {account_id} ({account_config.name})[/cyan]")
                else:
                    console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号 {account_id}，使用命令行参数或环境变量")
            except Exception as exc:
                console.print(f"[yellow]警告:[/yellow] 读取配置文件失败: {exc}，使用命令行参数或环境变量")

        final_api_key, final_api_secret = resolve_credentials(exchange, api_key, api_secret)

        account_label = selected_account_config.name if selected_account_config else None
        account_ref = selected_account_config.account_id if selected_account_config else account_id

        if exchange == ExchangeName.XT:
            if not final_api_key or not final_api_secret:
                console.print("[red]错误:[/red] 缺少 XT API 密钥配置")
                console.print("\n请设置环境变量或使用命令行参数:")
                console.print("  环境变量: export XT_API_KEY=your_key && export XT_API_SECRET=your_secret")
                console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
                console.print("  配置文件: --config config/accounts.json --account-id account_001")
                raise typer.Exit(code=1)

            asyncio.run(
                _run_xt_watch_positions_async(
                    interval=interval,
                    api_key=final_api_key,
                    api_secret=final_api_secret,
                    symbol=symbol,
                    debug=debug,
                    lark_webhook=lark_webhook if enable_lark else None,
                    lark_secret=lark_secret if enable_lark else None,
                    account_id=account_ref,
                    account_name=account_label,
                    database_url=database_url,
                )
            )
            return

        if exchange == ExchangeName.BINANCE:
            if not final_api_key or not final_api_secret:
                console.print("[red]错误:[/red] 缺少 Binance API 密钥配置")
                console.print("\n请设置环境变量或使用命令行参数:")
                console.print("  环境变量: export BINANCE_API_KEY=your_key && export BINANCE_API_SECRET=your_secret")
                console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
                console.print("  配置文件: --config config/accounts.json --account-id binance_main")
                raise typer.Exit(code=1)

            asyncio.run(
                _run_binance_watch_positions_async(
                    interval=interval,
                    api_key=final_api_key,
                    api_secret=final_api_secret,
                    symbol=symbol,
                    debug=debug,
                    account_id=account_ref,
                    account_name=account_label,
                    database_url=database_url,
                )
            )
            return

        console.print(f"[red]错误:[/red] 交易所 '{exchange.value}' 暂不支持 watch-positions 功能")
        raise typer.Exit(code=1)

    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
    except ValueError as exc:
        error_msg = str(exc) if str(exc) else "配置错误，请检查API密钥"
        console.print(f"[red]配置错误:[/red] {error_msg}")
        raise typer.Exit(code=1)
    except Exception as exc:
        if debug:
            console.print_exception()
        else:
            error_msg = str(exc) if str(exc) else f"未知错误: {type(exc).__name__}"
            console.print(f"[red]错误:[/red] {error_msg}")
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
        5,
        "--interval",
        "-i",
        help="查询间隔（分钟），默认5分钟"
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
        help="OKX 交易所需要的 passphrase（覆盖环境变量）"
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
    ),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="账号ID（可选，仅支持XT），如果提供则使用账号特定的表。例如: account_001"
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="账号配置文件路径（JSON格式）。如果提供，将从配置文件读取账号信息（API密钥等）"
    ),
    accounts: Optional[str] = typer.Option(
        None,
        "--accounts",
        help="多个账号ID（逗号分隔），例如: account_001,account_002。需要配合 --config 使用，只监控 enabled: true 的账号"
    ),
    all_accounts: bool = typer.Option(
        False,
        "--all-accounts",
        help="从配置文件读取所有启用的账号（enabled: true）并同时监控。需要配合 --config 使用"
    ),
):
    """定时查询账户余额.
    
    每隔指定分钟查询一次余额，持续监控账户变化。
    如果提供账号ID（仅支持XT），数据会保存到账号特定的表中。
    表会在首次运行时自动创建，不会重复创建。
    
    支持从配置文件读取账号信息：
    - 如果提供了 --config 和 --account-id，将从配置文件读取该账号的 API 密钥
    - 如果提供了 --config 和 --accounts，将同时监控多个账号（逗号分隔，只监控 enabled: true 的账号）
    - 如果提供了 --config 和 --all-accounts，将监控配置文件中所有 enabled: true 的账号
    - 配置文件格式参考: config/accounts.example.json
    
    按 Ctrl+C 停止监控。
    
    示例:
        # 每1分钟查询一次余额
        cextools account watch-balance -e perp
        
        # 使用账号特定的表（XT）
        cextools account watch-balance -x xt -e perp --account-id account_001
        
        # 从配置文件读取账号信息
        cextools account watch-balance -x xt -e perp --config config/accounts.json --account-id account_001
        
        # 同时监控多个账号（只监控启用的账号）
        cextools account watch-balance -x xt -e perp --config config/accounts.json --accounts account_001,account_002
        
        # 监控配置文件中所有启用的账号
        cextools account watch-balance -x xt -e perp --config config/accounts.json --all-accounts
        
        # 每5分钟查询一次Binance余额
        cextools account watch-balance -x binance -e perp --interval 5
        
        # 每10分钟查询一次OKX余额
        cextools account watch-balance -x okx -e perp -i 10
    """
    try:
        # 验证间隔时间
        if interval < 1:
            raise ValueError("查询间隔必须至少为1分钟")
        
        # 检查是否使用多账号模式（仅支持XT）
        if exchange == ExchangeName.XT:
            account_id_list = None
            if accounts:
                account_id_list = [acc_id.strip() for acc_id in accounts.split(",")]
            elif all_accounts:
                if not config_path:
                    console.print("[red]错误:[/red] --all-accounts 需要配合 --config 使用")
                    raise typer.Exit(code=1)
                try:
                    from tri_arb.config.account_manager import AccountManager
                    account_manager = AccountManager(config_path)
                    enabled_accounts = account_manager.get_enabled_accounts()
                    account_id_list = [acc.account_id for acc in enabled_accounts]
                    if not account_id_list:
                        console.print("[red]错误:[/red] 配置文件中没有启用的账号")
                        raise typer.Exit(code=1)
                except Exception as e:
                    console.print(f"[red]错误:[/red] 读取配置文件失败: {e}")
                    raise typer.Exit(code=1)
            
            # 多账号模式
            if account_id_list:
                if not config_path:
                    console.print("[red]错误:[/red] 多账号模式需要配合 --config 使用")
                    raise typer.Exit(code=1)
                
                try:
                    from tri_arb.config.account_manager import AccountManager
                    account_manager = AccountManager(config_path)
                    
                    # 验证所有账号是否存在，并过滤出启用的账号
                    account_configs = []
                    for acc_id in account_id_list:
                        acc_config = account_manager.get_account(acc_id)
                        if not acc_config:
                            console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号: {acc_id}，跳过")
                            continue
                        if not acc_config.enabled:
                            console.print(f"[yellow]警告:[/yellow] 账号 {acc_id} 未启用（enabled: false），跳过")
                            continue
                        account_configs.append(acc_config)
                    
                    if not account_configs:
                        console.print("[red]错误:[/red] 没有可用的启用账号")
                        raise typer.Exit(code=1)
                    
                    console.print(f"[cyan]多账号监控模式[/cyan]")
                    console.print(f"[cyan]账号数量: {len(account_configs)}[/cyan]")
                    for acc in account_configs:
                        console.print(f"  - {acc.account_id}: {acc.name}")
                    console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
                    console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")
                    
                    # 为每个账号启动独立的监控任务
                    # 从配置文件获取 database_url
                    database_url = account_manager.global_settings.get("database_url")
                    
                    async def run_multi_account_watch():
                        tasks = []
                        for acc_config in account_configs:
                            # 根据账号配置中的交易所类型路由到不同的监控函数
                            task = asyncio.create_task(
                                _run_watch_balance_async(
                                    exchange=acc_config.exchange.lower(),
                                    interval=interval,
                                    api_key=acc_config.api_key,
                                    api_secret=acc_config.api_secret,
                                    exchange_type=exchange_type,
                                    output=output,
                                    debug=debug,
                                    account_id=acc_config.account_id,
                                    account_name=acc_config.name,
                                    database_url=database_url,
                                    passphrase=getattr(acc_config, 'passphrase', None),
                                )
                            )
                            tasks.append(task)
                            # 稍微延迟，避免同时连接过多
                            await asyncio.sleep(0.5)
                        
                        try:
                            await asyncio.gather(*tasks, return_exceptions=True)
                        except KeyboardInterrupt:
                            console.print("\n[yellow]监控已停止[/yellow]")
                    
                    asyncio.run(run_multi_account_watch())
                    return
                    
                except Exception as e:
                    console.print(f"[red]错误:[/red] 多账号模式启动失败: {e}")
                    if debug:
                        console.print_exception()
                    raise typer.Exit(code=1)
            
            # 单账号模式：如果提供了配置文件，尝试从配置文件读取账号信息
            if config_path and account_id:
                try:
                    from tri_arb.config.account_manager import AccountManager
                    account_manager = AccountManager(config_path)
                    account_config = account_manager.get_account(account_id)
                    
                    if account_config:
                        # 检查账号是否启用
                        if not account_config.enabled:
                            console.print(f"[yellow]警告:[/yellow] 账号 {account_id} 未启用（enabled: false）")
                        
                        # 从配置文件读取 API 密钥（如果命令行未提供）
                        if not api_key:
                            api_key = account_config.api_key
                        if not api_secret:
                            api_secret = account_config.api_secret
                        if not passphrase and account_config.passphrase:
                            passphrase = account_config.passphrase
                        
                        console.print(f"[cyan]从配置文件加载账号: {account_id} ({account_config.name})[/cyan]")
                    else:
                        console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号 {account_id}，使用命令行参数或环境变量")
                except Exception as e:
                    console.print(f"[yellow]警告:[/yellow] 读取配置文件失败: {e}，使用命令行参数或环境变量")
        
        # 创建 exchange 实例
        exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange)
        
        console.print(f"[cyan]开始监控 {exchange.value.upper()} {exchange_type.value.upper()} 账户余额[/cyan]")
        console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
        console.print(f"[yellow]按 Ctrl+C 停止监控[/yellow]\n")
        
        # 预初始化数据库（创建一次表结构）
        db_manager = DatabaseManager()

        # 定时查询函数
        async def watch_loop():
            iteration = 0
            try:
                await exchange_instance.connect()
                # 确保所需表存在（统一表，不再需要按账号分表）
                try:
                    await db_manager.create_tables()
                    console.print(f"[green]✓[/green] 数据库表已就绪\n")
                except Exception as init_exc:
                    logger.warning(f"初始化数据库表失败: {init_exc}")
                
                while True:
                    iteration += 1
                    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    console.print(f"\n{'='*60}")
                    console.print(f"[bold]第 {iteration} 次查询 - {current_time}[/bold]")
                    console.print(f"{'='*60}\n")
                    
                    try:
                        # 查询余额
                        balance_data = await exchange_instance.get_balance()

                        # OKX 仅保留 USDT 合约余额
                        if exchange == ExchangeName.OKX and exchange_type == ExchangeType.PERP and balance_data:
                            filtered = {}
                            for k, v in balance_data.items():
                                if (k or "").upper() == "USDT":
                                    filtered["USDT"] = v
                            balance_data = filtered
                        
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
                                now = datetime.datetime.utcnow()
                                # 标准化余额数据: {currency: {available, frozen, total, raw}}
                                for currency, data in balance_data.items():
                                    available = Decimal(str(data.get("available", 0)))
                                    frozen = Decimal(str(data.get("frozen", 0)))
                                    total = Decimal(str(data.get("total", 0)))
                                    # 原始数据可能包含 Decimal，使用 default=str 以避免序列化错误
                                    raw_json = json.dumps(data, default=str)

                                    async with db_manager.session() as session:
                                        if exchange == ExchangeName.BINANCE:
                                            record = BinanceAccountBalance(
                                                exchange_type=exchange_type.value if hasattr(exchange_type, 'value') else str(exchange_type),
                                                query_time=now,
                                                query_type='manual',
                                                account_id=account_id,
                                                asset=currency.upper(),
                                                free=available,
                                                locked=frozen,
                                                total=total,
                                                raw_data=raw_json,
                                            )
                                            # 设置 update_time 属性（向后兼容）
                                            record.update_time = now
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
                                        elif exchange == ExchangeName.XT:
                                            # 如果提供了账号ID，使用账号特定的表模型
                                            # 复用 XT WebSocket 的账户更新表，记录 REST 快照
                                            record = XTAccountUpdate(
                                                update_time=now,
                                                account_id=account_id,  # 使用统一表 + account_id
                                                currency=currency.upper(),
                                                available=available,
                                                frozen=frozen,
                                                total=total,
                                                raw_data=raw_json,
                                            )
                                        else:
                                            record = None

                                        if record is not None:
                                            session.add(record)
                                            logger.info(f"余额已保存到数据库: {currency.upper()}")
                                            if exchange == ExchangeName.OKX:
                                                table_name = "okx_account_update"
                                            elif exchange == ExchangeName.GATE:
                                                table_name = "gate_account_update"
                                            elif exchange == ExchangeName.XT:
                                                table_name = "xt_account_update"
                                            else:
                                                table_name = "unknown"
                                            # account_label 可能未定义，使用 account_id 或默认值
                                            acc_label = account_id or account_name or "默认账号"
                                            console.print(f"[green]✓[/green] [账号 {acc_label}] 余额数据 ({exchange_type.value}) 已保存到 [cyan]{table_name}[/cyan]: {currency.upper()}")
                                # 提交由 session ctx 管理
                            except Exception as save_exc:
                                logger.warning(f"保存余额到数据库失败: {save_exc}")
                                console.print(f"[red]✗[/red] 保存余额失败: {save_exc}")
                        
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


async def _run_xt_watch_balance_async(
    interval: int,
    api_key: str,
    api_secret: str,
    exchange_type: ExchangeType,
    output: str,
    debug: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """异步版本的 XT 余额监控（用于多账号并发）."""
    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的余额监控")

    exchange_instance = create_exchange(exchange_type, api_key, api_secret, ExchangeName.XT)
    db_manager = DatabaseManager(database_url=database_url)
    metrics_account = account_id or (account_name or "default")
    exchange_label = ExchangeName.XT.value
    exchange_type_label = exchange_type.value
    ensure_metrics_server()

    async def watch_loop():
        iteration = 0
        try:
            await exchange_instance.connect()
            # 确保所需表存在（统一表，不再需要按账号分表）
            try:
                await db_manager.create_tables()
                logger.info(f"账号 {account_label} 的数据库表已就绪")
            except Exception as init_exc:
                logger.warning(f"账号 {account_label} 初始化数据库表失败: {init_exc}")

            while True:
                iteration += 1
                current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                console.print(f"\n[cyan][账号 {account_label}] 第 {iteration} 次查询 - {current_time}[/cyan]")

                try:
                    balance_data = await exchange_instance.get_balance()
                    record_balance_query_status(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        success=True,
                    )
                    update_balance_metrics(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        balance_data,
                    )

                    if not balance_data:
                        console.print(f"[yellow][账号 {account_label}] 账户余额为空或所有币种余额为0[/yellow]")
                    else:
                        # 根据输出格式显示
                        if output == "json":
                            print_json(balance_data)
                        else:  # table (default)
                            format_balance_table(balance_data, exchange_instance)

                        # 保存到数据库
                        try:
                            now = datetime.datetime.utcnow()
                            for currency, data in balance_data.items():
                                available = Decimal(str(data.get("available", 0)))
                                frozen = Decimal(str(data.get("frozen", 0)))
                                total = Decimal(str(data.get("total", 0)))
                                raw_json = json.dumps(data, default=str)

                                async with db_manager.session() as session:
                                    record = XTAccountUpdate(
                                        update_time=now,
                                        account_id=account_id,  # 使用统一表 + account_id
                                        currency=currency.upper(),
                                        available=available,
                                        frozen=frozen,
                                        total=total,
                                        raw_data=raw_json,
                                    )
                                    session.add(record)
                                    # 提交由 session 上下文管理器自动处理
                                    logger.info(f"账号 {account_label} 余额已保存到数据库: {currency.upper()}")
                                    console.print(f"[green]✓[/green] [账号 {account_label}] 余额数据 ({exchange_type.value}) 已保存到 [cyan]xt_account_update[/cyan]: {currency.upper()}")
                        except Exception as save_exc:
                            logger.warning(f"账号 {account_label} 保存余额到数据库失败: {save_exc}")
                            console.print(f"[red]✗[/red] [账号 {account_label}] 保存余额失败: {save_exc}")

                        next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval)
                        console.print(f"[dim][账号 {account_label}] 下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")

                except Exception as e:
                    record_balance_query_status(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        success=False,
                    )
                    console.print(f"[red][账号 {account_label}] 查询失败:[/red] {e}")
                    if debug:
                        console.print_exception()

                console.print(f"[dim][账号 {account_label}] 等待 {interval} 分钟...[/dim]")
                await asyncio.sleep(interval * 60)

        except KeyboardInterrupt:
            logger.info(f"账号 {account_label} 的监控已停止")
        finally:
            await exchange_instance.disconnect()

    await watch_loop()


async def _run_watch_balance_async(
    exchange: str,
    interval: int,
    api_key: str,
    api_secret: str,
    exchange_type: ExchangeType,
    output: str,
    debug: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
    passphrase: Optional[str] = None,
) -> None:
    """通用的多交易所余额监控函数（用于多账号并发）.
    
    Args:
        exchange: 交易所名称 (xt, binance, okx, gate)
        interval: 查询间隔（分钟）
        api_key: API密钥
        api_secret: API密钥
        exchange_type: 交易类型 (spot, perp)
        output: 输出格式 (table, json)
        debug: 是否启用调试模式
        account_id: 账号ID（可选）
        account_name: 账号名称（可选）
        database_url: 数据库连接URL（可选）
    """
    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的余额监控 (交易所: {exchange})")
    
    # 根据交易所名称创建对应的ExchangeName枚举
    exchange_name_map = {
        "xt": ExchangeName.XT,
        "binance": ExchangeName.BINANCE,
        "okx": ExchangeName.OKX,
        "gate": ExchangeName.GATE,
    }
    
    exchange_name = exchange_name_map.get(exchange.lower())
    if not exchange_name:
        raise ValueError(f"不支持的交易所: {exchange}，支持的交易所: {', '.join(exchange_name_map.keys())}")
    
    # 对于XT交易所，使用专门的实现（支持账号特定表）
    if exchange.lower() == "xt":
        await _run_xt_watch_balance_async(
            interval=interval,
            api_key=api_key,
            api_secret=api_secret,
            exchange_type=exchange_type,
            output=output,
            debug=debug,
            account_id=account_id,
            account_name=account_name,
            database_url=database_url,
        )
        return
    
    # 对于其他交易所，使用通用实现
    await _run_generic_watch_balance_async(
        exchange_name=exchange_name,
        interval=interval,
        api_key=api_key,
        api_secret=api_secret,
        exchange_type=exchange_type,
        output=output,
        debug=debug,
        account_id=account_id,
        account_name=account_name,
        database_url=database_url,
        passphrase=passphrase,
    )


async def _run_generic_watch_balance_async(
    exchange_name: ExchangeName,
    interval: int,
    api_key: str,
    api_secret: str,
    exchange_type: ExchangeType,
    output: str,
    debug: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
    passphrase: Optional[str] = None,
) -> None:
    """通用的多交易所余额监控函数（用于非XT交易所）.
    
    Args:
        exchange_name: 交易所名称枚举
        interval: 查询间隔（分钟）
        api_key: API密钥
        api_secret: API密钥
        exchange_type: 交易类型 (spot, perp)
        output: 输出格式 (table, json)
        debug: 是否启用调试模式
        account_id: 账号ID（可选）
        account_name: 账号名称（可选）
        database_url: 数据库连接URL（可选）
    """
    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的余额监控 ({exchange_name.value})")
    
    exchange_instance = create_exchange(exchange_type, api_key, api_secret, exchange_name, passphrase=passphrase)
    db_manager = DatabaseManager(database_url=database_url)
    rest_data_service = RestDataService(db_manager)
    metrics_account = account_id or (account_name or "default")
    exchange_label = exchange_name.value
    exchange_type_label = exchange_type.value
    ensure_metrics_server()
    
    async def watch_loop():
        iteration = 0
        try:
            await exchange_instance.connect()
            # 确保所需表存在（使用默认表，不支持账号特定表）
            try:
                await db_manager.create_tables()
            except Exception as init_exc:
                logger.warning(f"账号 {account_label} 初始化数据库表失败: {init_exc}")
            
            while True:
                iteration += 1
                current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                console.print(f"\n[cyan][账号 {account_label}] 第 {iteration} 次查询 - {current_time}[/cyan]")
                
                try:
                    balance_data = await exchange_instance.get_balance()
                    record_balance_query_status(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        success=True,
                    )
                    update_balance_metrics(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        balance_data,
                    )
                    
                    if not balance_data:
                        console.print(f"[yellow][账号 {account_label}] 账户余额为空或所有币种余额为0[/yellow]")
                    else:
                        # 根据输出格式显示
                        if output == "json":
                            print_json(balance_data)
                        else:  # table (default)
                            format_balance_table(balance_data, exchange_instance)
                        
                        # 保存到数据库（使用 exchange-specific REST 表，如 binance_balance_rest）
                        try:
                            await rest_data_service.save_balance_query(
                                exchange=exchange_name.value,
                                exchange_type=exchange_type.value,
                                balances_data=balance_data,
                                query_type="scheduled",
                                account_id=account_id,
                            )
                            console.print(
                                f"[green]✓[/green] [账号 {account_label}] 余额数据 ({exchange_type.value}) 已保存到 [cyan]{exchange_name.value}_account_snapshot[/cyan]"
                            )
                        except Exception as save_exc:
                            logger.warning(
                                f"账号 {account_label} 保存余额失败: {save_exc}",
                                extra={"exchange": exchange_name.value, "account_id": account_id},
                            )
                            console.print(f"[red]✗[/red] [账号 {account_label}] 保存余额失败: {save_exc}")
                        
                        next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval)
                        console.print(f"[dim][账号 {account_label}] 下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
                
                except Exception as e:
                    record_balance_query_status(
                        exchange_label,
                        exchange_type_label,
                        metrics_account,
                        success=False,
                    )
                    console.print(f"[red][账号 {account_label}] 查询失败:[/red] {e}")
                    logger.error("账号 %s watch-balance query error: %s", account_label, e)
                    if debug:
                        console.print_exception()
                
                console.print(f"[dim][账号 {account_label}] 等待 {interval} 分钟...[/dim]")
                await asyncio.sleep(interval * 60)
        
        except KeyboardInterrupt:
            console.print(f"\n[yellow][账号 {account_label}] 监控已停止[/yellow]")
            raise
        except Exception as e:
            console.print(f"[red][账号 {account_label}] 监控异常:[/red] {e}")
            logger.error("账号 %s watch-balance error: %s", account_label, e)
            if debug:
                console.print_exception()
            raise
        finally:
            try:
                await exchange_instance.disconnect()
            except Exception:
                pass
    
    await watch_loop()


async def _run_binance_watch_account_async(
    interval_minutes: int,
    api_key: str,
    api_secret: str,
    debug: bool,
    enable_lark: bool,
    lark_webhook: Optional[str],
    lark_secret: Optional[str],
    metrics_config: Optional[str],
    enable_metrics: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """Binance 账户监控实现（spot + perp + positions）."""
    from rich.table import Table
    from tri_arb.exchanges.binance_spot import BinanceSpotExchange
    from tri_arb.exchanges.binance_perp import BinancePerpExchange

    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的 Binance 账户监控")

    if enable_lark:
        console.print("[yellow]提示:[/yellow] Binance 模式暂不支持 Lark 告警，选项已忽略。")
    if enable_metrics:
        console.print("[yellow]提示:[/yellow] Binance 模式暂不支持指标评估，选项已忽略。")

    db_manager = DatabaseManager(database_url=database_url)
    rest_data_service = RestDataService(db_manager)
    metrics_account = account_id or (account_name or "default")
    spot_exchange = BinanceSpotExchange(api_key=api_key, api_secret=api_secret)
    perp_exchange = BinancePerpExchange(api_key=api_key, api_secret=api_secret)

    async def fetch_and_display(iteration_num: int):
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"\n[cyan][账号 {account_label}] 第 {iteration_num} 次查询 - {current_time}[/cyan]")

        # Spot balances
        try:
            spot_balances = await spot_exchange.get_balance()
            if spot_balances:
                spot_table = Table(
                    title=f"Binance 现货账户余额 - {account_label}",
                    show_header=True,
                    header_style="bold magenta",
                )
                spot_table.add_column("Currency", style="cyan", width=12)
                spot_table.add_column("Available", justify="right", style="green")
                spot_table.add_column("Frozen", justify="right", style="yellow")
                spot_table.add_column("Total", justify="right", style="white")

                for currency, data in spot_balances.items():
                    available = Decimal(str(data.get("available", 0)))
                    frozen = Decimal(str(data.get("frozen", 0)))
                    total = Decimal(str(data.get("total", available + frozen)))
                    spot_table.add_row(
                        currency,
                        f"{available:.8f}",
                        f"{frozen:.8f}",
                        f"{total:.8f}",
                    )

                console.print(spot_table)
                console.print(
                    f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n"
                )

                await rest_data_service.save_balance_query(
                    exchange="binance",
                    exchange_type="spot",
                    balances_data=spot_balances,
                    query_type="scheduled",
                    account_id=account_id,
                )
                console.print(f"[green]✓[/green] [账号 {account_label}] 余额数据 (spot) 已保存到 [cyan]binance_account_snapshot[/cyan]")
                # 更新 Prometheus 指标
                update_balance_metrics(
                    "binance",
                    "spot",
                    metrics_account,
                    spot_balances,
                )
            else:
                console.print(f"[yellow][账号 {account_label}] Binance 现货账户余额为空[/yellow]")
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取现货余额失败:[/red] {exc}")
            if debug:
                console.print_exception()

        # Perp balances
        try:
            perp_balances = await perp_exchange.get_balance()
            if perp_balances:
                perp_table = Table(
                    title=f"Binance 合约账户余额 - {account_label}",
                    show_header=True,
                    header_style="bold magenta",
                )
                perp_table.add_column("Currency", style="cyan", width=12)
                perp_table.add_column("Available", justify="right", style="green")
                perp_table.add_column("Frozen", justify="right", style="yellow")
                perp_table.add_column("Total", justify="right", style="white")
                perp_table.add_column("Unrealized PnL", justify="right")

                for currency, data in perp_balances.items():
                    available = Decimal(str(data.get("available", 0)))
                    frozen = Decimal(str(data.get("frozen", 0)))
                    total = Decimal(str(data.get("total", 0)))
                    unrealized = Decimal(str(data.get("unrealized_pnl", 0)))
                    perp_table.add_row(
                        currency,
                        f"{available:.8f}",
                        f"{frozen:.8f}",
                        f"{total:.8f}",
                        f"{unrealized:.8f}",
                    )

                console.print(perp_table)
                console.print(
                    f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n"
                )

                await rest_data_service.save_balance_query(
                    exchange="binance",
                    exchange_type="perp",
                    balances_data=perp_balances,
                    query_type="scheduled",
                    account_id=account_id,
                )
                console.print(f"[green]✓[/green] [账号 {account_label}] 余额数据 (perp) 已保存到 [cyan]binance_account_snapshot[/cyan]")
                # 更新 Prometheus 指标
                update_balance_metrics(
                    "binance",
                    "perp",
                    metrics_account,
                    perp_balances,
                )
            else:
                console.print(f"[yellow][账号 {account_label}] Binance 合约账户余额为空[/yellow]")
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取合约余额失败:[/red] {exc}")
            if debug:
                console.print_exception()

        # Positions
        try:
            positions = await perp_exchange.get_positions()
            if positions:
                position_table = Table(
                    title=f"Binance 合约仓位 - {account_label}",
                    show_header=True,
                    header_style="bold magenta",
                )
                position_table.add_column("Symbol", style="cyan")
                position_table.add_column("Side", style="yellow")
                position_table.add_column("Quantity", justify="right")
                position_table.add_column("Entry", justify="right")
                position_table.add_column("Mark", justify="right")
                position_table.add_column("Unrealized PnL", justify="right")
                position_table.add_column("Leverage", justify="right")

                formatted_positions: list[dict[str, Any]] = []
                for pos in positions:
                    qty = Decimal(str(pos.get("positionAmt", "0")))
                    entry = Decimal(str(pos.get("entryPrice", "0")))
                    mark = Decimal(str(pos.get("markPrice", "0")))
                    unrealized = Decimal(str(pos.get("unRealizedProfit", "0")))
                    side = pos.get("positionSide", "BOTH") or "BOTH"
                    leverage = pos.get("leverage", "1")

                    position_table.add_row(
                        pos.get("symbol", ""),
                        side,
                        f"{qty:.8f}",
                        f"{entry:.4f}",
                        f"{mark:.4f}",
                        f"{unrealized:.4f}",
                        str(leverage),
                    )
                    formatted_positions.append(pos)

                console.print(position_table)
                console.print(
                    f"[dim][账号 {account_label}] 仓位获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n"
                )

                await rest_data_service.save_positions_query(
                    exchange="binance",
                    exchange_type="perp",
                    positions_data=formatted_positions,
                    query_type="scheduled",
                    account_id=account_id,
                )
                console.print(f"[green]✓[/green] [账号 {account_label}] 仓位数据 (perp) 已保存到 [cyan]binance_position_snapshot[/cyan]")
                # 更新 Prometheus 指标
                update_position_metrics(
                    "binance",
                    "perp",
                    metrics_account,
                    formatted_positions,
                )
            else:
                console.print(f"[yellow][账号 {account_label}] Binance 当前无持仓[/yellow]")
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取合约仓位失败:[/red] {exc}")
            if debug:
                console.print_exception()

        # 查询活跃订单并更新 metrics（当前挂单数量）
        try:
            active_orders = await perp_exchange.get_open_orders(None)
            # 更新 Prometheus metrics
            ensure_metrics_server()
            try:
                update_active_orders_metrics(
                    exchange="binance",
                    exchange_type="perp",
                    account_id=metrics_account,
                    orders=active_orders if active_orders else [],
                )
            except Exception as metric_error:
                logger.error(f"Failed to update active orders metrics: {metric_error}", exc_info=True)
        except Exception as exc:
            logger.debug(f"获取活跃订单失败: {exc}")

        next_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)
        console.print(f"[dim]下次查询: {next_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
        console.print(f"[dim]等待 {interval_minutes} 分钟...[/dim]\n")

    async def watch_loop():
        iteration = 0
        try:
            await spot_exchange.connect()
            await perp_exchange.connect()
            while True:
                iteration += 1
                await fetch_and_display(iteration)
                await asyncio.sleep(interval_minutes * 60)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            console.print(f"\n[yellow][账号 {account_label}] 监控已停止[/yellow]")
            raise
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 监控异常:[/red] {exc}")
            logger.error("Binance watch-account loop error: %s", exc)
            if debug:
                console.print_exception()
            raise
        finally:
            try:
                await spot_exchange.disconnect()
            except Exception:
                pass
            try:
                await perp_exchange.disconnect()
            except Exception:
                pass

    await watch_loop()


@app.command("watch-account")
def watch_account(
    exchange: ExchangeName = typer.Option(
        ExchangeName.XT,
        "--exchange",
        "-x",
        help="交易所 (xt, binance, okx, gate)，默认 xt"
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
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    ),
    enable_lark: bool = typer.Option(
        False,
        "--enable-lark",
        help="启用 Lark 告警推送（需配置 webhook）"
    ),
    interval_minutes: int = typer.Option(
        10,
        "--interval",
        "-i",
        help="查询间隔（分钟），默认 10 分钟"
    ),
    lark_webhook: Optional[str] = typer.Option(
        None,
        "--lark-webhook",
        help="Lark 群机器人 Webhook，未提供时可使用环境变量 LARK_WEBHOOK_URL"
    ),
    lark_secret: Optional[str] = typer.Option(
        None,
        "--lark-secret",
        help="Lark 机器人签名密钥（可选；未提供则不做签名）"
    ),
    metrics_config: Optional[str] = typer.Option(
        None,
        "--metrics-config",
        help="指标配置文件路径（YAML）。未提供时可使用环境变量 METRICS_CONFIG_PATH"
    ),
    enable_metrics: bool = typer.Option(
        True,
        "--enable-metrics/--disable-metrics",
        help="是否启用指标评估（默认启用）"
    ),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="账号ID（可选），如果提供则使用账号特定的表。例如: account_001"
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="账号配置文件路径（JSON格式）。如果提供，将从配置文件读取账号信息（API密钥、Lark配置、指标配置等）"
    ),
    accounts: Optional[str] = typer.Option(
        None,
        "--accounts",
        help="多个账号ID（逗号分隔），例如: account_001,account_002。需要配合 --config 使用，只监控 enabled: true 的账号"
    ),
    all_accounts: bool = typer.Option(
        False,
        "--all-accounts",
        help="从配置文件读取所有启用的账号（enabled: true）并同时监控。需要配合 --config 使用"
    ),
):
    """定时获取账户数据（现货余额、合约余额、合约仓位）.
    
    每个周期自动获取一次交易所的：
    - 现货账户余额
    - 合约账户余额  
    - 合约账户仓位
    
    数据自动保存到PostgreSQL数据库。
    如果提供账号ID，数据会保存到账号特定的表中（例如: xt_spot_balances_account_001）。
    表会在首次运行时自动创建，不会重复创建。
    
    支持从配置文件读取账号信息：
    - 如果提供了 --config 和 --account-id，将从配置文件读取该账号的 API 密钥、Lark 配置和指标配置
    - 如果提供了 --config 和 --accounts，将同时监控多个账号（逗号分隔，只监控 enabled: true 的账号）
    - 如果提供了 --config 和 --all-accounts，将监控配置文件中所有 enabled: true 的账号
    - 配置文件格式参考: config/accounts.example.json
    
    按 Ctrl+C 停止监控。
    
    示例:
        # 使用环境变量中的API密钥（XT交易所）
        cextools account watch-account -x xt
        
        # 使用账号特定的表
        cextools account watch-account -x xt --account-id account_001
        
        # 从配置文件读取账号信息
        cextools account watch-account -x xt --config config/accounts.json --account-id account_001
        
        # 同时监控多个账号（只监控启用的账号）
        cextools account watch-account -x xt --config config/accounts.json --accounts account_001,account_002
        
        # 监控配置文件中所有启用的账号
        cextools account watch-account -x xt --config config/accounts.json --all-accounts
        
        # 通过命令行参数提供API密钥
        cextools account watch-account -x xt --api-key YOUR_KEY --api-secret YOUR_SECRET
        
        # 启用调试模式
        cextools account watch-account -x xt --debug
    """
    account_manager = None
    selected_account_config = None

    def resolve_credentials(target_exchange: ExchangeName, key: Optional[str], secret: Optional[str]) -> tuple[str, str]:
        env_prefix = target_exchange.value.upper()
        final_key = key or os.getenv(f"{env_prefix}_API_KEY", "")
        final_secret = secret or os.getenv(f"{env_prefix}_API_SECRET", "")
        return final_key, final_secret
    try:
        # 检查交易所支持情况
        if exchange != ExchangeName.XT:
            console.print(f"[red]错误:[/red] 交易所 '{exchange.value}' 暂时不支持 watch-account 功能")
            console.print("\n目前仅支持以下交易所:")
            console.print("  • xt (XT交易所)")
            console.print("\n请使用: [cyan]cextools account watch-account -x xt[/cyan]")
            raise typer.Exit(code=1)
        
        # 检查是否使用多账号模式
        account_id_list = None
        if accounts:
            account_id_list = [acc_id.strip() for acc_id in accounts.split(",")]
        elif all_accounts:
            if not config_path:
                console.print("[red]错误:[/red] --all-accounts 需要配合 --config 使用")
                raise typer.Exit(code=1)
            try:
                from tri_arb.config.account_manager import AccountManager
                if account_manager is None:
                    account_manager = AccountManager(config_path)
                enabled_accounts = account_manager.get_enabled_accounts()
                account_id_list = [acc.account_id for acc in enabled_accounts]
                if not account_id_list:
                    console.print("[red]错误:[/red] 配置文件中没有启用的账号")
                    raise typer.Exit(code=1)
            except Exception as e:
                console.print(f"[red]错误:[/red] 读取配置文件失败: {e}")
                raise typer.Exit(code=1)
        
        # 多账号模式
        if account_id_list:
            if not config_path:
                console.print("[red]错误:[/red] 多账号模式需要配合 --config 使用")
                raise typer.Exit(code=1)
            
            try:
                from tri_arb.config.account_manager import AccountManager
                account_manager = AccountManager(config_path)
                
                # 验证所有账号是否存在，并过滤出启用的账号
                account_configs = []
                for acc_id in account_id_list:
                    acc_config = account_manager.get_account(acc_id)
                    if not acc_config:
                        console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号: {acc_id}，跳过")
                        continue
                    if not acc_config.enabled:
                        console.print(f"[yellow]警告:[/yellow] 账号 {acc_id} 未启用（enabled: false），跳过")
                        continue
                    account_configs.append(acc_config)
                
                if not account_configs:
                    console.print("[red]错误:[/red] 没有可用的启用账号")
                    raise typer.Exit(code=1)
                
                console.print(f"[cyan]多账号监控模式[/cyan]")
                console.print(f"[cyan]账号数量: {len(account_configs)}[/cyan]")
                for acc in account_configs:
                    console.print(f"  - {acc.account_id}: {acc.name}")
                console.print(f"[cyan]查询间隔: {interval_minutes} 分钟[/cyan]")
                console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")
                
                # 为每个账号启动独立的监控任务
                # 从配置文件获取 database_url
                database_url = account_manager.global_settings.get("database_url")
                
                async def run_multi_account_watch():
                    tasks = []
                    for acc_config in account_configs:
                        try:
                            acc_exchange = ExchangeName(acc_config.exchange.lower())
                        except ValueError:
                            console.print(f"[yellow]警告:[/yellow] 账号 {acc_config.account_id} 使用不支持的交易所 {acc_config.exchange}，跳过")
                            continue

                        if acc_exchange == ExchangeName.XT:
                            task = asyncio.create_task(
                                _run_xt_watch_account_async(
                                    interval_minutes=interval_minutes,
                                    api_key=acc_config.api_key,
                                    api_secret=acc_config.api_secret,
                                    debug=debug,
                                    enable_lark=enable_lark,
                                    lark_webhook=acc_config.lark_webhook if enable_lark else None,
                                    lark_secret=acc_config.lark_secret if enable_lark else None,
                                    metrics_config=metrics_config,
                                    enable_metrics=enable_metrics,
                                    account_id=acc_config.account_id,
                                    account_name=acc_config.name,
                                    database_url=database_url,
                                )
                            )
                        elif acc_exchange == ExchangeName.BINANCE:
                            task = asyncio.create_task(
                                _run_binance_watch_account_async(
                                    interval_minutes=interval_minutes,
                                    api_key=acc_config.api_key,
                                    api_secret=acc_config.api_secret,
                                    debug=debug,
                                    enable_lark=enable_lark,
                                    lark_webhook=acc_config.lark_webhook if enable_lark else None,
                                    lark_secret=acc_config.lark_secret if enable_lark else None,
                                    metrics_config=metrics_config,
                                    enable_metrics=enable_metrics,
                                    account_id=acc_config.account_id,
                                    account_name=acc_config.name,
                                    database_url=database_url,
                                )
                            )
                        else:
                            console.print(f"[yellow]警告:[/yellow] 账号 {acc_config.account_id} 的交易所 {acc_exchange.value} 暂不支持 watch-account，已跳过")
                            continue

                        tasks.append(task)
                        await asyncio.sleep(0.5)

                    if not tasks:
                        console.print("[red]错误:[/red] 选择的账号交易所暂不支持 watch-account 功能")
                        return
                    
                    try:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    except KeyboardInterrupt:
                        console.print("\n[yellow]监控已停止[/yellow]")
                
                asyncio.run(run_multi_account_watch())
                return
                
            except Exception as e:
                console.print(f"[red]错误:[/red] 多账号模式启动失败: {e}")
                if debug:
                    console.print_exception()
                raise typer.Exit(code=1)
        
        # 单账号模式：如果提供了配置文件，尝试从配置文件读取账号信息
        if config_path and account_id:
            try:
                from tri_arb.config.account_manager import AccountManager
                if account_manager is None:
                    account_manager = AccountManager(config_path)
                account_config = account_manager.get_account(account_id)
                
                if account_config:
                    selected_account_config = account_config
                    try:
                        exchange = ExchangeName(account_config.exchange.lower())
                    except ValueError:
                        console.print(f"[yellow]警告:[/yellow] 账号 {account_id} 配置的交易所 {account_config.exchange} 无效，保持命令行参数")
                    
                    # 检查账号是否启用
                    if not account_config.enabled:
                        console.print(f"[yellow]警告:[/yellow] 账号 {account_id} 未启用（enabled: false）")
                    
                    # 从配置文件读取 API 密钥（如果命令行未提供）
                    if not api_key:
                        api_key = account_config.api_key
                    if not api_secret:
                        api_secret = account_config.api_secret
                    
                    # 从配置文件读取 Lark 配置（如果命令行未提供且启用 Lark）
                    if enable_lark and not lark_webhook:
                        lark_webhook = account_config.lark_webhook
                    if enable_lark and not lark_secret:
                        lark_secret = account_config.lark_secret
                    
                    console.print(f"[cyan]从配置文件加载账号: {account_id} ({account_config.name})[/cyan]")
                else:
                    console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号 {account_id}，使用命令行参数或环境变量")
            except Exception as e:
                console.print(f"[yellow]警告:[/yellow] 读取配置文件失败: {e}，使用命令行参数或环境变量")
        
        database_url = account_manager.global_settings.get("database_url") if account_manager else None
        account_display_name = selected_account_config.name if selected_account_config else None
        final_api_key, final_api_secret = resolve_credentials(exchange, api_key, api_secret)

        if interval_minutes <= 0:
            console.print("[red]错误:[/red] 查询间隔必须大于 0 分钟")
            raise typer.Exit(code=1)

        if exchange == ExchangeName.XT:
            if not final_api_key or not final_api_secret:
                console.print("[red]错误:[/red] 缺少 XT API 密钥配置")
                console.print("\n请设置环境变量或使用命令行参数:")
                console.print("  环境变量: export XT_API_KEY=your_key && export XT_API_SECRET=your_secret")
                console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
                console.print("  配置文件: --config config/accounts.json --account-id account_001")
                raise typer.Exit(code=1)

            console.print("[cyan]启动 XT 账户定时任务服务[/cyan]")
            console.print(f"[cyan]查询间隔: {interval_minutes} 分钟[/cyan]")
            console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")

            asyncio.run(
                _run_xt_watch_account_async(
                    interval_minutes=interval_minutes,
                    api_key=final_api_key,
                    api_secret=final_api_secret,
                    debug=debug,
                    enable_lark=enable_lark,
                    lark_webhook=lark_webhook,
                    lark_secret=lark_secret,
                    metrics_config=metrics_config,
                    enable_metrics=enable_metrics,
                    account_id=account_id,
                    account_name=account_display_name,
                    database_url=database_url,
                )
            )
            return

        if exchange == ExchangeName.BINANCE:
            if not final_api_key or not final_api_secret:
                console.print("[red]错误:[/red] 缺少 Binance API 密钥配置")
                console.print("\n请设置环境变量或使用命令行参数:")
                console.print("  环境变量: export BINANCE_API_KEY=your_key && export BINANCE_API_SECRET=your_secret")
                console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
                console.print("  配置文件: --config config/accounts.json --account-id account_001")
                raise typer.Exit(code=1)

            console.print("[cyan]启动 Binance 账户定时任务服务[/cyan]")
            console.print(f"[cyan]查询间隔: {interval_minutes} 分钟[/cyan]")
            console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")

            asyncio.run(
                _run_binance_watch_account_async(
                    interval_minutes=interval_minutes,
                    api_key=final_api_key,
                    api_secret=final_api_secret,
                    debug=debug,
                    enable_lark=enable_lark,
                    lark_webhook=lark_webhook,
                    lark_secret=lark_secret,
                    metrics_config=metrics_config,
                    enable_metrics=enable_metrics,
                    account_id=account_id,
                    account_name=account_display_name,
                    database_url=database_url,
                )
            )
            return

        console.print(f"[red]错误:[/red] 交易所 '{exchange.value}' 暂不支持 watch-account 功能")
        raise typer.Exit(code=1)


        
    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
    except ValueError as e:
        error_msg = str(e) if str(e) else "配置错误，请检查API密钥"
        console.print(f"[red]配置错误:[/red] {error_msg}")
        raise typer.Exit(code=1)
    except Exception as e:
        if debug:
            console.print_exception()
        else:
            error_msg = str(e) if str(e) else f"未知错误: {type(e).__name__}"
            console.print(f"[red]错误:[/red] {error_msg}")
        raise typer.Exit(code=1)


async def _run_xt_watch_account_async(
    interval_minutes: int,
    api_key: str,
    api_secret: str,
    debug: bool,
    enable_lark: bool,
    lark_webhook: Optional[str],
    lark_secret: Optional[str],
    metrics_config: Optional[str],
    enable_metrics: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """异步版本的 XT 账户监控（用于多账号并发）."""
    from rich.table import Table
    from tri_arb.exchanges.xt_spot import XTSpotExchange
    from tri_arb.exchanges.xt_perp import XTPerpExchange
    from tri_arb.services.xt_rest_data_service import XTRestDataService

    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的账户监控")

    metrics_account = account_id or (account_name or "default")
    exchange_label = ExchangeName.XT.value
    ensure_metrics_server()

    db_manager = DatabaseManager(database_url=database_url)
    spot_exchange = XTSpotExchange(
        name="xt",
        api_key=api_key,
        api_secret=api_secret,
    )
    perp_exchange = XTPerpExchange(
        api_key=api_key,
        api_secret=api_secret,
    )
    xt_rest_service = XTRestDataService(db_manager, account_id=account_id)

    webhook_url: Optional[str] = lark_webhook
    webhook_secret: Optional[str] = lark_secret
    if enable_lark and not webhook_url:
        webhook_url = os.getenv("LARK_WEBHOOK_URL")
    if enable_lark and not webhook_secret:
        webhook_secret = os.getenv("LARK_WEBHOOK_SECRET")

    metrics_definition: Optional[MetricsConfig] = None
    if enable_metrics:
        metrics_path = metrics_config or os.getenv("METRICS_CONFIG_PATH")
        metrics_definition = load_metrics_config(metrics_path)
        if not metrics_definition.exchanges:
            logger.info(f"账号 {account_label} 指标配置为空，跳过指标评估")
            metrics_definition = None

    async def fetch_and_display(iteration_num: int):
        """获取数据并显示表格."""
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        console.print(f"\n[cyan][账号 {account_label}] 第 {iteration_num} 次查询 - {current_time}[/cyan]")

        try:
            # 1. 获取并显示现货账户余额
            try:
                spot_balances = await spot_exchange.get_balance()
                record_balance_query_status(
                    exchange_label,
                    "spot",
                    metrics_account,
                    success=True,
                )
                if spot_balances:
                    spot_table = Table(
                        title=f"XT 现货账户余额 - {account_label}",
                        show_header=True,
                        header_style="bold magenta"
                    )
                    spot_table.add_column("Currency", style="cyan", width=12)
                    spot_table.add_column("Available", justify="right", style="green")
                    spot_table.add_column("Frozen", justify="right", style="yellow")
                    spot_table.add_column("Total", justify="right", style="white")
                    
                    for currency, data in spot_balances.items():
                        available = data.get('available', Decimal('0'))
                        frozen = data.get('frozen', Decimal('0'))
                        total = data.get('total', available + frozen)
                        
                        spot_table.add_row(
                            currency,
                            f"{available:.8f}",
                            f"{frozen:.8f}",
                            f"{total:.8f}",
                        )
                    
                    console.print(spot_table)
                    console.print(f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                    
                    await xt_rest_service.save_spot_balance(
                        balances_data=spot_balances,
                        query_type="scheduled",
                    )
                    # 更新 Prometheus 指标
                    update_balance_metrics(
                        exchange_label,
                        "spot",
                        metrics_account,
                        spot_balances,
                    )
                else:
                    console.print(f"[yellow][账号 {account_label}] XT 现货账户余额为空[/yellow]\n")
            except Exception as e:
                record_balance_query_status(
                    exchange_label,
                    "spot",
                    metrics_account,
                    success=False,
                )
                console.print(f"[red][账号 {account_label}] 获取现货余额失败:[/red] {e}\n")
                if debug:
                    console.print_exception()

            # 2. 获取并显示合约账户余额
            try:
                perp_balances = await perp_exchange.get_balance()
                record_balance_query_status(
                    exchange_label,
                    "perp",
                    metrics_account,
                    success=True,
                )
                if perp_balances:
                    balances_data: dict[str, dict[str, Any]] = {}
                    for currency, balance_info in perp_balances.items():
                        # 包含所有字段，特别是保证金占用率计算所需的字段
                        balances_data[currency] = {
                            "available": balance_info.get("available", Decimal("0")),
                            "frozen": balance_info.get("frozen", Decimal("0")),
                            "total": balance_info.get("total", Decimal("0")),
                            "unrealized_pnl": balance_info.get("unrealized_pnl", Decimal("0")),
                            "realized_pnl": balance_info.get("realized_pnl", Decimal("0")),
                            "equity": balance_info.get("equity", Decimal("0")),
                            "margin": balance_info.get("margin", Decimal("0")),
                            "margin_ratio": balance_info.get("margin_ratio", Decimal("0")),
                            # 保证金占用率计算所需字段
                            "openOrderMarginFrozen": balance_info.get("openOrderMarginFrozen", balance_info.get("frozen", Decimal("0"))),
                            "isolatedMargin": balance_info.get("isolatedMargin", Decimal("0")),
                            "crossedMargin": balance_info.get("crossedMargin", Decimal("0")),
                            "totalAmount": balance_info.get("totalAmount", Decimal("0")),
                            "walletBalance": balance_info.get("walletBalance", Decimal("0")),
                            "marginBalance": balance_info.get("marginBalance", Decimal("0")),
                        }

                    perp_table = Table(
                        title=f"XT 合约账户余额 - {account_label}",
                        show_header=True,
                        header_style="bold magenta"
                    )
                    perp_table.add_column("Currency", style="cyan", width=12)
                    perp_table.add_column("Available", justify="right", style="green")
                    perp_table.add_column("Frozen", justify="right", style="yellow")
                    perp_table.add_column("Total", justify="right", style="white")
                    perp_table.add_column("Unrealized PnL", justify="right")
                    perp_table.add_column("Realized PnL", justify="right")
                    perp_table.add_column("Equity", justify="right")
                    perp_table.add_column("Margin", justify="right")

                    for currency, data in balances_data.items():
                        available = data.get("available", Decimal("0"))
                        frozen = data.get("frozen", Decimal("0"))
                        total = data.get("total", Decimal("0"))
                        unrealized_pnl = data.get("unrealized_pnl", Decimal("0"))
                        realized_pnl = data.get("realized_pnl", Decimal("0"))
                        equity = data.get("equity", Decimal("0"))
                        margin = data.get("margin", Decimal("0"))

                        unrealized_style = "green" if unrealized_pnl >= 0 else "red"
                        realized_style = "green" if realized_pnl >= 0 else "red"

                        perp_table.add_row(
                            currency,
                            f"{available:.8f}",
                            f"{frozen:.8f}",
                            f"{total:.8f}",
                            f"[{unrealized_style}]{unrealized_pnl:.8f}[/{unrealized_style}]",
                            f"[{realized_style}]{realized_pnl:.8f}[/{realized_style}]",
                            f"{equity:.8f}",
                            f"{margin:.8f}",
                        )

                    console.print(perp_table)
                    console.print(f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                    
                    await xt_rest_service.save_perp_balance(
                        balances_data=balances_data,
                        query_type="scheduled",
                    )
                    # 更新 Prometheus 指标
                    update_balance_metrics(
                        exchange_label,
                        "perp",
                        metrics_account,
                        balances_data,
                    )
                else:
                    console.print(f"[yellow][账号 {account_label}] XT 合约账户余额为空[/yellow]\n")
            except Exception as e:
                record_balance_query_status(
                    exchange_label,
                    "perp",
                    metrics_account,
                    success=False,
                )
                console.print(f"[red][账号 {account_label}] 获取合约余额失败:[/red] {e}\n")
                if debug:
                    console.print_exception()

            # 3. 获取并显示合约账户仓位
            try:
                positions = await perp_exchange.get_positions(symbol=None)
                if positions:
                    position_table = Table(
                        title=f"XT 合约账户仓位 - {account_label}",
                        show_header=True,
                        header_style="bold magenta"
                    )
                    position_table.add_column("Symbol", style="cyan")
                    position_table.add_column("Side", style="white")
                    position_table.add_column("Quantity", justify="right")
                    position_table.add_column("Entry Price", justify="right")
                    position_table.add_column("Mark Price", justify="right")
                    position_table.add_column("Liquidation Price", justify="right")
                    position_table.add_column("Unrealized PnL", justify="right")
                    position_table.add_column("Realized PnL", justify="right")
                    position_table.add_column("Maintenance Margin", justify="right")
                    position_table.add_column("Leverage", justify="right")

                    positions_data: list[dict[str, Any]] = []
                    for pos in positions:
                        if hasattr(pos, "symbol"):
                            pos_symbol = pos.symbol
                            side = getattr(pos, "side", getattr(pos, "position_side", ""))
                            quantity = getattr(pos, "quantity", Decimal("0"))
                            entry_price = getattr(pos, "entry_price", Decimal("0"))
                            mark_price = getattr(pos, "mark_price", Decimal("0"))
                            unrealized_pnl = getattr(pos, "unrealized_pnl", Decimal("0"))
                            realized_pnl = getattr(pos, "realized_pnl", Decimal("0"))
                            liquidation_price = getattr(pos, "liquidation_price", Decimal("0"))
                            leverage = getattr(pos, "leverage", "")
                            maintenance_margin = getattr(pos, "maintenance_margin", Decimal("0"))
                        else:
                            pos_symbol = pos.get("symbol", "")
                            side = pos.get("positionSide") or pos.get("side", "")
                            quantity = Decimal(str(pos.get("positionSize") or pos.get("positionAmt") or "0"))
                            entry_price = Decimal(str(pos.get("entryPrice") or "0"))
                            mark_price = Decimal(str(pos.get("calMarkPrice") or pos.get("markPrice") or "0"))
                            unrealized_pnl = Decimal(str(pos.get("floatingPL") or pos.get("unRealizedProfit") or pos.get("unrealizedPnl") or "0"))
                            realized_pnl = Decimal(str(pos.get("realizedProfit") or pos.get("realizedPnl") or "0"))
                            liquidation_price = Decimal(str(pos.get("breakPrice") or pos.get("liquidationPrice") or "0"))
                            leverage = pos.get("leverage", "")
                            maintenance_margin = Decimal(str(pos.get("maintMargin") or "0"))

                        if quantity == Decimal("0"):
                            continue

                        unrealized_style = "green" if unrealized_pnl >= 0 else "red"
                        realized_style = "green" if realized_pnl >= 0 else "red"

                        position_table.add_row(
                            pos_symbol,
                            side,
                            f"{quantity:.8f}",
                            f"{entry_price:.8f}",
                            f"{mark_price:.8f}",
                            f"{liquidation_price:.8f}",
                            f"[{unrealized_style}]{unrealized_pnl:.8f}[/{unrealized_style}]",
                            f"[{realized_style}]{realized_pnl:.8f}[/{realized_style}]",
                            f"{maintenance_margin:.8f}",
                            f"{leverage}x" if leverage else "-",
                        )

                        pos_dict = {
                            "symbol": pos_symbol,
                            "positionSide": side,
                            "positionSize": str(quantity),
                            "entryPrice": str(entry_price),
                            "calMarkPrice": str(mark_price),
                            "floatingPL": str(unrealized_pnl),
                            "realizedProfit": str(realized_pnl),
                            "breakPrice": str(liquidation_price),
                            "isolatedMargin": str(getattr(pos, "margin", Decimal("0")) if hasattr(pos, "margin") else pos.get("isolatedMargin", "0")),
                            "maintMargin": str(maintenance_margin),
                            "leverage": leverage,
                        }
                        positions_data.append(pos_dict)

                    if positions_data:
                        console.print(position_table)
                        console.print(f"[dim][账号 {account_label}] 数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                        
                        await xt_rest_service.save_perp_positions(
                            positions_data=positions_data,
                            query_type="scheduled",
                        )
                        # 更新 Prometheus 指标
                        update_position_metrics(
                            exchange_label,
                            "perp",
                            metrics_account,
                            positions_data,
                        )
                    else:
                        console.print(f"[yellow][账号 {account_label}] XT 当前无持仓[/yellow]\n")
                else:
                    console.print(f"[yellow][账号 {account_label}] XT 当前无持仓[/yellow]\n")
            except Exception as e:
                console.print(f"[red][账号 {account_label}] 获取仓位失败:[/red] {e}\n")
                if debug:
                    console.print_exception()

            # 查询活跃订单并更新 metrics（当前挂单数量）
            try:
                active_orders = await perp_exchange.get_open_orders(None)
                # 更新 Prometheus metrics
                ensure_metrics_server()
                try:
                    update_active_orders_metrics(
                        exchange=exchange_label if 'exchange_label' in locals() else "binance",
                        exchange_type="perp",
                        account_id=metrics_account,
                        orders=active_orders if active_orders else [],
                    )
                except Exception as metric_error:
                    logger.error(f"Failed to update active orders metrics: {metric_error}", exc_info=True)
            except Exception as e:
                logger.debug(f"获取活跃订单失败: {e}")

            # 4. 评估指标（如果启用）
            if metrics_definition:
                await _evaluate_metrics(
                    metrics_config=metrics_definition,
                    db_manager=db_manager,
                    enable_lark=enable_lark,
                    default_webhook=webhook_url,
                    default_secret=webhook_secret,
                    debug=debug,
                )

            # 显示下次查询时间
            next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval_minutes)
            console.print(f"[dim][账号 {account_label}] 下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
            console.print(f"[dim][账号 {account_label}] 等待 {interval_minutes} 分钟...[/dim]\n")

        except Exception as e:
            console.print(f"[red][账号 {account_label}] 查询过程出错:[/red] {e}")
            if debug:
                console.print_exception()

    iteration = 0
    try:
        # 创建数据库表
        if account_id:
            await xt_rest_service.ensure_account_tables()
            logger.info(f"账号 {account_label} 的数据库表已就绪")
        else:
            await db_manager.create_tables()

        # 连接交易所
        await spot_exchange.connect()
        await perp_exchange.connect()
        logger.info(f"账号 {account_label} 交易所连接成功")

        # 立即执行一次查询
        iteration = 1
        await fetch_and_display(iteration)

        # 定时查询循环
        while True:
            await asyncio.sleep(interval_minutes * 60)
            iteration += 1
            await fetch_and_display(iteration)

    except KeyboardInterrupt:
        logger.info(f"账号 {account_label} 的监控已停止")
    except Exception as e:
        logger.error("账号 %s 的监控异常: %s", account_label, e, exc_info=True)
        if debug:
            console.print_exception()
    finally:
        await spot_exchange.disconnect()
        await perp_exchange.disconnect()
        await db_manager.close()


async def _run_binance_watch_positions_async(
    interval: int,
    api_key: str,
    api_secret: str,
    symbol: Optional[str],
    debug: bool,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    database_url: Optional[str] = None,
) -> None:
    """异步版本的 Binance 仓位监控."""
    from rich.table import Table
    from tri_arb.exchanges.binance_perp import BinancePerpExchange

    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info("启动账号 %s 的 Binance 仓位监控", account_label)
    console.print(f"[cyan]启动账号 {account_label} 的 Binance 仓位监控[/cyan]")

    db_manager = DatabaseManager(database_url=database_url)
    rest_data_service = RestDataService(db_manager)
    perp_exchange = BinancePerpExchange(api_key=api_key, api_secret=api_secret)

    normalized_symbol: Optional[str] = None
    if symbol:
        normalized_symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()

    async def fetch_positions(iteration_num: int):
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        console.print(f"\n[cyan][账号 {account_label}] 第 {iteration_num} 次查询 - {current_time}[/cyan]")

        try:
            positions = await perp_exchange.get_positions(symbol=normalized_symbol)
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 获取仓位失败:[/red] {exc}")
            logger.error("账号 %s Binance 持仓查询失败: %s", account_label, exc)
            if debug:
                console.print_exception()
            return

        if not positions:
            console.print(f"[yellow][账号 {account_label}] 当前无持仓[/yellow]")
            return

        position_table = Table(
            title=f"Binance 合约仓位 - {account_label}",
            show_header=True,
            header_style="bold magenta",
        )
        position_table.add_column("Symbol", style="cyan")
        position_table.add_column("Side", style="yellow")
        position_table.add_column("Quantity", justify="right")
        position_table.add_column("Entry", justify="right")
        position_table.add_column("Mark", justify="right")
        position_table.add_column("Unrealized PnL", justify="right")
        position_table.add_column("Leverage", justify="right")

        for pos in positions:
            qty = Decimal(str(pos.get("positionAmt", "0")))
            entry_price = Decimal(str(pos.get("entryPrice", "0")))
            mark_price = Decimal(str(pos.get("markPrice", "0")))
            unrealized = Decimal(str(pos.get("unRealizedProfit", "0")))
            leverage = pos.get("leverage", "1")
            side = pos.get("positionSide") or ("LONG" if qty > 0 else "SHORT" if qty < 0 else "FLAT")

            position_table.add_row(
                pos.get("symbol", ""),
                side,
                f"{qty:.8f}",
                f"{entry_price:.4f}",
                f"{mark_price:.4f}",
                f"{unrealized:.4f}",
                str(leverage),
            )

        console.print(position_table)
        console.print(
            f"[dim][账号 {account_label}] 仓位获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n"
        )

        try:
            await rest_data_service.save_positions_query(
                exchange="binance",
                exchange_type="perp",
                positions_data=positions,
                query_type="scheduled",
                account_id=account_id,
            )
            console.print(f"[green]✓[/green] [账号 {account_label}] 仓位数据 (perp) 已保存到 [cyan]binance_position_snapshot[/cyan]")
        except Exception as save_exc:
            console.print(f"[red][账号 {account_label}] 保存仓位失败:[/red] {save_exc}")
            logger.error("账号 %s Binance 仓位保存失败: %s", account_label, save_exc)
            if debug:
                console.print_exception()

    async def watch_loop():
        iteration = 0
        try:
            await perp_exchange.connect()
            while True:
                iteration += 1
                await fetch_positions(iteration)
                await asyncio.sleep(interval * 60)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            console.print(f"\n[yellow][账号 {account_label}] 监控已停止[/yellow]")
            raise
        except Exception as exc:
            console.print(f"[red][账号 {account_label}] 监控异常:[/red] {exc}")
            logger.error("账号 %s Binance 监控异常: %s", account_label, exc)
            if debug:
                console.print_exception()
            raise
        finally:
            try:
                await perp_exchange.disconnect()
            except Exception:
                pass

    await watch_loop()


@app.command("watch-positions")
def watch_positions(
    exchange_type: ExchangeType = typer.Option(
        ExchangeType.PERP,
        "--exchange-type",
        "-e",
        help="交易类型（仅支持 perp，默认 perp）"
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
    ),
    lark_webhook: Optional[str] = typer.Option(
        None,
        "--lark-webhook",
        help="Lark群机器人Webhook URL，用于推送仓位告警"
    ),
    lark_secret: Optional[str] = typer.Option(
        None,
        "--lark-secret",
        help="Lark机器人签名密钥（若启用安全校验需提供）"
    ),
    enable_lark: bool = typer.Option(
        False,
        "--enable-lark/--disable-lark",
        help="启用/禁用 Lark 告警推送（默认禁用）"
    ),
    account_id: Optional[str] = typer.Option(
        None,
        "--account-id",
        "-a",
        help="账号ID（可选，仅支持XT），如果提供则使用账号特定的表。例如: account_001"
    ),
    config_path: Optional[str] = typer.Option(
        None,
        "--config",
        "-c",
        help="账号配置文件路径（JSON格式）。如果提供，将从配置文件读取账号信息（API密钥、Lark配置等）"
    ),
    accounts: Optional[str] = typer.Option(
        None,
        "--accounts",
        help="多个账号ID（逗号分隔），例如: account_001,account_002。需要配合 --config 使用"
    ),
    all_accounts: bool = typer.Option(
        False,
        "--all-accounts",
        help="从配置文件读取所有启用的账号并同时监控。需要配合 --config 使用"
    ),
):
    """定时查询持仓（仅永续合约）.
    
    每隔指定分钟查询一次持仓，持续监控持仓变化。
    如果提供账号ID（仅支持XT），数据会保存到账号特定的表中。
    表会在首次运行时自动创建，不会重复创建。
    
    支持从配置文件读取账号信息：
    - 如果提供了 --config 和 --account-id，将从配置文件读取该账号的 API 密钥和 Lark 配置
    - 如果提供了 --config 和 --accounts，将同时监控多个账号（逗号分隔）
    - 如果提供了 --config 和 --all-accounts，将监控配置文件中所有启用的账号
    - 配置文件格式参考: config/accounts.example.json
    
    按 Ctrl+C 停止监控。
    
    示例:
        # 每1分钟查询一次所有持仓
        cextools account watch-positions -e perp
        
        # 使用账号特定的表（XT）
        cextools account watch-positions -x xt -e perp --account-id account_001
        
        # 从配置文件读取单个账号信息
        cextools account watch-positions -x xt -e perp --config config/accounts.json --account-id account_001
        
        # 同时监控多个账号
        cextools account watch-positions -x xt -e perp --config config/accounts.json --accounts account_001,account_002
        
        # 监控配置文件中所有启用的账号
        cextools account watch-positions -x xt -e perp --config config/accounts.json --all-accounts
        
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

        webhook_url = None
        webhook_secret = None
        if enable_lark:
            webhook_url = lark_webhook or os.getenv("LARK_WEBHOOK_URL")
            if lark_secret is not None:
                webhook_secret = lark_secret or None
            else:
                webhook_secret = os.getenv("LARK_WEBHOOK_SECRET")

            if not webhook_url:
                console.print("[yellow]未提供 Lark Webhook，跳过告警推送[/yellow]")
                enable_lark = False

        if exchange == ExchangeName.XT:
            # 检查是否使用多账号模式
            account_id_list = None
            account_manager = None
            if accounts:
                account_id_list = [acc_id.strip() for acc_id in accounts.split(",")]
            elif all_accounts:
                if not config_path:
                    console.print("[red]错误:[/red] --all-accounts 需要配合 --config 使用")
                    raise typer.Exit(code=1)
                try:
                    from tri_arb.config.account_manager import AccountManager
                    account_manager = AccountManager(config_path)
                    enabled_accounts = account_manager.get_enabled_accounts()
                    account_id_list = [acc.account_id for acc in enabled_accounts]
                    if not account_id_list:
                        console.print("[red]错误:[/red] 配置文件中没有启用的账号")
                        raise typer.Exit(code=1)
                except Exception as e:
                    console.print(f"[red]错误:[/red] 读取配置文件失败: {e}")
                    raise typer.Exit(code=1)
            
            # 多账号模式
            if account_id_list:
                if not config_path:
                    console.print("[red]错误:[/red] 多账号模式需要配合 --config 使用")
                    raise typer.Exit(code=1)
                
                try:
                    from tri_arb.config.account_manager import AccountManager
                    # 如果之前已经初始化过，复用实例；否则创建新实例
                    if account_manager is None:
                        account_manager = AccountManager(config_path)
                    
                    # 验证所有账号是否存在，并过滤出启用的账号
                    account_configs = []
                    for acc_id in account_id_list:
                        acc_config = account_manager.get_account(acc_id)
                        if not acc_config:
                            console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号: {acc_id}，跳过")
                            continue
                        if not acc_config.enabled:
                            console.print(f"[yellow]警告:[/yellow] 账号 {acc_id} 未启用（enabled: false），跳过")
                            continue
                        account_configs.append(acc_config)
                    
                    if not account_configs:
                        console.print("[red]错误:[/red] 没有可用的启用账号")
                        raise typer.Exit(code=1)
                    
                    # 显示统计信息
                    all_accounts_list = account_manager.get_all_accounts()
                    total_count = len(all_accounts_list)
                    enabled_count = len(account_configs)
                    disabled_count = total_count - enabled_count
                    
                    console.print(f"[cyan]多账号监控模式[/cyan]")
                    console.print(f"[cyan]配置文件账号统计:[/cyan]")
                    console.print(f"  - 总账号数: {total_count}")
                    console.print(f"  - 启用账号: {enabled_count}")
                    if disabled_count > 0:
                        console.print(f"  - 禁用账号: {disabled_count} (已自动跳过)")
                    console.print(f"[cyan]监控账号列表:[/cyan]")
                    for acc in account_configs:
                        console.print(f"  - {acc.account_id}: {acc.name}")
                    console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
                    console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")
                    
                    # 为每个账号启动独立的监控任务
                    # 从配置文件获取 database_url
                    database_url = account_manager.global_settings.get("database_url")
                    
                    async def run_multi_account_watch():
                        tasks = []
                        for acc_config in account_configs:
                            try:
                                acc_exchange = ExchangeName(acc_config.exchange.lower())
                                console.print(f"[dim]调试: 账号 {acc_config.account_id} 交易所识别为: {acc_exchange.value}[/dim]")
                            except ValueError:
                                console.print(f"[yellow]警告:[/yellow] 账号 {acc_config.account_id} 使用未支持的交易所 {acc_config.exchange}，跳过")
                                continue

                            if acc_exchange == ExchangeName.XT:
                                console.print(f"[dim]调试: 账号 {acc_config.account_id} 路由到 XT 实现[/dim]")
                                task = asyncio.create_task(
                                    _run_xt_watch_positions_async(
                                        interval=interval,
                                        api_key=acc_config.api_key,
                                        api_secret=acc_config.api_secret,
                                        symbol=symbol,
                                        debug=debug,
                                        lark_webhook=acc_config.lark_webhook if enable_lark else None,
                                        lark_secret=acc_config.lark_secret if enable_lark else None,
                                        account_id=acc_config.account_id,
                                        account_name=acc_config.name,
                                        database_url=database_url,
                                    )
                                )
                            elif acc_exchange == ExchangeName.BINANCE:
                                console.print(f"[dim]调试: 账号 {acc_config.account_id} 路由到 Binance 实现[/dim]")
                                task = asyncio.create_task(
                                    _run_binance_watch_positions_async(
                                        interval=interval,
                                        api_key=acc_config.api_key,
                                        api_secret=acc_config.api_secret,
                                        symbol=symbol,
                                        debug=debug,
                                        account_id=acc_config.account_id,
                                        account_name=acc_config.name,
                                        database_url=database_url,
                                    )
                                )
                            else:
                                console.print(f"[yellow]警告:[/yellow] 账号 {acc_config.account_id} 的交易所 {acc_exchange.value} 暂不支持 watch-positions，跳过")
                                continue

                            tasks.append(task)
                            # 稍微延迟，避免同时连接过多
                            await asyncio.sleep(0.5)
                        
                        try:
                            results = await asyncio.gather(*tasks, return_exceptions=True)
                            # 检查是否有异常
                            for i, result in enumerate(results):
                                if isinstance(result, Exception):
                                    console.print(f"[red]账号 {account_configs[i].account_id} 监控任务异常:[/red] {result}")
                                    logger.error(f"账号 {account_configs[i].account_id} 监控任务异常", exc_info=result)
                                    if debug:
                                        console.print_exception()
                        except KeyboardInterrupt:
                            console.print("\n[yellow]监控已停止[/yellow]")
                        except Exception as e:
                            console.print(f"[red]多账号监控异常:[/red] {e}")
                            logger.error("多账号监控异常", exc_info=True)
                            if debug:
                                console.print_exception()
                    
                    asyncio.run(run_multi_account_watch())
                    return
                    
                except Exception as e:
                    console.print(f"[red]错误:[/red] 多账号模式启动失败: {e}")
                    if debug:
                        console.print_exception()
                    raise typer.Exit(code=1)
            
            # 单账号模式（原有逻辑）
            # 如果提供了配置文件，尝试从配置文件读取账号信息
            if config_path and account_id:
                try:
                    from tri_arb.config.account_manager import AccountManager
                    account_manager = AccountManager(config_path)
                    account_config = account_manager.get_account(account_id)
                    
                    if account_config:
                        # 从配置文件读取 API 密钥（如果命令行未提供）
                        if not api_key:
                            api_key = account_config.api_key
                        if not api_secret:
                            api_secret = account_config.api_secret
                        
                        # 从配置文件读取 Lark 配置（如果命令行未提供且启用 Lark）
                        if enable_lark and not webhook_url:
                            webhook_url = account_config.lark_webhook
                        if enable_lark and not webhook_secret:
                            webhook_secret = account_config.lark_secret
                        
                        console.print(f"[cyan]从配置文件加载账号: {account_id} ({account_config.name})[/cyan]")
                    else:
                        console.print(f"[yellow]警告:[/yellow] 配置文件中未找到账号 {account_id}，使用命令行参数或环境变量")
                except Exception as e:
                    console.print(f"[yellow]警告:[/yellow] 读取配置文件失败: {e}，使用命令行参数或环境变量")
            
            final_api_key = api_key or os.getenv("XT_API_KEY", "")
            final_api_secret = api_secret or os.getenv("XT_API_SECRET", "")

            if not final_api_key or not final_api_secret:
                console.print("[red]错误:[/red] 缺少XT API密钥配置")
                console.print("\n请设置环境变量或使用命令行参数:")
                console.print("  环境变量: export XT_API_KEY=your_key && export XT_API_SECRET=your_secret")
                console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
                console.print("  配置文件: --config config/accounts.json --account-id account_001")
                raise typer.Exit(code=1)

            _run_xt_watch_positions(
                interval=interval,
                api_key=final_api_key,
                api_secret=final_api_secret,
                symbol=symbol,
                debug=debug,
                lark_webhook=webhook_url if enable_lark else None,
                lark_secret=webhook_secret if enable_lark else None,
                account_id=account_id,
            )
            return

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
                        
                        # 更新 Prometheus metrics（当前挂单数量）
                        ensure_metrics_server()
                        try:
                            update_active_orders_metrics(
                                exchange=exchange.value,
                                exchange_type=exchange_type.value,
                                account_id="default",  # 单账号命令使用 default
                                orders=orders_data if orders_data else [],
                            )
                        except Exception as metric_error:
                            logger.error(f"Failed to update active orders metrics: {metric_error}", exc_info=True)
                        
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


async def _run_watch_orders_async(
    exchange: ExchangeName,
    interval: int,
    api_key: str,
    api_secret: str,
    symbol: Optional[str] = None,
    debug: bool = False,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
    passphrase: Optional[str] = None,
) -> None:
    """异步版本的 watch-orders 函数（用于多账号并发）.
    
    Args:
        exchange: 交易所名称
        interval: 查询间隔（分钟）
        api_key: API 密钥
        api_secret: API 密钥
        symbol: 交易对（可选）
        debug: 是否启用调试模式
        account_id: 账号ID（可选）
        account_name: 账号名称（可选）
        passphrase: API 密码短语（可选，用于某些交易所）
    """
    from tri_arb.exchanges.base import BaseExchange
    
    account_label = f"{account_id} ({account_name})" if account_name else account_id or "默认账号"
    logger.info(f"启动账号 {account_label} 的挂单监控 ({exchange.value})")
    
    # 创建 exchange 实例（仅支持永续合约）
    exchange_instance = create_exchange(ExchangeType.PERP, api_key, api_secret, exchange, passphrase=passphrase)
    
    metrics_account = account_id or (account_name or "default")
    exchange_label = exchange.value
    
    # 初始化数据库管理器
    db_manager = DatabaseManager()
    
    iteration = 0
    try:
        # 确保数据库表存在
        try:
            console.print(f"[cyan]正在检查/创建数据库表（账号 {account_label}）...[/cyan]")
            await db_manager.create_tables()
            console.print(f"[green]✅ 数据库表已就绪[/green]\n")
        except Exception as init_exc:
            console.print(f"[yellow]警告:[/yellow] 数据库表初始化失败: {init_exc}")
        
        await exchange_instance.connect()
        
        while True:
            iteration += 1
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            console.print(f"\n[cyan][账号 {account_label}] 第 {iteration} 次查询挂单 - {current_time}[/cyan]")
            
            try:
                # 获取所有挂单
                orders_data = await exchange_instance.get_open_orders(None)
                
                # 如果指定了symbol，在本地筛选
                if symbol:
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
                    console.print(f"[yellow][账号 {account_label}] 当前无挂单[/yellow]")
                else:
                    format_open_orders_table(orders_data, exchange_instance)
                    total_orders = len(orders_data)
                    buy_orders = sum(1 for o in orders_data if o.get('side', '').upper() == 'BUY' or o.get('side', '').lower() == 'buy')
                    sell_orders = total_orders - buy_orders
                    console.print(f"[dim][账号 {account_label}] 统计: 共 {total_orders} 个挂单 (买单: {buy_orders}, 卖单: {sell_orders})[/dim]")
                
                # 更新 Prometheus metrics（当前挂单数量）
                ensure_metrics_server()
                try:
                    update_active_orders_metrics(
                        exchange=exchange_label,
                        exchange_type="perp",
                        account_id=metrics_account,
                        orders=orders_data if orders_data else [],
                    )
                except Exception as metric_error:
                    logger.error(f"Failed to update active orders metrics: {metric_error}", exc_info=True)
                
                # 显示下次查询时间
                next_query_time = datetime.datetime.now() + datetime.timedelta(minutes=interval)
                console.print(f"[dim][账号 {account_label}] 下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
                
            except Exception as e:
                console.print(f"[red][账号 {account_label}] 查询挂单失败:[/red] {e}")
                logger.error(f"账号 {account_label} watch-orders query error: {e}")
                if debug:
                    console.print_exception()
            
            # 等待指定分钟数
            console.print(f"[dim][账号 {account_label}] 等待 {interval} 分钟...[/dim]\n")
            await asyncio.sleep(interval * 60)
            
    except KeyboardInterrupt:
        logger.info(f"账号 {account_label} 的挂单监控已停止")
    except Exception as e:
        logger.error(f"账号 {account_label} watch-orders error: {e}")
        if debug:
            console.print_exception()
        raise
    finally:
        try:
            await exchange_instance.disconnect()
        except Exception:
            pass
        try:
            await db_manager.close()
        except Exception:
            pass


@app.command("watch-all")
def watch_all(
    config_path: str = typer.Option(
        "config/accounts.json",
        "--config",
        "-c",
        help="账号配置文件路径（JSON格式）"
    ),
    accounts: Optional[str] = typer.Option(
        None,
        "--accounts",
        "-a",
        help="要监控的账号ID列表，用逗号分隔。留空则监控所有启用的账号"
    ),
    database_url: Optional[str] = typer.Option(
        None,
        "--database-url",
        help="数据库连接URL（覆盖配置文件和环境变量）"
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="启用调试模式"
    ),
):
    """同时运行 watch-balance、watch-account 和 watch-positions 命令.
    
    从配置文件读取账号信息，为每个账号同时启动三个监控任务：
    - watch-balance: 余额监控
    - watch-account: 账户监控（余额、持仓）
    - watch-positions: 持仓监控
    
    可以在配置文件中为每个账号指定要运行的 watch 任务：
    ```json
    {
      "accounts": {
        "account_001": {
          "name": "账号1",
          "exchange": "xt",
          "api_key": "...",
          "api_secret": "...",
          "enabled": true,
          "watch_tasks": {
            "balance": {"enabled": true, "exchange_type": "perp", "interval": 5},
            "account": {"enabled": true, "interval": 10},
            "positions": {"enabled": true, "interval": 1}
          }
        }
      }
    }
    ```
    
    如果配置文件中没有 watch_tasks，则默认启用所有任务。
    """
    import asyncio
    from tri_arb.config.account_manager import AccountManager
    
    try:
        # 加载账号配置
        account_manager = AccountManager(config_path)
    except FileNotFoundError:
        console.print(f"[red]错误:[/red] 配置文件不存在: {config_path}")
        console.print("请创建配置文件，参考: config/accounts.json")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]错误:[/red] 加载配置文件失败: {exc}")
        if debug:
            console.print_exception()
        raise typer.Exit(code=1)

    # 获取数据库URL
    db_url = database_url or account_manager.global_settings.get("database_url") or os.getenv("DATABASE_URL")
    if not db_url:
        console.print("[red]错误:[/red] 未指定数据库URL")
        console.print("请通过 --database-url 参数、配置文件 global_settings 或 DATABASE_URL 环境变量指定")
        raise typer.Exit(code=1)

    # 解析账号ID列表
    requested_ids = None
    if accounts:
        requested_ids = [acc_id.strip() for acc_id in accounts.split(",") if acc_id.strip()]
        if not requested_ids:
            console.print("[red]错误:[/red] --accounts 参数为空")
            raise typer.Exit(code=1)

    # 过滤启用的账号
    enabled_accounts = account_manager.get_enabled_accounts()
    if requested_ids is not None:
        enabled_accounts = [acc for acc in enabled_accounts if acc.account_id in requested_ids]
        missing = set(requested_ids) - {acc.account_id for acc in enabled_accounts}
        if missing:
            console.print(f"[yellow]警告:[/yellow] 下列账号未启用或不存在: {', '.join(sorted(missing))}")
    
    if not enabled_accounts:
        console.print("[red]错误:[/red] 没有可用的启用账号")
        raise typer.Exit(code=1)

    console.print("[cyan]多任务监控服务[/cyan]")
    console.print(f"[cyan]配置文件: {config_path}[/cyan]")
    console.print(f"[cyan]数据库: {db_url.split('@')[-1] if '@' in db_url else db_url}[/cyan]")
    console.print(f"[cyan]监控账号: {len(enabled_accounts)}[/cyan]")
    
    # 显示每个账号的监控任务配置
    for acc in enabled_accounts:
        watch_tasks = getattr(acc, 'watch_tasks', None) or {}
        if watch_tasks:
            tasks_str = []
            balance_config = watch_tasks.get('balance', {})
            account_config = watch_tasks.get('account', {})
            positions_config = watch_tasks.get('positions', {})
            orders_config = watch_tasks.get('orders', {})
            if balance_config.get('enabled', True) if isinstance(balance_config, dict) else balance_config:
                tasks_str.append("balance")
            if account_config.get('enabled', True) if isinstance(account_config, dict) else account_config:
                tasks_str.append("account")
            if positions_config.get('enabled', True) if isinstance(positions_config, dict) else positions_config:
                tasks_str.append("positions")
            if orders_config.get('enabled', True) if isinstance(orders_config, dict) else orders_config:
                tasks_str.append("orders")
            console.print(f"  - {acc.account_id}: {acc.name} [{acc.exchange.upper()}] 任务: {', '.join(tasks_str) if tasks_str else '无'}")
        else:
            console.print(f"  - {acc.account_id}: {acc.name} [{acc.exchange.upper()}] 任务: balance, account, positions (默认)")
    
    console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")

    async def run_all_watch_tasks():
        # 在启动所有任务前，统一确保基础数据库表存在
        console.print("[cyan]正在检查/创建基础数据库表（watch-all）...[/cyan]")
        db_manager = DatabaseManager(database_url=db_url)
        try:
            await db_manager.create_tables()
            # 统一表已通过 create_tables() 创建，不再需要按账号分表
            console.print("[green]✅ 基础数据库表已就绪[/green]\n")
        except Exception as init_exc:
            console.print(f"[red]错误:[/red] 基础数据库表初始化失败: {init_exc}")
            if debug:
                import traceback
                console.print_exception()
            logger.error("Failed to create database tables", exc_info=True, extra={"error": str(init_exc)})
            # 不关闭连接，让后续任务有机会重试
        finally:
            await db_manager.close()
        
        all_tasks = []
        
        for acc in enabled_accounts:
            try:
                acc_exchange = ExchangeName(acc.exchange.lower())
            except ValueError:
                console.print(f"[yellow]警告:[/yellow] 账号 {acc.account_id} 使用未支持的交易所 {acc.exchange}，跳过")
                continue

            # 获取账号的 watch_tasks 配置，如果没有则使用默认值
            watch_tasks = getattr(acc, 'watch_tasks', None) or {}
            
            # 默认启用所有任务
            balance_config = watch_tasks.get('balance', {})
            if not balance_config:
                balance_config = {'enabled': True, 'exchange_type': 'perp', 'interval': 5}
            else:
                # 确保有默认值
                balance_config.setdefault('enabled', True)
                balance_config.setdefault('exchange_type', 'perp')
                balance_config.setdefault('interval', 5)
            
            account_config = watch_tasks.get('account', {})
            if not account_config:
                account_config = {'enabled': True, 'interval': 10}
            else:
                account_config.setdefault('enabled', True)
                account_config.setdefault('interval', 10)
            
            positions_config = watch_tasks.get('positions', {})
            if not positions_config:
                positions_config = {'enabled': True, 'interval': 1}
            else:
                positions_config.setdefault('enabled', True)
                positions_config.setdefault('interval', 1)
            
            orders_config = watch_tasks.get('orders', {})
            # 支持两种格式：{"orders": {"enabled": true, "interval": 5}} 或 {"orders": true, "interval": 5}
            if isinstance(orders_config, bool):
                orders_config = {'enabled': orders_config, 'interval': watch_tasks.get('interval', 5)}
            elif not orders_config:
                orders_config = {'enabled': False, 'interval': 5}
            else:
                orders_config.setdefault('enabled', True)
                orders_config.setdefault('interval', 5)
            
            account_label = f"{acc.account_id} ({acc.name})"
            
            # 启动 watch-balance 任务
            if balance_config.get('enabled', True):
                try:
                    exchange_type_str = balance_config.get('exchange_type', 'perp')
                    exchange_type_enum = ExchangeType.PERP if exchange_type_str.lower() == 'perp' else ExchangeType.SPOT
                    interval = balance_config.get('interval', 5)
                    
                    task = asyncio.create_task(
                        _run_watch_balance_async(
                            exchange=acc_exchange.value,
                            interval=interval,
                            api_key=acc.api_key,
                            api_secret=acc.api_secret,
                            exchange_type=exchange_type_enum,
                            output="table",
                            debug=debug,
                            account_id=acc.account_id,
                            account_name=acc.name,
                            database_url=db_url,
                            passphrase=getattr(acc, 'passphrase', None),
                        )
                    )
                    all_tasks.append(task)
                    await asyncio.sleep(0.2)  # 稍微延迟，避免同时连接过多
                except Exception as e:
                    console.print(f"[red]账号 {account_label} watch-balance 启动失败:[/red] {e}")
                    if debug:
                        console.print_exception()
            
            # 启动 watch-account 任务
            if account_config.get('enabled', True):
                try:
                    interval = account_config.get('interval', 10)
                    
                    if acc_exchange == ExchangeName.XT:
                        task = asyncio.create_task(
                            _run_xt_watch_account_async(
                                interval_minutes=interval,
                                api_key=acc.api_key,
                                api_secret=acc.api_secret,
                                debug=debug,
                                account_id=acc.account_id,
                                account_name=acc.name,
                                database_url=db_url,
                                enable_lark=getattr(acc, 'enable_lark', False),
                                lark_webhook=getattr(acc, 'lark_webhook', None),
                                lark_secret=getattr(acc, 'lark_secret', None),
                                metrics_config=None,
                                enable_metrics=True,
                            )
                        )
                    elif acc_exchange == ExchangeName.BINANCE:
                        task = asyncio.create_task(
                            _run_binance_watch_account_async(
                                interval_minutes=interval,
                                api_key=acc.api_key,
                                api_secret=acc.api_secret,
                                debug=debug,
                                account_id=acc.account_id,
                                account_name=acc.name,
                                database_url=db_url,
                                enable_lark=getattr(acc, 'enable_lark', False),
                                lark_webhook=getattr(acc, 'lark_webhook', None),
                                lark_secret=getattr(acc, 'lark_secret', None),
                                metrics_config=None,
                                enable_metrics=True,
                            )
                        )
                    else:
                        console.print(f"[yellow]警告:[/yellow] 账号 {account_label} 的交易所 {acc_exchange.value} 暂不支持 watch-account，跳过")
                        continue
                    
                    all_tasks.append(task)
                    await asyncio.sleep(0.2)
                except Exception as e:
                    console.print(f"[red]账号 {account_label} watch-account 启动失败:[/red] {e}")
                    if debug:
                        console.print_exception()
            
            # 启动 watch-positions 任务
            if positions_config.get('enabled', True):
                try:
                    interval = positions_config.get('interval', 1)
                    symbol = positions_config.get('symbol', None)
                    
                    if acc_exchange == ExchangeName.XT:
                        task = asyncio.create_task(
                            _run_xt_watch_positions_async(
                                interval=interval,
                                api_key=acc.api_key,
                                api_secret=acc.api_secret,
                                symbol=symbol,
                                debug=debug,
                                account_id=acc.account_id,
                                account_name=acc.name,
                                database_url=db_url,
                                lark_webhook=None,
                                lark_secret=None,
                            )
                        )
                    elif acc_exchange == ExchangeName.BINANCE:
                        task = asyncio.create_task(
                            _run_binance_watch_positions_async(
                                interval=interval,
                                api_key=acc.api_key,
                                api_secret=acc.api_secret,
                                symbol=symbol,
                                debug=debug,
                                account_id=acc.account_id,
                                account_name=acc.name,
                                database_url=db_url,
                            )
                        )
                    else:
                        console.print(f"[yellow]警告:[/yellow] 账号 {account_label} 的交易所 {acc_exchange.value} 暂不支持 watch-positions，跳过")
                        continue
                    
                    all_tasks.append(task)
                    await asyncio.sleep(0.2)
                except Exception as e:
                    console.print(f"[red]账号 {account_label} watch-positions 启动失败:[/red] {e}")
                    if debug:
                        console.print_exception()
            
            # 启动 watch-orders 任务
            if orders_config.get('enabled', False):
                try:
                    interval = orders_config.get('interval', 5)
                    symbol = orders_config.get('symbol', None)
                    
                    task = asyncio.create_task(
                        _run_watch_orders_async(
                            exchange=acc_exchange,
                            interval=interval,
                            api_key=acc.api_key,
                            api_secret=acc.api_secret,
                            symbol=symbol,
                            debug=debug,
                            account_id=acc.account_id,
                            account_name=acc.name,
                            passphrase=getattr(acc, 'passphrase', None),
                        )
                    )
                    all_tasks.append(task)
                    await asyncio.sleep(0.2)
                except Exception as e:
                    console.print(f"[red]账号 {account_label} watch-orders 启动失败:[/red] {e}")
                    if debug:
                        console.print_exception()
        
        if not all_tasks:
            console.print("[red]错误:[/red] 没有可启动的监控任务")
            return
        
        console.print(f"[green]已启动 {len(all_tasks)} 个监控任务[/green]\n")
        
        try:
            await asyncio.gather(*all_tasks, return_exceptions=True)
        except KeyboardInterrupt:
            console.print("\n[yellow]监控已停止[/yellow]")
        except Exception as exc:
            console.print(f"[red]监控异常:[/red] {exc}")
            logger.error("watch-all 异常: %s", exc)
            if debug:
                console.print_exception()

    try:
        asyncio.run(run_all_watch_tasks())
    except KeyboardInterrupt:
        console.print("\n[yellow]监控已停止[/yellow]")
    except Exception as exc:
        console.print(f"[red]启动失败:[/red] {exc}")
        if debug:
            console.print_exception()
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
