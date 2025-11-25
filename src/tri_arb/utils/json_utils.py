"""JSON utilities for handling special types like Decimal."""

import json
from decimal import Decimal
from typing import Any


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal objects by converting them to strings.

    This prevents 'Object of type Decimal is not JSON serializable' errors
    when serializing data containing Decimal values.
    """

    def default(self, obj: Any) -> Any:
        """Convert Decimal to string, otherwise use default encoding."""
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def dumps_with_decimal(obj: Any, **kwargs) -> str:
    """Serialize obj to JSON string, handling Decimal objects.

    Args:
        obj: Object to serialize
        **kwargs: Additional arguments to pass to json.dumps

    Returns:
        JSON string representation

    Example:
        >>> from decimal import Decimal
        >>> data = {'price': Decimal('123.45'), 'quantity': Decimal('10')}
        >>> dumps_with_decimal(data)
        '{"price": "123.45", "quantity": "10"}'
    """
    return json.dumps(obj, cls=DecimalEncoder, **kwargs)
