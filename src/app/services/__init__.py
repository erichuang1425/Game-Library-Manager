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

# F95zone advanced integration (Phase 6-10)
from .f95_api import (
    ThreadInfo, DownloadLink,
    normalize_f95_url, is_f95_url, extract_thread_id,
    parse_thread_title, extract_download_links, extract_thread_info,
    derive_title_from_url, group_download_links_by_host
)
from .f95_auth import (
    F95AuthManager, AuthResult, SessionInfo,
    get_auth_manager
)
from .download_manager import (
    DownloadManager, DownloadItem, DownloadStatus, DownloadProgress,
    get_download_manager, format_size, format_speed, format_eta
)
from .archive_extractor import (
    ArchiveFormat, ExtractionResult, ArchiveInfo, ScannedArchive,
    detect_format, get_archive_info, extract_archive,
    find_executables, find_save_folder,
    add_custom_password, remove_custom_password, get_custom_passwords,
    set_custom_passwords, get_all_passwords, load_custom_passwords, save_custom_passwords,
    scan_for_archives, parse_archive_filename, normalize_title, calculate_title_similarity
)
from .bulk_archive_import import (
    BulkArchiveImporter, ImportItem, ImportResult, ImportAction, ImportStatus,
    MatchResult, format_size
)
