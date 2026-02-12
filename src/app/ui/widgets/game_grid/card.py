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
from app.ui.theme import current_theme, card_style, chip_style, is_reduced_motion, status_color
from app.ui.icons import AppIcons
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

        # Refined card styling — subtle border, clean background
        self.setStyleSheet(
            f"QFrame {{ {card_style(theme)} }}"
            f"QFrame:hover {{ {card_style(theme, hover=True)} }}"
        )

        # Soft drop shadow for depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(theme.shadow.red(), theme.shadow.green(), theme.shadow.blue(), theme.elevation_low))
        self.setGraphicsEffect(shadow)
        self._shadow_effect = shadow

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        assert self.parent() is not None, "GameCard requires a parent; prevents floating windows."

        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(4 if view_mode == "compact" else 8)
        self.setMinimumHeight(220 if view_mode == "comfortable" else 160)

        # Build the card UI: icon, title, always-visible metadata, hover actions
        self._build_icon_area(layout, theme, view_mode, game)
        self._build_info_section(layout, theme, view_mode, game)
        self._build_overlay_sheet(layout, theme, game)

    def _build_icon_area(self, layout: QVBoxLayout, theme, view_mode: str, game: Game) -> None:
        """Build the icon/image area with status bar and update badge."""
        # Container for icon + status bar
        icon_container = QVBoxLayout()
        icon_container.setContentsMargins(0, 0, 0, 0)
        icon_container.setSpacing(0)

        self.icon_frame = QFrame()
        self.icon_frame.setStyleSheet(
            f"QFrame {{ background:{theme.surface_alt.name(QColor.HexArgb)}; "
            f"border-radius:{theme.radius_md}px; border: none; overflow: hidden; }}"
        )
        icon_ratio = 0.65 if view_mode == "comfortable" else 0.55
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
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        self._set_icon_pixmap(icon_height)
        base_layout.addWidget(self.icon_label)

        self._ambient_color: QColor | None = None
        self._extract_ambient_color()

        # Overlay for selection checkbox + update badge
        badge_overlay = QWidget()
        badge_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        sw = QHBoxLayout(badge_overlay)
        sw.setContentsMargins(8, 8, 8, 8)
        sw.setSpacing(4)

        # Selection checkbox (multi-select mode)
        self._select_checkbox = QLabel("\u2610")
        self._select_checkbox.setFixedSize(24, 24)
        self._select_checkbox.setAlignment(Qt.AlignCenter)
        self._select_checkbox.setStyleSheet(
            f"background: rgba(0,0,0,0.55); color: white; "
            f"border-radius: 6px; font-size: 14px; font-weight: bold;"
        )
        self._select_checkbox.setToolTip("Click to select")
        self._select_checkbox.hide()
        sw.addWidget(self._select_checkbox, 0, Qt.AlignLeft | Qt.AlignTop)

        sw.addStretch(1)

        # Update indicator badge (top-right, accent-colored pill)
        inst_vi = parse_version(game.installed_version_raw) if game.installed_version_raw else None
        src_vi = parse_version(game.source_version_raw) if game.source_version_raw else None
        cmp = compare_versions(inst_vi, src_vi)
        if game.source_url and cmp in (CompareResult.OLDER, CompareResult.UNKNOWN):
            update_badge = QLabel(AppIcons.STS_UPDATE)
            update_badge.setFixedSize(24, 24)
            update_badge.setAlignment(Qt.AlignCenter)
            update_badge.setStyleSheet(
                f"background: {theme.accent.name()}; color: {theme.bg.name()}; "
                f"border-radius: 12px; font-size: 12px; font-weight: bold; border: none;"
            )
            update_badge.setToolTip("Update available" if cmp == CompareResult.OLDER else "Version unknown")
            sw.addWidget(update_badge, 0, Qt.AlignRight | Qt.AlignTop)

        base_layout.addWidget(badge_overlay)
        icon_layout.addWidget(base)
        icon_container.addWidget(self.icon_frame)

        # Status bar — colored strip at bottom of icon area
        sc = status_color(theme, game.status)
        self._status_bar = QFrame()
        self._status_bar.setFixedHeight(3)
        self._status_bar.setStyleSheet(
            f"background: {sc.name()}; border: none; "
            f"border-radius: 0px;"
        )
        self._status_bar.setToolTip(status_label(game.status))
        icon_container.addWidget(self._status_bar)

        layout.addLayout(icon_container)

    def _build_info_section(self, layout: QVBoxLayout, theme, view_mode: str, game: Game) -> None:
        """Build the always-visible info section: title, rating + time, tags."""
        scale = {"small": 0.9, "normal": 1.0, "large": 1.1}.get(self.type_scale, 1.0)

        # Title (bold, 2-line max)
        title = QLabel()
        title_size = int((15 if view_mode == "comfortable" else 13) * scale)
        fm = title.fontMetrics()
        title.setWordWrap(True)
        title.setMaximumHeight(fm.lineSpacing() * 2 + 4)
        title.setText(game.title)
        title.setToolTip(game.title)
        title.setStyleSheet(
            f"font-size: {title_size}px; font-weight: 600; "
            f"color: {theme.text.name()}; background: transparent; border: none;"
        )
        layout.addWidget(title)

        # Rating + last played (always visible, muted)
        meta_size = int(11 * scale)
        rating_text = stars(game.rating)
        time_text = relative_time(game.last_played)

        meta_parts = [rating_text]
        if time_text and view_mode == "comfortable":
            meta_parts.append(time_text)
        meta_line = "  \u00B7  ".join(meta_parts)

        meta_label = QLabel(meta_line)
        meta_label.setStyleSheet(
            f"font-size: {meta_size}px; color: {theme.text_muted.name()}; "
            f"background: transparent; border: none;"
        )
        meta_label.setToolTip(
            f"Rating: {game.rating or 'unrated'}"
            + (f"\nLast played: {time_text}" if time_text else "")
        )
        layout.addWidget(meta_label)

        # Tag chips (max 2-3, always visible in comfortable mode)
        if view_mode == "comfortable":
            tags = game.tags or []
            if tags:
                tag_row = QHBoxLayout()
                tag_row.setContentsMargins(0, 4, 0, 0)
                tag_row.setSpacing(4)
                max_tags = 2 if self.chip_level == "narrow" else 3
                for t in tags[:max_tags]:
                    tag_lbl = QLabel(t)
                    tag_lbl.setStyleSheet(
                        f"font-size: {int(10 * scale)}px; "
                        f"color: {theme.text_muted.name()}; "
                        f"background: {theme.chip_bg.name(QColor.HexArgb)}; "
                        f"border-radius: {theme.radius_sm - 2}px; "
                        f"padding: 2px 8px; border: none;"
                    )
                    tag_lbl.setMaximumWidth(90)
                    tag_row.addWidget(tag_lbl)
                if len(tags) > max_tags:
                    more = QLabel(f"+{len(tags) - max_tags}")
                    more.setStyleSheet(
                        f"font-size: {int(10 * scale)}px; color: {theme.text_muted.name()}; "
                        f"background: transparent; border: none;"
                    )
                    tag_row.addWidget(more)
                tag_row.addStretch(1)
                layout.addLayout(tag_row)

    def _build_overlay_sheet(self, layout: QVBoxLayout, theme, game: Game) -> None:
        """Build the hover overlay — action buttons only (metadata is always visible)."""
        self.overlay_sheet = QFrame()
        sr = theme.surface_raised or theme.surface_alt
        self.overlay_sheet.setStyleSheet(
            f"QFrame {{ background: rgba({sr.red()},{sr.green()},{sr.blue()},230); "
            f"border-radius: {theme.radius_sm}px; border: none; }}"
        )
        self.overlay_opacity = QGraphicsOpacityEffect(self.overlay_sheet)
        self.overlay_sheet.setGraphicsEffect(self.overlay_opacity)
        self.overlay_opacity.setOpacity(0.0)
        self.overlay_anim = QPropertyAnimation(self.overlay_opacity, b"opacity", self)
        self.overlay_anim.setDuration(120)
        self.overlay_anim.setStartValue(0.0)
        self.overlay_anim.setEndValue(1.0)
        self.overlay_anim.finished.connect(self._on_overlay_anim_finished)

        sheet_layout = QHBoxLayout(self.overlay_sheet)
        sheet_layout.setContentsMargins(8, 8, 8, 8)
        sheet_layout.setSpacing(8)

        # Action buttons only
        play_btn = QPushButton(f"{AppIcons.ACT_PLAY} Play")
        play_btn.setCursor(Qt.PointingHandCursor)
        play_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.accent.name()}; color: {theme.bg.name()}; "
            f"border: none; border-radius: {theme.radius_sm}px; padding: 4px 12px; "
            f"font-weight: 600; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {theme.accent.lighter(110).name()}; }}"
        )
        play_btn.clicked.connect(lambda: self.play_clicked.emit(self.game.game_id))
        sheet_layout.addWidget(play_btn)

        folder_btn = QPushButton(AppIcons.ACT_FOLDER)
        folder_btn.setCursor(Qt.PointingHandCursor)
        folder_btn.setToolTip("Open folder")
        folder_btn.setFixedSize(28, 28)
        folder_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {theme.text_muted.name()}; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_sm}px; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {theme.text.name()}; "
            f"background: {theme.surface_alt.name(QColor.HexArgb)}; }}"
        )
        folder_btn.clicked.connect(lambda: self.context_action.emit(self.game.game_id, "open_folder"))
        sheet_layout.addWidget(folder_btn)

        more_btn = QPushButton(AppIcons.UI_DOTS)
        more_btn.setCursor(Qt.PointingHandCursor)
        more_btn.setToolTip("More actions")
        more_btn.setFixedSize(28, 28)
        more_btn.setStyleSheet(folder_btn.styleSheet())
        more_btn.clicked.connect(lambda: self._show_context_menu())
        sheet_layout.addWidget(more_btn)

        sheet_layout.addStretch(1)

        self.overlay_sheet.setFixedHeight(40)
        self.overlay_sheet.hide()
        layout.addWidget(self.overlay_sheet)

    def _show_context_menu(self) -> None:
        """Show context menu from the more button."""
        menu = QMenu(self)
        menu.addAction("Add to collection\u2026").triggered.connect(
            lambda: self.context_action.emit(self.game.game_id, "add_to_collection"))
        menu.addSeparator()
        menu.addAction("Open shortcut folder").triggered.connect(
            lambda: self.context_action.emit(self.game.game_id, "open_folder"))
        menu.addAction("Open shortcut file").triggered.connect(
            lambda: self.context_action.emit(self.game.game_id, "open_file"))
        menu.addSeparator()
        menu.addAction("Rename\u2026").triggered.connect(
            lambda: self.context_action.emit(self.game.game_id, "rename"))
        menu.addAction("Remove\u2026").triggered.connect(
            lambda: self.context_action.emit(self.game.game_id, "remove"))
        menu.exec(QCursor.pos())

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
        self.overlay_sheet.setVisible(True)
        self.overlay_anim.stop()
        self.overlay_anim.setDirection(QPropertyAnimation.Forward)
        self.overlay_anim.start()
        theme = self._theme
        # Elevate shadow for "lift" effect
        if hasattr(self, '_shadow_effect') and self._shadow_effect:
            self._shadow_effect.setBlurRadius(28)
            self._shadow_effect.setOffset(0, 8)
            self._shadow_effect.setColor(QColor(
                theme.shadow.red(), theme.shadow.green(), theme.shadow.blue(),
                theme.elevation_mid,
            ))
        # Subtle upward lift via margin animation
        if not is_reduced_motion():
            self._hover_margin_anim = QPropertyAnimation(self, b"contentsMargins_top", self)
            curr = self.contentsMargins()
            self.setContentsMargins(curr.left(), max(0, curr.top() - 2), curr.right(), curr.bottom() + 2)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.overlay_anim.stop()
        self.overlay_anim.setDirection(QPropertyAnimation.Backward)
        self.overlay_anim.start()
        theme = self._theme
        # Reset shadow
        if hasattr(self, '_shadow_effect') and self._shadow_effect:
            self._shadow_effect.setBlurRadius(16)
            self._shadow_effect.setOffset(0, 3)
            self._shadow_effect.setColor(QColor(
                theme.shadow.red(), theme.shadow.green(), theme.shadow.blue(),
                theme.elevation_low,
            ))
        # Reset lift
        if not is_reduced_motion():
            pad = theme.spacing_md if self.view_mode == "comfortable" else theme.spacing_sm
            self.setContentsMargins(pad, pad, pad, pad)
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
