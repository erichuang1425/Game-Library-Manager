# Identified Improvements

> **Project:** Game Library Manager v4
> **Created:** 2026-02-12
> **Scope:** Code quality, security, performance, testing, infrastructure, UI/UX

---

## Table of Contents

1. [Code Quality](#1-code-quality)
2. [Security](#2-security)
3. [Performance](#3-performance)
4. [Testing & CI](#4-testing--ci)
5. [Infrastructure & Build](#5-infrastructure--build)
6. [UI/UX Improvements](#6-uiux-improvements)

---

## 1. Code Quality

### 1.1 Oversized Files

Files exceeding the 500-line guideline:

| File | Lines | Over by |
|------|-------|---------|
| `services/f95_api.py` | 703 | +203 |
| `ui/main_window/window.py` | 704 | +204 |
| `services/f95_auth.py` | 678 | +178 |
| `services/smart_download.py` | 626 | +126 |
| `ui/dialogs/bulk_archive_import_dialog.py` | 626 | +126 |
| `ui/dialogs/theme_editor.py` | 537 | +37 |
| `ui/widgets/game_grid/card.py` | ~589 | +89 |
| `ui/widgets/game_grid/grid.py` | ~570 | +70 |

**Action:** Extract download-link parsing from `f95_api.py`, session management from `f95_auth.py`, and `HostLimitTracker`/`LinkValidator` from `smart_download.py`.

### 1.2 Generic Exception Handling

184 occurrences of `except Exception` across 52 files. Most problematic:

- `logging_utils.py:50, 56, 140, 235, 267` — 5 generic catches in the logger itself
- `launch_service.py:40` — silently warns on launch failure
- `storage/paths.py:34` — bare except
- `f95_parser.py:34, 49` — swallows parse errors
- `storage/json_store.py:25` — silent `pass` on save failure

**Action:** Replace with specific exception types (`IOError`, `ValueError`, `urllib.error.HTTPError`, etc.) and add meaningful context to log messages.

### 1.3 Global Singletons Without Thread Safety

11+ module-level singletons that risk race conditions and hinder testing:

| Global | File |
|--------|------|
| `_enhanced_service` | `enhanced_download_service.py:414` |
| `_auth_manager` | `f95_auth.py:675` |
| `_selector` | `smart_download.py:605` |
| `_redirect_handler` | `smart_download.py:613` |
| `_search_cache` | `filter_utils.py:156` |
| `_global_undo_stack` | `undo_redo.py:304` |
| `_custom_passwords` | `archive/passwords.py:26, 72` |
| `_reduced_motion` | `theme.py:397` |
| `_download_manager` | `download/manager.py:349` |
| `_dialog_shown` | `exception_hook.py:69, 85, 98` |
| `_CONFIGURED`, `_LOG_MESSAGE_SHOWN` | `logging_utils.py:96, 253` |

**Action:** Refactor to dependency-injection-friendly patterns; add synchronization where multi-thread access is possible.

### 1.4 Game Model Bloat

`models/game.py` has a single `Game` dataclass with **67 fields** — violates single responsibility.

**Action:** Split into nested dataclasses:
```
Game
├── GameCore       (id, title, status, rating, tags)
├── GameSource     (source_url, source_checked_at, ...)
├── GameArchive    (archive_path, archive_format, ...)
├── GameLaunch     (last_played, play_count, ...)
└── GameDownload   (download_url, download_status, ...)
```

### 1.5 Inconsistent Logging

- Some modules use `_log = get_logger("module")` at module level, others create loggers in functions
- Inconsistent use of `kv()` structured logging helper
- Some files still use `print()` instead of logging

**Action:** Standardize all modules to `_log = get_logger(__name__)` at module level; replace `print()` with `_log.info()`.

### 1.6 Magic Numbers & Hardcoded Values

- `http_utils.py:40` — `max_size: int = 100` cache bound
- `f95_auth.py:43` — `SESSION_MAX_AGE = 60 * 60 * 24 * 7`
- `f95_auth.py:38` — `REQUEST_TIMEOUT = 30`
- `main_window/window.py:62` — `self.resize(1200, 750)`

**Action:** Extract to named constants or centralized `AppConfig` dataclass.

---

## 2. Security

### 2.1 Credential Storage

`f95_auth.py` stores encrypted credentials using `_derive_key()` from machine-specific data. Concerns:
- May confuse `base64` encoding with actual encryption
- Machine-specific key derivation robustness unknown
- No evidence of secure memory wiping after use

**Action:** Audit `_derive_key()` implementation; consider using `cryptography.fernet` with OS keyring.

### 2.2 HTTP Security

`http_utils.py:100-120`:
- No explicit SSL certificate verification enforcement
- No certificate pinning
- Not all call sites enforce timeouts (default 30s but not universal)

**Action:** Add `ssl.create_default_context()` to all urllib calls; enforce timeout at the utility level.

### 2.3 Unvalidated File Paths

Multiple places accept file paths without sanitization:
- Archive extraction targets
- Game folder paths
- Icon cache paths

**Action:** Add path-traversal checks (`os.path.realpath()` validation) at system boundaries.

---

## 3. Performance

### 3.1 Virtual Scrolling Not Implemented

`game_grid/grid.py` renders all cards, even off-screen ones. Libraries with 100+ games will create unnecessary widgets.

**Action:** Implement virtual scrolling — only render visible cards plus a buffer row.

### 3.2 Icon Rendering on Resize

`game_grid/card.py` reschedules icon refresh on resize events. Rapid resizing causes repeated re-renders with no throttle.

**Action:** Add debounce/throttle to icon re-render on resize.

### 3.3 Linear Game Lookups

`library_service.py` iterates the entire game list for ID lookups. Collection filtering also iterates games multiple times.

**Action:** Add `Dict[str, Game]` index for O(1) lookups.

---

## 4. Testing & CI

### 4.1 Near-Zero Test Coverage

Only 3 test files exist covering a fraction of ~25,000 lines:
- `test_json_store_dt.py` — 23 lines (datetime parsing)
- `test_version_parser.py` — manual script format
- `guardrails_check.py` — manual guards check

**Action:** Set up pytest, add unit tests for services and models. Target >60% coverage.

### 4.2 No CI/CD Pipeline

No GitHub Actions, no automated tests on push, no release automation.

**Action:** Add `.github/workflows/ci.yml` with lint + test + build verification.

### 4.3 No Linting Configuration

Missing: `.flake8`, `mypy.ini`, `pyproject.toml`, `.pre-commit-config.yaml`

**Action:** Add `pyproject.toml` with `[tool.mypy]`, `[tool.ruff]` sections; set up pre-commit hooks.

---

## 5. Infrastructure & Build

### 5.1 Loose Dependency Pinning

`requirements.txt` uses open-ended constraints:
```
PySide6>=6.5      # could break on 7.0
pywin32>=306      # could break on major bump
lxml>=4.9         # could break on 5.0
```

**Action:** Add upper bounds: `PySide6>=6.5,<7.0`, etc. Separate dev/test dependencies.

### 5.2 No Package Metadata

No `pyproject.toml` or `setup.py`. No version management, author, or license metadata.

**Action:** Create `pyproject.toml` with build metadata and tool configuration.

---

## 6. UI/UX Improvements

### 6.1 Accessibility

#### 6.1.1 Missing Tooltips
Only 46 tooltip occurrences across 12 files. Many interactive elements lack guidance.
- `grid.py:322` — "Load grid" overlay has no user explanation
- Sidebar toggle button (`library_sidebar.py:65`) — icon-only, no accessible label
- Batch toolbar buttons (`batch_toolbar.py:80-101`) — action buttons without descriptive tooltips

**Action:** Add tooltips to all interactive controls. Use `setAccessibleName()` on icon-only buttons.

#### 6.1.2 No Tab Order Management
No `setTabOrder()` calls in main window. Focus may not follow logical flow when using keyboard.

**Action:** Define explicit tab order: search bar → filter chips → grid → details panel → sidebar.

#### 6.1.3 Color-Only Status Indicators
Card status (`card.py:173-181`) uses color alone to convey state. Users with color blindness cannot differentiate.

**Action:** Add text labels or icons alongside color indicators.

#### 6.1.4 Reduced Motion Not Consistently Honored
`theme.py:395-403` provides `is_reduced_motion()` but it's only checked in `card.py:570` and `filter_chips.py:45-54`. Dialogs and other animations ignore it.

**Action:** Check `is_reduced_motion()` in all animation code paths.

#### 6.1.5 Focus Indicators Inconsistent
Grid cards (`grid.py:475-511`) show a 2px focus border, but sidebar items and toolbar buttons have no visible focus ring.

**Action:** Add uniform focus styling via theme for all focusable widgets.

---

### 6.2 Responsiveness & Layout

#### 6.2.1 Hardcoded Card Dimensions
`grid.py:210-212` uses fixed widths: 260px (comfortable) and 200px (compact). No smooth scale-down below 240px — grid breaks on small windows.

**Action:** Use proportional sizing with min/max constraints. Allow fractional column widths.

#### 6.2.2 Abrupt Breakpoint Transitions
`ui_mixin.py:235-258` has discrete breakpoints at 900px and 1200px. At exactly 900px, the sidebar collapses instantly, losing user context.

**Action:** Add smooth transitions or progressive disclosure at breakpoints.

#### 6.2.3 Fixed Sidebar Width
`library_sidebar.py:40-46` — min 220px, max 320px. The "Library" title can be cut off at 220px.

**Action:** Allow sidebar to collapse to icon-only mode. Truncate labels with ellipsis.

#### 6.2.4 Details Panel Squeeze
`window.py:587-588` — details panel min 340px, max 520px. On a 1200px window with sidebar open, the grid gets squeezed below usable width.

**Action:** Implement priority-based layout where grid always gets minimum viable width before panel shrinks.

#### 6.2.5 Fixed Header Height
`window.py:215` — `setFixedHeight(theme.toolbar_height)` at 48px with no scaling.

**Action:** Scale toolbar height with system DPI/font size settings.

---

### 6.3 Error Feedback

#### 6.3.1 Render Errors Rate-Limited to One Per Session
`grid.py:178-184` catches render exceptions and shows `QMessageBox.warning()` but only once. All subsequent render failures are silently dropped.

**Action:** Accumulate errors and show summary, or add a persistent error indicator.

#### 6.3.2 Silent Card Build Failures
`grid.py:227-231` logs card build failures with `continue` — user sees an incomplete grid without knowing games were skipped.

**Action:** Show a "X games failed to load" banner with option to view details.

#### 6.3.3 Silent Icon Loading Failures
`card.py:499-504` shows gray placeholder on icon failure with no user feedback.

**Action:** Show a broken-image icon or "No icon" label. Offer "Retry" on hover.

#### 6.3.4 Toast Auto-Dismiss Too Fast for Errors
`toast.py:275` — error toasts auto-dismiss after 6 seconds. Complex error messages may not be read in time.

**Action:** Make error toasts persistent until manually dismissed. Or add "View details" link.

#### 6.3.5 No Retry Mechanism
When scan, import, or update operations fail, no "Retry" button is offered.

**Action:** Add retry button in error dialogs and toasts.

---

### 6.4 Loading States

#### 6.4.1 No Skeleton During First Grid Render
`grid.py:289-312` provides `show_skeleton_loading()` but it's not called during initial grid render.

**Action:** Show skeleton cards during first render and library load.

#### 6.4.2 No Loading State for Details Panel
`details_panel.py:57` shows "Select a game" but has no loading state when fetching async data (e.g., update info).

**Action:** Add a loading spinner or skeleton to details panel during data fetch.

#### 6.4.3 Search Debounce Not Visible
`search_bar.py:261-264` debounces at 300ms with no visual indicator. User doesn't know if search is pending.

**Action:** Show a subtle spinner or "Searching..." text in the search bar during debounce.

#### 6.4.4 No Progress Percentage for Scans
Startup overlay (`ui_mixin.py:316`) shows an indeterminate progress bar. User can't estimate time remaining.

**Action:** Emit progress count (e.g., "Scanning 45 of 200 shortcuts...").

---

### 6.5 Confirmations & Undo

#### 6.5.1 No Confirmation for Destructive Actions
Game deletion, collection deletion (`library_sidebar.py:30-31`), and filter clearing (`filter_mixin.py:174-191`) happen immediately without confirmation.

**Action:** Add confirmation dialog for delete operations. At minimum: "Delete [game]? This cannot be undone."

#### 6.5.2 No Undo for Ratings
Rating changes in `card.py:560-561` are applied instantly with no undo.

**Action:** Support Ctrl+Z undo for rating/status changes. The `undo_redo.py` service exists but isn't wired to these actions.

#### 6.5.3 Batch Operations Unconfirmed
`batch_toolbar.py:80-101` applies bulk status/tag changes to all selected games without a confirmation prompt.

**Action:** Show "Apply [action] to X games?" confirmation before batch operations.

#### 6.5.4 Unsaved Changes Not Warned
Details panel allows editing metadata but switching games or closing the app doesn't warn about unsaved changes.

**Action:** Check for dirty state on game switch; prompt "Save changes?" if modified.

---

### 6.6 Navigation & Discoverability

#### 6.6.1 No Breadcrumbs
User doesn't see where they are when viewing a collection or filtered view. Only the title area shows "All Games" or a collection name.

**Action:** Add breadcrumb trail: "Library > RPGs > Playing" to show navigation context.

#### 6.6.2 No Navigation History
No back/forward button. Once user navigates to a collection, there's no quick way to return to the previous view.

**Action:** Add back/forward buttons or Alt+Left/Right keyboard shortcuts.

#### 6.6.3 Sidebar Collapse Icon Doesn't Reflect State
`library_sidebar.py:65` — chevron icon doesn't change direction when sidebar is collapsed.

**Action:** Toggle between `CHEVRON_LEFT` and `CHEVRON_RIGHT` based on collapsed state.

#### 6.6.4 Context Menu Hidden Until Hover
`card.py:314-329` — the "More" (three-dots) button only appears on hover. Not discoverable.

**Action:** Always show a subtle menu indicator, or add right-click context menu hint.

#### 6.6.5 Keyboard Shortcuts Not Discoverable
`window.py:142` sets up shortcuts but no built-in help dialog shows them.

**Action:** Add a "Keyboard Shortcuts" dialog accessible via `?` or Help menu.

---

### 6.7 Theme & Visual Consistency

#### 6.7.1 Hover Colors Not Unified
Card hover defined in `card.py:370-408`, sidebar hover in `theme.py:818-821`. No shared hover token.

**Action:** Add `bg_hover` token to theme and use it across all hoverable elements.

#### 6.7.2 Status Colors Unused in Details Panel
`theme.py` defines `status_backlog/playing/finished/dropped` colors but `details_panel.py` renders status as plain text.

**Action:** Apply status colors in the details panel status badge.

#### 6.7.3 High-Contrast Theme Color Concerns
High-contrast theme (`theme.py:270-309`) uses yellow focus (`line 284`) which may not meet WCAG AA against white text.

**Action:** Validate all theme variants against WCAG AA contrast ratios (4.5:1 for normal text).

#### 6.7.4 No Live Preview in Theme Editor
`theme_editor.py` requires applying the theme to see changes. No side-by-side preview.

**Action:** Add a preview panel showing sample UI elements with the edited theme.

---

### 6.8 Dialog UX

#### 6.8.1 No Dialog Position/Size Memory
Dialogs (`preferences.py`, etc.) don't save/restore position or size. Always reopen at default location.

**Action:** Persist dialog geometry in settings; restore on reopen.

#### 6.8.2 Non-Modal Error Dialogs Can Stack
`ui_mixin.py:53` creates non-modal error dialogs. Multiple errors can stack up unnoticed.

**Action:** Queue error dialogs or consolidate into a single error panel.

#### 6.8.3 No Cancel Mid-Operation in Bulk Import
`enhanced_bulk_import.py` doesn't appear to support cancellation during processing.

**Action:** Add cancel button that sets a cancellation flag checked by the worker thread.

---

### 6.9 Grid & Card Interaction

#### 6.9.1 Multi-Select Checkbox Hidden
`card.py:148` — selection checkbox only appears in batch mode on hover. Users may not discover multi-select.

**Action:** Show a subtle checkbox area on all cards. Or add "Select multiple" button to toolbar.

#### 6.9.2 Update Badge Tooltip Vague
`card.py:165` shows "Update available" or "Version unknown" without explaining why.

**Action:** Show current vs. available version in tooltip: "Update: v0.3 → v0.5".

#### 6.9.3 Tag Chips Not Clickable
Tag chips in `card.py:225-251` are static labels. Clicking a tag should filter the library.

**Action:** Make tag chips clickable — add `cursor: pointer` and filter-on-click behavior.

#### 6.9.4 Hover Lift Shifts Text
`card.py:386-388` adjusts margins on hover, causing text below to shift vertically.

**Action:** Use `transform: translateY()` or `box-shadow` instead of margin changes.

---

### 6.10 Search & Filter UX

#### 6.10.1 No Saved Searches
`search_bar.py:105-138` stores recent searches but has no way to pin/save frequent queries.

**Action:** Add "Save this search" option to search dropdown.

#### 6.10.2 Filter Chips Can Scroll Off-Screen
`filter_chips.py:87` uses `QScrollArea` but there's no visual indicator that more chips exist.

**Action:** Add fade-out gradient or "N more" badge when chips overflow.

#### 6.10.3 Quick Filter Counts Stale During Load
`filter_mixin.py:220-223` updates pill labels with counts, but during grid loading old counts display.

**Action:** Show a subtle loading indicator on count badges during recalculation.

---

### 6.11 Empty States

#### 6.11.1 Empty Collection Has No Context
When a collection is empty, the generic empty-state CTA shows but doesn't mention which collection is being viewed.

**Action:** Show "No games in [Collection Name]. Add games from your library."

#### 6.11.2 Empty Search Results Offer No Guidance
No suggestion to refine search query or clear active filters.

**Action:** Show "No results for '[query]'. Try a different search or clear filters." with a clear-filters button.

---

### 6.12 Onboarding & First-Run

#### 6.12.1 No Welcome Dialog
App launches straight to an empty grid on first run. New users don't know where to start.

**Action:** Show a welcome modal with "Scan your game folder" CTA on first launch.

#### 6.12.2 Startup Messages Too Technical
`ui_mixin.py:303-351` shows "Starting...", "Loading library...", "Building UI...", "Rendering grid..." — confusing for non-technical users.

**Action:** Use friendly messages: "Getting things ready...", "Loading your games..."

#### 6.12.3 Advanced Search Syntax Not Discoverable
Search syntax help (`search_bar.py:196-222`) only appears on focus. New users won't discover `status:playing` syntax.

**Action:** Add a "?" icon next to search bar that opens a search syntax help popover.

---

### 6.13 Drag & Drop (Missing Feature)

No drag-and-drop support exists in the application:
- Can't drag games to reorder or assign to collections
- Can't drag files (shortcuts/links) into the window to import
- Can't drag games onto sidebar collections

**Action:** Implement drag-to-collection as a high-value improvement. Accept file drops for import.

---

### 6.14 Notifications & Status

#### 6.14.1 Status Bar Messages Easily Missed
`window.py:612-625` — footer status bar is bottom-right and messages auto-clear after 5-8 seconds.

**Action:** Use toasts for important status updates; keep status bar for persistent info only.

#### 6.14.2 Game Count Footer Lacks Context
`window.py:628-645` shows "X of Y games" but doesn't explain why some are hidden (filtered? collection subset?).

**Action:** Show "X of Y games (filtered by: [active filters])" or "X games in [Collection]".

#### 6.14.3 No Notification Grouping
Multiple toasts stack vertically and consume screen space.

**Action:** Group related notifications; add "N more" collapse for rapid-fire toasts.

---

## Priority Summary

### Critical (Fix First)
1. Oversized files — split `f95_api.py`, `f95_auth.py`, `smart_download.py`
2. Generic exception handling — 184 occurrences to fix
3. Silent render/build failures in grid — users lose data without knowing
4. No confirmation for destructive actions

### High
5. Test coverage — currently ~0.2%, target >60%
6. Credential security audit
7. Linting + CI setup
8. Accessibility: tooltips, focus indicators, tab order
9. Loading states for grid render and details panel
10. Keyboard shortcuts help dialog

### Medium
11. Game model decomposition (67 fields)
12. Virtual scrolling for large libraries
13. Theme contrast validation (WCAG AA)
14. Dialog position/size persistence
15. Search debounce indicator
16. Drag-and-drop to collections

### Low
17. First-run welcome dialog
18. Breadcrumb navigation
19. Saved searches
20. Notification grouping
21. Settings import/export

---

*Document Version: 1.0*
*Last Updated: 2026-02-12*
