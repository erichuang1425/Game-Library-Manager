"""
Centralized HTTP utilities for consistent network operations.

This module provides shared constants and utilities for HTTP operations across
the application, eliminating duplicate User-Agent strings and download logic.
"""

from __future__ import annotations

import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from app.logging_utils import get_logger

_log = get_logger("http_utils")


# ============================================================================
# Constants
# ============================================================================

# Standard User-Agent string - use this everywhere instead of hardcoding
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Short version for simple requests
USER_AGENT_SHORT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Download chunk size in bytes
CHUNK_SIZE = 8192

# Default timeout in seconds
DEFAULT_TIMEOUT = 30

# Extended timeout for large files
EXTENDED_TIMEOUT = 60


# ============================================================================
# Type Definitions
# ============================================================================

# Progress callback: (bytes_downloaded, bytes_total, speed_bps) -> None
ProgressCallback = Callable[[int, int, float], None]


# ============================================================================
# HTTP Error Handling
# ============================================================================

# Error code to (message, is_retriable) mapping
HTTP_ERROR_MAP: Dict[int, Tuple[str, bool]] = {
    400: ("Bad request", False),
    401: ("Authentication required", False),
    403: ("Access denied", False),
    404: ("File not found", False),
    410: ("File no longer available", False),
    429: ("Rate limited - please try again later", True),
    500: ("Server error", True),
    502: ("Bad gateway", True),
    503: ("Service unavailable", True),
    504: ("Gateway timeout", True),
}


def handle_http_error(error: urllib.error.HTTPError) -> Tuple[bool, str]:
    """
    Standardized HTTP error handling.

    Args:
        error: The HTTPError to handle

    Returns:
        Tuple of (is_retriable, error_message)
    """
    if error.code in HTTP_ERROR_MAP:
        message, retriable = HTTP_ERROR_MAP[error.code]
        return retriable, message
    return False, f"HTTP error {error.code}"


def is_retriable_error(error: Exception) -> bool:
    """
    Check if an error is retriable.

    Args:
        error: The exception to check

    Returns:
        True if the operation should be retried
    """
    if isinstance(error, urllib.error.HTTPError):
        retriable, _ = handle_http_error(error)
        return retriable
    if isinstance(error, urllib.error.URLError):
        # Network errors are usually retriable
        reason = str(error.reason).lower()
        return any(
            term in reason
            for term in ["timeout", "connection", "reset", "temporary"]
        )
    return False


# ============================================================================
# Request Creation
# ============================================================================

def create_request(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    method: str = "GET",
) -> urllib.request.Request:
    """
    Create a request with standard headers.

    Args:
        url: The URL to request
        headers: Additional headers to include
        method: HTTP method (GET, POST, HEAD, etc.)

    Returns:
        Configured Request object
    """
    default_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }
    if headers:
        default_headers.update(headers)
    return urllib.request.Request(url, headers=default_headers, method=method)


def fetch_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> bytes:
    """
    Fetch URL content.

    Args:
        url: URL to fetch
        headers: Optional additional headers
        timeout: Request timeout in seconds

    Returns:
        Response content as bytes

    Raises:
        urllib.error.HTTPError: On HTTP errors
        urllib.error.URLError: On network errors
    """
    req = create_request(url, headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_url_text(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = DEFAULT_TIMEOUT,
    encoding: str = "utf-8",
) -> str:
    """
    Fetch URL content as text.

    Args:
        url: URL to fetch
        headers: Optional additional headers
        timeout: Request timeout in seconds
        encoding: Text encoding

    Returns:
        Response content as string
    """
    data = fetch_url(url, headers, timeout)
    return data.decode(encoding)


def check_url_availability(
    url: str,
    timeout: int = 15,
) -> Tuple[bool, str]:
    """
    Check if a URL is available without downloading it.

    Args:
        url: URL to check
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_available, error_message)
    """
    try:
        req = create_request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout):
            return True, ""
    except urllib.error.HTTPError as e:
        _, message = handle_http_error(e)
        return False, message
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}"
    except Exception as e:
        return False, str(e)


# ============================================================================
# Download Operations
# ============================================================================

def download_file(
    url: str,
    destination: Path,
    filename: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    timeout: int = EXTENDED_TIMEOUT,
    chunk_size: int = CHUNK_SIZE,
) -> Tuple[bool, str, int]:
    """
    Download a file with progress reporting.

    Args:
        url: URL to download from
        destination: Directory to save file (or full path if filename not provided)
        filename: Optional filename (derived from URL if not provided)
        headers: Optional additional headers
        progress_callback: Optional callback for progress updates
        timeout: Request timeout in seconds
        chunk_size: Size of download chunks in bytes

    Returns:
        Tuple of (success, file_path_or_error, bytes_downloaded)
    """
    try:
        req = create_request(url, headers)

        with urllib.request.urlopen(req, timeout=timeout) as response:
            # Get file size
            content_length = response.headers.get("Content-Length")
            total_size = int(content_length) if content_length else 0

            # Determine filename
            if not filename:
                # Try Content-Disposition header
                content_disp = response.headers.get("Content-Disposition", "")
                if "filename=" in content_disp:
                    import re
                    from urllib.parse import unquote

                    match = re.search(r'filename[*]?=["\']?([^"\';\n]+)', content_disp)
                    if match:
                        filename = unquote(match.group(1).strip())

            if not filename:
                # Derive from URL
                from urllib.parse import urlparse, unquote

                filename = unquote(Path(urlparse(url).path).name) or "download"

            # Ensure destination directory exists
            if destination.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                file_path = destination / filename
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                file_path = destination

            # Download with progress
            bytes_downloaded = 0
            start_time = time.time()

            with open(file_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_downloaded += len(chunk)

                    if progress_callback:
                        elapsed = time.time() - start_time
                        speed = bytes_downloaded / elapsed if elapsed > 0 else 0
                        progress_callback(bytes_downloaded, total_size, speed)

            return True, str(file_path), bytes_downloaded

    except urllib.error.HTTPError as e:
        _, message = handle_http_error(e)
        return False, message, 0
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}", 0
    except Exception as e:
        return False, str(e), 0


def download_with_retry(
    url: str,
    destination: Path,
    filename: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    progress_callback: Optional[ProgressCallback] = None,
    timeout: int = EXTENDED_TIMEOUT,
    max_retries: int = 3,
    retry_delay: float = 1.0,
) -> Tuple[bool, str, int]:
    """
    Download a file with automatic retry on retriable errors.

    Args:
        url: URL to download from
        destination: Directory to save file
        filename: Optional filename
        headers: Optional additional headers
        progress_callback: Optional callback for progress updates
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_delay: Initial delay between retries (doubles each attempt)

    Returns:
        Tuple of (success, file_path_or_error, bytes_downloaded)
    """
    last_error = ""
    delay = retry_delay

    for attempt in range(max_retries + 1):
        success, result, size = download_file(
            url,
            destination,
            filename,
            headers,
            progress_callback,
            timeout,
        )

        if success:
            return True, result, size

        last_error = result

        # Check if we should retry
        if attempt < max_retries:
            # Simple heuristic for retriable errors
            retriable_terms = ["timeout", "rate limit", "502", "503", "504", "server error"]
            should_retry = any(term in last_error.lower() for term in retriable_terms)

            if should_retry:
                _log.info(
                    "download_retry attempt=%d delay=%.1f error=%s",
                    attempt + 1,
                    delay,
                    last_error,
                )
                time.sleep(delay)
                delay *= 2  # Exponential backoff
                continue

            # Non-retriable error
            break

    return False, last_error, 0


# ============================================================================
# Utility Functions
# ============================================================================

def format_size(bytes_val: int) -> str:
    """
    Format bytes as human-readable size.

    Args:
        bytes_val: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 MB")
    """
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"


def format_speed(bps: float) -> str:
    """
    Format speed as human-readable.

    Args:
        bps: Speed in bytes per second

    Returns:
        Formatted string (e.g., "1.5 MB/s")
    """
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    else:
        return f"{bps / (1024 * 1024):.1f} MB/s"


def format_eta(seconds: float) -> str:
    """
    Format ETA as human-readable.

    Args:
        seconds: Remaining time in seconds

    Returns:
        Formatted string (e.g., "5m 30s")
    """
    if seconds <= 0:
        return "--:--"
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds / 3600)
        mins = int((seconds % 3600) / 60)
        return f"{hours}h {mins}m"
