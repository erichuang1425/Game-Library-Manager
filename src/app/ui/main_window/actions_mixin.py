"""Actions and keyboard shortcuts mixin for MainWindow."""
from __future__ import annotations
from typing import TYPE_CHECKING
from pathlib import Path
import os

from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QMessageBox, QFileDialog, QInputDialog

from app.services import (
    export_to_json, export_to_csv, export_to_markdown,
    import_from_json, import_from_csv, merge_imported_games,
    get_undo_stack,
)
from app.ui.widgets import show_success, show_error

if TYPE_CHECKING:
    from .window import MainWindow


class ActionsMixin:
    """Mixin providing keyboard shortcuts and actions for MainWindow."""

    def _setup_shortcuts(self: "MainWindow") -> None:
        """Configure keyboard shortcuts for common actions."""
        # Search focus: Ctrl+F or /
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("/"), self, self._focus_search)

        # Scan: Ctrl+Shift+S
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self._on_scan_clicked)

        # Export: Ctrl+E
        QShortcut(QKeySequence("Ctrl+E"), self, self._show_export_dialog)

        # Import: Ctrl+I
        QShortcut(QKeySequence("Ctrl+I"), self, self._show_import_dialog)

        # Toggle details panel: Ctrl+D
        QShortcut(QKeySequence("Ctrl+D"), self, self._toggle_details_panel)

        # Toggle focus mode: Ctrl+Shift+F
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, self._toggle_focus_mode)

        # Select mode: Ctrl+A (in grid context)
        QShortcut(QKeySequence("Ctrl+A"), self, self._select_all_games)

        # Escape: Exit select mode or clear search
        QShortcut(QKeySequence("Escape"), self, self._on_escape_pressed)

        # Undo: Ctrl+Z
        QShortcut(QKeySequence("Ctrl+Z"), self, self._undo_action)

        # Redo: Ctrl+Shift+Z or Ctrl+Y
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self._redo_action)
        QShortcut(QKeySequence("Ctrl+Y"), self, self._redo_action)

        # Theme Editor: Ctrl+T
        QShortcut(QKeySequence("Ctrl+T"), self, self._open_theme_editor)

        # Layout Customization: Ctrl+L
        QShortcut(QKeySequence("Ctrl+L"), self, self._open_layout_customization)

    def _focus_search(self: "MainWindow") -> None:
        """Focus the search bar."""
        self.search.setFocus()
        self.search.selectAll()

    def _select_all_games(self: "MainWindow") -> None:
        """Select all games (enter select mode if not active)."""
        if not self.select_btn.isChecked():
            self.select_btn.setChecked(True)
            self._toggle_multi_select_mode()
        self.grid.select_all()

    def _on_escape_pressed(self: "MainWindow") -> None:
        """Handle Escape key."""
        if self.select_btn.isChecked():
            self._exit_multi_select_mode()
        elif self.search.hasFocus():
            self.search.clear()
            self.grid.setFocus()

    def _show_export_dialog(self: "MainWindow") -> None:
        """Show export dialog."""
        if not self._all_games:
            QMessageBox.information(self, "Export", "No games to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Library",
            str(Path.home() / "game_library_export"),
            "JSON Files (*.json);;CSV Files (*.csv);;Markdown Files (*.md)"
        )
        if not path:
            return

        try:
            path = Path(path)
            if path.suffix == ".csv":
                count = export_to_csv(self._all_games, path)
            elif path.suffix == ".md":
                count = export_to_markdown(self._all_games, path)
            else:
                count = export_to_json(self._all_games, self._collections, path)

            show_success(f"Exported {count} games to {path.name}")
            self.statusBar().showMessage(f"Exported to {path}", 5000)
        except Exception as e:
            show_error(f"Export failed: {e}")
            QMessageBox.warning(self, "Export Failed", str(e))

    def _show_import_dialog(self: "MainWindow") -> None:
        """Show import dialog."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Library",
            str(Path.home()),
            "JSON Files (*.json);;CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            path = Path(path)
            if path.suffix == ".csv":
                games, metadata = import_from_csv(path)
                collections = []
            else:
                games, collections, metadata = import_from_json(path)

            # Ask for merge strategy
            strategies = ["Skip existing", "Overwrite existing", "Merge fields"]
            choice, ok = QInputDialog.getItem(
                self, "Import Strategy",
                f"Found {len(games)} games. How to handle duplicates?",
                strategies, 0, False
            )
            if not ok:
                return

            strategy_map = {
                "Skip existing": "skip",
                "Overwrite existing": "overwrite",
                "Merge fields": "merge"
            }
            strategy = strategy_map.get(choice, "skip")

            merged, stats = merge_imported_games(self._all_games, games, strategy)
            self._all_games = merged

            # Merge collections if any
            if collections:
                existing_names = {c.name for c in self._collections}
                for coll in collections:
                    if coll.name not in existing_names:
                        self._collections.append(coll)

            self._save_bundle()
            self._apply_search()
            self.sidebar.set_collections(self._collections, self._all_games)

            msg = f"Added: {stats.get('added', 0)}, Updated: {stats.get('updated', 0)}, Skipped: {stats.get('skipped', 0)}"
            show_success(f"Import complete. {msg}")
            self.statusBar().showMessage(msg, 5000)

        except Exception as e:
            show_error(f"Import failed: {e}")
            QMessageBox.warning(self, "Import Failed", str(e))

    def _undo_action(self: "MainWindow") -> None:
        """Undo the last action."""
        undo_stack = get_undo_stack()
        if undo_stack.can_undo():
            cmd = undo_stack.undo()
            if cmd:
                show_success(f"Undone: {cmd.description}")
                self._persist_library()
                self._refresh_list()
        else:
            self.statusBar().showMessage("Nothing to undo", 2000)

    def _redo_action(self: "MainWindow") -> None:
        """Redo the last undone action."""
        undo_stack = get_undo_stack()
        if undo_stack.can_redo():
            cmd = undo_stack.redo()
            if cmd:
                show_success(f"Redone: {cmd.description}")
                self._persist_library()
                self._refresh_list()
        else:
            self.statusBar().showMessage("Nothing to redo", 2000)

    def _open_data_folder(self: "MainWindow") -> None:
        from app.storage.paths import get_app_dir
        path = get_app_dir()
        self._log.info("open_data_folder %s", kv(path=path))
        try:
            os.startfile(str(path))
        except Exception:
            self._log.exception("open_data_folder_failed")


# Need kv for logging
from app.logging_utils import kv
