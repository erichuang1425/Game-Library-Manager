"""Reusable visual input controls: star rating, status chips, tag editor.

These replace plain combo boxes / line edits in the details panel with
interactive, branded controls. Public setters (``set_*``) update state silently;
only genuine user interaction emits the ``changed`` signal, so callers can load
values without triggering edit callbacks.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QRect, QPoint, QSize
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QLineEdit, QLayout,
)
from PySide6.QtGui import QColor

from app.ui.theme import current_theme, status_color
from app.ui.widgets.game_grid.display_utils import status_label


# ---------------------------------------------------------------------------
#  FlowLayout — wraps child widgets onto multiple rows (used by TagEditor)
# ---------------------------------------------------------------------------
class FlowLayout(QLayout):
    """A layout that arranges children left-to-right, wrapping as needed."""

    def __init__(self, parent: Optional[QWidget] = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:  # noqa: N802 (Qt override)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only: bool) -> int:
        x, y = rect.x(), rect.y()
        line_height = 0
        spacing = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width()
            if next_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()


# ---------------------------------------------------------------------------
#  StarRating — interactive 1..10 rating shown as five stars
# ---------------------------------------------------------------------------
class StarRating(QWidget):
    """Five clickable stars representing a 1-10 rating (even values on click).

    Clicking a star sets the rating to ``(index + 1) * 2``; clicking the active
    star again clears it. Loaded odd values (e.g. 7) display rounded but are
    preserved until the user edits.
    """

    changed = Signal(object)  # int (1-10) or None

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rating: Optional[int] = None
        self._buttons: list[QPushButton] = []
        theme = current_theme()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        for i in range(5):
            btn = QPushButton("☆")
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(26, 26)
            btn.setStyleSheet(
                f"QPushButton {{ font-size: 18px; color: {theme.text_muted.name()}; "
                f"background: transparent; border: none; padding: 0; }}"
                f"QPushButton:hover {{ color: {theme.accent.name()}; }}"
            )
            value = (i + 1) * 2
            btn.clicked.connect(lambda _=False, v=value: self._on_click(v))
            btn.setToolTip(f"Rate {value}/10")
            self._buttons.append(btn)
            row.addWidget(btn)
        self._value_label = QLabel("")
        self._value_label.setStyleSheet(
            f"color: {theme.text_muted.name()}; font-size: 12px; "
            f"background: transparent; border: none;"
        )
        row.addSpacing(6)
        row.addWidget(self._value_label)
        row.addStretch(1)
        self._theme = theme
        self._refresh()

    def _on_click(self, value: int) -> None:
        self._rating = None if self._rating == value else value
        self._refresh()
        self.changed.emit(self._rating)

    def set_rating(self, rating: Optional[int]) -> None:
        """Set the rating without emitting ``changed``."""
        self._rating = rating
        self._refresh()

    def rating(self) -> Optional[int]:
        return self._rating

    def _refresh(self) -> None:
        filled = 0 if not self._rating else max(0, min(5, round(self._rating / 2)))
        accent = self._theme.accent.name()
        muted = self._theme.text_muted.name()
        for i, btn in enumerate(self._buttons):
            on = i < filled
            btn.setText("★" if on else "☆")
            btn.setStyleSheet(
                f"QPushButton {{ font-size: 18px; "
                f"color: {accent if on else muted}; "
                f"background: transparent; border: none; padding: 0; }}"
                f"QPushButton:hover {{ color: {accent}; }}"
            )
        self._value_label.setText(f"{self._rating}/10" if self._rating else "Unrated")


# ---------------------------------------------------------------------------
#  StatusChips — segmented status selector using semantic colors
# ---------------------------------------------------------------------------
class StatusChips(QWidget):
    """Four toggle chips for backlog / playing / finished / dropped."""

    changed = Signal(str)
    STATUSES = ["backlog", "playing", "finished", "dropped"]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._status = "backlog"
        self._chips: dict[str, QPushButton] = {}
        self._theme = current_theme()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        for s in self.STATUSES:
            chip = QPushButton(status_label(s))
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, st=s: self._on_click(st))
            self._chips[s] = chip
            row.addWidget(chip)
        row.addStretch(1)
        self._refresh()

    def _on_click(self, status: str) -> None:
        self._status = status
        self._refresh()
        self.changed.emit(status)

    def set_status(self, status: str) -> None:
        """Set the active status without emitting ``changed``."""
        if status in self._chips:
            self._status = status
            self._refresh()

    def status(self) -> str:
        return self._status

    def _refresh(self) -> None:
        theme = self._theme
        for s, chip in self._chips.items():
            active = s == self._status
            chip.setChecked(active)
            sc = status_color(theme, s)
            if active:
                chip.setStyleSheet(
                    f"QPushButton {{ background: {sc.name()}; color: {theme.bg.name()}; "
                    f"border: 1px solid {sc.name()}; border-radius: {theme.radius_sm}px; "
                    f"padding: 4px 10px; font-size: 12px; font-weight: 600; }}"
                )
            else:
                chip.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {theme.text_muted.name()}; "
                    f"border: 1px solid {theme.outline.name(QColor.HexArgb)}; "
                    f"border-radius: {theme.radius_sm}px; padding: 4px 10px; font-size: 12px; }}"
                    f"QPushButton:hover {{ color: {theme.text.name()}; "
                    f"border-color: {sc.name()}; }}"
                )


# ---------------------------------------------------------------------------
#  TagEditor — removable tag chips with an inline add field
# ---------------------------------------------------------------------------
class TagEditor(QWidget):
    """Editable set of tags shown as removable chips, with an add field."""

    changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tags: List[str] = []
        self._theme = current_theme()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._chips_host = QWidget()
        self._flow = FlowLayout(self._chips_host, spacing=6)
        outer.addWidget(self._chips_host)

        self._add = QLineEdit()
        self._add.setPlaceholderText("Add tag…")
        self._add.returnPressed.connect(self._on_add)
        outer.addWidget(self._add)

    # -- public API --
    def set_tags(self, tags: List[str]) -> None:
        """Replace the tag set without emitting ``changed``."""
        self._tags = [t for t in (tags or []) if t]
        self._rebuild()

    def tags(self) -> List[str]:
        return list(self._tags)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 (Qt override)
        super().setEnabled(enabled)
        self._add.setEnabled(enabled)

    # -- internals --
    def _on_add(self) -> None:
        raw = self._add.text().strip()
        if not raw:
            return
        added = False
        for part in raw.split(","):
            t = part.strip()
            if t and t not in self._tags:
                self._tags.append(t)
                added = True
        self._add.clear()
        if added:
            self._rebuild()
            self.changed.emit()

    def _remove(self, tag: str) -> None:
        if tag in self._tags:
            self._tags.remove(tag)
            self._rebuild()
            self.changed.emit()

    def _rebuild(self) -> None:
        # Clear existing chips
        while self._flow.count():
            item = self._flow.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()
        theme = self._theme
        acc = theme.accent
        acc_rgb = f"{acc.red()},{acc.green()},{acc.blue()}"
        for t in self._tags:
            chip = QPushButton(f"{t}   ✕")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setToolTip(f"Remove '{t}'")
            chip.clicked.connect(lambda _=False, tag=t: self._remove(tag))
            chip.setStyleSheet(
                f"QPushButton {{ color: {theme.text.name()}; "
                f"background: rgba({acc_rgb},28); "
                f"border: 1px solid rgba({acc_rgb},70); "
                f"border-radius: {theme.radius_sm}px; padding: 3px 8px; font-size: 12px; }}"
                f"QPushButton:hover {{ background: rgba({acc_rgb},55); }}"
            )
            self._flow.addWidget(chip)
        if not self._tags:
            placeholder = QLabel("No tags yet")
            placeholder.setStyleSheet(
                f"color: {theme.text_muted.name()}; font-size: 12px; "
                f"background: transparent; border: none;"
            )
            self._flow.addWidget(placeholder)
        self._chips_host.updateGeometry()
