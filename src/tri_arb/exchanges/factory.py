"""Exchange factory for dynamic exchange adapter creation.

Provides factory pattern implementation for creating exchange instances
with a registration system for extensibility.
"""


from tri_arb.config.logging import get_logger
from tri_arb.core.exceptions import ExchangeConnectionError
from tri_arb.exchanges.base import BaseExchange


logger = get_logger(__name__)


class ExchangeFactory:
    """Factory for creating exchange adapter instances.

    Implements the factory pattern with a registration system that allows
    dynamic registration of exchange implementations at runtime.

    Attributes:
        _registry: Dictionary mapping exchange names to their classes
    """

    def __init__(self) -> None:
        """Initialize exchange factory with empty registry."""
        self._registry: dict[str, type[BaseExchange]] = {}
        logger.info("ExchangeFactory initialized")

    def register(self, name: str, exchange_class: type[BaseExchange]) -> None:
        """Register an exchange implementation.

        Args:
            name: Exchange name identifier (e.g., 'binance', 'okx')
            exchange_class: Exchange class that inherits from BaseExchange

        Raises:
            ValueError: If exchange name is already registered

        Example:
            factory.register('binance', BinanceExchange)
        """
        if name in self._registry:
            raise ValueError(f"Exchange '{name}' is already registered")

        if not issubclass(exchange_class, BaseExchange):
            raise ValueError(
                f"Exchange class must inherit from BaseExchange, got {exchange_class}"
            )

        self._registry[name] = exchange_class
        logger.info("Exchange registered", name=name, class_name=exchange_class.__name__)

    def unregister(self, name: str) -> None:
        """Unregister an exchange implementation.

        Args:
            name: Exchange name identifier to remove

        Raises:
            KeyError: If exchange name is not registered
        """
        if name not in self._registry:
            raise KeyError(f"Exchange '{name}' is not registered")

        del self._registry[name]
        logger.info("Exchange unregistered", name=name)

    def create(self, name: str, **kwargs) -> BaseExchange:
        """Create an exchange adapter instance.

        Args:
            name: Exchange name identifier
            **kwargs: Additional arguments to pass to exchange constructor

        Returns:
            Exchange adapter instance

        Raises:
            ExchangeConnectionError: If exchange is not registered

        Example:
            binance = factory.create('binance', api_key='...', api_secret='...')
        """
        if name not in self._registry:
            available = ", ".join(self._registry.keys())
            raise ExchangeConnectionError(
                f"Exchange '{name}' is not registered. "
                f"Available exchanges: {available or 'none'}"
            )

        exchange_class = self._registry[name]
        logger.info(
            "Creating exchange instance",
            name=name,
            class_name=exchange_class.__name__,
        )

        try:
            instance = exchange_class(name=name, **kwargs)
            logger.debug("Exchange instance created", name=name)
            return instance
        except Exception as e:
            logger.error(
                "Failed to create exchange instance",
                name=name,
                error=str(e),
            )
            raise ExchangeConnectionError(
                f"Failed to create exchange '{name}': {str(e)}"
            ) from e

    def list_registered(self) -> list[str]:
        """Get list of registered exchange names.

        Returns:
            List of registered exchange identifiers
        """
        return list(self._registry.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an exchange is registered.

        Args:
            name: Exchange name identifier

        Returns:
            True if exchange is registered, False otherwise
        """
        return name in self._registry


# Global exchange factory instance
exchange_factory = ExchangeFactory()


def register_exchange(name: str, exchange_class: type[BaseExchange]) -> None:
    """Convenience function to register exchange with global factory.

    Args:
        name: Exchange name identifier
        exchange_class: Exchange class that inherits from BaseExchange
    """
    exchange_factory.register(name, exchange_class)


def create_exchange(name: str, **kwargs) -> BaseExchange:
    """Convenience function to create exchange from global factory.

    Args:
        name: Exchange name identifier
        **kwargs: Additional arguments to pass to exchange constructor

    Returns:
        Exchange adapter instance
    """
    return exchange_factory.create(name, **kwargs)


def get_available_exchanges() -> list[str]:
    """Get list of available exchanges from global factory.

    Returns:
        List of registered exchange identifiers
    """
    return exchange_factory.list_registered()
