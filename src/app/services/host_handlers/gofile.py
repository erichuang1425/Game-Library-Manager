from __future__ import annotations
"""
Gofile.io host handler.

Gofile requires getting a guest token and then using their API.
"""

import re
import json
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import urllib.request
import urllib.error

from .base import HostHandler, ResolvedLink, DownloadResult, ProgressCallback, register_handler
from app.logging_utils import get_logger
from app.services.http_utils import (
    create_request, handle_http_error,
    DEFAULT_TIMEOUT, EXTENDED_TIMEOUT, CHUNK_SIZE,
)

_log = get_logger("gofile_handler")


@register_handler
class GofileHandler(HostHandler):
    """
    Handler for Gofile.io downloads.

    Gofile requires:
    1. Get a guest account token
    2. Use token to access content API
    3. Get direct download link

    Gofile is generally generous with limits but can rate limit heavy use.
    """

    SUPPORTED_DOMAINS = ["gofile.io"]
    DISPLAY_NAME = "Gofile"
    REQUIRES_AUTH = False
    PRIORITY = 2  # Good reliability, minimal limits
    HAS_DAILY_LIMIT = False  # Generally no strict limit

    API_BASE = "https://api.gofile.io"

    # Error patterns
    ERROR_PATTERNS = [
        "notFound",
        "not found",
        "expired",
        "rate limit",
    ]

    def __init__(self) -> None:
        super().__init__()
        self._token: Optional[str] = None

    def _get_token(self) -> Optional[str]:
        """Get or create a guest account token."""
        if self._token:
            return self._token

        try:
            url = f"{self.API_BASE}/createAccount"
            req = create_request(url)

            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))

                if data.get("status") == "ok":
                    self._token = data.get("data", {}).get("token")
                    _log.info("gofile_token_created")
                    return self._token

        except Exception as e:
            _log.warning("gofile_token_error %s", str(e))

        return None

    def _extract_content_id(self, url: str) -> Optional[str]:
        """Extract content ID from Gofile URL."""
        # URL format: https://gofile.io/d/CONTENT_ID
        match = re.search(r"/d/([a-zA-Z0-9]+)", url)
        if match:
            return match.group(1)
        return None

    def resolve_link(self, url: str) -> ResolvedLink:
        """Resolve Gofile URL to direct download link."""
        content_id = self._extract_content_id(url)

        if not content_id:
            return ResolvedLink(
                direct_url="",
                error="Could not extract content ID from Gofile URL"
            )

        token = self._get_token()
        if not token:
            return ResolvedLink(
                direct_url="",
                error="Could not get Gofile access token"
            )

        try:
            # Get content info using shared http_utils
            info_url = f"{self.API_BASE}/getContent?contentId={content_id}&token={token}"
            req = create_request(info_url)

            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as response:
                data = json.loads(response.read().decode("utf-8"))

                if data.get("status") != "ok":
                    return ResolvedLink(
                        direct_url="",
                        error=data.get("status", "Unknown error")
                    )

                content_data = data.get("data", {})

                # Check if it's a folder or file
                if content_data.get("type") == "folder":
                    # Get first file in folder
                    children = content_data.get("children", {})
                    if children:
                        first_file = list(children.values())[0]
                        direct_url = first_file.get("link", "")
                        filename = first_file.get("name", f"gofile_{content_id}")
                        file_size = first_file.get("size", 0)
                    else:
                        return ResolvedLink(
                            direct_url="",
                            error="Folder is empty"
                        )
                else:
                    direct_url = content_data.get("link", "")
                    filename = content_data.get("name", f"gofile_{content_id}")
                    file_size = content_data.get("size", 0)

                return ResolvedLink(
                    direct_url=direct_url,
                    filename=filename,
                    file_size=file_size,
                )

        except urllib.error.HTTPError as e:
            _, message = handle_http_error(e)
            return ResolvedLink(direct_url="", error=message)

        except Exception as e:
            _log.warning("gofile_resolve_error %s", str(e))
            return ResolvedLink(direct_url="", error=str(e))

    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """Download from Gofile with token authentication."""
        import time

        try:
            resolved = self.resolve_link(url)
            if resolved.error and not resolved.direct_url:
                return DownloadResult(success=False, error=resolved.error)

            if not resolved.direct_url:
                return DownloadResult(success=False, error="No download link available")

            destination.mkdir(parents=True, exist_ok=True)

            # Create request with token cookie
            extra_headers = {"Cookie": f"accountToken={self._token}"} if self._token else {}
            req = create_request(resolved.direct_url, headers=extra_headers)

            with urllib.request.urlopen(req, timeout=EXTENDED_TIMEOUT) as response:
                filename = resolved.filename or "gofile_download"
                file_path = destination / filename

                total_size = int(response.headers.get("Content-Length", 0)) or resolved.file_size
                bytes_downloaded = 0
                start_time = time.time()

                with open(file_path, "wb") as f:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
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
            _log.warning("gofile_download_error %s", str(e))
            return DownloadResult(success=False, error=str(e))

    def check_availability(self, url: str) -> tuple[bool, str]:
        """Check if content is available on Gofile."""
        content_id = self._extract_content_id(url)
        if not content_id:
            return False, "Invalid Gofile URL"

        token = self._get_token()
        if not token:
            return False, "Could not get access token"

        try:
            info_url = f"{self.API_BASE}/getContent?contentId={content_id}&token={token}"
            req = create_request(info_url)

            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
                status = data.get("status", "")

                if status == "ok":
                    return True, ""
                elif status == "error-notFound":
                    return False, "Content not found"
                else:
                    return False, f"Error: {status}"

        except urllib.error.HTTPError as e:
            _, message = handle_http_error(e)
            return False, message

        except Exception as e:
            return False, str(e)
