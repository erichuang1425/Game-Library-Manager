"""ZIP archive format handler."""

import zipfile
from pathlib import Path
from typing import List, Optional

from app.logging_utils import get_logger, kv

from .base import ArchiveInfo, ExtractionResult, FormatHandler, ProgressCallback

_log = get_logger("archive.zip")


class ZipHandler(FormatHandler):
    """Handler for ZIP archive format."""

    @property
    def name(self) -> str:
        return "ZIP"

    @property
    def extensions(self) -> List[str]:
        return [".zip"]

    @property
    def magic_bytes(self) -> List[bytes]:
        return [b"PK\x03\x04"]

    def can_handle(self, path: Path) -> bool:
        """Check if file is a valid ZIP archive."""
        if path.suffix.lower() == ".zip":
            return True

        # Check magic bytes
        try:
            with open(path, "rb") as f:
                header = f.read(4)
                return header == b"PK\x03\x04"
        except Exception:
            return False

    def get_info(self, path: Path) -> ArchiveInfo:
        """Get ZIP archive information."""
        info = ArchiveInfo(path=str(path))

        try:
            with zipfile.ZipFile(path, "r") as zf:
                info.file_count = len(zf.namelist())
                info.total_size = sum(zi.file_size for zi in zf.infolist())

                # Check for encryption
                for zi in zf.infolist():
                    if zi.flag_bits & 0x1:
                        info.is_encrypted = True
                        break

        except Exception as e:
            _log.debug("zip_info_error %s", kv(path=str(path), err=str(e)))

        return info

    def extract(
        self,
        path: Path,
        destination: Path,
        password: Optional[str] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> ExtractionResult:
        """Extract ZIP archive."""
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                total = len(names)
                extracted_size = 0

                for i, name in enumerate(names):
                    if progress:
                        progress(name, i + 1, total)

                    try:
                        zf.extract(
                            name,
                            destination,
                            pwd=password.encode() if password else None
                        )
                        info = zf.getinfo(name)
                        extracted_size += info.file_size
                    except Exception as e:
                        _log.warning(
                            "zip_extract_file_error %s",
                            kv(name=name, err=str(e))
                        )

                return ExtractionResult(
                    success=True,
                    extracted_path=str(destination),
                    file_count=total,
                    total_size=extracted_size,
                    password_used=password or "",
                )

        except zipfile.BadZipFile:
            return ExtractionResult(
                success=False,
                error="Invalid or corrupted ZIP file"
            )
        except RuntimeError as e:
            if "password" in str(e).lower():
                return ExtractionResult(
                    success=False,
                    error="Incorrect password"
                )
            return ExtractionResult(success=False, error=str(e))
        except Exception as e:
            return ExtractionResult(success=False, error=str(e))

    def try_password(self, path: Path, password: str) -> bool:
        """Test if password works for ZIP archive."""
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = zf.namelist()
                if names:
                    zf.read(names[0], pwd=password.encode() if password else None)
                    return True
        except Exception:
            pass
        return False
