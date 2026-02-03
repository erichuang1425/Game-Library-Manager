"""Archive utility functions."""
from __future__ import annotations
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

from app.logging_utils import get_logger, kv

from .models import (
    ArchiveFormat, ScannedArchive,
    MULTIPART_PATTERNS, MULTIPART_FIRST_PATTERNS,
)
from .detection import detect_format, get_archive_info, find_all_parts

_log = get_logger("archive.utils")


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


def scan_for_archives(
    folder: Path,
    recursive: bool = True,
) -> List[ScannedArchive]:
    """
    Scan a folder for archive files.
    Groups multi-part archives and returns only first parts.
    """
    archives: List[ScannedArchive] = []
    seen_multipart_bases: Set[str] = set()

    pattern = "**/*" if recursive else "*"

    for item in folder.glob(pattern):
        if not item.is_file():
            continue

        suffix = item.suffix.lower()
        name_lower = item.name.lower()

        # Skip non-first multipart files
        is_later_part = False
        for mp_pattern in MULTIPART_PATTERNS.values():
            match = mp_pattern.search(item.name)
            if match:
                part_num = int(match.group(1))
                if part_num > 1:
                    is_later_part = True
                    break

        # Skip .rXX files (later parts)
        if re.match(r".*\.r\d{2,}$", name_lower):
            is_later_part = True

        if is_later_part:
            continue

        # Check if it's an archive
        fmt = detect_format(item)
        if fmt == ArchiveFormat.UNKNOWN:
            continue

        # Detect multipart
        is_multipart = False
        parts: List[Path] = []
        total_size = item.stat().st_size

        for mp_pattern in MULTIPART_FIRST_PATTERNS:
            if mp_pattern.search(item.name):
                is_multipart = True
                break

        # Also check if next part exists (for .rar without .part pattern)
        if suffix == ".rar" and not is_multipart:
            r00_path = item.parent / (item.stem + ".r00")
            if r00_path.exists():
                is_multipart = True

        if is_multipart:
            parts = find_all_parts(item)
            total_size = sum(p.stat().st_size for p in parts if p.exists())

        # Extract title from filename
        detected_title, detected_version = parse_archive_filename(item.name)

        # Get encryption status
        info = get_archive_info(item)

        archive = ScannedArchive(
            path=item,
            name=item.name,
            format=fmt,
            size=total_size,
            is_multipart=is_multipart,
            parts=parts,
            is_encrypted=info.is_encrypted,
            detected_title=detected_title,
            detected_version=detected_version,
        )
        archives.append(archive)

    return sorted(archives, key=lambda a: a.detected_title.lower())


def parse_archive_filename(filename: str) -> Tuple[str, str]:
    """
    Parse a game archive filename to extract title and version.

    Common patterns:
    - Game Name v0.1.2.zip
    - Game Name [v0.1.2].rar
    - Game-Name-0.1.2-pc.7z
    - Game_Name_0.1.zip
    """
    # Remove extension
    name = Path(filename).stem

    # Remove multipart suffixes
    name = re.sub(r"\.part\d+$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.7z$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.zip$", "", name, flags=re.IGNORECASE)

    # Remove common suffixes
    name = re.sub(r"[-_\s]*(pc|win|windows|linux|mac|android)[-_\s]*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[-_\s]*(x64|x86|64bit|32bit)[-_\s]*$", "", name, flags=re.IGNORECASE)

    # Try to find version pattern
    version = ""
    version_patterns = [
        # [v0.1.2] or (v0.1.2)
        re.compile(r"[\[\(]\s*v?(\d+(?:\.\d+)+[a-z]?)\s*[\]\)]", re.IGNORECASE),
        # v0.1.2 or V0.1.2
        re.compile(r"\s+v(\d+(?:\.\d+)+[a-z]?)", re.IGNORECASE),
        # -0.1.2 or _0.1.2 at end
        re.compile(r"[-_](\d+(?:\.\d+)+[a-z]?)$", re.IGNORECASE),
    ]

    for pattern in version_patterns:
        match = pattern.search(name)
        if match:
            version = match.group(1)
            # Remove version from name
            name = pattern.sub("", name)
            break

    # Clean up title
    title = name.strip()
    title = re.sub(r"[-_]+$", "", title)  # Trailing separators
    title = re.sub(r"[-_]+", " ", title)  # Replace separators with spaces
    title = re.sub(r"\s+", " ", title)    # Multiple spaces
    title = title.strip()

    return title, version


def normalize_title(title: str) -> str:
    """Normalize a title for comparison."""
    # Lowercase
    t = title.lower()
    # Remove punctuation and special chars
    t = re.sub(r"[^\w\s]", "", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def calculate_title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two titles (0.0 - 1.0).
    Uses normalized comparison.
    """
    n1 = normalize_title(title1)
    n2 = normalize_title(title2)

    if not n1 or not n2:
        return 0.0

    if n1 == n2:
        return 1.0

    # Check if one contains the other
    if n1 in n2 or n2 in n1:
        return 0.9

    # Word overlap
    words1 = set(n1.split())
    words2 = set(n2.split())

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union) if union else 0.0
