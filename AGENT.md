# Agent Context Guide

> Quick reference for Claude Code sessions working on this codebase.
> Read this first to understand architecture and save context window.

## Project Overview

**Game Library Manager v4** - A PySide6 desktop application for managing game libraries with:
- Game shortcut management and launching
- F95zone integration for update checking
- Archive extraction and bulk import
- Download management with queue support

**Tech Stack:** Python 3.10+, PySide6 (Qt), JSON storage

**Codebase Size:** ~40K lines across 90+ Python files

---

## Directory Structure

```
src/app/
├── config/          # ARCH-003: Centralized configuration (NEW)
│   └── app_config.py    # Type-safe config with NetworkConfig, UIConfig, etc.
│
├── events/          # ARCH-002: Event bus for decoupled communication (NEW)
│   └── event_bus.py     # Pub/sub with 30+ events, priorities, weak refs
│
├── repositories/    # ARCH-001: Repository pattern for data access (NEW)
│   ├── game_repository.py      # GameRepository with JSON storage
│   └── collection_repository.py # CollectionRepository
│
├── models/          # Data models (dataclasses)
│   ├── game.py          # Game model (~50 fields)
│   └── collection.py    # Collection model (manual/smart)
│
├── services/        # Business logic layer
│   ├── archive/         # MOD-003: Modular archive extraction (NEW)
│   │   ├── extractor.py     # Main orchestrator
│   │   ├── utils.py         # Passwords, multipart, parsing
│   │   └── formats/         # Pluggable handlers (ZIP, RAR, 7z)
│   ├── cache_utils.py   # PERF-004: BoundedCache LRU implementation (NEW)
│   ├── http_utils.py    # Centralized HTTP operations
│   ├── title_matcher.py # Fuzzy matching with TitleIndex
│   ├── filter_utils.py  # Filtering, sorting, SearchCache
│   ├── download_manager.py  # Queue-based download manager
│   ├── update_checker.py    # Version checking with bounded caches
│   └── host_handlers/   # Download handlers (mega, gofile, etc.)
│
├── storage/         # Persistence layer
│   ├── json_store.py    # Library load/save
│   └── paths.py         # App directories
│
└── ui/              # PySide6 UI layer
    ├── main_window.py   # Main window (2400+ lines - needs split)
    └── widgets/
        ├── game_grid/   # MOD-002: Modular game grid (NEW)
        │   ├── card.py      # GameCard widget
        │   ├── grid.py      # GameGrid container
        │   └── skeleton.py  # Loading skeleton
        └── ...
```

---

## Key Patterns & Conventions

### 1. Global Singletons with Lazy Loading
```python
_instance: Optional[ClassName] = None

def get_instance() -> ClassName:
    global _instance
    if _instance is None:
        _instance = ClassName()
    return _instance
```
Used by: `get_config()`, `get_event_bus()`, `get_game_repository()`, `get_download_manager()`

### 2. Service Module Exports
All services export through `services/__init__.py`. Import from there:
```python
from app.services import extract_archive, BoundedCache, get_game_repository
```

### 3. Logging Pattern
```python
from app.logging_utils import get_logger, kv, RateLimiter

_log = get_logger("module_name")
_rate = RateLimiter()

_log.info("action_name %s", kv(key1=val1, key2=val2))
if _rate.allow("frequent_log", 1000):  # Max once per second
    _log.debug("...")
```

### 4. Qt Signals for Thread Communication
```python
class Worker(QThread):
    progress = Signal(int, str)
    finished = Signal(object)
    error = Signal(str)
```

---

## Recent Architecture Improvements (v1.7-1.9)

### Event Bus (`app.events`)
```python
from app.events import Event, emit, subscribe

# Subscribe
subscribe(Event.GAME_ADDED, lambda game: print(f"Added: {game.title}"))

# Emit
emit(Event.GAME_ADDED, game)
```

### Repository Pattern (`app.repositories`)
```python
from app.repositories import get_game_repository

repo = get_game_repository()
games = repo.get_all()
game = repo.get_by_id("id")
repo.save(game)
repo.find_by_status("playing")
```

### Configuration (`app.config`)
```python
from app.config import get_config

config = get_config()
timeout = config.network.timeout
config.ui.theme = "dark"
config.save()
```

### Bounded Cache (`app.services.cache_utils`)
```python
from app.services import BoundedCache

cache: BoundedCache[str, str] = BoundedCache(max_size=100, ttl_seconds=3600)
cache.set("key", "value")
value = cache.get("key")  # None if expired/missing
```

### Archive Extraction (`app.services.archive`)
```python
from app.services import extract_archive, scan_for_archives

result = extract_archive(Path("game.zip"), Path("/dest"))
archives = scan_for_archives(Path("/downloads"))
```

---

## Key Entry Points

| Task | Location | Function/Class |
|------|----------|----------------|
| App startup | `src/main.py` | `main()` |
| Main window | `ui/main_window.py` | `MainWindow` |
| Load library | `storage/json_store.py` | `load_library_bundle()` |
| Save library | `storage/json_store.py` | `save_library_bundle()` |
| Game model | `models/game.py` | `Game` dataclass |
| Check updates | `services/update_checker.py` | `check_updates_background()` |
| Extract archive | `services/archive/extractor.py` | `extract_archive()` |
| Download file | `services/download_manager.py` | `DownloadManager` |

---

## Code Quality Plan Status

See `docs/CODE_QUALITY_PLAN.md` for full details. Current version: **1.9**

### Completed
- [x] Sprint 1: Critical bug fixes (P0, P1 issues)
- [x] Sprint 2: Code deduplication (http_utils, title_matcher)
- [x] Sprint 3: Modularization Part 1 (game_grid package)
- [x] Sprint 4: Modularization Part 2 (archive package)
- [x] Sprint 5: Performance (BoundedCache, SearchCache)
- [x] Sprint 6: Architecture (Repository, EventBus, Config)

### Remaining
- [ ] MOD-001: Split main_window.py (2400 lines → 5-6 modules)
- [ ] PERF-003: Virtual scrolling for game grid
- [ ] Test coverage (currently ~0%, target >40%)

---

## Common Tasks Quick Reference

### Adding a new service
1. Create file in `services/`
2. Export in `services/__init__.py`
3. Use logging pattern with `get_logger()`

### Adding a new event
1. Add to `Event` enum in `events/event_bus.py`
2. Emit with `emit(Event.YOUR_EVENT, data)`
3. Subscribe with `subscribe(Event.YOUR_EVENT, handler)`

### Adding configuration
1. Add field to appropriate config section in `config/app_config.py`
2. Add validation in `__post_init__` if needed
3. Access via `get_config().section.field`

### Working with games
```python
# Via repository (preferred for new code)
from app.repositories import get_game_repository
repo = get_game_repository()
games = repo.find_by_status("playing")

# Via direct storage (legacy)
from app.storage import load_library_bundle, save_library_bundle
games, collections = load_library_bundle(path)
```

---

## Files to Read First

1. **This file** - Architecture overview
2. **docs/CODE_QUALITY_PLAN.md** - Detailed improvement plan and changelog
3. **models/game.py** - Understand the Game model
4. **services/__init__.py** - See all available service exports

---

## Tips for Efficient Context Usage

1. **Use `services/__init__.py`** to see all exports without reading individual files
2. **Check `CODE_QUALITY_PLAN.md` changelog** for recent changes
3. **New packages** (config/, events/, repositories/, archive/) follow consistent patterns
4. **Search for `get_*()` functions** to find global accessors
5. **UI code** is in `ui/`, business logic in `services/`, data in `models/`

---

*Last updated: 2026-02-03*
