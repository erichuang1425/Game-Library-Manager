"""UI helpers mixin for MainWindow."""
from __future__ import annotations
from typing import TYPE_CHECKING
import time

from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QVBoxLayout, QLabel,
    QProgressBar, QGraphicsOpacityEffect, QMessageBox,
)

from app.storage import settings_json_path, save_settings
from app.ui.theme import apply_theme
from app.ui.dialogs import PreferencesDialog
from app.logging_utils import kv

if TYPE_CHECKING:
    from .window import MainWindow


class UIMixin:
    """Mixin providing UI helper methods for MainWindow."""

    def _render(self: "MainWindow") -> None:
        start = time.perf_counter()
        self._render_count += 1
        self.grid.set_games(self._filtered)
        self.add_to_collection_btn.setEnabled(self._selected_game_id is not None)
        if self._selected_game_id is not None:
            g = self._get_game(self._selected_game_id)
            self.details.show_game(g)
            self._ensure_details_visible()
        self._apply_quick_filter_buttons()
        self._update_view_mode_buttons()
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        if self._render_count == 1:
            self._set_startup_status("Rendering grid…")
            self._log.info("main_render_first %s", kv(duration_ms=duration_ms, filtered=len(self._filtered)))
            self._hide_startup_overlay()
        elif self._log_rate.allow("main_render", interval_ms=800):
            self._log.debug("main_render %s", kv(duration_ms=duration_ms, filtered=len(self._filtered)))

    def _notify_async_error(self: "MainWindow", text: str) -> None:
        """Non-blocking error toast for background tasks."""
        try:
            box = QMessageBox(QMessageBox.Critical, "Error", f"{text}\nSee manager.log.", QMessageBox.Ok, self)
            box.setWindowModality(Qt.NonModal)
            box.setAttribute(Qt.WA_DeleteOnClose)
            box.show()
        except Exception:
            self._log.exception("toast_error_failed")

    def _update_view_mode_buttons(self: "MainWindow") -> None:
        self.view_comfort.setChecked(self._view_mode == "comfortable")
        self.view_compact.setChecked(self._view_mode == "compact")

    def _pulse_widget(self: "MainWindow", widget) -> None:
        if widget is None:
            return
        eff = widget.graphicsEffect()
        if not isinstance(eff, QGraphicsOpacityEffect):
            eff = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(130)
        anim.setStartValue(0.6)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutQuad)
        anim.start()
        widget._pulse_anim = anim

    def _on_view_mode_changed(self: "MainWindow") -> None:
        self._view_mode = "compact" if self.sender() == self.view_compact else "comfortable"
        self._pulse_widget(self.sender())
        self.grid.set_view_mode(self._view_mode)
        self._settings["view_mode"] = self._view_mode
        self._persist_settings()
        self._update_view_mode_buttons()

    def _toggle_focus_mode(self: "MainWindow") -> None:
        self._focus_mode = self.focus_btn.isChecked()
        self._pulse_widget(self.focus_btn)
        self._settings["focus_mode"] = self._focus_mode
        self._persist_settings()
        self._apply_focus_mode()

    def _apply_focus_mode(self: "MainWindow", initial: bool = False) -> None:
        if self._focus_mode:
            self._details_widget.hide()
            self._splitter.setSizes([220, max(800, self.width() - 260), 0])
        else:
            self._details_widget.show()
            if not initial:
                sizes = self._settings.get("splitter_sizes")
                if isinstance(sizes, list) and len(sizes) == 3:
                    self._splitter.setSizes([int(x) for x in sizes])
            else:
                self._apply_details_visibility(initial=True)
        self.details_toggle.setEnabled(not self._focus_mode)
        self.grid.refresh()

    def _on_splitter_moved(self: "MainWindow", *_args) -> None:
        sizes = self._splitter.sizes()
        if self._details_visible and not self._focus_mode and len(sizes) == 3 and sizes[2] < 260:
            delta = 260 - sizes[2]
            sizes[2] = 260
            sizes[1] = max(400, sizes[1] - delta)
            self._splitter.setSizes(sizes)
        self._settings["splitter_sizes"] = sizes
        self._persist_settings()

    def _apply_filter_combo_defaults(self: "MainWindow") -> None:
        def set_if(combo: QComboBox, value: str):
            for i in range(combo.count()):
                if combo.itemText(i).lower() == value:
                    combo.setCurrentIndex(i)
                    break
        set_if(self.status_filter, self._status_filter)
        set_if(self.conf_filter, self._confidence_filter)
        set_if(self.type_filter, self._type_filter)
        self._apply_quick_filter_buttons()

    def _persist_settings(self: "MainWindow") -> None:
        save_settings(settings_json_path(), self._settings)

    def _save_updates_prefs(self: "MainWindow") -> None:
        self._settings["updates_filter"] = self.updates._filter_mode
        self._settings["updates_density"] = self.updates._density
        self._persist_settings()

    def _save_health_prefs(self: "MainWindow") -> None:
        self._settings["health_filter"] = self.health._filter_mode
        self._settings["health_density"] = self.health._density
        self._persist_settings()

    def _ensure_details_visible(self: "MainWindow") -> None:
        if self._focus_mode:
            return
        if not self._details_visible and self._details_on_selection and not self._user_hid_details:
            self._details_visible = True
            self.details_toggle.setChecked(True)
            self._settings["details_visible"] = True
            self._persist_settings()
        self._apply_details_visibility()

    def _apply_details_visibility(self: "MainWindow", initial: bool = False) -> None:
        if self._details_visible and not self._focus_mode:
            self._details_widget.show()
            if not initial:
                self._splitter.setSizes([220, max(600, self.width() - 560), 340])
        else:
            self._details_widget.hide()
            if not initial:
                self._splitter.setSizes([220, max(700, self.width() - 220), 0])
        self.grid.refresh()

    def _reset_layout(self: "MainWindow") -> None:
        self._splitter.setSizes([200, 900, 320 if self._details_visible else 0])
        self._settings["splitter_sizes"] = self._splitter.sizes()
        self._persist_settings()
        self.grid.refresh()

    def _safe_refresh_ui(self: "MainWindow") -> None:
        """Re-apply palette/QSS/font only; avoid rebuilding views."""
        self._log.info("safe_refresh_ui %s", kv(event="safe_refresh"))
        apply_theme(QApplication.instance(), self._theme, self._font_family, self._font_scale)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def _apply_responsive_type(self: "MainWindow") -> None:
        """Step-based responsive typography based on window width buckets."""
        width = self.width()
        bucket = "normal"
        if width < 1100:
            bucket = "small"
        elif width > 1500:
            bucket = "large"
        if bucket == self._type_scale_bucket:
            return
        self._type_scale_bucket = bucket
        self.grid.set_type_scale(bucket)
        font_delta = {"small": -1, "normal": 0, "large": 1}[bucket]
        self._bump_table_font(self.updates.table, base=10 + font_delta)
        self._bump_table_font(self.health.table, base=10 + font_delta)

    def _bump_table_font(self: "MainWindow", table, base: int) -> None:
        f = table.font()
        f.setPointSize(max(8, base))
        table.setFont(f)
        header = table.horizontalHeader()
        hf = header.font()
        hf.setPointSize(max(8, base))
        header.setFont(hf)
        row_h = 40 if base >= 11 else 34
        for r in range(table.rowCount()):
            table.setRowHeight(r, row_h)

    def _guard_top_level_windows(self: "MainWindow") -> None:
        """Debug guardrail to catch accidental top-level widgets."""
        from app.ui.main_window.window import DEBUG_GUARDS
        if not DEBUG_GUARDS:
            return
        allowed_types = (type(self), PreferencesDialog)
        for w in QApplication.topLevelWidgets():
            if isinstance(w, allowed_types):
                continue
            name = w.__class__.__name__
            title = getattr(w, "windowTitle", lambda: "")()
            self._log.error("Unexpected top-level window: %s | title=%s", name, title)
            try:
                w.close()
            except Exception:
                pass

    # ---------- startup overlay ----------
    def _build_startup_overlay(self: "MainWindow", host) -> None:
        try:
            overlay = QFrame(host)
            overlay.setStyleSheet("background: rgba(10,10,14,180); border-radius: 10px;")
            overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            overlay.hide()
            layout = QVBoxLayout(overlay)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(12)
            title = QLabel("Game Library Manager")
            title.setStyleSheet("color: white; font-size: 18px; font-weight: 700;")
            status = QLabel("Starting…")
            status.setStyleSheet("color: #dce7ff; font-size: 12px;")
            bar = QProgressBar()
            bar.setRange(0, 0)
            bar.setTextVisible(False)
            layout.addStretch(1)
            layout.addWidget(title, 0, Qt.AlignCenter)
            layout.addWidget(status, 0, Qt.AlignCenter)
            layout.addWidget(bar)
            layout.addStretch(2)
            self._startup_overlay = overlay
            self._startup_status = status
            overlay.show()
            self._update_startup_overlay_geometry()
        except Exception:
            self._startup_overlay = None
            self._startup_status = None

    def _set_startup_status(self: "MainWindow", text: str) -> None:
        if self._startup_status:
            self._startup_status.setText(text)
            if self._startup_overlay:
                self._startup_overlay.raise_()
        if self._log_rate.allow("startup_status", 400):
            self._log.info("startup_status %s", kv(text=text))

    def _hide_startup_overlay(self: "MainWindow") -> None:
        if self._startup_overlay and not self._first_render_done:
            self._first_render_done = True
            self._startup_overlay.hide()

    def _update_startup_overlay_geometry(self: "MainWindow") -> None:
        if not self._startup_overlay:
            return
        try:
            self._startup_overlay.setGeometry(self.centralWidget().geometry())
        except Exception:
            pass
