"""Metrics configuration loader for account monitoring."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from tri_arb.config.logging import get_logger

logger = get_logger(__name__)

# Pattern for ${ENV_VAR} or ${ENV_VAR:-default}
ENV_PATTERN = re.compile(r"\$\{([^:}]+)(?::-(.*?))?\}")


@dataclass
class MetricDefinition:
    """Definition of a single monitoring metric."""

    name: str
    type: str
    window_minutes: int
    warning_threshold: float
    critical_threshold: float
    lark_webhook: Optional[str] = None
    lark_secret: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExchangeMetrics:
    """Collection of metrics for a specific exchange."""

    name: str
    metrics: list[MetricDefinition] = field(default_factory=list)


@dataclass
class MetricsConfig:
    """Top-level metrics configuration."""

    exchanges: Dict[str, ExchangeMetrics] = field(default_factory=dict)

    def get_exchange(self, name: str) -> Optional[ExchangeMetrics]:
        return self.exchanges.get(name)


def load_metrics_config(path: Optional[str]) -> MetricsConfig:
    """Load metrics configuration from YAML.

    Args:
        path: Path to YAML configuration. If None, falls back to METRICS_CONFIG_PATH env.

    Returns:
        MetricsConfig: Parsed configuration. Empty if file missing or invalid.
    """

    if not path:
        path = os.getenv("METRICS_CONFIG_PATH")

    if not path:
        logger.info("Metrics configuration path not provided; metrics disabled")
        return MetricsConfig()

    config_path = Path(path).expanduser()
    if not config_path.exists():
        logger.warning(
            "Metrics configuration file not found; metrics disabled",
            extra={"path": str(config_path)},
        )
        return MetricsConfig()

    try:
        raw_data = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_data) or {}
        data = _resolve_env_variables(data)
        return _parse_metrics_config(data)
    except Exception as exc:
        logger.error(
            "Failed to load metrics configuration; metrics disabled",
            extra={"path": str(config_path), "error": str(exc)},
            exc_info=True,
        )
        return MetricsConfig()


def _resolve_env_variables(value: Any) -> Any:
    """Recursively resolve ${VAR} style placeholders in configuration."""

    if isinstance(value, dict):
        return {k: _resolve_env_variables(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_variables(item) for item in value]
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_value = os.getenv(var_name)
            if env_value is None:
                env_value = default if default is not None else ""
            return env_value

        return ENV_PATTERN.sub(replace, value)

    return value


def _parse_metrics_config(data: Dict[str, Any]) -> MetricsConfig:
    """Parse raw dictionary into MetricsConfig dataclasses."""

    exchanges_data = data.get("exchanges", {})
    exchanges: Dict[str, ExchangeMetrics] = {}

    for exchange_name, exchange_cfg in exchanges_data.items():
        metrics_cfg = exchange_cfg.get("metrics", {})
        metric_definitions: list[MetricDefinition] = []

        for metric_name, metric_cfg in metrics_cfg.items():
            metric_type = metric_cfg.get("type")
            if not metric_type:
                logger.warning(
                    "Metric definition missing 'type'; skipping",
                    extra={"exchange": exchange_name, "metric": metric_name},
                )
                continue

            try:
                window = int(metric_cfg.get("window_minutes", 0))
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid window_minutes for metric; skipping",
                    extra={"exchange": exchange_name, "metric": metric_name},
                )
                continue

            try:
                warning_threshold = float(metric_cfg.get("warning_threshold", 0))
                critical_threshold = float(metric_cfg.get("critical_threshold", 0))
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid threshold for metric; skipping",
                    extra={"exchange": exchange_name, "metric": metric_name},
                )
                continue

            lark_webhook = metric_cfg.get("lark_webhook")
            lark_secret = metric_cfg.get("lark_secret")

            extra_params = {
                k: v
                for k, v in metric_cfg.items()
                if k
                not in {
                    "type",
                    "window_minutes",
                    "warning_threshold",
                    "critical_threshold",
                    "lark_webhook",
                    "lark_secret",
                }
            }

            metric_definitions.append(
                MetricDefinition(
                    name=metric_name,
                    type=metric_type,
                    window_minutes=window,
                    warning_threshold=warning_threshold,
                    critical_threshold=critical_threshold,
                    lark_webhook=lark_webhook,
                    lark_secret=lark_secret,
                    parameters=extra_params,
                )
            )

        exchanges[exchange_name] = ExchangeMetrics(
            name=exchange_name,
            metrics=metric_definitions,
        )

    return MetricsConfig(exchanges=exchanges)

