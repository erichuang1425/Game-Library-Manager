"""Download models and data types."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


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
