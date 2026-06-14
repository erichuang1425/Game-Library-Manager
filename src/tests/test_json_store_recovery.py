"""
Recovery / fault-injection tests for app.storage.json_store.

These cover the hardening called out in PR #31 review:
  - P1: recovery must select the *newest valid* persisted copy rather than using
        an unconditional primary -> fallback precedence.
  - P2: recovery must also consider fallback backup generations.
Plus the atomic-write backup chain and the last_download_at datetime round-trip.
"""
import json
import os

import pytest

from app.models import Game
from app.exceptions import StorageError
from app.storage import json_store
from app.storage.json_store import (
    _atomic_write_json,
    _read_with_recovery,
    _backup_path,
    _is_library_payload,
    BACKUP_GENERATIONS,
    save_library,
    load_library,
)
from datetime import datetime


@pytest.fixture
def isolated_fallback(tmp_path, monkeypatch):
    """Point the fallback (temp) directory at an isolated dir for the test."""
    fb_dir = tmp_path / "fallback"
    fb_dir.mkdir()
    monkeypatch.setattr(json_store, "temp_data_dir", lambda: fb_dir)
    return fb_dir


def _set_mtime(path, seconds):
    os.utime(path, (seconds, seconds))


def test_round_trip(tmp_path, isolated_fallback):
    primary = tmp_path / "library.json"
    _atomic_write_json(primary, {"version": 1, "games": [{"game_id": "1"}]})
    assert _read_with_recovery(primary) == {"version": 1, "games": [{"game_id": "1"}]}


def test_newest_valid_copy_wins_over_stale_primary(tmp_path, isolated_fallback):
    """P1: a newer fallback save must not be discarded in favour of an older primary."""
    primary = tmp_path / "library.json"
    fallback = isolated_fallback / "library.json"

    _atomic_write_json(primary, {"version": 1, "marker": "old-primary"})
    _atomic_write_json(fallback, {"version": 1, "marker": "new-fallback"})

    # Make the fallback unambiguously newer than the primary.
    _set_mtime(primary, 1_000_000)
    _set_mtime(fallback, 2_000_000)

    data = _read_with_recovery(primary)
    assert data["marker"] == "new-fallback"


def test_newer_primary_outranks_stale_fallback(tmp_path, isolated_fallback):
    """P1: a stale fallback must not outrank a newer primary copy."""
    primary = tmp_path / "library.json"
    fallback = isolated_fallback / "library.json"

    _atomic_write_json(fallback, {"version": 1, "marker": "stale-fallback"})
    _atomic_write_json(primary, {"version": 1, "marker": "fresh-primary"})

    _set_mtime(fallback, 1_000_000)
    _set_mtime(primary, 2_000_000)

    data = _read_with_recovery(primary)
    assert data["marker"] == "fresh-primary"


def test_fallback_backup_used_when_active_fallback_corrupt(tmp_path, isolated_fallback):
    """P2: fallback backup generations must be recovery candidates."""
    primary = tmp_path / "library.json"
    fallback = isolated_fallback / "library.json"

    # Two fallback saves -> fallback + fallback.bak.1
    _atomic_write_json(fallback, {"version": 1, "marker": "fb-gen1"})
    _atomic_write_json(fallback, {"version": 1, "marker": "fb-gen2"})
    assert _backup_path(fallback, 1).exists()

    # Corrupt the active fallback; the .bak.1 generation is still good.
    fallback.write_text("{not json", encoding="utf-8")

    # No primary exists at all.
    assert not primary.exists()

    data = _read_with_recovery(primary)
    assert data["marker"] == "fb-gen1"


def test_all_copies_corrupt_raises(tmp_path, isolated_fallback):
    primary = tmp_path / "library.json"
    primary.write_text("{broken", encoding="utf-8")
    with pytest.raises(StorageError):
        _read_with_recovery(primary)


def test_missing_returns_none(tmp_path, isolated_fallback):
    primary = tmp_path / "library.json"
    assert _read_with_recovery(primary) is None


def test_write_falls_back_when_primary_unwritable(tmp_path, isolated_fallback):
    """A blocked primary path triggers an atomic fallback write."""
    # Place a regular file where the primary's parent directory should be so
    # mkdir(parents=True) fails -> fallback path is taken.
    blocked = tmp_path / "blocked"
    blocked.write_text("x", encoding="utf-8")
    primary = blocked / "library.json"

    written = json_store._write_with_fallback(primary, {"version": 1, "marker": "v"})
    assert written == isolated_fallback / "library.json"
    assert _read_with_recovery(primary)["marker"] == "v"


def test_backup_rotation_does_not_promote_corrupt(tmp_path, isolated_fallback):
    primary = tmp_path / "library.json"
    _atomic_write_json(primary, {"version": 1, "marker": "good"})

    # Corrupt the live file, then write again: the corrupt copy must NOT be
    # promoted into the backup chain.
    primary.write_text("{corrupt", encoding="utf-8")
    _atomic_write_json(primary, {"version": 1, "marker": "good2"})

    bak1 = _backup_path(primary, 1)
    if bak1.exists():
        assert json.loads(bak1.read_text(encoding="utf-8"))["marker"] != "{corrupt"


def test_backup_chain_capped_at_generations(tmp_path, isolated_fallback):
    primary = tmp_path / "library.json"
    for i in range(BACKUP_GENERATIONS + 3):
        _atomic_write_json(primary, {"version": 1, "n": i})
    # Never more than BACKUP_GENERATIONS backups exist.
    assert not _backup_path(primary, BACKUP_GENERATIONS + 1).exists()


def test_wrong_shape_candidate_does_not_outrank_good_backup(tmp_path, isolated_fallback):
    """P1: a newer but wrong-shaped library file must not hide a recoverable backup."""
    primary = tmp_path / "library.json"

    _atomic_write_json(primary, {"version": 1, "games": [{"game_id": "keep"}]})
    _atomic_write_json(primary, {"version": 1, "games": [{"game_id": "keep2"}]})
    assert _backup_path(primary, 1).exists()  # bak.1 holds the first good copy

    # Overwrite the live file with valid JSON of the wrong shape, made newest.
    primary.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    _set_mtime(primary, 9_000_000)

    data = _read_with_recovery(primary, validate=_is_library_payload)
    assert isinstance(data.get("games"), list)
    assert data["games"][0]["game_id"] in {"keep", "keep2"}


def test_wrong_shape_only_candidate_raises(tmp_path, isolated_fallback):
    """P1: if every candidate is parseable but wrong-shaped, surface a StorageError."""
    primary = tmp_path / "library.json"
    primary.write_text(json.dumps({"not": "a library"}), encoding="utf-8")
    with pytest.raises(StorageError):
        _read_with_recovery(primary, validate=_is_library_payload)


def test_empty_library_is_valid_payload():
    assert _is_library_payload({"version": 1, "games": []})
    assert not _is_library_payload({})
    assert not _is_library_payload({"games": "nope"})
    assert not _is_library_payload({"games": [1, 2]})
    assert not _is_library_payload({"games": [], "collections": {}})
    assert not _is_library_payload({"games": [], "collections": [None]})
    assert not _is_library_payload({"games": [], "collections": [1]})
    assert _is_library_payload({"games": [], "collections": [{"collection_id": "c"}]})


def test_failed_serialization_does_not_rotate_backups(tmp_path, isolated_fallback):
    """P2: a save that fails before replace must not advance the backup chain."""
    primary = tmp_path / "library.json"
    _atomic_write_json(primary, {"version": 1, "games": [{"game_id": "v0"}]})
    _atomic_write_json(primary, {"version": 1, "games": [{"game_id": "v1"}]})

    bak1 = _backup_path(primary, 1)
    before = bak1.read_text(encoding="utf-8")
    assert not _backup_path(primary, 2).exists()

    # Unserializable payload -> json.dumps raises before any rotation/replace.
    with pytest.raises(TypeError):
        _atomic_write_json(primary, {"bad": {object()}})

    # Backup chain unchanged; no generation evicted.
    assert bak1.read_text(encoding="utf-8") == before
    assert not _backup_path(primary, 2).exists()
    # Live file still the last good write.
    assert json.loads(primary.read_text(encoding="utf-8"))["games"][0]["game_id"] == "v1"


def test_last_download_at_round_trip(tmp_path, isolated_fallback):
    """last_download_at must serialize/deserialize like the other datetime fields."""
    primary = tmp_path / "library.json"
    dt = datetime(2026, 6, 14, 10, 1, 57)
    save_library(primary, [Game(game_id="1", title="A", last_download_at=dt)])

    # Stored as an ISO string (not a raw datetime, which would crash json.dumps).
    stored = json.loads(primary.read_text(encoding="utf-8"))
    assert stored["games"][0]["last_download_at"] == dt.isoformat()

    games = load_library(primary)
    assert games[0].last_download_at == dt
