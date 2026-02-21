"""Archive format detection and multipart handling."""
from __future__ import annotations
import re
import zipfile
from pathlib import Path
from typing import List

from app.logging_utils import get_logger, kv

from .models import ArchiveFormat, ArchiveInfo, MULTIPART_PATTERNS

_log = get_logger("archive.detection")


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
    pattern_name = None
    for pn, pattern in MULTIPART_PATTERNS.items():
        match = pattern.search(name)
        if match or pn == "rar_rxx":
            pattern_name = pn
            break

    if pattern_name is None:
        return parts

    # Find subsequent parts
    if pattern_name == "rar_part":
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
