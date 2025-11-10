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
from sqlalchemy import select, func

from tri_arb.storage.xt_rest_models import XTPerpBalance, XTPerpPosition
from tri_arb.config.metrics_loader import (
    MetricsConfig,
    MetricDefinition,
    load_metrics_config,
)


def _run_xt_watch_positions(
    interval: int,
    api_key: str,
    api_secret: str,
    symbol: Optional[str],
    debug: bool,
    lark_webhook: Optional[str] = None,
    lark_secret: Optional[str] = None,
) -> None:
    """运行XT永续仓位定时监控并写入数据库."""
    from rich.table import Table
    from tri_arb.exchanges.xt_perp import XTPerpExchange
    from tri_arb.services.xt_rest_data_service import XTRestDataService

    console.print("[cyan]启动XT仓位定时监控服务[/cyan]")
    console.print(f"[cyan]查询间隔: {interval} 分钟[/cyan]")
    if symbol:
        console.print(f"[cyan]仅监控交易对: {symbol}[/cyan]")
    console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")

    db_manager = DatabaseManager()
    perp_exchange = XTPerpExchange(api_key=api_key, api_secret=api_secret)
    xt_rest_service = XTRestDataService(db_manager)

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
            logger.error("watch-positions fetch error", error=str(exc))
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
        console.print("[green]✓[/green] 仓位数据已保存到数据库\n")

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
        from tri_arb.storage.xt_rest_models import Base as XTRestBase

        async with db_manager.async_engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: XTRestBase.metadata.create_all(sync_conn, checkfirst=True)
            )

    async def run_scheduler():
        iteration = 0
        try:
            await _ensure_xt_rest_tables()
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
                "指标评估完成",
                extra={
                    "metric": metric.name,
                    "type": metric.type,
                    "severity": severity,
                    "volatility": str(volatility),
                    "samples": sample_count,
                    "window_minutes": window_minutes,
                },
            )

            if severity == "NORMAL":
                continue

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
            maintenance_total = result["maintenance_total"]
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
                    "maintenance_total": str(maintenance_total),
                    "floating_loss": str(floating_loss),
                    "positions": position_count,
                },
            )

            if severity == "NORMAL":
                continue

            message_lines = [
                "[XT 指标监控]",
                f"指标: {metric.name}",
                f"类型: 仓位风险率",
                f"最新仓位数: {position_count}",
                f"可用保证金: {available_margin:.4f}",
                f"维持保证金合计: {maintenance_total:.4f}",
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
                        success_message="[green]✓[/green] Lark 风险率告警已发送\n",
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
                    "风险率达到阈值但 Lark 告警未启用",
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
            select(XTPerpBalance.free, XTPerpBalance.query_time)
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
                XTPerpPosition.maintenance_margin,
                XTPerpPosition.unrealized_pnl,
                XTPerpPosition.raw_data,
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

    maintenance_total = Decimal("0")
    floating_loss = Decimal("0")
    position_count = 0

    for maint_val, unrealized_val, raw_data in position_rows:
        maintenance_margin = Decimal(str(maint_val)) if maint_val is not None else None
        unrealized = Decimal(str(unrealized_val)) if unrealized_val is not None else None

        if maintenance_margin is None or unrealized is None:
            maint_fallback = None
            unrealized_fallback = None
            if raw_data:
                try:
                    raw = json.loads(raw_data)
                    maint_fallback = (
                        raw.get("maintMargin")
                        or raw.get("maintenanceMargin")
                        or raw.get("maintMarginAmount")
                    )
                    unrealized_fallback = (
                        raw.get("floatingPL")
                        or raw.get("unRealizedProfit")
                        or raw.get("unrealizedPnl")
                    )
                except json.JSONDecodeError:
                    logger.debug(
                        "解析仓位 raw_data 失败",
                        extra={"metric": metric.name},
                    )

            if maintenance_margin is None and maint_fallback is not None:
                maintenance_margin = Decimal(str(maint_fallback))
            if unrealized is None and unrealized_fallback is not None:
                unrealized = Decimal(str(unrealized_fallback))

        if maintenance_margin is None:
            maintenance_margin = Decimal("0")
        if unrealized is None:
            unrealized = Decimal("0")

        maintenance_total += maintenance_margin
        floating_loss += max(Decimal("0"), -unrealized)
        position_count += 1

    numerator = maintenance_total + floating_loss
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
        "maintenance_total": maintenance_total,
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
        
        # 预初始化数据库（创建一次表结构）
        db_manager = DatabaseManager()

        # 定时查询函数
        async def watch_loop():
            iteration = 0
            try:
                await exchange_instance.connect()
                # 确保所需表存在（只执行一次）
                try:
                    await db_manager.create_tables()
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
                                        elif exchange == ExchangeName.XT:
                                            # 复用 XT WebSocket 的账户更新表，记录 REST 快照
                                            record = XTAccountUpdate(
                                                update_time=now,
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
):
    """定时获取账户数据（现货余额、合约余额、合约仓位）.
    
    每个周期自动获取一次交易所的：
    - 现货账户余额
    - 合约账户余额  
    - 合约账户仓位
    
    数据自动保存到PostgreSQL数据库。
    按 Ctrl+C 停止监控。
    
    示例:
        # 使用环境变量中的API密钥（XT交易所）
        cextools account watch-account -x xt
        
        # 通过命令行参数提供API密钥
        cextools account watch-account -x xt --api-key YOUR_KEY --api-secret YOUR_SECRET
        
        # 启用调试模式
        cextools account watch-account -x xt --debug
    """
    try:
        # 检查交易所支持情况
        if exchange != ExchangeName.XT:
            console.print(f"[red]错误:[/red] 交易所 '{exchange.value}' 暂时不支持 watch-account 功能")
            console.print("\n目前仅支持以下交易所:")
            console.print("  • xt (XT交易所)")
            console.print("\n请使用: [cyan]cextools account watch-account -x xt[/cyan]")
            raise typer.Exit(code=1)
        
        # 获取API密钥（优先使用命令行参数，否则使用环境变量）
        final_api_key = api_key or os.getenv("XT_API_KEY", "")
        final_api_secret = api_secret or os.getenv("XT_API_SECRET", "")
        
        if not final_api_key or not final_api_secret:
            console.print("[red]错误:[/red] 缺少XT API密钥配置")
            console.print("\n请设置环境变量或使用命令行参数:")
            console.print("  环境变量: export XT_API_KEY=your_key && export XT_API_SECRET=your_secret")
            console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
            console.print("\n注意: XT交易所的现货和合约使用同一套API密钥")
            raise typer.Exit(code=1)
        
        webhook_url: Optional[str] = None
        webhook_secret: Optional[str] = None
        if enable_lark:
            webhook_url = lark_webhook or os.getenv("LARK_WEBHOOK_URL")
            if lark_secret is not None:
                webhook_secret = lark_secret or None
            else:
                webhook_secret = os.getenv("LARK_WEBHOOK_SECRET")

            if not webhook_url:
                console.print("[yellow]未提供 Lark Webhook，禁用告警推送[/yellow]")
                enable_lark = False

        metrics_definition: Optional[MetricsConfig] = None
        if enable_metrics:
            metrics_path = metrics_config or os.getenv("METRICS_CONFIG_PATH")
            metrics_definition = load_metrics_config(metrics_path)
            if not metrics_definition.exchanges:
                logger.info("指标配置为空，跳过指标评估")
                metrics_definition = None

        if interval_minutes <= 0:
            console.print("[red]错误:[/red] 查询间隔必须大于 0 分钟")
            raise typer.Exit(code=1)

        console.print("[cyan]启动XT账户定时任务服务[/cyan]")
        console.print(f"[cyan]查询间隔: {interval_minutes} 分钟[/cyan]")
        console.print("[cyan]监控内容:[/cyan]")
        console.print("  • 现货账户余额")
        console.print("  • 合约账户余额")
        console.print("  • 合约账户仓位")
        console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")
        
        # 初始化数据库管理器
        db_manager = DatabaseManager()
        
        # 创建交易所实例
        from tri_arb.exchanges.xt_spot import XTSpotExchange
        from tri_arb.exchanges.xt_perp import XTPerpExchange
        from tri_arb.services.xt_rest_data_service import XTRestDataService
        
        spot_exchange = XTSpotExchange(
            name="xt",
            api_key=final_api_key,
            api_secret=final_api_secret,
        )
        perp_exchange = XTPerpExchange(
            api_key=final_api_key,
            api_secret=final_api_secret,
        )
        xt_rest_service = XTRestDataService(db_manager)
        
        # 异步运行定时任务
        async def run_scheduler():
            iteration = 0
            try:
                # 创建数据库表（如果不存在）
                await db_manager.create_tables()
                console.print("[green]✓[/green] 数据库表已就绪\n")
                
                # 连接交易所
                await spot_exchange.connect()
                await perp_exchange.connect()
                console.print("[green]✓[/green] 交易所连接成功\n")
                
                # 立即执行一次查询并显示
                iteration = 1
                await fetch_and_display(iteration)
                
                # 定时查询循环
                try:
                    while True:
                        await asyncio.sleep(interval_minutes * 60)
                        iteration += 1
                        await fetch_and_display(iteration)
                except KeyboardInterrupt:
                    console.print("\n[yellow]收到停止信号，正在关闭...[/yellow]")
                finally:
                    await spot_exchange.disconnect()
                    await perp_exchange.disconnect()
                    await db_manager.close()
                    console.print("[green]✓[/green] 服务已停止")
                    
            except Exception as e:
                console.print(f"[red]错误:[/red] {e}")
                if debug:
                    console.print_exception()
                raise typer.Exit(code=1)
        
        async def fetch_and_display(iteration_num: int):
            """获取数据并显示表格."""
            from rich.table import Table
            
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            console.print(f"\n{'='*60}")
            console.print(f"[bold]第 {iteration_num} 次查询 - {current_time}[/bold]")
            console.print(f"{'='*60}\n")
            
            try:
                # 1. 获取并显示现货账户余额
                try:
                    spot_balances = await spot_exchange.get_balance()
                    if spot_balances:
                        # 创建现货余额表格
                        spot_table = Table(
                            title="XT 现货账户余额",
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
                        console.print(f"[dim]数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                        
                        # 保存到数据库（XT专用表）
                        await xt_rest_service.save_spot_balance(
                            balances_data=spot_balances,
                            query_type="scheduled",
                        )
                    else:
                        console.print("[yellow]XT 现货账户余额为空[/yellow]\n")
                except Exception as e:
                    console.print(f"[red]获取现货余额失败:[/red] {e}\n")
                    if debug:
                        console.print_exception()
                
                # 2. 获取并显示合约账户余额
                try:
                    perp_balances = await perp_exchange.get_balance()
                    if perp_balances:
                        # 转换为标准格式（包含所有字段）
                        balances_data: dict[str, dict[str, Any]] = {}
                        for currency, balance_info in perp_balances.items():
                            balances_data[currency] = {
                                "available": balance_info.get("available", Decimal("0")),
                                "frozen": balance_info.get("frozen", Decimal("0")),
                                "total": balance_info.get("total", Decimal("0")),
                                "unrealized_pnl": balance_info.get("unrealized_pnl", Decimal("0")),
                                "realized_pnl": balance_info.get("realized_pnl", Decimal("0")),
                                "equity": balance_info.get("equity", balance_info.get("total", Decimal("0")) + balance_info.get("unrealized_pnl", Decimal("0"))),
                                "margin": balance_info.get("margin", Decimal("0")),
                                "margin_ratio": balance_info.get("margin_ratio", Decimal("0")),
                            }
                        
                        # 创建合约余额表格
                        perp_balance_table = Table(
                            title="XT 合约账户余额",
                            show_header=True,
                            header_style="bold magenta"
                        )
                        perp_balance_table.add_column("Currency", style="cyan", width=12)
                        perp_balance_table.add_column("Available", justify="right", style="green")
                        perp_balance_table.add_column("Frozen", justify="right", style="yellow")
                        perp_balance_table.add_column("Total", justify="right", style="white")
                        perp_balance_table.add_column("Unrealized PnL", justify="right", style="white")
                        perp_balance_table.add_column("Realized PnL", justify="right", style="white")
                        perp_balance_table.add_column("Equity", justify="right", style="cyan")
                        perp_balance_table.add_column("Margin", justify="right", style="yellow")
                        
                        for currency, data in balances_data.items():
                            available = data.get("available", Decimal("0"))
                            frozen = data.get("frozen", Decimal("0"))
                            total = data.get("total", Decimal("0"))
                            unrealized_pnl = data.get("unrealized_pnl", Decimal("0"))
                            realized_pnl = data.get("realized_pnl", Decimal("0"))
                            equity = data.get("equity", total + unrealized_pnl)
                            margin = data.get("margin", Decimal("0"))
                            
                            # 格式化PnL颜色
                            unrealized_pnl_style = "green" if unrealized_pnl >= 0 else "red"
                            realized_pnl_style = "green" if realized_pnl >= 0 else "red"
                            unrealized_pnl_text = f"[{unrealized_pnl_style}]{unrealized_pnl:.8f}[/{unrealized_pnl_style}]"
                            realized_pnl_text = f"[{realized_pnl_style}]{realized_pnl:.8f}[/{realized_pnl_style}]"
                            
                            perp_balance_table.add_row(
                                currency,
                                f"{available:.8f}",
                                f"{frozen:.8f}",
                                f"{total:.8f}",
                                unrealized_pnl_text,
                                realized_pnl_text,
                                f"{equity:.8f}",
                                f"{margin:.8f}",
                            )
                        
                        console.print(perp_balance_table)
                        console.print(f"[dim]数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                        
                        # 保存到数据库（XT专用表）
                        await xt_rest_service.save_perp_balance(
                            balances_data=balances_data,
                            query_type="scheduled",
                        )
                    else:
                        console.print("[yellow]XT 合约账户余额为空[/yellow]\n")
                except Exception as e:
                    console.print(f"[red]获取合约余额失败:[/red] {e}\n")
                    if debug:
                        console.print_exception()
                
                # 3. 获取并显示合约账户仓位
                try:
                    positions = await perp_exchange.get_positions(symbol=None)
                    if positions:
                        # 创建仓位表格
                        position_table = Table(
                            title="XT 合约账户仓位",
                            show_header=True,
                            header_style="bold magenta"
                        )
                        position_table.add_column("Symbol", style="cyan")
                        position_table.add_column("Side", style="white")
                        position_table.add_column("Quantity", justify="right")
                        position_table.add_column("Entry Price", justify="right")
                        position_table.add_column("Current Price", justify="right")
                        position_table.add_column("Liquidation Price", justify="right")
                        position_table.add_column("Unrealized PnL", justify="right")
                        position_table.add_column("Realized PnL", justify="right")
                        position_table.add_column("ROE", justify="right")
                        position_table.add_column("Leverage", justify="right")
                        
                        # 转换为字典格式保存
                        positions_data: list[dict[str, Any]] = []
                        
                        for pos in positions:
                            if hasattr(pos, 'symbol'):
                                # Position对象 (XT格式)
                                symbol = pos.symbol
                                side = pos.side
                                quantity = pos.quantity
                                entry_price = pos.entry_price
                                mark_price = pos.mark_price
                                unrealized_pnl = pos.unrealized_pnl
                                realized_pnl = getattr(pos, 'realized_pnl', Decimal('0'))
                                leverage = f"{pos.leverage}"
                                roe = (pos.unrealized_pnl / pos.margin * 100) if hasattr(pos, 'margin') and pos.margin > 0 else Decimal('0')
                                liquidation_price = pos.liquidation_price if hasattr(pos, 'liquidation_price') else Decimal('0')
                                
                                # 格式化未实现PnL
                                unrealized_pnl_style = "green" if unrealized_pnl >= 0 else "red"
                                unrealized_pnl_text = f"[{unrealized_pnl_style}]{unrealized_pnl:.8f}[/{unrealized_pnl_style}]"
                                
                                # 格式化已实现PnL
                                realized_pnl_style = "green" if realized_pnl >= 0 else "red"
                                realized_pnl_text = f"[{realized_pnl_style}]{realized_pnl:.8f}[/{realized_pnl_style}]"
                                
                                # 格式化ROE
                                roe_style = "green" if roe >= 0 else "red"
                                roe_text = f"[{roe_style}]{roe:.2f}%[/{roe_style}]"
                                
                                position_table.add_row(
                                    symbol,
                                    side,
                                    f"{quantity:.8f}",
                                    f"{entry_price:.8f}",
                                    f"{mark_price:.8f}",
                                    f"{liquidation_price:.8f}",
                                    unrealized_pnl_text,
                                    realized_pnl_text,
                                    roe_text,
                                    f"{leverage}x",
                                )
                                
                                # 保存数据（使用XT API字段名）
                                pos_dict = {
                                    "symbol": symbol,
                                    "positionSide": side,
                                    "positionSize": str(quantity),  # XT API uses positionSize
                                    "entryPrice": str(entry_price),
                                    "calMarkPrice": str(mark_price),  # XT API uses calMarkPrice
                                    "floatingPL": str(unrealized_pnl),  # XT API uses floatingPL
                                    "realizedProfit": str(realized_pnl),  # XT API uses realizedProfit
                                    "leverage": leverage,
                                    "isolatedMargin": str(pos.margin) if hasattr(pos, 'margin') else "0",  # XT API uses isolatedMargin
                                    "roe": str(roe),
                                    "breakPrice": str(liquidation_price),  # XT API uses breakPrice
                                    "maintMargin": str(getattr(pos, "maintenance_margin", Decimal("0"))),
                                    # 保留兼容字段名
                                    "positionAmt": str(quantity),
                                    "markPrice": str(mark_price),
                                    "unRealizedProfit": str(unrealized_pnl),
                                    "liquidationPrice": str(liquidation_price),
                                    "margin": str(pos.margin) if hasattr(pos, 'margin') else "0",
                                }
                                positions_data.append(pos_dict)
                            else:
                                # 字典格式
                                positions_data.append(pos)
                        
                        if positions_data:
                            console.print(position_table)
                            console.print(f"[dim]数据获取时间: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]\n")
                            
                            # 保存到数据库（XT专用表）
                            await xt_rest_service.save_perp_positions(
                                positions_data=positions_data,
                                query_type="scheduled",
                            )
                        else:
                            console.print("[yellow]XT 当前无持仓[/yellow]\n")
                    else:
                        console.print("[yellow]XT 当前无持仓[/yellow]\n")
                except Exception as e:
                    console.print(f"[red]获取仓位失败:[/red] {e}\n")
                    if debug:
                        console.print_exception()
                
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
                console.print(f"\n[dim]下次查询: {next_query_time.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
                console.print(f"[dim]等待 {interval_minutes} 分钟...[/dim]\n")
                
            except Exception as e:
                console.print(f"[red]查询过程出错:[/red] {e}")
                if debug:
                    console.print_exception()
        
        # 运行定时任务
        asyncio.run(run_scheduler())
        
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
            final_api_key = api_key or os.getenv("XT_API_KEY", "")
            final_api_secret = api_secret or os.getenv("XT_API_SECRET", "")

            if not final_api_key or not final_api_secret:
                console.print("[red]错误:[/red] 缺少XT API密钥配置")
                console.print("\n请设置环境变量或使用命令行参数:")
                console.print("  环境变量: export XT_API_KEY=your_key && export XT_API_SECRET=your_secret")
                console.print("  命令行:   --api-key YOUR_KEY --api-secret YOUR_SECRET")
                raise typer.Exit(code=1)

            _run_xt_watch_positions(
                interval=interval,
                api_key=final_api_key,
                api_secret=final_api_secret,
                symbol=symbol,
                debug=debug,
                lark_webhook=webhook_url if enable_lark else None,
                lark_secret=webhook_secret if enable_lark else None,
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
