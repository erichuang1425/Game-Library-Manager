"""
Host handlers for various file hosting services.

Each handler provides methods to:
- Resolve direct download links from page URLs
- Handle authentication if required
- Download files with progress reporting
- Check file availability

Supported hosts (in priority order):
1. Buzzheavier - Fast, no limits
2. Gofile - Reliable, minimal limits
3. Pixeldrain - Good but has daily limits (~6GB)
4. MEGA - Good but has transfer quota (~5GB/6h)
5. Google Drive - Reliable but can have access issues
6. MediaFire - Generally reliable
7. Workupload - Decent, can have wait times
8. Anonfiles - Unreliable, often down
"""

from .base import (
    HostHandler,
    HostHandlerError,
    ResolvedLink,
    DownloadResult,
    ProgressCallback,
    get_handler_for_url,
    get_handler_for_host,
    register_handler,
)
from .direct import DirectDownloadHandler
from .mega import MegaHandler
from .gdrive import GDriveHandler
from .pixeldrain import PixeldrainHandler
from .gofile import GofileHandler
from .buzzheavier import BuzzheavierHandler
from .mediafire import MediafireHandler
from .workupload import WorkuploadHandler
from .anonfiles import AnonfilesHandler

__all__ = [
    # Base classes and utilities
    "HostHandler",
    "HostHandlerError",
    "ResolvedLink",
    "DownloadResult",
    "ProgressCallback",
    "get_handler_for_url",
    "get_handler_for_host",
    "register_handler",
    # Handlers (in priority order)
    "BuzzheavierHandler",
    "GofileHandler",
    "PixeldrainHandler",
    "MegaHandler",
    "GDriveHandler",
    "MediafireHandler",
    "WorkuploadHandler",
    "AnonfilesHandler",
    "DirectDownloadHandler",
]


def get_all_handlers() -> list[type[HostHandler]]:
    """Get all registered handlers sorted by priority."""
    handlers = [
        BuzzheavierHandler,
        GofileHandler,
        PixeldrainHandler,
        MegaHandler,
        GDriveHandler,
        MediafireHandler,
        WorkuploadHandler,
        AnonfilesHandler,
        DirectDownloadHandler,
    ]
    return sorted(handlers, key=lambda h: h.PRIORITY)


def get_handler_priority(host_type: str) -> int:
    """Get priority for a host type (lower = higher priority)."""
    priority_map = {
        "buzzheavier": 1,
        "gofile": 2,
        "pixeldrain": 3,
        "mega": 4,
        "gdrive": 5,
        "mediafire": 6,
        "workupload": 7,
        "anonfiles": 8,
        "direct": 99,
    }
    return priority_map.get(host_type, 50)
