from __future__ import annotations
"""
Workupload host handler.

Workupload is a file hosting service commonly used for game downloads.
"""

import re
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse
import urllib.request
import urllib.error

from .base import HostHandler, ResolvedLink, DownloadResult, ProgressCallback, register_handler
from app.logging_utils import get_logger

_log = get_logger("workupload_handler")


@register_handler
class WorkuploadHandler(HostHandler):
    """
    Handler for Workupload downloads.

    Workupload pages contain direct download links after potential wait times.
    """

    SUPPORTED_DOMAINS = ["workupload.com"]
    DISPLAY_NAME = "Workupload"
    REQUIRES_AUTH = False
    PRIORITY = 7  # Decent but can have wait times
    HAS_DAILY_LIMIT = False

    def _extract_file_id(self, url: str) -> Optional[str]:
        """Extract file ID from Workupload URL."""
        # URL format: https://workupload.com/file/FILE_ID
        patterns = [
            r"/file/([a-zA-Z0-9]+)",
            r"workupload\.com/([a-zA-Z0-9]+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _extract_download_link(self, html_content: str, base_url: str) -> Tuple[Optional[str], Optional[str], int]:
        """
        Extract download link from Workupload page.
        Returns: (direct_url, filename, file_size)
        """
        direct_url = None
        filename = None
        file_size = 0

        # Look for download link
        link_patterns = [
            r'href=["\']([^"\']*download[^"\']*)["\'][^>]*class=["\'][^"\']*btn[^"\']*["\']',
            r'id=["\']download["\'][^>]*href=["\']([^"\']+)["\']',
            r'href=["\']([^"\']+)["\'][^>]*id=["\']download["\']',
            r'class=["\']download[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
            r'data-url=["\']([^"\']+)["\']',
        ]

        for pattern in link_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                url = match.group(1)
                if not url.startswith("http"):
                    parsed = urlparse(base_url)
                    if url.startswith("/"):
                        url = f"{parsed.scheme}://{parsed.netloc}{url}"
                    else:
                        url = f"{parsed.scheme}://{parsed.netloc}/{url}"
                direct_url = url
                break

        # Extract filename
        filename_patterns = [
            r'<h1[^>]*>([^<]+)</h1>',
            r'<span[^>]*class=["\'][^"\']*filename[^"\']*["\'][^>]*>([^<]+)</span>',
            r'<title>([^<]+) - Workupload</title>',
            r'<div[^>]*class=["\'][^"\']*file-name[^"\']*["\'][^>]*>([^<]+)</div>',
        ]

        for pattern in filename_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                filename = match.group(1).strip()
                # Remove common suffixes
                filename = re.sub(r'\s*-\s*Workupload.*$', '', filename, flags=re.IGNORECASE)
                break

        # Extract file size
        size_patterns = [
            r'Size:\s*([0-9.]+)\s*(KB|MB|GB)',
            r'(\d+(?:\.\d+)?)\s*(KB|MB|GB)',
        ]

        for pattern in size_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                try:
                    size_val = float(match.group(1))
                    unit = match.group(2).upper()
                    multipliers = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
                    file_size = int(size_val * multipliers.get(unit, 1))
                except ValueError:
                    pass
                break

        return direct_url, filename, file_size

    def resolve_link(self, url: str) -> ResolvedLink:
        """Resolve Workupload URL to direct download link."""
        file_id = self._extract_file_id(url)

        if not file_id:
            return ResolvedLink(
                direct_url="",
                error="Could not extract file ID from Workupload URL"
            )

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=30) as response:
                html_content = response.read().decode("utf-8", errors="ignore")

                # Check for errors
                if any(err in html_content.lower() for err in [
                    "file not found", "removed", "deleted", "does not exist"
                ]):
                    return ResolvedLink(direct_url="", error="File not found or removed")

                direct_url, filename, file_size = self._extract_download_link(
                    html_content, response.geturl()
                )

                if not direct_url:
                    return ResolvedLink(
                        direct_url="",
                        error="Could not find download link on Workupload page"
                    )

                return ResolvedLink(
                    direct_url=direct_url,
                    filename=filename or f"workupload_{file_id}",
                    file_size=file_size,
                )

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ResolvedLink(direct_url="", error="File not found (404)")
            return ResolvedLink(direct_url="", error=f"HTTP error: {e.code}")

        except Exception as e:
            _log.warning("workupload_resolve_error %s", str(e))
            return ResolvedLink(direct_url="", error=str(e))

    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """Download from Workupload."""
        try:
            resolved = self.resolve_link(url)
            if resolved.error and not resolved.direct_url:
                return DownloadResult(success=False, error=resolved.error)

            if not resolved.direct_url:
                return DownloadResult(success=False, error="No download link available")

            destination.mkdir(parents=True, exist_ok=True)

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": url,
            }
            req = urllib.request.Request(resolved.direct_url, headers=headers)

            with urllib.request.urlopen(req, timeout=60) as response:
                filename = resolved.filename

                # Get filename from Content-Disposition if available
                content_disp = response.headers.get("Content-Disposition", "")
                if "filename=" in content_disp:
                    match = re.search(r'filename[*]?=["\']?([^"\';\n]+)', content_disp)
                    if match:
                        filename = match.group(1).strip()

                file_path = destination / filename

                total_size = int(response.headers.get("Content-Length", 0)) or resolved.file_size
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
            _log.warning("workupload_download_error %s", str(e))
            return DownloadResult(success=False, error=str(e))

    def check_availability(self, url: str) -> Tuple[bool, str]:
        """Check if file is available on Workupload."""
        file_id = self._extract_file_id(url)
        if not file_id:
            return False, "Invalid Workupload URL"

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=15) as response:
                html_content = response.read().decode("utf-8", errors="ignore")

                if any(err in html_content.lower() for err in [
                    "file not found", "removed", "deleted", "does not exist"
                ]):
                    return False, "File not found or removed"

                return True, ""

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "File not found"
            return False, f"HTTP error: {e.code}"

        except Exception as e:
            return False, str(e)
