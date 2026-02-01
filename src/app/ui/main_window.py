from __future__ import annotations
from typing import List, Optional
from datetime import datetime
import uuid

from PySide6.QtCore import Qt, QThread, QEasingCurve, QPropertyAnimation
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QFrame,
    QPushButton, QSplitter, QInputDialog, QFileDialog, QMessageBox, QProgressDialog, QMenu, QToolButton, QGraphicsOpacityEffect, QProgressBar
)
from PySide6.QtWidgets import QApplication

from app.models import Game, Collection
from app.storage import (
    library_json_path, settings_json_path,
    load_library, save_library, load_settings, save_settings,
    load_library_bundle, save_library_bundle
)
from app.logging_utils import connect_safe
from app.ui.widgets import GameGrid, DetailsPanel, FilterChipsBar, build_filter_chips, show_success, show_error, BatchToolbar
from app.ui.widgets.library_sidebar import LibrarySidebar
from app.ui.dialogs import ScanWorker, UpdateWorker
from app.ui.dialogs import PreferencesDialog
from app.ui.dialogs.bulk_source_import import BulkSourceImportDialog
from app.services import (
    find_duplicate_shortcuts_in_root, move_duplicates_to_quarantine, 
    launch_game, merge_scanned_into_library, apply_collection, parse_version, compare_versions,
    pixmap_for_path, pixmap_for_game
)
from app.services.version_parser import CompareResult
import os
import sys
import subprocess
from pathlib import Path
import time
from app.ui.widgets import HealthChecksWidget, UpdatesWidget
from app.ui.theme import apply_theme, THEMES, FONTS, FONT_SCALES, current_theme
from app.logging_utils import get_logger, kv, RateLimiter, wrap_slot

DEBUG_GUARDS = os.environ.get("GLM_GUARDS", "0") == "1"

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Game Library Manager")
        self.resize(1200, 750)
        self._log = get_logger("ui.main")
        self._log_rate = RateLimiter()
        self._render_count = 0
        self._c = lambda sig, fn, label, **ctx: connect_safe(sig, fn, self._log, label, **ctx)
        self._t0 = time.perf_counter()
        self._log.info("startup_init %s", kv(ts=time.strftime('%H:%M:%S')))
        # ensure startup overlay attrs exist before any status updates
        self._startup_overlay = None
        self._startup_status = None
        self._first_render_done = False

        # state
        settings_start = time.perf_counter()
        self._settings = load_settings(settings_json_path())
        self._log.info(
            "startup_settings_loaded %s",
            kv(duration_ms=round((time.perf_counter() - settings_start) * 1000, 1)),
        )
        self._root_folder: str = self._settings.get("root_folder", "")
        self._view_mode: str = self._settings.get("view_mode", "comfortable")
        self._focus_mode: bool = self._settings.get("focus_mode", False)
        self._quick_filter: str = self._settings.get("quick_filter", "all")
        self._tag_filter: Optional[str] = self._settings.get("tag_filter")
        self._status_filter: str = self._settings.get("status_filter", "all")
        self._confidence_filter: str = self._settings.get("confidence_filter", "all")
        self._type_filter: str = self._settings.get("type_filter", "all")
        self._sort_by: str = self._settings.get("sort_by", "title")
        self._updates_filter: str = self._settings.get("updates_filter", "all")
        self._updates_density: str = self._settings.get("updates_density", "comfortable")
        self._health_filter: str = self._settings.get("health_filter", "all")
        self._health_density: str = self._settings.get("health_density", "comfortable")
        self._details_visible: bool = self._settings.get("details_visible", False)
        self._details_on_launch: bool = self._settings.get("details_on_launch", False)
        self._details_on_selection: bool = self._settings.get("details_on_selection", True)
        self._user_hid_details: bool = False
        self._theme: str = self._settings.get("theme", "dark")
        self._font_family: str = self._settings.get("font_family", "Segoe UI")
        self._font_scale: str = self._settings.get("font_scale", "default")

        lib_start = time.perf_counter()
        self._all_games, self._collections = load_library_bundle(library_json_path())
        self._active_collection_id: Optional[str] = None
        self._log.info(
            "startup_library_loaded %s",
            kv(count=len(self._all_games), collections=len(self._collections), duration_ms=round((time.perf_counter() - lib_start) * 1000, 1)),
        )
        self._set_startup_status("Building UI…")
        self._log.info("data_paths %s", kv(library=library_json_path(), settings=settings_json_path()))

        self._filtered: List[Game] = list(self._all_games)
        self._selected_game_id: Optional[str] = None
        self._ignored_health: dict[str, set[str]] = {}

        # apply theme + font early so widgets pick them up
        apply_theme(QApplication.instance(), self._theme, self._font_family, self._font_scale)

        # scan worker handles
        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._progress_dialog: Optional[QProgressDialog] = None
        self._update_thread: Optional[QThread] = None
        self._update_worker: Optional[UpdateWorker] = None
        self._update_progress_dialog: Optional[QProgressDialog] = None
        ui_build_start = time.perf_counter()
        root = QWidget()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # startup overlay (non-blocking)
        self._build_startup_overlay(root)
        self._set_startup_status("Loading library…")

        # --- Top bar ---
        topbar = QHBoxLayout()
        self.title_label = QLabel("Library")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600;")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games, tags, notes…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(350)
        self.search.textChanged.connect(self._apply_search)

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setMinimumWidth(72)
        self.scan_btn.setToolTip("Scan shortcuts root")
        self.scan_btn.clicked.connect(self._on_scan_clicked)

        self.check_updates_btn = QToolButton()
        self.check_updates_btn.setText("Check Updates")
        self.check_updates_btn.setPopupMode(QToolButton.MenuButtonPopup)
        self.check_updates_btn.setMinimumWidth(120)
        self.check_updates_btn.setToolTip("Check updates or open sources")
        self.check_updates_btn.clicked.connect(self._on_check_updates_fetch)
        updates_menu = QMenu(self)
        act_fetch = QAction("Background fetch & parse", self)
        act_open = QAction("Open sources only", self)
        act_fetch.triggered.connect(self._on_check_updates_fetch)
        act_open.triggered.connect(self._on_check_updates_open_only)
        updates_menu.addAction(act_fetch)
        updates_menu.addAction(act_open)
        self.check_updates_btn.setMenu(updates_menu)

        tools_menu = QMenu(self)
        act_bulk = QAction("Bulk Source URLs…", self)
        act_bulk.triggered.connect(self._open_bulk_sources)
        act_scan = QAction("Scanner", self)
        act_scan.triggered.connect(self._open_scanner_project)
        act_settings = QAction("Settings", self)
        act_settings.triggered.connect(self._open_preferences)
        act_data = QAction("Open Data Folder", self)
        act_data.triggered.connect(self._open_data_folder)
        tools_menu.addAction(act_bulk)
        tools_menu.addAction(act_scan)
        tools_menu.addSeparator()
        tools_menu.addAction(act_settings)
        tools_menu.addAction(act_data)
        self.tools_btn = QToolButton()
        self.tools_btn.setText("Tools")
        self.tools_btn.setMinimumWidth(80)
        self.tools_btn.setToolTip("Tools and settings")
        self.tools_btn.setPopupMode(QToolButton.InstantPopup)
        self.tools_btn.setMenu(tools_menu)

        self.new_collection_btn = QPushButton("New Collection")
        self.new_collection_btn.setMinimumWidth(120)
        self.new_collection_btn.setToolTip("Create a collection")
        self.new_collection_btn.clicked.connect(self._new_collection)

        self.add_to_collection_btn = QPushButton("Add to Collection")
        self.add_to_collection_btn.setMinimumWidth(130)
        self.add_to_collection_btn.setToolTip("Add selected game to collection")
        self.add_to_collection_btn.clicked.connect(self._add_selected_to_collection)
        self.add_to_collection_btn.setEnabled(False)

        self.rename_collection_btn = QPushButton("Rename Collection")
        self.rename_collection_btn.setMinimumWidth(130)
        self.rename_collection_btn.setToolTip("Rename selected collection")
        self.rename_collection_btn.clicked.connect(self._rename_active_collection)
        self.rename_collection_btn.setEnabled(False)

        self.delete_collection_btn = QPushButton("Delete Collection")
        self.delete_collection_btn.setMinimumWidth(120)
        self.delete_collection_btn.setToolTip("Delete selected collection")
        self.delete_collection_btn.clicked.connect(self._delete_active_collection)
        self.delete_collection_btn.setEnabled(False)


        topbar.addWidget(self.title_label)
        topbar.addStretch(1)
        topbar.addWidget(self.search)
        topbar.addWidget(self.scan_btn)
        topbar.addWidget(self.check_updates_btn)
        topbar.addWidget(self.tools_btn)
        topbar.addWidget(self.new_collection_btn)
        topbar.addWidget(self.add_to_collection_btn)
        topbar.addWidget(self.rename_collection_btn)
        topbar.addWidget(self.delete_collection_btn)
        outer.addLayout(topbar)

        # --- Main split: sidebar | content | details ---
        splitter = QSplitter(Qt.Horizontal)

        # Left sidebar
        self.sidebar = LibrarySidebar()
        self.sidebar.nav_changed.connect(wrap_slot(self._log, "nav_changed")(self._on_nav_changed))
        self.sidebar.set_games(self._all_games)

        # Center content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content.setMinimumWidth(520)

        self.content_title = QLabel("All Games")
        self.content_title.setStyleSheet("font-size: 14px; font-weight: 600;")

        # Filter / controls bar
        controls = QHBoxLayout()
        controls.setSpacing(8)
        # quick pills
        self.pill_all = QPushButton("All")
        self.pill_missing = QPushButton("Missing")
        self.pill_updates = QPushButton("Updates")
        self.pill_source = QPushButton("Source")
        for btn in (self.pill_all, self.pill_missing, self.pill_updates, self.pill_source):
            btn.setCheckable(True)
            btn.clicked.connect(self._on_quick_filter)
            controls.addWidget(btn)
        controls.addSpacing(12)

        self.tag_filter_label = QLabel("")
        self.tag_filter_label.setStyleSheet("color: #7ca1ff; font-weight: 600;")
        self.tag_filter_label.hide()
        self.clear_tag_btn = QPushButton("Clear tag")
        self.clear_tag_btn.clicked.connect(self._clear_tag_filter)
        self.clear_tag_btn.setVisible(False)
        controls.addWidget(self.tag_filter_label)
        controls.addWidget(self.clear_tag_btn)

        # dropdown filters
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Backlog", "Playing", "Finished", "Dropped"])
        status_label = self._status_filter.capitalize() if self._status_filter != "all" else "All"
        self.status_filter.setCurrentText(status_label)
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        controls.addWidget(QLabel("Status:"))
        controls.addWidget(self.status_filter)

        self.conf_filter = QComboBox()
        self.conf_filter.addItems(["All", "High", "Medium", "Low"])
        confidence_label = self._confidence_filter.capitalize() if self._confidence_filter != "all" else "All"
        self.conf_filter.setCurrentText(confidence_label)
        self.conf_filter.currentTextChanged.connect(self._on_filter_changed)
        controls.addWidget(QLabel("Confidence:"))
        controls.addWidget(self.conf_filter)

        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "lnk", "url", "html"])
        self.type_filter.setCurrentText(self._type_filter if self._type_filter != "all" else "All")
        self.type_filter.currentTextChanged.connect(self._on_filter_changed)
        controls.addWidget(QLabel("Type:"))
        controls.addWidget(self.type_filter)

        # sort
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Title", "Last Played", "Rating", "Launch Count", "Last Checked"])
        self.sort_combo.setCurrentText({
            "title": "Title",
            "last_played": "Last Played",
            "rating": "Rating",
            "launch_count": "Launch Count",
            "last_checked": "Last Checked"
        }.get(self._sort_by, "Title"))
        self.sort_combo.currentTextChanged.connect(self._on_sort_changed)
        controls.addWidget(QLabel("Sort:"))
        controls.addWidget(self.sort_combo)

        # view toggle
        self.view_comfort = QPushButton("Comfortable")
        self.view_compact = QPushButton("Compact")
        for btn in (self.view_comfort, self.view_compact):
            btn.setCheckable(True)
            btn.clicked.connect(self._on_view_mode_changed)
        controls.addWidget(self.view_comfort)
        controls.addWidget(self.view_compact)

        # focus mode
        self.focus_btn = QPushButton("Focus")
        self.focus_btn.setCheckable(True)
        self.focus_btn.clicked.connect(self._toggle_focus_mode)
        self.focus_btn.setChecked(self._focus_mode)
        controls.addWidget(self.focus_btn)

        self.details_toggle = QToolButton()
        self.details_toggle.setText("Details")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setChecked(self._details_visible)
        self.details_toggle.clicked.connect(self._toggle_details_panel)
        controls.addWidget(self.details_toggle)

        # Multi-select mode button
        self.select_btn = QPushButton("Select")
        self.select_btn.setCheckable(True)
        self.select_btn.clicked.connect(self._toggle_multi_select_mode)
        controls.addWidget(self.select_btn)

        controls.addStretch(1)

        # Filter chips bar (shows active filters)
        self.filter_chips = FilterChipsBar()
        self.filter_chips.filter_removed.connect(self._on_filter_chip_removed)
        self.filter_chips.clear_all_clicked.connect(self._clear_all_filters)
        content_layout.addWidget(self.filter_chips)

        # Batch toolbar (shown in multi-select mode)
        self.batch_toolbar = BatchToolbar()
        self.batch_toolbar.set_status_requested.connect(self._on_batch_set_status)
        self.batch_toolbar.add_tag_requested.connect(self._on_batch_add_tag)
        self.batch_toolbar.add_to_collection_requested.connect(self._on_batch_add_to_collection)
        self.batch_toolbar.select_all_clicked.connect(lambda: self.grid.select_all())
        self.batch_toolbar.clear_selection_clicked.connect(lambda: self.grid.clear_selection())
        self.batch_toolbar.exit_mode_clicked.connect(self._exit_multi_select_mode)
        content_layout.addWidget(self.batch_toolbar)

        self.grid = GameGrid()
        self.grid.context_action.connect(self._on_grid_context_action)
        self.grid.game_selected.connect(self._on_game_selected)
        self.grid.game_play.connect(self._on_game_play)
        self.grid.status_filter_requested.connect(self._on_status_filter_requested)
        self.grid.updates_requested.connect(self._jump_to_updates)
        self.grid.rating_changed.connect(self._on_rating_changed)
        self.grid.tag_filter_requested.connect(self._on_tag_filter_requested)
        self.grid.scan_requested.connect(self._on_scan_clicked)
        self.grid.selection_changed.connect(self._on_selection_changed)
        self.health = HealthChecksWidget()
        self.health.open_folder_requested.connect(self._open_shortcut_folder)
        self.health.remove_game_requested.connect(self._remove_game)
        self.health.fix_requested.connect(self._fix_game)
        self.health.resolve_requested.connect(self._resolve_issue)
        self.health.ignore_requested.connect(self._ignore_issue)
        self.updates = UpdatesWidget()
        self.updates.open_source_requested.connect(self._open_source_for_game)
        self.updates.mark_installed_requested.connect(self._mark_installed_from_source)
        self.updates._filter_mode = self._updates_filter
        self.updates.filter_all.setChecked(self._updates_filter == "all")
        self.updates.filter_updates.setChecked(self._updates_filter == "updates")
        self.updates.filter_unknown.setChecked(self._updates_filter == "unknown")
        self.updates.set_density(self._updates_density)
        for btn in (self.updates.density_comfort, self.updates.density_compact,
                    self.updates.filter_all, self.updates.filter_updates, self.updates.filter_unknown):
            btn.clicked.connect(self._save_updates_prefs)
        self.health._filter_mode = self._health_filter
        # set filter buttons
        for key, btn in [
            ("all", self.health.filter_all),
            ("errors", self.health.filter_errors),
            ("warnings", self.health.filter_warn),
            ("missing_source", self.health.filter_missing_source),
            ("missing_archive", self.health.filter_missing_archive),
        ]:
            btn.setChecked(self._health_filter == key)
        self.health.set_density(self._health_density)
        for btn in (self.health.density_comfort, self.health.density_compact,
                    self.health.filter_all, self.health.filter_errors, self.health.filter_warn,
                    self.health.filter_missing_source, self.health.filter_missing_archive):
            btn.clicked.connect(self._save_health_prefs)

        content_layout.addWidget(self.content_title)
        content_layout.addLayout(controls)
        content_layout.addWidget(self.grid, 1)
        content_layout.addWidget(self.health, 1)
        content_layout.addWidget(self.updates, 1)
        self.health.hide()
        self.updates.hide()
        # build sidebar after dependent views exist so initial selection can't hit missing attrs
        self._rebuild_sidebar()

        # Right details panel
        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        details.setMinimumWidth(320)
        details.setMaximumWidth(520)

        details_title = QLabel("Details")
        details_title.setStyleSheet("font-size: 14px; font-weight: 600;")

        self.details = DetailsPanel()
        self.details.play_clicked.connect(self._on_game_play)
        self.details.game_changed.connect(self._on_game_changed)

        details_layout.addWidget(details_title)
        details_layout.addWidget(self.details, 1)

        splitter.addWidget(self.sidebar)
        splitter.addWidget(content)
        splitter.addWidget(details)
        self._details_widget = details
        self._splitter = splitter

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setStretchFactor(2, 2)
        splitter.splitterMoved.connect(self._on_splitter_moved)
        splitter.setChildrenCollapsible(False)

        self._type_scale_bucket = "normal"

        outer.addWidget(splitter, 1)
        self._log.info(
            "startup_ui_built %s",
            kv(duration_ms=round((time.perf_counter() - ui_build_start) * 1000, 1)),
        )

        # restore splitter sizes if any
        sizes = self._settings.get("splitter_sizes")
        if isinstance(sizes, list) and len(sizes) == 3:
            splitter.setSizes([int(x) for x in sizes])
        else:
            splitter.setSizes([220, 820, 0 if not self._details_visible else 340])

        # initial render
        self._apply_focus_mode(initial=True)
        if self._details_on_launch:
            self._details_visible = True
            self.details_toggle.setChecked(True)
        self._apply_details_visibility(initial=True)
        self._log.info(
            "startup_layout_ready %s",
            kv(details_visible=self._details_visible, view_mode=self._view_mode, width=self.width(), height=self.height()),
        )
        self.grid.set_view_mode(self._view_mode)
        self._update_view_mode_buttons()
        self._apply_quick_filter_buttons()
        self._apply_filter_combo_defaults()
        self._apply_responsive_type()
        first_render_start = time.perf_counter()
        self._render()
        if not self._all_games:
            self.statusBar().showMessage("Tip: Click Scan to choose your games root folder.", 8000)
        else:
            self.statusBar().showMessage(f"Loaded {len(self._all_games)} games from library.json", 5000)
        self._log.info(
            "startup_first_render_done %s",
            kv(duration_ms=round((time.perf_counter() - first_render_start) * 1000, 1),
               total_ms=round((time.perf_counter() - self._t0) * 1000, 1),
               games=len(self._all_games))
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_startup_overlay_geometry()
        self._apply_responsive_type()
        if self._log_rate.allow("resize", interval_ms=300):
            self._log.debug("resize %s", kv(w=self.width(), h=self.height()))

    # ---------- rendering / search ----------
    def _render(self) -> None:
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

    def _get_game(self, game_id: str) -> Optional[Game]:
        for g in self._all_games:
            if g.game_id == game_id:
                return g
        return None

    def _fix_game(self, game_id: str, issue_code: str) -> None:
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

    def _apply_search(self) -> None:
        # 1) start from full list
        base = list(self._all_games)

        # 2) apply active collection filter
        if self._active_collection_id:
            c = self._get_collection(self._active_collection_id)
            if c:
                base = apply_collection(base, c)

        # quick filter counts (for pill labels)
        self._update_quick_filter_counts(base)

        # 3) quick filters
        def is_missing(g: Game) -> bool:
            p = Path(g.shortcut_path) if g.shortcut_path else None
            if not p or not p.exists():
                return True
            if g.shortcut_type == "lnk" and g.backup_target_path and not Path(g.backup_target_path).exists():
                return True
            if g.archive_folder_path and not Path(g.archive_folder_path).exists():
                return True
            if g.compressed_archive_path and not Path(g.compressed_archive_path).exists():
                return True
            return False

        def needs_update(g: Game) -> bool:
            inst_vi = parse_version(g.installed_version_raw) if g.installed_version_raw else None
            src_vi = parse_version(g.source_version_raw) if g.source_version_raw else None
            cmp = compare_versions(inst_vi, src_vi)
            return cmp == CompareResult.OLDER

        if self._quick_filter == "missing":
            base = [g for g in base if is_missing(g)]
        elif self._quick_filter == "updates":
            base = [g for g in base if needs_update(g)]
        elif self._quick_filter == "source":
            base = [g for g in base if g.source_url]

        # 4) dropdown filters
        if self._status_filter != "all":
            base = [g for g in base if g.status == self._status_filter]
        if self._confidence_filter != "all":
            base = [g for g in base if g.confidence == self._confidence_filter]
        if self._type_filter != "all":
            base = [g for g in base if (g.shortcut_type or "") == self._type_filter]
        if self._tag_filter:
            base = [g for g in base if any(t.lower() == self._tag_filter.lower() for t in g.tags)]

        # 5) apply search text
        q = self.search.text().strip().lower()
        if not q:
            self._filtered = base
        else:
            def match(g: Game) -> bool:
                hay = " ".join([
                    g.title,
                    g.status,
                    g.shortcut_type or "",
                    g.confidence,
                    " ".join(g.tags),
                    g.notes or "",
                    g.shortcut_path or "",
                    g.backup_target_path or "",
                    g.source_url or "",
                    g.installed_version_raw or "",
                    g.source_version_raw or "",
                    g.source_version_num or "" if g.source_version_num else "",
                    g.source_version_suffix or "",
                    g.archive_folder_path or "",
                    g.compressed_archive_path or "",
                ]).lower()
                return q in hay

            self._filtered = [g for g in base if match(g)]

        # 6) sort
        sort_by = self._sort_by
        if sort_by == "last_played":
            reverse = True
            key_fn = lambda g: g.last_played or datetime.min
        elif sort_by == "rating":
            reverse = True
            key_fn = lambda g: g.rating if g.rating is not None else -1
        elif sort_by == "launch_count":
            reverse = True
            key_fn = lambda g: g.launch_count or 0
        elif sort_by == "last_checked":
            reverse = True
            key_fn = lambda g: g.source_checked_at or datetime.min
        else:
            reverse = False
            key_fn = lambda g: g.title.lower()

        self._filtered = sorted(self._filtered, key=key_fn, reverse=reverse)

        # If the current selection was filtered out, clear selection/details to avoid stale UI.
        if self._selected_game_id and not any(g.game_id == self._selected_game_id for g in self._filtered):
            self._selected_game_id = None
            if hasattr(self, "details"):
                self.details.show_game(None)
            self.add_to_collection_btn.setEnabled(False)
        if self._log_rate.allow("filter_state", 400):
            self._log.info(
                "filter_state %s",
                kv(
                    nav=self.sidebar.current_key() if hasattr(self.sidebar, "current_key") else "",
                    total=len(self._all_games),
                    filtered=len(self._filtered),
                    quick=self._quick_filter,
                    status=self._status_filter,
                    confidence=self._confidence_filter,
                    type=self._type_filter,
                    tag=self._tag_filter or "",
                    search=self.search.text().strip(),
                    sort=self._sort_by,
                ),
            )

        self._render()
        self._update_filter_chips()
        if self._tag_filter:
            from app.ui.theme import current_theme
            theme = current_theme()
            self.tag_filter_label.setStyleSheet(f"color:{theme.accent.name()}; font-weight:600;")
            self.tag_filter_label.setText(f"Tag: {self._tag_filter}")
            self.tag_filter_label.show()
            self.clear_tag_btn.setVisible(True)
        else:
            self.tag_filter_label.hide()
            self.clear_tag_btn.setVisible(False)


    # ---------- scan ----------
    def _on_scan_clicked(self) -> None:
        if self._scan_thread:
            QMessageBox.information(self, "Scan in progress", "A scan is already running. Please wait for it to finish.")
            return

        if not self._root_folder:
            self._choose_root_folder()
            if not self._root_folder:
                return

        root_path = Path(self._root_folder)
        if not root_path.exists() or not root_path.is_dir():
            choice = QMessageBox.question(
                self,
                "Shortcuts root missing",
                f"The configured shortcuts root no longer exists:\n\n{self._root_folder}\n\nPick a new folder now?",
            )
            if choice == QMessageBox.Yes:
                self._choose_root_folder()
                if not self._root_folder:
                    return
                root_path = Path(self._root_folder)
            else:
                return

        # 1) detect duplicates first (brief wait cursor so the UI feels responsive)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            dups = find_duplicate_shortcuts_in_root(str(root_path))
        finally:
            QApplication.restoreOverrideCursor()
        if dups:
            lines = []
            for k, paths in dups.items():
                names = ", ".join([p.name for p in sorted(paths, key=lambda p: p.name.lower())])
                lines.append(f"- {k}: {names}")

            msg = (
                "Found duplicate shortcut files in the shortcuts root.\n\n"
                "Examples: Game.lnk and Game (1).lnk\n\n"
                "Duplicates:\n"
                + "\n".join(lines)
                + "\n\nMove duplicates to a quarantine folder now? (Recommended)"
            )

            choice = QMessageBox.question(self, "Duplicates found", msg, QMessageBox.Yes | QMessageBox.No)
            if choice == QMessageBox.Yes:
                quarantine = move_duplicates_to_quarantine(self._root_folder, dups)
                QMessageBox.information(
                    self, "Duplicates moved",
                    f"Moved duplicates to:\n{quarantine}\n\nKept the first file in root for each group."
                )

        # 2) Confirm scan target
        msg = f"Scan this shortcuts folder?\n\n{self._root_folder}\n\n(Top level only: .lnk / .url / .html)"
        if QMessageBox.question(self, "Scan shortcuts", msg) != QMessageBox.Yes:
            return

        self._start_scan_thread(str(root_path))

    def _open_scanner_project(self) -> None:
        """
        Launch relocated Scanner (external/scanner/GameShortcutMaker) without blocking this Qt loop.
        """
        try:
            project_root = Path(__file__).resolve().parents[2]
            scanner_root = project_root / "external" / "scanner" / "GameShortcutMaker"
            entry = scanner_root / "app.py"
            if not entry.exists():
                raise FileNotFoundError(f"Scanner entry not found at {entry}")

            cmd = [
                sys.executable,
                "-c",
                "from external.scanner.GameShortcutMaker.app import run_app; run_app()",
            ]
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root)
            subprocess.Popen(cmd, cwd=str(project_root), env=env)
            self.statusBar().showMessage("Opening Scanner…", 4000)
        except Exception as e:
            QMessageBox.warning(self, "Open Scanner failed", f"{e}")

    def _choose_root_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose shortcuts root folder")
        if not folder:
            return
        self._root_folder = folder
        self._settings["root_folder"] = folder
        save_settings(settings_json_path(), self._settings)
        self.statusBar().showMessage(f"Root folder set: {folder}", 5000)

    def _start_scan_thread(self, root_folder: str) -> None:
        self._log.info("scan_start %s", kv(event="scan", path=root_folder))
        # progress dialog
        self._progress_dialog = QProgressDialog(f"Scanning…\n{root_folder}", "Cancel", 0, 0, self)
        self._progress_dialog.setWindowTitle("Scanning")
        self._progress_dialog.setWindowModality(Qt.WindowModal)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setMinimumWidth(420)
        self._progress_dialog.canceled.connect(self._cancel_scan)
        self._progress_dialog.show()
        self.scan_btn.setEnabled(False)

        # thread + worker
        self._scan_thread = QThread()
        self._scan_worker = ScanWorker(root_folder)
        self._scan_worker.moveToThread(self._scan_thread)

        # Use queued connections so UI updates stay on the main thread.
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress, Qt.QueuedConnection)
        self._scan_worker.finished.connect(self._on_scan_finished, Qt.QueuedConnection)
        self._scan_worker.failed.connect(self._on_scan_failed, Qt.QueuedConnection)

        self._scan_thread.start()

    def _cancel_scan(self) -> None:
        # We can’t safely stop filesystem scanning mid-loop without extra control.
        # So we just hide the dialog and let it finish quietly.
        if self._scan_worker:
            try:
                self._scan_worker.stop()
            except Exception:
                pass
        if self._progress_dialog:
            self._progress_dialog.setLabelText("Cancelling… (will stop after current file)")
            self._progress_dialog.setCancelButton(None)

    def _on_scan_progress(self, msg: str, current: int = 0, total: int = 0) -> None:
        if self._progress_dialog:
            self._progress_dialog.setLabelText(msg)
            if total > 0:
                self._progress_dialog.setRange(0, total)
                self._progress_dialog.setValue(current)
            else:
                # keep indeterminate spinner
                self._progress_dialog.setRange(0, 0)
        if self._log_rate.allow("scan_progress_log", 500):
            self._log.debug("scan_progress %s", kv(msg=msg, current=current, total=total))

    def _on_scan_failed(self, err: str) -> None:
        self._cleanup_scan_thread()
        self._log.error("scan_failed %s", kv(err=err))
        self._notify_async_error(f"Scan failed: {err}")

    def _on_scan_finished(self, games: list) -> None:
        # games is List[Game]
        cancelled = getattr(self._scan_worker, "cancelled", False) if self._scan_worker else False
        self._cleanup_scan_thread()

        if cancelled:
            self.statusBar().showMessage("Scan cancelled. No changes applied.", 6000)
            self._log.info("scan_cancelled %s", kv(event="scan", scanned=len(games)))
            return

        before = len(self._all_games)
        before_keys = {self._game_key(g) for g in self._all_games}
        scanned_keys = {self._game_key(g) for g in games}

        self._all_games = merge_scanned_into_library(self._all_games, games)
        after = len(self._all_games)
        delta = after - before
        new_count = len(scanned_keys - before_keys)
        updated_count = len(scanned_keys & before_keys)

        # Prime icons only for items touched by this scan and not already upscaled.
        to_prime = [g for g in self._all_games if (self._game_key(g) in scanned_keys) and (not getattr(g, "icon_upscaled", False))]
        icons_refreshed = self._prime_icons(to_prime)
        self._apply_search()  # re-filter + render
        save_library_bundle(library_json_path(), self._all_games, self._collections)
        self._refresh_scan_views()

        msg_lines = [
            f"Shortcuts read: {len(games)}",
            f"New entries: {new_count}",
            f"Updated: {updated_count}",
            f"Icons refreshed: {icons_refreshed}",
            f"Library total: {after} ({'+' if delta>=0 else ''}{delta} vs previous)",
        ]
        msg = "Scan finished: no shortcut files found." if len(games) == 0 else "\n".join(msg_lines)
        self.statusBar().showMessage(msg, 8000)
        # Show toast for quick feedback
        if len(games) == 0:
            show_error("No shortcuts found in the selected folder.")
        else:
            show_success(f"Scan complete: {new_count} new, {updated_count} updated games.")
        QMessageBox.information(self, "Scan summary", msg)
        self._log.info(
            "scan_done %s",
            kv(event="scan", scanned=len(games), total=after, delta=delta, cancelled=cancelled),
        )

    def _cleanup_scan_thread(self) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        if self._scan_thread:
            self._scan_thread.quit()
            self._scan_thread.wait()
            self._scan_thread = None

        self._scan_worker = None
        self.scan_btn.setEnabled(True)

    def _refresh_scan_views(self) -> None:
        """
        Refresh sidebar counts and any visible secondary views after a scan.
        """
        key = self.sidebar.current_key() if hasattr(self, "sidebar") else "all"
        select_kind = "all"
        select_id = None
        if key == "updates":
            select_kind = "updates"
        elif key == "health":
            select_kind = "health"
        elif key and key.startswith("collection:"):
            select_kind = "collection"
            select_id = key.split(":", 1)[1]

        self._rebuild_sidebar(select_kind=select_kind, select_id=select_id)

        if hasattr(self, "health") and self.health.isVisible():
            self.health.set_games(self._all_games)
            self.health.set_ignored(self._ignored_health)
        if hasattr(self, "updates") and self.updates.isVisible():
            self.updates.set_games(self._all_games)

    def _prime_icons(self, games: List[Game], size: int = 256) -> int:
        """
        Warm high-quality icons for scanned games once; mark them so we don't redo work.
        """
        count = 0
        seen_paths = set()
        for g in games:
            if getattr(g, "icon_upscaled", False):
                continue
            path = getattr(g, "shortcut_path", "") or ""
            if not path:
                continue
            key = path.lower()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            try:
                pm = pixmap_for_game(g, size=size)
                if not pm.isNull():
                    g.icon_upscaled = True
                    count += 1
            except Exception as e:
                if self._log_rate.allow("icon_prime_error", 1500):
                    self._log.warning("icon_prime_error %s", kv(path=path, err=e))
        return count

    def _game_key(self, g: Game) -> str:
        try:
            return str(Path(g.shortcut_path)).lower()
        except Exception:
            return g.shortcut_path.lower() if getattr(g, "shortcut_path", "") else ""

    def _notify_async_error(self, text: str) -> None:
        """
        Non-blocking error toast for background tasks.
        """
        try:
            box = QMessageBox(QMessageBox.Critical, "Error", f"{text}\nSee manager.log.", QMessageBox.Ok, self)
            box.setWindowModality(Qt.NonModal)
            box.setAttribute(Qt.WA_DeleteOnClose)
            box.show()
        except Exception:
            self._log.exception("toast_error_failed")

    # ---------- updates ----------
    def _on_check_updates_fetch(self) -> None:
        if not self._all_games:
            QMessageBox.information(self, "No games", "No games loaded. Scan or load a library first.")
            return
        self._log.info("updates_check_start %s", kv(event="updates", mode="fetch"))
        self._start_update_thread()

    def _on_check_updates_open_only(self) -> None:
        if not self._all_games:
            QMessageBox.information(self, "No games", "No games loaded. Scan or load a library first.")
            return
        count = 0
        import webbrowser
        for g in self._all_games:
            if g.source_url:
                webbrowser.open(g.source_url)
                count += 1
        self.statusBar().showMessage(f"Opened {count} source pages", 5000)
        self._log.info("updates_open_only %s", kv(count=count))

    def _start_update_thread(self) -> None:
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

    def _cancel_updates(self) -> None:
        if self._update_worker:
            self._update_worker.cancel()
        if self._update_progress_dialog:
            self._update_progress_dialog.setLabelText("Cancelling…")
            self._update_progress_dialog.setCancelButton(None)

    def _on_update_progress(self, msg: str, done: int, total: int) -> None:
        if self._update_progress_dialog:
            if total > 0:
                self._update_progress_dialog.setRange(0, total)
                self._update_progress_dialog.setValue(done)
            self._update_progress_dialog.setLabelText(msg)
        if self._log_rate.allow("updates_progress_log", 500):
            self._log.debug("updates_progress %s", kv(done=done, total=total, msg=msg))

    def _on_update_failed(self, err: str) -> None:
        self._cleanup_update_thread()
        self._log.error("updates_failed %s", kv(err=err))
        self._notify_async_error(f"Updates failed: {err}")

    def _on_update_finished(self, results: list) -> None:
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
            lines = "\n".join(f"- {r.get('error')}" for r in errs[:10])
            QMessageBox.warning(self, "Some checks failed", lines)
        else:
            show_success(f"Update check complete: {ok} sources checked")
        self._log.info("updates_done %s", kv(ok=ok, errors=len(errs), total=len(results)))

    def _apply_settings_values(self, vals: dict) -> None:
        old_view = self._view_mode
        old_theme = self._theme
        old_font = self._font_family
        old_scale = self._font_scale

        self._view_mode = vals.get("view_mode", self._view_mode)
        self._details_on_launch = vals.get("details_on_launch", self._details_on_launch)
        self._details_on_selection = vals.get("details_on_selection", self._details_on_selection)
        self._theme = vals.get("theme", self._theme)
        self._font_family = vals.get("font_family", self._font_family)
        self._font_scale = vals.get("font_scale", self._font_scale)

        for key, val in [
            ("view_mode", self._view_mode),
            ("details_on_launch", self._details_on_launch),
            ("details_on_selection", self._details_on_selection),
            ("theme", self._theme),
            ("font_family", self._font_family),
            ("font_scale", self._font_scale),
        ]:
            self._settings[key] = val
        self._persist_settings()

        # palette / font without rebuilding grid
        if (self._theme, self._font_family, self._font_scale) != (old_theme, old_font, old_scale):
            self._safe_refresh_ui()

        if self._view_mode != old_view:
            self.grid.set_view_mode(self._view_mode)
            self._update_view_mode_buttons()

        if vals.get("reset_layout"):
            self._reset_layout()

        if self._details_on_launch:
            self._details_visible = True
            self.details_toggle.setChecked(True)
            self._apply_details_visibility()

        self._guard_top_level_windows()

    def _open_bulk_sources(self) -> None:
        dlg = BulkSourceImportDialog(self, games=self._all_games)
        if dlg.exec():
            self._save_bundle()
            self._apply_search()

    def _resolve_issue(self, game_id: str, code: str) -> None:
        self._ignored_health.setdefault(game_id, set()).add(code)
        if self.health.isVisible():
            self.health.set_ignored(self._ignored_health)
        self.statusBar().showMessage("Issue marked resolved", 2000)

    def _ignore_issue(self, game_id: str, code: str) -> None:
        self._ignored_health.setdefault(game_id, set()).add(code)
        if self.health.isVisible():
            self.health.set_ignored(self._ignored_health)
        self.statusBar().showMessage("Issue ignored", 2000)

    def _focus_details(self, game: Game, hint: str, field: Optional[str] = None) -> None:
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

    def _cleanup_update_thread(self) -> None:
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

    # ---------- filters / view ----------
    def _apply_quick_filter_buttons(self) -> None:
        mapping = {
            "all": self.pill_all,
            "missing": self.pill_missing,
            "updates": self.pill_updates,
            "source": self.pill_source,
        }
        for key, btn in mapping.items():
            btn.setChecked(self._quick_filter == key)

    def _on_quick_filter(self) -> None:
        sender = self.sender()
        if sender == self.pill_missing:
            self._quick_filter = "missing"
        elif sender == self.pill_updates:
            self._quick_filter = "updates"
        elif sender == self.pill_source:
            self._quick_filter = "source"
        else:
            self._quick_filter = "all"
        self._pulse_widget(sender)
        self._settings["quick_filter"] = self._quick_filter
        self._persist_settings()
        self._apply_search()

    def _on_filter_changed(self) -> None:
        self._status_filter = self.status_filter.currentText().lower()
        self._confidence_filter = self.conf_filter.currentText().lower()
        self._type_filter = self.type_filter.currentText().lower()
        for key in ("status_filter", "confidence_filter", "type_filter"):
            self._settings[key] = getattr(self, f"_{key}")
        self._persist_settings()
        self._apply_search()

    def _on_status_filter_requested(self, status: str) -> None:
        self._status_filter = status
        self.status_filter.setCurrentText(status.capitalize())
        self._settings["status_filter"] = status
        self._persist_settings()
        self._apply_search()

    def _on_tag_filter_requested(self, tag: str) -> None:
        if self._tag_filter == tag:
            self._tag_filter = None
            self.statusBar().showMessage("Tag filter cleared", 2000)
        else:
            self._tag_filter = tag
            self.statusBar().showMessage(f"Filtered by tag: {tag}", 2000)
        if self._tag_filter:
            self._settings["tag_filter"] = self._tag_filter
        else:
            self._settings.pop("tag_filter", None)
        self._persist_settings()
        self._apply_search()

    def _clear_tag_filter(self) -> None:
        self._tag_filter = None
        self.tag_filter_label.hide()
        self.clear_tag_btn.setVisible(False)
        self._settings.pop("tag_filter", None)
        self._persist_settings()
        self._apply_search()

    def _on_filter_chip_removed(self, key: str) -> None:
        """Handle removal of a filter chip."""
        if key == "status":
            self._status_filter = "all"
            self.status_filter.setCurrentText("All")
        elif key == "confidence":
            self._confidence_filter = "all"
            self.conf_filter.setCurrentText("All")
        elif key == "type":
            self._type_filter = "all"
            self.type_filter.setCurrentText("All")
        elif key == "tag":
            self._tag_filter = None
            self.tag_filter_label.hide()
            self.clear_tag_btn.setVisible(False)
        elif key == "quick":
            self._quick_filter = "all"
        elif key == "search":
            self.search.clear()

        self._persist_settings()
        self._apply_search()

    def _clear_all_filters(self) -> None:
        """Clear all active filters."""
        self._status_filter = "all"
        self._confidence_filter = "all"
        self._type_filter = "all"
        self._tag_filter = None
        self._quick_filter = "all"

        # Update UI
        self.status_filter.setCurrentText("All")
        self.conf_filter.setCurrentText("All")
        self.type_filter.setCurrentText("All")
        self.search.clear()
        self.tag_filter_label.hide()
        self.clear_tag_btn.setVisible(False)

        self._persist_settings()
        self._apply_search()

    def _update_filter_chips(self) -> None:
        """Update the filter chips bar based on current filter state."""
        chips = build_filter_chips(
            status=self._status_filter,
            confidence=self._confidence_filter,
            type_filter=self._type_filter,
            tag=self._tag_filter,
            quick_filter=self._quick_filter,
            search_query=self.search.text().strip(),
        )
        self.filter_chips.set_filters(chips)

    # ---- Multi-Select Mode ----
    def _toggle_multi_select_mode(self) -> None:
        """Toggle multi-select mode on/off."""
        enabled = self.select_btn.isChecked()
        self.grid.set_multi_select_mode(enabled)
        if enabled:
            self.batch_toolbar.show_toolbar()
        else:
            self.batch_toolbar.hide_toolbar()
            self.grid.clear_selection()

    def _exit_multi_select_mode(self) -> None:
        """Exit multi-select mode."""
        self.select_btn.setChecked(False)
        self._toggle_multi_select_mode()

    def _on_selection_changed(self, game_ids: list) -> None:
        """Handle selection changes in the grid."""
        self.batch_toolbar.update_selection(game_ids)

    def _on_batch_set_status(self, status: str, game_ids: list) -> None:
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

    def _on_batch_add_tag(self, tag: str, game_ids: list) -> None:
        """Add a tag to multiple games."""
        changed = 0
        for game_id in game_ids:
            g = self._get_game(game_id)
            if g:
                existing = [t.strip() for t in (g.tags or "").split(",") if t.strip()]
                if tag not in existing:
                    existing.append(tag)
                    g.tags = ", ".join(existing)
                    changed += 1
        if changed:
            self._save_bundle()
            self._apply_search()
            show_success(f"Added tag '{tag}' to {changed} games")

    def _on_batch_add_to_collection(self, game_ids: list) -> None:
        """Add multiple games to a collection."""
        manual = [c for c in self._collections if c.type == "manual"]
        if not manual:
            QMessageBox.information(self, "No Collections", "Create a collection first.")
            return

        from PySide6.QtWidgets import QInputDialog
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

    def _jump_to_updates(self, game_id: str) -> None:
        # switch nav to Updates and highlight
        self.sidebar.set_selected("updates")
        self.updates.set_games(self._all_games)
        self.updates.highlight_game(game_id)

    def _on_rating_changed(self, game_id: str, rating) -> None:
        g = self._get_game(game_id)
        if g:
            g.rating = rating
            self._save_bundle()
            self._apply_search()
            self.details.show_game(g)

    def _on_sort_changed(self) -> None:
        mapping = {
            "Title": "title",
            "Last Played": "last_played",
            "Rating": "rating",
            "Launch Count": "launch_count",
            "Last Checked": "last_checked",
        }
        self._sort_by = mapping.get(self.sort_combo.currentText(), "title")
        self._settings["sort_by"] = self._sort_by
        self._persist_settings()
        self._apply_search()

    def _update_quick_filter_counts(self, games: List[Game]) -> None:
        missing = 0
        updates = 0
        source = 0
        for g in games:
            p = Path(g.shortcut_path) if g.shortcut_path else None
            if (not p) or (not p.exists()):
                missing += 1
            inst_vi = parse_version(g.installed_version_raw) if g.installed_version_raw else None
            src_vi = parse_version(g.source_version_raw) if g.source_version_raw else None
            cmp = compare_versions(inst_vi, src_vi)
            if cmp == CompareResult.OLDER:
                updates += 1
            if g.source_url:
                source += 1
        self.pill_all.setText(f"All ({len(games)})")
        self.pill_missing.setText(f"Missing ({missing})")
        self.pill_updates.setText(f"Updates ({updates})")
        self.pill_source.setText(f"Source ({source})")

    def _update_view_mode_buttons(self) -> None:
        self.view_comfort.setChecked(self._view_mode == "comfortable")
        self.view_compact.setChecked(self._view_mode == "compact")

    def _pulse_widget(self, widget) -> None:
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

    def _on_view_mode_changed(self) -> None:
        self._view_mode = "compact" if self.sender() == self.view_compact else "comfortable"
        self._pulse_widget(self.sender())
        self.grid.set_view_mode(self._view_mode)
        self._settings["view_mode"] = self._view_mode
        self._persist_settings()
        self._update_view_mode_buttons()

    def _toggle_focus_mode(self) -> None:
        self._focus_mode = self.focus_btn.isChecked()
        self._pulse_widget(self.focus_btn)
        self._settings["focus_mode"] = self._focus_mode
        self._persist_settings()
        self._apply_focus_mode()

    def _apply_focus_mode(self, initial: bool = False) -> None:
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

    def _on_splitter_moved(self, *_args) -> None:
        sizes = self._splitter.sizes()
        if self._details_visible and not self._focus_mode and len(sizes) == 3 and sizes[2] < 260:
            delta = 260 - sizes[2]
            sizes[2] = 260
            sizes[1] = max(400, sizes[1] - delta)
            self._splitter.setSizes(sizes)
        self._settings["splitter_sizes"] = sizes
        self._persist_settings()

    def _apply_filter_combo_defaults(self) -> None:
        # ensure UI matches stored filters
        def set_if(combo: QComboBox, value: str):
            for i in range(combo.count()):
                if combo.itemText(i).lower() == value:
                    combo.setCurrentIndex(i)
                    break
        set_if(self.status_filter, self._status_filter)
        set_if(self.conf_filter, self._confidence_filter)
        set_if(self.type_filter, self._type_filter)
        # pills
        self._apply_quick_filter_buttons()

    def _persist_settings(self) -> None:
        save_settings(settings_json_path(), self._settings)

    def _save_updates_prefs(self) -> None:
        self._settings["updates_filter"] = self.updates._filter_mode
        self._settings["updates_density"] = self.updates._density
        self._persist_settings()

    def _save_health_prefs(self) -> None:
        self._settings["health_filter"] = self.health._filter_mode
        self._settings["health_density"] = self.health._density
        self._persist_settings()

    def _toggle_details_panel(self) -> None:
        desired = self.details_toggle.isChecked()
        if self._focus_mode and desired:
            # auto-exit focus to honor user intent
            self._focus_mode = False
            self.focus_btn.setChecked(False)
            self._settings["focus_mode"] = False
        if not desired:
            self._user_hid_details = True
        else:
            self._user_hid_details = False
        self._pulse_widget(self.details_toggle)
        self._details_visible = desired
        self._settings["details_visible"] = self._details_visible
        self._persist_settings()
        self._apply_details_visibility()

    def _open_preferences(self) -> None:
        dlg = PreferencesDialog(
            self,
            view_mode=self._view_mode,
            details_on_launch=self._details_on_launch,
            details_on_selection=self._details_on_selection,
            theme=self._theme,
            font_family=self._font_family,
            font_scale=self._font_scale,
        )
        dlg.apply_clicked.connect(self._apply_settings_values)
        dlg.exec()

    def _open_data_folder(self) -> None:
        from app.storage.paths import get_app_dir
        path = get_app_dir()
        self._log.info("open_data_folder %s", kv(path=path))
        try:
            os.startfile(str(path))
        except Exception:
            self._log.exception("open_data_folder_failed")

    def _ensure_details_visible(self) -> None:
        if self._focus_mode:
            return
        if not self._details_visible and self._details_on_selection and not self._user_hid_details:
            self._details_visible = True
            self.details_toggle.setChecked(True)
            self._settings["details_visible"] = True
            self._persist_settings()
        self._apply_details_visibility()

    def _apply_details_visibility(self, initial: bool = False) -> None:
        if self._details_visible and not self._focus_mode:
            self._details_widget.show()
            if not initial:
                self._splitter.setSizes([220, max(600, self.width() - 560), 340])
        else:
            self._details_widget.hide()
            if not initial:
                self._splitter.setSizes([220, max(700, self.width() - 220), 0])
        self.grid.refresh()

    def _reset_layout(self) -> None:
        self._splitter.setSizes([200, 900, 320 if self._details_visible else 0])
        self._settings["splitter_sizes"] = self._splitter.sizes()
        self._persist_settings()
        self.grid.refresh()

    def _safe_refresh_ui(self) -> None:
        """
        Re-apply palette/QSS/font only; avoid rebuilding views.
        """
        self._log.info("safe_refresh_ui %s", kv(event="safe_refresh"))
        apply_theme(QApplication.instance(), self._theme, self._font_family, self._font_scale)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    # ---------- startup overlay ----------
    def _build_startup_overlay(self, host: QWidget) -> None:
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

    def _set_startup_status(self, text: str) -> None:
        if self._startup_status:
            self._startup_status.setText(text)
            if self._startup_overlay:
                self._startup_overlay.raise_()
        if self._log_rate.allow("startup_status", 400):
            self._log.info("startup_status %s", kv(text=text))

    def _hide_startup_overlay(self) -> None:
        if self._startup_overlay and not self._first_render_done:
            self._first_render_done = True
            self._startup_overlay.hide()

    def _update_startup_overlay_geometry(self) -> None:
        if not self._startup_overlay:
            return
        try:
            self._startup_overlay.setGeometry(self.centralWidget().geometry())
        except Exception:
            pass

    def _apply_responsive_type(self) -> None:
        """
        Step-based responsive typography based on window width buckets.
        """
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

    def _bump_table_font(self, table, base: int) -> None:
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

    def _guard_top_level_windows(self) -> None:
        """Debug guardrail to catch accidental top-level widgets (e.g., orphaned cards)."""
        if not DEBUG_GUARDS:
            return
        allowed_types = (MainWindow, PreferencesDialog)
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

    def _new_collection(self) -> None:
        name, ok = QInputDialog.getText(self, "New Collection", "Collection name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return

        kind, ok2 = QInputDialog.getItem(
            self, "Collection Type", "Type:",
            [
                "manual",
                "smart (preset: Low confidence)",
                "smart (preset: HTML only)",
                "smart (preset: Backlog)",
                "smart (preset: Unplayed)",
            ],
            0, False
        )
        if not ok2:
            return

        c = Collection(collection_id=str(uuid.uuid4()), name=name)

        if kind == "manual":
            c.type = "manual"
            c.game_ids = []
        else:
            c.type = "smart"
            # You can expand these later.
            if "Low confidence" in kind:
                c.filter = {"confidence_in": ["low"]}
            elif "HTML only" in kind:
                c.filter = {"shortcut_type_in": ["html"]}
            elif "Backlog" in kind:
                c.filter = {"status_in": ["backlog"]}
            elif "Unplayed" in kind:
                c.filter = {"launch_count_max": 0}
            else:
                c.filter = {}

        # prevent duplicate names (optional but nice)
        existing_names = {x.name.lower() for x in self._collections}
        if c.name.lower() in existing_names:
            QMessageBox.warning(self, "Name exists", "A collection with the same name already exists.")
            return

        self._collections.append(c)
        self._save_bundle()

        # jump to new collection in sidebar
        self._active_collection_id = c.collection_id
        self._refresh_ui_after_collections_change(keep_kind="collection", keep_id=c.collection_id)


    # ---------- selection / play ----------

    def _on_grid_context_action(self, game_id: str, action: str) -> None:
        g = self._get_game(game_id)
        if not g:
            return

        # keep selection in sync
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

    def _on_game_selected(self, game_id: str) -> None:
        self._selected_game_id = game_id
        g = self._get_game(game_id)
        self.details.show_game(g)
        self.add_to_collection_btn.setEnabled(True)
        self._ensure_details_visible()

    def _on_game_play(self, game_id: str) -> None:
        g = self._get_game(game_id)
        if g is None:
            return

        ok, info = launch_game(g)

        if ok:
            g.launch_count += 1
            from datetime import datetime
            g.last_played = datetime.now()
            save_library_bundle(library_json_path(), self._all_games, self._collections)
            self.details.show_game(g)
            self.statusBar().showMessage(f"{g.title}: {info}", 5000)
        else:
            QMessageBox.warning(self, "Launch failed", f"{g.title}\n\n{info}")

    def _get_collection(self, cid: Optional[str]) -> Optional[Collection]:
        if not cid:
            return None
        for c in self._collections:
            if c.collection_id == cid:
                return c
        return None

    def _nav_key(self, kind: str, cid: Optional[str] = None) -> str:
        if kind == "collection" and cid:
            return f"collection:{cid}"
        return kind
    
    def _rename_active_collection(self) -> None:
        c = self._get_collection(self._active_collection_id)
        if not c:
            return

        new_name, ok = QInputDialog.getText(self, "Rename Collection", "New name:", text=c.name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return

        # prevent duplicate names
        if any(x.collection_id != c.collection_id and x.name.lower() == new_name.lower() for x in self._collections):
            QMessageBox.warning(self, "Name exists", "Another collection already uses that name.")
            return

        c.name = new_name
        self._save_bundle()
        self._rebuild_sidebar(select_kind="collection", select_id=c.collection_id)
        self._apply_search()

    def _delete_active_collection(self) -> None:
        c = self._get_collection(self._active_collection_id)
        if not c:
            return

        if QMessageBox.question(self, "Delete Collection", f"Delete '{c.name}'?") != QMessageBox.Yes:
            return

        self._collections = [x for x in self._collections if x.collection_id != c.collection_id]
        self._active_collection_id = None
        self._save_bundle()

        self._rebuild_sidebar(select_kind="all")
        self._apply_search()


    def _on_nav_changed(self, key: str) -> None:
        if not key:
            return
        if self._log_rate.allow("nav_change", 400):
            self._log.info("nav_change %s", kv(event="nav_change", key=key))

        grid = getattr(self, "grid", None)
        health = getattr(self, "health", None)
        updates = getattr(self, "updates", None)

        if key == "health":
            self.rename_collection_btn.setEnabled(False)
            self.delete_collection_btn.setEnabled(False)
            self.content_title.setText("Health Checks")
            if grid:
                grid.hide()
            if health:
                health.show()
                health.set_games(self._all_games)
                health.set_ignored(self._ignored_health)
                self._settings["health_filter"] = health._filter_mode
                self._settings["health_density"] = health._density
            else:
                if self._log_rate.allow("health_missing", 2000):
                    self._log.warning("Health view missing during nav")
            if updates:
                updates.hide()
            self._persist_settings()
            return
        if key == "updates":
            self.rename_collection_btn.setEnabled(False)
            self.delete_collection_btn.setEnabled(False)
            self.content_title.setText("Updates")
            if grid:
                grid.hide()
            if health:
                health.hide()
            if updates:
                updates.show()
                updates.set_games(self._all_games)
            else:
                if self._log_rate.allow("updates_missing", 2000):
                    self._log.warning("Updates view missing during nav")
            return

        # library pages
        if health:
            health.hide()
        if updates:
            updates.hide()
        if grid:
            grid.show()

        if key == "all":
            self.rename_collection_btn.setEnabled(False)
            self.delete_collection_btn.setEnabled(False)
            self._active_collection_id = None
            self.content_title.setText("All Games")
        elif key.startswith("collection:"):
            self._active_collection_id = key.split(":", 1)[1]
            c = self._get_collection(self._active_collection_id)
            self.content_title.setText(c.name if c else "Collection")
        else:
            self._active_collection_id = None
        
        c = self._get_collection(self._active_collection_id) if self._active_collection_id else None
        is_collection = c is not None
        self.rename_collection_btn.setEnabled(is_collection)
        self.delete_collection_btn.setEnabled(is_collection)

        self._apply_search()

    def _open_shortcut_folder(self, shortcut_path: str) -> None:
        try:
            # prefer game folder when available
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
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Open folder failed", str(e))

    def _open_source_for_game(self, game_id: str) -> None:
        g = self._get_game(game_id)
        if g and g.source_url:
            import webbrowser
            webbrowser.open(g.source_url)

    def _mark_installed_from_source(self, game_id: str) -> None:
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

    def _remove_game(self, game_id: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        if QMessageBox.question(self, "Remove", "Remove this entry from the library?") != QMessageBox.Yes:
            return

        self._all_games = [g for g in self._all_games if g.game_id != game_id]
        self._apply_search()
        save_library_bundle(library_json_path(), self._all_games, self._collections)

        # If health page is visible, refresh it
        if self.health.isVisible():
            self.health.set_games(self._all_games)
    
    def _on_game_changed(self, game_id: str) -> None:
        g = self._get_game(game_id)
        if g is None:
            return
        if self._log_rate.allow("game_changed", 400):
            self._log.info("game_changed %s", kv(game_id=game_id, title=getattr(g, "title", "")))

        # Pull edits from UI into the object
        self.details.apply_edits_to_game()

        # Persist
        save_library_bundle(library_json_path(), self._all_games, self._collections)

        # Re-render cards so rating/status updates show immediately
        self._apply_search()

        # Keep selection stable
        self._selected_game_id = game_id

    def _rebuild_sidebar(self, select_kind: str = "all", select_id: Optional[str] = None) -> None:
        selected_key = self._nav_key(select_kind, select_id)
        self.sidebar.set_games(self._all_games)
        self.sidebar.populate(
            all_count=len(self._all_games),
            updates_count=0,
            health_count=0,
            collections=self._collections,
            selected_key=selected_key,
        )

    def _save_bundle(self) -> None:
        save_library_bundle(library_json_path(), self._all_games, self._collections)

    def _refresh_ui_after_collections_change(self, keep_kind: str = "all", keep_id: Optional[str] = None) -> None:
        """
        Rebuild sidebar without forcibly resetting to All Games,
        then re-apply current filters/search.
        """
        self._rebuild_sidebar(select_kind=keep_kind, select_id=keep_id)
        self._apply_search()
        self.statusBar().showMessage("Saved.", 2000)
    
    def _add_selected_to_collection(self) -> None:
        if not self._selected_game_id:
            return

        g = self._get_game(self._selected_game_id)
        if not g:
            return

        manual = [c for c in self._collections if c.type == "manual"]
        if not manual:
            QMessageBox.information(self, "No manual collections", "Create a manual collection first.")
            return

        names = [c.name for c in sorted(manual, key=lambda x: x.name.lower())]
        choice, ok = QInputDialog.getItem(self, "Add to Collection", "Choose a manual collection:", names, 0, False)
        if not ok:
            return

        target = None
        for c in manual:
            if c.name == choice:
                target = c
                break
        if not target:
            return

        if not hasattr(target, "game_ids") or target.game_ids is None:
            target.game_ids = []

        if g.game_id not in target.game_ids:
            target.game_ids.append(g.game_id)
            self._save_bundle()
            self.statusBar().showMessage(f"Added '{g.title}' to '{target.name}'", 3000)
        else:
            self.statusBar().showMessage("Already in that collection.", 2000)

        # keep user on current view
        self._apply_search()
