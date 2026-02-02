from .library_service import load_fake_games
from .scan_service import scan_shortcut_root, find_duplicate_shortcuts_in_root, move_duplicates_to_quarantine
from .launch_service import launch_game
from .shortcut_resolver import resolve_lnk, resolve_url, resolve_shortcut_any
from .icon_service import icon_for_path, pixmap_for_path, pixmap_for_game, best_icon_path
from .library_merge import merge_scanned_into_library
from .collection_engine import apply_collection
from .version_parser import parse_version, compare_versions
from .update_checker import fetch_source_version, check_updates_background
from .color_extractor import extract_dominant_color, extract_palette, color_for_overlay
from .export_import import (
    export_to_json, export_to_csv, export_to_markdown,
    import_from_json, import_from_csv, merge_imported_games
)
from .undo_redo import (
    UndoStack, Command, GameFieldChangeCommand, GameMultiFieldChangeCommand,
    BatchGameChangeCommand, AddGameCommand, RemoveGameCommand,
    get_undo_stack, create_field_change, create_multi_field_change, create_batch_change
)
