from __future__ import annotations
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import Game, Collection
from app.logging_utils import get_logger, kv
from app.storage.paths import temp_data_dir
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

_log = get_logger("storage.json")

def _warn_fallback(fb_path: Path) -> None:
    try:
        app = QApplication.instance()
        if app:
            box = QMessageBox(QMessageBox.Warning, "Storage fallback", f"Primary data path not writable.\nUsing: {fb_path}", QMessageBox.Ok)
            box.setWindowModality(Qt.NonModal if hasattr(box, "setWindowModality") else 0)
            box.setAttribute(Qt.WA_DeleteOnClose)
            box.show()
    except Exception:
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
        "games": []
    }
    for g in games:
        obj = asdict(g)
        obj["last_played"] = _dt_to_str(g.last_played)
        obj["source_checked_at"] = _dt_to_str(g.source_checked_at)
        data["games"].append(obj)

    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("save_library_done %s", kv(path=path, count=len(games), bytes=path.stat().st_size if path.exists() else 0,
                                             duration_ms=round((time.perf_counter()-start)*1000,1), fallback_used=False))
    except Exception as e:
        fb_dir = temp_data_dir()
        fb_dir.mkdir(parents=True, exist_ok=True)
        fb_path = fb_dir / path.name
        fb_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.error("save_library_fallback %s", kv(path=path, fallback=str(fb_path), err=e))
        _warn_fallback(fb_path)

def load_library(path: Path) -> List[Game]:
    """
    Backward compatible loader:
    - Ignores unknown fields from older versions
    - Migrates old keys when possible
    """
    start = time.perf_counter()
    if not path.exists():
        _log.warning("load_library_missing %s", kv(path=path))
        return []

    raw = json.loads(path.read_text(encoding="utf-8"))
    games: List[Game] = []

    # Allowed keys for current Game model
    allowed = set(Game.__dataclass_fields__.keys())

    for obj in raw.get("games", []):
        # datetime field
        obj["last_played"] = _str_to_dt(obj.get("last_played"))
        obj["source_checked_at"] = _str_to_dt(obj.get("source_checked_at"))

        # ---- migrations from older versions ----
        # Old scan version used folder_path + launcher fields
        # New shortcut manager uses shortcut_path + shortcut_type
        if "shortcut_path" not in obj:
            # If old data has folder_path, keep it but ignore it later
            pass

        # If old model used selected_launcher_path, treat it as backup target
        if "selected_launcher_path" in obj and "backup_target_path" not in obj:
            obj["backup_target_path"] = obj.get("selected_launcher_path", "")

        # Old field names that should be dropped automatically:
        # folder_path, launcher_type, selected_launcher_path, etc.

        # ---- filter unknown keys ----
        cleaned = {k: v for k, v in obj.items() if k in allowed}

        # Ensure required fields exist
        cleaned.setdefault("game_id", "")
        cleaned.setdefault("title", "Unknown")
        cleaned.setdefault("game_folder_path", "")
        cleaned.setdefault("icon_upscaled", False)

        games.append(Game(**cleaned))

    _log.info("load_library_done %s", kv(path=path, count=len(games), duration_ms=round((time.perf_counter()-start)*1000,1)))
    return games


def save_settings(path: Path, settings: Dict[str, Any]) -> None:
    start = time.perf_counter()
    try:
        path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info("save_settings_done %s", kv(path=path, keys=len(settings), duration_ms=round((time.perf_counter()-start)*1000,1), fallback_used=False))
    except Exception as e:
        fb_dir = temp_data_dir()
        fb_dir.mkdir(parents=True, exist_ok=True)
        fb_path = fb_dir / path.name
        fb_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.error("save_settings_fallback %s", kv(path=path, fallback=str(fb_path), err=e))
        _warn_fallback(fb_path)

def load_settings(path: Path) -> Dict[str, Any]:
    start = time.perf_counter()
    if not path.exists():
        _log.warning("load_settings_missing %s", kv(path=path))
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    _log.info("load_settings_done %s", kv(path=path, keys=len(data), duration_ms=round((time.perf_counter()-start)*1000,1)))
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
    data: Dict[str, Any] = {
        "version": 2,
        "games": [],
        "collections": [],
    }

    for g in games:
        obj = asdict(g)
        obj["last_played"] = _dt_to_str(g.last_played)
        obj["source_checked_at"] = _dt_to_str(g.source_checked_at)
        data["games"].append(obj)

    for c in collections:
        data["collections"].append(asdict(c))

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_library_bundle(path: Path) -> tuple[List[Game], List[Collection]]:
    """
    Backward compatible:
    - v1 had only games
    - v2 has games + collections
    """
    if not path.exists():
        return [], []

    raw = json.loads(path.read_text(encoding="utf-8"))

    games: List[Game] = []
    collections: List[Collection] = []

    # ---- games (your existing backward compatible logic) ----
    allowed_game = set(Game.__dataclass_fields__.keys())
    for obj in raw.get("games", []):
        obj["last_played"] = _str_to_dt(obj.get("last_played"))
        obj["source_checked_at"] = _str_to_dt(obj.get("source_checked_at"))

        # migrate older key names if needed
        if "selected_launcher_path" in obj and "backup_target_path" not in obj:
            obj["backup_target_path"] = obj.get("selected_launcher_path", "")

        cleaned = {k: v for k, v in obj.items() if k in allowed_game}
        cleaned.setdefault("game_id", "")
        cleaned.setdefault("title", "Unknown")
        cleaned.setdefault("game_folder_path", "")
        cleaned.setdefault("icon_upscaled", False)
        games.append(Game(**cleaned))

    # ---- collections (v2 only; safe if missing) ----
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
