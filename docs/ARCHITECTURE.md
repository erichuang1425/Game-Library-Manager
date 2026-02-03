# Architecture Reference

> Detailed architecture documentation for Game Library Manager v4.
> For quick start, see `/AGENT.md` first.

## Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        UI Layer                              │
│  main_window.py, widgets/, dialogs/                         │
│  PySide6 widgets, signals, user interaction                 │
├─────────────────────────────────────────────────────────────┤
│                     Service Layer                            │
│  services/                                                   │
│  Business logic, HTTP, downloads, archive extraction        │
├─────────────────────────────────────────────────────────────┤
│                   Repository Layer                           │
│  repositories/                                               │
│  Data access abstraction, caching, queries                  │
├─────────────────────────────────────────────────────────────┤
│                    Storage Layer                             │
│  storage/                                                    │
│  JSON persistence, file paths                               │
├─────────────────────────────────────────────────────────────┤
│                    Model Layer                               │
│  models/                                                     │
│  Game, Collection dataclasses                               │
└─────────────────────────────────────────────────────────────┘

Cross-cutting concerns:
- config/      → Configuration for all layers
- events/      → Communication between layers
- logging_utils.py → Structured logging
```

---

## Package Details

### `app.config` - Configuration Management

**Purpose:** Centralized, type-safe configuration

**Key Classes:**
- `AppConfig` - Root configuration container
- `NetworkConfig` - HTTP settings (timeout, retries, user-agent)
- `CacheConfig` - Cache sizes and TTLs
- `UIConfig` - Theme, fonts, layout preferences
- `DownloadConfig` - Download settings

**Usage:**
```python
from app.config import get_config

config = get_config()

# Read
timeout = config.network.timeout
theme = config.ui.theme

# Write (validates automatically)
config.network.timeout = 60
config.save()  # Persists to ~/.game-manager/config.json
```

**File:** `config/app_config.py` (~350 lines)

---

### `app.events` - Event Bus

**Purpose:** Decouple components via publish/subscribe

**Key Classes:**
- `Event` - Enum of all events
- `EventBus` - Singleton pub/sub manager
- `EventPriority` - Handler priority levels

**Event Categories:**
| Category | Events |
|----------|--------|
| Game | GAME_ADDED, GAME_UPDATED, GAME_DELETED, GAME_LAUNCHED |
| Library | LIBRARY_LOADED, LIBRARY_SAVED, LIBRARY_SCAN_* |
| Collection | COLLECTION_CREATED, COLLECTION_UPDATED, COLLECTION_DELETED |
| Download | DOWNLOAD_QUEUED, DOWNLOAD_STARTED, DOWNLOAD_COMPLETED, etc. |
| Archive | ARCHIVE_EXTRACT_STARTED, ARCHIVE_EXTRACT_COMPLETED, etc. |
| Updates | UPDATES_CHECK_STARTED, UPDATES_AVAILABLE |
| UI | THEME_CHANGED, VIEW_MODE_CHANGED, FILTER_CHANGED |
| App | APP_STARTUP, APP_SHUTDOWN, APP_ERROR |

**Usage:**
```python
from app.events import Event, emit, subscribe, EventPriority

# Subscribe with priority
unsubscribe_fn = subscribe(
    Event.GAME_ADDED,
    on_game_added,
    priority=EventPriority.HIGH
)

# One-time subscription
subscribe(Event.LIBRARY_LOADED, handler, once=True)

# Emit event
emit(Event.GAME_ADDED, game)

# Unsubscribe
unsubscribe_fn()  # or unsubscribe(Event.GAME_ADDED, on_game_added)
```

**File:** `events/event_bus.py` (~360 lines)

---

### `app.repositories` - Data Access

**Purpose:** Abstract data storage from business logic

**Key Classes:**
- `Repository[T, ID]` - Generic repository interface
- `GameRepository` - Game-specific queries
- `JsonGameRepository` - JSON file implementation
- `CollectionRepository` - Collection-specific queries
- `JsonCollectionRepository` - JSON file implementation

**GameRepository Methods:**
```python
# CRUD
get_all() -> List[Game]
get_by_id(id) -> Optional[Game]
save(game) -> None
delete(id) -> bool

# Queries
find_by_title(title, exact=False) -> List[Game]
find_by_status(status) -> List[Game]
find_by_tag(tag) -> List[Game]
find_by_shortcut_path(path) -> Optional[Game]
find_with_updates() -> List[Game]
find_missing_files() -> List[Game]

# Bulk operations
bulk_save(games) -> None
bulk_delete(game_ids) -> int
```

**Files:** `repositories/base.py`, `game_repository.py`, `collection_repository.py`

---

### `app.services.archive` - Archive Extraction

**Purpose:** Modular archive handling with pluggable format support

**Structure:**
```
archive/
├── __init__.py      # Package exports
├── extractor.py     # ArchiveExtractor orchestrator
├── utils.py         # Passwords, multipart, parsing
└── formats/
    ├── base.py      # FormatHandler ABC
    ├── zip_handler.py
    ├── rar_handler.py
    └── sevenz_handler.py
```

**Key Classes:**
- `ArchiveExtractor` - Main extraction service
- `FormatHandler` - Abstract handler interface
- `ZipHandler`, `RarHandler`, `SevenZipHandler` - Implementations
- `ExtractionResult` - Result dataclass
- `ScannedArchive` - Archive info dataclass

**Usage:**
```python
from app.services import (
    extract_archive,
    scan_for_archives,
    get_archive_info,
    try_passwords,
)

# Extract
result = extract_archive(
    path=Path("game.zip"),
    destination=Path("/games/MyGame"),
    try_common_passwords=True,
)
if result.success:
    print(f"Extracted {result.file_count} files")

# Scan folder
archives = scan_for_archives(Path("/downloads"), recursive=True)

# Get info without extracting
info = get_archive_info(Path("game.rar"))
print(f"Encrypted: {info.is_encrypted}")
```

---

### `app.services.cache_utils` - Bounded Caching

**Purpose:** LRU caches with size limits and TTL

**Key Classes:**
- `BoundedCache[K, V]` - Thread-safe LRU cache
- `TimestampedCache[K, V]` - Cache with timestamp access

**Features:**
- Maximum size with LRU eviction
- Optional TTL (time-to-live)
- Thread-safe with RLock
- Hit/miss statistics

**Usage:**
```python
from app.services import BoundedCache

# Create cache
cache: BoundedCache[str, dict] = BoundedCache(
    max_size=100,
    ttl_seconds=3600,  # 1 hour
    name="my_cache",
)

# Use
cache.set("key", {"data": "value"})
result = cache.get("key")  # Returns None if missing/expired

# Stats
print(cache.stats)  # {"hits": 10, "misses": 2, "hit_rate": 0.833, ...}
```

**Used by:** `update_checker.py` for HTML and parsed version caching

---

## Data Flow Examples

### Game Update Check
```
MainWindow._on_check_updates_fetch()
    └── UpdateWorker.run()
        └── check_updates_background(games)
            └── fetch_source_version(url)
                ├── _html_cache.get(url)  # BoundedCache
                ├── _fetch(url)           # HTTP request
                ├── _html_cache.set(url, html)
                └── parse with f95_parser or generic
```

### Archive Import
```
BulkArchiveImportDialog
    └── BulkArchiveImporter.scan_folder()
        └── scan_for_archives(folder)
            └── ArchiveExtractor.scan_folder()
    └── BulkArchiveImporter.import_archive()
        └── extract_archive(path, dest)
            └── ZipHandler/RarHandler.extract()
```

### Event Flow (New Architecture)
```
# When game is added via UI
MainWindow._add_game(game)
    ├── repo.save(game)         # Repository
    ├── emit(Event.GAME_ADDED)  # Event bus
    │   └── Sidebar.on_game_added()  # Subscriber
    │   └── Grid.on_game_added()     # Subscriber
    └── _apply_search()         # UI refresh
```

---

## Threading Model

**Main Thread (Qt Event Loop):**
- All UI operations
- Signal/slot handlers
- Event bus emissions

**Worker Threads (QThread):**
- HTTP requests
- File I/O (large files)
- Archive extraction
- Update checking

**Thread Communication:**
- Qt Signals (preferred)
- QMutex for shared state
- Event bus (main thread only for handlers)

**Pattern:**
```python
class Worker(QThread):
    progress = Signal(int, str)
    finished = Signal(object)

    def run(self):
        # Heavy work here (worker thread)
        result = do_work()
        self.finished.emit(result)  # Signal to main thread

# In main thread
worker = Worker()
worker.finished.connect(self.on_finished)  # Handler runs in main thread
worker.start()
```

---

## File Size Guidelines

| Size | Status | Action |
|------|--------|--------|
| <300 lines | Ideal | - |
| 300-500 lines | Acceptable | Consider splitting |
| 500-700 lines | Warning | Plan to split |
| >700 lines | Critical | Must split |

**Current large files:**
- `main_window.py` - 2,400 lines (needs MOD-001)
- `f95_api.py` - 700 lines
- `download_manager.py` - 690 lines (well-structured)

---

## Testing Strategy

**Current:** ~0% coverage (only 84 lines of tests)

**Priority modules for testing:**
1. `services/` - Business logic (target: 70%)
2. `storage/` - Persistence (target: 80%)
3. `models/` - Data validation (target: 90%)
4. `repositories/` - Data access (target: 70%)

**Test patterns:**
```python
# Unit test with mock
def test_game_repository_save(tmp_path):
    repo = JsonGameRepository(storage_path=tmp_path / "lib.json")
    game = Game(game_id="1", title="Test")
    repo.save(game)
    assert repo.get_by_id("1") == game

# Integration test
def test_archive_extraction(tmp_path):
    result = extract_archive(test_zip, tmp_path)
    assert result.success
    assert result.file_count > 0
```

---

*Last updated: 2026-02-03*
