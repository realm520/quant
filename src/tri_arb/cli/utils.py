"""CLI utilities for formatting, validation, and helpers.

Provides common utilities used across CLI commands including
formatters, validators, and helper functions.
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

import typer

from tri_arb.config.logging import get_logger

logger = get_logger(__name__)


# Formatters


def format_price(price: Decimal, precision: int = 2) -> str:
    """Format price value for display.

    Args:
        price: Price value
        precision: Number of decimal places

    Returns:
        Formatted price string
    """
    return f"${price:,.{precision}f}"


def format_quantity(quantity: Decimal, precision: int = 8) -> str:
    """Format quantity value for display.

    Args:
        quantity: Quantity value
        precision: Number of decimal places

    Returns:
        Formatted quantity string
    """
    return f"{quantity:.{precision}f}".rstrip("0").rstrip(".")


def format_percentage(value: float, precision: int = 2) -> str:
    """Format percentage value for display.

    Args:
        value: Percentage value (0-1 or 0-100)
        precision: Number of decimal places

    Returns:
        Formatted percentage string
    """
    # Auto-detect if value is already in percentage format
    if value > 1.0:
        return f"{value:.{precision}f}%"
    return f"{value * 100:.{precision}f}%"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string (e.g., "1h 23m 45s")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.0f}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def format_table(
    headers: List[str],
    rows: List[List[str]],
    max_width: int = 120,
) -> str:
    """Format data as ASCII table.

    Args:
        headers: Column headers
        rows: Data rows
        max_width: Maximum table width

    Returns:
        Formatted table string
    """
    if not rows:
        return "No data"

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Create separator
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    # Format header
    header = "|" + "|".join(f" {h:<{w}} " for h, w in zip(headers, col_widths)) + "|"

    # Format rows
    formatted_rows = []
    for row in rows:
        formatted_row = (
            "|" + "|".join(f" {str(c):<{w}} " for c, w in zip(row, col_widths)) + "|"
        )
        formatted_rows.append(formatted_row)

    # Combine all parts
    table = [separator, header, separator, *formatted_rows, separator]
    return "\n".join(table)


# Validators


def validate_trading_pair(pair: str) -> bool:
    """Validate trading pair format.

    Args:
        pair: Trading pair string (e.g., "BTC/USDT")

    Returns:
        True if valid, False otherwise
    """
    if "/" not in pair:
        return False

    parts = pair.split("/")
    if len(parts) != 2:
        return False

    base, quote = parts
    if not (2 <= len(base) <= 10 and 2 <= len(quote) <= 10):
        return False

    return True


def validate_decimal(value: str) -> Optional[Decimal]:
    """Validate and convert string to Decimal.

    Args:
        value: String value to validate

    Returns:
        Decimal value if valid, None otherwise
    """
    try:
        return Decimal(value)
    except Exception:
        return None


def validate_positive_decimal(value: str) -> Optional[Decimal]:
    """Validate string is positive Decimal.

    Args:
        value: String value to validate

    Returns:
        Decimal value if valid and positive, None otherwise
    """
    decimal_value = validate_decimal(value)
    if decimal_value is not None and decimal_value > 0:
        return decimal_value
    return None


# Helpers


def confirm_action(message: str, default: bool = False) -> bool:
    """Prompt user for confirmation.

    Args:
        message: Confirmation message
        default: Default value if user just presses Enter

    Returns:
        True if confirmed, False otherwise
    """
    return typer.confirm(message, default=default)


def prompt_choice(
    message: str,
    choices: List[str],
    default: Optional[str] = None,
) -> str:
    """Prompt user to select from choices.

    Args:
        message: Prompt message
        choices: List of valid choices
        default: Default choice if user just presses Enter

    Returns:
        Selected choice
    """
    choices_str = "/".join(choices)
    if default:
        prompt = f"{message} [{choices_str}] (default: {default}): "
    else:
        prompt = f"{message} [{choices_str}]: "

    while True:
        choice = typer.prompt(prompt, default=default or "")
        if choice in choices:
            return choice
        typer.echo(f"Invalid choice. Please select from: {choices_str}", err=True)


def print_success(message: str) -> None:
    """Print success message.

    Args:
        message: Success message
    """
    typer.secho(f"✓ {message}", fg=typer.colors.GREEN)


def print_error(message: str) -> None:
    """Print error message.

    Args:
        message: Error message
    """
    typer.secho(f"✗ {message}", fg=typer.colors.RED, err=True)


def print_warning(message: str) -> None:
    """Print warning message.

    Args:
        message: Warning message
    """
    typer.secho(f"⚠ {message}", fg=typer.colors.YELLOW)


def print_info(message: str) -> None:
    """Print info message.

    Args:
        message: Info message
    """
    typer.secho(f"ℹ {message}", fg=typer.colors.BLUE)


def print_json(data: Dict[str, Any], indent: int = 2) -> None:
    """Print data as formatted JSON.

    Args:
        data: Data dictionary
        indent: JSON indentation level
    """
    import json

    typer.echo(json.dumps(data, indent=indent, default=str))


# Error handling


class CLIError(Exception):
    """Base exception for CLI errors."""

    pass


class ValidationError(CLIError):
    """Raised when input validation fails."""

    pass


class ConfigurationError(CLIError):
    """Raised when configuration is invalid."""

    pass
