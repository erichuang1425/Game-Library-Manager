"""Shared utilities for archive handling."""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set, Tuple

from app.logging_utils import get_logger, kv
from app.storage.paths import get_app_dir

_log = get_logger("archive.utils")


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


def _passwords_file() -> Path:
    """Get path to password storage file."""
    return get_app_dir() / "archive_passwords.json"


def load_custom_passwords() -> List[str]:
    """Load custom passwords from persistent storage."""
    global _custom_passwords
    try:
        path = _passwords_file()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            _custom_passwords = data.get("passwords", [])
            _log.info("loaded_passwords %s", kv(count=len(_custom_passwords)))
    except Exception as e:
        _log.warning("load_passwords_error %s", kv(err=str(e)))
    return list(_custom_passwords)


def save_custom_passwords() -> None:
    """Save custom passwords to persistent storage."""
    try:
        path = _passwords_file()
        data = {"passwords": _custom_passwords}
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _log.info("saved_passwords %s", kv(count=len(_custom_passwords)))
    except Exception as e:
        _log.warning("save_passwords_error %s", kv(err=str(e)))


def add_custom_password(password: str, persist: bool = True) -> None:
    """Add a custom password to try."""
    if password and password not in _custom_passwords:
        _custom_passwords.append(password)
        if persist:
            save_custom_passwords()


def remove_custom_password(password: str, persist: bool = True) -> None:
    """Remove a custom password."""
    if password in _custom_passwords:
        _custom_passwords.remove(password)
        if persist:
            save_custom_passwords()


def get_custom_passwords() -> List[str]:
    """Get list of custom passwords."""
    return list(_custom_passwords)


def set_custom_passwords(passwords: List[str], persist: bool = True) -> None:
    """Set the full list of custom passwords."""
    global _custom_passwords
    _custom_passwords = list(passwords)
    if persist:
        save_custom_passwords()


def get_all_passwords() -> List[str]:
    """Get all passwords to try (common + custom)."""
    return COMMON_PASSWORDS + _custom_passwords


# Multipart archive patterns
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

# Patterns for first parts of multipart archives
MULTIPART_FIRST_PATTERNS = [
    re.compile(r"\.part1\.rar$", re.IGNORECASE),
    re.compile(r"\.zip\.001$", re.IGNORECASE),
    re.compile(r"\.7z\.001$", re.IGNORECASE),
]


def find_first_part(path: Path) -> Path:
    """Find the first part of a multipart archive."""
    name = path.name
    parent = path.parent

    for pattern_name, pattern in MULTIPART_PATTERNS.items():
        match = pattern.search(name)
        if match:
            if pattern_name == "rar_part":
                first_name = pattern.sub(".part1.rar", name)
            elif pattern_name == "rar_rxx":
                first_name = pattern.sub(".rar", name)
            elif pattern_name in ("split", "zip_split", "7z_split"):
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
    matched_pattern = None
    for pattern_name, pattern in MULTIPART_PATTERNS.items():
        match = pattern.search(name)
        if match or pattern_name == "rar_rxx":
            matched_pattern = pattern_name
            break

    if not matched_pattern:
        return parts

    # Find subsequent parts
    if matched_pattern == "rar_part":
        base = re.sub(r"\.part\d+\.rar$", "", name, flags=re.IGNORECASE)
        for i in range(2, 100):
            part_path = parent / f"{base}.part{i}.rar"
            if part_path.exists():
                parts.append(part_path)
            else:
                break

    elif matched_pattern == "rar_rxx":
        base = re.sub(r"\.(rar|r\d{2,})$", "", name, flags=re.IGNORECASE)
        for i in range(0, 100):
            part_path = parent / f"{base}.r{i:02d}"
            if part_path.exists():
                parts.append(part_path)
            else:
                break

    elif matched_pattern in ("split", "zip_split", "7z_split"):
        base = re.sub(r"\.\d{3}$", "", name)
        for i in range(2, 1000):
            part_path = parent / f"{base}.{i:03d}"
            if part_path.exists():
                parts.append(part_path)
            else:
                break

    return sorted(parts)


def is_multipart(path: Path) -> bool:
    """Check if a file is part of a multipart archive."""
    name = path.name
    for pattern in MULTIPART_PATTERNS.values():
        if pattern.search(name):
            return True
    return False


def is_later_part(path: Path) -> bool:
    """Check if a file is a later part (not first) of a multipart archive."""
    name = path.name.lower()

    # Check for .rXX files (always later parts)
    if re.match(r".*\.r\d{2,}$", name):
        return True

    # Check numbered parts
    for pattern in MULTIPART_PATTERNS.values():
        match = pattern.search(path.name)
        if match:
            part_num = int(match.group(1))
            if part_num > 1:
                return True

    return False


def parse_archive_filename(filename: str) -> Tuple[str, str]:
    """
    Parse a game archive filename to extract title and version.

    Common patterns:
    - Game Name v0.1.2.zip
    - Game Name [v0.1.2].rar
    - Game-Name-0.1.2-pc.7z

    Returns:
        Tuple of (title, version)
    """
    # Remove extension
    name = Path(filename).stem

    # Remove multipart suffixes
    name = re.sub(r"\.part\d+$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.7z$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.zip$", "", name, flags=re.IGNORECASE)

    # Remove common suffixes
    name = re.sub(
        r"[-_\s]*(pc|win|windows|linux|mac|android)[-_\s]*$",
        "", name, flags=re.IGNORECASE
    )
    name = re.sub(
        r"[-_\s]*(x64|x86|64bit|32bit)[-_\s]*$",
        "", name, flags=re.IGNORECASE
    )

    # Try to find version pattern
    version = ""
    version_patterns = [
        re.compile(r"[\[\(]\s*v?(\d+(?:\.\d+)+[a-z]?)\s*[\]\)]", re.IGNORECASE),
        re.compile(r"\s+v(\d+(?:\.\d+)+[a-z]?)", re.IGNORECASE),
        re.compile(r"[-_](\d+(?:\.\d+)+[a-z]?)$", re.IGNORECASE),
    ]

    for pattern in version_patterns:
        match = pattern.search(name)
        if match:
            version = match.group(1)
            name = pattern.sub("", name)
            break

    # Clean up title
    title = name.strip()
    title = re.sub(r"[-_]+$", "", title)
    title = re.sub(r"[-_]+", " ", title)
    title = re.sub(r"\s+", " ", title)
    title = title.strip()

    return title, version


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


def normalize_title(title: str) -> str:
    """Normalize a title for comparison."""
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def calculate_title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two titles (0.0 - 1.0).
    Uses normalized comparison with word overlap.
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

    # Word overlap (Jaccard similarity)
    words1 = set(n1.split())
    words2 = set(n2.split())

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union) if union else 0.0


# Archive extensions for scanning
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}


@dataclass
class ScannedArchive:
    """Represents a scanned archive file."""
    path: Path
    name: str
    format_name: str
    size: int
    is_multipart: bool = False
    parts: List[Path] = field(default_factory=list)
    is_encrypted: bool = False
    detected_title: str = ""
    detected_version: str = ""
