"""Theme Editor dialog for customizing application themes."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QGroupBox, QScrollArea, QWidget, QFrame, QColorDialog, QLineEdit,
    QFileDialog, QMessageBox, QGridLayout, QSpinBox, QTabWidget
)

from app.ui.theme import THEMES, ThemeSpec, _c


class ColorButton(QPushButton):
    """Button that displays and allows selecting a color."""

    color_changed = Signal(QColor)

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(60, 28)
        self.clicked.connect(self._pick_color)
        self._update_style()

    @property
    def color(self) -> QColor:
        return self._color

    @color.setter
    def color(self, c: QColor):
        self._color = c
        self._update_style()
        self.color_changed.emit(c)

    def _update_style(self):
        # Show color with border for visibility
        self.setStyleSheet(
            f"background-color: {self._color.name(QColor.HexArgb)}; "
            f"border: 2px solid #555; border-radius: 4px;"
        )
        self.setToolTip(self._color.name(QColor.HexArgb))

    def _pick_color(self):
        color = QColorDialog.getColor(
            self._color, self, "Select Color",
            QColorDialog.ShowAlphaChannel
        )
        if color.isValid():
            self.color = color


class ThemeEditorDialog(QDialog):
    """Dialog for creating and editing custom themes."""

    theme_changed = Signal(dict)  # Emits theme data when saved

    # Color field definitions: (field_name, display_name, group)
    COLOR_FIELDS = [
        ("bg", "Background", "Base"),
        ("surface", "Surface", "Base"),
        ("surface_alt", "Surface Alt", "Base"),
        ("card", "Card Background", "Cards"),
        ("card_border", "Card Border", "Cards"),
        ("card_hover", "Card Hover", "Cards"),
        ("text", "Text", "Text"),
        ("text_muted", "Text Muted", "Text"),
        ("accent", "Accent", "Accent"),
        ("accent_alt", "Accent Alt", "Accent"),
        ("chip_bg", "Chip Background", "Chips"),
        ("chip_border", "Chip Border", "Chips"),
        ("focus", "Focus Ring", "Interactive"),
        ("outline", "Outline", "Interactive"),
        ("shadow", "Shadow", "Interactive"),
    ]

    # Numeric field definitions
    NUMERIC_FIELDS = [
        ("spacing_xs", "Spacing XS", 0, 24),
        ("spacing_sm", "Spacing SM", 0, 32),
        ("spacing_md", "Spacing MD", 0, 48),
        ("spacing_lg", "Spacing LG", 0, 64),
        ("spacing_xl", "Spacing XL", 0, 96),
        ("radius_sm", "Radius SM", 0, 32),
        ("radius_md", "Radius MD", 0, 48),
        ("radius_lg", "Radius LG", 0, 64),
        ("radius_xl", "Radius XL", 0, 96),
        ("anim_fast", "Anim Fast (ms)", 0, 500),
        ("anim_normal", "Anim Normal (ms)", 0, 1000),
        ("anim_slow", "Anim Slow (ms)", 0, 2000),
        ("elevation_low", "Elevation Low", 0, 255),
        ("elevation_mid", "Elevation Mid", 0, 255),
        ("elevation_high", "Elevation High", 0, 255),
    ]

    def __init__(self, parent=None, current_theme: str = "dark"):
        super().__init__(parent)
        self.setWindowTitle("Theme Editor")
        self.setModal(True)
        self.setMinimumSize(700, 600)

        self._color_buttons: Dict[str, ColorButton] = {}
        self._numeric_spinboxes: Dict[str, QSpinBox] = {}
        self._base_theme = current_theme
        self._custom_name = ""

        self._setup_ui()
        self._load_theme(current_theme)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Theme selector
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Base Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([spec.name for spec in THEMES.values()])
        self._theme_keys = list(THEMES.keys())
        self.theme_combo.currentIndexChanged.connect(self._on_base_theme_changed)
        top_row.addWidget(self.theme_combo, 1)

        top_row.addWidget(QLabel("Custom Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My Custom Theme")
        top_row.addWidget(self.name_edit, 1)

        layout.addLayout(top_row)

        # Tab widget for colors and tokens
        tabs = QTabWidget()

        # Colors tab
        colors_widget = QWidget()
        colors_layout = QVBoxLayout(colors_widget)

        # Create grouped color editors
        groups: Dict[str, list] = {}
        for field, name, group in self.COLOR_FIELDS:
            if group not in groups:
                groups[group] = []
            groups[group].append((field, name))

        colors_grid = QGridLayout()
        col = 0
        for group_name, fields in groups.items():
            group_box = QGroupBox(group_name)
            group_layout = QGridLayout(group_box)

            for row, (field, name) in enumerate(fields):
                group_layout.addWidget(QLabel(name + ":"), row, 0)
                btn = ColorButton(QColor(128, 128, 128))
                btn.color_changed.connect(self._on_color_changed)
                self._color_buttons[field] = btn
                group_layout.addWidget(btn, row, 1)

            colors_grid.addWidget(group_box, col // 3, col % 3)
            col += 1

        colors_layout.addLayout(colors_grid)
        colors_layout.addStretch()
        tabs.addTab(colors_widget, "Colors")

        # Tokens tab (spacing, radius, animation)
        tokens_widget = QWidget()
        tokens_layout = QVBoxLayout(tokens_widget)

        tokens_grid = QGridLayout()
        for i, (field, name, min_val, max_val) in enumerate(self.NUMERIC_FIELDS):
            row, col = i // 3, i % 3
            h = QHBoxLayout()
            h.addWidget(QLabel(name + ":"))
            spin = QSpinBox()
            spin.setRange(min_val, max_val)
            spin.valueChanged.connect(self._on_value_changed)
            self._numeric_spinboxes[field] = spin
            h.addWidget(spin)
            tokens_grid.addLayout(h, row, col)

        tokens_layout.addLayout(tokens_grid)
        tokens_layout.addStretch()
        tabs.addTab(tokens_widget, "Design Tokens")

        # Preview tab
        preview_widget = self._create_preview_widget()
        tabs.addTab(preview_widget, "Preview")

        layout.addWidget(tabs)

        # Import/Export buttons
        io_row = QHBoxLayout()
        import_btn = QPushButton("Import Theme...")
        import_btn.clicked.connect(self._import_theme)
        export_btn = QPushButton("Export Theme...")
        export_btn.clicked.connect(self._export_theme)
        io_row.addWidget(import_btn)
        io_row.addWidget(export_btn)
        io_row.addStretch()
        layout.addLayout(io_row)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        reset_btn = QPushButton("Reset to Base")
        reset_btn.clicked.connect(self._reset_to_base)
        btn_row.addWidget(reset_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply_theme)
        btn_row.addWidget(apply_btn)

        save_btn = QPushButton("Save && Apply")
        save_btn.clicked.connect(self._save_and_apply)
        btn_row.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _create_preview_widget(self) -> QWidget:
        """Create a preview widget showing theme colors."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.preview_frame = QFrame()
        self.preview_frame.setFrameShape(QFrame.StyledPanel)
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setSpacing(12)

        # Title
        self.preview_title = QLabel("Preview: Sample Game")
        self.preview_title.setStyleSheet("font-weight: bold; font-size: 16px;")
        preview_layout.addWidget(self.preview_title)

        # Subtitle
        self.preview_subtitle = QLabel("Status: Playing | Rating: 8/10")
        preview_layout.addWidget(self.preview_subtitle)

        # Card sample
        self.preview_card = QFrame()
        self.preview_card.setFrameShape(QFrame.StyledPanel)
        card_layout = QVBoxLayout(self.preview_card)
        self.preview_card_title = QLabel("Game Card")
        self.preview_card_text = QLabel("This is how game cards will appear")
        card_layout.addWidget(self.preview_card_title)
        card_layout.addWidget(self.preview_card_text)
        preview_layout.addWidget(self.preview_card)

        # Buttons
        btn_row = QHBoxLayout()
        self.preview_btn_primary = QPushButton("Primary Action")
        self.preview_btn_secondary = QPushButton("Secondary")
        btn_row.addWidget(self.preview_btn_primary)
        btn_row.addWidget(self.preview_btn_secondary)
        btn_row.addStretch()
        preview_layout.addLayout(btn_row)

        # Chips
        chip_row = QHBoxLayout()
        self.preview_chip1 = QLabel(" Tag: RPG ")
        self.preview_chip2 = QLabel(" Status: Active ")
        chip_row.addWidget(self.preview_chip1)
        chip_row.addWidget(self.preview_chip2)
        chip_row.addStretch()
        preview_layout.addLayout(chip_row)

        preview_layout.addStretch()
        layout.addWidget(self.preview_frame)

        return widget

    def _load_theme(self, theme_key: str):
        """Load a theme into the editor."""
        if theme_key not in THEMES:
            theme_key = "dark"

        spec = THEMES[theme_key]
        self._base_theme = theme_key

        # Set combo box
        try:
            idx = self._theme_keys.index(theme_key)
            self.theme_combo.setCurrentIndex(idx)
        except ValueError:
            pass

        # Load colors
        for field, _, _ in self.COLOR_FIELDS:
            color = getattr(spec, field, QColor(128, 128, 128))
            if field in self._color_buttons:
                self._color_buttons[field].color = color

        # Load numeric values
        for field, _, _, _ in self.NUMERIC_FIELDS:
            value = getattr(spec, field, 0)
            if field in self._numeric_spinboxes:
                self._numeric_spinboxes[field].setValue(value)

        self._update_preview()

    def _on_base_theme_changed(self, index: int):
        """Handle base theme selection change."""
        if 0 <= index < len(self._theme_keys):
            self._load_theme(self._theme_keys[index])

    def _on_color_changed(self, color: QColor):
        """Handle color change."""
        self._update_preview()

    def _on_value_changed(self, value: int):
        """Handle numeric value change."""
        self._update_preview()

    def _update_preview(self):
        """Update the preview widget with current colors."""
        colors = self._get_current_colors()

        bg = colors["bg"]
        surface = colors["surface"]
        card = colors["card"]
        card_border = colors["card_border"]
        text = colors["text"]
        text_muted = colors["text_muted"]
        accent = colors["accent"]
        accent_alt = colors["accent_alt"]
        chip_bg = colors["chip_bg"]
        chip_border = colors["chip_border"]

        radius = self._numeric_spinboxes.get("radius_md", None)
        r = radius.value() if radius else 10

        # Preview frame
        self.preview_frame.setStyleSheet(
            f"QFrame {{ background: {bg.name(QColor.HexArgb)}; "
            f"border: 1px solid {card_border.name(QColor.HexArgb)}; "
            f"border-radius: {r}px; }}"
        )

        # Title
        self.preview_title.setStyleSheet(
            f"color: {text.name()}; font-weight: bold; font-size: 16px; background: transparent;"
        )

        # Subtitle
        self.preview_subtitle.setStyleSheet(
            f"color: {text_muted.name()}; background: transparent;"
        )

        # Card
        self.preview_card.setStyleSheet(
            f"QFrame {{ background: {card.name(QColor.HexArgb)}; "
            f"border: 1px solid {card_border.name(QColor.HexArgb)}; "
            f"border-radius: {r - 2}px; }}"
        )
        self.preview_card_title.setStyleSheet(
            f"color: {text.name()}; font-weight: 600; background: transparent;"
        )
        self.preview_card_text.setStyleSheet(
            f"color: {text_muted.name()}; background: transparent;"
        )

        # Buttons
        self.preview_btn_primary.setStyleSheet(
            f"background: {accent.name(QColor.HexArgb)}; "
            f"color: {bg.name()}; border: none; border-radius: {r - 4}px; "
            f"padding: 6px 12px;"
        )
        self.preview_btn_secondary.setStyleSheet(
            f"background: {surface.name(QColor.HexArgb)}; "
            f"color: {text.name()}; border: 1px solid {card_border.name(QColor.HexArgb)}; "
            f"border-radius: {r - 4}px; padding: 6px 12px;"
        )

        # Chips
        chip_style = (
            f"background: {chip_bg.name(QColor.HexArgb)}; "
            f"color: {text.name()}; border: 1px solid {chip_border.name(QColor.HexArgb)}; "
            f"border-radius: {r - 4}px; padding: 2px 8px;"
        )
        self.preview_chip1.setStyleSheet(chip_style)
        self.preview_chip2.setStyleSheet(
            f"background: {accent.name(QColor.HexArgb)}; "
            f"color: {bg.name()}; border: none; "
            f"border-radius: {r - 4}px; padding: 2px 8px;"
        )

    def _get_current_colors(self) -> Dict[str, QColor]:
        """Get current color values from buttons."""
        colors = {}
        for field, _, _ in self.COLOR_FIELDS:
            if field in self._color_buttons:
                colors[field] = self._color_buttons[field].color
            else:
                colors[field] = QColor(128, 128, 128)
        return colors

    def _get_current_tokens(self) -> Dict[str, int]:
        """Get current numeric token values."""
        tokens = {}
        for field, _, _, _ in self.NUMERIC_FIELDS:
            if field in self._numeric_spinboxes:
                tokens[field] = self._numeric_spinboxes[field].value()
        return tokens

    def _build_theme_data(self) -> dict:
        """Build theme data dictionary for export/apply."""
        colors = self._get_current_colors()
        tokens = self._get_current_tokens()

        data = {
            "name": self.name_edit.text() or "Custom Theme",
            "base": self._base_theme,
            "colors": {},
            "tokens": tokens,
        }

        for field, color in colors.items():
            data["colors"][field] = {
                "r": color.red(),
                "g": color.green(),
                "b": color.blue(),
                "a": color.alpha(),
            }

        return data

    def _reset_to_base(self):
        """Reset to the base theme."""
        self._load_theme(self._base_theme)

    def _apply_theme(self):
        """Apply the theme without saving."""
        data = self._build_theme_data()
        self.theme_changed.emit(data)

    def _save_and_apply(self):
        """Save and apply the theme."""
        data = self._build_theme_data()
        self.theme_changed.emit(data)
        self.accept()

    def _import_theme(self):
        """Import a theme from JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Theme",
            str(Path.home()),
            "JSON Files (*.json)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Load colors
            if "colors" in data:
                for field, color_data in data["colors"].items():
                    if field in self._color_buttons:
                        c = QColor(
                            color_data.get("r", 128),
                            color_data.get("g", 128),
                            color_data.get("b", 128),
                            color_data.get("a", 255)
                        )
                        self._color_buttons[field].color = c

            # Load tokens
            if "tokens" in data:
                for field, value in data["tokens"].items():
                    if field in self._numeric_spinboxes:
                        self._numeric_spinboxes[field].setValue(value)

            # Load name
            if "name" in data:
                self.name_edit.setText(data["name"])

            self._update_preview()
            QMessageBox.information(self, "Import", "Theme imported successfully!")

        except Exception as e:
            QMessageBox.warning(self, "Import Failed", f"Could not import theme: {e}")

    def _export_theme(self):
        """Export the current theme to JSON file."""
        name = self.name_edit.text() or "custom_theme"
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Theme",
            str(Path.home() / f"{safe_name}.json"),
            "JSON Files (*.json)"
        )
        if not path:
            return

        try:
            data = self._build_theme_data()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            QMessageBox.information(self, "Export", f"Theme exported to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Could not export theme: {e}")

    def get_theme_spec(self) -> Optional[ThemeSpec]:
        """Convert current settings to a ThemeSpec."""
        colors = self._get_current_colors()
        tokens = self._get_current_tokens()

        try:
            return ThemeSpec(
                name=self.name_edit.text() or "Custom",
                bg=colors["bg"],
                surface=colors["surface"],
                surface_alt=colors["surface_alt"],
                card=colors["card"],
                card_border=colors["card_border"],
                card_hover=colors["card_hover"],
                text=colors["text"],
                text_muted=colors["text_muted"],
                accent=colors["accent"],
                accent_alt=colors["accent_alt"],
                chip_bg=colors["chip_bg"],
                chip_border=colors["chip_border"],
                focus=colors["focus"],
                outline=colors["outline"],
                shadow=colors["shadow"],
                **tokens
            )
        except Exception:
            return None
