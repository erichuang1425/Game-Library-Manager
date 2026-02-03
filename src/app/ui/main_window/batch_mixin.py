"""Batch operations mixin for MainWindow."""
from __future__ import annotations
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox, QInputDialog

from app.ui.widgets import show_success

if TYPE_CHECKING:
    from .window import MainWindow


class BatchMixin:
    """Mixin providing batch/multi-select operations for MainWindow."""

    def _toggle_multi_select_mode(self: "MainWindow") -> None:
        """Toggle multi-select mode on/off."""
        enabled = self.select_btn.isChecked()
        self.grid.set_multi_select_mode(enabled)
        if enabled:
            self.batch_toolbar.show_toolbar()
        else:
            self.batch_toolbar.hide_toolbar()
            self.grid.clear_selection()

    def _exit_multi_select_mode(self: "MainWindow") -> None:
        """Exit multi-select mode."""
        self.select_btn.setChecked(False)
        self._toggle_multi_select_mode()

    def _on_selection_changed(self: "MainWindow", game_ids: list) -> None:
        """Handle selection changes in the grid."""
        self.batch_toolbar.update_selection(game_ids)

    def _on_batch_set_status(self: "MainWindow", status: str, game_ids: list) -> None:
        """Set status for multiple games."""
        changed = 0
        for game_id in game_ids:
            g = self._get_game(game_id)
            if g and g.status != status:
                g.status = status
                changed += 1
        if changed:
            self._save_bundle()
            self._apply_search()
            show_success(f"Updated status to '{status}' for {changed} games")

    def _on_batch_add_tag(self: "MainWindow", tag: str, game_ids: list) -> None:
        """Add a tag to multiple games."""
        changed = 0
        for game_id in game_ids:
            g = self._get_game(game_id)
            if g:
                existing = list(g.tags) if g.tags else []
                if tag not in existing:
                    existing.append(tag)
                    g.tags = existing
                    changed += 1
        if changed:
            self._save_bundle()
            self._apply_search()
            show_success(f"Added tag '{tag}' to {changed} games")

    def _on_batch_add_to_collection(self: "MainWindow", game_ids: list) -> None:
        """Add multiple games to a collection."""
        manual = [c for c in self._collections if c.type == "manual"]
        if not manual:
            QMessageBox.information(self, "No Collections", "Create a collection first.")
            return

        names = [c.name for c in manual]
        chosen, ok = QInputDialog.getItem(self, "Add to Collection", "Choose collection:", names, 0, False)
        if not ok:
            return

        target = next((c for c in manual if c.name == chosen), None)
        if not target:
            return

        added = 0
        for game_id in game_ids:
            if game_id not in target.game_ids:
                target.game_ids.append(game_id)
                added += 1

        if added:
            self._save_bundle()
            self.sidebar.set_collections(self._collections, self._all_games)
            show_success(f"Added {added} games to '{chosen}'")
