"""Exchange integration layer.

Provides abstract interfaces and concrete implementations for cryptocurrency
exchange connectivity and trading operations.
"""

from tri_arb.exchanges.base import BaseExchange
from tri_arb.exchanges.xt import XTExchange


__all__ = ["BaseExchange", "XTExchange"]
