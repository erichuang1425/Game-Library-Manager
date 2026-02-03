"""
Archive extraction package for Game Library Manager.

Provides a modular architecture with pluggable format handlers for
ZIP, RAR, and 7z archives.

Usage:
    from app.services.archive import extract_archive, get_archive_info

    # Extract an archive
    result = extract_archive(Path("game.zip"), Path("/dest"))
    if result.success:
        print(f"Extracted {result.file_count} files")

    # Get archive info without extracting
    info = get_archive_info(Path("game.rar"))
    print(f"Encrypted: {info.is_encrypted}")

Package Structure:
    archive/
    ├── __init__.py         - Package exports (this file)
    ├── extractor.py        - Main ArchiveExtractor orchestrator
    ├── utils.py            - Shared utilities (passwords, multipart, etc.)
    └── formats/
        ├── base.py         - FormatHandler ABC
        ├── zip_handler.py  - ZIP format handler
        ├── rar_handler.py  - RAR format handler (requires rarfile)
        └── sevenz_handler.py - 7z format handler (requires py7zr)
"""

# Core classes and functions
from .extractor import (
    ArchiveExtractor,
    ArchiveFormat,
    detect_format,
    extract_archive,
    get_archive_info,
    get_extractor,
    scan_for_archives,
    try_passwords,
)

# Format handlers
from .formats import (
    ArchiveInfo,
    ExtractionResult,
    FormatHandler,
    ProgressCallback,
    RarHandler,
    SevenZipHandler,
    ZipHandler,
)

# Utilities
from .utils import (
    ARCHIVE_EXTENSIONS,
    COMMON_PASSWORDS,
    ScannedArchive,
    add_custom_password,
    calculate_title_similarity,
    find_all_parts,
    find_executables,
    find_first_part,
    find_save_folder,
    get_all_passwords,
    get_custom_passwords,
    is_later_part,
    is_multipart,
    load_custom_passwords,
    normalize_title,
    parse_archive_filename,
    remove_custom_password,
    save_custom_passwords,
    set_custom_passwords,
)

__all__ = [
    # Main extractor
    "ArchiveExtractor",
    "ArchiveFormat",
    "detect_format",
    "extract_archive",
    "get_archive_info",
    "get_extractor",
    "scan_for_archives",
    "try_passwords",
    # Format handlers
    "ArchiveInfo",
    "ExtractionResult",
    "FormatHandler",
    "ProgressCallback",
    "ZipHandler",
    "RarHandler",
    "SevenZipHandler",
    # Utilities
    "ARCHIVE_EXTENSIONS",
    "COMMON_PASSWORDS",
    "ScannedArchive",
    "add_custom_password",
    "calculate_title_similarity",
    "find_all_parts",
    "find_executables",
    "find_first_part",
    "find_save_folder",
    "get_all_passwords",
    "get_custom_passwords",
    "is_later_part",
    "is_multipart",
    "load_custom_passwords",
    "normalize_title",
    "parse_archive_filename",
    "remove_custom_password",
    "save_custom_passwords",
    "set_custom_passwords",
]
