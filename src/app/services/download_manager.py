from __future__ import annotations
"""
Download Manager for Game Library Manager.

Provides:
- Download queue with priority
- Progress tracking with speed/ETA calculation
- Pause/resume support
- Concurrent downloads (configurable)
- Download history persistence
"""

import os
import time
import uuid
import json
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import PriorityQueue
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, unquote
import urllib.request
import urllib.error

from PySide6.QtCore import QObject, Signal, QThread, QMutex, QMutexLocker

from app.logging_utils import get_logger, kv, RateLimiter
from app.storage.paths import get_app_dir

_log = get_logger("download_manager")
_rate = RateLimiter()


class DownloadStatus(Enum):
    """Status of a download."""
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadProgress:
    """Progress information for a download."""
    bytes_downloaded: int = 0
    bytes_total: int = 0
    speed_bps: float = 0.0  # bytes per second
    eta_seconds: float = 0.0
    percent: float = 0.0
    elapsed_seconds: float = 0.0


@dataclass
class DownloadItem:
    """A download task in the queue."""
    download_id: str
    url: str
    destination: str
    game_id: Optional[str] = None
    game_title: str = ""
    version: str = ""
    host_type: str = ""
    priority: int = 0  # Lower = higher priority
    status: DownloadStatus = DownloadStatus.QUEUED
    progress: DownloadProgress = field(default_factory=DownloadProgress)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: str = ""
    final_path: str = ""
    file_name: str = ""

    def __lt__(self, other: "DownloadItem") -> bool:
        """For priority queue ordering."""
        return self.priority < other.priority


@dataclass
class DownloadHistory:
    """Historical download record."""
    download_id: str
    url: str
    game_id: Optional[str]
    game_title: str
    version: str
    file_path: str
    file_size: int
    status: str
    started_at: str
    completed_at: str
    duration_seconds: float


class DownloadWorker(QThread):
    """
    Worker thread for downloading files.
    """

    progress_updated = Signal(str, int, int, float)  # id, bytes_done, bytes_total, speed
    download_completed = Signal(str, str)  # id, file_path
    download_failed = Signal(str, str)  # id, error_message
    status_changed = Signal(str, str)  # id, status

    def __init__(
        self,
        item: DownloadItem,
        chunk_size: int = 8192,
        parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self.item = item
        self.chunk_size = chunk_size
        self._paused = False
        self._cancelled = False
        self._mutex = QMutex()

    def run(self) -> None:
        """Execute the download."""
        item = self.item
        item.status = DownloadStatus.DOWNLOADING
        item.started_at = datetime.now()
        self.status_changed.emit(item.download_id, "downloading")

        try:
            _log.info("download_start %s", kv(
                id=item.download_id,
                url=item.url[:100],
                dest=item.destination
            ))

            # Prepare request
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "*/*",
            }

            req = urllib.request.Request(item.url, headers=headers)

            # Resume support - check if partial file exists
            dest_path = Path(item.destination)
            temp_path = dest_path.with_suffix(dest_path.suffix + ".part")
            resume_pos = 0

            if temp_path.exists():
                resume_pos = temp_path.stat().st_size
                if resume_pos > 0:
                    headers["Range"] = f"bytes={resume_pos}-"
                    req = urllib.request.Request(item.url, headers=headers)
                    _log.info("download_resume %s", kv(id=item.download_id, pos=resume_pos))

            # Open connection
            with urllib.request.urlopen(req, timeout=60) as response:
                # Get file size
                content_length = response.headers.get("Content-Length")
                if content_length:
                    total_size = int(content_length) + resume_pos
                else:
                    total_size = 0

                item.progress.bytes_total = total_size

                # Get filename from Content-Disposition if available
                content_disp = response.headers.get("Content-Disposition", "")
                if "filename=" in content_disp:
                    match = __import__("re").search(r'filename[*]?=["\']?([^"\';\n]+)', content_disp)
                    if match:
                        item.file_name = unquote(match.group(1).strip())

                if not item.file_name:
                    # Derive from URL
                    item.file_name = unquote(Path(urlparse(item.url).path).name) or "download"

                # Ensure destination directory exists
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Download with progress
                bytes_downloaded = resume_pos
                start_time = time.time()
                last_progress_time = start_time
                last_bytes = resume_pos

                mode = "ab" if resume_pos > 0 else "wb"
                with open(temp_path, mode) as f:
                    while True:
                        # Check for pause/cancel
                        with QMutexLocker(self._mutex):
                            if self._cancelled:
                                item.status = DownloadStatus.CANCELLED
                                self.status_changed.emit(item.download_id, "cancelled")
                                return

                            if self._paused:
                                item.status = DownloadStatus.PAUSED
                                self.status_changed.emit(item.download_id, "paused")
                                # Wait for unpause or cancel
                                while self._paused and not self._cancelled:
                                    self._mutex.unlock()
                                    time.sleep(0.1)
                                    self._mutex.lock()
                                if self._cancelled:
                                    item.status = DownloadStatus.CANCELLED
                                    self.status_changed.emit(item.download_id, "cancelled")
                                    return
                                item.status = DownloadStatus.DOWNLOADING
                                self.status_changed.emit(item.download_id, "downloading")
                                start_time = time.time()
                                last_progress_time = start_time
                                last_bytes = bytes_downloaded

                        # Read chunk
                        chunk = response.read(self.chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        bytes_downloaded += len(chunk)

                        # Calculate speed and ETA
                        now = time.time()
                        elapsed = now - start_time
                        progress_elapsed = now - last_progress_time

                        if progress_elapsed >= 0.5:  # Update every 0.5 seconds
                            bytes_since_last = bytes_downloaded - last_bytes
                            speed = bytes_since_last / progress_elapsed if progress_elapsed > 0 else 0

                            if total_size > 0 and speed > 0:
                                remaining = total_size - bytes_downloaded
                                eta = remaining / speed
                            else:
                                eta = 0

                            percent = (bytes_downloaded / total_size * 100) if total_size > 0 else 0

                            item.progress = DownloadProgress(
                                bytes_downloaded=bytes_downloaded,
                                bytes_total=total_size,
                                speed_bps=speed,
                                eta_seconds=eta,
                                percent=percent,
                                elapsed_seconds=elapsed,
                            )

                            self.progress_updated.emit(
                                item.download_id,
                                bytes_downloaded,
                                total_size,
                                speed
                            )

                            last_progress_time = now
                            last_bytes = bytes_downloaded

                # Rename temp file to final destination
                final_path = dest_path.parent / item.file_name
                if final_path.exists():
                    # Add timestamp to avoid overwrite
                    stem = final_path.stem
                    suffix = final_path.suffix
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    final_path = final_path.parent / f"{stem}_{timestamp}{suffix}"

                temp_path.rename(final_path)
                item.final_path = str(final_path)
                item.status = DownloadStatus.COMPLETED
                item.completed_at = datetime.now()
                item.progress.bytes_downloaded = bytes_downloaded
                item.progress.percent = 100.0

                _log.info("download_complete %s", kv(
                    id=item.download_id,
                    path=str(final_path),
                    size=bytes_downloaded,
                    duration=round(time.time() - start_time, 1)
                ))

                self.download_completed.emit(item.download_id, str(final_path))

        except Exception as e:
            item.status = DownloadStatus.FAILED
            item.error_message = str(e)
            _log.warning("download_failed %s", kv(id=item.download_id, err=str(e)))
            self.download_failed.emit(item.download_id, str(e))

    def pause(self) -> None:
        """Pause the download."""
        with QMutexLocker(self._mutex):
            self._paused = True

    def resume(self) -> None:
        """Resume the download."""
        with QMutexLocker(self._mutex):
            self._paused = False

    def cancel(self) -> None:
        """Cancel the download."""
        with QMutexLocker(self._mutex):
            self._cancelled = True
            self._paused = False  # Unpause to allow thread to exit


class DownloadManager(QObject):
    """
    Central download management with queue, progress, and history.
    """

    # Signals
    download_queued = Signal(str)  # download_id
    download_started = Signal(str)  # download_id
    progress_updated = Signal(str, int, int, float)  # id, bytes_done, bytes_total, speed
    download_completed = Signal(str, str)  # id, file_path
    download_failed = Signal(str, str)  # id, error
    download_cancelled = Signal(str)  # download_id
    queue_changed = Signal()  # Emitted when queue state changes

    def __init__(
        self,
        max_concurrent: int = 2,
        default_download_dir: Optional[str] = None,
        parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)

        self.max_concurrent = max_concurrent
        self.default_download_dir = default_download_dir or str(
            Path.home() / "Downloads" / "GameLibraryManager"
        )

        self._queue: Dict[str, DownloadItem] = {}
        self._active_workers: Dict[str, DownloadWorker] = {}
        self._history: List[DownloadHistory] = []
        self._mutex = QMutex()

        self._history_path = get_app_dir() / "download_history.json"
        self._load_history()

    def _load_history(self) -> None:
        """Load download history from disk."""
        try:
            if self._history_path.exists():
                data = json.loads(self._history_path.read_text(encoding="utf-8"))
                for item in data.get("history", [])[-100:]:  # Keep last 100
                    self._history.append(DownloadHistory(**item))
        except Exception as e:
            _log.warning("history_load_error %s", kv(err=str(e)))

    def _save_history(self) -> None:
        """Save download history to disk."""
        try:
            data = {"history": [asdict(h) for h in self._history[-100:]]}
            self._history_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            _log.warning("history_save_error %s", kv(err=str(e)))

    def _add_to_history(self, item: DownloadItem) -> None:
        """Add completed download to history."""
        history = DownloadHistory(
            download_id=item.download_id,
            url=item.url,
            game_id=item.game_id,
            game_title=item.game_title,
            version=item.version,
            file_path=item.final_path,
            file_size=item.progress.bytes_downloaded,
            status=item.status.value,
            started_at=item.started_at.isoformat() if item.started_at else "",
            completed_at=item.completed_at.isoformat() if item.completed_at else "",
            duration_seconds=item.progress.elapsed_seconds,
        )
        self._history.append(history)
        self._save_history()

    def queue_download(
        self,
        url: str,
        game_id: Optional[str] = None,
        game_title: str = "",
        version: str = "",
        host_type: str = "",
        destination: Optional[str] = None,
        priority: int = 0,
    ) -> str:
        """
        Add a download to the queue.

        Args:
            url: URL to download
            game_id: Associated game ID
            game_title: Game title for display
            version: Version being downloaded
            host_type: Type of host (mega, gdrive, etc.)
            destination: Download destination directory
            priority: Priority (lower = higher priority)

        Returns:
            Download ID
        """
        download_id = str(uuid.uuid4())[:8]

        if not destination:
            destination = self.default_download_dir

        dest_path = Path(destination)
        dest_path.mkdir(parents=True, exist_ok=True)

        item = DownloadItem(
            download_id=download_id,
            url=url,
            destination=str(dest_path / "download"),  # Will be renamed
            game_id=game_id,
            game_title=game_title,
            version=version,
            host_type=host_type,
            priority=priority,
        )

        with QMutexLocker(self._mutex):
            self._queue[download_id] = item

        _log.info("download_queued %s", kv(
            id=download_id,
            url=url[:100],
            game=game_title,
            priority=priority
        ))

        self.download_queued.emit(download_id)
        self.queue_changed.emit()

        # Try to start download if slots available
        self._process_queue()

        return download_id

    def _process_queue(self) -> None:
        """Process queued downloads if slots available."""
        with QMutexLocker(self._mutex):
            if len(self._active_workers) >= self.max_concurrent:
                return

            # Find highest priority queued item
            queued = [
                item for item in self._queue.values()
                if item.status == DownloadStatus.QUEUED
            ]
            if not queued:
                return

            queued.sort(key=lambda x: (x.priority, x.created_at))
            item = queued[0]

            # Start download
            self._start_download(item)

    def _start_download(self, item: DownloadItem) -> None:
        """Start a download worker for an item."""
        worker = DownloadWorker(item)

        # Connect signals
        worker.progress_updated.connect(self._on_progress)
        worker.download_completed.connect(self._on_completed)
        worker.download_failed.connect(self._on_failed)
        worker.status_changed.connect(self._on_status_changed)
        worker.finished.connect(lambda: self._on_worker_finished(item.download_id))

        self._active_workers[item.download_id] = worker
        worker.start()

        self.download_started.emit(item.download_id)
        _log.info("download_started %s", kv(id=item.download_id))

    def _on_progress(self, download_id: str, bytes_done: int, bytes_total: int, speed: float) -> None:
        """Handle progress update from worker."""
        self.progress_updated.emit(download_id, bytes_done, bytes_total, speed)

    def _on_completed(self, download_id: str, file_path: str) -> None:
        """Handle download completion."""
        with QMutexLocker(self._mutex):
            if download_id in self._queue:
                item = self._queue[download_id]
                self._add_to_history(item)

        self.download_completed.emit(download_id, file_path)
        self.queue_changed.emit()

    def _on_failed(self, download_id: str, error: str) -> None:
        """Handle download failure."""
        self.download_failed.emit(download_id, error)
        self.queue_changed.emit()

    def _on_status_changed(self, download_id: str, status: str) -> None:
        """Handle status change."""
        self.queue_changed.emit()

    def _on_worker_finished(self, download_id: str) -> None:
        """Handle worker thread completion."""
        with QMutexLocker(self._mutex):
            if download_id in self._active_workers:
                del self._active_workers[download_id]

        # Process queue to start next download
        self._process_queue()

    def pause(self, download_id: str) -> bool:
        """Pause a download."""
        with QMutexLocker(self._mutex):
            if download_id in self._active_workers:
                self._active_workers[download_id].pause()
                _log.info("download_paused %s", kv(id=download_id))
                return True
        return False

    def resume(self, download_id: str) -> bool:
        """Resume a paused download."""
        with QMutexLocker(self._mutex):
            if download_id in self._active_workers:
                self._active_workers[download_id].resume()
                _log.info("download_resumed %s", kv(id=download_id))
                return True

            # If not active, try to restart from queue
            if download_id in self._queue:
                item = self._queue[download_id]
                if item.status == DownloadStatus.PAUSED:
                    item.status = DownloadStatus.QUEUED
                    self._process_queue()
                    return True
        return False

    def cancel(self, download_id: str) -> bool:
        """Cancel a download."""
        with QMutexLocker(self._mutex):
            if download_id in self._active_workers:
                self._active_workers[download_id].cancel()
                _log.info("download_cancelled %s", kv(id=download_id))
                self.download_cancelled.emit(download_id)
                return True

            if download_id in self._queue:
                self._queue[download_id].status = DownloadStatus.CANCELLED
                _log.info("download_cancelled %s", kv(id=download_id))
                self.download_cancelled.emit(download_id)
                self.queue_changed.emit()
                return True
        return False

    def remove_from_queue(self, download_id: str) -> bool:
        """Remove a download from the queue (if not active)."""
        with QMutexLocker(self._mutex):
            if download_id in self._queue:
                item = self._queue[download_id]
                if item.status in (DownloadStatus.QUEUED, DownloadStatus.CANCELLED, DownloadStatus.FAILED):
                    del self._queue[download_id]
                    self.queue_changed.emit()
                    return True
        return False

    def get_item(self, download_id: str) -> Optional[DownloadItem]:
        """Get a download item by ID."""
        with QMutexLocker(self._mutex):
            return self._queue.get(download_id)

    def get_all_items(self) -> List[DownloadItem]:
        """Get all items in queue."""
        with QMutexLocker(self._mutex):
            return list(self._queue.values())

    def get_active_downloads(self) -> List[DownloadItem]:
        """Get currently downloading items."""
        with QMutexLocker(self._mutex):
            return [
                item for item in self._queue.values()
                if item.status == DownloadStatus.DOWNLOADING
            ]

    def get_queued_downloads(self) -> List[DownloadItem]:
        """Get queued (waiting) items."""
        with QMutexLocker(self._mutex):
            items = [
                item for item in self._queue.values()
                if item.status == DownloadStatus.QUEUED
            ]
            items.sort(key=lambda x: (x.priority, x.created_at))
            return items

    def get_completed_downloads(self) -> List[DownloadItem]:
        """Get completed items."""
        with QMutexLocker(self._mutex):
            return [
                item for item in self._queue.values()
                if item.status == DownloadStatus.COMPLETED
            ]

    def get_history(self) -> List[DownloadHistory]:
        """Get download history."""
        return list(self._history)

    def clear_completed(self) -> int:
        """Remove completed downloads from queue. Returns count removed."""
        with QMutexLocker(self._mutex):
            to_remove = [
                did for did, item in self._queue.items()
                if item.status in (DownloadStatus.COMPLETED, DownloadStatus.CANCELLED, DownloadStatus.FAILED)
            ]
            for did in to_remove:
                del self._queue[did]
            if to_remove:
                self.queue_changed.emit()
            return len(to_remove)

    def set_max_concurrent(self, max_concurrent: int) -> None:
        """Set maximum concurrent downloads."""
        self.max_concurrent = max(1, max_concurrent)
        self._process_queue()

    def cancel_all(self) -> None:
        """Cancel all downloads."""
        with QMutexLocker(self._mutex):
            for download_id in list(self._active_workers.keys()):
                self._active_workers[download_id].cancel()
            for item in self._queue.values():
                if item.status == DownloadStatus.QUEUED:
                    item.status = DownloadStatus.CANCELLED
        self.queue_changed.emit()


# Global instance
_download_manager: Optional[DownloadManager] = None


def get_download_manager() -> DownloadManager:
    """Get the global download manager instance."""
    global _download_manager
    if _download_manager is None:
        _download_manager = DownloadManager()
    return _download_manager


def format_size(bytes_val: int) -> str:
    """Format bytes as human-readable size."""
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"


def format_speed(bps: float) -> str:
    """Format speed as human-readable."""
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    else:
        return f"{bps / (1024 * 1024):.1f} MB/s"


def format_eta(seconds: float) -> str:
    """Format ETA as human-readable."""
    if seconds <= 0:
        return "--:--"
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds / 3600)
        mins = int((seconds % 3600) / 60)
        return f"{hours}h {mins}m"
