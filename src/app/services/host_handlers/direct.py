from __future__ import annotations
"""
Direct download handler for generic HTTP/HTTPS URLs.
"""

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote

from .base import HostHandler, ResolvedLink, DownloadResult, ProgressCallback, register_handler


@register_handler
class DirectDownloadHandler(HostHandler):
    """Handler for direct HTTP/HTTPS download links."""

    SUPPORTED_DOMAINS = ["direct"]  # Special marker
    DISPLAY_NAME = "Direct Download"
    REQUIRES_AUTH = False

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Direct handler can handle any http(s) URL as fallback."""
        try:
            parsed = urlparse(url)
            return parsed.scheme in ("http", "https")
        except Exception:
            return False

    def resolve_link(self, url: str) -> ResolvedLink:
        """For direct links, the URL is already the download URL."""
        try:
            parsed = urlparse(url)
            filename = unquote(Path(parsed.path).name) or "download"

            return ResolvedLink(
                direct_url=url,
                filename=filename,
            )
        except Exception as e:
            return ResolvedLink(direct_url="", error=str(e))
