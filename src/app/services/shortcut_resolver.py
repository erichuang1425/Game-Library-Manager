from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import pythoncom
from win32com.shell import shell

@dataclass
class ResolvedShortcut:
    target_path: str = ""
    args: str = ""
    working_dir: str = ""
    url: str = ""

def resolve_lnk(lnk_path: Path) -> ResolvedShortcut:
    """
    Resolves a .lnk using pywin32. If resolution fails, returns empty fields.
    """
    try:

        pythoncom.CoInitialize()
        link = pythoncom.CoCreateInstance(
            shell.CLSID_ShellLink, None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink
        )
        persist = link.QueryInterface(pythoncom.IID_IPersistFile)
        persist.Load(str(lnk_path))

        target, _ = link.GetPath(shell.SLGP_UNCPRIORITY)
        args = link.GetArguments() or ""
        workdir = link.GetWorkingDirectory() or ""

        return ResolvedShortcut(
            target_path=target or "",
            args=args,
            working_dir=workdir
        )
    except Exception:
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
    except Exception:
        return ResolvedShortcut()

def resolve_shortcut_any(path: Path) -> ResolvedShortcut:
    ext = path.suffix.lower()
    if ext == ".lnk":
        return resolve_lnk(path)
    if ext == ".url":
        return resolve_url(path)
    # .html is a file we open directly; no need to resolve
    return ResolvedShortcut()
