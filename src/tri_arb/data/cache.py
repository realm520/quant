"""Cache wrapper using cachetools for in-memory caching.

Provides TTL-based and LRU caching strategies with async-safe access patterns.
"""

import asyncio
from typing import Any, Optional

from cachetools import LRUCache, TTLCache

from tri_arb.config.logging import get_logger
from tri_arb.config.settings import settings

logger = get_logger(__name__)


class CacheManager:
    """Manages in-memory caches with TTL and LRU strategies.

    Provides async-safe caching with configurable TTL and size limits.
    """

    def __init__(
        self,
        ttl: Optional[int] = None,
        max_size: Optional[int] = None,
    ) -> None:
        """Initialize cache manager.

        Args:
            ttl: Time-to-live in seconds (default from settings)
            max_size: Maximum cache size (default from settings)
        """
        self.ttl = ttl or settings.cache_ttl
        self.max_size = max_size or settings.cache_max_size

        # TTL cache for price data (short-lived)
        self._ttl_cache: TTLCache = TTLCache(maxsize=self.max_size, ttl=self.ttl)

        # LRU cache for exchange metadata (longer-lived)
        self._lru_cache: LRUCache = LRUCache(maxsize=self.max_size)

        # Lock for thread-safe access
        self._lock = asyncio.Lock()

        logger.info(
            "CacheManager initialized",
            ttl=self.ttl,
            max_size=self.max_size,
        )

    async def get_ttl(self, key: str) -> Optional[Any]:
        """Get value from TTL cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        async with self._lock:
            value = self._ttl_cache.get(key)
            if value is not None:
                logger.debug("TTL cache hit", key=key)
            else:
                logger.debug("TTL cache miss", key=key)
            return value

    async def set_ttl(self, key: str, value: Any) -> None:
        """Set value in TTL cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        async with self._lock:
            self._ttl_cache[key] = value
            logger.debug("TTL cache set", key=key)

    async def get_lru(self, key: str) -> Optional[Any]:
        """Get value from LRU cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        async with self._lock:
            value = self._lru_cache.get(key)
            if value is not None:
                logger.debug("LRU cache hit", key=key)
            else:
                logger.debug("LRU cache miss", key=key)
            return value

    async def set_lru(self, key: str, value: Any) -> None:
        """Set value in LRU cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        async with self._lock:
            self._lru_cache[key] = value
            logger.debug("LRU cache set", key=key)

    async def invalidate_ttl(self, key: str) -> bool:
        """Remove key from TTL cache.

        Args:
            key: Cache key to invalidate

        Returns:
            True if key was present, False otherwise
        """
        async with self._lock:
            try:
                del self._ttl_cache[key]
                logger.debug("TTL cache invalidated", key=key)
                return True
            except KeyError:
                logger.debug("TTL cache key not found", key=key)
                return False

    async def invalidate_lru(self, key: str) -> bool:
        """Remove key from LRU cache.

        Args:
            key: Cache key to invalidate

        Returns:
            True if key was present, False otherwise
        """
        async with self._lock:
            try:
                del self._lru_cache[key]
                logger.debug("LRU cache invalidated", key=key)
                return True
            except KeyError:
                logger.debug("LRU cache key not found", key=key)
                return False

    async def clear_ttl(self) -> None:
        """Clear all entries from TTL cache."""
        async with self._lock:
            self._ttl_cache.clear()
            logger.info("TTL cache cleared")

    async def clear_lru(self) -> None:
        """Clear all entries from LRU cache."""
        async with self._lock:
            self._lru_cache.clear()
            logger.info("LRU cache cleared")

    async def clear_all(self) -> None:
        """Clear all caches."""
        await self.clear_ttl()
        await self.clear_lru()
        logger.info("All caches cleared")

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        async with self._lock:
            return {
                "ttl_cache": {
                    "size": len(self._ttl_cache),
                    "max_size": self._ttl_cache.maxsize,
                    "ttl": self.ttl,
                },
                "lru_cache": {
                    "size": len(self._lru_cache),
                    "max_size": self._lru_cache.maxsize,
                },
            }


# Global cache manager instance
cache_manager = CacheManager()
