"""Redesigned library sidebar with icons, sections, and rich navigation."""
from __future__ import annotations
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QHBoxLayout, QPushButton, QMenu,
)
from PySide6.QtGui import QFont

from app.models import Collection
from app.services.collection_engine import apply_collection
from app.ui.theme import current_theme, sidebar_item_style, ghost_btn_style
from app.ui.icons import AppIcons


def _collection_key(collection_id: str) -> str:
    return f"collection:{collection_id}"


class LibrarySidebar(QWidget):
    """Sidebar widget with rich navigation, icons, sections, and context menus."""

    nav_changed = Signal(str)
    new_collection_requested = Signal()
    rename_collection_requested = Signal(str)
    delete_collection_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._theme = current_theme()
        theme = self._theme

        self.setMinimumWidth(theme.sidebar_width_min)
        self.setMaximumWidth(theme.sidebar_width_max)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, theme.spacing_sm, 0, theme.spacing_sm)
        layout.setSpacing(0)

        # Sidebar header
        header = QHBoxLayout()
        header.setContentsMargins(theme.spacing_lg, theme.spacing_sm, theme.spacing_md, theme.spacing_md)
        title = QLabel("Library")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {theme.text.name()}; "
            f"background: transparent; border: none;"
        )
        header.addWidget(title)
        header.addStretch(1)
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
        self.new_btn.clicked.connect(lambda: self.new_collection_requested.emit())
        btn_row.addWidget(self.new_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # Version label
        ver = QLabel("v4.0")
        ver.setStyleSheet(
            f"color: {theme.text_muted.name()}; font-size: 9px; "
            f"padding: {theme.spacing_xs}px {theme.spacing_lg}px; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(ver)

        self._collections: List[Collection] = []
        self._games = None

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

    # ---- private helpers ----
    def _add_section_header(self, text: str) -> None:
        theme = self._theme
        item = QListWidgetItem(f"  {text}")
        item.setFlags(Qt.NoItemFlags)
        font = item.font()
        font.setPointSize(8)
        font.setWeight(QFont.Bold)
        item.setFont(font)
        item.setForeground(theme.text_muted)
        item.setSizeHint(item.sizeHint().__class__(item.sizeHint().width(), 32))
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
        item.setSizeHint(item.sizeHint().__class__(item.sizeHint().width(), 36))
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
