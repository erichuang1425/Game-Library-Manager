"""
Skeleton card widget for loading state.

Displays a placeholder card with gradient sweep shimmer animation
that matches the actual card layout (icon area + title + chips row).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    Qt, QEasingCurve, QPropertyAnimation, QRectF, QTimer, Property,
)
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy,
    QGraphicsOpacityEffect,
)
from PySide6.QtGui import QColor, QPainter, QLinearGradient

from app.ui.theme import current_theme, card_style, is_reduced_motion


class ShimmerFrame(QFrame):
    """A frame with a gradient sweep shimmer effect."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._shimmer_pos: float = -0.3
        self._base_color = QColor(128, 128, 128, 30)
        self._highlight_color = QColor(255, 255, 255, 50)

    def set_colors(self, base: QColor, highlight: QColor) -> None:
        self._base_color = base
        self._highlight_color = highlight

    def set_shimmer_pos(self, pos: float) -> None:
        self._shimmer_pos = pos
        self.update()

    def shimmer_pos(self) -> float:
        return self._shimmer_pos

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        # Draw gradient sweep overlay
        gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
        transparent = QColor(0, 0, 0, 0)
        pos = max(0.0, min(1.0, self._shimmer_pos))
        width = 0.3  # shimmer band width

        gradient.setColorAt(max(0.0, pos - width), transparent)
        gradient.setColorAt(pos, self._highlight_color)
        gradient.setColorAt(min(1.0, pos + width), transparent)

        painter.fillRect(rect, gradient)
        painter.end()

    # Qt property for QPropertyAnimation
    shimmerPos = Property(float, shimmer_pos, set_shimmer_pos)


class SkeletonCard(QFrame):
    """Placeholder card shown during loading with gradient sweep shimmer."""

    def __init__(self, view_mode: str = "comfortable", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        theme = current_theme()
        pad = theme.spacing_md if view_mode == "comfortable" else theme.spacing_sm

        self.setStyleSheet(f"QFrame {{ {card_style(theme)} }}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(220 if view_mode == "comfortable" else 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(6 if view_mode == "comfortable" else 4)

        base = theme.surface_alt
        highlight = QColor(
            min(255, base.red() + 30),
            min(255, base.green() + 30),
            min(255, base.blue() + 30),
            80,
        )

        # Skeleton icon area (matches card icon proportion)
        self._icon_skeleton = ShimmerFrame()
        self._icon_skeleton.set_colors(base, highlight)
        self._icon_skeleton.setStyleSheet(
            f"background: {base.name(QColor.HexArgb)}; "
            f"border-radius: {theme.radius_md}px;"
        )
        icon_ratio = 0.65 if view_mode == "comfortable" else 0.55
        self._icon_skeleton.setMinimumHeight(int(self.minimumHeight() * icon_ratio))
        layout.addWidget(self._icon_skeleton)

        # Skeleton title bar
        self._title_skeleton = ShimmerFrame()
        self._title_skeleton.set_colors(base, highlight)
        self._title_skeleton.setFixedHeight(16)
        self._title_skeleton.setStyleSheet(
            f"background: {base.lighter(105).name(QColor.HexArgb)}; "
            f"border-radius: 4px;"
        )
        layout.addWidget(self._title_skeleton)

        # Skeleton meta line (rating + time)
        self._meta_skeleton = ShimmerFrame()
        self._meta_skeleton.set_colors(base, highlight)
        self._meta_skeleton.setFixedHeight(12)
        self._meta_skeleton.setFixedWidth(140)
        self._meta_skeleton.setStyleSheet(
            f"background: {base.name(QColor.HexArgb)}; "
            f"border-radius: 3px;"
        )
        layout.addWidget(self._meta_skeleton)

        # Skeleton tag chips row (only in comfortable mode)
        if view_mode == "comfortable":
            chips_row = QHBoxLayout()
            chips_row.setContentsMargins(0, 2, 0, 0)
            chips_row.setSpacing(4)
            for w in (60, 48, 36):
                chip = ShimmerFrame()
                chip.set_colors(base, highlight)
                chip.setFixedHeight(18)
                chip.setFixedWidth(w)
                chip.setStyleSheet(
                    f"background: {base.name(QColor.HexArgb)}; "
                    f"border-radius: {theme.radius_sm - 2}px;"
                )
                chips_row.addWidget(chip)
                setattr(self, f"_chip_{w}", chip)
            chips_row.addStretch(1)
            layout.addLayout(chips_row)

        layout.addStretch(1)

        # Shimmer animation using gradient sweep
        self._shimmer_anims: list = []
        if not is_reduced_motion():
            # Collect all shimmer frames
            shimmer_frames = [
                self._icon_skeleton, self._title_skeleton, self._meta_skeleton,
            ]
            for attr in ("_chip_60", "_chip_48", "_chip_36"):
                if hasattr(self, attr):
                    shimmer_frames.append(getattr(self, attr))

            for i, frame in enumerate(shimmer_frames):
                anim = QPropertyAnimation(frame, b"shimmerPos", self)
                anim.setDuration(1800)
                anim.setStartValue(-0.3)
                anim.setEndValue(1.3)
                anim.setEasingCurve(QEasingCurve.InOutSine)
                anim.setLoopCount(-1)
                self._shimmer_anims.append(anim)
                # Stagger start for wave effect
                QTimer.singleShot(i * 80, anim.start)

    def stop_animation(self) -> None:
        """Stop all shimmer animations."""
        for anim in self._shimmer_anims:
            anim.stop()
