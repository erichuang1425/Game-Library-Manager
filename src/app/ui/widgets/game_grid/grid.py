"""
GameGrid widget for displaying a grid of game cards.

Provides:
- Virtual scrolling (only visible cards + buffer rows are in the DOM)
- Two browse modes: scroll (continuous) and pages (paginated)
- Responsive grid layout
- Keyboard navigation
- Multi-select support
- Empty state handling
- Loading skeleton state
"""

from __future__ import annotations

from typing import List, Optional
import math
import time

from PySide6.QtCore import Qt, Signal, QTimer, QRect
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QSizePolicy, QGridLayout, QStackedLayout,
)
from PySide6.QtGui import QColor
from shiboken6 import isValid

from app.models import Game
from app.ui.theme import current_theme, card_style, primary_btn_style, secondary_btn_style, ghost_btn_style
from app.ui.icons import AppIcons
from app.logging_utils import get_logger, kv, RateLimiter, wrap_slot

from .card import GameCard
from .skeleton import SkeletonCard

_log = get_logger("ui.game_grid")
_render_rate = RateLimiter()


class GameGrid(QWidget):
    """Grid container for displaying GameCard widgets with virtual scrolling."""

    game_selected = Signal(str)   # game_id
    game_play = Signal(str)       # game_id
    context_action = Signal(str, str)  # (game_id, action)
    status_filter_requested = Signal(str)
    updates_requested = Signal(str)
    rating_changed = Signal(str, object)
    tag_filter_requested = Signal(str)
    scan_requested = Signal()  # emitted when user clicks scan from empty state
    selection_changed = Signal(list)  # emits list of selected game_ids
    browse_mode_changed = Signal(str)  # "scroll" or "pages"
    page_changed = Signal(int)  # current page (0-indexed)

    def __init__(self) -> None:
        super().__init__()
        self._focused_index: int = -1  # keyboard navigation index
        self._multi_select_mode: bool = False
        self._selected_game_ids: set[str] = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Stacked layout for empty state vs grid
        self._stack = QStackedLayout()

        # Empty state widget
        self._empty_state = self._build_empty_state()
        self._stack.addWidget(self._empty_state)

        # Main content area (holds scroll-mode or pages-mode)
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

        # Scroll area for cards (used in both modes for the card grid)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        theme = current_theme()
        self.grid.setContentsMargins(
            theme.grid_padding, theme.grid_padding,
            theme.grid_padding, theme.grid_padding,
        )
        self.grid.setSpacing(theme.grid_gap)
        self.container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.scroll.setWidget(self.container)
        self._content_layout.addWidget(self.scroll, 1)

        # Pagination bar (hidden in scroll mode, shown in pages mode)
        self._pagination_bar = self._build_pagination_bar()
        self._pagination_bar.hide()
        self._content_layout.addWidget(self._pagination_bar)

        self._stack.addWidget(self._content_widget)

        stack_widget = QWidget()
        stack_widget.setLayout(self._stack)
        outer.addWidget(stack_widget, 1)

        # lightweight loading overlay shown during costly renders
        self._loading_overlay: QFrame | None = None

        self._games: List[Game] = []
        self._view_mode = "comfortable"
        self._type_scale = "normal"
        self._resize_timer = QTimer(self)
        self._resize_timer.setInterval(200)  # debounce resize to reduce layout thrashing
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(wrap_slot(_log, "resize_timeout")(self._render))
        self._rendering = False
        self._render_pending = False
        self._render_reason = "init"
        self._rate = RateLimiter()
        self._card_rate = RateLimiter()
        self._skeleton_cards: List[SkeletonCard] = []

        # --- Browse mode state ---
        self._browse_mode: str = "scroll"   # "scroll" or "pages"
        self._page_size: int = 24           # cards per page in pages mode
        self._current_page: int = 0         # 0-indexed current page
        self._total_pages: int = 1

        # --- Viewport retry state ---
        self._viewport_retry_count: int = 0
        self._VIEWPORT_MAX_RETRIES: int = 5

        # --- Virtual scroll state ---
        self._visible_cards: dict[int, GameCard] = {}  # index -> card widget
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(50)  # debounce scroll updates (was 16ms — too aggressive)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._on_scroll_settle)
        self._last_scroll_range: tuple[int, int] = (0, 0)
        self._est_card_h: int = 300
        self._current_cols: int = 1
        self._current_card_w: int = 260
        self._current_chip_level: str = "medium"

        # Coalesce rapid set_games calls into a single deferred render
        self._set_games_timer = QTimer(self)
        self._set_games_timer.setSingleShot(True)
        self._set_games_timer.setInterval(16)  # ~1 frame
        self._set_games_timer.timeout.connect(self._render)

        # Connect scroll events for virtual scrolling
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

        _log.info("grid_init %s", kv(view_mode=self._view_mode, type_scale=self._type_scale, browse_mode=self._browse_mode))

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def set_games(self, games: List[Game]) -> None:
        self._games = games or []
        self._focused_index = -1  # reset keyboard focus on data change
        self._render_reason = "set_games"
        if self._rate.allow("set_games", interval_ms=500):
            _log.info("set_games %s", kv(count=len(self._games), mode=self._browse_mode))
        self._update_empty_state_visibility()
        # Clamp current page if out of range
        self._total_pages = max(1, math.ceil(len(self._games) / self._page_size)) if self._games else 1
        if self._current_page >= self._total_pages:
            self._current_page = max(0, self._total_pages - 1)
        self._set_games_timer.start()

    def set_view_mode(self, mode: str) -> None:
        if mode not in ("comfortable", "compact"):
            return
        if mode == self._view_mode:
            return
        if self._rate.allow("view_mode", interval_ms=1000):
            _log.info("view_mode_changed %s", kv(mode=mode))
        self._render_reason = "view_mode"
        self._view_mode = mode
        self._render()

    def set_type_scale(self, scale: str) -> None:
        if scale not in ("small", "normal", "large"):
            return
        if scale == self._type_scale:
            return
        if self._rate.allow("type_scale", interval_ms=1000):
            _log.info("type_scale_changed %s", kv(scale=scale))
        self._render_reason = "type_scale"
        self._type_scale = scale
        self._render()

    def set_browse_mode(self, mode: str) -> None:
        """Switch between 'scroll' and 'pages' browse modes."""
        if mode not in ("scroll", "pages"):
            return
        if mode == self._browse_mode:
            return
        _log.info("browse_mode_changed %s", kv(old=self._browse_mode, new=mode))
        self._browse_mode = mode
        self._current_page = 0
        if mode == "pages":
            self._pagination_bar.show()
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self._pagination_bar.hide()
            self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._render_reason = "browse_mode"
        self.browse_mode_changed.emit(mode)
        self._render()

    def set_page_size(self, size: int) -> None:
        """Set the number of cards per page (pages mode)."""
        size = max(6, min(120, size))
        if size == self._page_size:
            return
        self._page_size = size
        self._total_pages = max(1, math.ceil(len(self._games) / self._page_size)) if self._games else 1
        if self._current_page >= self._total_pages:
            self._current_page = max(0, self._total_pages - 1)
        if self._browse_mode == "pages":
            self._render_reason = "page_size"
            self._render()

    def get_browse_mode(self) -> str:
        return self._browse_mode

    def get_current_page(self) -> int:
        return self._current_page

    def get_total_pages(self) -> int:
        return self._total_pages

    # ------------------------------------------------------------------ #
    #  Grid layout computation
    # ------------------------------------------------------------------ #

    def _compute_layout(self):
        """Compute columns, card width, and chip level from current viewport."""
        theme = current_theme()
        width = max(240, self.scroll.viewport().width())
        preferred_w = 260 if self._view_mode == "comfortable" else 200
        min_w = theme.card_min_width  # 200
        max_w = theme.card_max_width  # 320
        gap = theme.grid_gap
        padding = theme.grid_padding * 2

        available = width - padding
        cols = max(1, (available + gap) // (preferred_w + gap))
        card_w = max(min_w, min(max_w, (available - gap * (cols - 1)) // cols))

        if card_w < min_w and cols > 1:
            cols -= 1
            card_w = max(min_w, min(max_w, (available - gap * (cols - 1)) // cols))

        chip_level = "medium"
        if card_w < 230:
            chip_level = "narrow"
        elif card_w > 280:
            chip_level = "wide"

        return cols, card_w, chip_level

    # ------------------------------------------------------------------ #
    #  Clear / render orchestration
    # ------------------------------------------------------------------ #

    def _clear_grid(self) -> None:
        self._visible_cards.clear()
        # Reset the deferred-icon stagger counter so the next batch of cards
        # starts with zero delay.
        from .card import _deferred_icon_counter
        import app.ui.widgets.game_grid.card as _card_mod
        _card_mod._deferred_icon_counter = 0
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
        # reset stretches so previous column/row counts don't leave empty space
        for c in range(self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
        for r in range(self.grid.rowCount()):
            self.grid.setRowStretch(r, 0)
        if _render_rate.allow("clear_grid", 500):
            _log.debug("grid_cleared %s", kv(items=self.grid.count()))

    def _render(self) -> None:
        # bail out if widget or child objects are already destroyed
        if not isValid(self) or not isValid(self.scroll) or not isValid(self.container):
            if self._rate.allow("render_invalid_obj", interval_ms=1000):
                _log.warning("render_skip %s", kv(reason="invalid_qobject"))
            self._rendering = False
            self._render_pending = False
            return
        # Allow callers to suppress renders during bulk configuration.
        if getattr(self, '_render_suppressed', False):
            self._render_pending = True
            return
        if self._rendering:
            if self._rate.allow("render_reentry", interval_ms=400):
                _log.debug("render_deferred %s", kv(reason="in_progress"))
            self._render_pending = True
            return
        self._rendering = True
        self._set_loading(True)
        reason = self._render_reason or "unknown"
        self._render_reason = "idle"
        QTimer.singleShot(0, lambda r=reason: self._render_async(r))

    def _render_async(self, reason: str) -> None:
        viewport = self.scroll.viewport().size()
        start = time.perf_counter()
        try:
            _log.info(
                "render_start %s",
                kv(event="grid_render", reason=reason, w=viewport.width(), h=viewport.height(),
                   games=len(self._games), mode=self._browse_mode),
            )
            if self._browse_mode == "pages":
                self._render_pages()
            else:
                self._render_virtual_scroll()
        except Exception:
            _log.exception("render_failed %s", kv(event="grid_render"))
            from PySide6.QtWidgets import QMessageBox
            try:
                QMessageBox.warning(self, "Render error", "An error occurred while rendering the library. See manager.log.")
            except Exception:
                pass
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            _log.info(
                "render_end %s",
                kv(event="grid_render", reason=reason, duration_ms=round(duration_ms, 1),
                   pending=self._render_pending, mode=self._browse_mode),
            )
            self._set_loading(False)
            self._rendering = False
            if self._render_pending:
                self._render_pending = False
                self._render_reason = "pending_rerun"
                QTimer.singleShot(0, self._render)

    # ------------------------------------------------------------------ #
    #  SCROLL MODE — Virtual scrolling
    # ------------------------------------------------------------------ #

    def _render_virtual_scroll(self) -> None:
        """Render only cards visible in the viewport + buffer rows."""
        start = time.perf_counter()
        self._clear_grid()

        viewport = self.scroll.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            self._viewport_retry_count += 1
            if self._viewport_retry_count <= self._VIEWPORT_MAX_RETRIES:
                if self._rate.allow("render_invalid_view", interval_ms=500):
                    _log.warning("render_skip %s", kv(reason="viewport_invalid", retry=self._viewport_retry_count))
                QTimer.singleShot(100, self._render)
            else:
                _log.warning("render_abandon %s", kv(reason="viewport_invalid_max_retries"))
            return
        self._viewport_retry_count = 0

        cols, card_w, chip_level = self._compute_layout()
        self._current_cols = cols
        self._current_card_w = card_w
        self._current_chip_level = chip_level

        theme = current_theme()
        self.container.setMinimumWidth(theme.card_min_width)
        gap = theme.grid_gap

        # Estimate card height
        self._est_card_h = 300 if self._view_mode == "comfortable" else 200
        total_rows = math.ceil(len(self._games) / cols) if self._games else 0

        # Total content height to make scrollbar work properly
        total_h = total_rows * (self._est_card_h + gap) + theme.grid_padding * 2
        self.container.setMinimumHeight(max(total_h, viewport.height()))

        # Determine which rows are visible (3 buffer rows for smoother scrolling)
        scroll_y = self.scroll.verticalScrollBar().value()
        row_h = self._est_card_h + gap

        first_visible_row = max(0, scroll_y // row_h - 3)  # 3 buffer rows above
        last_visible_row = min(total_rows - 1, (scroll_y + viewport.height()) // row_h + 3)  # 3 buffer below

        first_idx = first_visible_row * cols
        last_idx = min(len(self._games) - 1, (last_visible_row + 1) * cols - 1)

        self._last_scroll_range = (first_idx, last_idx)

        _log.debug(
            "virtual_scroll_render %s",
            kv(scroll_y=scroll_y, first_row=first_visible_row, last_row=last_visible_row,
               first_idx=first_idx, last_idx=last_idx, total=len(self._games), cols=cols),
        )

        # Render visible cards (skip fade-in on scroll to avoid animation overhead)
        reason = self._render_reason or "unknown"
        should_animate = reason in ("set_games", "init")
        for idx in range(first_idx, last_idx + 1):
            if idx < len(self._games):
                card = self._create_card(idx, chip_level)
                if card:
                    row = idx // cols
                    col = idx % cols
                    self.grid.addWidget(card, row, col)
                    self._visible_cards[idx] = card
                    if should_animate and idx < first_idx + 20:
                        card.fade_in(delay_ms=((idx - first_idx) % 20) * 25)

        # Column stretches
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)

        # Add bottom stretch to keep cards at top when few items
        self.grid.setRowStretch(total_rows, 1)

        duration = (time.perf_counter() - start) * 1000
        rendered = last_idx - first_idx + 1 if last_idx >= first_idx else 0
        _log.info("virtual_scroll_done %s", kv(
            rendered=rendered, total=len(self._games), cols=cols,
            duration_ms=round(duration, 1),
        ))

    def _on_scroll_value_changed(self, value: int) -> None:
        """Handle scroll position changes — trigger virtual scroll update."""
        if self._browse_mode != "scroll" or not self._games:
            return
        self._scroll_timer.start()

    def _on_scroll_settle(self) -> None:
        """Called after scroll settles — update visible cards."""
        if not isValid(self) or not isValid(self.scroll):
            return
        if self._browse_mode != "scroll" or not self._games:
            return

        viewport = self.scroll.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return

        cols = self._current_cols
        gap = current_theme().grid_gap
        row_h = self._est_card_h + gap
        scroll_y = self.scroll.verticalScrollBar().value()
        total_rows = math.ceil(len(self._games) / cols) if self._games else 0

        first_visible_row = max(0, scroll_y // row_h - 3)
        last_visible_row = min(total_rows - 1, (scroll_y + viewport.height()) // row_h + 3)

        first_idx = first_visible_row * cols
        last_idx = min(len(self._games) - 1, (last_visible_row + 1) * cols - 1)

        # Check if the visible range has changed enough to warrant re-render
        old_first, old_last = self._last_scroll_range
        if first_idx == old_first and last_idx == old_last:
            return  # No change needed

        # Prefer incremental updates when ranges overlap at all
        overlap_start = max(first_idx, old_first)
        overlap_end = min(last_idx, old_last)
        if overlap_end >= overlap_start:
            # Any overlap — do incremental update (add/remove only changed cards)
            self._incremental_scroll_update(first_idx, last_idx)
            return

        # No overlap at all — full re-render of visible region
        self._render_reason = "scroll"
        self._render()

    def _incremental_scroll_update(self, new_first: int, new_last: int) -> None:
        """Incrementally add/remove cards when scroll position changes slightly."""
        old_first, old_last = self._last_scroll_range
        cols = self._current_cols
        chip_level = self._current_chip_level

        # Remove cards that are no longer visible
        to_remove = []
        for idx in list(self._visible_cards.keys()):
            if idx < new_first or idx > new_last:
                card = self._visible_cards[idx]
                if isValid(card):
                    card.hide()
                    card.setParent(None)
                to_remove.append(idx)
        for idx in to_remove:
            del self._visible_cards[idx]

        # Add new cards that have become visible
        for idx in range(new_first, new_last + 1):
            if idx not in self._visible_cards and idx < len(self._games):
                card = self._create_card(idx, chip_level)
                if card:
                    row = idx // cols
                    col = idx % cols
                    self.grid.addWidget(card, row, col)
                    self._visible_cards[idx] = card

        self._last_scroll_range = (new_first, new_last)

    # ------------------------------------------------------------------ #
    #  PAGES MODE — Paginated rendering
    # ------------------------------------------------------------------ #

    def _render_pages(self) -> None:
        """Render a single page of cards with pagination controls."""
        start = time.perf_counter()
        self._clear_grid()

        viewport = self.scroll.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            self._viewport_retry_count += 1
            if self._viewport_retry_count <= self._VIEWPORT_MAX_RETRIES:
                if self._rate.allow("render_invalid_view", interval_ms=500):
                    _log.warning("render_skip %s", kv(reason="viewport_invalid", retry=self._viewport_retry_count))
                QTimer.singleShot(100, self._render)
            else:
                _log.warning("render_abandon %s", kv(reason="viewport_invalid_max_retries"))
            return
        self._viewport_retry_count = 0

        cols, card_w, chip_level = self._compute_layout()
        self._current_cols = cols
        self._current_card_w = card_w
        self._current_chip_level = chip_level

        theme = current_theme()
        self.container.setMinimumWidth(theme.card_min_width)
        # Reset container height for pages mode (no virtual scroll trick)
        self.container.setMinimumHeight(0)

        self._total_pages = max(1, math.ceil(len(self._games) / self._page_size)) if self._games else 1
        if self._current_page >= self._total_pages:
            self._current_page = max(0, self._total_pages - 1)

        page_start = self._current_page * self._page_size
        page_end = min(page_start + self._page_size, len(self._games))

        _log.debug(
            "render_pages %s",
            kv(page=self._current_page, total_pages=self._total_pages,
               start=page_start, end=page_end, cols=cols),
        )

        reason = self._render_reason or "unknown"
        for i, game_idx in enumerate(range(page_start, page_end)):
            card = self._create_card(game_idx, chip_level)
            if card:
                row = i // cols
                col = i % cols
                self.grid.addWidget(card, row, col)
                self._visible_cards[game_idx] = card
                if reason in ("set_games", "init", "page_change"):
                    card.fade_in(delay_ms=(i % 20) * 25)

        # Push cards to top-left
        total_rows = math.ceil((page_end - page_start) / cols) if page_end > page_start else 0
        self.grid.setRowStretch(total_rows, 1)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)

        # Update pagination controls
        self._update_pagination_bar()

        # Scroll to top of page
        self.scroll.verticalScrollBar().setValue(0)

        duration = (time.perf_counter() - start) * 1000
        _log.info("render_pages_done %s", kv(
            page=self._current_page, total_pages=self._total_pages,
            rendered=page_end - page_start, cols=cols,
            duration_ms=round(duration, 1),
        ))

    def go_to_page(self, page: int) -> None:
        """Navigate to a specific page (0-indexed)."""
        page = max(0, min(page, self._total_pages - 1))
        if page == self._current_page:
            return
        self._current_page = page
        self._focused_index = -1
        self.page_changed.emit(page)
        self._render_reason = "page_change"
        self._render()

    def next_page(self) -> None:
        """Go to the next page."""
        if self._current_page < self._total_pages - 1:
            self.go_to_page(self._current_page + 1)

    def prev_page(self) -> None:
        """Go to the previous page."""
        if self._current_page > 0:
            self.go_to_page(self._current_page - 1)

    # ------------------------------------------------------------------ #
    #  Pagination bar
    # ------------------------------------------------------------------ #

    def _build_pagination_bar(self) -> QWidget:
        """Build the pagination controls bar."""
        theme = current_theme()
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"QFrame {{ background: {theme.surface.name(QColor.HexArgb)}; "
            f"border-top: 1px solid {theme.outline.name(QColor.HexArgb)}; }}"
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(theme.grid_padding, 4, theme.grid_padding, 4)
        layout.setSpacing(6)

        layout.addStretch(1)

        # Prev button
        self._page_prev_btn = QPushButton(f"{AppIcons.UI_ARROW_LEFT}  Prev")
        self._page_prev_btn.setCursor(Qt.PointingHandCursor)
        self._page_prev_btn.setStyleSheet(ghost_btn_style(theme))
        self._page_prev_btn.clicked.connect(self.prev_page)
        layout.addWidget(self._page_prev_btn)

        # Page buttons container
        self._page_btns_layout = QHBoxLayout()
        self._page_btns_layout.setSpacing(4)
        layout.addLayout(self._page_btns_layout)

        # Next button
        self._page_next_btn = QPushButton(f"Next  {AppIcons.UI_ARROW_RIGHT}")
        self._page_next_btn.setCursor(Qt.PointingHandCursor)
        self._page_next_btn.setStyleSheet(ghost_btn_style(theme))
        self._page_next_btn.clicked.connect(self.next_page)
        layout.addWidget(self._page_next_btn)

        layout.addStretch(1)

        # Page info label
        self._page_info_label = QLabel("Page 1 of 1")
        self._page_info_label.setStyleSheet(
            f"color: {theme.text_muted.name()}; font-size: 11px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._page_info_label)

        return bar

    def _update_pagination_bar(self) -> None:
        """Update pagination controls to reflect current state."""
        theme = current_theme()
        self._page_prev_btn.setEnabled(self._current_page > 0)
        self._page_next_btn.setEnabled(self._current_page < self._total_pages - 1)

        # Update page info
        if self._games:
            page_start = self._current_page * self._page_size + 1
            page_end = min((self._current_page + 1) * self._page_size, len(self._games))
            self._page_info_label.setText(
                f"{page_start}-{page_end} of {len(self._games)}"
            )
        else:
            self._page_info_label.setText("No games")

        # Clear existing page buttons
        while self._page_btns_layout.count():
            item = self._page_btns_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        # Build page number buttons (show max 7 buttons with ellipsis)
        max_visible = 7
        if self._total_pages <= max_visible:
            pages_to_show = list(range(self._total_pages))
        else:
            # Always show first, last, current, and neighbors
            pages_to_show = set()
            pages_to_show.add(0)
            pages_to_show.add(self._total_pages - 1)
            for delta in range(-1, 2):
                p = self._current_page + delta
                if 0 <= p < self._total_pages:
                    pages_to_show.add(p)
            # Fill remaining slots near current
            for delta in range(-2, 3):
                if len(pages_to_show) >= max_visible:
                    break
                p = self._current_page + delta
                if 0 <= p < self._total_pages:
                    pages_to_show.add(p)
            pages_to_show = sorted(pages_to_show)

        last_shown = -2
        for p in pages_to_show:
            if p - last_shown > 1:
                # Add ellipsis
                ellipsis = QLabel("...")
                ellipsis.setStyleSheet(
                    f"color: {theme.text_muted.name()}; font-size: 11px; "
                    f"background: transparent; border: none; padding: 0 2px;"
                )
                self._page_btns_layout.addWidget(ellipsis)

            btn = QPushButton(str(p + 1))
            btn.setFixedSize(32, 28)
            btn.setCursor(Qt.PointingHandCursor)
            if p == self._current_page:
                btn.setStyleSheet(
                    f"QPushButton {{ background: {theme.accent.name()}; "
                    f"color: {theme.bg.name()}; border: none; "
                    f"border-radius: {theme.radius_sm}px; font-weight: 600; "
                    f"font-size: 11px; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; "
                    f"color: {theme.text_muted.name()}; border: none; "
                    f"border-radius: {theme.radius_sm}px; font-size: 11px; }}"
                    f"QPushButton:hover {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
                    f"color: {theme.text.name()}; }}"
                )
            page_num = p
            btn.clicked.connect(lambda checked, pn=page_num: self.go_to_page(pn))
            self._page_btns_layout.addWidget(btn)
            last_shown = p

    # ------------------------------------------------------------------ #
    #  Card creation (shared between modes)
    # ------------------------------------------------------------------ #

    def _create_card(self, idx: int, chip_level: str, animate: bool = False) -> Optional[GameCard]:
        """Create a single GameCard for the game at the given index."""
        g = self._games[idx]
        try:
            card = GameCard(
                g, view_mode=self._view_mode, parent=self.container,
                type_scale=self._type_scale, chip_level=chip_level,
                multi_select_mode=self._multi_select_mode,
            )
        except Exception:
            _log.exception("card_build_failed %s", kv(game_id=getattr(g, "game_id", "unknown"), title=getattr(g, "title", "unknown")))
            return None
        card.context_action.connect(self.context_action.emit)
        card.clicked.connect(self.game_selected.emit)
        card.play_clicked.connect(self.game_play.emit)
        card.status_clicked.connect(self.status_filter_requested.emit)
        card.updates_clicked.connect(self.updates_requested.emit)
        card.rating_changed.connect(self.rating_changed.emit)
        card.tag_clicked.connect(self.tag_filter_requested.emit)
        card.selection_toggled.connect(self._on_card_selection_toggled)

        if g.game_id in self._selected_game_ids:
            card.set_selected(True)

        if animate:
            card.fade_in(delay_ms=(idx % 20) * 25)
        return card

    # ------------------------------------------------------------------ #
    #  Resize
    # ------------------------------------------------------------------ #

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_overlay_geometry()
        self._render_reason = "resize"
        self._resize_timer.start()
        if self._rate.allow("resize_trigger", interval_ms=250):
            _log.debug("resize_trigger %s", kv(w=self.width(), h=self.height()))

    def refresh(self) -> None:
        if self._rate.allow("refresh", interval_ms=500):
            _log.debug("grid_refresh")
        self._render_reason = "refresh"
        self._render()

    # ------------------------------------------------------------------ #
    #  Skeleton loading
    # ------------------------------------------------------------------ #

    def show_skeleton_loading(self, count: int = 8) -> None:
        """Show skeleton loading cards."""
        self._clear_grid()
        self._skeleton_cards = []

        theme = current_theme()
        width = max(240, self.scroll.viewport().width())
        preferred_w = 260 if self._view_mode == "comfortable" else 200
        gap = theme.grid_gap
        padding = theme.grid_padding * 2
        available = width - padding
        cols = max(1, (available + gap) // (preferred_w + gap))

        for idx in range(count):
            skeleton = SkeletonCard(view_mode=self._view_mode, parent=self.container)
            self._skeleton_cards.append(skeleton)
            row = idx // cols
            col = idx % cols
            self.grid.addWidget(skeleton, row, col)

        self._stack.setCurrentIndex(1)  # Show grid with skeletons

    def hide_skeleton_loading(self) -> None:
        """Remove skeleton cards and prepare for real content."""
        for skeleton in self._skeleton_cards:
            skeleton.stop_animation()
            skeleton.deleteLater()
        self._skeleton_cards.clear()

    # ------------------------------------------------------------------ #
    #  Overlay helpers
    # ------------------------------------------------------------------ #

    def _ensure_overlay(self) -> None:
        if self._loading_overlay is not None:
            return
        try:
            overlay = QFrame(self)
            overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            overlay.setStyleSheet("background: rgba(0,0,0,90); border-radius: 8px;")
            overlay.setVisible(False)
            ol_layout = QVBoxLayout(overlay)
            ol_layout.setContentsMargins(16, 16, 16, 16)
            ol_layout.setSpacing(8)
            lbl = QLabel("Loading\u2026")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: white; font-weight:600;")
            ol_layout.addStretch(1)
            ol_layout.addWidget(lbl, 0, Qt.AlignCenter)
            ol_layout.addStretch(2)
            self._loading_overlay = overlay
        except Exception:
            _log.exception("overlay_init_failed")
            self._loading_overlay = None

    def _set_loading(self, show: bool) -> None:
        self._ensure_overlay()
        if self._loading_overlay is None:
            return
        if show:
            self._update_overlay_geometry()
            self._loading_overlay.raise_()
        self._loading_overlay.setVisible(show)

    def _update_overlay_geometry(self) -> None:
        if self._loading_overlay is None:
            return
        if self.width() > 0 and self.height() > 0:
            self._loading_overlay.setGeometry(self.rect())

    # ------------------------------------------------------------------ #
    #  Empty state
    # ------------------------------------------------------------------ #

    def _build_empty_state(self) -> QWidget:
        """Build a polished empty state widget."""
        theme = current_theme()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(60, 80, 60, 80)
        layout.setSpacing(12)
        layout.addStretch(2)

        # Large icon
        icon_label = QLabel(AppIcons.NAV_LIBRARY)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"font-size: 72px; color: {theme.text_muted.name()}; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(icon_label)

        layout.addSpacing(8)

        # Title
        title = QLabel("Your library is empty")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {theme.text.name()}; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(title)

        # Description
        desc = QLabel(
            "Point the scanner at your shortcuts folder to build your library,\n"
            "or adjust your search filters if you expect to see games."
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size: 13px; color: {theme.text_muted.name()}; "
            f"line-height: 1.5; max-width: 440px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(desc)

        layout.addSpacing(24)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)

        scan_btn = QPushButton(f"{AppIcons.ACT_SCAN}  Scan Shortcuts")
        scan_btn.setMinimumWidth(160)
        scan_btn.setStyleSheet(primary_btn_style(theme))
        scan_btn.setCursor(Qt.PointingHandCursor)
        scan_btn.clicked.connect(lambda: self.scan_requested.emit())
        btn_row.addWidget(scan_btn)

        import_btn = QPushButton(f"{AppIcons.ACT_IMPORT}  Import Library")
        import_btn.setMinimumWidth(140)
        import_btn.setStyleSheet(secondary_btn_style(theme))
        import_btn.setCursor(Qt.PointingHandCursor)
        # Import is handled at the window level; emit scan as a fallback signal
        import_btn.setToolTip("Import a previously exported library JSON file")
        btn_row.addWidget(import_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addStretch(3)
        return widget

    def _update_empty_state_visibility(self) -> None:
        """Show empty state when no games, otherwise show grid."""
        if not self._games:
            self._stack.setCurrentIndex(0)  # empty state
        else:
            self._stack.setCurrentIndex(1)  # grid

    # ------------------------------------------------------------------ #
    #  Keyboard Navigation
    # ------------------------------------------------------------------ #

    def keyPressEvent(self, event) -> None:
        """Handle keyboard navigation in the grid."""
        if not self._games:
            super().keyPressEvent(event)
            return

        key = event.key()
        cols = self._get_column_count()

        if key == Qt.Key_Right:
            self._move_focus(1, cols)
        elif key == Qt.Key_Left:
            self._move_focus(-1, cols)
        elif key == Qt.Key_Down:
            self._move_focus(cols, cols)
        elif key == Qt.Key_Up:
            self._move_focus(-cols, cols)
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            self._activate_focused()
        elif key == Qt.Key_Space:
            self._play_focused()
        elif key == Qt.Key_PageDown:
            if self._browse_mode == "pages":
                self.next_page()
            else:
                super().keyPressEvent(event)
        elif key == Qt.Key_PageUp:
            if self._browse_mode == "pages":
                self.prev_page()
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def _get_column_count(self) -> int:
        """Calculate current number of columns based on viewport width."""
        theme = current_theme()
        width = max(240, self.scroll.viewport().width())
        preferred_w = 260 if self._view_mode == "comfortable" else 200
        gap = theme.grid_gap
        padding = theme.grid_padding * 2
        available = width - padding
        return max(1, (available + gap) // (preferred_w + gap))

    def _move_focus(self, delta: int, cols: int) -> None:
        """Move focus by delta positions."""
        if not self._games:
            return

        # In pages mode, constrain focus to current page
        if self._browse_mode == "pages":
            page_start = self._current_page * self._page_size
            page_end = min(page_start + self._page_size, len(self._games)) - 1
            new_idx = self._focused_index + delta
            new_idx = max(page_start, min(page_end, new_idx))
        else:
            new_idx = self._focused_index + delta
            new_idx = max(0, min(len(self._games) - 1, new_idx))

        if new_idx != self._focused_index:
            self._set_focus_index(new_idx)

    def _set_focus_index(self, idx: int) -> None:
        """Set focus to the card at the given index."""
        # Clear previous focus styling
        if self._focused_index in self._visible_cards:
            old_card = self._visible_cards[self._focused_index]
            if isValid(old_card):
                self._apply_focus_style(old_card, False)

        self._focused_index = idx

        # Apply focus styling to new card
        if idx in self._visible_cards:
            card = self._visible_cards[idx]
            if isValid(card):
                self._apply_focus_style(card, True)
                # Scroll to ensure card is visible
                self.scroll.ensureWidgetVisible(card, 50, 50)
                # Emit selection
                self.game_selected.emit(card.game.game_id)

    def _apply_focus_style(self, card: QWidget, focused: bool) -> None:
        """Apply or remove focus styling from a card."""
        if not isinstance(card, GameCard):
            return
        theme = current_theme()
        if focused:
            card.setStyleSheet(
                f"QFrame {{ {card_style(theme)} border: 2px solid {theme.focus.name()}; }}"
                f"QFrame:hover {{ {card_style(theme, hover=True)} }}"
            )
        else:
            card.setStyleSheet(
                f"QFrame {{ {card_style(theme)} }}"
                f"QFrame:hover {{ {card_style(theme, hover=True)} }}"
            )

    def _activate_focused(self) -> None:
        """Activate (select) the currently focused card."""
        if 0 <= self._focused_index < len(self._games):
            game = self._games[self._focused_index]
            self.game_selected.emit(game.game_id)

    def _play_focused(self) -> None:
        """Play the currently focused game."""
        if 0 <= self._focused_index < len(self._games):
            game = self._games[self._focused_index]
            self.game_play.emit(game.game_id)

    def focus_first(self) -> None:
        """Focus the first card in the grid."""
        if self._games:
            if self._browse_mode == "pages":
                self._set_focus_index(self._current_page * self._page_size)
            else:
                self._set_focus_index(0)

    def clear_focus(self) -> None:
        """Clear keyboard focus from the grid."""
        if self._focused_index in self._visible_cards:
            card = self._visible_cards[self._focused_index]
            if isValid(card):
                self._apply_focus_style(card, False)
        self._focused_index = -1

    # ------------------------------------------------------------------ #
    #  Multi-Select Mode
    # ------------------------------------------------------------------ #

    def set_multi_select_mode(self, enabled: bool) -> None:
        """Enable or disable multi-select mode for the grid."""
        if self._multi_select_mode == enabled:
            return
        self._multi_select_mode = enabled
        if not enabled:
            self._selected_game_ids.clear()
        # Update all existing visible cards
        for card in self._visible_cards.values():
            if isValid(card) and isinstance(card, GameCard):
                card.set_multi_select_mode(enabled)
        self.selection_changed.emit(list(self._selected_game_ids))

    def is_multi_select_mode(self) -> bool:
        """Check if multi-select mode is enabled."""
        return self._multi_select_mode

    def get_selected_game_ids(self) -> List[str]:
        """Get list of selected game IDs."""
        return list(self._selected_game_ids)

    def select_all(self) -> None:
        """Select all games in the current view."""
        self._selected_game_ids = {g.game_id for g in self._games}
        for card in self._visible_cards.values():
            if isValid(card) and isinstance(card, GameCard):
                card.set_selected(True)
        self.selection_changed.emit(list(self._selected_game_ids))

    def clear_selection(self) -> None:
        """Clear all selections."""
        self._selected_game_ids.clear()
        for card in self._visible_cards.values():
            if isValid(card) and isinstance(card, GameCard):
                card.set_selected(False)
        self.selection_changed.emit([])

    def _on_card_selection_toggled(self, game_id: str, is_selected: bool) -> None:
        """Handle selection toggle from a card."""
        if is_selected:
            self._selected_game_ids.add(game_id)
        else:
            self._selected_game_ids.discard(game_id)
        self.selection_changed.emit(list(self._selected_game_ids))
