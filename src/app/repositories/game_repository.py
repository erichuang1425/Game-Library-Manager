"""Abstract game repository interface."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from app.models import Game, Collection


class GameRepository(ABC):
    """Abstract interface for game data access.

    Decouples data storage from UI logic, enabling unit testing
    with mock repositories and future backend changes (e.g. SQLite).

    Mutation contract
    -----------------
    The repository is the single source of truth for the game list, the
    ``game_id`` index, and the collection list. ``get_all()``, ``index``, and
    ``get_collections()`` return *live* references whose object identity is
    stable for the repository's lifetime, so callers may safely alias them.

    Every structural change — adding, replacing, removing, reordering, or
    bulk-replacing entries — MUST go through the mutating methods below.
    Callers must not rebind these references to fresh objects, because that
    would let the window and the repository diverge and silently bypass
    persistence. Implementations keep the ``game_id`` index consistent with the
    game list on every mutation.
    """

    @abstractmethod
    def get_all(self) -> List[Game]:
        """Return the live game list (stable identity; do not rebind)."""

    @abstractmethod
    def get_by_id(self, game_id: str) -> Optional[Game]:
        """Return a game by ID, or None."""

    @abstractmethod
    def add(self, game: Game) -> None:
        """Add a game to the repository."""

    @abstractmethod
    def upsert(self, game: Game) -> None:
        """Insert *game*, or replace the existing game with the same ID."""

    @abstractmethod
    def remove(self, game_id: str) -> None:
        """Remove a game by ID."""

    @abstractmethod
    def update_all(self, games: List[Game]) -> None:
        """Replace the full game list in place (after merge/import)."""

    @abstractmethod
    def save(self) -> None:
        """Persist all changes to storage."""

    @abstractmethod
    def get_collections(self) -> List[Collection]:
        """Return the live collection list (stable identity; do not rebind)."""

    @abstractmethod
    def set_collections(self, collections: List[Collection]) -> None:
        """Replace the collection list in place."""

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
