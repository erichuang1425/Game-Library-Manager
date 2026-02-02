from __future__ import annotations
"""
Enhanced Bulk Import Dialog with automatic F95zone thread fetching.

Features:
- Paste multiple URLs
- Auto-fetch thread titles and metadata
- Smart fuzzy matching to existing games
- Download link extraction
- Batch assignment with preview
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QCheckBox, QComboBox, QProgressBar,
    QHeaderView, QFrame, QApplication
)

from app.models import Game
from app.services.f95_api import (
    is_f95_url, extract_thread_id, extract_thread_info,
    derive_title_from_url, ThreadInfo
)
from app.services.update_checker import _fetch
from app.logging_utils import get_logger, kv
from app.ui.theme import current_theme

_log = get_logger("enhanced_bulk_import")


@lru_cache(maxsize=4096)
def _normalize_title(txt: str) -> str:
    """Normalize title for fuzzy matching."""
    txt = txt.lower()
    txt = re.sub(r"https?://", "", txt)
    txt = re.sub(r"[/#?].*", "", txt)
    txt = re.sub(r"[._-]+", " ", txt)
    txt = re.sub(r"\b(v|build|season)\s*\d+[.\d]*", "", txt)
    txt = re.sub(r"\b(alpha|beta|demo|redux|patreon)\b", "", txt)
    txt = re.sub(r"\d+", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


@lru_cache(maxsize=4096)
def _tokens(name: str) -> frozenset:
    return frozenset(t for t in _normalize_title(name).split(" ") if t)


def _score(a: str, b: str) -> float:
    """Calculate Jaccard similarity between two titles."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union


class FetchWorker(QThread):
    """Worker thread for fetching URL metadata."""

    progress = Signal(int, int, str)  # current, total, url
    item_fetched = Signal(str, object)  # url, ThreadInfo or None
    finished = Signal()

    def __init__(self, urls: List[str], parent: Optional[QThread] = None) -> None:
        super().__init__(parent)
        self.urls = urls
        self._cancelled = False

    def run(self) -> None:
        total = len(self.urls)
        for i, url in enumerate(self.urls):
            if self._cancelled:
                break

            self.progress.emit(i + 1, total, url)

            try:
                if is_f95_url(url):
                    html_text = _fetch(url)
                    info = extract_thread_info(html_text, url)
                    self.item_fetched.emit(url, info)
                else:
                    self.item_fetched.emit(url, None)
            except Exception as e:
                _log.warning("fetch_url_error %s", kv(url=url, err=str(e)))
                self.item_fetched.emit(url, None)

        self.finished.emit()

    def cancel(self) -> None:
        self._cancelled = True


class EnhancedBulkImportDialog(QDialog):
    """
    Enhanced dialog for bulk importing F95zone URLs with auto-fetching.
    """

    games_updated = Signal()  # Emitted when games are updated

    def __init__(self, parent=None, games: Optional[List[Game]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Enhanced Bulk Import")
        self.setModal(True)
        self.setMinimumSize(900, 600)

        self._theme = current_theme()
        self.games = games or []
        self._game_choices = {g.title: g for g in self.games}
        self._fetched_info: Dict[str, Optional[ThreadInfo]] = {}
        self._worker: Optional[FetchWorker] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        theme = self._theme

        layout = QVBoxLayout(self)
        layout.setSpacing(theme.spacing_md)

        # Header
        header = QLabel("Bulk Import F95zone URLs")
        header.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {theme.text.name(QColor.HexArgb)};")
        layout.addWidget(header)

        desc = QLabel(
            "Paste F95zone URLs below. The system will automatically fetch thread titles, "
            "extract version info, and find download links."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {theme.text_muted.name(QColor.HexArgb)};")
        layout.addWidget(desc)

        # URL input
        input_label = QLabel("URLs (one per line):")
        input_label.setStyleSheet(f"font-weight: 500; color: {theme.text.name(QColor.HexArgb)};")
        layout.addWidget(input_label)

        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText(
            "https://f95zone.to/threads/game-name.12345/\n"
            "https://f95zone.to/threads/another-game.67890/\n"
            "..."
        )
        self.url_input.setMaximumHeight(120)
        layout.addWidget(self.url_input)

        # Action buttons
        actions_row = QHBoxLayout()

        self.fetch_btn = QPushButton("Fetch Info")
        self.fetch_btn.setMinimumWidth(100)
        self.fetch_btn.clicked.connect(self._on_fetch_clicked)
        actions_row.addWidget(self.fetch_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        actions_row.addWidget(self.progress_bar, 1)

        actions_row.addStretch(1)

        self.overwrite_check = QCheckBox("Overwrite existing source URLs")
        self.overwrite_check.setStyleSheet(f"color: {theme.text.name(QColor.HexArgb)};")
        actions_row.addWidget(self.overwrite_check)

        layout.addLayout(actions_row)

        # Results table
        table_label = QLabel("Results:")
        table_label.setStyleSheet(f"font-weight: 500; color: {theme.text.name(QColor.HexArgb)};")
        layout.addWidget(table_label)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Use", "URL", "Title (Fetched)", "Developer", "Version",
            "Matched Game", "Score", "Downloads"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)

        # Bottom buttons
        buttons_row = QHBoxLayout()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._on_select_all)
        buttons_row.addWidget(self.select_all_btn)

        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self._on_select_none)
        buttons_row.addWidget(self.select_none_btn)

        buttons_row.addStretch(1)

        self.apply_btn = QPushButton("Apply Selected")
        self.apply_btn.setMinimumWidth(120)
        self.apply_btn.setStyleSheet(f"""
            QPushButton {{
                background: {theme.accent.name(QColor.HexArgb)};
                color: white;
                border: none;
                border-radius: {theme.radius_sm}px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {theme.accent.darker(110).name(QColor.HexArgb)};
            }}
        """)
        self.apply_btn.clicked.connect(self._on_apply)
        buttons_row.addWidget(self.apply_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        buttons_row.addWidget(self.close_btn)

        layout.addLayout(buttons_row)

        # Status bar
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {theme.text_muted.name(QColor.HexArgb)}; font-size: 11px;")
        layout.addWidget(self.status_label)

    def _parse_urls(self) -> List[str]:
        """Parse URLs from input."""
        urls = []
        for line in self.url_input.toPlainText().splitlines():
            line = line.strip()
            if line and (line.startswith("http://") or line.startswith("https://")):
                urls.append(line)
        return urls

    def _on_fetch_clicked(self) -> None:
        """Handle fetch button click."""
        urls = self._parse_urls()
        if not urls:
            self.status_label.setText("No valid URLs found.")
            return

        self.fetch_btn.setEnabled(False)
        self.progress_bar.setRange(0, len(urls))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.table.setRowCount(0)
        self._fetched_info.clear()

        self._worker = FetchWorker(urls)
        self._worker.progress.connect(self._on_fetch_progress)
        self._worker.item_fetched.connect(self._on_item_fetched)
        self._worker.finished.connect(self._on_fetch_finished)
        self._worker.start()

    def _on_fetch_progress(self, current: int, total: int, url: str) -> None:
        """Handle fetch progress."""
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Fetching {current}/{total}: {url[:60]}...")

    def _on_item_fetched(self, url: str, info: Optional[ThreadInfo]) -> None:
        """Handle fetched item."""
        self._fetched_info[url] = info
        self._add_table_row(url, info)

    def _on_fetch_finished(self) -> None:
        """Handle fetch completion."""
        self.fetch_btn.setEnabled(True)
        self.progress_bar.hide()
        total = len(self._fetched_info)
        with_title = len([i for i in self._fetched_info.values() if i and i.title])
        self.status_label.setText(f"Fetched {total} URLs. {with_title} with title info.")

    def _add_table_row(self, url: str, info: Optional[ThreadInfo]) -> None:
        """Add a row to the results table."""
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Checkbox
        chk = QCheckBox()
        chk.setChecked(info is not None and info.title != "")
        self.table.setCellWidget(row, 0, chk)

        # URL
        url_item = QTableWidgetItem(url[:60] + "..." if len(url) > 60 else url)
        url_item.setToolTip(url)
        url_item.setData(Qt.UserRole, url)
        self.table.setItem(row, 1, url_item)

        # Fetched info
        title = info.title if info else ""
        developer = info.developer if info else ""
        version = info.version if info else ""

        self.table.setItem(row, 2, QTableWidgetItem(title))
        self.table.setItem(row, 3, QTableWidgetItem(developer))
        self.table.setItem(row, 4, QTableWidgetItem(version))

        # Match to existing game
        match_game, score = self._find_match(title or derive_title_from_url(url))

        # Game combo
        combo = QComboBox()
        combo.addItem("(no match)")
        for g in self.games:
            combo.addItem(g.title)
        if match_game and score > 0.3:
            idx = [g.title for g in self.games].index(match_game.title) + 1
            combo.setCurrentIndex(idx)
        self.table.setCellWidget(row, 5, combo)

        # Score
        score_item = QTableWidgetItem(f"{score:.2f}")
        self.table.setItem(row, 6, score_item)

        # Download links count
        downloads = len(info.download_links) if info else 0
        dl_item = QTableWidgetItem(str(downloads) if downloads else "-")
        dl_item.setToolTip(
            "\n".join(f"[{l.host_type}] {l.url[:50]}" for l in info.download_links[:5])
            if info and info.download_links else "No download links found"
        )
        self.table.setItem(row, 7, dl_item)

    def _find_match(self, title: str) -> Tuple[Optional[Game], float]:
        """Find best matching game for a title."""
        if not title:
            return None, 0.0

        best = None
        best_score = 0.0
        for g in self.games:
            s = _score(title, g.title)
            if s > best_score:
                best_score, best = s, g

        return best, best_score

    def _on_select_all(self) -> None:
        """Select all rows."""
        for row in range(self.table.rowCount()):
            chk = self.table.cellWidget(row, 0)
            if chk:
                chk.setChecked(True)

    def _on_select_none(self) -> None:
        """Deselect all rows."""
        for row in range(self.table.rowCount()):
            chk = self.table.cellWidget(row, 0)
            if chk:
                chk.setChecked(False)

    def _on_apply(self) -> None:
        """Apply selected assignments."""
        applied = 0
        skipped = 0

        for row in range(self.table.rowCount()):
            chk = self.table.cellWidget(row, 0)
            if not chk or not chk.isChecked():
                skipped += 1
                continue

            # Get URL
            url_item = self.table.item(row, 1)
            url = url_item.data(Qt.UserRole) if url_item else ""
            if not url:
                skipped += 1
                continue

            # Get selected game
            combo = self.table.cellWidget(row, 5)
            if not combo or combo.currentIndex() == 0:
                skipped += 1
                continue

            game_title = combo.currentText()
            game = self._game_choices.get(game_title)
            if not game:
                skipped += 1
                continue

            # Check overwrite
            if game.source_url and not self.overwrite_check.isChecked():
                skipped += 1
                continue

            # Update game
            game.source_url = url

            # Update with fetched info
            info = self._fetched_info.get(url)
            if info:
                if info.thread_id:
                    game.f95_thread_id = info.thread_id
                if info.developer and not game.developer:
                    game.developer = info.developer
                if info.version and not game.installed_version_raw:
                    game.source_version_raw = info.version
                if info.category:
                    game.f95_category = info.category
                if info.tags:
                    # Merge tags
                    existing = set(game.f95_tags)
                    for tag in info.tags:
                        if tag not in existing:
                            game.f95_tags.append(tag)

            applied += 1

        _log.info("enhanced_bulk_import_applied %s", kv(applied=applied, skipped=skipped))
        self.status_label.setText(f"Applied {applied} assignments. Skipped {skipped}.")

        if applied > 0:
            self.games_updated.emit()

    def closeEvent(self, event) -> None:
        """Handle dialog close."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait()
        super().closeEvent(event)
