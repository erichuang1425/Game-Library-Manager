from __future__ import annotations
import json
import os
import shutil
import tempfile
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import Game, Collection
from app.logging_utils import get_logger, kv
from app.storage.paths import temp_data_dir
from app.exceptions import StorageError
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

_log = get_logger("storage.json")

_DATETIME_FIELDS = ("last_played", "source_checked_at", "last_download_at")
_BACKUP_COUNT = 3


def _fallback_path(path: Path) -> Path:
    """Return the deterministic emergency-storage path for *path*."""
    return temp_data_dir() / path.name


def _backup_path(path: Path, generation: int = 1) -> Path:
    return path.with_name(f"{path.name}.bak.{generation}")


def _rotate_backups(path: Path) -> None:
    """Keep the last three known-good versions without modifying the live file."""
    if not path.exists():
        return
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _log.warning("backup_skipped_invalid_source %s", kv(path=path))
        return
    for generation in range(_BACKUP_COUNT, 1, -1):
        older = _backup_path(path, generation - 1)
        newer = _backup_path(path, generation)
        if older.exists():
            os.replace(older, newer)
    shutil.copy2(path, _backup_path(path))


def _atomic_write_json(path: Path, data: Any) -> None:
    """Durably write JSON beside the destination and atomically replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    temp_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _rotate_backups(path)
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def _write_with_fallback(path: Path, data: Any) -> tuple[Path, bool]:
    try:
        _atomic_write_json(path, data)
        return path, False
    except OSError as error:
        fallback = _fallback_path(path)
        try:
            _atomic_write_json(fallback, data)
        except OSError as fallback_error:
            raise StorageError(
                f"Unable to save data to {path} or fallback {fallback}"
            ) from fallback_error
        _log.error("save_fallback %s", kv(path=path, fallback=fallback, err=error))
        _warn_fallback(fallback)
        return fallback, True


def _read_json(path: Path) -> tuple[Any, Path]:
    """Read primary, fallback, or newest valid backup in recovery order."""
    candidates = [path, _fallback_path(path)] + [
        _backup_path(path, generation) for generation in range(1, _BACKUP_COUNT + 1)
    ]
    failures: list[str] = []
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            failures.append(f"{candidate}: {error}")
            continue
        if candidate != path:
            _log.warning("load_recovered %s", kv(requested=path, source=candidate))
        return data, candidate
    if failures:
        raise StorageError(
            f"No valid JSON copy found for {path}: {'; '.join(failures)}"
        )
    raise FileNotFoundError(path)


def _serialize_game(game: Game) -> Dict[str, Any]:
    data = asdict(game)
    for field_name in _DATETIME_FIELDS:
        data[field_name] = _dt_to_str(getattr(game, field_name, None))
    return data


def _deserialize_game(obj: Dict[str, Any]) -> Game:
    data = dict(obj)
    for field_name in _DATETIME_FIELDS:
        data[field_name] = _str_to_dt(data.get(field_name))
    if "selected_launcher_path" in data and "backup_target_path" not in data:
        data["backup_target_path"] = data.get("selected_launcher_path", "")
    allowed = set(Game.__dataclass_fields__.keys())
    cleaned = {key: value for key, value in data.items() if key in allowed}
    cleaned.setdefault("game_id", "")
    cleaned.setdefault("title", "Unknown")
    cleaned.setdefault("game_folder_path", "")
    cleaned.setdefault("icon_upscaled", False)
    return Game(**cleaned)


def _warn_fallback(fb_path: Path) -> None:
    try:
        app = QApplication.instance()
        if app:
            box = QMessageBox(
                QMessageBox.Warning,
                "Storage fallback",
                f"Primary data path not writable.\nUsing: {fb_path}",
                QMessageBox.Ok,
            )
            box.setWindowModality(
                Qt.NonModal if hasattr(box, "setWindowModality") else 0
            )
            box.setAttribute(Qt.WA_DeleteOnClose)
            box.show()
    except (RuntimeError, AttributeError):
        # Silently skip UI notification if QApplication is not available or widget creation fails
        pass


def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
    """
    Robust loader for legacy / mixed datetime representations.
    Accepts:
      - None -> None
      - datetime -> passthrough
      - str (ISO; supports trailing Z) -> datetime
      - int/float (epoch seconds, assumed UTC) -> datetime
      - other -> None (logged)
    """
    from app.logging_utils import get_logger

    log = get_logger("json_store")

    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    if isinstance(s, (int, float)):
        try:
            return datetime.fromtimestamp(s, tz=timezone.utc).astimezone(None)
        except Exception as e:
            log.warning("Failed to parse epoch timestamp %s: %s", s, e)
            return None
    if isinstance(s, str):
        txt = s.strip()
        if not txt:
            return None
        # handle trailing Z (UTC)
        if txt.endswith("Z"):
            txt = txt[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(txt)
        except Exception as e:
            log.warning("Failed to parse datetime string %s: %s", s, e)
            return None

    log.warning("Unexpected datetime payload (type=%s): %s", type(s).__name__, s)
    return None


def save_library(path: Path, games: List[Game]) -> None:
    start = time.perf_counter()
    data: Dict[str, Any] = {
        "version": 1,
        "games": [_serialize_game(game) for game in games],
    }
    written_path, fallback_used = _write_with_fallback(path, data)
    _log.info(
        "save_library_done %s",
        kv(
            path=written_path,
            count=len(games),
            bytes=written_path.stat().st_size,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            fallback_used=fallback_used,
        ),
    )


def load_library(path: Path) -> List[Game]:
    """Load the library, recovering from fallback storage or backups if needed."""
    start = time.perf_counter()
    try:
        raw, source = _read_json(path)
    except FileNotFoundError:
        _log.warning("load_library_missing %s", kv(path=path))
        return []
    games = [_deserialize_game(obj) for obj in raw.get("games", [])]
    _log.info(
        "load_library_done %s",
        kv(
            path=source,
            count=len(games),
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        ),
    )
    return games


def save_settings(path: Path, settings: Dict[str, Any]) -> None:
    start = time.perf_counter()
    written_path, fallback_used = _write_with_fallback(path, settings)
    _log.info(
        "save_settings_done %s",
        kv(
            path=written_path,
            keys=len(settings),
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            fallback_used=fallback_used,
        ),
    )


def load_settings(path: Path) -> Dict[str, Any]:
    start = time.perf_counter()
    try:
        data, source = _read_json(path)
    except FileNotFoundError:
        _log.warning("load_settings_missing %s", kv(path=path))
        return {}
    _log.info(
        "load_settings_done %s",
        kv(
            path=source,
            keys=len(data),
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        ),
    )
    return data


def save_collections(path: Path, collections: List[Collection]) -> None:
    """
    Save both games + collections in the same file.
    (We keep the old function names, but we’ll update save_library/load_library to include collections.)
    """
    raise NotImplementedError("Use save_library_bundle instead")


def load_collections(path: Path) -> List[Collection]:
    raise NotImplementedError("Use load_library_bundle instead")


def save_library_bundle(
    path: Path, games: List[Game], collections: List[Collection]
) -> None:
    start = time.perf_counter()
    data: Dict[str, Any] = {
        "version": 2,
        "games": [_serialize_game(game) for game in games],
        "collections": [asdict(collection) for collection in collections],
    }
    written_path, fallback_used = _write_with_fallback(path, data)
    _log.info(
        "save_library_bundle_done %s",
        kv(
            path=written_path,
            games=len(games),
            collections=len(collections),
            bytes=written_path.stat().st_size,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
            fallback_used=fallback_used,
        ),
    )


def load_library_bundle(path: Path) -> tuple[List[Game], List[Collection]]:
    """Load a v1/v2 bundle, recovering from fallback storage or backups."""
    try:
        raw, _source = _read_json(path)
    except FileNotFoundError:
        return [], []

    games = [_deserialize_game(obj) for obj in raw.get("games", [])]
    collections: List[Collection] = []
    allowed = set(Collection.__dataclass_fields__.keys())
    for obj in raw.get("collections", []):
        cleaned = {key: value for key, value in obj.items() if key in allowed}
        cleaned.setdefault("collection_id", "")
        cleaned.setdefault("name", "Untitled")
        cleaned.setdefault("type", "manual")
        if "game_ids" not in cleaned and "manual_game_ids" in obj:
            cleaned["game_ids"] = obj.get("manual_game_ids", [])
        collections.append(Collection(**cleaned))
    return games, collections
