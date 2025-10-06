"""Database connection manager using aiosqlite.

Provides async SQLite database connection management with connection pooling,
WAL mode for better concurrent access, and proper resource cleanup.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

import aiosqlite

from tri_arb.config.logging import get_logger
from tri_arb.config.settings import settings

logger = get_logger(__name__)


class DatabaseManager:
    """Manages SQLite database connections with connection pooling.

    Attributes:
        db_path: Path to SQLite database file
        pool_size: Maximum number of concurrent connections
        _connections: Pool of database connections
        _semaphore: Semaphore to limit concurrent connections
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        pool_size: Optional[int] = None,
    ) -> None:
        """Initialize database manager.

        Args:
            db_path: Path to database file (default from settings)
            pool_size: Connection pool size (default from settings)
        """
        self.db_path = Path(db_path or settings.db_path)
        self.pool_size = pool_size or settings.db_pool_size
        self._connections: list[aiosqlite.Connection] = []
        self._semaphore = asyncio.Semaphore(self.pool_size)
        self._initialized = False

        logger.info(
            "DatabaseManager initialized",
            db_path=str(self.db_path),
            pool_size=self.pool_size,
        )

    async def initialize(self) -> None:
        """Initialize database and enable WAL mode.

        Creates database file if it doesn't exist and enables Write-Ahead Logging
        for better concurrent read performance.
        """
        if self._initialized:
            logger.warning("Database already initialized")
            return

        # Create database file and parent directories if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Open connection to initialize database
        async with aiosqlite.connect(str(self.db_path)) as conn:
            # Enable WAL mode for better concurrent access
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            await conn.commit()

        self._initialized = True
        logger.info("Database initialized with WAL mode", db_path=str(self.db_path))

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get a database connection from the pool.

        Yields:
            Database connection

        Example:
            async with db_manager.connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT * FROM trades")
                    rows = await cursor.fetchall()
        """
        if not self._initialized:
            await self.initialize()

        # Acquire semaphore to limit concurrent connections
        async with self._semaphore:
            conn = await aiosqlite.connect(str(self.db_path), timeout=settings.db_timeout)
            try:
                # Enable foreign keys
                await conn.execute("PRAGMA foreign_keys=ON")
                yield conn
            finally:
                await conn.close()

    async def execute(self, query: str, parameters: tuple = ()) -> None:
        """Execute a SQL query without returning results.

        Args:
            query: SQL query to execute
            parameters: Query parameters

        Example:
            await db_manager.execute(
                "INSERT INTO trades (id, price) VALUES (?, ?)",
                ("trade_123", 50000.0)
            )
        """
        async with self.connection() as conn:
            await conn.execute(query, parameters)
            await conn.commit()

        logger.debug("Executed query", query=query[:100])

    async def fetch_one(self, query: str, parameters: tuple = ()) -> Optional[dict]:
        """Execute a query and fetch one result.

        Args:
            query: SQL query to execute
            parameters: Query parameters

        Returns:
            Single row as dict, or None if no results

        Example:
            result = await db_manager.fetch_one(
                "SELECT * FROM trades WHERE id = ?",
                ("trade_123",)
            )
        """
        async with self.connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, parameters) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None

    async def fetch_all(self, query: str, parameters: tuple = ()) -> list[dict]:
        """Execute a query and fetch all results.

        Args:
            query: SQL query to execute
            parameters: Query parameters

        Returns:
            List of rows as dicts

        Example:
            results = await db_manager.fetch_all(
                "SELECT * FROM trades WHERE exchange = ?",
                ("binance",)
            )
        """
        async with self.connection() as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, parameters) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def close(self) -> None:
        """Close all database connections.

        Should be called during application shutdown.
        """
        for conn in self._connections:
            await conn.close()
        self._connections.clear()
        logger.info("All database connections closed")


# Global database manager instance
db_manager = DatabaseManager()
