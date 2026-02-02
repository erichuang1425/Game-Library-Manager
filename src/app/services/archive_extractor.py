from __future__ import annotations
"""
Archive extraction service for Game Library Manager.

Supports:
- ZIP files (built-in)
- RAR files (requires rarfile + unrar)
- 7z files (requires py7zr)
- Multi-part archives
- Password-protected archives
"""

import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from app.logging_utils import get_logger, kv
from app.storage.paths import get_app_dir

_log = get_logger("archive_extractor")


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

# User custom passwords (loaded from settings)
_custom_passwords: List[str] = []

# Archive format patterns
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

# Progress callback type
ProgressCallback = Callable[[str, int, int], None]  # filename, current, total


def detect_format(path: Path) -> ArchiveFormat:
    """Detect archive format from file extension and magic bytes."""
    suffix = path.suffix.lower()

    # Check by extension first
    if suffix == ".zip":
        return ArchiveFormat.ZIP
    elif suffix == ".rar":
        return ArchiveFormat.RAR
    elif suffix == ".7z":
        return ArchiveFormat.SEVEN_ZIP

    # Check for multipart extensions
    name_lower = path.name.lower()
    if ".part" in name_lower and ".rar" in name_lower:
        return ArchiveFormat.RAR
    if name_lower.endswith((".r00", ".r01")):
        return ArchiveFormat.RAR

    # Try magic bytes
    try:
        with open(path, "rb") as f:
            header = f.read(8)

            # ZIP: PK\x03\x04
            if header[:4] == b"PK\x03\x04":
                return ArchiveFormat.ZIP

            # RAR: Rar!\x1a\x07
            if header[:6] == b"Rar!\x1a\x07":
                return ArchiveFormat.RAR

            # 7z: 7z\xbc\xaf\x27\x1c
            if header[:6] == b"7z\xbc\xaf\x27\x1c":
                return ArchiveFormat.SEVEN_ZIP
    except Exception:
        pass

    return ArchiveFormat.UNKNOWN


def get_archive_info(path: Path) -> ArchiveInfo:
    """Get information about an archive."""
    fmt = detect_format(path)

    info = ArchiveInfo(
        path=str(path),
        format=fmt,
    )

    # Check for multipart
    name = path.name
    for pattern_name, pattern in MULTIPART_PATTERNS.items():
        match = pattern.search(name)
        if match:
            info.is_multipart = True
            info.part_number = int(match.group(1))
            info.first_part_path = str(find_first_part(path))
            break

    # Get file info based on format
    try:
        if fmt == ArchiveFormat.ZIP:
            with zipfile.ZipFile(path, "r") as zf:
                info.file_count = len(zf.namelist())
                info.total_size = sum(zi.file_size for zi in zf.infolist())
                # Check if encrypted
                for zi in zf.infolist():
                    if zi.flag_bits & 0x1:
                        info.is_encrypted = True
                        break

        elif fmt == ArchiveFormat.RAR:
            try:
                import rarfile
                with rarfile.RarFile(path, "r") as rf:
                    info.file_count = len(rf.namelist())
                    info.total_size = sum(ri.file_size for ri in rf.infolist())
                    info.is_encrypted = rf.needs_password()
            except ImportError:
                _log.debug("rarfile not available")

        elif fmt == ArchiveFormat.SEVEN_ZIP:
            try:
                import py7zr
                with py7zr.SevenZipFile(path, "r") as sz:
                    info.file_count = len(sz.getnames())
                    # Note: py7zr doesn't easily expose total size
                    info.is_encrypted = sz.needs_password()
            except ImportError:
                _log.debug("py7zr not available")

    except Exception as e:
        _log.debug("archive_info_error %s", kv(path=str(path), err=str(e)))

    return info


def find_first_part(path: Path) -> Path:
    """Find the first part of a multipart archive."""
    name = path.name
    parent = path.parent

    # Check patterns
    for pattern_name, pattern in MULTIPART_PATTERNS.items():
        match = pattern.search(name)
        if match:
            if pattern_name == "rar_part":
                # Replace .partN.rar with .part1.rar
                first_name = pattern.sub(".part1.rar", name)
            elif pattern_name == "rar_rxx":
                # Replace .rNN with .rar
                first_name = pattern.sub(".rar", name)
            elif pattern_name in ("split", "zip_split", "7z_split"):
                # Replace .NNN with .001
                first_name = pattern.sub(".001", name)
            else:
                first_name = name

            first_path = parent / first_name
            if first_path.exists():
                return first_path

    return path


def find_all_parts(first_part: Path) -> List[Path]:
    """Find all parts of a multipart archive."""
    parts = [first_part]
    parent = first_part.parent
    name = first_part.name

    # Determine pattern
    for pattern_name, pattern in MULTIPART_PATTERNS.items():
        match = pattern.search(name)
        if match or pattern_name == "rar_rxx":
            break
    else:
        return parts

    # Find subsequent parts
    if "rar_part" in pattern_name or pattern_name == "rar_part":
        # .part1.rar, .part2.rar, etc.
        base = re.sub(r"\.part\d+\.rar$", "", name, flags=re.IGNORECASE)
        for i in range(2, 100):
            part_path = parent / f"{base}.part{i}.rar"
            if part_path.exists():
                parts.append(part_path)
            else:
                break

    elif pattern_name == "rar_rxx":
        # .rar, .r00, .r01, etc.
        base = re.sub(r"\.(rar|r\d{2,})$", "", name, flags=re.IGNORECASE)
        for i in range(0, 100):
            part_path = parent / f"{base}.r{i:02d}"
            if part_path.exists():
                parts.append(part_path)
            else:
                break

    elif pattern_name in ("split", "zip_split", "7z_split"):
        # .001, .002, etc.
        base = re.sub(r"\.\d{3}$", "", name)
        for i in range(2, 1000):
            part_path = parent / f"{base}.{i:03d}"
            if part_path.exists():
                parts.append(part_path)
            else:
                break

    return sorted(parts)


def try_passwords(
    path: Path,
    fmt: ArchiveFormat,
    passwords: Optional[List[str]] = None
) -> Optional[str]:
    """
    Try common passwords to find working one.
    Returns working password or None.
    """
    if passwords is None:
        passwords = COMMON_PASSWORDS + _custom_passwords

    for pwd in passwords:
        try:
            if fmt == ArchiveFormat.ZIP:
                with zipfile.ZipFile(path, "r") as zf:
                    # Try to read first file
                    names = zf.namelist()
                    if names:
                        zf.read(names[0], pwd=pwd.encode() if pwd else None)
                        return pwd

            elif fmt == ArchiveFormat.RAR:
                import rarfile
                with rarfile.RarFile(path, "r") as rf:
                    rf.setpassword(pwd)
                    names = rf.namelist()
                    if names:
                        rf.read(names[0])
                        return pwd

            elif fmt == ArchiveFormat.SEVEN_ZIP:
                import py7zr
                with py7zr.SevenZipFile(path, "r", password=pwd if pwd else None) as sz:
                    # Just opening successfully with password is enough
                    return pwd

        except Exception:
            continue

    return None


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


def add_custom_password(password: str) -> None:
    """Add a custom password to try."""
    if password and password not in _custom_passwords:
        _custom_passwords.append(password)


def remove_custom_password(password: str) -> None:
    """Remove a custom password."""
    if password in _custom_passwords:
        _custom_passwords.remove(password)


def get_custom_passwords() -> List[str]:
    """Get list of custom passwords."""
    return list(_custom_passwords)


def find_executables(directory: Path) -> List[Path]:
    """
    Find executable files in extracted directory.
    Useful for finding the game executable after extraction.
    """
    executables = []
    exe_extensions = {".exe", ".bat", ".cmd", ".sh"}
    exe_patterns = [
        re.compile(r"game", re.IGNORECASE),
        re.compile(r"play", re.IGNORECASE),
        re.compile(r"start", re.IGNORECASE),
        re.compile(r"launch", re.IGNORECASE),
    ]

    try:
        for item in directory.rglob("*"):
            if item.is_file() and item.suffix.lower() in exe_extensions:
                executables.append(item)
    except Exception as e:
        _log.warning("find_executables_error %s", kv(err=str(e)))

    # Sort by likelihood of being the main game executable
    def score(p: Path) -> int:
        name = p.stem.lower()
        s = 0
        for pattern in exe_patterns:
            if pattern.search(name):
                s += 10
        # Prefer files in root or first-level subdirectory
        rel_parts = len(p.relative_to(directory).parts)
        s -= rel_parts * 2
        return s

    executables.sort(key=score, reverse=True)
    return executables


def find_save_folder(directory: Path) -> Optional[Path]:
    """
    Find the save game folder in an extracted directory.
    Common patterns: saves, save, game/saves, etc.
    """
    save_patterns = ["saves", "save", "savegame", "savedata", "game/saves"]

    for pattern in save_patterns:
        save_path = directory / pattern
        if save_path.exists() and save_path.is_dir():
            return save_path

    # Search recursively
    for item in directory.rglob("*"):
        if item.is_dir() and item.name.lower() in ("saves", "save", "savegame"):
            return item

    return None
