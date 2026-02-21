"""Archive extraction functions."""
from __future__ import annotations
import zipfile
from pathlib import Path
from typing import Optional

from app.logging_utils import get_logger, kv

from .models import ArchiveFormat, ExtractionResult, ProgressCallback
from .detection import detect_format, get_archive_info, find_first_part
from .passwords import try_passwords

_log = get_logger("archive.extraction")


def extract_zip(
    path: Path,
    destination: Path,
    password: Optional[str] = None,
    progress: Optional[ProgressCallback] = None,
) -> ExtractionResult:
    """Extract a ZIP archive."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            total = len(names)
            extracted_size = 0

            for i, name in enumerate(names):
                if progress:
                    progress(name, i + 1, total)

                try:
                    zf.extract(name, destination, pwd=password.encode() if password else None)
                    info = zf.getinfo(name)
                    extracted_size += info.file_size
                except Exception as e:
                    _log.warning("zip_extract_file_error %s", kv(name=name, err=str(e)))

            return ExtractionResult(
                success=True,
                extracted_path=str(destination),
                file_count=total,
                total_size=extracted_size,
                password_used=password or "",
            )

    except zipfile.BadZipFile:
        return ExtractionResult(success=False, error="Invalid or corrupted ZIP file")
    except RuntimeError as e:
        if "password" in str(e).lower():
            return ExtractionResult(success=False, error="Incorrect password")
        return ExtractionResult(success=False, error=str(e))
    except Exception as e:
        return ExtractionResult(success=False, error=str(e))


def extract_rar(
    path: Path,
    destination: Path,
    password: Optional[str] = None,
    progress: Optional[ProgressCallback] = None,
) -> ExtractionResult:
    """Extract a RAR archive."""
    try:
        import rarfile
    except ImportError:
        return ExtractionResult(
            success=False,
            error="RAR extraction requires the 'rarfile' library. Install with: pip install rarfile"
        )

    try:
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
                    _log.warning("rar_extract_file_error %s", kv(name=name, err=str(e)))

            return ExtractionResult(
                success=True,
                extracted_path=str(destination),
                file_count=total,
                total_size=extracted_size,
                password_used=password or "",
            )

    except rarfile.BadRarFile:
        return ExtractionResult(success=False, error="Invalid or corrupted RAR file")
    except rarfile.RarWrongPassword:
        return ExtractionResult(success=False, error="Incorrect password")
    except Exception as e:
        return ExtractionResult(success=False, error=str(e))


def extract_7z(
    path: Path,
    destination: Path,
    password: Optional[str] = None,
    progress: Optional[ProgressCallback] = None,
) -> ExtractionResult:
    """Extract a 7z archive."""
    try:
        import py7zr
    except ImportError:
        return ExtractionResult(
            success=False,
            error="7z extraction requires the 'py7zr' library. Install with: pip install py7zr"
        )

    try:
        with py7zr.SevenZipFile(path, "r", password=password if password else None) as sz:
            names = sz.getnames()
            total = len(names)

            # py7zr extracts all at once
            sz.extractall(destination)

            # Calculate size
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

    except py7zr.exceptions.Bad7zFile:
        return ExtractionResult(success=False, error="Invalid or corrupted 7z file")
    except py7zr.exceptions.PasswordRequired:
        return ExtractionResult(success=False, error="Password required")
    except Exception as e:
        if "password" in str(e).lower():
            return ExtractionResult(success=False, error="Incorrect password")
        return ExtractionResult(success=False, error=str(e))


def extract_archive(
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
        destination: Extraction destination (default: same directory as archive)
        password: Password for encrypted archives
        try_common_passwords: Try common F95zone passwords if encrypted
        progress: Progress callback

    Returns:
        ExtractionResult with extraction status
    """
    path = Path(path)

    if not path.exists():
        return ExtractionResult(success=False, error=f"Archive not found: {path}")

    # Detect format
    fmt = detect_format(path)
    if fmt == ArchiveFormat.UNKNOWN:
        return ExtractionResult(success=False, error="Unknown archive format")

    # Set destination
    if destination is None:
        destination = path.parent / path.stem

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    _log.info("extract_start %s", kv(
        path=str(path),
        format=fmt.value,
        dest=str(destination)
    ))

    # Check for multipart
    info = get_archive_info(path)
    if info.is_multipart:
        first_part = Path(info.first_part_path) if info.first_part_path else find_first_part(path)
        if first_part != path:
            _log.info("multipart_using_first %s", kv(first=str(first_part)))
            path = first_part

    # Try password if needed
    if info.is_encrypted and not password and try_common_passwords:
        password = try_passwords(path, fmt)
        if password:
            _log.info("password_found %s", kv(password="***"))

    # Extract based on format
    if fmt == ArchiveFormat.ZIP:
        result = extract_zip(path, destination, password, progress)
    elif fmt == ArchiveFormat.RAR:
        result = extract_rar(path, destination, password, progress)
    elif fmt == ArchiveFormat.SEVEN_ZIP:
        result = extract_7z(path, destination, password, progress)
    else:
        result = ExtractionResult(success=False, error=f"Unsupported format: {fmt.value}")

    if result.success:
        _log.info("extract_complete %s", kv(
            files=result.file_count,
            size=result.total_size,
            dest=result.extracted_path
        ))
    else:
        _log.warning("extract_failed %s", kv(error=result.error))

    return result
