"""
GameGrid widget for displaying a grid of game cards.

Provides:
- Responsive grid layout
- Keyboard navigation
- Multi-select support
- Empty state handling
- Loading skeleton state
"""

from __future__ import annotations

from typing import List, Optional
import time

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton, QSizePolicy, QGridLayout, QStackedLayout,
)
from PySide6.QtGui import QColor
from shiboken6 import isValid

from app.models import Game
from app.ui.theme import current_theme, card_style
from app.logging_utils import get_logger, kv, RateLimiter, wrap_slot

from .card import GameCard
from .skeleton import SkeletonCard

_log = get_logger("ui.game_grid")
_render_rate = RateLimiter()


class GameGrid(QWidget):
    """Grid container for displaying GameCard widgets."""

    game_selected = Signal(str)   # game_id
    game_play = Signal(str)       # game_id
    context_action = Signal(str, str)  # (game_id, action)
    status_filter_requested = Signal(str)
    updates_requested = Signal(str)
    rating_changed = Signal(str, object)
    tag_filter_requested = Signal(str)
    scan_requested = Signal()  # emitted when user clicks scan from empty state
    selection_changed = Signal(list)  # emits list of selected game_ids

    def __init__(self) -> None:
        super().__init__()
        self._focused_index: int = -1  # keyboard navigation index
        self._multi_select_mode: bool = False
        self._selected_game_ids: set[str] = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # Stacked layout for empty state vs grid
        self._stack = QStackedLayout()

        # Empty state widget
        self._empty_state = self._build_empty_state()
        self._stack.addWidget(self._empty_state)

        # Scroll area for cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)

        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(10)
        self.container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.scroll.setWidget(self.container)
        self._stack.addWidget(self.scroll)

        stack_widget = QWidget()
        stack_widget.setLayout(self._stack)
        outer.addWidget(stack_widget, 1)

        # lightweight loading overlay shown during costly renders
        self._loading_overlay: QFrame | None = None

        self._games: List[Game] = []
        self._view_mode = "comfortable"
        self._type_scale = "normal"
        self._resize_timer = QTimer(self)
        self._resize_timer.setInterval(120)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(wrap_slot(_log, "resize_timeout")(self._render))
        self._rendering = False
        self._render_pending = False
        self._render_reason = "init"
        self._rate = RateLimiter()
        self._card_rate = RateLimiter()
        self._skeleton_cards: List[SkeletonCard] = []
        _log.info("grid_init %s", kv(view_mode=self._view_mode, type_scale=self._type_scale))

    def set_games(self, games: List[Game]) -> None:
        self._games = games or []
        self._focused_index = -1  # reset keyboard focus on data change
        self._render_reason = "set_games"
        if self._rate.allow("set_games", interval_ms=500):
            _log.info("set_games %s", kv(count=len(self._games)))
        self._update_empty_state_visibility()
        self._render()

    def set_view_mode(self, mode: str) -> None:
        if mode not in ("comfortable", "compact"):
            return
        if mode != self._view_mode and self._rate.allow("view_mode", interval_ms=1000):
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

    def _clear_grid(self) -> None:
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
        # bail out if widget or child objects are already destroyed (can happen on shutdown/nav swap)
        if not isValid(self) or not isValid(self.scroll) or not isValid(self.container):
            if self._rate.allow("render_invalid_obj", interval_ms=1000):
                _log.warning("render_skip %s", kv(reason="invalid_qobject"))
            self._rendering = False
            self._render_pending = False
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
                kv(event="grid_render", reason=reason, w=viewport.width(), h=viewport.height(), games=len(self._games)),
            )
            self._render_inner()
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
                kv(event="grid_render", reason=reason, duration_ms=round(duration_ms, 1), pending=self._render_pending),
            )
            self._set_loading(False)
            self._rendering = False
            if self._render_pending:
                self._render_pending = False
                self._render_reason = "pending_rerun"
                QTimer.singleShot(0, self._render)

    def _render_inner(self) -> None:
        start = time.perf_counter()
        self._clear_grid()

        viewport = self.scroll.viewport().size()
        if viewport.width() <= 0 or viewport.height() <= 0:
            if self._rate.allow("render_invalid_view", interval_ms=500):
                _log.warning("render_skip %s", kv(reason="viewport_invalid", w=viewport.width(), h=viewport.height()))
            QTimer.singleShot(100, self._render)
            return

        # Responsive-ish: choose columns based on width
        width = max(240, self.scroll.viewport().width())
        card_w = 260 if self._view_mode == "comfortable" else 200
        cols = max(1, width // card_w)
        self.container.setMinimumWidth(card_w)

        chip_level = "medium"
        if card_w < 230:
            chip_level = "narrow"
        elif card_w > 280:
            chip_level = "wide"

        _log.debug(
            "render_layout %s",
            kv(width=width, height=viewport.height(), card_w=card_w, cols=cols, chip_level=chip_level, games=len(self._games)),
        )

        for idx, g in enumerate(self._games):
            try:
                card = GameCard(g, view_mode=self._view_mode, parent=self.container, type_scale=self._type_scale, chip_level=chip_level, multi_select_mode=self._multi_select_mode)
            except Exception:
                _log.exception("card_build_failed %s", kv(game_id=getattr(g, "game_id", "unknown"), title=getattr(g, "title", "unknown")))
                continue
            card.context_action.connect(self.context_action.emit)
            card.clicked.connect(self.game_selected.emit)
            card.play_clicked.connect(self.game_play.emit)
            card.status_clicked.connect(self.status_filter_requested.emit)
            card.updates_clicked.connect(self.updates_requested.emit)
            card.rating_changed.connect(self.rating_changed.emit)
            card.tag_clicked.connect(self.tag_filter_requested.emit)
            card.selection_toggled.connect(self._on_card_selection_toggled)

            # Restore selection state if card was previously selected
            if g.game_id in self._selected_game_ids:
                card.set_selected(True)

            row = idx // cols
            col = idx % cols
            try:
                self.grid.addWidget(card, row, col)
            except Exception:
                _log.exception("add_widget_failed %s", kv(row=row, col=col, game_id=getattr(g, "game_id", "unknown")))
                card.setParent(None)
                continue

            # Staggered entrance animation (only for first ~20 visible cards to avoid performance issues)
            if idx < 20 and self._render_reason in ("set_games", "init"):
                card.fade_in(delay_ms=idx * 25)

            if self._card_rate.allow(f"card_added:{g.game_id}", 800):
                _log.debug("card_added %s", kv(game_id=g.game_id, row=row, col=col))

        # push cards to top-left
        self.grid.setRowStretch((len(self._games) // cols) + 1, 1)
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        duration = (time.perf_counter() - start) * 1000
        _log.info("render_inner_done %s", kv(cards=len(self._games), cols=cols, duration_ms=round(duration, 1)))
        # orphan check
        for idx in range(self.grid.count()):
            w = self.grid.itemAt(idx).widget()
            if isinstance(w, GameCard) and w.parent() is None:
                _log.warning("orphan GameCard detected: %s", getattr(w.game, "title", "unknown"))
        if self.grid.count() == 0 and self._games:
            _log.warning("grid_empty_after_render %s", kv(expected=len(self._games)))

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

    def show_skeleton_loading(self, count: int = 8) -> None:
        """Show skeleton loading cards."""
        self._clear_grid()
        self._skeleton_cards = []

        width = max(240, self.scroll.viewport().width())
        card_w = 260 if self._view_mode == "comfortable" else 200
        cols = max(1, width // card_w)

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

    # ---- helpers ----
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
            lbl = QLabel("Loading…")
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

    def _build_empty_state(self) -> QWidget:
        """Build the empty state widget shown when no games are present."""
        theme = current_theme()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(40, 60, 40, 60)
        layout.setSpacing(16)

        layout.addStretch(2)

        # Icon placeholder (using unicode game controller)
        icon_label = QLabel("🎮")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(f"font-size: 64px; color: {theme.text_muted.name()};")
        layout.addWidget(icon_label)

        # Title
        title = QLabel("No games in your library")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size: 20px; font-weight: 600; color: {theme.text.name()};")
        layout.addWidget(title)

        # Description
        desc = QLabel("Scan your shortcuts folder to add games, or check your search filters.")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 13px; color: {theme.text_muted.name()}; max-width: 400px;")
        layout.addWidget(desc)

        layout.addSpacing(12)

        # Action buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch(1)

        scan_btn = QPushButton("Scan Shortcuts")
        scan_btn.setMinimumWidth(140)
        scan_btn.setStyleSheet(
            f"QPushButton {{ "
            f"background: {theme.accent.name()}; "
            f"color: {theme.bg.name()}; "
            f"padding: 10px 20px; "
            f"border-radius: {theme.radius_md}px; "
            f"font-weight: 600; "
            f"font-size: 13px; "
            f"border: none; "
            f"}} "
            f"QPushButton:hover {{ background: {theme.accent.lighter(110).name()}; }}"
        )
        scan_btn.setCursor(Qt.PointingHandCursor)
        scan_btn.clicked.connect(lambda: self.scan_requested.emit())
        btn_row.addWidget(scan_btn)

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

    # ---- Keyboard Navigation ----
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
        else:
            super().keyPressEvent(event)

    def _get_column_count(self) -> int:
        """Calculate current number of columns based on viewport width."""
        width = max(240, self.scroll.viewport().width())
        card_w = 260 if self._view_mode == "comfortable" else 200
        return max(1, width // card_w)

    def _move_focus(self, delta: int, cols: int) -> None:
        """Move focus by delta positions."""
        if not self._games:
            return

        new_idx = self._focused_index + delta
        if new_idx < 0:
            new_idx = 0
        elif new_idx >= len(self._games):
            new_idx = len(self._games) - 1

        if new_idx != self._focused_index:
            self._set_focus_index(new_idx)

    def _set_focus_index(self, idx: int) -> None:
        """Set focus to the card at the given index."""
        # Clear previous focus styling
        if 0 <= self._focused_index < self.grid.count():
            old_item = self.grid.itemAt(self._focused_index)
            if old_item and old_item.widget():
                self._apply_focus_style(old_item.widget(), False)

        self._focused_index = idx

        # Apply focus styling to new card
        if 0 <= idx < self.grid.count():
            item = self.grid.itemAt(idx)
            if item and item.widget():
                card = item.widget()
                self._apply_focus_style(card, True)
                # Scroll to ensure card is visible
                self.scroll.ensureWidgetVisible(card, 50, 50)
                # Emit selection
                if isinstance(card, GameCard):
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
            self._set_focus_index(0)

    def clear_focus(self) -> None:
        """Clear keyboard focus from the grid."""
        if 0 <= self._focused_index < self.grid.count():
            item = self.grid.itemAt(self._focused_index)
            if item and item.widget():
                self._apply_focus_style(item.widget(), False)
        self._focused_index = -1

    # ---- Multi-Select Mode ----
    def set_multi_select_mode(self, enabled: bool) -> None:
        """Enable or disable multi-select mode for the grid."""
        if self._multi_select_mode == enabled:
            return
        self._multi_select_mode = enabled
        if not enabled:
            self._selected_game_ids.clear()
        # Update all existing cards
        for idx in range(self.grid.count()):
            item = self.grid.itemAt(idx)
            if item and item.widget() and isinstance(item.widget(), GameCard):
                item.widget().set_multi_select_mode(enabled)
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
        for idx in range(self.grid.count()):
            item = self.grid.itemAt(idx)
            if item and item.widget() and isinstance(item.widget(), GameCard):
                item.widget().set_selected(True)
        self.selection_changed.emit(list(self._selected_game_ids))

    def clear_selection(self) -> None:
        """Clear all selections."""
        self._selected_game_ids.clear()
        for idx in range(self.grid.count()):
            item = self.grid.itemAt(idx)
            if item and item.widget() and isinstance(item.widget(), GameCard):
                item.widget().set_selected(False)
        self.selection_changed.emit([])

    def _on_card_selection_toggled(self, game_id: str, is_selected: bool) -> None:
        """Handle selection toggle from a card."""
        if is_selected:
            self._selected_game_ids.add(game_id)
        else:
            self._selected_game_ids.discard(game_id)
        self.selection_changed.emit(list(self._selected_game_ids))
