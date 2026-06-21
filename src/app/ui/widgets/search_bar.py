"""Enhanced search bar with syntax parsing and recent searches."""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
import re

from PySide6.QtCore import Qt, Signal, QTimer, QEvent
from PySide6.QtWidgets import (
    QWidget, QLineEdit, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame
)
from PySide6.QtGui import QColor

from app.ui.theme import current_theme
from app.ui.icons import AppIcons


@dataclass
class ParsedSearch:
    """Represents a parsed search query with filters."""
    text: str = ""  # Plain text search
    status: Optional[str] = None
    tag: Optional[str] = None
    confidence: Optional[str] = None
    type_filter: Optional[str] = None
    rating_min: Optional[int] = None
    rating_max: Optional[int] = None
    has_source: Optional[bool] = None
    has_updates: Optional[bool] = None


class SearchParser:
    """Parses search syntax into structured filters.

    Supported syntax:
        status:playing - Filter by status
        tag:rpg - Filter by tag
        confidence:high - Filter by confidence
        type:lnk - Filter by shortcut type
        rating:>7 - Filter by minimum rating
        rating:<5 - Filter by maximum rating
        rating:7 - Filter by exact rating
        has:source - Has source URL
        has:updates - Has available updates
        Regular text - Title/notes search
    """

    FILTER_PATTERN = re.compile(
        r'(status|tag|confidence|type|rating|has):(\S+)',
        re.IGNORECASE
    )

    @classmethod
    def parse(cls, query: str) -> ParsedSearch:
        """Parse a search query into structured filters."""
        result = ParsedSearch()

        # Extract filter tokens
        remaining = query
        for match in cls.FILTER_PATTERN.finditer(query):
            filter_type = match.group(1).lower()
            value = match.group(2).lower()
            remaining = remaining.replace(match.group(0), "")

            if filter_type == "status":
                if value in ("backlog", "playing", "finished", "dropped"):
                    result.status = value
            elif filter_type == "tag":
                result.tag = value
            elif filter_type == "confidence":
                if value in ("high", "medium", "low"):
                    result.confidence = value
            elif filter_type == "type":
                if value in ("lnk", "url", "html"):
                    result.type_filter = value
            elif filter_type == "rating":
                if value.startswith(">"):
                    try:
                        result.rating_min = int(value[1:])
                    except ValueError:
                        pass
                elif value.startswith("<"):
                    try:
                        result.rating_max = int(value[1:])
                    except ValueError:
                        pass
                else:
                    try:
                        val = int(value)
                        result.rating_min = val
                        result.rating_max = val
                    except ValueError:
                        pass
            elif filter_type == "has":
                if value == "source":
                    result.has_source = True
                elif value == "updates":
                    result.has_updates = True

        # Remaining text is plain search
        result.text = " ".join(remaining.split()).strip()

        return result


class RecentSearches:
    """Manages recent search history."""

    def __init__(self, max_items: int = 10) -> None:
        self._searches: List[str] = []
        self._max_items = max_items

    def add(self, query: str) -> None:
        """Add a search to history."""
        query = query.strip()
        if not query:
            return
        # Remove if exists, add to front
        if query in self._searches:
            self._searches.remove(query)
        self._searches.insert(0, query)
        # Trim to max
        self._searches = self._searches[:self._max_items]

    def get_all(self) -> List[str]:
        """Get all recent searches."""
        return list(self._searches)

    def clear(self) -> None:
        """Clear all recent searches."""
        self._searches.clear()

    def load(self, searches: List[str]) -> None:
        """Load searches from storage."""
        self._searches = list(searches[:self._max_items])

    def save(self) -> List[str]:
        """Get searches for storage."""
        return list(self._searches)


class SearchSuggestionPopup(QFrame):
    """Dropdown popup showing search suggestions."""

    suggestion_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        theme = current_theme()
        self.setStyleSheet(
            f"QFrame {{ "
            f"background: {theme.surface.name(QColor.HexArgb)}; "
            f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; "
            f"}} "
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        # Recent searches section
        self._recent_header = QLabel("Recent Searches")
        self._recent_header.setStyleSheet(
            f"color: {theme.text_muted.name()}; "
            f"font-size: 11px; "
            f"font-weight: 600; "
            f"padding: 6px 8px 4px 8px; "
            f"background: transparent; "
            f"border: none;"
        )
        layout.addWidget(self._recent_header)

        self._list = QListWidget()
        self._list.setStyleSheet(
            f"QListWidget {{ "
            f"background: transparent; "
            f"border: none; "
            f"}} "
            f"QListWidget::item {{ "
            f"padding: 6px 8px; "
            f"color: {theme.text.name()}; "
            f"}} "
            f"QListWidget::item:hover {{ "
            f"background: {theme.chip_bg.name(QColor.HexArgb)}; "
            f"}} "
            f"QListWidget::item:selected {{ "
            f"background: {theme.accent.name()}; "
            f"color: {theme.bg.name()}; "
            f"}}"
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        # Syntax help section
        self._help_header = QLabel("Search Syntax")
        self._help_header.setStyleSheet(
            f"color: {theme.text_muted.name()}; "
            f"font-size: 11px; "
            f"font-weight: 600; "
            f"padding: 8px 8px 4px 8px; "
            f"background: transparent; "
            f"border: none;"
        )
        layout.addWidget(self._help_header)

        help_items = [
            ("status:playing", "Filter by status"),
            ("tag:rpg", "Filter by tag"),
            ("rating:>7", "Minimum rating"),
            ("has:source", "Has source URL"),
        ]
        self._help_list = QListWidget()
        self._help_list.setStyleSheet(self._list.styleSheet())
        self._help_list.setMaximumHeight(100)
        for syntax, desc in help_items:
            item = QListWidgetItem(f"{syntax}  —  {desc}")
            item.setData(Qt.UserRole, syntax)
            self._help_list.addItem(item)
        self._help_list.itemClicked.connect(self._on_help_clicked)
        layout.addWidget(self._help_list)

        self.setMinimumWidth(300)

    def update_recent(self, searches: List[str]) -> None:
        """Update the recent searches list."""
        self._list.clear()
        for search in searches:
            item = QListWidgetItem(search)
            item.setData(Qt.UserRole, search)
            self._list.addItem(item)

        self._recent_header.setVisible(bool(searches))
        self._list.setVisible(bool(searches))

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle recent search item click."""
        query = item.data(Qt.UserRole)
        if query:
            self.suggestion_selected.emit(query)
            self.hide()

    def _on_help_clicked(self, item: QListWidgetItem) -> None:
        """Handle syntax help item click."""
        syntax = item.data(Qt.UserRole)
        if syntax:
            self.suggestion_selected.emit(syntax + " ")
            self.hide()


class EnhancedSearchBar(QWidget):
    """Search bar with syntax parsing, suggestions, and recent searches."""

    search_triggered = Signal(ParsedSearch)  # Emits parsed search
    text_changed = Signal(str)  # Raw text changed

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._recent = RecentSearches()
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._emit_search)

        theme = current_theme()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Unified search field: a bordered container holding a leading magnifier
        # glyph and a borderless input, so the whole control reads as one element
        # and can light up its border with the accent color on focus.
        self._field = QFrame()
        self._field.setObjectName("searchField")
        field_layout = QHBoxLayout(self._field)
        field_layout.setContentsMargins(theme.spacing_md, 0, theme.spacing_sm, 0)
        field_layout.setSpacing(theme.spacing_sm - 2)

        self._icon = QLabel(AppIcons.ACT_SEARCH)
        self._icon.setStyleSheet(
            f"color: {theme.text_muted.name()}; "
            f"background: transparent; border: none; font-size: 13px;"
        )
        field_layout.addWidget(self._icon)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Search... (try status:playing or tag:rpg)")
        self._input.setStyleSheet(
            "QLineEdit { background: transparent; border: none; padding: 7px 0; }"
        )
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._on_return_pressed)
        self._input.installEventFilter(self)
        field_layout.addWidget(self._input, 1)

        layout.addWidget(self._field)
        self._apply_field_style(focused=False)

        # Suggestion popup
        self._popup = SearchSuggestionPopup(self)
        self._popup.suggestion_selected.connect(self._on_suggestion_selected)

    def _apply_field_style(self, focused: bool) -> None:
        """Paint the search field container, accenting its border on focus."""
        theme = current_theme()
        border = theme.focus if focused else theme.outline
        bg = theme.surface if focused else theme.surface_alt
        self._field.setStyleSheet(
            f"QFrame#searchField {{ "
            f"background: {bg.name(QColor.HexArgb)}; "
            f"border: 1px solid {border.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px; "
            f"}}"
        )
        self._icon.setStyleSheet(
            f"color: {(theme.accent if focused else theme.text_muted).name()}; "
            f"background: transparent; border: none; font-size: 13px;"
        )

    def text(self) -> str:
        """Get current search text."""
        return self._input.text()

    def setText(self, text: str) -> None:
        """Set search text."""
        self._input.setText(text)

    def clear(self) -> None:
        """Clear search text."""
        self._input.clear()

    def setPlaceholderText(self, text: str) -> None:
        """Set placeholder text."""
        self._input.setPlaceholderText(text)

    def load_recent(self, searches: List[str]) -> None:
        """Load recent searches from storage."""
        self._recent.load(searches)

    def save_recent(self) -> List[str]:
        """Get recent searches for storage."""
        return self._recent.save()

    def show_suggestions(self) -> None:
        """Show the suggestions popup anchored under the search field."""
        self._popup.update_recent(self._recent.get_all())
        pos = self._field.mapToGlobal(self._field.rect().bottomLeft())
        self._popup.move(pos.x(), pos.y() + 4)
        self._popup.setMinimumWidth(self._field.width())
        self._popup.show()

    def _on_text_changed(self, text: str) -> None:
        """Handle text changes with debounce."""
        self.text_changed.emit(text)
        self._debounce_timer.start()

    def _on_return_pressed(self) -> None:
        """Handle enter key - immediate search and add to history."""
        self._debounce_timer.stop()
        query = self._input.text().strip()
        if query:
            self._recent.add(query)
        self._emit_search()

    def _emit_search(self) -> None:
        """Parse and emit the search."""
        parsed = SearchParser.parse(self._input.text())
        self.search_triggered.emit(parsed)

    def _on_suggestion_selected(self, text: str) -> None:
        """Handle suggestion selection."""
        current = self._input.text()
        # If suggestion is a filter syntax, append to current
        if ":" in text and not text.endswith(" "):
            self._input.setText(current + " " + text if current else text)
        else:
            self._input.setText(text)
        self._input.setFocus()

    def eventFilter(self, obj, event) -> bool:
        """Track focus/keys on the nested input to drive field styling and popup.

        Focus lands on the child line edit rather than this widget, so we watch
        it here to highlight the field border and surface suggestions reliably.
        """
        if obj is self._input:
            etype = event.type()
            if etype == QEvent.FocusIn:
                self._apply_field_style(focused=True)
                if not self._input.text():
                    self.show_suggestions()
            elif etype == QEvent.FocusOut:
                self._apply_field_style(focused=False)
            elif etype == QEvent.KeyPress:
                key = event.key()
                if key == Qt.Key_Escape and self._popup.isVisible():
                    self._popup.hide()
                    return True
                if key == Qt.Key_Down and not self._popup.isVisible():
                    self.show_suggestions()
                    return True
        return super().eventFilter(obj, event)
