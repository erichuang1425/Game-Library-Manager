from __future__ import annotations
"""
MediaFire host handler.

MediaFire provides file hosting with direct download links
after navigating their download page.
"""

import re
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, urljoin
import urllib.request
import urllib.error

from .base import HostHandler, ResolvedLink, DownloadResult, ProgressCallback, register_handler
from app.logging_utils import get_logger

_log = get_logger("mediafire_handler")


@register_handler
class MediafireHandler(HostHandler):
    """
    Handler for MediaFire downloads.

    MediaFire download pages contain a direct download button.
    We need to parse the page to extract the actual download link.
    """

    SUPPORTED_DOMAINS = ["mediafire.com"]
    DISPLAY_NAME = "MediaFire"
    REQUIRES_AUTH = False
    PRIORITY = 6  # Generally reliable but can have popups/ads
    HAS_DAILY_LIMIT = False

    def _extract_file_key(self, url: str) -> Optional[str]:
        """Extract file key from MediaFire URL."""
        # URL formats:
        # https://www.mediafire.com/file/KEY/filename
        # https://www.mediafire.com/file/KEY
        # https://www.mediafire.com/?KEY
        patterns = [
            r"/file/([a-zA-Z0-9]+)",
            r"\?([a-zA-Z0-9]+)$",
            r"/view/([a-zA-Z0-9]+)",
            r"/download/([a-zA-Z0-9]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _extract_direct_link(self, html_content: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract direct download link from MediaFire page.
        Returns: (direct_url, filename)
        """
        # Look for the download button href
        patterns = [
            # Standard download button
            r'href=["\']([^"\']*download[^"\']*mediafire\.com[^"\']*)["\']',
            r'id=["\']downloadButton["\'][^>]*href=["\']([^"\']+)["\']',
            r'href=["\']([^"\']+)["\'][^>]*id=["\']downloadButton["\']',
            # aria-label download
            r'aria-label=["\']Download file["\'][^>]*href=["\']([^"\']+)["\']',
            # Direct CDN links
            r'(https?://download\d*\.mediafire\.com/[^"\'<>\s]+)',
        ]

        direct_url = None
        for pattern in patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                direct_url = match.group(1)
                break

        # Extract filename
        filename = None
        filename_patterns = [
            r'<div[^>]*class=["\'][^"\']*filename[^"\']*["\'][^>]*>([^<]+)<',
            r'<title>([^<]+) - MediaFire</title>',
            r'data-filename=["\']([^"\']+)["\']',
        ]

        for pattern in filename_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                filename = match.group(1).strip()
                break

        return direct_url, filename

    def resolve_link(self, url: str) -> ResolvedLink:
        """Resolve MediaFire URL to direct download link."""
        file_key = self._extract_file_key(url)

        if not file_key:
            return ResolvedLink(
                direct_url="",
                error="Could not extract file key from MediaFire URL"
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
                if "File Removed" in html_content or "Invalid or Deleted File" in html_content:
                    return ResolvedLink(direct_url="", error="File has been removed")

                if "This file is no longer available" in html_content:
                    return ResolvedLink(direct_url="", error="File no longer available")

                direct_url, filename = self._extract_direct_link(html_content)

                if not direct_url:
                    return ResolvedLink(
                        direct_url="",
                        error="Could not find download link on MediaFire page"
                    )

                return ResolvedLink(
                    direct_url=direct_url,
                    filename=filename or f"mediafire_{file_key}",
                )

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ResolvedLink(direct_url="", error="File not found (404)")
            return ResolvedLink(direct_url="", error=f"HTTP error: {e.code}")

        except Exception as e:
            _log.warning("mediafire_resolve_error %s", str(e))
            return ResolvedLink(direct_url="", error=str(e))

    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """Download from MediaFire."""
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
                # Get filename from Content-Disposition if available
                content_disp = response.headers.get("Content-Disposition", "")
                filename = resolved.filename

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
            _log.warning("mediafire_download_error %s", str(e))
            return DownloadResult(success=False, error=str(e))

    def check_availability(self, url: str) -> Tuple[bool, str]:
        """Check if file is available on MediaFire."""
        file_key = self._extract_file_key(url)
        if not file_key:
            return False, "Invalid MediaFire URL"

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=15) as response:
                html_content = response.read().decode("utf-8", errors="ignore")

                if any(err in html_content for err in [
                    "File Removed", "Invalid or Deleted", "no longer available"
                ]):
                    return False, "File has been removed"

                # Check for download button
                if "downloadButton" in html_content or "Download file" in html_content:
                    return True, ""

                return False, "Download button not found"

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "File not found"
            return False, f"HTTP error: {e.code}"

        except Exception as e:
            return False, str(e)
