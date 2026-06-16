"""
Corruption-recovery UX tests for app.storage.json_store.

These cover the report/quarantine behavior that lets the UI explain recovery to
the user (Complete Revamp Plan, Milestone 1 — "corruption recovery UX") instead
of recovering silently or crashing during construction:

  - A clean primary load reports no recovery.
  - A fresh install (nothing on disk) reports no recovery and is not fatal.
  - Recovery from a backup/fallback copy is reported as ``recovered``.
  - An unrecoverable load is reported as ``fatal``, never raises, quarantines the
    corrupt copies, and leaves the originals untouched.
  - A valid-shaped but unmigratable (future-schema) library degrades to a fatal
    report instead of raising.
"""
import json

import pytest

from app.models import Game
from app.storage import json_store
from app.storage.json_store import (
    RecoveryReport,
    save_library_bundle,
    load_library_bundle_with_recovery,
)


@pytest.fixture
def isolated_fallback(tmp_path, monkeypatch):
    fb_dir = tmp_path / "fallback"
    fb_dir.mkdir()
    monkeypatch.setattr(json_store, "temp_data_dir", lambda: fb_dir)
    return fb_dir


def test_clean_load_reports_no_recovery(tmp_path, isolated_fallback):
    path = tmp_path / "library.json"
    save_library_bundle(path, [Game(game_id="1", title="A")], [])

    games, _collections, report = load_library_bundle_with_recovery(path)

    assert [g.game_id for g in games] == ["1"]
    assert isinstance(report, RecoveryReport)
    assert report.source == path
    assert not report.recovered
    assert not report.fatal
    assert not report.needs_notice


def test_missing_library_is_fresh_not_fatal(tmp_path, isolated_fallback):
    path = tmp_path / "library.json"

    games, collections, report = load_library_bundle_with_recovery(path)

    assert games == []
    assert collections == []
    assert not report.fatal
    assert not report.recovered
    assert report.source is None


def test_recovered_from_backup_is_reported(tmp_path, isolated_fallback):
    path = tmp_path / "library.json"
    # Two good saves -> live + bak.1, then corrupt the live file.
    save_library_bundle(path, [Game(game_id="1", title="A")], [])
    save_library_bundle(path, [Game(game_id="2", title="B")], [])
    path.write_text("{not json", encoding="utf-8")

    games, _collections, report = load_library_bundle_with_recovery(path)

    assert [g.game_id for g in games] == ["1"]  # the surviving backup
    assert report.recovered
    assert not report.fatal
    assert report.source == json_store._backup_path(path, 1)
    assert path in report.skipped
    assert report.needs_notice


def test_unreadable_library_is_fatal_and_quarantined(tmp_path, isolated_fallback):
    path = tmp_path / "library.json"
    original = "{totally broken"
    path.write_text(original, encoding="utf-8")

    games, collections, report = load_library_bundle_with_recovery(path)

    # Starts empty rather than crashing.
    assert games == []
    assert collections == []
    assert report.fatal
    assert report.needs_notice
    # The corrupt original is left in place...
    assert path.read_text(encoding="utf-8") == original
    # ...and a forensic copy was quarantined alongside it.
    assert report.quarantined
    quarantined = report.quarantined[0]
    assert quarantined.exists()
    assert quarantined.read_text(encoding="utf-8") == original
    assert ".corrupt-" in quarantined.name


def test_future_schema_version_degrades_to_fatal(tmp_path, isolated_fallback):
    path = tmp_path / "library.json"
    # Valid library shape (passes payload check) but a schema version we cannot
    # migrate, which load_library_bundle would raise on.
    path.write_text(
        json.dumps({"version": 999, "games": [{"game_id": "1"}]}),
        encoding="utf-8",
    )

    games, _collections, report = load_library_bundle_with_recovery(path)

    assert games == []
    assert report.fatal
    assert report.quarantined  # the source copy was preserved
