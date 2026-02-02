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
from app.services.http_utils import create_request, handle_http_error, DEFAULT_TIMEOUT

_log = get_logger("pixeldrain_handler")


@register_handler
class PixeldrainHandler(HostHandler):
    """
    Handler for Pixeldrain downloads.

    Pixeldrain has a simple API:
    - File info: https://pixeldrain.com/api/file/{id}/info
    - Download: https://pixeldrain.com/api/file/{id}

    Note: Pixeldrain has daily bandwidth limits for free users (~6GB/day).
    """

    SUPPORTED_DOMAINS = ["pixeldrain.com"]
    DISPLAY_NAME = "Pixeldrain"
    REQUIRES_AUTH = False
    PRIORITY = 3  # Good but has limits
    HAS_DAILY_LIMIT = True
    DAILY_LIMIT_GB = 6.0

    API_BASE = "https://pixeldrain.com/api"

    # Error patterns indicating bandwidth limit
    LIMIT_ERROR_PATTERNS = [
        "bandwidth limit",
        "download limit",
        "rate limit",
        "too many requests",
    ]

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
            # Get file info from API using shared http_utils
            info_url = f"{self.API_BASE}/file/{file_id}/info"
            req = create_request(info_url)

            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
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
            _, message = handle_http_error(e)
            return ResolvedLink(direct_url="", error=message)

        except Exception as e:
            _log.warning("pixeldrain_resolve_error %s", str(e))
            # Return basic URL anyway
            return ResolvedLink(
                direct_url=f"{self.API_BASE}/file/{file_id}",
                filename=f"pixeldrain_{file_id}",
            )

    def check_availability(self, url: str) -> tuple[bool, str]:
        """Check if file is available on Pixeldrain."""
        file_id = self._extract_file_id(url)
        if not file_id:
            return False, "Invalid Pixeldrain URL"

        try:
            info_url = f"{self.API_BASE}/file/{file_id}/info"
            req = create_request(info_url)

            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("success") is False:
                    return False, data.get("message", "Unknown error")
                return True, ""

        except urllib.error.HTTPError as e:
            # Try to read error message from response body
            try:
                error_data = json.loads(e.read().decode("utf-8"))
                error_msg = error_data.get("message", "")
                # Check for limit errors
                if any(p in error_msg.lower() for p in self.LIMIT_ERROR_PATTERNS):
                    return False, f"Daily limit reached: {error_msg}"
                if error_msg:
                    return False, error_msg
            except Exception:
                pass
            # Fall back to standard error handling
            _, message = handle_http_error(e)
            return False, message

        except Exception as e:
            return False, str(e)
