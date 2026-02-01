"""Filter chips bar for displaying and clearing active filters."""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QScrollArea, QFrame
)
from PySide6.QtGui import QColor

from app.ui.theme import current_theme, filter_chip_style


@dataclass
class FilterChip:
    """Represents an active filter."""
    key: str  # unique identifier (e.g., "status", "tag", "confidence")
    label: str  # display text (e.g., "Status: Playing")
    value: Any  # the filter value


class FilterChipWidget(QPushButton):
    """A single filter chip with remove button."""

    removed = Signal(str)  # emits the filter key when removed

    def __init__(self, chip: FilterChip, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._chip = chip
        theme = current_theme()

        # Style as active chip with close indicator
        self.setText(f"{chip.label} ×")
        self.setStyleSheet(
            f"QPushButton {{ {filter_chip_style(theme, active=True)} }} "
            f"QPushButton:hover {{ background: {theme.accent.lighter(115).name()}; }}"
        )
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Click to remove filter: {chip.label}")
        self.clicked.connect(lambda: self.removed.emit(chip.key))

    @property
    def filter_key(self) -> str:
        return self._chip.key


class FilterChipsBar(QWidget):
    """A horizontal bar displaying active filters as chips."""

    filter_removed = Signal(str)  # emits filter key when a filter is removed
    clear_all_clicked = Signal()  # emitted when "Clear all" is clicked

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._chips: Dict[str, FilterChipWidget] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(6)

        # Label
        self._label = QLabel("Filters:")
        theme = current_theme()
        self._label.setStyleSheet(f"color: {theme.text_muted.name()}; font-size: 12px;")
        layout.addWidget(self._label)

        # Scroll area for chips (in case there are many)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setMaximumHeight(36)
        self._scroll.setStyleSheet("background: transparent;")

        self._chips_container = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_container)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(6)
        self._chips_layout.addStretch(1)

        self._scroll.setWidget(self._chips_container)
        layout.addWidget(self._scroll, 1)

        # Clear all button
        self._clear_btn = QPushButton("Clear all")
        self._clear_btn.setStyleSheet(
            f"QPushButton {{ "
            f"color: {theme.accent.name()}; "
            f"background: transparent; "
            f"border: none; "
            f"font-size: 12px; "
            f"font-weight: 500; "
            f"padding: 4px 8px; "
            f"}} "
            f"QPushButton:hover {{ text-decoration: underline; }}"
        )
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.clicked.connect(self.clear_all_clicked.emit)
        layout.addWidget(self._clear_btn)

        # Start hidden until filters are added
        self.hide()

    def set_filters(self, filters: List[FilterChip]) -> None:
        """Update the displayed filters.

        Args:
            filters: List of active filters to display
        """
        # Clear existing chips
        while self._chips_layout.count() > 1:  # Keep the stretch
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chips.clear()

        # Add new chips
        for chip in filters:
            widget = FilterChipWidget(chip)
            widget.removed.connect(self._on_chip_removed)
            self._chips[chip.key] = widget
            self._chips_layout.insertWidget(self._chips_layout.count() - 1, widget)

        # Show/hide based on whether there are active filters
        if filters:
            self.show()
        else:
            self.hide()

    def add_filter(self, chip: FilterChip) -> None:
        """Add a single filter chip."""
        if chip.key in self._chips:
            # Update existing
            self.remove_filter(chip.key)

        widget = FilterChipWidget(chip)
        widget.removed.connect(self._on_chip_removed)
        self._chips[chip.key] = widget
        self._chips_layout.insertWidget(self._chips_layout.count() - 1, widget)
        self.show()

    def remove_filter(self, key: str) -> None:
        """Remove a filter by key."""
        if key in self._chips:
            widget = self._chips.pop(key)
            widget.deleteLater()

        if not self._chips:
            self.hide()

    def clear_all(self) -> None:
        """Remove all filter chips."""
        for key in list(self._chips.keys()):
            self.remove_filter(key)

    def has_filters(self) -> bool:
        """Check if any filters are active."""
        return bool(self._chips)

    def _on_chip_removed(self, key: str) -> None:
        """Handle chip removal."""
        self.remove_filter(key)
        self.filter_removed.emit(key)


def build_filter_chips(
    status: str = "all",
    confidence: str = "all",
    type_filter: str = "all",
    tag: Optional[str] = None,
    quick_filter: str = "all",
    search_query: str = "",
) -> List[FilterChip]:
    """Build a list of FilterChip objects from current filter state.

    Args:
        status: Current status filter
        confidence: Current confidence filter
        type_filter: Current type filter
        tag: Current tag filter
        quick_filter: Current quick filter
        search_query: Current search query

    Returns:
        List of active FilterChip objects
    """
    chips = []

    if status and status != "all":
        chips.append(FilterChip(
            key="status",
            label=f"Status: {status.capitalize()}",
            value=status
        ))

    if confidence and confidence != "all":
        chips.append(FilterChip(
            key="confidence",
            label=f"Confidence: {confidence.capitalize()}",
            value=confidence
        ))

    if type_filter and type_filter != "all":
        chips.append(FilterChip(
            key="type",
            label=f"Type: {type_filter.upper()}",
            value=type_filter
        ))

    if tag:
        chips.append(FilterChip(
            key="tag",
            label=f"Tag: {tag}",
            value=tag
        ))

    if quick_filter and quick_filter not in ("all", ""):
        labels = {
            "missing": "Missing files",
            "updates": "Has updates",
            "source": "Has source URL",
        }
        chips.append(FilterChip(
            key="quick",
            label=labels.get(quick_filter, quick_filter.capitalize()),
            value=quick_filter
        ))

    if search_query:
        chips.append(FilterChip(
            key="search",
            label=f'Search: "{search_query[:20]}..."' if len(search_query) > 20 else f'Search: "{search_query}"',
            value=search_query
        ))

    return chips
