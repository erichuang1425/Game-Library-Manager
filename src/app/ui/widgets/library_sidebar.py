from __future__ import annotations
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem

from app.models import Collection
from app.services.collection_engine import apply_collection


def _collection_key(collection_id: str) -> str:
    return f"collection:{collection_id}"


class LibrarySidebar(QWidget):
    """
    Sidebar widget that lists library navigation entries (All, collections, updates, health).
    Emits `nav_changed(str key)` when selection changes.
    """

    nav_changed = Signal(str)  # keys: "all", "updates", "health", "collection:<id>"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setMaximumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Library")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._on_row_changed)

        layout.addWidget(title)
        layout.addWidget(self.list)

        self._collections: List[Collection] = []
        self._games = None  # Optional[List[Game]]

    # ---- public API ----
    def set_games(self, games) -> None:
        """Provide the current games list for collection counts."""
        self._games = games

    def populate(
        self,
        all_count: int,
        updates_count: int,
        health_count: int,
        collections: List[Collection],
        selected_key: str = "all",
    ) -> None:
        """Rebuild sidebar entries with elision + tooltips."""
        self._collections = collections or []
        self.list.blockSignals(True)
        self.list.clear()

        fm = self.list.fontMetrics()
        max_w = max(140, self.list.viewport().width() - 12)

        def _item(text: str, key: str | None) -> QListWidgetItem:
            it = QListWidgetItem(fm.elidedText(text, Qt.ElideRight, max_w))
            it.setToolTip(text)
            if key is None:
                it.setFlags(Qt.NoItemFlags)
            else:
                it.setData(Qt.UserRole, key)
            return it

        # All games
        self.list.addItem(_item(f"All Games ({all_count})", "all"))

        # Manual collections
        self.list.addItem(_item("-- Collections --", None))
        manual = sorted([c for c in self._collections if c.type == "manual"], key=lambda x: x.name.lower())
        for c in manual:
            cnt = self._collection_count(c)
            self.list.addItem(_item(f"* {c.name} ({cnt})", _collection_key(c.collection_id)))

        # Smart collections
        self.list.addItem(_item("-- Smart Collections --", None))
        smart = sorted([c for c in self._collections if c.type == "smart"], key=lambda x: x.name.lower())
        for c in smart:
            cnt = self._collection_count(c)
            self.list.addItem(_item(f"> {c.name} ({cnt})", _collection_key(c.collection_id)))

        # Tools
        self.list.addItem(_item("-- Tools --", None))
        self.list.addItem(_item("Updates", "updates"))
        self.list.addItem(_item("Health Checks", "health"))

        self.list.blockSignals(False)
        self.set_selected(selected_key)

    def update_counts(self, all_count: int, updates_count: int, health_count: int) -> None:
        """Refresh counts while keeping current selection."""
        key = self.current_key() or "all"
        self.populate(all_count, updates_count, health_count, self._collections, key)

    def set_selected(self, key: str) -> None:
        """Select the given nav key if present."""
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

    # ---- helpers ----
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
