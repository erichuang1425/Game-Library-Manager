"""Typography scale system for consistent text hierarchy."""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QColor


@dataclass(frozen=True)
class TypeScale:
    """Typography scale based on a base size and multiplier."""
    base: int = 11

    @property
    def caption(self) -> int:
        return int(self.base * 0.82)  # ~9px

    @property
    def body(self) -> int:
        return self.base  # 11px

    @property
    def body_lg(self) -> int:
        return int(self.base * 1.1)  # ~12px

    @property
    def heading(self) -> int:
        return int(self.base * 1.27)  # ~14px

    @property
    def title(self) -> int:
        return int(self.base * 1.45)  # ~16px

    @property
    def display(self) -> int:
        return int(self.base * 1.64)  # ~18px


# Pre-defined scales for font size preferences
SCALES = {
    "small": TypeScale(base=10),
    "default": TypeScale(base=11),
    "large": TypeScale(base=13),
}


def get_scale(name: str = "default") -> TypeScale:
    """Get a typography scale by name."""
    return SCALES.get(name, SCALES["default"])


def text_style(
    size: int,
    weight: int = 400,
    color: "QColor | str | None" = None,
    muted: bool = False,
    line_height: float | None = None,
) -> str:
    """
    Generate a stylesheet string for text styling.

    Args:
        size: Font size in pixels
        weight: Font weight (400=normal, 500=medium, 600=semibold, 700=bold)
        color: QColor or hex string for text color
        muted: If True and no color specified, will need theme's text_muted
        line_height: Optional line-height multiplier

    Returns:
        CSS-style string for use in setStyleSheet()
    """
    parts = [f"font-size: {size}px", f"font-weight: {weight}"]

    if color is not None:
        if hasattr(color, 'name'):
            parts.append(f"color: {color.name()}")
        else:
            parts.append(f"color: {color}")

    if line_height is not None:
        parts.append(f"line-height: {line_height}")

    return "; ".join(parts) + ";"


def label_style(theme, scale: TypeScale | None = None) -> str:
    """Style for form labels."""
    s = scale or get_scale()
    return text_style(s.body, weight=500, color=theme.text_muted)


def heading_style(theme, scale: TypeScale | None = None) -> str:
    """Style for section headings."""
    s = scale or get_scale()
    return text_style(s.heading, weight=600, color=theme.text)


def title_style(theme, scale: TypeScale | None = None) -> str:
    """Style for panel/card titles."""
    s = scale or get_scale()
    return text_style(s.title, weight=700, color=theme.text)


def caption_style(theme, scale: TypeScale | None = None) -> str:
    """Style for small captions and metadata."""
    s = scale or get_scale()
    return text_style(s.caption, weight=400, color=theme.text_muted)


def body_style(theme, scale: TypeScale | None = None) -> str:
    """Style for body text."""
    s = scale or get_scale()
    return text_style(s.body, weight=400, color=theme.text)
