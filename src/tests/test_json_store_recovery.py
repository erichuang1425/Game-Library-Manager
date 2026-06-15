"""Fault-injection and recovery tests for JSON persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.exceptions import StorageError
from app.models import Collection, Game
from app.storage.json_store import (
    _atomic_write_json,
    _fallback_marker_path,
    _fallback_path,
    load_library_bundle,
    load_settings,
    save_library,
    save_library_bundle,
    save_settings,
)


def test_atomic_write_preserves_live_file_when_replace_fails(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"theme": "dark"}', encoding="utf-8")

    with patch("app.storage.json_store.os.replace", side_effect=OSError("injected")):
        with pytest.raises(OSError, match="injected"):
            _atomic_write_json(path, {"theme": "light"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"theme": "dark"}
    assert list(tmp_path.glob(".settings.json.*.tmp")) == []


def test_successive_saves_rotate_known_good_backups(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"

    for revision in range(1, 5):
        save_settings(path, {"revision": revision})

    assert load_settings(path) == {"revision": 4}
    assert json.loads((tmp_path / "settings.json.bak.1").read_text()) == {"revision": 3}
    assert json.loads((tmp_path / "settings.json.bak.2").read_text()) == {"revision": 2}
    assert json.loads((tmp_path / "settings.json.bak.3").read_text()) == {"revision": 1}


def test_load_recovers_from_newest_valid_backup(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    (tmp_path / "settings.json.bak.1").write_text(
        '{"recovered": true}', encoding="utf-8"
    )

    with patch(
        "app.storage.json_store.temp_data_dir", return_value=tmp_path / "fallback"
    ):
        assert load_settings(path) == {"recovered": True}


def test_load_raises_when_every_existing_copy_is_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    (tmp_path / "settings.json.bak.1").write_text("{also-broken", encoding="utf-8")

    with patch(
        "app.storage.json_store.temp_data_dir", return_value=tmp_path / "fallback"
    ):
        with pytest.raises(StorageError, match="No valid JSON copy"):
            load_settings(path)


def test_fallback_write_is_read_consistently(tmp_path: Path) -> None:
    primary = tmp_path / "primary" / "settings.json"
    fallback_dir = tmp_path / "fallback"
    real_atomic_write = _atomic_write_json

    def fail_primary(path: Path, data: object) -> None:
        if path == primary:
            raise OSError("primary unavailable")
        real_atomic_write(path, data)

    with (
        patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir),
        patch("app.storage.json_store._atomic_write_json", side_effect=fail_primary),
    ):
        save_settings(primary, {"theme": "dark"})

    with patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir):
        assert load_settings(primary) == {"theme": "dark"}


def test_fallback_write_wins_over_stale_primary(tmp_path: Path) -> None:
    primary = tmp_path / "primary" / "settings.json"
    primary.parent.mkdir()
    primary.write_text('{"theme": "old"}', encoding="utf-8")
    fallback_dir = tmp_path / "fallback"
    real_atomic_write = _atomic_write_json

    def fail_primary(path: Path, data: object) -> None:
        if path == primary:
            raise OSError("primary unavailable")
        real_atomic_write(path, data)

    with (
        patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir),
        patch("app.storage.json_store._atomic_write_json", side_effect=fail_primary),
    ):
        save_settings(primary, {"theme": "new"})

    with patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir):
        assert load_settings(primary) == {"theme": "new"}


def test_successful_primary_write_clears_fallback_marker(tmp_path: Path) -> None:
    primary = tmp_path / "primary" / "settings.json"
    fallback_dir = tmp_path / "fallback"
    real_atomic_write = _atomic_write_json

    def fail_primary(path: Path, data: object) -> None:
        if path == primary:
            raise OSError("primary unavailable")
        real_atomic_write(path, data)

    with (
        patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir),
        patch("app.storage.json_store._atomic_write_json", side_effect=fail_primary),
    ):
        save_settings(primary, {"theme": "fallback"})

    with patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir):
        save_settings(primary, {"theme": "primary"})
        assert load_settings(primary) == {"theme": "primary"}
        assert not _fallback_marker_path(primary).exists()


def test_fallback_paths_do_not_collide_for_matching_filenames(
    tmp_path: Path,
) -> None:
    fallback_dir = tmp_path / "fallback"
    first = tmp_path / "profile-a" / "settings.json"
    second = tmp_path / "profile-b" / "settings.json"

    with patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir):
        assert _fallback_path(first) != _fallback_path(second)


def test_marker_cleanup_failure_does_not_trigger_fallback_write(
    tmp_path: Path,
) -> None:
    primary = tmp_path / "primary" / "settings.json"
    fallback_dir = tmp_path / "fallback"
    real_atomic_write = _atomic_write_json

    def fail_primary(path: Path, data: object) -> None:
        if path == primary:
            raise OSError("primary unavailable")
        real_atomic_write(path, data)

    with (
        patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir),
        patch("app.storage.json_store._atomic_write_json", side_effect=fail_primary),
    ):
        save_settings(primary, {"theme": "fallback"})

    marker = None
    with patch("app.storage.json_store.temp_data_dir", return_value=fallback_dir):
        marker = _fallback_marker_path(primary)

        def fail_marker_cleanup(target: Path, **_: object) -> None:
            if target == marker:
                raise OSError("marker locked")

        with patch.object(
            Path,
            "unlink",
            autospec=True,
            side_effect=fail_marker_cleanup,
        ):
            save_settings(primary, {"theme": "primary"})

        assert marker.exists()
        assert load_settings(primary) == {"theme": "primary"}


def test_legacy_save_library_writes_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "library.json"

    save_library(path, [Game(game_id="game-1", title="Example")])

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["version"] == 2
    assert document["collections"] == []


def test_library_bundle_round_trips_every_datetime(tmp_path: Path) -> None:
    path = tmp_path / "library.json"
    timestamp = datetime(2026, 6, 14, 12, 30, tzinfo=timezone.utc)
    game = Game(
        game_id="game-1",
        title="Example",
        last_played=timestamp,
        source_checked_at=timestamp,
        last_download_at=timestamp,
    )
    collection = Collection(
        collection_id="favorites", name="Favorites", game_ids=["game-1"]
    )

    save_library_bundle(path, [game], [collection])
    games, collections = load_library_bundle(path)

    assert games[0].last_played == timestamp
    assert games[0].source_checked_at == timestamp
    assert games[0].last_download_at == timestamp
    assert collections == [collection]


def test_v1_library_document_migrates_to_bundle_shape(tmp_path: Path) -> None:
    path = tmp_path / "library.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "games": [{"game_id": "legacy", "title": "Legacy Game"}],
            }
        ),
        encoding="utf-8",
    )

    games, collections = load_library_bundle(path)

    assert [game.game_id for game in games] == ["legacy"]
    assert collections == []


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "top level"),
        ({"version": "2", "games": []}, "schema version"),
        ({"version": 99, "games": []}, "newer than supported"),
        ({"version": 2, "games": {}}, "'games' must contain a list"),
        ({"version": 2, "games": ["invalid"]}, "'games' must contain only objects"),
    ],
)
def test_invalid_library_documents_are_rejected(
    tmp_path: Path, payload: object, message: str
) -> None:
    path = tmp_path / "library.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StorageError, match=message):
        load_library_bundle(path)


def test_non_object_settings_document_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(StorageError, match="Settings JSON must contain an object"):
        load_settings(path)
