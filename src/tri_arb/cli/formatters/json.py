"""JSON formatter for CLI output."""

import json
from decimal import Decimal
from datetime import datetime
from typing import Any


def decimal_default(obj: Any) -> str:
    """JSON serializer for Decimal and datetime objects."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def format_json(data: Any) -> str:
    """Format data as JSON string.

    Args:
        data: Data to format (list, dict, or object)

    Returns:
        JSON formatted string
    """
    # Convert objects to dicts if needed
    if hasattr(data, "__dict__"):
        data = data.__dict__
    elif isinstance(data, list) and data and hasattr(data[0], "__dict__"):
        data = [item.__dict__ for item in data]

    return json.dumps(data, indent=2, default=decimal_default, ensure_ascii=False)


def print_json(data: Any) -> None:
    """Print data as formatted JSON.

    Args:
        data: Data to print
    """
    print(format_json(data))
