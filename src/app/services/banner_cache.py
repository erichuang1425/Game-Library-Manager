"""Banner image caching service.

Fetches banner images from URLs (typically F95zone thread images),
caches them to disk, and provides QPixmap retrieval with graceful fallback.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QThread, Signal, QObject
from PySide6.QtGui import QPixmap, QImage

from app.logging_utils import get_logger, kv, RateLimiter
from app.services.http_utils import fetch_url, BoundedCache, DEFAULT_TIMEOUT
from app.storage.paths import get_app_dir

_log = get_logger("banner_cache")
_rate = RateLimiter()

# In-memory pixmap cache keyed by URL hash
_pixmap_cache: BoundedCache[str, QPixmap] = BoundedCache(max_size=100, ttl=3600 * 6)


def _banner_cache_dir() -> Path:
    """Return the banner image cache directory, creating it if needed."""
    d = get_app_dir() / "banner_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _url_hash(url: str) -> str:
    """Create a stable filename-safe hash from a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def _cache_path_for_url(url: str) -> Path:
    """Return the on-disk cache path for a banner URL."""
    return _banner_cache_dir() / f"{_url_hash(url)}.img"


def get_cached_banner(url: str) -> Optional[QPixmap]:
    """Retrieve a cached banner pixmap (memory first, then disk).

    Returns None if not cached or if the cached image is corrupt.
    """
    if not url:
        return None

    h = _url_hash(url)

    # 1. Check in-memory cache
    pm = _pixmap_cache.get(h)
    if pm is not None and not pm.isNull():
        return pm

    # 2. Check on-disk cache
    disk_path = _cache_path_for_url(url)
    if disk_path.exists():
        pm = QPixmap()
        if pm.load(str(disk_path)):
            if not pm.isNull():
                _pixmap_cache.set(h, pm)
                if _rate.allow("banner_disk_hit", 2000):
                    _log.debug("banner_disk_cache_hit %s", kv(url=url[:60]))
                return pm
        # Corrupt file - remove it
        try:
            disk_path.unlink()
        except OSError:
            pass

    return None


def store_banner(url: str, data: bytes) -> Optional[QPixmap]:
    """Store fetched image data to disk and memory cache.

    Returns the QPixmap on success, or None if the data is not valid image.
    """
    if not url or not data:
        return None

    h = _url_hash(url)
    disk_path = _cache_path_for_url(url)

    # Write raw bytes to disk
    try:
        disk_path.write_bytes(data)
    except OSError as e:
        _log.warning("banner_cache_write_error %s", kv(url=url[:60], err=str(e)))
        return None

    # Load into QPixmap
    pm = QPixmap()
    if pm.load(str(disk_path)):
        if not pm.isNull():
            _pixmap_cache.set(h, pm)
            _log.info("banner_cached %s", kv(
                url=url[:60], size=f"{pm.width()}x{pm.height()}", bytes=len(data)
            ))
            return pm

    # Data wasn't a valid image - clean up
    try:
        disk_path.unlink()
    except OSError:
        pass
    return None


def fetch_and_cache_banner(url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[QPixmap]:
    """Fetch a banner image from URL, cache it, and return the QPixmap.

    Returns None on any failure (network error, invalid image, etc.).
    The caller should fall back to a gradient banner on None.
    """
    if not url:
        return None

    # Check cache first
    cached = get_cached_banner(url)
    if cached is not None:
        return cached

    # Fetch from network
    try:
        data = fetch_url(url, timeout=timeout)
        if data:
            return store_banner(url, data)
    except Exception as e:
        if _rate.allow("banner_fetch_error", 5000):
            _log.warning("banner_fetch_error %s", kv(url=url[:80], err=str(e)))

    return None


def scaled_banner(pixmap: QPixmap, width: int, height: int) -> QPixmap:
    """Scale a banner pixmap to fit the given dimensions while maintaining aspect ratio.

    Uses crop-to-fill strategy for a cinematic look - scales to cover the
    entire area and crops the excess.
    """
    if pixmap.isNull():
        return pixmap

    target = QSize(width, height)
    # Scale to cover (not fit) for cinematic crop effect
    src_ratio = pixmap.width() / max(pixmap.height(), 1)
    tgt_ratio = width / max(height, 1)

    if src_ratio > tgt_ratio:
        # Source is wider - scale by height, crop width
        scaled_h = height
        scaled_w = int(pixmap.width() * height / max(pixmap.height(), 1))
    else:
        # Source is taller - scale by width, crop height
        scaled_w = width
        scaled_h = int(pixmap.height() * width / max(pixmap.width(), 1))

    scaled = pixmap.scaled(
        QSize(scaled_w, scaled_h), Qt.KeepAspectRatio, Qt.SmoothTransformation
    )

    # Crop to target from center
    if scaled.width() > width or scaled.height() > height:
        x = max(0, (scaled.width() - width) // 2)
        y = max(0, (scaled.height() - height) // 2)
        return scaled.copy(x, y, min(width, scaled.width()), min(height, scaled.height()))

    return scaled


class BannerFetchWorker(QObject):
    """Worker that fetches a banner image in a background thread."""
    finished = Signal(str, object)  # game_id, QPixmap or None

    def __init__(self, game_id: str, url: str, parent=None):
        super().__init__(parent)
        self._game_id = game_id
        self._url = url

    def run(self):
        """Fetch the banner (runs in worker thread)."""
        pm = fetch_and_cache_banner(self._url)
        self.finished.emit(self._game_id, pm)


def clear_banner_cache() -> None:
    """Clear both in-memory and on-disk banner caches."""
    _pixmap_cache.clear()
    cache_dir = _banner_cache_dir()
    if cache_dir.exists():
        for f in cache_dir.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
    _log.info("banner_cache_cleared")
