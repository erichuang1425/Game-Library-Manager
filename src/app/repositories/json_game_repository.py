"""JSON file-backed game repository with O(1) lookups."""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional

from app.models import Game, Collection
from app.storage.json_store import load_library_bundle, save_library_bundle
from app.logging_utils import get_logger, kv

from .game_repository import GameRepository

_log = get_logger("repo.json")


class JsonGameRepository(GameRepository):
    """JSON file-backed game repository with O(1) lookups."""

    def __init__(self, library_path: Path) -> None:
        self._library_path = library_path
        games, collections = load_library_bundle(library_path)
        self._games: List[Game] = games
        self._index: Dict[str, Game] = {g.game_id: g for g in games}
        self._collections: List[Collection] = collections
        _log.info(
            "repo_loaded %s",
            kv(games=len(games), collections=len(collections)),
        )

    def get_all(self) -> List[Game]:
        return self._games

    def get_by_id(self, game_id: str) -> Optional[Game]:
        return self._index.get(game_id)

    def add(self, game: Game) -> None:
        self._games.append(game)
        self._index[game.game_id] = game

    def remove(self, game_id: str) -> None:
        self._games = [g for g in self._games if g.game_id != game_id]
        self._index.pop(game_id, None)

    def update_all(self, games: List[Game]) -> None:
        """Replace the full game list and rebuild index."""
        self._games = games
        self._rebuild_index()

    def save(self) -> None:
        save_library_bundle(self._library_path, self._games, self._collections)

    def get_collections(self) -> List[Collection]:
        return self._collections

    def set_collections(self, collections: List[Collection]) -> None:
        self._collections = collections

    def save_collections(self) -> None:
        self.save()

    @property
    def count(self) -> int:
        return len(self._games)

    @property
    def index(self) -> Dict[str, Game]:
        return self._index

    def _rebuild_index(self) -> None:
        self._index = {g.game_id: g for g in self._games}
