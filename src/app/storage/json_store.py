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

# Number of rotating known-good backup generations kept beside each persisted file.
BACKUP_GENERATIONS = 3

# Datetime fields on Game that must be round-tripped consistently.
_GAME_DT_FIELDS = ("last_played", "source_checked_at", "last_download_at")


def _warn_fallback(fb_path: Path) -> None:
    try:
        app = QApplication.instance()
        if app:
            box = QMessageBox(QMessageBox.Warning, "Storage fallback", f"Primary data path not writable.\nUsing: {fb_path}", QMessageBox.Ok)
            box.setWindowModality(Qt.NonModal if hasattr(box, "setWindowModality") else 0)
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


# ---------------------------------------------------------------------------
# Atomic write + recovery primitives
# ---------------------------------------------------------------------------

def _backup_path(path: Path, generation: int) -> Path:
    return path.with_name(f"{path.name}.bak.{generation}")


def _fallback_path(path: Path) -> Path:
    return temp_data_dir() / path.name


def _read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    """Parse a JSON object from disk, returning None if missing/unreadable/not an object."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _rotate_backup(path: Path) -> None:
    """
    Promote the current live file into the rotating backup chain.

    Only rotates when the live file contains valid JSON, so a corrupted live file
    is never promoted into the known-good backup set. Backups preserve the
    original modification time (copy2) so newest-valid recovery stays meaningful.
    """
    if _read_json_file(path) is None:
        return

    oldest = _backup_path(path, BACKUP_GENERATIONS)
    try:
        if oldest.exists():
            oldest.unlink()
    except OSError:
        pass

    for gen in range(BACKUP_GENERATIONS - 1, 0, -1):
        src = _backup_path(path, gen)
        dst = _backup_path(path, gen + 1)
        if src.exists():
            try:
                os.replace(src, dst)
            except OSError:
                pass

    try:
        shutil.copy2(path, _backup_path(path, 1))
    except OSError:
        pass


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """
    Write JSON atomically: serialize to a fsynced temp file in the destination
    directory, then atomically replace the target via os.replace. Rotates a
    known-good backup of the previous contents first.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_backup(path)

    text = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _write_with_fallback(path: Path, data: Dict[str, Any]) -> Path:
    """
    Atomically write to the primary path; on failure fall back to a temp
    directory copy (also written atomically, with its own backup chain).
    Returns the path actually written so callers can report the active location.
    """
    try:
        _atomic_write_json(path, data)
        return path
    except (OSError, IOError) as e:
        fb_path = _fallback_path(path)
        _atomic_write_json(fb_path, data)
        _log.error("write_fallback %s", kv(path=path, fallback=str(fb_path), err=e))
        _warn_fallback(fb_path)
        return fb_path


def _candidate_paths(path: Path) -> List[Path]:
    """
    All persisted copies that may hold recoverable data for a logical path:
    the primary and its backup generations, plus the fallback and ITS backup
    generations (these exist when the primary stayed unwritable across saves).
    """
    candidates = [path]
    candidates += [_backup_path(path, g) for g in range(1, BACKUP_GENERATIONS + 1)]
    fb = _fallback_path(path)
    candidates.append(fb)
    candidates += [_backup_path(fb, g) for g in range(1, BACKUP_GENERATIONS + 1)]
    return candidates


def _read_with_recovery(path: Path) -> Optional[Dict[str, Any]]:
    """
    Return the newest valid persisted copy among all candidates.

    Selection is by modification time (nanosecond resolution) rather than a
    fixed primary->fallback precedence, so a fallback save made after a transient
    primary failure is not silently discarded, and a stale fallback never
    outranks a newer primary or backup. Fallback backup generations are included
    so recovery succeeds even if the active fallback later becomes corrupt.

    Returns:
      - dict: contents of the newest valid copy
      - None: no candidate file exists at all (fresh install)
    Raises:
      - StorageError: candidate files exist but none are valid/recoverable
    """
    best: Optional[tuple[int, Dict[str, Any], Path]] = None
    any_existed = False

    for cand in _candidate_paths(path):
        if not cand.exists():
            continue
        any_existed = True
        data = _read_json_file(cand)
        if data is None:
            _log.warning("recovery_skip_invalid %s", kv(path=cand))
            continue
        try:
            mtime_ns = cand.stat().st_mtime_ns
        except OSError:
            continue
        if best is None or mtime_ns > best[0]:
            best = (mtime_ns, data, cand)

    if best is not None:
        if best[2] != path:
            _log.warning("recovery_used %s", kv(path=path, recovered_from=str(best[2])))
        return best[1]

    if any_existed:
        raise StorageError(f"All persisted copies of {path.name} are unreadable or corrupt")
    return None


# ---------------------------------------------------------------------------
# Game (de)serialization
# ---------------------------------------------------------------------------

def _serialize_game(g: Game) -> Dict[str, Any]:
    obj = asdict(g)
    for field in _GAME_DT_FIELDS:
        obj[field] = _dt_to_str(getattr(g, field, None))
    return obj


def _deserialize_game(obj: Dict[str, Any]) -> Game:
    """
    Backward compatible game loader:
    - Ignores unknown fields from older versions
    - Migrates old key names when possible
    """
    allowed = set(Game.__dataclass_fields__.keys())

    for field in _GAME_DT_FIELDS:
        if field in obj:
            obj[field] = _str_to_dt(obj.get(field))

    # If old model used selected_launcher_path, treat it as backup target
    if "selected_launcher_path" in obj and "backup_target_path" not in obj:
        obj["backup_target_path"] = obj.get("selected_launcher_path", "")

    cleaned = {k: v for k, v in obj.items() if k in allowed}

    # Ensure required fields exist
    cleaned.setdefault("game_id", "")
    cleaned.setdefault("title", "Unknown")
    cleaned.setdefault("game_folder_path", "")
    cleaned.setdefault("icon_upscaled", False)

    return Game(**cleaned)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_library(path: Path, games: List[Game]) -> None:
    start = time.perf_counter()
    data: Dict[str, Any] = {
        "version": 1,
        "games": [_serialize_game(g) for g in games],
    }
    written = _write_with_fallback(path, data)
    _log.info("save_library_done %s", kv(path=path, count=len(games),
                                         bytes=written.stat().st_size if written.exists() else 0,
                                         duration_ms=round((time.perf_counter() - start) * 1000, 1),
                                         fallback_used=written != path))


def load_library(path: Path) -> List[Game]:
    start = time.perf_counter()
    raw = _read_with_recovery(path)
    if raw is None:
        _log.warning("load_library_missing %s", kv(path=path))
        return []

    games = [_deserialize_game(obj) for obj in raw.get("games", [])]
    _log.info("load_library_done %s", kv(path=path, count=len(games), duration_ms=round((time.perf_counter() - start) * 1000, 1)))
    return games


def save_settings(path: Path, settings: Dict[str, Any]) -> None:
    start = time.perf_counter()
    written = _write_with_fallback(path, settings)
    _log.info("save_settings_done %s", kv(path=path, keys=len(settings),
                                          duration_ms=round((time.perf_counter() - start) * 1000, 1),
                                          fallback_used=written != path))


def load_settings(path: Path) -> Dict[str, Any]:
    start = time.perf_counter()
    data = _read_with_recovery(path)
    if data is None:
        _log.warning("load_settings_missing %s", kv(path=path))
        return {}
    _log.info("load_settings_done %s", kv(path=path, keys=len(data), duration_ms=round((time.perf_counter() - start) * 1000, 1)))
    return data


def save_collections(path: Path, collections: List[Collection]) -> None:
    """
    Save both games + collections in the same file.
    (We keep the old function names, but we’ll update save_library/load_library to include collections.)
    """
    raise NotImplementedError("Use save_library_bundle instead")


def load_collections(path: Path) -> List[Collection]:
    raise NotImplementedError("Use load_library_bundle instead")


def save_library_bundle(path: Path, games: List[Game], collections: List[Collection]) -> None:
    start = time.perf_counter()
    data: Dict[str, Any] = {
        "version": 2,
        "games": [_serialize_game(g) for g in games],
        "collections": [asdict(c) for c in collections],
    }
    written = _write_with_fallback(path, data)
    _log.info("save_library_bundle_done %s", kv(path=path, games=len(games), collections=len(collections),
                                                bytes=written.stat().st_size if written.exists() else 0,
                                                duration_ms=round((time.perf_counter() - start) * 1000, 1),
                                                fallback_used=written != path))


def load_library_bundle(path: Path) -> tuple[List[Game], List[Collection]]:
    """
    Backward compatible:
    - v1 had only games
    - v2 has games + collections
    """
    raw = _read_with_recovery(path)
    if raw is None:
        return [], []

    games = [_deserialize_game(obj) for obj in raw.get("games", [])]

    # ---- collections (v2 only; safe if missing) ----
    collections: List[Collection] = []
    allowed_col = set(Collection.__dataclass_fields__.keys())
    for obj in raw.get("collections", []):
        cleaned = {k: v for k, v in obj.items() if k in allowed_col}
        cleaned.setdefault("collection_id", "")
        cleaned.setdefault("name", "Untitled")
        cleaned.setdefault("type", "manual")
        # migrate legacy manual_game_ids -> game_ids
        if "game_ids" not in cleaned and "manual_game_ids" in obj:
            cleaned["game_ids"] = obj.get("manual_game_ids", [])
        collections.append(Collection(**cleaned))

    return games, collections
