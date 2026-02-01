"""Batch operations toolbar for multi-select actions."""
from __future__ import annotations
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QMenu, QGraphicsOpacityEffect
)
from PySide6.QtGui import QColor

from app.ui.theme import current_theme


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

        # Toolbar styling
        self.setStyleSheet(
            f"QWidget {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_lg}px; "
            f"}} "
        )
        self.setMinimumHeight(50)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        # Selection count label
        self._count_label = QLabel("0 selected")
        self._count_label.setStyleSheet(
            f"color: {theme.text.name()}; "
            f"font-size: 13px; "
            f"font-weight: 600; "
            f"background: transparent; "
            f"border: none;"
        )
        layout.addWidget(self._count_label)

        layout.addSpacing(8)

        # Action buttons
        btn_style = (
            f"QPushButton {{ "
            f"background: {theme.chip_bg.name(QColor.HexArgb)}; "
            f"color: {theme.text.name()}; "
            f"border: 1px solid {theme.chip_border.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_sm}px; "
            f"padding: 6px 12px; "
            f"font-size: 12px; "
            f"}} "
            f"QPushButton:hover {{ "
            f"background: {theme.chip_bg.lighter(110).name(QColor.HexArgb)}; "
            f"border-color: {theme.focus.name(QColor.HexArgb)}; "
            f"}} "
            f"QPushButton:pressed {{ "
            f"background: {theme.chip_bg.darker(105).name(QColor.HexArgb)}; "
            f"}}"
        )

        # Set Status button with dropdown
        self._status_btn = QPushButton("Set Status")
        self._status_btn.setStyleSheet(btn_style)
        self._status_btn.setCursor(Qt.PointingHandCursor)
        status_menu = QMenu(self)
        for status in ["backlog", "playing", "finished", "dropped"]:
            action = status_menu.addAction(status.capitalize())
            action.triggered.connect(lambda checked, s=status: self._emit_status(s))
        self._status_btn.setMenu(status_menu)
        layout.addWidget(self._status_btn)

        # Add Tag button
        self._tag_btn = QPushButton("Add Tag")
        self._tag_btn.setStyleSheet(btn_style)
        self._tag_btn.setCursor(Qt.PointingHandCursor)
        self._tag_btn.clicked.connect(self._on_add_tag)
        layout.addWidget(self._tag_btn)

        # Add to Collection button
        self._collection_btn = QPushButton("Add to Collection")
        self._collection_btn.setStyleSheet(btn_style)
        self._collection_btn.setCursor(Qt.PointingHandCursor)
        self._collection_btn.clicked.connect(lambda: self.add_to_collection_requested.emit(self._selected_ids))
        layout.addWidget(self._collection_btn)

        layout.addStretch(1)

        # Select All / Clear buttons
        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setStyleSheet(btn_style)
        self._select_all_btn.setCursor(Qt.PointingHandCursor)
        self._select_all_btn.clicked.connect(self.select_all_clicked.emit)
        layout.addWidget(self._select_all_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setStyleSheet(btn_style)
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.clicked.connect(self.clear_selection_clicked.emit)
        layout.addWidget(self._clear_btn)

        layout.addSpacing(8)

        # Exit button (styled as accent)
        exit_style = (
            f"QPushButton {{ "
            f"background: {theme.accent.name()}; "
            f"color: {theme.bg.name()}; "
            f"border: none; "
            f"border-radius: {theme.radius_sm}px; "
            f"padding: 6px 16px; "
            f"font-size: 12px; "
            f"font-weight: 600; "
            f"}} "
            f"QPushButton:hover {{ "
            f"background: {theme.accent.lighter(110).name()}; "
            f"}}"
        )
        self._exit_btn = QPushButton("Done")
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
        self._count_label.setText(f"{self._selected_count} selected")

        # Enable/disable buttons based on selection
        has_selection = self._selected_count > 0
        self._status_btn.setEnabled(has_selection)
        self._tag_btn.setEnabled(has_selection)
        self._collection_btn.setEnabled(has_selection)

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
