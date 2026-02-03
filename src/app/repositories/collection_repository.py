"""Collection repository implementation."""

from pathlib import Path
from typing import Dict, List, Optional

from app.logging_utils import get_logger, kv
from app.models import Collection
from app.storage.paths import library_json_path

from .base import Repository

_log = get_logger("collection_repository")


class CollectionRepository(Repository[Collection, str]):
    """
    Abstract repository for Collection entities.

    Extends the base Repository with collection-specific query methods.
    """

    def find_by_name(self, name: str, exact: bool = False) -> List[Collection]:
        """
        Find collections by name.

        Args:
            name: Name to search for
            exact: If True, require exact match; otherwise partial match

        Returns:
            List of matching collections
        """
        name_lower = name.lower()
        if exact:
            return [c for c in self.get_all() if c.name.lower() == name_lower]
        return [c for c in self.get_all() if name_lower in c.name.lower()]

    def find_by_type(self, collection_type: str) -> List[Collection]:
        """Find collections by type (manual or smart)."""
        return [c for c in self.get_all() if c.type == collection_type]

    def find_manual_collections(self) -> List[Collection]:
        """Find all manual collections."""
        return self.find_by_type("manual")

    def find_smart_collections(self) -> List[Collection]:
        """Find all smart collections."""
        return self.find_by_type("smart")

    def find_containing_game(self, game_id: str) -> List[Collection]:
        """Find all manual collections containing a specific game."""
        return [
            c for c in self.get_all()
            if c.type == "manual" and game_id in (c.game_ids or [])
        ]


class JsonCollectionRepository(CollectionRepository):
    """
    JSON file-based collection repository.

    Stores collections alongside games in the same JSON file.
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        auto_persist: bool = True,
    ) -> None:
        """
        Initialize JSON collection repository.

        Args:
            storage_path: Path to JSON file (uses default if not provided)
            auto_persist: If True, save to disk on every write operation
        """
        self._path = storage_path or library_json_path()
        self._auto_persist = auto_persist
        self._cache: Dict[str, Collection] = {}
        self._loaded = False
        self._dirty = False

    def _ensure_loaded(self) -> None:
        """Load collections from disk if not already loaded."""
        if self._loaded:
            return

        from app.storage.json_store import load_library_bundle

        if self._path.exists():
            _, collections = load_library_bundle(self._path)
            self._cache = {c.collection_id: c for c in collections}
            _log.info("collection_repo_loaded %s", kv(count=len(self._cache)))
        else:
            self._cache = {}
            _log.info("collection_repo_initialized_empty %s", kv(path=str(self._path)))

        self._loaded = True

    def _persist(self) -> None:
        """Save collections to disk."""
        if not self._dirty:
            return

        from app.storage.json_store import load_library_bundle, save_library_bundle

        # Load games to preserve them
        games = []
        if self._path.exists():
            games, _ = load_library_bundle(self._path)

        collections = list(self._cache.values())
        save_library_bundle(self._path, games, collections)
        self._dirty = False
        _log.info("collection_repo_persisted %s", kv(count=len(collections)))

    def get_all(self) -> List[Collection]:
        """Get all collections."""
        self._ensure_loaded()
        return list(self._cache.values())

    def get_by_id(self, collection_id: str) -> Optional[Collection]:
        """Get a collection by ID."""
        self._ensure_loaded()
        return self._cache.get(collection_id)

    def save(self, collection: Collection) -> None:
        """Save a collection (insert or update)."""
        self._ensure_loaded()
        self._cache[collection.collection_id] = collection
        self._dirty = True

        if self._auto_persist:
            self._persist()

    def delete(self, collection_id: str) -> bool:
        """Delete a collection by ID."""
        self._ensure_loaded()

        if collection_id not in self._cache:
            return False

        del self._cache[collection_id]
        self._dirty = True

        if self._auto_persist:
            self._persist()

        return True

    def exists(self, collection_id: str) -> bool:
        """Check if a collection exists."""
        self._ensure_loaded()
        return collection_id in self._cache

    def count(self) -> int:
        """Count total collections."""
        self._ensure_loaded()
        return len(self._cache)

    def flush(self) -> None:
        """Force persist any pending changes."""
        if self._dirty:
            self._persist()

    def reload(self) -> None:
        """Force reload from disk, discarding any unsaved changes."""
        self._loaded = False
        self._dirty = False
        self._cache.clear()
        self._ensure_loaded()

    def add_game_to_collection(
        self,
        collection_id: str,
        game_id: str
    ) -> bool:
        """
        Add a game to a manual collection.

        Args:
            collection_id: ID of the collection
            game_id: ID of the game to add

        Returns:
            True if game was added, False if collection not found
            or game already in collection
        """
        collection = self.get_by_id(collection_id)
        if not collection or collection.type != "manual":
            return False

        if collection.game_ids is None:
            collection.game_ids = []

        if game_id in collection.game_ids:
            return False

        collection.game_ids.append(game_id)
        self.save(collection)
        return True

    def remove_game_from_collection(
        self,
        collection_id: str,
        game_id: str
    ) -> bool:
        """
        Remove a game from a manual collection.

        Args:
            collection_id: ID of the collection
            game_id: ID of the game to remove

        Returns:
            True if game was removed, False if collection not found
            or game not in collection
        """
        collection = self.get_by_id(collection_id)
        if not collection or collection.type != "manual":
            return False

        if collection.game_ids is None or game_id not in collection.game_ids:
            return False

        collection.game_ids.remove(game_id)
        self.save(collection)
        return True


# Global instance
_collection_repository: Optional[JsonCollectionRepository] = None


def get_collection_repository() -> JsonCollectionRepository:
    """Get the global collection repository instance."""
    global _collection_repository
    if _collection_repository is None:
        _collection_repository = JsonCollectionRepository()
    return _collection_repository
