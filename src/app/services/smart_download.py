from __future__ import annotations
"""
Smart Download Selector for F95zone.

Provides intelligent download source selection with:
- Host priority ranking (buzzheavier > gofile > pixeldrain > mega > etc.)
- Daily limit tracking for hosts with quotas
- 404 detection with automatic fallback to alternatives
- Redirect/confirm page handling
- Multi-click bypass for ad-protected links
- Download link validation
"""

import json
import time
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from urllib.parse import urlparse
import urllib.request
import urllib.error

from app.logging_utils import get_logger, kv
from app.storage.paths import get_app_dir

_log = get_logger("smart_download")


# Host priority ranking (lower number = higher priority = try first)
HOST_PRIORITY = {
    "buzzheavier": 1,
    "gofile": 2,
    "pixeldrain": 3,
    "mega": 4,
    "gdrive": 5,
    "mediafire": 6,
    "workupload": 7,
    "anonfiles": 8,
    "uploadhaven": 9,
    "mixdrop": 10,
    "katfile": 11,
    "bowfile": 12,
    "direct": 99,  # Fallback
}

# Hosts with daily download limits
HOSTS_WITH_LIMITS = {
    "pixeldrain": {
        "daily_limit_gb": 6.0,  # Free users get ~6GB/day
        "limit_reset_hours": 24,
        "error_patterns": ["bandwidth limit", "download limit", "quota exceeded", "rate limit"],
    },
    "mega": {
        "daily_limit_gb": 5.0,  # Free users get ~5GB transfer quota
        "limit_reset_hours": 6,  # MEGA resets every 6 hours partially
        "error_patterns": ["transfer quota", "bandwidth limit", "over quota", "temporarily unavailable"],
    },
    "gofile": {
        "daily_limit_gb": 10.0,  # Generally generous but has limits
        "limit_reset_hours": 24,
        "error_patterns": ["download limit", "too many requests"],
    },
}

# Hosts that are known to be unreliable
UNRELIABLE_HOSTS = {"anonfiles", "bowfile", "katfile"}

# Patterns indicating file not found
FILE_NOT_FOUND_PATTERNS = [
    r"404",
    r"not found",
    r"doesn'?t exist",
    r"has been (removed|deleted)",
    r"no longer available",
    r"file (was )?(removed|deleted)",
    r"content unavailable",
    r"link (expired|invalid)",
    r"error.*finding",
]


@dataclass
class HostStatus:
    """Tracks status and usage for a host."""
    host_type: str
    bytes_downloaded_today: int = 0
    last_download: Optional[str] = None
    last_error: Optional[str] = None
    last_error_time: Optional[str] = None
    consecutive_failures: int = 0
    is_limited: bool = False
    limit_reset_time: Optional[str] = None
    date_tracked: str = field(default_factory=lambda: date.today().isoformat())

    def reset_if_new_day(self) -> None:
        """Reset daily counters if it's a new day."""
        today = date.today().isoformat()
        if self.date_tracked != today:
            self.bytes_downloaded_today = 0
            self.consecutive_failures = 0
            self.is_limited = False
            self.limit_reset_time = None
            self.date_tracked = today


@dataclass
class DownloadSource:
    """A download source option."""
    url: str
    host_type: str
    priority: int
    label: str = ""
    file_size: int = 0
    is_available: bool = True
    error: str = ""
    last_checked: Optional[str] = None


@dataclass
class SmartDownloadResult:
    """Result from smart download attempt."""
    success: bool
    url: str = ""
    host_type: str = ""
    file_path: str = ""
    file_size: int = 0
    error: str = ""
    tried_hosts: List[str] = field(default_factory=list)
    fallback_used: bool = False


class HostLimitTracker:
    """
    Tracks daily download limits for various hosts.
    Persists to disk to survive restarts.
    """

    def __init__(self) -> None:
        self._status: Dict[str, HostStatus] = {}
        self._storage_path = get_app_dir() / "host_limits.json"
        self._load()

    def _load(self) -> None:
        """Load host status from disk."""
        try:
            if self._storage_path.exists():
                data = json.loads(self._storage_path.read_text(encoding="utf-8"))
                for host_type, status_data in data.get("hosts", {}).items():
                    self._status[host_type] = HostStatus(**status_data)
                _log.info("host_limits_loaded count=%d", len(self._status))
        except Exception as e:
            _log.warning("host_limits_load_error %s", str(e))

    def _save(self) -> None:
        """Save host status to disk."""
        try:
            data = {"hosts": {k: asdict(v) for k, v in self._status.items()}}
            self._storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            _log.warning("host_limits_save_error %s", str(e))

    def get_status(self, host_type: str) -> HostStatus:
        """Get or create status for a host."""
        if host_type not in self._status:
            self._status[host_type] = HostStatus(host_type=host_type)
        status = self._status[host_type]
        status.reset_if_new_day()
        return status

    def record_download(self, host_type: str, bytes_downloaded: int) -> None:
        """Record a successful download."""
        status = self.get_status(host_type)
        status.bytes_downloaded_today += bytes_downloaded
        status.last_download = datetime.now().isoformat()
        status.consecutive_failures = 0

        # Check if approaching limit
        if host_type in HOSTS_WITH_LIMITS:
            limit_gb = HOSTS_WITH_LIMITS[host_type]["daily_limit_gb"]
            used_gb = status.bytes_downloaded_today / (1024 * 1024 * 1024)
            if used_gb >= limit_gb * 0.9:  # 90% of limit
                _log.warning("host_approaching_limit host=%s used=%.2fGB limit=%.2fGB",
                           host_type, used_gb, limit_gb)

        self._save()

    def record_error(self, host_type: str, error: str) -> None:
        """Record a download error."""
        status = self.get_status(host_type)
        status.last_error = error
        status.last_error_time = datetime.now().isoformat()
        status.consecutive_failures += 1

        # Check if it's a limit-related error
        if host_type in HOSTS_WITH_LIMITS:
            patterns = HOSTS_WITH_LIMITS[host_type]["error_patterns"]
            error_lower = error.lower()
            if any(p in error_lower for p in patterns):
                status.is_limited = True
                reset_hours = HOSTS_WITH_LIMITS[host_type]["limit_reset_hours"]
                from datetime import timedelta
                status.limit_reset_time = (datetime.now() + timedelta(hours=reset_hours)).isoformat()
                _log.warning("host_limit_reached host=%s reset=%s", host_type, status.limit_reset_time)

        self._save()

    def is_host_available(self, host_type: str) -> Tuple[bool, str]:
        """
        Check if a host is available for downloads.
        Returns: (is_available, reason)
        """
        status = self.get_status(host_type)

        # Check if limited
        if status.is_limited:
            if status.limit_reset_time:
                try:
                    reset_time = datetime.fromisoformat(status.limit_reset_time)
                    if datetime.now() >= reset_time:
                        # Limit should be reset
                        status.is_limited = False
                        status.limit_reset_time = None
                        self._save()
                    else:
                        return False, f"Daily limit reached, resets at {reset_time.strftime('%H:%M')}"
                except Exception:
                    pass
            else:
                return False, "Daily limit reached"

        # Check consecutive failures
        if status.consecutive_failures >= 5:
            return False, f"Too many consecutive failures ({status.consecutive_failures})"

        # Check daily usage
        if host_type in HOSTS_WITH_LIMITS:
            limit_gb = HOSTS_WITH_LIMITS[host_type]["daily_limit_gb"]
            used_gb = status.bytes_downloaded_today / (1024 * 1024 * 1024)
            if used_gb >= limit_gb:
                status.is_limited = True
                self._save()
                return False, f"Daily limit of {limit_gb}GB reached"

        return True, ""

    def get_remaining_quota(self, host_type: str) -> Optional[float]:
        """Get remaining download quota in GB, or None if unlimited."""
        if host_type not in HOSTS_WITH_LIMITS:
            return None

        status = self.get_status(host_type)
        limit_gb = HOSTS_WITH_LIMITS[host_type]["daily_limit_gb"]
        used_gb = status.bytes_downloaded_today / (1024 * 1024 * 1024)
        return max(0, limit_gb - used_gb)

    def reset_host(self, host_type: str) -> None:
        """Manually reset a host's status."""
        if host_type in self._status:
            del self._status[host_type]
            self._save()


class LinkValidator:
    """
    Validates download links before attempting download.
    Handles redirect pages and detects unavailable files.
    """

    # Known ad/spam domains to avoid
    AD_DOMAINS = {
        "bit.ly", "tinyurl.com", "adf.ly", "ouo.io", "bc.vc",
        "linkvertise.com", "shrinkme.io", "exe.io", "sub2unlock.com",
    }

    # Patterns for fake download buttons
    FAKE_BUTTON_PATTERNS = [
        r"onclick=['\"].*(?:pop|ad|banner|track)",
        r"href=['\"](?:javascript:|#|void)",
        r"class=['\"][^'\"]*(?:ad|banner|sponsor|popup)",
    ]

    def __init__(self) -> None:
        self._click_count: Dict[str, int] = {}  # Track clicks per URL

    def is_ad_link(self, url: str) -> bool:
        """Check if URL is likely an ad/tracking link."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            return domain in self.AD_DOMAINS
        except Exception:
            return False

    def validate_url(self, url: str) -> Tuple[bool, str]:
        """
        Validate a download URL.
        Returns: (is_valid, error_message)
        """
        if not url:
            return False, "Empty URL"

        if self.is_ad_link(url):
            return False, "URL appears to be an ad link"

        try:
            parsed = urlparse(url)
            if not parsed.scheme in ("http", "https"):
                return False, f"Invalid scheme: {parsed.scheme}"
            if not parsed.netloc:
                return False, "Missing domain"
            return True, ""
        except Exception as e:
            return False, str(e)

    def check_link_availability(self, url: str, timeout: int = 15) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check if a link is available by making a HEAD request.
        Returns: (is_available, error, metadata)
        """
        metadata: Dict[str, Any] = {}

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            req = urllib.request.Request(url, method="HEAD", headers=headers)

            with urllib.request.urlopen(req, timeout=timeout) as response:
                metadata["status_code"] = response.status
                metadata["content_type"] = response.headers.get("Content-Type", "")
                metadata["content_length"] = response.headers.get("Content-Length", "")

                # If we get HTML, the file might be behind a redirect page
                if "text/html" in metadata["content_type"]:
                    metadata["is_redirect_page"] = True

                return True, "", metadata

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False, "File not found (404)", {"status_code": 404}
            elif e.code == 403:
                return False, "Access denied (403)", {"status_code": 403}
            elif e.code == 429:
                return False, "Rate limited (429)", {"status_code": 429}
            return False, f"HTTP error: {e.code}", {"status_code": e.code}

        except Exception as e:
            return False, str(e), {}

    def handle_multi_click_link(self, url: str, max_clicks: int = 3) -> Tuple[str, bool]:
        """
        Handle links that require multiple clicks.
        Some sites show ads for first 1-2 clicks, then actual download.

        Returns: (final_url, was_redirected)
        """
        click_key = url
        current_clicks = self._click_count.get(click_key, 0)

        if current_clicks >= max_clicks:
            # Already clicked enough times
            return url, False

        self._click_count[click_key] = current_clicks + 1

        # TODO: This would need JavaScript execution for full support
        # For now, we just track the click count

        return url, False


class SmartDownloadSelector:
    """
    Intelligently selects the best download source and handles failures.
    """

    def __init__(self) -> None:
        self._limit_tracker = HostLimitTracker()
        self._link_validator = LinkValidator()

    def sort_by_priority(self, sources: List[DownloadSource]) -> List[DownloadSource]:
        """Sort download sources by priority."""
        def get_priority(source: DownloadSource) -> Tuple[int, int, bool]:
            # Consider host priority, availability, and reliability
            base_priority = HOST_PRIORITY.get(source.host_type, 50)

            # Penalize unavailable sources
            if not source.is_available:
                base_priority += 100

            # Penalize unreliable hosts
            if source.host_type in UNRELIABLE_HOSTS:
                base_priority += 20

            # Penalize hosts at their limit
            available, _ = self._limit_tracker.is_host_available(source.host_type)
            if not available:
                base_priority += 200

            return (base_priority, source.priority, not source.is_available)

        return sorted(sources, key=get_priority)

    def select_best_source(self, sources: List[DownloadSource]) -> Optional[DownloadSource]:
        """Select the best available download source."""
        sorted_sources = self.sort_by_priority(sources)

        for source in sorted_sources:
            # Validate URL
            valid, error = self._link_validator.validate_url(source.url)
            if not valid:
                source.is_available = False
                source.error = error
                continue

            # Check host availability
            available, reason = self._limit_tracker.is_host_available(source.host_type)
            if not available:
                source.is_available = False
                source.error = reason
                continue

            # Quick availability check
            available, error, metadata = self._link_validator.check_link_availability(source.url)
            if not available:
                source.is_available = False
                source.error = error
                continue

            source.last_checked = datetime.now().isoformat()
            return source

        return None

    def get_fallback_sources(
        self,
        sources: List[DownloadSource],
        exclude_host: str
    ) -> List[DownloadSource]:
        """Get alternative sources, excluding the failed host."""
        alternatives = [s for s in sources if s.host_type != exclude_host and s.is_available]
        return self.sort_by_priority(alternatives)

    def record_success(self, host_type: str, bytes_downloaded: int) -> None:
        """Record a successful download."""
        self._limit_tracker.record_download(host_type, bytes_downloaded)

    def record_failure(self, host_type: str, error: str) -> None:
        """Record a download failure."""
        self._limit_tracker.record_error(host_type, error)

    def get_host_status(self, host_type: str) -> HostStatus:
        """Get current status for a host."""
        return self._limit_tracker.get_status(host_type)

    def get_all_host_statuses(self) -> Dict[str, HostStatus]:
        """Get status for all tracked hosts."""
        return {ht: self._limit_tracker.get_status(ht) for ht in HOST_PRIORITY.keys()}

    def check_file_not_found(self, error: str) -> bool:
        """Check if error indicates file not found."""
        error_lower = error.lower()
        return any(re.search(p, error_lower) for p in FILE_NOT_FOUND_PATTERNS)


class RedirectHandler:
    """
    Handles redirect/confirm pages for various file hosts.
    """

    # Patterns for different types of redirect pages
    COUNTDOWN_PATTERNS = [
        r"var\s+seconds?\s*=\s*(\d+)",
        r"countdown\s*[=:]\s*(\d+)",
        r"timer\s*[=:]\s*(\d+)",
        r"wait\s+(\d+)\s+seconds?",
    ]

    DIRECT_LINK_PATTERNS = [
        r'href=["\']([^"\']+\.(?:zip|rar|7z|exe|apk|iso)[^"\']*)["\']',
        r'(https?://[^\s"\'<>]+\.(?:zip|rar|7z|exe|apk|iso)(?:\?[^\s"\'<>]*)?)',
        r'download[_-]?url\s*[=:]\s*["\']([^"\']+)["\']',
    ]

    def __init__(self) -> None:
        self._session_cookies: Dict[str, str] = {}

    def extract_direct_link(self, html_content: str, base_url: str) -> Optional[str]:
        """Extract direct download link from HTML content."""
        for pattern in self.DIRECT_LINK_PATTERNS:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches:
                url = match if isinstance(match, str) else match[0]

                # Skip obviously wrong URLs
                if any(skip in url.lower() for skip in [
                    "javascript:", "#", "void(0)", "facebook", "twitter",
                    "instagram", "adserver", "tracking", "banner"
                ]):
                    continue

                # Make absolute if needed
                if url.startswith("//"):
                    url = "https:" + url
                elif url.startswith("/"):
                    parsed = urlparse(base_url)
                    url = f"{parsed.scheme}://{parsed.netloc}{url}"

                return url

        return None

    def get_countdown_time(self, html_content: str) -> int:
        """Extract countdown/wait time from HTML content."""
        for pattern in self.COUNTDOWN_PATTERNS:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return 0

    def navigate_redirect(
        self,
        url: str,
        max_redirects: int = 5,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Tuple[str, str]:
        """
        Navigate through redirect pages to find the final download URL.

        Returns: (final_url, error)
        """
        current_url = url

        for step in range(max_redirects):
            if progress_callback:
                progress_callback(f"Navigating redirect {step + 1}/{max_redirects}")

            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,*/*",
                    "Referer": current_url,
                }

                if self._session_cookies:
                    headers["Cookie"] = "; ".join(
                        f"{k}={v}" for k, v in self._session_cookies.items()
                    )

                req = urllib.request.Request(current_url, headers=headers)

                with urllib.request.urlopen(req, timeout=30) as response:
                    # Store cookies
                    for header in response.headers.get_all("Set-Cookie", []):
                        match = re.match(r"([^=]+)=([^;]+)", header)
                        if match:
                            self._session_cookies[match.group(1)] = match.group(2)

                    content_type = response.headers.get("Content-Type", "").lower()

                    # If not HTML, it's the actual file
                    if "text/html" not in content_type:
                        return response.geturl(), ""

                    content = response.read().decode("utf-8", errors="ignore")

                    # Check for countdown
                    wait_time = self.get_countdown_time(content)
                    if wait_time > 0:
                        if progress_callback:
                            progress_callback(f"Waiting {wait_time}s for countdown...")
                        time.sleep(min(wait_time, 30))  # Cap at 30s

                    # Try to find direct link
                    direct_link = self.extract_direct_link(content, response.geturl())
                    if direct_link and direct_link != current_url:
                        current_url = direct_link
                        continue

                    # No more redirects found
                    return current_url, ""

            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return "", "File not found (404)"
                return "", f"HTTP error: {e.code}"
            except Exception as e:
                return "", str(e)

        return current_url, "Max redirects exceeded"


# Global instances
_selector: Optional[SmartDownloadSelector] = None
_redirect_handler: Optional[RedirectHandler] = None


def get_smart_selector() -> SmartDownloadSelector:
    """Get the global smart download selector."""
    global _selector
    if _selector is None:
        _selector = SmartDownloadSelector()
    return _selector


def get_redirect_handler() -> RedirectHandler:
    """Get the global redirect handler."""
    global _redirect_handler
    if _redirect_handler is None:
        _redirect_handler = RedirectHandler()
    return _redirect_handler


def get_host_priority(host_type: str) -> int:
    """Get priority for a host type (lower = better)."""
    return HOST_PRIORITY.get(host_type, 50)


def is_host_limited(host_type: str) -> Tuple[bool, str]:
    """Check if a host has reached its daily limit."""
    return get_smart_selector()._limit_tracker.is_host_available(host_type)
