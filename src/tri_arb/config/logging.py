"""Logging configuration with structlog."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
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


def setup_file_handlers() -> None:
    """Setup rotating file handlers for persistent logging.

    Creates two log files in the logs/ directory:
    - tri-arb.log: All logs (INFO and above)
    - tri-arb-errors.log: Error logs only (ERROR and above)

    Both files use JSON format and rotate at 10MB with 5 backups.
    """
    # Get project root directory (3 levels up from this file)
    project_root = Path(__file__).parent.parent.parent.parent
    logs_dir = project_root / "logs"

    # Ensure logs directory exists
    logs_dir.mkdir(exist_ok=True)

    # Get root logger for stdlib logging
    root_logger = logging.getLogger()

    # Create JSON formatter for file logs
    json_formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

    # Setup main log file (INFO and above)
    main_log_file = logs_dir / "tri-arb.log"
    main_handler = RotatingFileHandler(
        main_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    main_handler.setLevel(logging.INFO)
    main_handler.setFormatter(json_formatter)
    root_logger.addHandler(main_handler)

    # Setup error log file (ERROR and above)
    error_log_file = logs_dir / "tri-arb-errors.log"
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(json_formatter)
    root_logger.addHandler(error_handler)


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

    # Setup file handlers for persistent logging
    setup_file_handlers()

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
