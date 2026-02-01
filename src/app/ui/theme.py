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
    # Design tokens - spacing (8px grid system)
    spacing_xs: int = 4
    spacing_sm: int = 8
    spacing_md: int = 12
    spacing_lg: int = 16
    spacing_xl: int = 24
    # Design tokens - border radius
    radius_sm: int = 6
    radius_md: int = 10
    radius_lg: int = 14
    radius_xl: int = 18
    # Design tokens - animation durations (ms)
    anim_fast: int = 100
    anim_normal: int = 180
    anim_slow: int = 280
    # Design tokens - elevation/shadow intensity (0-255 alpha)
    elevation_low: int = 20
    elevation_mid: int = 40
    elevation_high: int = 70


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

    # Use design tokens for consistent styling
    r_sm, r_md = theme.radius_sm, theme.radius_md
    sp_sm, sp_md = theme.spacing_sm, theme.spacing_md

    css = f"""
    QWidget {{
        color: {theme.text.name()};
        background: {theme.bg.name(QColor.HexArgb)};
    }}
    QToolTip {{
        background: {theme.surface_alt.name(QColor.HexArgb)};
        color: {theme.text.name()};
        border: 1px solid {theme.outline.name(QColor.HexArgb)};
        border-radius: {r_sm}px;
        padding: {sp_sm - 4}px {sp_sm}px;
    }}
    QLineEdit, QTextEdit, QComboBox, QListWidget, QTableWidget {{
        background: {theme.surface.name(QColor.HexArgb)};
        color: {theme.text.name()};
        border: 1px solid {theme.outline.name(QColor.HexArgb)};
        border-radius: {r_sm}px;
        padding: {sp_sm - 2}px;
        selection-background-color: {theme.focus.name(QColor.HexArgb)};
        selection-color: {theme.bg.name(QColor.HexArgb)};
    }}
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
        border-color: {theme.focus.name(QColor.HexArgb)};
    }}
    QPushButton, QToolButton {{
        color: {theme.text.name()};
        background: {theme.surface_alt.name(QColor.HexArgb)};
        border: 1px solid {theme.outline.name(QColor.HexArgb)};
        border-radius: {r_md}px;
        padding: {sp_sm - 2}px {sp_md}px;
    }}
    QPushButton:hover, QToolButton:hover {{
        border-color: {theme.focus.name(QColor.HexArgb)};
        background: {theme.surface_alt.lighter(108).name(QColor.HexArgb)};
    }}
    QPushButton:pressed, QToolButton:pressed {{
        background: {theme.surface_alt.darker(108).name(QColor.HexArgb)};
    }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {theme.text_muted.name()};
        background: {theme.surface.name(QColor.HexArgb)};
        border-color: {theme.outline.darker(110).name(QColor.HexArgb)};
    }}
    QListWidget::item {{
        padding: {sp_sm - 4}px {sp_sm}px;
        border-radius: {r_sm}px;
    }}
    QListWidget::item:selected, QTableWidget::item:selected {{
        background: {theme.focus.name(QColor.HexArgb)};
        color: {theme.bg.name(QColor.HexArgb)};
    }}
    QListWidget::item:hover {{
        background: {theme.surface_alt.name(QColor.HexArgb)};
    }}
    QHeaderView::section {{
        background: {theme.surface_alt.name(QColor.HexArgb)};
        color: {theme.text.name()};
        border: 0px;
        padding: {sp_sm - 2}px {sp_sm}px;
        font-weight: 600;
    }}
    QScrollBar:vertical {{
        background: {theme.surface.name(QColor.HexArgb)};
        width: 10px;
        border-radius: 5px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {theme.outline.name(QColor.HexArgb)};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {theme.text_muted.name()};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: {theme.surface.name(QColor.HexArgb)};
        height: 10px;
        border-radius: 5px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {theme.outline.name(QColor.HexArgb)};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {theme.text_muted.name()};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QComboBox::drop-down {{
        border: none;
        padding-right: {sp_sm}px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {theme.text_muted.name()};
    }}
    """
    app.setStyleSheet(css)


def current_theme() -> ThemeSpec:
    app = QApplication.instance()
    if not app:
        return THEMES["dark"]
    spec = app.property("theme_spec")
    return spec if isinstance(spec, ThemeSpec) else THEMES["dark"]


def shadow_style(theme: ThemeSpec, elevation: str = "mid") -> str:
    """Generate a box-shadow-like border effect for Qt widgets.

    Qt doesn't support CSS box-shadow, so we simulate depth with borders.
    For true shadows, use QGraphicsDropShadowEffect on the widget.

    Args:
        theme: Current theme spec
        elevation: "low", "mid", or "high"

    Returns:
        Border style string suggesting depth
    """
    alpha = getattr(theme, f"elevation_{elevation}", theme.elevation_mid)
    shadow_color = QColor(theme.shadow.red(), theme.shadow.green(), theme.shadow.blue(), alpha)
    return shadow_color.name(QColor.HexArgb)


def card_style(theme: ThemeSpec, hover: bool = False, radius: int | None = None) -> str:
    """Generate consistent card styling.

    Args:
        theme: Current theme spec
        hover: Whether this is for hover state
        radius: Override border radius (uses theme.radius_lg by default)

    Returns:
        Complete stylesheet for a card QFrame
    """
    r = radius if radius is not None else theme.radius_lg
    border_color = theme.card_hover if hover else theme.card_border
    bg = theme.card

    return (
        f"border: 1px solid {border_color.name(QColor.HexArgb)}; "
        f"border-radius: {r}px; "
        f"background: {bg.name(QColor.HexArgb)};"
    )


def chip_style(theme: ThemeSpec, bg_color: QColor | None = None, active: bool = False) -> str:
    """Generate consistent chip/pill button styling.

    Args:
        theme: Current theme spec
        bg_color: Override background color (uses theme.chip_bg by default)
        active: Whether this chip is in active/selected state

    Returns:
        Complete stylesheet for a chip QPushButton
    """
    bg = bg_color or theme.chip_bg
    border = theme.focus if active else theme.chip_border
    text = theme.bg if active else theme.text

    return (
        f"background: {bg.name(QColor.HexArgb)}; "
        f"color: {text.name()}; "
        f"padding: 2px 8px; "
        f"border-radius: {theme.radius_sm + 1}px; "
        f"font-size: 11px; "
        f"border: 1px solid {border.name(QColor.HexArgb)};"
    )
