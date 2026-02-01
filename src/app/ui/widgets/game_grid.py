from __future__ import annotations
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QTimer, QEasingCurve, QPropertyAnimation, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QFrame, QPushButton, QSizePolicy, QGridLayout, QMenu, QGraphicsOpacityEffect, QStackedLayout,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QAction, QCursor, QColor, QPixmap
from PySide6.QtWidgets import QApplication, QMessageBox
from shiboken6 import isValid

from app.models import Game
from app.services import pixmap_for_game, parse_version, compare_versions, icon_for_path, best_icon_path, extract_dominant_color
from app.services.version_parser import CompareResult
from app.models import game
from app.ui.theme import current_theme, card_style, chip_style
from app.logging_utils import get_logger, kv, RateLimiter, wrap_slot
import time

_log = get_logger("ui.game_grid")
_render_rate = RateLimiter()
_icon_rate = RateLimiter()
_icon_failures: set[str] = set()

def _status_label(status: str) -> str:
    mapping = {
        "backlog": "Backlog",
        "playing": "Playing",
        "finished": "Finished",
        "dropped": "Dropped",
    }
    return mapping.get(status, status)

def _confidence_icon(conf: str) -> str:
    return {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "🟡")

def _stars(rating: Optional[int]) -> str:
    # show 5-star visual mapped from 1..10
    if rating is None:
        return "—"
    five = max(1, min(5, round(rating / 2)))
    return "★" * five + "☆" * (5 - five)

class GameCard(QFrame):
    clicked = Signal(str)        # game_id
    play_clicked = Signal(str)   # game_id
    context_action = Signal(str, str)  # (game_id, action)
    status_clicked = Signal(str)       # status value
    updates_clicked = Signal(str)      # game_id
    rating_changed = Signal(str, object)  # game_id, rating or None
    tag_clicked = Signal(str)          # tag text


    def __init__(self, game: Game, view_mode: str = "comfortable", parent: Optional[QWidget] = None, type_scale: str = "normal", chip_level: str = "medium") -> None:
        super().__init__(parent)
        self.game = game
        self.type_scale = type_scale
        self.chip_level = chip_level
        self._icon_update_scheduled = False
        self._last_icon_size = QSize()
        self.setFrameShape(QFrame.StyledPanel)
        self.view_mode = view_mode
        self._theme = current_theme()
        theme = self._theme
        pad = theme.spacing_md if view_mode == "comfortable" else theme.spacing_sm

        # Use design token-based card styling
        self.setStyleSheet(
            f"QFrame {{ {card_style(theme)} }}"
            f"QFrame:hover {{ {card_style(theme, hover=True)} }}"
        )

        # Add subtle drop shadow for depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(theme.shadow.red(), theme.shadow.green(), theme.shadow.blue(), theme.elevation_low))
        self.setGraphicsEffect(shadow)
        self._shadow_effect = shadow

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # defensive: cards must never become top-level windows
        assert self.parent() is not None, "GameCard requires a parent; prevents floating windows."

        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(6 if view_mode == "compact" else 10)
        self.setMinimumHeight(200 if view_mode == "comfortable" else 150)

        # Icon-first area
        self.icon_frame = QFrame()
        self.icon_frame.setStyleSheet(
            f"QFrame {{ background:{theme.surface_alt.name(QColor.HexArgb)}; border-radius:12px; }}"
        )
        icon_ratio = 0.78 if view_mode == "comfortable" else 0.6
        icon_height = int(self.minimumHeight() * icon_ratio)
        self.icon_frame.setMinimumHeight(icon_height)
        icon_layout = QStackedLayout(self.icon_frame)
        icon_layout.setStackingMode(QStackedLayout.StackAll)

        base = QWidget()
        base_layout = QStackedLayout(base)
        base_layout.setStackingMode(QStackedLayout.StackAll)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setScaledContents(False)
        self._set_icon_pixmap(icon_height)
        base_layout.addWidget(self.icon_label)

        # Extract ambient color from icon for dynamic accents
        self._ambient_color: QColor | None = None
        self._extract_ambient_color()

        status_overlay = QWidget()
        status_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        sw = QHBoxLayout(status_overlay)
        sw.setContentsMargins(6, 6, 6, 6)
        sw.setSpacing(0)

        # Enhanced status badge with icon and subtle styling
        status_colors = {
            "backlog": ("#5cc1ff", "○"),   # Light blue, circle
            "playing": ("#7bed9f", "▶"),   # Green, play icon
            "finished": ("#ffa94d", "✓"),  # Orange, check
            "dropped": ("#ef6c00", "✕"),   # Dark orange, x
        }
        status_color, status_icon = status_colors.get(game.status, ("#5cc1ff", "○"))

        status_badge = QLabel(status_icon)
        status_badge.setFixedSize(20, 20)
        status_badge.setAlignment(Qt.AlignCenter)
        status_badge.setStyleSheet(
            f"background: {status_color}; "
            f"color: rgba(0,0,0,0.7); "
            f"border-radius: 10px; "
            f"font-size: 11px; "
            f"font-weight: bold;"
        )
        status_badge.setToolTip(_status_label(game.status))
        sw.addWidget(status_badge, 0, Qt.AlignLeft | Qt.AlignTop)
        sw.addStretch(1)
        base_layout.addWidget(status_overlay)

        icon_layout.addWidget(base)

        layout.addWidget(self.icon_frame)

        # Title row (rest-visible)
        title = QLabel()
        scale = {"small": 0.9, "normal": 1.0, "large": 1.1}.get(self.type_scale, 1.0)
        title_size = int((15 if view_mode == "comfortable" else 13) * scale)
        fm = title.fontMetrics()
        title.setWordWrap(True)
        title.setMaximumHeight(fm.lineSpacing() * 2 + 4)
        title.setText(game.title)
        title.setToolTip(game.title)
        title.setStyleSheet(f"font-size: {title_size}px; font-weight: 650; color: {theme.text.name()};")
        layout.addWidget(title)

        # Hover overlay bottom sheet
        self.overlay_sheet = QFrame()
        self.overlay_sheet.setStyleSheet(
            f"QFrame {{ background: rgba({theme.surface_alt.red()},{theme.surface_alt.green()},{theme.surface_alt.blue()},204); border-radius: 10px; }}"
        )
        self.overlay_opacity = QGraphicsOpacityEffect(self.overlay_sheet)
        self.overlay_sheet.setGraphicsEffect(self.overlay_opacity)
        self.overlay_opacity.setOpacity(0.0)
        self.overlay_anim = QPropertyAnimation(self.overlay_opacity, b"opacity", self)
        self.overlay_anim.setDuration(140)
        self.overlay_anim.setStartValue(0.0)
        self.overlay_anim.setEndValue(1.0)
        self.overlay_anim.finished.connect(self._on_overlay_anim_finished)

        sheet_layout = QVBoxLayout(self.overlay_sheet)
        sheet_layout.setContentsMargins(10, 8, 10, 8)
        sheet_layout.setSpacing(4)

        overlay_title = QLabel()
        overlay_title.setWordWrap(False)
        overlay_title.setToolTip(game.title)
        overlay_title.setStyleSheet(f"font-weight:650; color:{theme.text.name()};")
        ot = overlay_title.fontMetrics()
        overlay_title.setText(ot.elidedText(game.title, Qt.ElideRight, 220))
        sheet_layout.addWidget(overlay_title)

        stype = (game.shortcut_type or "—").upper()
        meta = QHBoxLayout()
        meta.setSpacing(6)

        def chip_btn(text: str, color, tooltip: str = "", click=None) -> QPushButton:
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFlat(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setStyleSheet(
                f"QPushButton {{ {chip_style(theme, color)} }}"
                f"QPushButton:hover {{ border-color:{theme.focus.name(QColor.HexArgb)}; }}"
                f"QPushButton:pressed {{ background-color: {theme.focus.name(QColor.HexArgb)}; color:{theme.bg.name(QColor.HexArgb)}; }}"
            )
            btn.setToolTip(tooltip or text)
            if click:
                btn.clicked.connect(click)
            return btn

        meta.addWidget(chip_btn(_status_label(game.status), theme.chip_bg, "Filter by status",
                                lambda: self.status_clicked.emit(game.status)))
        if self.chip_level != "narrow":
            meta.addWidget(chip_btn(stype, theme.chip_bg.lighter(108), "Shortcut type"))

        rating_text = _stars(game.rating)
        if self.chip_level == "wide":
            rating_btn = chip_btn(rating_text, theme.accent_alt.lighter(140), "Click to set rating")
            rating_btn.clicked.connect(lambda: self._pick_rating())
            meta.addWidget(rating_btn)

        # update chip if applicable
        inst_vi = parse_version(game.installed_version_raw) if game.installed_version_raw else None
        src_vi = parse_version(game.source_version_raw) if game.source_version_raw else None
        cmp = compare_versions(inst_vi, src_vi)
        if game.source_url and cmp in (CompareResult.OLDER, CompareResult.UNKNOWN):
            label = "Update" if cmp == CompareResult.OLDER else "Unknown"
            update_btn = chip_btn(label, QColor(255, 132, 132, 45), "Open Updates view",
                                  lambda: self.updates_clicked.emit(self.game.game_id))
            meta.addWidget(update_btn)
        meta.addStretch(1)
        sheet_layout.addLayout(meta)

        # Tags
        tags = game.tags or []
        tag_row = QHBoxLayout()
        tag_row.setSpacing(4)
        if tags:
            max_tags = 2
            for t in tags[:max_tags]:
                btn = chip_btn(t, theme.chip_bg.darker(105), "Filter by tag", lambda txt=t: self.tag_clicked.emit(txt))
                btn.setMaximumWidth(120)
                tag_row.addWidget(btn)
            if len(tags) > max_tags and self.chip_level == "wide":
                more = QLabel(f"+{len(tags) - max_tags} more")
                more.setStyleSheet(f"color:{theme.text_muted.name()}; font-size:{round(11*scale)}px;")
                tag_row.addWidget(more)
        tag_row.addStretch(1)
        sheet_layout.addLayout(tag_row)

        # Quick actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        play_btn = QPushButton("Play")
        play_btn.setStyleSheet("padding: 6px 12px;")
        play_btn.clicked.connect(lambda: self.play_clicked.emit(self.game.game_id))
        folder_btn = QPushButton("Open folder")
        folder_btn.setStyleSheet("padding: 6px 10px;")
        folder_btn.clicked.connect(lambda: self.context_action.emit(self.game.game_id, "open_folder"))
        btn_row.addWidget(play_btn)
        btn_row.addWidget(folder_btn)
        btn_row.addStretch(1)
        sheet_layout.addLayout(btn_row)
        sheet_layout.addStretch(1)
        self.overlay_sheet.setFixedHeight(int(self.minimumHeight() * 0.35))
        self.overlay_sheet.hide()
        layout.addWidget(self.overlay_sheet)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.game.game_id)
        super().mousePressEvent(event)
    
    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)

        a_play = menu.addAction("Play")
        a_add = menu.addAction("Add to collection…")
        menu.addSeparator()
        a_open_folder = menu.addAction("Open shortcut folder")
        a_open_file = menu.addAction("Open shortcut file")
        menu.addSeparator()
        a_rename = menu.addAction("Rename display name…")
        a_remove = menu.addAction("Remove from library…")

        chosen = menu.exec(event.globalPos())
        if not chosen:
            return

        if chosen == a_play:
            self.play_clicked.emit(self.game.game_id)
        elif chosen == a_add:
            self.context_action.emit(self.game.game_id, "add_to_collection")
        elif chosen == a_open_folder:
            self.context_action.emit(self.game.game_id, "open_folder")
        elif chosen == a_open_file:
            self.context_action.emit(self.game.game_id, "open_file")
        elif chosen == a_rename:
            self.context_action.emit(self.game.game_id, "rename")
        elif chosen == a_remove:
            self.context_action.emit(self.game.game_id, "remove")

    def enterEvent(self, event) -> None:
        # Apply ambient color tint to overlay
        self._apply_ambient_overlay()
        self.overlay_sheet.setVisible(True)
        self.overlay_anim.stop()
        self.overlay_anim.setDirection(QPropertyAnimation.Forward)
        self.overlay_anim.start()
        # Elevate shadow on hover for "lift" effect
        if hasattr(self, '_shadow_effect') and self._shadow_effect:
            theme = self._theme
            self._shadow_effect.setBlurRadius(20)
            self._shadow_effect.setOffset(0, 4)
            self._shadow_effect.setColor(QColor(theme.shadow.red(), theme.shadow.green(), theme.shadow.blue(), theme.elevation_mid))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.overlay_anim.stop()
        self.overlay_anim.setDirection(QPropertyAnimation.Backward)
        self.overlay_anim.start()
        # Reset shadow to normal state
        if hasattr(self, '_shadow_effect') and self._shadow_effect:
            theme = self._theme
            self._shadow_effect.setBlurRadius(12)
            self._shadow_effect.setOffset(0, 2)
            self._shadow_effect.setColor(QColor(theme.shadow.red(), theme.shadow.green(), theme.shadow.blue(), theme.elevation_low))
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        size = self.icon_frame.size()
        if size == self._last_icon_size:
            return
        self._last_icon_size = size
        if self._icon_update_scheduled:
            return
        self._icon_update_scheduled = True
        QTimer.singleShot(0, self._refresh_icon_pixmap)

    def _refresh_icon_pixmap(self) -> None:
        # Break potential resize->setPixmap->resize recursion by updating after the event loop returns.
        self._icon_update_scheduled = False
        self._set_icon_pixmap(self.icon_frame.height())

    def _set_icon_pixmap(self, target_height: int) -> None:
        target = self.icon_frame.size()
        target_width = target.width()
        target_size = max(96, target.height(), target_width, target_height)
        best_path = best_icon_path(self.game)
        pm = pixmap_for_game(self.game, target_size)
        if pm.isNull():
            if self.game.game_id not in _icon_failures:
                _icon_failures.add(self.game.game_id)
                _log.error("icon_null %s", kv(game_id=self.game.game_id, path=best_path, target_h=target_height))
            self._set_placeholder_pixmap()
            return

        if target.width() <= 0 or target.height() <= 0:
            if _icon_rate.allow(f"icon_invalid_size:{self.game.game_id}", interval_ms=1000):
                _log.warning("icon_target_invalid %s", kv(game_id=self.game.game_id, w=target.width(), h=target.height()))
            target = QSize(max(160, pm.width()), max(160, pm.height()))

        # One-scale rule: scale once from high-res cache
        scaled = pm if pm.size() == target else pm.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(scaled)
        if _icon_rate.allow(f"icon_ok:{self.game.game_id}", interval_ms=2000):
            _log.debug("icon_set %s", kv(game_id=self.game.game_id, path=best_path, target_w=target.width(), target_h=target.height(), pm_w=scaled.width(), pm_h=scaled.height()))

    def _on_overlay_anim_finished(self) -> None:
        if self.overlay_anim.direction() == QPropertyAnimation.Backward:
            self.overlay_sheet.hide()

    def _pick_rating(self) -> None:
        menu = QMenu(self)
        none_action = menu.addAction("Clear rating")
        actions = {none_action: None}
        for i in range(1, 11):
            act = menu.addAction(str(i))
            actions[act] = i
        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return
        rating = actions.get(chosen, None)
        self.game.rating = rating
        self.rating_changed.emit(self.game.game_id, rating)

    def _set_placeholder_pixmap(self) -> None:
        size = max(96, self.icon_frame.height() or 0, 160)
        pm = QPixmap(size, size)
        pm.fill(self._theme.surface_alt)
        self.icon_label.setPixmap(pm)

    def _extract_ambient_color(self) -> None:
        """Extract dominant color from icon for ambient accent effects."""
        pm = self.icon_label.pixmap()
        if pm and not pm.isNull():
            self._ambient_color = extract_dominant_color(pm)

    def fade_in(self, delay_ms: int = 0) -> None:
        """Animate card entrance with fade-in effect.

        Args:
            delay_ms: Delay before starting animation (for staggered effect)
        """
        # Start invisible
        self._card_opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._card_opacity)
        self._card_opacity.setOpacity(0.0)

        # Create fade animation
        self._fade_anim = QPropertyAnimation(self._card_opacity, b"opacity", self)
        self._fade_anim.setDuration(self._theme.anim_normal)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Restore shadow effect after fade completes
        def restore_shadow():
            if hasattr(self, '_shadow_effect'):
                self.setGraphicsEffect(self._shadow_effect)

        self._fade_anim.finished.connect(restore_shadow)

        # Start with delay
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, self._fade_anim.start)
        else:
            self._fade_anim.start()

    def _apply_ambient_overlay(self) -> None:
        """Apply ambient color tint to overlay sheet on hover."""
        theme = self._theme
        if self._ambient_color and self._ambient_color.isValid():
            # Blend ambient color with surface for subtle tint
            r = (self._ambient_color.red() + theme.surface_alt.red() * 2) // 3
            g = (self._ambient_color.green() + theme.surface_alt.green() * 2) // 3
            b = (self._ambient_color.blue() + theme.surface_alt.blue() * 2) // 3
            self.overlay_sheet.setStyleSheet(
                f"QFrame {{ background: rgba({r},{g},{b},215); border-radius: {theme.radius_md}px; }}"
            )
        else:
            self.overlay_sheet.setStyleSheet(
                f"QFrame {{ background: rgba({theme.surface_alt.red()},{theme.surface_alt.green()},{theme.surface_alt.blue()},204); border-radius: {theme.radius_md}px; }}"
            )


class GameGrid(QWidget):
    game_selected = Signal(str)   # game_id
    game_play = Signal(str)       # game_id
    context_action = Signal(str, str)  # (game_id, action)
    status_filter_requested = Signal(str)
    updates_requested = Signal(str)
    rating_changed = Signal(str, object)
    tag_filter_requested = Signal(str)
    scan_requested = Signal()  # emitted when user clicks scan from empty state

    def __init__(self) -> None:
        super().__init__()
        self._focused_index: int = -1  # keyboard navigation index

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
                card = GameCard(g, view_mode=self._view_mode, parent=self.container, type_scale=self._type_scale, chip_level=chip_level)
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
