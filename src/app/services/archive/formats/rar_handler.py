"""RAR archive format handler."""

from pathlib import Path
from typing import List, Optional

from app.logging_utils import get_logger, kv

from .base import ArchiveInfo, ExtractionResult, FormatHandler, ProgressCallback

_log = get_logger("archive.rar")


class RarHandler(FormatHandler):
    """Handler for RAR archive format."""

    @property
    def name(self) -> str:
        return "RAR"

    @property
    def extensions(self) -> List[str]:
        return [".rar"]

    @property
    def magic_bytes(self) -> List[bytes]:
        return [b"Rar!\x1a\x07"]

    def is_available(self) -> bool:
        """Check if rarfile library is available."""
        try:
            import rarfile
            return True
        except ImportError:
            return False

    def get_missing_dependency_message(self) -> str:
        return (
            "RAR extraction requires the 'rarfile' library. "
            "Install with: pip install rarfile"
        )

    def can_handle(self, path: Path) -> bool:
        """Check if file is a valid RAR archive."""
        name_lower = path.name.lower()

        # Check extension
        if path.suffix.lower() == ".rar":
            return True

        # Check for multipart RAR patterns
        if ".part" in name_lower and ".rar" in name_lower:
            return True
        if name_lower.endswith((".r00", ".r01")):
            return True

        # Check magic bytes
        try:
            with open(path, "rb") as f:
                header = f.read(6)
                return header == b"Rar!\x1a\x07"
        except Exception:
            return False

    def get_info(self, path: Path) -> ArchiveInfo:
        """Get RAR archive information."""
        info = ArchiveInfo(path=str(path))

        if not self.is_available():
            return info

        try:
            import rarfile
            with rarfile.RarFile(path, "r") as rf:
                info.file_count = len(rf.namelist())
                info.total_size = sum(ri.file_size for ri in rf.infolist())
                info.is_encrypted = rf.needs_password()
        except Exception as e:
            _log.debug("rar_info_error %s", kv(path=str(path), err=str(e)))

        return info

    def extract(
        self,
        path: Path,
        destination: Path,
        password: Optional[str] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        """Extract RAR archive."""
        if not self.is_available():
            return ExtractionResult(
                success=False,
                error=self.get_missing_dependency_message()
            )

        try:
            import rarfile

            with rarfile.RarFile(path, "r") as rf:
                if password:
                    rf.setpassword(password)

                names = rf.namelist()
                total = len(names)
                extracted_size = 0

                for i, name in enumerate(names):
                    if progress:
                        progress(name, i + 1, total)

                    try:
                        rf.extract(name, destination)
                        info = rf.getinfo(name)
                        extracted_size += info.file_size
                    except Exception as e:
                        _log.warning(
                            "rar_extract_file_error %s",
                            kv(name=name, err=str(e))
                        )

                return ExtractionResult(
                    success=True,
                    extracted_path=str(destination),
                    file_count=total,
                    total_size=extracted_size,
                    password_used=password or "",
                )

        except Exception as e:
            error_str = str(e).lower()
            if "badrarf" in error_str or "invalid" in error_str:
                return ExtractionResult(
                    success=False,
                    error="Invalid or corrupted RAR file"
                )
            if "password" in error_str:
                return ExtractionResult(
                    success=False,
                    error="Incorrect password"
                )
            return ExtractionResult(success=False, error=str(e))

    def try_password(self, path: Path, password: str) -> bool:
        """Test if password works for RAR archive."""
        if not self.is_available():
            return False

        try:
            import rarfile
            with rarfile.RarFile(path, "r") as rf:
                rf.setpassword(password)
                names = rf.namelist()
                if names:
                    rf.read(names[0])
                    return True
        except Exception:
            pass
        return False
