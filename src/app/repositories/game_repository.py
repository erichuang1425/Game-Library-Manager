"""Abstract game repository interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from app.models import Game, Collection


class GameRepository(ABC):
    """Abstract interface for game data access.

    Decouples data storage from UI logic, enabling unit testing
    with mock repositories and future backend changes (e.g. SQLite).
    """

    @abstractmethod
    def get_all(self) -> List[Game]:
        """Return all games."""

    @abstractmethod
    def get_by_id(self, game_id: str) -> Optional[Game]:
        """Return a game by ID, or None."""

    @abstractmethod
    def add(self, game: Game) -> None:
        """Add a game to the repository."""

    @abstractmethod
    def remove(self, game_id: str) -> None:
        """Remove a game by ID."""

    @abstractmethod
    def update_all(self, games: List[Game]) -> None:
        """Replace the full game list (after merge/import)."""

    @abstractmethod
    def save(self) -> None:
        """Persist all changes to storage."""

    @abstractmethod
    def get_collections(self) -> List[Collection]:
        """Return all collections."""

    @abstractmethod
    def set_collections(self, collections: List[Collection]) -> None:
        """Replace collections list."""

    @abstractmethod
    def save_collections(self) -> None:
        """Persist collections (bundled with games in JSON backend)."""

    @property
    @abstractmethod
    def count(self) -> int:
        """Return total game count."""

    @property
    @abstractmethod
    def index(self) -> Dict[str, Game]:
        """Return the game-id-to-Game lookup dict."""
