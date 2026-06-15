"""
Historical-fixture round-trip tests for app.storage.json_store.

Milestone 1 exit criterion: "Every historical fixture loads and round-trips."

These exercise on-disk documents written by older app versions:
  - a v1 (games-only) library, including legacy field names, mixed datetime
    encodings (trailing-Z UTC, naive ISO, epoch seconds), and unknown fields;
  - a v2 bundle with manual + smart collections, including the legacy
    `manual_game_ids` collection key.

Each fixture must load through the public API and, once decoded into the
domain model, survive a save -> reload cycle without loss.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.storage import json_store
from app.storage.json_store import (
    load_library,
    load_library_bundle,
    load_settings,
    save_library_bundle,
    save_settings,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def isolated_fallback(tmp_path, monkeypatch):
    """Point the fallback (temp) directory at an isolated, empty dir."""
    fb = tmp_path / "fallback"
    fb.mkdir()
    monkeypatch.setattr(json_store, "temp_data_dir", lambda: fb)
    return fb


def _stage(tmp_path: Path, fixture_name: str, dest_name: str) -> Path:
    """Copy a fixture verbatim into an isolated primary path and return it."""
    dest = tmp_path / dest_name
    dest.write_text(
        (FIXTURES / fixture_name).read_text(encoding="utf-8"), encoding="utf-8"
    )
    return dest


def test_v1_games_only_fixture_migrates_and_loads(tmp_path, isolated_fallback):
    path = _stage(tmp_path, "library_v1_games_only.json", "library.json")

    games, collections = load_library_bundle(path)

    assert [g.game_id for g in games] == ["game-001", "game-002"]
    # v1 carries no collections; migration to v2 yields an empty list.
    assert collections == []

    by_id = {g.game_id: g for g in games}
    # Legacy selected_launcher_path is mapped onto backup_target_path.
    assert by_id["game-002"].backup_target_path == "D:\\Games\\PixelQuest\\pixelquest.exe"
    # Unknown legacy fields are dropped rather than crashing the loader.
    assert not hasattr(by_id["game-002"], "legacy_only_field")

    # Mixed datetime encodings decode per documented _str_to_dt behaviour.
    assert by_id["game-001"].last_played == datetime(
        2026, 1, 15, 20, 30, tzinfo=timezone.utc
    )
    assert by_id["game-001"].source_checked_at == datetime(2026, 1, 10, 8, 0)
    assert by_id["game-001"].last_download_at == datetime.fromtimestamp(
        1700000000, tz=timezone.utc
    ).astimezone(None)


def test_legacy_load_library_reads_v1_fixture(tmp_path, isolated_fallback):
    path = _stage(tmp_path, "library_v1_games_only.json", "library.json")

    games = load_library(path)

    assert [g.game_id for g in games] == ["game-001", "game-002"]


def test_v2_bundle_fixture_loads_with_collections(tmp_path, isolated_fallback):
    path = _stage(tmp_path, "library_v2_bundle.json", "library.json")

    games, collections = load_library_bundle(path)

    assert [g.game_id for g in games] == ["game-010", "game-011"]

    cols = {c.collection_id: c for c in collections}
    assert cols["col-fav"].type == "manual"
    # Legacy manual_game_ids migrates to game_ids.
    assert cols["col-fav"].game_ids == ["game-010"]
    assert cols["col-high"].type == "smart"
    assert cols["col-high"].filter == {"rating_min": 8}
    assert cols["col-high"].game_ids == []


@pytest.mark.parametrize(
    "fixture",
    ["library_v1_games_only.json", "library_v2_bundle.json"],
)
def test_library_fixtures_round_trip_without_loss(tmp_path, isolated_fallback, fixture):
    src = _stage(tmp_path, fixture, "library.json")
    games, collections = load_library_bundle(src)

    out = tmp_path / f"roundtrip_{fixture}"
    save_library_bundle(out, games, collections)
    games2, collections2 = load_library_bundle(out)

    # The decoded domain model is stable across a save -> reload cycle.
    assert games2 == games
    assert collections2 == collections

    # The re-saved document is the current schema version.
    stored = json.loads(out.read_text(encoding="utf-8"))
    assert stored["version"] == 2


def test_settings_fixture_loads_and_round_trips(tmp_path, isolated_fallback):
    path = _stage(tmp_path, "settings_legacy.json", "settings.json")

    data = load_settings(path)
    assert data["root_folder"] == "C:\\Users\\Player\\Games"
    assert data["splitter_sizes"] == [250, 800]

    out = tmp_path / "settings_out.json"
    save_settings(out, data)
    assert load_settings(out) == data
