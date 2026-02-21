"""Archive models and constants."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, List

# Progress callback type
ProgressCallback = Callable[[str, int, int], None]  # filename, current, total


class ArchiveFormat(Enum):
    """Supported archive formats."""
    ZIP = "zip"
    RAR = "rar"
    SEVEN_ZIP = "7z"
    UNKNOWN = "unknown"


@dataclass
class ExtractionResult:
    """Result of archive extraction."""
    success: bool
    extracted_path: str = ""
    file_count: int = 0
    total_size: int = 0
    error: str = ""
    password_used: str = ""


@dataclass
class ArchiveInfo:
    """Information about an archive."""
    path: str
    format: ArchiveFormat
    is_encrypted: bool = False
    is_multipart: bool = False
    part_number: int = 0
    total_parts: int = 0
    file_count: int = 0
    total_size: int = 0
    first_part_path: str = ""


@dataclass
class ScannedArchive:
    """Represents a scanned archive file."""
    path: Path
    name: str  # Display name (from filename)
    format: ArchiveFormat
    size: int  # Total size in bytes (for multi-part, sum of all parts)
    is_multipart: bool = False
    parts: List[Path] = field(default_factory=list)
    is_encrypted: bool = False
    # For matching
    detected_title: str = ""
    detected_version: str = ""


# Common passwords used on F95zone
COMMON_PASSWORDS = [
    "f95zone",
    "f95",
    "www.f95zone.to",
    "f95zone.to",
    "www.f95zone.com",
    "f95zone.com",
    "",  # No password
]

# Archive format patterns for multipart detection
MULTIPART_PATTERNS = {
    # .part1.rar, .part01.rar, etc.
    "rar_part": re.compile(r"\.part(\d+)\.rar$", re.IGNORECASE),
    # .r00, .r01, etc.
    "rar_rxx": re.compile(r"\.r(\d{2,})$", re.IGNORECASE),
    # .001, .002, etc.
    "split": re.compile(r"\.(\d{3})$"),
    # .zip.001, .zip.002, etc.
    "zip_split": re.compile(r"\.zip\.(\d{3})$", re.IGNORECASE),
    # .7z.001, .7z.002, etc.
    "7z_split": re.compile(r"\.7z\.(\d{3})$", re.IGNORECASE),
}

# Patterns for first parts of multipart archives
MULTIPART_FIRST_PATTERNS = [
    re.compile(r"\.part1\.rar$", re.IGNORECASE),
    re.compile(r"\.zip\.001$", re.IGNORECASE),
    re.compile(r"\.7z\.001$", re.IGNORECASE),
]

# Archive extensions for scanning
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}
