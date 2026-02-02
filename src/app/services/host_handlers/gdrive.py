from __future__ import annotations
"""
Google Drive host handler.

Handles public Google Drive share links by converting them
to direct download URLs.
"""

import re
import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode
import urllib.request
import urllib.error

from .base import HostHandler, ResolvedLink, DownloadResult, ProgressCallback, register_handler
from app.logging_utils import get_logger

_log = get_logger("gdrive_handler")


@register_handler
class GDriveHandler(HostHandler):
    """
    Handler for Google Drive downloads.

    Converts share URLs to direct download URLs.
    Handles the virus scan warning for large files.
    """

    SUPPORTED_DOMAINS = ["drive.google.com", "docs.google.com"]
    DISPLAY_NAME = "Google Drive"
    REQUIRES_AUTH = False  # Public links don't need auth

    def _extract_file_id(self, url: str) -> Optional[str]:
        """Extract file ID from various Google Drive URL formats."""
        patterns = [
            # /file/d/FILE_ID/view
            r"/file/d/([a-zA-Z0-9_-]+)",
            # /open?id=FILE_ID
            r"[?&]id=([a-zA-Z0-9_-]+)",
            # /uc?id=FILE_ID
            r"/uc\?.*id=([a-zA-Z0-9_-]+)",
            # docs.google.com/document/d/FILE_ID
            r"/document/d/([a-zA-Z0-9_-]+)",
            # drive.google.com/drive/folders/FILE_ID (folder)
            r"/folders/([a-zA-Z0-9_-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _get_confirm_token(self, response_text: str) -> Optional[str]:
        """Extract virus scan confirmation token from response."""
        # Look for the confirm token in the page
        patterns = [
            r'confirm=([0-9A-Za-z_-]+)',
            r'"downloadUrl":"[^"]*confirm=([^&"]+)',
            r'id="uc-download-link"[^>]*href="[^"]*confirm=([^&"]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, response_text)
            if match:
                return match.group(1)

        return None

    def _get_file_name(self, response_text: str, headers: dict) -> str:
        """Extract filename from response."""
        # Try Content-Disposition header
        content_disp = headers.get("Content-Disposition", "")
        if "filename=" in content_disp:
            match = re.search(r'filename[*]?=["\']?([^"\';\n]+)', content_disp)
            if match:
                return match.group(1).strip()

        # Try to find in page
        match = re.search(r'<meta[^>]*content="([^"]+)"[^>]*property="og:title"', response_text)
        if match:
            return match.group(1)

        match = re.search(r'"title":"([^"]+)"', response_text)
        if match:
            return match.group(1)

        return "gdrive_download"

    def resolve_link(self, url: str) -> ResolvedLink:
        """Resolve Google Drive URL to direct download link."""
        file_id = self._extract_file_id(url)

        if not file_id:
            return ResolvedLink(
                direct_url="",
                error="Could not extract file ID from Google Drive URL"
            )

        # Construct direct download URL
        direct_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        try:
            # Try to get file info
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            req = urllib.request.Request(direct_url, headers=headers)

            with urllib.request.urlopen(req, timeout=30) as response:
                # Check if we got a direct download or a warning page
                content_type = response.headers.get("Content-Type", "")

                if "text/html" in content_type:
                    # Got a warning page - need to extract confirm token
                    body = response.read().decode("utf-8", errors="ignore")
                    confirm_token = self._get_confirm_token(body)

                    if confirm_token:
                        direct_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"

                    filename = self._get_file_name(body, dict(response.headers))
                else:
                    # Direct download
                    filename = self._get_file_name("", dict(response.headers))

                return ResolvedLink(
                    direct_url=direct_url,
                    filename=filename,
                )

        except Exception as e:
            _log.warning("gdrive_resolve_error %s", str(e))
            # Return basic URL anyway
            return ResolvedLink(
                direct_url=direct_url,
                filename=f"gdrive_{file_id}",
            )

    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """
        Download from Google Drive with virus scan handling.
        """
        import time

        try:
            resolved = self.resolve_link(url)
            if resolved.error and not resolved.direct_url:
                return DownloadResult(success=False, error=resolved.error)

            destination.mkdir(parents=True, exist_ok=True)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }

            # First request
            req = urllib.request.Request(resolved.direct_url, headers=headers)

            with urllib.request.urlopen(req, timeout=60) as response:
                content_type = response.headers.get("Content-Type", "")

                # Check for virus scan warning
                if "text/html" in content_type:
                    body = response.read().decode("utf-8", errors="ignore")
                    confirm_token = self._get_confirm_token(body)

                    if confirm_token:
                        file_id = self._extract_file_id(url)
                        confirmed_url = f"https://drive.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
                        req = urllib.request.Request(confirmed_url, headers=headers)
                        response = urllib.request.urlopen(req, timeout=60)
                    else:
                        return DownloadResult(
                            success=False,
                            error="Could not bypass virus scan warning"
                        )

                # Download the file
                filename = resolved.filename or "gdrive_download"
                file_path = destination / filename

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
            _log.warning("gdrive_download_error %s", str(e))
            return DownloadResult(success=False, error=str(e))
