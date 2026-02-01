from __future__ import annotations
from pathlib import Path
from typing import List, Tuple

from PySide6.QtCore import Signal, Qt, QTimer
from PySide6 import QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QAbstractItemView, QLineEdit, QFrame
)

from app.models import Game
from app.services import parse_version, compare_versions
from app.services.version_parser import CompareResult
from app.logging_utils import get_logger, kv, connect_safe, RateLimiter

_log = get_logger("ui.health")
_rate = RateLimiter()


class HealthChecksWidget(QWidget):
    open_folder_requested = Signal(str)   # shortcut_path
    remove_game_requested = Signal(str)   # game_id
    fix_requested = Signal(str, str)  # game_id, issue_code
    resolve_requested = Signal(str, str)  # game_id, issue_code
    ignore_requested = Signal(str, str)  # game_id, issue_code
    issue_filter_requested = Signal(str)  # issue tag

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("Health Checks")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)

        pill_row = QHBoxLayout()
        self.filter_all = QPushButton("All")
        self.filter_errors = QPushButton("Errors")
        self.filter_warn = QPushButton("Warnings")
        self.filter_missing_source = QPushButton("Missing Source")
        self.filter_missing_archive = QPushButton("Missing Archive")
        for btn in (self.filter_all, self.filter_errors, self.filter_warn, self.filter_missing_source, self.filter_missing_archive):
            btn.setCheckable(True)
            connect_safe(btn.clicked, self._on_filter_clicked, _log, "health_filter_click")
            pill_row.addWidget(btn)
        pill_row.addStretch(1)
        self.density_comfort = QPushButton("Comfort")
        self.density_compact = QPushButton("Compact")
        for btn in (self.density_comfort, self.density_compact):
            btn.setCheckable(True)
            connect_safe(btn.clicked, self._on_density_clicked, _log, "health_density_click")
            pill_row.addWidget(btn)
        layout.addLayout(pill_row)
        self._filter_mode = "all"
        self.filter_all.setChecked(True)

        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title or issue")
        connect_safe(self.search.textChanged, self._render, _log, "health_search")
        refresh_btn = QPushButton("Refresh")
        connect_safe(refresh_btn.clicked, self._render, _log, "health_refresh")
        search_row.addWidget(self.search, 1)
        search_row.addWidget(refresh_btn)
        layout.addLayout(search_row)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Game", "Issue", "Actions", "Resolve/Ignore", ""])
        self.table.horizontalHeader().setStyleSheet("font-weight: 600;")
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setFocusPolicy(Qt.StrongFocus)

        layout.addWidget(self.table, 1)

        self._games: List[Game] = []
        self._density = "comfortable"
        self._ignored: dict[str, set[str]] = {}

        # loading overlay shown during recalculation
        self._loading_overlay: QFrame | None = None

    def set_games(self, games: List[Game]) -> None:
        self._games = games
        self._render()

    def set_ignored(self, ignored: dict) -> None:
        self._ignored = ignored or {}
        self._render()

    def _emit_open(self, shortcut_path: str, game_id: str) -> None:
        _log.info("health_open %s", kv(game_id=game_id, path=shortcut_path))
        self.open_folder_requested.emit(shortcut_path)

    def _emit_remove(self, game_id: str) -> None:
        _log.info("health_remove %s", kv(game_id=game_id))
        self.remove_game_requested.emit(game_id)

    def _emit_fix(self, game_id: str, code: str) -> None:
        _log.info("health_fix %s", kv(game_id=game_id, issue=code))
        self.fix_requested.emit(game_id, code)

    def _emit_resolve(self, game_id: str, code: str) -> None:
        _log.info("health_resolve %s", kv(game_id=game_id, issue=code))
        self.resolve_requested.emit(game_id, code)

    def _emit_ignore(self, game_id: str, code: str) -> None:
        _log.info("health_ignore %s", kv(game_id=game_id, issue=code))
        self.ignore_requested.emit(game_id, code)

    def _render(self) -> None:
        # allow event loop to paint overlay before heavy work
        self._set_loading(True)
        QTimer.singleShot(0, self._render_inner)

    def _render_inner(self) -> None:
        try:
            issues = self._collect_issues(self._games)

            term = self.search.text().strip().lower()
            if term:
                issues = [(g, msg, level, code) for g, msg, level, code in issues if term in (g.title.lower() + " " + msg.lower())]

            if self._filter_mode == "errors":
                issues = [i for i in issues if i[2] == "error"]
            elif self._filter_mode == "warnings":
                issues = [i for i in issues if i[2] == "warn"]
            elif self._filter_mode == "missing_source":
                issues = [i for i in issues if "source" in i[1].lower()]
            elif self._filter_mode == "missing_archive":
                issues = [i for i in issues if "archive" in i[1].lower()]

            self.table.setRowCount(len(issues))
            fm = self.table.fontMetrics()
            for row, (g, issue_text, level, code) in enumerate(issues):
                title_item = QTableWidgetItem(fm.elidedText(g.title, Qt.ElideRight, 220))
                title_item.setToolTip(g.title)
                self.table.setItem(row, 0, title_item)
                msg_item = QTableWidgetItem(fm.elidedText(issue_text, Qt.ElideRight, 320))
                msg_item.setToolTip(issue_text)
                if level == "error":
                    msg_item.setForeground(QtGui.QColor("#c62828"))
                elif level == "warn":
                    msg_item.setForeground(QtGui.QColor("#ef6c00"))
                else:
                    msg_item.setForeground(QtGui.QColor("#455a64"))
                self.table.setItem(row, 1, msg_item)

                btn_open = QPushButton("Open")
                btn_open.setFixedHeight(26)
                connect_safe(btn_open.clicked, lambda _=False, sp=g.shortcut_path, gid=g.game_id: self._emit_open(sp, gid),
                             _log, "health_open_btn", game_id=g.game_id)

                btn_remove = QPushButton("Remove")
                btn_remove.setFixedHeight(26)
                connect_safe(btn_remove.clicked, lambda _=False, gid=g.game_id: self._emit_remove(gid),
                             _log, "health_remove_btn", game_id=g.game_id)

                btn_fix = QPushButton("Fix")
                btn_fix.setFixedHeight(26)
                connect_safe(btn_fix.clicked, lambda _=False, gid=g.game_id, c=code: self._emit_fix(gid, c),
                             _log, "health_fix_btn", game_id=g.game_id, issue=code)

                cell = QWidget()
                h = QHBoxLayout(cell)
                h.setContentsMargins(0, 0, 0, 0)
                h.setSpacing(6)
                h.addWidget(btn_open)
                h.addWidget(btn_fix)
                h.addWidget(btn_remove)
                h.addStretch(1)

                self.table.setCellWidget(row, 2, cell)

                btn_resolve = QPushButton("Mark resolved")
                btn_resolve.setFixedHeight(24)
                connect_safe(btn_resolve.clicked, lambda _=False, gid=g.game_id, c=code: self._emit_resolve(gid, c),
                             _log, "health_resolve_btn", game_id=g.game_id, issue=code)
                btn_ignore = QPushButton("Ignore")
                btn_ignore.setFixedHeight(24)
                connect_safe(btn_ignore.clicked, lambda _=False, gid=g.game_id, c=code: self._emit_ignore(gid, c),
                             _log, "health_ignore_btn", game_id=g.game_id, issue=code)
                res_cell = QWidget()
                h2 = QHBoxLayout(res_cell)
                h2.setContentsMargins(0, 0, 0, 0)
                h2.setSpacing(4)
                h2.addWidget(btn_resolve)
                h2.addWidget(btn_ignore)
                h2.addStretch(1)
                self.table.setCellWidget(row, 3, res_cell)
                self.table.setItem(row, 4, QTableWidgetItem(""))

            self.table.resizeColumnsToContents()
            self._apply_density()
            if not issues:
                self.table.setRowCount(1)
                self.table.setItem(0, 0, QTableWidgetItem("(no issues found)"))
                self.table.setSpan(0, 0, 1, 5)
                self.table.setRowHeight(0, 36)
            if _rate.allow("health_render", 400):
                _log.info("health_render %s", kv(count=len(issues), filter=self._filter_mode, term=self.search.text().strip()))
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

    def _collect_issues(self, games: List[Game]) -> List[Tuple[Game, str, str, str]]:
        out: List[Tuple[Game, str, str, str]] = []
        for g in games:
            sp = Path(g.shortcut_path) if g.shortcut_path else None
            shortcut_missing = (not sp) or (not sp.exists())

            if shortcut_missing:
                bt = Path(g.backup_target_path) if g.backup_target_path else None
                if bt and bt.exists():
                    out.append((g, "Shortcut missing, backup target exists", "error", "shortcut_missing_backup"))
                else:
                    out.append((g, "Shortcut missing and backup target missing", "error", "shortcut_missing_all"))
                continue

            # Shortcut exists, but .lnk target missing
            if g.shortcut_type == "lnk" and g.backup_target_path:
                bt = Path(g.backup_target_path)
                if not bt.exists():
                    out.append((g, "Shortcut exists, but target EXE is missing", "error", "target_missing"))

            # URL issue (confidence low usually means URL missing/empty)
            if g.shortcut_type == "url" and g.confidence == "low":
                out.append((g, "URL shortcut looks broken or empty", "warn", "url_broken"))

            # Archive presence
            if g.archive_folder_path:
                ap = Path(g.archive_folder_path)
                if not ap.exists():
                    out.append((g, "Archive folder missing", "warn", "archive_folder_missing"))
            if g.compressed_archive_path:
                cp = Path(g.compressed_archive_path)
                if not cp.exists():
                    out.append((g, "Compressed archive missing", "warn", "archive_compressed_missing"))

            # Version mismatch
            inst_vi = parse_version(g.installed_version_raw) if g.installed_version_raw else None
            src_vi = parse_version(g.source_version_raw) if g.source_version_raw else None
            cmp = compare_versions(inst_vi, src_vi)
            if cmp == CompareResult.OLDER:
                out.append((g, "Installed version older than source", "warn", "version_older"))
            if cmp == CompareResult.NEWER:
                out.append((g, "Installed version newer than source (review)", "warn", "version_newer"))

            # Missing source URL
            if not g.source_url:
                out.append((g, "No source URL set", "warn", "source_missing"))

            # Game folder
            if g.game_folder_path:
                gf = Path(g.game_folder_path)
                if not gf.exists():
                    out.append((g, "Game folder missing", "warn", "game_folder_missing"))
            else:
                out.append((g, "No game folder recorded", "warn", "game_folder_missing"))

        # filter ignored
        out = [(g, msg, lvl, code) for (g, msg, lvl, code) in out if code not in self._ignored.get(g.game_id, set())]

        return out

    def _on_filter_clicked(self) -> None:
        sender = self.sender()
        if sender == self.filter_errors:
            self._filter_mode = "errors"
        elif sender == self.filter_warn:
            self._filter_mode = "warnings"
        elif sender == self.filter_missing_source:
            self._filter_mode = "missing_source"
        elif sender == self.filter_missing_archive:
            self._filter_mode = "missing_archive"
        else:
            self._filter_mode = "all"
        for key, btn in [
            ("all", self.filter_all),
            ("errors", self.filter_errors),
            ("warnings", self.filter_warn),
            ("missing_source", self.filter_missing_source),
            ("missing_archive", self.filter_missing_archive),
        ]:
            btn.setChecked(self._filter_mode == key)
        self._render()

    def set_density(self, density: str) -> None:
        if density not in ("comfortable", "compact"):
            return
        self._density = density
        self._apply_density()

    def _apply_density(self) -> None:
        row_h = 42 if self._density == "comfortable" else 32
        for r in range(self.table.rowCount()):
            self.table.setRowHeight(r, row_h)

    def _on_density_clicked(self) -> None:
        self.set_density("compact" if self.sender() == self.density_compact else "comfortable")
