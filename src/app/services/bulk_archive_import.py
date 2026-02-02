from __future__ import annotations
"""
Bulk archive import service for Game Library Manager.

Handles:
- Scanning folders for archives
- Extracting archives with password management
- Matching extracted games to existing library entries
- Detecting duplicate/version conflicts
- Creating shortcuts
- Adding entries to library
"""

import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from app.logging_utils import get_logger, kv
from app.models import Game
from app.services.archive_extractor import (
    ArchiveFormat,
    ExtractionResult,
    ScannedArchive,
    calculate_title_similarity,
    extract_archive,
    find_executables,
    find_save_folder,
    get_all_passwords,
    get_archive_info,
    load_custom_passwords,
    normalize_title,
    parse_archive_filename,
    scan_for_archives,
    try_passwords,
)
from app.services.version_parser import CompareResult, parse_version, compare_versions
from app.storage.paths import get_app_dir

_log = get_logger("bulk_archive_import")


class ImportAction(Enum):
    """Action to take for an archive."""
    IMPORT_NEW = "import_new"           # New game, import
    UPDATE_EXISTING = "update_existing"  # Newer version, update
    SKIP_OLDER = "skip_older"           # Older version, skip
    SKIP_DUPLICATE = "skip_duplicate"   # Same version, skip
    CONFLICT = "conflict"               # Manual resolution needed
    SKIP_USER = "skip_user"             # User chose to skip


class ImportStatus(Enum):
    """Status of an import operation."""
    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    CREATING_SHORTCUT = "creating_shortcut"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class MatchResult:
    """Result of matching an archive to existing library."""
    matched_game: Optional[Game] = None
    similarity: float = 0.0
    action: ImportAction = ImportAction.IMPORT_NEW
    version_compare: Optional[CompareResult] = None
    notes: str = ""


@dataclass
class ImportItem:
    """Represents an archive to be imported."""
    archive: ScannedArchive
    match: MatchResult = field(default_factory=MatchResult)
    status: ImportStatus = ImportStatus.PENDING
    # User overrides
    custom_title: str = ""
    selected_action: Optional[ImportAction] = None
    # Results
    extracted_path: str = ""
    executable_path: str = ""
    shortcut_path: str = ""
    game_id: str = ""
    error: str = ""

    @property
    def display_title(self) -> str:
        return self.custom_title or self.archive.detected_title

    @property
    def final_action(self) -> ImportAction:
        return self.selected_action or self.match.action


@dataclass
class ImportResult:
    """Result of a bulk import operation."""
    total: int = 0
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    items: List[ImportItem] = field(default_factory=list)


# Progress callback type
ImportProgressCallback = Callable[[str, int, int, str], None]  # stage, current, total, message


class BulkArchiveImporter:
    """
    Service for bulk importing game archives.
    """

    def __init__(
        self,
        games_folder: Path,
        shortcuts_folder: Path,
        library: List[Game],
    ):
        """
        Initialize the importer.

        Args:
            games_folder: Folder where games will be extracted
            shortcuts_folder: Folder where shortcuts will be created
            library: Current game library for matching
        """
        self.games_folder = Path(games_folder)
        self.shortcuts_folder = Path(shortcuts_folder)
        self.library = library
        self._library_index: Dict[str, Game] = {}
        self._build_library_index()

        # Load custom passwords
        load_custom_passwords()

    def _build_library_index(self) -> None:
        """Build an index of library games by normalized title."""
        self._library_index.clear()
        for game in self.library:
            key = normalize_title(game.title)
            self._library_index[key] = game

    def scan_folder(
        self,
        source_folder: Path,
        recursive: bool = True,
    ) -> List[ImportItem]:
        """
        Scan a folder for archives and create import items.
        """
        _log.info("scan_start %s", kv(folder=str(source_folder), recursive=recursive))

        archives = scan_for_archives(Path(source_folder), recursive)
        items: List[ImportItem] = []

        for archive in archives:
            match = self._match_to_library(archive)
            item = ImportItem(archive=archive, match=match)
            items.append(item)

        _log.info("scan_complete %s", kv(
            archives=len(archives),
            new=sum(1 for i in items if i.match.action == ImportAction.IMPORT_NEW),
            updates=sum(1 for i in items if i.match.action == ImportAction.UPDATE_EXISTING),
            skipped=sum(1 for i in items if i.match.action in (ImportAction.SKIP_OLDER, ImportAction.SKIP_DUPLICATE)),
        ))

        return items

    def _match_to_library(self, archive: ScannedArchive) -> MatchResult:
        """
        Match an archive to existing library entries.
        """
        if not archive.detected_title:
            return MatchResult(action=ImportAction.IMPORT_NEW)

        normalized = normalize_title(archive.detected_title)

        # Exact match
        if normalized in self._library_index:
            game = self._library_index[normalized]
            return self._compare_versions(archive, game)

        # Fuzzy match
        best_match: Optional[Game] = None
        best_similarity = 0.0

        for game in self.library:
            similarity = calculate_title_similarity(archive.detected_title, game.title)
            if similarity > best_similarity and similarity >= 0.8:
                best_similarity = similarity
                best_match = game

        if best_match:
            result = self._compare_versions(archive, best_match)
            result.similarity = best_similarity
            return result

        return MatchResult(action=ImportAction.IMPORT_NEW)

    def _compare_versions(self, archive: ScannedArchive, game: Game) -> MatchResult:
        """
        Compare versions between archive and existing game.
        """
        result = MatchResult(
            matched_game=game,
            similarity=1.0,
        )

        archive_ver = archive.detected_version
        installed_ver = game.installed_version_raw or game.source_version_raw

        if not archive_ver:
            # No version in archive name, assume update
            result.action = ImportAction.UPDATE_EXISTING
            result.notes = "No version detected in archive"
            return result

        if not installed_ver:
            # No installed version, allow update
            result.action = ImportAction.UPDATE_EXISTING
            result.notes = "No installed version to compare"
            return result

        # Parse and compare versions
        archive_parsed = parse_version(archive_ver)
        installed_parsed = parse_version(installed_ver)
        cmp = compare_versions(archive_parsed, installed_parsed)

        result.version_compare = cmp

        if cmp == CompareResult.NEWER:
            result.action = ImportAction.UPDATE_EXISTING
            result.notes = f"Archive {archive_ver} is newer than installed {installed_ver}"
        elif cmp == CompareResult.OLDER:
            result.action = ImportAction.SKIP_OLDER
            result.notes = f"Archive {archive_ver} is older than installed {installed_ver}"
        elif cmp == CompareResult.SAME:
            result.action = ImportAction.SKIP_DUPLICATE
            result.notes = f"Same version {archive_ver}"
        else:
            result.action = ImportAction.CONFLICT
            result.notes = f"Cannot compare versions: archive={archive_ver}, installed={installed_ver}"

        return result

    def execute_import(
        self,
        items: List[ImportItem],
        progress: Optional[ImportProgressCallback] = None,
        delete_archives: bool = False,
    ) -> ImportResult:
        """
        Execute the import for selected items.

        Args:
            items: List of items to import
            progress: Progress callback
            delete_archives: Delete archives after successful extraction

        Returns:
            ImportResult with statistics
        """
        result = ImportResult(total=len(items), items=items)

        for i, item in enumerate(items):
            if progress:
                progress("import", i + 1, len(items), f"Processing {item.display_title}")

            # Skip based on action
            action = item.final_action
            if action in (ImportAction.SKIP_OLDER, ImportAction.SKIP_DUPLICATE, ImportAction.SKIP_USER):
                item.status = ImportStatus.SKIPPED
                result.skipped += 1
                continue

            try:
                # Extract
                if progress:
                    progress("extract", i + 1, len(items), f"Extracting {item.archive.name}")

                item.status = ImportStatus.EXTRACTING
                extract_result = self._extract_archive(item)

                if not extract_result.success:
                    item.status = ImportStatus.FAILED
                    item.error = extract_result.error
                    result.failed += 1
                    continue

                item.extracted_path = extract_result.extracted_path
                item.status = ImportStatus.EXTRACTED

                # Find executable
                executables = find_executables(Path(item.extracted_path))
                if executables:
                    item.executable_path = str(executables[0])

                # Create shortcut
                if progress:
                    progress("shortcut", i + 1, len(items), f"Creating shortcut for {item.display_title}")

                item.status = ImportStatus.CREATING_SHORTCUT
                shortcut_path = self._create_shortcut(item)
                if shortcut_path:
                    item.shortcut_path = shortcut_path

                # Generate game ID
                item.game_id = str(uuid.uuid4())
                item.status = ImportStatus.COMPLETE

                if action == ImportAction.UPDATE_EXISTING:
                    result.updated += 1
                else:
                    result.imported += 1

                # Delete archive if requested
                if delete_archives:
                    self._delete_archive(item)

            except Exception as e:
                _log.error("import_error %s", kv(
                    archive=item.archive.name,
                    err=str(e)
                ))
                item.status = ImportStatus.FAILED
                item.error = str(e)
                result.failed += 1

        _log.info("import_complete %s", kv(
            total=result.total,
            imported=result.imported,
            updated=result.updated,
            skipped=result.skipped,
            failed=result.failed,
        ))

        return result

    def _extract_archive(self, item: ImportItem) -> ExtractionResult:
        """Extract an archive to the games folder."""
        # Create destination folder
        folder_name = self._safe_folder_name(item.display_title)
        dest = self.games_folder / folder_name

        # Handle existing folder
        if dest.exists():
            if item.final_action == ImportAction.UPDATE_EXISTING:
                # Backup or remove old version
                backup_dir = self.games_folder / ".backups"
                backup_dir.mkdir(exist_ok=True)
                backup_name = f"{folder_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                shutil.move(str(dest), str(backup_dir / backup_name))
            else:
                # Add suffix for new game with same name
                suffix = 1
                while dest.exists():
                    dest = self.games_folder / f"{folder_name}_{suffix}"
                    suffix += 1

        # Extract
        result = extract_archive(
            item.archive.path,
            destination=dest,
            try_common_passwords=True,
        )

        return result

    def _create_shortcut(self, item: ImportItem) -> str:
        """Create a shortcut for the imported game."""
        if not item.executable_path:
            return ""

        try:
            # Import here to avoid circular imports
            from external.scanner.GameShortcutMaker.shortcut_manager import (
                create_or_replace_shortcut,
                safe_filename,
            )

            shortcut_name = safe_filename(item.display_title)
            shortcut_path = self.shortcuts_folder / f"{shortcut_name}.lnk"

            create_or_replace_shortcut(str(shortcut_path), item.executable_path)

            return str(shortcut_path)

        except Exception as e:
            _log.warning("shortcut_create_error %s", kv(
                title=item.display_title,
                err=str(e)
            ))
            return ""

    def _delete_archive(self, item: ImportItem) -> None:
        """Delete archive files after successful extraction."""
        try:
            if item.archive.is_multipart:
                for part in item.archive.parts:
                    if part.exists():
                        os.remove(part)
            else:
                if item.archive.path.exists():
                    os.remove(item.archive.path)
        except Exception as e:
            _log.warning("archive_delete_error %s", kv(
                archive=item.archive.name,
                err=str(e)
            ))

    def _safe_folder_name(self, title: str) -> str:
        """Create a safe folder name from a game title."""
        # Remove/replace invalid characters
        name = re.sub(r'[<>:"/\\|?*]', "", title)
        name = re.sub(r"\s+", " ", name).strip()
        return name if name else "Game"

    def create_game_entry(self, item: ImportItem) -> Game:
        """
        Create a Game entry from an imported item.
        """
        save_folder = find_save_folder(Path(item.extracted_path)) if item.extracted_path else None

        game = Game(
            game_id=item.game_id or str(uuid.uuid4()),
            title=item.display_title,
            shortcut_path=item.shortcut_path,
            shortcut_type="lnk" if item.shortcut_path.endswith(".lnk") else "",
            backup_target_path=item.executable_path,
            backup_working_dir=str(Path(item.executable_path).parent) if item.executable_path else "",
            status="backlog",
            confidence="high",
            installed_version_raw=item.archive.detected_version,
            archive_folder_path=item.extracted_path,
            compressed_archive_path=str(item.archive.path),
            game_folder_path=item.extracted_path,
            install_path=item.extracted_path,
            executable_path=item.executable_path,
            save_folder_path=str(save_folder) if save_folder else "",
        )

        # Copy data from matched game if updating
        if item.match.matched_game and item.final_action == ImportAction.UPDATE_EXISTING:
            existing = item.match.matched_game
            game.game_id = existing.game_id
            game.status = existing.status
            game.rating = existing.rating
            game.tags = existing.tags
            game.notes = existing.notes
            game.source_url = existing.source_url
            game.f95_thread_id = existing.f95_thread_id
            game.f95_category = existing.f95_category
            game.f95_tags = existing.f95_tags
            game.developer = existing.developer

        return game


def format_size(size_bytes: int) -> str:
    """Format a file size in bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
