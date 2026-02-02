from __future__ import annotations
"""
Buzzheavier host handler.

Buzzheavier is a file hosting service that may require handling
redirect/confirm pages before actual download.
"""

import re
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, urljoin, parse_qs
import urllib.request
import urllib.error

from .base import HostHandler, ResolvedLink, DownloadResult, ProgressCallback, register_handler
from app.logging_utils import get_logger

_log = get_logger("buzzheavier_handler")


@register_handler
class BuzzheavierHandler(HostHandler):
    """
    Handler for Buzzheavier downloads.

    Buzzheavier may use redirect/confirm pages before providing actual download.
    This handler navigates through those pages to get the final download link.
    """

    SUPPORTED_DOMAINS = ["buzzheavier.com", "bhvr.cc"]
    DISPLAY_NAME = "Buzzheavier"
    REQUIRES_AUTH = False

    # Priority ranking (lower = higher priority, best host)
    PRIORITY = 1  # Highest priority

    def __init__(self) -> None:
        super().__init__()
        self._session_cookies: Dict[str, str] = {}

    def _extract_file_id(self, url: str) -> Optional[str]:
        """Extract file ID from Buzzheavier URL."""
        # URL formats:
        # https://buzzheavier.com/f/FILE_ID
        # https://buzzheavier.com/FILE_ID
        # https://bhvr.cc/FILE_ID
        patterns = [
            r"/f/([a-zA-Z0-9_-]+)",
            r"buzzheavier\.com/([a-zA-Z0-9_-]+)$",
            r"bhvr\.cc/([a-zA-Z0-9_-]+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    def _make_request(
        self,
        url: str,
        method: str = "GET",
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> Tuple[bytes, Dict[str, str], str]:
        """
        Make HTTP request with cookie handling and redirect support.
        Returns (content, response_headers, final_url).
        """
        default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": url,
        }

        if headers:
            default_headers.update(headers)

        # Add session cookies
        if self._session_cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self._session_cookies.items())
            default_headers["Cookie"] = cookie_str

        req = urllib.request.Request(url, data=data, headers=default_headers, method=method)

        try:
            # Create opener that handles redirects
            if follow_redirects:
                opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
            else:
                opener = urllib.request.build_opener()

            with opener.open(req, timeout=30) as response:
                # Store any cookies from response
                for header in response.headers.get_all("Set-Cookie", []):
                    cookie_match = re.match(r"([^=]+)=([^;]+)", header)
                    if cookie_match:
                        self._session_cookies[cookie_match.group(1)] = cookie_match.group(2)

                content = response.read()
                resp_headers = dict(response.headers)
                final_url = response.geturl()

                return content, resp_headers, final_url

        except urllib.error.HTTPError as e:
            # Still try to read response body for error pages
            content = e.read() if hasattr(e, 'read') else b""
            return content, dict(e.headers) if hasattr(e, 'headers') else {}, url

    def _handle_confirm_page(self, content: bytes, base_url: str) -> Optional[str]:
        """
        Handle redirect/confirm pages to extract real download link.

        These pages often have:
        - Countdown timers
        - CAPTCHA (we can't solve automatically)
        - Multiple fake download buttons
        - JavaScript redirects
        """
        try:
            html_content = content.decode("utf-8", errors="ignore")

            # Look for direct download links in the page
            download_patterns = [
                # Direct download link patterns
                r'href=["\']([^"\']*(?:download|dl)[^"\']*)["\']',
                r'href=["\']([^"\']+\?(?:token|key|id)=[^"\']+)["\']',
                # Data attributes with download URL
                r'data-url=["\']([^"\']+)["\']',
                r'data-download=["\']([^"\']+)["\']',
                r'data-href=["\']([^"\']+)["\']',
                # JavaScript variables
                r'download_url\s*[=:]\s*["\']([^"\']+)["\']',
                r'directUrl\s*[=:]\s*["\']([^"\']+)["\']',
                r'fileUrl\s*[=:]\s*["\']([^"\']+)["\']',
                # Form actions
                r'<form[^>]*action=["\']([^"\']*download[^"\']*)["\']',
            ]

            for pattern in download_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE)
                for match in matches:
                    # Skip obviously wrong URLs
                    if any(skip in match.lower() for skip in [
                        "javascript:", "mailto:", "#", "void(0)",
                        "facebook", "twitter", "instagram", "ad.",
                        "popup", "banner", "click"
                    ]):
                        continue

                    # Make absolute URL
                    if match.startswith("//"):
                        match = "https:" + match
                    elif match.startswith("/"):
                        parsed = urlparse(base_url)
                        match = f"{parsed.scheme}://{parsed.netloc}{match}"
                    elif not match.startswith("http"):
                        match = urljoin(base_url, match)

                    _log.info("buzzheavier_found_link %s", match[:100])
                    return match

            # Look for countdown/timer redirect
            timer_patterns = [
                r'setTimeout[^}]*location\s*[=.]\s*["\']([^"\']+)["\']',
                r'window\.location\s*=\s*["\']([^"\']+)["\']',
                r'href=["\']([^"\']+)["\'][^>]*id=["\']?download',
            ]

            for pattern in timer_patterns:
                match = re.search(pattern, html_content, re.IGNORECASE)
                if match:
                    url = match.group(1)
                    if not url.startswith("http"):
                        url = urljoin(base_url, url)
                    return url

        except Exception as e:
            _log.warning("buzzheavier_parse_error %s", str(e))

        return None

    def _navigate_to_download(self, url: str, max_redirects: int = 5) -> Tuple[str, str, int]:
        """
        Navigate through redirect/confirm pages to find actual download.

        Returns: (direct_url, filename, file_size)
        """
        current_url = url
        filename = ""
        file_size = 0

        for i in range(max_redirects):
            _log.info("buzzheavier_navigate step=%d url=%s", i + 1, current_url[:100])

            content, headers, final_url = self._make_request(current_url)

            # Check if this is the actual file download (not HTML)
            content_type = headers.get("Content-Type", "").lower()
            if not any(ct in content_type for ct in ["text/html", "application/json"]):
                # This is the actual file
                content_disp = headers.get("Content-Disposition", "")
                if "filename=" in content_disp:
                    match = re.search(r'filename[*]?=["\']?([^"\';\n]+)', content_disp)
                    if match:
                        filename = match.group(1).strip()

                content_length = headers.get("Content-Length", "0")
                try:
                    file_size = int(content_length)
                except ValueError:
                    pass

                return final_url, filename, file_size

            # It's HTML, look for download link
            next_url = self._handle_confirm_page(content, final_url)
            if next_url and next_url != current_url:
                # Add small delay to appear more human-like
                time.sleep(0.5)
                current_url = next_url
            else:
                # No more redirects found, return current URL
                break

        return current_url, filename, file_size

    def resolve_link(self, url: str) -> ResolvedLink:
        """Resolve Buzzheavier URL to direct download link."""
        file_id = self._extract_file_id(url)

        if not file_id:
            _log.warning("buzzheavier_no_file_id url=%s", url[:100])
            # Try to use URL as-is
            file_id = "unknown"

        try:
            direct_url, filename, file_size = self._navigate_to_download(url)

            if not filename:
                filename = f"buzzheavier_{file_id}"

            return ResolvedLink(
                direct_url=direct_url,
                filename=filename,
                file_size=file_size,
            )

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return ResolvedLink(direct_url="", error="File not found (404)")
            elif e.code == 403:
                return ResolvedLink(direct_url="", error="Access denied (403)")
            elif e.code == 429:
                return ResolvedLink(direct_url="", error="Rate limited - please try again later")
            return ResolvedLink(direct_url="", error=f"HTTP error: {e.code}")

        except Exception as e:
            _log.warning("buzzheavier_resolve_error %s", str(e))
            return ResolvedLink(direct_url="", error=str(e))

    def download(
        self,
        url: str,
        destination: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> DownloadResult:
        """Download from Buzzheavier with redirect handling."""
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

            # Add session cookies
            if self._session_cookies:
                headers["Cookie"] = "; ".join(
                    f"{k}={v}" for k, v in self._session_cookies.items()
                )

            req = urllib.request.Request(resolved.direct_url, headers=headers)

            with urllib.request.urlopen(req, timeout=60) as response:
                filename = resolved.filename or "buzzheavier_download"
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

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return DownloadResult(success=False, error="File not found (404)")
            return DownloadResult(success=False, error=f"HTTP error: {e.code}")

        except Exception as e:
            _log.warning("buzzheavier_download_error %s", str(e))
            return DownloadResult(success=False, error=str(e))

    def check_availability(self, url: str) -> Tuple[bool, str]:
        """
        Check if file is available without downloading.
        Returns: (is_available, error_message)
        """
        try:
            file_id = self._extract_file_id(url)
            if not file_id:
                return False, "Invalid URL"

            content, headers, final_url = self._make_request(url)

            # Check for common error indicators
            html_content = content.decode("utf-8", errors="ignore").lower()

            if any(err in html_content for err in [
                "file not found", "404", "doesn't exist",
                "has been removed", "no longer available"
            ]):
                return False, "File not found"

            return True, ""

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "File not found (404)"
            return False, f"HTTP error: {e.code}"

        except Exception as e:
            return False, str(e)
