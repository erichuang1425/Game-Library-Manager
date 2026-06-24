"""Batch operations toolbar for multi-select actions."""
from __future__ import annotations
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QMenu, QGraphicsOpacityEffect,
    QFrame,
)
from PySide6.QtGui import QColor

from app.ui.theme import current_theme, ghost_btn_style
from app.ui.icons import AppIcons


class BatchToolbar(QWidget):
    """Floating toolbar for batch operations on selected games."""

    # Signals for batch operations
    set_status_requested = Signal(str, list)  # (status, game_ids)
    add_tag_requested = Signal(str, list)  # (tag, game_ids)
    add_to_collection_requested = Signal(list)  # game_ids
    remove_requested = Signal(list)  # game_ids
    select_all_clicked = Signal()
    clear_selection_clicked = Signal()
    exit_mode_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._selected_count = 0
        self._selected_ids: List[str] = []

        theme = current_theme()
        self._theme = theme
        ac = theme.accent
        self._accent_hex = ac.name()
        accent_rgb = f"{ac.red()},{ac.green()},{ac.blue()}"

        # Toolbar styling — a raised, accent-bordered floating surface so the
        # batch bar reads as a distinct, temporary mode over the grid.
        self.setStyleSheet(
            f"QWidget#batchToolbar {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border: 1px solid rgba({accent_rgb},90); "
            f"border-radius: {theme.radius_lg}px; "
            f"}} "
        )
        self.setObjectName("batchToolbar")
        self.setMinimumHeight(50)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            theme.spacing_md, theme.spacing_sm, theme.spacing_md, theme.spacing_sm
        )
        layout.setSpacing(theme.spacing_sm)

        # Selection count label — the number is emphasized in the accent color so
        # the current selection size is the first thing the eye lands on.
        self._count_label = QLabel()
        self._count_label.setTextFormat(Qt.RichText)
        self._count_label.setStyleSheet(
            f"color: {theme.text_muted.name()}; "
            f"font-size: 13px; font-weight: 600; "
            f"background: transparent; border: none;"
        )
        self._render_count()
        layout.addWidget(self._count_label)

        layout.addWidget(self._make_divider())

        # Action buttons — a clean neutral control that lifts to an accent
        # outline/tint on hover, matching the chip treatment used elsewhere.
        action_style = (
            f"QPushButton {{ "
            f"background: {theme.chip_bg.name(QColor.HexArgb)}; "
            f"color: {theme.text.name()}; "
            f"border: 1px solid {theme.chip_border.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; "
            f"padding: 7px 14px; "
            f"font-size: 12px; font-weight: 500; "
            f"}} "
            f"QPushButton::menu-indicator {{ width: 0px; }} "
            f"QPushButton:hover {{ "
            f"background: rgba({accent_rgb},22); "
            f"border-color: {ac.name()}; }} "
            f"QPushButton:pressed {{ background: rgba({accent_rgb},42); }} "
            f"QPushButton:disabled {{ "
            f"color: {theme.text_muted.name()}; "
            f"background: transparent; "
            f"border-color: {theme.outline.name(QColor.HexArgb)}; }}"
        )

        # Set Status button with dropdown (own chevron glyph; native indicator hidden)
        status_label = f"{AppIcons.STS_PLAYING}  Set Status  {AppIcons.UI_CHEVRON_DOWN}"
        self._status_btn = QPushButton(status_label)
        self._status_btn.setStyleSheet(action_style)
        self._status_btn.setCursor(Qt.PointingHandCursor)
        status_menu = QMenu(self)
        for status in ["backlog", "playing", "finished", "dropped"]:
            label = f"{AppIcons.status_icon(status)}  {status.capitalize()}"
            action = status_menu.addAction(label)
            action.triggered.connect(lambda checked, s=status: self._emit_status(s))
        self._status_btn.setMenu(status_menu)
        layout.addWidget(self._status_btn)

        # Add Tag button
        self._tag_btn = QPushButton(f"{AppIcons.UI_TAG}  Add Tag")
        self._tag_btn.setStyleSheet(action_style)
        self._tag_btn.setCursor(Qt.PointingHandCursor)
        self._tag_btn.clicked.connect(self._on_add_tag)
        layout.addWidget(self._tag_btn)

        # Add to Collection button
        self._collection_btn = QPushButton(
            f"{AppIcons.NAV_COLLECTION}  Add to Collection"
        )
        self._collection_btn.setStyleSheet(action_style)
        self._collection_btn.setCursor(Qt.PointingHandCursor)
        self._collection_btn.clicked.connect(lambda: self.add_to_collection_requested.emit(self._selected_ids))
        layout.addWidget(self._collection_btn)

        layout.addStretch(1)

        # Select All / Clear — subtle ghost controls; selection plumbing, not
        # primary actions, so they recede until hovered.
        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setStyleSheet(ghost_btn_style(theme))
        self._select_all_btn.setCursor(Qt.PointingHandCursor)
        self._select_all_btn.clicked.connect(self.select_all_clicked.emit)
        layout.addWidget(self._select_all_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setStyleSheet(ghost_btn_style(theme))
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.clicked.connect(self.clear_selection_clicked.emit)
        layout.addWidget(self._clear_btn)

        layout.addWidget(self._make_divider())

        # Exit button — the primary, filled-accent pill that closes batch mode.
        exit_style = (
            f"QPushButton {{ "
            f"background: {ac.name()}; "
            f"color: {theme.bg.name()}; "
            f"border: none; "
            f"border-radius: {theme.radius_pill}px; "
            f"padding: 7px 18px; "
            f"font-size: 12px; font-weight: 600; "
            f"}} "
            f"QPushButton:hover {{ background: {ac.lighter(112).name()}; }} "
            f"QPushButton:pressed {{ background: {ac.darker(110).name()}; }}"
        )
        self._exit_btn = QPushButton(f"{AppIcons.FB_SUCCESS}  Done")
        self._exit_btn.setStyleSheet(exit_style)
        self._exit_btn.setCursor(Qt.PointingHandCursor)
        self._exit_btn.clicked.connect(self.exit_mode_clicked.emit)
        layout.addWidget(self._exit_btn)

        # Opacity effect for animations
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(1.0)

        # Start hidden
        self.hide()

    def update_selection(self, game_ids: List[str]) -> None:
        """Update the selection count and stored IDs."""
        self._selected_ids = game_ids
        self._selected_count = len(game_ids)
        self._render_count()

        # Enable/disable buttons based on selection
        has_selection = self._selected_count > 0
        self._status_btn.setEnabled(has_selection)
        self._tag_btn.setEnabled(has_selection)
        self._collection_btn.setEnabled(has_selection)

    def _render_count(self) -> None:
        """Render the selection count with the number emphasized in the accent."""
        n = self._selected_count
        noun = "game" if n == 1 else "games"
        self._count_label.setText(
            f"<span style='color:{self._accent_hex}; font-weight:700;'>{n}</span> "
            f"{noun} selected"
        )

    def _make_divider(self) -> QFrame:
        """A slim vertical rule separating logical button groups."""
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFixedWidth(1)
        line.setFixedHeight(22)
        line.setStyleSheet(
            f"background: {self._theme.outline.name(QColor.HexArgb)}; border: none;"
        )
        return line

    def show_toolbar(self) -> None:
        """Show the toolbar with animation."""
        self.show()
        self._animate_opacity(0.0, 1.0)

    def hide_toolbar(self) -> None:
        """Hide the toolbar with animation."""
        anim = self._animate_opacity(1.0, 0.0)
        anim.finished.connect(self.hide)

    def _animate_opacity(self, start: float, end: float) -> QPropertyAnimation:
        """Animate the opacity of the toolbar."""
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(150)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        return anim

    def _emit_status(self, status: str) -> None:
        """Emit set status signal."""
        self.set_status_requested.emit(status, self._selected_ids)

    def _on_add_tag(self) -> None:
        """Handle add tag button click."""
        from PySide6.QtWidgets import QInputDialog
        tag, ok = QInputDialog.getText(self, "Add Tag", "Enter tag name:")
        if ok and tag.strip():
            self.add_tag_requested.emit(tag.strip(), self._selected_ids)
