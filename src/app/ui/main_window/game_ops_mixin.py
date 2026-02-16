"""Game operations mixin for MainWindow."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from datetime import datetime
from pathlib import Path
import os
import webbrowser

from PySide6.QtWidgets import QMessageBox, QInputDialog, QFileDialog

from app.models import Game
from app.services import launch_game
from app.logging_utils import kv

if TYPE_CHECKING:
    from .window import MainWindow


class GameOpsMixin:
    """Mixin providing game operations for MainWindow."""

    def _get_game(self: "MainWindow", game_id: str) -> Optional[Game]:
        """O(1) game lookup by ID using the indexed dict."""
        return self._games_by_id.get(game_id)

    def _add_game(self: "MainWindow", game: Game) -> None:
        """Add a game to the repository."""
        self._repo.add(game)

    def _remove_game_by_id(self: "MainWindow", game_id: str) -> None:
        """Remove a game from the repository."""
        self._repo.remove(game_id)
        self._all_games = self._repo.get_all()

    def _rebuild_game_index(self: "MainWindow") -> None:
        """Sync _all_games list into the repository and rebuild index."""
        self._repo.update_all(self._all_games)
        self._games_by_id = self._repo.index

    def _fix_game(self: "MainWindow", game_id: str, issue_code: str) -> None:
        g = self._get_game(game_id)
        if not g:
            return

        self._log.info("health_fix %s", kv(game_id=game_id, issue=issue_code, title=getattr(g, "title", "")))
        self._selected_game_id = game_id

        try:
            if issue_code.startswith("shortcut"):
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select replacement shortcut",
                    "",
                    "Shortcuts (*.lnk *.url *.html);;All files (*)",
                )
                if not path:
                    return
                from app.services.shortcut_resolver import resolve_shortcut_any

                g.shortcut_path = path
                g.shortcut_type = Path(path).suffix.lower().lstrip(".")
                res = resolve_shortcut_any(Path(path))
                if g.shortcut_type == "lnk":
                    g.backup_target_path = res.target_path
                    g.backup_args = res.args
                    g.backup_working_dir = res.working_dir
                    g.confidence = "high" if res.target_path else "low"
                elif g.shortcut_type == "url":
                    g.confidence = "high" if res.url else "low"
                else:
                    g.confidence = "high"
                self.statusBar().showMessage("Shortcut updated", 3000)

            elif issue_code in ("archive_folder_missing",):
                folder = QFileDialog.getExistingDirectory(self, "Select archive folder")
                if folder:
                    g.archive_folder_path = folder
                    self.statusBar().showMessage("Archive folder set", 3000)
                else:
                    self._focus_details(g, "Pick archive folder", field="archive_folder")
                    return

            elif issue_code in ("archive_compressed_missing",):
                path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select compressed archive",
                    "",
                    "Archives (*.zip *.rar *.7z *.7zip *.tar *.gz);;All files (*)",
                )
                if path:
                    g.compressed_archive_path = path
                    self.statusBar().showMessage("Compressed archive set", 3000)
                else:
                    self._focus_details(g, "Pick compressed archive", field="compressed")
                    return

            elif issue_code in ("version_older", "version_newer"):
                self._jump_to_updates(game_id)

            elif issue_code == "source_missing":
                self._details_visible = True
                self.details_toggle.setChecked(True)
                self._user_hid_details = False
                self._apply_details_visibility()
                self.details.show_game(g)
                self._focus_details(g, "Paste source URL here", field="source")

            elif issue_code == "target_missing":
                self.statusBar().showMessage("Pick new target via shortcut refresh", 3000)
                self._fix_game(game_id, "shortcut_missing_all")
                return

            elif issue_code == "url_broken":
                self._details_visible = True
                self.details_toggle.setChecked(True)
                self._apply_details_visibility()
                self.details.show_game(g)
                self._focus_details(g, "Update source URL or shortcut target")

            # persist and refresh
            self._save_bundle()
            self._apply_search()
            if self.health.isVisible():
                self.health.set_games(self._all_games)
            self.details.show_game(g)

        except Exception as e:
            QMessageBox.warning(self, "Fix failed", str(e))

    def _on_grid_context_action(self: "MainWindow", game_id: str, action: str) -> None:
        g = self._get_game(game_id)
        if not g:
            return

        self._selected_game_id = game_id
        self.details.show_game(g)

        if action == "add_to_collection":
            self._add_selected_to_collection()
            return

        if action == "open_folder":
            self._open_shortcut_folder(g.shortcut_path)
            return

        if action == "open_file":
            try:
                os.startfile(g.shortcut_path)
            except Exception as e:
                QMessageBox.warning(self, "Open shortcut failed", str(e))
            return

        if action == "rename":
            new_name, ok = QInputDialog.getText(self, "Rename display name", "New name:", text=g.title)
            if not ok:
                return
            new_name = new_name.strip()
            if not new_name:
                return
            g.title = new_name
            self._save_bundle()
            self._apply_search()
            self.details.show_game(g)
            return

        if action == "remove":
            self._remove_game(game_id)
            return

        # Handle status changes from inline card interactions
        if action.startswith("set_status_"):
            new_status = action.replace("set_status_", "")
            if new_status in ["backlog", "playing", "finished", "dropped"]:
                g.status = new_status
                self._persist_library()
                self._apply_search()
                self.details.show_game(g)
            return

    def _on_game_selected(self: "MainWindow", game_id: str) -> None:
        self._selected_game_id = game_id
        g = self._get_game(game_id)
        self.details.show_game(g)
        self.add_to_collection_btn.setEnabled(True)
        self._ensure_details_visible()
        # Open game homepage
        if g is not None:
            self._show_game_homepage(game_id)

    def _on_game_play(self: "MainWindow", game_id: str) -> None:
        g = self._get_game(game_id)
        if g is None:
            return

        ok, info = launch_game(g)

        if ok:
            g.launch_count += 1
            g.last_played = datetime.now()
            self._persist_library()
            self.details.show_game(g)
            self.statusBar().showMessage(f"{g.title}: {info}", 5000)
        else:
            QMessageBox.warning(self, "Launch failed", f"{g.title}\n\n{info}")

    def _on_rating_changed(self: "MainWindow", game_id: str, rating) -> None:
        g = self._get_game(game_id)
        if g:
            g.rating = rating
            self._save_bundle()
            self._apply_search()
            self.details.show_game(g)

    def _on_game_changed(self: "MainWindow", game_id: str) -> None:
        g = self._get_game(game_id)
        if g is None:
            return
        if self._log_rate.allow("game_changed", 400):
            self._log.info("game_changed %s", kv(game_id=game_id, title=getattr(g, "title", "")))

        self.details.apply_edits_to_game()
        self._persist_library()
        self._apply_search()
        self._selected_game_id = game_id

    def _remove_game(self: "MainWindow", game_id: str) -> None:
        if QMessageBox.question(self, "Remove", "Remove this entry from the library?") != QMessageBox.Yes:
            return

        self._remove_game_by_id(game_id)
        self._rebuild_search_cache()
        self._apply_search()
        self._persist_library()

        if self.health.isVisible():
            self.health.set_games(self._all_games)

    def _open_shortcut_folder(self: "MainWindow", shortcut_path: str) -> None:
        try:
            target = None
            if self._selected_game_id:
                g = self._get_game(self._selected_game_id)
                if g and g.game_folder_path and Path(g.game_folder_path).exists():
                    target = Path(g.game_folder_path)
            if not target:
                if not shortcut_path:
                    raise FileNotFoundError("No shortcut path stored.")
                p = Path(shortcut_path)
                target = p.parent if p.exists() else p.parent
            os.startfile(str(target))
        except Exception as e:
            QMessageBox.warning(self, "Open folder failed", str(e))

    def _open_source_for_game(self: "MainWindow", game_id: str) -> None:
        g = self._get_game(game_id)
        if g and g.source_url:
            webbrowser.open(g.source_url)

    def _mark_installed_from_source(self: "MainWindow", game_id: str) -> None:
        g = self._get_game(game_id)
        if not g:
            return
        if not g.source_version_raw:
            QMessageBox.information(self, "No source version", "Run Check Updates first to fetch source version.")
            return
        g.installed_version_raw = g.source_version_raw
        self._save_bundle()
        self._apply_search()
        self.details.show_game(g)
        if self.updates.isVisible():
            self.updates.set_games(self._all_games)
        self.statusBar().showMessage(f"Marked installed to {g.installed_version_raw}", 4000)
        self._settings["updates_filter"] = self.updates._filter_mode
        self._persist_settings()

    def _resolve_issue(self: "MainWindow", game_id: str, code: str) -> None:
        self._ignored_health.setdefault(game_id, set()).add(code)
        if self.health.isVisible():
            self.health.set_ignored(self._ignored_health)
        self.statusBar().showMessage("Issue marked resolved", 2000)

    def _ignore_issue(self: "MainWindow", game_id: str, code: str) -> None:
        self._ignored_health.setdefault(game_id, set()).add(code)
        if self.health.isVisible():
            self.health.set_ignored(self._ignored_health)
        self.statusBar().showMessage("Issue ignored", 2000)

    def _focus_details(self: "MainWindow", game: Game, hint: str, field: Optional[str] = None) -> None:
        self._details_visible = True
        self.details_toggle.setChecked(True)
        self._apply_details_visibility()
        self.details.show_game(game)
        self.details.show_hint(hint)
        if field == "archive_folder":
            self.details.archive_folder.setFocus()
        elif field == "compressed":
            self.details.compressed_path.setFocus()
        else:
            self.details.source_url.setFocus()

    def _jump_to_updates(self: "MainWindow", game_id: str) -> None:
        self.sidebar.set_selected("updates")
        self.updates.set_games(self._all_games)
        self.updates.highlight_game(game_id)

    # ---- Game Homepage navigation ----

    def _show_game_homepage(self: "MainWindow", game_id: str) -> None:
        """Navigate to the game homepage view for a specific game."""
        g = self._get_game(game_id)
        if g is None:
            return

        self._log.info("game_homepage_open %s", kv(game_id=game_id, title=g.title))

        # Try to get cached thread info if source URL exists
        thread_info = None
        if g.source_url:
            from app.services.f95_api import (
                extract_thread_id, get_cached_thread_info,
            )
            tid = g.f95_thread_id or extract_thread_id(g.source_url)
            if tid:
                thread_info = get_cached_thread_info(tid)

        # Get custom XPaths from settings if available
        from app.models.custom_paths import CustomXPaths
        custom_xpaths = None
        custom_data = self._settings.get("custom_xpaths")
        if isinstance(custom_data, dict):
            custom_xpaths = CustomXPaths.from_dict(custom_data)

        # Hide grid/health/updates and show homepage
        self.grid.hide()
        self.health.hide()
        self.updates.hide()
        self.game_home.show()

        # Hide the toolbar and filter rows for a clean homepage look
        self._homepage_toolbar_visible = True
        # Update content title
        self.content_title.setText(g.title)

        # Populate homepage
        self.game_home.show_game(g, thread_info=thread_info, custom_xpaths=custom_xpaths)

    def _on_homepage_back(self: "MainWindow") -> None:
        """Navigate back from game homepage to the grid view."""
        self._log.info("game_homepage_back")
        self.game_home.hide()
        self.grid.show()
        # Restore content title
        if self._active_collection_id:
            c = self._get_collection(self._active_collection_id)
            self.content_title.setText(c.name if c else "Collection")
        else:
            self.content_title.setText("All Games")

    def _on_homepage_download(self: "MainWindow", game_id: str, url: str) -> None:
        """Handle download request from game homepage."""
        import webbrowser as _wb
        self._log.info("homepage_download %s", kv(game_id=game_id, url=url[:80]))
        # Open in browser as a fallback; the download manager can be wired here
        _wb.open(url)
        self.statusBar().showMessage(f"Opening download link\u2026", 3000)
