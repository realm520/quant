"""CSV formatter for CLI output."""

import csv
import io
from typing import Any, List, Dict


def format_csv(data: List[Dict[str, Any]]) -> str:
    """Format data as CSV string.

    Args:
        data: List of dictionaries to format

    Returns:
        CSV formatted string
    """
    if not data:
        return ""

    output = io.StringIO()

    # Get fieldnames from first item
    fieldnames = list(data[0].keys())

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)

    return output.getvalue()


def print_csv(data: List[Dict[str, Any]]) -> None:
    """Print data as formatted CSV.

    Args:
        data: List of dictionaries to print
    """
    print(format_csv(data))
