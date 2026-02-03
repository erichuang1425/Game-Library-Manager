"""Base repository interface."""

from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar

T = TypeVar("T")
ID = TypeVar("ID")


class Repository(ABC, Generic[T, ID]):
    """
    Abstract base repository interface.

    Provides a consistent API for data access operations regardless
    of the underlying storage mechanism.

    Type Parameters:
        T: The entity type this repository manages
        ID: The type of the entity's identifier
    """

    @abstractmethod
    def get_all(self) -> List[T]:
        """
        Retrieve all entities.

        Returns:
            List of all entities
        """
        pass

    @abstractmethod
    def get_by_id(self, entity_id: ID) -> Optional[T]:
        """
        Retrieve an entity by its ID.

        Args:
            entity_id: The unique identifier

        Returns:
            The entity if found, None otherwise
        """
        pass

    @abstractmethod
    def save(self, entity: T) -> None:
        """
        Save an entity (insert or update).

        Args:
            entity: The entity to save
        """
        pass

    @abstractmethod
    def delete(self, entity_id: ID) -> bool:
        """
        Delete an entity by its ID.

        Args:
            entity_id: The unique identifier

        Returns:
            True if entity was deleted, False if not found
        """
        pass

    @abstractmethod
    def exists(self, entity_id: ID) -> bool:
        """
        Check if an entity exists.

        Args:
            entity_id: The unique identifier

        Returns:
            True if entity exists
        """
        pass

    def count(self) -> int:
        """
        Count total entities.

        Returns:
            Number of entities
        """
        return len(self.get_all())

    def save_all(self, entities: List[T]) -> None:
        """
        Save multiple entities.

        Args:
            entities: List of entities to save
        """
        for entity in entities:
            self.save(entity)

    def delete_all(self) -> int:
        """
        Delete all entities.

        Returns:
            Number of entities deleted
        """
        all_entities = self.get_all()
        count = 0
        for entity in all_entities:
            entity_id = getattr(entity, "game_id", None) or getattr(entity, "collection_id", None)
            if entity_id and self.delete(entity_id):
                count += 1
        return count
