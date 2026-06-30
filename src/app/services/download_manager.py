"""Compatibility exports for the download manager module."""

from app.services.download.manager import DownloadManager, get_download_manager
from app.services.download.models import (
    DownloadHistory,
    DownloadItem,
    DownloadProgress,
    DownloadStatus,
    format_eta,
    format_size,
    format_speed,
)

__all__ = [
    "DownloadHistory",
    "DownloadItem",
    "DownloadManager",
    "DownloadProgress",
    "DownloadStatus",
    "format_eta",
    "format_size",
    "format_speed",
    "get_download_manager",
]
