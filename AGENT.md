# Agent Context Document

> **Purpose:** Preserves context for AI agents to reduce exploration time and save context window.
> **Last Updated:** 2026-02-13
> **Project:** Game Library Manager v4

---

## Quick Reference

| Metric | Value |
|--------|-------|
| Lines of Code | ~24,500 |
| Files | 108 Python files |
| Tests | 225 (pytest) |
| Framework | PySide6 (Qt) |
| Platform | Windows |
| Entry Point | `src/main.py` |

---

## Project Structure

```
src/app/
├── config.py               # [ARCH-003] Type-safe AppConfig dataclass
├── events.py               # [ARCH-002] EventBus pub/sub system
├── models/
│   ├── game.py              # Game dataclass (core entity, uses enum defaults)
│   ├── collection.py        # Collection dataclass
│   └── enums.py             # [TASK-4] GameStatus, SortMode, QuickFilter, etc.
├── repositories/            # [ARCH-001] Data access abstraction
│   ├── game_repository.py   # GameRepository ABC
│   └── json_game_repository.py  # JSON-backed implementation
├── services/
│   ├── archive/             # [MOD-003] Archive extraction (5 modules)
│   ├── download/            # [MOD-004] Download manager (3 modules)
│   ├── host_handlers/       # Download site handlers (7+ handlers)
│   ├── http_utils.py        # [DUP-001] Centralized HTTP
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
    │   ├── window.py        # Core MainWindow (uses AppConfig, EventBus, Repository)
    │   ├── scan_mixin.py    # Shortcut scanning (emits GAMES_CHANGED event)
    │   ├── update_mixin.py  # Version checking
    │   ├── filter_mixin.py  # Search and filtering
    │   ├── dialog_mixin.py  # Dialog management
    │   ├── collection_mixin.py  # Collection CRUD (uses repo.save())
    │   ├── game_ops_mixin.py    # Game operations (debounced saves, O(1) lookups)
    │   ├── actions_mixin.py     # Shortcuts, export/import
    │   ├── ui_mixin.py          # UI helpers, startup (uses config.save())
    │   └── batch_mixin.py       # Multi-select operations
    ├── widgets/
    │   ├── game_grid/       # [MOD-002] Game grid package (4 modules)
    │   │   ├── grid.py      # GameGrid layout (~570 lines)
    │   │   ├── card.py      # GameCard widget (persists dominant_color_hex)
    │   │   ├── skeleton.py  # Loading skeleton
    │   │   └── display_utils.py  # Status label, stars, time
    │   └── ... (8+ widgets)
    ├── dialogs/             # 8+ dialog implementations
    ├── workers/             # Background threads
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
| Sprint 5 | Performance | ✅ Complete |

### Current Sprint: Sprint 6 (Architecture + Testing) — In Progress

| Task | Status | Notes |
|------|--------|-------|
| Task 1: Debounced Library Saves | ✅ Done | 500ms QTimer coalesces writes; closeEvent flushes |
| Task 2: Persist Dominant Colors | ✅ Done | `dominant_color_hex` field on Game; card.py checks persisted first |
| Task 3: Game Lookup Index | ✅ Done | `_games_by_id` Dict for O(1) lookups; `_rebuild_game_index()` |
| Task 4: Enums (str, Enum) | ✅ Done | `enums.py`: GameStatus, SortMode, QuickFilter, Confidence, etc. |
| Task 5: Repository Pattern (ARCH-001) | ✅ Done | `GameRepository` ABC + `JsonGameRepository`; injected into MainWindow |
| Task 6: Event Bus (ARCH-002) | ✅ Done | `EventBus` + `AppEvent` enum; scan_mixin emits GAMES_CHANGED |
| Task 7: Configuration Mgmt (ARCH-003) | ✅ Done | `AppConfig` dataclass; dict-compat interface for mixins |
| Task 8: pytest Migration + Tests | ✅ Done | 225 tests passing; 7 new test files + pyproject.toml |
| Task 9: Keyboard Navigation | ✅ Done | All shortcuts implemented in actions_mixin.py; Ctrl+F, Escape, Return, Delete, etc. |
| Task 10: Virtual Scrolling | ⬜ Pending | Major refactoring - requires QListView or manual virtual scroll |
| Task 11: Inline Grid Interactions | ✅ Done | Rating stars always visible & clickable; status bar click-to-cycle; context menu |
| Task 12: Drag-and-Drop to Collections | ✅ Done | Card drag + sidebar drop implemented; game_dropped_on_collection signal |
| Task 13: Named Views | ⬜ Pending | Save filter/search combos as reusable views |
| Task 14: Custom Exception Hierarchy | ✅ Done | `exceptions.py` with AppError, StorageError, NetworkError, ParseError, LaunchError, AuthError |
| Task 15: Split Oversized Files | ⬜ Pending | 6 files exceed 500 lines; requires module extraction |
| Task 16: CI Pipeline | ✅ Done | `.github/workflows/ci.yml` with pytest, coverage, ruff lint, Python 3.11/3.12 matrix |

### New Architecture (Sprint 6)

```python
# Repository pattern: data access via self._repo
self._repo = JsonGameRepository(library_json_path())
self._all_games = self._repo.get_all()
g = self._repo.get_by_id(game_id)  # O(1) lookup

# Event bus: decoupled communication
self._bus = EventBus()
self._bus.on(AppEvent.GAMES_CHANGED, handler)
self._bus.emit(AppEvent.GAMES_CHANGED)

# AppConfig: typed settings
self._config = AppConfig.load()
self._config.theme  # IDE autocompletion
self._config.save()

# Debounced saves: _persist_library() → 500ms timer → _save_bundle()
self._persist_library()  # queues write
self._flush_save()       # immediate write (scan, close)
```

---

## Files Exceeding Size Limits

| File | Lines | Target | Priority |
|------|-------|--------|----------|
| `f95_api.py` | 703 | <500 | MEDIUM |
| `f95_auth.py` | 679 | <500 | MEDIUM |
| `bulk_archive_import_dialog.py` | 626 | <500 | LOW |
| `smart_download.py` | 626 | <500 | LOW |
| `game_grid/card.py` | 589 | <500 | LOW |
| `main_window/window.py` | ~730 | <500 | LOW (core) |

---

## Key Patterns

### Repository Pattern (new)
```python
from app.repositories import JsonGameRepository
repo = JsonGameRepository(path)
games = repo.get_all()
game = repo.get_by_id("id")
repo.add(game)
repo.remove("id")
repo.save()
```

### Event Bus (new)
```python
from app.events import EventBus, AppEvent
bus = EventBus()
bus.on(AppEvent.GAMES_CHANGED, lambda data: handle(data))
bus.emit(AppEvent.GAMES_CHANGED, optional_data)
```

### Enums (new)
```python
from app.models.enums import GameStatus, SortMode, QuickFilter
g.status == GameStatus.PLAYING  # also == "playing"
```

### Mixin Pattern (main_window/)
```python
class MainWindow(QMainWindow, ScanMixin, UpdateMixin, FilterMixin, ...):
    # Core window inherits from multiple mixins
```

### Shared Utilities
```python
from app.services.http_utils import USER_AGENT, create_request, download_file
from app.services.title_matcher import TitleIndex, normalize_title
from app.services.filter_utils import FilterConfig, filter_and_sort_games
```

---

## Known Issues / TODOs

1. **Multi-click link handling incomplete** (smart_download.py:368)
2. **F95 API module too large** (703 lines) — needs split (Task 15)
3. **No CI pipeline** — Task 16

---

## Commands

```bash
# Run application
python src/main.py

# Run full test suite (225 tests)
PYTHONPATH=src python -m pytest src/tests/ -v

# Run with coverage
PYTHONPATH=src python -m pytest src/tests/ --cov=src/app --cov-report=term-missing
```

---

## Recent Changes (This Session — Sprint 6)

### Previous Session (Tasks 1-8)
1. **Task 1: Debounced saves** — 500ms QTimer coalesces _persist_library() calls (window.py, game_ops_mixin.py, scan_mixin.py)
2. **Task 2: Persist dominant colors** — `dominant_color_hex` field on Game; card.py checks persisted hex before pixel extraction
3. **Task 3: Game lookup index** — `_games_by_id` Dict[str, Game] for O(1) lookups; replaces linear scans in all mixins
4. **Task 4: Enums** — `enums.py` with GameStatus, SortMode, QuickFilter, Confidence, ShortcutType, ViewMode; backward-compat (str, Enum)
5. **Task 5: Repository pattern** — `GameRepository` ABC + `JsonGameRepository`; _save_bundle() delegates to repo.save()
6. **Task 6: Event bus** — `EventBus` + `AppEvent` enum; scan_mixin emits events instead of cross-mixin calls
7. **Task 7: AppConfig** — Type-safe dataclass replacing 25+ .get() calls; dict-compat interface for gradual migration
8. **Task 8: pytest suite** — 225 tests (98 new): filter_utils, game_model, version_parser, title_matcher, events, config, repository

### Current Session (Tasks 9-16 Review)
9. **Task 9: Keyboard shortcuts** — Already complete; actions_mixin.py has all shortcuts (Ctrl+F, Escape, Return, Delete, E, Ctrl+N, Ctrl+S, F5, Ctrl+U, Ctrl+Shift+/)
10. **Task 11: Inline interactions** — Already complete; rating stars always visible & clickable (card.py:211-251), status bar click-to-cycle (card.py:176-189), context menu
11. **Task 12: Drag-and-drop** — Already complete; card.py mouseMoveEvent + library_sidebar.py drop events + collection_mixin.py handler
12. **Task 14: Exception hierarchy** — Created exceptions.py with AppError, StorageError, NetworkError, ParseError, LaunchError, AuthError; updated json_store.py, launch_service.py, f95_parser.py, paths.py
13. **Task 16: CI Pipeline** — Already complete; .github/workflows/ci.yml with pytest, coverage, ruff lint, Python 3.11/3.12 matrix, Codecov integration

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
# New modules (Sprint 6)
from app.config import AppConfig
from app.events import EventBus, AppEvent
from app.repositories import JsonGameRepository, GameRepository
from app.models.enums import GameStatus, SortMode, QuickFilter, Confidence

# Existing public API via services/__init__.py
from app.services import (
    load_fake_games, scan_shortcut_root, launch_game,
    USER_AGENT, create_request, download_file,
    TitleIndex, normalize_title, calculate_similarity,
    FilterConfig, filter_and_sort_games,
    F95AuthManager, get_auth_manager,
    extract_archive, scan_for_archives,
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
6. **Debounced I/O** - Library saves coalesced via QTimer
7. **Decoupled components** - EventBus for inter-mixin communication
8. **Testable architecture** - Repository pattern enables mock data access

---

*This document should be read first by any agent working on this codebase to minimize exploration time.*
