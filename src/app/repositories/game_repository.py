"""Game repository implementation."""

from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.logging_utils import get_logger, kv
from app.models import Game
from app.storage.paths import library_json_path

from .base import Repository

_log = get_logger("game_repository")


class GameRepository(Repository[Game, str]):
    """
    Abstract repository for Game entities.

    Extends the base Repository with game-specific query methods.
    """

    def find_by_title(self, title: str, exact: bool = False) -> List[Game]:
        """
        Find games by title.

        Args:
            title: Title to search for
            exact: If True, require exact match; otherwise partial match

        Returns:
            List of matching games
        """
        title_lower = title.lower()
        if exact:
            return [g for g in self.get_all() if g.title.lower() == title_lower]
        return [g for g in self.get_all() if title_lower in g.title.lower()]

    def find_by_status(self, status: str) -> List[Game]:
        """Find games by status."""
        return [g for g in self.get_all() if g.status == status]

    def find_by_tag(self, tag: str) -> List[Game]:
        """Find games that have a specific tag."""
        return [g for g in self.get_all() if tag in (g.tags or [])]

    def find_by_shortcut_path(self, path: str) -> Optional[Game]:
        """Find a game by its shortcut path."""
        path_lower = path.lower()
        for g in self.get_all():
            if g.shortcut_path and g.shortcut_path.lower() == path_lower:
                return g
        return None

    def find_with_updates(self) -> List[Game]:
        """Find games that have available updates."""
        games = []
        for g in self.get_all():
            if (
                g.source_version_raw
                and g.installed_version_raw
                and g.source_version_raw != g.installed_version_raw
            ):
                games.append(g)
        return games

    def find_missing_files(self) -> List[Game]:
        """Find games with missing shortcut files."""
        games = []
        for g in self.get_all():
            if g.shortcut_path and not Path(g.shortcut_path).exists():
                games.append(g)
        return games

    def find_by_filter(
        self,
        predicate: Callable[[Game], bool]
    ) -> List[Game]:
        """Find games matching a custom predicate."""
        return [g for g in self.get_all() if predicate(g)]


class JsonGameRepository(GameRepository):
    """
    JSON file-based game repository.

    Stores games in a JSON file and maintains an in-memory cache
    for fast access.
    """

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        auto_persist: bool = True,
    ) -> None:
        """
        Initialize JSON game repository.

        Args:
            storage_path: Path to JSON file (uses default if not provided)
            auto_persist: If True, save to disk on every write operation
        """
        self._path = storage_path or library_json_path()
        self._auto_persist = auto_persist
        self._cache: Dict[str, Game] = {}
        self._loaded = False
        self._dirty = False

    def _ensure_loaded(self) -> None:
        """Load games from disk if not already loaded."""
        if self._loaded:
            return

        from app.storage.json_store import load_library_bundle

        if self._path.exists():
            games, _ = load_library_bundle(self._path)
            self._cache = {g.game_id: g for g in games}
            _log.info("repo_loaded %s", kv(count=len(self._cache)))
        else:
            self._cache = {}
            _log.info("repo_initialized_empty %s", kv(path=str(self._path)))

        self._loaded = True

    def _persist(self) -> None:
        """Save games to disk."""
        if not self._dirty:
            return

        from app.storage.json_store import load_library_bundle, save_library_bundle

        # Load collections to preserve them
        collections = []
        if self._path.exists():
            _, collections = load_library_bundle(self._path)

        games = list(self._cache.values())
        save_library_bundle(self._path, games, collections)
        self._dirty = False
        _log.info("repo_persisted %s", kv(count=len(games)))

    def get_all(self) -> List[Game]:
        """Get all games."""
        self._ensure_loaded()
        return list(self._cache.values())

    def get_by_id(self, game_id: str) -> Optional[Game]:
        """Get a game by ID."""
        self._ensure_loaded()
        return self._cache.get(game_id)

    def save(self, game: Game) -> None:
        """Save a game (insert or update)."""
        self._ensure_loaded()
        self._cache[game.game_id] = game
        self._dirty = True

        if self._auto_persist:
            self._persist()

    def delete(self, game_id: str) -> bool:
        """Delete a game by ID."""
        self._ensure_loaded()

        if game_id not in self._cache:
            return False

        del self._cache[game_id]
        self._dirty = True

        if self._auto_persist:
            self._persist()

        return True

    def exists(self, game_id: str) -> bool:
        """Check if a game exists."""
        self._ensure_loaded()
        return game_id in self._cache

    def count(self) -> int:
        """Count total games."""
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

    def bulk_save(self, games: List[Game]) -> None:
        """
        Save multiple games efficiently.

        More efficient than calling save() repeatedly as it only
        persists once at the end.
        """
        self._ensure_loaded()
        for game in games:
            self._cache[game.game_id] = game
        self._dirty = True
        self._persist()

    def bulk_delete(self, game_ids: List[str]) -> int:
        """
        Delete multiple games efficiently.

        Returns:
            Number of games deleted
        """
        self._ensure_loaded()
        count = 0
        for game_id in game_ids:
            if game_id in self._cache:
                del self._cache[game_id]
                count += 1

        if count > 0:
            self._dirty = True
            self._persist()

        return count


# Global instance
_game_repository: Optional[JsonGameRepository] = None


def get_game_repository() -> JsonGameRepository:
    """Get the global game repository instance."""
    global _game_repository
    if _game_repository is None:
        _game_repository = JsonGameRepository()
    return _game_repository
