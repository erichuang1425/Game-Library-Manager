from __future__ import annotations
import os
import subprocess
import webbrowser
from pathlib import Path
from typing import Optional

from app.models import Game

def launch_game(game: Game) -> tuple[bool, str]:
    """
    Launch order:
      1) If shortcut file exists -> os.startfile(shortcut)
      2) Else fallback to backup_target_path (if present)
    """
    try:
        sp = Path(game.shortcut_path) if game.shortcut_path else None
        if sp and sp.exists():
            # Windows can open .lnk and .url directly
            os.startfile(str(sp))
            return True, "Launched via shortcut"

        # Fallback: backup target
        target = Path(game.backup_target_path) if game.backup_target_path else None
        if target and target.exists():
            if target.suffix.lower() in {".html", ".htm"}:
                webbrowser.open(target.as_uri())
                return True, "Launched via backup HTML"
            # exe / other
            args = game.backup_args.strip()
            cmd = [str(target)] + ([args] if args else [])
            subprocess.Popen(
                " ".join(cmd),
                cwd=game.backup_working_dir or None,
                shell=True
            )
            return True, "Launched via backup target"

        return False, "Shortcut missing and no valid backup target"
    except Exception as e:
        return False, str(e)
