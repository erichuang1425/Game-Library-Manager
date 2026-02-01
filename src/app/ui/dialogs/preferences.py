from __future__ import annotations
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QCheckBox, QPushButton, QComboBox, QGroupBox,
    QFrame, QWidget
)

from app.ui.theme import THEMES, FONTS, FONT_SCALES


class PreferencesDialog(QDialog):
    apply_clicked = Signal(dict)

    def __init__(
        self,
        parent=None,
        view_mode: str = "comfortable",
        details_on_launch: bool = False,
        details_on_selection: bool = True,
        theme: str = "dark",
        font_family: str = "Segoe UI",
        font_scale: str = "default",
    ):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)

        layout = QVBoxLayout(self)

        appearance = QGroupBox("Appearance")
        applayout = QVBoxLayout(appearance)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([spec.name for spec in THEMES.values()])
        # map theme key -> display name
        self._theme_keys = [k for k in THEMES.keys()]
        try:
            idx = self._theme_keys.index(theme.lower())
            self.theme_combo.setCurrentIndex(idx)
        except ValueError:
            pass
        theme_row.addWidget(self.theme_combo, 1)
        applayout.addLayout(theme_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel("Font:"))
        self.font_combo = QComboBox()
        self.font_combo.addItems(list(FONTS.keys()))
        if font_family in FONTS:
            self.font_combo.setCurrentText(font_family)
        font_row.addWidget(self.font_combo, 1)
        applayout.addLayout(font_row)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("Font size:"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["Small", "Default", "Large"])
        scale_map = {"small": "Small", "default": "Default", "large": "Large"}
        self.scale_combo.setCurrentText(scale_map.get(font_scale, "Default"))
        scale_row.addWidget(self.scale_combo, 1)
        applayout.addLayout(scale_row)

        preview_wrap = QVBoxLayout()
        preview_wrap.addWidget(QLabel("Preview"))
        self.preview_card = self._build_preview_card()
        preview_wrap.addWidget(self.preview_card)
        applayout.addLayout(preview_wrap)

        layout.addWidget(appearance)

        layout_group = QGroupBox("Layout")
        lay_layout = QVBoxLayout(layout_group)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Default view:"))
        self.radio_comfort = QRadioButton("Comfortable")
        self.radio_compact = QRadioButton("Compact")
        if view_mode == "compact":
            self.radio_compact.setChecked(True)
        else:
            self.radio_comfort.setChecked(True)
        mode_row.addWidget(self.radio_comfort)
        mode_row.addWidget(self.radio_compact)
        mode_row.addStretch(1)
        lay_layout.addLayout(mode_row)

        layout.addWidget(layout_group)

        behavior = QGroupBox("Behavior")
        beh_layout = QVBoxLayout(behavior)

        self.chk_details_launch = QCheckBox("Show Details panel on launch")
        self.chk_details_launch.setChecked(details_on_launch)
        self.chk_details_select = QCheckBox("Open Details when selecting a game")
        self.chk_details_select.setChecked(details_on_selection)
        beh_layout.addWidget(self.chk_details_launch)
        beh_layout.addWidget(self.chk_details_select)

        reset_row = QHBoxLayout()
        self.reset_layout_btn = QPushButton("Reset layout splitters")
        self._reset_requested = False
        self.reset_layout_btn.clicked.connect(lambda: setattr(self, "_reset_requested", True))
        reset_row.addWidget(self.reset_layout_btn)
        reset_row.addStretch(1)
        beh_layout.addLayout(reset_row)

        layout.addWidget(behavior)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.reset_btn = QPushButton("Reset to defaults")
        self.reset_btn.clicked.connect(self._on_reset)
        btns.addWidget(self.reset_btn)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._on_apply)
        btns.addWidget(self.apply_btn)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

        # live preview updates (not applied globally)
        self.theme_combo.currentIndexChanged.connect(self._apply_preview_styles)
        self.font_combo.currentIndexChanged.connect(self._apply_preview_styles)
        self.scale_combo.currentIndexChanged.connect(self._apply_preview_styles)
        self._apply_preview_styles()

    def values(self):
        mode = "compact" if self.radio_compact.isChecked() else "comfortable"
        return {
            "view_mode": mode,
            "details_on_launch": self.chk_details_launch.isChecked(),
            "details_on_selection": self.chk_details_select.isChecked(),
            "theme": self._theme_keys[self.theme_combo.currentIndex()],
            "font_family": self.font_combo.currentText(),
            "font_scale": {
                "Small": "small",
                "Default": "default",
                "Large": "large",
            }.get(self.scale_combo.currentText(), "default"),
            "reset_layout": self._reset_requested,
        }

    # ---- preview helpers ----
    def _build_preview_card(self) -> QWidget:
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(6)
        self.prev_title = QLabel("Sample Game Title")
        self.prev_meta = QLabel("Status • URL • v0.1.0")
        self.prev_chips = QLabel("★ ★ ★ ☆ ☆    Tag: Sandbox")
        self.prev_button = QPushButton("Play")
        v.addWidget(self.prev_title)
        v.addWidget(self.prev_meta)
        v.addWidget(self.prev_chips)
        v.addStretch(1)
        v.addWidget(self.prev_button, alignment=Qt.AlignLeft)
        return card

    def _current_theme_key(self) -> str:
        return self._theme_keys[self.theme_combo.currentIndex()]

    def _current_scale(self) -> float:
        return {"Small": 0.9, "Default": 1.0, "Large": 1.15}.get(self.scale_combo.currentText(), 1.0)

    def _apply_preview_styles(self) -> None:
        key = self._current_theme_key()
        spec = THEMES.get(key, list(THEMES.values())[0])
        scale = self._current_scale()
        font_family = self.font_combo.currentText()
        base_font = QFont(font_family, max(9, round(10 * scale)))
        self.preview_card.setFont(base_font)
        # ensure children inherit
        for child in self.preview_card.findChildren(QWidget):
            child.setFont(base_font)

        pal = QPalette()
        pal.setColor(QPalette.Window, spec.card)
        pal.setColor(QPalette.WindowText, spec.text)
        self.preview_card.setAutoFillBackground(True)
        self.preview_card.setPalette(pal)

        css = (
            f"QFrame {{ background:{spec.card.name(QColor.HexArgb)}; "
            f"border: 2px solid {spec.card_border.name(QColor.HexArgb)}; border-radius: 12px; }}"
            f"QLabel {{ color:{spec.text.name(QColor.HexArgb)}; }}"
            f"QPushButton {{ background:{spec.accent.name(QColor.HexArgb)}; color:{spec.bg.name(QColor.HexArgb)}; "
            f"border:0; border-radius:8px; padding:6px 10px; }}"
            f"QPushButton:hover {{ background:{spec.accent_alt.name(QColor.HexArgb)}; }}"
        )
        self.preview_card.setStyleSheet(css)
        self.prev_title.setStyleSheet(f"font-weight:700; font-size:{round(15*scale)}px;")
        self.prev_meta.setStyleSheet(f"color:{spec.text_muted.name(QColor.HexArgb)}; font-size:{round(11*scale)}px;")
        self.prev_chips.setStyleSheet(f"color:{spec.accent_alt.name(QColor.HexArgb)}; font-size:{round(12*scale)}px;")
        # spacing reflects scale
        m = max(8, round(12 * scale))
        layout: QVBoxLayout = self.preview_card.layout()
        layout.setContentsMargins(m, m, m, m)
        layout.setSpacing(max(4, round(6 * scale)))
        # force style refresh on the preview only
        self.preview_card.style().unpolish(self.preview_card)
        self.preview_card.style().polish(self.preview_card)
        self.preview_card.updateGeometry()
        self.preview_card.update()
        # simple assurance: set window title temporarily for debugging font family
        _ = self.prev_title.font().family()

    def _on_apply(self) -> None:
        self.apply_clicked.emit(self.values())

    def _on_ok(self) -> None:
        self.apply_clicked.emit(self.values())
        self.accept()

    def _on_reset(self) -> None:
        # defaults
        self.theme_combo.setCurrentIndex(self._theme_keys.index("dark"))
        self.font_combo.setCurrentText("Segoe UI")
        self.scale_combo.setCurrentText("Default")
        self.radio_comfort.setChecked(True)
        self.radio_compact.setChecked(False)
        self.chk_details_launch.setChecked(False)
        self.chk_details_select.setChecked(True)
        self._reset_requested = True
        self._apply_preview_styles()
