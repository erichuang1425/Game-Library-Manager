from __future__ import annotations
import re
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QCheckBox, QWidget, QComboBox,
    QHeaderView
)

from app.models import Game
from app.services.title_matcher import calculate_similarity, normalize_title
from app.logging_utils import get_logger

_log = get_logger("bulk_source")


# Use shared title_matcher module for fuzzy matching
def _score(a: str, b: str) -> float:
    """Calculate similarity between two titles using shared utility."""
    return calculate_similarity(a, b)


def _derive_title_from_url(url: str) -> str:
    """Extract and normalize title from URL slug."""
    m = re.search(r"/threads/([^/]+)/", url)
    if not m:
        return ""
    slug = m.group(1)
    return normalize_title(slug)


class BulkSourceImportDialog(QDialog):
    def __init__(self, parent=None, games: Optional[List[Game]] = None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Source URLs")
        self.setModal(True)
        self.games = games or []
        self._game_choices = {g.title: g for g in self.games}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Paste source URLs (one per line). Optional formats: title<TAB>url or title | url"))

        self.text = QTextEdit()
        layout.addWidget(self.text)

        row = QHBoxLayout()
        load_btn = QPushButton("Load .txt…")
        load_btn.clicked.connect(self._load_file)
        self.overwrite = QCheckBox("Overwrite existing source_url")
        self.overwrite.setChecked(False)
        row.addWidget(load_btn)
        row.addStretch(1)
        row.addWidget(self.overwrite)
        layout.addLayout(row)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Use", "Input", "Detected Title", "Matched Game", "Score", "Existing", "New URL"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("Close")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(apply_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        self._parsed = []

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load URLs", "", "Text files (*.txt);;All files (*)")
        if not path:
            return
        self.text.setPlainText(Path(path).read_text(encoding="utf-8", errors="ignore"))
        _log.info("bulk_import_show %s", kv(event="bulk_import_show", games=len(self.games)))
        self._parse_and_preview()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._parse_and_preview()

    def _parse_lines(self) -> List[Tuple[str, str, str]]:
        out = []
        for raw in self.text.toPlainText().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            title = ""
            url = ""
            if "\t" in line:
                parts = line.split("\t", 1)
                title, url = parts[0].strip(), parts[1].strip()
            elif "|" in line:
                parts = line.split("|", 1)
                title, url = parts[0].strip(), parts[1].strip()
            else:
                url = line
            out.append((line, title, url))
        return out

    def _match(self, maybe_title: str, url: str) -> Tuple[Optional[Game], float, str]:
        title_hint = maybe_title or _derive_title_from_url(url)
        if not title_hint:
            return None, 0.0, title_hint
        best = None
        best_score = 0.0
        for g in self.games:
            s = _score(title_hint, g.title)
            if s > best_score:
                best_score, best = s, g
        return best, best_score, title_hint

    def _parse_and_preview(self) -> None:
        lines = self._parse_lines()
        _log.info("bulk_parse %s", kv(lines=len(lines)))
        self.table.setRowCount(len(lines))
        self._parsed = []
        for row, (raw, title, url) in enumerate(lines):
            match, score, detected = self._match(title, url)
            self._parsed.append((raw, title, url, detected, match, score))

            chk = QCheckBox()
            chk.setChecked(True if match else False)
            self.table.setCellWidget(row, 0, chk)

            self.table.setItem(row, 1, QTableWidgetItem(raw))
            self.table.setItem(row, 2, QTableWidgetItem(detected or title))

            combo = QComboBox()
            titles = [g.title for g in self.games]
            combo.addItems(["(no match)"] + titles)
            if match:
                combo.setCurrentIndex(titles.index(match.title) + 1)
            self.table.setCellWidget(row, 3, combo)

            score_item = QTableWidgetItem(f"{score:.2f}")
            score_item.setToolTip(f"{score:.2f}")
            self.table.setItem(row, 4, score_item)
            existing = match.source_url if match else ""
            self.table.setItem(row, 5, QTableWidgetItem(existing))
            self.table.setItem(row, 6, QTableWidgetItem(url))

    def _apply(self) -> None:
        applied = 0
        skipped = 0
        for row, parsed in enumerate(self._parsed):
            chk: QCheckBox = self.table.cellWidget(row, 0)
            if chk and not chk.isChecked():
                skipped += 1
                continue

            combo: QComboBox = self.table.cellWidget(row, 3)
            game_obj = None
            if combo and combo.currentIndex() > 0:
                title = combo.currentText()
                game_obj = self._game_choices.get(title)
            if not game_obj:
                skipped += 1
                continue

            url = self.table.item(row, 6).text().strip()
            if not url:
                skipped += 1
                continue
            if game_obj.source_url and not self.overwrite.isChecked():
                skipped += 1
                continue
            game_obj.source_url = url
            applied += 1

        _log.info("bulk_apply_done %s", kv(applied=applied, skipped=skipped, overwrite=self.overwrite.isChecked()))
        self.accept()
