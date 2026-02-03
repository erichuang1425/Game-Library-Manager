"""
GameCard widget for displaying individual games.

Provides an interactive card with:
- Game icon with ambient color extraction
- Status badges and metadata chips
- Hover overlay with actions
- Multi-select support
- Rating system
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer, QEasingCurve, QPropertyAnimation, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QSizePolicy, QMenu,
    QGraphicsOpacityEffect, QStackedLayout, QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QCursor, QColor, QPixmap

from app.models import Game
from app.services import pixmap_for_game, parse_version, compare_versions, best_icon_path, extract_dominant_color
from app.services.version_parser import CompareResult
from app.ui.theme import current_theme, card_style, chip_style, is_reduced_motion
from app.logging_utils import get_logger, kv, RateLimiter

from .display_utils import status_label, stars, relative_time

_log = get_logger("ui.game_card")
_icon_rate = RateLimiter()
_icon_failures: set[str] = set()


class GameCard(QFrame):
    """Interactive game card widget with hover overlay and actions."""

    clicked = Signal(str)        # game_id
    play_clicked = Signal(str)   # game_id
    context_action = Signal(str, str)  # (game_id, action)
    status_clicked = Signal(str)       # status value
    updates_clicked = Signal(str)      # game_id
    rating_changed = Signal(str, object)  # game_id, rating or None
    tag_clicked = Signal(str)          # tag text
    selection_toggled = Signal(str, bool)  # game_id, is_selected

    def __init__(
        self,
        game: Game,
        view_mode: str = "comfortable",
        parent: Optional[QWidget] = None,
        type_scale: str = "normal",
        chip_level: str = "medium",
        multi_select_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.type_scale = type_scale
        self.chip_level = chip_level
        self._icon_update_scheduled = False
        self._last_icon_size = QSize()
        self._selected = False
        self._multi_select_mode = multi_select_mode
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

        # Build the card UI
        self._build_icon_area(layout, theme, view_mode, game)
        self._build_title(layout, theme, view_mode, game)
        self._build_overlay_sheet(layout, theme, game)

    def _build_icon_area(self, layout: QVBoxLayout, theme, view_mode: str, game: Game) -> None:
        """Build the icon/image area of the card."""
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
        sw.setSpacing(4)

        # Selection checkbox (visible in multi-select mode)
        self._select_checkbox = QLabel("☐")
        self._select_checkbox.setFixedSize(22, 22)
        self._select_checkbox.setAlignment(Qt.AlignCenter)
        self._select_checkbox.setStyleSheet(
            f"background: rgba(0,0,0,0.5); "
            f"color: white; "
            f"border-radius: 4px; "
            f"font-size: 14px; "
            f"font-weight: bold;"
        )
        self._select_checkbox.setToolTip("Click to select")
        self._select_checkbox.hide()  # Hidden by default, shown in multi-select mode
        sw.addWidget(self._select_checkbox, 0, Qt.AlignLeft | Qt.AlignTop)

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
        status_badge.setToolTip(status_label(game.status))
        sw.addWidget(status_badge, 0, Qt.AlignLeft | Qt.AlignTop)
        sw.addStretch(1)
        base_layout.addWidget(status_overlay)

        icon_layout.addWidget(base)
        layout.addWidget(self.icon_frame)

    def _build_title(self, layout: QVBoxLayout, theme, view_mode: str, game: Game) -> None:
        """Build the title row."""
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

    def _build_overlay_sheet(self, layout: QVBoxLayout, theme, game: Game) -> None:
        """Build the hover overlay bottom sheet."""
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

        # Overlay title
        overlay_title = QLabel()
        overlay_title.setWordWrap(False)
        overlay_title.setToolTip(game.title)
        overlay_title.setStyleSheet(f"font-weight:650; color:{theme.text.name()};")
        ot = overlay_title.fontMetrics()
        overlay_title.setText(ot.elidedText(game.title, Qt.ElideRight, 220))
        sheet_layout.addWidget(overlay_title)

        # Metadata chips row
        self._build_metadata_chips(sheet_layout, theme, game)

        # Tags row
        self._build_tags_row(sheet_layout, theme, game)

        # Quick action buttons
        self._build_action_buttons(sheet_layout, game)

        sheet_layout.addStretch(1)
        self.overlay_sheet.setFixedHeight(int(self.minimumHeight() * 0.35))
        self.overlay_sheet.hide()
        layout.addWidget(self.overlay_sheet)

    def _build_metadata_chips(self, sheet_layout: QVBoxLayout, theme, game: Game) -> None:
        """Build the metadata chips row."""
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

        meta.addWidget(chip_btn(status_label(game.status), theme.chip_bg, "Filter by status",
                                lambda: self.status_clicked.emit(game.status)))
        if self.chip_level != "narrow":
            meta.addWidget(chip_btn(stype, theme.chip_bg.lighter(108), "Shortcut type"))

        scale = {"small": 0.9, "normal": 1.0, "large": 1.1}.get(self.type_scale, 1.0)
        rating_text = stars(game.rating)
        if self.chip_level == "wide":
            rating_btn = chip_btn(rating_text, theme.accent_alt.lighter(140), "Click to set rating")
            rating_btn.clicked.connect(lambda: self._pick_rating())
            meta.addWidget(rating_btn)

        # Last played badge
        last_played_text = relative_time(game.last_played)
        if last_played_text and self.chip_level != "narrow":
            last_played_lbl = QLabel(f"⏱ {last_played_text}")
            last_played_lbl.setStyleSheet(
                f"color: {theme.text_muted.name()}; "
                f"font-size: 10px; "
                f"padding: 2px 6px; "
                f"background: transparent;"
            )
            last_played_lbl.setToolTip(f"Last played: {game.last_played.strftime('%Y-%m-%d %H:%M') if game.last_played else 'Never'}")
            meta.addWidget(last_played_lbl)

        # Update chip if applicable
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

    def _build_tags_row(self, sheet_layout: QVBoxLayout, theme, game: Game) -> None:
        """Build the tags row."""
        tags = game.tags or []
        tag_row = QHBoxLayout()
        tag_row.setSpacing(4)
        scale = {"small": 0.9, "normal": 1.0, "large": 1.1}.get(self.type_scale, 1.0)

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

    def _build_action_buttons(self, sheet_layout: QVBoxLayout, game: Game) -> None:
        """Build the quick action buttons."""
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

    # ---- Event handlers ----
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            # In multi-select mode or with Ctrl held, toggle selection
            if self._multi_select_mode or event.modifiers() & Qt.ControlModifier:
                self.toggle_selection()
            else:
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

    # ---- Multi-select methods ----
    def set_multi_select_mode(self, enabled: bool) -> None:
        """Enable or disable multi-select mode."""
        self._multi_select_mode = enabled
        if enabled:
            self._select_checkbox.show()
            self._update_checkbox_visual()
        else:
            self._select_checkbox.hide()
            if self._selected:
                self.set_selected(False)

    def set_selected(self, selected: bool) -> None:
        """Set the selection state of this card."""
        if self._selected != selected:
            self._selected = selected
            self._update_selection_visual()
            self._update_checkbox_visual()

    def toggle_selection(self) -> None:
        """Toggle the selection state."""
        self._selected = not self._selected
        self._update_selection_visual()
        self._update_checkbox_visual()
        self.selection_toggled.emit(self.game.game_id, self._selected)

    def is_selected(self) -> bool:
        """Return current selection state."""
        return self._selected

    def _update_checkbox_visual(self) -> None:
        """Update the checkbox appearance based on selection state."""
        theme = self._theme
        if self._selected:
            self._select_checkbox.setText("☑")
            self._select_checkbox.setStyleSheet(
                f"background: {theme.accent.name()}; "
                f"color: white; "
                f"border-radius: 4px; "
                f"font-size: 14px; "
                f"font-weight: bold;"
            )
        else:
            self._select_checkbox.setText("☐")
            self._select_checkbox.setStyleSheet(
                f"background: rgba(0,0,0,0.5); "
                f"color: white; "
                f"border-radius: 4px; "
                f"font-size: 14px; "
                f"font-weight: bold;"
            )

    def _update_selection_visual(self) -> None:
        """Update card border to show selection state."""
        theme = self._theme
        if self._selected:
            self.setStyleSheet(
                f"QFrame {{ {card_style(theme)} border: 2px solid {theme.accent.name()}; }}"
                f"QFrame:hover {{ {card_style(theme, hover=True)} border: 2px solid {theme.accent.name()}; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ {card_style(theme)} }}"
                f"QFrame:hover {{ {card_style(theme, hover=True)} }}"
            )

    # ---- Icon and rendering methods ----
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

    def fade_in(self, delay_ms: int = 0) -> None:
        """Animate card entrance with fade-in effect.

        Args:
            delay_ms: Delay before starting animation (for staggered effect)
        """
        # Skip animation if reduced motion is enabled
        if is_reduced_motion():
            return

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
