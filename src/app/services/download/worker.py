"""Download worker thread."""
from __future__ import annotations
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote

from PySide6.QtCore import QObject, Signal, QThread, QMutex, QMutexLocker

from app.logging_utils import get_logger, kv

from .models import DownloadItem, DownloadProgress, DownloadStatus

_log = get_logger("download.worker")


class DownloadWorker(QThread):
    """Worker thread for downloading files."""

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
                    match = re.search(r'filename[*]?=["\']?([^"\';\n]+)', content_disp)
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

                        # Handle pause state outside the lock to avoid deadlock risk
                        while True:
                            with QMutexLocker(self._mutex):
                                if self._cancelled:
                                    item.status = DownloadStatus.CANCELLED
                                    self.status_changed.emit(item.download_id, "cancelled")
                                    return
                                if not self._paused:
                                    break
                            # Sleep OUTSIDE the lock - safe for pause/resume
                            time.sleep(0.1)

                        # Resumed from pause - update timing
                        with QMutexLocker(self._mutex):
                            if item.status == DownloadStatus.PAUSED:
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
