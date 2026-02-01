"""Color extraction service for ambient accent system.

Extracts dominant colors from game icons to create dynamic, contextual UI accents.
"""
from __future__ import annotations
from functools import lru_cache
from typing import Tuple, Optional

from PySide6.QtGui import QPixmap, QColor, QImage


def _rgb_to_hsv(r: int, g: int, b: int) -> Tuple[float, float, float]:
    """Convert RGB to HSV color space."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    df = mx - mn

    if mx == mn:
        h = 0
    elif mx == r:
        h = (60 * ((g - b) / df) + 360) % 360
    elif mx == g:
        h = (60 * ((b - r) / df) + 120) % 360
    else:
        h = (60 * ((r - g) / df) + 240) % 360

    s = 0 if mx == 0 else (df / mx)
    v = mx
    return h, s, v


def extract_dominant_color(pixmap: QPixmap, sample_size: int = 32) -> Optional[QColor]:
    """Extract the dominant vibrant color from a pixmap.

    Samples the center region of the image and finds the most saturated,
    reasonably bright color to use as an accent.

    Args:
        pixmap: Source image
        sample_size: Size to scale down to for sampling (smaller = faster)

    Returns:
        QColor of the dominant accent color, or None if extraction fails
    """
    if pixmap.isNull():
        return None

    # Scale down for faster processing
    scaled = pixmap.scaled(sample_size, sample_size)
    image = scaled.toImage()

    if image.isNull():
        return None

    # Sample pixels and find most vibrant
    color_scores: dict[Tuple[int, int, int], float] = {}

    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            r, g, b = pixel.red(), pixel.green(), pixel.blue()

            # Skip near-black and near-white pixels
            if r + g + b < 60 or r + g + b > 700:
                continue

            h, s, v = _rgb_to_hsv(r, g, b)

            # Score based on saturation and brightness
            # Prefer saturated colors that aren't too dark or too bright
            score = s * 0.6 + (0.3 if 0.3 < v < 0.9 else 0.1)

            # Quantize to reduce noise
            key = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
            color_scores[key] = color_scores.get(key, 0) + score

    if not color_scores:
        return None

    # Get highest scoring color
    best = max(color_scores, key=color_scores.get)
    return QColor(best[0], best[1], best[2])


def extract_palette(pixmap: QPixmap, count: int = 3) -> list[QColor]:
    """Extract a palette of dominant colors from a pixmap.

    Args:
        pixmap: Source image
        count: Number of colors to extract

    Returns:
        List of QColors representing the palette
    """
    if pixmap.isNull():
        return []

    scaled = pixmap.scaled(48, 48)
    image = scaled.toImage()

    if image.isNull():
        return []

    # Collect color buckets
    buckets: dict[Tuple[int, int, int], list[Tuple[int, int, int]]] = {}

    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            r, g, b = pixel.red(), pixel.green(), pixel.blue()

            # Skip near-black and near-white
            if r + g + b < 45 or r + g + b > 720:
                continue

            # Quantize to bucket
            key = (r // 32 * 32, g // 32 * 32, b // 32 * 32)
            if key not in buckets:
                buckets[key] = []
            buckets[key].append((r, g, b))

    if not buckets:
        return []

    # Sort by bucket size and pick top N
    sorted_buckets = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)

    palette = []
    for key, pixels in sorted_buckets[:count]:
        # Average the pixels in this bucket
        avg_r = sum(p[0] for p in pixels) // len(pixels)
        avg_g = sum(p[1] for p in pixels) // len(pixels)
        avg_b = sum(p[2] for p in pixels) // len(pixels)
        palette.append(QColor(avg_r, avg_g, avg_b))

    return palette


def color_for_overlay(base_color: QColor, opacity: int = 40) -> QColor:
    """Create a translucent overlay color from a base color.

    Args:
        base_color: The source color
        opacity: Alpha value (0-255)

    Returns:
        QColor with adjusted opacity suitable for overlays
    """
    return QColor(base_color.red(), base_color.green(), base_color.blue(), opacity)


def contrasting_text_color(bg_color: QColor) -> QColor:
    """Determine whether white or black text works best on a background.

    Args:
        bg_color: Background color

    Returns:
        QColor (white or near-black) for readable text
    """
    # Calculate relative luminance
    luminance = (0.299 * bg_color.red() + 0.587 * bg_color.green() + 0.114 * bg_color.blue()) / 255
    return QColor(20, 20, 20) if luminance > 0.5 else QColor(245, 245, 245)
