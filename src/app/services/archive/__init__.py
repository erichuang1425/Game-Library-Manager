"""Archive extraction package - modular archive handling.

This package splits archive_extractor.py (853 lines) into focused modules:
- models.py: Data classes, enums, constants (~90 lines)
- detection.py: Format detection, multipart handling (~180 lines)
- passwords.py: Password management (~120 lines)
- extraction.py: Format-specific extraction (~220 lines)
- utils.py: Scanning, title parsing, utilities (~210 lines)

Total: ~820 lines with improved organization
"""

# Models and types
from .models import (
    ArchiveFormat,
    ExtractionResult,
    ArchiveInfo,
    ScannedArchive,
    ProgressCallback,
    COMMON_PASSWORDS,
    MULTIPART_PATTERNS,
    ARCHIVE_EXTENSIONS,
)

# Detection
from .detection import (
    detect_format,
    get_archive_info,
    find_first_part,
    find_all_parts,
)

# Password management
from .passwords import (
    try_passwords,
    load_custom_passwords,
    save_custom_passwords,
    add_custom_password,
    remove_custom_password,
    get_custom_passwords,
    set_custom_passwords,
    get_all_passwords,
)

# Extraction
from .extraction import (
    extract_zip,
    extract_rar,
    extract_7z,
    extract_archive,
)

# Utilities
from .utils import (
    find_executables,
    find_save_folder,
    scan_for_archives,
    parse_archive_filename,
    normalize_title,
    calculate_title_similarity,
)

__all__ = [
    # Models
    "ArchiveFormat",
    "ExtractionResult",
    "ArchiveInfo",
    "ScannedArchive",
    "ProgressCallback",
    "COMMON_PASSWORDS",
    "MULTIPART_PATTERNS",
    "ARCHIVE_EXTENSIONS",
    # Detection
    "detect_format",
    "get_archive_info",
    "find_first_part",
    "find_all_parts",
    # Passwords
    "try_passwords",
    "load_custom_passwords",
    "save_custom_passwords",
    "add_custom_password",
    "remove_custom_password",
    "get_custom_passwords",
    "set_custom_passwords",
    "get_all_passwords",
    # Extraction
    "extract_zip",
    "extract_rar",
    "extract_7z",
    "extract_archive",
    # Utilities
    "find_executables",
    "find_save_folder",
    "scan_for_archives",
    "parse_archive_filename",
    "normalize_title",
    "calculate_title_similarity",
]
