"""7-Zip archive format handler."""

from pathlib import Path
from typing import List, Optional

from app.logging_utils import get_logger, kv

from .base import ArchiveInfo, ExtractionResult, FormatHandler, ProgressCallback

_log = get_logger("archive.7z")


class SevenZipHandler(FormatHandler):
    """Handler for 7-Zip archive format."""

    @property
    def name(self) -> str:
        return "7-Zip"

    @property
    def extensions(self) -> List[str]:
        return [".7z"]

    @property
    def magic_bytes(self) -> List[bytes]:
        return [b"7z\xbc\xaf\x27\x1c"]

    def is_available(self) -> bool:
        """Check if py7zr library is available."""
        try:
            import py7zr
            return True
        except ImportError:
            return False

    def get_missing_dependency_message(self) -> str:
        return (
            "7z extraction requires the 'py7zr' library. "
            "Install with: pip install py7zr"
        )

    def can_handle(self, path: Path) -> bool:
        """Check if file is a valid 7z archive."""
        if path.suffix.lower() == ".7z":
            return True

        # Check magic bytes
        try:
            with open(path, "rb") as f:
                header = f.read(6)
                return header == b"7z\xbc\xaf\x27\x1c"
        except Exception:
            return False

    def get_info(self, path: Path) -> ArchiveInfo:
        """Get 7z archive information."""
        info = ArchiveInfo(path=str(path))

        if not self.is_available():
            return info

        try:
            import py7zr
            with py7zr.SevenZipFile(path, "r") as sz:
                info.file_count = len(sz.getnames())
                info.is_encrypted = sz.needs_password()
                # Note: py7zr doesn't easily expose total uncompressed size
        except Exception as e:
            _log.debug("7z_info_error %s", kv(path=str(path), err=str(e)))

        return info

    def extract(
        self,
        path: Path,
        destination: Path,
        password: Optional[str] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        """Extract 7z archive."""
        if not self.is_available():
            return ExtractionResult(
                success=False,
                error=self.get_missing_dependency_message()
            )

        try:
            import py7zr

            with py7zr.SevenZipFile(
                path, "r",
                password=password if password else None
            ) as sz:
                names = sz.getnames()
                total = len(names)

                # py7zr extracts all at once
                sz.extractall(destination)

                # Calculate extracted size
                extracted_size = 0
                for name in names:
                    file_path = destination / name
                    if file_path.is_file():
                        extracted_size += file_path.stat().st_size

                if progress:
                    progress("Extraction complete", total, total)

                return ExtractionResult(
                    success=True,
                    extracted_path=str(destination),
                    file_count=total,
                    total_size=extracted_size,
                    password_used=password or "",
                )

        except Exception as e:
            error_str = str(e).lower()
            if "bad7z" in error_str or "invalid" in error_str:
                return ExtractionResult(
                    success=False,
                    error="Invalid or corrupted 7z file"
                )
            if "password" in error_str:
                return ExtractionResult(
                    success=False,
                    error="Incorrect password or password required"
                )
            return ExtractionResult(success=False, error=str(e))

    def try_password(self, path: Path, password: str) -> bool:
        """Test if password works for 7z archive."""
        if not self.is_available():
            return False

        try:
            import py7zr
            with py7zr.SevenZipFile(
                path, "r",
                password=password if password else None
            ) as sz:
                # Just opening successfully is enough
                return True
        except Exception:
            pass
        return False
