from __future__ import annotations
"""
Base class for file host handlers.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Type
from urllib.parse import urlparse

from app.logging_utils import get_logger

_log = get_logger("host_handlers")


class HostHandlerError(Exception):
    """Error from host handler operations."""
    pass


@dataclass
class ResolvedLink:
    """Result of resolving a download link."""
    direct_url: str
    filename: str = ""
    file_size: int = 0
    requires_auth: bool = False
    error: str = ""


@dataclass
class DownloadResult:
    """Result of a download operation."""
    success: bool
    file_path: str = ""
    file_size: int = 0
    error: str = ""


ProgressCallback = Callable[[int, int, float], None]  # bytes_done, total, speed


class HostHandler(ABC):
    """
    Abstract base class for file host handlers.

    Subclasses implement host-specific logic for:
    - Resolving page URLs to direct download URLs
    - Downloading files with progress
    - Handling authentication
    """

    # List of domains this handler supports
    SUPPORTED_DOMAINS: List[str] = []

    # Handler display name
    DISPLAY_NAME: str = "Unknown"

    # Whether this host requires authentication
    REQUIRES_AUTH: bool = False

    # Priority ranking (lower = higher priority, try first)
    # Default priorities: buzzheavier=1, gofile=2, pixeldrain=3, mega=4, etc.
    PRIORITY: int = 50

    # Whether this host has daily download limits
    HAS_DAILY_LIMIT: bool = False

    # Daily limit in GB (if HAS_DAILY_LIMIT is True)
    DAILY_LIMIT_GB: float = 0.0

    def __init__(self) -> None:
        self._authenticated = False
        self._last_error: Optional[str] = None

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Check if this handler can handle the given URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            return any(d in domain for d in cls.SUPPORTED_DOMAINS)
        except Exception:
            return False

    @abstractmethod
    def resolve_link(self, url: str) -> ResolvedLink:
        """
        Resolve a page/share URL to a direct download link.

        Args:
            url: The page or share URL

        Returns:
            ResolvedLink with direct URL and metadata
        """
        pass

    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """
        Download a file to destination.

        Default implementation uses the resolved direct URL with
        standard HTTP download. Subclasses may override for
        host-specific APIs.

        Args:
            url: URL to download (page URL or direct URL)
            destination: Directory to save file
            progress_callback: Optional callback for progress updates

        Returns:
            DownloadResult with success status and file path
        """
        import urllib.request
        import time

        try:
            # Resolve if needed
            resolved = self.resolve_link(url)
            if resolved.error:
                return DownloadResult(success=False, error=resolved.error)

            direct_url = resolved.direct_url
            filename = resolved.filename or "download"

            # Prepare request
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            req = urllib.request.Request(direct_url, headers=headers)

            destination.mkdir(parents=True, exist_ok=True)
            file_path = destination / filename

            with urllib.request.urlopen(req, timeout=60) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                bytes_downloaded = 0
                start_time = time.time()

                with open(file_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        bytes_downloaded += len(chunk)

                        if progress_callback:
                            elapsed = time.time() - start_time
                            speed = bytes_downloaded / elapsed if elapsed > 0 else 0
                            progress_callback(bytes_downloaded, total_size, speed)

            return DownloadResult(
                success=True,
                file_path=str(file_path),
                file_size=bytes_downloaded,
            )

        except Exception as e:
            _log.warning("download_error %s", str(e))
            return DownloadResult(success=False, error=str(e))

    def authenticate(self, **credentials) -> bool:
        """
        Authenticate with the host if required.

        Args:
            **credentials: Host-specific credentials

        Returns:
            True if authentication successful
        """
        return True

    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._authenticated or not self.REQUIRES_AUTH

    def check_availability(self, url: str) -> Tuple[bool, str]:
        """
        Check if a file is available without downloading it.

        Returns: (is_available, error_message)
        """
        import urllib.request
        import urllib.error

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            req = urllib.request.Request(url, method="HEAD", headers=headers)

            with urllib.request.urlopen(req, timeout=15) as response:
                return True, ""

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "File not found (404)"
            elif e.code == 403:
                return False, "Access denied (403)"
            elif e.code == 429:
                return False, "Rate limited - please try again later"
            return False, f"HTTP error: {e.code}"

        except Exception as e:
            self._last_error = str(e)
            return False, str(e)

    def get_last_error(self) -> Optional[str]:
        """Get the last error message."""
        return self._last_error

    @classmethod
    def get_priority(cls) -> int:
        """Get host priority (lower = higher priority)."""
        return cls.PRIORITY


# Registry of handlers
_HANDLERS: Dict[str, Type[HostHandler]] = {}


def register_handler(handler_class: Type[HostHandler]) -> Type[HostHandler]:
    """Decorator to register a handler class."""
    for domain in handler_class.SUPPORTED_DOMAINS:
        _HANDLERS[domain] = handler_class
    return handler_class


def get_handler_for_url(url: str) -> Optional[HostHandler]:
    """Get appropriate handler for a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")

        for handler_domain, handler_class in _HANDLERS.items():
            if handler_domain in domain:
                return handler_class()

        return None
    except Exception:
        return None


def get_handler_for_host(host_type: str) -> Optional[HostHandler]:
    """Get handler by host type name."""
    host_map = {
        "mega": "mega.nz",
        "gdrive": "drive.google.com",
        "pixeldrain": "pixeldrain.com",
        "gofile": "gofile.io",
        "mediafire": "mediafire.com",
        "direct": "direct",
    }

    domain = host_map.get(host_type)
    if domain and domain in _HANDLERS:
        return _HANDLERS[domain]()

    return None
