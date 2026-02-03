# Agent Context Document

> **Purpose:** Preserves context for AI agents to reduce exploration time and save context window.
> **Last Updated:** 2026-02-03
> **Project:** Game Library Manager v4

---

## Quick Reference

| Metric | Value |
|--------|-------|
| Lines of Code | ~21,250 |
| Files | 97 Python files |
| Framework | PySide6 (Qt) |
| Platform | Windows |
| Entry Point | `src/main.py` |

---

## Project Structure

```
src/app/
├── models/
│   ├── game.py              # Game dataclass (core entity)
│   └── collection.py        # Collection dataclass
├── services/
│   ├── archive/             # [MOD-003] Archive extraction (5 modules)
│   │   ├── models.py        # ArchiveFormat, ExtractionResult, ScannedArchive
│   │   ├── detection.py     # Format detection, multipart handling
│   │   ├── passwords.py     # Password management
│   │   ├── extraction.py    # ZIP/RAR/7z extraction
│   │   └── utils.py         # Scanning, title parsing
│   ├── download/            # [MOD-004] Download manager (3 modules)
│   │   ├── models.py        # DownloadStatus, DownloadItem, DownloadHistory
│   │   ├── worker.py        # DownloadWorker QThread
│   │   └── manager.py       # DownloadManager with queue
│   ├── host_handlers/       # Download site handlers (7+ handlers)
│   │   ├── base.py          # HostHandler ABC
│   │   ├── mega.py, gofile.py, pixeldrain.py, mediafire.py, ...
│   ├── http_utils.py        # [DUP-001] Centralized HTTP (USER_AGENT, download_file)
│   ├── title_matcher.py     # [DUP-002] Fuzzy matching (TitleIndex)
│   ├── filter_utils.py      # [SPRINT-3] Search/filter utilities (SearchCache)
│   ├── f95_api.py           # F95zone thread parsing (703 lines - needs split)
│   ├── f95_auth.py          # F95zone auth (679 lines - needs split)
│   ├── smart_download.py    # Download coordination (626 lines)
│   └── ... (25+ more services)
├── storage/
│   ├── json_store.py        # Library/settings persistence
│   └── paths.py             # Storage path utilities
└── ui/
    ├── main_window/         # [MOD-001] Main window package (10 mixins)
    │   ├── window.py        # Core MainWindow (~576 lines)
    │   ├── scan_mixin.py    # Shortcut scanning
    │   ├── update_mixin.py  # Version checking
    │   ├── filter_mixin.py  # Search and filtering
    │   ├── dialog_mixin.py  # Dialog management
    │   ├── collection_mixin.py  # Collection CRUD
    │   ├── game_ops_mixin.py    # Game operations
    │   ├── actions_mixin.py     # Shortcuts, export/import
    │   ├── ui_mixin.py          # UI helpers, startup
    │   └── batch_mixin.py       # Multi-select operations
    ├── widgets/
    │   ├── game_grid/       # [MOD-002] Game grid package (4 modules)
    │   │   ├── grid.py      # GameGrid layout (~570 lines)
    │   │   ├── card.py      # GameCard widget (~589 lines)
    │   │   ├── skeleton.py  # Loading skeleton
    │   │   └── display_utils.py  # Status label, stars, time
    │   ├── details_panel.py # Game details sidebar
    │   ├── downloads_panel.py
    │   └── ... (8+ widgets)
    ├── dialogs/             # 8+ dialog implementations
    │   ├── bulk_archive_import_dialog.py  # 751 lines - NEEDS SPLIT
    │   └── ...
    ├── workers/             # Background threads
    │   └── base_worker.py   # [DUP-003] BaseWorker, CancellableWorker
    └── theme.py, typography.py
```

---

## Code Quality Plan Status

**Reference:** `docs/CODE_QUALITY_PLAN.md` (authoritative planning document)

### Completed Sprints

| Sprint | Focus | Status |
|--------|-------|--------|
| Sprint 1 | Critical Bug Fixes (P0, P1) | ✅ Complete |
| Sprint 2 | Code Deduplication | ✅ Complete |
| Sprint 3 | Modularization Part 1 | ✅ Complete |
| Sprint 4 | Modularization Part 2 | ✅ Complete |

### Current Sprint: Sprint 5 (Performance)

| Task | Status | Notes |
|------|--------|-------|
| PERF-001: Fuzzy matching index | ✅ Done | TitleIndex in title_matcher.py |
| PERF-002: Search haystack caching | ✅ Done | SearchCache in filter_utils.py |
| PERF-003: Virtual scrolling | ⏳ Pending | GameGrid needs implementation |
| PERF-004: LRU cache bounds | ✅ Done | BoundedCache in http_utils.py, used by update_checker.py |

### Next Sprint: Sprint 6 (Architecture)

- ARCH-001: Repository pattern for data access
- ARCH-002: Event bus for decoupled communication
- ARCH-003: Configuration management system
- Test coverage: 0.2% → 60% target

---

## Files Exceeding Size Limits

| File | Lines | Target | Priority |
|------|-------|--------|----------|
| `f95_api.py` | 703 | <500 | MEDIUM |
| `f95_auth.py` | 679 | <500 | MEDIUM |
| `bulk_archive_import_dialog.py` | 626 | <500 | LOW (reduced from 751) |
| `smart_download.py` | 626 | <500 | LOW |
| `game_grid/card.py` | 589 | <500 | LOW |
| `main_window/window.py` | 576 | <500 | LOW (core) |

---

## Key Patterns

### Mixin Pattern (main_window/)
```python
class MainWindow(QMainWindow, ScanMixin, UpdateMixin, FilterMixin, ...):
    # Core window inherits from multiple mixins
    # Each mixin provides specific functionality
```

### Shared Utilities
```python
# HTTP: Always use http_utils
from app.services.http_utils import USER_AGENT, create_request, download_file

# Title matching: Use title_matcher
from app.services.title_matcher import TitleIndex, normalize_title

# Filtering: Use filter_utils
from app.services.filter_utils import FilterConfig, filter_and_sort_games
```

### Storage with Fallback
```python
# json_store.py pattern: primary path → temp fallback on error
try:
    path.write_text(data)
except Exception:
    fb_path = temp_data_dir() / path.name
    fb_path.write_text(data)
    _warn_fallback(fb_path)
```

### Worker Pattern
```python
# Use BaseWorker from ui/workers/base_worker.py
class MyWorker(BaseWorker):
    def do_work(self) -> Any:
        # Override this, not run()
        return result
```

---

## Known Issues / TODOs

1. **Multi-click link handling incomplete** (smart_download.py:368)
   - TODO: Needs JavaScript execution for full support

2. **Test coverage minimal** (~0.2%)
   - Location: `src/tests/` (only 3 test files)
   - Framework: Simple assertions (not pytest)

3. **F95 API module too large** (703 lines)
   - Should split: URL normalization, parsing, link extraction

---

## Commands

```bash
# Run application
python src/main.py

# Run tests (basic)
python src/tests/guardrails_check.py
python src/tests/test_json_store_dt.py
python src/tests/test_version_parser.py
```

---

## Recent Changes (This Session)

1. **Fixed P1-001**: Added error handling with fallback to `save_library_bundle()` in json_store.py
2. **Fixed P1-010**: Added initial progress emission in http_utils.py `download_file()` for fast downloads
3. **Implemented PERF-004**: Added `BoundedCache` class to http_utils.py, applied to update_checker.py
4. **Split bulk_archive_import_dialog.py**: Extracted workers to bulk_archive_workers.py (70 lines) and PasswordManagerWidget to widgets/password_manager.py (130 lines)
5. **Created AGENT.md**: This document for context preservation

---

## Data Locations

| Data | Path |
|------|------|
| User data | `%APPDATA%/GameLibraryManager/` |
| Library | `library.json` |
| Settings | `settings.json` |
| Logs | `manager.log` (rotating) |
| F95 Session | `f95_session.json` |
| F95 Credentials | `f95_auth.enc` (encrypted) |

---

## Import Structure

```python
# Public API via services/__init__.py
from app.services import (
    # Core
    load_fake_games, scan_shortcut_root, launch_game,
    # HTTP
    USER_AGENT, create_request, download_file,
    # Matching
    TitleIndex, normalize_title, calculate_similarity,
    # Filtering
    FilterConfig, filter_and_sort_games,
    # F95
    F95AuthManager, get_auth_manager,
    # Archive
    extract_archive, scan_for_archives,
    # Download
    DownloadManager, get_download_manager,
)
```

---

## Architecture Notes

1. **No circular imports** - Clean dependency graph
2. **No wildcard imports** - Explicit imports throughout
3. **Logging via logging_utils** - `get_logger("module_name")`
4. **Thread safety** - QMutex/QMutexLocker for shared state
5. **Error propagation** - Custom exceptions with context

---

*This document should be read first by any agent working on this codebase to minimize exploration time.*
