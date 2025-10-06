"""Custom exception hierarchy for tri-arb application.

This module defines all custom exceptions used throughout the application,
organized in a hierarchy for specific error handling.
"""


class TriArbException(Exception):
    """Base exception for all tri-arb errors.

    All custom exceptions in the application should inherit from this base class.
    """

    pass


class InvalidTradingPairError(TriArbException):
    """Raised when trading pair configuration is invalid.

    Examples:
    - Invalid currency symbols
    - Invalid exchange identifier
    - Invalid order size constraints
    """

    pass


class StalePriceError(TriArbException):
    """Raised when price data is too old to be reliable.

    This typically indicates that the price data is older than the
    configured freshness threshold (default: 5 minutes).
    """

    pass


class InsufficientLiquidityError(TriArbException):
    """Raised when order book depth is insufficient.

    This occurs when there isn't enough volume at the desired price levels
    to execute the required trade size.
    """

    pass


class ExchangeConnectionError(TriArbException):
    """Raised when exchange connection or communication fails.

    Examples:
    - Network connectivity issues
    - Exchange API errors
    - Authentication failures
    - Rate limiting
    """

    pass


class OrderExecutionError(TriArbException):
    """Raised when order execution fails.

    Examples:
    - Order rejection by exchange
    - Insufficient balance
    - Invalid order parameters
    - Post-only order would take liquidity
    """

    pass
