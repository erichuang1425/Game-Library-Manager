"""Update check operations mixin for MainWindow."""
from __future__ import annotations
from typing import TYPE_CHECKING
import webbrowser

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from app.ui.dialogs import UpdateWorker
from app.ui.widgets import show_success, show_error
from app.logging_utils import kv

if TYPE_CHECKING:
    from .window import MainWindow


class UpdateMixin:
    """Mixin providing update check operations for MainWindow."""

    def _on_check_updates_fetch(self: "MainWindow") -> None:
        if not self._all_games:
            QMessageBox.information(self, "No games", "No games loaded. Scan or load a library first.")
            return
        self._log.info("updates_check_start %s", kv(event="updates", mode="fetch"))
        self._start_update_thread()

    def _on_check_updates_open_only(self: "MainWindow") -> None:
        if not self._all_games:
            QMessageBox.information(self, "No games", "No games loaded. Scan or load a library first.")
            return
        count = 0
        for g in self._all_games:
            if g.source_url:
                webbrowser.open(g.source_url)
                count += 1
        self.statusBar().showMessage(f"Opened {count} source pages", 5000)
        self._log.info("updates_open_only %s", kv(count=count))

    def _start_update_thread(self: "MainWindow") -> None:
        if self._update_thread:
            return
        self._update_progress_dialog = QProgressDialog("Checking updates…", "Cancel", 0, 0, self)
        self._update_progress_dialog.setWindowTitle("Updates")
        self._update_progress_dialog.setWindowModality(Qt.WindowModal)
        self._update_progress_dialog.canceled.connect(self._cancel_updates)
        self._update_progress_dialog.show()

        self._update_thread = QThread()
        self._update_worker = UpdateWorker(self._all_games)
        self._update_worker.moveToThread(self._update_thread)

        # Queued connections to keep GUI work on the main thread.
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.progress.connect(self._on_update_progress, Qt.QueuedConnection)
        self._update_worker.finished.connect(self._on_update_finished, Qt.QueuedConnection)
        self._update_worker.failed.connect(self._on_update_failed, Qt.QueuedConnection)

        self._update_thread.start()

    def _cancel_updates(self: "MainWindow") -> None:
        if self._update_worker:
            self._update_worker.cancel()
        if self._update_progress_dialog:
            self._update_progress_dialog.setLabelText("Cancelling…")
            self._update_progress_dialog.setCancelButton(None)

    def _on_update_progress(self: "MainWindow", msg: str, done: int, total: int) -> None:
        if self._update_progress_dialog:
            if total > 0:
                self._update_progress_dialog.setRange(0, total)
                self._update_progress_dialog.setValue(done)
            self._update_progress_dialog.setLabelText(msg)
        if self._log_rate.allow("updates_progress_log", 500):
            self._log.debug("updates_progress %s", kv(done=done, total=total, msg=msg))

    def _on_update_failed(self: "MainWindow", err: str) -> None:
        self._cleanup_update_thread()
        self._log.error("updates_failed %s", kv(err=err))
        self._notify_async_error(f"Updates failed: {err}")

    def _on_update_finished(self: "MainWindow", results: list) -> None:
        self._cleanup_update_thread()
        # save mutated games
        self._save_bundle()
        self._apply_search()
        if self.updates.isVisible():
            self.updates.set_games(self._all_games)

        ok = sum(1 for r in results if r.get("status") == "ok")
        errs = [r for r in results if r.get("status") == "error"]
        self.statusBar().showMessage(f"Updates checked: {ok} ok, {len(errs)} errors", 8000)
        self._pulse_widget(self.check_updates_btn)
        # Toast notification
        if errs:
            show_error(f"Update check: {ok} ok, {len(errs)} failed")
            lines = "\n".join(f"- {r.get('error', 'Unknown error')}" for r in errs[:10])
            QMessageBox.warning(self, "Some checks failed", lines)
        else:
            show_success(f"Update check complete: {ok} sources checked")
        self._log.info("updates_done %s", kv(ok=ok, errors=len(errs), total=len(results)))

    def _cleanup_update_thread(self: "MainWindow") -> None:
        if self._update_progress_dialog:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None
        if self._update_thread:
            self._update_thread.quit()
            self._update_thread.wait()
            self._update_thread = None
        self._update_worker = None
        self._settings["updates_filter"] = self.updates._filter_mode
        self._settings["updates_density"] = self.updates._density
        self._persist_settings()
