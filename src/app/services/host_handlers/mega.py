from __future__ import annotations
"""
MEGA.nz host handler.

MEGA uses client-side encryption and requires special handling.
This handler provides basic support - for full functionality,
the mega.py library should be used.
"""

import re
import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

from .base import HostHandler, ResolvedLink, DownloadResult, ProgressCallback, register_handler
from app.logging_utils import get_logger

_log = get_logger("mega_handler")


@register_handler
class MegaHandler(HostHandler):
    """
    Handler for MEGA.nz downloads.

    MEGA uses client-side encryption, so we need to:
    1. Extract file ID and key from URL
    2. Use MEGA API to get file info
    3. Download and decrypt

    For simplicity, this handler tries to use the mega.py library
    if available, otherwise provides basic URL parsing.

    Note: MEGA has transfer quota limits (~5GB every 6 hours for free users).
    """

    SUPPORTED_DOMAINS = ["mega.nz", "mega.co.nz"]
    DISPLAY_NAME = "MEGA"
    REQUIRES_AUTH = False  # Public links don't need auth
    PRIORITY = 4  # Has limits and requires special library
    HAS_DAILY_LIMIT = True
    DAILY_LIMIT_GB = 5.0

    # Error patterns indicating quota/limit
    LIMIT_ERROR_PATTERNS = [
        "transfer quota",
        "bandwidth limit",
        "over quota",
        "temporarily unavailable",
        "too many connections",
    ]

    def __init__(self) -> None:
        super().__init__()
        self._mega_client = None

        # Try to import mega library
        try:
            from mega import Mega
            self._mega_client = Mega()
            _log.info("mega_library_available")
        except ImportError:
            _log.info("mega_library_not_available")

    def _parse_mega_url(self, url: str) -> tuple[str, str, str]:
        """
        Parse MEGA URL to extract file ID and key.

        MEGA URLs have formats:
        - https://mega.nz/file/FILEID#KEY
        - https://mega.nz/#!FILEID!KEY (old format)
        - https://mega.nz/folder/FOLDERID#KEY

        Returns: (file_id, key, url_type)
        """
        file_id = ""
        key = ""
        url_type = "file"

        try:
            # New format: /file/ID#KEY or /folder/ID#KEY
            match = re.search(r"/(?:file|folder)/([^#/]+)(?:#(.+))?", url)
            if match:
                file_id = match.group(1)
                key = match.group(2) or ""
                url_type = "folder" if "/folder/" in url else "file"
                return file_id, key, url_type

            # Old format: #!ID!KEY
            match = re.search(r"#!([^!]+)!(.+)", url)
            if match:
                file_id = match.group(1)
                key = match.group(2)
                return file_id, key, "file"

            # Just fragment: #ID
            parsed = urlparse(url)
            if parsed.fragment:
                parts = parsed.fragment.split("!")
                if len(parts) >= 2:
                    file_id = parts[0].lstrip("!")
                    key = parts[1]

        except Exception as e:
            _log.warning("mega_url_parse_error %s", str(e))

        return file_id, key, url_type

    def resolve_link(self, url: str) -> ResolvedLink:
        """
        Resolve MEGA URL to get file info.

        Note: MEGA doesn't provide direct download URLs in the traditional sense.
        The download must be handled through the MEGA API with decryption.
        """
        file_id, key, url_type = self._parse_mega_url(url)

        if not file_id:
            return ResolvedLink(
                direct_url="",
                error="Could not parse MEGA URL"
            )

        # If we have the mega library, try to get file info
        if self._mega_client:
            try:
                # For public files, we can get info without login
                # This is a simplified version - full implementation would
                # use the MEGA API properly
                return ResolvedLink(
                    direct_url=url,  # MEGA URLs need special handling
                    filename=f"mega_file_{file_id}",  # Actual name from API
                    requires_auth=False,
                )
            except Exception as e:
                _log.warning("mega_info_error %s", str(e))

        # Without the library, we can only return the URL for manual download
        return ResolvedLink(
            direct_url=url,
            filename=f"mega_download_{file_id}",
            error="MEGA downloads require the mega.py library for full support. "
                  "Install with: pip install mega.py"
        )

    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """
        Download from MEGA using the mega.py library.
        """
        if not self._mega_client:
            return DownloadResult(
                success=False,
                error="MEGA downloads require the mega.py library. "
                      "Install with: pip install mega.py"
            )

        try:
            from mega import Mega
            mega = Mega()

            destination.mkdir(parents=True, exist_ok=True)

            # Download file
            # Note: mega.py doesn't have built-in progress callback
            # A full implementation would wrap this
            file_path = mega.download_url(url, dest_path=str(destination))

            if file_path:
                return DownloadResult(
                    success=True,
                    file_path=str(file_path),
                    file_size=Path(file_path).stat().st_size if Path(file_path).exists() else 0,
                )
            else:
                return DownloadResult(
                    success=False,
                    error="Download returned no file path"
                )

        except Exception as e:
            _log.warning("mega_download_error %s", str(e))
            return DownloadResult(success=False, error=str(e))
