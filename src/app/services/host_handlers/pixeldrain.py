from __future__ import annotations
"""
Pixeldrain host handler.

Pixeldrain provides a simple API for downloads.
"""

import re
import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import urllib.request
import urllib.error

from .base import HostHandler, ResolvedLink, DownloadResult, ProgressCallback, register_handler
from app.logging_utils import get_logger

_log = get_logger("pixeldrain_handler")


@register_handler
class PixeldrainHandler(HostHandler):
    """
    Handler for Pixeldrain downloads.

    Pixeldrain has a simple API:
    - File info: https://pixeldrain.com/api/file/{id}/info
    - Download: https://pixeldrain.com/api/file/{id}
    """

    SUPPORTED_DOMAINS = ["pixeldrain.com"]
    DISPLAY_NAME = "Pixeldrain"
    REQUIRES_AUTH = False

    API_BASE = "https://pixeldrain.com/api"

    def _extract_file_id(self, url: str) -> Optional[str]:
        """Extract file ID from Pixeldrain URL."""
        # URL formats:
        # https://pixeldrain.com/u/FILE_ID
        # https://pixeldrain.com/api/file/FILE_ID
        patterns = [
            r"/u/([a-zA-Z0-9]+)",
            r"/api/file/([a-zA-Z0-9]+)",
            r"/l/([a-zA-Z0-9]+)",  # List/folder
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def resolve_link(self, url: str) -> ResolvedLink:
        """Resolve Pixeldrain URL to direct download link."""
        file_id = self._extract_file_id(url)

        if not file_id:
            return ResolvedLink(
                direct_url="",
                error="Could not extract file ID from Pixeldrain URL"
            )

        try:
            # Get file info from API
            info_url = f"{self.API_BASE}/file/{file_id}/info"

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            req = urllib.request.Request(info_url, headers=headers)

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))

                filename = data.get("name", f"pixeldrain_{file_id}")
                file_size = data.get("size", 0)

                direct_url = f"{self.API_BASE}/file/{file_id}"

                return ResolvedLink(
                    direct_url=direct_url,
                    filename=filename,
                    file_size=file_size,
                )

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ResolvedLink(direct_url="", error="File not found")
            return ResolvedLink(direct_url="", error=f"HTTP error: {e.code}")

        except Exception as e:
            _log.warning("pixeldrain_resolve_error %s", str(e))
            # Return basic URL anyway
            return ResolvedLink(
                direct_url=f"{self.API_BASE}/file/{file_id}",
                filename=f"pixeldrain_{file_id}",
            )
