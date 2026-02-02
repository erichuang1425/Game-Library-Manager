"""
Host handlers for various file hosting services.

Each handler provides methods to:
- Resolve direct download links from page URLs
- Handle authentication if required
- Download files with progress reporting
"""

from .base import HostHandler, HostHandlerError, get_handler_for_url, get_handler_for_host
from .direct import DirectDownloadHandler
from .mega import MegaHandler
from .gdrive import GDriveHandler
from .pixeldrain import PixeldrainHandler
from .gofile import GofileHandler

__all__ = [
    "HostHandler",
    "HostHandlerError",
    "get_handler_for_url",
    "get_handler_for_host",
    "DirectDownloadHandler",
    "MegaHandler",
    "GDriveHandler",
    "PixeldrainHandler",
    "GofileHandler",
]
