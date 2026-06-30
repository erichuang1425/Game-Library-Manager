# Next Sprint: Immediate Task List

> **Purpose:** Comprehensive, actionable task document for future implementation work.
> **Last Updated:** 2026-02-13
> **Prerequisites:** Review the README, architecture notes, and current code before starting tasks.
> **Builds On:** `docs/CODE_QUALITY_PLAN.md` (Sprints 1-5 complete), `docs/IMPROVEMENTS.md` (issue catalog)

---

## Quick Context

- **Project:** Game Library Manager v4 — PySide6 desktop app for managing game shortcut libraries
- **Codebase:** ~23,900 lines across 104 Python files
- **Entry Point:** `src/main.py`
- **Architecture:** Mixin-based MainWindow (10 mixins) + service layer (43 modules) + JSON storage
- **Completed:** Sprints 1-5 (bug fixes, deduplication, modularization, performance)
- **Current Sprint:** Sprint 6 — Architecture + Performance + Interface + Testing

---

## Task Priority Order

Execute tasks in this order. Each task is self-contained with exact file paths, current behavior, and target behavior.

---

## TASK 1: Debounced Library Saves (Performance — Quick Win)

**Problem:** Every single game edit triggers a full `save_library_bundle()` call that serializes the entire `_all_games` list to JSON. During bulk operations (batch tag edits, imports, scans), this means N redundant full-file writes.

**Current Flow:**
```
game_ops_mixin.py → _on_game_changed() → _persist_library() → _save_bundle()
    → json_store.py:save_library_bundle() → writes entire library.json every time
```

**Files to Modify:**
- `src/app/ui/main_window/window.py:697-698` — `_persist_library()` calls `_save_bundle()` directly
- `src/app/ui/main_window/game_ops_mixin.py` — calls `_persist_library()` on every edit
- `src/app/ui/main_window/scan_mixin.py` — calls `_persist_library()` after scan
- `src/app/ui/main_window/actions_mixin.py` — calls `_persist_library()` after import

**Implementation:**
1. Add a `QTimer`-based dirty flag + coalesced write to `window.py`:
```python
# In MainWindow.__init__():
self._save_timer = QTimer(self)
self._save_timer.setSingleShot(True)
self._save_timer.setInterval(500)  # 500ms debounce
self._save_timer.timeout.connect(self._flush_save)
self._save_dirty = False

# Replace _persist_library():
def _persist_library(self) -> None:
    self._save_dirty = True
    self._save_timer.start()  # resets timer on each call

def _flush_save(self) -> None:
    if self._save_dirty:
        self._save_bundle()
        self._save_dirty = False

# In closeEvent():
def closeEvent(self, event):
    self._flush_save()  # ensure final save
    super().closeEvent(event)
```

2. Keep existing `_save_bundle()` implementation unchanged — only the trigger timing changes.

**Impact:** Eliminates redundant I/O. A batch edit of 50 games goes from 50 writes → 1 write.

**Tests:** Add `src/tests/test_debounced_save.py` — verify that rapid `_persist_library()` calls result in single `_save_bundle()` invocation.

---

## TASK 2: Persist Dominant Colors in Game Model (Performance — Quick Win)

**Problem:** `color_extractor.py` uses an in-memory `Dict[str, Optional[QColor]]` cache that is lost on restart. Every app launch re-extracts dominant colors for all visible cards by sampling pixels on a 32×32 scaled image.

**Current Implementation:**
- `src/app/services/color_extractor.py:12-21` — `_dominant_color_cache` dict, populated via `get_cached_dominant_color()`
- `src/app/ui/widgets/game_grid/card.py:25-26` — imports and calls `get_cached_dominant_color()` during card build
- Cache is per-session only; cleared on theme change via `clear_dominant_color_cache()`

**Implementation:**
1. Add a field to `src/app/models/game.py`:
```python
dominant_color_hex: str = ""  # cached hex color from icon, e.g. "#3a7bd5"
```

2. In `card.py`, when dominant color is extracted for a card, persist it back:
```python
color = get_cached_dominant_color(icon_path, pixmap)
if color and not game.dominant_color_hex:
    game.dominant_color_hex = color.name()  # "#rrggbb"
    # No immediate save — debounced save (Task 1) handles it
```

3. In `card.py` card build, check persisted color first:
```python
if game.dominant_color_hex:
    color = QColor(game.dominant_color_hex)
else:
    color = get_cached_dominant_color(icon_path, pixmap)
```

4. `json_store.py` serialization already handles new string fields automatically via `dataclasses.asdict()`.

**Impact:** Eliminates per-pixel extraction on subsequent launches. First launch extracts; all future launches use persisted hex values.

---

## TASK 3: Game Lookup Index (Performance — Quick Win)

**Problem:** `_all_games` is a `List[Game]`. Finding a game by ID requires linear scan: `next((g for g in self._all_games if g.game_id == game_id), None)`. This pattern appears in multiple mixins.

**Files with linear lookups:**
- `src/app/ui/main_window/game_ops_mixin.py` — `_on_game_selected`, `_on_game_changed`
- `src/app/ui/main_window/collection_mixin.py` — collection game resolution
- `src/app/ui/main_window/scan_mixin.py` — merge logic
- `src/app/services/filter_utils.py` — SearchCache keyed by game_id

**Implementation:**
1. In `window.py`, add a dict index alongside `_all_games`:
```python
self._all_games, self._collections = load_library_bundle(library_json_path())
self._games_by_id: Dict[str, Game] = {g.game_id: g for g in self._all_games}
```

2. Add helper methods:
```python
def _get_game(self, game_id: str) -> Optional[Game]:
    return self._games_by_id.get(game_id)

def _add_game(self, game: Game) -> None:
    self._all_games.append(game)
    self._games_by_id[game.game_id] = game

def _remove_game_by_id(self, game_id: str) -> None:
    self._all_games = [g for g in self._all_games if g.game_id != game_id]
    self._games_by_id.pop(game_id, None)
```

3. Replace linear lookups in mixins with `self._get_game(game_id)`.

4. Rebuild index after scans/imports that modify `_all_games`:
```python
def _rebuild_game_index(self) -> None:
    self._games_by_id = {g.game_id: g for g in self._all_games}
```

**Impact:** O(1) game lookups instead of O(n). Critical for large libraries (1000+ games).

---

## TASK 4: Enums for Status, Sort, and Filter Modes (Logic — Quick Win)

**Problem:** Filter keys, sort modes, and game statuses are passed as raw strings throughout the codebase. Typos silently produce wrong behavior.

**Current examples:**
- `window.py:87` — `self._quick_filter: str = "all"`
- `window.py:92` — `self._sort_by: str = "title"`
- `game.py:22` — `status: str = "backlog"`
- `filter_utils.py:22-28` — `FilterConfig` uses string fields

**Implementation:**
1. Create `src/app/models/enums.py`:
```python
from enum import Enum

class GameStatus(str, Enum):
    BACKLOG = "backlog"
    PLAYING = "playing"
    FINISHED = "finished"
    DROPPED = "dropped"

class SortMode(str, Enum):
    TITLE = "title"
    LAST_PLAYED = "last_played"
    RATING = "rating"
    LAUNCH_COUNT = "launch_count"
    LAST_CHECKED = "last_checked"

class QuickFilter(str, Enum):
    ALL = "all"
    MISSING = "missing"
    UPDATES = "updates"
    SOURCE = "source"

class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ShortcutType(str, Enum):
    LNK = "lnk"
    URL = "url"
    HTML = "html"

class ViewMode(str, Enum):
    COMFORTABLE = "comfortable"
    COMPACT = "compact"
```

2. Using `str, Enum` ensures backward compatibility — enum values serialize as plain strings in JSON, so `json_store.py` needs no changes.

3. Update `models/__init__.py` to export enums.

4. Update `filter_utils.py:FilterConfig` to use enum types.

5. Update `game.py` status and confidence fields to use enum defaults.

6. Gradually update comparisons in mixins: `self._sort_by == SortMode.TITLE` instead of `self._sort_by == "title"`.

**Impact:** Catches typos at import time. IDE autocompletion for all filter/sort values.

---

## TASK 5: Repository Pattern (Architecture — ARCH-001)

**Problem:** Data access is scattered across 10 mixins. Each mixin directly reads/writes `self._all_games`, `self._collections`, and calls `self._save_bundle()`. This makes unit testing impossible without a full MainWindow instance.

**Current data access points (grep for `self._all_games`):**
- `window.py:107, 117` — load + assign
- `filter_mixin.py` — reads for filtering
- `scan_mixin.py` — appends/merges after scan
- `game_ops_mixin.py` — modifies individual games
- `collection_mixin.py` — reads for collection membership
- `actions_mixin.py` — reads/writes for import/export
- `dialog_mixin.py` — passes to dialogs
- `batch_mixin.py` — batch modifications

**Implementation:**

1. Create `src/app/repositories/__init__.py` and `src/app/repositories/game_repository.py`:

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from app.models import Game, Collection

class GameRepository(ABC):
    """Abstract interface for game data access."""

    @abstractmethod
    def get_all(self) -> List[Game]:
        """Return all games."""

    @abstractmethod
    def get_by_id(self, game_id: str) -> Optional[Game]:
        """Return a game by ID, or None."""

    @abstractmethod
    def add(self, game: Game) -> None:
        """Add a game to the repository."""

    @abstractmethod
    def remove(self, game_id: str) -> None:
        """Remove a game by ID."""

    @abstractmethod
    def save(self) -> None:
        """Persist all changes."""

    @abstractmethod
    def get_collections(self) -> List[Collection]:
        """Return all collections."""

    @abstractmethod
    def save_collections(self, collections: List[Collection]) -> None:
        """Persist collections."""

    @property
    @abstractmethod
    def count(self) -> int:
        """Return total game count."""
```

2. Create `src/app/repositories/json_game_repository.py`:

```python
class JsonGameRepository(GameRepository):
    """JSON file-backed game repository with O(1) lookups."""

    def __init__(self, library_path: Path, settings_path: Path):
        self._library_path = library_path
        games, collections = load_library_bundle(library_path)
        self._games: List[Game] = games
        self._index: Dict[str, Game] = {g.game_id: g for g in games}
        self._collections: List[Collection] = collections

    def get_all(self) -> List[Game]:
        return self._games

    def get_by_id(self, game_id: str) -> Optional[Game]:
        return self._index.get(game_id)

    def add(self, game: Game) -> None:
        self._games.append(game)
        self._index[game.game_id] = game

    def remove(self, game_id: str) -> None:
        self._games = [g for g in self._games if g.game_id != game_id]
        self._index.pop(game_id, None)

    def save(self) -> None:
        save_library_bundle(self._library_path, self._games, self._collections)

    # ... etc.
```

3. Inject into MainWindow:
```python
# window.py __init__:
from app.repositories import JsonGameRepository
self._repo = JsonGameRepository(library_json_path(), settings_json_path())
self._all_games = self._repo.get_all()  # backward compat reference
```

4. Migrate mixins incrementally — start with `game_ops_mixin.py` (most CRUD), then `scan_mixin.py`.

**Impact:** Enables unit testing services/mixins with mock repositories. Foundation for future SQLite backend.

---

## TASK 6: Event Bus (Architecture — ARCH-002)

**Problem:** Mixins are tightly coupled through direct method calls. `scan_mixin` calls `_rebuild_sidebar()` on `collection_mixin`. `filter_mixin` calls methods on `game_ops_mixin`. Changes in one mixin can break others.

**Current coupling examples (grep for `self._` cross-mixin calls):**
- `scan_mixin.py` → calls `self._rebuild_sidebar()`, `self._rebuild_search_cache()`, `self._apply_search()`
- `game_ops_mixin.py` → calls `self._persist_library()`, `self._refresh_list()`
- `actions_mixin.py` → calls `self._rebuild_search_cache()`, `self._persist_library()`

**Implementation:**

1. Create `src/app/events.py`:

```python
from __future__ import annotations
from enum import Enum, auto
from typing import Any, Callable, Dict, List
from app.logging_utils import get_logger

_log = get_logger("events")

class AppEvent(Enum):
    GAMES_CHANGED = auto()       # after add/edit/delete/import/scan
    GAME_EDITED = auto()         # single game metadata changed (data: game_id)
    LIBRARY_LOADED = auto()      # after initial load or reload
    COLLECTION_CHANGED = auto()  # after collection CRUD
    SCAN_COMPLETE = auto()       # after scan finishes (data: scan_result)
    FILTER_CHANGED = auto()      # after filter/search change
    THEME_CHANGED = auto()       # after theme switch

class EventBus:
    """Lightweight pub/sub event bus for decoupling components."""

    def __init__(self) -> None:
        self._subs: Dict[AppEvent, List[Callable]] = {}

    def on(self, event: AppEvent, callback: Callable) -> None:
        self._subs.setdefault(event, []).append(callback)

    def off(self, event: AppEvent, callback: Callable) -> None:
        if event in self._subs:
            self._subs[event] = [cb for cb in self._subs[event] if cb is not callback]

    def emit(self, event: AppEvent, data: Any = None) -> None:
        for cb in self._subs.get(event, []):
            try:
                cb(data)
            except Exception:
                _log.exception("event_handler_error event=%s", event.name)
```

2. Add to MainWindow:
```python
# window.py __init__:
from app.events import EventBus, AppEvent
self._bus = EventBus()
self._bus.on(AppEvent.GAMES_CHANGED, lambda _: self._rebuild_search_cache())
self._bus.on(AppEvent.GAMES_CHANGED, lambda _: self._rebuild_sidebar())
self._bus.on(AppEvent.GAMES_CHANGED, lambda _: self._apply_search())
self._bus.on(AppEvent.GAME_EDITED, lambda gid: self._search_cache.invalidate(gid))
```

3. Replace direct cross-mixin calls:
```python
# scan_mixin.py BEFORE:
self._rebuild_sidebar()
self._rebuild_search_cache()
self._apply_search()

# scan_mixin.py AFTER:
self._bus.emit(AppEvent.GAMES_CHANGED)
```

**Impact:** Decouples all mixins. Adding a new reaction to "game changed" requires only subscribing, not modifying the emitting mixin.

---

## TASK 7: Configuration Management (Architecture — ARCH-003)

**Problem:** ~25 settings variables live as instance attributes on MainWindow (`window.py:84-103`). Settings are loaded individually with `.get()` fallbacks, modified in-place, and saved via scattered `_save_settings()` calls.

**Current state (window.py:84-103):**
```python
self._root_folder: str = self._settings.get("root_folder", "")
self._view_mode: str = self._settings.get("view_mode", "comfortable")
self._focus_mode: bool = self._settings.get("focus_mode", False)
self._quick_filter: str = self._settings.get("quick_filter", "all")
# ... 20+ more settings
```

**Implementation:**

1. Create `src/app/config.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from pathlib import Path
from app.storage import load_settings, save_settings, settings_json_path

@dataclass
class AppConfig:
    """Type-safe application configuration."""
    root_folder: str = ""
    view_mode: str = "comfortable"
    focus_mode: bool = False
    quick_filter: str = "all"
    tag_filter: Optional[str] = None
    status_filter: str = "all"
    confidence_filter: str = "all"
    type_filter: str = "all"
    sort_by: str = "title"
    updates_filter: str = "all"
    updates_density: str = "comfortable"
    health_filter: str = "all"
    health_density: str = "comfortable"
    details_visible: bool = False
    details_on_launch: bool = False
    details_on_selection: bool = True
    theme: str = "dark"
    font_family: str = "Segoe UI"
    font_scale: str = "default"
    splitter_sizes: Optional[List[int]] = None

    @classmethod
    def load(cls) -> AppConfig:
        raw = load_settings(settings_json_path())
        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in raw.items() if k in known_fields}
        return cls(**filtered)

    def save(self) -> None:
        save_settings(settings_json_path(), asdict(self))

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
```

2. Replace scattered settings in `window.py`:
```python
# BEFORE:
self._settings = load_settings(settings_json_path())
self._root_folder = self._settings.get("root_folder", "")
# ... 20 more lines

# AFTER:
self._config = AppConfig.load()
```

3. Access via `self._config.root_folder`, `self._config.theme`, etc.

4. Save via `self._config.save()` — replaces all scattered `_save_settings()` calls.

**Impact:** Type-safe settings with IDE autocompletion. Single source of truth. Eliminates 25+ `.get()` calls with hardcoded defaults.

---

## TASK 8: pytest Migration + Core Test Suite (Testing)

**Problem:** Test coverage is ~0.2%. Only 3 test files exist, using manual assertion scripts (not pytest). No `conftest.py` fixtures, no parametrize, no mocking infrastructure.

**Current tests:**
- `src/tests/test_version_parser.py` — manual script
- `src/tests/test_json_store_dt.py` — manual script
- `src/tests/guardrails_check.py` — manual script

**Implementation:**

1. Add pytest to `requirements.txt`:
```
pytest>=7.0
pytest-cov>=4.0
```

2. Create `src/tests/conftest.py` with shared fixtures:
```python
import pytest
from app.models import Game

@pytest.fixture
def sample_game():
    return Game(game_id="test-1", title="Test Game", status="backlog")

@pytest.fixture
def sample_games():
    return [
        Game(game_id="1", title="Alpha Game", status="playing", rating=8, tags=["rpg"]),
        Game(game_id="2", title="Beta Game", status="backlog", rating=None, tags=["action"]),
        Game(game_id="3", title="Gamma Game", status="finished", rating=9, tags=["rpg", "action"]),
    ]
```

3. Priority test files to create (highest value first):

**a) `src/tests/test_filter_utils.py`** — Tests for `filter_utils.py` (426 lines, core filtering logic):
- `test_apply_quick_filter_all` — returns all games
- `test_apply_quick_filter_source` — filters to games with source_url
- `test_apply_dropdown_filters_status` — filters by status
- `test_apply_dropdown_filters_tag` — case-insensitive tag filter
- `test_sort_games_by_title` — alphabetical sort
- `test_sort_games_by_rating` — descending, None-safe
- `test_search_cache_build_and_search` — cache builds and finds matches
- `test_search_cache_invalidate` — dirty entries get rebuilt
- `test_filter_and_sort_games` — full pipeline integration test

**b) `src/tests/test_version_parser.py`** — Convert existing manual tests to pytest:
- Parametrize across version formats: numeric, build, season, semver
- Test `compare_versions` edge cases: equal, older, newer, incompatible

**c) `src/tests/test_json_store.py`** — Round-trip serialization:
- `test_save_load_roundtrip` — save games, load back, verify equality
- `test_datetime_serialization` — ISO, epoch, None, legacy formats
- `test_migration_v1_to_v2` — v1 format loads correctly into v2
- `test_unknown_fields_ignored` — forward compatibility

**d) `src/tests/test_game_model.py`** — Model validation:
- `test_default_values` — verify all defaults
- `test_game_equality` — same game_id = same game

**e) `src/tests/test_title_matcher.py`** — Fuzzy matching:
- `test_normalize_title` — version stripping, bracket removal
- `test_calculate_similarity` — Jaccard scores
- `test_title_index_find_match` — TitleIndex O(n) lookup

4. Add `pyproject.toml` with pytest config:
```toml
[tool.pytest.ini_options]
testpaths = ["src/tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "--tb=short -q"
```

5. Run with: `python -m pytest src/tests/ -v`

**Target:** >40% coverage after this task (covering services + models).

---

## TASK 9: Keyboard Navigation & Shortcuts (Interface — High Value)

**Problem:** No keyboard shortcuts for common actions. Power users managing 500+ games need fast navigation without mouse.

**Current state:**
- `window.py:144` — `_setup_shortcuts()` exists but is minimal
- `game_grid/grid.py` — has basic arrow key navigation in grid
- No shortcut for: launch, edit, delete, search focus, next/prev game

**Implementation:**

1. In `window.py`, expand `_setup_shortcuts()`:
```python
def _setup_shortcuts(self) -> None:
    shortcuts = {
        "Ctrl+F": self.search.setFocus,          # focus search bar
        "Escape": self._clear_search_and_focus,   # clear search, return to grid
        "Return": self._launch_selected_game,     # launch selected game
        "Delete": self._delete_selected_game,     # delete with confirmation
        "E": self._edit_selected_game,            # open details panel
        "Ctrl+N": self._new_collection,           # new collection
        "Ctrl+S": self._flush_save,               # force save
        "F5": self._on_scan_clicked,              # scan
        "Ctrl+U": self._on_check_updates_fetch,   # check updates
        "Ctrl+Shift+/": self._show_shortcuts_help, # show shortcuts dialog
    }
    for key, slot in shortcuts.items():
        action = QAction(self)
        action.setShortcut(key)
        action.triggered.connect(slot)
        self.addAction(action)
```

2. Add a shortcuts help dialog `src/app/ui/dialogs/shortcuts_dialog.py`:
```python
class ShortcutsDialog(QDialog):
    """Shows all keyboard shortcuts in a clean table."""
    # Simple QTableWidget with Key | Action columns
```

3. Add "Keyboard Shortcuts" entry to the Tools menu in `window.py:_build_tools_menu()`.

**Impact:** Major UX improvement for power users. Expected shortcuts (Enter=launch, Delete=remove, Ctrl+F=search, Escape=clear) make the app feel native.

---

## TASK 10: Virtual Scrolling for Game Grid (Performance — Major)

**Problem:** `game_grid/grid.py` creates a `GameCard` QWidget for every game in the filtered list. With 500+ games, this means 500+ widget instances in memory, each with icon pixmaps, overlay widgets, and event handlers. The chunked rendering (PERF-003) helps startup but all widgets still exist.

**Current implementation (`grid.py:50+`):**
- `set_games()` creates card widgets for every game
- Chunked rendering defers creation but still creates all cards
- Each card holds a QPixmap icon, hover overlay, status labels

**Implementation approach:**

There are two viable strategies. Choose based on complexity tolerance:

**Option A: QListView + Custom Delegate (Recommended)**
- Replace `QScrollArea` + `QGridLayout` with a `QListView` in `IconMode`
- Create a `GameCardDelegate(QStyledItemDelegate)` that paints cards
- Use a `QStandardItemModel` or custom `QAbstractListModel` backed by `_filtered`
- Qt handles virtualization automatically — only visible items are painted
- Card interactions (click, hover, context menu) handled via delegate events

**Option B: Manual Virtual Scroll (Simpler but more code)**
- Keep `QScrollArea` but maintain a pool of reusable `GameCard` widgets
- On scroll, recycle off-screen cards by reassigning their `Game` data
- Only create `viewport_rows + 2 buffer rows` worth of cards

**Key implementation details:**
- Preserve existing card appearance (ambient colors, hover overlay, badges)
- Preserve existing signals: `game_selected`, `game_play`, `context_action`, `rating_changed`
- Preserve multi-select behavior
- Icon loading should remain lazy (load icons as cards become visible)

**Impact:** Memory usage drops from O(n) to O(viewport_size). Handles 10,000+ game libraries smoothly.

**Note:** This is the most complex task. Consider implementing Task 1-4 first as quick wins, then tackle this.

---

## TASK 11: Inline Grid Interactions (Interface — Medium)

**Problem:** Common metadata edits (rating, status) require opening the details panel. Users performing triage on large libraries need faster editing.

**Current state:**
- `card.py:47` — `rating_changed` signal exists but only on hover overlay
- Status changes require details panel or right-click context menu
- Tag filtering via tag chips already works (`card.py:48` — `tag_clicked` signal)

**Implementation:**
1. Make rating stars always visible on cards (not just hover):
   - Move star rendering from hover overlay to card body in `card.py`
   - Stars are clickable to set rating (existing `rating_changed` signal)
   - Show current rating as filled stars, empty stars for unset positions

2. Add status badge click-to-cycle on cards:
   - Click the status badge to cycle: backlog → playing → finished → dropped → backlog
   - Emit a new signal or reuse `context_action(game_id, "set_status_next")`

3. Add right-click context menu to cards (if not already present):
   - Launch, Edit Details, Set Status →, Rate →, Add to Collection →, Delete

**Impact:** Reduces clicks per edit from 3-4 (click card → open panel → find field → edit) to 1.

---

## TASK 12: Drag-and-Drop to Collections (Interface — Medium)

**Problem:** Adding games to collections requires: select game → click "Add to Collection" button → pick collection from list. No drag-and-drop.

**Files:**
- `src/app/ui/widgets/library_sidebar.py` — collection list (drop target)
- `src/app/ui/widgets/game_grid/card.py` — game cards (drag source)
- `src/app/ui/main_window/collection_mixin.py` — `_add_selected_to_collection()` logic

**Implementation:**
1. Enable drag on `GameCard`:
```python
# card.py:
def mouseMoveEvent(self, event):
    if event.buttons() & Qt.LeftButton:
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self._game.game_id)  # or JSON for multi-select
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)
```

2. Enable drop on `LibrarySidebar` collection items:
```python
# library_sidebar.py:
def dragEnterEvent(self, event):
    if event.mimeData().hasText():
        event.acceptProposedAction()

def dropEvent(self, event):
    game_id = event.mimeData().text()
    collection_id = self._item_at_pos(event.position()).data(Qt.UserRole)
    self.game_dropped_on_collection.emit(game_id, collection_id)
```

3. Connect signal in `window.py` to existing `_add_game_to_collection()` logic.

4. Support multi-drag: when in multi-select mode, drag all selected games.

**Impact:** Intuitive collection management. Matches user expectations from file managers and media apps.

---

## TASK 13: Search/Filter Persistence as Named Views (Interface — Low)

**Problem:** Users repeatedly apply the same filter combinations (e.g., "Unplayed RPGs rated 7+"). Smart collections partially address this, but there's no way to save arbitrary filter+search combos.

**Implementation:**
1. Add a "Save Current View" button next to the search bar
2. Persist saved views in `settings.json` as:
```json
{
  "saved_views": [
    {
      "name": "Unplayed RPGs",
      "quick_filter": "all",
      "status_filter": "backlog",
      "tag_filter": "rpg",
      "sort_by": "rating",
      "search_text": ""
    }
  ]
}
```
3. Show saved views in sidebar under "Views" section
4. Clicking a saved view restores all filter/search/sort state

---

## TASK 14: Custom Exception Hierarchy (Logic — Medium)

**Problem:** 184 occurrences of `except Exception` across 52 files (documented in `docs/IMPROVEMENTS.md` §1.2). Generic catches hide bugs and prevent targeted error handling.

**Implementation:**

1. Create `src/app/exceptions.py`:
```python
class AppError(Exception):
    """Base exception for all application errors."""

class StorageError(AppError):
    """Errors related to file I/O, JSON parsing, path resolution."""

class NetworkError(AppError):
    """Errors related to HTTP requests, timeouts, DNS."""
    def __init__(self, url: str, reason: str, retriable: bool = False):
        self.url = url
        self.reason = reason
        self.retriable = retriable
        super().__init__(f"Network error for {url}: {reason}")

class ParseError(AppError):
    """Errors related to version parsing, HTML parsing, data extraction."""

class LaunchError(AppError):
    """Errors related to game launching, shortcut resolution."""

class AuthError(NetworkError):
    """Errors related to authentication (F95zone login, session expiry)."""
```

2. Replace generic catches in highest-traffic modules first:
   - `json_store.py:25` — `except Exception: pass` → `except (IOError, json.JSONDecodeError) as e:`
   - `launch_service.py:40` — `except Exception` → `except (OSError, FileNotFoundError) as e:`
   - `f95_parser.py:34, 49` — `except Exception` → `except (ParseError, lxml.etree.Error) as e:`
   - `storage/paths.py:34` — `except Exception` → `except OSError as e:`

3. Log with context: `_log.warning("launch_failed %s", kv(game=title, error=str(e)))` instead of silent pass.

**Impact:** Bugs surface faster. Retriable errors can be retried. Non-retriable errors give useful messages.

---

## TASK 15: Split Oversized Files (Code Quality)

**Files exceeding 500-line limit:**

| File | Lines | Split Strategy |
|------|-------|----------------|
| `f95_api.py` | 703 | Extract `f95_url_utils.py` (URL normalization/validation, ~150 lines) and `f95_link_extractor.py` (download link parsing, ~200 lines) |
| `f95_auth.py` | 678 | Extract `f95_session.py` (session management, cookie handling, ~200 lines) and `f95_credentials.py` (encryption, storage, ~150 lines) |
| `smart_download.py` | 626 | Extract `host_limit_tracker.py` (~100 lines) and `link_validator.py` (~100 lines) |
| `card.py` | 589 | Extract `card_overlay.py` (hover overlay construction, ~150 lines) |
| `grid.py` | 570 | Acceptable if virtual scrolling (Task 10) replaces it |
| `window.py` | 712 | Extract `_build_ui` into `ui_builder.py` (~250 lines), keeping window.py as orchestrator |

**Approach:** Extract into same package/directory. Update `__init__.py` re-exports for backward compatibility. Run existing tests after each split to verify no regressions.

---

## TASK 16: CI Pipeline (Infrastructure)

**Problem:** No automated testing. Changes can break existing functionality without detection.

**Implementation:**

1. Create `.github/workflows/ci.yml`:
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt pytest pytest-cov
      - run: python -m pytest src/tests/ -v --tb=short --cov=src/app --cov-report=term-missing
```

2. Note: PySide6 and pywin32 imports will need mocks on Linux CI. The existing `conftest.py` already mocks win32-specific modules — verify it covers all imports.

3. Add a lint step (optional but recommended):
```yaml
      - run: pip install ruff
      - run: ruff check src/ --select E,W,F --ignore E501
```

---

## Implementation Order (Recommended)

| Phase | Tasks | Effort | Impact |
|-------|-------|--------|--------|
| **Phase 1: Quick Wins** | Tasks 1, 2, 3, 4 | 1-2 hours each | Immediate perf + safety |
| **Phase 2: Architecture** | Tasks 5, 6, 7 | 2-4 hours each | Unlocks testability |
| **Phase 3: Testing** | Task 8, 16 | 3-5 hours | Safety net for all future work |
| **Phase 4: Interface** | Tasks 9, 11, 12 | 2-3 hours each | UX improvements |
| **Phase 5: Cleanup** | Tasks 14, 15 | 2-3 hours each | Code quality |
| **Phase 6: Major** | Task 10, 13 | 4-8 hours each | Scaling + polish |

---

## Constraints & Guardrails

1. **No circular imports** — the codebase currently has zero. Keep it that way.
2. **No wildcard imports** — all imports are explicit. Continue this pattern.
3. **File size limit** — target <500 lines per file, hard limit 700.
4. **Backward compatibility** — new fields on `Game` model must have defaults. JSON storage must load old formats.
5. **Thread safety** — any shared state accessed from worker threads must use `QMutex` or `threading.Lock`.
6. **Windows-primary** — the app targets Windows. Use `os.startfile()`, `pywin32`, `%APPDATA%` paths. Linux mocks exist only for CI.
7. **Logging** — use `get_logger(__name__)` and structured `kv()` logging. No `print()`.
8. **Test after each task** — run `python -m pytest src/tests/ -v` after completing each task. Do not proceed to the next task if tests fail.

---

## Key File Reference

| Purpose | File Path |
|---------|-----------|
| Entry point | `src/main.py` |
| Game model | `src/app/models/game.py` |
| Collection model | `src/app/models/collection.py` |
| Main window | `src/app/ui/main_window/window.py` |
| Grid widget | `src/app/ui/widgets/game_grid/grid.py` |
| Card widget | `src/app/ui/widgets/game_grid/card.py` |
| Filter logic | `src/app/services/filter_utils.py` |
| JSON storage | `src/app/storage/json_store.py` |
| Icon caching | `src/app/services/icon_service.py` |
| Color extraction | `src/app/services/color_extractor.py` |
| Version parsing | `src/app/services/version_parser.py` |
| Title matching | `src/app/services/title_matcher.py` |
| HTTP utilities | `src/app/services/http_utils.py` |
| Theme system | `src/app/ui/theme.py` |
| Logging | `src/logging_utils.py` |
| Settings storage | `src/app/storage/paths.py` |
| Project context | README and docs |
| Quality plan | `docs/CODE_QUALITY_PLAN.md` |
| Issue catalog | `docs/IMPROVEMENTS.md` |

---

*This document should be read before improving this codebase. Execute tasks in order, commit focused changes, and run tests to verify behavior.*
