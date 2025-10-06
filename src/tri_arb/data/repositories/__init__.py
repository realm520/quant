"""Repository pattern base classes.

Provides abstract base class for data access repositories following the
repository pattern for separation of concerns.
"""

from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar

from tri_arb.config.logging import get_logger

logger = get_logger(__name__)

# Type variable for model type
T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Abstract base repository with common CRUD operations.

    This base class defines the interface for all repositories in the application.
    Concrete repositories should implement these methods for specific entity types.
    """

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create a new entity.

        Args:
            entity: Entity to create

        Returns:
            Created entity with any generated fields populated

        Raises:
            Exception: If creation fails
        """
        pass

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> Optional[T]:
        """Get entity by ID.

        Args:
            entity_id: Unique identifier

        Returns:
            Entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Get all entities with pagination.

        Args:
            limit: Maximum number of entities to return
            offset: Number of entities to skip

        Returns:
            List of entities
        """
        pass

    @abstractmethod
    async def update(self, entity_id: str, entity: T) -> Optional[T]:
        """Update an existing entity.

        Args:
            entity_id: Unique identifier
            entity: Updated entity data

        Returns:
            Updated entity if found, None otherwise
        """
        pass

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """Delete an entity.

        Args:
            entity_id: Unique identifier

        Returns:
            True if entity was deleted, False if not found
        """
        pass

    @abstractmethod
    async def exists(self, entity_id: str) -> bool:
        """Check if entity exists.

        Args:
            entity_id: Unique identifier

        Returns:
            True if entity exists, False otherwise
        """
        pass

    @abstractmethod
    async def count(self) -> int:
        """Count total number of entities.

        Returns:
            Total entity count
        """
        pass
