"""Layout Customization dialog for configuring UI layout preferences."""
from __future__ import annotations
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QGroupBox, QComboBox, QListWidget, QListWidgetItem, QSlider,
    QFrame, QMessageBox, QFileDialog
)
from pathlib import Path


@dataclass
class LayoutConfig:
    """Configuration for UI layout."""
    # Panel visibility
    show_sidebar: bool = True
    show_details_panel: bool = True
    show_filter_chips: bool = True
    show_status_bar: bool = True
    show_toolbar: bool = True

    # Panel positions (future: allow rearrangement)
    sidebar_position: str = "left"  # left, right
    details_position: str = "right"  # right, bottom

    # Splitter sizes (percentages)
    sidebar_width_pct: int = 20
    details_width_pct: int = 30
    grid_width_pct: int = 50

    # Card display options
    card_fields: List[str] = field(default_factory=lambda: [
        "title", "status", "rating", "tags", "last_played"
    ])
    show_card_icons: bool = True
    show_card_badges: bool = True

    # Default view per collection (collection_id -> view_mode)
    collection_views: Dict[str, str] = field(default_factory=dict)

    # Startup state
    remember_last_collection: bool = True
    last_collection_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayoutConfig":
        """Create from dictionary."""
        # Handle missing fields gracefully
        valid_fields = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


# Available card fields that can be shown
AVAILABLE_CARD_FIELDS = [
    ("title", "Title", True),  # field, display_name, required
    ("status", "Status", False),
    ("rating", "Rating", False),
    ("tags", "Tags", False),
    ("last_played", "Last Played", False),
    ("launch_count", "Play Count", False),
    ("installed_version_raw", "Version", False),
    ("confidence", "Confidence", False),
    ("source_url", "Source URL", False),
    ("notes", "Notes Preview", False),
]


class LayoutCustomizationDialog(QDialog):
    """Dialog for customizing the UI layout."""

    layout_changed = Signal(object)  # Emits LayoutConfig when applied

    def __init__(self, parent=None, config: Optional[LayoutConfig] = None):
        super().__init__(parent)
        self.setWindowTitle("Layout Customization")
        self.setModal(True)
        self.setMinimumSize(500, 550)

        self._config = config or LayoutConfig()
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Panel Visibility
        visibility_group = QGroupBox("Panel Visibility")
        vis_layout = QVBoxLayout(visibility_group)

        self.chk_sidebar = QCheckBox("Show Sidebar (Collections)")
        self.chk_details = QCheckBox("Show Details Panel")
        self.chk_filter_chips = QCheckBox("Show Filter Chips Bar")
        self.chk_status_bar = QCheckBox("Show Status Bar")
        self.chk_toolbar = QCheckBox("Show Toolbar")

        vis_layout.addWidget(self.chk_sidebar)
        vis_layout.addWidget(self.chk_details)
        vis_layout.addWidget(self.chk_filter_chips)
        vis_layout.addWidget(self.chk_status_bar)
        vis_layout.addWidget(self.chk_toolbar)

        layout.addWidget(visibility_group)

        # Panel Positions
        positions_group = QGroupBox("Panel Positions")
        pos_layout = QVBoxLayout(positions_group)

        sidebar_row = QHBoxLayout()
        sidebar_row.addWidget(QLabel("Sidebar Position:"))
        self.sidebar_pos_combo = QComboBox()
        self.sidebar_pos_combo.addItems(["Left", "Right"])
        sidebar_row.addWidget(self.sidebar_pos_combo)
        sidebar_row.addStretch()
        pos_layout.addLayout(sidebar_row)

        details_row = QHBoxLayout()
        details_row.addWidget(QLabel("Details Panel Position:"))
        self.details_pos_combo = QComboBox()
        self.details_pos_combo.addItems(["Right", "Bottom"])
        details_row.addWidget(self.details_pos_combo)
        details_row.addStretch()
        pos_layout.addLayout(details_row)

        layout.addWidget(positions_group)

        # Panel Sizes
        sizes_group = QGroupBox("Panel Sizes")
        sizes_layout = QVBoxLayout(sizes_group)

        # Sidebar width
        sidebar_size_row = QHBoxLayout()
        sidebar_size_row.addWidget(QLabel("Sidebar Width:"))
        self.sidebar_slider = QSlider(Qt.Horizontal)
        self.sidebar_slider.setRange(10, 40)
        self.sidebar_slider.setTickInterval(5)
        self.sidebar_slider.setTickPosition(QSlider.TicksBelow)
        self.sidebar_label = QLabel("20%")
        self.sidebar_slider.valueChanged.connect(
            lambda v: self.sidebar_label.setText(f"{v}%")
        )
        sidebar_size_row.addWidget(self.sidebar_slider)
        sidebar_size_row.addWidget(self.sidebar_label)
        sizes_layout.addLayout(sidebar_size_row)

        # Details width
        details_size_row = QHBoxLayout()
        details_size_row.addWidget(QLabel("Details Panel Width:"))
        self.details_slider = QSlider(Qt.Horizontal)
        self.details_slider.setRange(20, 50)
        self.details_slider.setTickInterval(5)
        self.details_slider.setTickPosition(QSlider.TicksBelow)
        self.details_label = QLabel("30%")
        self.details_slider.valueChanged.connect(
            lambda v: self.details_label.setText(f"{v}%")
        )
        details_size_row.addWidget(self.details_slider)
        details_size_row.addWidget(self.details_label)
        sizes_layout.addLayout(details_size_row)

        layout.addWidget(sizes_group)

        # Card Display Fields
        cards_group = QGroupBox("Card Display Fields")
        cards_layout = QVBoxLayout(cards_group)

        cards_layout.addWidget(QLabel("Select fields to display on game cards:"))

        self.fields_list = QListWidget()
        self.fields_list.setDragDropMode(QListWidget.InternalMove)
        for field_id, display_name, required in AVAILABLE_CARD_FIELDS:
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, field_id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if required:
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Checked)
            self.fields_list.addItem(item)

        cards_layout.addWidget(self.fields_list)

        card_options_row = QHBoxLayout()
        self.chk_card_icons = QCheckBox("Show Game Icons")
        self.chk_card_badges = QCheckBox("Show Status Badges")
        card_options_row.addWidget(self.chk_card_icons)
        card_options_row.addWidget(self.chk_card_badges)
        card_options_row.addStretch()
        cards_layout.addLayout(card_options_row)

        layout.addWidget(cards_group)

        # Startup Behavior
        startup_group = QGroupBox("Startup Behavior")
        startup_layout = QVBoxLayout(startup_group)

        self.chk_remember_collection = QCheckBox("Remember last selected collection")
        startup_layout.addWidget(self.chk_remember_collection)

        layout.addWidget(startup_group)

        # Import/Export
        io_row = QHBoxLayout()
        import_btn = QPushButton("Import Layout...")
        import_btn.clicked.connect(self._import_layout)
        export_btn = QPushButton("Export Layout...")
        export_btn.clicked.connect(self._export_layout)
        io_row.addWidget(import_btn)
        io_row.addWidget(export_btn)
        io_row.addStretch()
        layout.addLayout(io_row)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(reset_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        btn_row.addWidget(apply_btn)

        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._ok)
        btn_row.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _load_config(self):
        """Load current config into UI."""
        c = self._config

        # Visibility
        self.chk_sidebar.setChecked(c.show_sidebar)
        self.chk_details.setChecked(c.show_details_panel)
        self.chk_filter_chips.setChecked(c.show_filter_chips)
        self.chk_status_bar.setChecked(c.show_status_bar)
        self.chk_toolbar.setChecked(c.show_toolbar)

        # Positions
        self.sidebar_pos_combo.setCurrentText(c.sidebar_position.capitalize())
        self.details_pos_combo.setCurrentText(c.details_position.capitalize())

        # Sizes
        self.sidebar_slider.setValue(c.sidebar_width_pct)
        self.details_slider.setValue(c.details_width_pct)

        # Card fields
        selected_fields = set(c.card_fields)
        for i in range(self.fields_list.count()):
            item = self.fields_list.item(i)
            field_id = item.data(Qt.UserRole)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(
                    Qt.Checked if field_id in selected_fields else Qt.Unchecked
                )

        # Card options
        self.chk_card_icons.setChecked(c.show_card_icons)
        self.chk_card_badges.setChecked(c.show_card_badges)

        # Startup
        self.chk_remember_collection.setChecked(c.remember_last_collection)

    def _build_config(self) -> LayoutConfig:
        """Build config from UI state."""
        # Get selected card fields
        card_fields = []
        for i in range(self.fields_list.count()):
            item = self.fields_list.item(i)
            if item.checkState() == Qt.Checked:
                card_fields.append(item.data(Qt.UserRole))

        return LayoutConfig(
            show_sidebar=self.chk_sidebar.isChecked(),
            show_details_panel=self.chk_details.isChecked(),
            show_filter_chips=self.chk_filter_chips.isChecked(),
            show_status_bar=self.chk_status_bar.isChecked(),
            show_toolbar=self.chk_toolbar.isChecked(),
            sidebar_position=self.sidebar_pos_combo.currentText().lower(),
            details_position=self.details_pos_combo.currentText().lower(),
            sidebar_width_pct=self.sidebar_slider.value(),
            details_width_pct=self.details_slider.value(),
            grid_width_pct=100 - self.sidebar_slider.value() - self.details_slider.value(),
            card_fields=card_fields,
            show_card_icons=self.chk_card_icons.isChecked(),
            show_card_badges=self.chk_card_badges.isChecked(),
            collection_views=self._config.collection_views,
            remember_last_collection=self.chk_remember_collection.isChecked(),
            last_collection_id=self._config.last_collection_id,
        )

    def _reset_defaults(self):
        """Reset to default layout."""
        self._config = LayoutConfig()
        self._load_config()

    def _apply(self):
        """Apply without closing."""
        config = self._build_config()
        self.layout_changed.emit(config)

    def _ok(self):
        """Apply and close."""
        self._apply()
        self.accept()

    def _import_layout(self):
        """Import layout from JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Layout",
            str(Path.home()),
            "JSON Files (*.json)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._config = LayoutConfig.from_dict(data)
            self._load_config()
            QMessageBox.information(self, "Import", "Layout imported successfully!")
        except Exception as e:
            QMessageBox.warning(self, "Import Failed", f"Could not import layout: {e}")

    def _export_layout(self):
        """Export layout to JSON file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Layout",
            str(Path.home() / "layout_config.json"),
            "JSON Files (*.json)"
        )
        if not path:
            return

        try:
            config = self._build_config()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2)
            QMessageBox.information(self, "Export", f"Layout exported to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Could not export layout: {e}")

    def get_config(self) -> LayoutConfig:
        """Get the current configuration."""
        return self._build_config()
