from __future__ import annotations
import os
from pathlib import Path
import tempfile
import logging

APP_NAME = "GameLibraryManager"

def get_app_dir() -> Path:
    # Prefer Roaming AppData, fallback to LocalAppData, then home.
    base = os.environ.get("APPDATA")
    if not base:
        base = os.environ.get("LOCALAPPDATA", "")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p

def library_json_path() -> Path:
    return get_app_dir() / "library.json"

def settings_json_path() -> Path:
    return get_app_dir() / "settings.json"

def temp_data_dir() -> Path:
    return Path(tempfile.gettempdir()) / APP_NAME

def paths_diag(logger: logging.Logger) -> None:
    try:
        base = Path(__file__).resolve()
        proj_root = base.parent.parent.parent
        log = logger.info
    except (OSError, RuntimeError, AttributeError):
        # Silently skip diagnostic if path resolution fails
        return
    log("paths_diag %s", {
        "cwd": str(Path.cwd()),
        "__file__": str(base),
        "project_root": str(proj_root),
        "app_dir": str(get_app_dir()),
        "library_json": str(library_json_path()),
        "settings_json": str(settings_json_path()),
    })
