"""
Arbitrage module exceptions.

Defines exception hierarchy for error handling.
Based on specs/004-xt-get-ticker/contracts/monitor_api.md.
"""


class ArbitrageError(Exception):
    """Base exception for arbitrage module."""
    pass


class ConfigError(ArbitrageError):
    """Configuration validation error (FR-018)."""
    pass


class NetworkError(ArbitrageError):
    """Network request failure (NFR-005)."""
    pass


class InvalidPriceError(ArbitrageError):
    """Invalid price data (FR-002)."""
    pass
