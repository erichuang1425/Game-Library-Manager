"""Tests for the repository pattern — JsonGameRepository."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from app.models import Game, Collection
from app.repositories.json_game_repository import JsonGameRepository


@pytest.fixture
def repo(tmp_path, sample_games):
    """Create a JsonGameRepository backed by a temp file."""
    lib_path = tmp_path / "library.json"
    # Write test data in the expected bundle format
    data = {
        "version": 2,
        "games": [],
        "collections": [],
    }
    for g in sample_games:
        from dataclasses import asdict
        obj = asdict(g)
        obj["last_played"] = None
        obj["source_checked_at"] = None
        obj["last_download_at"] = None
        data["games"].append(obj)

    lib_path.write_text(json.dumps(data), encoding="utf-8")

    return JsonGameRepository(lib_path)


class TestJsonGameRepository:
    def test_get_all(self, repo):
        games = repo.get_all()
        assert len(games) == 3

    def test_get_by_id(self, repo):
        g = repo.get_by_id("1")
        assert g is not None
        assert g.title == "Alpha Game"

    def test_get_by_id_missing(self, repo):
        assert repo.get_by_id("nonexistent") is None

    def test_add(self, repo):
        new = Game(game_id="4", title="Delta Game")
        repo.add(new)
        assert repo.count == 4
        assert repo.get_by_id("4") is not None

    def test_remove(self, repo):
        repo.remove("1")
        assert repo.count == 2
        assert repo.get_by_id("1") is None

    def test_update_all(self, repo):
        new_list = [Game(game_id="x", title="X")]
        repo.update_all(new_list)
        assert repo.count == 1
        assert repo.get_by_id("x") is not None
        assert repo.get_by_id("1") is None

    def test_count(self, repo):
        assert repo.count == 3

    def test_index(self, repo):
        idx = repo.index
        assert "1" in idx
        assert "2" in idx
        assert "3" in idx

    def test_collections(self, repo):
        assert repo.get_collections() == []
        coll = Collection(collection_id="c1", name="Favorites", game_ids=["1"])
        repo.set_collections([coll])
        assert len(repo.get_collections()) == 1
