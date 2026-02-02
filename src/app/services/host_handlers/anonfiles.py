from __future__ import annotations
"""
Anonfiles host handler.

Anonfiles and similar anonymous file hosting services.
Note: Anonfiles service has been unreliable historically.
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

_log = get_logger("anonfiles_handler")


@register_handler
class AnonfilesHandler(HostHandler):
    """
    Handler for Anonfiles and similar anonymous file hosts.

    Supports:
    - anonfiles.com (original, often down)
    - Various anonfiles mirrors/alternatives
    """

    SUPPORTED_DOMAINS = [
        "anonfiles.com",
        "anonfiles.me",
        "anonfiles.la",
        "filechan.org",
        "letsupload.cc",
        "lolabits.se",
        "share-online.is",
        "zippyshare.day",
    ]
    DISPLAY_NAME = "Anonfiles"
    REQUIRES_AUTH = False
    PRIORITY = 8  # Unreliable, lower priority
    HAS_DAILY_LIMIT = False

    def _extract_file_id(self, url: str) -> Optional[str]:
        """Extract file ID from Anonfiles URL."""
        # URL format: https://anonfiles.com/FILE_ID/filename
        patterns = [
            r"anonfiles\.[a-z]+/([a-zA-Z0-9]+)",
            r"/([a-zA-Z0-9]{10,})/",  # Most IDs are 10+ chars
            r"filechan\.org/([a-zA-Z0-9]+)",
            r"letsupload\.cc/([a-zA-Z0-9]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _extract_download_link(self, html_content: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract download link from page.
        Returns: (direct_url, filename)
        """
        direct_url = None
        filename = None

        # Look for download link - multiple patterns for different versions
        link_patterns = [
            r'id=["\']download-url["\'][^>]*href=["\']([^"\']+)["\']',
            r'href=["\']([^"\']+)["\'][^>]*id=["\']download-url["\']',
            r'<a[^>]*download[^>]*href=["\']([^"\']+)["\']',
            r'href=["\']([^"\']*cdn[^"\']*)["\']',
            r'href=["\']([^"\']+\.(zip|rar|7z|exe|apk)[^"\']*)["\']',
        ]

        for pattern in link_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                url = match.group(1)
                # Skip javascript and anchors
                if url.startswith(("javascript:", "#", "void")):
                    continue
                direct_url = url
                break

        # Extract filename
        filename_patterns = [
            r'<h1[^>]*>([^<]+\.(zip|rar|7z|exe|apk|iso))</h1>',
            r'<title>([^<]+) - Anonfiles</title>',
            r'filename:\s*["\']?([^"\'<>\n]+)["\']?',
        ]

        for pattern in filename_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                filename = match.group(1).strip()
                break

        return direct_url, filename

    def resolve_link(self, url: str) -> ResolvedLink:
        """Resolve Anonfiles URL to direct download link."""
        file_id = self._extract_file_id(url)

        if not file_id:
            return ResolvedLink(
                direct_url="",
                error="Could not extract file ID from URL"
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
                error_patterns = [
                    "file not found",
                    "file was removed",
                    "file was deleted",
                    "not available",
                    "404",
                    "error",
                ]

                html_lower = html_content.lower()
                if any(err in html_lower for err in error_patterns):
                    # Only return error if it's clearly an error page
                    if "download" not in html_lower:
                        return ResolvedLink(direct_url="", error="File not found or removed")

                direct_url, filename = self._extract_download_link(html_content)

                if not direct_url:
                    return ResolvedLink(
                        direct_url="",
                        error="Could not find download link - site may be down"
                    )

                return ResolvedLink(
                    direct_url=direct_url,
                    filename=filename or f"anonfiles_{file_id}",
                )

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ResolvedLink(direct_url="", error="File not found (404)")
            elif e.code == 503:
                return ResolvedLink(direct_url="", error="Service unavailable - site may be down")
            return ResolvedLink(direct_url="", error=f"HTTP error: {e.code}")

        except urllib.error.URLError as e:
            return ResolvedLink(direct_url="", error=f"Connection error: {str(e)} - site may be down")

        except Exception as e:
            _log.warning("anonfiles_resolve_error %s", str(e))
            return ResolvedLink(direct_url="", error=str(e))

    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """Download from Anonfiles."""
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
            _log.warning("anonfiles_download_error %s", str(e))
            return DownloadResult(success=False, error=str(e))

    def check_availability(self, url: str) -> Tuple[bool, str]:
        """Check if file is available."""
        file_id = self._extract_file_id(url)
        if not file_id:
            return False, "Invalid URL"

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

                # Check if download link exists
                if "download" in html_content.lower():
                    return True, ""

                return False, "No download link found"

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "File not found"
            elif e.code == 503:
                return False, "Service unavailable"
            return False, f"HTTP error: {e.code}"

        except urllib.error.URLError:
            return False, "Site may be down"

        except Exception as e:
            return False, str(e)
