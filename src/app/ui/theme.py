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
    # Semantic status colors
    status_backlog: QColor = None  # type: ignore[assignment]
    status_playing: QColor = None  # type: ignore[assignment]
    status_finished: QColor = None  # type: ignore[assignment]
    status_dropped: QColor = None  # type: ignore[assignment]
    # Semantic feedback colors
    success: QColor = None  # type: ignore[assignment]
    warning: QColor = None  # type: ignore[assignment]
    error: QColor = None  # type: ignore[assignment]
    # Surface hierarchy
    surface_raised: QColor = None  # type: ignore[assignment]
    surface_sunken: QColor = None  # type: ignore[assignment]
    # Header gradient
    header_bg: QColor = None  # type: ignore[assignment]
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
    radius_pill: int = 50
    # Design tokens - animation durations (ms)
    anim_fast: int = 100
    anim_normal: int = 180
    anim_slow: int = 280
    # Design tokens - elevation/shadow intensity (0-255 alpha)
    elevation_low: int = 20
    elevation_mid: int = 40
    elevation_high: int = 70
    # Layout dimensions
    sidebar_width_min: int = 220
    sidebar_width_max: int = 320
    details_width_min: int = 340
    details_width_max: int = 520
    toolbar_height: int = 48
    grid_gap: int = 14
    grid_padding: int = 16


def _c(r: int, g: int, b: int, a: int = 255) -> QColor:
    return QColor(r, g, b, a)


THEMES: Dict[str, ThemeSpec] = {
    "dark": ThemeSpec(
        name="Dark",
        bg=_c(20, 23, 30),
        surface=_c(30, 34, 44),
        surface_alt=_c(40, 45, 55),
        card=_c(36, 42, 52),
        card_border=_c(50, 56, 68),
        card_hover=_c(80, 105, 130),
        text=_c(235, 238, 245),
        text_muted=_c(150, 158, 172),
        accent=_c(92, 193, 255),
        accent_alt=_c(255, 203, 92),
        chip_bg=_c(52, 61, 75),
        chip_border=_c(70, 83, 98),
        focus=_c(92, 193, 255),
        outline=_c(50, 56, 68),
        shadow=_c(0, 0, 0, 150),
        status_backlog=_c(120, 170, 230),
        status_playing=_c(80, 210, 130),
        status_finished=_c(255, 190, 70),
        status_dropped=_c(220, 100, 80),
        success=_c(80, 210, 130),
        warning=_c(255, 190, 70),
        error=_c(230, 75, 60),
        surface_raised=_c(44, 50, 62),
        surface_sunken=_c(16, 18, 24),
        header_bg=_c(24, 27, 35),
    ),
    "light": ThemeSpec(
        name="Light",
        bg=_c(246, 249, 252),
        surface=_c(255, 255, 255),
        surface_alt=_c(240, 243, 248),
        card=_c(255, 255, 255),
        card_border=_c(228, 232, 240),
        card_hover=_c(190, 210, 240),
        text=_c(28, 32, 38),
        text_muted=_c(105, 115, 130),
        accent=_c(41, 121, 255),
        accent_alt=_c(255, 152, 0),
        chip_bg=_c(235, 240, 248),
        chip_border=_c(210, 218, 230),
        focus=_c(41, 121, 255),
        outline=_c(218, 224, 235),
        shadow=_c(0, 0, 0, 55),
        status_backlog=_c(60, 130, 220),
        status_playing=_c(40, 180, 100),
        status_finished=_c(230, 160, 20),
        status_dropped=_c(210, 80, 60),
        success=_c(40, 180, 100),
        warning=_c(230, 160, 20),
        error=_c(220, 60, 50),
        surface_raised=_c(255, 255, 255),
        surface_sunken=_c(234, 238, 244),
        header_bg=_c(255, 255, 255),
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
        status_backlog=_c(72, 133, 237),
        status_playing=_c(46, 196, 100),
        status_finished=_c(255, 200, 0),
        status_dropped=_c(255, 94, 91),
        success=_c(46, 196, 100),
        warning=_c(255, 200, 0),
        error=_c(255, 94, 91),
        surface_raised=_c(255, 255, 255),
        surface_sunken=_c(238, 238, 238),
        header_bg=_c(255, 255, 255),
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
        status_backlog=_c(100, 140, 210),
        status_playing=_c(0, 191, 165),
        status_finished=_c(255, 180, 50),
        status_dropped=_c(210, 90, 70),
        success=_c(0, 191, 165),
        warning=_c(255, 180, 50),
        error=_c(210, 70, 60),
        surface_raised=_c(240, 245, 252),
        surface_sunken=_c(215, 220, 228),
        header_bg=_c(230, 235, 243),
    ),
    "glassmorphism": ThemeSpec(
        name="Glassmorphism",
        bg=_c(12, 18, 30),
        surface=_c(20, 28, 44, 180),
        surface_alt=_c(28, 38, 58, 200),
        card=_c(32, 46, 70, 210),
        card_border=_c(92, 193, 255, 70),
        card_hover=_c(92, 193, 255, 130),
        text=_c(235, 242, 255),
        text_muted=_c(160, 180, 210),
        accent=_c(92, 193, 255),
        accent_alt=_c(255, 255, 255),
        chip_bg=_c(92, 193, 255, 40),
        chip_border=_c(92, 193, 255, 90),
        focus=_c(92, 193, 255),
        outline=_c(72, 120, 160, 80),
        shadow=_c(0, 0, 0, 120),
        status_backlog=_c(100, 180, 255),
        status_playing=_c(80, 230, 150),
        status_finished=_c(255, 200, 80),
        status_dropped=_c(255, 110, 90),
        success=_c(80, 230, 150),
        warning=_c(255, 200, 80),
        error=_c(255, 90, 70),
        surface_raised=_c(38, 54, 80, 220),
        surface_sunken=_c(10, 14, 24),
        header_bg=_c(16, 22, 36, 220),
    ),
    "high_contrast": ThemeSpec(
        name="High Contrast",
        bg=_c(0, 0, 0),
        surface=_c(0, 0, 0),
        surface_alt=_c(20, 20, 20),
        card=_c(0, 0, 0),
        card_border=_c(255, 255, 255),
        card_hover=_c(255, 255, 0),
        text=_c(255, 255, 255),
        text_muted=_c(255, 255, 255),
        accent=_c(0, 255, 255),
        accent_alt=_c(255, 255, 0),
        chip_bg=_c(0, 0, 0),
        chip_border=_c(255, 255, 255),
        focus=_c(255, 255, 0),
        outline=_c(255, 255, 255),
        shadow=_c(255, 255, 255, 80),
        status_backlog=_c(0, 255, 255),
        status_playing=_c(0, 255, 0),
        status_finished=_c(255, 255, 0),
        status_dropped=_c(255, 0, 0),
        success=_c(0, 255, 0),
        warning=_c(255, 255, 0),
        error=_c(255, 0, 0),
        surface_raised=_c(30, 30, 30),
        surface_sunken=_c(0, 0, 0),
        header_bg=_c(0, 0, 0),
        # Larger focus indicators for accessibility
        radius_sm=4,
        radius_md=6,
        radius_lg=8,
        radius_xl=10,
    ),
}

FONTS = {
    "Segoe UI": "Segoe UI",
    "Arial": "Arial",
    "Calibri": "Calibri",
    "Consolas": "Consolas",
}

FONT_SCALES = {"small": 0.9, "default": 1.0, "large": 1.15}

# Accessibility: reduced motion preference
_reduced_motion: bool = False


def set_reduced_motion(enabled: bool) -> None:
    """Enable or disable reduced motion for accessibility."""
    global _reduced_motion
    _reduced_motion = enabled


def is_reduced_motion() -> bool:
    """Check if reduced motion is enabled."""
    return _reduced_motion


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
        background: transparent;
        width: 8px;
        border-radius: 4px;
        margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: rgba({theme.text_muted.red()},{theme.text_muted.green()},{theme.text_muted.blue()},60);
        border-radius: 3px;
        min-height: 40px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: rgba({theme.text_muted.red()},{theme.text_muted.green()},{theme.text_muted.blue()},120);
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        border-radius: 4px;
        margin: 2px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba({theme.text_muted.red()},{theme.text_muted.green()},{theme.text_muted.blue()},60);
        border-radius: 3px;
        min-width: 40px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: rgba({theme.text_muted.red()},{theme.text_muted.green()},{theme.text_muted.blue()},120);
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
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


def focus_ring_style(theme: ThemeSpec, width: int = 2) -> str:
    """Generate focus ring styling for keyboard navigation.

    Args:
        theme: Current theme spec
        width: Border width for focus ring

    Returns:
        CSS border style for focus state
    """
    return f"border: {width}px solid {theme.focus.name(QColor.HexArgb)}; outline: none;"


def filter_chip_style(theme: ThemeSpec, active: bool = False, removable: bool = False) -> str:
    """Generate styling for active filter chips."""
    if active:
        bg = theme.accent
        text = theme.bg
        border = theme.accent.darker(110)
    else:
        bg = theme.chip_bg
        text = theme.text
        border = theme.chip_border

    return (
        f"background: {bg.name(QColor.HexArgb)}; "
        f"color: {text.name()}; "
        f"padding: 4px 12px; "
        f"border-radius: {theme.radius_md}px; "
        f"font-size: 12px; "
        f"font-weight: 500; "
        f"border: 1px solid {border.name(QColor.HexArgb)};"
    )


# --------------- Button style tiers ---------------

def primary_btn_style(theme: ThemeSpec) -> str:
    """Filled accent button for primary actions (Play, Scan)."""
    return (
        f"QPushButton {{ "
        f"background: {theme.accent.name()}; "
        f"color: {theme.bg.name()}; "
        f"border: none; "
        f"border-radius: {theme.radius_md}px; "
        f"padding: 8px 20px; "
        f"font-weight: 600; font-size: 13px; "
        f"}} "
        f"QPushButton:hover {{ background: {theme.accent.lighter(112).name()}; }} "
        f"QPushButton:pressed {{ background: {theme.accent.darker(110).name()}; }} "
        f"QPushButton:disabled {{ background: {theme.surface_alt.name(QColor.HexArgb)}; "
        f"color: {theme.text_muted.name()}; }}"
    )


def secondary_btn_style(theme: ThemeSpec) -> str:
    """Outlined accent button for secondary actions (Check Updates, Open)."""
    return (
        f"QPushButton {{ "
        f"background: transparent; "
        f"color: {theme.accent.name()}; "
        f"border: 1px solid {theme.accent.name()}; "
        f"border-radius: {theme.radius_md}px; "
        f"padding: 7px 16px; "
        f"font-weight: 500; font-size: 12px; "
        f"}} "
        f"QPushButton:hover {{ background: rgba({theme.accent.red()},{theme.accent.green()},{theme.accent.blue()},25); }} "
        f"QPushButton:pressed {{ background: rgba({theme.accent.red()},{theme.accent.green()},{theme.accent.blue()},50); }} "
        f"QPushButton:disabled {{ color: {theme.text_muted.name()}; "
        f"border-color: {theme.outline.name(QColor.HexArgb)}; }}"
    )


def ghost_btn_style(theme: ThemeSpec) -> str:
    """Borderless button for subtle actions (Settings, Close)."""
    return (
        f"QPushButton, QToolButton {{ "
        f"background: transparent; "
        f"color: {theme.text_muted.name()}; "
        f"border: none; "
        f"border-radius: {theme.radius_sm}px; "
        f"padding: 6px 10px; "
        f"font-size: 12px; "
        f"}} "
        f"QPushButton:hover, QToolButton:hover {{ "
        f"color: {theme.text.name()}; "
        f"background: {theme.surface_alt.name(QColor.HexArgb)}; }} "
        f"QPushButton:pressed, QToolButton:pressed {{ "
        f"background: {theme.surface_alt.darker(108).name(QColor.HexArgb)}; }}"
    )


def danger_btn_style(theme: ThemeSpec) -> str:
    """Red-tinted button for destructive actions (Delete, Remove)."""
    err = theme.error or _c(230, 75, 60)
    return (
        f"QPushButton {{ "
        f"background: transparent; "
        f"color: {err.name()}; "
        f"border: 1px solid {err.name()}; "
        f"border-radius: {theme.radius_md}px; "
        f"padding: 7px 16px; "
        f"font-weight: 500; font-size: 12px; "
        f"}} "
        f"QPushButton:hover {{ background: rgba({err.red()},{err.green()},{err.blue()},25); }} "
        f"QPushButton:pressed {{ background: rgba({err.red()},{err.green()},{err.blue()},50); }}"
    )


def header_bar_style(theme: ThemeSpec) -> str:
    """Style for the slim header/title bar."""
    hbg = theme.header_bg or theme.surface
    return (
        f"background: {hbg.name(QColor.HexArgb)}; "
        f"border-bottom: 1px solid {theme.outline.name(QColor.HexArgb)};"
    )


def section_header_style(theme: ThemeSpec) -> str:
    """Style for section headers (uppercase, small, muted)."""
    return (
        f"color: {theme.text_muted.name()}; "
        f"font-size: 10px; font-weight: 700; "
        f"letter-spacing: 1px; "
        f"padding: {theme.spacing_sm}px {theme.spacing_sm}px {theme.spacing_xs}px; "
        f"border: none; background: transparent;"
    )


def status_color(theme: ThemeSpec, status: str) -> QColor:
    """Get the semantic color for a game status."""
    mapping = {
        "backlog": theme.status_backlog,
        "playing": theme.status_playing,
        "finished": theme.status_finished,
        "dropped": theme.status_dropped,
    }
    return mapping.get(status) or theme.accent


def sidebar_item_style(theme: ThemeSpec) -> str:
    """Style for sidebar navigation items."""
    return f"""
        QListWidget {{
            background: transparent;
            border: none;
            outline: none;
        }}
        QListWidget::item {{
            padding: {theme.spacing_sm}px {theme.spacing_md}px;
            border-radius: {theme.radius_sm}px;
            margin: 2px {theme.spacing_xs}px;
            border: none;
        }}
        QListWidget::item:selected {{
            background: rgba({theme.accent.red()},{theme.accent.green()},{theme.accent.blue()},30);
            color: {theme.accent.name()};
        }}
        QListWidget::item:hover:!selected {{
            background: {theme.surface_alt.name(QColor.HexArgb)};
        }}
    """
