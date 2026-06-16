from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ResolvedShortcut:
    target_path: str = ""
    args: str = ""
    working_dir: str = ""
    url: str = ""


class ShellLinkAdapter(Protocol):
    """Small boundary around the Windows ShellLink COM API."""

    def resolve(self, lnk_path: Path) -> ResolvedShortcut:
        """Return shortcut metadata for ``lnk_path`` or an empty result."""


class PyWin32ShellLinkAdapter:
    """Resolve .lnk files through pywin32 on Windows."""

    def resolve(self, lnk_path: Path) -> ResolvedShortcut:
        import pythoncom
        from win32com.shell import shell

        pythoncom.CoInitialize()
        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink,
        )
        persist = link.QueryInterface(pythoncom.IID_IPersistFile)
        persist.Load(str(lnk_path))

        target, _ = link.GetPath(shell.SLGP_UNCPRIORITY)
        return ResolvedShortcut(
            target_path=target or "",
            args=link.GetArguments() or "",
            working_dir=link.GetWorkingDirectory() or "",
        )


class NullShellLinkAdapter:
    """Portable no-op adapter used when Windows ShellLink is unavailable."""

    def resolve(self, lnk_path: Path) -> ResolvedShortcut:
        return ResolvedShortcut()


def default_shell_link_adapter() -> ShellLinkAdapter:
    """Return the platform adapter for resolving Windows .lnk shortcuts."""
    if os.name == "nt":
        return PyWin32ShellLinkAdapter()
    return NullShellLinkAdapter()


def resolve_lnk(
    lnk_path: Path, adapter: ShellLinkAdapter | None = None
) -> ResolvedShortcut:
    """
    Resolve a .lnk file through an injectable platform adapter.

    Resolution failures are treated as a broken shortcut and return an empty
    result, matching the historical scanner behavior while keeping pywin32
    behind a small testable boundary.
    """
    try:
        return (adapter or default_shell_link_adapter()).resolve(lnk_path)
    except Exception:
        # Platform adapters sit at the OS/COM boundary and can raise provider-specific
        # exceptions (for example pywintypes.com_error) that are not importable on
        # every CI platform. Treat any adapter failure as an unresolved shortcut.
        return ResolvedShortcut()


def resolve_url(url_path: Path) -> ResolvedShortcut:
    """
    .url is INI-like. We only care about URL=...
    """
    try:
        txt = url_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        url = ""
        for line in txt:
            line = line.strip()
            if line.lower().startswith("url="):
                url = line[4:].strip()
                break
        return ResolvedShortcut(url=url)
    except OSError:
        return ResolvedShortcut()


def resolve_shortcut_any(
    path: Path, adapter: ShellLinkAdapter | None = None
) -> ResolvedShortcut:
    ext = path.suffix.lower()
    if ext == ".lnk":
        return resolve_lnk(path, adapter=adapter)
    if ext == ".url":
        return resolve_url(path)
    # .html is a file we open directly; no need to resolve
    return ResolvedShortcut()
