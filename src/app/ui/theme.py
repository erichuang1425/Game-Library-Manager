from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

from PySide6.QtGui import QColor, QPalette, QFont
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeSpec:
    name: str
    bg: QColor
    surface: QColor
    surface_alt: QColor
    card: QColor
    card_border: QColor
    card_hover: QColor
    text: QColor
    text_muted: QColor
    accent: QColor
    accent_alt: QColor
    chip_bg: QColor
    chip_border: QColor
    focus: QColor
    outline: QColor
    shadow: QColor


def _c(r: int, g: int, b: int, a: int = 255) -> QColor:
    return QColor(r, g, b, a)


THEMES: Dict[str, ThemeSpec] = {
    "dark": ThemeSpec(
        name="Dark",
        bg=_c(20, 23, 30),
        surface=_c(30, 34, 44),
        surface_alt=_c(40, 45, 55),
        card=_c(36, 42, 52),
        card_border=_c(66, 73, 87),
        card_hover=_c(80, 105, 130),
        text=_c(235, 238, 245),
        text_muted=_c(170, 178, 190),
        accent=_c(92, 193, 255),
        accent_alt=_c(255, 203, 92),
        chip_bg=_c(52, 61, 75),
        chip_border=_c(70, 83, 98),
        focus=_c(92, 193, 255),
        outline=_c(60, 68, 82),
        shadow=_c(0, 0, 0, 150),
    ),
    "light": ThemeSpec(
        name="Light",
        bg=_c(246, 249, 252),
        surface=_c(255, 255, 255),
        surface_alt=_c(243, 246, 250),
        card=_c(255, 255, 255),
        card_border=_c(215, 222, 232),
        card_hover=_c(190, 210, 240),
        text=_c(28, 32, 38),
        text_muted=_c(92, 104, 118),
        accent=_c(41, 121, 255),
        accent_alt=_c(255, 152, 0),
        chip_bg=_c(235, 240, 248),
        chip_border=_c(210, 218, 230),
        focus=_c(41, 121, 255),
        outline=_c(200, 210, 225),
        shadow=_c(0, 0, 0, 80),
    ),
    "neubrutalism": ThemeSpec(
        name="Neubrutalism",
        bg=_c(247, 247, 247),
        surface=_c(250, 250, 250),
        surface_alt=_c(255, 255, 255),
        card=_c(255, 255, 255),
        card_border=_c(30, 30, 30),
        card_hover=_c(255, 240, 150),
        text=_c(20, 20, 20),
        text_muted=_c(60, 60, 60),
        accent=_c(255, 94, 91),
        accent_alt=_c(72, 133, 237),
        chip_bg=_c(255, 255, 160),
        chip_border=_c(30, 30, 30),
        focus=_c(72, 133, 237),
        outline=_c(30, 30, 30),
        shadow=_c(0, 0, 0, 180),
    ),
    "neumorphism": ThemeSpec(
        name="Neumorphism",
        bg=_c(228, 233, 241),
        surface=_c(235, 240, 247),
        surface_alt=_c(220, 226, 235),
        card=_c(235, 240, 247),
        card_border=_c(210, 216, 226),
        card_hover=_c(205, 213, 225),
        text=_c(46, 55, 70),
        text_muted=_c(100, 110, 125),
        accent=_c(126, 87, 194),
        accent_alt=_c(0, 191, 165),
        chip_bg=_c(220, 226, 235),
        chip_border=_c(210, 216, 226),
        focus=_c(126, 87, 194),
        outline=_c(190, 198, 212),
        shadow=_c(0, 0, 0, 70),
    ),
    "glassmorphism": ThemeSpec(
        name="Glassmorphism",
        bg=_c(12, 18, 30),
        surface=_c(20, 28, 44, 180),
        surface_alt=_c(28, 38, 58, 200),
        card=_c(32, 46, 70, 210),
        card_border=_c(92, 193, 255, 120),
        card_hover=_c(92, 193, 255, 160),
        text=_c(235, 242, 255),
        text_muted=_c(180, 195, 220),
        accent=_c(92, 193, 255),
        accent_alt=_c(255, 255, 255),
        chip_bg=_c(92, 193, 255, 40),
        chip_border=_c(92, 193, 255, 90),
        focus=_c(92, 193, 255),
        outline=_c(72, 120, 160, 130),
        shadow=_c(0, 0, 0, 120),
    ),
}

FONTS = {
    "Segoe UI": "Segoe UI",
    "Arial": "Arial",
    "Calibri": "Calibri",
    "Consolas": "Consolas",
}

FONT_SCALES = {"small": 0.9, "default": 1.0, "large": 1.15}


def apply_theme(app: QApplication, theme_name: str, font_family: str, font_scale: str) -> None:
    theme = THEMES.get(theme_name.lower(), THEMES["dark"])
    scale = FONT_SCALES.get(font_scale, 1.0)

    # palette
    pal = QPalette()
    pal.setColor(QPalette.Window, theme.bg)
    pal.setColor(QPalette.Base, theme.surface)
    pal.setColor(QPalette.AlternateBase, theme.surface_alt)
    pal.setColor(QPalette.Button, theme.surface_alt)
    pal.setColor(QPalette.ButtonText, theme.text)
    pal.setColor(QPalette.Text, theme.text)
    pal.setColor(QPalette.WindowText, theme.text)
    pal.setColor(QPalette.Highlight, theme.focus)
    pal.setColor(QPalette.HighlightedText, theme.bg if theme.focus.value() > 128 else theme.text)
    pal.setColor(QPalette.Link, theme.accent)
    pal.setColor(QPalette.ToolTipBase, theme.surface_alt)
    pal.setColor(QPalette.ToolTipText, theme.text)
    app.setPalette(pal)

    base_font = QFont(font_family or "Segoe UI", max(9, round(10 * scale)))
    app.setFont(base_font)

    # Expose theme to widgets
    app.setProperty("theme_name", theme_name.lower())
    app.setProperty("theme_spec", theme)
    app.setProperty("font_scale", font_scale)
    app.setProperty("font_family", font_family)

    app.setStyle("Fusion")

    css = f"""
    QWidget {{
        color: {theme.text.name()};
        background: {theme.bg.name(QColor.HexArgb)};
    }}
    QToolTip {{
        background: {theme.surface_alt.name(QColor.HexArgb)};
        color: {theme.text.name()};
        border: 1px solid {theme.outline.name(QColor.HexArgb)};
    }}
    QLineEdit, QTextEdit, QComboBox, QListWidget, QTableWidget {{
        background: {theme.surface.name(QColor.HexArgb)};
        color: {theme.text.name()};
        border: 1px solid {theme.outline.name(QColor.HexArgb)};
        border-radius: 6px;
        selection-background-color: {theme.focus.name(QColor.HexArgb)};
        selection-color: {theme.bg.name(QColor.HexArgb)};
    }}
    QPushButton, QToolButton {{
        color: {theme.text.name()};
        background: {theme.surface_alt.name(QColor.HexArgb)};
        border: 1px solid {theme.outline.name(QColor.HexArgb)};
        border-radius: 8px;
        padding: 6px 10px;
    }}
    QPushButton:hover, QToolButton:hover {{
        border-color: {theme.focus.name(QColor.HexArgb)};
        background: {theme.surface_alt.lighter(108).name(QColor.HexArgb)};
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: {theme.surface_alt.darker(108).name(QColor.HexArgb)};
    }}
    QListWidget::item:selected, QTableWidget::item:selected {{
        background: {theme.focus.name(QColor.HexArgb)};
        color: {theme.bg.name(QColor.HexArgb)};
    }}
    QHeaderView::section {{
        background: {theme.surface_alt.name(QColor.HexArgb)};
        color: {theme.text.name()};
        border: 0px;
        padding: 4px 6px;
    }}
    """
    app.setStyleSheet(css)


def current_theme() -> ThemeSpec:
    app = QApplication.instance()
    if not app:
        return THEMES["dark"]
    spec = app.property("theme_spec")
    return spec if isinstance(spec, ThemeSpec) else THEMES["dark"]
