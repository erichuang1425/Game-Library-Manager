from __future__ import annotations
from typing import List

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QAbstractItemView, QLineEdit, QFrame
)

from app.models import Game
from app.services import compare_versions, parse_version
from app.services.version_parser import CompareResult
from app.logging_utils import get_logger, kv, connect_safe, RateLimiter
from app.ui.theme import current_theme, chip_style
from app.ui.typography import get_scale, heading_style

_log = get_logger("ui.updates")
_rate = RateLimiter()


class UpdatesWidget(QWidget):
    open_source_requested = Signal(str)     # game_id
    mark_installed_requested = Signal(str)  # game_id
    game_highlight_requested = Signal(str)  # game_id

    def __init__(self) -> None:
        super().__init__()
        self._theme = current_theme()
        theme = self._theme
        scale = get_scale()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.spacing_sm)

        title = QLabel("Updates")
        title.setStyleSheet(heading_style(theme, scale))
        layout.addWidget(title)

        # Filters
        pill_row = QHBoxLayout()
        pill_row.setSpacing(theme.spacing_xs)

        def make_filter_btn(text: str) -> QPushButton:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{ {chip_style(theme)} }}
                QPushButton:checked {{ {chip_style(theme, active=True)} }}
                QPushButton:hover {{ border-color: {theme.focus.name(QColor.HexArgb)}; }}
            """)
            connect_safe(btn.clicked, self._on_filter_clicked, _log, "updates_filter_click")
            return btn

        self.filter_all = make_filter_btn("All")
        self.filter_updates = make_filter_btn("Updates")
        self.filter_unknown = make_filter_btn("Unknown")
        for btn in (self.filter_all, self.filter_updates, self.filter_unknown):
            pill_row.addWidget(btn)
        pill_row.addStretch(1)
        self.density_comfort = make_filter_btn("Comfort")
        self.density_compact = make_filter_btn("Compact")
        for btn in (self.density_comfort, self.density_compact):
            btn.clicked.disconnect()
            connect_safe(btn.clicked, self._on_density_clicked, _log, "updates_density_click")
            pill_row.addWidget(btn)
        layout.addLayout(pill_row)
        self._filter_mode = "all"
        self.filter_all.setChecked(True)

        # search box
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title or URL")
        connect_safe(self.search.textChanged, self._render, _log, "updates_search")
        search_row.addWidget(self.search)
        layout.addLayout(search_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Game", "Installed", "Source", "URL", "Actions"])
        self.table.horizontalHeader().setStyleSheet("font-weight: 600;")
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setFocusPolicy(Qt.StrongFocus)
        connect_safe(self.table.itemActivated, self._on_row_activated, _log, "updates_row_activate")
        layout.addWidget(self.table, 1)

        self._games: List[Game] = []
        self._density = "comfortable"

        # loading overlay for table rebuilds
        self._loading_overlay: QFrame | None = None

    def set_games(self, games: List[Game]) -> None:
        self._games = games
        self._render()
        self._apply_density()

    def _emit_open(self, game_id: str) -> None:
        _log.info("updates_open_source %s", kv(game_id=game_id))
        self.open_source_requested.emit(game_id)

    def _emit_mark_installed(self, game_id: str) -> None:
        _log.info("updates_mark_installed %s", kv(game_id=game_id))
        self.mark_installed_requested.emit(game_id)

    def _on_filter_clicked(self) -> None:
        sender = self.sender()
        if sender == self.filter_updates:
            self._filter_mode = "updates"
        elif sender == self.filter_unknown:
            self._filter_mode = "unknown"
        else:
            self._filter_mode = "all"

        # keep exclusive check
        self.filter_all.setChecked(self._filter_mode == "all")
        self.filter_updates.setChecked(self._filter_mode == "updates")
        self.filter_unknown.setChecked(self._filter_mode == "unknown")
        self._render()
        if _rate.allow("updates_filter", 400):
            _log.info("updates_filter %s", kv(filter=self._filter_mode))

    def _render(self) -> None:
        self._set_loading(True)
        QTimer.singleShot(0, self._render_inner)

    def _render_inner(self) -> None:
        try:
            rows = []
            title_counts = {}
            for g in self._games:
                title_counts[g.title] = title_counts.get(g.title, 0) + 1

            term = self.search.text().strip().lower()
            for g in self._games:
                if not g.source_url:
                    continue
                if term and term not in (g.title.lower() + " " + (g.source_url or "").lower()):
                    continue

                inst_vi = parse_version(g.installed_version_raw) if g.installed_version_raw else None
                src_vi = parse_version(g.source_version_raw) if g.source_version_raw else None
                cmp = compare_versions(inst_vi, src_vi)
                if cmp == CompareResult.UNKNOWN:
                    status = "Unknown"
                elif cmp == CompareResult.OLDER:
                    status = "Update"
                elif cmp == CompareResult.SAME:
                    status = "Up-to-date"
                else:
                    status = "Newer local"

                if self._filter_mode == "updates" and status != "Update":
                    continue
                if self._filter_mode == "unknown" and status != "Unknown":
                    continue

                rows.append((g, status, cmp, inst_vi.numeric_str if inst_vi else None))

            def sort_key(item):
                g, status, cmp_val, inst_num = item
                order = {"Update": 0, "Unknown": 1, "Up-to-date": 2, "Newer local": 3}
                return (order.get(status, 4), g.title.lower())

            rows.sort(key=sort_key)

            self.table.setRowCount(len(rows))
            fm = self.table.fontMetrics()
            for row, (g, status, _cmp_val, inst_num) in enumerate(rows):
                title_txt = g.title
                if title_counts.get(g.title, 0) > 1:
                    title_txt += f" · {g.game_id[:6]}"
                title_item = QTableWidgetItem(fm.elidedText(title_txt, Qt.ElideRight, 220))
                title_item.setData(Qt.UserRole, g.game_id)
                title_item.setToolTip(f"{g.title}\n{g.shortcut_path or ''}")
                self.table.setItem(row, 0, title_item)

                inst = g.installed_version_raw or "??"
                src = g.source_version_raw or "??"
                self.table.setItem(row, 1, QTableWidgetItem(inst))

                src_item = QTableWidgetItem(fm.elidedText(f"{src} ({status})", Qt.ElideRight, 200))
                src_item.setToolTip(f"{src} ({status})")
                self.table.setItem(row, 2, src_item)

                url_item = QTableWidgetItem(fm.elidedText(g.source_url, Qt.ElideRight, 260))
                url_item.setToolTip(g.source_url)
                self.table.setItem(row, 3, url_item)

                btn_open = QPushButton("Open")
                btn_open.setFixedHeight(26)
                btn_open.setToolTip("Open source page")
                connect_safe(btn_open.clicked, lambda _=False, gid=g.game_id: self._emit_open(gid),
                             _log, "updates_open_btn", game_id=g.game_id)

                btn_mark = QPushButton("Mark")
                btn_mark.setFixedHeight(26)
                btn_mark.setToolTip("Mark installed version = source version")
                connect_safe(btn_mark.clicked, lambda _=False, gid=g.game_id: self._emit_mark_installed(gid),
                             _log, "updates_mark_btn", game_id=g.game_id)

                cell = QWidget()
                h = QHBoxLayout(cell)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(6)
                h.addWidget(btn_open)
                h.addWidget(btn_mark)
                h.addStretch(1)
                self.table.setCellWidget(row, 4, cell)

            self.table.resizeColumnsToContents()
            if not rows:
                self.table.setRowCount(1)
                self.table.setItem(0, 0, QTableWidgetItem("(no updates found)"))
                self.table.setSpan(0, 0, 1, 5)
                self.table.setRowHeight(0, 36)
            self._apply_density()
            if _rate.allow("updates_render", 400):
                _log.info("updates_render %s", kv(rows=len(rows), filter=self._filter_mode, term=self.search.text().strip()))
        finally:
            self._set_loading(False)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_overlay_geometry()

    def _set_loading(self, show: bool) -> None:
        self._ensure_overlay()
        if self._loading_overlay is None:
            return
        if show:
            self._update_overlay_geometry()
            self._loading_overlay.raise_()
        self._loading_overlay.setVisible(show)

    def _ensure_overlay(self) -> None:
        if self._loading_overlay is not None:
            return
        try:
            overlay = QFrame(self)
            overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            overlay.setStyleSheet("background: rgba(0,0,0,90); border-radius: 8px;")
            overlay.setVisible(False)
            ol = QVBoxLayout(overlay)
            ol.setContentsMargins(16, 16, 16, 16)
            ol.setSpacing(8)
            lbl = QLabel("Loading…")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:white; font-weight:600;")
            ol.addStretch(1)
            ol.addWidget(lbl, 0, Qt.AlignCenter)
            ol.addStretch(2)
            self._loading_overlay = overlay
        except Exception:
            _log.exception("overlay_init_failed")
            self._loading_overlay = None

    def _update_overlay_geometry(self) -> None:
        if self._loading_overlay is None:
            return
        if self.width() > 0 and self.height() > 0:
            self._loading_overlay.setGeometry(self.rect())

    def _apply_density(self) -> None:
        row_h = 42 if self._density == "comfortable" else 32
        for r in range(self.table.rowCount()):
            self.table.setRowHeight(r, row_h)

    def set_density(self, density: str) -> None:
        if density not in ("comfortable", "compact"):
            return
        self._density = density
        self._apply_density()
        self.density_comfort.setChecked(self._density == "comfortable")
        self.density_compact.setChecked(self._density == "compact")

    def _on_density_clicked(self) -> None:
        self.set_density("compact" if self.sender() == self.density_compact else "comfortable")

    def _on_row_activated(self, item):
        row = item.row()
        gid = self.table.item(row, 0).data(Qt.UserRole) if self.table.item(row, 0) else None
        if gid:
            self._emit_open(gid)

    def highlight_game(self, game_id: str) -> None:
        for r in range(self.table.rowCount()):
            gid = self.table.item(r, 0).data(Qt.UserRole) if self.table.item(r, 0) else None
            if gid == game_id:
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, 0))
                break

