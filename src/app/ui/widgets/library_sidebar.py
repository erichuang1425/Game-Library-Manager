"""Redesigned library sidebar with icons, sections, collapsible mode, and rich navigation."""
from __future__ import annotations
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QPushButton, QMenu, QSizePolicy,
)
from PySide6.QtGui import QFont

from app.models import Collection
from app.services.collection_engine import apply_collection
from app.ui.theme import current_theme, sidebar_item_style, ghost_btn_style, is_reduced_motion
from app.ui.icons import AppIcons


def _collection_key(collection_id: str) -> str:
    return f"collection:{collection_id}"


class LibrarySidebar(QWidget):
    """Sidebar widget with rich navigation, icons, sections, and context menus.

    Supports collapsible icon-only mode for narrow windows.
    """

    nav_changed = Signal(str)
    new_collection_requested = Signal()
    rename_collection_requested = Signal(str)
    delete_collection_requested = Signal(str)
    collapse_toggled = Signal(bool)  # True = collapsed

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = current_theme()
        theme = self._theme
        self._collapsed = False
        self._pinned_expanded = True  # User preference: keep expanded
        self._expanded_width = theme.sidebar_width_min
        self._collapsed_width = theme.sidebar_collapsed_width
        self._hover_expand = False

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMinimumWidth(self._collapsed_width)
        self.setMaximumWidth(theme.sidebar_width_max)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, theme.spacing_sm, 0, theme.spacing_sm)
        layout.setSpacing(0)

        # Sidebar header
        header = QHBoxLayout()
        header.setContentsMargins(theme.spacing_lg, theme.spacing_sm, theme.spacing_md, theme.spacing_md)
        self._title_label = QLabel("Library")
        self._title_label.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {theme.text.name()}; "
            f"background: transparent; border: none;"
        )
        self._title_label.setMinimumWidth(0)
        header.addWidget(self._title_label, 1)
        header.addStretch(1)

        # Collapse toggle button
        self._collapse_btn = QPushButton(AppIcons.UI_CHEVRON_RIGHT)
        self._collapse_btn.setToolTip("Collapse sidebar")
        self._collapse_btn.setFixedSize(24, 24)
        self._collapse_btn.setStyleSheet(ghost_btn_style(theme))
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        header.addWidget(self._collapse_btn)
        layout.addLayout(header)

        # Main nav list
        self.list = QListWidget()
        self.list.setStyleSheet(sidebar_item_style(theme))
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self._on_row_changed)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.list, 1)

        # New collection button at bottom
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(theme.spacing_sm, theme.spacing_xs, theme.spacing_sm, 0)
        self.new_btn = QPushButton(f"{AppIcons.ACT_ADD}  New Collection")
        self.new_btn.setStyleSheet(ghost_btn_style(theme))
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.setToolTip("Create a new collection")
        self.new_btn.setMinimumWidth(0)
        self.new_btn.clicked.connect(lambda: self.new_collection_requested.emit())
        btn_row.addWidget(self.new_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Version label
        self._ver_label = QLabel("v4.0")
        self._ver_label.setStyleSheet(
            f"color: {theme.text_muted.name()}; font-size: 10px; "
            f"padding: {theme.spacing_xs}px {theme.spacing_lg}px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(self._ver_label)

        self._collections: List[Collection] = []
        self._games = None

        # Animation for collapse/expand
        self._width_anim = QPropertyAnimation(self, b"maximumWidth", self)
        self._width_anim.setDuration(200 if not is_reduced_motion() else 0)
        self._width_anim.setEasingCurve(QEasingCurve.OutCubic)

    # ---- public API ----
    def set_games(self, games) -> None:
        self._games = games

    def set_collections(self, collections: List[Collection], games=None) -> None:
        if games is not None:
            self._games = games
        self._collections = collections or []
        key = self.current_key() or "all"
        all_count = len(self._games) if self._games else 0
        self.populate(all_count, 0, 0, self._collections, key)

    def populate(
        self,
        all_count: int,
        updates_count: int,
        health_count: int,
        collections: List[Collection],
        selected_key: str = "all",
    ) -> None:
        self._collections = collections or []
        self.list.blockSignals(True)
        self.list.clear()

        fm = self.list.fontMetrics()
        max_w = max(140, self.list.viewport().width() - 48)

        if self._collapsed:
            self._add_icon_item(AppIcons.NAV_LIBRARY, "All Games", all_count, "all")
            for c in sorted(
                [c for c in self._collections if c.type == "manual"],
                key=lambda x: x.name.lower(),
            ):
                cnt = self._collection_count(c)
                self._add_icon_item(
                    AppIcons.NAV_COLLECTION, c.name, cnt,
                    _collection_key(c.collection_id),
                )
            for c in sorted(
                [c for c in self._collections if c.type == "smart"],
                key=lambda x: x.name.lower(),
            ):
                cnt = self._collection_count(c)
                self._add_icon_item(
                    AppIcons.NAV_SMART, c.name, cnt,
                    _collection_key(c.collection_id),
                )
            self._add_icon_item(AppIcons.NAV_UPDATES, "Updates", updates_count, "updates")
            self._add_icon_item(AppIcons.NAV_HEALTH, "Health Checks", health_count, "health")
        else:
            self._add_nav_item(AppIcons.NAV_LIBRARY, "All Games", all_count, "all", fm, max_w)

            self._add_section_header("COLLECTIONS")
            manual = sorted(
                [c for c in self._collections if c.type == "manual"],
                key=lambda x: x.name.lower(),
            )
            for c in manual:
                cnt = self._collection_count(c)
                self._add_nav_item(
                    AppIcons.NAV_COLLECTION, c.name, cnt,
                    _collection_key(c.collection_id), fm, max_w,
                )

            self._add_section_header("SMART")
            smart = sorted(
                [c for c in self._collections if c.type == "smart"],
                key=lambda x: x.name.lower(),
            )
            for c in smart:
                cnt = self._collection_count(c)
                self._add_nav_item(
                    AppIcons.NAV_SMART, c.name, cnt,
                    _collection_key(c.collection_id), fm, max_w,
                )

            self._add_section_header("TOOLS")
            self._add_nav_item(AppIcons.NAV_UPDATES, "Updates", updates_count, "updates", fm, max_w)
            self._add_nav_item(AppIcons.NAV_HEALTH, "Health Checks", health_count, "health", fm, max_w)

        self.list.blockSignals(False)
        self.set_selected(selected_key)

    def update_counts(self, all_count: int, updates_count: int, health_count: int) -> None:
        key = self.current_key() or "all"
        self.populate(all_count, updates_count, health_count, self._collections, key)

    def set_selected(self, key: str) -> None:
        if not key:
            return
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it and it.data(Qt.UserRole) == key:
                self.list.setCurrentRow(i)
                return

    def current_key(self) -> Optional[str]:
        it = self.list.currentItem()
        if not it:
            return None
        return it.data(Qt.UserRole)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        """Collapse or expand the sidebar."""
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        self._update_collapsed_visuals()

        target_width = self._collapsed_width if collapsed else self._expanded_width
        if animate and not is_reduced_motion():
            # Set minimum width to collapsed width for smooth animation in both directions
            self.setMinimumWidth(self._collapsed_width)
            self._width_anim.stop()
            self._width_anim.setStartValue(self.maximumWidth())
            self._width_anim.setEndValue(target_width)
            self._width_anim.finished.connect(
                lambda: self._on_collapse_anim_finished(collapsed)
            )
            self._width_anim.start()
        else:
            self.setMaximumWidth(target_width)
            self.setMinimumWidth(target_width)

        # Repopulate with collapsed/expanded items
        key = self.current_key() or "all"
        all_count = len(self._games) if self._games else 0
        self.populate(all_count, 0, 0, self._collections, key)
        self.collapse_toggled.emit(collapsed)

    def _on_collapse_anim_finished(self, collapsed: bool) -> None:
        """Finalize min/max width after collapse animation completes."""
        try:
            self._width_anim.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        target = self._collapsed_width if collapsed else self._expanded_width
        self.setMinimumWidth(target)
        self.setMaximumWidth(self._theme.sidebar_width_max if not collapsed else target)

    def select_by_index(self, index: int) -> None:
        """Select a sidebar item by index (for keyboard shortcuts)."""
        if 0 <= index < self.list.count():
            self.list.setCurrentRow(index)

    # ---- private helpers ----
    def _update_collapsed_visuals(self) -> None:
        """Show/hide text elements based on collapsed state."""
        show = not self._collapsed
        self._title_label.setVisible(show)
        self.new_btn.setVisible(show)
        self._ver_label.setVisible(show)
        self._collapse_btn.setText(
            AppIcons.UI_CHEVRON_RIGHT if self._collapsed else AppIcons.UI_CHEVRON_DOWN
        )
        self._collapse_btn.setToolTip(
            "Expand sidebar" if self._collapsed else "Collapse sidebar"
        )

    def _toggle_collapse(self) -> None:
        self._pinned_expanded = self._collapsed  # Toggle pin state
        self.set_collapsed(not self._collapsed)

    def _add_section_header(self, text: str) -> None:
        theme = self._theme
        item = QListWidgetItem(f"  {text}")
        item.setFlags(Qt.NoItemFlags)
        font = item.font()
        font.setPointSize(9)
        font.setWeight(QFont.Bold)
        item.setFont(font)
        item.setForeground(theme.text_muted)
        item.setSizeHint(item.sizeHint().__class__(item.sizeHint().width(), 36))
        self.list.addItem(item)

    def _add_nav_item(
        self, icon: str, label: str, count: int,
        key: str, fm, max_w: int,
    ) -> None:
        count_str = f"  ({count})" if count > 0 else ""
        display = f"{icon}  {label}{count_str}"
        elided = fm.elidedText(display, Qt.ElideRight, max_w)
        item = QListWidgetItem(elided)
        item.setToolTip(f"{label} ({count})" if count else label)
        item.setData(Qt.UserRole, key)
        item.setSizeHint(item.sizeHint().__class__(item.sizeHint().width(), 38))
        self.list.addItem(item)

    def _add_icon_item(self, icon: str, label: str, count: int, key: str) -> None:
        """Add an icon-only item for collapsed mode."""
        item = QListWidgetItem(icon)
        item.setTextAlignment(Qt.AlignCenter)
        item.setToolTip(f"{label} ({count})" if count else label)
        item.setData(Qt.UserRole, key)
        item.setSizeHint(item.sizeHint().__class__(self._collapsed_width - 8, 38))
        self.list.addItem(item)

    def _collection_count(self, coll: Collection) -> int:
        try:
            if self._games is not None:
                return len(apply_collection(self._games, coll))
            if hasattr(coll, "game_ids") and coll.game_ids is not None:
                return len(coll.game_ids)
        except Exception:
            pass
        return 0

    def _on_row_changed(self, idx: int) -> None:
        it = self.list.item(idx)
        if not it:
            return
        key = it.data(Qt.UserRole)
        if not key:
            return
        self.nav_changed.emit(str(key))

    def _on_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not item:
            return
        key = item.data(Qt.UserRole)
        if not key or not key.startswith("collection:"):
            return

        coll_id = key.replace("collection:", "")
        menu = QMenu(self)
        rename_act = menu.addAction(f"{AppIcons.ACT_EDIT}  Rename")
        delete_act = menu.addAction(f"{AppIcons.ACT_REMOVE}  Delete")

        chosen = menu.exec(self.list.mapToGlobal(pos))
        if chosen == rename_act:
            self.rename_collection_requested.emit(coll_id)
        elif chosen == delete_act:
            self.delete_collection_requested.emit(coll_id)

    def resizeEvent(self, event) -> None:
        """Refresh item labels on resize to re-elide text for current width."""
        super().resizeEvent(event)
        if not self._collapsed:
            # Update elision for current width
            fm = self.list.fontMetrics()
            max_w = max(80, self.list.viewport().width() - 48)
            for i in range(self.list.count()):
                item = self.list.item(i)
                if not item:
                    continue
                tooltip = item.toolTip()
                key = item.data(Qt.UserRole)
                if not key or not tooltip:
                    continue  # Skip section headers
                elided = fm.elidedText(tooltip, Qt.ElideRight, max_w)
                if elided != item.text():
                    item.setText(elided)

    # ---- Hover expand for collapsed mode ----
    def enterEvent(self, event) -> None:
        if self._collapsed and not self._pinned_expanded:
            self._hover_expand = True
            self.set_collapsed(False, animate=True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover_expand and not self._pinned_expanded:
            self._hover_expand = False
            self.set_collapsed(True, animate=True)
        super().leaveEvent(event)
