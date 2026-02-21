# Contributing Guidelines & Code Standards

Quick reference for maintaining code quality in the Game Library Manager project.

---

## Quick Reference Checklist

### Before Committing

- [ ] File is under 300 lines (hard limit: 500)
- [ ] No duplicate code - check if utility exists
- [ ] All network calls are in worker threads
- [ ] Error handling is specific and contextual
- [ ] No manual lock/unlock inside context managers
- [ ] Tests added/updated for changed code

### File Size Limits

| Category | Soft Limit | Hard Limit |
|----------|------------|------------|
| Regular modules | 300 lines | 500 lines |
| Test files | 400 lines | 600 lines |
| UI widgets | 400 lines | 600 lines |

---

## Shared Utilities (Use These!)

### HTTP Operations

```python
# Instead of duplicating urllib code:
from app.services.http_utils import (
    create_request,      # Adds User-Agent automatically
    download_with_progress,
    handle_http_error,
    USER_AGENT,          # Standard User-Agent string
    CHUNK_SIZE,          # 8192 bytes
)
```

### Title Matching

```python
# Instead of writing your own similarity functions:
from app.services.title_matcher import (
    normalize_title,
    tokenize,
    calculate_similarity,
)
```

### Background Workers

```python
# Instead of creating a new QThread subclass:
from app.ui.workers import BaseWorker

class MyWorker(BaseWorker):
    def do_work(self):
        # Your logic here
        return result
```

---

## Code Patterns

### Error Handling

```python
# GOOD: Specific, contextual exceptions
class DownloadError(Exception):
    def __init__(self, url: str, reason: str, retriable: bool = False):
        self.url = url
        self.reason = reason
        self.retriable = retriable
        super().__init__(f"Download failed: {reason}")

# BAD: Generic exceptions
raise Exception("Something went wrong")
```

### Threading

```python
# GOOD: Context manager for locks
with QMutexLocker(self._mutex):
    self._data = new_value

# BAD: Manual lock/unlock
self._mutex.lock()
try:
    self._data = new_value
finally:
    self._mutex.unlock()

# VERY BAD: Manual unlock inside context manager
with QMutexLocker(self._mutex):
    self._mutex.unlock()  # NEVER DO THIS
```

### Network Calls

```python
# GOOD: Worker thread for network I/O
class FetchWorker(BaseWorker):
    def do_work(self):
        return fetch_data(self.url)

# BAD: Blocking call in main thread
def on_button_click(self):
    data = urllib.request.urlopen(url).read()  # Freezes UI!
```

### Null Safety

```python
# GOOD: Safe dictionary access
value = stats.get("count", 0)

# BAD: Direct access without check
value = stats["count"]  # KeyError if missing

# GOOD: Check before index
if items and len(items) > 0:
    first = items[0]

# BAD: Assume list is populated
first = items[0]  # IndexError if empty
```

---

## Project Structure

```
src/app/
├── models/          # Data classes (Game, Collection)
├── storage/         # Persistence (JSON, paths)
├── services/        # Business logic
│   ├── http_utils.py       # Shared HTTP utilities
│   ├── title_matcher.py    # Fuzzy matching utilities
│   ├── host_handlers/      # Download host implementations
│   └── ...
├── ui/
│   ├── main_window/        # Main window modules
│   ├── widgets/            # Reusable UI components
│   │   └── game_grid/      # Grid-related widgets
│   ├── dialogs/            # Modal dialogs
│   └── workers/            # Background workers
│       └── base_worker.py  # Base class for workers
└── repositories/    # Data access layer (planned)
```

---

## When to Split a File

Split when:
- File exceeds 300 lines
- File has multiple unrelated classes
- You find yourself adding a "section comment" to separate code
- Testing requires mocking many unrelated things

How to split:
1. Identify cohesive groups of functions/classes
2. Create a new module for each group
3. Update imports to use the new modules
4. Use `__init__.py` to maintain backward compatibility

---

## Naming Conventions

| Type | Style | Example |
|------|-------|---------|
| Class | PascalCase | `GameCard` |
| Function | snake_case | `calculate_similarity` |
| Constant | UPPER_SNAKE | `MAX_RETRIES` |
| Private | _leading | `_internal_helper` |
| Module | snake_case | `download_manager.py` |

---

## Documentation

### Required for:
- All public functions/methods
- Complex algorithms
- Non-obvious business logic
- Configuration options

### Format:
```python
def process_game(game: Game, options: ProcessOptions) -> Result:
    """
    Process a game with the given options.

    Args:
        game: The game to process
        options: Processing configuration

    Returns:
        Result object with status and any errors

    Raises:
        ProcessingError: If game data is invalid
    """
```

---

## Testing Requirements

### Coverage Targets
- Services: 70%
- Storage: 80%
- Models: 90%
- UI: 40%

### Test Naming
```python
def test_<method>_<scenario>_<expected>():
    """Description of what's being tested."""
```

### Example
```python
def test_download_with_404_raises_download_error():
    """Attempting to download a non-existent file should raise DownloadError."""
```

---

## Performance Guidelines

1. **No N+1 patterns**: Use indexing for repeated lookups
2. **Cache expensive computations**: Especially string operations
3. **Use generators**: For large sequences you only iterate once
4. **Worker threads**: For all network and disk I/O
5. **Virtual scrolling**: For lists with 100+ items

---

## Common Anti-Patterns to Avoid

| Anti-Pattern | Instead Do |
|--------------|------------|
| God class (1000+ lines) | Split into focused modules |
| Copy-paste code | Extract to shared utility |
| `time.sleep()` in UI thread | Use QTimer or worker thread |
| Catching generic `Exception` | Catch specific exceptions |
| Manual lock/unlock | Use `with QMutexLocker()` |
| Direct dict/list access | Use `.get()` or check first |
| Blocking I/O in main thread | Use worker threads |
| Magic numbers | Define named constants |

---

*See CODE_QUALITY_PLAN.md for full details and implementation roadmap.*
