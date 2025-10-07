"""
Triangular arbitrage monitoring module.

This module provides functionality for detecting and analyzing triangular
arbitrage opportunities across cryptocurrency trading pairs.
"""

from tri_arb.arbitrage.calculator import calculate_profit_rate
from tri_arb.arbitrage.config import MonitorConfig
from tri_arb.arbitrage.exceptions import (
    ArbitrageError,
    ConfigError,
    InvalidPriceError,
    NetworkError,
)
from tri_arb.arbitrage.monitor import ArbitrageMonitor
from tri_arb.arbitrage.path_finder import find_arbitrage_paths


__all__ = [
    "ArbitrageMonitor",
    "MonitorConfig",
    "find_arbitrage_paths",
    "calculate_profit_rate",
    "ArbitrageError",
    "ConfigError",
    "NetworkError",
    "InvalidPriceError",
]
