"""Core MainWindow class combining all mixins."""
from __future__ import annotations
from typing import List, Optional
import os
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QSplitter, QMenu, QToolButton, QApplication,
)

from app.models import Game, Collection
from app.storage import (
    library_json_path, settings_json_path,
    load_settings, load_library_bundle,
)
from app.logging_utils import connect_safe, get_logger, kv, RateLimiter, wrap_slot
from app.ui.widgets import (
    GameGrid, DetailsPanel, FilterChipsBar, BatchToolbar,
    HealthChecksWidget, UpdatesWidget,
)
from app.ui.widgets.library_sidebar import LibrarySidebar
from app.ui.theme import apply_theme

# Import all mixins
from .scan_mixin import ScanMixin
from .update_mixin import UpdateMixin
from .filter_mixin import FilterMixin
from .dialog_mixin import DialogMixin
from .collection_mixin import CollectionMixin
from .game_ops_mixin import GameOpsMixin
from .actions_mixin import ActionsMixin
from .ui_mixin import UIMixin
from .batch_mixin import BatchMixin

DEBUG_GUARDS = os.environ.get("GLM_GUARDS", "0") == "1"


class MainWindow(
    ScanMixin,
    UpdateMixin,
    FilterMixin,
    DialogMixin,
    CollectionMixin,
    GameOpsMixin,
    ActionsMixin,
    UIMixin,
    BatchMixin,
    QMainWindow,
):
    """Main application window combining all functionality through mixins."""

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

        # Load settings
        settings_start = time.perf_counter()
        self._settings = load_settings(settings_json_path())
        self._log.info(
            "startup_settings_loaded %s",
            kv(duration_ms=round((time.perf_counter() - settings_start) * 1000, 1)),
        )

        # Initialize state from settings
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

        # Load library
        lib_start = time.perf_counter()
        self._all_games, self._collections = load_library_bundle(library_json_path())
        self._active_collection_id: Optional[str] = None
        self._log.info(
            "startup_library_loaded %s",
            kv(count=len(self._all_games), collections=len(self._collections),
               duration_ms=round((time.perf_counter() - lib_start) * 1000, 1)),
        )
        self._set_startup_status("Building UI…")
        self._log.info("data_paths %s", kv(library=library_json_path(), settings=settings_json_path()))

        self._filtered: List[Game] = list(self._all_games)
        self._selected_game_id: Optional[str] = None
        self._ignored_health: dict[str, set[str]] = {}

        # Restore custom theme if saved
        if self._theme == "custom" and "custom_theme" in self._settings:
            self._restore_custom_theme()

        # Apply theme + font early so widgets pick them up
        apply_theme(QApplication.instance(), self._theme, self._font_family, self._font_scale)

        # Worker handles
        self._scan_thread = None
        self._scan_worker = None
        self._progress_dialog = None
        self._update_thread = None
        self._update_worker = None
        self._update_progress_dialog = None

        # Build UI
        ui_build_start = time.perf_counter()
        self._build_ui()
        self._log.info(
            "startup_ui_built %s",
            kv(duration_ms=round((time.perf_counter() - ui_build_start) * 1000, 1)),
        )

        # Initial render
        self._finalize_startup()

        # Setup keyboard shortcuts
        self._setup_shortcuts()

    def _build_ui(self) -> None:
        """Build the main UI layout."""
        root = QWidget()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # Startup overlay
        self._build_startup_overlay(root)
        self._set_startup_status("Loading library…")

        # Top bar
        self._build_topbar(outer)

        # Main split: sidebar | content | details
        splitter = QSplitter(Qt.Horizontal)

        # Left sidebar
        self.sidebar = LibrarySidebar()
        self.sidebar.nav_changed.connect(wrap_slot(self._log, "nav_changed")(self._on_nav_changed))
        self.sidebar.set_games(self._all_games)

        # Center content
        content = self._build_content_area()

        # Right details panel
        details = self._build_details_panel()

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

        # Restore splitter sizes
        sizes = self._settings.get("splitter_sizes")
        if isinstance(sizes, list) and len(sizes) == 3:
            splitter.setSizes([int(x) for x in sizes])
        else:
            splitter.setSizes([220, 820, 0 if not self._details_visible else 340])

    def _build_topbar(self, outer: QVBoxLayout) -> None:
        """Build the top toolbar."""
        topbar = QHBoxLayout()

        self.title_label = QLabel("Library")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600;")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games, tags, notes…")
        self.search.setToolTip(
            "Search by title, tags, or notes.\n"
            "Advanced syntax: status:playing, tag:rpg, rating:>7, has:source"
        )
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

        self._build_tools_menu()

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

    def _build_tools_menu(self) -> None:
        """Build the tools dropdown menu."""
        tools_menu = QMenu(self)
        act_bulk = QAction("Bulk Source URLs…", self)
        act_bulk.triggered.connect(self._open_bulk_sources)
        act_bulk_archive = QAction("Bulk Archive Import…", self)
        act_bulk_archive.triggered.connect(self._open_bulk_archive_import)
        act_scan = QAction("Scanner", self)
        act_scan.triggered.connect(self._open_scanner_project)
        act_settings = QAction("Settings", self)
        act_settings.triggered.connect(self._open_preferences)
        act_theme_editor = QAction("Theme Editor…", self)
        act_theme_editor.triggered.connect(self._open_theme_editor)
        act_layout = QAction("Layout Customization…", self)
        act_layout.triggered.connect(self._open_layout_customization)
        act_data = QAction("Open Data Folder", self)
        act_data.triggered.connect(self._open_data_folder)
        tools_menu.addAction(act_bulk)
        tools_menu.addAction(act_bulk_archive)
        tools_menu.addAction(act_scan)
        tools_menu.addSeparator()
        tools_menu.addAction(act_settings)
        tools_menu.addAction(act_theme_editor)
        tools_menu.addAction(act_layout)
        tools_menu.addSeparator()
        tools_menu.addAction(act_data)

        self.tools_btn = QToolButton()
        self.tools_btn.setText("Tools")
        self.tools_btn.setMinimumWidth(80)
        self.tools_btn.setToolTip("Tools and settings")
        self.tools_btn.setPopupMode(QToolButton.InstantPopup)
        self.tools_btn.setMenu(tools_menu)

    def _build_content_area(self) -> QWidget:
        """Build the center content area with grid and controls."""
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        content.setMinimumWidth(520)

        self.content_title = QLabel("All Games")
        self.content_title.setStyleSheet("font-size: 14px; font-weight: 600;")

        # Filter / controls bar
        controls = self._build_controls_bar()

        # Filter chips bar
        self.filter_chips = FilterChipsBar()
        self.filter_chips.filter_removed.connect(self._on_filter_chip_removed)
        self.filter_chips.clear_all_clicked.connect(self._clear_all_filters)
        content_layout.addWidget(self.filter_chips)

        # Batch toolbar
        self.batch_toolbar = BatchToolbar()
        self.batch_toolbar.set_status_requested.connect(self._on_batch_set_status)
        self.batch_toolbar.add_tag_requested.connect(self._on_batch_add_tag)
        self.batch_toolbar.add_to_collection_requested.connect(self._on_batch_add_to_collection)
        self.batch_toolbar.select_all_clicked.connect(lambda: self.grid.select_all())
        self.batch_toolbar.clear_selection_clicked.connect(lambda: self.grid.clear_selection())
        self.batch_toolbar.exit_mode_clicked.connect(self._exit_multi_select_mode)
        content_layout.addWidget(self.batch_toolbar)

        # Game grid
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

        # Health and Updates widgets
        self.health = HealthChecksWidget()
        self.health.open_folder_requested.connect(self._open_shortcut_folder)
        self.health.remove_game_requested.connect(self._remove_game)
        self.health.fix_requested.connect(self._fix_game)
        self.health.resolve_requested.connect(self._resolve_issue)
        self.health.ignore_requested.connect(self._ignore_issue)

        self.updates = UpdatesWidget()
        self.updates.open_source_requested.connect(self._open_source_for_game)
        self.updates.mark_installed_requested.connect(self._mark_installed_from_source)

        # Apply saved preferences
        self._apply_saved_widget_prefs()

        content_layout.addWidget(self.content_title)
        content_layout.addLayout(controls)
        content_layout.addWidget(self.grid, 1)
        content_layout.addWidget(self.health, 1)
        content_layout.addWidget(self.updates, 1)
        self.health.hide()
        self.updates.hide()

        self._rebuild_sidebar()
        return content

    def _apply_saved_widget_prefs(self) -> None:
        """Apply saved preferences to health and updates widgets."""
        self.updates._filter_mode = self._updates_filter
        self.updates.filter_all.setChecked(self._updates_filter == "all")
        self.updates.filter_updates.setChecked(self._updates_filter == "updates")
        self.updates.filter_unknown.setChecked(self._updates_filter == "unknown")
        self.updates.set_density(self._updates_density)
        for btn in (self.updates.density_comfort, self.updates.density_compact,
                    self.updates.filter_all, self.updates.filter_updates, self.updates.filter_unknown):
            btn.clicked.connect(self._save_updates_prefs)

        self.health._filter_mode = self._health_filter
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

    def _build_controls_bar(self) -> QHBoxLayout:
        """Build the filter controls bar."""
        controls = QHBoxLayout()
        controls.setSpacing(8)

        # Quick pills
        self.pill_all = QPushButton("All")
        self.pill_all.setToolTip("Show all games in your library")
        self.pill_missing = QPushButton("Missing")
        self.pill_missing.setToolTip("Show games with missing shortcut files")
        self.pill_updates = QPushButton("Updates")
        self.pill_updates.setToolTip("Show games with available updates")
        self.pill_source = QPushButton("Source")
        self.pill_source.setToolTip("Show games with a source URL")
        for btn in (self.pill_all, self.pill_missing, self.pill_updates, self.pill_source):
            btn.setCheckable(True)
            btn.clicked.connect(self._on_quick_filter)
            controls.addWidget(btn)
        controls.addSpacing(12)

        # Tag filter display
        self.tag_filter_label = QLabel("")
        self.tag_filter_label.setStyleSheet("color: #7ca1ff; font-weight: 600;")
        self.tag_filter_label.hide()
        self.clear_tag_btn = QPushButton("Clear tag")
        self.clear_tag_btn.clicked.connect(self._clear_tag_filter)
        self.clear_tag_btn.setVisible(False)
        controls.addWidget(self.tag_filter_label)
        controls.addWidget(self.clear_tag_btn)

        # Dropdown filters
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Backlog", "Playing", "Finished", "Dropped"])
        self.status_filter.setToolTip("Filter by game play status")
        status_label = self._status_filter.capitalize() if self._status_filter != "all" else "All"
        self.status_filter.setCurrentText(status_label)
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        controls.addWidget(QLabel("Status:"))
        controls.addWidget(self.status_filter)

        self.conf_filter = QComboBox()
        self.conf_filter.addItems(["All", "High", "Medium", "Low"])
        self.conf_filter.setToolTip("Filter by metadata confidence level")
        confidence_label = self._confidence_filter.capitalize() if self._confidence_filter != "all" else "All"
        self.conf_filter.setCurrentText(confidence_label)
        self.conf_filter.currentTextChanged.connect(self._on_filter_changed)
        controls.addWidget(QLabel("Confidence:"))
        controls.addWidget(self.conf_filter)

        self.type_filter = QComboBox()
        self.type_filter.addItems(["All", "lnk", "url", "html"])
        self.type_filter.setToolTip("Filter by shortcut file type")
        self.type_filter.setCurrentText(self._type_filter if self._type_filter != "all" else "All")
        self.type_filter.currentTextChanged.connect(self._on_filter_changed)
        controls.addWidget(QLabel("Type:"))
        controls.addWidget(self.type_filter)

        # Sort
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Title", "Last Played", "Rating", "Launch Count", "Last Checked"])
        self.sort_combo.setToolTip("Change how games are sorted in the grid")
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

        # View toggle
        self.view_comfort = QPushButton("Comfortable")
        self.view_comfort.setToolTip("Larger cards with more details (200px height)")
        self.view_compact = QPushButton("Compact")
        self.view_compact.setToolTip("Smaller cards to see more games (150px height)")
        for btn in (self.view_comfort, self.view_compact):
            btn.setCheckable(True)
            btn.clicked.connect(self._on_view_mode_changed)
        controls.addWidget(self.view_comfort)
        controls.addWidget(self.view_compact)

        # Focus mode
        self.focus_btn = QPushButton("Focus")
        self.focus_btn.setToolTip("Hide side panels for full-width game grid")
        self.focus_btn.setCheckable(True)
        self.focus_btn.clicked.connect(self._toggle_focus_mode)
        self.focus_btn.setChecked(self._focus_mode)
        controls.addWidget(self.focus_btn)

        # Details toggle
        self.details_toggle = QToolButton()
        self.details_toggle.setText("Details")
        self.details_toggle.setToolTip("Show/hide the game details panel")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setChecked(self._details_visible)
        self.details_toggle.clicked.connect(self._toggle_details_panel)
        controls.addWidget(self.details_toggle)

        # Multi-select mode
        self.select_btn = QPushButton("Select")
        self.select_btn.setToolTip("Enable multi-select mode (Ctrl+Click to select multiple games)")
        self.select_btn.setCheckable(True)
        self.select_btn.clicked.connect(self._toggle_multi_select_mode)
        controls.addWidget(self.select_btn)

        controls.addStretch(1)
        return controls

    def _build_details_panel(self) -> QWidget:
        """Build the right details panel."""
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
        return details

    def _finalize_startup(self) -> None:
        """Finalize startup: apply modes, render, show status."""
        self._apply_focus_mode(initial=True)
        if self._details_on_launch:
            self._details_visible = True
            self.details_toggle.setChecked(True)
        self._apply_details_visibility(initial=True)
        self._log.info(
            "startup_layout_ready %s",
            kv(details_visible=self._details_visible, view_mode=self._view_mode,
               width=self.width(), height=self.height()),
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

    # Stub methods that may be referenced by undo/redo but not fully implemented
    def _persist_library(self) -> None:
        """Persist library (alias for _save_bundle)."""
        self._save_bundle()

    def _refresh_list(self) -> None:
        """Refresh list (alias for _apply_search)."""
        self._apply_search()
