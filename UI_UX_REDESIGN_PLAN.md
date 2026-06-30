# UI/UX Complete Redesign Plan

> **Project:** Game Library Manager v4 (PySide6 Desktop App)
> **Status:** UI/UX redesign planning notes
> **Goal:** Transform the current functional but utilitarian interface into a stunning, modern, and intuitive desktop experience.

---

## Current State Analysis

### What Exists
- **6 themes** (Dark, Light, Neubrutalism, Neumorphism, Glassmorphism, High Contrast) with design tokens
- **Typography system** with responsive scaling (small/default/large)
- **Game cards** with hover overlays, ambient color extraction, staggered fade-in
- **3-panel layout** (sidebar | grid | details) via QSplitter
- **Flat toolbar** with 10+ buttons crammed into a single horizontal row
- **Filter controls bar** with pills, combo boxes, and toggle buttons on a second row
- **Skeleton loading** and **toast notifications**
- **Search bar** with syntax parsing, recent searches, suggestion popup

### Key Pain Points Identified

1. **Toolbar Overload**: 10+ buttons (Scan, Check Updates, Tools, New Collection, Add to Collection, Rename Collection, Delete Collection, Comfortable, Compact, Focus, Details, Select) all in one flat row. Visually overwhelming and hard to parse.

2. **No Visual Hierarchy in Top Area**: Title label "Library", search bar, and all buttons share the same visual weight. Nothing guides the eye.

3. **Controls Bar Clutter**: Quick pills + tag filter + 4 combo box filters + sort combo + view toggles + focus button + details toggle + select button all on one line. Collapses badly at smaller widths.

4. **Sidebar is Plain**: Just a QListWidget with text items. No icons, no visual grouping, no visual richness.

5. **Details Panel is a Form**: Dense stack of form fields with no visual sections, no visual breathing room, no visual delight.

6. **Card Design is Functional but Generic**: Cards have good hover animations but the resting state is quite plain - just icon + title. Status badge is a tiny 20px circle in the corner.

7. **No Status Bar Richness**: Just a plain QStatusBar with temporary text messages.

8. **Inconsistent Spacing**: Some areas use raw pixel values, others use design tokens. Not uniform.

9. **No Branded Identity**: No app icon/logo in the titlebar area, no distinctive visual identity.

10. **Color Palette Under-utilized**: Theme accent colors are used sparingly. Most UI is monochrome surface/bg/text.

---

## Redesign Vision

**Design Language:** "Refined Clarity" - Clean, spacious layouts with purposeful use of color, depth, and motion. Inspired by modern media managers (Plex, Jellyfin, Playnite) and design-forward desktop apps (Figma, Linear, Arc).

**Core Principles:**
1. **Breathing Room** - Generous padding, clear sections, whitespace as a design element
2. **Progressive Disclosure** - Show essentials first, reveal details on interaction
3. **Color with Purpose** - Accent colors convey meaning (status, actions, urgency)
4. **Depth & Layers** - Subtle shadows, overlays, and elevation create spatial hierarchy
5. **Micro-Delight** - Smooth transitions, hover feedback, and polished details

---

## Phase 1: Design System Enhancement

### 1.1 Extended Color Tokens (theme.py)

**Files:** `src/app/ui/theme.py`

Add semantic color tokens to ThemeSpec:

```
# Semantic status colors (per theme)
status_backlog: QColor      # Cool blue
status_playing: QColor      # Vibrant green
status_finished: QColor     # Warm amber/gold
status_dropped: QColor      # Muted red/orange

# Semantic feedback colors
success: QColor             # Green for positive feedback
warning: QColor             # Amber for caution
error: QColor               # Red for errors
info: QColor                # Blue for information

# Surface hierarchy
surface_raised: QColor      # Cards, modals (elevated from surface)
surface_sunken: QColor      # Input fields, wells (recessed)
surface_overlay: QColor     # Overlays, dropdowns with alpha

# Interactive
interactive_hover: QColor   # General hover tint
interactive_active: QColor  # Active/pressed state
interactive_muted: QColor   # Disabled-but-visible controls

# Gradient support
gradient_start: QColor      # For header/hero gradients
gradient_end: QColor
```

Update all 6 themes with these new tokens. This provides a semantic vocabulary so widgets don't need to compute colors ad-hoc.

### 1.2 Spacing & Layout Tokens

**Files:** `src/app/ui/theme.py`

Add layout tokens to ThemeSpec:

```
# Layout dimensions
sidebar_width_min: int = 220
sidebar_width_max: int = 320
details_width_min: int = 340
details_width_max: int = 520
card_min_width: int = 200
card_max_width: int = 320
toolbar_height: int = 48

# Section spacing
section_gap: int = 24       # Between major sections
content_gap: int = 16       # Between content items
inline_gap: int = 8         # Between inline items

# Card grid
grid_gap: int = 12          # Gap between cards
grid_padding: int = 16      # Padding around grid
```

### 1.3 Iconography System

**Files:** New file `src/app/ui/icons.py`

Create a centralized icon provider using Unicode/emoji initially with clear abstraction for future SVG support:

```python
class AppIcons:
    # Navigation
    NAV_LIBRARY = "..."       # Library icon
    NAV_UPDATES = "..."       # Updates icon
    NAV_HEALTH = "..."        # Health icon
    NAV_COLLECTION = "..."    # Collection icon
    NAV_SMART = "..."         # Smart collection icon

    # Actions
    ACT_SCAN = "..."          # Scan shortcut
    ACT_PLAY = "..."          # Play game
    ACT_EDIT = "..."          # Edit metadata
    ACT_SEARCH = "..."        # Search
    ACT_FILTER = "..."        # Filter
    ACT_SETTINGS = "..."      # Settings gear

    # Status
    STS_BACKLOG = "..."       # Backlog indicator
    STS_PLAYING = "..."       # Playing indicator
    STS_FINISHED = "..."      # Completed indicator
    STS_DROPPED = "..."       # Dropped indicator
    STS_UPDATE = "..."        # Update available

    @staticmethod
    def icon_label(icon_key: str, size: int = 16) -> str:
        """Return styled HTML or stylesheet for an icon."""
        ...
```

---

## Phase 2: Layout Architecture Overhaul

### 2.1 Redesigned Main Window Structure

**Files:** `src/app/ui/main_window/window.py`, `src/app/ui/main_window/ui_mixin.py`

Replace the current flat layout with a structured, layered approach:

```
+----------------------------------------------------------+
|  [Logo] Game Library Manager          [Search........] [?]|  <- Header bar (slim, branded)
+----------------------------------------------------------+
|        |                                          |       |
| SIDE-  |  [Toolbar: Scan | Updates | Tools]       | DETL  |
| BAR    |  [Filter chips when active]              | PANEL |
|        |  +------------------------------------+  |       |
| All    |  |                                    |  | Title |
| Games  |  |         GAME GRID                  |  | Icon  |
| -----  |  |                                    |  | Meta  |
| Collns |  |     (cards with improved layout)   |  | Tags  |
|  RPGs  |  |                                    |  | Notes |
|  VNs   |  |                                    |  | Src   |
| -----  |  |                                    |  | Arch  |
| Smart  |  |                                    |  | ...   |
|  New   |  +------------------------------------+  |       |
| -----  |  [Status bar: count | filters | view]    |       |
| Tools  |                                          |       |
+----------------------------------------------------------+
```

**Key changes:**
- **Header bar** replaces the top toolbar: slim 48px band with logo/title on left, global search centered, and settings/profile on right
- **Context toolbar** replaces the controls bar: action buttons relevant to current view (Library, Updates, Health) with icon+label style
- **Status strip** at bottom shows game count, active filters summary, view mode controls
- Sidebar, grid, details remain a 3-panel QSplitter but with improved styling

### 2.2 Redesigned Header Bar

**Files:** `src/app/ui/main_window/window.py` (in `_build_topbar`)

Replace the current chaotic toolbar:

```
BEFORE: [Library label] [stretch] [search] [Scan] [Check Updates] [Tools]
        [New Collection] [Add to Collection] [Rename] [Delete]

AFTER:  [App Icon + Title] -------- [Search Bar (centered, wide)] -------- [Theme] [Settings]
```

- Remove collection management buttons from the top bar entirely (move to sidebar context actions)
- Search bar becomes the visual centerpiece, wider, with rounded pill shape
- Settings and theme become small icon buttons on the far right
- The "Scan" and "Check Updates" become part of the context toolbar below

### 2.3 Context Toolbar

**Files:** `src/app/ui/main_window/window.py` (new `_build_context_toolbar`)

A contextual action bar that changes based on active view:

**Library view:**
```
[Scan] [Check Updates] | [All] [Missing] [Updates] [Source] | [Sort: v] [View: v] | [Focus] [Select]
```

**Updates view:**
```
[< Back to Library] [Refresh] | [All] [Has Updates] [Unknown] | [Density: v]
```

**Health view:**
```
[< Back to Library] [Re-scan] | [All] [Errors] [Warnings] | [Density: v]
```

- Buttons have icon + text, styled as a segmented control group
- Quick filter pills become proper segmented toggle buttons with active color indicator
- Sort and View become compact dropdown buttons
- Separator dividers between logical groups

### 2.4 Redesigned Sidebar

**Files:** `src/app/ui/widgets/library_sidebar.py`

Transform from plain QListWidget to a rich, structured navigation panel:

```
+------------------+
|  LIBRARY         |
|  [icon] All (42) |  <- Active: accent bg, bold
+------------------+
|  COLLECTIONS     |  <- Section header, muted, uppercase small
|  [icon] RPGs (8) |
|  [icon] VNs (12) |
|  [+] New...      |  <- Inline "add" button
+------------------+
|  SMART           |
|  [icon] Playing  |
|  [icon] Recent   |
+------------------+
|  TOOLS           |
|  [icon] Updates  |
|  [icon] Health   |
+------------------+
```

**Changes:**
- Icons for every nav item (Unicode initially)
- Active item gets accent-colored background with rounded corners
- Section headers are styled differently (uppercase, small, muted, with top border)
- "New Collection" becomes an inline `[+]` button within the Collections section
- Right-click context menu on collections for rename/delete (removing those toolbar buttons)
- Hover effects with subtle background tint
- Item counts styled as a secondary badge/pill on the right side
- Bottom section: version number, settings link

### 2.5 Footer Status Bar

**Files:** `src/app/ui/main_window/window.py` (new `_build_status_bar`)

Replace the default QStatusBar with a custom styled status strip:

```
[Games: 42 of 128 shown] [Filters: Status=Playing, Tag=RPG] ... [Comfortable | Compact] [Details]
```

- Left: game count (filtered / total)
- Center: active filter summary (clickable to clear)
- Right: view mode segmented control, details toggle
- Slim 28px height, subtle top border, surface_alt background

---

## Phase 3: Card Redesign

### 3.1 Enhanced Card Layout

**Files:** `src/app/ui/widgets/game_grid/card.py`

Redesign cards for better visual hierarchy and information density:

**Comfortable Mode (220px+ width):**
```
+----------------------------------+
|                                  |
|        [GAME ICON/IMAGE]         |  <- Rounded top corners, fills width
|                                  |
|  [Status dot] [Update badge]    |  <- Floating overlays on icon
+----------------------------------+
|  Game Title That May Wrap to     |  <- Bold, 14-15px, max 2 lines
|  Two Lines                       |
|  ★★★★☆  ·  2d ago              |  <- Rating + last played, muted
|  [RPG] [VN] [+3]               |  <- Tag chips, compact
+----------------------------------+
```

**Compact Mode (180px width):**
```
+------------------------+
|                        |
|    [GAME ICON]         |
|  [Status] [Update]    |
+------------------------+
|  Game Title            |  <- Single line, ellipsized
|  ★★★☆☆               |  <- Rating only
+------------------------+
```

**Key changes from current:**
- **Title moves below icon** (already is, but clean up spacing)
- **Rating and "last played" always visible** below title (not only in overlay)
- **Tag chips visible at rest** (max 2-3, compact) instead of only in hover overlay
- **Status indicator** becomes a small colored dot (6-8px) in top-left of icon area using semantic status colors
- **Update badge** becomes a small accent-colored dot in top-right when update available
- **Hover overlay simplified**: Shows only action buttons (Play, Open Folder, More...) since metadata is now visible at rest
- **Card border** removed or very subtle (1px matching card bg); depth comes from shadow
- **Ambient color** subtly tints the bottom gradient of the icon area

### 3.2 Improved Hover State

**Files:** `src/app/ui/widgets/game_grid/card.py`

Redesign hover overlay as a clean bottom sheet:

```
Hover state:
+----------------------------------+
|                                  |
|        [GAME ICON]               |  <- Slight scale-up (102%)
|                                  |
+----------------------------------+
|  Game Title                      |
|  ★★★★☆  ·  2d ago              |
|  [RPG] [VN]                     |
|  [  Play  ] [Folder] [  ...  ]  |  <- Action buttons appear on hover
+----------------------------------+
```

- Remove the full-overlay approach (overlay_sheet covering the card)
- Instead, action buttons slide in from bottom of the card info area
- Card gets a "lift" effect: increased shadow + slight translate-Y on hover
- Icon area gets a subtle brightness increase

### 3.3 Card Grid Spacing

**Files:** `src/app/ui/widgets/game_grid/grid.py`

- Increase grid gap from 10px to 14px
- Add grid padding (16px around the grid)
- Better column width calculation for visual balance
- Minimum card width: 200px comfortable, 160px compact
- Maximum card width: 320px (prevent overly wide cards on large screens)

---

## Phase 4: Details Panel Redesign

### 4.1 Sectioned Details Layout

**Files:** `src/app/ui/widgets/details_panel.py`

Transform from a flat form to a visually organized panel with clear sections:

```
+----------------------------------+
|  Game Title                      |  <- Large, bold (18px)
|  RPG · LNK · High confidence    |  <- Subtitle meta line
+----------------------------------+
|                                  |
|  [  PLAY  ]                     |  <- Full-width accent primary button
|                                  |
+----------------------------------+
|  STATUS & RATING                 |  <- Section header
|  ┌────────────┐ ┌──────────────┐|
|  │ ▶ Playing  │ │ ★★★★☆ 8/10 │|  <- Status chip + rating display
|  └────────────┘ └──────────────┘|
+----------------------------------+
|  TAGS                            |
|  [RPG] [Fantasy] [Open World]   |  <- Editable chip row
|  [+ Add tag...]                 |
+----------------------------------+
|  NOTES                           |
|  Short review text here...      |  <- TextEdit with softer styling
+----------------------------------+
|  SOURCE                          |
|  [URL field............] [Open] |
|  Installed: 0.9.2               |
|  Source: 1.0.0 (checked 2d ago) |
+----------------------------------+
|  ARCHIVES                        |
|  Folder: [...............] [📁] |
|  Archive: [...............] [📁]|
+----------------------------------+
|  INFO                            |
|  Shortcut: LNK                  |
|  Path: C:\Games\...             |
|  Last played: 2 days ago        |
+----------------------------------+
```

**Key changes:**
- **Section dividers** with header labels (uppercase, small, muted, with horizontal line)
- **Play button** becomes a large, prominent, accent-colored button
- **Status** displayed as a colored chip instead of a plain combo box (clicking opens dropdown)
- **Rating** displayed as interactive stars (click to set) instead of combo box
- **Tags** displayed as editable chips with add/remove, not a plain text field
- **Grouped layout** with clear visual sections separated by subtle dividers
- **Scrollable** - panel becomes scrollable with all sections, instead of fixed
- **Section collapse** - sections can be collapsed via click on header (progressive disclosure)

---

## Phase 5: Polish & Micro-Interactions

### 5.1 Refined Scrollbar

**Files:** `src/app/ui/theme.py`

- Thinner scrollbar (8px instead of 10px)
- Only visible on hover (auto-hide with fade animation)
- Rounded thumb with accent tint on hover

### 5.2 Enhanced Search Bar

**Files:** `src/app/ui/main_window/window.py`

- Pill-shaped (large border-radius) search input
- Search icon (magnifying glass) inside the field on the left
- Subtle inner shadow for "sunken" feel
- Focus state: accent border glow + slight expand animation

### 5.3 Improved Filter Chips

**Files:** `src/app/ui/widgets/filter_chips.py`

- Animated entrance/exit (fade + slide)
- "Clear all" becomes a subtle "x" icon button, not a text button
- Active filter chips use semantic colors (status chips use status colors)

### 5.4 Button Styling Tiers

**Files:** `src/app/ui/theme.py`

Define button style tiers:
- **Primary**: Filled accent color, white text (Play, Scan)
- **Secondary**: Outlined accent border, accent text (Check Updates, Open)
- **Ghost**: No border/bg, accent text, hover reveals bg (Settings, Close)
- **Danger**: Red-tinted for destructive actions (Delete, Remove)

Add helper functions: `primary_btn_style()`, `secondary_btn_style()`, `ghost_btn_style()`, `danger_btn_style()`

### 5.5 Empty State Enhancement

**Files:** `src/app/ui/widgets/game_grid/grid.py`

- Larger, more polished empty state illustration
- Subtle background pattern or gradient
- Multiple CTAs: "Scan Shortcuts" (primary) + "Import Library" (secondary)
- Animated entrance

### 5.6 Loading States

**Files:** `src/app/ui/widgets/game_grid/skeleton.py`

- Improved skeleton shimmer with gradient sweep (not just opacity pulse)
- Skeleton matches exact card layout (icon area + title bar + chip row)
- Skeleton count matches expected card count

### 5.7 Transition Animations

**Files:** Various widget files

- View switching (Library/Updates/Health): Crossfade transition
- Details panel open/close: Slide animation (not instant show/hide)
- Sidebar collapse/expand: Smooth width animation
- Card entrance: Staggered slide-up + fade (current is good, refine easing)

---

## Phase 6: Responsive Design

### 6.1 Breakpoint System

**Files:** `src/app/ui/main_window/ui_mixin.py`

Define clear breakpoints:

```
< 900px:   Compact mode
            - Sidebar auto-collapses to icon-only mode
            - Details panel hidden
            - Single-column card grid
            - Toolbar items collapse to icons-only

900-1200px: Default mode
            - Sidebar visible (220px)
            - Optional details panel
            - 2-3 column grid
            - Full toolbar

> 1200px:  Expanded mode
            - Wide sidebar (280px)
            - Details panel visible
            - 3-5 column grid
            - Spacious toolbar
```

### 6.2 Collapsible Sidebar

**Files:** `src/app/ui/widgets/library_sidebar.py`

- At narrow widths, sidebar collapses to show only icons (40px width)
- Hovering expands it temporarily
- Toggle button to pin expanded/collapsed state
- Smooth width animation on collapse/expand

---

## Phase 7: Accessibility Enhancements

### 7.1 Focus Visibility

- All interactive elements get visible focus rings (2px accent outline)
- Focus ring has 2px offset to not overlap content
- Tab order follows logical visual flow: header -> sidebar -> toolbar -> grid -> details

### 7.2 Color Contrast

- Ensure all text meets WCAG AA (4.5:1 body, 3:1 large text)
- Status colors have distinct shapes/icons (not color-only differentiation)
- High contrast theme gets extra attention for full WCAG AAA

### 7.3 Keyboard Enhancement

- `Ctrl+1-5` for sidebar navigation sections
- `Tab` cycles: search -> toolbar -> grid -> details
- Grid: arrow keys, Enter to open details, Space to play
- `Escape` clears search / closes details / exits multi-select

---

## Implementation Order

### Batch 1: Foundation (Theme + Layout)
1. **Extend ThemeSpec** with semantic colors, button tiers, layout tokens
2. **Create icons.py** with centralized icon system
3. **Redesign header bar** (slim branded header + centered search)
4. **Redesign footer status bar** (move view controls, filter summary)

### Batch 2: Navigation + Toolbar
5. **Redesign sidebar** (icons, sections, inline actions, context menus)
6. **Build context toolbar** (view-specific action bars)
7. **Move collection buttons** to sidebar context menu
8. **Clean up controls bar** into context toolbar

### Batch 3: Cards + Grid
9. **Redesign card layout** (always-visible metadata, refined hover)
10. **Improve grid spacing** and column calculation
11. **Enhance empty state** and skeleton loading
12. **Refine card animations** (hover lift, entrance stagger)

### Batch 4: Details Panel
13. **Redesign details panel** (sections, interactive controls, scroll)
14. **Add section headers** with collapsible regions
15. **Replace form controls** (status chips, star rating, tag chips)
16. **Add prominent Play button**

### Batch 5: Polish
17. **Button style tiers** (primary/secondary/ghost/danger)
18. **Enhanced search bar** (pill shape, icon, glow focus)
19. **Refined scrollbar** styling
20. **Transition animations** (view switch, panel slide, sidebar collapse)

### Batch 6: Responsive + Accessibility
21. **Breakpoint system** implementation
22. **Collapsible sidebar** at narrow widths
23. **Focus management** audit and fixes
24. **Keyboard navigation** enhancements

---

## Files Modified Summary

| File | Changes |
|------|---------|
| `src/app/ui/theme.py` | Semantic colors, layout tokens, button style helpers, scrollbar refinement |
| `src/app/ui/icons.py` | **NEW** - Centralized icon system |
| `src/app/ui/typography.py` | Minor tweaks for new heading levels |
| `src/app/ui/main_window/window.py` | Restructured layout: header bar, context toolbar, footer |
| `src/app/ui/main_window/ui_mixin.py` | Breakpoint system, panel animations, responsive helpers |
| `src/app/ui/widgets/library_sidebar.py` | Complete redesign with icons, sections, context menus |
| `src/app/ui/widgets/game_grid/card.py` | New card layout, refined hover, always-visible metadata |
| `src/app/ui/widgets/game_grid/grid.py` | Grid spacing, column calculation, empty state, animations |
| `src/app/ui/widgets/game_grid/skeleton.py` | Improved shimmer, layout matching |
| `src/app/ui/widgets/details_panel.py` | Sectioned layout, interactive controls, scroll |
| `src/app/ui/widgets/filter_chips.py` | Animated entrance/exit, semantic colors |
| `src/app/ui/widgets/search_bar.py` | Pill shape, icon, focus glow |

---

## Design Constraints

1. **No new dependencies** - Everything uses PySide6 + existing deps
2. **Backward compatible settings** - Existing `settings.json` migrated gracefully
3. **Performance budget** - No increase in initial load time; maintain 60fps scroll
4. **All 6 themes supported** - Every visual change works across all themes
5. **Existing functionality preserved** - No feature regression
6. **File size limits** - No file exceeds 500 lines (split if needed)
7. **Existing patterns** - Use signals/slots, design tokens, mixin pattern

---

*Plan created: 2026-02-11*
*Version: 1.0*
