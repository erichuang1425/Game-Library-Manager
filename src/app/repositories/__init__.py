"""
Repository pattern implementation for Game Library Manager.

Provides an abstraction layer between data access and business logic,
making the codebase more testable and maintainable.

Usage:
    from app.repositories import get_game_repository

    repo = get_game_repository()
    games = repo.get_all()
    game = repo.get_by_id("some-id")
    repo.save(game)
"""

from .base import Repository
from .game_repository import GameRepository, JsonGameRepository, get_game_repository
from .collection_repository import (
    CollectionRepository,
    JsonCollectionRepository,
    get_collection_repository,
)

__all__ = [
    "Repository",
    "GameRepository",
    "JsonGameRepository",
    "get_game_repository",
    "CollectionRepository",
    "JsonCollectionRepository",
    "get_collection_repository",
]
