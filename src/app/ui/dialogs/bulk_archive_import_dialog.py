from __future__ import annotations
"""
Bulk Archive Import Dialog for Game Library Manager.

Provides a comprehensive UI for:
- Scanning folders for game archives
- Managing extraction passwords
- Reviewing and selecting archives to import
- Configuring import options
- Tracking import progress
"""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QComboBox,
    QGroupBox, QFileDialog, QProgressBar, QTextEdit,
    QWidget, QMessageBox, QTabWidget, QAbstractItemView
)

from app.logging_utils import get_logger
from app.models import Game
from app.services import (
    BulkArchiveImporter, ImportItem, ImportResult, ImportAction, ImportStatus,
    load_custom_passwords, format_size
)
from app.ui.widgets.password_manager import PasswordManagerWidget
from .bulk_archive_workers import ScanWorker, ImportWorker

_log = get_logger("ui.bulk_archive_import")


class BulkArchiveImportDialog(QDialog):
    """
    Dialog for bulk importing game archives.
    """
    import_complete = Signal(list)  # List[Game] - newly created games

    def __init__(
        self,
        parent=None,
        games_folder: str = "",
        shortcuts_folder: str = "",
        library: Optional[List[Game]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Bulk Archive Import")
        self.setMinimumSize(1000, 700)
        self.setModal(True)

        self._games_folder = Path(games_folder) if games_folder else Path.home() / "Games"
        self._shortcuts_folder = Path(shortcuts_folder) if shortcuts_folder else Path.home() / "Shortcuts"
        self._library = library or []
        self._importer: Optional[BulkArchiveImporter] = None
        self._items: List[ImportItem] = []
        self._scan_thread: Optional[QThread] = None
        self._import_thread: Optional[QThread] = None

        # Load custom passwords
        load_custom_passwords()

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Create tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        # Tab 1: Scan & Select
        self.tabs.addTab(self._build_scan_tab(), "1. Scan Archives")

        # Tab 2: Password Management
        self.tabs.addTab(self._build_passwords_tab(), "2. Passwords")

        # Tab 3: Import
        self.tabs.addTab(self._build_import_tab(), "3. Import")

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _build_scan_tab(self) -> QWidget:
        """Build the scan/select tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Source folder selection
        source_group = QGroupBox("Source Folder")
        source_layout = QVBoxLayout(source_group)

        folder_row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Select folder containing game archives...")
        folder_row.addWidget(self.source_edit, 1)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._browse_source)
        folder_row.addWidget(self.browse_btn)

        source_layout.addLayout(folder_row)

        options_row = QHBoxLayout()
        self.recursive_check = QCheckBox("Scan subfolders")
        self.recursive_check.setChecked(True)
        options_row.addWidget(self.recursive_check)

        self.scan_btn = QPushButton("Scan for Archives")
        self.scan_btn.clicked.connect(self._start_scan)
        options_row.addWidget(self.scan_btn)

        options_row.addStretch()
        source_layout.addLayout(options_row)

        layout.addWidget(source_group)

        # Archives table
        table_group = QGroupBox("Found Archives")
        table_layout = QVBoxLayout(table_group)

        # Table controls
        controls = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.select_new_btn = QPushButton("Select New Only")
        self.select_new_btn.clicked.connect(self._select_new_only)

        controls.addWidget(self.select_all_btn)
        controls.addWidget(self.deselect_all_btn)
        controls.addWidget(self.select_new_btn)
        controls.addStretch()

        self.scan_status = QLabel("")
        controls.addWidget(self.scan_status)

        table_layout.addLayout(controls)

        # Table
        self.archives_table = QTableWidget()
        self.archives_table.setColumnCount(8)
        self.archives_table.setHorizontalHeaderLabels([
            "Import", "Title", "Version", "Format", "Size",
            "Encrypted", "Match", "Action"
        ])
        self.archives_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.archives_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.archives_table.setAlternatingRowColors(True)
        table_layout.addWidget(self.archives_table, 1)

        layout.addWidget(table_group, 1)

        # Destination settings
        dest_group = QGroupBox("Destination Settings")
        dest_layout = QVBoxLayout(dest_group)

        games_row = QHBoxLayout()
        games_row.addWidget(QLabel("Games Folder:"))
        self.games_folder_edit = QLineEdit(str(self._games_folder))
        games_row.addWidget(self.games_folder_edit, 1)
        self.games_browse_btn = QPushButton("Browse...")
        self.games_browse_btn.clicked.connect(self._browse_games_folder)
        games_row.addWidget(self.games_browse_btn)
        dest_layout.addLayout(games_row)

        shortcuts_row = QHBoxLayout()
        shortcuts_row.addWidget(QLabel("Shortcuts Folder:"))
        self.shortcuts_folder_edit = QLineEdit(str(self._shortcuts_folder))
        shortcuts_row.addWidget(self.shortcuts_folder_edit, 1)
        self.shortcuts_browse_btn = QPushButton("Browse...")
        self.shortcuts_browse_btn.clicked.connect(self._browse_shortcuts_folder)
        shortcuts_row.addWidget(self.shortcuts_browse_btn)
        dest_layout.addLayout(shortcuts_row)

        layout.addWidget(dest_group)

        # Next button
        next_layout = QHBoxLayout()
        next_layout.addStretch()
        self.to_import_btn = QPushButton("Continue to Import")
        self.to_import_btn.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        self.to_import_btn.setEnabled(False)
        next_layout.addWidget(self.to_import_btn)
        layout.addLayout(next_layout)

        return widget

    def _build_passwords_tab(self) -> QWidget:
        """Build the password management tab using reusable widget."""
        self.password_manager = PasswordManagerWidget()
        return self.password_manager

    def _build_import_tab(self) -> QWidget:
        """Build the import tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Import options
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)

        self.delete_archives_check = QCheckBox("Delete archives after successful extraction")
        self.delete_archives_check.setChecked(False)
        options_layout.addWidget(self.delete_archives_check)

        self.create_shortcuts_check = QCheckBox("Create shortcuts for imported games")
        self.create_shortcuts_check.setChecked(True)
        options_layout.addWidget(self.create_shortcuts_check)

        layout.addWidget(options_group)

        # Summary
        summary_group = QGroupBox("Import Summary")
        summary_layout = QVBoxLayout(summary_group)
        self.summary_label = QLabel("No archives selected for import.")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_group)

        # Progress
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        progress_layout.addWidget(self.progress_label)

        # Log
        self.import_log = QTextEdit()
        self.import_log.setReadOnly(True)
        self.import_log.setMaximumHeight(200)
        progress_layout.addWidget(self.import_log)

        layout.addWidget(progress_group, 1)

        # Import button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.start_import_btn = QPushButton("Start Import")
        self.start_import_btn.clicked.connect(self._start_import)
        self.start_import_btn.setEnabled(False)
        btn_layout.addWidget(self.start_import_btn)

        layout.addLayout(btn_layout)

        return widget

    def _connect_signals(self):
        """Connect UI signals."""
        self.archives_table.itemChanged.connect(self._on_table_item_changed)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _browse_source(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Archives Folder",
            str(Path.home())
        )
        if folder:
            self.source_edit.setText(folder)

    def _browse_games_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Games Folder",
            str(self._games_folder)
        )
        if folder:
            self.games_folder_edit.setText(folder)
            self._games_folder = Path(folder)

    def _browse_shortcuts_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Shortcuts Folder",
            str(self._shortcuts_folder)
        )
        if folder:
            self.shortcuts_folder_edit.setText(folder)
            self._shortcuts_folder = Path(folder)

    def _start_scan(self):
        source = self.source_edit.text().strip()
        if not source:
            QMessageBox.warning(self, "Error", "Please select a source folder.")
            return

        source_path = Path(source)
        if not source_path.exists():
            QMessageBox.warning(self, "Error", "Source folder does not exist.")
            return

        # Update folders
        self._games_folder = Path(self.games_folder_edit.text())
        self._shortcuts_folder = Path(self.shortcuts_folder_edit.text())

        # Create importer
        self._importer = BulkArchiveImporter(
            games_folder=self._games_folder,
            shortcuts_folder=self._shortcuts_folder,
            library=self._library,
        )

        # Disable controls
        self.scan_btn.setEnabled(False)
        self.scan_status.setText("Scanning...")

        # Start scan in thread
        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(
            self._importer,
            source_path,
            self.recursive_check.isChecked()
        )
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.error.connect(self._scan_thread.quit)
        self._scan_thread.start()

    def _on_scan_finished(self, items: List[ImportItem]):
        self._items = items
        self._populate_table()
        self.scan_btn.setEnabled(True)
        self.scan_status.setText(f"Found {len(items)} archives")
        self.to_import_btn.setEnabled(len(items) > 0)
        self._update_summary()

    def _on_scan_error(self, error: str):
        self.scan_btn.setEnabled(True)
        self.scan_status.setText("Scan failed")
        QMessageBox.critical(self, "Scan Error", error)

    def _populate_table(self):
        """Populate the archives table."""
        self.archives_table.setRowCount(len(self._items))

        for row, item in enumerate(self._items):
            # Import checkbox
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            should_import = item.match.action in (ImportAction.IMPORT_NEW, ImportAction.UPDATE_EXISTING)
            check.setCheckState(Qt.Checked if should_import else Qt.Unchecked)
            self.archives_table.setItem(row, 0, check)

            # Title
            title_item = QTableWidgetItem(item.archive.detected_title or item.archive.name)
            title_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsEditable)
            self.archives_table.setItem(row, 1, title_item)

            # Version
            version_item = QTableWidgetItem(item.archive.detected_version or "-")
            version_item.setFlags(Qt.ItemIsEnabled)
            self.archives_table.setItem(row, 2, version_item)

            # Format
            format_item = QTableWidgetItem(item.archive.format.value.upper())
            format_item.setFlags(Qt.ItemIsEnabled)
            self.archives_table.setItem(row, 3, format_item)

            # Size
            size_item = QTableWidgetItem(format_size(item.archive.size))
            size_item.setFlags(Qt.ItemIsEnabled)
            self.archives_table.setItem(row, 4, size_item)

            # Encrypted
            encrypted_item = QTableWidgetItem("Yes" if item.archive.is_encrypted else "No")
            encrypted_item.setFlags(Qt.ItemIsEnabled)
            if item.archive.is_encrypted:
                encrypted_item.setForeground(QColor("#ff9800"))
            self.archives_table.setItem(row, 5, encrypted_item)

            # Match
            match_text = "-"
            if item.match.matched_game:
                match_text = f"{item.match.matched_game.title} ({int(item.match.similarity * 100)}%)"
            match_item = QTableWidgetItem(match_text)
            match_item.setFlags(Qt.ItemIsEnabled)
            self.archives_table.setItem(row, 6, match_item)

            # Action
            action_combo = QComboBox()
            action_combo.addItems([
                "Import as New",
                "Update Existing",
                "Skip (Older)",
                "Skip (Duplicate)",
                "Skip"
            ])
            action_map = {
                ImportAction.IMPORT_NEW: 0,
                ImportAction.UPDATE_EXISTING: 1,
                ImportAction.SKIP_OLDER: 2,
                ImportAction.SKIP_DUPLICATE: 3,
                ImportAction.CONFLICT: 0,
                ImportAction.SKIP_USER: 4,
            }
            action_combo.setCurrentIndex(action_map.get(item.match.action, 0))
            action_combo.currentIndexChanged.connect(
                lambda idx, r=row: self._on_action_changed(r, idx)
            )
            self.archives_table.setCellWidget(row, 7, action_combo)

            # Color row based on action
            self._color_row(row, item.match.action)

    def _color_row(self, row: int, action: ImportAction):
        """Color a row based on its action."""
        color_map = {
            ImportAction.IMPORT_NEW: QColor("#1a472a"),      # Green tint
            ImportAction.UPDATE_EXISTING: QColor("#1a3a5c"), # Blue tint
            ImportAction.SKIP_OLDER: QColor("#4a3a1a"),      # Yellow tint
            ImportAction.SKIP_DUPLICATE: QColor("#3a3a3a"),  # Gray tint
            ImportAction.CONFLICT: QColor("#5c1a1a"),        # Red tint
            ImportAction.SKIP_USER: QColor("#2a2a2a"),       # Dark gray
        }
        color = color_map.get(action, QColor("#2a2a2a"))

        for col in range(7):  # Skip action column (has widget)
            item = self.archives_table.item(row, col)
            if item:
                item.setBackground(color)

    def _on_action_changed(self, row: int, index: int):
        """Handle action combo change."""
        action_map = {
            0: ImportAction.IMPORT_NEW,
            1: ImportAction.UPDATE_EXISTING,
            2: ImportAction.SKIP_OLDER,
            3: ImportAction.SKIP_DUPLICATE,
            4: ImportAction.SKIP_USER,
        }
        if row < len(self._items):
            self._items[row].selected_action = action_map.get(index)
            self._color_row(row, action_map.get(index, ImportAction.IMPORT_NEW))
            self._update_summary()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        """Handle table item changes."""
        row = item.row()
        col = item.column()

        if col == 0:  # Checkbox
            self._update_summary()
        elif col == 1:  # Title
            if row < len(self._items):
                self._items[row].custom_title = item.text()

    def _select_all(self):
        for row in range(self.archives_table.rowCount()):
            item = self.archives_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Checked)
        self._update_summary()

    def _deselect_all(self):
        for row in range(self.archives_table.rowCount()):
            item = self.archives_table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self._update_summary()

    def _select_new_only(self):
        for row in range(self.archives_table.rowCount()):
            item = self.archives_table.item(row, 0)
            if item and row < len(self._items):
                is_new = self._items[row].match.action == ImportAction.IMPORT_NEW
                item.setCheckState(Qt.Checked if is_new else Qt.Unchecked)
        self._update_summary()

    def _update_summary(self):
        """Update the import summary."""
        selected = []
        for row in range(self.archives_table.rowCount()):
            item = self.archives_table.item(row, 0)
            if item and item.checkState() == Qt.Checked and row < len(self._items):
                selected.append(self._items[row])

        if not selected:
            self.summary_label.setText("No archives selected for import.")
            self.start_import_btn.setEnabled(False)
            return

        new_count = sum(1 for i in selected if i.final_action == ImportAction.IMPORT_NEW)
        update_count = sum(1 for i in selected if i.final_action == ImportAction.UPDATE_EXISTING)
        total_size = sum(i.archive.size for i in selected)
        encrypted_count = sum(1 for i in selected if i.archive.is_encrypted)

        text = (
            f"Selected: {len(selected)} archives ({format_size(total_size)})\n"
            f"New games: {new_count}, Updates: {update_count}\n"
        )
        if encrypted_count:
            text += f"Encrypted: {encrypted_count} (passwords will be auto-tried)"

        self.summary_label.setText(text)
        self.start_import_btn.setEnabled(True)

    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        if index == 2:  # Import tab
            self._update_summary()

    def _start_import(self):
        """Start the import process."""
        if not self._importer:
            QMessageBox.warning(self, "Error", "Please scan for archives first.")
            return

        # Get selected items
        selected = []
        for row in range(self.archives_table.rowCount()):
            item = self.archives_table.item(row, 0)
            if item and item.checkState() == Qt.Checked and row < len(self._items):
                import_item = self._items[row]
                # Update custom title from table
                title_item = self.archives_table.item(row, 1)
                if title_item:
                    import_item.custom_title = title_item.text()
                selected.append(import_item)

        if not selected:
            QMessageBox.warning(self, "Error", "No archives selected for import.")
            return

        # Disable controls
        self.start_import_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(selected))
        self.import_log.clear()

        # Start import in thread
        self._import_thread = QThread()
        self._import_worker = ImportWorker(
            self._importer,
            selected,
            self.delete_archives_check.isChecked()
        )
        self._import_worker.moveToThread(self._import_thread)
        self._import_thread.started.connect(self._import_worker.run)
        self._import_worker.finished.connect(self._on_import_finished)
        self._import_worker.error.connect(self._on_import_error)
        self._import_worker.progress.connect(self._on_import_progress)
        self._import_worker.finished.connect(self._import_thread.quit)
        self._import_worker.error.connect(self._import_thread.quit)
        self._import_thread.start()

    def _on_import_progress(self, stage: str, current: int, total: int, message: str):
        self.progress_bar.setValue(current)
        self.progress_label.setText(message)
        self.import_log.append(f"[{stage}] {message}")

    def _on_import_finished(self, result: ImportResult):
        self.start_import_btn.setEnabled(True)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_label.setText("Import complete!")

        # Log summary
        self.import_log.append("")
        self.import_log.append("=" * 40)
        self.import_log.append(f"Import Complete!")
        self.import_log.append(f"  Imported: {result.imported}")
        self.import_log.append(f"  Updated: {result.updated}")
        self.import_log.append(f"  Skipped: {result.skipped}")
        self.import_log.append(f"  Failed: {result.failed}")

        # Log failures
        failed_items = [i for i in result.items if i.status == ImportStatus.FAILED]
        if failed_items:
            self.import_log.append("")
            self.import_log.append("Failed items:")
            for item in failed_items:
                self.import_log.append(f"  - {item.archive.name}: {item.error}")

        # Create game entries for successful imports
        new_games = []
        for item in result.items:
            if item.status == ImportStatus.COMPLETE:
                game = self._importer.create_game_entry(item)
                new_games.append(game)

        if new_games:
            self.import_complete.emit(new_games)

        QMessageBox.information(
            self,
            "Import Complete",
            f"Successfully imported {result.imported} new games and updated {result.updated} existing games.\n"
            f"Skipped: {result.skipped}, Failed: {result.failed}"
        )

    def _on_import_error(self, error: str):
        self.start_import_btn.setEnabled(True)
        self.progress_label.setText("Import failed!")
        self.import_log.append(f"ERROR: {error}")
        QMessageBox.critical(self, "Import Error", error)

    def set_library(self, library: List[Game]):
        """Update the library for matching."""
        self._library = library

    def set_games_folder(self, path: str):
        """Set the games folder path."""
        self._games_folder = Path(path)
        self.games_folder_edit.setText(path)

    def set_shortcuts_folder(self, path: str):
        """Set the shortcuts folder path."""
        self._shortcuts_folder = Path(path)
        self.shortcuts_folder_edit.setText(path)
