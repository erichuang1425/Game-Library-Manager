"""Archive password management."""
from __future__ import annotations
import json
import zipfile
from pathlib import Path
from typing import List, Optional

from app.logging_utils import get_logger, kv
from app.storage.paths import get_app_dir

from .models import ArchiveFormat, COMMON_PASSWORDS

_log = get_logger("archive.passwords")

# User custom passwords (loaded from settings)
_custom_passwords: List[str] = []


def _passwords_file() -> Path:
    """Get path to passwords storage file."""
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
