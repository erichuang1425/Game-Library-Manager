from __future__ import annotations
"""
Enhanced Download Service for F95zone.

Provides intelligent download management with:
- Smart host selection based on priority
- Automatic fallback on failures (404, limits, etc.)
- Daily limit tracking and management
- Redirect/confirm page handling
- Download validation and retry logic
"""

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from app.logging_utils import get_logger, kv
from app.services.download_manager import (
    DownloadManager,
    DownloadStatus,
    DownloadItem,
    get_download_manager,
)
from app.services.f95_api import (
    DownloadLink,
    get_best_download_link,
    get_fallback_links,
    mark_link_unavailable,
    HOST_PRIORITY,
)
from app.services.smart_download import (
    SmartDownloadSelector,
    HostLimitTracker,
    RedirectHandler,
    DownloadSource,
    SmartDownloadResult,
    get_smart_selector,
    get_redirect_handler,
)
from app.services.host_handlers import (
    get_handler_for_url,
    get_handler_for_host,
    HostHandler,
    ResolvedLink,
)

_log = get_logger("enhanced_download")


@dataclass
class EnhancedDownloadRequest:
    """Request for enhanced download with fallback support."""
    links: List[DownloadLink]  # All available download links
    game_id: Optional[str] = None
    game_title: str = ""
    version: str = ""
    destination: Optional[str] = None
    preferred_host: Optional[str] = None  # Force specific host
    skip_hosts: List[str] = field(default_factory=list)  # Hosts to skip
    max_retries: int = 3
    auto_fallback: bool = True  # Automatically try next host on failure


@dataclass
class EnhancedDownloadStatus:
    """Status of an enhanced download operation."""
    download_id: str
    current_host: str
    status: str  # queued, downloading, completed, failed
    progress_percent: float = 0.0
    bytes_downloaded: int = 0
    bytes_total: int = 0
    speed_bps: float = 0.0
    tried_hosts: List[str] = field(default_factory=list)
    fallback_count: int = 0
    error: str = ""
    file_path: str = ""


class EnhancedDownloadService(QObject):
    """
    Enhanced download service with smart host selection and fallback.
    """

    # Signals
    download_started = Signal(str, str)  # download_id, host_type
    progress_updated = Signal(str, int, int, float)  # id, bytes_done, bytes_total, speed
    download_completed = Signal(str, str)  # id, file_path
    download_failed = Signal(str, str)  # id, error
    fallback_triggered = Signal(str, str, str)  # id, from_host, to_host
    host_limit_reached = Signal(str, str)  # host_type, message

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self._download_manager = get_download_manager()
        self._smart_selector = get_smart_selector()
        self._redirect_handler = get_redirect_handler()

        # Track active enhanced downloads
        self._active_downloads: Dict[str, EnhancedDownloadRequest] = {}
        self._download_status: Dict[str, EnhancedDownloadStatus] = {}

        # Connect to download manager signals
        self._download_manager.download_completed.connect(self._on_download_completed)
        self._download_manager.download_failed.connect(self._on_download_failed)
        self._download_manager.progress_updated.connect(self._on_progress_updated)

    def start_download(self, request: EnhancedDownloadRequest) -> Tuple[str, str]:
        """
        Start an enhanced download with smart host selection.

        Args:
            request: Download request with all available links

        Returns:
            Tuple of (download_id, selected_host)
        """
        if not request.links:
            return "", "No download links available"

        # Get skip hosts (user-specified + hosts at limit)
        skip_hosts = list(request.skip_hosts)
        for host_type in HOST_PRIORITY.keys():
            available, reason = self._smart_selector._limit_tracker.is_host_available(host_type)
            if not available:
                if host_type not in skip_hosts:
                    skip_hosts.append(host_type)
                    _log.info("skipping_limited_host %s", kv(host=host_type, reason=reason))

        # Select best link
        if request.preferred_host:
            # Use preferred host if available
            link = next(
                (l for l in request.links if l.host_type == request.preferred_host and l.is_available),
                None
            )
            if not link:
                link = get_best_download_link(request.links, skip_hosts)
        else:
            link = get_best_download_link(request.links, skip_hosts)

        if not link:
            return "", "No available download links (all hosts may be at their daily limit)"

        # Resolve link to direct URL
        handler = get_handler_for_host(link.host_type) or get_handler_for_url(link.url)
        if not handler:
            return "", f"No handler available for {link.host_type}"

        # Check availability first
        available, error = handler.check_availability(link.url)
        if not available:
            _log.warning("link_unavailable %s", kv(host=link.host_type, error=error))
            mark_link_unavailable(request.links, link.url, error)

            if request.auto_fallback:
                # Try fallback
                return self._try_fallback(request, link.host_type, error)
            return "", error

        # Try to resolve the link
        resolved = handler.resolve_link(link.url)
        if resolved.error and not resolved.direct_url:
            _log.warning("resolve_failed %s", kv(host=link.host_type, error=resolved.error))
            mark_link_unavailable(request.links, link.url, resolved.error)

            if request.auto_fallback:
                return self._try_fallback(request, link.host_type, resolved.error)
            return "", resolved.error

        # Queue the download
        download_url = resolved.direct_url or link.url
        download_id = self._download_manager.queue_download(
            url=download_url,
            game_id=request.game_id,
            game_title=request.game_title,
            version=request.version,
            host_type=link.host_type,
            destination=request.destination,
        )

        # Track the download
        self._active_downloads[download_id] = request
        self._download_status[download_id] = EnhancedDownloadStatus(
            download_id=download_id,
            current_host=link.host_type,
            status="queued",
            tried_hosts=[link.host_type],
        )

        _log.info("enhanced_download_started %s", kv(
            id=download_id,
            host=link.host_type,
            game=request.game_title,
        ))

        self.download_started.emit(download_id, link.host_type)
        return download_id, ""

    def _try_fallback(
        self,
        request: EnhancedDownloadRequest,
        failed_host: str,
        error: str
    ) -> Tuple[str, str]:
        """
        Try downloading from an alternative host.

        Returns:
            Tuple of (download_id, error)
        """
        # Get alternative links
        alternatives = get_fallback_links(request.links, failed_host)

        if not alternatives:
            return "", f"Download failed from {failed_host}: {error}. No alternative hosts available."

        # Add failed host to skip list
        new_request = EnhancedDownloadRequest(
            links=alternatives,
            game_id=request.game_id,
            game_title=request.game_title,
            version=request.version,
            destination=request.destination,
            skip_hosts=request.skip_hosts + [failed_host],
            max_retries=request.max_retries - 1,
            auto_fallback=request.auto_fallback and request.max_retries > 1,
        )

        _log.info("trying_fallback %s", kv(
            from_host=failed_host,
            to_host=alternatives[0].host_type if alternatives else "none",
            remaining=len(alternatives),
        ))

        return self.start_download(new_request)

    def _on_download_completed(self, download_id: str, file_path: str) -> None:
        """Handle successful download completion."""
        if download_id not in self._active_downloads:
            return

        request = self._active_downloads[download_id]
        status = self._download_status.get(download_id)

        if status:
            status.status = "completed"
            status.file_path = file_path
            status.progress_percent = 100.0

            # Record success with limit tracker
            item = self._download_manager.get_item(download_id)
            if item:
                self._smart_selector.record_success(
                    status.current_host,
                    item.progress.bytes_downloaded
                )

        _log.info("enhanced_download_completed %s", kv(
            id=download_id,
            host=status.current_host if status else "unknown",
            path=file_path,
        ))

        self.download_completed.emit(download_id, file_path)

        # Cleanup
        del self._active_downloads[download_id]

    def _on_download_failed(self, download_id: str, error: str) -> None:
        """Handle download failure with automatic fallback."""
        if download_id not in self._active_downloads:
            # Not an enhanced download, just propagate
            self.download_failed.emit(download_id, error)
            return

        request = self._active_downloads[download_id]
        status = self._download_status.get(download_id)
        current_host = status.current_host if status else "unknown"

        _log.warning("enhanced_download_failed %s", kv(
            id=download_id,
            host=current_host,
            error=error,
        ))

        # Record failure
        self._smart_selector.record_failure(current_host, error)

        # Check if this is a limit error
        if any(pattern in error.lower() for pattern in [
            "limit", "quota", "rate", "bandwidth"
        ]):
            self.host_limit_reached.emit(current_host, error)

        # Check if auto-fallback is enabled and we have retries left
        if request.auto_fallback and request.max_retries > 0:
            # Mark the link as unavailable
            for link in request.links:
                if link.host_type == current_host:
                    mark_link_unavailable(request.links, link.url, error)
                    break

            # Try fallback
            new_id, fallback_error = self._try_fallback(request, current_host, error)

            if new_id:
                if status:
                    status.fallback_count += 1
                self.fallback_triggered.emit(download_id, current_host,
                    self._download_status.get(new_id, EnhancedDownloadStatus(
                        download_id=new_id, current_host="unknown", status="queued"
                    )).current_host)
                # Cleanup old download
                del self._active_downloads[download_id]
                return
            else:
                error = fallback_error

        # No fallback available or disabled
        if status:
            status.status = "failed"
            status.error = error

        self.download_failed.emit(download_id, error)

        # Cleanup
        if download_id in self._active_downloads:
            del self._active_downloads[download_id]

    def _on_progress_updated(self, download_id: str, bytes_done: int, bytes_total: int, speed: float) -> None:
        """Handle progress update."""
        if download_id in self._download_status:
            status = self._download_status[download_id]
            status.bytes_downloaded = bytes_done
            status.bytes_total = bytes_total
            status.speed_bps = speed
            status.progress_percent = (bytes_done / bytes_total * 100) if bytes_total > 0 else 0
            status.status = "downloading"

        self.progress_updated.emit(download_id, bytes_done, bytes_total, speed)

    def get_status(self, download_id: str) -> Optional[EnhancedDownloadStatus]:
        """Get status of an enhanced download."""
        return self._download_status.get(download_id)

    def get_host_availability(self) -> Dict[str, Tuple[bool, str]]:
        """
        Get availability status for all hosts.

        Returns:
            Dict mapping host_type to (is_available, reason)
        """
        result = {}
        for host_type in HOST_PRIORITY.keys():
            available, reason = self._smart_selector._limit_tracker.is_host_available(host_type)
            result[host_type] = (available, reason)
        return result

    def get_host_remaining_quota(self, host_type: str) -> Optional[float]:
        """Get remaining download quota for a host (GB), or None if unlimited."""
        return self._smart_selector._limit_tracker.get_remaining_quota(host_type)

    def reset_host_limit(self, host_type: str) -> None:
        """Manually reset a host's daily limit tracking."""
        self._smart_selector._limit_tracker.reset_host(host_type)
        _log.info("host_limit_reset %s", kv(host=host_type))

    def cancel_download(self, download_id: str) -> bool:
        """Cancel an enhanced download."""
        if download_id in self._active_downloads:
            del self._active_downloads[download_id]
        if download_id in self._download_status:
            self._download_status[download_id].status = "cancelled"
        return self._download_manager.cancel(download_id)

    def validate_links(self, links: List[DownloadLink]) -> List[DownloadLink]:
        """
        Validate download links and update their availability status.

        Args:
            links: List of download links to validate

        Returns:
            The same list with is_available and error fields updated
        """
        for link in links:
            handler = get_handler_for_host(link.host_type) or get_handler_for_url(link.url)
            if handler:
                available, error = handler.check_availability(link.url)
                link.is_available = available
                link.error = error
                if not available:
                    _log.info("link_validation_failed %s", kv(
                        host=link.host_type,
                        error=error,
                    ))

        return links


# Global instance
_enhanced_service: Optional[EnhancedDownloadService] = None


def get_enhanced_download_service() -> EnhancedDownloadService:
    """Get the global enhanced download service."""
    global _enhanced_service
    if _enhanced_service is None:
        _enhanced_service = EnhancedDownloadService()
    return _enhanced_service


def quick_download(
    links: List[DownloadLink],
    game_title: str = "",
    game_id: Optional[str] = None,
    version: str = "",
    destination: Optional[str] = None,
    preferred_host: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Quick helper to start a download with smart host selection.

    Args:
        links: Available download links
        game_title: Game title
        game_id: Game ID
        version: Version being downloaded
        destination: Download destination
        preferred_host: Preferred host to use

    Returns:
        Tuple of (download_id, error)
    """
    service = get_enhanced_download_service()

    request = EnhancedDownloadRequest(
        links=links,
        game_id=game_id,
        game_title=game_title,
        version=version,
        destination=destination,
        preferred_host=preferred_host,
        auto_fallback=True,
    )

    return service.start_download(request)
