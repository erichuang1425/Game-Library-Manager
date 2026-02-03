"""
Archive extraction orchestrator.

Main entry point for archive operations. Automatically selects the
appropriate format handler based on file type.
"""

from enum import Enum
from pathlib import Path
from typing import List, Optional, Set

from app.logging_utils import get_logger, kv

from .formats import (
    ArchiveInfo,
    ExtractionResult,
    FormatHandler,
    ProgressCallback,
    RarHandler,
    SevenZipHandler,
    ZipHandler,
)
from .utils import (
    ARCHIVE_EXTENSIONS,
    MULTIPART_FIRST_PATTERNS,
    ScannedArchive,
    find_all_parts,
    find_first_part,
    get_all_passwords,
    is_later_part,
    is_multipart,
    parse_archive_filename,
)

_log = get_logger("archive.extractor")


class ArchiveFormat(Enum):
    """Supported archive formats."""
    ZIP = "zip"
    RAR = "rar"
    SEVEN_ZIP = "7z"
    UNKNOWN = "unknown"


class ArchiveExtractor:
    """
    Central archive extraction service.

    Automatically detects format and delegates to appropriate handler.
    Supports password-protected and multipart archives.
    """

    def __init__(self) -> None:
        """Initialize with all available format handlers."""
        self._handlers: List[FormatHandler] = [
            ZipHandler(),
            RarHandler(),
            SevenZipHandler(),
        ]

    def detect_format(self, path: Path) -> ArchiveFormat:
        """
        Detect archive format from extension and magic bytes.

        Args:
            path: Path to archive file

        Returns:
            Detected ArchiveFormat or UNKNOWN
        """
        suffix = path.suffix.lower()

        # Quick extension check
        format_map = {
            ".zip": ArchiveFormat.ZIP,
            ".rar": ArchiveFormat.RAR,
            ".7z": ArchiveFormat.SEVEN_ZIP,
        }

        if suffix in format_map:
            return format_map[suffix]

        # Check by handler capability
        for handler in self._handlers:
            if handler.can_handle(path):
                if isinstance(handler, ZipHandler):
                    return ArchiveFormat.ZIP
                elif isinstance(handler, RarHandler):
                    return ArchiveFormat.RAR
                elif isinstance(handler, SevenZipHandler):
                    return ArchiveFormat.SEVEN_ZIP

        return ArchiveFormat.UNKNOWN

    def get_handler(self, path: Path) -> Optional[FormatHandler]:
        """
        Get the appropriate handler for an archive.

        Args:
            path: Path to archive file

        Returns:
            FormatHandler instance or None if unsupported
        """
        for handler in self._handlers:
            if handler.can_handle(path):
                return handler
        return None

    def get_info(self, path: Path) -> ArchiveInfo:
        """
        Get information about an archive.

        Args:
            path: Path to archive file

        Returns:
            ArchiveInfo with file details
        """
        handler = self.get_handler(path)
        if handler:
            return handler.get_info(path)
        return ArchiveInfo(path=str(path))

    def extract(
        self,
        path: Path,
        destination: Optional[Path] = None,
        password: Optional[str] = None,
        try_common_passwords: bool = True,
        progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        """
        Extract an archive to destination.

        Args:
            path: Path to archive file
            destination: Extraction destination (default: same dir as archive)
            password: Password for encrypted archives
            try_common_passwords: Try common F95zone passwords if encrypted
            progress: Progress callback

        Returns:
            ExtractionResult with extraction status
        """
        path = Path(path)

        if not path.exists():
            return ExtractionResult(
                success=False,
                error=f"Archive not found: {path}"
            )

        # Get handler
        handler = self.get_handler(path)
        if not handler:
            return ExtractionResult(
                success=False,
                error="Unknown or unsupported archive format"
            )

        # Check availability
        if not handler.is_available():
            return ExtractionResult(
                success=False,
                error=handler.get_missing_dependency_message()
            )

        # Set destination
        if destination is None:
            destination = path.parent / path.stem
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)

        fmt = self.detect_format(path)
        _log.info("extract_start %s", kv(
            path=str(path),
            format=fmt.value,
            dest=str(destination),
            handler=handler.name
        ))

        # Handle multipart archives
        if is_multipart(path):
            first_part = find_first_part(path)
            if first_part != path:
                _log.info("multipart_using_first %s", kv(first=str(first_part)))
                path = first_part

        # Try password if needed
        info = handler.get_info(path)
        if info.is_encrypted and not password and try_common_passwords:
            password = self._find_password(handler, path)
            if password:
                _log.info("password_found %s", kv(password="***"))

        # Extract
        result = handler.extract(path, destination, password, progress)

        if result.success:
            _log.info("extract_complete %s", kv(
                files=result.file_count,
                size=result.total_size,
                dest=result.extracted_path
            ))
        else:
            _log.warning("extract_failed %s", kv(error=result.error))

        return result

    def _find_password(
        self,
        handler: FormatHandler,
        path: Path
    ) -> Optional[str]:
        """Try common passwords to find one that works."""
        for pwd in get_all_passwords():
            if handler.try_password(path, pwd):
                return pwd
        return None

    def scan_folder(
        self,
        folder: Path,
        recursive: bool = True,
    ) -> List[ScannedArchive]:
        """
        Scan a folder for archive files.

        Groups multipart archives and returns only first parts.

        Args:
            folder: Folder to scan
            recursive: Whether to scan subdirectories

        Returns:
            List of ScannedArchive entries
        """
        archives: List[ScannedArchive] = []
        pattern = "**/*" if recursive else "*"

        for item in folder.glob(pattern):
            if not item.is_file():
                continue

            # Skip later parts of multipart archives
            if is_later_part(item):
                continue

            # Get handler
            handler = self.get_handler(item)
            if not handler:
                continue

            # Detect multipart
            multipart = is_multipart(item) or any(
                p.search(item.name) for p in MULTIPART_FIRST_PATTERNS
            )

            # Also check if next RAR part exists
            if item.suffix.lower() == ".rar" and not multipart:
                r00_path = item.parent / (item.stem + ".r00")
                if r00_path.exists():
                    multipart = True

            # Get parts and total size
            if multipart:
                parts = find_all_parts(item)
                total_size = sum(
                    p.stat().st_size for p in parts if p.exists()
                )
            else:
                parts = []
                total_size = item.stat().st_size

            # Parse filename
            title, version = parse_archive_filename(item.name)

            # Get encryption status
            info = handler.get_info(item)

            archive = ScannedArchive(
                path=item,
                name=item.name,
                format_name=handler.name,
                size=total_size,
                is_multipart=multipart,
                parts=parts,
                is_encrypted=info.is_encrypted,
                detected_title=title,
                detected_version=version,
            )
            archives.append(archive)

        return sorted(archives, key=lambda a: a.detected_title.lower())


# Module-level convenience functions

_extractor: Optional[ArchiveExtractor] = None


def get_extractor() -> ArchiveExtractor:
    """Get the global extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = ArchiveExtractor()
    return _extractor


def extract_archive(
    path: Path,
    destination: Optional[Path] = None,
    password: Optional[str] = None,
    try_common_passwords: bool = True,
    progress: Optional[ProgressCallback] = None,
) -> ExtractionResult:
    """
    Convenience function to extract an archive.

    See ArchiveExtractor.extract() for details.
    """
    return get_extractor().extract(
        path, destination, password, try_common_passwords, progress
    )


def detect_format(path: Path) -> ArchiveFormat:
    """Convenience function to detect archive format."""
    return get_extractor().detect_format(path)


def get_archive_info(path: Path) -> ArchiveInfo:
    """Convenience function to get archive info."""
    return get_extractor().get_info(path)


def scan_for_archives(
    folder: Path,
    recursive: bool = True,
) -> List[ScannedArchive]:
    """Convenience function to scan folder for archives."""
    return get_extractor().scan_folder(folder, recursive)


def try_passwords(
    path: Path,
    fmt: Optional[ArchiveFormat] = None,
    passwords: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Try passwords to find one that works for an encrypted archive.

    Args:
        path: Path to archive file
        fmt: Archive format (auto-detected if not provided)
        passwords: List of passwords to try (uses common + custom if not provided)

    Returns:
        Working password or None
    """
    extractor = get_extractor()
    handler = extractor.get_handler(path)

    if not handler:
        return None

    if passwords is None:
        passwords = get_all_passwords()

    for pwd in passwords:
        if handler.try_password(path, pwd):
            return pwd

    return None
