from __future__ import annotations
from pathlib import Path
from typing import Iterable, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFileIconProvider
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QFileInfo
from functools import lru_cache
import time
from app.logging_utils import get_logger, kv, RateLimiter

_icon_provider = QFileIconProvider()
_log = get_logger("icons")
_rate = RateLimiter()

# Base size for icon cache. 512 is sufficient for max card width of 320px
# while using 1/4 the memory of 1024. Qt SmoothTransformation keeps quality.
_BASE_ICON_SIZE = 512

@lru_cache(maxsize=2048)
def _icon_for_path_cached(path: str) -> QIcon:
    start = time.perf_counter()
    if not path:
        return QIcon()
    # Skip the redundant Path.exists() check — callers already filter via
    # best_icon_path / _first_existing.  The QFileIconProvider will return a
    # generic icon for missing files which we already handle as a null pixmap.
    ico = _icon_provider.icon(QFileInfo(path))
    if _rate.allow("icon_base_miss", 800):
        _log.debug("icon_base_miss %s", kv(path=path, duration_ms=round((time.perf_counter() - start) * 1000, 1)))
    return ico


def icon_for_path(path: str) -> QIcon:
    before = _icon_for_path_cached.cache_info()
    ico = _icon_for_path_cached(path)
    after = _icon_for_path_cached.cache_info()
    hit = after.hits > before.hits
    if _rate.allow(f"icon_cache:{path}", interval_ms=2000):
        _log.debug("icon_cache_%s %s", "hit" if hit else "miss", kv(path=path))
    return ico


@lru_cache(maxsize=2048)
def _raw_pixmap_cached(path: str) -> QPixmap:
    """Highest-quality pixmap we can get for a path."""
    ico = icon_for_path(path)
    pm = ico.pixmap(QSize(_BASE_ICON_SIZE, _BASE_ICON_SIZE))
    return pm


@lru_cache(maxsize=4096)
def _scaled_pixmap_cached(path: str, size: int) -> QPixmap:
    base = _raw_pixmap_cached(path)
    if base.isNull():
        return QPixmap()
    if max(base.width(), base.height()) <= size:
        return base
    return base.scaled(QSize(size, size), Qt.KeepAspectRatio, Qt.SmoothTransformation)


def pixmap_for_path(path: str, size: int = 32) -> QPixmap:
    before = _scaled_pixmap_cached.cache_info()
    pm = _scaled_pixmap_cached(path, size)
    if _rate.allow(f"pixmap_cache:{path}:{size}", interval_ms=1200):
        info = _scaled_pixmap_cached.cache_info()
        hit = info.hits > before.hits
        base_ready = not _raw_pixmap_cached(path).isNull()
        _log.debug("pixmap_cache_%s %s", "hit" if hit else "miss", kv(path=path, size=size, base_cached=base_ready))
    if pm.isNull() and _rate.allow(f"pixmap_null:{path}", interval_ms=1500):
        _log.warning("pixmap_null %s", kv(path=path, size=size))
    return pm


# ---- higher-level helpers ----

# Cache Path.exists() results to avoid redundant stat() syscalls.
# Games typically reference the same shortcut/archive paths across renders.
@lru_cache(maxsize=4096)
def _path_exists_cached(p: str) -> bool:
    return Path(p).exists()


def _first_existing(paths: Iterable[str]) -> Optional[str]:
    for p in paths:
        if p and _path_exists_cached(p):
            return p
    return None


@lru_cache(maxsize=2048)
def _best_icon_path_cached(shortcut: str, backup: str, archive: str, compressed: str) -> str:
    best = _first_existing([shortcut, backup, archive, compressed]) or (shortcut or backup or archive or compressed)
    return best or ""


def best_icon_path(game) -> str:
    """
    Best-effort icon path selection for a Game.
    Order:
      1) shortcut_path
      2) backup_target_path (resolved exe/file)
      3) archive_folder_path
      4) compressed_archive_path
    Returns empty string if none are present.
    """
    shortcut = getattr(game, "shortcut_path", "") or ""
    backup = getattr(game, "backup_target_path", "") or ""
    archive = getattr(game, "archive_folder_path", "") or ""
    compressed = getattr(game, "compressed_archive_path", "") or ""
    return _best_icon_path_cached(shortcut, backup, archive, compressed)


def pixmap_for_game(game, size: int = 32) -> QPixmap:
    """
    Choose and fetch the best available icon for a game, cached at high quality.
    """
    best = best_icon_path(game)
    if not best:
        return QPixmap()
    return pixmap_for_path(best, size=size)


def clear_icon_caches() -> None:
    """Allow manual invalidation (e.g., theme/icon pack changes)."""
    _icon_for_path_cached.cache_clear()
    _raw_pixmap_cached.cache_clear()
    _scaled_pixmap_cached.cache_clear()
    _path_exists_cached.cache_clear()
    _best_icon_path_cached.cache_clear()
