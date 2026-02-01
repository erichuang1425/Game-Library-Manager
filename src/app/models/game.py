from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Game:
    game_id: str
    title: str

    # Shortcut entry (centralized launcher directory)
    shortcut_path: str = ""              # absolute path to .lnk/.url/.html
    shortcut_type: str = ""              # lnk | url | html

    # Backup launch info (mainly from .lnk)
    backup_target_path: str = ""         # resolved target exe/file path
    backup_args: str = ""                # resolved arguments from .lnk
    backup_working_dir: str = ""         # resolved working directory from .lnk

    # Library metadata
    status: str = "backlog"              # backlog | playing | finished | dropped
    rating: Optional[int] = None         # 1..10
    tags: List[str] = field(default_factory=list)
    last_played: Optional[datetime] = None
    launch_count: int = 0
    notes: str = ""

    # Quality flags
    confidence: str = "medium"           # high | medium | low

    # Source / update tracking
    source_url: str = ""                 # source page (e.g., f95zone thread)
    source_checked_at: Optional[datetime] = None  # last time we parsed source page
    installed_version_raw: str = ""      # local version string (manual/detected)
    source_version_raw: str = ""         # raw version string from source page
    source_version_num: Optional[str] = None  # numeric component extracted (e.g., 0.1.1)
    source_version_suffix: str = ""      # label / suffix, e.g., "Redux Demo"

    # Archive tracking
    archive_folder_path: str = ""        # extracted archive folder path
    compressed_archive_path: str = ""    # original compressed archive (.zip/.rar/etc)
    game_folder_path: str = ""           # resolved folder from shortcut target (best-effort)

    # Icon quality tracking
    icon_upscaled: bool = False          # True once a high-quality icon has been cached
