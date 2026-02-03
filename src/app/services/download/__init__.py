"""Download manager package - modular download handling.

This package splits download_manager.py (687 lines) into focused modules:
- models.py: Data classes, enums, format utilities (~100 lines)
- worker.py: DownloadWorker thread (~230 lines)
- manager.py: DownloadManager with queue and history (~320 lines)

Total: ~650 lines with improved organization
"""

from .models import (
    DownloadStatus,
    DownloadProgress,
    DownloadItem,
    DownloadHistory,
    format_size,
    format_speed,
    format_eta,
)

from .worker import DownloadWorker

from .manager import (
    DownloadManager,
    get_download_manager,
)

__all__ = [
    # Models
    "DownloadStatus",
    "DownloadProgress",
    "DownloadItem",
    "DownloadHistory",
    # Utilities
    "format_size",
    "format_speed",
    "format_eta",
    # Worker
    "DownloadWorker",
    # Manager
    "DownloadManager",
    "get_download_manager",
]
