from __future__ import annotations
from datetime import datetime
from typing import Optional, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton,
    QComboBox, QLineEdit, QTextEdit, QFileDialog
)

from app.models import Game
from app.ui.theme import current_theme
from app.ui.typography import get_scale, title_style, caption_style, label_style

def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "Never"
    return dt.strftime("%Y-%m-%d %H:%M")

class DetailsPanel(QWidget):
    play_clicked = Signal(str)          # game_id
    game_changed = Signal(str)          # game_id (any metadata changed)

    def __init__(self) -> None:
        super().__init__()
        self._game: Optional[Game] = None
        self._loading = False
        theme = current_theme()
        scale = get_scale()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(theme.spacing_md)

        self.title = QLabel("Select a game")
        self.title.setStyleSheet(title_style(theme, scale))
        self.title.setWordWrap(True)
        layout.addWidget(self.title)

        self.hint = QLabel("")
        self.hint.setStyleSheet(f"color:{theme.accent.name()}; {caption_style(theme, scale).replace(f'color: {theme.text_muted.name()};', '')}")
        self.hint.setWordWrap(True)
        self.hint.hide()
        layout.addWidget(self.hint)

        # Play + status row
        row = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._emit_play)

        self.status = QComboBox()
        self.status.addItems(["backlog", "playing", "finished", "dropped"])
        self.status.setEnabled(False)
        self.status.currentTextChanged.connect(self._on_changed)

        row.addWidget(self.play_btn)
        row.addWidget(QLabel("Status:"))
        row.addWidget(self.status, 1)
        layout.addLayout(row)

        # Rating
        self.rating = QComboBox()
        self.rating.addItem("—")
        for i in range(1, 11):
            self.rating.addItem(str(i))
        self.rating.setEnabled(False)
        self.rating.currentIndexChanged.connect(self._on_changed)

        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Rating:"))
        rrow.addWidget(self.rating, 1)
        layout.addLayout(rrow)

        # Tags
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("Tags (comma separated)")
        self.tags.setEnabled(False)
        self.tags.textChanged.connect(self._on_changed)
        layout.addWidget(self.tags)

        # Notes
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Notes / short review…")
        self.notes.setEnabled(False)
        self.notes.setFixedHeight(140)
        self.notes.textChanged.connect(self._on_changed)
        layout.addWidget(self.notes)

        # Source URL + versions
        src_row = QHBoxLayout()
        self.source_url = QLineEdit()
        self.source_url.setPlaceholderText("Source page URL (e.g., f95zone thread)")
        self.source_url.setEnabled(False)
        self.source_url.textChanged.connect(self._on_changed)
        self.open_source_btn = QPushButton("Open")
        self.open_source_btn.setEnabled(False)
        self.open_source_btn.clicked.connect(self._open_source)
        src_row.addWidget(QLabel("Source:"))
        src_row.addWidget(self.source_url, 1)
        src_row.addWidget(self.open_source_btn)
        layout.addLayout(src_row)

        ver_row = QHBoxLayout()
        self.installed_ver = QLineEdit()
        self.installed_ver.setPlaceholderText("Installed version (e.g., 0.1.1a)")
        self.installed_ver.setEnabled(False)
        self.installed_ver.textChanged.connect(self._on_changed)

        self.source_ver = QLabel("Source: —")
        self.source_ver.setStyleSheet(caption_style(theme, scale))

        ver_row.addWidget(QLabel("Installed:"))
        ver_row.addWidget(self.installed_ver, 1)
        ver_row.addWidget(self.source_ver, 1)
        layout.addLayout(ver_row)

        # Archive locations
        arch_row = QHBoxLayout()
        self.archive_folder = QLineEdit()
        self.archive_folder.setPlaceholderText("Archive folder path")
        self.archive_folder.setEnabled(False)
        self.archive_folder.textChanged.connect(self._on_changed)
        self.pick_archive_folder = QPushButton("Pick")
        self.pick_archive_folder.setEnabled(False)
        self.pick_archive_folder.clicked.connect(self._pick_archive_folder)
        self.open_archive_folder = QPushButton("Open")
        self.open_archive_folder.setEnabled(False)
        self.open_archive_folder.clicked.connect(self._open_archive_folder)
        arch_row.addWidget(QLabel("Folder:"))
        arch_row.addWidget(self.archive_folder, 1)
        arch_row.addWidget(self.pick_archive_folder)
        arch_row.addWidget(self.open_archive_folder)
        layout.addLayout(arch_row)

        comp_row = QHBoxLayout()
        self.compressed_path = QLineEdit()
        self.compressed_path.setPlaceholderText("Compressed archive path (.zip/.rar)")
        self.compressed_path.setEnabled(False)
        self.compressed_path.textChanged.connect(self._on_changed)
        self.pick_compressed = QPushButton("Pick")
        self.pick_compressed.setEnabled(False)
        self.pick_compressed.clicked.connect(self._pick_compressed)
        self.open_compressed = QPushButton("Open")
        self.open_compressed.setEnabled(False)
        self.open_compressed.clicked.connect(self._open_compressed)
        comp_row.addWidget(QLabel("Archive:"))
        comp_row.addWidget(self.compressed_path, 1)
        comp_row.addWidget(self.pick_compressed)
        comp_row.addWidget(self.open_compressed)
        layout.addLayout(comp_row)

        # Shortcut info
        self.launcher_info = QLabel("")
        self.launcher_info.setStyleSheet(caption_style(theme, scale))
        self.launcher_info.setWordWrap(True)
        layout.addWidget(self.launcher_info)

        # Last played
        self.last_played = QLabel("")
        self.last_played.setStyleSheet(caption_style(theme, scale))
        layout.addWidget(self.last_played)

        layout.addStretch(1)

    def show_game(self, game: Optional[Game]) -> None:
        self._loading = True
        self._game = game

        if game is None:
            self.title.setText("Select a game")
            self.play_btn.setEnabled(False)
            for w in (self.status, self.rating, self.tags, self.notes,
                      self.source_url, self.installed_ver,
                      self.archive_folder, self.compressed_path,
                      self.pick_archive_folder, self.pick_compressed,
                      self.open_archive_folder, self.open_compressed,
                      self.open_source_btn):
                w.setEnabled(False)
            self.launcher_info.setText("")
            self.last_played.setText("")
            self.source_ver.setText("Source: —")
            self._loading = False
            return

        self.title.setText(game.title)
        self.play_btn.setEnabled(True)

        self.status.setEnabled(True)
        self.status.setCurrentText(game.status)

        self.rating.setEnabled(True)
        self.rating.setCurrentIndex(0 if game.rating is None else game.rating)

        self.tags.setEnabled(True)
        self.tags.setText(", ".join(game.tags))

        self.notes.setEnabled(True)
        self.notes.setPlainText(game.notes)

        # source + versions
        self.source_url.setEnabled(True)
        self.source_url.setText(game.source_url)
        self.open_source_btn.setEnabled(bool(game.source_url))

        self.installed_ver.setEnabled(True)
        self.installed_ver.setText(game.installed_version_raw)

        src_raw = game.source_version_raw or "—"
        src_num = game.source_version_num or "—"
        src_suf = game.source_version_suffix or ""
        checked = game.source_checked_at.strftime("%Y-%m-%d %H:%M") if game.source_checked_at else "never"
        self.source_ver.setText(f"Source: {src_raw}  (num: {src_num}; suffix: {src_suf}; checked: {checked})")

        # archive paths
        for w in (self.archive_folder, self.pick_archive_folder, self.open_archive_folder,
                  self.compressed_path, self.pick_compressed, self.open_compressed):
            w.setEnabled(True)

        self.archive_folder.setText(game.archive_folder_path)
        self.compressed_path.setText(game.compressed_archive_path)

        self.launcher_info.setText(
            f"Shortcut: {game.shortcut_type.upper()} • Confidence: {game.confidence}\n"
            f"Shortcut path:\n{game.shortcut_path}\n\n"
            f"Backup target:\n{game.backup_target_path or '—'}"
        )
        self.last_played.setText(f"Last played: {_fmt_dt(game.last_played)}")

        self._loading = False
        self.show_hint("")

    def apply_edits_to_game(self) -> None:
        """
        Copy UI fields into the current Game object.
        Call this from MainWindow when DetailsPanel emits game_changed.
        """
        if self._game is None:
            return

        # status
        self._game.status = self.status.currentText()

        # rating
        if self.rating.currentIndex() == 0:
            self._game.rating = None
        else:
            self._game.rating = self.rating.currentIndex()

        # tags
        raw = self.tags.text().strip()
        if raw:
            parts = [t.strip() for t in raw.split(",")]
            self._game.tags = [t for t in parts if t]
        else:
            self._game.tags = []

        # notes
        self._game.notes = self.notes.toPlainText().strip()

        # source + versions
        self._game.source_url = self.source_url.text().strip()
        self._game.installed_version_raw = self.installed_ver.text().strip()

        # archive paths
        self._game.archive_folder_path = self.archive_folder.text().strip()
        self._game.compressed_archive_path = self.compressed_path.text().strip()

    def _emit_play(self) -> None:
        if self._game is not None:
            self.play_clicked.emit(self._game.game_id)

    def _on_changed(self) -> None:
        if self._loading:
            return
        if self._game is not None:
            self.game_changed.emit(self._game.game_id)

    def _open_source(self) -> None:
        if not self._game or not self._game.source_url:
            return
        import webbrowser
        webbrowser.open(self._game.source_url)

    def _pick_archive_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select archive folder")
        if folder:
            self.archive_folder.setText(folder)
            self._on_changed()

    def _open_archive_folder(self) -> None:
        import os
        if self.archive_folder.text().strip():
            try:
                os.startfile(self.archive_folder.text().strip())
            except Exception:
                pass

    def _pick_compressed(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select compressed archive", "", "Archives (*.zip *.rar *.7z *.7zip *.tar *.gz);;All files (*)")
        if path:
            self.compressed_path.setText(path)
            self._on_changed()

    def _open_compressed(self) -> None:
        import os
        if self.compressed_path.text().strip():
            try:
                os.startfile(self.compressed_path.text().strip())
            except Exception:
                pass

    def show_hint(self, text: str) -> None:
        if text:
            self.hint.setText(text)
            self.hint.show()
        else:
            self.hint.hide()
