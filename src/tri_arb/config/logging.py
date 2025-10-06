"""Logging configuration with structlog."""
import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from tri_arb.config.settings import settings


def add_correlation_id(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add correlation ID to log events if available in context."""
    # Placeholder for correlation ID - would be set from async context in real implementation
    event_dict["correlation_id"] = event_dict.get("correlation_id", "none")
    return event_dict


def configure_logging() -> None:
    """Configure structured logging with structlog."""
    # Determine if we're in production
    is_production = settings.environment == "production"

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level),
    )

    # Shared processors for all environments
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        add_correlation_id,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if is_production:
        # Production: JSON output for log aggregation
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: Human-readable console output
        processors = shared_processors + [
            structlog.processors.ExceptionPrettyPrinter(),
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,  # type: ignore[arg-type]
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)
