from .library_service import load_fake_games
from .scan_service import scan_shortcut_root, find_duplicate_shortcuts_in_root, move_duplicates_to_quarantine
from .launch_service import launch_game
from .shortcut_resolver import resolve_lnk, resolve_url, resolve_shortcut_any
from .icon_service import icon_for_path, pixmap_for_path, pixmap_for_game, best_icon_path
from .library_merge import merge_scanned_into_library
from .collection_engine import apply_collection
from .version_parser import parse_version, compare_versions
from .update_checker import fetch_source_version, check_updates_background
